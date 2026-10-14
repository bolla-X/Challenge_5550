"""Alertas agrupados em incidentes por (câmera, regra, zona) — MISSÃO 2, P0.2."""

from __future__ import annotations

from app.models import Alert, Incidente
from app.repositories.alert_repository import AlertRepository
from app.services.alert_state_service import AlertStateService
from app.services.risk_rules import RuleAlert


class DummySocket:
    def __init__(self):
        self.events = []

    def emit(self, event, payload=None, *args, **kwargs):
        self.events.append((event, payload))


def sem(feature: str, pessoa: int, *, na_zona: bool = False) -> RuleAlert:
    nomes = {"helmet": "Sem capacete", "vest": "Sem colete"}
    return RuleAlert(
        rule=f"missing_{feature}",
        severity="critical",
        message=f"{nomes[feature]} · Pessoa {pessoa}",
        feature=feature,
        metadata={"person_id": pessoa, "person_label": f"Pessoa {pessoa}", "na_zona": na_zona},
    )


def servico(socket, zona: str | None = "Zona A"):
    return AlertStateService(
        AlertRepository(), socket, create_after_frames=1, resolve_after_frames=1, camera_id=3, nome_da_zona=lambda: zona
    )


def test_tres_pessoas_sem_capacete_viram_um_incidente(app):
    with app.app_context():
        socket = DummySocket()
        s = servico(socket)
        r = s.process([sem("helmet", 4), sem("helmet", 7), sem("helmet", 9)])
        assert len(r["created"]) == 3  # o alerta continua por pessoa (evidência)
        incidentes = s.active_incidents()
        assert len(incidentes) == 1
        inc = incidentes[0]
        assert inc["titulo"] == "Sem capacete"
        assert inc["zona"] == "Fora da zona"
        assert inc["pessoas_ativas"] == [4, 7, 9]
        assert inc["pico_pessoas"] == 3
        # Cada alerta aponta para o incidente.
        assert {a["metadata"]["incidente_id"] for a in r["created"]} == {inc["id"]}
        # O evento de ativos leva os incidentes junto.
        ativos = [p for e, p in socket.events if e == "active_alerts"][-1]
        assert [i["id"] for i in ativos["incidentes"]] == [inc["id"]]


def test_regra_e_zona_diferentes_separam_incidentes(app):
    with app.app_context():
        s = servico(DummySocket())
        s.process([sem("helmet", 1), sem("vest", 1), sem("helmet", 2, na_zona=True)])
        chaves = sorted((i["titulo"], i["zona"]) for i in s.active_incidents())
        assert chaves == [("Sem capacete", "Fora da zona"), ("Sem capacete", "Zona A"), ("Sem colete", "Fora da zona")]


def test_id_do_rastreador_vira_o_numero_mostrado(app):
    with app.app_context():
        s = servico(DummySocket())
        item = sem("helmet", 1)
        item = RuleAlert(item.rule, item.severity, item.message, item.feature, item.metadata | {"person_id": "person_38"})
        s.process([item])
        assert s.active_incidents()[0]["pessoas_ativas"] == [38]


def test_sem_zona_desenhada_a_zona_e_a_camera_toda(app):
    with app.app_context():
        s = servico(DummySocket(), zona=None)
        s.process([sem("helmet", 1, na_zona=True)])
        assert s.active_incidents()[0]["zona"] == "Toda a câmera"


def test_pessoa_que_sai_deixa_o_incidente_e_a_ultima_fecha(app):
    with app.app_context():
        s = servico(DummySocket())
        s.process([sem("helmet", 1), sem("helmet", 2)])
        inc_id = s.active_incidents()[0]["id"]
        s.process([sem("helmet", 2)])  # pessoa 1 voltou a usar capacete
        assert s.active_incidents()[0]["pessoas_ativas"] == [2]
        s.process([])
        assert s.active_incidents() == []
        from app.extensions import db

        inc = db.session.get(Incidente, inc_id)
        assert inc.status == "resolved" and inc.fechado_em is not None
        assert inc.pessoas == [1, 2] and len(inc.alert_ids) == 2


