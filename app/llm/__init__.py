"""Camada de análise multimodal de risco (Sprint 3).

Fronteira arquitetural: este pacote **não conhece Flask, banco nem socket**.
Recebe bytes de imagem e devolve `AnaliseRisco` ou `None`. Quem integra com o
pipeline é `app/services/llm_risk_service.py`.

A regra que organiza o módulo inteiro: **uma resposta que não cabe no schema
não pode virar alerta.** Um modelo de linguagem devolve JSON truncado, campo
alucinado, ou prosa quando você pediu JSON. Se qualquer um desses casos gerar
um `Alert` no banco, o sistema passa a inventar violação de segurança — pior
do que não ter camada LLM nenhuma. Por isso `AnalisadorDeRisco.analisar`
**nunca levanta**: devolve `None` e registra.
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections import deque
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

logger = logging.getLogger(__name__)

DIR_PROMPTS = Path(__file__).resolve().parent / "prompts"

# Os mesmos seis EPIs que o pipeline de visão conhece
# (app/vision/person_compliance_matcher.py::PPE_KEYS). Manter as duas listas
# iguais é o que permite comparar YOLO e LLM na mesma tabela.
EPIS_CONHECIDOS: tuple[str, ...] = ("helmet", "vest", "gloves", "glasses", "mask", "safety_shoe")

NIVEIS_DE_RISCO: tuple[str, ...] = ("baixo", "medio", "alto", "critico")

NivelDeRisco = Literal["baixo", "medio", "alto", "critico"]

# Modelo multimodal do free tier. Em variável de ambiente para não exigir
# deploy quando o Google renomear a família.
MODELO_PADRAO = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

# Qualquer coisa que pareça chave sai da mensagem antes de virar log. O prefixo
# AIza é o formato de chave de API do Google; a segunda regra pega token longo
# genérico.
_PADROES_DE_SEGREDO = (
    re.compile(r"AIza[0-9A-Za-z_\-]{10,}"),
    re.compile(r"\b[A-Za-z0-9_\-]{32,}\b"),
)

# O modelo costuma embrulhar o JSON em cerca markdown, com prosa em volta.
_CERCA = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


# --------------------------------------------------------------- schema ----
class AnaliseRisco(BaseModel):
    """Resultado validado de uma análise multimodal.

    `extra="forbid"`: campo a mais é sinal de que o modelo não seguiu o
    contrato — prompt trocado, modelo trocado, ou alucinação. Aceitar em
    silêncio deixaria isso passar sem ninguém perceber.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    nivel_risco: NivelDeRisco
    # SEM default: omitir o campo teria virado "nenhum EPI ausente", ou seja, o
    # sistema concluiria CONFORMIDADE a partir de um campo que o modelo nao
    # respondeu. Lista vazia explicita continua valida — o que nao vale e
    # silencio.
    epis_ausentes: list[str]
    justificativa: str
    confianca: float = Field(ge=0.0, le=1.0)
    acao_recomendada: str

    @field_validator("epis_ausentes")
    @classmethod
    def _epis_precisam_ser_conhecidos(cls, valor: list[str]) -> list[str]:
        desconhecidos = [item for item in valor if item not in EPIS_CONHECIDOS]
        if desconhecidos:
            raise ValueError(f"EPI fora do vocabulario do sistema: {desconhecidos}")
        return valor

    @field_validator("justificativa", "acao_recomendada")
    @classmethod
    def _texto_nao_pode_ser_vazio(cls, valor: str) -> str:
        limpo = valor.strip()
        if not limpo:
            raise ValueError("texto vazio: analise sem justificativa nao e acionavel")
        return limpo


# ------------------------------------------------------------ provedores ----
def redigir_segredos(mensagem: str) -> str:
    """Remove o que parece chave de API antes de a mensagem virar log."""
    for padrao in _PADROES_DE_SEGREDO:
        mensagem = padrao.sub("***", mensagem)
    return mensagem


class ProvedorIndisponivel(RuntimeError):
    """Provedor não pode atender: sem chave, sem SDK, sem cota.

    Não é bug — é o caminho de degradação. O sistema segue sem a camada LLM.
    """


@runtime_checkable
class ProvedorMultimodal(Protocol):
    def analisar(self, imagem_jpeg: bytes, prompt: str) -> str:
        """Devolve o texto CRU do modelo. Validar é trabalho do analisador."""
        ...


class ProvedorFake:
    """Dublê de teste: devolve resposta fixa e registra o que recebeu."""

    def __init__(self, resposta: str) -> None:
        self.resposta = resposta
        self.chamadas: list[tuple[int, str]] = []

    def analisar(self, imagem_jpeg: bytes, prompt: str) -> str:
        self.chamadas.append((len(imagem_jpeg), prompt))
        return self.resposta


