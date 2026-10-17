"""Antes/depois de uma intervenção e ROI com premissas digitadas (MISSÃO 4, M8).

Princípios:

- JANELAS IGUAIS: `janela_dias` dias antes da data da intervenção contra
  `janela_dias` dias a partir dela (dias de hora local do servidor, como a Liga);
- o tamanho da amostra vai junto de qualquer número, e o aviso "correlação não é
  causa" é fixo na resposta;
- janela "depois" ainda aberta: conta só o que já aconteceu, diz isso e NÃO
  extrapola (sem variação percentual);
- alertas marcados como falso positivo não entram na contagem;
- o ROI é só aritmética sobre números digitados pelo usuário, com a fórmula
  devolvida em texto. Nenhuma estatística oficial, média de mercado ou custo
  padrão é embutido aqui.

Limite conhecido: o sistema não grava, por período, os minutos com gente na
câmera (o contador do Andon vive em memória; a Liga só guarda os minutos
CONFORMES). Por isso a comparação NÃO calcula alertas por hora de exposição:
`exposicao.disponivel` é falso e diz por quê.
"""

from __future__ import annotations

import math
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Mapping

from app.extensions import db
from app.models import Alert, Camera, Incidente, Intervencao, PontoDaLiga
from app.services.liga import setor_da_camera
from app.utils.texto import pluralizar

AVISO = "Correlação não é causa: outras mudanças no período também contam."
AVISO_DO_ROI = (
    "Estimativa com as suas premissas. Nenhum número aqui vem de estatística oficial: "
    "se as premissas mudarem, o resultado muda."
)
MOTIVO_SEM_EXPOSICAO = (
    "O sistema não guarda, por período, os minutos com gente na câmera; por isso os alertas "
    "não são divididos por horas de exposição. Compare as contagens sabendo disso."
)
JANELA_PADRAO_DIAS = 7
JANELA_MAXIMA_DIAS = 90
LIMITE_NUMERICO = 1e12


class DadoInvalido(ValueError):
    """Entrada fora do formato. A mensagem já vem em pt-BR; `code` é estável para a UI."""

    def __init__(self, message: str, code: str = "campo_invalido") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


# ------------------------------------------------------------------ cadastro ---
def _texto(corpo: Mapping[str, Any], campo: str, rotulo: str, maximo: int, *, obrigatorio: bool) -> str:
    """`rotulo` é o nome que a pessoa vê ("o título"); o nome do campo da API nunca aparece na mensagem."""
    valor = corpo.get(campo)
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        if obrigatorio:
            raise DadoInvalido(f"Informe {rotulo}.")
        return ""
    if not isinstance(valor, str):
        raise DadoInvalido(f"Escreva {rotulo} em texto.")
    texto = valor.strip()
    if len(texto) > maximo:
        raise DadoInvalido(f"{rotulo.capitalize()} aceita no máximo {maximo} caracteres.")
    return texto


def setores_conhecidos() -> set[str]:
    return {setor_da_camera(camera) for camera in Camera.query.all()}


def aplicar(intervencao: Intervencao, corpo: Any) -> Intervencao:
    """Valida o corpo e o copia para a intervenção (sem gravar). Câmera OU setor, nunca os dois."""
    if not isinstance(corpo, dict):
        raise DadoInvalido("Preencha os dados da intervenção.")
    titulo = _texto(corpo, "titulo", "o título", 160, obrigatorio=True)
    descricao = _texto(corpo, "descricao", "a descrição", 2000, obrigatorio=False)
    bruta = corpo.get("data_da_intervencao")
    try:
        if not isinstance(bruta, str):
            raise ValueError
        dia = date.fromisoformat(bruta.strip())
    except ValueError:
        raise DadoInvalido("Informe a data da intervenção no formato AAAA-MM-DD.") from None

    camera_id = corpo.get("camera_id")
    setor = corpo.get("setor")
    setor = setor.strip() if isinstance(setor, str) else setor
    if (camera_id is None) == (not setor):
        raise DadoInvalido("Informe a câmera OU o setor da intervenção (um dos dois).", "escopo_invalido")
    if camera_id is not None:
        if isinstance(camera_id, bool) or not isinstance(camera_id, int):
            raise DadoInvalido("Escolha uma câmera da lista.")
        if db.session.get(Camera, camera_id) is None:
            raise DadoInvalido("Câmera não encontrada.", "camera_nao_encontrada")
        setor = None
    else:
        if not isinstance(setor, str) or len(setor) > 160:
            raise DadoInvalido("Escolha um setor da lista.")
        if setor not in setores_conhecidos():
            raise DadoInvalido("Setor desconhecido: use o nome de um setor das câmeras cadastradas.", "setor_desconhecido")
        camera_id = None

    intervencao.titulo = titulo
    intervencao.descricao = descricao
    intervencao.data_da_intervencao = dia
    intervencao.camera_id = camera_id
    intervencao.setor = setor
    return intervencao


