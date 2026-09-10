"""Resiliência da captura de vídeo.

O caso que motivou isto: uma fonte RTSP que cai costuma deixar o
`VideoCapture` "aberto" e apenas devolver `False` em todo `read()`. Como a
versão anterior só reabria quando `isOpened()` era falso, a câmera ficava em
"Frame indisponível" para sempre, sem nunca tentar voltar.
"""
from __future__ import annotations

import numpy as np
import pytest
from app.vision import video_stream as vs_module
from app.vision.video_stream import LIVE, RECONNECTING, UNAVAILABLE, VideoStream, VideoStreamError

FRAME = np.zeros((4, 4, 3), dtype=np.uint8)


def frame_com_id(n: int):
    """Frame identificável: todo pixel vale `n`.

    Sem identidade não dá para distinguir "devolveu o frame mais novo" de
    "devolveu o mais velho" — que é exatamente a pergunta do descarte de
    frame atrasado.
    """
    return np.full((4, 4, 3), n % 256, dtype=np.uint8)


def id_do_frame(frame) -> int:
    return int(frame[0, 0, 0])


class FakeCapture:
    """Dublê de cv2.VideoCapture com roteiro de leituras controlado.

    `grab()`/`retrieve()` existem porque é assim que o OpenCV separa "avançar
    para o próximo frame" de "decodificar o frame atual", e é sobre essa
    separação que o descarte de frame atrasado se apoia. `read()` fica
    definido em termos dos dois, como no próprio OpenCV — doc oficial de
    `VideoCapture::read`: "The method/function combines VideoCapture::grab()
    and VideoCapture::retrieve() in one call."
    https://docs.opencv.org/4.x/d8/dfe/classcv_1_1VideoCapture.html

    `ms_por_grab` simula o custo de cada `grab()`: frame que já está no buffer
    volta instantâneo, frame que ainda não chegou custa a espera da rede. É o
    que permite testar o descarte sem servidor RTSP nenhum.
    """

    def __init__(
        self,
        leituras: list[bool],
        abre: bool = True,
        relogio: dict | None = None,
        ms_por_grab: list[float] | None = None,
    ):
        self.leituras = list(leituras)
        self._abre = abre
        self.liberado = False
        self.grabs = 0
        self.retrieves = 0
        self._seq = 0
        self._ultimo_id: int | None = None
        self._relogio = relogio
        self._ms_por_grab = list(ms_por_grab) if ms_por_grab is not None else None

    def isOpened(self):  # noqa: N802  (assinatura do cv2)
        return self._abre and not self.liberado

    def grab(self):
        if self._relogio is not None and self._ms_por_grab:
            self._relogio["t"] += self._ms_por_grab.pop(0) / 1000.0
        if not self.leituras:
            self._ultimo_id = None
            return False
        self.grabs += 1
        ok = self.leituras.pop(0)
        if not ok:
            self._ultimo_id = None
            return False
        self._seq += 1
        self._ultimo_id = self._seq
        return True

    def retrieve(self):
        self.retrieves += 1
        if self._ultimo_id is None:
            return False, None
        return True, frame_com_id(self._ultimo_id)

    def read(self):
        if not self.grab():
            return False, None
        return self.retrieve()

    def set(self, *_args):
        return True

    def release(self):
        self.liberado = True


@pytest.fixture()
def relogio(monkeypatch):
    """Relógio controlado — backoff é testado sem dormir de verdade."""
    agora = {"t": 1000.0}
    monkeypatch.setattr(vs_module, "monotonic", lambda: agora["t"])
    return agora


