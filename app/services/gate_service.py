"""Modo portaria: aprova a entrada só se TODO EPI exigido estiver presente.

Diferente do alerta (que espera, confirma e resolve com histerese), a portaria
precisa de um veredito a cada instante e de uma regra dura: na dúvida, NEGA.
Um EPI que não pode ser verificado (feature desligada, classe que o modelo não
tem, região do corpo fora do quadro) conta como ausente.
"""
from __future__ import annotations

from collections import deque
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


# --- Portal de Entrada (G1) -------------------------------------------------
#
# A portaria acima é controle de acesso: na dúvida, NEGA. O portal é o
# check-in de EPI diante da câmera, e diz a verdade item a item: confirmado,
# faltando, ou "não verificável neste enquadramento" (pés ou mãos fora do
# quadro, EPI que o modelo não detecta). Não detectado não é ausente — e não
# verificável não é confirmado: só libera com TODO item verificável confirmado
# e pelo menos um item verificado.

CONFIRMADO, FALTANDO, NAO_VERIFICAVEL = "confirmado", "faltando", "nao_verificavel"
# Que parte do corpo cada EPI precisa ver, e por quais keypoints COCO.
REGIAO_DO_EPI = {
    "helmet": "cabeca", "glasses": "cabeca", "mask": "cabeca", "ear_protection": "cabeca",
    "vest": "tronco", "gloves": "maos", "safety_shoe": "pes",
}
KEYPOINTS_DA_REGIAO = {
    "cabeca": ("nose", "left_eye", "right_eye"),
    "tronco": ("left_shoulder", "right_shoulder", "left_hip", "right_hip"),
    "maos": ("left_wrist", "right_wrist"),
    "pes": ("left_ankle", "right_ankle"),
}
MOTIVO_DA_REGIAO = {
    "cabeca": "cabeça fora do quadro",
    "tronco": "tronco fora do quadro",
    "maos": "mãos fora do quadro",
    "pes": "pés fora do quadro",
}
# Caixa encostada na borda (fração do quadro): a região naquela borda pode
# estar cortada.
MARGEM_DA_BORDA = 0.02


def _regiao_visivel(regiao: str, caixa: dict[str, Any], frame_shape, pose) -> bool:
    altura, largura = frame_shape[:2]
    if regiao == "pes" and caixa.get("y2", 0) >= altura * (1 - MARGEM_DA_BORDA):
        return False
    if regiao == "cabeca" and caixa.get("y1", 0) <= altura * MARGEM_DA_BORDA:
        return False
    if pose is None or not getattr(pose, "found", False):
        # Sem esqueleto, só a borda decide; mãos ficam por conta do detector.
        return True
    nomes = KEYPOINTS_DA_REGIAO[regiao]
    vistos = [lm for lm in (pose.by_name(n) for n in nomes) if lm is not None and lm.visibility >= 0.4]
    # Mãos e pés: as duas; cabeça e tronco: basta metade dos pontos.
    return len(vistos) == len(nomes) if regiao in ("maos", "pes") else len(vistos) * 2 >= len(nomes)


def _explicar(chave: str, estado: dict[str, Any], status: str | None, caixa: dict[str, Any],
              descartadas: list[dict[str, Any]], pisos: dict[str, float]) -> str:
    """Por que o item ficou assim, em uma frase (Raio-X do portal, X9). Só o que o sistema registrou."""
    conf = float(estado.get("confidence") or 0.0)
    if status == "ok":
        return f"visto com confiança {conf:.2f}".replace(".", ",")
    if status == "incorrect":
        return f"visto com {conf:.2f}, mas fora da posição esperada".replace(".", ",")
    dentro = [
        d for d in descartadas
        if d.get("l") == chave and caixa
        and caixa.get("x1", 0) <= (d["b"][0] + d["b"][2]) / 2 <= caixa.get("x2", 0)
        and caixa.get("y1", 0) <= (d["b"][1] + d["b"][3]) / 2 <= caixa.get("y2", 0)
    ]
    if dentro:
        melhor = max(dentro, key=lambda d: d.get("c", 0))
        return f"o modelo viu com {melhor['c']:.2f} ({melhor['m']}) e descartou".replace(".", ",", 1)
    return "o modelo não viu este item na pessoa"


