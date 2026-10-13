"""G5: projeção da imagem da câmera para a planta com pontos conhecidos."""

from __future__ import annotations

import pytest
from app.vision.planta import homografia, pes_na_planta, poligono_na_planta, projetar, validar_pontos

QUAD_CAMERA = [(0.2, 0.5), (0.8, 0.5), (1.0, 1.0), (0.0, 1.0)]  # trapézio do chão em perspectiva
QUAD_PLANTA = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]  # o mesmo chão visto de cima
CAL = {"pontos_camera": QUAD_CAMERA, "pontos_planta": QUAD_PLANTA}


def test_cantos_vao_para_os_cantos():
    m = homografia(QUAD_CAMERA, QUAD_PLANTA)
    for (x, y), (ex, ey) in zip(projetar(m, QUAD_CAMERA), QUAD_PLANTA, strict=True):
        assert x == pytest.approx(ex, abs=1e-5) and y == pytest.approx(ey, abs=1e-5)


def test_centro_da_base_do_trapezio_cai_no_meio_da_borda_de_baixo():
    m = homografia(QUAD_CAMERA, QUAD_PLANTA)
    (x, y), = projetar(m, [(0.5, 1.0)])
    assert x == pytest.approx(0.5, abs=1e-5) and y == pytest.approx(1.0, abs=1e-5)


def test_perspectiva_nao_e_linear():
    # Na imagem, o meio da altura do trapézio NÃO é o meio do chão: o fundo
    # aparece comprimido. Um mapeamento linear daria 0,5.
    m = homografia(QUAD_CAMERA, QUAD_PLANTA)
    (_, y), = projetar(m, [(0.5, 0.75)])
    assert 0.55 < y < 0.8


def test_identidade():
    m = homografia(QUAD_PLANTA, QUAD_PLANTA)
    (x, y), = projetar(m, [(0.3, 0.7)])
    assert (x, y) == pytest.approx((0.3, 0.7), abs=1e-5)


def test_pes_das_pessoas_rastreadas_e_fora_da_calibracao():
    pessoas = [
        {"track_id": 3, "box": {"x1": 400, "y1": 100, "x2": 560, "y2": 540}, "risk_area": {"status": "inside"}},
        {"track_id": 4, "box": {"x1": 400, "y1": 10, "x2": 560, "y2": 100}},  # pé acima do chão calibrado
        {"track_id": None, "box": {"x1": 0, "y1": 0, "x2": 10, "y2": 10}},  # sem rastreio: fora
    ]
    pontos = pes_na_planta(pessoas, (540, 960, 3), CAL)
    assert [p["track_id"] for p in pontos] == [3, 4]
    assert pontos[0]["dentro_da_calibracao"] and pontos[0]["na_zona"]
    assert pontos[0]["y"] == pytest.approx(1.0, abs=1e-3)
    assert not pontos[1]["dentro_da_calibracao"]


def test_zona_de_risco_vai_para_a_planta():
    zona = poligono_na_planta([(0.2, 0.5), (0.8, 0.5), (1.0, 1.0), (0.0, 1.0)], CAL)
    assert zona == [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]


@pytest.mark.parametrize(
    "pontos",
    [[(0, 0), (1, 1), (0.5, 0.5)], [(0, 0), (0.5, 0.5), (1, 1), (0.25, 0.25)], [(0, 0), (2, 0), (1, 1), (0, 1)]],
)
def test_pontos_invalidos(pontos):
    with pytest.raises(ValueError):
        validar_pontos(pontos)


def test_api_calibra_valida_e_apaga(real_monitor_app):
    from app.extensions import db
    from app.models import Camera

    with real_monitor_app.app_context():
        cam = Camera(name="Doca", source_type="USB", source="0")
        db.session.add(cam)
        db.session.commit()
        cid = cam.id
    cliente = real_monitor_app.test_client()
    ruim = cliente.put(f"/api/cameras/{cid}/planta", json={"pontos_camera": [[0, 0], [1, 1], [0.5, 0.5], [0.2, 0.2]],
                                                           "pontos_planta": QUAD_PLANTA})
    assert ruim.status_code == 400
    ok = cliente.put(f"/api/cameras/{cid}/planta", json={"pontos_camera": QUAD_CAMERA, "pontos_planta": QUAD_PLANTA})
    assert ok.status_code == 200
    estado = cliente.get(f"/api/cameras/{cid}/planta").get_json()
    assert estado["calibracao"]["pontos_camera"][0] == [0.2, 0.5]
    assert cliente.put(f"/api/cameras/{cid}/planta", json={"pontos_camera": None}).status_code == 200
    assert cliente.get(f"/api/cameras/{cid}/planta").get_json()["calibracao"] is None
