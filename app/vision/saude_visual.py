"""Saúde visual da câmera: obstrução, escuridão, ofuscamento, desfoque e câmera movida (MISSÃO 4, M1).

Sabotagem (mão, fita, papel, giro do suporte) e degradação (queda de luz, lente
suja ou fora de foco) têm uma coisa em comum: o modelo continua rodando e
devolve "nenhuma violação" — o pior resultado possível para um sistema de
segurança, porque parece "tudo certo". Este módulo responde a uma pergunta
anterior à detecção: "a câmera está VENDO a cena que deveria ver?".

É PURO: sem Flask, sem thread, sem I/O. O worker chama `observar` com o quadro
que já tem na mão e lê `estado()`/`alertas()`. O relógio é injetável (`relogio`)
para o teste da histerese não depender de `sleep`.

Custo: tudo roda numa miniatura em cinza de no máximo `lado` px (160 por
padrão) e no máximo uma vez por `intervalo_s` — entre uma medição e outra,
`observar` só compara o relógio e devolve None.

Decisões que não são óbvias:

- **Obstruída ≠ escura.** Uma mão ou fita tampando a lente dá quadro escuro E
  liso; um papel branco dá claro E liso. O que as une é a falta de DETALHE
  (desvio-padrão baixo ou quase todos os pixels numa faixa estreita do
  histograma), não o brilho. Por isso "obstruída" é testada antes e tem
  prioridade sobre escura/ofuscada, que são só histograma (muita sombra ou
  muito estouro numa cena que ainda tem estrutura).
- **Desfoque é RELATIVO à referência.** Cada cena tem uma nitidez própria
  (variância do Laplaciano de um pátio ≠ de um corredor), então um limiar
  absoluto acusaria a cena errada. Compara-se com a referência.
- **Câmera movida exige evidência POSITIVA.** ORB + `findHomography` (RANSAC)
  entre a referência e o quadro atual; "movida" só sai quando a geometria é
  CONFIÁVEL (inliers suficientes e, ao trazer o quadro de volta com ela, o
  fundo da referência reaparece) E o deslocamento/rotação/escala é grande. O
  RANSAC fica com o modelo que explica a maioria dos pontos: numa cena de
  canteiro é o fundo estático, então pessoas andando são outliers e não
  disparam nada. Se ORB acha pontos nos dois quadros mas não consegue casá-los
  (multidão em primeiro plano, oclusão parcial), o veredito é "inconclusivo" =
  NÃO movida: dizer "movida" aí seria o falso positivo que faz o operador
  desligar o alerta. Quadro inconclusivo também não libera uma "movida" já
  confirmada (`Histerese.avancar`). Só quando ORB não tem com o que trabalhar
  (cena lisa, poucos pontos) cai para a correlação normalizada das miniaturas.
  Limite conhecido: com a referência velha e a cena já renovada (muita gente
  entrou/saiu), a câmera movida pode passar como inconclusiva; a saída é
  renovar a referência (`definir_referencia`) em momento calmo.
- **Histerese por tipo, em tempo e não em quadros.** Mesmo motivo do brilho em
  `camera_worker._amostrar_brilho`: o operador percebe segundos, e a mesma
  oclusão acusaria em tempos diferentes numa câmera de 25 fps e numa de 6.
- **Referência provisória.** Sem referência explícita, o primeiro quadro vira
  referência (`referencia_automatica`). Se esse quadro já estava degradado
  (câmera ligada tampada), a referência vale só até o primeiro quadro bom —
  senão a cena de verdade apareceria como "movida" para sempre.
- **Câmera movida/escura continua assim até alguém agir.** A referência não se
  atualiza sozinha; depois de reposicionar a câmera, o operador chama
  `definir_referencia` de novo.
"""

from __future__ import annotations

import hashlib
import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

# --- estados (o valor é o que vai no JSON e no nome da regra: camera_<estado>) ---
OK = "ok"
OBSTRUIDA = "obstruida"
MOVIDA = "movida"
ESCURA = "escura"
OFUSCADA = "ofuscada"
DESFOCADA = "desfocada"

