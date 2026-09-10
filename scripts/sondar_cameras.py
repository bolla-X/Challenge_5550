"""Sonda as câmeras da planta: porta, abertura, resolução e FPS REAL.

É o primeiro comando do runbook de campo (docs/DEMO.md). Responde, para cada
endereço e para **os dois subtypes**, as únicas perguntas que decidem o resto
do dia:

1. a porta RTSP aceita conexão?
2. abre e entrega frame?
3. que resolução e que FPS **de verdade** — não o que o stream declara?
4. (com `--pessoas`) a pessoa aparece grande o bastante para avaliar EPI?

Por que os dois subtypes na mesma passada: o cadastro tem default
`subtype=1` (substream) por custo medido, mas o substream pode estar
desabilitado na câmera, e a imagem dele pode ser pequena demais para o EPI
aparecer. Sondar os dois de uma vez transforma essa decisão numa leitura de
tabela, em vez de duas rodadas de tentativa e erro na frente do cliente.

Por que FPS medido e não `CAP_PROP_FPS`: o segundo é o que o stream **declara**
no cabeçalho, e câmera IP mente com frequência (declara 25 e entrega 8 quando a
rede aperta). O que importa para o pipeline é o que chega.

O que já existia e não serve: `GET /api/cameras/discover` só varre índice USB
(está na docstring dele), e `CameraWorker.preflight()` confere a config de uma
câmera JÁ CADASTRADA — não abre fonte de rede, não mede resolução nem FPS.
Sondar tem que vir antes do cadastro, senão o cadastro é chute.

A CREDENCIAL VEM DO `.env` (`RTSP_USUARIO`/`RTSP_SENHA`), nunca de argumento:
argumento fica no histórico do shell e em `ps aux`. Toda saída passa por
`redigir_segredos`.

Uso:

    python scripts/sondar_cameras.py 192.0.2.10 192.0.2.11 192.0.2.12
    python scripts/sondar_cameras.py --pessoas 192.0.2.10
    python scripts/sondar_cameras.py --url "rtsp://usuario:senha@localhost:8554/cam/realmonitor"
"""

from __future__ import annotations

import argparse
import socket
import sys
import time
from pathlib import Path

import cv2

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from app.config import CAMINHO_RTSP_PADRAO, Config, montar_url_rtsp  # noqa: E402
from app.llm import redigir_segredos  # noqa: E402
from app.vision.video_stream import abrir_captura  # noqa: E402

DESTINO_QUADROS = RAIZ / "runtime" / "sondagem"
# Quadros espalhados pela janela para julgar enquadramento. Poucos de
# proposito: cada um custa uma inferencia de pessoa, e a sondagem de campo
# roda 10 vezes (5 enderecos x 2 subtypes).
MAX_AMOSTRAS_DE_PESSOA = 4


class Resultado:
    """Uma linha da tabela. Tudo opcional porque a sonda para no primeiro
    nível que falhar — não adianta medir FPS de uma porta que nem abriu."""

    def __init__(self, rotulo: str, subtype: int | None) -> None:
        self.rotulo = rotulo
        self.subtype = subtype
        self.porta_ok: bool | None = None
        self.abriu = False
        self.largura = 0
        self.altura = 0
        self.fps_declarado = 0.0
        self.fps_real = 0.0
        self.frames = 0
        self.ms_abertura = 0.0
        self.pessoas: int | None = None
        self.altura_pessoa_pct = 0.0
        self.quadro = None
        self.candidatos: list = []
        self.erro = ""


def porta_aceita(host: str, porta: int, timeout: float) -> bool:
    """TCP puro, antes de gastar segundos no OpenCV.

    Separado da abertura RTSP de propósito: `abriu: False` sozinho não
    distingue "não há rota" de "credencial errada", e são ações diferentes.
    """
    try:
        with socket.create_connection((host, porta), timeout=timeout):
            return True
    except OSError:
        return False