@pytest.fixture()
def capturas(monkeypatch):
    """Fila de FakeCapture: cada abertura consome a próxima da lista."""
    fila: list[FakeCapture] = []
    criadas: list[FakeCapture] = []

    chamadas: list[tuple] = []

    def fabrica(_source, _api=None, _params=None):
        # `_api` existe porque VideoStream escolhe o backend explicitamente
        # (DirectShow para webcam no Windows, ver video_stream.capture_api).
        # `_params` e a sobrecarga (filename, apiPreference, params) do OpenCV,
        # usada para o timeout de abertura. Os dois ficam opcionais para o
        # dublê servir a todos os formatos de chamada.
        chamadas.append((_source, _api, _params))
        cap = fila.pop(0) if fila else FakeCapture([], abre=False)
        criadas.append(cap)
        return cap

    monkeypatch.setattr(vs_module.cv2, "VideoCapture", fabrica)
    return {"fila": fila, "criadas": criadas, "chamadas": chamadas}


def _stream(**kwargs) -> VideoStream:
    return VideoStream("rtsp://camera/1", 640, 480, **kwargs)


# ------------------------------------------------------------ caminho feliz --
def test_leitura_bem_sucedida_marca_live(relogio, capturas):
    capturas["fila"].append(FakeCapture([True, True]))
    stream = _stream()

    ok, frame = stream.read()

    assert ok is True and frame is not None
    assert stream.is_live is True
    assert stream.status().state == LIVE
    assert stream.status().consecutive_failures == 0


def test_falha_isolada_nao_derruba_a_conexao(relogio, capturas):
    """Engasgo de rede não pode custar uma reconexão."""
    capturas["fila"].append(FakeCapture([True, False, True]))
    stream = _stream(failures_before_reconnect=15)

    stream.read()
    stream.read()  # falha isolada
    assert stream.status().consecutive_failures == 1
    assert len(capturas["criadas"]) == 1  # nao reabriu

    assert stream.read()[0] is True
    assert stream.status().consecutive_failures == 0


# ------------------------------------------------------- o bug do RTSP morto -
def test_fonte_aberta_mas_morta_forca_reconexao(relogio, capturas):
    """`isOpened()` continua True e `read()` só devolve False — era aqui que a
    versão anterior travava para sempre."""
    morta = FakeCapture([False] * 10)
    viva = FakeCapture([True])
    capturas["fila"].extend([morta, viva])
    stream = _stream(failures_before_reconnect=3)

    for _ in range(3):
        stream.read()

    assert morta.liberado is True, "a captura morta precisa ser liberada"
    assert stream.status().state == RECONNECTING

    relogio["t"] += 10  # passa a janela de backoff
    ok, _ = stream.read()

    assert ok is True
    assert stream.status().state == LIVE
    assert stream.status().total_reconnects == 1


def test_dentro_do_backoff_nao_tenta_reabrir(relogio, capturas):
    """Fonte morta não pode ser martelada 12x por segundo."""
    capturas["fila"].append(FakeCapture([False, False]))
    stream = _stream(failures_before_reconnect=2, initial_backoff_seconds=5.0)

    stream.read()
    stream.read()  # estoura o limite -> agenda retry em 5s
    aberturas = len(capturas["criadas"])

    for _ in range(20):
        assert stream.read()[0] is False
    assert len(capturas["criadas"]) == aberturas, "nao pode reabrir dentro do backoff"

    assert stream.status().seconds_until_retry == pytest.approx(5.0)


def test_backoff_dobra_ate_o_teto(relogio, capturas):
    stream = _stream(failures_before_reconnect=1, initial_backoff_seconds=1.0, max_backoff_seconds=8.0)
    esperado = [1.0, 2.0, 4.0, 8.0, 8.0, 8.0]

    for espera in esperado:
        capturas["fila"].append(FakeCapture([], abre=False))  # abertura falha
        relogio["t"] += 100  # sempre fora da janela
        stream.read()
        assert stream.status().seconds_until_retry == pytest.approx(espera)

    assert stream.status().state == UNAVAILABLE


