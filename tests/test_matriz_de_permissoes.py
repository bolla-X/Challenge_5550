"""Matriz de permissões: todo endpoint REST e todo evento de socket × cada papel.

A MISSÃO 4 (Fase 1, item 3) pede: "para cada endpoint REST e evento de socket,
teste com cada papel e sem sessão; o resultado tem que bater com a tabela de
papéis do README". `tests/test_auth.py` varre "toda rota exige sessão" e
`tests/test_escopo_camera.py` / `tests/test_escopo_socket.py` fixam o escopo do
Operador em casos escolhidos. O que faltava era a grade inteira: uma célula por
(endpoint, método, papel), com o ESPERADO escrito à mão a partir do README — não
copiado do que o código devolve.

Fonte de verdade das expectativas (nesta ordem): README.md, seção
"Autenticação e papéis" (papéis hierárquicos; operador restrito à câmera do
próprio setor; operador sem setor não vê nada; toda rota da API exige sessão),
depois `app/utils/auth.py` (404 fora do escopo, 403 sem setor, 403 papel
insuficiente, 401 sem sessão). A saída medida está em
`docs/NEXT2026/PERMISSOES.md`.

As seis colunas de cada linha, nesta ordem:

    anon          sem sessão
    op            operador da câmera 1, acessando recurso da câmera 1
    op_fora       o MESMO operador acessando o recurso da câmera 2
    op_sem_setor  operador sem `camera_id` (recurso da câmera 1)
    tec           técnico (recurso da câmera 2, para provar que vê o parque)
    sup           supervisor (recurso da câmera 2)

Cada célula é um status exato ("401", "403", "404") ou "ok" = o pedido passou da
autorização e do escopo e chegou na regra de negócio (qualquer status de `ok`
da linha: 200, 201, 409 por câmera sem sinal etc. — NUNCA 401/403, validado
abaixo). Rota sem recurso por câmera repete o mesmo valor em `op` e `op_fora`.

Divergência entre o README e o código é BUG DE SEGURANÇA: o teste da célula
fica como `xfail(strict=True, reason="BUG-SEG: ...")` em `DIVERGENCIAS` — quando
a correção entrar, o XPASS estrito derruba a suíte e obriga a remover a marca.

Nada aqui chama o pipeline de visão: câmeras do tipo Arquivo apontando para
arquivo inexistente, sem loop de captura (`INFERENCIA_ASSINCRONA=False`, socket
sem `start_background_task`), sem YOLO (`MULTI_PERSON_DETECTION=False` e
features pesadas desligadas) e `cv2` da descoberta de webcams substituído.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import pytest
from app import create_app
from app.config import AuthTestConfig
from app.extensions import db, socketio
from app.models import (
    DEFAULT_CAMERA_FEATURES,
    ROLE_OPERATOR,
    ROLE_SUPERVISOR,
    ROLE_TECHNICAL,
    Camera,
    Incidente,
    Missao,
    PermissaoDeTrabalho,
    User,
    utc_now,
)
from app.repositories.alert_repository import AlertRepository
from app.repositories.event_repository import EventRepository
from app.services.auth_service import hash_password
from app.services.palco import Palco
from app.utils.salas import emitir_para_camera, emitir_para_foco

SENHA = "senha-forte-de-teste"
RAIZ_DO_PROJETO = Path(__file__).resolve().parent.parent

ANON, OP, OP_FORA, OP_SEM_SETOR, TEC, SUP = "anon", "op", "op_fora", "op_sem_setor", "tec", "sup"
PAPEIS = (ANON, OP, OP_FORA, OP_SEM_SETOR, TEC, SUP)

# Quem é quem no banco semeado. Os ids saem da ordem de inserção (1..4) e são
# os mesmos em todo app montado aqui — é isso que deixa o cookie de sessão
# emitido pelo login real valer nos apps seguintes (mesma SECRET_KEY, mesmo
# `session_epoch`).
CONTAS = {
    OP: ("ana@fabrica.com", "Ana", ROLE_OPERATOR, "c1"),
    OP_SEM_SETOR: ("semsetor@fabrica.com", "Sem Setor", ROLE_OPERATOR, None),
    TEC: ("tec@fabrica.com", "Tec", ROLE_TECHNICAL, None),
    SUP: ("sup@fabrica.com", "Sup", ROLE_SUPERVISOR, None),
}
CONTA_DO_PAPEL = {ANON: None, OP: OP, OP_FORA: OP, OP_SEM_SETOR: OP_SEM_SETOR, TEC: TEC, SUP: SUP}

NOME_DA_CAMERA = {"c1": "Portaria", "c2": "Almoxarifado"}
# Quantos alertas cada câmera recebe na semente: números DIFERENTES para que uma
# soma vazada (risk-score, relatório) não seja confundida com a câmera certa.
ALERTAS_NA_CAMERA = {"c1": 1, "c2": 2}

JPEG_MINIMO = b"\xff\xd8\xff\xd9"
POLIGONO = [{"x": 0.1, "y": 0.1}, {"x": 0.9, "y": 0.1}, {"x": 0.5, "y": 0.9}]
RECURSOS_DE_CAMERA = ("cam", "alerta", "incidente", "snap")


# ============================================================ app e semente ==
class _CapturaFalsa:
    """Webcam que não existe: `GET /api/cameras/discover` abriria hardware de verdade."""

    def __init__(self, *_args, **_kwargs) -> None:
        pass

    def isOpened(self) -> bool:  # noqa: N802  (API do cv2)
        return False

    def read(self):
        return False, None

    def release(self) -> None:
        pass


_CV2_FALSO = SimpleNamespace(VideoCapture=_CapturaFalsa)


class _SocketMudo:
    """Mesmo papel do `DummySocket` do conftest: o monitor emite para o vazio e
    `start_background_task` NUNCA dispara a thread do loop de captura."""

    def emit(self, *_args, **_kwargs) -> None:
        pass

    def start_background_task(self, *_args, **_kwargs):
        return None


def _config(raiz: Path) -> type[AuthTestConfig]:
    class Cfg(AuthTestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{raiz / 'matriz.db'}"
        # Registra também `POST /api/demo/reset`, para a varredura enxergar a
        # lista COMPLETA de rotas que um deploy em modo demo expõe.
        DEMO_MODE = True
        # Sem agendador: `start()` não sobe a thread de inferência.
        INFERENCIA_ASSINCRONA = False
        # Sem detector de pessoa: `/status` e `/preflight` não carregam pesos.
        MULTI_PERSON_DETECTION = False
        SNAPSHOT_DIR = str(raiz / "snapshots")
        REPLAY_DIR = str(raiz / "clips")
        ROTULOS_DIR = str(raiz / "rotulos")
        TRILHAS_DIR = str(raiz / "trilhas")
        # Sem gravações de demonstração e sem fixture da prova de escala: as
        # rotas respondem "indisponível" (404/409) em vez de decodificar vídeo.
        DESAFIO_FIXTURES_DIR = str(raiz / "sem-gravacoes")
        ESCALA_FIXTURE = "tests/fixtures/__nao_existe__.mp4"
        LAB_PERGUNTE_ATIVO = False

    return Cfg


def _features_sem_modelo() -> dict[str, bool]:
    """Tudo desligado: `_needs_yolo_detection()` falso, nenhum peso é carregado."""
    return {chave: False for chave in DEFAULT_CAMERA_FEATURES}


def _montar_app(raiz: Path):
    """App real + banco semeado. Devolve `(app, ids)`; sem app_context aberto."""
    raiz.mkdir(parents=True, exist_ok=True)
    app = create_app(_config(raiz))
    ids: dict[str, Any] = {}
    with app.app_context():
        db.create_all()
        cameras = {
            chave: Camera(
                name=nome, location=nome, source_type="Arquivo", source=f"inexistente-{chave}.mp4",
                features_json=_features_sem_modelo(),
            )
            for chave, nome in NOME_DA_CAMERA.items()
        }
        db.session.add_all(cameras.values())
        db.session.commit()
        for chave, camera in cameras.items():
            ids[chave] = camera.id

        # Direto na tabela, com UM hash calculado uma vez: o scrypt de
        # `AuthService.create_user` custa ~0,1 s por pessoa e a matriz monta um
        # app por célula. O login em si é exercitado de verdade em
        # `cookies_de_sessao` (e em tests/test_auth.py).
        hash_comum = _hash_da_senha()
        for papel, (email, nome, funcao, camera) in CONTAS.items():
            usuario = User(
                email=email, name=nome, password_hash=hash_comum, role=funcao,
                camera_id=ids[camera] if camera else None,
            )
            db.session.add(usuario)
            db.session.commit()
            ids[f"u_{papel}"] = usuario.id
        ids["alvo"] = ids[f"u_{OP_SEM_SETOR}"]

        monitor = app.extensions["monitor_service"]
        monitor.socketio = _SocketMudo()
        monitor.load_cameras_from_db()

        pasta_snap, pasta_clips = Path(raiz / "snapshots"), Path(raiz / "clips")
        pasta_snap.mkdir(parents=True, exist_ok=True)
        for chave, quantidade in ALERTAS_NA_CAMERA.items():
            for n in range(quantidade):
                alerta = AlertRepository().create(
                    rule="missing_helmet", severity="critical", message=f"alerta {n} em {NOME_DA_CAMERA[chave]}",
                    feature="helmet", camera_id=ids[chave], metadata={"person_id": f"person_{n}"},
                )
                if n:
                    continue
                arquivo = f"alert_{alerta.id}_missing_helmet_20261015.jpg"
                (pasta_snap / arquivo).write_bytes(JPEG_MINIMO)
                AlertRepository().update_frame_ref(alerta, f"/snapshots/{arquivo}")
                clipe = pasta_clips / f"alert_{alerta.id}"
                clipe.mkdir(parents=True, exist_ok=True)
                (clipe / "clip.json").write_text(json.dumps({"quadros": 1}), encoding="utf-8")
                (clipe / "0000.jpg").write_bytes(JPEG_MINIMO)
                ids[f"a{chave[1]}"] = alerta.id
                ids[f"snap{chave[1]}"] = arquivo
                incidente = Incidente(
                    camera_id=ids[chave], rule="missing_helmet", feature="helmet", zona="Zona A", severity="critical",
                    titulo="Sem capacete", alert_ids=[alerta.id], pessoas=["person_0"], pico_pessoas=1,
                )
                db.session.add(incidente)
                db.session.commit()
                ids[f"i{chave[1]}"] = incidente.id
            EventRepository().create(
                event_type="sonda", message=f"evento em {NOME_DA_CAMERA[chave]}", camera_id=ids[chave]
            )
        missao = Missao(titulo="Missão de teste", tipo="rotulo", alvo=5)
        db.session.add(missao)
        db.session.commit()
        ids["missao"] = missao.id
        agora = utc_now()
        for chave in NOME_DA_CAMERA:
            permissao = PermissaoDeTrabalho(
                numero=f"PT-2026-000{chave[1]}", camera_id=ids[chave], tipo="geral", descricao="Serviço de teste",
                responsavel="Responsável de teste", inicio=agora - timedelta(hours=1), fim=agora + timedelta(hours=4),
                epis_exigidos=["helmet"], criada_por="supervisor@fabrica.com",
            )
            db.session.add(permissao)
            db.session.commit()
            ids[f"p{chave[1]}"] = permissao.id
        db.session.remove()

    app.extensions["palco"] = Palco()
    ids["token_palco"] = app.extensions["palco"].token
    return app, ids


_HASH_CACHE: dict[str, str] = {}


def _hash_da_senha() -> str:
    if "hash" not in _HASH_CACHE:
        _HASH_CACHE["hash"] = hash_password(SENHA)
    return _HASH_CACHE["hash"]


def _soltar_banco(app) -> None:
    """Fecha as conexões do SQLite (no Windows o arquivo não some enquanto aberto)."""
    with app.app_context():
        db.session.remove()
        db.engine.dispose()


@pytest.fixture(scope="module")
def molde(tmp_path_factory):
    """Banco + arquivos semeados UMA vez, e o cookie de cada conta emitido pelo LOGIN REAL.

    Cada célula da matriz parte de uma CÓPIA deste molde (rotas que apagam
    câmera, usuário e alerta não podem contaminar a célula seguinte) e reaproveita
    os cookies, que continuam válidos porque os usuários vêm com os mesmos ids e
    o mesmo `session_epoch`.
    """
    raiz = tmp_path_factory.mktemp("matriz-molde")
    app, ids = _montar_app(raiz)
    cookies: dict[str, str] = {}
    try:
        for papel, (email, _nome, _funcao, _camera) in CONTAS.items():
            cliente = app.test_client()
            resposta = cliente.post("/api/auth/login", json={"email": email, "password": SENHA})
            assert resposta.status_code == 200, f"login de {email} falhou: {resposta.status_code}"
            cookie = cliente.get_cookie("session")
            assert cookie is not None, f"login de {email} não emitiu cookie de sessão"
            cookies[papel] = cookie.value
    finally:
        _soltar_banco(app)
    return SimpleNamespace(raiz=raiz, ids=ids, cookies=cookies)


def _clonar_app(molde, raiz: Path):
    """App novo sobre uma cópia do molde: mesmos ids, mesmos arquivos, estado em memória virgem."""
    raiz.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(molde.raiz / "matriz.db", raiz / "matriz.db")
    for pasta in ("snapshots", "clips"):
        shutil.copytree(molde.raiz / pasta, raiz / pasta)
    app = create_app(_config(raiz))
    with app.app_context():
        monitor = app.extensions["monitor_service"]
        mudo = _SocketMudo()
        monitor.socketio = mudo
        monitor.load_cameras_from_db()
        # O banco copiado já tem câmeras: o `create_app` montou os workers com o socketio REAL e o
        # `load_cameras_from_db` acima os reaproveita (config igual). Sem isto, `POST .../start` subia o
        # loop de captura de verdade, que ficava vivo até o fim da suíte (11 threads, ~4 núcleos).
        for worker in list(monitor._workers.values()):
            worker.socketio = mudo
        db.session.remove()
    app.extensions["palco"] = Palco()
    return app, dict(molde.ids, token_palco=app.extensions["palco"].token)


class Mundo:
    """O app da célula, as contas semeadas e um cliente HTTP por papel."""

    def __init__(self, app, ids, cookies) -> None:
        self.app, self.ids, self._cookies = app, ids, cookies

    def cliente(self, papel: str):
        cliente = self.app.test_client()
        conta = CONTA_DO_PAPEL[papel]
        if conta is not None:
            cliente.set_cookie("session", self._cookies[conta])
        return cliente

    def substituicoes(self, papel: str) -> dict[str, Any]:
        """Recurso 'de dentro' (câmera 1) para quem é do setor; câmera 2 para o resto.

        Técnico e supervisor são medidos contra a câmera 2 de propósito: é a que
        o operador NÃO alcança, então provam que eles veem o parque inteiro.
        """
        k = "1" if papel in (ANON, OP, OP_SEM_SETOR) else "2"
        return {
            "cam": self.ids[f"c{k}"], "alerta": self.ids[f"a{k}"], "incidente": self.ids[f"i{k}"],
            "snap": self.ids[f"snap{k}"], "permissao": self.ids[f"p{k}"], "alvo": self.ids["alvo"], "missao": self.ids["missao"],
            "token": self.ids["token_palco"], "setor": NOME_DA_CAMERA[f"c{k}"],
        }

    def nome_da_camera(self, camera_id: int | None) -> str | None:
        for chave, nome in NOME_DA_CAMERA.items():
            if self.ids[chave] == camera_id:
                return nome
        return None


@pytest.fixture()
def mundo(tmp_path, molde, monkeypatch):
    app, ids = _clonar_app(molde, tmp_path / "celula")
    monkeypatch.setattr("app.api.cameras.cv2", _CV2_FALSO)
    # O reset de verdade apaga `instance/demo/{clips,snapshots,trilhas}` e as
    # tabelas de histórico: numa máquina de desenvolvedor isso destrói dado.
    # Aqui interessa só QUEM consegue chamar (a autorização é a parte real).
    monkeypatch.setattr("app.api.demo.resetar_no_servidor", lambda _app: {"ok": True})
    token = tmp_path / "token-da-demo"
    token.write_text("token-da-demo-de-teste", encoding="utf-8")
    monkeypatch.setattr("app.api.demo.TOKEN", token)
    yield Mundo(app, ids, molde.cookies)
    _soltar_banco(app)


# ================================================================== tabela ==
@dataclass(frozen=True)
class Linha:
    metodo: str
    regra: str  # exatamente como o Flask a registra: é a chave da varredura
    caminho: str  # URL com {placeholders} resolvidos por papel
    esperado: dict[str, str]
    corpo: Any = None
    ok: tuple[int, ...] = (200,)
    corpo_ok: str | None = None  # trecho que a resposta "ok" precisa ter (desambigua 404 de escopo)
    stream: bool = False
    publica_por: str | None = None  # por que a célula `anon` NÃO é 401 (exceção documentada)
    variante: str = ""

    @property
    def id(self) -> str:
        return f"{self.metodo} {self.caminho}{self.variante}"


def L(
    metodo: str, regra: str, esp: str, caminho: str | None = None, *, corpo: Any = None, ok: tuple[int, ...] = (200,),
    corpo_ok: str | None = None, stream: bool = False, publica_por: str | None = None, variante: str = "",
) -> Linha:
    colunas = esp.split()
    assert len(colunas) == len(PAPEIS), f"{metodo} {regra}: esperava 6 colunas, vieram {esp!r}"
    return Linha(
        metodo, regra, caminho if caminho is not None else regra, dict(zip(PAPEIS, colunas, strict=True)),
        corpo, ok, corpo_ok, stream, publica_por, variante,
    )


# Perfis de expectativa que se repetem. Ordem: anon op op_fora op_sem_setor tec sup.
PUBLICA = "ok ok ok ok ok ok"  # sem sessão passa (exceção documentada em `publica_por`)
QUALQUER_LOGADO = "401 ok ok ok ok ok"  # autenticado; sem recurso por câmera (o escopo está no CONTEÚDO)
DA_CAMERA = "401 ok 404 403 ok ok"  # recurso de uma câmera: fora do setor 404, sem setor 403
LEGADA = "401 ok ok 403 ok ok"  # rota legada "da câmera padrão": o operador cai no setor dele
PARQUE = "401 ok ok 403 ok ok"  # listagem do parque (exige_setor): operador vê o setor dele; sem setor, 403
TEC_OU_MAIS = "401 403 403 403 ok ok"
SO_SUPERVISOR = "401 403 403 403 403 ok"

SHELL_DO_SPA = "HTML estático do build React: não carrega dado nenhum, o dado vem de /api (401 sem sessão)"
PWA = "arquivo estático do PWA (service worker / manifesto) que o navegador pede antes de qualquer login"
LOGIN = "é o próprio login: ninguém tem sessão antes dele"
TOKEN_CELULAR = "o celular não tem sessão: só aceita quadro com o token da câmera (desconhecido -> 404)"
TOKEN_PALCO = "o celular de controle do palco não tem sessão: vale o token do QR (?t=), que só muda a cena"
TOKEN_ERRADO = "token informado e errado: 403 para qualquer papel (a rota decide pelo token antes da sessão)"
TOKEN_DEMO ="terminal da demo manda X-Demo-Token; sem ele e sem supervisor, 403 (não 401) por desenho"

LINHAS: list[Linha] = [
    # ---------------------------------------------------- shell do SPA e PWA --
    *[
        L("GET", regra, PUBLICA, publica_por=SHELL_DO_SPA)
        for regra in (
            "/", "/dashboard", "/dashboard/", "/portal", "/tv", "/rotular", "/desafio", "/gemeo", "/simulador",
            "/auditoria", "/palco", "/palco/controle", "/retrospectiva", "/liga", "/evacuacao", "/torre", "/regras", "/produto",
            "/caixa-de-entrada", "/ajuda", "/intervencoes", "/busca",
            "/permissoes", "/primeiro-acesso", "/novidades", "/configuracoes",
        )
    ],
    L("GET", "/sw.js", PUBLICA, publica_por=PWA),
    L("GET", "/manifest.webmanifest", PUBLICA, publica_por=PWA),
    L("GET", "/cam", PUBLICA, publica_por="página do celular-câmera: HTML estático sem dado, o token vem na URL"),
    # --------------------------------------------------------- autenticação --
    L("POST", "/api/auth/login", PUBLICA, corpo={}, ok=(400,), publica_por=LOGIN),
    L("POST", "/api/auth/logout", PUBLICA, ok=(200,), publica_por="idempotente e não expõe nada"),
    L("GET", "/api/auth/me", PUBLICA, ok=(200,),
      publica_por="o frontend chama no boot para decidir se mostra o login: 200 com user=null, não 401"),
    L("POST", "/api/auth/password", "401 ok ok ok ok ok", corpo={"current_password": SENHA, "new_password": "x"},
      ok=(400,)),
    L("GET", "/api/users", SO_SUPERVISOR),
    L("POST", "/api/users", SO_SUPERVISOR, corpo={}, ok=(400,)),
    L("PATCH", "/api/users/<int:user_id>", SO_SUPERVISOR, "/api/users/{alvo}", corpo={"name": "Renomeado"}),
    L("DELETE", "/api/users/<int:user_id>", SO_SUPERVISOR, "/api/users/{alvo}"),
    # --------------------------------------------------------------- alertas --
    L("GET", "/alerts", QUALQUER_LOGADO),
    L("GET", "/alerts/<int:alert_id>/evidence", DA_CAMERA, "/alerts/{alerta}/evidence"),
    L("GET", "/api/alerts/<int:alert_id>/clip", DA_CAMERA, "/api/alerts/{alerta}/clip"),
    L("GET", "/api/alerts/<int:alert_id>/clip/<int:indice>.jpg", DA_CAMERA, "/api/alerts/{alerta}/clip/0.jpg"),
    L("POST", "/alerts/<int:alert_id>/false-positive", DA_CAMERA, "/alerts/{alerta}/false-positive",
      corpo={"reason": "teste de permissão"}),
    L("POST", "/alerts/<int:alert_id>/acknowledge", DA_CAMERA, "/alerts/{alerta}/acknowledge", corpo={"note": "avisei"}),
    L("POST", "/alerts/acknowledge-all", "401 ok ok 403 ok ok"),
    L("POST", "/alerts/resolve-active", TEC_OU_MAIS),
    L("DELETE", "/alerts/resolved", SO_SUPERVISOR),
    # --------------------------------------------------------------- câmeras --
    L("GET", "/api/cameras/discover", TEC_OU_MAIS, "/api/cameras/discover?max_index=1"),
    L("GET", "/api/cameras", QUALQUER_LOGADO),
    L("GET", "/api/cameras/<int:camera_id>", DA_CAMERA, "/api/cameras/{cam}"),
    L("POST", "/api/cameras", TEC_OU_MAIS, corpo={"name": "Nova", "source_type": "Arquivo", "source": "nova.mp4"},
      ok=(201,)),
    L("PUT", "/api/cameras/<int:camera_id>", TEC_OU_MAIS, "/api/cameras/{cam}", corpo={"name": "Renomeada"}),
    L("PATCH", "/api/cameras/<int:camera_id>", TEC_OU_MAIS, "/api/cameras/{cam}", corpo={"name": "Renomeada"}),
    L("DELETE", "/api/cameras/<int:camera_id>", TEC_OU_MAIS, "/api/cameras/{cam}"),
    L("GET", "/api/cameras/<int:camera_id>/status", DA_CAMERA, "/api/cameras/{cam}/status"),
    L("POST", "/api/cameras/<int:camera_id>/start", DA_CAMERA, "/api/cameras/{cam}/start"),
    L("POST", "/api/cameras/<int:camera_id>/stop", DA_CAMERA, "/api/cameras/{cam}/stop"),
    L("GET", "/api/cameras/<int:camera_id>/video_feed", DA_CAMERA, "/api/cameras/{cam}/video_feed", stream=True),
    L("GET", "/api/cameras/<int:camera_id>/conformidade-por-id", DA_CAMERA, "/api/cameras/{cam}/conformidade-por-id"),
    L("GET", "/api/cameras/<int:camera_id>/conformidade-por-id/<pessoa_id>", DA_CAMERA,
      "/api/cameras/{cam}/conformidade-por-id/person_9", ok=(404,), corpo_ok="ID de rastreio"),
    L("GET", "/api/cameras/<int:camera_id>/planta", DA_CAMERA, "/api/cameras/{cam}/planta"),
    L("PUT", "/api/cameras/<int:camera_id>/planta", TEC_OU_MAIS, "/api/cameras/{cam}/planta",
      corpo={"pontos_camera": None}),
    L("GET", "/api/cameras/<int:camera_id>/mapa-de-calor", DA_CAMERA, "/api/cameras/{cam}/mapa-de-calor"),
    L("GET", "/api/cameras/<int:camera_id>/saude-visual", DA_CAMERA, "/api/cameras/{cam}/saude-visual"),
    L("POST", "/api/cameras/<int:camera_id>/saude-visual/referencia", TEC_OU_MAIS,
      "/api/cameras/{cam}/saude-visual/referencia", ok=(409,)),  # 409: câmera sem quadro para virar referência
    L("PATCH", "/api/cameras/<int:camera_id>/privacidade", SO_SUPERVISOR, "/api/cameras/{cam}/privacidade",
      corpo={"ativa": True, "motivo": "teste"}),
    L("GET", "/api/cameras/<int:camera_id>/frame.jpg", DA_CAMERA, "/api/cameras/{cam}/frame.jpg"),
    L("GET", "/api/cameras/<int:camera_id>/analysis", DA_CAMERA, "/api/cameras/{cam}/analysis"),
    L("GET", "/api/cameras/<int:camera_id>/gate", DA_CAMERA, "/api/cameras/{cam}/gate"),
    L("GET", "/api/cameras/<int:camera_id>/portal", DA_CAMERA, "/api/cameras/{cam}/portal"),
    L("PUT", "/api/cameras/<int:camera_id>/gate", TEC_OU_MAIS, "/api/cameras/{cam}/gate", corpo={"required": ["helmet"]}),
    L("GET", "/api/cameras/<int:camera_id>/risk-area", DA_CAMERA, "/api/cameras/{cam}/risk-area"),
    L("PUT", "/api/cameras/<int:camera_id>/risk-area", TEC_OU_MAIS, "/api/cameras/{cam}/risk-area",
      corpo={"name": "Zona", "polygon": POLIGONO}),
    L("PATCH", "/api/cameras/<int:camera_id>/risk-area", TEC_OU_MAIS, "/api/cameras/{cam}/risk-area",
      corpo={"name": "Zona", "polygon": POLIGONO}),
    L("GET", "/api/cameras/<int:camera_id>/area-deteccao", DA_CAMERA, "/api/cameras/{cam}/area-deteccao"),
    L("PUT", "/api/cameras/<int:camera_id>/area-deteccao", TEC_OU_MAIS, "/api/cameras/{cam}/area-deteccao",
      corpo={"polygon": POLIGONO}),
    L("DELETE", "/api/cameras/<int:camera_id>/area-deteccao", TEC_OU_MAIS, "/api/cameras/{cam}/area-deteccao"),
    # ----------------------------------------------------------- celular-câmera --
    L("POST", "/api/celular/<token>/quadro", PUBLICA, "/api/celular/token-inexistente/quadro", ok=(404,),
      publica_por=TOKEN_CELULAR),
    L("GET", "/api/cameras/<int:camera_id>/celular", TEC_OU_MAIS, "/api/cameras/{cam}/celular", ok=(409,)),
    # ------------------------------------------------------------- custódia --
    L("GET", "/api/custodia/verificar", TEC_OU_MAIS),
    L("GET", "/api/custodia/verificar", DA_CAMERA, "/api/custodia/verificar?incidente_id={incidente}",
      variante=" (de um incidente)"),
    L("GET", "/api/custodia", TEC_OU_MAIS),
    # ----------------------------------------------------------------- demo --
    L("POST", "/api/demo/reset", "403 403 403 403 403 ok", publica_por=TOKEN_DEMO),
    # -------------------------------------------------------------- desafio --
    L("GET", "/api/desafio/rodadas", QUALQUER_LOGADO, ok=(404,), corpo_ok="gravações de demonstração ausentes"),
    L("GET", "/api/desafio/<ident>/quadro/<int:k>.jpg", QUALQUER_LOGADO, "/api/desafio/bench/quadro/0.jpg", ok=(404,),
      corpo_ok="gravações de demonstração ausentes"),
    L("POST", "/api/desafio/<ident>/resposta", QUALQUER_LOGADO, "/api/desafio/bench/resposta", corpo={}, ok=(404,),
      corpo_ok="gravações de demonstração ausentes"),
    # ---------------------------------------------------------- diagnóstico --
    L("GET", "/model", LEGADA),
    L("GET", "/api/diagnostics/pipeline", QUALQUER_LOGADO),
    L("GET", "/api/status", TEC_OU_MAIS),
    L("GET", "/settings", LEGADA),
    L("PATCH", "/settings", TEC_OU_MAIS, corpo={"target_fps": 10}),
    L("GET", "/overlay", LEGADA),
    L("PATCH", "/overlay", TEC_OU_MAIS, corpo={"boxes": True}),
    L("GET", "/risk-area", LEGADA),
    L("PATCH", "/risk-area", TEC_OU_MAIS, corpo={"name": "Zona", "polygon": POLIGONO}),
    L("GET", "/events", QUALQUER_LOGADO),
    L("GET", "/snapshots/<path:filename>", DA_CAMERA, "/snapshots/{snap}"),
    # ---------------------------------------------------------------- escala --
    L("POST", "/api/escala", TEC_OU_MAIS, corpo={"n": 2}, ok=(409,)),
    L("DELETE", "/api/escala", TEC_OU_MAIS),
    L("GET", "/api/escala", TEC_OU_MAIS),
    # ------------------------------------------------------------ evacuação --
    # Iniciar/encerrar: supervisor OU token do palco (?t= ou corpo {"t"}). O corpo
    # de `iniciar` é inválido de propósito (400 = passou da autorização) para não
    # abrir uma evacuação de verdade; `encerrar` sem evacuação ativa dá 409.
    L("POST", "/api/evacuacao/iniciar", SO_SUPERVISOR, corpo={"ponto_de_encontro_camera_id": "abc"}, ok=(400,)),
    L("POST", "/api/evacuacao/iniciar", PUBLICA, "/api/evacuacao/iniciar?t={token}",
      corpo={"ponto_de_encontro_camera_id": "abc"}, ok=(400,), publica_por=TOKEN_PALCO, variante=" (com token do QR)"),
    L("POST", "/api/evacuacao/iniciar", PUBLICA, corpo={"t": "{token}", "ponto_de_encontro_camera_id": "abc"}, ok=(400,),
      publica_por=TOKEN_PALCO, variante=" (token no corpo)"),
    L("POST", "/api/evacuacao/iniciar", "403 403 403 403 403 403", "/api/evacuacao/iniciar?t=token-errado",
      corpo={"ponto_de_encontro_camera_id": "abc"}, publica_por=TOKEN_ERRADO, variante=" (token errado)"),
    L("POST", "/api/evacuacao/encerrar", SO_SUPERVISOR, ok=(409,)),
    L("POST", "/api/evacuacao/encerrar", PUBLICA, "/api/evacuacao/encerrar?t={token}", ok=(409,),
      publica_por=TOKEN_PALCO, variante=" (com token do QR)"),
    L("POST", "/api/evacuacao/encerrar", PUBLICA, corpo={"t": "{token}"}, ok=(409,),
      publica_por=TOKEN_PALCO, variante=" (token no corpo)"),
    L("POST", "/api/evacuacao/encerrar", "403 403 403 403 403 403", "/api/evacuacao/encerrar?t=token-errado",
      publica_por=TOKEN_ERRADO, variante=" (token errado)"),
    L("GET", "/api/evacuacao", TEC_OU_MAIS),
    L("GET", "/api/evacuacao/relatorios", TEC_OU_MAIS),
    L("GET", "/api/evacuacao/relatorios/<int:numero>", TEC_OU_MAIS, "/api/evacuacao/relatorios/999", ok=(404,)),
    # -------------------------------------------------------------- features --
    L("GET", "/features", QUALQUER_LOGADO),
    L("GET", "/features", DA_CAMERA, "/features?camera_id={cam}", variante=" (de uma câmera)"),
    L("PUT", "/features", TEC_OU_MAIS, corpo={"features": {"helmet": True}}),
    L("PATCH", "/features", TEC_OU_MAIS, corpo={"features": {"helmet": True}}),
    # ---------------------------------------------------------------- gêmeo --
    L("GET", "/api/gemeo", PARQUE),
    # busca nas trilhas (M6) e API documentada (M11)
    L("GET", "/api/busca/trilhas", TEC_OU_MAIS, ok=(400,)),
    L("GET", "/api/openapi.json", TEC_OU_MAIS),
    L("GET", "/api/docs", TEC_OU_MAIS),
    # intervenções e ROI (MISSÃO 4, M8)
    L("GET", "/api/intervencoes", TEC_OU_MAIS),
    L("POST", "/api/intervencoes", SO_SUPERVISOR, corpo={}, ok=(400,)),
    L("GET", "/api/intervencoes/<int:intervencao_id>", TEC_OU_MAIS, "/api/intervencoes/9999", ok=(404,)),
    L("PUT", "/api/intervencoes/<int:intervencao_id>", SO_SUPERVISOR, "/api/intervencoes/9999", corpo={}, ok=(404,)),
    L("DELETE", "/api/intervencoes/<int:intervencao_id>", SO_SUPERVISOR, "/api/intervencoes/9999", ok=(404,)),
    L("GET", "/api/intervencoes/<int:intervencao_id>/comparacao", TEC_OU_MAIS, "/api/intervencoes/9999/comparacao", ok=(404,)),
    L("POST", "/api/intervencoes/<int:intervencao_id>/roi", TEC_OU_MAIS, "/api/intervencoes/9999/roi", corpo={}, ok=(404, 400)),
    # feedback e contatos (MISSÃO 4, Fase 3 itens 10 e 11)
    L("POST", "/api/feedback", QUALQUER_LOGADO, corpo={"texto": "teste"}, ok=(201,)),
    L("GET", "/api/feedback", SO_SUPERVISOR),
    L("POST", "/api/feedback/<int:feedback_id>/lido", SO_SUPERVISOR, "/api/feedback/9999/lido", ok=(404,)),
    L("POST", "/api/contatos", PUBLICA, corpo={}, ok=(400,),
      publica_por="formulário público de /produto: só grava, valida, exige consentimento e tem limite por IP"),
    L("GET", "/api/contatos", SO_SUPERVISOR),
    L("POST", "/api/contatos/<int:contato_id>/lido", SO_SUPERVISOR, "/api/contatos/9999/lido", ok=(404,)),
    L("DELETE", "/api/contatos/<int:contato_id>", SO_SUPERVISOR, "/api/contatos/9999", ok=(404,)),
    # primeiro acesso do supervisor (MISSÃO 4, Fase 3 item 2)
    L("GET", "/api/onboarding", SO_SUPERVISOR),
    L("PUT", "/api/onboarding/<passo>", SO_SUPERVISOR, "/api/onboarding/camera", corpo={"estado": "pendente"}),
    L("POST", "/api/onboarding/refazer", SO_SUPERVISOR),
    L("POST", "/api/onboarding/concluir", SO_SUPERVISOR),
    # ------------------------------------------------------- integração (torre) --
    L("GET", "/api/integracao/estado", LEGADA),
    # ------------------------------------------------- permissão de trabalho --
    L("GET", "/api/permissoes", QUALQUER_LOGADO),
    L("POST", "/api/permissoes", TEC_OU_MAIS, corpo={}, ok=(400,)),
    L("GET", "/api/permissoes/<int:permissao_id>", DA_CAMERA, "/api/permissoes/{permissao}"),
    L("POST", "/api/permissoes/<int:permissao_id>/encerrar", TEC_OU_MAIS, "/api/permissoes/{permissao}/encerrar"),
    L("POST", "/api/permissoes/<int:permissao_id>/cancelar", TEC_OU_MAIS, "/api/permissoes/{permissao}/cancelar"),
    L("GET", "/api/cameras/<int:camera_id>/zona-controlada", DA_CAMERA, "/api/cameras/{cam}/zona-controlada"),
    L("PUT", "/api/cameras/<int:camera_id>/zona-controlada", TEC_OU_MAIS, "/api/cameras/{cam}/zona-controlada",
      corpo={"exige_permissao": True}),
    # --------------------------------------------------- editor de regras --
    L("GET", "/api/regras", TEC_OU_MAIS),
    L("POST", "/api/regras", TEC_OU_MAIS, corpo={}, ok=(400,)),
    L("PUT", "/api/regras/<regra_id>", TEC_OU_MAIS, "/api/regras/inexistente", corpo={}, ok=(404,)),
    L("DELETE", "/api/regras/<regra_id>", TEC_OU_MAIS, "/api/regras/inexistente", ok=(404,)),
    L("POST", "/api/regras/<regra_id>/ativar", TEC_OU_MAIS, "/api/regras/inexistente/ativar", ok=(404,)),
    L("POST", "/api/regras/<regra_id>/desativar", TEC_OU_MAIS, "/api/regras/inexistente/desativar", ok=(404,)),
    L("POST", "/api/regras/testar", TEC_OU_MAIS, corpo={}, ok=(400,)),
    # ------------------------------------------------------------ incidentes --
    L("GET", "/api/incidentes", QUALQUER_LOGADO),
    L("GET", "/api/incidentes/<int:incidente_id>", DA_CAMERA, "/api/incidentes/{incidente}"),
    L("POST", "/api/incidentes/<int:incidente_id>/reconhecer", DA_CAMERA, "/api/incidentes/{incidente}/reconhecer"),
    L("GET", "/api/incidentes/<int:incidente_id>/linha-causal", DA_CAMERA, "/api/incidentes/{incidente}/linha-causal"),
    # ------------------------------------------------------------------- lab --
    L("GET", "/api/lab/pergunte", TEC_OU_MAIS),
    L("POST", "/api/lab/pergunte", TEC_OU_MAIS, corpo={"pergunta": "quantos alertas?"}, ok=(409,)),
    # ------------------------------------------------------- liga / retrospectiva --
    L("GET", "/api/liga", QUALQUER_LOGADO),
    L("GET", "/api/retrospectiva", QUALQUER_LOGADO),
    L("POST", "/api/liga/missoes", SO_SUPERVISOR, corpo={"tipo": "rotulo", "alvo": 5, "titulo": "Missão"}, ok=(201,)),
    L("DELETE", "/api/liga/missoes/<int:missao_id>", SO_SUPERVISOR, "/api/liga/missoes/{missao}"),
    # -------------------------------------------------------------- monitor --
    L("POST", "/start", LEGADA),
    L("POST", "/stop", LEGADA),
    # ----------------------------------------------------------------- palco --
    L("GET", "/api/palco/roteiro", QUALQUER_LOGADO),
    L("GET", "/api/palco/estado", TEC_OU_MAIS),
    L("GET", "/api/palco/estado", PUBLICA, "/api/palco/estado?t={token}", publica_por=TOKEN_PALCO,
      variante=" (com token do QR)"),
    L("GET", "/api/palco/estado", "403 403 403 403 403 403", "/api/palco/estado?t=token-errado",
      publica_por=TOKEN_ERRADO, variante=" (token errado)"),
    L("POST", "/api/palco/ir", TEC_OU_MAIS, corpo={"acao": "inexistente"}, ok=(400,)),
    L("POST", "/api/palco/ir", PUBLICA, "/api/palco/ir?t={token}", corpo={"acao": "inexistente"}, ok=(400,),
      publica_por=TOKEN_PALCO, variante=" (com token do QR)"),
    L("POST", "/api/palco/ir", "403 403 403 403 403 403", "/api/palco/ir?t=token-errado",
      corpo={"acao": "inexistente"}, publica_por=TOKEN_ERRADO, variante=" (token errado)"),
    L("GET", "/api/palco/controle", TEC_OU_MAIS),
    # ------------------------------------------------------------ relatório --
    L("GET", "/api/relatorio/turno", PARQUE),
    L("GET", "/relatorio/turno", PARQUE),
    L("POST", "/api/relatorio/turno/resumo", PARQUE),
    L("GET", "/api/relatorio/turno/resumo", PARQUE),
    # ----------------------------------------------------------- risk score --
    L("GET", "/api/relatorio/mensal", PARQUE),
    L("GET", "/relatorio/mensal", PARQUE),
    L("GET", "/risk-score", PARQUE),
    L("GET", "/risk-score/trend", PARQUE),
    # --------------------------------------------------------------- rótulos --
    L("GET", "/api/rotulos/proximo", TEC_OU_MAIS),
    L("GET", "/api/rotulos/<ident>.jpg", TEC_OU_MAIS, "/api/rotulos/inexistente.jpg", ok=(404,)),
    L("POST", "/api/rotulos/<ident>", TEC_OU_MAIS, "/api/rotulos/inexistente", corpo={"decisao": "confirmar"}, ok=(404,)),
    L("GET", "/api/rotulos/dataset.zip", TEC_OU_MAIS),
    # ------------------------------------------------------------- simulador --
    L("GET", "/api/simulador/contexto", TEC_OU_MAIS, "/api/simulador/contexto?camera_id={cam}"),
    L("POST", "/api/simulador", TEC_OU_MAIS, corpo={"camera_id": "{cam}", "horas": 1}, ok=(200, 409)),
    # ---------------------------------------------------------------- status --
    L("GET", "/status", LEGADA),
    L("GET", "/preflight", LEGADA),
    # ---------------------------------------------------------------- stream --
    L("GET", "/video_feed", LEGADA, stream=True),
    L("GET", "/analysis/latest", LEGADA),
    # -------------------------------------------------------------------- tv --
    L("GET", "/api/tv", PARQUE),
    L("GET", "/api/tv/metas", QUALQUER_LOGADO),
    L("PUT", "/api/tv/metas/<path:setor>", SO_SUPERVISOR, "/api/tv/metas/{setor}", corpo={"minutos_conformes": 30}),
]

# --------------------------------------------------------------------------
# Células em que o código DIVERGE do README. Cada uma é bug de segurança de
# prioridade máxima: o teste fica `xfail(strict=True)` e vira XPASS (e portanto
# falha, exigindo remover a entrada) no dia em que a correção entrar.
# Chave: (id da linha, papel). Preenchido a partir da medição — ver
# docs/NEXT2026/PERMISSOES.md.
_BUG_SNAPSHOT = (
    "BUG-SEG: GET /snapshots/<arquivo> só exige login e nunca aplica o escopo de câmera "
    "(app/api/diagnostics.py::get_snapshot): a evidência (imagem de pessoas) de um alerta de OUTRO setor é "
    "entregue a quem souber o nome do arquivo. /alerts/<id>/evidence, que serve o mesmo arquivo, respeita o escopo."
)
DIVERGENCIAS: dict[tuple[str, str], str] = {
    # D1/D2 (snapshot sem escopo) corrigidas na MISSÃO 4: app/api/diagnostics.py::get_snapshot.
}


def _validar_tabela() -> None:
    """Falha na importação se a própria tabela for incoerente."""
    for linha in LINHAS:
        assert not set(linha.ok) & {401, 403}, f"{linha.id}: `ok` não pode conter 401/403"
        for papel, valor in linha.esperado.items():
            assert valor in {"ok", "401", "403", "404"}, f"{linha.id}/{papel}: {valor!r}"


_validar_tabela()
_MEDIDOS: list[dict[str, Any]] = []


@pytest.fixture(scope="module", autouse=True)
def _gravar_medicao():
    """`VISIONEPI_MATRIZ_DUMP=<arquivo>` grava o status medido de cada célula (gera o PERMISSOES.md)."""
    yield
    destino = os.environ.get("VISIONEPI_MATRIZ_DUMP")
    if destino:
        # Uma célula por linha (JSON compacto): dá para ler e filtrar com grep.
        linhas = [json.dumps(medida, ensure_ascii=False) for medida in _MEDIDOS]
        Path(destino).write_text("\n".join(linhas) + "\n", encoding="utf-8")


def _resolver(valor: Any, subs: dict[str, Any]) -> Any:
    if isinstance(valor, dict):
        return {k: _resolver(v, subs) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_resolver(v, subs) for v in valor]
    if isinstance(valor, str):
        puro = re.fullmatch(r"\{(\w+)\}", valor)
        return subs[puro.group(1)] if puro else valor.format(**subs)
    return valor


def _texto_da_resposta(resposta) -> str:
    """Corpo legível: imagem/zip viram texto com substituição; JSON sai sem escapes `\\uXXXX`."""
    texto = resposta.get_data().decode("utf-8", errors="replace")
    try:
        return json.dumps(json.loads(texto), ensure_ascii=False)
    except ValueError:
        return texto


def _celulas() -> list:
    pares = []
    for linha in LINHAS:
        for papel in PAPEIS:
            marcas = []
            motivo = DIVERGENCIAS.get((linha.id, papel))
            if motivo:
                marcas.append(pytest.mark.xfail(strict=True, raises=AssertionError, reason=motivo))
            pares.append(pytest.param(linha, papel, id=f"{linha.id} :: {papel}", marks=marcas))
    return pares


@pytest.mark.parametrize(("linha", "papel"), _celulas())
def test_matriz_rest(mundo, linha, papel):
    subs = mundo.substituicoes(papel)
    caminho = linha.caminho.format(**subs)
    cliente = mundo.cliente(papel)
    try:
        resposta = cliente.open(caminho, method=linha.metodo, json=_resolver(linha.corpo, subs))
    except Exception as exc:  # noqa: BLE001  (no TestConfig o Flask propaga a exceção em vez de devolver 500)
        _MEDIDOS.append(_medida(linha, papel, f"EXC {type(exc).__name__}"))
        raise AssertionError(f"{linha.id} como {papel}: exceção não tratada {type(exc).__name__}: {exc}") from exc
    try:
        status = resposta.status_code
        texto = "" if linha.stream else _texto_da_resposta(resposta)
    finally:
        resposta.close()  # fecha o gerador de vídeo: sem isto ele ficaria registrado como espectador
    _MEDIDOS.append(_medida(linha, papel, str(status)))

    esperado = linha.esperado[papel]
    if esperado == "ok":
        assert status in linha.ok, (
            f"{linha.id} como {papel}: o pedido deveria passar da autorização (status em {linha.ok}) "
            f"e voltou {status}: {texto[:200]}"
        )
        if linha.corpo_ok:
            assert linha.corpo_ok in texto, f"{linha.id} como {papel}: resposta sem {linha.corpo_ok!r}: {texto[:200]}"
    else:
        assert status == int(esperado), (
            f"{linha.id} como {papel}: esperado {esperado} (README + app/utils/auth.py), voltou {status}: {texto[:200]}"
        )
        if esperado == "404" and linha.corpo_ok:
            # O 404 de escopo tem texto próprio; um 404 "de negócio" não vale.
            assert "câmera não encontrada" in texto, f"{linha.id} como {papel}: 404 que não é de escopo: {texto[:200]}"


def _medida(linha: Linha, papel: str, obtido: str) -> dict[str, Any]:
    return {
        "metodo": linha.metodo, "regra": linha.regra, "caminho": linha.caminho, "variante": linha.variante,
        "papel": papel, "esperado": linha.esperado[papel], "obtido": obtido, "publica_por": linha.publica_por,
        "diverge": (linha.id, papel) in DIVERGENCIAS,
    }


# ============================================================ varredura (guard) ==
def _regras_do_app(app) -> set[tuple[str, str]]:
    return {
        (metodo, regra.rule)
        for regra in app.url_map.iter_rules()
        if regra.endpoint != "static"
        for metodo in regra.methods - {"HEAD", "OPTIONS"}
    }


def test_toda_rota_registrada_esta_na_tabela(mundo):
    """Endpoint novo sem classificação FALHA aqui — é isto que impede a matriz de apodrecer.

    Ao adicionar uma rota: acrescente a linha em `LINHAS` com o esperado tirado do
    README (e da regra de escopo), nunca do que a rota devolve hoje.
    """
    no_app = _regras_do_app(mundo.app)
    na_tabela = {(linha.metodo, linha.regra) for linha in LINHAS}
    sem_linha = sorted(no_app - na_tabela)
    obsoletas = sorted(na_tabela - no_app)
    assert not sem_linha, (
        "rotas registradas SEM expectativa na matriz de permissões (classifique cada uma em LINHAS): "
        + ", ".join(f"{m} {r}" for m, r in sem_linha)
    )
    assert not obsoletas, (
        "linhas da matriz sem rota correspondente (rota removida ou regra digitada errado): "
        + ", ".join(f"{m} {r}" for m, r in obsoletas)
    )


def test_rotas_condicionais_ao_demo_estao_na_varredura(mundo):
    """A varredura roda com DEMO_MODE=True; sem isso `POST /api/demo/reset` ficaria de fora."""
    assert ("POST", "/api/demo/reset") in _regras_do_app(mundo.app)


# ----------------------------------------------- coerência da própria tabela --
def _acesso(linha: Linha, papel: str) -> bool:
    return linha.esperado[papel] == "ok"


@pytest.mark.parametrize("linha", LINHAS, ids=lambda linha: linha.id)
def test_tabela_respeita_a_hierarquia_do_readme(linha):
    """Papéis hierárquicos e escopo: a tabela não pode prometer mais a quem tem menos."""
    assert _acesso(linha, SUP) or not _acesso(linha, TEC), "técnico com acesso e supervisor sem: papéis são hierárquicos"
    assert _acesso(linha, TEC) or not _acesso(linha, OP), "operador com acesso e técnico sem: papéis são hierárquicos"
    assert _acesso(linha, OP) or not _acesso(linha, OP_FORA), "fora do setor com mais acesso que o próprio setor"
    assert _acesso(linha, OP) or not _acesso(linha, OP_SEM_SETOR), "operador sem setor com mais acesso que o com setor"
    assert _acesso(linha, OP_SEM_SETOR) or not _acesso(linha, ANON), "sem sessão com mais acesso que o operador sem setor"


@pytest.mark.parametrize("linha", LINHAS, ids=lambda linha: linha.id)
def test_sem_sessao_e_401_salvo_excecao_documentada(linha):
    """README: 'todas as rotas da API exigem sessão'. Exceção só com motivo escrito."""
    if linha.esperado[ANON] == "401":
        assert linha.publica_por is None
        return
    assert linha.publica_por, f"{linha.id}: anon != 401 exige `publica_por` explicando a exceção"


def test_demais_rotas_da_api_nao_tem_excecao_alem_das_documentadas():
    """Lista fechada: só estas rotas da API (e das legadas) respondem sem sessão."""
    publicas = {
        (linha.metodo, linha.caminho.split("?")[0]) for linha in LINHAS if linha.esperado[ANON] != "401"
    }
    esperadas_na_api = {
        ("POST", "/api/auth/login"), ("POST", "/api/auth/logout"), ("GET", "/api/auth/me"),
        ("POST", "/api/celular/token-inexistente/quadro"), ("POST", "/api/demo/reset"),
        ("GET", "/api/palco/estado"), ("POST", "/api/palco/ir"),
        ("POST", "/api/evacuacao/iniciar"), ("POST", "/api/evacuacao/encerrar"),
        # formulário público de /produto (só grava, com consentimento e limite por IP)
        ("POST", "/api/contatos"),
    }
    na_api = {item for item in publicas if item[1].startswith("/api/")}
    assert na_api == esperadas_na_api, f"exceções à regra 'sem sessão = 401' mudaram: {sorted(na_api ^ esperadas_na_api)}"
    fora_da_api = {item for item in publicas if not item[1].startswith("/api/")}
    for metodo, caminho in fora_da_api:
        assert metodo == "GET", f"{metodo} {caminho}: rota fora de /api pública que não é GET"


def test_estaticos_so_expoem_o_build_e_a_pagina_do_celular(mundo):
    """`static` fica fora da matriz (é a pasta do build, pública por natureza) — então o que mora nela é o contrato."""
    pasta = Path(mundo.app.static_folder)
    assert sorted(item.name for item in pasta.iterdir()) == ["cam.html", "dist"], (
        "app/static passou a ter outro arquivo: tudo que está lá é servido SEM sessão em /static/"
    )
    anonimo = mundo.cliente(ANON)
    assert anonimo.get("/static/cam.html").status_code == 200
    assert anonimo.get("/static/%2e%2e/models.py").status_code == 404
    assert anonimo.get("/static/../models.py").status_code == 404


# ============================================ conteúdo: o escopo vale nos dados ==
@dataclass(frozen=True)
class Listagem:
    """Endpoint que devolve dado de várias câmeras. Status 200 não prova escopo: o CONTEÚDO prova."""

    nome: str
    caminho: str
    extrai: Callable[[Any, "Mundo"], Any]  # JSON (ou texto) -> o que foi visto
    modo: str = "nomes"  # "nomes": conjunto de nomes de câmera/setor; "contagem": número de alertas contados
    presenca: bool = True  # exige que o operador veja a PRÓPRIA câmera (contraprova: escopo != "ninguém vê nada")
    json: bool = True


def _nomes_alertas(corpo, mundo):
    return {mundo.nome_da_camera(item["camera_id"]) for item in corpo["items"]} - {None}


def _nomes_html(texto, _mundo):
    return {nome for nome in NOME_DA_CAMERA.values() if nome in texto}


LISTAGENS = [
    Listagem("/api/cameras", "/api/cameras", lambda j, m: {i["name"] for i in j["items"]}),
    Listagem("/alerts", "/alerts", _nomes_alertas),
    Listagem("/events", "/events?limit=300", lambda j, m: {m.nome_da_camera(i["camera_id"]) for i in j["items"]} - {None}),
    Listagem("/api/incidentes", "/api/incidentes", _nomes_alertas),
    Listagem("/api/permissoes", "/api/permissoes", _nomes_alertas),
    Listagem(
        "/api/integracao/estado", "/api/integracao/estado",
        lambda j, m: {c["nome"] for c in j["planta"]["cameras"]}, presenca=False,
    ),
    Listagem("/api/gemeo", "/api/gemeo", lambda j, m: {c["nome"] for c in j["cameras"]}),
    Listagem("/api/tv", "/api/tv", lambda j, m: {s["setor"] for s in j["setores"]}),
    Listagem(
        "/api/diagnostics/pipeline", "/api/diagnostics/pipeline",
        lambda j, m: {m.nome_da_camera(int(chave)) for chave in j["cameras"]} - {None}, presenca=False,
    ),
    Listagem("/risk-score", "/risk-score", lambda j, m: j["overall"]["alert_count"], modo="contagem"),
    Listagem(
        "/risk-score/trend", "/risk-score/trend?hours=2",
        lambda j, m: sum(b["overall"]["score"] > 0 for b in j["buckets"]) > 0, modo="existe_dado",
    ),
    Listagem("/api/relatorio/turno", "/api/relatorio/turno", lambda j, m: j["alertas"]["total"], modo="contagem"),
    Listagem("/relatorio/turno (HTML)", "/relatorio/turno", _nomes_html, json=False),
]


def _esperado_da_listagem(listagem: Listagem, papel: str, mundo: Mundo):
    todos = set(NOME_DA_CAMERA.values())
    if listagem.modo == "contagem":
        return {OP: ALERTAS_NA_CAMERA["c1"], OP_SEM_SETOR: 0, TEC: sum(ALERTAS_NA_CAMERA.values()),
                SUP: sum(ALERTAS_NA_CAMERA.values())}[papel]
    if listagem.modo == "existe_dado":
        return {OP: True, OP_SEM_SETOR: False, TEC: True, SUP: True}[papel]
    return {OP: {NOME_DA_CAMERA["c1"]}, OP_SEM_SETOR: set(), TEC: todos, SUP: todos}[papel]


# Listagens em que o código diverge do README: (nome, papel) -> motivo.
_BUG_SEM_SETOR = (
    "BUG-SEG: operador SEM setor recebe o dado do parque inteiro ({}). `camera_scope()` devolve None tanto para "
    "técnico/supervisor (vê tudo) quanto para o operador sem `camera_id`, e esta rota só consulta `camera_scope()` "
    "sem a guarda `_operador_sem_setor()` que /alerts, /events e /api/cameras já têm. README: 'operador sem setor "
    "não vê nada'."
)
DIVERGENCIAS_DE_CONTEUDO: dict[tuple[str, str], str] = {
    # D3-D8 (operador sem setor via o parque) corrigidas na MISSÃO 4: decorator `exige_setor`.
}


def _celulas_de_conteudo() -> list:
    pares = []
    for listagem in LISTAGENS:
        for papel in (OP, OP_SEM_SETOR, TEC, SUP):
            marcas = []
            motivo = DIVERGENCIAS_DE_CONTEUDO.get((listagem.nome, papel))
            if motivo:
                marcas.append(pytest.mark.xfail(strict=True, raises=AssertionError, reason=motivo))
            pares.append(pytest.param(listagem, papel, id=f"{listagem.nome} :: {papel}", marks=marcas))
    return pares


@pytest.mark.parametrize(("listagem", "papel"), _celulas_de_conteudo())
def test_o_conteudo_respeita_o_escopo_de_camera(mundo, listagem, papel):
    """README: lista de câmeras, alertas, linha do tempo e score de risco vêm só do setor do operador.

    Operador sem setor 'não vê nada': 403 ou resposta vazia, nunca o parque inteiro.
    """
    resposta = mundo.cliente(papel).get(listagem.caminho)
    esperado = _esperado_da_listagem(listagem, papel, mundo)
    if papel == OP_SEM_SETOR and resposta.status_code == 403:
        _MEDIDOS.append({"conteudo": listagem.nome, "papel": papel, "obtido": "403"})
        return
    assert resposta.status_code == 200, f"{listagem.nome} como {papel}: {resposta.status_code}"
    visto = listagem.extrai(resposta.get_json() if listagem.json else resposta.get_data(as_text=True), mundo)
    _MEDIDOS.append({"conteudo": listagem.nome, "papel": papel, "obtido": repr(visto),
                     "diverge": (listagem.nome, papel) in DIVERGENCIAS_DE_CONTEUDO})
    if isinstance(esperado, set) and not listagem.presenca:
        assert visto <= esperado, f"{listagem.nome} como {papel}: viu {sorted(visto)}, só podia ver {sorted(esperado)}"
        return
    assert visto == esperado, f"{listagem.nome} como {papel}: viu {visto!r}, o README manda ver {esperado!r}"


# ========================================== casos de borda do escopo (REST) ==
def test_operador_nao_amplia_o_escopo_com_camera_id_na_query(mundo):
    """`?camera_id=` do operador não vence o setor dele (alertas, eventos, risco, relatório)."""
    operador = mundo.cliente(OP)
    outra = mundo.ids["c2"]
    itens = operador.get(f"/alerts?camera_id={outra}").get_json()["items"]
    assert {i["camera_id"] for i in itens} == {mundo.ids["c1"]}
    eventos = operador.get(f"/events?camera_id={outra}").get_json()["items"]
    assert {i["camera_id"] for i in eventos} <= {mundo.ids["c1"]}
    assert operador.get(f"/risk-score?camera_id={outra}").get_json()["overall"]["alert_count"] == ALERTAS_NA_CAMERA["c1"]
    relatorio = operador.get(f"/api/relatorio/turno?camera_id={outra}").get_json()
    assert relatorio["alertas"]["total"] == ALERTAS_NA_CAMERA["c1"]


def test_operador_com_todas_1_nao_liga_a_camera_dos_outros(mundo):
    """`POST /start?todas=1` é do técnico: o operador segue no escopo dele."""
    mundo.cliente(OP).post("/start?todas=1")
    c2 = mundo.ids["c2"]
    assert mundo.cliente(TEC).get(f"/api/cameras/{c2}/status").get_json()["running"] is False


def test_tecnico_com_todas_1_liga_o_parque(mundo):
    """Contraprova do teste acima: o escopo do operador não pode ter virado 'ninguém liga todas'."""
    mundo.cliente(TEC).post("/start?todas=1")
    c2 = mundo.ids["c2"]
    assert mundo.cliente(TEC).get(f"/api/cameras/{c2}/status").get_json()["running"] is True


def test_operador_nao_para_a_camera_dos_outros_com_stop_todas(mundo):
    tecnico = mundo.cliente(TEC)
    tecnico.post("/start?todas=1")
    mundo.cliente(OP).post("/stop?todas=1")
    c2 = mundo.ids["c2"]
    assert tecnico.get(f"/api/cameras/{c2}/status").get_json()["running"] is True


def test_acao_em_lote_do_operador_so_alcanca_o_setor_dele(mundo):
    """'Avisei todos' do operador da câmera 1 não marca os alertas da câmera 2."""
    resposta = mundo.cliente(OP).post("/alerts/acknowledge-all")
    assert resposta.status_code == 200
    assert resposta.get_json()["acknowledged"] == ALERTAS_NA_CAMERA["c1"]
    alertas = mundo.cliente(TEC).get(f"/alerts?camera_id={mundo.ids['c2']}").get_json()["items"]
    assert alertas and not any(a["acknowledged"] for a in alertas), "alerta da câmera 2 foi marcado pelo operador da 1"


def test_marcar_falso_positivo_de_outro_setor_nao_altera_o_alerta(mundo):
    resposta = mundo.cliente(OP).post(f"/alerts/{mundo.ids['a2']}/false-positive", json={"reason": "x"})
    assert resposta.status_code == 404
    alerta = mundo.cliente(TEC).get(f"/alerts?camera_id={mundo.ids['c2']}").get_json()["items"][0]
    assert alerta["false_positive"] is False and alerta["status"] == "active"


def test_operador_nao_reconhece_incidente_de_outro_setor(mundo):
    resposta = mundo.cliente(OP).post(f"/api/incidentes/{mundo.ids['i2']}/reconhecer")
    assert resposta.status_code == 404
    incidente = mundo.cliente(TEC).get(f"/api/incidentes/{mundo.ids['i2']}").get_json()["incidente"]
    assert incidente["reconhecido_em"] is None


def test_desativar_o_operador_derruba_o_cookie_na_proxima_chamada(mundo):
    """Sem sessão válida volta 401, não o escopo antigo: a revogação vale na matriz inteira."""
    operador = mundo.cliente(OP)
    assert operador.get("/alerts").status_code == 200
    with mundo.app.app_context():
        usuario = db.session.get(User, mundo.ids[f"u_{OP}"])
        usuario.active = False
        db.session.commit()
    assert operador.get("/alerts").status_code == 401


# ------------------------------------------------- exceções legítimas por token --
def test_reset_da_demo_por_token_do_terminal(mundo, tmp_path):
    anonimo = mundo.cliente(ANON)
    assert anonimo.post("/api/demo/reset").status_code == 403
    assert anonimo.post("/api/demo/reset", headers={"X-Demo-Token": "errado"}).status_code == 403
    assert anonimo.post("/api/demo/reset", headers={"X-Demo-Token": "token-da-demo-de-teste"}).status_code == 200


def test_reset_da_demo_nao_aceita_token_vazio(mundo):
    assert mundo.cliente(ANON).post("/api/demo/reset", headers={"X-Demo-Token": ""}).status_code == 403


def test_celular_so_quadro_com_token_conhecido(mundo):
    anonimo = mundo.cliente(ANON)
    assert anonimo.post("/api/celular/qualquer/quadro", data=JPEG_MINIMO).status_code == 404
    assert anonimo.post("/api/celular/../cameras/quadro", data=JPEG_MINIMO).status_code == 404


def test_token_do_palco_nao_abre_outras_rotas(mundo):
    """O token do QR só muda a cena: não dá acesso a vídeo, alerta, nem ao próprio QR."""
    token = mundo.ids["token_palco"]
    anonimo = mundo.cliente(ANON)
    assert anonimo.get(f"/api/palco/controle?t={token}").status_code == 401
    assert anonimo.get(f"/alerts?t={token}").status_code == 401
    assert anonimo.get(f"/api/evacuacao?t={token}").status_code == 401
    assert anonimo.get(f"/api/evacuacao/relatorios?t={token}").status_code == 401
    assert anonimo.get(f"/api/cameras/{mundo.ids['c1']}/video_feed?t={token}").status_code == 401


# ================================================================== socket ==
def _conectar(mundo, papel):
    return socketio.test_client(mundo.app, flask_test_client=mundo.cliente(papel))


def _recebidos(cliente_ws, nome: str) -> list[dict]:
    return [evento["args"][0] for evento in cliente_ws.get_received() if evento["name"] == nome]


def _sondar_cameras(mundo) -> None:
    with mundo.app.app_context():
        for chave in ("c1", "c2"):
            emitir_para_camera(socketio, "sonda", {"camera_id": mundo.ids[chave]}, mundo.ids[chave])


# (conecta?, recebe câmera 1?, recebe câmera 2?) por papel — README: socket exige
# sessão; o escopo vale também no socket; técnico/supervisor entram na sala do parque;
# operador só na do setor; operador sem setor em sala nenhuma.
ESPERADO_CONNECT = {
    ANON: (False, False, False),
    OP: (True, True, False),
    OP_SEM_SETOR: (True, False, False),
    TEC: (True, True, True),
    SUP: (True, True, True),
}

SOCKET_PAPEIS = (ANON, OP, OP_SEM_SETOR, TEC, SUP)


@pytest.mark.parametrize("papel", SOCKET_PAPEIS)
def test_socket_connect(mundo, papel):
    conecta, ve_c1, ve_c2 = ESPERADO_CONNECT[papel]
    cliente_ws = _conectar(mundo, papel)
    assert cliente_ws.is_connected() is conecta, f"connect como {papel}: esperado conectado={conecta}"
    if not conecta:
        return
    cliente_ws.get_received()
    _sondar_cameras(mundo)
    camera_ids = {e["camera_id"] for e in _recebidos(cliente_ws, "sonda")}
    assert (mundo.ids["c1"] in camera_ids) is ve_c1, f"{papel} e a câmera 1 (a dele): esperado receber={ve_c1}"
    assert (mundo.ids["c2"] in camera_ids) is ve_c2, f"{papel} e a câmera 2: esperado receber={ve_c2}"


def test_socket_connect_com_cookie_invalido_e_recusado(mundo):
    cliente = mundo.app.test_client()
    cliente.set_cookie("session", "cookie-forjado.sem-assinatura.valida")
    assert socketio.test_client(mundo.app, flask_test_client=cliente).is_connected() is False


def test_socket_connect_de_usuario_desativado_e_recusado(mundo):
    with mundo.app.app_context():
        db.session.get(User, mundo.ids[f"u_{TEC}"]).active = False
        db.session.commit()
    assert _conectar(mundo, TEC).is_connected() is False


# `focar` — o cliente diz qual câmera está aberta; a sala de foco recebe telemetria.
# (papel, câmera pedida) -> resposta. Operador só foca a do setor; sem setor, nenhuma.
ESPERADO_FOCAR = {
    (OP, "c1"): True, (OP, "c2"): False,
    (OP_SEM_SETOR, "c1"): False, (OP_SEM_SETOR, "c2"): False,
    (TEC, "c1"): True, (TEC, "c2"): True,
    (SUP, "c1"): True, (SUP, "c2"): True,
}


@pytest.mark.parametrize(("papel", "camera"), list(ESPERADO_FOCAR), ids=lambda v: str(v))
def test_socket_focar(mundo, papel, camera):
    esperado = ESPERADO_FOCAR[(papel, camera)]
    cliente_ws = _conectar(mundo, papel)
    assert cliente_ws.is_connected()
    camera_id = mundo.ids[camera]
    assert cliente_ws.emit("focar", {"camera_id": camera_id}, callback=True) == {"ok": esperado}
    cliente_ws.get_received()
    with mundo.app.app_context():
        emitir_para_foco(socketio, "telemetria_sonda", {"camera_id": camera_id}, camera_id)
    recebeu = bool(_recebidos(cliente_ws, "telemetria_sonda"))
    assert recebeu is esperado, f"{papel} focou a câmera {camera}: telemetria recebida={recebeu}, esperado={esperado}"


@pytest.mark.parametrize("papel", [OP, OP_SEM_SETOR, TEC, SUP])
@pytest.mark.parametrize(
    "carga",
    [
        None, {}, {"camera_id": None}, {"camera_id": "abc"}, {"camera_id": [1]},
        # Payload que não é objeto estourava AttributeError em `_focar` (corrigido na MISSÃO 4).
        "texto",
    ],
    ids=["none", "vazio", "camera_nula", "camera_texto", "camera_lista", "payload_texto"],
)
def test_socket_focar_com_carga_invalida_recusa(mundo, papel, carga):
    cliente_ws = _conectar(mundo, papel)
    assert cliente_ws.emit("focar", carga, callback=True) == {"ok": False}


def test_socket_focar_depois_de_desativado_recusa(mundo):
    """`focar` revalida a pessoa: sessão revogada não escolhe câmera."""
    cliente_ws = _conectar(mundo, TEC)
    assert cliente_ws.emit("focar", {"camera_id": mundo.ids["c1"]}, callback=True) == {"ok": True}
    with mundo.app.app_context():
        db.session.get(User, mundo.ids[f"u_{TEC}"]).active = False
        db.session.commit()
    assert cliente_ws.emit("focar", {"camera_id": mundo.ids["c2"]}, callback=True) == {"ok": False}


@pytest.mark.parametrize("papel", [OP, OP_SEM_SETOR, TEC, SUP])
def test_socket_revalidate_mantem_sessao_valida(mundo, papel):
    cliente_ws = _conectar(mundo, papel)
    cliente_ws.emit("revalidate")
    assert cliente_ws.is_connected(), f"revalidate derrubou {papel} com sessão válida"


@pytest.mark.parametrize("papel", [OP, OP_SEM_SETOR, TEC, SUP])
@pytest.mark.parametrize("revogacao", ["desativada", "senha_trocada"])
def test_socket_revalidate_derruba_sessao_revogada(mundo, papel, revogacao):
    """README: 'o socket revalida a sessão a cada 30 s' — acesso revogado não segue recebendo feed."""
    cliente_ws = _conectar(mundo, papel)
    assert cliente_ws.is_connected()
    with mundo.app.app_context():
        usuario = db.session.get(User, mundo.ids[f"u_{papel}"])
        if revogacao == "desativada":
            usuario.active = False
        else:
            usuario.session_epoch += 1
        db.session.commit()
    cliente_ws.emit("revalidate")
    assert not cliente_ws.is_connected(), f"{papel} com sessão {revogacao} seguiu conectado após revalidate"


# ---------------------------------------------- varredura dos eventos de socket --
EVENTOS_DE_SOCKET_NA_MATRIZ = {"connect", "focar", "revalidate"}


def test_todo_evento_de_socket_esta_classificado(mundo):
    """Handler novo de socket sem expectativa FALHA aqui.

    Duas fontes, porque cada uma tem um ponto cego: o registro do servidor
    Socket.IO (só vê handlers de módulos já importados) e o texto de `app/`
    (só vê quem escreveu `socketio.on("...")` literal).
    """
    registrados = {nome for nome in socketio.server.handlers.get("/", {})} - {"disconnect"}
    no_codigo: set[str] = set()
    for arquivo in (RAIZ_DO_PROJETO / "app").rglob("*.py"):
        no_codigo |= set(re.findall(r"\.on\(\s*[\"'](\w+)[\"']", arquivo.read_text(encoding="utf-8")))
    desconhecidos = (registrados | no_codigo) - EVENTOS_DE_SOCKET_NA_MATRIZ - {"disconnect"}
    assert not desconhecidos, (
        "eventos de socket sem expectativa na matriz (acrescente testes por papel): " + ", ".join(sorted(desconhecidos))
    )
    assert EVENTOS_DE_SOCKET_NA_MATRIZ <= registrados | no_codigo, "a matriz cobre um evento que não existe mais"
