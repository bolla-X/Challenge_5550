"""Fallback determinístico da segunda opinião no modo demonstração (ES Sprint 4, F1.3).

Uma linha por caminho da decisão em `ServicoDeRiscoLLM.a_partir_da_config`:

- demo sem chave → provedor fixo, `modo="demonstracao"`, rotulado e com confiança 0;
- `LLM_DEMO_FALLBACK` FORA da demo (um .env copiado) → continua desligado;
- fora da demo sem chave → continua desligado (comportamento de sempre);
- com chave → Gemini (o fallback nunca substitui a análise real);
- a análise que sai para o painel/socket carrega `modo="demonstracao"`, e o
  schema do Gemini continua recusando esse campo.
"""

from __future__ import annotations

import pytest
from app.llm import AnalisadorDeRisco, AnaliseDeDemonstracao, ProvedorDemonstracao, ProvedorFake, ProvedorGemini
from app.services.llm_risk_service import ServicoDeRiscoLLM

DEMO = {"LLM_ENABLED": True, "LLM_DEMO_FALLBACK": True, "DEMO_MODE": True}


@pytest.fixture()
def sem_chave(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)


@pytest.mark.usefixtures("sem_chave")
def test_demo_sem_chave_usa_resposta_fixa_rotulada():
    servico = ServicoDeRiscoLLM.a_partir_da_config(DEMO)

    assert servico.habilitado is True
    assert servico.modo == "demonstracao"
    assert servico.estatisticas()["modo"] == "demonstracao"
    assert isinstance(servico.analisador.provedor, ProvedorDemonstracao)


def test_resposta_fixa_passa_no_schema_e_nao_finge_analise():
    analisador = AnalisadorDeRisco(provedor=ProvedorDemonstracao())

    primeira = analisador.analisar(b"\xff\xd8 qualquer jpeg", versao="v2")
    segunda = analisador.analisar(b"outra imagem completamente diferente", versao="v2")

    assert primeira is not None and primeira == segunda  # determinística: não depende da imagem
    assert primeira.confianca == 0.0
    assert primeira.epis_ausentes == []
    assert "Modo demonstração" in primeira.justificativa


@pytest.mark.usefixtures("sem_chave")
def test_flag_de_fallback_fora_da_demo_nao_liga_nada():
    servico = ServicoDeRiscoLLM.a_partir_da_config({"LLM_ENABLED": True, "LLM_DEMO_FALLBACK": True})

    assert servico.habilitado is False
    assert servico.modo == "real"


@pytest.mark.usefixtures("sem_chave")
def test_fora_da_demo_sem_chave_continua_desligado():
    servico = ServicoDeRiscoLLM.a_partir_da_config({"LLM_ENABLED": True})

    assert servico.habilitado is False
    assert servico.modo == "real"


def test_com_chave_vale_o_gemini_mesmo_na_demo(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "chave-de-teste-nao-usada")

    servico = ServicoDeRiscoLLM.a_partir_da_config(DEMO)

    assert servico.habilitado is True
    assert servico.modo == "real"
    assert isinstance(servico.analisador.provedor, ProvedorGemini)


@pytest.mark.usefixtures("sem_chave")
def test_payload_do_modo_demonstracao_carrega_a_marca():
    servico = ServicoDeRiscoLLM.a_partir_da_config(DEMO)
    servico.executor = lambda tarefa: tarefa()  # síncrono no teste
    recebidas = []
    servico.ao_concluir = recebidas.append

    assert servico.submeter(camera_id=1, imagem_jpeg=b"\xff\xd8")
    assert len(recebidas) == 1 and isinstance(recebidas[0], AnaliseDeDemonstracao)
    assert recebidas[0].model_dump()["modo"] == "demonstracao"


def test_gemini_nao_pode_se_declarar_demonstracao():
    resposta = ProvedorDemonstracao.RESPOSTA[:-1] + ', "modo": "demonstracao"}'
    assert AnalisadorDeRisco(provedor=ProvedorFake(resposta)).analisar(b"x", versao="v2") is None
