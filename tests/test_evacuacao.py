"""Modo Evacuação (M3, MISSÃO 4): estado puro, API por papel e relatório na cadeia de custódia."""

from __future__ import annotations

import json
import threading
from types import SimpleNamespace

import pytest
from app import create_app
from app.api import evacuacao as api_evacuacao
from app.api.evacuacao import evacuacao_bp
from app.config import AuthTestConfig
from app.extensions import db
from app.models import Camera, ElodeCustodia, EventLog
from app.services import custodia
from app.services.auth_service import AuthService
from app.services.evacuacao import (
    AVISO_DUPLA_CONTAGEM,
    Evacuacao,
    EvacuacaoInativa,
    EvacuacaoJaAtiva,
    arquivar_relatorio,
    coletar_cameras_info,
    gravar_relatorio,
    ler_relatorio,
    listar_relatorios,
    sha256_do_relatorio,
    ultimo_resumo,
)
from app.services.palco import Palco

SENHA = "senha-forte-de-teste"
T0 = 1_000_000.0  # relógio falso: tudo é função do `agora` passado


def _cam(cid=1, pessoas=0, zonas=None, pes=(), ts=None, online=True, nome=None):
    return {"id": cid, "nome": nome or f"Cam {cid}", "pessoas": pessoas, "zonas": zonas or {},
            "pes_na_planta": [{"x": x, "y": y, "track_id": t} for t, x, y in pes], "ts_ultima_analise": ts, "online": online}


# ------------------------------------------------------------------ service puro
def test_cronometro_segue_o_relogio_passado():
    e = Evacuacao()
    assert not e.ativa
    e.iniciar("sup@x.local", None, T0)
    assert e.ativa
    assert e.snapshot([_cam()], T0 + 12.5)["segundos"] == 12.5
    assert e.snapshot([_cam()], T0 + 90)["segundos"] == 90.0


def test_snapshot_conta_por_camera_e_zona_e_soma_o_total():
    e = Evacuacao()
    e.iniciar("sup@x.local", None, T0)
    snap = e.snapshot([_cam(1, 3, {"Prensa": 2}), _cam(2, 4, {"Doca": 1})], T0 + 1)
    por_id = {c["id"]: c for c in snap["cameras"]}
    assert por_id[1]["pessoas"] == 3 and por_id[1]["zonas"] == {"Prensa": 2}
    assert por_id[2]["pessoas"] == 4 and por_id[2]["zonas"] == {"Doca": 1}
    assert snap["total"] == 7


def test_aviso_de_dupla_contagem_sempre_presente():
    e = Evacuacao()
    assert e.snapshot([], T0)["aviso"] == AVISO_DUPLA_CONTAGEM  # sem evacuação
    e.iniciar("sup@x.local", 1, T0)
    assert e.snapshot([_cam(1, 1)], T0 + 1)["aviso"] == AVISO_DUPLA_CONTAGEM
    assert e.snapshot([], T0 + 2)["aviso"] == AVISO_DUPLA_CONTAGEM  # nem sem câmera nenhuma
    assert e.encerrar("sup@x.local", T0 + 3)["aviso"] == AVISO_DUPLA_CONTAGEM
    assert "dupla contagem" in AVISO_DUPLA_CONTAGEM


def test_camera_offline_nao_conta_pessoas():
    e = Evacuacao()
    e.iniciar("sup@x.local", None, T0)
    snap = e.snapshot([_cam(1, 5, {"A": 5}, pes=[(1, 0.1, 0.1)], online=False), _cam(2, 2)], T0 + 1)
    por_id = {c["id"]: c for c in snap["cameras"]}
    assert por_id[1]["online"] is False and por_id[1]["pessoas"] == 0 and por_id[1]["zonas"] == {}
    assert snap["total"] == 2
    assert snap["ultimas_posicoes"] == []  # câmera offline não alimenta a planta


