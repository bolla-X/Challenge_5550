"""Modo Apresentação (X6): roteiro único, cena sincronizada e controle por token."""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest
from app import create_app
from app.config import AuthTestConfig
from app.extensions import db
from app.services.auth_service import AuthService
from app.services.palco import ROTEIRO, Palco

SENHA = "senha-forte-de-teste"

ORDEM_DAS_CENAS = [
    "abertura", "portal", "enganar", "raiox", "tape_camera", "gemeo", "queda", "evacuacao", "incidente", "custodia",
    "simulador", "regra", "permissao", "fabrica", "primeiro_acesso", "liga", "retrospectiva", "encerramento",
]
CENAS_NOVAS = ("tape_camera", "fabrica", "evacuacao", "regra", "permissao", "primeiro_acesso")


def _cena(chave):
    return next(c for c in ROTEIRO if c["chave"] == chave)


def _indice(chave):
    return next(i for i, c in enumerate(ROTEIRO) if c["chave"] == chave)


def test_navegacao_nos_limites_do_roteiro():
    p = Palco()
    assert p.publico()["cena"] == 0
    assert p.ir(acao="anterior").cena == 0
    for _ in range(len(ROTEIRO) + 3):
        p.ir(acao="proxima")
    assert p.estado.cena == len(ROTEIRO) - 1
    assert p.publico()["proxima"] is None
    assert p.ir(acao="ir", indice=2).cena == 2
    with pytest.raises(ValueError):
        p.ir(acao="pular")


def test_roteiro_tem_as_cenas_da_missao():
    chaves = [c["chave"] for c in ROTEIRO]
    for chave in ("portal", "enganar", "raiox", "gemeo", "queda", "incidente", "custodia", "simulador", "liga", "retrospectiva"):
        assert chave in chaves
    assert all(c["legenda"] and len(c["legenda"]) <= 110 for c in ROTEIRO)


def test_ordem_das_cenas_encaixa_as_novas_na_narrativa():
    chaves = [c["chave"] for c in ROTEIRO]
    assert chaves == ORDEM_DAS_CENAS
    assert len(set(chaves)) == len(chaves)
    # Depois das cenas de EPI (portal, enganar, raiox) e antes do fechamento (retrospectiva, obrigado).
    primeira_nova = min(chaves.index(c) for c in CENAS_NOVAS)
    ultima_nova = max(chaves.index(c) for c in CENAS_NOVAS)
    assert primeira_nova > chaves.index("raiox") and ultima_nova < chaves.index("retrospectiva")


def test_regra_de_exemplo_e_valida_no_editor_e_nao_promete_numero():
    from app.services.regras_editor import validar

    cena = _cena("regra")
    regra = validar({"id": "exemplo", **cena["regra"]})
    assert regra.nome == "Sem capacete por 5 s na zona de risco"
    assert {i.tipo for i in regra.condicao.itens} == {"zona", "epi", "duracao"}
    assert "disparos" not in str(cena)  # o resultado vem de /api/regras/testar, nunca do roteiro


@pytest.fixture()
def app_auth(tmp_path):
    class Cfg(AuthTestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'palco.db'}"
        EVACUACAO_DIR = str(tmp_path / "relatorios")

    app = create_app(Cfg)
    with app.app_context():
        db.create_all()
        AuthService().create_user(email="tec@x.local", name="Tec", password=SENHA, role="technical")
        AuthService().create_user(email="sup@x.local", name="Sup", password=SENHA, role="supervisor")
        AuthService().create_user(email="op@x.local", name="Op", password=SENHA, role="operator", camera_id=1)
    return app


def test_celular_muda_a_cena_so_com_o_token(app_auth):
    celular = app_auth.test_client()
    assert celular.get("/api/palco/estado").status_code == 401
    assert celular.post("/api/palco/ir", json={"acao": "proxima", "t": "errado"}).status_code == 403
    tecnico = app_auth.test_client()
    tecnico.post("/api/auth/login", json={"email": "tec@x.local", "password": SENHA})
    url = tecnico.get("/api/palco/controle").get_json()
    token = url["caminho"].split("t=", 1)[1]
    r = celular.post("/api/palco/ir", json={"acao": "proxima", "t": token}).get_json()
    assert r["cena"] == 1
    # A tela do palco (técnico logado) vê a mesma cena.
    assert tecnico.get("/api/palco/estado").get_json()["cena"] == 1
    assert url["aviso"]  # teste em HTTP: avisa que o celular precisa de --https


