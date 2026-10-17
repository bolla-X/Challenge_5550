"""Limite simples por endereço, em memória, para rotas públicas (sem sessão).

Janela deslizante: cada endereço pode registrar até `maximo` ocorrências dentro
de `janela_s` segundos. Nada vai a disco e nenhum IP é gravado no banco: o estado
morre com o processo, e é por instância do app (guardado em `app.extensions`).

O relógio entra por parâmetro (`agora`) para o teste avançar o tempo sem dormir.
Atrás de um proxy reverso, `request.remote_addr` é o do proxy: quem implanta deve
configurar o `ProxyFix` do Werkzeug. Este módulo NÃO lê `X-Forwarded-For` sozinho,
porque qualquer cliente poderia forjá-lo e escapar do limite.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Callable

# Teto de endereços acompanhados ao mesmo tempo: sem ele, um atacante com muitos
# endereços faria o dicionário crescer sem limite.
MAXIMO_DE_ENDERECOS = 5000


class LimitePorIp:
    def __init__(self, maximo: int, janela_s: float, agora: Callable[[], float] = time.monotonic) -> None:
        self.maximo = max(1, int(maximo))
        self.janela_s = float(janela_s)
        self._agora = agora
        self._ocorrencias: dict[str, deque[float]] = {}
        self._trava = threading.Lock()

    def _podar(self, ip: str, agora: float) -> deque[float]:
        fila = self._ocorrencias.get(ip)
        if fila is None:
            return deque()
        while fila and agora - fila[0] >= self.janela_s:
            fila.popleft()
        if not fila:
            self._ocorrencias.pop(ip, None)
        return fila

    def segundos_para_liberar(self, ip: str) -> int:
        """0 quando há vaga; senão, quantos segundos faltam para a mais antiga sair da janela."""
        with self._trava:
            agora = self._agora()
            fila = self._podar(ip, agora)
            if len(fila) < self.maximo:
                return 0
            return max(1, int(self.janela_s - (agora - fila[0])) + 1)

    def registrar(self, ip: str) -> None:
        """Conta uma ocorrência aceita para `ip`."""
        with self._trava:
            agora = self._agora()
            if ip not in self._ocorrencias and len(self._ocorrencias) >= MAXIMO_DE_ENDERECOS:
                self._limpar_expirados(agora)
                if len(self._ocorrencias) >= MAXIMO_DE_ENDERECOS:
                    # Tudo ainda vigente: descarta o mais antigo (o dicionário preserva a ordem de entrada).
                    self._ocorrencias.pop(next(iter(self._ocorrencias)))
            self._ocorrencias.setdefault(ip, deque()).append(agora)

    def _limpar_expirados(self, agora: float) -> None:
        for ip in list(self._ocorrencias):
            self._podar(ip, agora)
