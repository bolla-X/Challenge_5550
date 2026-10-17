"""Cadeia de custódia das evidências (X3, MISSÃO 2).

Cada evidência — o alerta (os campos que não mudam depois de criado), o
snapshot, o clipe do replay e cada troca de privacidade — vira um elo:

    conteudo = sha256(da evidência)
    elo      = sha256(seq | tipo | ref | conteudo | elo_anterior | criado_em)

A verificação refaz tudo a partir das fontes (arquivo no disco, linha no
banco) e aponta o PRIMEIRO elo que não fecha, com o motivo:

- `conteudo_alterado`: a evidência mudou (um byte num JPEG do clipe basta);
  no clipe, diz também qual arquivo;
- `registro_alterado`: alguém editou a linha da cadeia no banco;
- `cadeia_quebrada`: um elo foi removido ou reordenado;
- `ausente`: a evidência sumiu do disco (limpeza, exclusão) — não é "íntegra",
  mas também não é afirmado como adulteração.

O que isto prova e o que não prova (vai para a banca do jeito que é): prova que
nada mudou DEPOIS de entrar na cadeia, desde que a cadeia (ou só o hash do
último elo) esteja guardada fora do alcance de quem quer adulterar. Sem
âncora externa, quem tem acesso de escrita ao banco E ao disco pode refazer a
cadeia inteira. A âncora é publicar o hash do último elo (ex.: no relatório de
turno impresso/assinado).
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.extensions import db
from app.models import Alert, ElodeCustodia, EventLog

logger = logging.getLogger(__name__)

GENESE = "0" * 64
# Um elo por vez no processo inteiro: workers, gravador e rotas HTTP anexam.
_trava = threading.Lock()


def sha256_bytes(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


def _json_canonico(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")


def _iso(valor: datetime | None) -> str | None:
    if valor is None:
        return None
    if valor.tzinfo is None:
        valor = valor.replace(tzinfo=timezone.utc)
    return valor.astimezone(timezone.utc).isoformat()


def hash_do_elo(seq: int, tipo: str, ref: str, conteudo: str, anterior: str, criado_em: str) -> str:
    return sha256_bytes(f"{seq}|{tipo}|{ref}|{conteudo}|{anterior}|{criado_em}".encode())


# ------------------------------------------------------------- conteúdos
def conteudo_do_alerta(alerta: Alert) -> bytes:
    """Só o que não muda depois de criado (o alerta é renovado e resolvido depois)."""
    meta = alerta.metadata_json or {}
    return _json_canonico({
        "id": alerta.id,
        "camera_id": alerta.camera_id,
        "rule": alerta.rule,
        "severity": alerta.severity,
        "message": alerta.message,
        "feature": alerta.feature,
        "created_at": _iso(alerta.created_at),
        "person_id": meta.get("person_id"),
    })


def conteudo_do_evento(evento: EventLog) -> bytes:
    return _json_canonico({
        "id": evento.id,
        "camera_id": evento.camera_id,
        "event_type": evento.event_type,
        "message": evento.message,
        "subject": evento.subject,
        "metadata": evento.metadata_json or {},
        "created_at": _iso(evento.created_at),
    })


def manifesto_da_pasta(pasta: Path) -> dict[str, str]:
    """sha256 de cada arquivo do clipe (quadros + índice), em ordem de nome."""
    return {arq.name: sha256_bytes(arq.read_bytes()) for arq in sorted(pasta.iterdir()) if arq.is_file()}


def conteudo_do_manifesto(manifesto: dict[str, str]) -> bytes:
    return "".join(f"{nome}:{h}\n" for nome, h in sorted(manifesto.items())).encode()


# ------------------------------------------------------------- anexar
def _novo_elo(ultimo: ElodeCustodia | None, *, tipo: str, ref: str, conteudo_sha256: str, descricao: str,
              camera_id: int | None = None, alert_id: int | None = None,
              detalhe: dict[str, Any] | None = None) -> ElodeCustodia:
    anterior = ultimo.elo_sha256 if ultimo else GENESE
    seq = (ultimo.id if ultimo else 0) + 1
    criado_em = datetime.now(timezone.utc).isoformat()
    elo = ElodeCustodia(
        id=seq,
        tipo=tipo,
        ref=ref[:240],
        camera_id=camera_id,
        alert_id=alert_id,
        descricao=descricao[:255],
        detalhe=detalhe or {},
        conteudo_sha256=conteudo_sha256,
        anterior_sha256=anterior,
        elo_sha256=hash_do_elo(seq, tipo, ref[:240], conteudo_sha256, anterior, criado_em),
        criado_em=criado_em,
    )
    db.session.add(elo)
    return elo


def _ultimo() -> ElodeCustodia | None:
    return ElodeCustodia.query.order_by(ElodeCustodia.id.desc()).first()


def _anexar(**campos: Any) -> ElodeCustodia:
    with _trava:
        elo = _novo_elo(_ultimo(), **campos)
        db.session.commit()
        return elo


@contextmanager
def lote_de_alertas():
    """Elos dos alertas de UMA análise, na MESMA transação deles (um commit só).

    Quem usa faz o commit dentro do `with`: a trava segura a ordem da cadeia
    até o commit. Um commit por alerta dentro do loop da câmera era o custo
    que o PR1 tinha tirado (tests/test_alert_state.py).
    """
    with _trava:
        estado = {"ultimo": _ultimo()}

        def anexar(alerta: Alert) -> None:
            try:
                estado["ultimo"] = _novo_elo(
                    estado["ultimo"], tipo="alerta", ref=f"alerta:{alerta.id}",
                    conteudo_sha256=sha256_bytes(conteudo_do_alerta(alerta)), descricao=alerta.message,
                    camera_id=alerta.camera_id, alert_id=alerta.id,
                )
            except Exception as exc:  # noqa: BLE001  (o alerta é gravado mesmo sem o elo; a verificação mostra a falta)
                logger.warning("custodia_falhou", extra={"funcao": "lote_de_alertas", "error": str(exc)})

        yield anexar


def _seguro(funcao):
    """Custódia nunca derruba quem gera a evidência: falha vira log (e o elo falta, o que a verificação mostra)."""

    def envolvida(*args, **kwargs):
        try:
            return funcao(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            db.session.rollback()
            logger.warning("custodia_falhou", extra={"funcao": funcao.__name__, "error": str(exc)})
            return None

    envolvida.__name__ = funcao.__name__
    return envolvida


@_seguro
def registrar_alerta(alerta: Alert) -> ElodeCustodia:
    return _anexar(tipo="alerta", ref=f"alerta:{alerta.id}", conteudo_sha256=sha256_bytes(conteudo_do_alerta(alerta)),
                   descricao=alerta.message, camera_id=alerta.camera_id, alert_id=alerta.id)


@_seguro
def registrar_snapshot(alerta: Alert, caminho: Path, *, alert_ids: list[int] | None = None) -> ElodeCustodia:
    ids = alert_ids or [alerta.id]
    return _anexar(tipo="snapshot", ref=f"snapshot:{caminho.name}", conteudo_sha256=sha256_bytes(caminho.read_bytes()),
                   descricao=f"Quadro do alerta {alerta.id}" + (f" e de mais {len(ids) - 1}" if len(ids) > 1 else ""),
                   camera_id=alerta.camera_id, alert_id=alerta.id, detalhe={"caminho": str(caminho), "alert_ids": ids})


def manifesto_das_pastas(pastas: list[Path]) -> dict[str, str]:
    """Uma pasta: nomes simples (formato original). Várias: "pasta/arquivo"."""
    if len(pastas) == 1:
        return manifesto_da_pasta(pastas[0])
    saida: dict[str, str] = {}
    for pasta in pastas:
        for nome, h in manifesto_da_pasta(pasta).items():
            saida[f"{pasta.name}/{nome}"] = h
    return saida


@_seguro
def registrar_clipe(alert_id: int, camera_id: int | None, pastas: Path | list[Path], *,
                    alert_ids: list[int] | None = None) -> ElodeCustodia:
    lista = [pastas] if isinstance(pastas, Path) else list(pastas)
    manifesto = manifesto_das_pastas(lista)
    quadros = sum(1 for n in manifesto if n.endswith(".jpg"))
    ids = alert_ids or [alert_id]
    return _anexar(tipo="clipe", ref=f"clipe:{lista[0].name}", conteudo_sha256=sha256_bytes(conteudo_do_manifesto(manifesto)),
                   descricao=f"Replay do alerta {alert_id} ({quadros} quadros)"
                   + (f", compartilhado com mais {len(ids) - 1}" if len(ids) > 1 else ""),
                   camera_id=camera_id, alert_id=alert_id,
                   detalhe={"caminho": str(lista[0]), "pastas": [str(x) for x in lista], "manifesto": manifesto, "alert_ids": ids})


@_seguro
def registrar_evacuacao(caminho: Path) -> ElodeCustodia:
    """Relatório de evacuação (M3): o conteúdo é o sha256 do ARQUIVO JSON, byte a byte."""
    return _anexar(tipo="evacuacao", ref=caminho.name, conteudo_sha256=sha256_bytes(caminho.read_bytes()),
                   descricao=f"Relatório de evacuação {caminho.name}", detalhe={"caminho": str(caminho)})


@_seguro
def registrar_evento(evento: EventLog) -> ElodeCustodia:
    return _anexar(tipo="privacidade" if evento.event_type == "privacy_toggled" else "evento", ref=f"evento:{evento.id}",
                   conteudo_sha256=sha256_bytes(conteudo_do_evento(evento)), descricao=evento.message,
                   camera_id=evento.camera_id)


# ------------------------------------------------------------- verificar
def _recalcular(elo: ElodeCustodia, alertas: dict[int, Alert], eventos: dict[int, EventLog]) -> tuple[str | None, str | None]:
    """(hash recalculado, arquivo que mudou) — hash None = evidência ausente."""
    if elo.tipo == "alerta":
        alerta = alertas.get(elo.alert_id) if elo.alert_id else None
        return (sha256_bytes(conteudo_do_alerta(alerta)) if alerta else None), None
    if elo.tipo in ("privacidade", "evento"):
        evento = eventos.get(int(elo.ref.split(":", 1)[1]))
        return (sha256_bytes(conteudo_do_evento(evento)) if evento else None), None
    caminho = Path(str((elo.detalhe or {}).get("caminho") or ""))
    if elo.tipo in ("snapshot", "evacuacao"):
        return (sha256_bytes(caminho.read_bytes()) if caminho.is_file() else None), None
    if elo.tipo == "clipe":
        pastas = [Path(x) for x in ((elo.detalhe or {}).get("pastas") or [str(caminho)])]
        if not all(p.is_dir() for p in pastas):
            return None, None
        atual = manifesto_das_pastas(pastas)
        antigo = (elo.detalhe or {}).get("manifesto") or {}
        mudou = next((nome for nome in sorted(set(antigo) | set(atual)) if antigo.get(nome) != atual.get(nome)), None)
        return sha256_bytes(conteudo_do_manifesto(atual)), mudou
    return None, None


VERIFICACAO_THREADS = 8


def verificar(*, alert_ids: set[int] | None = None) -> dict[str, Any]:
    """Refaz a cadeia inteira; o conteúdo é conferido em todos os elos (ou só nos de `alert_ids`).

    A estrutura (registro e encadeamento) é sempre conferida do começo: um elo
    só é confiável se todos os anteriores também forem.
    """
    elos = ElodeCustodia.query.order_by(ElodeCustodia.id).all()
    # Fontes em lote (uma consulta por tabela, não uma por elo): a cadeia de um
    # turno tem milhares de elos e a verificação tinha de caber num clique.
    def do_incidente(e: ElodeCustodia) -> bool:
        return alert_ids is None or e.alert_id in alert_ids or bool(alert_ids & set((e.detalhe or {}).get("alert_ids") or []))

    conferir = [e for e in elos if do_incidente(e)]
    ids_alerta = {e.alert_id for e in conferir if e.tipo == "alerta" and e.alert_id}
    ids_evento = {int(e.ref.split(":", 1)[1]) for e in conferir if e.tipo in ("privacidade", "evento")}
    alertas = {a.id: a for a in Alert.query.filter(Alert.id.in_(ids_alerta)).all()} if ids_alerta else {}
    eventos = {v.id: v for v in EventLog.query.filter(EventLog.id.in_(ids_evento)).all()} if ids_evento else {}
    # Arquivos em paralelo: no Windows cada abertura custa ~1 ms (antivírus), e
    # a cadeia de um E2E de 20 min tinha 31 mil quadros de replay → 92 s em
    # série. Só leitura de disco nas threads; os elos já estão carregados.
    de_arquivo = [e for e in conferir if e.tipo in ("snapshot", "clipe", "evacuacao")]
    with ThreadPoolExecutor(max_workers=VERIFICACAO_THREADS) as pool:
        recalculados = dict(zip((e.id for e in de_arquivo), pool.map(lambda e: _recalcular(e, alertas, eventos), de_arquivo),
                                strict=True))
    anterior = GENESE
    resultado: list[dict[str, Any]] = []
    primeiro_problema: dict[str, Any] | None = None
    ausentes = 0
    for esperado_seq, elo in enumerate(elos, start=1):
        situacao, arquivo = "ok", None
        if elo.id != esperado_seq or elo.anterior_sha256 != anterior:
            situacao = "cadeia_quebrada"
        elif hash_do_elo(elo.id, elo.tipo, elo.ref, elo.conteudo_sha256, elo.anterior_sha256, elo.criado_em) != elo.elo_sha256:
            situacao = "registro_alterado"
        elif do_incidente(elo):
            recalculado, arquivo = recalculados.get(elo.id) or _recalcular(elo, alertas, eventos)
            if recalculado is None:
                situacao = "ausente"
                ausentes += 1
            elif recalculado != elo.conteudo_sha256:
                situacao = "conteudo_alterado"
        anterior = elo.elo_sha256
        if not do_incidente(elo) and situacao == "ok":
            continue
        item = elo.to_dict() | {"situacao": situacao, **({"arquivo": arquivo} if arquivo else {})}
        resultado.append(item)
        if situacao not in ("ok", "ausente") and primeiro_problema is None:
            primeiro_problema = item
    return {
        "integra": primeiro_problema is None and ausentes == 0,
        "adulterada": primeiro_problema is not None,
        "elos_verificados": len(resultado),
        "elos_na_cadeia": len(elos),
        "ausentes": ausentes,
        "quebrado": primeiro_problema,
        "ultimo_elo": elos[-1].elo_sha256 if elos else GENESE,
        "elos": resultado,
    }