def test_operador_nao_comanda_o_palco(app_auth):
    op = app_auth.test_client()
    op.post("/api/auth/login", json={"email": "op@x.local", "password": SENHA})
    assert op.post("/api/palco/ir", json={"acao": "proxima"}).status_code == 403
    assert op.get("/api/palco/controle").status_code == 403


def test_camera_lenta_so_dura_a_cena_da_queda(app_auth, tmp_path, monkeypatch):
    """Entrar na cena "Queda" põe a gravação dela a 0,25× ANTES de responder; sair volta a 1×."""
    import cv2
    import numpy as np
    from app.api import palco as api_palco
    from app.models import Camera

    gravacao = tmp_path / "queda.avi"
    escritor = cv2.VideoWriter(str(gravacao), cv2.VideoWriter_fourcc(*"MJPG"), 10, (64, 48))
    for _ in range(10):
        escritor.write(np.zeros((48, 64, 3), dtype=np.uint8))
    escritor.release()
    with app_auth.app_context():
        db.session.add(Camera(name="Queda", source_type="Arquivo", source=str(gravacao), fps=12, width=64, height=48))
        db.session.commit()
        monitor = app_auth.extensions["monitor_service"]
        monitor.load_cameras_from_db()
        worker = monitor.worker_da_camera(Camera.query.filter_by(name="Queda").one().id)
    preparadas = []
    monkeypatch.setattr(api_palco, "_preparar", lambda app, cena: preparadas.append(cena["chave"]))  # sem ligar câmera
    tecnico = app_auth.test_client()
    tecnico.post("/api/auth/login", json={"email": "tec@x.local", "password": SENHA})
    queda = next(i for i, c in enumerate(ROTEIRO) if c["chave"] == "queda")

    assert tecnico.post("/api/palco/ir", json={"acao": "ir", "indice": queda}).status_code == 200
    assert worker.velocidade_gravacao == 0.25
    assert worker.video_state()["velocidade"] == 0.25
    tecnico.post("/api/palco/ir", json={"acao": "proxima"})
    assert worker.velocidade_gravacao == 1.0


def test_toda_cena_declara_as_cameras_ativas():
    assert all(c.get("ativas") in ("todas", "cena") for c in ROTEIRO)
    assert {c["chave"] for c in ROTEIRO if c["ativas"] == "cena"} == {"portal", "enganar", "queda", "tape_camera", "permissao"}
    assert all(c["titulo"] and c["legenda"] for c in ROTEIRO)


def test_cameras_pausadas_so_com_a_camera_da_cena_presente():
    from app.services.palco import cameras_pausadas

    portal = next(c for c in ROTEIRO if c["chave"] == "portal")
    gemeo = next(c for c in ROTEIRO if c["chave"] == "gemeo")
    por_nome = {"Portal": 4, "Canteiro": 1, "Pátio": 2, "Escada": 3}
    assert cameras_pausadas(portal, por_nome) == {1, 2, 3}
    assert cameras_pausadas(gemeo, por_nome) == set()
    # Sem a câmera da cena, pausar as outras só apagaria a planta.
    assert cameras_pausadas(portal, {"Pátio": 2}) == set()


def _video(tmp_path, nome):
    import cv2
    import numpy as np

    caminho = tmp_path / f"{nome}.avi"
    escritor = cv2.VideoWriter(str(caminho), cv2.VideoWriter_fourcc(*"MJPG"), 10, (64, 48))
    for _ in range(10):
        escritor.write(np.zeros((48, 64, 3), dtype=np.uint8))
    escritor.release()
    return caminho