def test_pessoa_nova_entra_no_incidente_aberto(app):
    with app.app_context():
        s = servico(DummySocket())
        s.process([sem("helmet", 1)])
        s.process([sem("helmet", 1), sem("helmet", 5)])
        incs = s.active_incidents()
        assert len(incs) == 1 and incs[0]["pessoas_ativas"] == [1, 5]
        assert Incidente.query.count() == 1


def test_renovacao_do_alerta_mantem_o_incidente(app):
    with app.app_context():
        s = AlertStateService(AlertRepository(), DummySocket(), create_after_frames=1, resolve_after_frames=1,
                              camera_id=3, intervalo_touch=0.0)
        s.process([sem("helmet", 1)])
        s.process([sem("helmet", 1)])  # touch regrava a metadata inteira
        alerta = Alert.query.one()
        assert alerta.metadata_json.get("incidente_id") == s.active_incidents()[0]["id"]


def test_resolver_todos_fecha_os_incidentes(app):
    with app.app_context():
        socket = DummySocket()
        s = servico(socket)
        s.process([sem("helmet", 1), sem("vest", 2)])
        s.resolve_all(reason="manual")
        assert s.active_incidents() == []
        assert Incidente.query.filter_by(status="active").count() == 0


def test_incidente_orfao_de_execucao_anterior_e_fechado(app):
    with app.app_context():
        from app.extensions import db

        db.session.add(Incidente(camera_id=3, rule="missing_helmet", feature="helmet", zona="Zona A", severity="critical",
                                 titulo="Sem capacete", status="active", pessoas=[], alert_ids=[], pico_pessoas=0))
        db.session.commit()
        s = servico(DummySocket())
        s.process([sem("helmet", 1)])
        assert Incidente.query.filter_by(status="active").count() == 1  # só o novo


def _logar(client, app, papel="technical", camera_id=None):
    from app.services.auth_service import AuthService

    with app.app_context():
        AuthService().create_user(email=f"{papel}@t.local", name=papel, password="senha-forte-123", role=papel,
                                  camera_id=camera_id)
    r = client.post("/api/auth/login", json={"email": f"{papel}@t.local", "password": "senha-forte-123"})
    assert r.status_code == 200, r.get_json()


def test_api_lista_detalha_e_reconhece(app, client):
    with app.app_context():
        s = servico(DummySocket())
        s.process([sem("helmet", 1), sem("helmet", 2)])
        inc_id = s.active_incidents()[0]["id"]
    _logar(client, app)
    lista = client.get("/api/incidentes?status=active").get_json()
    assert [i["id"] for i in lista["items"]] == [inc_id]
    detalhe = client.get(f"/api/incidentes/{inc_id}").get_json()
    assert len(detalhe["alertas"]) == 2
    r = client.post(f"/api/incidentes/{inc_id}/reconhecer").get_json()
    assert r["primeira_vez"] and r["incidente"]["reconhecido_em_s"] is not None
    assert client.post(f"/api/incidentes/{inc_id}/reconhecer").get_json()["primeira_vez"] is False
    detalhe = client.get(f"/api/incidentes/{inc_id}").get_json()
    assert all(a["acknowledged"] for a in detalhe["alertas"])


def test_api_operador_so_ve_o_proprio_setor(tmp_path):
    from app import create_app
    from app.config import AuthTestConfig
    from app.extensions import db

    class Cfg(AuthTestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'inc.db'}"

    app = create_app(Cfg)
    client = app.test_client()
    with app.app_context():
        db.create_all()
        s = servico(DummySocket())  # câmera 3
        s.process([sem("helmet", 1)])
        inc_id = s.active_incidents()[0]["id"]
    _logar(client, app, papel="operator", camera_id=99)
    assert client.get("/api/incidentes").get_json()["items"] == []
    assert client.get(f"/api/incidentes/{inc_id}").status_code == 404
