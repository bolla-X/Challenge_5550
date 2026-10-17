"""Documento OpenAPI 3.1 e página `/api/docs`, gerados do `app.url_map` (M11).

Nada aqui é escrito à mão por rota, exceto:

- `ROTAS`: a descrição curta em pt-BR das rotas de INTEGRAÇÃO (as que um sistema externo
  chamaria). As demais rotas `/api/*` saem com a primeira linha do docstring da view;
- `CONSULTA`: parâmetros de consulta das rotas de integração;
- `ACESSO_EXPLICITO`: onde o decorador sozinho conta só parte da regra de acesso.

O tipo de conta mínimo de cada operação é LIDO da view: `require_role(minimo)` e
`login_required` (em `app/utils/auth.py`) guardam o que precisam em closures; percorremos
`__wrapped__` e as closures das camadas e achamos o decorador pelo arquivo onde ele nasceu.
Rota sem nenhum dos dois é pública (ex.: login).

Só documenta: não chama view, não toca em banco nem em câmera.
"""

from __future__ import annotations

import html
import inspect
import re
from typing import Any

from flask import Flask

from app.models import ROLE_LEVELS, ROLE_OPERATOR, ROLE_SUPERVISOR, ROLE_TECHNICAL
from app.utils import auth as _auth

# Descreve o contrato de HOJE; ainda não há versionamento de rota.
VERSAO_DA_API = "1.0.0"
VERSAO_OPENAPI = "3.1.0"
NOME_DO_ESQUEMA = "sessao"

ROTULO_DA_CONTA = {ROLE_OPERATOR: "Operador", ROLE_TECHNICAL: "Técnico", ROLE_SUPERVISOR: "Supervisor"}
ROTULO_DO_ACESSO = {
    ROLE_OPERATOR: "Qualquer conta com login",
    ROLE_TECHNICAL: "Técnico ou acima",
    ROLE_SUPERVISOR: "Supervisor",
    None: "Sem login",
}

