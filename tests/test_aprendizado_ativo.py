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
