"""G3 (SOS por gesto), G4 (pessoa imóvel) e G7 (ergonomia) com keypoints sintéticos.

O relógio é passado de fora: nenhum teste dorme.
"""

from __future__ import annotations

from collections.abc import Mapping

import pytest

from app.vision.schemas import PoseLandmark, PoseResult
from app.vision.sinais_por_id import (
    ConfigSinais,
    Persistencia,
    SinaisPorId,
    bracos_erguidos,
    flexao_do_tronco,
)

QUADRO = (1000, 1000, 3)  # 1000x1000: normalizado x1000 = pixels


def _pose(pontos: Mapping[str, tuple[float, float]], *, pid="p1", tid=1, vis=0.9) -> PoseResult:
    return PoseResult(
        landmarks=[PoseLandmark(nome, x / 1000, y / 1000, 0.0, vis) for nome, (x, y) in pontos.items()],
        person_id=pid,
        track_id=tid,
    )


EM_PE = {
    "nose": (500, 200),
    "left_eye": (490, 190),
    "right_eye": (510, 190),
    "left_shoulder": (450, 300),
    "right_shoulder": (550, 300),
    "left_hip": (460, 550),
    "right_hip": (540, 550),
    "left_wrist": (430, 520),
    "right_wrist": (570, 520),
}
BRACOS_ERGUIDOS = {**EM_PE, "left_wrist": (420, 120), "right_wrist": (580, 110)}
UM_BRACO = {**EM_PE, "left_wrist": (420, 120)}
# Ombros 250 px à frente e 250 px acima do quadril: 45°.
CURVADO_45 = {**EM_PE, "left_shoulder": (700, 300), "right_shoulder": (800, 300)}
# Ombros 450 px à frente e 250 px acima: ~61°.
CURVADO_60 = {**EM_PE, "left_shoulder": (900, 300), "right_shoulder": (999, 300)}


def test_bracos_erguidos_exige_os_dois_punhos_acima_da_cabeca():
    assert bracos_erguidos(_pose(BRACOS_ERGUIDOS), QUADRO) is True
    assert bracos_erguidos(_pose(UM_BRACO), QUADRO) is False
    assert bracos_erguidos(_pose(EM_PE), QUADRO) is False


def test_bracos_erguidos_sem_confianca_nao_e_verificavel():
    assert bracos_erguidos(_pose(BRACOS_ERGUIDOS, vis=0.2), QUADRO) is None
    sem_punho = {k: v for k, v in BRACOS_ERGUIDOS.items() if k != "right_wrist"}
    assert bracos_erguidos(_pose(sem_punho), QUADRO) is None


def test_flexao_do_tronco_em_graus():
    assert flexao_do_tronco(_pose(EM_PE), QUADRO) == pytest.approx(0.0, abs=0.01)
    assert flexao_do_tronco(_pose(CURVADO_45), QUADRO) == pytest.approx(45.0, abs=0.5)
    assert flexao_do_tronco(_pose(CURVADO_60), QUADRO) == pytest.approx(60.9, abs=0.5)


def test_persistencia_tolera_buraco_curto_e_zera_com_negativa():
    p = Persistencia(tolerancia_s=1.5)
    assert p.atualizar("a", True, 0.0) == 0.0
    assert p.atualizar("a", None, 1.0) == 1.0  # punho perdido num quadro
    assert p.atualizar("a", True, 2.0) == 2.0
    assert p.atualizar("a", False, 3.0) == 0.0
    p.atualizar("a", True, 4.0)
    assert p.atualizar("a", None, 6.0) == 0.0  # sem evidência por 2 s > tolerância


def _rodar(sinais: SinaisPorId, pose, tempos, ligados, people=None):
    saida = []
    for t in tempos:
        saida = sinais.atualizar([pose], people or [], QUADRO, t, ligados)
    return saida


def test_sos_so_dispara_depois_de_3_segundos_com_id():
    sinais = SinaisPorId()
    assert _rodar(sinais, _pose(BRACOS_ERGUIDOS), [0.0, 1.0, 2.0], {"sos"}) == []
    alertas = _rodar(sinais, _pose(BRACOS_ERGUIDOS), [3.0], {"sos"})
    assert [a["rule"] for a in alertas] == ["sos_gesto"]
    assert alertas[0]["severity"] == "critical"
    assert alertas[0]["metadata"]["person_id"] == "p1"
    assert "Pessoa 1" in alertas[0]["message"]


