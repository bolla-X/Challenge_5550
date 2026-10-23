"""Gestão de EPIs: colaboradores, catálogo com CA, entregas e ocorrências (ES Sprint 4).

Contrato com o frontend: docs/specs/es-sprint4-contrato-gestao.md.

Princípios:

- cadastro ADMINISTRATIVO, separado da visão: nada aqui liga colaborador a ID de rastreio, câmera ou imagem;
- situações (CA `valido`/`a_vencer`/`vencido`, entrega `vigente`/`troca_vencida`/`devolvido`) são CALCULADAS contra
  a data de hoje (hora local do servidor) a cada leitura, nunca gravadas. A regra vive nos modelos (`EpiCatalogo.situacao_ca`,
  `EntregaEpi.situacao`); aqui só se consulta. `hoje()` e `agora()` são os relógios: quem chama pode injetar outros;
- ler não é usar: colaborador desligado e EPI com CA vencido continuam legíveis (cadastro, histórico, relatório), mas o
  servidor RECUSA nova entrega para eles (`garantir_colaborador_operacional`, `garantir_epi_operacional`). A tela
  também esconde, mas a trava de verdade é esta;
- o CA vencido bloquear a entrega é POLÍTICA DA EMPRESA, não uma exigência literal da norma. A NR-6 (item 6.5.1) pede o
  registro do fornecimento e, se for sistema eletrônico, a extração de relatórios (6.5.1.1): é o que a exportação CSV atende.
"""

from __future__ import annotations

import csv
import io
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Mapping

from sqlalchemy import and_, func

from app.extensions import db
from app.models import (
    CA_A_VENCER,
    CA_VENCIDO,
    CATEGORIAS_DE_EPI,
    ENTREGA_DEVOLVIDO,
    ENTREGA_MOTIVOS,
    ENTREGA_TROCA_VENCIDA,
    ENTREGA_VIGENTE,
    OCORRENCIA_ABERTA,
    OCORRENCIA_ENCERRADA,
    OCORRENCIA_GRAVIDADES,
    OCORRENCIA_STATUS,
    OCORRENCIA_TIPOS,
    Alert,
    Colaborador,
    EntregaEpi,
    EpiCatalogo,
    Ocorrencia,
    _aware,
)
from app.repositories.event_repository import EventRepository
from app.services.alertas_simulados import e_simulado, so_simulados

ATIVOS, INATIVOS, TODOS = "ativos", "inativos", "todos"
SITUACOES_DE_CA = ("valido", CA_A_VENCER, CA_VENCIDO)
SITUACOES_DE_ENTREGA = (ENTREGA_VIGENTE, ENTREGA_TROCA_VENCIDA, ENTREGA_DEVOLVIDO)
RECURSOS_DE_EXPORTACAO = ("colaboradores", "epis", "entregas", "ocorrencias", "alertas")
LIMITE_DA_LISTAGEM = 1000
LIMITE_DA_EXPORTACAO = 50000
DIAS_DO_RESUMO = 30
TAMANHO_MAXIMO_DA_BUSCA = 100
ANO_MINIMO = 1900
TOLERANCIA_DO_RELOGIO = timedelta(minutes=5)  # `ocorrida_em` pode estar até 5 min à frente do servidor


