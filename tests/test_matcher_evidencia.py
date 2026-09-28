"""Especifica o terceiro estado de EPI: AUSENTE nao e o mesmo que NAO VISTO.

Ate a Sprint 3, "missing" significava "o detector nao achou a caixa positiva".
Isso junta dois casos que para a seguranca do trabalho sao opostos:

- a pessoa esta SEM capacete (o detector viu a cabeca descoberta);
- o capacete simplesmente nao foi detectado (pequeno, de costas, oculto,
  confianca abaixo do corte — a Fase 9 da BENCH.md mediu 0,14 a 0,26 para
  capacete branco visivel a olho nu).

Os dois modelos avaliados (Vyra e o treinado no Construction-PPE) tem classes
NEGATIVAS explicitas (NO-Hardhat, no_helmet, none...). Com elas o matcher pode
separar "negativa detectada" de "nada detectado", e a politica decide o que
vira alerta.
"""

from __future__ import annotations

from app.vision.person_compliance_matcher import PPE_KEYS, PersonComplianceMatcher
from app.vision.schemas import BoundingBox, Detection
from app.vision.yolo_ppe_detector import YoloPPEDetector

TUDO = dict.fromkeys(PPE_KEYS, True)
PESSOA = Detection(label="person", confidence=0.9, box=BoundingBox(100, 100, 300, 900), category="person")


def _det(label: str, box: BoundingBox, conf: float = 0.8) -> Detection:
    return Detection(label=label, confidence=conf, box=box, category="ppe")


CABECA = BoundingBox(150, 100, 250, 170)
TORSO = BoundingBox(120, 300, 280, 520)


def _status(pessoas, epi):
    return pessoas[0]["ppe"][epi]


def test_aliases_das_classes_negativas_dos_dois_modelos():
    n = YoloPPEDetector.normalize_label
    # Vyra
    assert n("NO-Hardhat") == "no_helmet"
    assert n("NO-Safety Vest") == "no_vest"
    assert n("NO-Gloves") == "no_gloves"
    assert n("NO-Goggles") == "no_glasses"
    assert n("NO-Mask") == "no_mask"
    # Construction-PPE (Ultralytics): "none" e o torso sem colete
    assert n("no_helmet") == "no_helmet"
    assert n("none") == "no_vest"
    assert n("no_goggle") == "no_glasses"
    assert n("no_boots") == "no_safety_shoe"


def test_politica_ausencia_preserva_o_comportamento_antigo():
    """Default: nada detectado continua sendo missing (compatibilidade)."""
    pessoas = PersonComplianceMatcher().build([PESSOA], supported_ppe=TUDO, enabled_ppe=TUDO)
    capacete = _status(pessoas, "helmet")
    assert capacete["status"] == "missing"
    assert capacete["evidence"] == "nao_detectado"


def test_politica_evidencia_separa_nao_visto_de_ausente():
    matcher = PersonComplianceMatcher(missing_policy="evidencia")
    deteccoes = [PESSOA, _det("no_helmet", CABECA)]
    pessoas = matcher.build(deteccoes, supported_ppe=TUDO, enabled_ppe=TUDO)
    capacete = _status(pessoas, "helmet")
    colete = _status(pessoas, "vest")
    assert capacete["status"] == "missing"
    assert capacete["evidence"] == "negativa_detectada"
    assert capacete["confidence"] == 0.8
    # Nenhuma caixa de colete, nem positiva nem negativa: nao da para afirmar.
    assert colete["status"] == "unverified"
    assert colete["evidence"] == "nao_detectado"


def test_positiva_detectada_e_ok_nas_duas_politicas():
    for politica in ("ausencia", "evidencia"):
        pessoas = PersonComplianceMatcher(missing_policy=politica).build(
            [PESSOA, _det("vest", TORSO)], supported_ppe=TUDO, enabled_ppe=TUDO
        )
        assert _status(pessoas, "vest")["status"] == "ok"
        assert _status(pessoas, "vest")["evidence"] == "detectado"


def test_conflito_na_mesma_cabeca_vence_a_mais_confiante():
    matcher = PersonComplianceMatcher(missing_policy="evidencia")
    deteccoes = [PESSOA, _det("helmet", CABECA, 0.40), _det("no_helmet", CABECA, 0.75)]
    assert _status(matcher.build(deteccoes, supported_ppe=TUDO, enabled_ppe=TUDO), "helmet")["status"] == "missing"
    deteccoes = [PESSOA, _det("helmet", CABECA, 0.80), _det("no_helmet", CABECA, 0.30)]
    assert _status(matcher.build(deteccoes, supported_ppe=TUDO, enabled_ppe=TUDO), "helmet")["status"] == "ok"


