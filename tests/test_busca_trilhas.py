"""Busca nas trilhas (M6): filtros, agregação por trecho contínuo, replay e papéis da API."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone

import pytest
from app import create_app
from app.api.busca import busca_bp
from app.config import AuthTestConfig
from app.extensions import db
from app.models import Alert, Camera, Incidente
from app.services.auth_service import AuthService
from app.services.busca_trilhas import MAX_PONTOS, AlertaDaBusca, Filtros, amostrar, associar_clipes, buscar

SENHA = "senha-forte-de-teste"
DIREITA = ((0.5, 0.0), (1.0, 0.0), (1.0, 1.0), (0.5, 1.0))  # metade direita do quadro


def _p(pid, x=0.2, y=0.8, epis=None, *, cy=None):
    """Uma entrada da trilha: [id, pé_x, pé_y, centro_x, centro_y, epis]."""
    return [pid, x, y, x, y - 0.1 if cy is None else cy, epis if epis is not None else {"helmet": "o", "vest": "o"}]


def _reg(t, *pessoas):
    return {"t": float(t), "p": list(pessoas)}


def _rotulos(resultados):
    return [(r["rotulo"], r["inicio"], r["fim"]) for r in resultados]


# ------------------------------------------------------------- permanência ---
def test_permanencia_minima_continua_descarta_o_trecho_curto():
    sem_capacete = {"helmet": "m", "vest": "o"}
    registros = [_reg(t, _p(1, epis=sem_capacete), _p(2, 0.6, epis=sem_capacete) if t < 3 else _p(2, 0.6)) for t in range(11)]
    todos = buscar(registros, Filtros(epi_ausente=frozenset({"helmet"})), camera_id=7)
    assert {r["rotulo"]: r["duracao_s"] for r in todos} == {"Pessoa 1": 10.0, "Pessoa 2": 2.0}
    longos = buscar(registros, Filtros(epi_ausente=frozenset({"helmet"}), permanencia_min_s=5), camera_id=7)
    assert [r["rotulo"] for r in longos] == ["Pessoa 1"]
    assert longos[0]["camera_id"] == 7 and longos[0]["rastreio"] == 1


def test_permanencia_so_conta_tempo_continuo_que_atende_o_filtro():
    # Sem capacete 4 s, com capacete 1 s, sem capacete 4 s: nenhum trecho chega a 5 s.
    estados = ["m"] * 5 + ["o"] + ["m"] * 5
    registros = [_reg(t, _p(1, epis={"helmet": e})) for t, e in enumerate(estados)]
    assert buscar(registros, Filtros(epi_ausente=frozenset({"helmet"}), permanencia_min_s=5)) == []
    dois = buscar(registros, Filtros(epi_ausente=frozenset({"helmet"}), permanencia_min_s=4))
    assert [(r["inicio"], r["fim"]) for r in dois] == [(6.0, 10.0), (0.0, 4.0)]  # mais recente primeiro


# -------------------------------------------------------------------- zona ---
def test_zona_usa_o_centro_da_caixa_e_quebra_o_trecho_ao_sair():
    xs = [0.2, 0.2, 0.7, 0.8, 0.8, 0.2, 0.7, 0.7]
    registros = [_reg(t, _p(1, x)) for t, x in enumerate(xs)]
    dentro = buscar(registros, Filtros(zona=DIREITA))
    assert [(r["inicio"], r["fim"]) for r in dentro] == [(6.0, 7.0), (2.0, 4.0)]
    assert buscar(registros, Filtros(zona=None))[0]["total_pontos"] == len(xs)


def test_zona_olha_o_centro_e_nao_o_pe():
    # Pé na zona (x=0.9), centro fora (cx=0.3): não conta.
    registros = [_reg(t, [1, 0.9, 0.9, 0.3, 0.8, {}]) for t in range(4)]
    assert buscar(registros, Filtros(zona=DIREITA)) == []


# --------------------------------------------------------------------- EPI ---
def test_epi_ausente_basta_um_dos_pedidos_e_lista_o_que_faltou():
    registros = [_reg(t, _p(1, epis={"helmet": "o", "vest": "m"}), _p(2, 0.7, epis={"helmet": "o", "vest": "o"})) for t in range(4)]
    so_capacete = buscar(registros, Filtros(epi_ausente=frozenset({"helmet"})))
    assert so_capacete == []
    qualquer = buscar(registros, Filtros(epi_ausente=frozenset({"helmet", "vest"})))
    assert [(r["rotulo"], r["epis_ausentes"]) for r in qualquer] == [("Pessoa 1", ["vest"])]


def test_epi_ausente_aceita_os_nomes_missing_e_ausente_e_ignora_nao_verificavel():
    registros = [
        _reg(0, _p(1, epis={"helmet": "missing"}), _p(2, epis={"helmet": "ausente"}), _p(3, epis={"helmet": "n"})),
        _reg(1, _p(1, epis={"helmet": "missing"}), _p(2, epis={"helmet": "ausente"}), _p(3, epis={"helmet": "i"})),
    ]
    achados = buscar(registros, Filtros(epi_ausente=frozenset({"helmet"})))
    assert sorted(r["rotulo"] for r in achados) == ["Pessoa 1", "Pessoa 2"]


# -------------------------------------------------------------- velocidade ---
def _caminhada(passo, n=6, pid=1):
    return [_reg(t, _p(pid, 0.1 + passo * t)) for t in range(n)]


def test_velocidade_e_deslocamento_dos_pes_por_segundo():
    parado, andando = _caminhada(0.0, pid=1), _caminhada(0.1, pid=2)
    registros = [_reg(a["t"], *a["p"], *b["p"]) for a, b in zip(parado, andando, strict=True)]
    rapidos = buscar(registros, Filtros(vel_min=0.05))
    assert [(r["rotulo"], r["velocidade_media"]) for r in rapidos] == [("Pessoa 2", 0.1)]
    lentos = buscar(registros, Filtros(vel_max=0.01))
    assert [r["rotulo"] for r in lentos] == ["Pessoa 1"]


def test_velocidade_normaliza_pelo_intervalo_entre_amostras():
    # 0,2 do quadro em 2 s é a mesma velocidade que 0,1 em 1 s.
    registros = [_reg(0, _p(1, 0.1)), _reg(2, _p(1, 0.3)), _reg(4, _p(1, 0.5))]
    assert buscar(registros, Filtros(vel_min=0.099, vel_max=0.101))[0]["velocidade_media"] == 0.1


def test_primeira_amostra_nao_tem_velocidade_e_nao_passa_no_filtro():
    registros = _caminhada(0.1, n=3)
    achado = buscar(registros, Filtros(vel_min=0.05))[0]
    assert achado["inicio"] == 1.0 and achado["total_pontos"] == 2


# --------------------------------------------------------------- agregação ---
def test_agrega_por_rotulo_e_trecho_e_separa_quando_o_id_some():
    registros = [_reg(t, _p(1), _p(2, 0.6)) for t in range(0, 4)]
    registros += [_reg(t, _p(1)) for t in range(20, 23)]  # Pessoa 1 volta 16 s depois; Pessoa 2 não
    achados = buscar(registros, Filtros(lacuna_s=6))
    assert _rotulos(achados) == [("Pessoa 1", 20.0, 22.0), ("Pessoa 1", 0.0, 3.0), ("Pessoa 2", 0.0, 3.0)]
    assert buscar(registros, Filtros(lacuna_s=30))[0]["inicio"] == 0.0  # lacuna tolerada: um trecho só


def test_pontos_amostrados_no_maximo_200_com_primeiro_e_ultimo():
    registros = [_reg(t, _p(1, 0.1 + 0.0001 * t)) for t in range(1000)]
    achado = buscar(registros, Filtros())[0]
    assert achado["total_pontos"] == 1000 and len(achado["pontos"]) == MAX_PONTOS
    assert achado["pontos"][0][2] == 0.0 and achado["pontos"][-1][2] == 999.0
    tempos = [p[2] for p in achado["pontos"]]
    assert tempos == sorted(tempos)
    assert len(amostrar(list(range(50)))) == 50


def test_janela_de_horario_corta_antes_e_depois():
    registros = [_reg(t, _p(1)) for t in range(100)]
    achado = buscar(registros, Filtros(de=10, ate=20))[0]
    assert (achado["inicio"], achado["fim"]) == (10.0, 20.0)
    assert buscar(registros, Filtros(de=500, ate=600)) == []


def test_filtros_combinados_valem_ao_mesmo_tempo():
    sem = {"helmet": "m"}
    registros = [_reg(t, _p(1, 0.7, epis=sem), _p(2, 0.2, epis=sem), _p(3, 0.7)) for t in range(8)]
    achados = buscar(registros, Filtros(zona=DIREITA, epi_ausente=frozenset({"helmet"}), permanencia_min_s=5))
    assert [r["rotulo"] for r in achados] == ["Pessoa 1"]


def test_linhas_malformadas_sao_ignoradas_e_a_busca_e_deterministica():
    registros = [{"p": [_p(1)]}, {"t": "x", "p": []}, _reg(0, [1, 0.2], "lixo", _p(1)), _reg(1, _p(1)), _reg(2, _p(1))]
    a, b = buscar(registros, Filtros()), buscar(registros, Filtros())
    assert a == b and a[0]["total_pontos"] == 3


def test_rotulo_nunca_carrega_identidade():
    achado = buscar([_reg(0, _p(5)), _reg(1, _p(5))], Filtros())[0]
    assert achado["rotulo"] == "Pessoa 5"
    assert not {"nome", "name", "identidade"} & achado.keys()


# --------------------------------------------------------- clipe do replay ---
def test_associar_clipes_prefere_a_mesma_pessoa_e_so_considera_alerta_com_clipe():
    achados = buscar([_reg(t, _p(1)) for t in range(10, 20)], Filtros())
    alertas = [
        AlertaDaBusca(id=1, t=10.5, rastreio=2, incidente_id=9),    # mais perto, mas de outra pessoa
        AlertaDaBusca(id=2, t=15.0, rastreio=1, incidente_id=11),   # mesma pessoa
        AlertaDaBusca(id=3, t=16.0, rastreio=1, incidente_id=12),   # mesma pessoa, sem clipe gravado
        AlertaDaBusca(id=4, t=200.0, rastreio=1, incidente_id=13),  # fora do período
    ]
    ligado = associar_clipes(achados, alertas, lambda i: i != 3)[0]
    assert (ligado["alerta_id"], ligado["incidente_id"], ligado["clipe_da_mesma_pessoa"]) == (2, 11, True)

    so_de_outra = associar_clipes(achados, alertas[:1], lambda _i: True)[0]
    assert (so_de_outra["alerta_id"], so_de_outra["clipe_da_mesma_pessoa"]) == (1, False)

    sem_clipe = associar_clipes(achados, alertas, lambda _i: False)[0]
    assert sem_clipe["alerta_id"] is None and sem_clipe["incidente_id"] is None
    assert achados[0]["alerta_id"] is None  # a entrada não é alterada


# --------------------------------------------------------------------- API ---
ZONA_API = [[0.5, 0.0], [1.0, 0.0], [1.0, 1.0], [0.5, 1.0]]
PLANTA = {"pontos_camera": [[0.1, 0.5], [0.9, 0.5], [0.9, 0.95], [0.1, 0.95]], "pontos_planta": [[0, 0], [1, 0], [1, 1], [0, 1]]}


def _pessoa(pid, x, y=800, helmet="ok"):
    """Caixa em quadro 1000x1000: pé em (x/1000, y/1000), centro 100 px acima."""
    return {"id": f"person_{pid}", "box": {"x1": x - 50, "y1": y - 200, "x2": x + 50, "y2": y},
            "ppe": {"helmet": {"status": helmet}, "vest": {"status": "ok"}}}


@pytest.fixture()
def app_auth(tmp_path):
    class Cfg(AuthTestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'busca.db'}"
        TRILHAS_DIR = str(tmp_path / "trilhas")
        REPLAY_DIR = str(tmp_path / "clips")

    app = create_app(Cfg)
    if busca_bp.name not in app.blueprints:  # o app factory já registra
        app.register_blueprint(busca_bp)
    with app.app_context():
        db.create_all()
        db.session.add(Camera(id=1, name="Pátio", source_type="Arquivo", source="x", risk_polygon=ZONA_API, planta=PLANTA))
        db.session.commit()
        app.extensions["monitor_service"].load_cameras_from_db()
        db.session.add(Camera(id=2, name="Sem worker", source_type="Arquivo", source="x"))
        db.session.commit()
        AuthService().create_user(email="sup@x.local", name="Sup", password=SENHA, role="supervisor")
        AuthService().create_user(email="tec@x.local", name="Tec", password=SENHA, role="technical")
        AuthService().create_user(email="op@x.local", name="Op", password=SENHA, role="operator", camera_id=1)
    return app


def _entrar(app, email):
    cliente = app.test_client()
    assert cliente.post("/api/auth/login", json={"email": email, "password": SENHA}).status_code == 200
    return cliente


def _gravar(app, base, quadros):
    """quadros: lista de listas de pessoas, 1 s entre eles, começando em `base`."""
    with app.app_context():
        trilhas = app.extensions["monitor_service"].worker_da_camera(1).trilhas
        for i, pessoas in enumerate(quadros):
            trilhas.registrar(base + i, pessoas, 1000, 1000)


def test_sem_sessao_401_operador_403_tecnico_e_supervisor_200(app_auth):
    url = "/api/busca/trilhas?camera_id=1"
    assert app_auth.test_client().get(url).status_code == 401
    operador = _entrar(app_auth, "op@x.local").get(url)
    assert operador.status_code == 403 and operador.get_json()["required_role"] == "technical"
    assert _entrar(app_auth, "tec@x.local").get(url).status_code == 200
    assert _entrar(app_auth, "sup@x.local").get(url).status_code == 200


@pytest.mark.parametrize(
    ("consulta", "campo"),
    [
        ("", "camera_id"),
        ("camera_id=1&permanencia_min_s=abc", "permanencia_min_s"),
        ("camera_id=1&permanencia_min_s=-1", "permanencia_min_s"),
        ("camera_id=1&permanencia_min_s=nan", "permanencia_min_s"),
        ("camera_id=1&vel_min=-0.1", "vel_min"),
        ("camera_id=1&vel_min=0.5&vel_max=0.1", "vel_max"),
        ("camera_id=1&epi_ausente=helmet,chapeu", "epi_ausente"),
        ("camera_id=1&zona=talvez", "zona"),
        ("camera_id=1&de=ontem", "de"),
        ("camera_id=1&de=2026-10-17T10:00:00Z&ate=2026-10-17T09:00:00Z", "ate"),
        ("camera_id=1&limite=0", "limite"),
        ("camera_id=1&limite=201", "limite"),
    ],
)
def test_parametro_invalido_devolve_400_em_portugues(app_auth, consulta, campo):
    resposta = _entrar(app_auth, "tec@x.local").get(f"/api/busca/trilhas?{consulta}")
    corpo = resposta.get_json()
    assert resposta.status_code == 400 and corpo["code"] == "busca_invalida" and corpo["campo"] == campo
    assert corpo["error"].endswith(".") and "invalid" not in corpo["error"].lower()


def test_mensagem_de_erro_diz_o_que_fazer_em_portugues(app_auth):
    resposta = _entrar(app_auth, "tec@x.local").get("/api/busca/trilhas?camera_id=1&permanencia_min_s=abc")
    assert resposta.get_json()["error"] == "Informe a permanência mínima, em segundos, como um número entre 0 e 86400."


def test_camera_inexistente_404_e_sem_trilha_409(app_auth):
    tecnico = _entrar(app_auth, "tec@x.local")
    assert tecnico.get("/api/busca/trilhas?camera_id=99").status_code == 404
    assert tecnico.get("/api/busca/trilhas?camera_id=2").status_code == 409


def test_zona_sem_area_de_risco_desenhada_e_400(app_auth):
    with app_auth.app_context():
        app_auth.extensions["monitor_service"].worker_da_camera(1).rule_engine.risk_polygon = []
    resposta = _entrar(app_auth, "tec@x.local").get("/api/busca/trilhas?camera_id=1&zona=1")
    assert resposta.status_code == 400 and resposta.get_json()["campo"] == "zona"


def test_busca_na_api_filtra_projeta_na_planta_e_liga_o_replay(app_auth, tmp_path):
    base = time.time() - 120
    sem = "missing"
    _gravar(app_auth, base, [
        [_pessoa(1, 700, helmet=sem), _pessoa(2, 200, helmet=sem)] for _ in range(10)
    ])
    with app_auth.app_context():
        alerta = Alert(camera_id=1, rule="missing_helmet", severity="high", message="Sem capacete",
                       metadata_json={"person_id": "person_1"}, created_at=datetime.fromtimestamp(base + 4, tz=timezone.utc))
        db.session.add(alerta)
        db.session.flush()
        db.session.add(Incidente(camera_id=1, rule="missing_helmet", severity="high", titulo="Sem capacete na Zona",
                                 alert_ids=[alerta.id], aberto_em=datetime.fromtimestamp(base + 4, tz=timezone.utc)))
        db.session.commit()
        alerta_id = alerta.id
        incidente_id = Incidente.query.one().id
    pasta = tmp_path / "clips" / f"alert_{alerta_id}"
    pasta.mkdir(parents=True)
    (pasta / "clip.json").write_text(json.dumps({"alert_id": alerta_id, "quadros": [], "total": 0}), encoding="utf-8")

    tecnico = _entrar(app_auth, "tec@x.local")
    corpo = tecnico.get("/api/busca/trilhas?camera_id=1&zona=1&epi_ausente=helmet&permanencia_min_s=5&limite=10").get_json()

    assert corpo["registros_lidos"] == 10 and corpo["total"] == 1 and corpo["camera"]["nome"] == "Pátio"
    assert corpo["camera"]["planta_calibrada"] is True and len(corpo["camera"]["zona_planta"]) >= 3
    assert corpo["filtros"]["epi_ausente"] == ["helmet"] and corpo["filtros"]["zona"] is True
    (achado,) = corpo["items"]
    assert achado["rotulo"] == "Pessoa 1" and achado["duracao_s"] == 9.0 and achado["epis_ausentes"] == ["helmet"]
    assert (achado["alerta_id"], achado["incidente_id"], achado["clipe_da_mesma_pessoa"]) == (alerta_id, incidente_id, True)
    x, y, _t = achado["pontos"][0]
    assert (x, y) == (0.7, 0.8)
    xp, yp, _tp = achado["pontos_planta"][0]
    assert (xp, round(yp, 3)) == (0.75, 0.667)  # homografia da calibração de teste

    sem_zona = tecnico.get("/api/busca/trilhas?camera_id=1&epi_ausente=helmet").get_json()
    assert sorted(r["rotulo"] for r in sem_zona["items"]) == ["Pessoa 1", "Pessoa 2"]
    pessoa2 = next(r for r in sem_zona["items"] if r["rotulo"] == "Pessoa 2")
    assert pessoa2["alerta_id"] == alerta_id and pessoa2["clipe_da_mesma_pessoa"] is False  # clipe do período, de outro rótulo


def test_limite_corta_a_lista_e_informa_o_total(app_auth):
    base = time.time() - 600
    _gravar(app_auth, base, [[_pessoa(1, 700)], [_pessoa(1, 700)], [], [], [], [], [], [], [_pessoa(1, 700)], [_pessoa(1, 700)]])
    corpo = _entrar(app_auth, "tec@x.local").get("/api/busca/trilhas?camera_id=1&limite=1").get_json()
    assert corpo["total"] == 2 and corpo["limite"] == 1 and len(corpo["items"]) == 1
    assert corpo["items"][0]["inicio"] > base + 7  # o mais recente primeiro


def test_camera_sem_planta_calibrada_devolve_so_a_camera(app_auth):
    with app_auth.app_context():
        db.session.get(Camera, 1).planta = None
        db.session.commit()
    _gravar(app_auth, time.time() - 30, [[_pessoa(1, 700)] for _ in range(3)])
    corpo = _entrar(app_auth, "tec@x.local").get("/api/busca/trilhas?camera_id=1").get_json()
    assert corpo["camera"]["planta_calibrada"] is False and corpo["camera"]["zona_planta"] == []
    assert "pontos_planta" not in corpo["items"][0]