# Ordem = prioridade quando várias condições valem no mesmo quadro.
PRIORIDADE = (OBSTRUIDA, MOVIDA, ESCURA, OFUSCADA, DESFOCADA)

ROTULOS = {
    OK: "OK",
    OBSTRUIDA: "OBSTRUÍDA",
    MOVIDA: "MOVIDA",
    ESCURA: "ESCURA",
    OFUSCADA: "OFUSCADA",
    DESFOCADA: "DESFOCADA",
}
SEVERIDADES = {OBSTRUIDA: "high", MOVIDA: "high", ESCURA: "medium", OFUSCADA: "medium", DESFOCADA: "medium"}
FEATURE = "saude_visual"

# --- limiares (medidos nas fixtures reais; ver o relatório da M1) ---
# Obstruída: falta de detalhe. Desvio-padrão da cinza baixo OU quase todos os
# pixels dentro de uma faixa estreita do histograma, sem borda nenhuma.
LIMIAR_DESVIO_LISO = 6.0
FAIXA_UNIFORME = 24  # largura (em níveis de cinza) da janela do histograma
COBERTURA_UNIFORME = 0.92
LIMIAR_LAPLACIANO_LISO = 6.0
# Escura / ofuscada: fração de pixels nos extremos do histograma.
NIVEL_ESCURO = 20
NIVEL_CLARO = 235
FRACAO_ESCURA = 0.60
FRACAO_CLARA = 0.45
# Desfocada: variância do Laplaciano < fração da referência; com piso absoluto
# (uma referência já lisa não permite concluir nada).
FRACAO_NITIDEZ = 0.35
NITIDEZ_MINIMA_DA_REFERENCIA = 15.0
# Movida.
ORB_PONTOS = 300
ORB_NIVEIS = 4  # miniatura de 160 px: os níveis a mais do padrão (8) caem abaixo de 50 px e só custam tempo
RAZAO_LOWE = 0.75
MIN_CORRESPONDENCIAS = 12  # ORB só "tem com o que trabalhar" com pelo menos isto nos DOIS quadros
MIN_INLIERS = 8
LIMIAR_RANSAC_PX = 3.0
DESLOCAMENTO_MAXIMO = 0.08  # fração do lado maior da miniatura
ROTACAO_MAXIMA_GRAUS = 4.0
ESCALA_MAXIMA = 0.12  # |log(escala)|, ~ ±12 %
ESCALA_PLAUSIVEL = 0.35  # fora disso a pose é degenerada, não uma câmera movida
BLOCO = 16  # lado do bloco da checagem de alinhamento, em px da miniatura
DESVIO_MINIMO_DO_BLOCO = 6.0
NCC_DO_BLOCO = 0.6
MIN_BLOCOS = 4  # blocos texturizados (e visíveis após o alinhamento) para a checagem valer
ALINHAMENTO_MINIMO = 0.88
CORRELACAO_MINIMA = 0.30  # só no fallback, quando ORB não tem pontos
CORRELACAO_SEM_DUVIDA = 0.90  # miniaturas quase idênticas: a câmera não se mexeu, nem se gasta ORB


# Medidas de movimento quando não há comparação a fazer (ou ela não concluiu).
_SEM_MOVIMENTO: dict[str, float] = {
    "correlacao": 0.0,
    "deslocamento": 0.0,
    "rotacao": 0.0,
    "escala": 0.0,
    "inliers": 0,
    "alinhamento": 0.0,
}


@dataclass
class _Referencia:
    """Quadro de referência já reduzido + o que se mede dele uma vez só."""

    cinza: np.ndarray
    pontos: np.ndarray  # (N, 2) float32, coordenadas da miniatura
    descritores: np.ndarray | None
    nitidez: float


def _miniatura_cinza(frame_bgr: np.ndarray, lado: int) -> np.ndarray:
    """Cinza com o lado maior = `lado` (nunca amplia). INTER_AREA: média, não amostragem."""
    cinza = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY) if frame_bgr.ndim == 3 else frame_bgr
    maior = max(cinza.shape[:2])
    if maior <= lado:
        return np.ascontiguousarray(cinza)
    escala = lado / maior
    novo = (max(1, round(cinza.shape[1] * escala)), max(1, round(cinza.shape[0] * escala)))
    return cv2.resize(cinza, novo, interpolation=cv2.INTER_AREA)