def test_cena_do_portal_pausa_as_outras_e_sair_devolve(app_auth, tmp_path, monkeypatch):
    """ADENDO 3: só a câmera do Portal analisa na cena; as outras dizem "apresentacao"; o lease devolve."""
    from app.api import palco as api_palco
    from app.models import Camera

    with app_auth.app_context():
        for nome in ("Portal", "Pátio", "Escada"):
            db.session.add(Camera(name=nome, source_type="Arquivo", source=str(_video(tmp_path, nome)), fps=12, width=64,
                                  height=48))
        db.session.commit()
        monitor = app_auth.extensions["monitor_service"]
        monitor.load_cameras_from_db()
        ids = {c.name: c.id for c in Camera.query.all()}
    monkeypatch.setattr(api_palco, "_preparar", lambda app, cena: None)
    tecnico = app_auth.test_client()
    tecnico.post("/api/auth/login", json={"email": "tec@x.local", "password": SENHA})
    portal = next(i for i, c in enumerate(ROTEIRO) if c["chave"] == "portal")
    enganar = next(i for i, c in enumerate(ROTEIRO) if c["chave"] == "enganar")

    tecnico.post("/api/palco/ir", json={"acao": "ir", "indice": portal})
    assert not monitor.worker_da_camera(ids["Portal"]).pausada_pelo_palco
    assert monitor.status(ids["Pátio"])["pausa"] == "apresentacao"
    assert monitor.status(ids["Portal"])["pausa"] is None
    assert tecnico.get("/api/palco/estado").get_json()["pausadas"] == ["Escada", "Pátio"]

    tecnico.post("/api/palco/ir", json={"acao": "ir", "indice": enganar})  # a cena seguinte também é do portal
    assert monitor.worker_da_camera(ids["Escada"]).pausada_pelo_palco
    tecnico.post("/api/palco/ir", json={"acao": "proxima"})  # saiu: todas voltam
    assert not any(monitor.worker_da_camera(cid).pausada_pelo_palco for cid in ids.values())
    assert tecnico.get("/api/palco/estado").get_json()["pausadas"] == []

    # Palco fechado no meio da cena: o lease vence e as câmeras voltam sozinhas.
    tecnico.post("/api/palco/ir", json={"acao": "ir", "indice": portal})
    assert monitor.worker_da_camera(ids["Pátio"]).pausada_pelo_palco
    monitor._pausa_palco_ate = 0.0
    assert monitor.expirar_pausa_do_palco() is True
    assert not monitor.worker_da_camera(ids["Pátio"]).pausada_pelo_palco
    # O celular (token) não sustenta a pausa: só a tela do palco.
    token = tecnico.get("/api/palco/controle").get_json()["caminho"].split("t=", 1)[1]
    assert app_auth.test_client().get(f"/api/palco/estado?t={token}").get_json()["pausadas"] == []
    assert not monitor.worker_da_camera(ids["Pátio"]).pausada_pelo_palco
    # A tela volta a consultar: a cena reaplica a pausa.
    tecnico.get("/api/palco/estado")
    assert monitor.worker_da_camera(ids["Pátio"]).pausada_pelo_palco


def test_worker_pausado_captura_devagar_e_nao_pede_inferencia(app_auth, tmp_path):
    from app.models import Camera

    with app_auth.app_context():
        db.session.add(Camera(name="Pátio", source_type="Arquivo", source=str(_video(tmp_path, "p")), fps=12, width=64,
                              height=48))
        db.session.commit()
        monitor = app_auth.extensions["monitor_service"]
        monitor.load_cameras_from_db()
        worker = monitor.worker_da_camera(Camera.query.filter_by(name="Pátio").one().id)
    antes = worker._taxa_util_de_captura()
    monitor.pausar_pelo_palco({worker.camera_id})
    assert worker._taxa_util_de_captura() == 1.0 < antes
    monitor.pausar_pelo_palco(set())
    assert worker._taxa_util_de_captura() == antes


# ------------------------------------------------ cenas novas (MISSÃO 4, Fase 6)
def _camera(app, nome, tipo="Arquivo", fonte="x"):
    from app.models import Camera

    with app.app_context():
        camera = Camera(name=nome, source_type=tipo, source=fonte, fps=12, width=64, height=48)
        db.session.add(camera)
        db.session.commit()
        return camera.id


def _login(app, email):
    cliente = app.test_client()
    assert cliente.post("/api/auth/login", json={"email": email, "password": SENHA}).status_code == 200
    return cliente


def _entrar(app, chave):
    palco = app.extensions.setdefault("palco", Palco())
    palco.ir(acao="ir", indice=_indice(chave))
    return palco