def avaliar_portal(compliance: dict[str, Any] | None, exigidos: list[str], frame_shape, poses=(),
                   descartadas: list[dict[str, Any]] | None = None, pisos: dict[str, float] | None = None) -> dict[str, Any]:
    """Estado bruto do portal num quadro, para a pessoa mais próxima (maior caixa)."""
    pessoas = (compliance or {}).get("people") or []
    if not pessoas:
        return {"verdict": "waiting", "itens": [], "people": 0, "track_id": None}

    def area(p):
        c = p.get("box") or {}
        return max(0, c.get("x2", 0) - c.get("x1", 0)) * max(0, c.get("y2", 0) - c.get("y1", 0))

    pessoa = max(pessoas, key=area)
    pose = next((p for p in poses or () if getattr(p, "person_id", None) == pessoa.get("id")), None)
    itens = []
    for chave in exigidos:
        estado = (pessoa.get("ppe") or {}).get(chave) or {}
        status = estado.get("status")
        regiao = REGIAO_DO_EPI.get(chave, "tronco")
        explicacao = _explicar(chave, estado, status, pessoa.get("box") or {}, descartadas or [], pisos or {})
        if status == "ok":
            itens.append({"key": chave, "estado": CONFIRMADO, "motivo": None, "explicacao": explicacao})
        elif status in ("disabled", "unsupported"):
            itens.append({"key": chave, "estado": NAO_VERIFICAVEL, "motivo": "o modelo não verifica este EPI"})
        elif not _regiao_visivel(regiao, pessoa.get("box") or {}, frame_shape, pose):
            itens.append({"key": chave, "estado": NAO_VERIFICAVEL, "motivo": MOTIVO_DA_REGIAO[regiao]})
        else:
            motivo = "fora da posição esperada" if status == "incorrect" else None
            itens.append({"key": chave, "estado": FALTANDO, "motivo": motivo, "explicacao": explicacao})
    verificaveis = [i for i in itens if i["estado"] != NAO_VERIFICAVEL]
    liberado = bool(verificaveis) and all(i["estado"] == CONFIRMADO for i in verificaveis)
    return {"verdict": "approved" if liberado else "denied", "itens": itens, "people": len(pessoas),
            "track_id": pessoa.get("track_id")}


class PortalState(GateState):
    """Mesmo debounce da portaria, contado em ANÁLISES novas (não em quadros
    publicados, que repetem a mesma análise). Conta os check-ins liberados.

    Análise sem ninguém detectado no meio de uma confirmação ("não detectado"
    não é "ausente") não zera a sequência: até `ausencias_toleradas` seguidas
    ficam neutras — não contam como confirmação nem a interrompem. Uma análise
    que VÊ a pessoa sem o EPI zera, como antes. Medido nas sequências brutas do
    portal com 4 câmeras (ADENDO 2, CHANGELOG): o pior caso caiu de 27 para 5
    análises.
    """

    def __init__(self, confirmacoes: int = 3, ausencias_toleradas: int = 2) -> None:
        self.CONFIRMACAO = {"approved": confirmacoes, "denied": 2, "waiting": 3}
        self.ausencias_toleradas = max(0, int(ausencias_toleradas))
        self.checkins = 0
        super().__init__()

    def reset(self) -> None:
        super().reset()
        self.atual = {"verdict": "waiting", "itens": [], "people": 0, "track_id": None}
        # Diagnóstico do tempo até "Liberado": veredito BRUTO de cada análise
        # desde o último reset e, nas negadas, qual item faltou.
        self.brutos = {"approved": 0, "denied": 0, "waiting": 0}
        self.faltas: dict[str, int] = {}
        # As últimas análises, em ordem: (veredito, track_id, itens confirmados) — A/D/W.
        self.sequencia: deque[tuple[str, Any, list[str]]] = deque(maxlen=120)
        self._ausencias = 0

    def atualizar(self, bruto: dict[str, Any]) -> dict[str, Any]:
        self.brutos[bruto["verdict"]] = self.brutos.get(bruto["verdict"], 0) + 1
        self.sequencia.append((bruto["verdict"], bruto.get("track_id"),
                               [i["key"] for i in bruto.get("itens") or [] if i["estado"] == CONFIRMADO]))
        for item in bruto.get("itens") or []:
            if item["estado"] == FALTANDO:
                self.faltas[item["key"]] = self.faltas.get(item["key"], 0) + 1
        confirmando = self._candidato == "approved" and self._streak > 0
        if bruto["verdict"] == "waiting" and confirmando and self._ausencias < self.ausencias_toleradas:
            self._ausencias += 1
            self.atual.pop("checkin_novo", None)
            return self.atual
        self._ausencias = 0
        antes = self.atual["verdict"]
        atual = super().atualizar(bruto)
        if atual["verdict"] == "approved" and antes != "approved":
            self.checkins += 1
            atual["checkin_novo"] = True
        else:
            atual.pop("checkin_novo", None)
        return atual