def _nitidez(cinza: np.ndarray) -> float:
    return float(cv2.Laplacian(cinza, cv2.CV_32F).var())


def _cobertura_da_faixa(cinza: np.ndarray) -> float:
    """Maior fração de pixels dentro de uma janela de `FAIXA_UNIFORME` níveis do histograma."""
    hist = cv2.calcHist([cinza], [0], None, [256], [0, 256]).ravel()
    acumulado = np.concatenate(([0.0], np.cumsum(hist)))
    janelas = acumulado[FAIXA_UNIFORME:] - acumulado[:-FAIXA_UNIFORME]
    return float(janelas.max() / cinza.size)


def _blocos(img: np.ndarray, ny: int, nx: int) -> np.ndarray:
    """(ny*nx, BLOCO*BLOCO), cada bloco menos a própria média."""
    recorte = img[: ny * BLOCO, : nx * BLOCO].astype(np.float32)
    b = recorte.reshape(ny, BLOCO, nx, BLOCO).transpose(0, 2, 1, 3).reshape(ny * nx, BLOCO * BLOCO)
    return b - b.mean(axis=1, keepdims=True)


def _alinhamento(alinhado: np.ndarray, referencia: np.ndarray, visivel: np.ndarray) -> float | None:
    """Fração dos blocos texturizados da referência que `alinhado` reproduz (correlação por bloco).

    `visivel` marca os pixels que a homografia trouxe de dentro do quadro (a
    borda que entrou na cena não conta). Pessoa passando estraga alguns
    blocos; uma homografia espúria estraga todos. None = poucos blocos para
    concluir.
    """
    ny, nx = referencia.shape[0] // BLOCO, referencia.shape[1] // BLOCO
    if ny == 0 or nx == 0:
        return None
    r, a = _blocos(referencia, ny, nx), _blocos(alinhado, ny, nx)
    bloco_visivel = (
        visivel[: ny * BLOCO, : nx * BLOCO].reshape(ny, BLOCO, nx, BLOCO).transpose(0, 2, 1, 3).reshape(ny * nx, -1).min(axis=1) > 0
    )
    desvio_r = np.sqrt((r * r).mean(axis=1))
    desvio_a = np.sqrt((a * a).mean(axis=1))
    contam = (desvio_r >= DESVIO_MINIMO_DO_BLOCO) & bloco_visivel
    if int(contam.sum()) < MIN_BLOCOS:
        return None
    ncc = (r * a).mean(axis=1) / np.maximum(desvio_r * desvio_a, 1e-6)
    return float((ncc[contam] >= NCC_DO_BLOCO).mean())


def _arredondar(metricas: dict[str, float | int]) -> dict[str, float | int]:
    return {k: (round(v, 3) if isinstance(v, float) else v) for k, v in metricas.items()}