def test_uma_mao_nua_e_violacao_mesmo_com_a_outra_de_luva():
    matcher = PersonComplianceMatcher(missing_policy="evidencia")
    mao_esq = BoundingBox(110, 560, 150, 610)
    mao_dir = BoundingBox(250, 560, 290, 610)
    deteccoes = [PESSOA, _det("gloves", mao_esq, 0.9), _det("no_gloves", mao_dir, 0.5)]
    assert _status(matcher.build(deteccoes, supported_ppe=TUDO, enabled_ppe=TUDO), "gloves")["status"] == "missing"


def test_negativa_de_outra_pessoa_nao_contamina():
    matcher = PersonComplianceMatcher(missing_policy="evidencia")
    outra = Detection(label="person", confidence=0.9, box=BoundingBox(600, 100, 800, 900), category="person")
    cabeca_da_outra = BoundingBox(650, 100, 750, 170)
    pessoas = matcher.build([PESSOA, outra, _det("no_helmet", cabeca_da_outra)], supported_ppe=TUDO, enabled_ppe=TUDO)
    por_x = sorted(pessoas, key=lambda p: p["box"]["x1"])
    assert por_x[0]["ppe"]["helmet"]["status"] == "unverified"
    assert por_x[1]["ppe"]["helmet"]["status"] == "missing"


def test_classe_negativa_nao_vira_epi_detectado():
    """Uma caixa NO-Hardhat nunca pode contar como capacete presente."""
    pessoas = PersonComplianceMatcher().build([PESSOA, _det("no_helmet", CABECA)], supported_ppe=TUDO, enabled_ppe=TUDO)
    assert _status(pessoas, "helmet")["status"] == "missing"
    assert _status(pessoas, "helmet")["detections"] == []


def test_politica_invalida_falha_cedo():
    import pytest

    with pytest.raises(ValueError):
        PersonComplianceMatcher(missing_policy="talvez")


# --- fio ate o RuleEngine: "unverified" nunca vira alerta --------------------


def _engine(politica: str):
    from app.config import Config
    from app.services.feature_manager import FeatureManager
    from app.services.risk_rules import RuleEngine

    manager = FeatureManager.from_config({"DEFAULT_FEATURES": Config.DEFAULT_FEATURES})
    return RuleEngine(
        manager,
        cooldown_seconds=0,
        risk_polygon=[(0.7, 0.1), (1, 0.1), (1, 1), (0.7, 1)],
        supported_ppe_getter=lambda: set(PPE_KEYS),
        missing_policy=politica,
    )


def test_rule_engine_com_evidencia_so_alerta_a_negativa():
    alertas = _engine("evidencia").evaluate([PESSOA, _det("no_helmet", CABECA)], None, (1000, 1000, 3))
    assert {a.feature for a in alertas} == {"helmet"}


def test_rule_engine_com_ausencia_alerta_tudo_que_nao_foi_visto():
    alertas = _engine("ausencia").evaluate([PESSOA], None, (1000, 1000, 3))
    assert {a.feature for a in alertas} == set(PPE_KEYS)


def test_compliance_mostra_nao_verificado_em_amarelo_e_sem_alerta():
    from app.config import Config
    from app.services.compliance_service import ComplianceService
    from app.services.feature_manager import FeatureManager

    manager = FeatureManager.from_config({"DEFAULT_FEATURES": Config.DEFAULT_FEATURES})
    engine = _engine("evidencia")
    servico = ComplianceService(manager, engine)
    estado = servico.build_state(
        detections=[PESSOA, _det("vest", TORSO)],
        pose=None,
        frame_shape=(1000, 1000, 3),
        model_diagnostics={"supported_ppe": dict.fromkeys(PPE_KEYS, True)},
        active_alerts=[],
    )
    assert estado["ppe"]["vest"]["status"] == "ok"
    assert estado["ppe"]["helmet"]["status"] == "unverified"
    assert "Não verificado" in estado["ppe"]["helmet"]["message"]


def test_config_le_a_politica_do_ambiente(monkeypatch):
    import importlib

    import app.config as modulo

    monkeypatch.setenv("PPE_MISSING_POLICY", "Evidencia ")
    recarregado = importlib.reload(modulo)
    try:
        assert recarregado.Config.PPE_MISSING_POLICY == "evidencia"
    finally:
        monkeypatch.delenv("PPE_MISSING_POLICY")
        importlib.reload(modulo)