# "MÉTODO /caminho" -> (tag, descrição curta). Só rotas de integração.
ROTAS: dict[str, tuple[str, str]] = {
    # Autenticação
    "POST /api/auth/login": ("Autenticação", "Entra com e-mail e senha e devolve o cookie de sessão."),
    "POST /api/auth/logout": ("Autenticação", "Encerra a sessão deste cookie."),
    "GET /api/auth/me": ("Autenticação", "Quem está logado. Responde 200 com user nulo quando ninguém está."),
    # Alertas
    "GET /alerts": ("Alertas", "Lista os alertas mais recentes, com filtros por gravidade, situação, câmera e recurso."),
    "GET /alerts/{alert_id}/evidence": ("Alertas", "Imagem de evidência guardada quando o alerta nasceu."),
    "GET /api/alerts/{alert_id}/clip": ("Alertas", "Índice do replay do alerta: quadros de 5 s antes a 3 s depois, com as evidências."),
    "GET /api/alerts/{alert_id}/clip/{indice}.jpg": ("Alertas", "Um quadro do replay do alerta."),
    "POST /alerts/{alert_id}/false-positive": ("Alertas", "Marca o alerta como falso positivo."),
    "POST /alerts/{alert_id}/acknowledge": ("Alertas", "Registra que o colaborador foi avisado. Não resolve o alerta."),
    # Incidentes
    "GET /api/incidentes": ("Incidentes", "Lista os incidentes (alertas agrupados por regra e zona), do mais recente para o mais antigo."),
    "GET /api/incidentes/{incidente_id}": ("Incidentes", "Um incidente com os alertas que o formam."),
    "POST /api/incidentes/{incidente_id}/reconhecer": (
        "Incidentes", "Reconhece o incidente (\"vi isto\"). Mede o tempo até a resposta; não resolve nada."),
    "GET /api/incidentes/{incidente_id}/linha-causal": (
        "Incidentes", "Linha causal: o que aconteceu com cada rótulo de rastreio dentro do incidente."),
    # Câmeras
    "GET /api/cameras": ("Câmeras", "Lista as câmeras cadastradas (o Operador vê só a do setor dele)."),
    "GET /api/cameras/{camera_id}": ("Câmeras", "Cadastro de uma câmera."),
    "GET /api/cameras/{camera_id}/status": ("Câmeras", "Situação da câmera: ligada ou não, imagem, último erro e recursos ativos."),
    # Integração
    "GET /api/integracao/estado": ("Integração", "Estado da planta publicado em OPC UA e MQTT, mais a situação de cada integração."),
    # Evacuação
    "POST /api/evacuacao/iniciar": ("Evacuação", "Aciona o Modo Evacuação, com ponto de encontro opcional."),
    "POST /api/evacuacao/encerrar": ("Evacuação", "Encerra a evacuação e grava o relatório na cadeia de custódia."),
    "GET /api/evacuacao": ("Evacuação", "Estado da evacuação: contagem por câmera, posição na planta e chegadas ao ponto de encontro."),
    "GET /api/evacuacao/relatorios": ("Evacuação", "Lista os relatórios de evacuação já encerrados."),
    "GET /api/evacuacao/relatorios/{numero}": ("Evacuação", "Um relatório de evacuação completo."),
    # Permissões
    "GET /api/permissoes": ("Permissões", "Lista as permissões de trabalho em zona controlada."),
    "POST /api/permissoes": ("Permissões", "Emite uma permissão de trabalho."),
    "GET /api/permissoes/{permissao_id}": ("Permissões", "Uma permissão de trabalho."),
    "POST /api/permissoes/{permissao_id}/encerrar": ("Permissões", "Encerra a permissão ao fim do trabalho."),
    "POST /api/permissoes/{permissao_id}/cancelar": ("Permissões", "Cancela uma permissão emitida."),
    "GET /api/cameras/{camera_id}/zona-controlada": ("Permissões", "Diz se a área de risco da câmera exige permissão."),
    "PUT /api/cameras/{camera_id}/zona-controlada": ("Permissões", "Liga ou desliga a exigência de permissão na área de risco da câmera."),
    # Regras
    "GET /api/regras": ("Regras", "Lista as regras de alerta (pré-carregadas e do usuário) com as opções do editor."),
    "POST /api/regras": ("Regras", "Cria uma regra de alerta montada com blocos."),
    "PUT /api/regras/{regra_id}": ("Regras", "Altera uma regra do usuário. Regra pré-carregada é protegida."),
    "DELETE /api/regras/{regra_id}": ("Regras", "Apaga uma regra do usuário."),
    "POST /api/regras/{regra_id}/ativar": ("Regras", "Ativa a regra."),
    "POST /api/regras/{regra_id}/desativar": ("Regras", "Desativa a regra."),
    "POST /api/regras/testar": ("Regras", "Testa uma regra na trilha gravada, sem criar nem mudar alerta real."),
    # Custódia
    "GET /api/custodia/verificar": ("Custódia", "Verifica a integridade (SHA-256) da cadeia de custódia inteira ou de um incidente."),
    "GET /api/custodia": ("Custódia", "Lista os elos da cadeia de custódia, do mais recente para o mais antigo."),
    # Relatório de turno
    "GET /api/relatorio/turno": ("Relatório de turno", "Relatório do turno em JSON: alertas por regra, câmera e hora, e itens da NR-6."),
    "GET /relatorio/turno": ("Relatório de turno", "O mesmo relatório do turno em HTML, pronto para imprimir."),
    "POST /api/relatorio/turno/resumo": ("Relatório de turno", "Pede o resumo em texto do relatório do turno."),
    "GET /api/relatorio/turno/resumo": ("Relatório de turno", "Lê o resumo em texto do relatório do turno."),
    # Busca
    "GET /api/busca/trilhas": ("Busca", "Busca nas trilhas de uma câmera por zona, horário, permanência, EPI ausente e velocidade."),
    # A própria documentação
    "GET /api/openapi.json": ("Documentação", "Este documento OpenAPI 3.1."),
    "GET /api/docs": ("Documentação", "Página com as operações, o tipo de conta de cada uma e exemplos de curl."),
}

