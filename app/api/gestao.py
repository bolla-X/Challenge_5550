"""Gestão de EPIs (ES Sprint 4): colaboradores, catálogo com CA, entregas, ocorrências e exportação CSV.

Contrato: docs/specs/es-sprint4-contrato-gestao.md. Regras e travas: app/services/gestao_epi.py.

Papéis: Técnico ou mais lê tudo, registra entrega, devolução e ocorrência e exporta; Supervisor cadastra e edita
colaborador e item do catálogo; Operador recebe 403 em tudo (o kiosk não usa este módulo). Cadastro administrativo:
nada aqui é ligado às câmeras.
"""

from __future__ import annotations

from flask import Blueprint, Response, jsonify, request
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import ROLE_SUPERVISOR, ROLE_TECHNICAL, Colaborador, EntregaEpi, EpiCatalogo, Ocorrencia
from app.services import gestao_epi as servico
from app.utils.auth import current_user, require_role

gestao_bp = Blueprint("gestao", __name__)

_CAMPOS_DO_COLABORADOR = (*servico.CAMPOS_DO_COLABORADOR, "ativo")


@gestao_bp.errorhandler(servico.ErroDeGestao)
def _erro(exc: servico.ErroDeGestao):
    db.session.rollback()
    return jsonify({"error": exc.message, "code": exc.code}), exc.status


def _quem() -> str:
    usuario = current_user()
    return usuario.email if usuario is not None else "sistema"


def _gravar() -> None:
    """Commit que traduz a corrida de dois pedidos com a mesma matrícula/CA/código em 409, não em 500."""
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise servico.ErroDeGestao(
            "Já existe um registro com estes dados (matrícula, CA ou código). Atualize a tela e confira.", "duplicado", 409,
        ) from None


def _atividade(bruto: str | None) -> str:
    """`?ativo=` -> TODOS (ausente), ATIVOS ou INATIVOS."""
    valor = (bruto or "").strip().lower()
    if valor in ("", "todos", "todas"):
        return servico.TODOS
    if valor in ("true", "1", "sim"):
        return servico.ATIVOS
    if valor in ("false", "0", "nao", "não"):
        return servico.INATIVOS
    raise servico.ErroDeGestao("Escolha ativos, inativos ou todos.", "filtro_invalido")


def _filtro(nome: str) -> str:
    return (request.args.get(nome) or "").strip()


def _filtro_de_id(nome: str) -> int | None:
    """`?colaborador_id=abc` é erro do chamador (400), não "sem filtro"."""
    bruto = _filtro(nome)
    if not bruto:
        return None
    try:
        valor = int(bruto)
    except ValueError:
        valor = 0
    if not 1 <= valor <= 2**31 - 1:
        raise servico.ErroDeGestao(f"O filtro {nome} precisa ser um número inteiro positivo.", "filtro_invalido")
    return valor


# --------------------------------------------------------------------- resumo ---
@gestao_bp.get("/api/gestao/resumo")
@require_role(ROLE_TECHNICAL)
def resumo_da_gestao():
    """Contadores da Gestão de EPIs: colaboradores, catálogo, entregas, CAs e ocorrências."""
    return jsonify(servico.resumo(servico.hoje(), servico.agora()))


# -------------------------------------------------------------- colaboradores ---
@gestao_bp.get("/api/gestao/colaboradores")
@require_role(ROLE_TECHNICAL)
def listar_colaboradores():
    """Lista os colaboradores com entregas vigentes e pendências (filtros: busca, setor, ativo)."""
    atividade = _atividade(request.args.get("ativo"))
    filtros = {"busca": _filtro("busca"), "setor": _filtro("setor")}
    if atividade == servico.ATIVOS:
        itens, truncado = servico.listar_colaboradores_operacionais(**filtros)
    else:
        itens, truncado = servico.listar_colaboradores_gestao(**filtros, atividade=atividade)
    contagens = servico.contagens_por_colaborador([c.id for c in itens], servico.hoje())
    return jsonify({
        "items": [servico.colaborador_para_api(c, contagens) for c in itens],
        "count": len(itens),
        "truncado": truncado,
        "setores": servico.setores_dos_colaboradores(),
    })


@gestao_bp.post("/api/gestao/colaboradores")
@require_role(ROLE_SUPERVISOR)
def criar_colaborador():
    """Cadastra um colaborador (matrícula única, sem CPF nem foto)."""
    novo = servico.aplicar_colaborador(Colaborador(), request.get_json(silent=True))
    db.session.add(novo)
    _gravar()
    return jsonify({"colaborador": servico.colaborador_para_api(novo, {})}), 201


