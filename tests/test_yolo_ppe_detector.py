from __future__ import annotations

from app.vision.yolo_ppe_detector import PPE_CORE_CLASSES, PPE_OPTIONAL_CLASSES, YoloPPEDetector

# Modelo padrão: Hexmon/vyra-yolo-ppe-detection (14 classes).
VYRA_MODEL = {
    0: "Fall-Detected",
    1: "Gloves",
    2: "Goggles",
    3: "Hardhat",
    4: "Ladder",
    5: "Mask",
    6: "NO-Gloves",
    7: "NO-Goggles",
    8: "NO-Hardhat",
    9: "NO-Mask",
    10: "NO-Safety Vest",
    11: "Person",
    12: "Safety Cone",
    13: "Safety Vest",
}
TODAS_AS_CLASSES = set(PPE_CORE_CLASSES) | set(PPE_OPTIONAL_CLASSES)


def _diagnostics_for(names: dict[int, str], *, require_person: bool) -> dict:
    detector = YoloPPEDetector(model_path="dummy.pt", require_person=require_person)
    return detector._build_diagnostics(names=names, error=None)


def test_vyra_traz_epi_e_pessoa_no_mesmo_peso():
    """É isso que permite rodar com MULTI_PERSON_DETECTION=false."""
    diagnostics = _diagnostics_for(VYRA_MODEL, require_person=True)

    suportadas = diagnostics["supported_ppe"]
    assert all(suportadas[key] for key in PPE_CORE_CLASSES)
    assert suportadas["glasses"] is True
    assert suportadas["mask"] is True
    # O Vyra não tem classe de calçado — fica "unsupported", não quebra nada.
    assert suportadas["safety_shoe"] is False
    assert diagnostics["person_supported"] is True
    assert diagnostics["ppe_ready"] is True
    assert diagnostics["warning"] is None


def test_modelo_so_com_o_nucleo_continua_pronto():
    """As classes opcionais não podem derrubar a prontidão: um peso de 3 classes
    já em uso não vira "modelo parcial" só porque classes novas existem."""
    diagnostics = _diagnostics_for({0: "helmet", 1: "vest", 2: "gloves"}, require_person=False)

    assert all(diagnostics["supported_ppe"][key] for key in PPE_CORE_CLASSES)
    assert not any(diagnostics["supported_ppe"][key] for key in PPE_OPTIONAL_CLASSES)
    assert diagnostics["ppe_ready"] is True
    assert diagnostics["warning"] is None


def test_ppe_only_model_is_ready_without_person_when_require_person_false():
    # epi_pretrained.pt: 6 classes de EPI, sem "person" e sem protetor auricular.
    names = {0: "Gloves", 1: "Vest", 2: "goggles", 3: "helmet", 4: "mask", 5: "safety_shoe"}
    diagnostics = _diagnostics_for(names, require_person=False)

    suportadas = diagnostics["supported_ppe"]
    assert all(suportadas[key] for key in TODAS_AS_CLASSES - {"ear_protection"})
    assert suportadas["ear_protection"] is False  # este peso não tem a classe
    assert diagnostics["person_supported"] is False
    assert diagnostics["ppe_ready"] is True  # não deve travar por falta de "person"
    assert diagnostics["warning"] is None


def test_same_model_without_person_warns_when_require_person_true():
    names = {0: "Gloves", 1: "Vest", 2: "helmet"}
    diagnostics = _diagnostics_for(names, require_person=True)

    assert diagnostics["ppe_ready"] is False
    assert "pessoa" in diagnostics["warning"]


def test_coco_person_model_reports_person_supported():
    # yolov8n.pt (COCO): classe 0 = person, sem nenhuma classe de EPI.
    diagnostics = _diagnostics_for({0: "person", 1: "bicycle"}, require_person=True)

    assert diagnostics["person_supported"] is True
    assert not any(diagnostics["supported_ppe"].values())


