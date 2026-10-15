"""Modo Apresentação — palco (X6, MISSÃO 2).

O roteiro mora AQUI (uma fonte só): a tela `/palco` e o controle do celular
(`/palco/controle`) leem a mesma lista e o mesmo estado. O teclado do
notebook e o celular mudam a cena pelo servidor; se o celular falhar, o
teclado continua funcionando sozinho.

Cada cena declara como se prepara, de forma determinística:
- `camera`: qual câmera fica em foco (nome; a primeira que existir);
- `reiniciar`: a gravação recomeça do início ao entrar na cena (o evento da
  gravação — a queda, a aproximação — acontece sempre no mesmo segundo);
- `raiox`: a cena liga o Modo Raio-X;
- `velocidade` e `inicio_s`: a gravação toca em câmera lenta, a partir desse
  segundo (cena "Queda", ADENDO 2 da MISSÃO 2). A queda da gravação fica
  ~0,8 s no chão; a 0,25× são ~3 s, e a regra de emergência (2 análises
  seguidas) confirma ao vivo. A tela mostra "GRAVAÇÃO · 0,25×" sobre o vídeo.
- `ativas`: quais câmeras continuam analisando durante a cena — "todas", ou
  "cena" (só a câmera da cena; as outras ficam "pausadas pela apresentação"
  até sair dela). O Portal usa "cena": com as 4 câmeras disputando a máquina,
  a pessoa diante do portal esperava a vez (ADENDO 3 da MISSÃO 2). A Queda
  também: a pessoa fica ~3 s no chão a 0,25× e a regra pede 2 análises
  seguidas; disputando com as outras, a câmera dela teve trechos de 5 s sem
  análise e o alerta não fechava (medido no E2E isolado). Fora do palco nada
  muda: o agendador dá ao foco pelo menos 50 % das vagas.
"""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any

ROTEIRO: list[dict[str, Any]] = [
    {"chave": "abertura", "titulo": "VisionEPI", "ativas": "todas",
     "legenda": "Segurança do trabalho que enxerga a planta inteira. Por setor, nunca por pessoa."},
    {"chave": "portal", "titulo": "Portal de Entrada", "ativas": "cena",
     "legenda": "Antes de entrar: cada EPI exigido confirmado, faltando ou não verificável.",
     "camera": ["Portal", "Canteiro"]},
    {"chave": "enganar", "titulo": "Tente enganar a IA", "ativas": "cena",
     "legenda": "Boné no lugar do capacete? O sistema mostra o que viu e por quê.",
     "camera": ["Portal", "Canteiro"], "raiox": True},
    {"chave": "raiox", "titulo": "Raio-X", "ativas": "todas", "legenda": "O que o modelo viu, separado do que o sistema decidiu.",
     "camera": ["Pátio"], "raiox": True},
    {"chave": "gemeo", "titulo": "Gêmeo digital", "ativas": "todas",
     "legenda": "A planta inteira ao vivo: cada pessoa na cor do seu estado, nunca foto."},
    {"chave": "queda", "titulo": "Queda", "ativas": "cena",
     "legenda": "Emergência atribuída a um ID de rastreio, ao vivo e com replay do momento.",
     "camera": ["Escada", "Queda"], "reiniciar": True, "velocidade": 0.25, "inicio_s": 4.0},
    {"chave": "incidente", "titulo": "Incidente e linha causal", "ativas": "todas",
     "legenda": "Alertas agrupados por regra e zona; a história contada só com o que foi registrado.",
     "camera": ["Pátio"]},
    {"chave": "custodia", "titulo": "Cadeia de custódia", "ativas": "todas",
     "legenda": "Cada evidência com SHA-256 encadeado: mudar um byte quebra a cadeia."},
    {"chave": "simulador", "titulo": "Simulador “E se?”", "ativas": "todas",
     "legenda": "Mudar a regra e ver, antes de aplicar, quantos alertas teriam disparado."},
    {"chave": "liga", "titulo": "Liga de Setores", "ativas": "todas",
     "legenda": "Gamificação só com indicadores positivos. Nunca premia “zero alertas”."},
    {"chave": "retrospectiva", "titulo": "Retrospectiva", "ativas": "todas", "legenda": "O turno em stories, com dados reais da equipe."},
    {"chave": "encerramento", "titulo": "Obrigado", "ativas": "todas", "legenda": "Tudo o que você viu roda offline nesta máquina."},
]


@dataclass
class EstadoDoPalco:
    cena: int = 0
    atualizado: float = field(default_factory=time.time)
    seq: int = 0


class Palco:
    def __init__(self) -> None:
        self.estado = EstadoDoPalco()
        # Token do controle pelo celular: muda a cada processo, só vale com o QR da tela.
        self.token = secrets.token_urlsafe(18)
        self._lock = threading.Lock()

    def total(self) -> int:
        return len(ROTEIRO)

    def ir(self, *, acao: str, indice: int | None = None) -> EstadoDoPalco:
        with self._lock:
            atual = self.estado.cena
            if acao == "proxima":
                nova = min(self.total() - 1, atual + 1)
            elif acao == "anterior":
                nova = max(0, atual - 1)
            elif acao == "ir" and indice is not None:
                nova = max(0, min(self.total() - 1, int(indice)))
            else:
                raise ValueError("ação deve ser proxima, anterior ou ir (com índice)")
            if nova != atual:
                self.estado = EstadoDoPalco(cena=nova, seq=self.estado.seq + 1)
            return self.estado

    def publico(self) -> dict[str, Any]:
        cena = ROTEIRO[self.estado.cena]
        return {
            "cena": self.estado.cena,
            "total": self.total(),
            "seq": self.estado.seq,
            "chave": cena["chave"],
            "titulo": cena["titulo"],
            "legenda": cena["legenda"],
            "proxima": ROTEIRO[self.estado.cena + 1]["titulo"] if self.estado.cena + 1 < self.total() else None,
        }


def camera_da_cena(cena: dict[str, Any], cameras_por_nome: dict[str, int]) -> int | None:
    for nome in cena.get("camera") or []:
        if nome in cameras_por_nome:
            return cameras_por_nome[nome]
    return None


def cameras_pausadas(cena: dict[str, Any], cameras_por_nome: dict[str, int]) -> set[int]:
    """Câmeras que a cena pausa: todas menos a dela, se `ativas == "cena"` e ela existir."""
    if cena.get("ativas", "todas") != "cena":
        return set()
    alvo = camera_da_cena(cena, cameras_por_nome)
    if alvo is None:
        return set()  # sem a câmera da cena, pausar as outras só apagaria a planta
    return {cid for cid in cameras_por_nome.values() if cid != alvo}