class Histerese:
    """Transforma observações brutas (uma por medição) num estado CONFIRMADO, por tipo e em tempo.

    - um tipo não-OK só é confirmado depois de `confirmar_s` de observações seguidas desse tipo;
    - um estado confirmado só é liberado depois de `liberar_s` de observações OK seguidas;
    - um tipo que muda no meio da confirmação reinicia a contagem; trocar de um estado confirmado
      para outro não passa por OK (o novo tipo só precisa se confirmar).
    """

    def __init__(self, confirmar_s: float, liberar_s: float) -> None:
        self.confirmar_s = confirmar_s
        self.liberar_s = liberar_s
        self.reiniciar()

    def reiniciar(self) -> None:
        self.estado = OK
        self.desde: float | None = None  # quando começou a sequência que confirmou o estado atual
        self._candidato: str | None = None  # tipo não-OK em confirmação
        self._candidato_desde: float | None = None
        self._ok_desde: float | None = None  # início da sequência de OK que libera o estado

    def avancar(self, bruto: str, agora: float, inconclusivo: bool = False) -> None:
        """`inconclusivo`: o quadro não prova nada sobre "movida" (ver `MonitorDeSaudeVisual._medir_movimento`)."""
        if bruto == OK:
            if inconclusivo and MOVIDA in (self.estado, self._candidato):
                # Quadro sem evidência (multidão, oclusão parcial) não confirma nem libera "movida":
                # senão a mesma câmera movida piscaria entre MOVIDA e OK a cada quadro ruim.
                return
            self._candidato = self._candidato_desde = None
            if self.estado == OK:
                self._ok_desde = None
                return
            if self._ok_desde is None:
                self._ok_desde = agora
            if agora - self._ok_desde >= self.liberar_s:
                self.estado, self.desde, self._ok_desde = OK, None, None
            return

        self._ok_desde = None  # um quadro ruim interrompe a contagem de liberação
        if bruto == self.estado:
            self._candidato = self._candidato_desde = None
            return
        if bruto != self._candidato:
            self._candidato, self._candidato_desde = bruto, agora
        if agora - self._candidato_desde >= self.confirmar_s:  # type: ignore[operator]
            self.estado, self.desde = bruto, self._candidato_desde
            self._candidato = self._candidato_desde = None