def janela_valida(bruta: Any) -> int:
    if bruta is None or bruta == "":
        return JANELA_PADRAO_DIAS
    try:
        valor = int(bruta)
    except (TypeError, ValueError):
        raise DadoInvalido(f"A janela precisa ser um número inteiro de dias, de 1 a {JANELA_MAXIMA_DIAS}.") from None
    if not 1 <= valor <= JANELA_MAXIMA_DIAS:
        raise DadoInvalido(f"A janela precisa ter de 1 a {JANELA_MAXIMA_DIAS} dias.")
    return valor


# ---------------------------------------------------------------- comparação ---
def _inicio_do_dia(dia: date) -> datetime:
    """00:00 local do dia, em UTC (os instantes do banco são UTC)."""
    return datetime.combine(dia, time.min).astimezone(timezone.utc)


def _sem_fuso(valor: datetime) -> datetime:
    return valor.astimezone(timezone.utc).replace(tzinfo=None)


def _dia_local(valor: datetime) -> date:
    aware = valor.replace(tzinfo=timezone.utc) if valor.tzinfo is None else valor
    return aware.astimezone().date()


def _cameras_do_escopo(intervencao: Intervencao) -> list[int]:
    if intervencao.camera_id is not None:
        return [intervencao.camera_id]
    return [camera.id for camera in Camera.query.all() if setor_da_camera(camera) == intervencao.setor]


def _janela(camera_ids: list[int], inicio: datetime, fim: datetime) -> dict[str, Any]:
    """Contagens de [inicio, fim) para as câmeras do escopo."""
    a, b = _sem_fuso(inicio), _sem_fuso(fim)
    if not camera_ids or b <= a:
        return {"por_regra": {}, "alertas": 0, "incidentes": 0, "dias_com_dados": 0, "minutos_conformes": 0}
    falso = Alert.metadata_json["false_positive"].as_boolean()
    no_periodo = db.and_(Alert.camera_id.in_(camera_ids), Alert.created_at >= a, Alert.created_at < b)
    por_regra = {
        regra: total
        for regra, total in db.session.query(Alert.rule, db.func.count(Alert.id))
        .filter(no_periodo, db.or_(falso.is_(False), falso.is_(None)))
        .group_by(Alert.rule)
        .all()
    }
    incidentes = Incidente.query.filter(Incidente.camera_id.in_(camera_ids), Incidente.aberto_em >= a, Incidente.aberto_em < b)
    pontos = PontoDaLiga.query.filter(PontoDaLiga.camera_id.in_(camera_ids), PontoDaLiga.criado_em >= a, PontoDaLiga.criado_em < b)
    dias = {_dia_local(c) for (c,) in db.session.query(Alert.created_at).filter(no_periodo).all()}
    dias |= {_dia_local(i) for (i,) in incidentes.with_entities(Incidente.aberto_em).all()}
    dias |= {_dia_local(p) for (p,) in pontos.with_entities(PontoDaLiga.criado_em).all()}
    return {
        "por_regra": por_regra,
        "alertas": sum(por_regra.values()),
        "incidentes": incidentes.count(),
        "dias_com_dados": len(dias),
        "minutos_conformes": pontos.filter(PontoDaLiga.tipo == "minuto_conforme").count(),
    }


