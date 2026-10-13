"""Laboratório “Pergunte à planta”: catálogo fixo, nunca SQL livre, resposta rotulada."""

from __future__ import annotations

import pytest

from app.services.pergunte_a_planta import PerguntaRecusada, interpretar_plano, responder

DADOS = {"alertas": {"total": 7, "criticos": 3, "por_regra": {"Sem capacete": 5, "Sem colete": 2}, "por_camera": {"Doca": 7},
                     "por_hora": {"10:00": 7}, "falsos_positivos": 1, "reconhecidos": 2, "ativos_agora": 0,
                     "duracao_mediana_s": 30}}


class _Provedor:
    def __init__(self, plano: str):
        self.plano = plano
        self.prompts: list[str] = []

    def resumir(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.plano if len(self.prompts) == 1 else "Foram 5 alertas sem capacete."


def _montar(horas, camera_id):
    _montar.chamadas.append((horas, camera_id))
    return DADOS


_montar.chamadas = []


def test_fluxo_completo_rotulado_e_com_numeros():
    p = _Provedor('{"agregacao": "alertas_por_tipo", "parametros": {"horas": 4}}')
    r = responder("quantos sem capacete hoje?", p, _montar)
    assert r["agregacao"] == "alertas_por_tipo"
    assert r["numeros"]["por_regra"]["Sem capacete"] == 5
    assert "gerada" in r["rotulo"]
    assert _montar.chamadas[-1] == (4.0, None)


@pytest.mark.parametrize(
    "texto",
    [
        '{"agregacao": "DROP TABLE alerts", "parametros": {}}',
        '{"agregacao": null}',
        "SELECT * FROM alerts",
        '{"agregacao": "alertas_por_tipo", "parametros": {"horas": "muitas"}}',
        '{"agregacao": "alertas_por_tipo", "parametros": {"camera_id": "1; DELETE"}}',
        '{"agregacao": "alertas_por_tipo", "parametros": "x"}',
    ],
)
def test_qualquer_coisa_fora_do_catalogo_e_recusada(texto):
    with pytest.raises(PerguntaRecusada):
        interpretar_plano(texto)


def test_horas_sao_limitadas():
    _, params = interpretar_plano('{"agregacao": "resumo_do_turno", "parametros": {"horas": 9999}}')
    assert params == {"horas": 72.0}


def test_api_desligada_por_padrao(real_monitor_app):
    r = real_monitor_app.test_client().post("/api/lab/pergunte", json={"pergunta": "quantos alertas?"})
    assert r.status_code == 409
