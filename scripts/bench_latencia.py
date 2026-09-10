"""Latência fim-a-fim: do frame PUBLICADO até ele aparecer no dashboard.

A pergunta aqui é diferente da de `bench_pipeline.py`. Aquele mede
**throughput** (quantos frames por segundo). Este mede **atraso** (quão velho é
o frame que está na tela). Os dois são independentes: um pipeline a 15 fps pode
estar mostrando imagem de 3 segundos atrás se houver buffer acumulando no
caminho, e é exatamente esse o risco de uma câmera IP.

Como o instante de publicação é conhecido: cada frame sai do publicador com um
**código de barras binário** desenhado na primeira faixa de pixels — 32 bits de
milissegundos desde o início do processo, mais 8 de checksum. Quem lê decodifica
o carimbo e subtrai do relógio. Não há relógio a sincronizar: publicador e leitor
são o mesmo processo.

O checksum não é enfeite: no caminho do dashboard o frame chega **anotado**, e
uma caixa de detecção desenhada por cima do carimbo o corromperia em silêncio.
Amostra que não fecha o checksum é DESCARTADA, e a taxa de descarte é
reportada — descarte alto invalida a medição e precisa aparecer.

Dois trechos, em fases separadas (nunca simultâneas, para não disputarem CPU):

    FONTE      publicação -> `VideoStream.read()` devolver o frame.
               É o buffer de rede/decoder: o que uma câmera IP real tem e um
               arquivo local não tem.

    DASHBOARD  publicação -> o mesmo frame sair pelo MJPEG do Flask.
               Inclui o trecho FONTE, mais o pipeline de visão, mais o
               `time.sleep(1/TARGET_FPS)` do gerador de MJPEG.

Fica DE FORA, e precisa ser somado à mão: o navegador decodificar e pintar.

Reproduzir (com o mediamtx do docs/DEMO.md no ar):

    python scripts/bench_latencia.py --ffmpeg ./ffmpeg.exe \\
        --url "rtsp://usuario:senha@localhost:8554/cam/realmonitor"
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

import cv2
import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from app.llm import redigir_segredos  # noqa: E402
from app.vision.video_stream import VideoStream  # noqa: E402

# Geometria do carimbo. O primeiro desenho tinha 40 blocos de 16 px com 32 bits
# de milissegundos, e NAO SOBREVIVEU: aresta preta/branca fina e o padrao mais
# caro que existe para o H.264, e a 512 kbps o encoder estourou o orcamento —
# o decoder cuspiu "error while decoding MB" em rajada e nao houve amostra
# valida. O carimbo agora carrega um NUMERO DE SEQUENCIA de 12 bits (mais 4 de
# checksum) em 16 blocos de 40x24 px: um sexto das arestas, e o instante de
# publicacao vira uma consulta na tabela que o publicador mantem.
BITS_DADOS = 12
BITS_CHECKSUM = 4
BLOCOS = BITS_DADOS + BITS_CHECKSUM
LARGURA_BLOCO = 40
ALTURA_BLOCO = 24
LARGURA_CARIMBO = BLOCOS * LARGURA_BLOCO
SEQ_MAX = 1 << BITS_DADOS  # 4096 frames = 273 s a 15 fps antes de dar a volta


def _bits(valor: int, largura: int) -> list[int]:
    return [(valor >> (largura - 1 - i)) & 1 for i in range(largura)]


def _checksum(seq: int) -> int:
    return (seq + (seq >> 4) + (seq >> 8)) & 0xF


def carimbar(frame, seq: int) -> None:
    """Desenha o numero de sequencia no canto superior esquerdo, in-place."""
    seq %= SEQ_MAX
    padrao = _bits(seq, BITS_DADOS) + _bits(_checksum(seq), BITS_CHECKSUM)
    for i, bit in enumerate(padrao):
        x = i * LARGURA_BLOCO
        frame[0:ALTURA_BLOCO, x:x + LARGURA_BLOCO] = 255 if bit else 0


def ler_carimbo(frame) -> int | None:
    """Decodifica o numero de sequencia. `None` se o checksum nao fechar."""
    if frame.shape[1] < LARGURA_CARIMBO or frame.shape[0] < ALTURA_BLOCO:
        return None
    faixa = frame[0:ALTURA_BLOCO, 0:LARGURA_CARIMBO]
    if faixa.ndim == 3:
        faixa = faixa[:, :, 0]
    valores = []
    for i in range(BLOCOS):
        # So o miolo do bloco: a borda e onde o ringing do H.264 se concentra.
        centro = faixa[6:ALTURA_BLOCO - 6, i * LARGURA_BLOCO + 10:(i + 1) * LARGURA_BLOCO - 10]
        valores.append(1 if float(centro.mean()) > 127 else 0)
    seq = 0
    for bit in valores[:BITS_DADOS]:
        seq = (seq << 1) | bit
    lido = 0
    for bit in valores[BITS_DADOS:]:
        lido = (lido << 1) | bit
    return seq if lido == _checksum(seq) else None


class Publicador:
    """Publica a fixture carimbada, no perfil pedido, via ffmpeg -> RTSP."""

    def __init__(self, ffmpeg: str, url: str, fixture: Path, largura: int, altura: int,
                 fps: int, kbps: int, lookahead: int = 0) -> None:
        self.t0 = time.perf_counter()
        self._parar = threading.Event()
        # seq -> instante em que o frame foi entregue ao ffmpeg. Lista de
        # tamanho fixo em vez de dict: da a volta junto com o contador e nao
        # cresce durante a medicao.
        self.publicado_em: list[float | None] = [None] * SEQ_MAX
        gop = fps * 2  # intervalo de I-frame tipico de encoder de vigilancia
        self._proc = subprocess.Popen(
            [
                ffmpeg, "-hide_banner", "-loglevel", "error",
                "-f", "rawvideo", "-pix_fmt", "bgr24",
                "-s", f"{largura}x{altura}", "-r", str(fps), "-i", "-",
                # `-rc-lookahead 0` NAO e detalhe. Com o default do preset veryfast
                # (40 quadros) o publicador segurava 45 frames antes de emitir
                # qualquer coisa: medido, 3.003 ms constantes a 15 fps e 5.628 ms
                # a 8 fps — o MESMO numero de frames, e imune ao bitrate (512 e
                # 4096 kbps deram 3.003 ms). Isso e lookahead do x264, nao da
                # rede, e encoder de camera de vigilancia nao faz isso: ele
                # emite quadro a quadro. Mantido o default, toda a medicao de
                # latencia seria dominada por um artefato da bancada.
                "-c:v", "libx264", "-profile:v", "main", "-preset", "veryfast", "-bf", "0",
                "-rc-lookahead", str(lookahead),
                "-g", str(gop), "-keyint_min", str(gop), "-sc_threshold", "0",
                "-b:v", f"{kbps}k", "-maxrate", f"{kbps}k", "-bufsize", f"{kbps * 2}k",
                "-pix_fmt", "yuv420p", "-f", "rtsp", "-rtsp_transport", "tcp", url,
            ],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        self._thread = threading.Thread(
            target=self._bombear, args=(fixture, largura, altura, fps), daemon=True
        )
        self._thread.start()

    def _bombear(self, fixture: Path, largura: int, altura: int, fps: int) -> None:
        intervalo = 1.0 / fps
        captura = cv2.VideoCapture(str(fixture))
        proximo = time.perf_counter()
        seq = 0
        while not self._parar.is_set():
            ok, frame = captura.read()
            if not ok:
                captura.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue
            frame = cv2.resize(frame, (largura, altura))
            # Carimba o MAIS TARDE possivel: entre carimbar e o ffmpeg receber
            # ha so o write do pipe. Carimbar antes do resize contaria o resize
            # como latencia de rede, que ele nao e.
            seq %= SEQ_MAX
            carimbar(frame, seq)
            self.publicado_em[seq] = time.perf_counter() - self.t0
            seq += 1
            try:
                self._proc.stdin.write(frame.tobytes())
            except (BrokenPipeError, OSError, ValueError):
                break
            proximo += intervalo
            time.sleep(max(0.0, proximo - time.perf_counter()))
        captura.release()

    def atraso_ms(self, seq: int) -> float | None:
        """Quantos ms se passaram desde que o frame `seq` foi publicado."""
        publicado = self.publicado_em[seq % SEQ_MAX]
        if publicado is None:
            return None
        return (time.perf_counter() - self.t0 - publicado) * 1000.0

    def parar(self) -> None:
        self._parar.set()
        self._thread.join(timeout=2)
        try:
            if self._proc.stdin:
                self._proc.stdin.close()
        except OSError:
            pass
        self._proc.terminate()
        try:
            self._proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._proc.kill()


def resumo(amostras: list[tuple[float, float]], descartadas: int) -> dict[str, float]:
    """`amostras` = pares (instante da leitura, atraso em ms).

    O instante entra porque a pergunta decisiva nao e "qual o atraso" e sim
    "o atraso FICA PARADO ou CRESCE?". Atraso constante e buffer, e tem teto.
    Atraso que cresce e fila: o consumidor e mais lento que a fonte, e nesse
    regime nao existe numero para relatar — existe uma rampa, e depois de
    tempo suficiente o video na tela e de minutos atras. So p50 e p95 nao
    distinguem os dois casos.
    """
    if not amostras:
        return {"n": 0, "descartadas": descartadas}
    valores = sorted(a for _, a in amostras)
    resultado = {
        "n": len(valores),
        "descartadas": descartadas,
        "p50": statistics.median(valores),
        "p95": valores[min(len(valores) - 1, int(round(0.95 * (len(valores) - 1))))],
        "max": valores[-1],
        "min": valores[0],
    }
    if len(amostras) >= 8:
        # Inclinacao por minimos quadrados: ms de atraso ganhos por segundo.
        ts = [t for t, _ in amostras]
        ys = [a for _, a in amostras]
        media_t, media_y = statistics.fmean(ts), statistics.fmean(ys)
        numerador = sum((t - media_t) * (y - media_y) for t, y in amostras)
        denominador = sum((t - media_t) ** 2 for t in ts)
        resultado["deriva_ms_por_s"] = numerador / denominador if denominador else 0.0
    return resultado


def medir_fonte(pub: Publicador, url: str, segundos: float, largura: int, altura: int) -> dict[str, float]:
    """Trecho FONTE, pelo `VideoStream` de producao.

    Pelo VideoStream e nao por um `cv2.VideoCapture` cru porque e ele que pede
    `CAP_PROP_BUFFERSIZE=1` — e esse pedido e exatamente o que decide se o
    atraso acumula ou fica plano.
    """
    stream = VideoStream(source=url, width=largura, height=altura)
    amostras: list[tuple[float, float]] = []
    descartadas = 0
    fim = time.perf_counter() + segundos
    while time.perf_counter() < fim:
        ok, frame = stream.read()
        if not ok or frame is None:
            time.sleep(0.01)
            continue
        carimbo = ler_carimbo(frame)
        atraso = None if carimbo is None else pub.atraso_ms(carimbo)
        if atraso is None:
            descartadas += 1
            continue
        amostras.append((time.perf_counter(), atraso))
    stream.release()
    return resumo(amostras, descartadas)


def medir_dashboard(pub: Publicador, url_mjpeg: str, segundos: float) -> dict[str, float]:
    """Trecho DASHBOARD: le o MJPEG do Flask por HTTP de verdade.

    Por HTTP, e nao chamando `latest_jpeg()` em processo, porque o gerador do
    endpoint dorme `1/TARGET_FPS` entre quadros — esse sono e atraso que o
    operador enxerga, e sumiria numa chamada direta.
    """
    import urllib.request

    amostras: list[tuple[float, float]] = []
    descartadas = 0
    fim = time.perf_counter() + segundos
    resposta = urllib.request.urlopen(url_mjpeg, timeout=15)  # noqa: S310  (localhost, do proprio bench)
    buffer = b""
    ultimo = None
    while time.perf_counter() < fim:
        pedaco = resposta.read(65536)
        if not pedaco:
            break
        buffer += pedaco
        # Extrai TODOS os JPEG completos do buffer, mas guarda so o ULTIMO.
        # Decodificar todos era um erro de medicao: o decode + leitura do
        # carimbo custa mais que os 1/TARGET_FPS entre quadros, entao este
        # leitor ficava para tras e passava a cronometrar a idade da FILA DELE
        # em vez da idade do que esta na tela. O navegador tambem so pinta o
        # ultimo quadro que chegou; medir como ele mede e o certo.
        mais_novo = None
        while True:  # JPEG entre os marcadores SOI (ffd8) e EOI (ffd9)
            inicio = buffer.find(b"\xff\xd8")
            termino = buffer.find(b"\xff\xd9", inicio + 2)
            if inicio < 0 or termino < 0:
                break
            mais_novo, buffer = buffer[inicio:termino + 2], buffer[termino + 2:]
        if mais_novo is None:
            continue
        frame = cv2.imdecode(np.frombuffer(mais_novo, np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            descartadas += 1
            continue
        carimbo = ler_carimbo(frame)
        atraso = None if carimbo is None else pub.atraso_ms(carimbo)
        if atraso is None:
            descartadas += 1
            continue
        # O MJPEG repete o ultimo frame quando o pipeline ainda nao produziu
        # um novo. Repetido nao e amostra: contaria a espera do gerador como
        # atraso do frame.
        if carimbo == ultimo:
            continue
        ultimo = carimbo
        amostras.append((time.perf_counter(), atraso))
    resposta.close()
    return resumo(amostras, descartadas)


def subir_app(url_rtsp: str, largura: int, altura: int, fps: int, porta: int, target_fps: int):
    """Sobe o Flask real com UMA camera na URL dada, ja monitorando.

    `AUTH_REQUIRED=False` (herdado de TestConfig): a sessao nao entra no caminho
    do frame — `login_required` roda uma vez, na abertura do stream — e exigir
    login aqui so acrescentaria um `users create` interativo ao bench.
    Declarado, nao escondido.
    """
    from app import create_app
    from app.config import TestConfig
    from app.extensions import db
    from app.models import DEFAULT_CAMERA_FEATURES, Camera
    from werkzeug.serving import make_server

    class Cfg(TestConfig):
        TARGET_FPS = target_fps
        # Sem fallback: se a fonte cair eu quero ver a falha, nao a fixture
        # assumindo o lugar dela e a latencia virar a de um arquivo local.
        RTSP_FIXTURE_FALLBACK = ""

    app = create_app(Cfg)
    with app.app_context():
        db.create_all()
        db.session.add(Camera(
            name="latencia", source_type="RTSP", source=url_rtsp,
            fps=fps, width=largura, height=altura,
            features_json=dict(DEFAULT_CAMERA_FEATURES),
        ))
        db.session.commit()
        monitor = app.extensions["monitor_service"]
        monitor.load_cameras_from_db()
        monitor.start_all()
        camera_id = Camera.query.one().id

    servidor = make_server("127.0.0.1", porta, app, threaded=True)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    return app, servidor, camera_id


def linha(nome: str, d: dict) -> str:
    if not d.get("n"):
        return f"{nome:<12} SEM AMOSTRA VALIDA (descartadas={d.get('descartadas', 0)})"
    deriva = d.get("deriva_ms_por_s")
    marca = "" if deriva is None else f"  deriva={deriva:+7.0f} ms/s"
    return (f"{nome:<12} p50={d['p50']:8.0f}  p95={d['p95']:8.0f}  min={d['min']:8.0f}  "
            f"max={d['max']:8.0f}{marca}   n={d['n']:4d}  desc={d['descartadas']}")


def main() -> int:
    analisador = argparse.ArgumentParser(description="Latencia publicacao -> dashboard.")
    analisador.add_argument("--ffmpeg", required=True, help="Caminho do ffmpeg (publicador).")
    analisador.add_argument("--url", required=True, help="URL RTSP para publicar E ler.")
    analisador.add_argument("--largura", type=int, default=704)
    analisador.add_argument("--altura", type=int, default=576)
    analisador.add_argument("--fps", type=int, default=15)
    analisador.add_argument("--kbps", type=int, default=512)
    analisador.add_argument("--segundos", type=float, default=25.0, help="Janela de cada fase.")
    analisador.add_argument("--porta", type=int, default=5099)
    analisador.add_argument("--target-fps", type=int, default=0,
                            help="TARGET_FPS do worker. 0 = igual ao da fonte. Acima do FPS "
                                 "da fonte da folga para o worker DRENAR fila acumulada.")
    analisador.add_argument("--lookahead", type=int, default=0,
                            help="rc-lookahead do x264. 0 = como encoder de camera.")
    analisador.add_argument("--json", default="")
    argumentos = analisador.parse_args()

    fixture = RAIZ / "tests" / "fixtures" / "bench.mp4"
    if not fixture.exists():
        raise SystemExit("fixture ausente: rode python scripts/fetch_fixtures.py")
    if argumentos.largura < LARGURA_CARIMBO:
        raise SystemExit(f"largura {argumentos.largura} < {LARGURA_CARIMBO} px do carimbo")

    print(f"\n=== latencia | {argumentos.largura}x{argumentos.altura} @ {argumentos.fps} fps, "
          f"{argumentos.kbps} kbps ===")
    print(f"destino: {redigir_segredos(argumentos.url)}")

    # --- fase 1: FONTE ---------------------------------------------------
    pub = Publicador(argumentos.ffmpeg, argumentos.url, fixture, argumentos.largura,
                     argumentos.altura, argumentos.fps, argumentos.kbps, argumentos.lookahead)
    time.sleep(4)  # o publicador precisa estar no ar antes de alguem ler
    print("fase 1/2: FONTE (publicacao -> VideoStream.read)...", flush=True)
    fonte = medir_fonte(pub, argumentos.url, argumentos.segundos, argumentos.largura, argumentos.altura)
    pub.parar()
    time.sleep(2)

    # --- fase 2: DASHBOARD -----------------------------------------------
    # Publicador novo: o t0 do carimbo tem que ser o mesmo relogio de quem le,
    # e o da fase 1 ja foi encerrado.
    pub2 = Publicador(argumentos.ffmpeg, argumentos.url, fixture, argumentos.largura,
                      argumentos.altura, argumentos.fps, argumentos.kbps, argumentos.lookahead)
    time.sleep(4)
    print("fase 2/2: DASHBOARD (publicacao -> MJPEG do Flask por HTTP)...", flush=True)
    app, servidor, camera_id = subir_app(argumentos.url, argumentos.largura, argumentos.altura,
                                         argumentos.fps, argumentos.porta,
                                         argumentos.target_fps or argumentos.fps)
    time.sleep(6)  # o worker abre a fonte e produz o primeiro frame
    # A rota POR CAMERA, que e a que o dashboard pede (camera-grid.tsx). A
    # legada `/video_feed` serve so a camera padrao e nao e o caminho real.
    painel = medir_dashboard(
        pub2, f"http://127.0.0.1:{argumentos.porta}/api/cameras/{camera_id}/video_feed",
        argumentos.segundos,
    )
    with app.app_context():
        app.extensions["monitor_service"].stop_all()
    servidor.shutdown()
    pub2.parar()

    print(f"\n{'trecho':<12} {'ms':>10}")
    print("-" * 78)
    print(linha("FONTE", fonte))
    print(linha("DASHBOARD", painel))
    if fonte.get("n") and painel.get("n"):
        print("-" * 78)
        print(f"{'pipeline + HTTP (subtracao dos p50)':<46} {painel['p50'] - fonte['p50']:8.0f} ms")
    # A leitura que importa, dita em voz alta: 100 ms/s de deriva quer dizer
    # que a cada 10 s de operacao o video na tela envelhece 1 s a mais.
    for nome, d in (("FONTE", fonte), ("DASHBOARD", painel)):
        deriva = d.get("deriva_ms_por_s")
        if deriva is None or abs(deriva) <= 20:
            continue
        # O SINAL importa, e confundi-lo inverte o diagnostico. Positivo: a
        # fila cresce, o consumidor nao acompanha a fonte. Negativo: a fila
        # esta ESVAZIANDO — tipico logo depois do start, quando o backlog
        # acumulado enquanto o worker subia esta sendo drenado. Alarme de
        # "consumidor lento" numa deriva negativa mandaria degradar justamente
        # o pipeline que esta se recuperando sozinho.
        if deriva > 0:
            print(f"\nATENCAO: {nome} nao tem atraso estavel, tem FILA CRESCENDO "
                  f"({deriva:+.0f} ms/s = {deriva * 60 / 1000:+.1f} s a cada minuto).")
            print("         O consumidor e mais lento que a fonte. Baixe o FPS da camera")
            print("         ou o custo por frame ate a deriva zerar; so entao o p50 vale.")
        else:
            print(f"\nNOTA: {nome} esta DRENANDO fila ({deriva:+.0f} ms/s). O consumidor e")
            print("      mais rapido que a fonte e o atraso esta CAINDO — comportamento")
            print("      esperado depois do start. O p50 tende ao piso; confirme com uma")
            print("      janela mais longa, em que a parte drenada pesa menos.")
    print("\nFora da conta: o navegador decodificar e pintar o MJPEG.")

    if argumentos.json:
        Path(argumentos.json).write_text(
            json.dumps({"perfil": {"largura": argumentos.largura, "altura": argumentos.altura,
                                   "fps": argumentos.fps, "kbps": argumentos.kbps},
                        "fonte": fonte, "dashboard": painel}, indent=2),
            encoding="utf-8",
        )
        print(f"JSON: {argumentos.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