class MonitorDeSaudeVisual:
    """Diz, a cada `intervalo_s`, se a câmera está obstruída, escura, ofuscada, desfocada ou movida.

    Não é thread-safe: o worker de UMA câmera é o único chamador.
    """

    def __init__(
        self,
        intervalo_s: float = 1.0,
        confirmar_s: float = 3.0,
        liberar_s: float = 3.0,
        lado: int = 160,
        relogio: Callable[[], float] = time.monotonic,
    ) -> None:
        self.intervalo_s = intervalo_s
        self.confirmar_s = confirmar_s
        self.liberar_s = liberar_s
        self.lado = lado
        self._relogio = relogio
        self._orb = cv2.ORB_create(nfeatures=ORB_PONTOS, nlevels=ORB_NIVEIS, edgeThreshold=15, patchSize=15, fastThreshold=10)
        self._casador = cv2.BFMatcher(cv2.NORM_HAMMING)

        self._referencia: _Referencia | None = None
        self._referencia_automatica = False
        # Referência adotada sozinha num quadro já degradado (ex.: a câmera subiu
        # tampada) é provisória: vale até o primeiro quadro bom.
        self._referencia_provisoria = False

        self._ultima_medicao: float | None = None
        self._ultimas_metricas: dict[str, float | int] = {}
        self._histerese = Histerese(confirmar_s, liberar_s)

    # ------------------------------------------------------------------ referência

    @property
    def tem_referencia(self) -> bool:
        return self._referencia is not None

    def definir_referencia(self, frame_bgr: np.ndarray) -> None:
        """Fixa o quadro "como a câmera deve ver". Zera a histerese: é um novo ponto de partida."""
        self._adotar(_miniatura_cinza(frame_bgr, self.lado), automatica=False)

    def _adotar(self, cinza: np.ndarray, automatica: bool, provisoria: bool = False) -> None:
        pontos, descritores = self._orb_do(cinza)
        self._referencia = _Referencia(cinza=cinza, pontos=pontos, descritores=descritores, nitidez=_nitidez(cinza))
        self._referencia_automatica = automatica
        self._referencia_provisoria = provisoria
        if not automatica:
            self._histerese.reiniciar()

    def _orb_do(self, cinza: np.ndarray) -> tuple[np.ndarray, np.ndarray | None]:
        pontos, descritores = self._orb.detectAndCompute(cinza, None)
        coords = np.array([p.pt for p in pontos], dtype=np.float32).reshape(-1, 2)
        return coords, descritores

    def serializar_referencia(self) -> bytes:
        """PNG da miniatura de referência (sem perdas: os pontos ORB saem idênticos ao recarregar)."""
        if self._referencia is None:
            raise ValueError("Sem referência para serializar.")
        ok, png = cv2.imencode(".png", self._referencia.cinza)
        if not ok:
            raise RuntimeError("OpenCV não conseguiu codificar a referência em PNG.")
        return png.tobytes()

    def carregar_referencia(self, png_bytes: bytes) -> None:
        cinza = cv2.imdecode(np.frombuffer(png_bytes, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
        if cinza is None:
            raise ValueError("PNG de referência inválido.")
        self.definir_referencia(cinza)

    # ------------------------------------------------------------------ medição

    def observar(self, frame_bgr: np.ndarray, agora: float | None = None) -> dict[str, Any] | None:
        """Mede e classifica o quadro, no máximo uma vez por `intervalo_s`. Fora disso, None sem custo."""
        agora = self._relogio() if agora is None else agora
        if self._ultima_medicao is not None and agora - self._ultima_medicao < self.intervalo_s:
            return None
        self._ultima_medicao = agora

        cinza = _miniatura_cinza(frame_bgr, self.lado)
        absolutas = self._medidas_absolutas(cinza)
        tipo_absoluto = self._classificar_absoluto(absolutas)

        adotou = False
        if self._referencia is None:
            self._adotar(cinza, automatica=True, provisoria=tipo_absoluto != OK)
            adotou = True
        elif self._referencia_provisoria and tipo_absoluto == OK:
            self._adotar(cinza, automatica=True)
            adotou = True

        metricas: dict[str, float | int] = dict(absolutas)
        if adotou:
            # Comparar o quadro com ele mesmo não mede nada; vale só o absoluto.
            metricas.update(_SEM_MOVIMENTO, correlacao=1.0, alinhamento=1.0, nitidez_relativa=1.0, conclusivo=1.0)
            bruto = tipo_absoluto
            inconclusivo = False
        else:
            movimento = self._medir_movimento(cinza)
            nitidez_relativa = absolutas["nitidez"] / max(self._referencia.nitidez, 1e-6)  # type: ignore[union-attr]
            metricas.update({k: v for k, v in movimento.items() if k != "movida"}, nitidez_relativa=nitidez_relativa)
            bruto = self._classificar(tipo_absoluto, bool(movimento["movida"]), nitidez_relativa)
            inconclusivo = not movimento["conclusivo"]

        self._ultimas_metricas = _arredondar(metricas)
        self._histerese.avancar(bruto, agora, inconclusivo)
        return {
            "bruto": bruto,
            "estado": self._histerese.estado,
            "metricas": dict(self._ultimas_metricas),
            "referencia_automatica": adotou and self._referencia_automatica,
        }

    @staticmethod
    def _medidas_absolutas(cinza: np.ndarray) -> dict[str, float]:
        total = cinza.size
        return {
            "brilho": float(cinza.mean()),
            "desvio": float(cinza.std()),
            "nitidez": _nitidez(cinza),
            "fracao_escura": float(np.count_nonzero(cinza < NIVEL_ESCURO) / total),
            "fracao_clara": float(np.count_nonzero(cinza > NIVEL_CLARO) / total),
            "cobertura": _cobertura_da_faixa(cinza),
        }

    @staticmethod
    def _classificar_absoluto(m: dict[str, float]) -> str:
        """O que dá para dizer SEM referência: obstruída, escura, ofuscada ou OK."""
        lisa = m["desvio"] < LIMIAR_DESVIO_LISO or (m["cobertura"] >= COBERTURA_UNIFORME and m["nitidez"] < LIMIAR_LAPLACIANO_LISO)
        if lisa:
            return OBSTRUIDA
        if m["fracao_escura"] >= FRACAO_ESCURA:
            return ESCURA
        if m["fracao_clara"] >= FRACAO_CLARA:
            return OFUSCADA
        return OK

    def _classificar(self, tipo_absoluto: str, movida: bool, nitidez_relativa: float) -> str:
        presentes = {tipo_absoluto} - {OK}
        if movida:
            presentes.add(MOVIDA)
        # Desfoque só faz sentido numa imagem que tem estrutura e contra uma referência que também tinha.
        if (
            tipo_absoluto == OK
            and self._referencia is not None
            and self._referencia.nitidez >= NITIDEZ_MINIMA_DA_REFERENCIA
            and nitidez_relativa < FRACAO_NITIDEZ
        ):
            presentes.add(DESFOCADA)
        return next((tipo for tipo in PRIORIDADE if tipo in presentes), OK)

    def _medir_movimento(self, cinza: np.ndarray) -> dict[str, float]:
        """Correlação e, quando ORB consegue, deslocamento/rotação/escala da cena.

        `movida` e `conclusivo` são 0.0 ou 1.0; `conclusivo` = 0.0 quando ORB tinha pontos nos dois
        quadros mas não produziu uma geometria em que se possa confiar.
        """
        ref = self._referencia
        assert ref is not None
        if cinza.shape != ref.cinza.shape:
            cinza = cv2.resize(cinza, (ref.cinza.shape[1], ref.cinza.shape[0]), interpolation=cv2.INTER_AREA)
        correlacao = float(cv2.matchTemplate(cinza, ref.cinza, cv2.TM_CCOEFF_NORMED)[0, 0])
        if not math.isfinite(correlacao):  # quadro constante: variância zero
            correlacao = 0.0
        saida: dict[str, float] = {**_SEM_MOVIMENTO, "correlacao": correlacao, "conclusivo": 1.0, "movida": 0.0}

        if correlacao >= CORRELACAO_SEM_DUVIDA:
            return saida

        pontos, descritores = self._orb_do(cinza)
        ref_tem_pontos = ref.descritores is not None and len(ref.descritores) >= MIN_CORRESPONDENCIAS
        atual_tem_pontos = descritores is not None and len(descritores) >= MIN_CORRESPONDENCIAS
        if not (ref_tem_pontos and atual_tem_pontos):
            # ORB não tem com o que trabalhar (cena lisa, ou o quadro perdeu a estrutura):
            # vale a queda de similaridade.
            saida["movida"] = float(correlacao < CORRELACAO_MINIMA)
            return saida

        geometria = self._geometria(cinza, ref, pontos, descritores)
        if geometria is None:
            saida["conclusivo"] = 0.0  # sem evidência positiva: não é "movida", mas também não prova que não é
            return saida
        saida.update(geometria)
        saida["movida"] = float(
            geometria["deslocamento"] > DESLOCAMENTO_MAXIMO
            or abs(geometria["rotacao"]) > ROTACAO_MAXIMA_GRAUS
            or abs(geometria["escala"]) > ESCALA_MAXIMA
        )
        return saida

    def _geometria(
        self, cinza: np.ndarray, ref: _Referencia, pontos: np.ndarray, descritores: np.ndarray
    ) -> dict[str, float] | None:
        """Quanto a cena se deslocou/girou/escalou em relação à referência, ou None se não há base para CONFIAR.

        `findHomography` (RANSAC) separa os pontos do fundo rígido dos outliers (pessoas). O "quanto" é
        medido com uma SIMILARIDADE (translação + rotação + escala uniforme) ajustada só nesses inliers:
        a homografia livre tem 8 graus de liberdade e, numa miniatura de 160 px, superajusta o ruído dos
        pontos — nas fixtures isso derrubava o alinhamento até de câmeras realmente movidas, e deixava
        uma pessoa grande se mexendo chegar mais perto de passar por câmera movida.
        """
        assert ref.descritores is not None
        pares = self._casador.knnMatch(ref.descritores, descritores, k=2)
        boas = [p[0] for p in pares if len(p) == 2 and p[0].distance < RAZAO_LOWE * p[1].distance]
        if len(boas) < MIN_CORRESPONDENCIAS:
            return None
        origem = ref.pontos[[m.queryIdx for m in boas]].reshape(-1, 1, 2)
        destino = pontos[[m.trainIdx for m in boas]].reshape(-1, 1, 2)
        _, mascara = cv2.findHomography(origem, destino, cv2.RANSAC, LIMIAR_RANSAC_PX)
        if mascara is None:
            return None
        do_fundo = mascara.ravel() > 0
        if int(do_fundo.sum()) < MIN_INLIERS:
            return None
        pose, mascara_pose = cv2.estimateAffinePartial2D(
            origem[do_fundo], destino[do_fundo], method=cv2.RANSAC, ransacReprojThreshold=LIMIAR_RANSAC_PX
        )
        if pose is None or mascara_pose is None:
            return None
        inliers = int(mascara_pose.sum())
        if inliers < MIN_INLIERS:
            return None

        altura, largura = ref.cinza.shape
        centro = np.array([[[largura / 2, altura / 2]]], dtype=np.float32)
        deslocado = cv2.transform(centro, pose).reshape(2)
        escala = float(math.log(max(math.hypot(pose[0, 0], pose[1, 0]), 1e-6)))
        if abs(escala) > ESCALA_PLAUSIVEL:
            return None

        # Contraprova: trazer o quadro atual de volta para a referência com a pose achada. Se ela é
        # real, o fundo reaparece; se foi RANSAC fechando em pessoas, não.
        alinhado = cv2.warpAffine(cinza, pose, (largura, altura), flags=cv2.WARP_INVERSE_MAP | cv2.INTER_LINEAR)
        visivel = cv2.warpAffine(
            np.full(cinza.shape, 255, np.uint8), pose, (largura, altura), flags=cv2.WARP_INVERSE_MAP | cv2.INTER_NEAREST
        )
        alinhamento = _alinhamento(alinhado, ref.cinza, visivel)
        if alinhamento is None or alinhamento < ALINHAMENTO_MINIMO:
            return None
        return {
            "deslocamento": float(np.linalg.norm(deslocado - centro[0, 0]) / max(largura, altura)),
            "rotacao": float(math.degrees(math.atan2(pose[1, 0], pose[0, 0]))),
            "escala": escala,
            "inliers": inliers,
            "alinhamento": alinhamento,
        }

    # ------------------------------------------------------------------ saída

    def estado(self) -> dict[str, Any]:
        """Estado CONFIRMADO (com histerese) + métricas da última medição. `desde` está no domínio do relógio."""
        estado = self._histerese.estado
        return {
            "estado": estado,
            "rotulo": ROTULOS[estado],
            "desde": self._histerese.desde,
            "metricas": dict(self._ultimas_metricas),
            "tem_referencia": self.tem_referencia,
            "referencia_automatica": self._referencia_automatica and self.tem_referencia,
        }

    def alertas(self) -> list[dict[str, Any]]:
        """Um dict compatível com `RuleAlert(**dict)` para o estado confirmado, ou lista vazia se OK."""
        estado, desde = self._histerese.estado, self._histerese.desde
        if estado == OK or desde is None:
            return []
        fim = self._ultima_medicao if self._ultima_medicao is not None else desde
        return [
            {
                "rule": f"camera_{estado}",
                "severity": SEVERIDADES[estado],
                "message": _mensagem(estado, max(0, round(fim - desde))),
                "feature": FEATURE,
                "metadata": {"subject": "camera", "metricas": dict(self._ultimas_metricas)},
            }
        ]


def _mensagem(estado: str, segundos: int) -> str:
    texto = {
        OBSTRUIDA: "Câmera obstruída — imagem sem detalhe",
        MOVIDA: "Câmera movida — a cena não confere com a referência",
        ESCURA: "Câmera escura — pouca luz na imagem",
        OFUSCADA: "Câmera ofuscada — imagem estourada",
        DESFOCADA: "Câmera desfocada — perda de nitidez",
    }[estado]
    return f"{texto} há {segundos} s"


def caminho_da_referencia(pasta_configurada: str | None, instance_path: str, camera_id: int, fonte: object) -> Path:
    """Arquivo da referência de UMA câmera com UMA fonte (fonte única da regra: worker e primeiro acesso).

    Só o id não basta: o banco da demo e o do E2E são recriados a cada subida e os
    ids recomeçam em 1; a "câmera 2" de agora herdava a referência da "câmera 2"
    de outra rodada, com outra fonte, e acusava DESFOCADA/MOVIDA sem nada ter
    acontecido (visto nas capturas da MISSÃO 4).
    """
    pasta = Path(pasta_configurada or Path(instance_path) / "referencias")
    marca = hashlib.sha1(str(fonte).encode("utf-8")).hexdigest()[:10]
    return pasta / f"camera_{camera_id}_{marca}.png"
