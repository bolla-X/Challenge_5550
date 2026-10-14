"""Trilhas compactas por câmera para o simulador "E se?" (X2, MISSÃO 2).

Uma linha JSON por análise nova: instante, e por pessoa rastreada o ID, o pé
e o centro da caixa (normalizados) e o estado de cada EPI. SEM imagem.
Arquivo rotativo com teto: `trilha.jsonl` cresce até `teto_bytes`, vira
`trilha.1.jsonl` e assim por diante até `arquivos`; o mais antigo sai.

Formato de uma linha (curto de propósito, ~60 B por pessoa):
    {"t": 1760412345.12, "p": [[id, pe_x, pe_y, cx, cy, {"helmet": "m", ...}], ...]}
Estados: m = faltando, i = incorreto, o = ok, n = não verificável/desconhecido.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Iterator

CODIGO = {"missing": "m", "incorrect": "i", "ok": "o", "present": "o", "detected": "o"}


def _codigo(status: str | None) -> str:
    return CODIGO.get(str(status or ""), "n")


def numero(person_id: Any) -> Any:
    if isinstance(person_id, str) and person_id.startswith("person_") and person_id[7:].isdigit():
        return int(person_id[7:])
    return person_id


class GravadorDeTrilhas:
    def __init__(self, pasta: Path, *, teto_bytes: int = 16 * 1024 * 1024, arquivos: int = 4) -> None:
        self.pasta = Path(pasta)
        self.teto_bytes = max(64 * 1024, int(teto_bytes))
        self.arquivos = max(1, int(arquivos))
        self._lock = threading.Lock()
        # Arquivo fica aberto: abrir/fechar a cada análise custava ~6 ms no
        # Windows (medido no teste de rotação). Flush a cada segundo e antes de ler.
        self._arq = None
        self._tamanho = 0
        self._ultimo_flush = 0.0

    @property
    def atual(self) -> Path:
        return self.pasta / "trilha.jsonl"

    def _fechar(self) -> None:
        if self._arq is not None:
            self._arq.close()
            self._arq = None

    def _abrir(self) -> None:
        if self._arq is None:
            self.pasta.mkdir(parents=True, exist_ok=True)
            self._arq = self.atual.open("a", encoding="utf-8")
            self._tamanho = self.atual.stat().st_size

    def _rotacionar(self) -> None:
        self._fechar()
        for i in range(self.arquivos - 1, 0, -1):
            origem = self.pasta / ("trilha.jsonl" if i == 1 else f"trilha.{i - 1}.jsonl")
            destino = self.pasta / f"trilha.{i}.jsonl"
            if origem.exists():
                origem.replace(destino)
        if self.arquivos == 1 and self.atual.exists():
            self.atual.unlink()

    def registrar(self, t: float, pessoas: list[dict[str, Any]], largura: int, altura: int) -> None:
        linhas = []
        for pessoa in pessoas or []:
            caixa = pessoa.get("box") or {}
            if not caixa:
                continue
            w, h = max(1, largura), max(1, altura)
            pe = ((caixa["x1"] + caixa["x2"]) / 2 / w, caixa["y2"] / h)
            centro = ((caixa["x1"] + caixa["x2"]) / 2 / w, (caixa["y1"] + caixa["y2"]) / 2 / h)
            epis = {k: _codigo((v or {}).get("status")) for k, v in (pessoa.get("ppe") or {}).items()
                    if (v or {}).get("status") not in ("disabled", "unsupported")}
            linhas.append([numero(pessoa.get("id")), round(pe[0], 4), round(pe[1], 4), round(centro[0], 4),
                           round(centro[1], 4), epis])
        registro = json.dumps({"t": round(t, 3), "p": linhas}, separators=(",", ":"), ensure_ascii=False) + "\n"
        tamanho = len(registro.encode("utf-8"))
        with self._lock:
            self._abrir()
            if self._tamanho and self._tamanho + tamanho > self.teto_bytes:
                self._rotacionar()
                self._abrir()
            assert self._arq is not None
            self._arq.write(registro)
            self._tamanho += tamanho
            agora = time.monotonic()
            if agora - self._ultimo_flush >= 1.0:
                self._arq.flush()
                self._ultimo_flush = agora

    def fechar(self) -> None:
        with self._lock:
            self._fechar()

    def ler(self, desde: float | None = None, ate: float | None = None) -> Iterator[dict[str, Any]]:
        """Registros em ordem de tempo (do arquivo mais antigo para o atual)."""
        with self._lock:
            if self._arq is not None:
                self._arq.flush()
            caminhos = [self.pasta / f"trilha.{i}.jsonl" for i in range(self.arquivos - 1, 0, -1)] + [self.atual]
            caminhos = [c for c in caminhos if c.exists()]
            conteudos = [c.read_text(encoding="utf-8") for c in caminhos]
        for texto in conteudos:
            for linha in texto.splitlines():
                try:
                    registro = json.loads(linha)
                except ValueError:
                    continue  # linha cortada no meio (processo morto escrevendo)
                if desde is not None and registro["t"] < desde:
                    continue
                if ate is not None and registro["t"] > ate:
                    continue
                yield registro

    def tamanho_total(self) -> int:
        return sum(c.stat().st_size for c in self.pasta.glob("trilha*.jsonl")) if self.pasta.exists() else 0
