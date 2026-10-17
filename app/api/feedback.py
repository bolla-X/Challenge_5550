"""Feedback dentro do app e contatos da página pública `/produto` (MISSÃO 4, Fase 3 itens 10 e 11).

Tudo é gravado LOCALMENTE (tabelas `feedback` e `contatos`), sem envio a terceiros.

| rota | quem |
|---|---|
| `POST /api/feedback` | qualquer conta logada (a sessão dá o tipo de conta e o `user_id`) |
| `GET /api/feedback`, `POST /api/feedback/<id>/lido` | Supervisor |
| `POST /api/contatos` | PÚBLICA (sem sessão), com limite por IP em memória |
| `GET /api/contatos`, `POST /api/contatos/<id>/lido` | Supervisor |

`sempre=True` nas rotas com sessão: mesmo com `AUTH_REQUIRED=false` elas exigem login,
porque gravam (ou leem) o que uma conta específica escreveu.

O blueprint NÃO é registrado em `create_app` por este módulo: quem liga é
`app/__init__.py` (`app.register_blueprint(feedback_bp)`).
"""

from __future__ import annotations

import re

from flask import Blueprint, current_app, jsonify, request

from app.extensions import db
from app.models import ROLE_SUPERVISOR, TAMANHO_MAXIMO_FEEDBACK, Contato, Feedback, User
from app.utils.auth import current_user, login_required, require_role
from app.utils.limite_por_ip import LimitePorIp

feedback_bp = Blueprint("feedback", __name__)

_MAXIMO_NOME = 120
_MAXIMO_EMPRESA = 160
_MAXIMO_EMAIL = 254
_MAXIMO_TELA = 200
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_LIMITE_PADRAO = 100
_LIMITE_MAXIMO = 500

# Padrão do limite por IP do formulário público: 5 mensagens por hora (ajustável em config).
_CONTATOS_POR_IP_PADRAO = 5
_CONTATOS_JANELA_S_PADRAO = 3600


