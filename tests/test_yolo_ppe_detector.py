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
    # epi_pretrained.pt: 6 classes de EPI, sem "person".
    names = {0: "Gloves", 1: "Vest", 2: "goggles", 3: "helmet", 4: "mask", 5: "safety_shoe"}
    diagnostics = _diagnostics_for(names, require_person=False)

    assert diagnostics["supported_ppe"] == {key: True for key in TODAS_AS_CLASSES}
    assert diagnostics["person_supported"] is False
    assert diagnostics["ppe_ready"] is True  # não deve travar por falta de "person"
    assert diagnostics["warning"] is None


def test_same_model_without_person_warns_when_require_person_true():
    names = {0: "Gloves", 1: "Vest", 2: "helmet"}
    diagnostics = _diagnostics_for(names, require_person=True)

    assert diagnostics["ppe_ready"] is False
    assert "person" in diagnostics["warning"]


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
