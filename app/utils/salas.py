"""Escopo de câmera no WebSocket, via rooms do Socket.IO.

O escopo do Operador nasceu só no REST (`app/utils/auth.py::camera_scope`).
Todo `socketio.emit` do projeto era broadcast, então o operador da Portaria —
que recebe 404 ao pedir a câmera do Almoxarifado por HTTP — recebia
`active_alerts`, `analysis` e `compliance_state` do Almoxarifado pelo socket,
~12 vezes por segundo. Proteger só o REST deixava a porta dos fundos aberta.

O desenho é o mais simples que funciona:

- Técnico e Supervisor entram na sala `parque` e recebem tudo, porque é o
  trabalho deles.
- Operador COM setor entra só em `camera:<id>`.
- Operador SEM setor não entra em sala nenhuma — mesma decisão já tomada no
  REST: conta incompleta não vira acesso amplo.

Evento de câmera sai em **duas** emissões (uma para `parque`, uma para
`camera:<id>`) em vez de uma. Emitir para sala vazia NÃO é de graça: o
python-socketio 5.16.4 serializa o pacote antes de procurar quem está na sala
(`socketio/manager.py`, `Manager.emit`: `pkt.encode()` vem antes de
`get_participants`) — por isso `_tem_alguem` pula a emissão quando a sala está
vazia (correção de 13/10; este comentário dizia o contrário). E a alternativa — privilegiado entrar em todas as salas de câmera — exigiria
rastrear sids e sincronizar quando uma câmera nova é cadastrada. Não vale a
complexidade.
"""

from __future__ import annotations

from typing import Any

from app.models import ROLE_OPERATOR, User

# Quem ve o parque inteiro. Tambem e onde cai a sessao quando AUTH_REQUIRED
# esta desligado (teste automatizado), senao desligar autenticacao faria os
# eventos nao chegarem em ninguem.
SALA_PARQUE = "parque"


def sala_da_camera(camera_id: int | None) -> str:
    return f"camera:{camera_id}"


def salas_do_usuario(usuario: User | None) -> list[str]:
    """Em quais salas este socket entra ao conectar.

    `None` significa autenticacao desligada — nao "usuario anonimo". Socket sem
    sessao com autenticacao ligada e recusado antes de chegar aqui
    (`app/__init__.py::_authorize_socket`).
    """
    if usuario is None:
        return [SALA_PARQUE]
    if usuario.role == ROLE_OPERATOR:
        return [sala_da_camera(usuario.camera_id)] if usuario.camera_id is not None else []
    return [SALA_PARQUE]


def _tem_alguem(socketio: Any, sala: str, namespace: str = "/") -> bool:
    """False só quando dá para AFIRMAR que a sala está vazia.

    Lê `server.manager.rooms` do python-socketio. Sem essa estrutura (dublê de
    teste, outra implementação), emite como antes.
    """
    gerente = getattr(getattr(socketio, "server", None), "manager", None)
    salas = getattr(gerente, "rooms", None)
    if not isinstance(salas, dict):
        return True
    return bool((salas.get(namespace) or {}).get(sala))


def sala_de_foco(camera_id: int | None) -> str:
    """Sala de quem está com a câmera ABERTA na tela (telemetria de alta frequência)."""
    return f"foco:{camera_id}"


def emitir_para_foco(socketio: Any, evento: str, payload: Any, camera_id: int | None) -> None:
    """Telemetria de alta frequência (`analysis`, `compliance_state`) só para quem a vê.

    Antes ia para o parque inteiro: com 4 câmeras a 8 Hz, todo navegador
    recebia 32 eventos/s e descartava 24 no cliente (`belongsToFocusedCamera`).
    O escopo continua garantido: só entra em `foco:<id>` quem tem permissão
    sobre a câmera (ver `app/__init__.py::_focar`).
    """
    if camera_id is not None and _tem_alguem(socketio, sala_de_foco(camera_id)):
        socketio.emit(evento, payload, to=sala_de_foco(camera_id))


def emitir_para_camera(socketio: Any, evento: str, payload: Any, camera_id: int | None) -> None:
    """Emite um evento so para quem tem escopo sobre `camera_id`.

    Sem `camera_id` o evento alcanca apenas o parque: um evento que nao sabe de
    qual camera e nao pode ser entregue a um operador restrito a uma.
    """
    if _tem_alguem(socketio, SALA_PARQUE):
        socketio.emit(evento, payload, to=SALA_PARQUE)
    if camera_id is not None and _tem_alguem(socketio, sala_da_camera(camera_id)):
        socketio.emit(evento, payload, to=sala_da_camera(camera_id))
