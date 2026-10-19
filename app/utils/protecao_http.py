"""Proteções HTTP globais: CSRF residual (same-site) e cabeçalhos de segurança.

O cookie de sessão é `SameSite=Lax`, que ainda deixa passar mutação vinda de OUTRO subdomínio do
mesmo site. Por isso toda escrita (POST/PUT/PATCH/DELETE) é recusada quando o navegador diz que ela
não nasceu na própria origem:

- `Sec-Fetch-Site` presente (todo navegador atual manda): só `same-origin` (e `none`, ação do próprio
  usuário) passam; `same-site` e `cross-site` levam 403.
- Sem `Sec-Fetch-Site` mas com `Origin`: tem de ser igual à origem desta requisição (`request.host_url`).
  Atrás de proxy que termina TLS, o proxy precisa repassar o esquema (ProxyFix); senão a origem
  `https://` não bate com o `http://` visto aqui.
- Nenhum dos dois (curl, `requests`, test client do Flask, CLP): passa. Quem não é navegador não é
  vetor de CSRF, e a autenticação continua valendo.

CSP fica de fora por enquanto: o tema da demo usa script inline e o three.js do gêmeo precisa de
`unsafe-eval`/`blob:`; ver docs/NEXT2026/CHANGELOG.md ("Fase 5 item 5").
"""

from __future__ import annotations

from flask import Flask, Response, jsonify, request

_METODOS_DE_ESCRITA = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_SITES_CONFIAVEIS = frozenset({"same-origin", "none"})

_CABECALHOS_DE_SEGURANCA = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "SAMEORIGIN",
    "Referrer-Policy": "same-origin",
}


def origem_cruzada() -> bool:
    """True se o navegador indica que esta requisição não veio da própria origem."""
    site = request.headers.get("Sec-Fetch-Site")
    if site is not None:
        return site.strip().lower() not in _SITES_CONFIAVEIS
    origem = request.headers.get("Origin")
    if origem is None:
        return False
    return origem.strip().rstrip("/") != request.host_url.rstrip("/")


def registrar_protecoes_http(app: Flask) -> None:
    @app.before_request
    def _barrar_escrita_de_outra_origem():
        if request.method in _METODOS_DE_ESCRITA and origem_cruzada():
            return jsonify({"error": "Requisição bloqueada: ela não veio da origem deste sistema.", "code": "origem_cruzada"}), 403
        return None

    @app.after_request
    def _cabecalhos_de_seguranca(resposta: Response) -> Response:
        for nome, valor in _CABECALHOS_DE_SEGURANCA.items():
            resposta.headers.setdefault(nome, valor)
        return resposta
