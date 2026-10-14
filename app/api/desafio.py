"""“Você vs. a IA” (G2): `/api/desafio/rodadas`, quadros do clipe e resposta.

Os quadros vêm das gravações de demonstração (`tests/fixtures/`, baixadas por
`python scripts/fetch_fixtures.py`), com a cabeça de cada pessoa desfocada. O
placar é da sessão do navegador: nenhum apelido nem resultado vai ao banco.
"""

from __future__ import annotations

from pathlib import Path

from flask import Blueprint, Response, current_app, jsonify, request

from app.config import BASE_DIR
from app.services.desafio import Desafio
from app.utils.auth import login_required

desafio_bp = Blueprint("desafio", __name__)

ARQUIVOS = {"bench": "bench.mp4", "multidao": "next_multidao.mp4"}


def _desafio() -> Desafio | None:
    existente = current_app.extensions.get("desafio")
    if existente is not None:
        return existente
    pasta = Path(str(current_app.config.get("DESAFIO_FIXTURES_DIR", "tests/fixtures")))
    pasta = pasta if pasta.is_absolute() else Path(BASE_DIR) / pasta
    caminhos = {nome: str(pasta / arq) for nome, arq in ARQUIVOS.items()}
    if not all(Path(c).exists() for c in caminhos.values()):
        return None
    monitor = current_app.extensions.get("monitor_service")
    desafio = Desafio(
        caminhos,
        detector=getattr(monitor, "detector", None),
        person_detector=getattr(monitor, "person_detector", None) if current_app.config.get("MULTI_PERSON_DETECTION", True) else None,
        lock=getattr(monitor, "_inference_lock", None),
    )
    current_app.extensions["desafio"] = desafio
    return desafio


def _indisponivel():
    return jsonify({"error": "gravações de demonstração ausentes: python scripts/fetch_fixtures.py"}), 404


@desafio_bp.get("/api/desafio/rodadas")
@login_required
def rodadas():
    d = _desafio()
    if d is None:
        return _indisponivel()
    return jsonify({"rodadas": d.publicas(), "largura": 960, "altura": 540})


@desafio_bp.get("/api/desafio/<ident>/quadro/<int:k>.jpg")
@login_required
def quadro(ident: str, k: int):
    d = _desafio()
    if d is None:
        return _indisponivel()
    try:
        return Response(d.quadro(ident, k), mimetype="image/jpeg", headers={"Cache-Control": "private, max-age=600"})
    except LookupError as exc:
        return jsonify({"error": str(exc)}), 404


@desafio_bp.post("/api/desafio/<ident>/resposta")
@login_required
def responder(ident: str):
    d = _desafio()
    if d is None:
        return _indisponivel()
    corpo = request.get_json(silent=True) or {}
    try:
        cliques = [(float(x), float(y)) for x, y in (corpo.get("cliques") or [])][:50]
        tempo_ms = float(corpo["tempo_ms"]) if corpo.get("tempo_ms") is not None else None
    except (TypeError, ValueError):
        return jsonify({"error": "cliques = [[x, y], ...] em 960×540"}), 400
    try:
        return jsonify(d.responder(ident, cliques, tempo_ms))
    except LookupError as exc:
        return jsonify({"error": str(exc)}), 404