def test_camera_de_cada_cena_nova_e_o_que_ela_pausa():
    from app.services.palco import camera_da_cena, cameras_pausadas

    demo = {"Portal": 4, "Canteiro": 1, "Pátio": 2, "Escada": 3}
    tape = _cena("tape_camera")
    assert camera_da_cena(tape, demo, {4}) == 4  # a webcam da demo
    assert camera_da_cena(tape, demo, frozenset()) == 4  # sem webcam o Portal toca a gravação (a tela avisa)
    # Fora da demo: a primeira câmera ao vivo (menor id), mesmo que o nome não seja "Portal".
    assert camera_da_cena(tape, {"Doca": 7, "Galpão": 5, "Pátio": 2}, {7, 5}) == 5
    # Há Portal gravado e uma câmera ao vivo de outro nome: vale a ao vivo.
    assert camera_da_cena(tape, {"Portal": 4, "RTSP": 7}, {7}) == 7
    assert camera_da_cena(tape, {"Pátio": 2}, frozenset()) is None
    assert cameras_pausadas(tape, demo, {4}) == {1, 2, 3}
    assert cameras_pausadas(tape, {"Pátio": 2}, frozenset()) == set()  # sem câmera da cena, ninguém pausa

    for chave in ("regra", "permissao"):
        assert camera_da_cena(_cena(chave), demo) == 2
    assert cameras_pausadas(_cena("permissao"), demo) == {1, 3, 4}
    for chave in ("fabrica", "evacuacao", "primeiro_acesso", "regra"):
        assert cameras_pausadas(_cena(chave), demo) == set()
    for chave in ("fabrica", "evacuacao", "primeiro_acesso"):
        assert camera_da_cena(_cena(chave), demo) is None


def test_roteiro_diz_se_a_camera_do_tape_e_ao_vivo(app_auth):
    from app.models import Camera

    portal = _camera(app_auth, "Portal", "Arquivo", "portal.mp4")
    tecnico = _login(app_auth, "tec@x.local")

    def cena_tape():
        cenas = tecnico.get("/api/palco/roteiro").get_json()["cenas"]
        assert "camera_ao_vivo" not in next(c for c in cenas if c["chave"] == "portal")
        return next(c for c in cenas if c["chave"] == "tape_camera")

    assert (cena_tape()["camera_id"], cena_tape()["camera_ao_vivo"]) == (portal, False)
    with app_auth.app_context():
        db.session.get(Camera, portal).source_type = "USB"
        db.session.commit()
    assert (cena_tape()["camera_id"], cena_tape()["camera_ao_vivo"]) == (portal, True)
    with app_auth.app_context():
        db.session.get(Camera, portal).source_type = "Arquivo"
        db.session.commit()
    doca = _camera(app_auth, "Doca", "RTSP", "rtsp://x")
    assert (cena_tape()["camera_id"], cena_tape()["camera_ao_vivo"]) == (doca, True)


def test_fallback_so_vale_na_cena_que_o_registrou():
    palco = Palco()
    palco.ir(acao="ir", indice=_indice("tape_camera"))
    assert palco.publico()["fallback"] is None
    palco.registrar_fallback("tape_camera", "sem imagem")
    assert palco.publico()["fallback"] == "sem imagem"
    palco.ir(acao="proxima")
    assert palco.publico()["fallback"] is None
    palco.registrar_fallback("tape_camera", "preparo atrasado da cena anterior")  # chegou depois de sair
    assert palco.publico()["fallback"] is None
    palco.ir(acao="anterior")  # voltar a uma cena começa sem contingência velha
    assert palco.publico()["fallback"] is None


class _WorkerDaSaude:
    """Dublê do worker: responde em sequência (a última resposta se repete) e conta as chamadas."""

    velocidade_gravacao = 1.0  # o palco confere a velocidade de cada worker ao trocar de cena

    def __init__(self, *respostas):
        self.respostas = list(respostas)
        self.chamadas = 0

    def redefinir_referencia_visual(self):
        self.chamadas += 1
        resposta = self.respostas.pop(0) if len(self.respostas) > 1 else self.respostas[0]
        if isinstance(resposta, Exception):
            raise resposta
        return resposta


@pytest.fixture()
def tape(app_auth, monkeypatch):
    """Câmera "Portal" ao vivo, o palco na cena "Tape a câmera" e o worker trocado por um dublê."""
    from app.api import palco as api_palco

    portal = _camera(app_auth, "Portal", "USB", "0")
    monkeypatch.setattr(api_palco, "_dormir", lambda s: None)

    def com_worker(worker):
        pedidas = []
        monkeypatch.setattr(app_auth.extensions["monitor_service"], "worker_da_camera",
                            lambda camera_id=None: pedidas.append(camera_id) or worker)
        return pedidas

    return SimpleNamespace(app=app_auth, portal=portal, palco=_entrar(app_auth, "tape_camera"), com_worker=com_worker,
                           preparar=lambda: api_palco._preparar(app_auth, _cena("tape_camera")))


