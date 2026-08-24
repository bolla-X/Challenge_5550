"""Trava contra o bloqueador que motivou este PR.

Ao adicionar a classe `glasses`, a versão original desta mudança:
  - tirou helmet/vest/gloves de DEFAULT_FEATURES (ficaram desligados por padrão);
  - não adicionou `glasses` à lista `checks` do RuleEngine.

Somados, os dois deixavam o sistema sem emitir NENHUM alerta de EPI — que é a
função principal do produto. Estes testes falham se isso voltar a acontecer.
"""
from __future__ import annotations

from app.config import Config
from app.services.feature_manager import FeatureManager
from app.services.risk_rules import RuleEngine
from app.vision.person_compliance_matcher import PPE_KEYS
from app.vision.schemas import BoundingBox, Detection

TODOS_SUPORTADOS = set(PPE_KEYS)


def _engine(feature_manager: FeatureManager) -> RuleEngine:
    return RuleEngine(
        feature_manager,
        cooldown_seconds=0,
        risk_polygon=[(0.7, 0.1), (1, 0.1), (1, 1), (0.7, 1)],
        supported_ppe_getter=lambda: TODOS_SUPORTADOS,
    )


def _pessoa_sem_epi() -> list[Detection]:
    return [Detection(label="person", confidence=0.9, box=BoundingBox(10, 10, 100, 240), category="person")]


def test_default_features_liga_todos_os_epis():
    """O default de fábrica não pode deixar nenhum EPI desligado."""
    manager = FeatureManager.from_config({"DEFAULT_FEATURES": Config.DEFAULT_FEATURES})
    desligados = [flag.key for flag in manager.list() if flag.group == "EPIs" and not flag.enabled]
    assert desligados == [], f"features de EPI desligadas por padrão: {desligados}"


def test_pessoa_sem_epi_gera_alerta_de_cada_item():
    """Cada chave em PPE_KEYS precisa ter uma regra correspondente.

    É este teste que pega uma classe nova adicionada ao matcher/compliance mas
    esquecida no RuleEngine — que foi exatamente o caso de `glasses`.
    """
    manager = FeatureManager.from_config({"DEFAULT_FEATURES": Config.DEFAULT_FEATURES})
    alertas = _engine(manager).evaluate(_pessoa_sem_epi(), None, (480, 640, 3))

    features_alertadas = {alerta.feature for alerta in alertas}
    faltando = set(PPE_KEYS) - features_alertadas
    assert faltando == set(), f"sem regra de alerta para: {sorted(faltando)}"


def test_desligar_uma_feature_silencia_so_ela():
    manager = FeatureManager.from_config({"DEFAULT_FEATURES": Config.DEFAULT_FEATURES})
    manager.update({"glasses": False})
    alertas = _engine(manager).evaluate(_pessoa_sem_epi(), None, (480, 640, 3))

    features_alertadas = {alerta.feature for alerta in alertas}
    assert "glasses" not in features_alertadas
    assert {"helmet", "vest", "gloves"} <= features_alertadas


def test_glasses_e_conhecido_pelo_score_de_risco_e_pela_api_de_camera():
    """Uma classe de EPI só está de fato integrada quando entra no score e no
    CRUD de câmera — senão o alerta existe mas não pontua e o toggle por câmera
    é rejeitado com 400."""
    from app.api.cameras import VALID_FEATURE_KEYS
    from app.services.risk_score_service import FEATURES

    for key in PPE_KEYS:
        assert key in FEATURES, f"{key} não entra no score de risco"
        assert key in VALID_FEATURE_KEYS, f"{key} é rejeitado por PUT /api/cameras/<id>"
