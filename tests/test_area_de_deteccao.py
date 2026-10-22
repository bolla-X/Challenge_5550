"""Área de detecção por câmera (MISSÃO 7): recorte, volta ao quadro, filtro pelos pés, API e evidência.

Nada aqui carrega peso de modelo: os detectores são dublês que registram o que receberam e devolvem caixas nas
coordenadas do recorte, como o ultralytics devolve (`Boxes.xyxy` no tamanho da imagem de entrada).
"""

from __future__ import annotations

import threading
from pathlib import Path

import numpy as np
import pytest
from app import create_app
from app.config import TestConfig
from app.models import Camera
from app.services.agendador_de_inferencia import AgendadorDeInferencia
from app.services.camera_worker import CameraWorker
from app.services.feature_manager import FeatureManager
from app.vision.area_de_deteccao import (
    SEM_AREA,
    AreaDeDeteccao,
    deslocar,
    do_banco,
    fora_da_area,
    ponto_no_poligono,
    validar_poligono,
)
from app.vision.schemas import BoundingBox, Detection, PoseLandmark, PoseResult

RAIZ = Path(__file__).resolve().parent.parent

# Retângulo à esquerda: x 0,1–0,4; y 0,2–0,9. Num quadro 960×540, o recorte (5 % de margem nos lados e
# embaixo, 30 % em cima) é x 48–432, y 0–513.
RETANGULO = [(0.1, 0.2), (0.4, 0.2), (0.4, 0.9), (0.1, 0.9)]
# "U": o entalhe do meio (x 0,4–0,6, y 0,4–0,9) fica FORA.
U = [(0.1, 0.1), (0.9, 0.1), (0.9, 0.9), (0.6, 0.9), (0.6, 0.4), (0.4, 0.4), (0.4, 0.9), (0.1, 0.9)]
QUADRO = np.zeros((540, 960, 3), dtype=np.uint8)


def caixa(x1, y1, x2, y2, rotulo="person", categoria="person", **kw) -> Detection:
    return Detection(label=rotulo, confidence=0.9, box=BoundingBox(x1, y1, x2, y2), category=categoria, **kw)


def capacete(x1, y1, x2, y2) -> Detection:
    return caixa(x1, y1, x2, y2, rotulo="helmet", categoria="ppe")


# ------------------------------------------------------------------ validação --
def test_poligono_valido_vira_pontos_normalizados():
    assert validar_poligono([{"x": 0.1, "y": 0.2}, [0.4, 0.2], {"x": 0.4, "y": 0.9}]) == [(0.1, 0.2), (0.4, 0.2), (0.4, 0.9)]


@pytest.mark.parametrize("raw, trecho", [
    (None, "pelo menos 3"),
    ([{"x": 0.1, "y": 0.1}, {"x": 0.5, "y": 0.5}], "pelo menos 3"),
    ([{"x": 1.2, "y": 0.1}, {"x": 0.5, "y": 0.5}, {"x": 0.1, "y": 0.9}], "dentro do quadro"),
    ([{"x": -0.01, "y": 0.1}, {"x": 0.5, "y": 0.5}, {"x": 0.1, "y": 0.9}], "dentro do quadro"),
    ([{"x": "a", "y": 0.1}, {"x": 0.5, "y": 0.5}, {"x": 0.1, "y": 0.9}], "numéricos"),
    ([{"x": float("nan"), "y": 0.1}, {"x": 0.5, "y": 0.5}, {"x": 0.1, "y": 0.9}], "numéricos"),
    ([{"x": True, "y": 0.1}, {"x": 0.5, "y": 0.5}, {"x": 0.1, "y": 0.9}], "numéricos"),
    ([{"x": "0.5", "y": 0.1}, {"x": 0.5, "y": 0.5}, {"x": 0.1, "y": 0.9}], "numéricos"),
    ([{"x": 10 ** 400, "y": 0.1}, {"x": 0.5, "y": 0.5}, {"x": 0.1, "y": 0.9}], "numéricos"),
    ([{"x": 0.1, "y": 0.1}, {"x": 0.1, "y": 0.1}, {"x": 0.5, "y": 0.9}], "repetidos"),
    # gravata-borboleta: as arestas 0–1 e 2–3 se cruzam
    ([[0.1, 0.1], [0.9, 0.9], [0.9, 0.1], [0.1, 0.9]], "cruzar"),
    # colinear: área zero
    ([[0.1, 0.1], [0.5, 0.5], [0.9, 0.9]], "pequena demais"),
    ([[0.1, 0.1], [0.15, 0.1], [0.15, 0.15]], "pequena demais"),
    ([[0.5 + 0.4 * np.cos(i / 65 * 6.28), 0.5 + 0.4 * np.sin(i / 65 * 6.28)] for i in range(65)], "no máximo 64"),
])
def test_poligono_invalido_e_recusado_com_motivo(raw, trecho):
    with pytest.raises(ValueError, match=trecho):
        validar_poligono(raw)