def _lado(contagem: dict[str, Any], inicio: datetime, fim: datetime, observado_ate: datetime, dias_na_janela: int, *, completa: bool,
          dias_decorridos: int) -> dict[str, Any]:
    return {
        "inicio": inicio.isoformat(),
        "fim": fim.isoformat(),
        "observado_ate": observado_ate.isoformat(),
        "completa": completa,
        "dias_na_janela": dias_na_janela,
        "dias_decorridos": dias_decorridos,
        "alertas": {"total": contagem["alertas"], "por_regra": contagem["por_regra"]},
        "incidentes": {"total": contagem["incidentes"]},
        "amostra": {
            "dias_com_dados": contagem["dias_com_dados"],
            "dias_decorridos": dias_decorridos,
            "minutos_conformes_registrados": contagem["minutos_conformes"],
            "minutos_observados": None,
        },
    }


def _variacao(antes: int, depois: int) -> float | None:
    return None if antes == 0 else round((depois - antes) / antes * 100, 1)


def comparar(intervencao: Intervencao, janela_dias: int, agora: datetime) -> dict[str, Any]:
    """Compara janelas iguais antes e depois da data. `agora` entra por parâmetro (teste determinístico)."""
    agora = agora if agora.tzinfo is not None else agora.replace(tzinfo=timezone.utc)
    dia = intervencao.data_da_intervencao
    camera_ids = _cameras_do_escopo(intervencao)
    marco = _inicio_do_dia(dia)
    antes_inicio = _inicio_do_dia(dia - timedelta(days=janela_dias))
    depois_fim = _inicio_do_dia(dia + timedelta(days=janela_dias))
    completa = agora >= depois_fim
    observado_ate = min(depois_fim, max(marco, agora))
    dias_decorridos = max(0, min(janela_dias, (agora.astimezone().date() - dia).days))

    antes = _janela(camera_ids, antes_inicio, marco)
    depois = _janela(camera_ids, marco, observado_ate)
    regras = sorted(set(antes["por_regra"]) | set(depois["por_regra"]))
    por_regra = sorted(
        ({"regra": r, "antes": antes["por_regra"].get(r, 0), "depois": depois["por_regra"].get(r, 0)} for r in regras),
        key=lambda x: (-(x["antes"] + x["depois"]), x["regra"]),
    )

    aviso_da_janela = None
    if not completa:
        faltam = janela_dias - dias_decorridos
        if agora < marco:
            aviso_da_janela = (
                f"A intervenção ainda não aconteceu (é em {dia.strftime('%d/%m/%Y')}). "
                "Ainda não há dados do depois; nada foi estimado."
            )
        else:
            aviso_da_janela = (
                f"A janela do depois ainda não terminou: faltam {pluralizar(faltam, 'dia')} de {janela_dias}. "
                "Os números do depois são parciais e não foram extrapolados; a variação só aparece com a janela completa."
            )

    return {
        "intervencao": intervencao.to_dict(),
        "janela_dias": janela_dias,
        "escopo": {"camera_ids": camera_ids, "setor": intervencao.setor},
        "antes": _lado(antes, antes_inicio, marco, marco, janela_dias, completa=True, dias_decorridos=janela_dias),
        "depois": _lado(depois, marco, depois_fim, observado_ate, janela_dias, completa=completa, dias_decorridos=dias_decorridos),
        "por_regra": por_regra,
        "variacao": (
            {
                "alertas_pct": _variacao(antes["alertas"], depois["alertas"]),
                "incidentes_pct": _variacao(antes["incidentes"], depois["incidentes"]),
            }
            if completa
            else None
        ),
        "exposicao": {"disponivel": False, "motivo": MOTIVO_SEM_EXPOSICAO},
        "observacoes": [
            "Alertas marcados como falso positivo não entram na contagem.",
            "Dia sem nenhum registro pode ser dia sem ocorrência ou dia com o sistema desligado: o sistema não distingue.",
        ],
        "aviso_da_janela": aviso_da_janela,
        "aviso": AVISO,
    }