def medir_fluxo(url: str, segundos: float, teto_ms: int) -> Resultado:
    resultado = Resultado(url, None)
    inicio_abertura = time.perf_counter()
    captura = abrir_captura(url, open_timeout_ms=teto_ms)
    resultado.ms_abertura = (time.perf_counter() - inicio_abertura) * 1000.0
    if not captura.isOpened():
        resultado.erro = "nao abriu (credencial, caminho ou servico RTSP)"
        captura.release()
        return resultado

    ok, primeiro = captura.read()
    if not ok or primeiro is None:
        resultado.erro = "abriu mas nao entregou frame (substream desabilitado?)"
        captura.release()
        return resultado

    resultado.abriu = True
    resultado.altura, resultado.largura = primeiro.shape[:2]
    resultado.fps_declarado = float(captura.get(cv2.CAP_PROP_FPS) or 0.0)
    resultado.quadro = primeiro

    # Drena antes de medir. Na abertura ha frames JA BUFERIZADOS (no servidor,
    # no socket e no decoder), e eles saem o mais rapido que o loop consegue
    # ler — nao na taxa da camera. Medido contra o servidor local de perfil
    # Dahua: sem drenar, um stream de 15 fps declarados media 17,36 fps.
    # Com drenagem de 1 s, cai para a taxa real. Sem isto a sondagem de campo
    # reportaria uma camera mais rapida do que ela e, que e o erro caro.
    fim_da_drenagem = time.perf_counter() + 1.0
    while time.perf_counter() < fim_da_drenagem:
        if not captura.read()[0]:
            break

    # FPS real: conta o que chega numa janela de parede. De passagem, guarda
    # alguns quadros espalhados pela janela: julgar enquadramento pelo PRIMEIRO
    # frame e enganoso — contra o servidor local o primeiro quadro nao tinha
    # ninguem e a sonda reportou "0 pessoas" para uma cena que tem tres. O
    # criterio do passo (b) do runbook depende disto estar certo.
    contados = 0
    candidatos: list = []
    proxima_amostra = 0.0
    intervalo_amostra = max(0.5, segundos / MAX_AMOSTRAS_DE_PESSOA)
    inicio = time.perf_counter()
    while time.perf_counter() - inicio < segundos:
        ok, quadro = captura.read()
        if not ok:
            break
        contados += 1
        decorrido_ate_agora = time.perf_counter() - inicio
        if decorrido_ate_agora >= proxima_amostra and len(candidatos) < MAX_AMOSTRAS_DE_PESSOA:
            candidatos.append(quadro)
            proxima_amostra = decorrido_ate_agora + intervalo_amostra
    decorrido = time.perf_counter() - inicio
    captura.release()
    resultado.frames = contados
    resultado.fps_real = contados / decorrido if decorrido > 0 else 0.0
    resultado.candidatos = candidatos or [primeiro]
    return resultado


def medir_pessoas(resultado: Resultado, detector) -> None:
    """Quantas pessoas o modelo de pessoa ve, e qual a altura da maior caixa.

    A altura em % do frame e o numero que responde "da para avaliar EPI?" —
    capacete e oculos sao objetos pequenos DENTRO da pessoa. Numa pessoa que
    ocupa 10% da altura do quadro, o capacete tem uns poucos pixels e nenhum
    ajuste de confianca conserta isso.
    """
    melhor_altura = 0.0
    melhor_quadro = resultado.candidatos[0]
    resultado.pessoas = 0
    for quadro in resultado.candidatos:
        deteccoes = detector.detect(quadro)
        alturas = [d.box.y2 - d.box.y1 for d in deteccoes]
        # MAX entre as amostras, nao media: a pergunta e "esta camera CONSEGUE
        # enquadrar alguem de forma avaliavel?". Um quadro vazio no meio da
        # janela nao desqualifica o ponto de instalacao.
        resultado.pessoas = max(resultado.pessoas, len(deteccoes))
        if alturas and max(alturas) > melhor_altura:
            melhor_altura = max(alturas)
            melhor_quadro = quadro
    if melhor_altura:
        resultado.altura_pessoa_pct = 100.0 * melhor_altura / max(1, resultado.altura)
    # Grava o quadro que MELHOR representa o enquadramento, nao um qualquer.
    resultado.quadro = melhor_quadro


def nome_de_arquivo(rotulo: str) -> str:
    """Nome de arquivo seguro a partir do rotulo do alvo.

    Nao e cosmetica. O rotulo do modo `--url` e a URL REDIGIDA, que carrega
    `*`, `?`, `:` e `&` — todos ilegais em nome de arquivo no Windows. Com um
    `replace` parcial o `cv2.imwrite` falhava devolvendo `False` em silencio, e
    o passo (b) do runbook mandava olhar imagens que nunca tinham sido
    gravadas. Whitelist, e nao blacklist, justamente para nao depender de
    lembrar de todos.
    """
    seguro = "".join(c if (c.isalnum() or c in "-_.") else "_" for c in rotulo)
    return seguro.strip("_")[:100] or "alvo"


def salvar_quadro(resultado: Resultado, nome: str) -> None:
    """Grava o quadro mais representativo. Olhar as imagens lado a lado decide
    enquadramento mais rapido que qualquer metrica."""
    DESTINO_QUADROS.mkdir(parents=True, exist_ok=True)
    destino = DESTINO_QUADROS / f"{nome}.jpg"
    # `imwrite` nao levanta: devolve False. Sem checar, uma gravacao que falhou
    # vira "olhe as imagens" apontando para uma pasta vazia.
    if not cv2.imwrite(str(destino), resultado.quadro):
        resultado.erro = (resultado.erro + " | " if resultado.erro else "") + \
            f"nao consegui gravar {destino.name}"
        return
    resultado.quadro = destino


