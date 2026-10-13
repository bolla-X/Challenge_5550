"""Linha do tempo de conformidade por ID de rastreio (F2).

Responde "o que aconteceu com a Pessoa 3 nos últimos minutos?": quando ela
apareceu sem capacete, quando colocou, quando entrou na zona, quando caiu.

- Só MUDANÇAS: um evento quando o estado da pessoa muda, não um por análise.
- Memória limitada: `max_eventos` por ID e `max_ids` IDs (o mais antigo sai).
- ID de rastreio NÃO é identidade: some quando a pessoa sai de cena e volta
  com outro número. Nada aqui reconhece ninguém, e a tela diz isso.
"""

from __future__ import annotations

import threading
from collections import OrderedDict, deque
from typing import Any


def _estado(pessoa: dict[str, Any]) -> dict[str, Any]:
    ppe = {
        chave: item.get("status")
        for chave, item in (pessoa.get("ppe") or {}).items()
        if item.get("status") not in ("disabled", "unsupported")
    }
    return {
        "ppe": ppe,
        "queda": bool((pessoa.get("pose") or {}).get("fallen")),
        "zona": (pessoa.get("risk_area") or {}).get("status"),
    }


class LinhaDoTempoPorId:
    def __init__(self, *, max_eventos: int = 120, max_ids: int = 64) -> None:
        self.max_eventos = max(1, int(max_eventos))
        self.max_ids = max(1, int(max_ids))
        self._por_id: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._lock = threading.Lock()

    def limpar(self) -> None:
        with self._lock:
            self._por_id.clear()

    def registrar(self, pessoas: list[dict[str, Any]], agora: float) -> None:
        with self._lock:
            for pessoa in pessoas or []:
                pid = pessoa.get("id")
                if not pid:
                    continue
                estado = _estado(pessoa)
                registro = self._por_id.get(pid)
                if registro is None:
                    registro = {"rotulo": pessoa.get("label") or pid, "eventos": deque(maxlen=self.max_eventos)}
                    self._por_id[pid] = registro
                    while len(self._por_id) > self.max_ids:
                        self._por_id.popitem(last=False)
                self._por_id.move_to_end(pid)
                registro["visto_em"] = agora
                eventos = registro["eventos"]
                if not eventos or {k: v for k, v in eventos[-1].items() if k != "ts"} != estado:
                    eventos.append({"ts": agora, **estado})

    def obter(self, pid: str) -> dict[str, Any] | None:
        with self._lock:
            registro = self._por_id.get(pid)
            if registro is None:
                return None
            return {"id": pid, "rotulo": registro["rotulo"], "visto_em": registro.get("visto_em"),
                    "eventos": list(registro["eventos"])}

    def ids(self) -> list[dict[str, Any]]:
        with self._lock:
            return [{"id": pid, "rotulo": r["rotulo"], "visto_em": r.get("visto_em"), "eventos": len(r["eventos"])}
                    for pid, r in reversed(self._por_id.items())]