def test_ultima_posicao_do_track_fica_com_o_horario_mesmo_depois_de_sumir():
    e = Evacuacao()
    e.iniciar("sup@x.local", None, T0)
    e.observar([_cam(1, 1, pes=[(7, 0.1, 0.2)])], T0 + 1)
    e.observar([_cam(1, 1, pes=[(7, 0.3, 0.4)])], T0 + 2)
    visivel = e.snapshot([_cam(1, 1, pes=[(7, 0.3, 0.4)])], T0 + 3)["ultimas_posicoes"]  # o snapshot também observa
    assert visivel == [{"camera_id": 1, "track_id": 7, "x": 0.3, "y": 0.4, "visto_em": visivel[0]["visto_em"],
                        "ha_s": 0.0, "visivel_agora": True}]
    # O track some: a última posição vista continua lá, agora marcada como não visível.
    sumido = e.snapshot([_cam(1, 0)], T0 + 20)["ultimas_posicoes"]
    assert len(sumido) == 1
    assert (sumido[0]["x"], sumido[0]["y"], sumido[0]["ha_s"], sumido[0]["visivel_agora"]) == (0.3, 0.4, 17.0, False)
    assert sumido[0]["visto_em"].startswith("1970-01-12")  # ISO UTC do horário em que foi visto


def test_posicao_usa_o_horario_da_analise_quando_a_camera_atrasou():
    e = Evacuacao()
    e.iniciar("sup@x.local", None, T0)
    snap = e.snapshot([_cam(1, 1, pes=[(3, 0.5, 0.5)], ts=T0 + 2)], T0 + 30)
    assert snap["ultimas_posicoes"][0]["ha_s"] == 28.0
    assert snap["cameras"][0]["desatualizada"] is True and snap["cameras"][0]["idade_analise_s"] == 28.0


def test_so_ha_rotulo_de_rastreio_nunca_identidade():
    e = Evacuacao()
    e.iniciar("sup@x.local", None, T0)
    snap = e.snapshot([_cam(1, 1, pes=[(7, 0.1, 0.2)])], T0 + 1)
    assert set(snap["ultimas_posicoes"][0]) == {"camera_id", "track_id", "x", "y", "visto_em", "ha_s", "visivel_agora"}


def test_chegadas_e_o_maximo_simultaneo_na_camera_do_ponto_de_encontro():
    e = Evacuacao()
    e.iniciar("sup@x.local", 2, T0)
    for n_ponto, n_outra, t in ((2, 9, 1), (5, 9, 2), (3, 9, 3), (0, 9, 4)):
        e.observar([_cam(1, n_outra), _cam(2, n_ponto)], T0 + t)
    snap = e.snapshot([_cam(1, 9), _cam(2, 1)], T0 + 5)
    assert snap["chegadas_ponto_de_encontro"] == 5  # o pico, não o valor atual (1) nem o da outra câmera (9)
    assert e.encerrar("sup@x.local", T0 + 6)["chegadas_ponto_de_encontro"] == 5


def test_sem_ponto_de_encontro_chegadas_e_nulo():
    e = Evacuacao()
    e.iniciar("sup@x.local", None, T0)
    assert e.snapshot([_cam(1, 4)], T0 + 1)["chegadas_ponto_de_encontro"] is None


def test_serie_temporal_e_amostrada_a_cada_5_s():
    e = Evacuacao()
    e.iniciar("sup@x.local", 1, T0)
    for t in (0, 1, 2, 4.9, 5, 6, 9, 10, 10.5):
        e.observar([_cam(1, int(t))], T0 + t)
    serie = e.snapshot([_cam(1, 0)], T0 + 10.6)["serie"]
    assert [p["t_s"] for p in serie] == [0.0, 5.0, 10.0]
    assert serie[1]["por_camera"] == {"1": 5} and serie[1]["ponto_de_encontro"] == 5 and serie[1]["total"] == 5