def main() -> int:
    analisador = argparse.ArgumentParser(
        description="Sonda RTSP de campo: porta, abertura, resolucao e FPS real.",
    )
    analisador.add_argument("hosts", nargs="*", help="IPs/hosts das cameras.")
    analisador.add_argument("--url", action="append", default=[], help="URL RTSP pronta (repetivel).")
    analisador.add_argument("--subtypes", default="0,1", help="Subtypes a sondar. Default: 0,1.")
    analisador.add_argument("--canal", type=int, default=1)
    analisador.add_argument("--porta", type=int, default=Config.RTSP_PORTA)
    analisador.add_argument("--segundos", type=float, default=3.0, help="Janela do FPS real.")
    analisador.add_argument("--teto-ms", type=int, default=5000, help="Teto de abertura, igual ao do worker.")
    analisador.add_argument("--pessoas", action="store_true", help="Roda o YOLO de pessoa no primeiro frame.")
    argumentos = analisador.parse_args()

    if not argumentos.hosts and not argumentos.url:
        analisador.error("informe ao menos um host ou --url")

    subtypes = [int(s) for s in argumentos.subtypes.split(",") if s.strip()]
    usuario = str(Config.RTSP_USUARIO or "")
    senha = str(Config.RTSP_SENHA or "")
    if argumentos.hosts and not (usuario and senha):
        print(
            "AVISO: RTSP_USUARIO/RTSP_SENHA vazios no .env — as URLs vao sem credencial.\n"
            "       Se a camera exigir login, todas darao 'nao abriu'.\n"
        )

    detector = None
    if argumentos.pessoas:
        from app.vision.yolo_ppe_detector import YoloPPEDetector  # import caro: so sob demanda

        detector = YoloPPEDetector(
            model_path=str(RAIZ / Config.PERSON_MODEL_PATH),
            confidence=Config.YOLO_CONFIDENCE,
            classes=[0],
            imgsz=Config.YOLO_IMGSZ,
            require_person=False,
        )

    alvos: list[tuple[str, int | None, str]] = []
    for host in argumentos.hosts:
        for subtype in subtypes:
            alvos.append((
                host,
                subtype,
                montar_url_rtsp(
                    host=host, usuario=usuario, senha=senha, porta=argumentos.porta,
                    canal=argumentos.canal, subtype=subtype,
                    caminho=str(Config.RTSP_CAMINHO or CAMINHO_RTSP_PADRAO),
                ),
            ))
    for url in argumentos.url:
        alvos.append((redigir_segredos(url), None, url))

    resultados: list[Resultado] = []
    for rotulo, subtype, url in alvos:
        nome = rotulo + (f"_sub{subtype}" if subtype is not None else "")
        print(f"sondando {redigir_segredos(nome)} ...", flush=True)
        if subtype is not None and not porta_aceita(rotulo, argumentos.porta, timeout=2.0):
            parcial = Resultado(rotulo, subtype)
            parcial.porta_ok = False
            parcial.erro = f"TCP {argumentos.porta} nao aceita conexao"
            resultados.append(parcial)
            continue
        resultado = medir_fluxo(url, argumentos.segundos, argumentos.teto_ms)
        resultado.rotulo, resultado.subtype = rotulo, subtype
        resultado.porta_ok = True if subtype is not None else None
        if resultado.abriu:
            if detector is not None and resultado.candidatos:
                medir_pessoas(resultado, detector)
            salvar_quadro(resultado, nome_de_arquivo(redigir_segredos(nome)))
        resultados.append(resultado)

    cabecalho = (
        f"\n{'alvo':<26} {'sub':>3} {'554':>4} {'abriu':>6} {'resolucao':>11} "
        f"{'fps decl':>9} {'fps real':>9} {'abrir ms':>9}"
    )
    if argumentos.pessoas:
        cabecalho += f" {'pessoas':>8} {'alt %':>6}"
    print(cabecalho)
    print("-" * (len(cabecalho) - 1))
    for r in resultados:
        sub = "-" if r.subtype is None else str(r.subtype)
        porta = "-" if r.porta_ok is None else ("ok" if r.porta_ok else "NAO")
        resolucao = f"{r.largura}x{r.altura}" if r.abriu else "-"
        linha = (
            f"{redigir_segredos(r.rotulo)[:26]:<26} {sub:>3} {porta:>4} {('sim' if r.abriu else 'NAO'):>6} "
            f"{resolucao:>11} {r.fps_declarado:>9.2f} {r.fps_real:>9.2f} {r.ms_abertura:>9.0f}"
        )
        if argumentos.pessoas:
            pessoas = "-" if r.pessoas is None else str(r.pessoas)
            linha += f" {pessoas:>8} {r.altura_pessoa_pct:>6.1f}"
        print(linha)
        if r.erro:
            print(f"{'':<26} +- {r.erro}")

    vivos = [r for r in resultados if r.abriu]
    print(f"\n{len(vivos)} de {len(resultados)} alvo(s) entregaram frame.")
    if vivos:
        print(f"Primeiro frame de cada um em: {DESTINO_QUADROS.relative_to(RAIZ)}")
        print("Escolha as 2 com a pessoa MAIOR no quadro: capacete e oculos sao objetos")
        print("pequenos dentro dela, e resolucao de fonte nao compensa enquadramento ruim.")
    return 0 if vivos else 1


if __name__ == "__main__":
    sys.exit(main())
