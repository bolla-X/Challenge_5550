"""Modo portaria: aprova a entrada só se TODO EPI exigido estiver presente.

Diferente do alerta (que espera, confirma e resolve com histerese), a portaria
precisa de um veredito a cada instante e de uma regra dura: na dúvida, NEGA.
Um EPI que não pode ser verificado (feature desligada, classe que o modelo não
tem, região do corpo fora do quadro) conta como ausente.
"""
from __future__ import annotations

from typing import Any

PPE_KEYS = ("helmet", "vest", "gloves", "glasses", "mask", "safety_shoe", "ear_protection")


def normalizar_exigidos(valor: Any) -> list[str] | None:
    """None = câmera fora do modo portaria; lista = EPIs obrigatórios."""
    if valor is None:
        return None
    if not isinstance(valor, (list, tuple)):
        raise ValueError("'required' deve ser uma lista de EPIs.")
    itens: list[str] = []
    for item in valor:
        if item not in PPE_KEYS:
            raise ValueError(f"EPI desconhecido: {item!r}. Válidos: {', '.join(PPE_KEYS)}.")
        if item not in itens:
            itens.append(item)
    if not itens:
        raise ValueError("Escolha ao menos um EPI obrigatório.")
    return itens


def avaliar_quadro(compliance: dict[str, Any] | None, exigidos: list[str]) -> dict[str, Any]:
    """Veredito BRUTO de um quadro (sem debounce)."""
    pessoas = (compliance or {}).get("people") or []
    if not pessoas:
        return {"verdict": "waiting", "missing": [], "people": 0}
    faltando: list[str] = []
    for pessoa in pessoas:
        ppe = pessoa.get("ppe") or {}
        for chave in exigidos:
            if (ppe.get(chave) or {}).get("status") != "ok" and chave not in faltando:
                faltando.append(chave)
    return {"verdict": "denied" if faltando else "approved", "missing": faltando, "people": len(pessoas)}


class GateState:
    """Estabiliza o veredito: só muda depois de N quadros seguidos iguais.

    Aprovar exige mais quadros que negar: liberar por engano é o erro caro.
    """

    CONFIRMACAO = {"approved": 8, "denied": 3, "waiting": 12}

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.atual: dict[str, Any] = {"verdict": "waiting", "missing": [], "people": 0}
        self._candidato: str | None = None
        self._streak = 0

    def atualizar(self, bruto: dict[str, Any]) -> dict[str, Any]:
        veredito = bruto["verdict"]
        if veredito == self.atual["verdict"]:
            self.atual = dict(bruto)  # mesmo veredito: só acompanha a lista de faltantes
            self._candidato, self._streak = None, 0
            return self.atual
        if veredito == self._candidato:
            self._streak += 1
        else:
            self._candidato, self._streak = veredito, 1
        if self._streak >= self.CONFIRMACAO[veredito]:
            self.atual = dict(bruto)
            self._candidato, self._streak = None, 0
        return self.atual