def test_valor_invalido_no_banco_vira_quadro_inteiro_sem_derrubar():
    assert do_banco(None) is SEM_AREA
    assert do_banco([[0.1, 0.1]]) is SEM_AREA
    assert do_banco([[0.1, 0.2], [0.4, 0.2], [0.4, 0.9]]).ativa


# ------------------------------------------------------------ recorte e mapeamento --
def test_retangulo_envolvente_com_margem_e_dentro_do_quadro():
    """5 % nos lados e embaixo; 30 % em cima, onde fica o corpo de quem tem os pés perto da borda de cima."""
    assert AreaDeDeteccao(RETANGULO).retangulo(960, 540) == (48, 0, 432, 513)
    assert AreaDeDeteccao([(0.1, 0.5), (0.4, 0.5), (0.4, 0.9), (0.1, 0.9)]).retangulo(960, 540) == (48, 108, 432, 513)
    # encostada na borda: a margem não sai do quadro
    assert AreaDeDeteccao([(0.0, 0.0), (0.5, 0.0), (0.5, 1.0), (0.0, 1.0)]).retangulo(960, 540) == (0, 0, 528, 540)


def test_recorte_e_uma_vista_do_quadro_com_o_deslocamento():
    entrada, deslocamento = AreaDeDeteccao(RETANGULO).recortar(QUADRO)
    assert entrada.shape == (513, 384, 3) and deslocamento == (48, 0)
    assert np.shares_memory(entrada, QUADRO)


def test_deslocar_leva_caixa_e_esqueleto_ao_quadro_inteiro():
    det = caixa(10, 20, 30, 40, keypoints=((15.0, 25.0, 0.9), (20.0, 38.0, 0.8)))
    movida = deslocar(det, 48, 81)
    assert movida.box == BoundingBox(58, 101, 78, 121)
    assert movida.keypoints == ((63.0, 106.0, 0.9), (68.0, 119.0, 0.8))


def test_ponto_nao_visto_continua_nao_visto_depois_de_deslocar():
    """(0, 0) é o "não visto" do ultralytics: deslocá-lo virava junta falsa no canto do recorte (e "Pessoa caída")."""
    from app.vision.yolo_pose_detector import pose_da_deteccao

    pontos = tuple([(150.0, 300.0, 0.9)] + [(0.0, 0.0, 0.45)] * 16)
    det = caixa(100, 100, 200, 380, keypoints=pontos)
    movida = deslocar(det, 100, 60)
    assert movida.keypoints[0] == (250.0, 360.0, 0.9)
    assert all(k == (0.0, 0.0, 0.45) for k in movida.keypoints[1:])
    antes = pose_da_deteccao(det, (540, 960, 3), person_id="person_1")
    depois = pose_da_deteccao(movida, (540, 960, 3), person_id="person_1")
    assert len(depois.landmarks) == len(antes.landmarks) == 1