# (nome, tipo, descrição) dos parâmetros de consulta das rotas de integração.
CONSULTA: dict[str, list[tuple[str, str, str]]] = {
    "GET /alerts": [
        ("limit", "integer", "Quantidade máxima, até 500 (padrão 100)."),
        ("severity", "string", "Gravidade: low, medium, high ou critical."),
        ("status", "string", "active ou resolved."),
        ("camera_id", "integer", "Só os alertas desta câmera."),
        ("feature", "string", "Só os alertas deste recurso."),
        ("false_positive", "boolean", "Só falsos positivos (1) ou só os demais (0)."),
    ],
    "GET /api/incidentes": [
        ("status", "string", "active ou resolved."),
        ("rule", "string", "Só os incidentes desta regra."),
        ("camera_id", "integer", "Só os incidentes desta câmera."),
        ("limit", "integer", "Quantidade máxima, até 500 (padrão 100)."),
    ],
    "GET /api/custodia/verificar": [("incidente_id", "integer", "Verifica só as evidências deste incidente.")],
    "GET /api/relatorio/turno": [
        ("horas", "number", "Janela em horas, de 0,5 a 72 (padrão 8)."),
        ("camera_id", "integer", "Só esta câmera."),
    ],
    "GET /api/busca/trilhas": [
        ("camera_id", "integer", "Obrigatório. Câmera cuja trilha será pesquisada."),
        ("de", "string", "Início da janela: ISO 8601 (sem fuso vale UTC) ou segundos desde 1970."),
        ("ate", "string", "Fim da janela, no mesmo formato."),
        ("zona", "boolean", "1: só quando o centro da pessoa está dentro da área de risco atual da câmera."),
        ("permanencia_min_s", "number", "Permanência contínua mínima, em segundos."),
        ("epi_ausente", "string", "EPIs separados por vírgula (helmet,vest...): pelo menos um ausente."),
        ("vel_min", "number", "Velocidade mínima, em fração do quadro por segundo."),
        ("vel_max", "number", "Velocidade máxima, em fração do quadro por segundo."),
        ("limite", "integer", "Quantidade máxima de trechos, até 200 (padrão 50)."),
    ],
}

# Onde o decorador sozinho não conta a regra inteira: (conta mínima, observação).
ACESSO_EXPLICITO: dict[str, tuple[str | None, str]] = {
    "GET /api/custodia/verificar": (
        ROLE_OPERATOR,
        "Sem parâmetro, verifica a cadeia inteira e exige Técnico. Com incidente_id, qualquer conta, dentro do próprio setor.",
    ),
    "POST /api/evacuacao/iniciar": (ROLE_SUPERVISOR, "Aceita também o token do palco (parâmetro t), sem sessão."),
    "POST /api/evacuacao/encerrar": (ROLE_SUPERVISOR, "Aceita também o token do palco (parâmetro t), sem sessão."),
    "GET /api/palco/estado": (ROLE_TECHNICAL, "Aceita também o token do palco (parâmetro t), sem sessão."),
    "POST /api/palco/ir": (ROLE_TECHNICAL, "Aceita também o token do palco (parâmetro t), sem sessão."),
    "POST /api/celular/{token}/quadro": (None, "Sem sessão: o token do celular da câmera vai na própria URL."),
}

TAGS_DE_INTEGRACAO = ["Autenticação", "Alertas", "Incidentes", "Câmeras", "Integração", "Evacuação", "Permissões", "Regras", "Custódia",
                      "Relatório de turno", "Busca", "Documentação"]
TAG_POR_BLUEPRINT = {
    "alerts": "Alertas", "auth": "Autenticação", "cameras": "Câmeras", "celular": "Celular", "custodia": "Custódia",
    "demo": "Demonstração", "desafio": "Desafio", "escala": "Escala", "evacuacao": "Evacuação", "features": "Recursos",
    "feedback": "Feedback", "gemeo": "Gêmeo digital", "incidentes": "Incidentes", "integracao": "Integração",
    "lab": "Laboratório", "liga": "Liga de Setores", "monitor": "Monitor", "onboarding": "Primeiro acesso",
    "palco": "Palco", "permissoes": "Permissões", "regras": "Regras", "relatorio": "Relatório de turno",
    "risk": "Risco", "rotulos": "Rótulos", "runtime": "Diagnóstico", "simulador": "Simulador", "status": "Páginas",
    "stream": "Vídeo", "tv": "Modo TV", "busca": "Busca", "openapi": "Documentação",
}
SEM_DESCRICAO = "Sem descrição curta (rota de uso interno da interface)."

_PARAMETRO = re.compile(r"<(?:(?P<conv>[A-Za-z_]\w*)(?:\(.*?\))?:)?(?P<nome>[A-Za-z_]\w*)>")
_TIPO_DO_CONVERSOR = {
    "int": {"type": "integer"},
    "float": {"type": "number"},
    "uuid": {"type": "string", "format": "uuid"},
}
_AUTH_ARQUIVO = _auth.require_role.__code__.co_filename