def test_reconexao_bem_sucedida_zera_o_backoff(relogio, capturas):
    capturas["fila"].extend([FakeCapture([], abre=False), FakeCapture([True])])
    stream = _stream(failures_before_reconnect=1, initial_backoff_seconds=1.0)

    stream.read()  # falha ao abrir -> backoff
    assert stream.status().seconds_until_retry > 0

    relogio["t"] += 100
    assert stream.read()[0] is True
    assert stream.status().seconds_until_retry == 0.0
    assert stream.status().reconnect_attempts == 0


# ------------------------------------------------------------- contrato geral -
def test_read_nunca_levanta_excecao(relogio, capturas):
    """O loop de captura depende disso: antes, `open()` levantava a cada
    iteração e enchia o log de traceback."""
    stream = _stream()
    for _ in range(5):
        capturas["fila"].append(FakeCapture([], abre=False))
        relogio["t"] += 100
        assert stream.read() == (False, None)


def test_open_explicito_ainda_levanta(relogio, capturas):
    """`warmup`/preflight querem falhar alto — só o `read()` é silencioso."""
    capturas["fila"].append(FakeCapture([], abre=False))
    with pytest.raises(VideoStreamError):
        _stream().open()


def test_release_volta_ao_estado_inicial(relogio, capturas):
    capturas["fila"].append(FakeCapture([True]))
    stream = _stream()
    stream.read()

    stream.release()

    estado = stream.status()
    assert estado.state == "idle"
    assert estado.seconds_until_retry == 0.0
    assert stream.is_live is False


def test_latest_frame_sobrevive_a_queda(relogio, capturas):
    """A UI continua mostrando o último frame bom enquanto reconecta."""
    capturas["fila"].append(FakeCapture([True, False, False, False]))
    stream = _stream(failures_before_reconnect=2)

    stream.read()
    for _ in range(3):
        stream.read()

    assert stream.latest_frame() is not None
    assert stream.status().state in (RECONNECTING, UNAVAILABLE)


# ------------------------------------------- abertura de fonte de rede -----
# Os dois testes abaixo vieram de MEDICAO contra um servidor RTSP local
# (mediamtx com usuario e senha), nao de leitura de codigo. Com o servidor
# morto, abrir a fonte custava 34,3 s por tentativa e o log do OpenCV
# despejava uma excecao do backend CAP_IMAGES sobre a URL RTSP.
#
# Medido nesta maquina, abrindo `rtsp://...@localhost:554/...` sem nada
# escutando na porta:
#
#   CAP_ANY,    sem params                      -> 34.319 ms
#   CAP_FFMPEG, sem params                      -> 30.054 ms
#   CAP_FFMPEG, cap.set() antes do open         -> 30.045 ms  (nao funciona)
#   CAP_FFMPEG, params=[OPEN_TIMEOUT_MSEC 3000] ->  3.037 ms
#
# 11,3x. `cap.set()` nao serve porque a propriedade e "open-only" — OpenCV
# 4.11.0, modules/videoio/include/opencv2/videoio.hpp:
#   CAP_PROP_OPEN_TIMEOUT_MSEC=53, //!< (**open-only**) timeout in
#   milliseconds for opening a video capture (applicable for FFmpeg and
#   GStreamer back-ends only)
# Por isso vai pela sobrecarga de construtor que aceita params:
#   explicit VideoCapture(const String& filename, int apiPreference,
#                         const std::vector<int>& params);
#   "The params parameter allows to specify extra parameters encoded as pairs
#    (paramId_1, paramValue_1, paramId_2, paramValue_2, ...)."
def test_fonte_de_rede_abre_com_o_backend_ffmpeg():
    """CAP_ANY faz o OpenCV tentar outros backends depois do FFMPEG falhar.

    Medido: 4,3 s a mais por tentativa, e uma excecao do backend CAP_IMAGES
    sobre a URL RTSP no log — erro que nao tem nada a ver com a causa real e
    manda quem esta diagnosticando para o lado errado.
    """
    assert vs_module.capture_api("rtsp://camera/1") == vs_module.cv2.CAP_FFMPEG
    assert vs_module.capture_api("http://camera/stream") == vs_module.cv2.CAP_FFMPEG