def test_tape_a_camera_refaz_a_referencia_da_camera_ao_entrar(tape, monkeypatch):
    from app.api import palco as api_palco

    esperas = []
    monkeypatch.setattr(api_palco, "_dormir", esperas.append)
    worker = _WorkerDaSaude(ValueError("A câmera ainda não entregou imagem"), {"estado": "ok", "rotulo": "OK"})
    pedidas = tape.com_worker(worker)
    tape.preparar()
    assert pedidas == [tape.portal] and worker.chamadas == 2  # esperou a primeira imagem e refez
    assert esperas == [1.0]
    assert tape.palco.publico()["fallback"] is None


@pytest.mark.parametrize(
    ("resposta", "chamadas", "trecho"),
    [
        (ValueError("sem imagem"), 6, "ainda não entregou imagem"),  # insiste por ~6 s; só repete se não há imagem
        ({"ativa": False}, 1, "saúde visual está desligada"),
    ],
)
def test_tape_a_camera_sem_o_que_precisa_mostra_legenda_de_contingencia(tape, resposta, chamadas, trecho):
    worker = _WorkerDaSaude(resposta)
    tape.com_worker(worker)
    tape.preparar()
    assert trecho in tape.palco.publico()["fallback"]
    assert worker.chamadas == chamadas


def test_tape_a_camera_com_a_camera_desligada_mostra_legenda_de_contingencia(tape, monkeypatch):
    def sem_worker(camera_id=None):
        raise LookupError("câmera sem worker ativo")

    monkeypatch.setattr(tape.app.extensions["monitor_service"], "worker_da_camera", sem_worker)
    tape.preparar()
    assert "não está ligada" in tape.palco.publico()["fallback"]


def test_preparo_que_estoura_vira_log_e_contingencia_sem_derrubar_o_palco(tape, caplog):
    from app.services.palco_preparos import FALHA_DE_PREPARO

    tape.com_worker(_WorkerDaSaude(RuntimeError("câmera em pane")))
    with caplog.at_level("ERROR"):
        tape.preparar()  # não levanta
    assert "palco_preparo_falhou" in caplog.text
    assert tape.palco.publico()["fallback"] == FALHA_DE_PREPARO
    tecnico = _login(tape.app, "tec@x.local")
    assert tecnico.get("/api/palco/estado").get_json()["fallback"] == FALHA_DE_PREPARO  # a tela e o celular veem
    assert tecnico.post("/api/palco/ir", json={"acao": "proxima"}).get_json()["fallback"] is None  # sair limpa


def _permissoes(app):
    from app.models import PermissaoDeTrabalho

    with app.app_context():
        return [
            {"status": p.status, "tipo": p.tipo, "camera_id": p.camera_id, "responsavel": p.responsavel, "por": p.criada_por,
             "exige_vigia": p.exige_vigia, "area": p.area_vigia, "janela": p.fim - p.inicio, "encerrada_por": p.encerrada_por}
            for p in PermissaoDeTrabalho.query.order_by(PermissaoDeTrabalho.id).all()
        ]


def test_permissao_de_demonstracao_nasce_ao_entrar_e_encerra_ao_sair(app_auth):
    from app.api import palco as api_palco
    from app.models import EventLog

    patio = _camera(app_auth, "Pátio")
    _entrar(app_auth, "permissao")
    cena = _cena("permissao")
    api_palco._preparar(app_auth, cena)
    api_palco._preparar(app_auth, cena)  # entrar de novo na cena reaproveita a vigente
    (pt,) = _permissoes(app_auth)
    assert (pt["status"], pt["tipo"], pt["camera_id"]) == ("ativa", "espaco_confinado", patio)
    assert pt["responsavel"] == "Equipe de demonstração" and pt["por"] == "palco (apresentação)"
    assert pt["exige_vigia"] and len(pt["area"]) == 4 and pt["janela"] == timedelta(hours=1)
    assert all(x < 0.3 for x, _y in pt["area"])  # o vigia fica num canto; a zona de risco da demo é a metade direita

    api_palco._ao_sair(app_auth, cena)
    (pt,) = _permissoes(app_auth)
    assert (pt["status"], pt["encerrada_por"]) == ("encerrada", "palco (apresentação)")
    with app_auth.app_context():
        tipos = [e.event_type for e in EventLog.query.order_by(EventLog.id)]
    assert tipos == ["permissao_emitida", "permissao_encerrada"]


