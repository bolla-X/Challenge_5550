"""Simulador "E se?" (X2): trilhas rotativas e reprocessamento determinístico."""

from __future__ import annotations

from app.services.simulador import Parametros, simular
from app.services.trilhas import GravadorDeTrilhas


def pessoa(pid: int, *, x1=100, helmet="missing", vest="ok"):
    return {"id": f"person_{pid}", "box": {"x1": x1, "y1": 200, "x2": x1 + 80, "y2": 400},
            "ppe": {"helmet": {"status": helmet}, "vest": {"status": vest}, "mask": {"status": "disabled"}}}


def test_trilha_grava_sem_imagem_e_le_em_ordem(tmp_path):
    g = GravadorDeTrilhas(tmp_path)
    g.registrar(10.0, [pessoa(3)], 960, 540)
    g.registrar(11.0, [pessoa(3, helmet="ok")], 960, 540)
    regs = list(g.ler())
    assert [r["t"] for r in regs] == [10.0, 11.0]
    pid, pe_x, pe_y, cx, cy, epis = regs[0]["p"][0]
    assert pid == 3 and epis == {"helmet": "m", "vest": "o"}  # desligado não entra
    assert (pe_x, pe_y) == (round(140 / 960, 4), round(400 / 540, 4))
    assert (cx, cy) == (round(140 / 960, 4), round(300 / 540, 4))
    assert list(g.ler(desde=10.5)) == regs[1:]


def test_trilha_rotaciona_no_teto_e_descarta_o_mais_antigo(tmp_path):
    g = GravadorDeTrilhas(tmp_path, teto_bytes=64 * 1024, arquivos=3)
    for i in range(2500):
        g.registrar(float(i), [pessoa(1), pessoa(2, x1=500)], 960, 540)
    assert g.tamanho_total() <= 3 * 64 * 1024 + 200
    assert len(list(tmp_path.glob("trilha*.jsonl"))) == 3
    tempos = [r["t"] for r in g.ler()]
    assert tempos == sorted(tempos) and tempos[-1] == 2499.0 and tempos[0] > 0


def _registros(sequencia):
    """sequencia: lista de (t, [(pid, helmet, cx)])."""
    regs = []
    for t, pessoas in sequencia:
        regs.append({"t": t, "p": [[pid, cx, 0.9, cx, 0.6, {"helmet": h, "vest": "o"}] for pid, h, cx in pessoas]})
    return regs


BASE = dict(criar_apos_quadros=8, criar_apos_s=2.0, min_confirmacoes=2, resolver_apos_quadros=20,
            resolver_apos_s=None, min_confirmacoes_resolver=3)


def test_mesma_entrada_mesmo_resultado():
    regs = _registros([(i * 0.5, [(1, "m", 0.2), (2, "m" if i % 3 else "o", 0.8)]) for i in range(40)])
    p = Parametros(epis=frozenset({"helmet"}), zona=None, **BASE)
    a, b = simular(regs, p), simular(regs, p)
    assert a.alertas == b.alertas and a.incidentes == b.incidentes


def test_histerese_maior_dispara_menos():
    # Pessoa 1 sem capacete 1,5 s; pessoa 2 sem capacete 6 s.
    regs = _registros([(i * 0.5, [(1, "m" if i < 3 else "o", 0.2), (2, "m" if i < 12 else "o", 0.8)]) for i in range(30)])
    curta = simular(regs, Parametros(epis=frozenset({"helmet"}), zona=None, **(BASE | {"criar_apos_s": 1.0})))
    longa = simular(regs, Parametros(epis=frozenset({"helmet"}), zona=None, **(BASE | {"criar_apos_s": 4.0})))
    assert len(curta.alertas) == 2 and len(longa.alertas) == 1
    assert longa.alertas[0]["pessoa"] == 2


def test_desligar_o_epi_zera_os_alertas_dele():
    regs = _registros([(i * 0.5, [(1, "m", 0.2)]) for i in range(20)])
    assert simular(regs, Parametros(epis=frozenset(), zona=None, **BASE)).alertas == []
    assert len(simular(regs, Parametros(epis=frozenset({"helmet"}), zona=None, **BASE)).alertas) == 1


def test_zona_maior_pega_quem_estava_fora():
    regs = _registros([(i * 0.5, [(1, "o", 0.3), (2, "o", 0.8)]) for i in range(20)])
    estreita = ((0.7, 0.0), (1.0, 0.0), (1.0, 1.0), (0.7, 1.0))
    larga = ((0.2, 0.0), (1.0, 0.0), (1.0, 1.0), (0.2, 1.0))
    a = simular(regs, Parametros(epis=frozenset(), zona=estreita, **BASE))
    b = simular(regs, Parametros(epis=frozenset(), zona=larga, **BASE))
    assert {x["pessoa"] for x in a.alertas} == {2}
    assert {x["pessoa"] for x in b.alertas} == {1, 2}
    assert a.incidentes == b.incidentes == 1  # mesma regra, mesma zona: um incidente


def test_api_compara_com_a_regra_atual_e_os_alertas_reais(real_monitor_app, real_monitor_client, tmp_path):
    import time

    from app.extensions import db
    from app.models import Camera

    real_monitor_app.config["TRILHAS_DIR"] = str(tmp_path)
    with real_monitor_app.app_context():
        cam = Camera(name="Pátio", source_type="Arquivo", source="x.mp4")
        db.session.add(cam)
        db.session.commit()
        monitor = real_monitor_app.extensions["monitor_service"]
        monitor.load_cameras_from_db()
        worker = monitor.worker_da_camera(cam.id)
        agora = time.time()
        for i in range(30):
            worker.trilhas.registrar(agora - 30 + i, [pessoa(1)], 960, 540)
        cid = cam.id
    ctx = real_monitor_client.get(f"/api/simulador/contexto?camera_id={cid}").get_json()
    assert ctx["trilha"]["registros"] == 30 and "helmet" in ctx["epis_com_dado"]
    r = real_monitor_client.post("/api/simulador", json={"camera_id": cid, "horas": 1, "epis": [], "zona": None}).get_json()
    assert r["simulado"]["total"] == 0
    assert r["com_regra_atual"]["total"] >= 1  # capacete exigido hoje
    assert r["real"]["total"] == 0  # nenhum alerta real foi criado nem mexido
    assert len(r["simulado"]["linha"]) == len(r["real"]["linha"])
