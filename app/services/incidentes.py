"""Agrupa os alertas por pessoa em incidentes por (câmera, regra, zona) — MISSÃO 2, P0.2.

Antes, cada pessoa sem EPI virava uma linha (e uma pílula) por EPI: na
multidão com os 7 EPIs ligados eram dezenas de alertas, e cada troca de ID do
rastreador abria mais um. A demo só ligava 3 EPIs para caber na tela.

Agora o alerta continua por pessoa (é a evidência: caixa, clipe, replay) e o
painel mostra o INCIDENTE: "Sem capacete · Zona A · 3 pessoas (IDs 4, 7, 9)".
Um incidente abre com o primeiro alerta da chave, ganha as pessoas que
entram, e fecha quando o último alerta dele resolve (a histerese de
resolução continua sendo a do alerta). Roda na thread do worker, dentro da
mesma transação de `AlertStateService.process`.
"""

from __future__ import annotations

import re

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from app.extensions import db
from app.models import Alert, Incidente
from app.services.risk_rules import RuleAlert

ZONA_FORA = "Fora da zona"
ZONA_CAMERA = "Toda a câmera"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def numero_da_pessoa(person_id: Any) -> Any:
    """"person_38" → 38 (o número que a tela mostra como "Pessoa 38"); outros valores passam."""
    if isinstance(person_id, str) and person_id.startswith("person_") and person_id[7:].isdigit():
        return int(person_id[7:])
    return person_id


def titulo_do_alerta(mensagem: str) -> str:
    """"Sem capacete · Pessoa 3" → "Sem capacete" (o incidente não é de uma pessoa)."""
    return re.split(r" [·—] ", mensagem or "")[0].strip() or "Alerta"


@dataclass
class _Aberto:
    incidente_id: int
    # chave do alerta (regra:feature:pessoa) -> ID de rastreio (ou None)
    ativos: dict[str, Any] = field(default_factory=dict)
    snapshot: dict[str, Any] | None = None


class AgrupadorDeIncidentes:
    def __init__(self, camera_id: int | None, nome_da_zona: Callable[[], str | None] | None = None) -> None:
        self.camera_id = camera_id
        # Nome da zona de risco da câmera; None = câmera sem zona desenhada.
        self._nome_da_zona = nome_da_zona or (lambda: None)
        self._abertos: dict[tuple[str, str | None, str], _Aberto] = {}
        self._orfaos_fechados = False

    # ------------------------------------------------------------ chaves
    def zona_de(self, item: RuleAlert) -> str:
        nome = self._nome_da_zona()
        if item.rule == "risk_area_presence":
            return nome or "Área de risco"
        if not nome:
            return ZONA_CAMERA
        return nome if item.metadata.get("na_zona") else ZONA_FORA

    def _chave(self, item: RuleAlert) -> tuple[str, str | None, str]:
        return (item.rule, item.feature, self.zona_de(item))

    # ------------------------------------------------------------ ciclo
    def fechar_orfaos(self) -> None:
        """Incidentes que ficaram "ativos" de uma execução anterior (processo morto, reset)."""
        if self._orfaos_fechados or self._abertos:
            return
        self._orfaos_fechados = True
        agora = utc_now()
        for inc in Incidente.query.filter_by(camera_id=self.camera_id, status="active").all():
            inc.status, inc.fechado_em, inc.atualizado_em = "resolved", agora, agora

    def anexar(self, alert: Alert, item: RuleAlert, chave_alerta: str) -> dict[str, Any]:
        """Alerta recém-criado entra no incidente da chave (abre um se não houver)."""
        self.fechar_orfaos()
        chave = self._chave(item)
        aberto = self._abertos.get(chave)
        inc = db.session.get(Incidente, aberto.incidente_id) if aberto else None
        agora = utc_now()
        if inc is None:
            inc = Incidente(
                camera_id=self.camera_id,
                rule=item.rule,
                feature=item.feature,
                zona=chave[2],
                severity=item.severity,
                titulo=titulo_do_alerta(item.message),
                status="active",
                pessoas=[],
                alert_ids=[],
                pico_pessoas=0,
                aberto_em=agora,
                atualizado_em=agora,
            )
            db.session.add(inc)
            db.session.flush()
            aberto = self._abertos[chave] = _Aberto(incidente_id=inc.id)
        assert aberto is not None
        pessoa = numero_da_pessoa(item.metadata.get("person_id"))
        aberto.ativos[chave_alerta] = pessoa
        # Listas NOVAS (o JSON puro não detecta mutação in-place).
        if pessoa is not None and pessoa not in (inc.pessoas or []):
            inc.pessoas = [*(inc.pessoas or []), pessoa]
        if alert.id not in (inc.alert_ids or []):
            inc.alert_ids = [*(inc.alert_ids or []), alert.id]
        inc.pico_pessoas = max(int(inc.pico_pessoas or 0), len(aberto.ativos))
        inc.atualizado_em = agora
        aberto.snapshot = inc.to_dict(self._pessoas_ativas(aberto))
        return aberto.snapshot

    def desanexar(self, chave_alerta: str) -> dict[str, Any] | None:
        """Alerta resolvido sai do incidente; o último a sair fecha o incidente."""
        for chave, aberto in list(self._abertos.items()):
            if chave_alerta not in aberto.ativos:
                continue
            del aberto.ativos[chave_alerta]
            inc = db.session.get(Incidente, aberto.incidente_id)
            if inc is None:
                del self._abertos[chave]
                return None
            agora = utc_now()
            inc.atualizado_em = agora
            if not aberto.ativos:
                inc.status, inc.fechado_em = "resolved", agora
                del self._abertos[chave]
            aberto.snapshot = inc.to_dict(self._pessoas_ativas(aberto))
            return aberto.snapshot
        return None

    def fechar_todos(self) -> list[dict[str, Any]]:
        fechados = []
        for chave in list(self._abertos):
            aberto = self._abertos.pop(chave)
            inc = db.session.get(Incidente, aberto.incidente_id)
            if inc is None:
                continue
            agora = utc_now()
            inc.status, inc.fechado_em, inc.atualizado_em = "resolved", agora, agora
            fechados.append(inc.to_dict([]))
        return fechados

    def reset(self) -> None:
        self._abertos.clear()
        self._orfaos_fechados = False

    # ------------------------------------------------------------ leitura
    @staticmethod
    def _pessoas_ativas(aberto: _Aberto) -> list[Any]:
        return sorted({p for p in aberto.ativos.values() if p is not None}, key=lambda p: (str(type(p)), p))

    def ativos(self) -> list[dict[str, Any]]:
        """Snapshots (dicts puros, atravessam threads — ver AlertRuntimeState.snapshot)."""
        return [a.snapshot for a in list(self._abertos.values()) if a.snapshot is not None]