def test_mapeamento_recorte_quadro_com_o_letterbox_do_ultralytics():
    """A cadeia inteira: caixa no espaço do modelo (recorte com letterbox) → recorte → quadro.

    O desfazer do letterbox é a função do próprio ultralytics (`ops.scale_boxes`, a que o predictor usa); o
    que este módulo soma depois é só o canto do recorte. Vale para o letterbox quadrado e o retangular.
    """
    import torch
    from ultralytics.data.augment import LetterBox
    from ultralytics.utils import ops

    area = AreaDeDeteccao(RETANGULO)
    entrada, (dx, dy) = area.recortar(QUADRO)
    original = (150.0, 200.0, 260.0, 470.0)  # caixa da pessoa no QUADRO inteiro
    for auto in (False, True):  # quadrado (lote de formas diferentes) e retangular (dinâmico)
        no_modelo = LetterBox((640, 640), auto=auto, stride=32)(image=entrada)
        alt_m, larg_m = no_modelo.shape[:2]
        ganho = min(alt_m / entrada.shape[0], larg_m / entrada.shape[1])
        pad_x = round((larg_m - entrada.shape[1] * ganho) / 2 - 0.1)
        pad_y = round((alt_m - entrada.shape[0] * ganho) / 2 - 0.1)
        x1, y1, x2, y2 = original
        modelo = torch.tensor([[(x1 - dx) * ganho + pad_x, (y1 - dy) * ganho + pad_y,
                                (x2 - dx) * ganho + pad_x, (y2 - dy) * ganho + pad_y]])
        no_recorte = ops.scale_boxes((alt_m, larg_m), modelo, entrada.shape).round().int().tolist()[0]
        det = deslocar(caixa(*no_recorte), dx, dy)
        assert abs(det.box.x1 - x1) <= 1 and abs(det.box.y1 - y1) <= 1, (auto, det.box)
        assert abs(det.box.x2 - x2) <= 1 and abs(det.box.y2 - y2) <= 1, (auto, det.box)


# --------------------------------------------------------------- ponto dos pés --
@pytest.mark.parametrize("x, y, dentro", [(0.2, 0.5, True), (0.5, 0.5, False), (0.05, 0.5, False), (0.39, 0.89, True)])
def test_pes_em_poligono_convexo(x, y, dentro):
    assert ponto_no_poligono(x, y, RETANGULO) is dentro


@pytest.mark.parametrize("x, y, dentro", [
    (0.5, 0.8, False),   # no entalhe do U
    (0.5, 0.2, True),    # na barra de cima
    (0.2, 0.8, True),    # na perna esquerda
    (0.8, 0.8, True),    # na perna direita
    (0.95, 0.5, False),  # fora de tudo
])
def test_pes_em_poligono_concavo(x, y, dentro):
    assert ponto_no_poligono(x, y, U) is dentro


def test_pessoa_cruzando_a_borda_vale_pelo_pe():
    """Cabeça fora e pés dentro: fica. Cabeça dentro e pés fora: sai. EPI acompanha a pessoa, não o polígono."""
    area = AreaDeDeteccao(RETANGULO)  # em px: x 96–384, y 108–486
    pes_dentro = caixa(150, 40, 250, 300)    # topo acima da área (y 40 < 108), pés (200, 300) dentro
    pes_fora = caixa(300, 300, 420, 520)     # corpo começa dentro, pés (360, 520) abaixo da área
    capacete_do_que_fica = capacete(170, 40, 230, 80)   # inteiro FORA do polígono, mas na cabeça de quem fica
    capacete_do_que_sai = capacete(330, 300, 390, 340)  # dentro do polígono, mas de quem sai
    deteccoes, pessoas, _ = area.filtrar([capacete_do_que_fica, capacete_do_que_sai], [pes_dentro, pes_fora], None,
                                         960, 540, sobreposicao_min=0.35)
    assert pessoas == [pes_dentro]
    assert deteccoes == [capacete_do_que_fica]


def test_epi_solto_sem_pessoa_mantida_sai():
    area = AreaDeDeteccao(RETANGULO)
    deteccoes, pessoas, _ = area.filtrar([capacete(150, 200, 200, 240)], [], None, 960, 540, sobreposicao_min=0.35)
    assert deteccoes == [] and pessoas == []


def test_queda_e_pessoa_do_modelo_de_epi_valem_pelo_pe():
    area = AreaDeDeteccao(RETANGULO)
    queda_dentro = caixa(150, 300, 300, 400, rotulo="fall_detected", categoria="fall_detected")
    queda_fora = caixa(500, 300, 700, 400, rotulo="fall_detected", categoria="fall_detected")
    pessoa_epi_fora = caixa(600, 100, 700, 500)
    deteccoes, _, _ = area.filtrar([queda_dentro, queda_fora, pessoa_epi_fora], [], None, 960, 540, 0.35)
    assert deteccoes == [queda_dentro]