# ------------------------------------------------------------------ acesso ---
def _celulas(funcao: Any) -> dict[str, Any]:
    codigo = getattr(funcao, "__code__", None)
    celulas = getattr(funcao, "__closure__", None)
    if codigo is None or not celulas:
        return {}
    saida: dict[str, Any] = {}
    for nome, celula in zip(codigo.co_freevars, celulas, strict=True):
        try:
            saida[nome] = celula.cell_contents
        except ValueError:  # célula ainda vazia
            continue
    return saida


def conta_minima(view: Any) -> str | None:
    """Tipo de conta mínimo que a view exige (`operator`, `technical`, `supervisor`) ou None se é pública.

    `login_required` vale `operator` (qualquer conta). Com decoradores empilhados vale o mais exigente.
    """
    pendentes, vistos, exigidos = [view], set(), []
    while pendentes:
        atual = pendentes.pop()
        if not inspect.isfunction(atual) or id(atual) in vistos:
            continue
        vistos.add(id(atual))
        celulas = _celulas(atual)
        if atual.__code__.co_filename == _AUTH_ARQUIVO:
            if "minimo" in celulas:  # require_role
                exigidos.append(celulas["minimo"])
            elif "alvo" in celulas:  # login_required
                exigidos.append(ROLE_OPERATOR)
        pendentes.extend(celulas.values())
        embrulhada = getattr(atual, "__wrapped__", None)
        if embrulhada is not None:
            pendentes.append(embrulhada)
    validos = [e for e in exigidos if e in ROLE_LEVELS]
    return max(validos, key=lambda e: ROLE_LEVELS[e]) if validos else None


# ---------------------------------------------------------------- documento ---
def _caminho_openapi(regra: str) -> tuple[str, list[dict[str, Any]]]:
    parametros: list[dict[str, Any]] = []

    def trocar(m: re.Match[str]) -> str:
        parametros.append({
            "name": m["nome"], "in": "path", "required": True,
            "schema": dict(_TIPO_DO_CONVERSOR.get(m["conv"] or "string", {"type": "string"})),
        })
        return "{" + m["nome"] + "}"

    return _PARAMETRO.sub(trocar, regra), parametros


def _primeira_linha(view: Any) -> str:
    texto = inspect.getdoc(view) or ""
    linha = texto.strip().splitlines()[0].strip() if texto.strip() else ""
    return linha.rstrip(".") + "." if linha else ""


def _respostas(conta: str | None) -> dict[str, Any]:
    respostas: dict[str, Any] = {"200": {"description": "Sucesso."}}
    if conta is not None:
        respostas["401"] = {"description": "Sem sessão: faça login em /api/auth/login."}
        if conta != ROLE_OPERATOR:
            respostas["403"] = {"description": "O tipo de conta não permite esta operação."}
    return respostas


def _corpo_json(metodo: str) -> dict[str, Any] | None:
    if metodo not in ("POST", "PUT", "PATCH"):
        return None
    return {"required": False, "content": {"application/json": {"schema": {"type": "object"}}}}