@gestao_bp.get("/api/gestao/colaboradores/<int:colaborador_id>")
@require_role(ROLE_TECHNICAL)
def detalhe_do_colaborador(colaborador_id: int):
    """Um colaborador com o histórico de entregas (mais recente primeiro) e as ocorrências ligadas a ele."""
    colaborador = servico.buscar(Colaborador, colaborador_id, "colaborador_nao_encontrado", "Colaborador não encontrado.")
    dia = servico.hoje()
    entregas, truncado = servico.listar_entregas(dia, colaborador_id=colaborador.id)
    ocorrencias = Ocorrencia.query.filter(Ocorrencia.colaborador_id == colaborador.id).order_by(
        Ocorrencia.ocorrida_em.desc(), Ocorrencia.id.desc()).all()
    contagens = servico.contagens_por_colaborador([colaborador.id], dia)
    return jsonify({
        "colaborador": servico.colaborador_para_api(colaborador, contagens),
        "entregas": [e.to_dict(dia) for e in entregas],
        "entregas_truncado": truncado,
        "ocorrencias": [o.to_dict() for o in ocorrencias],
    })


@gestao_bp.put("/api/gestao/colaboradores/<int:colaborador_id>")
@require_role(ROLE_SUPERVISOR)
def editar_colaborador(colaborador_id: int):
    """Edita o cadastro do colaborador, inclusive desligar (ativo=false) sem apagar o histórico."""
    colaborador = servico.buscar(Colaborador, colaborador_id, "colaborador_nao_encontrado", "Colaborador não encontrado.")
    antes = servico.instantaneo(colaborador, _CAMPOS_DO_COLABORADOR)
    servico.aplicar_colaborador(colaborador, request.get_json(silent=True))
    _gravar()
    servico.registrar_edicao(
        "gestao_colaborador_editado", f"Colaborador {colaborador.matricula} editado", por=_quem(), item_id=colaborador.id,
        antes=antes, depois=servico.instantaneo(colaborador, _CAMPOS_DO_COLABORADOR),
    )
    contagens = servico.contagens_por_colaborador([colaborador.id], servico.hoje())
    return jsonify({"colaborador": servico.colaborador_para_api(colaborador, contagens)})


# --------------------------------------------------------------------- catálogo ---
@gestao_bp.get("/api/gestao/epis")
@require_role(ROLE_TECHNICAL)
def listar_epis():
    """Lista o catálogo de EPIs com a situação do CA (filtros: categoria, situacao)."""
    dia = servico.hoje()
    itens, truncado = servico.listar_epis(dia, categoria=_filtro("categoria"), situacao=_filtro("situacao"))
    vigentes = servico.entregas_vigentes_por_epi(dia)
    return jsonify({"items": [servico.epi_para_api(e, dia, vigentes) for e in itens], "count": len(itens), "truncado": truncado})


@gestao_bp.post("/api/gestao/epis")
@require_role(ROLE_SUPERVISOR)
def criar_epi():
    """Cadastra um item no catálogo (CA único)."""
    novo = servico.aplicar_epi(EpiCatalogo(), request.get_json(silent=True))
    db.session.add(novo)
    _gravar()
    dia = servico.hoje()
    return jsonify({"epi": servico.epi_para_api(novo, dia, servico.entregas_vigentes_por_epi(dia))}), 201


@gestao_bp.put("/api/gestao/epis/<int:epi_id>")
@require_role(ROLE_SUPERVISOR)
def editar_epi(epi_id: int):
    """Edita um item do catálogo (por exemplo, renova a validade do CA)."""
    epi = servico.buscar(EpiCatalogo, epi_id, "epi_nao_encontrado", "EPI não encontrado no catálogo.")
    antes = servico.instantaneo(epi, servico.CAMPOS_DO_EPI)
    servico.aplicar_epi(epi, request.get_json(silent=True))
    _gravar()
    servico.registrar_edicao(
        "gestao_epi_editado", f"EPI CA {epi.ca} editado", por=_quem(), item_id=epi.id,
        antes=antes, depois=servico.instantaneo(epi, servico.CAMPOS_DO_EPI),
    )
    dia = servico.hoje()
    return jsonify({"epi": servico.epi_para_api(epi, dia, servico.entregas_vigentes_por_epi(dia))})