# ----------------------------------------------------------------------- ROI ---
def _numero(corpo: Mapping[str, Any], campo: str, rotulo: str, *, obrigatorio: bool, inteiro: bool = False, minimo: float = 0.0) -> float:
    """`rotulo` é o que a pessoa vê ("o custo da intervenção em R$"); o nome do campo da API não entra na mensagem."""
    valor = corpo.get(campo)
    sujeito = rotulo[:1].upper() + rotulo[1:]
    if valor is None:
        if obrigatorio:
            raise DadoInvalido(f"Informe {rotulo}: o cálculo usa só números digitados por você.")
        return 0.0
    if isinstance(valor, bool) or not isinstance(valor, (int, float)) or not math.isfinite(valor):
        raise DadoInvalido(f"{sujeito} precisa ser um número.")
    if inteiro and float(valor) != int(valor):
        raise DadoInvalido(f"{sujeito} precisa ser um número inteiro.")
    if valor < minimo:
        raise DadoInvalido(f"{sujeito} não pode ser menor que {minimo:g}.")
    if valor > LIMITE_NUMERICO:
        raise DadoInvalido(f"{sujeito} está grande demais.")
    return float(valor)


def _brl(valor: float) -> str:
    texto = f"{valor:,.2f}"
    return "R$ " + texto.replace(",", "X").replace(".", ",").replace("X", ".")


def _num(valor: float) -> str:
    return f"{valor:g}".replace(".", ",")


def calcular_roi(corpo: Any) -> dict[str, Any]:
    """ROI só com as premissas do corpo. Nada é lido do banco nem de tabela embutida.

    Premissas: `custo_da_intervencao` (R$), `incidentes_evitados` (no período),
    `custo_medio_por_incidente` (R$), `periodo_dias`; opcionais `horas_perdidas_por_incidente`
    e `custo_da_hora` (R$; 0 se faltarem).
    """
    if not isinstance(corpo, dict):
        raise DadoInvalido("Preencha as suas premissas para calcular.")
    custo = _numero(corpo, "custo_da_intervencao", "o custo da intervenção em R$", obrigatorio=True)
    evitados = _numero(corpo, "incidentes_evitados", "quantos incidentes você estima ter evitado no período", obrigatorio=True)
    medio = _numero(corpo, "custo_medio_por_incidente", "o custo médio estimado de um incidente em R$", obrigatorio=True)
    periodo = _numero(corpo, "periodo_dias", "o período, em dias, dos incidentes evitados", obrigatorio=True, inteiro=True, minimo=1)
    horas = _numero(corpo, "horas_perdidas_por_incidente", "as horas perdidas por incidente", obrigatorio=False)
    valor_hora = _numero(corpo, "custo_da_hora", "o custo de uma hora em R$", obrigatorio=False)

    por_incidente = medio + horas * valor_hora
    economia = evitados * por_incidente
    ganho = economia - custo
    roi_pct = round(ganho / custo * 100, 1) if custo > 0 else None
    payback = round(custo / (economia / periodo), 1) if economia > 0 else None

    linhas = [
        "Custo por incidente = custo médio + horas perdidas × custo da hora"
        f" = {_brl(medio)} + {_num(horas)} × {_brl(valor_hora)} = {_brl(por_incidente)}",
        "Economia no período = incidentes evitados × custo por incidente"
        f" = {_num(evitados)} × {_brl(por_incidente)} = {_brl(economia)}",
        f"Ganho líquido = economia − custo da intervenção = {_brl(economia)} − {_brl(custo)} = {_brl(ganho)}",
        (f"ROI = ganho líquido ÷ custo da intervenção = {_brl(ganho)} ÷ {_brl(custo)} = {_num(roi_pct)}%" if roi_pct is not None
         else "ROI: não calculado (o custo da intervenção é zero)."),
        ("Retorno em dias = custo ÷ (economia ÷ período)"
         f" = {_brl(custo)} ÷ ({_brl(economia)} ÷ {int(periodo)} dias) = {_num(payback)} dias"
         if payback is not None else "Retorno em dias: não calculado (a economia estimada é zero)."),
    ]
    return {
        "premissas": {
            "custo_da_intervencao": custo,
            "incidentes_evitados": evitados,
            "custo_medio_por_incidente": medio,
            "periodo_dias": int(periodo),
            "horas_perdidas_por_incidente": horas,
            "custo_da_hora": valor_hora,
        },
        "resultado": {
            "custo_por_incidente": round(por_incidente, 2),
            "economia": round(economia, 2),
            "ganho_liquido": round(ganho, 2),
            "roi_pct": roi_pct,
            "payback_dias": payback,
        },
        "formula": "\n".join(linhas),
        "aviso": AVISO_DO_ROI,
    }
