from __future__ import annotations

from app.vision.yolo_ppe_detector import YoloPPEDetector


def _diagnostics_for(names: dict[int, str], *, require_person: bool) -> dict:
    detector = YoloPPEDetector(model_path="dummy.pt", require_person=require_person)
    return detector._build_diagnostics(names=names, error=None)


def test_ppe_only_model_is_ready_without_person_when_require_person_false():
    # epi_pretrained.pt: 6 classes de EPI, sem "person".
    names = {0: "Gloves", 1: "Vest", 2: "goggles", 3: "helmet", 4: "mask", 5: "safety_shoe"}
    diagnostics = _diagnostics_for(names, require_person=False)

    assert diagnostics["supported_ppe"] == {"helmet": True, "vest": True, "gloves": True}
    assert diagnostics["person_supported"] is False
    assert diagnostics["ppe_ready"] is True  # não deve travar por falta de "person"
    assert diagnostics["warning"] is None


def test_same_model_without_person_warns_when_require_person_true():
    names = {0: "Gloves", 1: "Vest", 2: "helmet"}
    diagnostics = _diagnostics_for(names, require_person=True)

    assert diagnostics["ppe_ready"] is False
    assert "person" in diagnostics["warning"]


def test_coco_person_model_reports_person_supported():
    # yolov8n.pt (COCO): classe 0 = person, sem helmet/vest/gloves.
    names = {0: "person", 1: "bicycle"}
    diagnostics = _diagnostics_for(names, require_person=True)

    assert diagnostics["person_supported"] is True
    assert diagnostics["supported_ppe"] == {"helmet": False, "vest": False, "gloves": False}


def test_normalize_label_maps_new_model_raw_names():
    assert YoloPPEDetector.normalize_label("Gloves") == "gloves"
    assert YoloPPEDetector.normalize_label("Vest") == "vest"
    assert YoloPPEDetector.normalize_label("helmet") == "helmet"
    # goggles/mask/safety_shoe não têm nome interno hoje: ficam como vieram.
    assert YoloPPEDetector.normalize_label("goggles") == "goggles"
    assert YoloPPEDetector.normalize_label("mask") == "mask"
    assert YoloPPEDetector.normalize_label("safety_shoe") == "safety_shoe"