# --------------------------------------------------------------------- entregas ---
@gestao_bp.get("/api/gestao/entregas")
@require_role(ROLE_TECHNICAL)
def listar_entregas():
    """Lista as entregas de EPI, da mais recente para a mais antiga (filtros: colaborador_id, epi_id, situacao)."""
    dia = servico.hoje()
    itens, truncado = servico.listar_entregas(
        dia, colaborador_id=_filtro_de_id("colaborador_id"), epi_id=_filtro_de_id("epi_id"), situacao=_filtro("situacao"),
    )
    return jsonify({"items": [e.to_dict(dia) for e in itens], "count": len(itens), "truncado": truncado})


@gestao_bp.post("/api/gestao/entregas")
@require_role(ROLE_TECHNICAL)
def registrar_entrega():
    """Registra a entrega de um EPI. Recusa CA vencido e colaborador desligado (409)."""
    dia = servico.hoje()
    nova = servico.registrar_entrega(request.get_json(silent=True), por=_quem(), dia=dia)
    db.session.add(nova)
    _gravar()
    return jsonify({"entrega": nova.to_dict(dia)}), 201


@gestao_bp.post("/api/gestao/entregas/<int:entrega_id>/devolucao")
@require_role(ROLE_TECHNICAL)
def registrar_devolucao(entrega_id: int):
    """Registra a devolução de uma entrega (data opcional, padrão hoje). Devolver duas vezes dá 409."""
    entrega = servico.buscar(EntregaEpi, entrega_id, "entrega_nao_encontrada", "Entrega não encontrada.")
    dia = servico.hoje()
    servico.registrar_devolucao(entrega, request.get_json(silent=True), dia)
    _gravar()
    return jsonify({"entrega": entrega.to_dict(dia)})


# ------------------------------------------------------------------ ocorrências ---
@gestao_bp.get("/api/gestao/ocorrencias")
@require_role(ROLE_TECHNICAL)
def listar_ocorrencias():
    """Lista as ocorrências de segurança, da mais recente para a mais antiga (filtros: status, tipo, setor)."""
    itens, truncado = servico.listar_ocorrencias(status=_filtro("status"), tipo=_filtro("tipo"), setor=_filtro("setor"))
    return jsonify({"items": [o.to_dict() for o in itens], "count": len(itens), "truncado": truncado})


@gestao_bp.post("/api/gestao/ocorrencias")
@require_role(ROLE_TECHNICAL)
def registrar_ocorrencia():
    """Registra uma ocorrência de segurança (nasce aberta)."""
    nova = servico.registrar_ocorrencia(request.get_json(silent=True), por=_quem(), instante=servico.agora())
    db.session.add(nova)
    _gravar()
    return jsonify({"ocorrencia": nova.to_dict()}), 201


@gestao_bp.put("/api/gestao/ocorrencias/<int:ocorrencia_id>")
@require_role(ROLE_TECHNICAL)
def atualizar_ocorrencia(ocorrencia_id: int):
    """Muda o status e a ação corretiva da ocorrência. Encerrar preenche a data de encerramento."""
    ocorrencia = servico.buscar(Ocorrencia, ocorrencia_id, "ocorrencia_nao_encontrada", "Ocorrência não encontrada.")
    campos = ("status", "acao_corretiva", "encerrada_em")
    antes = servico.instantaneo(ocorrencia, campos)
    servico.atualizar_ocorrencia(ocorrencia, request.get_json(silent=True), servico.agora())
    _gravar()
    depois = servico.instantaneo(ocorrencia, campos)
    mudanca = f" ({antes['status']} → {depois['status']})" if antes["status"] != depois["status"] else ""
    servico.registrar_edicao(
        "gestao_ocorrencia_atualizada", f"Ocorrência {ocorrencia.codigo} atualizada{mudanca}", por=_quem(),
        item_id=ocorrencia.id, antes=antes, depois=depois,
    )
    return jsonify({"ocorrencia": ocorrencia.to_dict()})


# ------------------------------------------------------------------- exportação ---
@gestao_bp.get("/api/gestao/exportar/<recurso>.csv")
@require_role(ROLE_TECHNICAL)
def exportar_csv(recurso: str):
    """Exporta colaboradores, epis, entregas, ocorrencias ou alertas em CSV (UTF-8 com BOM, separador ;)."""
    dia = servico.hoje()
    texto, truncado = servico.exportar_csv(recurso, dia)
    resposta = Response(texto.encode("utf-8"), content_type="text/csv; charset=utf-8")
    resposta.headers["Content-Disposition"] = f"attachment; filename={servico.nome_do_arquivo_csv(recurso, dia)}"
    resposta.headers["Cache-Control"] = "no-store"
    if truncado:
        resposta.headers["X-Registros-Truncados"] = "true"  # passou do teto de linhas: o arquivo traz só as mais recentes
    return resposta
