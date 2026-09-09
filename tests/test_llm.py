"""Camada LLM: schema, validação e degradação.

A regra que organiza este arquivo: **uma resposta que não cabe no schema não
pode virar alerta.** Um modelo de linguagem erra, alucina campo, devolve JSON
truncado, ou responde em prosa quando você pediu JSON. Se qualquer um desses
casos produzir um `Alert` no banco, o sistema passa a inventar violação de
segurança — que é pior do que não ter camada LLM nenhuma.

Por isso o analisador **nunca levanta** para o chamador: devolve `None` e
registra. Quem chama é o loop de captura (indiretamente), e uma exceção ali
derruba o worker da câmera.

Nenhum teste aqui toca a rede nem lê chave de API.
"""

from __future__ import annotations

import json

import pytest
from app.llm import (
    NIVEIS_DE_RISCO,
    AnalisadorDeRisco,
    AnaliseRisco,
    ProvedorFake,
    ProvedorIndisponivel,
    carregar_prompt,
    versoes_de_prompt,
)

RESPOSTA_VALIDA = {
    "nivel_risco": "alto",
    "epis_ausentes": ["helmet", "vest"],
    "justificativa": "Duas pessoas operando proximas a escavadeira sem capacete nem colete.",
    "confianca": 0.82,
    "acao_recomendada": "Interromper a frente de servico e fornecer EPI antes de retomar.",
}


def analisador(resposta) -> AnalisadorDeRisco:
    """Analisador com provedor FAKE — nenhuma chamada de rede."""
    return AnalisadorDeRisco(provedor=ProvedorFake(resposta))


# ------------------------------------------------------------- caminho ok ---
def test_resposta_valida_vira_analise_tipada():
    resultado = analisador(json.dumps(RESPOSTA_VALIDA)).analisar(b"jpeg-falso", versao="v1")

    assert isinstance(resultado, AnaliseRisco)
    assert resultado.nivel_risco == "alto"
    assert resultado.epis_ausentes == ["helmet", "vest"]
    assert resultado.confianca == pytest.approx(0.82)
    assert resultado.justificativa.startswith("Duas pessoas")


def test_json_dentro_de_cerca_markdown_e_aceito():
    """Modelo devolvendo ```json ... ``` e o caso comum, nao a excecao."""
    cercado = "Claro! Segue a analise:\n```json\n" + json.dumps(RESPOSTA_VALIDA) + "\n```\n"
    resultado = analisador(cercado).analisar(b"jpeg-falso", versao="v1")

    assert isinstance(resultado, AnaliseRisco)
    assert resultado.nivel_risco == "alto"


def test_lista_de_epis_vazia_e_valida():
    """Cena segura: nenhum EPI ausente, risco baixo. Nao e erro."""
    segura = RESPOSTA_VALIDA | {"nivel_risco": "baixo", "epis_ausentes": [], "confianca": 0.9}
    resultado = analisador(json.dumps(segura)).analisar(b"jpeg-falso", versao="v1")

    assert resultado is not None
    assert resultado.epis_ausentes == []
    assert resultado.nivel_risco == "baixo"


# ------------------------------------------------- resposta fora do schema ---
@pytest.mark.parametrize(
    ("rotulo", "resposta"),
    [
        ("prosa sem json", "Nao consigo analisar esta imagem."),
        ("json truncado", '{"nivel_risco": "alto", "epis_ausentes": ['),
        ("vazio", ""),
        ("nivel inexistente", json.dumps(RESPOSTA_VALIDA | {"nivel_risco": "apocaliptico"})),
        ("confianca acima de 1", json.dumps(RESPOSTA_VALIDA | {"confianca": 7.5})),
        ("confianca negativa", json.dumps(RESPOSTA_VALIDA | {"confianca": -0.2})),
        ("confianca como texto", json.dumps(RESPOSTA_VALIDA | {"confianca": "muita"})),
        ("epi desconhecido", json.dumps(RESPOSTA_VALIDA | {"epis_ausentes": ["capa_de_chuva"]})),
        ("justificativa vazia", json.dumps(RESPOSTA_VALIDA | {"justificativa": "   "})),
        ("acao vazia", json.dumps(RESPOSTA_VALIDA | {"acao_recomendada": ""})),
        ("epis_ausentes nao e lista", json.dumps(RESPOSTA_VALIDA | {"epis_ausentes": "helmet"})),
        ("lista no lugar do objeto", json.dumps([RESPOSTA_VALIDA])),
    ],
)
def test_resposta_invalida_devolve_none_sem_levantar(rotulo, resposta):
    """Nunca crash, nunca alerta inventado. `None` e a resposta correta."""
    resultado = analisador(resposta).analisar(b"jpeg-falso", versao="v1")

    assert resultado is None, f"{rotulo}: deveria ter sido rejeitado, virou {resultado!r}"