class ProvedorGemini:
    """Gemini via `google-genai`, com cliente criado sob demanda.

    O cliente **não** nasce no `__init__`: sem isso, importar o módulo numa
    máquina sem chave quebraria a inicialização da aplicação. Aqui a ausência
    de chave só aparece quando alguém realmente tenta analisar — e aparece como
    `ProvedorIndisponivel`, que o analisador trata.
    """

    def __init__(
        self, api_key: str | None = None, modelo: str = MODELO_PADRAO, timeout_s: float = 8.0
    ) -> None:
        self._api_key = api_key or os.getenv("GEMINI_API_KEY") or ""
        self.modelo = modelo
        self.timeout_s = timeout_s
        self._cliente = None

    @property
    def configurado(self) -> bool:
        return bool(self._api_key)

    def _obter_cliente(self):
        if self._cliente is not None:
            return self._cliente
        if not self._api_key:
            raise ProvedorIndisponivel(
                "GEMINI_API_KEY ausente. Camada LLM desligada; o resto do sistema segue."
            )
        try:
            from google import genai
        except ImportError as exc:
            raise ProvedorIndisponivel("pacote google-genai nao instalado") from exc
        # timeout em MILISSEGUNDOS, conforme HttpOptions do SDK.
        self._cliente = genai.Client(
            api_key=self._api_key, http_options={"timeout": int(self.timeout_s * 1000)}
        )
        return self._cliente

    def analisar(self, imagem_jpeg: bytes, prompt: str) -> str:
        from google.genai import types

        cliente = self._obter_cliente()
        try:
            resposta = cliente.models.generate_content(
                model=self.modelo,
                contents=[types.Part.from_bytes(data=imagem_jpeg, mime_type="image/jpeg"), prompt],
            )
        except Exception as exc:  # noqa: BLE001  (fronteira de rede engole tudo de proposito)
            raise ProvedorIndisponivel(redigir_segredos(f"{type(exc).__name__}: {exc}")) from None
        return resposta.text or ""


# --------------------------------------------------------------- prompts ----
def versoes_de_prompt() -> list[str]:
    return sorted(caminho.stem for caminho in DIR_PROMPTS.glob("v*.md"))


def carregar_prompt(versao: str) -> str:
    caminho = DIR_PROMPTS / f"{versao}.md"
    if not caminho.exists():
        raise KeyError(f"Versao de prompt inexistente: {versao}. Disponiveis: {versoes_de_prompt()}")
    return caminho.read_text(encoding="utf-8")


def extrair_json(texto: str) -> str | None:
    """Acha o objeto JSON na resposta, com ou sem cerca markdown."""
    if not texto:
        return None
    cercado = _CERCA.search(texto)
    if cercado:
        texto = cercado.group(1)
    despido = texto.strip()
    # Se o texto INTEIRO já é JSON válido, devolva o que ele é — inclusive
    # quando for uma lista. Extrair o objeto de dentro de `[{...}]` mascararia
    # um modelo que respondeu no formato errado, e quem valida adiante
    # rejeitaria corretamente o que não é objeto.
    try:
        json.loads(despido)
    except json.JSONDecodeError:
        pass
    else:
        return despido
    inicio, fim = despido.find("{"), despido.rfind("}")
    if inicio == -1 or fim <= inicio:
        return None
    return despido[inicio : fim + 1]


# ------------------------------------------------------------ analisador ----
class AnalisadorDeRisco:
    """Converte imagem em `AnaliseRisco` validada, ou em `None`.

    `None` não é falha silenciosa: é a resposta correta quando não há resposta
    confiável. O motivo fica em `ultimos_erros` e no log, já redigido — a chave
    de API nunca entra em nenhum dos dois.
    """

    def __init__(self, provedor: ProvedorMultimodal | None, *, historico: int = 20) -> None:
        self.provedor = provedor
        self._erros: deque[str] = deque(maxlen=historico)

    @property
    def ultimos_erros(self) -> list[str]:
        return list(self._erros)

    def _registrar(self, motivo: str, detalhe: str) -> None:
        mensagem = redigir_segredos(f"{motivo}: {detalhe}")[:400]
        self._erros.append(mensagem)
        logger.warning("llm_analise_descartada", extra={"motivo": motivo})

    def analisar(self, imagem_jpeg: bytes, *, versao: str = "v1") -> AnaliseRisco | None:
        if self.provedor is None:
            self._registrar("sem_provedor", "camada LLM desligada")
            return None
        try:
            prompt = carregar_prompt(versao)
        except KeyError as exc:
            self._registrar("versao_invalida", str(exc))
            return None
        try:
            cru = self.provedor.analisar(imagem_jpeg, prompt)
        except Exception as exc:  # noqa: BLE001  (timeout, DNS, 500, cota: nada escapa)
            self._registrar("provedor_falhou", f"{type(exc).__name__}: {exc}")
            return None
        return self.validar(cru)

    def validar(self, cru: str) -> AnaliseRisco | None:
        """Texto cru -> análise tipada. Separado para os golden tests offline."""
        bruto = extrair_json(cru or "")
        if bruto is None:
            self._registrar("sem_json", (cru or "")[:200])
            return None
        try:
            dados = json.loads(bruto)
        except json.JSONDecodeError as exc:
            self._registrar("json_invalido", str(exc))
            return None
        if not isinstance(dados, dict):
            self._registrar("json_nao_e_objeto", type(dados).__name__)
            return None
        try:
            return AnaliseRisco.model_validate(dados)
        except ValidationError as exc:
            self._registrar("fora_do_schema", str(exc.errors(include_url=False)))
            return None


__all__ = [
    "EPIS_CONHECIDOS",
    "MODELO_PADRAO",
    "NIVEIS_DE_RISCO",
    "AnaliseRisco",
    "AnalisadorDeRisco",
    "ProvedorFake",
    "ProvedorGemini",
    "ProvedorIndisponivel",
    "ProvedorMultimodal",
    "carregar_prompt",
    "extrair_json",
    "redigir_segredos",
    "versoes_de_prompt",
]
