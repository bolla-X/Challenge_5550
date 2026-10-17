"""Mensagens em pt-BR para falhas de rede comuns na subida dos servidores embutidos."""

from __future__ import annotations

import errno

# 10048 = WSAEADDRINUSE e 10013 = WSAEACCES (Windows). No Windows, abrir uma porta que
# outro processo já escuta pode vir como "em uso" (10048) ou "acesso negado" (10013),
# conforme as opções do socket do outro lado; os dois significam "esta porta não é sua".
_EM_USO = {errno.EADDRINUSE, 10048, 98, 48}
_SEM_ACESSO = {errno.EACCES, 10013, 13}


def sondar_porta(host: str, porta: int) -> None:
    """Abre e fecha um socket em `host:porta`; lança `OSError` se a porta não estiver livre.

    Falha rápido antes de uma subida cara (o asyncua gasta segundos carregando o
    espaço de endereços padrão antes de tentar o bind).
    """
    familia = socket.AF_INET6 if ":" in host else socket.AF_INET
    with socket.create_server((host, porta), family=familia):
        pass


def descrever_falha_de_bind(exc: BaseException, servico: str, host: str, porta: int) -> str:
    """Mensagem legível para a falha de abrir `host:porta` de `servico`."""
    causa = exc.__cause__ if isinstance(exc.__cause__, OSError) else exc
    if isinstance(causa, OSError):
        codigo = getattr(causa, "winerror", None) or causa.errno
        if codigo in _EM_USO:
            return f"Porta {porta} já está em uso em {host}: outro programa (ou outra instância) escuta nela. Servidor {servico} não iniciou."
    