def test_arquivo_e_webcam_nao_mudam_de_backend():
    """Contraprova: so fonte de REDE muda. Webcam no Windows segue DirectShow
    (medido: 0,86 s contra 20 s do MSMF) e arquivo segue no CAP_ANY."""
    import sys

    if sys.platform == "win32":
        assert vs_module.capture_api(0) == vs_module.cv2.CAP_DSHOW
    assert vs_module.capture_api("tests/fixtures/bench.mp4") == vs_module.cv2.CAP_ANY


def test_fonte_de_rede_recebe_timeout_de_abertura(relogio, capturas):
    """Sem isto, uma camera morta trava o worker 30 s por tentativa.

    O default do OpenCV e o proprio callback de interrupcao dele: o log traz
    "Stream timeout triggered after 30043.883000 ms". Com 5 tentativas antes do
    modo fixture, sao ~150 s de camera parada antes de o demo ter imagem.
    """
    capturas["fila"].append(FakeCapture([True]))
    stream = VideoStream("rtsp://camera/1", 640, 480, open_timeout_ms=4000)

    stream.read()

    _source, _api, params = capturas["chamadas"][0]
    assert params is not None, "fonte de rede tem que abrir com params de timeout"
    pares = dict(zip(params[::2], params[1::2]))
    assert pares[int(vs_module.cv2.CAP_PROP_OPEN_TIMEOUT_MSEC)] == 4000
    assert pares[int(vs_module.cv2.CAP_PROP_READ_TIMEOUT_MSEC)] == 4000


def test_arquivo_local_nao_recebe_timeout(relogio, capturas):
    """Timeout de rede em arquivo local nao faz sentido, e a fixture do modo
    fixture e um arquivo local: um timeout ali seria risco sem ganho."""
    capturas["fila"].append(FakeCapture([True]))
    stream = VideoStream("tests/fixtures/bench.mp4", 640, 480)

    stream.read()

    _source, _api, params = capturas["chamadas"][0]
    assert params is None, f"arquivo local nao deveria receber params: {params}"


# ----------------------------------------------- fixture em loop -----------
def test_fim_de_arquivo_em_loop_rebobina_em_vez_de_falhar(relogio, capturas):
    """`em_loop=True`: fim do video nao e falha de fonte.

    Sem isto o fim do arquivo entra no caminho de falha — 15 leituras ruins
    mais 0,5 s de backoff a cada volta, ou seja meio segundo de imagem
    congelada a cada 7 s de fixture, na frente de quem esta assistindo.
    """
    capturas["fila"].append(FakeCapture([True, False, True]))
    stream = VideoStream("bench.mp4", 640, 480, em_loop=True)

    assert stream.read()[0] is True
    ok, _ = stream.read()  # fim do arquivo: rebobina, nao conta falha

    assert ok is False, "a leitura que bateu no fim ainda devolve falha"
    assert stream.status().consecutive_failures == 0, "rebobinar nao e falha"
    assert stream.status().state == LIVE, "nao pode ir para reconnecting no fim do arquivo"
    assert stream.read()[0] is True, "depois de rebobinar, volta a entregar"


def test_arquivo_ilegivel_em_loop_nao_gira_para_sempre(relogio, capturas):
    """Contraprova: rebobinar uma vez so.

    Se o .mp4 estiver corrompido, rebobinar sem limite esconderia o problema
    para sempre. A segunda falha seguida cai no caminho normal.
    """
    capturas["fila"].append(FakeCapture([True] + [False] * 30))
    stream = VideoStream("bench.mp4", 640, 480, em_loop=True, failures_before_reconnect=3)

    stream.read()
    for _ in range(6):
        stream.read()

    assert stream.status().consecutive_failures > 0, (
        "arquivo ilegivel tem que aparecer como falha, nao virar loop infinito de rebobinamento"
    )