def test_permissao_de_demonstracao_nao_toca_na_de_ninguem_e_limpa_a_vencida(app_auth):
    from app.api import palco as api_palco
    from app.models import utc_now
    from app.services import palco_preparos, permissoes

    patio = _camera(app_auth, "Pátio")
    _entrar(app_auth, "permissao")
    with app_auth.app_context():
        agora = utc_now()
        # Uma PT com o mesmo texto da demo, mas emitida por um técnico: não é do palco.
        permissoes.emitir_permissao(palco_preparos.dados_da_permissao_de_demonstracao(patio, agora), criada_por="tec@x.local")
        # Uma do palco que ficou ativa e venceu (saída que falhou numa apresentação anterior).
        antes = agora - timedelta(hours=3)
        permissoes.emitir_permissao(palco_preparos.dados_da_permissao_de_demonstracao(patio, antes),
                                    criada_por=palco_preparos.POR_PALCO, agora=antes)
    api_palco._preparar(app_auth, _cena("permissao"))
    status = [(p["por"], p["status"]) for p in _permissoes(app_auth)]
    assert status == [("tec@x.local", "ativa"), ("palco (apresentação)", "encerrada"), ("palco (apresentação)", "ativa")]
    api_palco._ao_sair(app_auth, _cena("permissao"))
    assert [(p["por"], p["status"]) for p in _permissoes(app_auth)] == [
        ("tec@x.local", "ativa"), ("palco (apresentação)", "encerrada"), ("palco (apresentação)", "encerrada")]


def test_permissao_de_demonstracao_sem_a_camera_da_cena_vira_contingencia(app_auth):
    from app.api import palco as api_palco

    palco = _entrar(app_auth, "permissao")
    api_palco._preparar(app_auth, _cena("permissao"))  # não há "Pátio" cadastrado
    assert "não está cadastrada" in palco.publico()["fallback"]
    assert _permissoes(app_auth) == []


def test_corpo_da_permissao_de_demonstracao_passa_na_validacao_do_servico_sem_avisos():
    from app.models import utc_now
    from app.services import palco_preparos, permissoes

    agora = utc_now()
    campos, avisos = permissoes.validar_dados(palco_preparos.dados_da_permissao_de_demonstracao(3, agora), agora)
    assert avisos == []  # 1 h cabe na jornada; vigia e área informados
    assert campos["exige_vigia"] and campos["epis_exigidos"] == []


class _Socket:
    def emit(self, *args, **kwargs):
        return None


@pytest.fixture()
def evacuacao_falsa(app_auth, monkeypatch):
    """Uma câmera com 3 pessoas no lugar dos workers, e a thread de troca de cena rodando na hora."""
    from app.api import evacuacao as api_evacuacao
    from app.api import palco as api_palco

    app_auth.config["DEMO_MODE"] = True  # o token do palco só aciona evacuação na demo
    app_auth.extensions["monitor_service"].socketio = _Socket()
    cameras = [{"id": 1, "nome": "Portaria", "pessoas": 3, "zonas": {}, "pes_na_planta": [], "ts_ultima_analise": None,
                "online": True}]
    monkeypatch.setattr(api_evacuacao, "coletar_cameras_info", lambda _monitor: cameras)

    class ThreadNaHora:  # o teste confere o efeito da troca de cena sem esperar uma thread
        def __init__(self, target, args=(), daemon=None):
            self._alvo, self._args = target, args

        def start(self):
            self._alvo(*self._args)

    monkeypatch.setattr(api_palco, "threading", SimpleNamespace(Thread=ThreadNaHora))
    return app_auth


def _token(cliente):
    return cliente.get("/api/palco/controle").get_json()["caminho"].split("t=", 1)[1]