def test_pose_global_vale_pelos_tornozelos():
    area = AreaDeDeteccao(RETANGULO)

    def pose(x, y):
        return PoseResult(landmarks=[PoseLandmark("nose", x, 0.1, 0, 1), PoseLandmark("left_ankle", x, y, 0, 0.9),
                                     PoseLandmark("right_ankle", x, y, 0, 0.9)])

    assert area.mantem_pose(pose(0.2, 0.8)) and not area.mantem_pose(pose(0.6, 0.8))


# ----------------------------------------------------------------- worker --
class DetectorQueAnota:
    """Registra o quadro recebido e devolve caixas nas coordenadas DELE (como o ultralytics)."""

    def __init__(self, deteccoes: list[Detection]) -> None:
        self.recebidos: list[np.ndarray] = []
        self._deteccoes = deteccoes

    def detect(self, frame):
        self.recebidos.append(frame)
        return list(self._deteccoes)

    def detect_lote(self, frames):
        return [self.detect(f) for f in frames]

    def diagnostics(self):
        return {"model_path": "duble.pt", "classes": {}, "error": None}

    def supported_ppe_classes(self):
        return {"helmet", "vest"}


class SocketNulo:
    def emit(self, *args, **kwargs):  # noqa: ARG002
        pass


class PoseNula:
    def estimate(self, frame):  # noqa: ARG002
        return PoseResult(landmarks=[])

    def estimate_for_people(self, frame, people, *, max_people=4):  # noqa: ARG002
        return []


# Nas coordenadas do RECORTE do RETANGULO (deslocamento 48, 0):
PESSOA_A = caixa(100, 100, 200, 380)   # no quadro: 148,100–248,380 → pés (198, 380) = (0,21; 0,70) dentro
PESSOA_B = caixa(300, 50, 383, 150)    # no quadro: 348,50–431,150 → pés (389,5; 150) = (0,41; 0,28) fora
CAPACETE_A = capacete(120, 100, 180, 140)
CAPACETE_B = capacete(320, 50, 360, 80)


@pytest.fixture()
def app_teste():
    class Cfg(TestConfig):
        MULTI_PERSON_DETECTION = True
        POSE_PER_PERSON = True

    app = create_app(Cfg)
    with app.app_context():
        yield app


def _worker(app, area=None) -> CameraWorker:
    return CameraWorker(
        app, socketio=SocketNulo(), feature_manager=FeatureManager.from_config(app.config), camera_id=1,
        source="fonte-inexistente-nunca-aberta", fps=12, area_deteccao=area,
        detector=DetectorQueAnota([CAPACETE_A, CAPACETE_B]), person_detector=DetectorQueAnota([PESSOA_A, PESSOA_B]),
        pose_estimator=PoseNula(), inference_lock=threading.Lock(),
    )


def test_sem_area_o_modelo_ve_o_quadro_inteiro_e_o_resultado_e_o_de_hoje(app_teste):
    """Câmera sem área configurada: o MESMO quadro vai ao modelo e as MESMAS detecções voltam (identidade)."""
    worker = _worker(app_teste)
    ppe, pessoas, esqueletos = worker._detectar(QUADRO, lambda _etapa: None)
    assert worker.detector.recebidos[0] is QUADRO and worker.person_detector.recebidos[0] is QUADRO
    assert ppe == [CAPACETE_A, CAPACETE_B] and pessoas == [PESSOA_A, PESSOA_B] and esqueletos is None
    assert not worker.area_deteccao.ativa
    assert worker._produzir_overlay() is None or worker._produzir_overlay()["area"] == []


