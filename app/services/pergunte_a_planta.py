"""Laboratório “Pergunte à planta”: perguntas em português sobre o histórico de alertas.

Desligado por padrão (`LAB_PERGUNTE_ATIVO=false`). Como funciona, e o que NÃO faz:

1. o modelo de linguagem recebe a pergunta e o CATÁLOGO abaixo e devolve só um
   JSON `{"agregacao": nome, "parametros": {...}}`. Ele nunca escreve SQL nem
   código; nome fora do catálogo ou parâmetro inválido é recusado aqui;
2. o servidor executa a agregação escolhida, SOMENTE LEITURA, com os mesmos
   números do relatório de turno (`montar_relatorio`);
3. o modelo redige a resposta a partir desses números; ela volta rotulada como
   "gerada por modelo de linguagem", junto com os números brutos.

A chave do provedor fica só no backend. Sem internet ou sem chave, o laboratório
diz que está indisponível — o resto do sistema não depende dele.
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable

CATALOGO: dict[str, dict[str, Any]] = {
    "resumo_do_turno": {
        "descricao": "totais de alertas, críticos, falsos positivos, reconhecidos e duração mediana",
        "campos": ["total", "criticos", "falsos_positivos", "reconhecidos", "ativos_agora", "duracao_mediana_s"],
    },
    "alertas_por_tipo": {"descricao": "quantos alertas de cada tipo (sem capacete, sem colete, queda...)", "campos": ["por_regra"]},
    "alertas_por_camera": {"descricao": "quantos alertas em cada câmera", "campos": ["por_camera"]},
    "alertas_por_hora": {"descricao": "quantos alertas em cada hora do dia", "campos": ["por_hora"]},
}
HORAS_MIN, HORAS_MAX = 0.5, 72.0


class PerguntaRecusada(ValueError):
    pass


def _prompt_de_plano(pergunta: str) -> str:
    itens = "\n".join(f'- "{nome}": {c["descricao"]}' for nome, c in CATALOGO.items())
    return (
        "Você traduz perguntas sobre alertas de segurança do trabalho em UMA consulta de um catálogo fixo.\n"
        f"Catálogo:\n{itens}\n"
        'Parâmetros: "horas" (número entre 0.5 e 72; padrão 8) e "camera_id" (inteiro, opcional).\n'
        'Responda SOMENTE com JSON no formato {"agregacao": "<nome>", "parametros": {"horas": 8}}. '
        'Se a pergunta não couber no catálogo, responda {"agregacao": null}.\n'
        f"Pergunta: {pergunta}"
    )


def interpretar_plano(texto: str) -> tuple[str, dict[str, Any]]:
    """Valida o JSON do modelo. Qualquer coisa fora do catálogo é recusada."""
    achado = re.search(r"\{.*\}", texto or "", re.DOTALL)
    if not achado:
        raise PerguntaRecusada("o modelo não devolveu uma consulta")
    try:
        plano = json.loads(achado.group(0))
    except ValueError as exc:
        raise PerguntaRecusada("o modelo não devolveu JSON válido") from exc
    nome = plano.get("agregacao")
    if nome not in CATALOGO:
        raise PerguntaRecusada("pergunta fora do que o laboratório sabe responder")
    brutos = plano.get("parametros") or {}
    if not isinstance(brutos, dict):
        raise PerguntaRecusada("parâmetros inválidos")
    try:
        horas = float(brutos.get("horas", 8))
    except (TypeError, ValueError) as exc:
        raise PerguntaRecusada("parâmetro 'horas' inválido") from exc
    parametros: dict[str, Any] = {"horas": min(HORAS_MAX, max(HORAS_MIN, horas))}
    camera = brutos.get("camera_id")
    if camera is not None:
        if isinstance(camera, bool) or not isinstance(camera, int):
            raise PerguntaRecusada("parâmetro 'camera_id' inválido")
        parametros["camera_id"] = camera
    return nome, parametros


def executar(nome: str, parametros: dict[str, Any], montar: Callable[[float, int | None], dict[str, Any]]) -> dict[str, Any]:
    """Só leitura: recorta do relatório de turno os campos da agregação."""
    dados = montar(parametros["horas"], parametros.get("camera_id"))
    alertas = dados["alertas"]
    return {campo: alertas.get(campo) for campo in CATALOGO[nome]["campos"]} | {"janela_h": parametros["horas"]}


def responder(pergunta: str, provedor, montar: Callable[[float, int | None], dict[str, Any]]) -> dict[str, Any]:
    pergunta = (pergunta or "").strip()[:300]
    if not pergunta:
        raise PerguntaRecusada("pergunta vazia")
    nome, parametros = interpretar_plano(provedor.resumir(_prompt_de_plano(pergunta)))
    numeros = executar(nome, parametros, montar)
    texto = provedor.resumir(
        "Responda em até 3 frases, em português, à pergunta abaixo usando SOMENTE os números dados. "
        "Se os números não respondem, diga isso.\n"
        f"Pergunta: {pergunta}\nNúmeros ({nome}): {json.dumps(numeros, ensure_ascii=False)}"
    )
    return {
        "agregacao": nome,
        "parametros": parametros,
        "numeros": numeros,
        "texto": texto.strip(),
        "rotulo": "Resposta gerada por modelo de linguagem a partir dos números ao lado",
    }