def construir_documento(app: Flask) -> dict[str, Any]:
    """OpenAPI 3.1 de toda rota `/api/*` do app, mais as rotas de integração fora desse prefixo."""
    caminhos: dict[str, dict[str, Any]] = {}
    ids_usados: set[str] = set()
    tags_vistas: set[str] = set()
    for regra in sorted(app.url_map.iter_rules(), key=lambda r: (r.rule, r.endpoint)):
        caminho, parametros = _caminho_openapi(regra.rule)
        for metodo in sorted(regra.methods - {"HEAD", "OPTIONS"}):
            chave = f"{metodo} {caminho}"
            if not (caminho.startswith("/api/") or chave in ROTAS):
                continue
            view = app.view_functions[regra.endpoint]
            conta, observacao = ACESSO_EXPLICITO.get(chave, (conta_minima(view), ""))
            tag, resumo = ROTAS.get(chave, (None, ""))
            integracao = tag is not None
            tag = tag or TAG_POR_BLUEPRINT.get(regra.endpoint.split(".")[0], regra.endpoint.split(".")[0].capitalize())
            resumo = resumo or _primeira_linha(view) or SEM_DESCRICAO
            descricao = f"{resumo} Acesso: {ROTULO_DO_ACESSO[conta]}." + (f" {observacao}" if observacao else "")
            identificador = f"{regra.endpoint.replace('.', '_')}_{metodo.lower()}"
            while identificador in ids_usados:
                identificador += "_"
            ids_usados.add(identificador)
            tags_vistas.add(tag)
            consulta = [
                {"name": n, "in": "query", "required": d.startswith("Obrigatório"),
                 "description": d, "schema": {"type": t}}
                for n, t, d in CONSULTA.get(chave, [])
            ]
            operacao: dict[str, Any] = {
                "operationId": identificador,
                "tags": [tag],
                "summary": resumo.rstrip("."),
                "description": descricao,
                "parameters": [dict(p) for p in parametros] + consulta,
                "responses": _respostas(conta),
                "security": [{NOME_DO_ESQUEMA: []}] if conta is not None else [],
                "x-conta-minima": conta,
                "x-conta-minima-rotulo": ROTULO_DA_CONTA.get(conta) if conta else None,
                "x-integracao": integracao,
            }
            corpo = _corpo_json(metodo)
            if corpo is not None:
                operacao["requestBody"] = corpo
            caminhos.setdefault(caminho, {})[metodo.lower()] = operacao
    ordem = {t: i for i, t in enumerate(TAGS_DE_INTEGRACAO)}
    return {
        "openapi": VERSAO_OPENAPI,
        "info": {
            "title": "VisionEPI API",
            "version": VERSAO_DA_API,
            "description": (
                "Rotas do VisionEPI geradas a partir do servidor. A autenticação é por sessão: faça login em "
                "/api/auth/login e envie o cookie de sessão nas demais chamadas. Cada operação informa o tipo de "
                "conta mínimo (Operador, Técnico ou Supervisor). Rótulos de rastreio (\"Pessoa N\") não identificam ninguém."
            ),
        },
        "servers": [{"url": "/"}],
        "tags": sorted(({"name": t} for t in tags_vistas), key=lambda t: (ordem.get(t["name"], 99), t["name"])),
        "paths": dict(sorted(caminhos.items())),
        "components": {
            "securitySchemes": {
                NOME_DO_ESQUEMA: {
                    "type": "apiKey",
                    "in": "cookie",
                    "name": str(app.config.get("SESSION_COOKIE_NAME", "session")),
                    "description": "Cookie de sessão (HttpOnly) devolvido por POST /api/auth/login.",
                }
            }
        },
    }


# ---------------------------------------------------------------------- HTML ---
_CSS = """
:root{color-scheme:light dark;--fundo:#fafafa;--texto:#1c1c1e;--apoio:#555;--linha:#d8d8dc;--cartao:#fff;--codigo:#f0f0f2}
@media (prefers-color-scheme:dark){:root{--fundo:#161618;--texto:#ececee;--apoio:#a0a0a6;--linha:#34343a;--cartao:#1e1e21;--codigo:#27272b}}
*{box-sizing:border-box}
body{margin:0;background:var(--fundo);color:var(--texto);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:60rem;margin:0 auto;padding:1.5rem 1rem 3rem}h1{font-size:1.6rem;margin:0 0 .25rem}h2{font-size:1.2rem;margin:2rem 0 .5rem}
p{margin:.25rem 0}.apoio{color:var(--apoio)}code,pre{font-family:ui-monospace,Consolas,monospace;font-size:.85rem}
pre{background:var(--codigo);padding:.75rem;border-radius:8px;overflow-x:auto;margin:.5rem 0 0}
article{background:var(--cartao);border:1px solid var(--linha);border-radius:10px;padding:.75rem 1rem;margin:.5rem 0}
.rota{display:flex;gap:.6rem;align-items:baseline;flex-wrap:wrap}.metodo{font-weight:700;min-width:3.6rem}.caminho{overflow-wrap:anywhere}
.conta{font-size:.8rem;color:var(--apoio)}summary{cursor:pointer;color:var(--apoio);margin-top:.4rem}
dl{margin:.4rem 0 0;font-size:.85rem}
dt{font-family:ui-monospace,Consolas,monospace;float:left;clear:left;min-width:11rem}dd{margin:0 0 .15rem 11.5rem}
a{color:inherit}
"""


