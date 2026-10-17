"""Texto que o usuário lê: concordância de número em mensagens do backend."""

from __future__ import annotations


def pluralizar(n: int, singular: str, plural: str | None = None) -> str:
    """Contagem com o substantivo no número certo: "1 alerta", "3 alertas".

    Plurais irregulares vão no terceiro argumento: pluralizar(2, "missão", "missões").
    Mesma regra de frontend/src/utils/formato.ts (pluralizar).
    """
    return f"{n} {singular if n == 1 else (plural or singular + 's')}"