def test_com_area_o_modelo_ve_so_o_recorte_e_so_o_mantido_segue(app_teste):
    worker = _worker(app_teste, area=[list(p) for p in RETANGULO])
    ppe, pessoas, _ = worker._detectar(QUADRO, lambda _etapa: None)
    assert worker.detector.recebidos[0].shape == (513, 384, 3)
    assert worker.person_detector.recebidos[0].shape == (513, 384, 3)
    assert [p.box for p in pessoas] == [BoundingBox(148, 100, 248, 380)]
    assert [d.box for d in ppe] == [BoundingBox(168, 100, 228, 140)]
    # E daí para o tracker: a análise só tem a pessoa A (com ID) e o capacete dela.
    analise = worker._inferir(QUADRO, lambda _etapa: None)
    pessoas_na_analise = [d for d in analise.detections if d.category == "person"]
    assert len(pessoas_na_analise) == 1 and pessoas_na_analise[0].box == BoundingBox(148, 100, 248, 380)
    assert [d.label for d in analise.detections if d.category != "person"] == ["helmet"]


def test_trocar_a_area_vale_na_proxima_inferencia_e_remover_volta_ao_quadro_inteiro(app_teste):
    worker = _worker(app_teste)
    worker.definir_area_deteccao(AreaDeDeteccao(RETANGULO))
    worker._detectar(QUADRO, lambda _etapa: None)
    assert worker.detector.recebidos[-1].shape == (513, 384, 3)
    estado = worker.definir_area_deteccao(SEM_AREA)
    assert estado["ativa"] is False and estado["polygon"] == []
    worker._detectar(QUADRO, lambda _etapa: None)
    assert worker.detector.recebidos[-1] is QUADRO


def test_lote_recorta_e_devolve_por_camera():
    """No lote, as câmeras SEM área vão juntas, como antes; cada recorte vai na sua chamada e volta ao seu quadro.

    Misturar formas no mesmo lote troca o letterbox retangular pelo quadrado e mudaria o resultado de quem não
    tem área (achado da auditoria, M3).
    """
    chamado: list[list[tuple]] = []
    entregues: dict[int, tuple] = {}

    def detectar_lote(frames):
        chamado.append([f.shape for f in frames])
        return [([], [caixa(100, 100, 200, 380)], None) for _ in frames]

    ag = AgendadorDeInferencia(lote=True)
    ag._garantir_thread = lambda: None
    com_area, sem_area = AreaDeDeteccao(RETANGULO), SEM_AREA
    for cid, area in ((1, com_area), (2, sem_area)):
        ag.registrar(cid, analisar=None, entregar=lambda r, ts, cid=cid: entregues.__setitem__(cid, r),
                     detectar_lote=detectar_lote, pos_lote=lambda frame, bruto, cron: bruto,
                     recortar=lambda f, area=area: area.para_lote(f, 0.35))
    ag.registrar(3, analisar=None, entregar=lambda r, ts: entregues.__setitem__(3, r),
                 detectar_lote=detectar_lote, pos_lote=lambda frame, bruto, cron: bruto)
    ag._servir_lote([(ag._slots[1], QUADRO, 0.0), (ag._slots[2], QUADRO, 0.0), (ag._slots[3], QUADRO, 0.0)])
    assert chamado == [[(540, 960, 3), (540, 960, 3)], [(513, 384, 3)]]
    assert entregues[1][1][0].box == BoundingBox(148, 100, 248, 380)   # câmera 1: deslocada e mantida
    assert entregues[2][1][0].box == BoundingBox(100, 100, 200, 380)   # câmera 2: como veio


def test_saude_visual_continua_olhando_o_quadro_inteiro(app_teste):
    worker = _worker(app_teste, area=[list(p) for p in RETANGULO])
    if worker.saude_visual is None:
        pytest.skip("saúde visual desligada nesta configuração")
    vistos = []
    worker.saude_visual.observar = lambda frame, agora: vistos.append(frame.shape)
    worker._observar_saude_visual(QUADRO, 0.0)
    assert vistos == [(540, 960, 3)]


# ---------------------------------------------------------- imagem e evidência --
def test_fora_da_area_escurece_e_na_evidencia_tambem_desfoca():
    xadrez = (np.indices((540, 960)).sum(axis=0) % 2 * 200).astype(np.uint8)
    quadro = np.dstack([xadrez] * 3)
    area = AreaDeDeteccao(RETANGULO)
    escuro = area.aplicar(quadro, desfocar=False)
    evidencia = area.aplicar(quadro, desfocar=True)
    dentro, fora = (300, 200), (300, 700)  # (linha, coluna)
    assert (escuro[dentro] == quadro[dentro]).all() and (evidencia[dentro] == quadro[dentro]).all()
    assert escuro[fora][0] <= round(quadro[fora][0] * 0.35) + 1
    # desfocado: o xadrez de 1 px vira um cinza quase uniforme
    assert evidencia[250:350, 650:750].std() < 5 < escuro[250:350, 650:750].std()
    assert SEM_AREA.aplicar(quadro, desfocar=True) is quadro