_PARAMETRO_DOC = re.compile(r"\{(?P<nome>[^}]+)\}")


def _tipo_do_parametro(operacao: dict[str, Any], nome: str) -> str:
    for p in operacao.get("parameters", []):
        if p["name"] == nome and p["in"] == "path":
            return str(p["schema"].get("type", "string"))
    return "string"


def _exemplo_curl(base: str, metodo: str, caminho: str, operacao: dict[str, Any]) -> str:
    url = _PARAMETRO_DOC.sub(lambda m: "1" if _tipo_do_parametro(operacao, m["nome"]) == "integer" else "exemplo", caminho)
    partes = ["curl", "-b cookies.txt"]
    if metodo != "GET":
        partes.append(f"-X {metodo}")
    if "requestBody" in operacao:
        partes += ["-H 'Content-Type: application/json'", "-d '{}'"]
    partes.append(f'"{base}{url}"')
    return " ".join(partes)


def renderizar_html(documento: dict[str, Any], base_url: str) -> str:
    """Página única, sem script e sem recurso externo: funciona offline."""
    def esc(texto: Any) -> str:  # texto entre tags: aspas não precisam de escape e ficam legíveis no curl
        return html.escape(str(texto), quote=False)

    def atr(texto: Any) -> str:  # valor de atributo
        return html.escape(str(texto), quote=True)

    base = base_url.rstrip("/")
    # (integração?, tag) -> operações
    grupos: dict[tuple[bool, str], list[tuple[str, str, dict[str, Any]]]] = {}
    for caminho, metodos in documento["paths"].items():
        for metodo, operacao in metodos.items():
            grupos.setdefault((bool(operacao["x-integracao"]), operacao["tags"][0]), []).append((metodo.upper(), caminho, operacao))
    ordem = {t["name"]: i for i, t in enumerate(documento["tags"])}

    def secao(titulo: str, integracao: bool) -> str:
        saida = [f"<h2>{esc(titulo)}</h2>"]
        for tag in sorted((t for flag, t in grupos if flag == integracao), key=lambda t: (ordem.get(t, 99), t)):
            saida.append(f"<h3>{esc(tag)}</h3>")
            for metodo, caminho, op in sorted(grupos[(integracao, tag)], key=lambda x: (x[1], x[0])):
                consulta = [p for p in op["parameters"] if p["in"] == "query"]
                parametros = (
                    "<dl>" + "".join(
                        f"<dt>{esc(p['name'])}{' *' if p['required'] else ''}</dt><dd>{esc(p['description'])}</dd>" for p in consulta
                    ) + "</dl>"
                    if consulta else ""
                )
                saida.append(
                    f'<article data-metodo="{atr(metodo)}" data-caminho="{atr(caminho)}">'
                    f'<div class="rota"><span class="metodo">{esc(metodo)}</span><code class="caminho">{esc(caminho)}</code>'
                    f'<span class="conta">{esc(ROTULO_DO_ACESSO[op["x-conta-minima"]])}</span></div>'
                    f"<p>{esc(op['description'])}</p>{parametros}"
                    f"<details><summary>Exemplo com curl</summary><pre>{esc(_exemplo_curl(base, metodo, caminho, op))}</pre></details>"
                    "</article>"
                )
        return "".join(saida)

    corpo_do_login = '{"email":"voce@empresa.com","password":"..."}'
    login = f"curl -c cookies.txt -X POST -H 'Content-Type: application/json' -d '{corpo_do_login}' \"{base}/api/auth/login\""
    return (
        '<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>API do VisionEPI</title><style>{_CSS}</style></head><body><main>"
        "<h1>API do VisionEPI</h1>"
        '<p class="apoio">Gerada das rotas do servidor. Cada operação mostra o tipo de conta mínimo. '
        'O documento OpenAPI 3.1 está em <a href="/api/openapi.json">/api/openapi.json</a>.</p>'
        "<h2>Como autenticar</h2>"
        "<p>A API usa sessão por cookie. Entre uma vez, guarde o cookie e envie-o nas demais chamadas.</p>"
        f"<pre>{esc(login)}</pre>"
        f"{secao('Rotas de integração', True)}"
        f"{secao('Demais rotas da API (uso interno da interface)', False)}"
        "</main></body></html>"
    )