def test_sos_baixar_os_bracos_zera():
    sinais = SinaisPorId()
    _rodar(sinais, _pose(BRACOS_ERGUIDOS), [0.0, 1.0, 2.0], {"sos"})
    assert _rodar(sinais, _pose(EM_PE), [2.5], {"sos"}) == []
    assert _rodar(sinais, _pose(BRACOS_ERGUIDOS), [3.0, 4.0, 5.0], {"sos"}) == []


def test_sos_desligado_nao_dispara():
    sinais = SinaisPorId()
    assert _rodar(sinais, _pose(BRACOS_ERGUIDOS), [0.0, 5.0, 10.0], set()) == []


def test_sos_e_por_id_e_nao_mistura_pessoas():
    sinais = SinaisPorId()
    a, b = _pose(BRACOS_ERGUIDOS, pid="p1", tid=1), _pose(EM_PE, pid="p2", tid=2)
    for t in (0.0, 1.0, 2.0, 3.0):
        alertas = sinais.atualizar([a, b], [], QUADRO, t, {"sos"})
    assert [x["metadata"]["person_id"] for x in alertas] == ["p1"]


def test_pose_sem_id_nao_gera_sinal():
    sinais = SinaisPorId()
    assert _rodar(sinais, _pose(BRACOS_ERGUIDOS, pid=None, tid=None), [0.0, 5.0], {"sos"}) == []


def test_ergonomia_acumula_tempo_acima_de_45_e_60_e_alerta_com_aviso():
    sinais = SinaisPorId(ConfigSinais(ergonomia_segundos=4.0))
    pose = _pose(CURVADO_60)
    alertas = _rodar(sinais, pose, [0.0, 1.0, 2.0, 3.0, 4.0], {"ergonomia"})
    assert [a["rule"] for a in alertas] == ["ergonomia_tronco"]
    meta = alertas[0]["metadata"]
    assert meta["acumulado_s"] == {"45": 4.0, "60": 4.0}
    assert "estimativa" in alertas[0]["message"].lower()
    assert "RULA" in meta["aviso"] and "NR-17" in meta["aviso"]


def test_ergonomia_a_45_nao_conta_para_60():
    sinais = SinaisPorId(ConfigSinais(ergonomia_segundos=100.0))
    pose = _pose({**EM_PE, "left_shoulder": (720, 300), "right_shoulder": (820, 300)})  # ~47°
    _rodar(sinais, pose, [0.0, 1.0, 2.0], {"ergonomia"})
    est = sinais.ergonomia.estado("p1", 2.0)
    assert est.acumulado.get(45) == pytest.approx(2.0)
    assert est.acumulado.get(60) is None


def _pessoa(x, *, dentro=True, pid="p1", tid=1):
    return {
        "id": pid,
        "track_id": tid,
        "label": f"Pessoa {tid}",
        "box": {"x1": x - 50, "y1": 300, "x2": x + 50, "y2": 700},
        "risk_area": {"status": "inside" if dentro else "outside"},
    }


def test_pessoa_imovel_na_zona_dispara_depois_do_tempo():
    sinais = SinaisPorId(ConfigSinais(imovel_segundos=10.0))
    for t in range(0, 10):
        assert sinais.atualizar([], [_pessoa(500 + (t % 2) * 5)], QUADRO, float(t), {"imobilidade"}) == []
    alertas = sinais.atualizar([], [_pessoa(500)], QUADRO, 10.0, {"imobilidade"})
    assert [a["rule"] for a in alertas] == ["pessoa_imovel"]
    assert "não é diagnóstico" in alertas[0]["message"]


def test_pessoa_que_se_move_ou_esta_fora_da_zona_nao_dispara():
    sinais = SinaisPorId(ConfigSinais(imovel_segundos=5.0))
    for t in range(0, 12):
        # 40 px por análise > 8 % de 400 px (32 px): está andando.
        assert sinais.atualizar([], [_pessoa(300 + t * 40)], QUADRO, float(t), {"imobilidade"}) == []
    sinais = SinaisPorId(ConfigSinais(imovel_segundos=5.0))
    for t in range(0, 12):
        assert sinais.atualizar([], [_pessoa(500, dentro=False)], QUADRO, float(t), {"imobilidade"}) == []


def test_ids_sumidos_sao_esquecidos():
    sinais = SinaisPorId()
    sinais.atualizar([_pose(BRACOS_ERGUIDOS)], [], QUADRO, 0.0, {"sos"})
    assert len(sinais.sos) == 1
    sinais.atualizar([], [], QUADRO, 30.0, {"sos"})
    assert len(sinais.sos) == 0
