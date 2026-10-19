"""Preparo das cenas do palco que mexem em dados reais (MISSÃO 4, Fase 6).

Cada função devolve `None` quando deu certo, ou o TEXTO de contingência que o
palco mostra no lugar da legenda ("o que não está acontecendo"). Quem chama
(`app/api/palco.py`) roda isto em thread e nunca deixa uma falha derrubar a
apresentação. As dependências entram por parâmetro (monitor, relógio, `dormir`)
para o teste exercitar o preparo sem câmera nem espera.

Permissão de demonstração: nasce ao entrar na cena "Permissão com vigia" e é
encerrada ao sair (ou quando o preparo seguinte a encontra vencida). É uma PT
de verdade no banco, com responsável "Equipe de demonstração" e criada por
`POR_PALCO`: aparece em /permissoes e no histórico como qualquer outra, e é
reconhecível, para o palco nunca encerrar a PT de um técnico.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from app.models import PERMISSAO_ATIVA, PermissaoDeTrabalho, utc_now
from app.services import permissoes as servico_permissoes

POR_PALCO = "palco (apresentação)"
RESPONSAVEL_DA_DEMO = "Equipe de demonstração"
JANELA_DA_PERMISSAO = timedelta(hours=1)
# O vigia fica no canto inferior esquerdo; a área de risco da demo (Pátio) é a metade direita.
AREA_DO_VIGIA = [[0.02, 0.62], [0.22, 0.62], [0.22, 0.96], [0.02, 0.96]]
DESCRICAO_DA_PERMISSAO = "Demonstração: entrada em espaço confinado, com vigia na área marcada no canto da imagem."

FALHA_DE_PREPARO = "O preparo desta cena falhou (veja o log do servidor): o que aparece pode não refletir o roteiro."


# ------------------------------------------------------------ saúde visual ---
def redefinir_referencia_visual(
    monitor: Any, camera_id: int, *, tentativas: int = 6, espera_s: float = 1.0, dormir: Callable[[float], None] = time.sleep
) -> str | None:
    """"Esta é a imagem certa agora": a cena "Tape a câmera" não herda a referência de uma cena anterior.

    A câmera pode ter acabado de ligar (sem quadro ainda): tenta de novo por até `tentativas * espera_s`.
    """
    try:
        worker = monitor.worker_da_camera(camera_id)
    except LookupError:
        return "A câmera da cena não está ligada: a cena mostra o vídeo, mas não acusa obstrução."
    for tentativa in range(max(1, tentativas)):
        try:
            estado = worker.redefinir_referencia_visual()
        except ValueError:  # ainda sem imagem
            if tentativa < tentativas - 1:
                dormir(espera_s)
            continue
        if estado.get("ativa") is False:
            return "A saúde visual está desligada neste ambiente: a cena mostra o vídeo, mas não acusa obstrução."
        return None
    return "A câmera ainda não entregou imagem: ao tapar a lente, o alerta pode demorar ou não aparecer."


# --------------------------------------------------- permissão de demonstração ---
def dados_da_permissao_de_demonstracao(camera_id: int, agora: datetime) -> dict[str, Any]:
    """Corpo de emissão: espaço confinado, janela de 1 h que já começou, área do vigia num canto, sem EPI exigido."""
    inicio = agora - timedelta(minutes=1)  # já vigente ao entrar na cena, sem depender do relógio fino
    return {
        "tipo": "espaco_confinado",
        "camera_id": camera_id,
        "descricao": DESCRICAO_DA_PERMISSAO,
        "responsavel": RESPONSAVEL_DA_DEMO,
        "inicio": inicio,
        "fim": inicio + JANELA_DA_PERMISSAO,
        "epis_exigidos": [],
        "exige_vigia": True,
        "area_vigia": AREA_DO_VIGIA,
    }


def permissoes_de_demonstracao_ativas(camera_id: int | None = None) -> list[PermissaoDeTrabalho]:
    """As PT ativas que o palco emitiu. Usa a leitura de gestão (qualquer status) e filtra pelo selo da demo."""
    ativas = servico_permissoes.listar_gerenciamento_permissoes(camera_id=camera_id, status=PERMISSAO_ATIVA, limite=500)
    return [p for p in ativas if p.criada_por == POR_PALCO and p.responsavel == RESPONSAVEL_DA_DEMO]


def encerrar_permissoes_de_demonstracao(agora: datetime | None = None, *, so_vencidas: bool = False) -> int:
    """Encerra as PT de demonstração ativas (só as vencidas, se pedido). Devolve quantas encerrou."""
    agora = agora or utc_now()
    encerradas = 0
    for permissao in permissoes_de_demonstracao_ativas():
        if so_vencidas and permissao.vigente(agora):
            continue
        try:
            servico_permissoes.encerrar_permissao(permissao.id, por=POR_PALCO, agora=agora)
        except servico_permissoes.PermissaoInvalida:  # alguém encerrou no meio: o guarda de escrita recusou, e está certo
            continue
        encerradas += 1
    return encerradas


def abrir_permissao_de_demonstracao(camera_id: int, agora: datetime | None = None) -> PermissaoDeTrabalho:
    """Emite a PT da cena. Idempotente: entrar de novo na cena reaproveita a vigente e limpa as vencidas."""
    agora = agora or utc_now()
    encerrar_permissoes_de_demonstracao(agora, so_vencidas=True)
    vigentes = [p for p in permissoes_de_demonstracao_ativas(camera_id) if p.vigente(agora)]
    if vigentes:
        return vigentes[0]
    permissao, _avisos = servico_permissoes.emitir_permissao(
        dados_da_permissao_de_demonstracao(camera_id, agora), criada_por=POR_PALCO, agora=agora
    )
    return permissao