def test_normalize_label_maps_new_model_raw_names():
    assert YoloPPEDetector.normalize_label("Gloves") == "gloves"
    assert YoloPPEDetector.normalize_label("Vest") == "vest"
    assert YoloPPEDetector.normalize_label("helmet") == "helmet"
    # Nomes crus do Vyra.
    assert YoloPPEDetector.normalize_label("Hardhat") == "helmet"
    assert YoloPPEDetector.normalize_label("Safety Vest") == "vest"
    assert YoloPPEDetector.normalize_label("Goggles") == "glasses"
    assert YoloPPEDetector.normalize_label("Mask") == "mask"
    assert YoloPPEDetector.normalize_label("Safety Cone") == "safety_cone"
    assert YoloPPEDetector.normalize_label("Person") == "person"
    # Sinônimos de outros datasets de EPI.
    assert YoloPPEDetector.normalize_label("Safety Goggles") == "glasses"
    assert YoloPPEDetector.normalize_label("face mask") == "mask"
    assert YoloPPEDetector.normalize_label("safety boots") == "safety_shoe"


class _FormaParcial:
    def __init__(self, dinamica: bool) -> None:
        self.is_dynamic = dinamica


class _EntradaOV:
    def __init__(self, dinamica: bool) -> None:
        self._dinamica = dinamica

    def get_partial_shape(self):
        return _FormaParcial(self._dinamica)


class _CompiladoOV:
    def __init__(self, dinamica: bool) -> None:
        self._dinamica = dinamica

    def input(self, indice):  # noqa: ARG002
        return _EntradaOV(self._dinamica)


class _YoloOpenVinoFalso:
    """Imita o `YOLO` do ultralytics 8.3.40 com backend OpenVINO.

    Guarda, a cada predict, se o AutoBackend estava marcado como dinâmico —
    é esse atributo que decide entre letterbox quadrado e retangular no
    predictor (`auto=... getattr(self.model, "dynamic", False)`).
    """

    def __init__(self, dinamica: bool) -> None:
        self.predictor = type("P", (), {})()
        self.predictor.model = type("B", (), {"dynamic": False, "ov_compiled_model": _CompiladoOV(dinamica)})()
        self.dinamico_em_cada_chamada: list[bool] = []

    def predict(self, **kwargs):  # noqa: ARG002
        self.dinamico_em_cada_chamada.append(self.predictor.model.dynamic)
        return []


def _detector_openvino(tmp_path, dinamica: bool):
    pasta = tmp_path / "vyra_ppe_640_dyn_openvino_model"
    pasta.mkdir()
    detector = YoloPPEDetector(model_path=str(pasta))
    falso = _YoloOpenVinoFalso(dinamica)
    detector.__dict__["model"] = falso  # cached_property: injeta sem carregar peso
    return detector, falso


def test_openvino_com_entrada_dinamica_usa_letterbox_retangular_e_refaz_a_primeira_chamada(tmp_path):
    """Medido: sem isto o export dinâmico dava a MESMA concordância do estático (95,04 %)."""
    import numpy as np

    detector, falso = _detector_openvino(tmp_path, dinamica=True)
    quadro = np.zeros((540, 960, 3), dtype=np.uint8)

    detector.detect(quadro)
    detector.detect(quadro)

    # 1ª chamada saiu quadrada e foi refeita já retangular; daí em diante, retangular.
    assert falso.dinamico_em_cada_chamada == [False, True, True]
    assert falso.predictor.model.dynamic is True


def test_openvino_estatico_continua_quadrado_e_nao_refaz(tmp_path):
    import numpy as np

    detector, falso = _detector_openvino(tmp_path, dinamica=False)
    quadro = np.zeros((540, 960, 3), dtype=np.uint8)

    detector.detect(quadro)
    detector.detect(quadro)

    assert falso.dinamico_em_cada_chamada == [False, False]