class ErroDeGestao(ValueError):
    """Entrada inválida ou regra de negócio violada. `message` já vem em pt-BR; `code` é estável para a UI."""

    def __init__(self, message: str, code: str = "campo_invalido", status: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status


def hoje() -> date:
    return date.today()


def agora() -> datetime:
    return datetime.now(timezone.utc)


def _data_br(dia: date) -> str:
    return dia.strftime("%d/%m/%Y")


# ----------------------------------------------------------------- validação ---
def _corpo(corpo: Any, rotulo: str) -> dict[str, Any]:
    if not isinstance(corpo, dict):
        raise ErroDeGestao(f"Preencha os dados d{rotulo}.")
    return corpo


def _texto(corpo: Mapping[str, Any], campo: str, rotulo: str, maximo: int, *, obrigatorio: bool = True) -> str:
    """`rotulo` é o nome que a pessoa vê ("o nome"); o nome do campo da API nunca aparece na mensagem."""
    valor = corpo.get(campo)
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        if obrigatorio:
            raise ErroDeGestao(f"Informe {rotulo}.")
        return ""
    if not isinstance(valor, str):
        raise ErroDeGestao(f"Escreva {rotulo} em texto.")
    texto = valor.strip()
    if len(texto) > maximo:
        raise ErroDeGestao(f"{rotulo.capitalize()} aceita no máximo {maximo} caracteres.")
    return texto


def _ano_plausivel(ano: int, rotulo: str) -> None:
    """Recusa ano absurdo (0001, 9999): `entregue_em + vida útil` estouraria em OverflowError e viraria 500."""
    if not ANO_MINIMO <= ano <= hoje().year + 1:
        raise ErroDeGestao(f"Informe {rotulo} com um ano entre {ANO_MINIMO} e {hoje().year + 1}.")


def _data(corpo: Mapping[str, Any], campo: str, rotulo: str, *, obrigatorio: bool = True) -> date | None:
    valor = corpo.get(campo)
    if valor is None or valor == "":
        if obrigatorio:
            raise ErroDeGestao(f"Informe {rotulo}.")
        return None
    try:
        if not isinstance(valor, str):
            raise ValueError
        dia = date.fromisoformat(valor.strip())
    except ValueError:
        raise ErroDeGestao(f"Informe {rotulo} no formato AAAA-MM-DD.") from None
    _ano_plausivel(dia.year, rotulo)
    return dia


def _inteiro(corpo: Mapping[str, Any], campo: str, rotulo: str, minimo: int, maximo: int, *, obrigatorio: bool = True) -> int | None:
    valor = corpo.get(campo)
    if valor is None or valor == "":
        if obrigatorio:
            raise ErroDeGestao(f"Informe {rotulo}.")
        return None
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise ErroDeGestao(f"Informe {rotulo} como número inteiro.")
    if not minimo <= valor <= maximo:
        raise ErroDeGestao(f"Informe {rotulo} entre {minimo} e {maximo}.")
    return valor


def _escolha(corpo: Mapping[str, Any], campo: str, rotulo: str, opcoes: Iterable[str]) -> str:
    valor = corpo.get(campo)
    if not isinstance(valor, str) or valor not in tuple(opcoes):
        raise ErroDeGestao(f"Escolha {rotulo} da lista.")
    return valor


def _instante(corpo: Mapping[str, Any], campo: str, rotulo: str) -> datetime | None:
    """ISO 8601. Sem fuso vale UTC (mesma convenção da busca nas trilhas)."""
    valor = corpo.get(campo)
    if valor is None or valor == "":
        return None
    try:
        if not isinstance(valor, str):
            raise ValueError
        instante = _aware(datetime.fromisoformat(valor.strip())).astimezone(timezone.utc)
    except (ValueError, OverflowError):
        raise ErroDeGestao(f"Informe {rotulo} no formato AAAA-MM-DDThh:mm.") from None
    _ano_plausivel(instante.year, rotulo)
    return instante


def _com_atuais(item: Any, campos: Iterable[str], corpo: Mapping[str, Any]) -> dict[str, Any]:
    """Edição parcial: o que não vem no corpo fica como está (o item novo não tem atuais)."""
    atuais = {}
    for campo in campos:
        valor = getattr(item, campo)
        if valor is not None:
            atuais[campo] = valor.isoformat() if isinstance(valor, date) else valor
    return {**atuais, **corpo}


def buscar(modelo: type, ident: int, code: str, mensagem: str) -> Any:
    item = db.session.get(modelo, ident)
    if item is None:
        raise ErroDeGestao(mensagem, code, 404)
    return item


# -------------------------------------------------------------- colaboradores ---
CAMPOS_DO_COLABORADOR = ("matricula", "nome", "setor", "funcao", "admissao")


def aplicar_colaborador(colaborador: Colaborador, corpo: Any) -> Colaborador:
    """Valida o corpo e o copia para o colaborador (sem gravar). Em edição, o que não vier fica como está."""
    corpo = _com_atuais(colaborador, CAMPOS_DO_COLABORADOR, _corpo(corpo, "o colaborador"))
    matricula = _texto(corpo, "matricula", "a matrícula", 32).upper()
    nome = _texto(corpo, "nome", "o nome", 160)
    setor = _texto(corpo, "setor", "o setor", 120)
    funcao = _texto(corpo, "funcao", "a função", 120)
    admissao = _data(corpo, "admissao", "a data de admissão")
    ativo = corpo.get("ativo", colaborador.ativo if colaborador.ativo is not None else True)
    if not isinstance(ativo, bool):
        raise ErroDeGestao("Informe se o colaborador está ativo (sim ou não).")
    repetido = Colaborador.query.filter(Colaborador.matricula == matricula, Colaborador.id != (colaborador.id or 0)).first()
    if repetido is not None:
        raise ErroDeGestao(f"A matrícula {matricula} já está cadastrada.", "matricula_duplicada", 409)
    colaborador.matricula, colaborador.nome, colaborador.setor = matricula, nome, setor
    colaborador.funcao, colaborador.admissao, colaborador.ativo = funcao, admissao, ativo
    return colaborador


def _filtro_de_atividade(consulta, atividade: str):
    if atividade == ATIVOS:
        return consulta.filter(Colaborador.ativo.is_(True))
    if atividade == INATIVOS:
        return consulta.filter(Colaborador.ativo.is_(False))
    return consulta


def _pagina(itens: list) -> tuple[list, bool]:
    """As listagens pedem LIMITE+1 linhas: a que sobra só diz que há mais (`truncado`) e não é devolvida."""
    return itens[:LIMITE_DA_LISTAGEM], len(itens) > LIMITE_DA_LISTAGEM


def consultar_colaboradores(*, busca: str = "", setor: str = "", atividade: str = TODOS) -> tuple[list[Colaborador], bool]:
    """Base ÚNICA das listagens de colaborador: busca, setor, atividade e ordem. Use um dos dois invólucros abaixo."""
    consulta = _filtro_de_atividade(Colaborador.query, atividade)
    if setor:
        consulta = consulta.filter(Colaborador.setor == setor)
    busca = busca.strip()[:TAMANHO_MAXIMO_DA_BUSCA].lower()
    if busca:
        # % e _ digitados valem como texto, não como curinga do LIKE
        termo = "%" + busca.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        consulta = consulta.filter(db.or_(
            func.lower(Colaborador.nome).like(termo, escape="\\"),
            func.lower(Colaborador.matricula).like(termo, escape="\\"),
        ))
    return _pagina(consulta.order_by(Colaborador.nome.asc(), Colaborador.id.asc()).limit(LIMITE_DA_LISTAGEM + 1).all())


def listar_colaboradores_gestao(*, busca: str = "", setor: str = "", atividade: str = TODOS) -> tuple[list[Colaborador], bool]:
    """Visão de GESTÃO: vê ativos e desligados (o histórico não some)."""
    return consultar_colaboradores(busca=busca, setor=setor, atividade=atividade)


def listar_colaboradores_operacionais(*, busca: str = "", setor: str = "") -> tuple[list[Colaborador], bool]:
    """Visão OPERACIONAL (quem pode receber entrega): só ativos."""
    return consultar_colaboradores(busca=busca, setor=setor, atividade=ATIVOS)


def garantir_colaborador_operacional(colaborador: Colaborador) -> None:
    """Trava de escrita: colaborador desligado continua legível, mas não recebe entrega nova."""
    if not colaborador.ativo:
        raise ErroDeGestao(
            f"{colaborador.nome} está desligado(a): reative o cadastro antes de registrar uma nova entrega.",
            "colaborador_inativo", 409,
        )


def setores_dos_colaboradores() -> list[str]:
    return [linha[0] for linha in db.session.query(Colaborador.setor).distinct().order_by(Colaborador.setor.asc()).all()]


def colaborador_para_api(colaborador: Colaborador, contagens: Mapping[int, tuple[int, int]]) -> dict[str, Any]:
    vigentes, pendencias = contagens.get(colaborador.id, (0, 0))
    return {**colaborador.to_dict(), "entregas_vigentes": vigentes, "pendencias": pendencias}


def contagens_por_colaborador(ids: Iterable[int], dia: date) -> dict[int, tuple[int, int]]:
    """`{colaborador_id: (entregas_vigentes, pendencias)}`.

    Pendência = entrega em aberto cuja troca venceu OU cujo EPI está com o CA vencido (precisa ser substituída).
    """
    ids = list(ids)
    if not ids:
        return {}
    contagens: dict[int, list[int]] = {}
    abertas = EntregaEpi.query.filter(EntregaEpi.devolvido_em.is_(None), EntregaEpi.colaborador_id.in_(ids)).all()
    for entrega in abertas:
        situacao = entrega.situacao(dia)
        linha = contagens.setdefault(entrega.colaborador_id, [0, 0])
        if situacao == ENTREGA_VIGENTE:
            linha[0] += 1
        if situacao == ENTREGA_TROCA_VENCIDA or entrega.epi.situacao_ca(dia) == CA_VENCIDO:
            linha[1] += 1
    return {ident: (v, p) for ident, (v, p) in contagens.items()}


# ------------------------------------------------------------------- catálogo ---
CAMPOS_DO_EPI = ("nome", "categoria", "ca", "validade_ca", "fabricante", "vida_util_dias")


def aplicar_epi(epi: EpiCatalogo, corpo: Any) -> EpiCatalogo:
    """Valida o corpo e o copia para o item do catálogo (sem gravar). Em edição, o que não vier fica como está."""
    corpo = _com_atuais(epi, CAMPOS_DO_EPI, _corpo(corpo, "o item"))
    nome = _texto(corpo, "nome", "o nome do EPI", 160)
    categoria = _escolha(corpo, "categoria", "uma categoria", CATEGORIAS_DE_EPI)
    ca = _texto(corpo, "ca", "o número do CA", 20)
    validade = _data(corpo, "validade_ca", "a validade do CA")
    fabricante = _texto(corpo, "fabricante", "o fabricante", 160)
    vida_util = _inteiro(corpo, "vida_util_dias", "a vida útil em dias", 1, 3650)
    repetido = EpiCatalogo.query.filter(EpiCatalogo.ca == ca, EpiCatalogo.id != (epi.id or 0)).first()
    if repetido is not None:
        raise ErroDeGestao(f"O CA {ca} já está no catálogo ({repetido.nome}).", "ca_duplicado", 409)
    epi.nome, epi.categoria, epi.ca, epi.validade_ca = nome, categoria, ca, validade
    epi.fabricante, epi.vida_util_dias = fabricante, vida_util
    return epi


def garantir_epi_operacional(epi: EpiCatalogo, dia: date) -> None:
    """Trava de escrita: item com CA vencido continua no catálogo e no histórico, mas não é entregue.

    Conferido contra HOJE. Como a data da entrega nunca passa de hoje (ver `registrar_entrega`), um CA vencido antes da
    data da entrega (`validade_ca < entregue_em`) já está vencido hoje: uma checagem só cobre as duas.
    """
    if epi.situacao_ca(dia) == CA_VENCIDO:
        raise ErroDeGestao(
            f"O CA {epi.ca} deste EPI venceu em {_data_br(epi.validade_ca)}: a entrega fica bloqueada pela política da "
            "empresa. Atualize a validade no catálogo (supervisor) quando houver CA renovado.",
            "ca_vencido", 409,
        )


def filtro_de_situacao(situacao: str, dia: date):
    """A MESMA regra de `EntregaEpi.situacao`, em SQL (tests/test_gestao_epi.py trava que as duas concordam)."""
    if situacao == ENTREGA_DEVOLVIDO:
        return EntregaEpi.devolvido_em.is_not(None)
    em_aberto = EntregaEpi.devolvido_em.is_(None)
    if situacao == ENTREGA_TROCA_VENCIDA:
        return and_(em_aberto, EntregaEpi.troca_prevista_em < dia)
    return and_(em_aberto, EntregaEpi.troca_prevista_em >= dia)


def entregas_vigentes_por_epi(dia: date) -> dict[int, int]:
    linhas = (
        db.session.query(EntregaEpi.epi_id, func.count(EntregaEpi.id))
        .filter(filtro_de_situacao(ENTREGA_VIGENTE, dia)).group_by(EntregaEpi.epi_id).all()
    )
    return dict(linhas)


def epi_para_api(epi: EpiCatalogo, dia: date, vigentes: Mapping[int, int]) -> dict[str, Any]:
    return {**epi.to_dict(dia), "entregas_vigentes": vigentes.get(epi.id, 0)}


def listar_epis(dia: date, *, categoria: str = "", situacao: str = "") -> tuple[list[EpiCatalogo], bool]:
    if categoria and categoria not in CATEGORIAS_DE_EPI:
        raise ErroDeGestao("Escolha uma categoria da lista.", "filtro_invalido")
    if situacao and situacao not in SITUACOES_DE_CA:
        raise ErroDeGestao("Escolha uma situação de CA da lista.", "filtro_invalido")
    consulta = EpiCatalogo.query
    if categoria:
        consulta = consulta.filter(EpiCatalogo.categoria == categoria)
    itens = consulta.order_by(EpiCatalogo.nome.asc(), EpiCatalogo.id.asc()).limit(LIMITE_DA_LISTAGEM + 1).all()
    return _pagina([e for e in itens if not situacao or e.situacao_ca(dia) == situacao])


# -------------------------------------------------------------------- entregas ---
def _codigo(prefixo: str) -> str:
    return f"{prefixo}-{uuid.uuid4().hex[:10].upper()}"


def registrar_entrega(corpo: Any, *, por: str, dia: date) -> EntregaEpi:
    """Valida, aplica as travas (colaborador ativo, CA vigente) e devolve a entrega (sem gravar)."""
    corpo = _corpo(corpo, "a entrega")
    colaborador_id = _inteiro(corpo, "colaborador_id", "o colaborador", 1, 2**31 - 1)
    epi_id = _inteiro(corpo, "epi_id", "o EPI", 1, 2**31 - 1)
    quantidade = _inteiro(corpo, "quantidade", "a quantidade", 1, 999)
    entregue_em = _data(corpo, "entregue_em", "a data de entrega", obrigatorio=False) or dia
    if entregue_em > dia:
        raise ErroDeGestao("A data de entrega não pode ser no futuro.", "data_invalida")
    motivo = _escolha(corpo, "motivo", "o motivo", ENTREGA_MOTIVOS)
    observacao = _texto(corpo, "observacao", "a observação", 500, obrigatorio=False)
    colaborador = buscar(Colaborador, colaborador_id, "colaborador_nao_encontrado", "Colaborador não encontrado.")
    epi = buscar(EpiCatalogo, epi_id, "epi_nao_encontrado", "EPI não encontrado no catálogo.")
    garantir_colaborador_operacional(colaborador)
    garantir_epi_operacional(epi, dia)
    return EntregaEpi(
        codigo=_codigo("ENT"), colaborador=colaborador, epi=epi, ca_na_entrega=epi.ca, epi_nome_na_entrega=epi.nome,
        quantidade=quantidade, entregue_em=entregue_em, troca_prevista_em=entregue_em + timedelta(days=epi.vida_util_dias),
        motivo=motivo, observacao=observacao,
        registrado_por=por,
    )


def registrar_devolucao(entrega: EntregaEpi, corpo: Any, dia: date) -> EntregaEpi:
    """Marca a entrega como devolvida (sem gravar). Devolver não depende de colaborador ativo nem de CA: é o desligamento."""
    if entrega.devolvido_em is not None:
        raise ErroDeGestao(
            f"Esta entrega já foi devolvida em {_data_br(entrega.devolvido_em)}.", "ja_devolvido", 409)
    corpo = _corpo(corpo if corpo is not None else {}, "a devolução")
    devolvido_em = _data(corpo, "devolvido_em", "a data de devolução", obrigatorio=False) or dia
    if devolvido_em < entrega.entregue_em:
        raise ErroDeGestao("A devolução não pode ser antes da entrega.", "data_invalida")
    if devolvido_em > dia:
        raise ErroDeGestao("A data de devolução não pode ser no futuro.", "data_invalida")
    entrega.devolvido_em = devolvido_em
    return entrega


def listar_entregas(
    dia: date, *, colaborador_id: int | None = None, epi_id: int | None = None, situacao: str = "",
) -> tuple[list[EntregaEpi], bool]:
    if situacao and situacao not in SITUACOES_DE_ENTREGA:
        raise ErroDeGestao("Escolha uma situação de entrega da lista.", "filtro_invalido")
    consulta = EntregaEpi.query
    if colaborador_id is not None:
        consulta = consulta.filter(EntregaEpi.colaborador_id == colaborador_id)
    if epi_id is not None:
        consulta = consulta.filter(EntregaEpi.epi_id == epi_id)
    if situacao:
        consulta = consulta.filter(filtro_de_situacao(situacao, dia))
    return _pagina(consulta.order_by(EntregaEpi.entregue_em.desc(), EntregaEpi.id.desc()).limit(LIMITE_DA_LISTAGEM + 1).all())


# ----------------------------------------------------------------- ocorrências ---
def registrar_ocorrencia(corpo: Any, *, por: str, instante: datetime) -> Ocorrencia:
    """Valida e devolve a ocorrência nova, sempre `aberta` (sem gravar)."""
    corpo = _corpo(corpo, "a ocorrência")
    tipo = _escolha(corpo, "tipo", "o tipo", OCORRENCIA_TIPOS)
    gravidade = _escolha(corpo, "gravidade", "a gravidade", OCORRENCIA_GRAVIDADES)
    setor = _texto(corpo, "setor", "o setor", 160)
    descricao = _texto(corpo, "descricao", "a descrição", 2000)
    ocorrida_em = _instante(corpo, "ocorrida_em", "a data e hora da ocorrência") or instante
    if ocorrida_em > instante + TOLERANCIA_DO_RELOGIO:
        raise ErroDeGestao("A data e hora da ocorrência não podem ser no futuro.", "data_invalida")
    colaborador_id = _inteiro(corpo, "colaborador_id", "o colaborador", 1, 2**31 - 1, obrigatorio=False)
    alerta_id = _inteiro(corpo, "alerta_id", "o alerta", 1, 2**31 - 1, obrigatorio=False)
    if colaborador_id is not None and alerta_id is not None:
        # Privacidade: o alerta é da visão (câmera, rótulo de rastreio, imagem). Ligar uma pessoa nomeada a ele
        # transformaria o cadastro administrativo em identificação por câmera.
        raise ErroDeGestao(
            "Ocorrência ligada a um alerta da câmera não pode identificar o colaborador.", "vinculo_proibido")
    colaborador = (
        buscar(Colaborador, colaborador_id, "colaborador_nao_encontrado", "Colaborador não encontrado.")
        if colaborador_id is not None else None
    )
    if alerta_id is not None:
        buscar(Alert, alerta_id, "alerta_nao_encontrado", "Alerta não encontrado.")
    return Ocorrencia(
        codigo=_codigo("OCO"), tipo=tipo, gravidade=gravidade, setor=setor, descricao=descricao, ocorrida_em=ocorrida_em,
        status=OCORRENCIA_ABERTA, colaborador=colaborador, alerta_id=alerta_id, registrada_por=por,
    )


def atualizar_ocorrencia(ocorrencia: Ocorrencia, corpo: Any, instante: datetime) -> Ocorrencia:
    """Muda status e ação corretiva (sem gravar). Encerrar preenche `encerrada_em`; reabrir limpa."""
    corpo = _com_atuais(ocorrencia, ("status", "acao_corretiva"), _corpo(corpo, "a ocorrência"))
    status = _escolha(corpo, "status", "o status", OCORRENCIA_STATUS)
    acao = _texto(corpo, "acao_corretiva", "a ação corretiva", 2000, obrigatorio=False)
    if status == OCORRENCIA_ENCERRADA and ocorrencia.encerrada_em is None:
        ocorrencia.encerrada_em = instante
    elif status != OCORRENCIA_ENCERRADA:
        ocorrencia.encerrada_em = None
    ocorrencia.status, ocorrencia.acao_corretiva = status, acao
    return ocorrencia


def listar_ocorrencias(*, status: str = "", tipo: str = "", setor: str = "") -> tuple[list[Ocorrencia], bool]:
    if status and status not in OCORRENCIA_STATUS:
        raise ErroDeGestao("Escolha um status da lista.", "filtro_invalido")
    if tipo and tipo not in OCORRENCIA_TIPOS:
        raise ErroDeGestao("Escolha um tipo da lista.", "filtro_invalido")
    consulta = Ocorrencia.query
    if status:
        consulta = consulta.filter(Ocorrencia.status == status)
    if tipo:
        consulta = consulta.filter(Ocorrencia.tipo == tipo)
    if setor:
        consulta = consulta.filter(Ocorrencia.setor == setor)
    return _pagina(consulta.order_by(Ocorrencia.ocorrida_em.desc(), Ocorrencia.id.desc()).limit(LIMITE_DA_LISTAGEM + 1).all())


# ------------------------------------------------------------ trilha de edições ---
def instantaneo(item: Any, campos: Iterable[str]) -> dict[str, Any]:
    """Valores de `campos` em tipos que cabem no JSON do log (datas em ISO)."""
    saida = {}
    for campo in campos:
        valor = getattr(item, campo)
        if isinstance(valor, datetime):
            valor = _aware(valor).isoformat()
        elif isinstance(valor, date):
            valor = valor.isoformat()
        saida[campo] = valor
    return saida


def registrar_edicao(tipo: str, mensagem: str, *, por: str, item_id: int, antes: dict[str, Any], depois: dict[str, Any]) -> bool:
    """Grava no `EventLog` quem mudou o quê (só os campos que mudaram). Sem mudança, não grava nada.

    Chame DEPOIS do commit da edição. `EventRepository.create` faz o próprio commit.
    """
    mudados = sorted(campo for campo in depois if antes.get(campo) != depois[campo])
    if not mudados:
        return False
    EventRepository().create(
        event_type=tipo, message=f"{mensagem} por {por}: {', '.join(mudados)}"[:255], subject=por[:120],
        metadata={"id": item_id, "por": por, "antes": {c: antes.get(c) for c in mudados}, "depois": {c: depois[c] for c in mudados}},
    )
    return True


# ---------------------------------------------------------------------- resumo ---
def resumo(dia: date, instante: datetime) -> dict[str, Any]:
    desde = instante - timedelta(days=DIAS_DO_RESUMO)
    epis = EpiCatalogo.query.all()
    alertas_30d = Alert.query.filter(Alert.created_at >= desde)
    simulados = any(
        db.session.query(modelo.id).filter(modelo.ficticio.is_(True)).first() is not None
        for modelo in (Colaborador, EpiCatalogo, EntregaEpi, Ocorrencia)
    )
    return {
        "colaboradores_ativos": Colaborador.query.filter(Colaborador.ativo.is_(True)).count(),
        "epis_no_catalogo": len(epis),
        "entregas_vigentes": EntregaEpi.query.filter(filtro_de_situacao(ENTREGA_VIGENTE, dia)).count(),
        "trocas_vencidas": EntregaEpi.query.filter(filtro_de_situacao(ENTREGA_TROCA_VENCIDA, dia)).count(),
        "cas_vencidos": sum(1 for e in epis if e.situacao_ca(dia) == CA_VENCIDO),
        "cas_a_vencer": sum(1 for e in epis if e.situacao_ca(dia) == CA_A_VENCER),
        "ocorrencias_abertas": Ocorrencia.query.filter(Ocorrencia.status == OCORRENCIA_ABERTA).count(),
        "ocorrencias_30d": Ocorrencia.query.filter(Ocorrencia.ocorrida_em >= desde).count(),
        "alertas_30d": alertas_30d.count(),
        "alertas_simulados_30d": so_simulados(alertas_30d).count(),
        "simulados": simulados,
    }


# ----------------------------------------------------------------- exportação ---
def _sim_nao(valor: Any) -> str:
    return "sim" if valor else "não"


def _celula(valor: Any) -> Any:
    """Texto que o Excel/Planilhas leria como fórmula ganha um apóstrofo na frente (injeção de fórmula em CSV)."""
    if isinstance(valor, str) and valor[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + valor
    return "" if valor is None else valor


def _linhas_de_colaboradores(dia: date):
    cabecalho = ["Matrícula", "Nome", "Setor", "Função", "Admissão", "Ativo", "Dados simulados"]
    linhas = [[c.matricula, c.nome, c.setor, c.funcao, c.admissao.isoformat(), _sim_nao(c.ativo), _sim_nao(c.ficticio)]
              for c in Colaborador.query.order_by(Colaborador.matricula.asc()).limit(LIMITE_DA_EXPORTACAO + 1)]
    return cabecalho, linhas


def _linhas_de_epis(dia: date):
    cabecalho = ["Nome", "Categoria", "CA", "Validade do CA", "Situação do CA", "Dias para vencer", "Fabricante",
                 "Vida útil (dias)", "Dados simulados"]
    linhas = [[e.nome, e.categoria, e.ca, e.validade_ca.isoformat(), e.situacao_ca(dia), e.dias_para_vencer(dia), e.fabricante,
               e.vida_util_dias, _sim_nao(e.ficticio)]
              for e in EpiCatalogo.query.order_by(EpiCatalogo.nome.asc()).limit(LIMITE_DA_EXPORTACAO + 1)]
    return cabecalho, linhas


def _linhas_de_entregas(dia: date):
    cabecalho = ["Código", "Matrícula", "Colaborador", "Setor", "EPI", "CA", "Quantidade", "Entregue em", "Troca prevista em",
                 "Devolvido em", "Situação", "Motivo", "Observação", "Registrado por", "Dados simulados"]
    linhas = [
        [e.codigo, e.colaborador.matricula, e.colaborador.nome, e.colaborador.setor, e.epi_nome_na_entrega, e.ca_na_entrega, e.quantidade,
         e.entregue_em.isoformat(), e.troca_prevista_em.isoformat(), e.devolvido_em.isoformat() if e.devolvido_em else "",
         e.situacao(dia), e.motivo, e.observacao, e.registrado_por, _sim_nao(e.ficticio)]
        for e in EntregaEpi.query.order_by(EntregaEpi.entregue_em.desc(), EntregaEpi.id.desc()).limit(LIMITE_DA_EXPORTACAO + 1)
    ]
    return cabecalho, linhas


def _linhas_de_ocorrencias(dia: date):
    cabecalho = ["Código", "Tipo", "Gravidade", "Setor", "Descrição", "Ocorrida em", "Status", "Matrícula", "Colaborador",
                 "Ação corretiva", "Alerta", "Registrada por", "Encerrada em", "Dados simulados"]
    linhas = []
    for o in Ocorrencia.query.order_by(Ocorrencia.ocorrida_em.desc(), Ocorrencia.id.desc()).limit(LIMITE_DA_EXPORTACAO + 1):
        c = o.colaborador
        linhas.append([
            o.codigo, o.tipo, o.gravidade, o.setor, o.descricao, _aware(o.ocorrida_em).isoformat(), o.status,
            c.matricula if c else "", c.nome if c else "", o.acao_corretiva, o.alerta_id or "", o.registrada_por,
            _aware(o.encerrada_em).isoformat() if o.encerrada_em else "", _sim_nao(o.ficticio),
        ])
    return cabecalho, linhas


def _linhas_de_alertas(dia: date):
    """Só o que o painel já mostra (regra, gravidade, mensagem): sem metadados, caixa de pessoa nem evidência."""
    cabecalho = ["ID", "Criado em", "Câmera", "Regra", "Gravidade", "Mensagem", "Recurso", "Situação", "Falso positivo",
                 "Dados simulados"]
    alertas = Alert.query.order_by(Alert.created_at.desc(), Alert.id.desc()).limit(LIMITE_DA_EXPORTACAO + 1).all()
    linhas = [
        [a.id, _aware(a.created_at).isoformat(), a.camera_id or "", a.rule, a.severity, a.message, a.feature or "", a.status,
         _sim_nao((a.metadata_json or {}).get("false_positive")), _sim_nao(e_simulado(a))]
        for a in alertas
    ]
    return cabecalho, linhas


_EXPORTADORES = {
    "colaboradores": _linhas_de_colaboradores, "epis": _linhas_de_epis, "entregas": _linhas_de_entregas,
    "ocorrencias": _linhas_de_ocorrencias, "alertas": _linhas_de_alertas,
}


def exportar_csv(recurso: str, dia: date) -> tuple[str, bool]:
    """CSV com BOM UTF-8 e separador `;` (abre direto no Excel em pt-BR). Devolve `(texto, truncado)`."""
    if recurso not in _EXPORTADORES:
        raise ErroDeGestao("Recurso de exportação desconhecido.", "recurso_desconhecido", 404)
    cabecalho, linhas = _EXPORTADORES[recurso](dia)
    truncado = len(linhas) > LIMITE_DA_EXPORTACAO
    saida = io.StringIO()
    escritor = csv.writer(saida, delimiter=";", lineterminator="\r\n")
    escritor.writerow(cabecalho)
    for linha in linhas[:LIMITE_DA_EXPORTACAO]:
        escritor.writerow([_celula(valor) for valor in linha])
    return "\ufeff" + saida.getvalue(), truncado


def nome_do_arquivo_csv(recurso: str, dia: date) -> str:
    return f"visionepi-{recurso}-{dia.isoformat()}.csv"