def test_relatorio_tem_o_conteudo_pedido_e_sha256_do_json_canonico():
    e = Evacuacao()
    e.iniciar("sup@x.local", 2, T0)
    e.observar([_cam(1, 3, pes=[(1, 0.1, 0.1)]), _cam(2, 2)], T0 + 1)
    e.observar([_cam(1, 1), _cam(2, 6)], T0 + 7)
    rel = e.encerrar("tec2@x.local", T0 + 61.5)
    assert not e.ativa
    assert rel["inicio"].endswith("+00:00") and rel["fim"].endswith("+00:00") and rel["duracao_s"] == 61.5
    assert rel["iniciada_por"] == "sup@x.local" and rel["encerrada_por"] == "tec2@x.local"
    assert rel["maximo_por_camera"] == [{"camera_id": 1, "nome": "Cam 1", "maximo": 3},
                                        {"camera_id": 2, "nome": "Cam 2", "maximo": 6}]
    assert rel["chegadas_ponto_de_encontro"] == 6 and rel["total_maximo_somado"] == 7
    assert [p["t_s"] for p in rel["serie_temporal"]] == [1.0, 7.0]
    assert rel["aviso"] == AVISO_DUPLA_CONTAGEM
    assert rel["sha256"] == sha256_do_relatorio(rel)
    # Mexer em qualquer campo muda o hash; o próprio campo sha256 e o número do arquivo não entram nele.
    assert sha256_do_relatorio(rel | {"chegadas_ponto_de_encontro": 7}) != rel["sha256"]
    assert sha256_do_relatorio(rel | {"numero": 12, "sha256": "x"}) == rel["sha256"]
    # E sobrevive a uma ida e volta pelo JSON (é assim que o relatório é conferido depois).
    assert sha256_do_relatorio(json.loads(json.dumps(rel))) == rel["sha256"]


def test_iniciar_duas_vezes_e_encerrar_sem_iniciar_sao_recusados():
    e = Evacuacao()
    with pytest.raises(EvacuacaoInativa):
        e.encerrar("sup@x.local", T0)
    e.iniciar("sup@x.local", None, T0)
    with pytest.raises(EvacuacaoJaAtiva):
        e.iniciar("outro@x.local", None, T0 + 1)
    e.encerrar("sup@x.local", T0 + 2)
    with pytest.raises(EvacuacaoInativa):
        e.encerrar("sup@x.local", T0 + 3)


def test_nova_evacuacao_nao_herda_o_estado_da_anterior():
    e = Evacuacao()
    e.iniciar("sup@x.local", 1, T0)
    e.observar([_cam(1, 8, pes=[(1, 0.1, 0.1)])], T0 + 1)
    sessao = e.sessao
    e.encerrar("sup@x.local", T0 + 2)
    e.iniciar("sup@x.local", 1, T0 + 100)
    assert e.sessao == sessao + 1
    snap = e.snapshot([_cam(1, 0)], T0 + 101)
    assert snap["chegadas_ponto_de_encontro"] == 0 and snap["ultimas_posicoes"] == [] and snap["segundos"] == 1.0


def test_relatorio_resume_a_serie_longa_sem_perder_o_ultimo_ponto():
    e = Evacuacao(amostra_s=1.0)
    e.iniciar("sup@x.local", None, T0)
    for t in range(1000):
        e.observar([_cam(1, t % 7)], T0 + t)
    rel = e.encerrar("sup@x.local", T0 + 1000)
    assert len(rel["serie_temporal"]) <= 121
    assert rel["serie_temporal"][0]["t_s"] == 0.0 and rel["serie_temporal"][-1]["t_s"] == 999.0