def test_campo_faltando_devolve_none():
    for campo in RESPOSTA_VALIDA:
        incompleta = {k: v for k, v in RESPOSTA_VALIDA.items() if k != campo}
        assert analisador(json.dumps(incompleta)).analisar(b"x", versao="v1") is None, (
            f"faltando '{campo}' deveria ter sido rejeitado"
        )


def test_campo_extra_inventado_pelo_modelo_e_rejeitado():
    """Campo a mais e sinal de que o modelo nao seguiu o contrato.

    Aceitar em silencio deixaria passar resposta de um prompt errado ou de um
    modelo trocado sem ninguem perceber.
    """
    com_extra = RESPOSTA_VALIDA | {"multa_sugerida": "R$ 5.000"}
    assert analisador(json.dumps(com_extra)).analisar(b"x", versao="v1") is None


# ------------------------------------------------------------- degradacao ---
def test_provedor_indisponivel_degrada_para_none():
    """Sem chave de API o sistema segue funcionando, sem a camada LLM."""

    class ProvedorSemChave:
        def analisar(self, imagem_jpeg, prompt):  # noqa: ARG002
            raise ProvedorIndisponivel("GEMINI_API_KEY ausente")

    assert AnalisadorDeRisco(provedor=ProvedorSemChave()).analisar(b"x", versao="v1") is None


def test_erro_inesperado_do_provedor_nao_escapa():
    """Timeout, DNS, 500, qualquer coisa: o loop de captura nao pode cair."""

    class ProvedorQueExplode:
        def analisar(self, imagem_jpeg, prompt):  # noqa: ARG002
            raise TimeoutError("estourou o timeout")

    assert AnalisadorDeRisco(provedor=ProvedorQueExplode()).analisar(b"x", versao="v1") is None


def test_analisador_sem_provedor_nenhum_devolve_none():
    assert AnalisadorDeRisco(provedor=None).analisar(b"x", versao="v1") is None


def test_erro_nunca_carrega_a_chave_de_api():
    """A mensagem de erro nao pode vazar segredo — nem para o log.

    Quem le log de producao nao deveria conseguir extrair a chave de uma falha
    de autenticacao.
    """
    segredo = "AIzaSyFAKE-CHAVE-DE-TESTE-NAO-REAL-123456789"

    class ProvedorQueVazaria:
        def analisar(self, imagem_jpeg, prompt):  # noqa: ARG002
            raise ProvedorIndisponivel(f"401 com a chave {segredo}")

    analisadora = AnalisadorDeRisco(provedor=ProvedorQueVazaria())
    assert analisadora.analisar(b"x", versao="v1") is None
    assert segredo not in " ".join(analisadora.ultimos_erros)


# --------------------------------------------------------------- prompts ---
def test_existem_duas_versoes_de_prompt():
    assert versoes_de_prompt() == ["v1", "v2"]


def test_prompts_sao_diferentes_e_nao_vazios():
    v1, v2 = carregar_prompt("v1"), carregar_prompt("v2")

    assert len(v1) > 200 and len(v2) > 200, "prompt vazio ou stub nao conta como versao"
    assert v1 != v2, "v2 tem que mudar algo em relacao a v1, senao nao e uma versao nova"


def test_prompt_declara_o_schema_que_o_codigo_valida():
    """Prompt e schema nao podem divergir em silencio.

    Se alguem renomear um campo no schema e esquecer o prompt, o modelo passa a
    responder no formato antigo e TODA resposta e rejeitada — o sintoma seria
    "o LLM parou de funcionar", sem pista da causa.
    """
    for versao in versoes_de_prompt():
        texto = carregar_prompt(versao)
        for campo in AnaliseRisco.model_fields:
            assert campo in texto, f"{versao} nao menciona o campo '{campo}'"
        for nivel in NIVEIS_DE_RISCO:
            assert nivel in texto, f"{versao} nao menciona o nivel '{nivel}'"


def test_versao_de_prompt_inexistente_e_erro_explicito():
    with pytest.raises(KeyError):
        carregar_prompt("v99")