def test_pessoa_mantida_fica_nitida_inteira_mesmo_com_a_cabeca_fora_do_poligono():
    """A evidência de uma violação não pode sair borrada justamente na cabeça (achado A2 da auditoria)."""
    xadrez = (np.indices((540, 960)).sum(axis=0) % 2 * 200).astype(np.uint8)
    quadro = np.dstack([xadrez] * 3)
    area = AreaDeDeteccao([(0.1, 0.5), (0.4, 0.5), (0.4, 0.9), (0.1, 0.9)])  # em px: y 270–486
    pessoa = BoundingBox(150, 120, 250, 400)  # pés dentro, cabeça (y 120–270) acima do polígono
    evidencia = area.aplicar(quadro, desfocar=True, caixas=[pessoa])
    assert (evidencia[130:260, 160:240] == quadro[130:260, 160:240]).all()
    assert evidencia[130:260, 600:700].std() < 5  # fora da área e de qualquer pessoa: borrado


def test_aviso_de_risco_fora_da_area():
    area = AreaDeDeteccao(RETANGULO)
    assert not fora_da_area([(0.15, 0.3), (0.35, 0.3), (0.35, 0.8)], area)
    assert fora_da_area([(0.15, 0.3), (0.6, 0.3), (0.35, 0.8)], area)           # parcialmente
    assert fora_da_area([(0.6, 0.3), (0.9, 0.3), (0.8, 0.8)], area)             # totalmente
    assert not fora_da_area([(0.6, 0.3), (0.9, 0.3), (0.8, 0.8)], SEM_AREA)     # sem área: tudo é vigiado


# -------------------------------------------------------------------- API --
def _criar(client, nome="A"):
    r = client.post("/api/cameras", json={"name": nome, "source_type": "USB", "source": "0"})
    assert r.status_code == 201, r.get_json()
    return r.get_json()["id"]


AREA_API = [{"x": 0.1, "y": 0.2}, {"x": 0.4, "y": 0.2}, {"x": 0.4, "y": 0.9}, {"x": 0.1, "y": 0.9}]


def test_api_le_salva_e_remove(real_monitor_app, real_monitor_client):
    cid = _criar(real_monitor_client)
    url = f"/api/cameras/{cid}/area-deteccao"
    assert real_monitor_client.get(url).get_json()["area_deteccao"] | {"camera_id": None} == {
        "camera_id": None, "ativa": False, "polygon": [], "risco_fora": False}
    r = real_monitor_client.put(url, json={"polygon": AREA_API})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["area_deteccao"]["ativa"] is True
    assert real_monitor_client.get(url).get_json()["area_deteccao"]["polygon"] == AREA_API
    from app.extensions import db

    assert db.session.get(Camera, cid).area_deteccao == [[0.1, 0.2], [0.4, 0.2], [0.4, 0.9], [0.1, 0.9]]
    r = real_monitor_client.delete(url)
    assert r.status_code == 200 and r.get_json()["area_deteccao"]["ativa"] is False
    db.session.expire_all()
    assert db.session.get(Camera, cid).area_deteccao is None


@pytest.mark.parametrize("corpo", [
    {}, {"polygon": None}, {"polygon": AREA_API[:2]},
    {"polygon": [{"x": 1.5, "y": 0.2}, {"x": 0.4, "y": 0.2}, {"x": 0.4, "y": 0.9}]},
    {"polygon": [{"x": 0.1, "y": 0.1}, {"x": 0.9, "y": 0.9}, {"x": 0.9, "y": 0.1}, {"x": 0.1, "y": 0.9}]},
])
def test_api_recusa_area_invalida_sem_mexer_na_salva(real_monitor_client, corpo):
    cid = _criar(real_monitor_client)
    url = f"/api/cameras/{cid}/area-deteccao"
    real_monitor_client.put(url, json={"polygon": AREA_API})
    r = real_monitor_client.put(url, json=corpo)
    assert r.status_code == 400 and r.get_json()["error"]
    assert real_monitor_client.get(url).get_json()["area_deteccao"]["polygon"] == AREA_API