# ============================================================================
# Descarte de frame atrasado — so em fonte de REDE
# ============================================================================
# MEDIDO na sessao anterior, contra o servidor RTSP local no perfil Dahua:
#
#   - `cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)` devolve **False** no backend
#     FFMPEG, e `cap.get(...)` devolve 0.0. O pedido nao tem efeito.
#   - abrindo o stream e parando de ler por 10 s, ao voltar saem **104 frames
#     instantaneos** antes de a leitura voltar a bloquear — identico com e sem
#     o pedido de BUFFERSIZE.
#   - efeito no dashboard: o atraso NAO e constante, **cresce +135 ms/s** a
#     15 fps (8,1 s a cada minuto), porque nada no caminho descarta frame
#     velho e o worker consome mais devagar que a fonte produz.
#
# A doc oficial do OpenCV lista CAP_PROP_BUFFERSIZE sem garantia de suporte por
# backend (https://docs.opencv.org/4.x/d4/d15/group__videoio__flags__base.html);
# quem decide e o backend, e o FFMPEG nao implementa.
#
# O conserto e descartar no leitor: `grab()` em laco (avanca sem decodificar) e
# `retrieve()` so no ultimo (decodifica uma vez).


def _stream_de_rede(relogio, capturas, leituras, ms_por_grab, **kwargs):
    capturas["fila"].append(
        FakeCapture(leituras, relogio=relogio, ms_por_grab=ms_por_grab)
    )
    return VideoStream("rtsp://camera/1", 640, 480, **kwargs)


def test_rede_devolve_o_frame_MAIS_NOVO_da_fila(relogio, capturas):
    """O teste que estava vermelho antes do fix.

    Cinco frames disponiveis: quatro ja estao no buffer (grab instantaneo) e o
    quinto e o vivo (grab espera 200 ms pela rede). Uma leitura tem que
    devolver o **quinto**, nao o primeiro.
    """
    stream = _stream_de_rede(
        relogio, capturas,
        leituras=[True] * 5,
        ms_por_grab=[0, 0, 0, 0, 200],
    )

    ok, frame = stream.read()

    assert ok is True
    assert id_do_frame(frame) == 5, (
        f"devolveu o frame {id_do_frame(frame)} de 5 — a fila nao foi descartada, "
        "e o atraso vai crescer sem parar"
    )


def test_rede_decodifica_uma_vez_so(relogio, capturas):
    """Descartar com `read()` custaria um decode por frame jogado fora.

    `grab()` avanca sem decodificar; so o ultimo vira imagem. Sem isto o
    'conserto' de latencia viraria custo de CPU no loop de captura.
    """
    stream = _stream_de_rede(
        relogio, capturas,
        leituras=[True] * 5,
        ms_por_grab=[0, 0, 0, 0, 200],
    )

    stream.read()

    captura = capturas["criadas"][0]
    assert captura.grabs == 5, f"esperava 5 grabs, houve {captura.grabs}"
    assert captura.retrieves == 1, (
        f"esperava 1 decode, houve {captura.retrieves} — descartar nao pode custar decode"
    )


def test_rede_para_de_descartar_ao_alcancar_o_vivo(relogio, capturas):
    """O primeiro `grab()` que ESPERA pela rede ja e o frame vivo.

    Continuar depois dele nao adiantaria nada (nao ha mais nada bufferizado) e
    bloquearia o loop de captura esperando o proximo frame chegar.
    """
    stream = _stream_de_rede(
        relogio, capturas,
        leituras=[True] * 10,
        ms_por_grab=[0, 0, 200, 0, 0, 0, 0, 0, 0, 0],
    )

    ok, frame = stream.read()

    assert ok is True
    assert id_do_frame(frame) == 3, f"parou no frame errado: {id_do_frame(frame)}"
    assert capturas["criadas"][0].grabs == 3


