"""G9: fila de recortes duvidosos, decisão por teclado e exportação YOLO."""

from __future__ import annotations

import io
import zipfile

import numpy as np
import pytest
from app.services.aprendizado_ativo import FilaDeRotulos
from app.vision.schemas import BoundingBox, Detection

QUADRO = np.full((540, 960, 3), 127, dtype=np.uint8)


def _det(label="helmet", conf=0.4, box=(100, 100, 160, 150)):
    return Detection(label=label, confidence=conf, box=BoundingBox(*box), category="ppe")


def test_so_coleta_epi_na_faixa_de_duvida(tmp_path):
    fila = FilaDeRotulos(tmp_path)
    assert fila.candidato([_det(conf=0.9), _det(conf=0.1), _det(label="person", conf=0.4)]) is None
    assert fila.candidato([_det(conf=0.9), _det(conf=0.38)]).confidence == 0.38


def test_um_recorte_por_camera_por_intervalo_e_limite(tmp_path):
    fila = FilaDeRotulos(tmp_path, limite=2, intervalo_s=5)
    assert fila.talvez_coletar(1, QUADRO, [_det()], agora=0.0)
    assert fila.talvez_coletar(1, QUADRO, [_det()], agora=1.0) is None  # dentro do intervalo
    assert fila.talvez_coletar(2, QUADRO, [_det()], agora=1.0)  # outra câmera
    assert fila.talvez_coletar(1, QUADRO, [_det()], agora=10.0) is None  # fila cheia
    assert fila.contagem()["fila"] == 2


def test_decidir_move_e_exporta_so_confirmados_no_formato_yolo(tmp_path):
    fila = FilaDeRotulos(tmp_path, intervalo_s=0)
    a = fila.talvez_coletar(1, QUADRO, [_det(label="vest")], agora=0.0)
    b = fila.talvez_coletar(1, QUADRO, [_det()], agora=1.0)
    assert fila.proximo()["id"] in (a, b)
    fila.decidir(a, "confirmar")
    fila.decidir(b, "rejeitar")
    assert fila.contagem() == {"fila": 0, "confirmados": 1, "rejeitados": 1}
    with zipfile.ZipFile(io.BytesIO(fila.exportar_zip())) as z:
        nomes = set(z.namelist())
        assert {f"images/train/{a}.jpg", f"labels/train/{a}.txt", "data.yaml", "README.md"} <= nomes
        assert f"images/train/{b}.jpg" not in nomes
        classe, cx, cy, w, h = z.read(f"labels/train/{a}.txt").decode().split()
        assert classe == "1"  # vest é o índice 1 de PPE_KEYS
        assert 0 < float(w) < 1 and 0 < float(h) < 1 and abs(float(cx) - 0.5) < 0.05
        assert "licença" in z.read("README.md").decode().lower()


def test_decisao_invalida_ou_id_estranho(tmp_path):
    fila = FilaDeRotulos(tmp_path)
    with pytest.raises(ValueError):
        fila.decidir("abc", "talvez")
    with pytest.raises(ValueError):
        fila.decidir("../x", "confirmar")
    with pytest.raises(LookupError):
        fila.decidir("naoexiste", "confirmar")
    assert fila.imagem("../../etc") is None


def test_classes_do_rosto_podem_ser_excluidas(tmp_path):
    fila = FilaDeRotulos(tmp_path)
    assert fila.candidato([_det(label="glasses")], excluir=frozenset({"glasses"})) is None
    assert fila.candidato([_det(label="helmet")], excluir=frozenset({"glasses"})).label == "helmet"


def test_recorte_desfoca_so_olhos_e_nariz_e_sem_keypoint_nao_recorta():
    from app.vision.privacidade import regioes_de_olhos_e_nariz

    sem = Detection(label="person", confidence=0.9, box=BoundingBox(100, 100, 200, 400), category="person")
    assert regioes_de_olhos_e_nariz([sem], (540, 960, 3)) is None
    kps = tuple([(150.0, 160.0, 0.9), (145.0, 155.0, 0.9), (155.0, 155.0, 0.9)] + [(0.0, 0.0, 0.0)] * 14)
    com = sem.with_keypoints(kps)
    (x1, y1, x2, y2), = regioes_de_olhos_e_nariz([com], (540, 960, 3))
    # Cobre olhos e nariz, mas não sobe até o topo da caixa (onde fica o capacete).
    assert x1 <= 145 and x2 >= 155 and y1 <= 155 and y2 >= 160
    assert y1 > 120


def test_decidir_depois_de_servir_a_imagem_nao_trava_o_arquivo(real_monitor_app, tmp_path):
    """Regressão (E2E, 13/10): com `send_file`, o handle da imagem ficava aberto e o
    Windows recusava mover o arquivo ao decidir (WinError 32 → HTTP 500)."""
    monitor = real_monitor_app.extensions["monitor_service"]
    fila = FilaDeRotulos(tmp_path, intervalo_s=0)
    monitor.fila_de_rotulos = fila
    ident = fila.talvez_coletar(1, QUADRO, [_det()], agora=0.0)
    cliente = real_monitor_app.test_client()
    resposta = cliente.get(f"/api/rotulos/{ident}.jpg")  # não consumida nem fechada
    assert resposta.status_code == 200
    assert cliente.post(f"/api/rotulos/{ident}", json={"decisao": "confirmar"}).status_code == 200
    assert fila.contagem()["confirmados"] == 1
