from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, jsonify, request, send_from_directory
from werkzeug.exceptions import NotFound

from app.utils.auth import escopo_ou_erro, login_required

status_bp = Blueprint("status", __name__)

# Caminhos que NUNCA devolvem o shell do SPA num 404: API, arquivos e canais em
# tempo real continuam respondendo como o servidor sempre respondeu.
_PREFIXOS_SEM_SHELL = ("/api", "/static", "/socket.io", "/snapshots", "/alerts", "/events")


def _servir_shell(condicional: bool = True):
    """O shell do build React (mesma resposta para `index()` e para o 404 do SPA).

    `condicional=False` ignora If-None-Match/If-Modified-Since: um 304 apagaria o
    status 404 e o corpo.
    """
    dist_dir = Path(current_app.static_folder) / "dist"
    if current_app.config.get("DEMO_MODE"):
        # Demo em tema claro (projetor), salvo se a pessoa já escolheu um tema.
        html = (dist_dir / "index.html").read_text(encoding="utf-8")
        script = ("<script>try{if(!localStorage.getItem('visionepi-theme'))"
                  "localStorage.setItem('visionepi-theme','light')}catch(e){}</script>")
        return current_app.response_class(html.replace("<head>", "<head>" + script, 1), mimetype="text/html")
    return send_from_directory(dist_dir, "index.html", conditional=condicional)


def _sob_prefixo(caminho: str, prefixos: tuple[str, ...]) -> bool:
    return any(caminho == p or caminho.startswith(p + "/") for p in prefixos)


@status_bp.app_errorhandler(404)
def nao_encontrado(erro: NotFound):
    """404 de ENDEREÇO desconhecido (nenhuma rota casou).

    - `/api/...`: JSON, como o resto da API.
    - GET de página (sem extensão, fora dos prefixos de API/arquivo): o shell do
      SPA com status 404, para a tela "Esta página não existe" aparecer em vez do
      404 cru do Flask.
    - O resto (inclusive `abort(404)` dentro de uma rota que casou, como uma
      evidência inexistente) segue exatamente como estava.
    """
    if request.url_rule is not None:
        return erro
    caminho = request.path
    if _sob_prefixo(caminho, ("/api",)):
        return jsonify({"error": "Recurso não encontrado.", "code": "not_found"}), 404
    if (
        request.method in ("GET", "HEAD")
        and not _sob_prefixo(caminho, _PREFIXOS_SEM_SHELL)
        and "." not in caminho.rsplit("/", 1)[-1]
        and (Path(current_app.static_folder) / "dist" / "index.html").is_file()
    ):
        resposta = _servir_shell(condicional=False)
        resposta.status_code = 404
        resposta.headers["Cache-Control"] = "no-store"
        return resposta
    return erro


@status_bp.get("/")
@status_bp.get("/dashboard")
@status_bp.get("/dashboard/")
@status_bp.get("/portal")
@status_bp.get("/tv")
@status_bp.get("/rotular")
@status_bp.get("/desafio")
@status_bp.get("/gemeo")
@status_bp.get("/simulador")
@status_bp.get("/auditoria")
@status_bp.get("/palco")
@status_bp.get("/palco/controle")
@status_bp.get("/retrospectiva")
@status_bp.get("/liga")
@status_bp.get("/evacuacao")
@status_bp.get("/torre")
@status_bp.get("/regras")
@status_bp.get("/permissoes")
@status_bp.get("/primeiro-acesso")
@status_bp.get("/produto")
@status_bp.get("/ajuda")
@status_bp.get("/caixa-de-entrada")
@status_bp.get("/novidades")
@status_bp.get("/configuracoes")
def index():
    # Serve o shell do build React (frontend/vite.config.ts emite aqui).
    # O caminho Jinja antigo (app/templates/ + app/static/app.js|styles.css)
    # foi removido do disco — nenhuma rota o referenciava desde a migração.
    return _servir_shell()


@status_bp.get("/sw.js")
def service_worker():
    """Service worker do PWA (X10) servido na RAIZ: só assim o escopo dele é o app inteiro."""
    dist_dir = Path(current_app.static_folder) / "dist"
    resposta = send_from_directory(dist_dir, "sw.js", mimetype="text/javascript", max_age=0)
    resposta.headers["Cache-Control"] = "no-cache"
    return resposta


@status_bp.get("/manifest.webmanifest")
def manifesto():
    dist_dir = Path(current_app.static_folder) / "dist"
    return send_from_directory(dist_dir, "manifest.webmanifest", mimetype="application/manifest+json", max_age=0)


def _pede_a_pagina() -> bool:
    """O pedido é de uma pessoa abrindo `/status` no navegador (e não de um `fetch` de JSON)?

    `GET /status` é, desde antes da página, a rota JSON do monitor. A mesma URL agora
    também é a página de saúde do sistema (SPA). O desempate é o `Accept`: navegação
    declara `text/html` com prioridade sobre `*/*`; `fetch` sem cabeçalho (`*/*`),
    `curl` e os testes, não. Quem pede `application/json` explicitamente recebe JSON.
    """
    if request.headers.get("X-Requested-With"):
        return False
    return request.accept_mimetypes.best_match(["application/json", "text/html"], default="application/json") == "text/html"


@status_bp.get("/status")
def status():
    # A página não carrega dado nenhum (o dado vem de /api/status, que exige sessão),
    # então o shell sai sem login, como o de toda outra rota de tela.
    if _pede_a_pagina():
        return _servir_shell()
    return _status_do_monitor()


@login_required
def _status_do_monitor():
    camera_id, erro = escopo_ou_erro()
    if erro:
        return erro
    monitor = current_app.extensions["monitor_service"]
    return jsonify({"system": "VisionEPI", **monitor.status(camera_id=camera_id)})


@status_bp.get("/preflight")
@login_required
def preflight():
    camera_id, erro = escopo_ou_erro()
    if erro:
        return erro
    monitor = current_app.extensions["monitor_service"]
    return jsonify(monitor.preflight(camera_id=camera_id))
