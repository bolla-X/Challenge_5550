"""Relatório de turno (F9): números do banco, escopo do operador, LLM opcional."""

from __future__ import annotations

from app.extensions import db
from app.models import Alert, Camera


def _alerta(camera_id, *, severity="critical", rule="missing_helmet", message="Sem capacete — Pessoa 1", **kw):
    meta = {"false_positive": True} if kw.pop("false_positive", False) else {}
    return Alert(camera_id=camera_id, rule=rule, severity=severity, message=message, feature="helmet",
                 status=kw.pop("status", "resolved"), metadata_json=meta, **kw)


def test_relatorio_conta_por_tipo_e_por_camera(real_monitor_app):
    with real_monitor_app.app_context():
        a, b = Camera(name="Portaria", source_type="USB", source="0"), Camera(name="Doca", source_type="USB", source="1")
        db.session.add_all([a, b])
        db.session.commit()
        db.session.add_all([_alerta(a.id), _alerta(a.id, false_positive=True),
                            _alerta(b.id, severity="high", rule="missing_vest", message="Sem colete — Pessoa 2")])
        db.session.commit()
    dados = real_monitor_app.test_client().get("/api/relatorio/turno?horas=8").get_json()
    assert dados["alertas"]["total"] == 3
    assert dados["alertas"]["criticos"] == 2
    assert dados["alertas"]["falsos_positivos"] == 1
    assert dados["alertas"]["por_regra"] == {"Sem capacete": 2, "Sem colete": 1}
    assert dados["alertas"]["por_camera"] == {"Portaria": 2, "Doca": 1}


def test_pagina_imprimivel_e_resumo_llm_desligado(real_monitor_app):
    cliente = real_monitor_app.test_client()
    pagina = cliente.get("/relatorio/turno")
    assert pagina.status_code == 200 and b"Relat\xc3\xb3rio de turno" in pagina.data
    assert b"Nenhum texto deste relat" in pagina.data, "os números não podem parecer texto de LLM"
    resumo = cliente.post("/api/relatorio/turno/resumo").get_json()
    assert resumo["estado"] == "indisponivel", "sem LLM, o relatório funciona e diz que o resumo não existe"