def _milhar(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _erro(mensagem: str, campo: str | None = None, status: int = 400):
    corpo = {"error": mensagem}
    if campo:
        corpo["campo"] = campo
    return jsonify(corpo), status


def _texto(valor, *, rotulo: str, maximo: int, obrigatorio: bool = True) -> tuple[str | None, str | None]:
    """(texto limpo, erro). Texto que não é string, vazio ou longo demais vira erro em pt-BR."""
    if valor is None:
        valor = ""
    if not isinstance(valor, str):
        return None, f"{rotulo}: envie um texto."
    limpo = valor.replace("\x00", "").strip()
    if not limpo:
        return (None, f"{rotulo}: preencha este campo.") if obrigatorio else ("", None)
    if len(limpo) > maximo:
        return None, f"{rotulo}: passa de {_milhar(maximo)} caracteres."
    return limpo, None


def _so_o_caminho(tela) -> str | None:
    """A tela de onde veio o feedback: só o caminho. Query e fragmento podem ter token (ex.: `?t=` do palco)."""
    if not isinstance(tela, str):
        return None
    caminho = tela.split("?", 1)[0].split("#", 1)[0].strip()
    return caminho[:_MAXIMO_TELA] if caminho.startswith("/") else None


# ------------------------------------------------ leitura e "lido" (as duas caixas) --
def _listar(modelo):
    """Base única das duas listagens do supervisor: filtro `lido`, limite e contagem de não lidos."""
    consulta = modelo.query
    filtro = request.args.get("lido")
    if filtro in ("true", "false"):
        consulta = consulta.filter(modelo.lido.is_(filtro == "true"))
    limite = min(max(request.args.get("limit", _LIMITE_PADRAO, type=int) or _LIMITE_PADRAO, 1), _LIMITE_MAXIMO)
    itens = consulta.order_by(modelo.criado_em.desc(), modelo.id.desc()).limit(limite).all()
    nao_lidos = modelo.query.filter(modelo.lido.is_(False)).count()
    return itens, nao_lidos


def _marcar_lido(modelo, item_id: int):
    """`{"lido": false}` desfaz; sem corpo, marca como lido. Idempotente."""
    item = db.session.get(modelo, item_id)
    if item is None:
        return None, _erro("Item não encontrado.", status=404)
    corpo = request.get_json(silent=True)
    novo = corpo.get("lido", True) if isinstance(corpo, dict) else True
    if not isinstance(novo, bool):
        return None, _erro('Envie {"lido": true} ou {"lido": false}.')
    item.lido = novo
    db.session.commit()
    return item, None


# ---------------------------------------------------------------------- feedback --
@feedback_bp.post("/api/feedback")
@login_required(sempre=True)
def enviar_feedback():
    corpo = request.get_json(silent=True)
    if not isinstance(corpo, dict):
        return _erro("Envie um JSON com o texto do feedback.")
    texto, falha = _texto(corpo.get("texto"), rotulo="Feedback", maximo=TAMANHO_MAXIMO_FEEDBACK)
    if falha:
        return _erro(falha, "texto")
    usuario = current_user()
    item = Feedback(texto=texto, tela=_so_o_caminho(corpo.get("tela")), tipo_de_conta=usuario.role, user_id=usuario.id)
    db.session.add(item)
    db.session.commit()
    return jsonify({"feedback": item.to_dict()}), 201


@feedback_bp.get("/api/feedback")
@require_role(ROLE_SUPERVISOR, sempre=True)
def listar_feedback():
    itens, nao_lidos = _listar(Feedback)
    ids = {i.user_id for i in itens if i.user_id is not None}
    nomes = {u.id: u.name for u in User.query.filter(User.id.in_(ids)).all()} if ids else {}
    return jsonify(
        {
            "items": [i.to_dict() | {"autor": nomes.get(i.user_id)} for i in itens],
            "count": len(itens),
            "nao_lidos": nao_lidos,
        }
    )


@feedback_bp.post("/api/feedback/<int:feedback_id>/lido")
@require_role(ROLE_SUPERVISOR, sempre=True)
def marcar_feedback_lido(feedback_id: int):
    item, erro = _marcar_lido(Feedback, feedback_id)
    return erro if erro else jsonify({"feedback": item.to_dict()})


# ---------------------------------------------------------------------- contatos --
def _limite_de_contatos() -> LimitePorIp:
    """Um limitador por instância do app. Criado sob demanda para o teste poder trocá-lo (relógio falso)."""
    extensoes = current_app.extensions
    if "limite_contatos" not in extensoes:
        extensoes["limite_contatos"] = LimitePorIp(
            current_app.config.get("CONTATOS_POR_IP_MAX", _CONTATOS_POR_IP_PADRAO),
            current_app.config.get("CONTATOS_JANELA_S", _CONTATOS_JANELA_S_PADRAO),
        )
    return extensoes["limite_contatos"]


@feedback_bp.post("/api/contatos")
def criar_contato():
    """PÚBLICA: o formulário de `/produto` não tem sessão. Validação estrita, consentimento explícito e limite por IP."""
    ip = request.remote_addr or "desconhecido"
    limite = _limite_de_contatos()
    espera = limite.segundos_para_liberar(ip)
    if espera:
        resposta, status = _erro(f"Muitas mensagens deste endereço. Tente de novo em {max(1, espera // 60)} min.", status=429)
        resposta.headers["Retry-After"] = str(espera)
        return resposta, status

    corpo = request.get_json(silent=True)
    if not isinstance(corpo, dict):
        return _erro("Envie um JSON com os dados do contato.")
    nome, falha = _texto(corpo.get("nome"), rotulo="Nome", maximo=_MAXIMO_NOME)
    if falha:
        return _erro(falha, "nome")
    empresa, falha = _texto(corpo.get("empresa"), rotulo="Empresa", maximo=_MAXIMO_EMPRESA, obrigatorio=False)
    if falha:
        return _erro(falha, "empresa")
    email, falha = _texto(corpo.get("email"), rotulo="E-mail", maximo=_MAXIMO_EMAIL)
    if falha:
        return _erro(falha, "email")
    if not _EMAIL.match(email):
        return _erro("E-mail: informe um endereço válido, como nome@empresa.com.br.", "email")
    mensagem, falha = _texto(corpo.get("mensagem"), rotulo="Mensagem", maximo=TAMANHO_MAXIMO_FEEDBACK)
    if falha:
        return _erro(falha, "mensagem")
    if corpo.get("consentimento") is not True:
        return _erro("Marque o consentimento para guardarmos seus dados e respondermos o contato.", "consentimento")

    db.session.add(Contato(nome=nome, empresa=empresa or None, email=email, mensagem=mensagem, consentimento=True))
    db.session.commit()
    limite.registrar(ip)
    return jsonify({"ok": True}), 201


@feedback_bp.get("/api/contatos")
@require_role(ROLE_SUPERVISOR, sempre=True)
def listar_contatos():
    itens, nao_lidos = _listar(Contato)
    return jsonify({"items": [i.to_dict() for i in itens], "count": len(itens), "nao_lidos": nao_lidos})


@feedback_bp.post("/api/contatos/<int:contato_id>/lido")
@require_role(ROLE_SUPERVISOR, sempre=True)
def marcar_contato_lido(contato_id: int):
    item, erro = _marcar_lido(Contato, contato_id)
    return erro if erro else jsonify({"contato": item.to_dict()})
