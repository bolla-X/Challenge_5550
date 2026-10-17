"""API documentada (M11): documento OpenAPI 3.1 e página `/api/docs`, técnico ou acima.

Os dois são gerados a cada pedido do `app.url_map` (ver `app/services/openapi_doc.py`): rota
nova aparece sozinha, com o tipo de conta mínimo lido da própria view.
"""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from app.models import ROLE_TECHNICAL
from app.services.openapi_doc import construir_documento, renderizar_html
from app.utils.auth import require_role

openapi_bp = Blueprint("openapi", __name__)


@openapi_bp.get("/api/openapi.json")
@require_role(ROLE_TECHNICAL)
def documento_openapi():
    """Documento OpenAPI 3.1 das rotas do servidor."""
    return jsonify(construir_documento(current_app))


@openapi_bp.get("/api/docs")
@require_role(ROLE_TECHNICAL)
def pagina_da_api():
    """Página HTML (offline) com as operações por grupo, o tipo de conta de cada uma e exemplos de curl."""
    pagina = renderizar_html(construir_documento(current_app), request.host_url)
    return current_app.response_class(pagina, mimetype="text/html")
