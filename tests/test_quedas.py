"""F2: queda pela classe `fall_detected` do modelo de EPI, atribuída a um ID de rastreio."""

from __future__ import annotations

from app.services.feature_manager import FeatureManager
from app.services.risk_rules import RuleEngine
from app.vision.person_tracker import PersonTracker
from app.vision.quedas import atribuir_quedas, pessoas_com_quedas
from app.vision.schemas import BoundingBox, Detection


def _pessoa(x1, y1, x2, y2, track_id=None):
    return Detection(label="person", confidence=0.9, box=BoundingBox(x1, y1, x2, y2), category="person", track_id=track_id)


def _queda(x1, y1, x2, y2, conf=0.6):
    return Detection(label="fall_detected", confidence=conf, box=BoundingBox(x1, y1, x2, y2), category="fall")


def _motor(features="falls,pose"):
    return RuleEngine(FeatureManager.from_config({"DEFAULT_FEATURES": features}), cooldown_seconds=0, risk_polygon=[])


def test_queda_dentro_de_uma_pessoa_e_dela():
    pessoas = [_pessoa(0, 0, 100, 300, 1), _pessoa(300, 100, 600, 400, 2)]
    queda = _queda(320, 250, 590, 390)
    assert pessoas_com_quedas(pessoas, [queda]) == pessoas, "contida: não cria pessoa nova"


def test_pessoa_caida_que_o_detector_nao_viu_vira_pessoa_rastreada():
    """O caso da fixture: ninguém contém a caixa de queda (sobreposição 0,00–0,18)."""
    pessoas = [_pessoa(0, 0, 100, 300)]
    queda = _queda(260, 430, 560, 530)
    todas = pessoas_com_quedas(pessoas, [queda])
    assert len(todas) == 2 and todas[1].box == queda.box and todas[1].label == "person"

    rastreadas = PersonTracker().update(todas)
    assert all(p.track_id is not None for p in rastreadas)


def test_alerta_de_queda_sai_com_o_id_da_pessoa():
    motor = _motor()
    caida = _pessoa(260, 430, 560, 530, track_id=7)
    queda = _queda(262, 432, 558, 528)
    alertas = [a for a in motor.evaluate([caida, queda], None, (576, 720, 3)) if a.rule == "fall_detected"]

    assert len(alertas) == 1
    assert alertas[0].metadata["person_id"] == "person_7"
    assert alertas[0].feature == "falls" and alertas[0].severity == "critical"
    assert "Pessoa" in alertas[0].message


def test_queda_desligada_nao_alerta():
    motor = _motor(features="pose")
    caida = _pessoa(260, 430, 560, 530, track_id=7)
    assert not [a for a in motor.evaluate([caida, _queda(262, 432, 558, 528)], None, (576, 720, 3))
                if a.rule == "fall_detected"]


def test_sobreposicao_pequena_nao_atribui():
    pessoas = [{"id": "person_1", "label": "Pessoa 1", "box": {"x1": 0, "y1": 0, "x2": 100, "y2": 100}}]
    [(queda, pessoa)] = atribuir_quedas([_queda(80, 80, 400, 400)], pessoas)
    assert pessoa is None, "só ~0,4 % da caixa de queda cai dentro da pessoa"


def test_linha_do_tempo_guarda_so_mudancas_e_e_limitada():
    from app.services.linha_do_tempo_conformidade import LinhaDoTempoPorId

    def pessoa(capacete, caida=False):
        return {"id": "person_3", "label": "Pessoa 3", "ppe": {"helmet": {"status": capacete}, "glasses": {"status": "disabled"}},
                "pose": {"fallen": caida}, "risk_area": {"status": "outside"}}

    linha = LinhaDoTempoPorId(max_eventos=3, max_ids=2)
    linha.registrar([pessoa("missing")], 1.0)
    linha.registrar([pessoa("missing")], 2.0)  # igual: não registra
    linha.registrar([pessoa("ok")], 3.0)
    linha.registrar([pessoa("ok", caida=True)], 4.0)
    eventos = linha.obter("person_3")["eventos"]
    assert [(e["ts"], e["ppe"]["helmet"], e["queda"]) for e in eventos] == [(1.0, "missing", False), (3.0, "ok", False), (4.0, "ok", True)]
    assert "glasses" not in eventos[0]["ppe"], "recurso desligado não entra"

    for i in range(5):
        linha.registrar([{"id": f"person_{10 + i}", "label": "x", "ppe": {}}], 5.0 + i)
    assert len(linha.ids()) == 2 and linha.obter("person_3") is None, "limite de IDs: sai o mais antigo"
