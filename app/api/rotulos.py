"""Aprendizado ativo (G9): revisão dos recortes e exportação do dataset.

`GET /api/rotulos/proximo`, `GET /api/rotulos/<id>.jpg`, `POST /api/rotulos/<id>`
({"decisao": "confirmar"|"rejeitar"}) e `GET /api/rotulos/dataset.zip`. Só
técnico (e supervisor). A contagem de contribuições é da EQUIPE (vai para o
Modo TV); quem decidiu não é gravado.
"""

from __future__ import annotations

from flask import Blueprint, Response, current_app, jsonify, request, send_file

from app.models import ROLE_TECHNICAL
from app.utils.auth import require_role

rotulos_bp = Blueprint("rotulos", __name__)


def _fila():
    fila = current_app.extensions["monitor_service"].fila_de_rotulos
    if fila is None:
        return None
    return fila


@rotulos_bp.get("/api/rotulos/proximo")
@require_role(ROLE_TECHNICAL)
def proximo():
    fila = _fila()
    if fila is None:
        return jsonify({"habilitado": False, "item": None, "contagem": None})
    return jsonify({"habilitado": True, "item": fila.proximo(), "contagem": fila.contagem()})


@rotulos_bp.get("/api/rotulos/<ident>.jpg")
@require_role(ROLE_TECHNICAL)
def imagem(ident: str):
    fila = _fila()
    caminho = fila.imagem(ident) if fila else None
    if caminho is None:
        return jsonify({"error": "recorte não encontrado"}), 404
    return send_file(caminho, mimetype="image/jpeg", max_age=0)


@rotulos_bp.post("/api/rotulos/<ident>")
@require_role(ROLE_TECHNICAL)
def decidir(ident: str):
    fila = _fila()
    if fila is None:
        return jsonify({"error": "aprendizado ativo desligado"}), 409
    decisao = (request.get_json(silent=True) or {}).get("decisao")
    try:
        fila.decidir(ident, str(decisao))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except LookupError as exc:
        return jsonify({"error": str(exc)}), 404
    return jsonify({"contagem": fila.contagem()})


@rotulos_bp.get("/api/rotulos/dataset.zip")
@require_role(ROLE_TECHNICAL)
def exportar():
    fila = _fila()
    if fila is None:
        return jsonify({"error": "aprendizado ativo desligado"}), 409
    return Response(fila.exportar_zip(), mimetype="application/zip",
                    headers={"Content-Disposition": "attachment; filename=visionepi-rotulos-yolo.zip"})