def test_rede_tem_teto_de_descarte_por_leitura(relogio, capturas):
    """Fonte que entrega instantaneo para sempre nao pode prender o loop.

    Sem teto, uma fonte mais rapida que o consumidor faria `read()` girar sem
    devolver frame nenhum — trocar atraso por travamento nao e conserto.
    """
    stream = _stream_de_rede(
        relogio, capturas,
        leituras=[True] * 500,
        ms_por_grab=[0] * 500,
        max_descarte_por_leitura=8,
    )

    ok, _ = stream.read()

    assert ok is True
    assert capturas["criadas"][0].grabs == 8, (
        f"descartou {capturas['criadas'][0].grabs} frames; o teto pedido era 8"
    )


def test_rede_sem_fila_nao_descarta_nada(relogio, capturas):
    """Caso normal: a fonte esta no ritmo do consumidor.

    O primeiro grab ja espera pela rede, entao nao ha o que descartar e o
    custo do descarte e zero.
    """
    stream = _stream_de_rede(
        relogio, capturas,
        leituras=[True, True],
        ms_por_grab=[200, 200],
    )

    ok, frame = stream.read()

    assert ok is True
    assert id_do_frame(frame) == 1
    assert capturas["criadas"][0].grabs == 1, "nao havia fila: nao podia haver descarte"


# ---- contraprova: as outras duas fontes NAO podem descartar ---------------
def test_arquivo_le_todos_os_frames_em_ordem(relogio, capturas):
    """CARACTERIZACAO. O modo fixture depende disto.

    A fonte de demonstracao e um arquivo em loop; pular frame ali seria video
    acelerado e picotado na frente do avaliador — e o modo fixture e o plano B
    do demo.
    """
    capturas["fila"].append(FakeCapture([True] * 5))
    stream = VideoStream("tests/fixtures/bench.mp4", 640, 480, em_loop=True)

    lidos = [id_do_frame(stream.read()[1]) for _ in range(3)]

    assert lidos == [1, 2, 3], f"arquivo pulou frame: {lidos}"
    assert capturas["criadas"][0].grabs == 3


def test_webcam_usb_le_todos_os_frames_em_ordem(relogio, capturas):
    """CARACTERIZACAO. A webcam ja entrega o frame mais recente.

    Descartar aqui so jogaria fora quadro bom e derrubaria o FPS, sem ganho de
    latencia nenhum.
    """
    capturas["fila"].append(FakeCapture([True] * 5))
    stream = VideoStream(0, 640, 480)

    lidos = [id_do_frame(stream.read()[1]) for _ in range(3)]

    assert lidos == [1, 2, 3], f"webcam pulou frame: {lidos}"
    assert capturas["criadas"][0].grabs == 3


# ---- caracterizacao: o descarte nao pode mexer em reconexao ---------------
def test_rede_falha_de_leitura_continua_contando_para_reconectar(relogio, capturas):
    """CARACTERIZACAO. O contrato de reconexao e anterior a este fix e segue
    igual: N falhas seguidas derrubam e reagendam."""
    capturas["fila"].append(
        FakeCapture([False] * 10, relogio=relogio, ms_por_grab=[0] * 10)
    )
    stream = VideoStream("rtsp://camera/1", 640, 480, failures_before_reconnect=3)

    for _ in range(3):
        assert stream.read() == (False, None)

    assert capturas["criadas"][0].liberado is True
    assert stream.status().state == RECONNECTING


def test_rede_frame_bom_depois_de_falha_zera_o_contador(relogio, capturas):
    """CARACTERIZACAO: engasgo isolado nao pode custar reconexao, nem com o
    descarte ligado."""
    capturas["fila"].append(
        FakeCapture([True, False, True], relogio=relogio, ms_por_grab=[200, 0, 200])
    )
    stream = VideoStream("rtsp://camera/1", 640, 480, failures_before_reconnect=15)

    stream.read()
    stream.read()
    assert stream.status().consecutive_failures == 1

    assert stream.read()[0] is True
    assert stream.status().consecutive_failures == 0
