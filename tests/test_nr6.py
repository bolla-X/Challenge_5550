"""G10: infração de EPI → item da NR-6, só com trecho que existe no texto oficial."""

from __future__ import annotations

from app.extensions import db
from app.models import Alert, Camera
from app.services.nr6 import ANEXO_I, SEM_ITEM, epi_da_regra, mapear


def test_epi_da_regra():
    assert epi_da_regra("missing_helmet") == "helmet"
    assert epi_da_regra("incorrect_gloves") == "gloves"
    assert epi_da_regra("fall_detected") is None


def test_capacete_liga_ao_anexo_e_aos_itens_gerais():
    (linha,) = mapear({"missing_helmet": 3, "incorrect_helmet": 1})
    assert linha["epi"] == "helmet" and linha["alertas"] == 4
    itens = [i["item"] for i in linha["itens"]]
    assert itens == ["6.5.1 e)", "6.6.1 a)", "Anexo I, A.1"]


def test_colete_e_mascara_ficam_sem_item_com_motivo():
    linhas = {lin["epi"]: lin for lin in mapear({"missing_vest": 2, "missing_mask": 1})}
    assert linhas["vest"]["itens"] == [] and "alta visibilidade" in linhas["vest"]["sem_item"]
    assert linhas["mask"]["itens"] == [] and "respirador" in linhas["mask"]["sem_item"]


def test_nenhum_epi_mapeado_e_nao_mapeado_ao_mesmo_tempo():
    assert not set(ANEXO_I) & set(SEM_ITEM)


def test_regras_que_nao_sao_de_epi_nao_entram():
    assert mapear({"fall_detected": 5, "risk_area_presence": 2}) == []


def test_relatorio_traz_nr6_e_ignora_falso_positivo(real_monitor_app):
    with real_monitor_app.app_context():
        cam = Camera(name="Doca", source_type="USB", source="0")
        db.session.add(cam)
        db.session.commit()
        db.session.add_all([
            Alert(camera_id=cam.id, rule="missing_helmet", severity="critical", message="Sem capacete · Pessoa 1",
                  feature="helmet", status="resolved", metadata_json={}),
            Alert(camera_id=cam.id, rule="missing_gloves", severity="medium", message="Sem luvas · Pessoa 1",
                  feature="gloves", status="resolved", metadata_json={"false_positive": True}),
        ])
        db.session.commit()
    cliente = real_monitor_app.test_client()
    nr6 = cliente.get("/api/relatorio/turno?horas=8").get_json()["nr6"]
    assert nr6["fonte"].startswith("https://www.gov.br/trabalho-e-emprego/")
    assert [lin["epi"] for lin in nr6["linhas"]] == ["helmet"]
    pagina = cliente.get("/relatorio/turno").get_data(as_text=True)
    assert "Infrações × NR-6" in pagina and "A.1 - Capacete" in pagina