def test_api_camera_inexistente_e_404(real_monitor_client):
    assert real_monitor_client.get("/api/cameras/999/area-deteccao").status_code == 404
    assert real_monitor_client.put("/api/cameras/999/area-deteccao", json={"polygon": AREA_API}).status_code == 404
    assert real_monitor_client.delete("/api/cameras/999/area-deteccao").status_code == 404


def test_area_sobrevive_a_reconstruir_o_worker(real_monitor_app, real_monitor_client):
    """Reinício (ou o CRUD reconstruir o worker) reaplica a área salva no banco."""
    cid = _criar(real_monitor_client)
    real_monitor_client.put(f"/api/cameras/{cid}/area-deteccao", json={"polygon": AREA_API})
    from app.extensions import db

    monitor = real_monitor_app.extensions["monitor_service"]
    novo = monitor._build_worker(db.session.get(Camera, cid), is_default=False)
    assert novo.area_deteccao.para_api() == AREA_API
    assert novo.annotator.area_deteccao == [(0.1, 0.2), (0.4, 0.2), (0.4, 0.9), (0.1, 0.9)]


def test_troca_de_area_e_auditada_com_o_usuario(real_monitor_app, real_monitor_client):
    """A área decide o que a câmera deixa de ver: a troca vai para a linha do tempo (e a custódia)."""
    from app.models import EventLog

    cid = _criar(real_monitor_client)
    real_monitor_client.put(f"/api/cameras/{cid}/area-deteccao", json={"polygon": AREA_API})
    real_monitor_client.delete(f"/api/cameras/{cid}/area-deteccao")
    eventos = EventLog.query.filter_by(camera_id=cid, event_type="area_deteccao_atualizada").order_by(EventLog.id).all()
    assert [e.message.split(" por ")[0] for e in eventos] == [
        "Área de detecção atualizada", "Área de detecção removida: quadro inteiro"]
    meta = eventos[0].to_dict()["metadata"]
    assert meta["anterior"] is None and meta["nova"] == [[0.1, 0.2], [0.4, 0.2], [0.4, 0.9], [0.1, 0.9]]


def test_trocar_a_area_esvazia_o_buffer_do_replay(app_teste):
    """Quadros mascarados com a área anterior não entram no clipe de um alerta que nasça logo depois."""
    worker = _worker(app_teste)
    if worker.replay is None:
        pytest.skip("replay desligado nesta configuração")
    worker.replay.gravar(QUADRO, 1000.0, None)
    assert worker.replay.entre(0, 2000)
    worker.definir_area_deteccao(AreaDeDeteccao(RETANGULO))
    assert worker.replay.entre(0, 2000) == []


def test_api_avisa_risco_fora_da_area(real_monitor_client):
    cid = _criar(real_monitor_client)
    real_monitor_client.put(f"/api/cameras/{cid}/risk-area",
                            json={"polygon": [{"x": 0.15, "y": 0.3}, {"x": 0.8, "y": 0.3}, {"x": 0.35, "y": 0.8}]})
    r = real_monitor_client.put(f"/api/cameras/{cid}/area-deteccao", json={"polygon": AREA_API})
    assert r.get_json()["area_deteccao"]["risco_fora"] is True


def test_migracao_cria_a_coluna_nula(tmp_path):
    """Banco existente migrado: a coluna nasce nula = quadro inteiro (comportamento de antes)."""
    from flask_migrate import upgrade
    from sqlalchemy import create_engine, inspect

    banco = tmp_path / "migrado.db"

    class Cfg(TestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{banco.as_posix()}"
        AUTO_CREATE_TABLES = False

    app = create_app(Cfg)
    with app.app_context():
        upgrade(directory=str(RAIZ / "migrations"))
    motor = create_engine(f"sqlite:///{banco.as_posix()}")
    colunas = {c["name"]: c for c in inspect(motor).get_columns("cameras")}
    motor.dispose()
    assert colunas["area_deteccao"]["nullable"] is True
