"""Persistência e aplicação das regras do editor (M4).

Uma base de consulta (`consultar_regras`), dois pontos de entrada com sentido
de negócio e a guarda de escrita — para a tela e o motor nunca filtrarem por
conta própria:

- `listar_regras_gestao`      tudo: pré-carregadas + do usuário, ativas e inativas
                              (o editor precisa ver e reativar as desligadas);
- `listar_regras_operacionais` só as ATIVAS: é o que o RuleEngine executa;
- `garantir_regra_editavel`   a pré-carregada é de leitura (editar/excluir = erro
                              estável); quem quer mudar uma, duplica.

Histórico: desligar ou excluir uma regra não apaga nem reescreve os alertas que
ela já gerou (o `regra_editor_id` fica no metadata do alerta).
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import replace
from typing import Any

from app.extensions import db
from app.models import RegraEditor
from app.services.regras_editor import AvaliadorDeRegras, Regra, RegraInvalida, compilar, regras_pre_carregadas, validar

logger = logging.getLogger(__name__)

FILTROS_DE_ATIVIDADE = ("todas", "ativas", "inativas")
PREFIXO_RESERVADO = "pre_"


class RegraNaoEncontrada(LookupError):
    pass


class RegraProtegida(PermissionError):
    """Tentativa de editar ou excluir uma regra pré-carregada."""


class RegraJaExiste(ValueError):
    pass


def _pre_carregadas_por_id() -> dict[str, Regra]:
    return {regra.id: regra for regra in regras_pre_carregadas()}


# ------------------------------------------------------------- consulta ---
def consultar_regras(filtro_atividade: str = "todas") -> list[Regra]:
    """Base única: pré-carregadas (ordem do código) e depois as do usuário (mais antigas primeiro).

    A coluna `ativa` da tabela é a fonte da verdade; pré-carregada sem linha é inativa.
    """
    if filtro_atividade not in FILTROS_DE_ATIVIDADE:
        raise ValueError(f"filtro_atividade deve ser um de {FILTROS_DE_ATIVIDADE}")
    linhas = {linha.id: linha for linha in RegraEditor.query.order_by(RegraEditor.criada_em, RegraEditor.id).all()}
    regras: list[Regra] = []
    for pre in regras_pre_carregadas():
        linha = linhas.pop(pre.id, None)
        regras.append(replace(pre, ativa=bool(linha and linha.ativa)))
    for linha in linhas.values():
        try:
            regras.append(validar({**linha.definicao, "id": linha.id, "ativa": bool(linha.ativa)}))
        except RegraInvalida as erro:
            # Definição de uma versão antiga do formato: não derruba o motor nem a tela.
            logger.warning("regra_do_editor_ignorada", extra={"regra": linha.id, "motivo": str(erro)})
    if filtro_atividade == "ativas":
        return [r for r in regras if r.ativa]
    if filtro_atividade == "inativas":
        return [r for r in regras if not r.ativa]
    return regras


def listar_regras_gestao() -> list[Regra]:
    return consultar_regras("todas")


def listar_regras_operacionais() -> list[Regra]:
    return consultar_regras("ativas")


def obter_regra(regra_id: str) -> Regra:
    for regra in consultar_regras("todas"):
        if regra.id == regra_id:
            return regra
    raise RegraNaoEncontrada(regra_id)


def garantir_regra_editavel(regra_id: str) -> Regra:
    """Guarda de escrita: ver a pré-carregada pode, alterá-la ou excluí-la não."""
    regra = obter_regra(regra_id)
    if regra.origem == "pre_carregada":
        raise RegraProtegida(regra_id)
    return regra


# --------------------------------------------------------------- escrita ---
def criar_regra(dado: dict[str, Any], criada_por: str | None = None) -> Regra:
    """Valida e grava. `origem` é sempre "usuario" aqui; `id` é gerado se não vier."""
    corpo = {**dado, "origem": "usuario"}
    corpo["id"] = corpo.get("id") or uuid.uuid4().hex[:12]
    regra = validar(corpo)
    if regra.id.startswith(PREFIXO_RESERVADO):
        raise RegraInvalida(f"id: o prefixo '{PREFIXO_RESERVADO}' é reservado às regras pré-carregadas")
    if db.session.get(RegraEditor, regra.id) is not None:
        raise RegraJaExiste(regra.id)
    db.session.add(RegraEditor(id=regra.id, definicao=regra.to_dict(), ativa=regra.ativa, criada_por=criada_por))
    db.session.commit()
    return regra


def atualizar_regra(regra_id: str, dado: dict[str, Any]) -> Regra:
    atual = garantir_regra_editavel(regra_id)
    regra = validar({"ativa": atual.ativa, **dado, "id": regra_id, "origem": "usuario"})
    linha = db.session.get(RegraEditor, regra_id)
    linha.definicao, linha.ativa = regra.to_dict(), regra.ativa
    db.session.commit()
    return regra


def excluir_regra(regra_id: str) -> None:
    garantir_regra_editavel(regra_id)
    db.session.delete(db.session.get(RegraEditor, regra_id))
    db.session.commit()


def definir_ativa(regra_id: str, ativa: bool) -> Regra:
    """Liga/desliga. Vale também para a pré-carregada (ganha uma linha só com a flag)."""
    regra = obter_regra(regra_id)
    linha = db.session.get(RegraEditor, regra_id)
    if linha is None:
        linha = RegraEditor(id=regra_id, definicao=regra.to_dict(), ativa=ativa, criada_por=None)
        db.session.add(linha)
    linha.ativa = ativa
    if regra.origem == "usuario":
        linha.definicao = replace(regra, ativa=ativa).to_dict()
    db.session.commit()
    return replace(regra, ativa=ativa)


# ------------------------------------------------------------- aplicação ---
def _workers_do_monitor(monitor: Any) -> dict[int, Any]:
    workers = getattr(monitor, "_workers", None)
    if not isinstance(workers, dict):
        return {}
    trava = getattr(monitor, "_workers_lock", None)
    if trava is None:
        return dict(workers)
    with trava:
        return dict(workers)


def aplicar_regras(app) -> int:
    """Recompila as regras ativas e entrega ao `rule_engine` de cada worker.

    Um avaliador por worker (o estado de duração é por câmera) compartilhando
    as regras compiladas, que são imutáveis. Devolve quantos workers receberam.
    `getattr` defensivo: o monitor de teste (DummyMonitor) não tem workers.
    """
    with app.app_context():
        compiladas = [compilar(regra) for regra in listar_regras_operacionais()]
    aplicados = 0
    for camera_id, worker in _workers_do_monitor(app.extensions.get("monitor_service")).items():
        motor = getattr(worker, "rule_engine", None)
        if motor is None:
            continue
        relogio = getattr(motor, "relogio", None) or time.monotonic
        motor.avaliador_do_editor = AvaliadorDeRegras(compiladas, relogio) if compiladas else None
        contexto = getattr(motor, "contexto_do_editor", None)
        if isinstance(contexto, dict):
            contexto["camera_id"] = camera_id
        aplicados += 1
    return aplicados