def test_token_do_palco_aciona_a_evacuacao_e_sair_da_cena_encerra_e_registra(evacuacao_falsa):
    from app.models import ElodeCustodia, EventLog
    from app.services.evacuacao import ler_relatorio, pasta_dos_relatorios

    app = evacuacao_falsa
    tecnico, celular = _login(app, "tec@x.local"), app.test_client()
    token = _token(tecnico)
    assert tecnico.post("/api/palco/ir", json={"acao": "ir", "indice": _indice("evacuacao")}).status_code == 200

    # O palco aciona com o token do QR (sem sessão); o token não lê nada nem abre porta para quem erra a chave.
    assert celular.post("/api/evacuacao/iniciar", json={"t": "errado"}).status_code == 403
    assert not getattr(app.extensions.get("evacuacao"), "ativa", False)
    inicio = celular.post("/api/evacuacao/iniciar", json={"t": token})
    assert inicio.status_code == 200 and inicio.get_json()["total"] == 3
    assert celular.get(f"/api/evacuacao?t={token}").status_code == 401
    assert app.extensions["evacuacao"].ativa

    # A legenda da cena promete isto: ao sair, encerra e grava o relatório na custódia.
    assert tecnico.post("/api/palco/ir", json={"acao": "proxima"}).status_code == 200
    assert not app.extensions["evacuacao"].ativa
    relatorio = ler_relatorio(pasta_dos_relatorios(app), 1)
    assert (relatorio["iniciada_por"], relatorio["encerrada_por"]) == ("palco (token)", "palco (saída da cena)")
    with app.app_context():
        assert ElodeCustodia.query.filter_by(tipo="evacuacao").one().ref == "evacuacao_1.json"
        tipos = [e.event_type for e in EventLog.query.order_by(EventLog.id)]
    assert tipos == ["evacuacao_iniciada", "evacuacao_encerrada"]
    assert celular.post("/api/evacuacao/encerrar", json={"t": token}).get_json()["code"] == "evacuacao_inativa"  # nada ficou aberto


def test_encerrar_pelo_botao_da_cena_e_depois_sair_nao_duplica_o_relatorio(evacuacao_falsa):
    from app.services.evacuacao import listar_relatorios, pasta_dos_relatorios

    app = evacuacao_falsa
    tecnico, celular = _login(app, "tec@x.local"), app.test_client()
    token = _token(tecnico)
    tecnico.post("/api/palco/ir", json={"acao": "ir", "indice": _indice("evacuacao")})
    celular.post("/api/evacuacao/iniciar", json={"t": token})
    fim = celular.post("/api/evacuacao/encerrar", json={"t": token})
    assert fim.status_code == 200 and fim.get_json()["custodia_registrada"] is True
    tecnico.post("/api/palco/ir", json={"acao": "proxima"})
    assert len(listar_relatorios(pasta_dos_relatorios(app))) == 1


def test_sair_da_cena_nao_encerra_evacuacao_acionada_por_outro_caminho(evacuacao_falsa):
    app = evacuacao_falsa
    tecnico, supervisor = _login(app, "tec@x.local"), _login(app, "sup@x.local")
    tecnico.post("/api/palco/ir", json={"acao": "ir", "indice": _indice("evacuacao")})
    assert supervisor.post("/api/evacuacao/iniciar").status_code == 200  # pela tela /evacuacao, não pelo palco
    tecnico.post("/api/palco/ir", json={"acao": "proxima"})
    assert app.extensions["evacuacao"].ativa  # navegar na apresentação nunca fecha uma ocorrência real
    assert supervisor.post("/api/evacuacao/encerrar").status_code == 200


def test_transicao_nao_prepara_a_cena_que_o_apresentador_ja_deixou(app_auth, monkeypatch):
    from app.api import palco as api_palco

    preparadas, saidas = [], []
    monkeypatch.setattr(api_palco, "_preparar", lambda app, cena: preparadas.append(cena["chave"]))
    monkeypatch.setattr(api_palco, "_ao_sair", lambda app, cena: saidas.append(cena["chave"]))
    palco = _entrar(app_auth, "gemeo")
    api_palco._transicao(app_auth, _cena("tape_camera"), _cena("permissao"))  # o palco já está em outra cena
    assert (saidas, preparadas) == (["tape_camera"], [])
    palco.ir(acao="ir", indice=_indice("permissao"))
    api_palco._transicao(app_auth, _cena("gemeo"), _cena("permissao"))
    assert (saidas, preparadas) == (["tape_camera", "gemeo"], ["permissao"])


def test_saida_que_estoura_vira_log_e_a_troca_de_cena_continua(app_auth, monkeypatch, caplog):
    from app.api import palco as api_palco

    def estoura(app, cena):
        raise RuntimeError("disco cheio")

    monkeypatch.setitem(api_palco._SAIDAS, "encerrar_evacuacao", estoura)
    with caplog.at_level("ERROR"):
        api_palco._ao_sair(app_auth, _cena("evacuacao"))  # não levanta
    assert "palco_saida_falhou" in caplog.text