def test_observacoes_concorrentes_nao_quebram_o_estado():
    e = Evacuacao(amostra_s=0.5)
    e.iniciar("sup@x.local", 1, T0)
    erros: list[Exception] = []

    def trabalhar(base: int) -> None:
        try:
            for i in range(200):
                e.observar([_cam(1, i % 9, pes=[(base, 0.1, 0.1)])], T0 + i * 0.1)
                e.snapshot([_cam(1, 1)], T0 + i * 0.1)
        except Exception as exc:  # noqa: BLE001
            erros.append(exc)

    threads = [threading.Thread(target=trabalhar, args=(n,)) for n in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not erros
    assert e.encerrar("sup@x.local", T0 + 30)["chegadas_ponto_de_encontro"] == 8


# ------------------------------------------------------------------ relatórios em disco
def test_relatorios_sao_numerados_e_listados_do_mais_novo_ao_mais_velho(tmp_path):
    pasta = tmp_path / "evac"
    assert listar_relatorios(pasta) == [] and ultimo_resumo(pasta) is None
    for n in (1, 2):
        e = Evacuacao()
        e.iniciar("sup@x.local", None, T0)
        caminho = gravar_relatorio(e.encerrar(f"u{n}@x.local", T0 + n), pasta)
        assert caminho.name == f"evacuacao_{n}.json"
    assert [r["numero"] for r in listar_relatorios(pasta)] == [2, 1]
    assert ultimo_resumo(pasta)["encerrada_por"] == "u2@x.local"
    lido = ler_relatorio(pasta, 1)
    assert lido["numero"] == 1 and lido["sha256"] == sha256_do_relatorio(lido)
    assert ler_relatorio(pasta, 99) is None


def test_gravar_nunca_sobrescreve_relatorio_existente(tmp_path):
    pasta = tmp_path / "evac"
    pasta.mkdir()
    (pasta / "evacuacao_1.json").write_text("{}", encoding="utf-8")
    e = Evacuacao()
    e.iniciar("sup@x.local", None, T0)
    assert gravar_relatorio(e.encerrar("sup@x.local", T0 + 1), pasta).name == "evacuacao_2.json"
    assert (pasta / "evacuacao_1.json").read_text(encoding="utf-8") == "{}"


# ------------------------------------------------------------------ coletar_cameras_info
class _Evento:
    def __init__(self, ligado: bool) -> None:
        self._ligado = ligado

    def is_set(self) -> bool:
        return self._ligado


class _WorkerFalso:
    def __init__(self, ligado=True, pessoas=(), pes=(), ts_ms=None, zona="Prensa", poligono=True):
        self._running = _Evento(ligado)
        self._pessoas = list(pessoas)
        self.pes_na_planta = list(pes)
        self._ts_analise_ms = ts_ms
        self.risk_area_name = zona
        self.rule_engine = SimpleNamespace(risk_polygon=[(0, 0), (1, 0), (1, 1)] if poligono else [])

    def latest_analysis(self):
        return {"compliance": {"people": self._pessoas}}


def test_coletar_le_os_workers_sem_travar_e_nao_vaza_identidade(app):
    db.session.add(Camera(id=1, name="Pátio", source_type="Arquivo", source="x", fps=12, width=64, height=48))
    db.session.commit()
    pessoas = [{"track_id": 1, "risk_area": {"status": "inside"}}, {"track_id": 2, "risk_area": {"status": "outside"}}]
    pes = [{"track_id": 1, "x": 0.1, "y": 0.2, "estado": "sem_epi", "faltando": ["helmet"], "na_zona": True}]
    monitor = SimpleNamespace(
        _workers_lock=threading.RLock(),
        _workers={1: _WorkerFalso(pessoas=pessoas, pes=pes, ts_ms=5_000_000.0),
                  2: _WorkerFalso(ligado=False, pessoas=pessoas, pes=pes),
                  3: _WorkerFalso(poligono=False)},
    )
    info = {c["id"]: c for c in coletar_cameras_info(monitor)}
    assert info[1] == {"id": 1, "nome": "Pátio", "pessoas": 2, "zonas": {"Prensa": 1},
                       "pes_na_planta": [{"x": 0.1, "y": 0.2, "track_id": 1}],  # sem estado de EPI
                       "ts_ultima_analise": 5000.0, "online": True}
    assert info[2]["online"] is False and info[2]["pessoas"] == 0 and info[2]["pes_na_planta"] == []
    assert info[2]["nome"] == "Câmera 2"  # sem linha no banco
    assert info[3]["zonas"] == {} and info[3]["ts_ultima_analise"] is None


def test_coletar_com_monitor_sem_workers_devolve_lista_vazia(app):
    assert coletar_cameras_info(SimpleNamespace()) == []
    assert coletar_cameras_info(app.extensions["monitor_service"]) == []  # DummyMonitor da suíte


# ------------------------------------------------------------------ custódia
def _evacuacao_encerrada(por="sup@x.local"):
    e = Evacuacao()
    e.iniciar(por, 1, T0)
    e.observar([_cam(1, 4)], T0 + 1)
    return e.encerrar(por, T0 + 2)


def test_encerrar_gera_elo_evacuacao_e_a_cadeia_continua_integra(app, tmp_path):
    caminho, registrado = arquivar_relatorio(_evacuacao_encerrada(), tmp_path / "evac")
    assert registrado
    elo = ElodeCustodia.query.one()
    assert elo.tipo == "evacuacao" and elo.ref == "evacuacao_1.json"
    assert elo.conteudo_sha256 == custodia.sha256_bytes(caminho.read_bytes())
    r = custodia.verificar()
    assert r["integra"] and not r["adulterada"]
    assert [e["tipo"] for e in r["elos"]] == ["evacuacao"]


def test_um_byte_adulterado_no_json_quebra_exatamente_o_elo_da_evacuacao(app, tmp_path):
    custodia.registrar_evento(_evento_qualquer())  # um elo antes e um depois: só o do meio pode ser apontado
    caminho, _ = arquivar_relatorio(_evacuacao_encerrada(), tmp_path / "evac")
    custodia.registrar_evento(_evento_qualquer())
    assert custodia.verificar()["integra"]
    dados = bytearray(caminho.read_bytes())
    dados[10] ^= 0x01
    caminho.write_bytes(bytes(dados))
    r = custodia.verificar()
    assert r["adulterada"] and not r["integra"]
    assert (r["quebrado"]["tipo"], r["quebrado"]["id"], r["quebrado"]["situacao"]) == ("evacuacao", 2, "conteudo_alterado")
    assert [e["id"] for e in r["elos"] if e["situacao"] != "ok"] == [2]


def test_relatorio_removido_do_disco_aparece_como_ausente_nao_como_adulteracao(app, tmp_path):
    caminho, _ = arquivar_relatorio(_evacuacao_encerrada(), tmp_path / "evac")
    caminho.unlink()
    r = custodia.verificar()
    assert r["ausentes"] == 1 and not r["adulterada"] and not r["integra"]


def test_custodia_desligada_grava_o_arquivo_mas_nao_o_elo(app, tmp_path):
    caminho, registrado = arquivar_relatorio(_evacuacao_encerrada(), tmp_path / "evac", custodia_ativa=False)
    assert caminho.is_file() and not registrado and ElodeCustodia.query.count() == 0


def _evento_qualquer() -> EventLog:
    ev = EventLog(camera_id=1, event_type="privacy_toggled", message="Privacidade LIGADA", subject="s@x", metadata_json={})
    db.session.add(ev)
    db.session.commit()
    return ev


# ------------------------------------------------------------------ API
class _Socket:
    def __init__(self) -> None:
        self.events: list[tuple[str, object]] = []

    def emit(self, evento, payload=None, *args, **kwargs):
        self.events.append((evento, payload))


@pytest.fixture()
def app_auth(tmp_path):
    class Cfg(AuthTestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'evacuacao.db'}"
        EVACUACAO_DIR = str(tmp_path / "relatorios")

    app = create_app(Cfg)
    app.register_blueprint(evacuacao_bp)  # o app factory registra na integração; aqui, só no app de teste
    with app.app_context():
        db.create_all()
        db.session.add_all([Camera(id=1, name="Portaria", source_type="Arquivo", source="x", fps=12, width=64, height=48),
                            Camera(id=2, name="Pátio", source_type="Arquivo", source="x", fps=12, width=64, height=48)])
        db.session.commit()
        AuthService().create_user(email="sup@x.local", name="Sup", password=SENHA, role="supervisor")
        AuthService().create_user(email="tec@x.local", name="Tec", password=SENHA, role="technical")
        AuthService().create_user(email="op@x.local", name="Op", password=SENHA, role="operator", camera_id=1)
        app.extensions["monitor_service"].socketio = _Socket()
    return app


def _login(app, email):
    c = app.test_client()
    assert c.post("/api/auth/login", json={"email": email, "password": SENHA}).status_code == 200
    return c


@pytest.fixture()
def cameras_falsas(monkeypatch):
    """Duas câmeras controláveis no lugar dos workers (o coletor tem teste próprio acima)."""
    estado = {"c1": 3, "c2": 0}

    def info(_monitor):
        return [_cam(1, estado["c1"], {"Prensa": 1}, pes=[(11, 0.2, 0.3)], nome="Portaria"), _cam(2, estado["c2"], nome="Pátio")]

    monkeypatch.setattr(api_evacuacao, "coletar_cameras_info", info)
    return estado


def test_sem_sessao_401_em_todas_as_rotas(app_auth):
    c = app_auth.test_client()
    assert c.post("/api/evacuacao/iniciar").status_code == 401
    assert c.post("/api/evacuacao/encerrar").status_code == 401
    assert c.get("/api/evacuacao").status_code == 401
    assert c.get("/api/evacuacao/relatorios").status_code == 401
    assert c.get("/api/evacuacao/relatorios/1").status_code == 401


def test_operador_recebe_403_em_tudo(app_auth):
    op = _login(app_auth, "op@x.local")
    assert op.post("/api/evacuacao/iniciar").status_code == 403
    assert op.post("/api/evacuacao/encerrar").status_code == 403
    assert op.get("/api/evacuacao").status_code == 403
    assert op.get("/api/evacuacao/relatorios").status_code == 403


def test_tecnico_ve_mas_nao_inicia_nem_encerra(app_auth, cameras_falsas):
    tec = _login(app_auth, "tec@x.local")
    assert tec.post("/api/evacuacao/iniciar").status_code == 403
    assert tec.post("/api/evacuacao/encerrar").status_code == 403
    assert tec.get("/api/evacuacao").get_json() == {"ativa": False, "ultima": None}
    assert tec.get("/api/evacuacao/relatorios").get_json() == {"items": [], "total": 0}
    assert not app_auth.extensions["evacuacao"].ativa


def test_supervisor_inicia_acompanha_e_encerra(app_auth, cameras_falsas):
    sup, tec = _login(app_auth, "sup@x.local"), _login(app_auth, "tec@x.local")
    r = sup.post("/api/evacuacao/iniciar", json={"ponto_de_encontro_camera_id": 2})
    assert r.status_code == 200
    snap = r.get_json()
    assert snap["ativa"] and snap["iniciada_por"] == "sup@x.local" and snap["ponto_de_encontro_camera_id"] == 2
    assert snap["aviso"] == AVISO_DUPLA_CONTAGEM and snap["total"] == 3
    assert snap["cameras"][0]["zonas"] == {"Prensa": 1}

    cameras_falsas["c1"], cameras_falsas["c2"] = 1, 5
    vivo = tec.get("/api/evacuacao").get_json()  # o técnico acompanha
    assert vivo["ativa"] and vivo["total"] == 6 and vivo["chegadas_ponto_de_encontro"] == 5
    assert vivo["ultimas_posicoes"] == [{"camera_id": 1, "track_id": 11, "x": 0.2, "y": 0.3,
                                         "visto_em": vivo["ultimas_posicoes"][0]["visto_em"],
                                         "ha_s": vivo["ultimas_posicoes"][0]["ha_s"], "visivel_agora": True}]

    assert sup.post("/api/evacuacao/iniciar").status_code == 409  # já ativa
    fim = sup.post("/api/evacuacao/encerrar")
    assert fim.status_code == 200
    corpo = fim.get_json()
    assert not corpo["ativa"] and corpo["arquivo"] == "evacuacao_1.json" and corpo["custodia_registrada"] is True
    rel = corpo["relatorio"]
    assert rel["numero"] == 1 and rel["iniciada_por"] == rel["encerrada_por"] == "sup@x.local"
    assert rel["chegadas_ponto_de_encontro"] == 5 and rel["aviso"] == AVISO_DUPLA_CONTAGEM
    assert rel["sha256"] == sha256_do_relatorio(rel)

    assert sup.post("/api/evacuacao/encerrar").status_code == 409  # já encerrada
    assert tec.get("/api/evacuacao").get_json()["ultima"]["numero"] == 1
    assert tec.get("/api/evacuacao/relatorios").get_json()["total"] == 1
    assert tec.get("/api/evacuacao/relatorios/1").get_json() == rel
    assert tec.get("/api/evacuacao/relatorios/2").status_code == 404


def test_encerrar_pela_api_registra_o_elo_e_a_verificacao_pega_a_adulteracao(app_auth, cameras_falsas, tmp_path):
    sup = _login(app_auth, "sup@x.local")
    sup.post("/api/evacuacao/iniciar", json={"ponto_de_encontro_camera_id": 1})
    sup.post("/api/evacuacao/encerrar")
    with app_auth.app_context():
        elo = ElodeCustodia.query.filter_by(tipo="evacuacao").one()
        elo_id = elo.id
        assert elo.ref == "evacuacao_1.json"
        assert custodia.verificar()["integra"]
    arquivo = tmp_path / "relatorios" / "evacuacao_1.json"
    dados = bytearray(arquivo.read_bytes())
    dados[-3] ^= 0x01
    arquivo.write_bytes(bytes(dados))
    tec = _login(app_auth, "tec@x.local")
    r = tec.get("/api/custodia/verificar").get_json()
    assert r["adulterada"] and r["quebrado"]["tipo"] == "evacuacao" and r["quebrado"]["id"] == elo_id


def test_iniciar_e_encerrar_gravam_evento_e_emitem_para_o_parque(app_auth, cameras_falsas):
    sup = _login(app_auth, "sup@x.local")
    sup.post("/api/evacuacao/iniciar", json={"ponto_de_encontro_camera_id": 2})
    sup.post("/api/evacuacao/encerrar")
    with app_auth.app_context():
        tipos = [e.event_type for e in EventLog.query.order_by(EventLog.id).all()]
        assert tipos == ["evacuacao_iniciada", "evacuacao_encerrada"]
        assert EventLog.query.first().subject == "sup@x.local"
    eventos = [(n, p) for n, p in app_auth.extensions["monitor_service"].socketio.events if n == "evacuacao"]
    assert [p["ativa"] for _, p in eventos] == [True, False]
    assert eventos[1][1]["relatorio"]["numero"] == 1


def test_ponto_de_encontro_invalido_e_recusado(app_auth, cameras_falsas):
    sup = _login(app_auth, "sup@x.local")
    assert sup.post("/api/evacuacao/iniciar", json={"ponto_de_encontro_camera_id": 99}).status_code == 404
    assert sup.post("/api/evacuacao/iniciar", json={"ponto_de_encontro_camera_id": "2"}).status_code == 400
    assert sup.post("/api/evacuacao/iniciar", json={"ponto_de_encontro_camera_id": True}).status_code == 400
    estado = app_auth.extensions.get("evacuacao")  # a validação recusa antes de criar o estado
    assert estado is None or not estado.ativa


def test_token_do_palco_inicia_e_encerra_sem_sessao(app_auth, cameras_falsas):
    celular = app_auth.test_client()
    assert celular.post("/api/evacuacao/iniciar", json={"t": "errado"}).status_code == 403
    assert celular.post("/api/evacuacao/iniciar?t=errado").status_code == 403
    token = app_auth.extensions.setdefault("palco", Palco()).token
    r = celular.post("/api/evacuacao/iniciar", json={"t": token})
    assert r.status_code == 200 and r.get_json()["iniciada_por"] == "palco (token)"
    # O token não dá leitura: ver o estado continua exigindo sessão de técnico.
    assert celular.get(f"/api/evacuacao?t={token}").status_code == 401
    fim = celular.post(f"/api/evacuacao/encerrar?t={token}")
    assert fim.status_code == 200 and fim.get_json()["relatorio"]["encerrada_por"] == "palco (token)"
