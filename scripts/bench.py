"""Benchmark ponta a ponta do VisionEPI — um comando, servidor REAL.

    python scripts/bench.py                    # 2 perfis x {1, 4} câmeras, 60 s cada
    python scripts/bench.py --perfis batata --cameras 4 --duracao 90
    python scripts/bench.py --soak 1200        # soak de 20 min, 4 câmeras
    python scripts/bench.py --env YOLO_IMGSZ=320 --rotulo imgsz320

O que ele faz, e por que cada passo é assim:

1. **Sobe o servidor de verdade** (`run.py`) num subprocesso com configuração
   explícita (`VISIONEPI_DOTENV=0`): o `.env` de quem roda não entra, então
   duas máquinas medem a mesma coisa. Banco e snapshots ficam em
   `bench/runtime/`, isolados dos dados reais.
2. **Câmeras de fixture** (`tests/fixtures/*.mp4`, baixadas por
   `scripts/fetch_fixtures.py` se faltarem) cadastradas pela API, como um
   técnico faria.
3. **Mede dentro do servidor** pelo `/api/diagnostics/pipeline`: p50/p95/p99
   de cada etapa do loop (captura, inferência EPI, pessoa, tracking, pose,
   regras, alertas, anotação, encode, emissão) e taxas (frames lidos,
   publicados, inferências, enviados, bytes).
4. **Mede no navegador** (Playwright/Chromium headless): a tela de foco da
   câmera 1 aberta como um operador abriria, mais uma sonda que lê o MJPEG por
   `fetch`, decodifica cada quadro (`createImageBitmap`) e calcula a idade do
   quadro (agora − `X-Capture-Ts`). Long tasks e commits do React vêm da
   Performance API e do hook de devtools; bytes do Socket.IO, do Resource
   Timing.
5. **Mede o processo** com psutil: CPU e RSS a cada segundo; tempo de subida e
   de carga do modelo.

Perfis de hardware (sempre os dois, salvo `--perfis`):

- `atual`: a máquina como está.
- `batata`: 2 threads (`OMP_NUM_THREADS=2`, `torch.set_num_threads(2)`,
  `cv2.setNumThreads(2)`) e afinidade em 2 núcleos lógicos — os 2 mais LENTOS
  da máquina, medidos no início (num híbrido Intel são E-cores), sem GPU.

Saída: `bench/results/<timestamp>.json` e uma tabela no terminal.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import secrets
import socket
import statistics
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parent.parent
PY = sys.executable
DIR_RESULTADOS = RAIZ / "bench" / "results"
DIR_RUNTIME = RAIZ / "bench" / "runtime"

# Configuração de referência = a do `.env.example` (o que o README manda usar).
CONFIG_BASE = {
    "VISIONEPI_DOTENV": "0",
    "HOST": "127.0.0.1",
    "AUTH_REQUIRED": "true",
    "AUTO_CREATE_TABLES": "true",
    "FLASK_DEBUG": "false",
    "PPE_MODEL_PATH": "models/vyra_ppe.pt",
    "PERSON_MODEL_PATH": "models/yolov8n.pt",
    "YOLO_CLASSES": "0,1,2,3,5,11,12,13",
    "YOLO_CONFIDENCE": "0.35",
    "YOLO_DEVICE": "",
    "PPE_CONF_MIN_BY_CLASS": "helmet:0.40,vest:0.40,gloves:0.30,mask:0.30,glasses:0.15,ear_protection:0.30",
    "MULTI_PERSON_DETECTION": "true",
    "YOLO_IMGSZ": "416",
    "DETECTION_EVERY_N_FRAMES": "3",
    "TARGET_FPS": "12",
    "JPEG_QUALITY": "80",
    "POSE_PER_PERSON": "true",
    "POSE_MAX_PEOPLE": "4",
    "ALERT_CREATE_AFTER_FRAMES": "8",
    "ALERT_RESOLVE_AFTER_FRAMES": "20",
    "TELEMETRY_HZ": "8",
    "LLM_ENABLED": "false",
    "DEFAULT_FEATURES": "ppe,helmet,vest,gloves,glasses,mask,safety_shoe,ear_protection,pose,falls,posture,risk_area",
    "CLEANUP_ON_MONITOR_START": "true",
    "PYTHONUNBUFFERED": "1",
}

FIXTURES_1CAM = ["bench"]
FIXTURES_4CAM = ["bench", "multidao", "queda", "bench"]

# Sonda do navegador. Lê o MJPEG por fetch, decodifica e mede idade/decodificação.
JS_INIT = r"""
window.__bench = {longtasks: [], commits: 0, raf: 0, erros: []};
try {
  new PerformanceObserver((l) => l.getEntries().forEach((e) => window.__bench.longtasks.push([e.startTime, e.duration])))
    .observe({type: 'longtask', buffered: true});
} catch (e) {}
window.__REACT_DEVTOOLS_GLOBAL_HOOK__ = {
  supportsFiber: true, renderers: new Map(), isDisabled: false,
  inject(r) { const id = this.renderers.size + 1; this.renderers.set(id, r); return id; },
  onCommitFiberRoot() { window.__bench.commits++; }, onCommitFiberUnmount() {}, onPostCommitFiberRoot() {},
  checkDCE() {}, on() {}, off() {}, emit() {}, sub() { return () => {}; },
};
(function loop() { window.__bench.raf++; requestAnimationFrame(loop); })();
window.addEventListener('error', (e) => window.__bench.erros.push(String(e.message)));
"""

JS_SONDA = r"""
async ([url, durMs]) => {
  const st = {frames: 0, bytes: 0, idades: [], decode: [], chegadas: [], dup: 0, erro: null};
  window.__sonda = st;
  const ctrl = new AbortController();
  let ultimoId = null;
  try {
    const resp = await fetch(url, {signal: ctrl.signal, credentials: 'same-origin'});
    const reader = resp.body.getReader();
    let buf = new Uint8Array(0);
    const fim = performance.now() + durMs;
    const canvas = new OffscreenCanvas(32, 32); const ctx = canvas.getContext('2d');
    const acha = (a, seq, de) => {
      outer: for (let i = de; i <= a.length - seq.length; i++) {
        for (let j = 0; j < seq.length; j++) if (a[i + j] !== seq[j]) continue outer;
        return i;
      }
      return -1;
    };
    const SEP = new TextEncoder().encode('\r\n\r\n');
    while (performance.now() < fim) {
      const {value, done} = await reader.read();
      if (done) break;
      const novo = new Uint8Array(buf.length + value.length); novo.set(buf); novo.set(value, buf.length); buf = novo;
      st.bytes += value.length;
      while (true) {
        const h = acha(buf, SEP, 0);
        if (h < 0) break;
        const cab = new TextDecoder().decode(buf.slice(0, h));
        const m = /Content-Length:\s*(\d+)/i.exec(cab);
        if (!m) { buf = buf.slice(h + 4); continue; }
        const len = parseInt(m[1], 10);
        if (buf.length < h + 4 + len) break;
        const jpeg = buf.slice(h + 4, h + 4 + len);
        buf = buf.slice(h + 4 + len);
        const ts = /X-Capture-Ts:\s*([\d.]+)/i.exec(cab);
        const id = /X-Frame-Id:\s*(-?\d+)/i.exec(cab);
        if (id && id[1] === ultimoId) st.dup++;
        ultimoId = id ? id[1] : null;
        const t0 = performance.now();
        const bmp = await createImageBitmap(new Blob([jpeg], {type: 'image/jpeg'}));
        ctx.drawImage(bmp, 0, 0, 32, 32); bmp.close();
        st.decode.push(performance.now() - t0);
        st.chegadas.push(performance.now());
        if (ts) st.idades.push(Date.now() - parseFloat(ts[1]));
        st.frames++;
      }
    }
  } catch (e) { if (e.name !== 'AbortError') st.erro = String(e); }
  ctrl.abort();
  return st;
}
"""


# ----------------------------------------------------------------- utilidades
def porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def pct(valores: list[float], p: float) -> float | None:
    if not valores:
        return None
    ordenados = sorted(valores)
    pos = (len(ordenados) - 1) * p / 100
    baixo = int(pos)
    alto = min(baixo + 1, len(ordenados) - 1)
    return round(ordenados[baixo] + (ordenados[alto] - ordenados[baixo]) * (pos - baixo), 2)


def nome_da_cpu() -> str:
    if sys.platform == "win32":
        try:
            import winreg

            chave = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
            return str(winreg.QueryValueEx(chave, "ProcessorNameString")[0]).strip()
        except OSError:
            pass
    return platform.processor() or "desconhecida"


def versoes() -> dict[str, str | None]:
    saida: dict[str, str | None] = {"python": platform.python_version()}
    for modulo in ("torch", "ultralytics", "cv2", "onnxruntime", "openvino", "mediapipe", "numpy", "flask_socketio"):
        try:
            mod = __import__(modulo)
            saida[modulo] = getattr(mod, "__version__", None)
        except Exception:  # noqa: BLE001
            saida[modulo] = None
    return saida


def nucleos_mais_lentos(n: int = 2) -> list[int]:
    """Os `n` núcleos lógicos mais lentos, por um laço de Python preso em cada um.

    Num i7 híbrido (P + E cores) isso acha os E-cores sem depender de API de
    topologia — e é o que torna o perfil "batata" honesto: 2 núcleos fracos, não
    2 threads de um P-core.
    """
    import psutil

    proc = psutil.Process()
    original = proc.cpu_affinity()
    tempos: list[tuple[float, int]] = []
    try:
        for cpu in original:
            proc.cpu_affinity([cpu])
            time.sleep(0.02)
            melhor = float("inf")
            for _ in range(3):
                inicio = time.perf_counter()
                x = 0
                for i in range(400_000):
                    x += i * i
                melhor = min(melhor, time.perf_counter() - inicio)
            tempos.append((melhor, cpu))
    finally:
        proc.cpu_affinity(original)
    tempos.sort(reverse=True)
    return sorted(cpu for _, cpu in tempos[:n])


def info_da_maquina() -> dict[str, Any]:
    import psutil

    gpu = None
    try:
        import torch

        gpu = torch.cuda.get_device_name(0) if torch.cuda.is_available() else None
    except Exception:  # noqa: BLE001
        pass
    return {
        "cpu": nome_da_cpu(),
        "nucleos_fisicos": psutil.cpu_count(logical=False),
        "nucleos_logicos": psutil.cpu_count(logical=True),
        "ram_gb": round(psutil.virtual_memory().total / 2**30, 1),
        "gpu_cuda": gpu,
        "so": f"{platform.system()} {platform.release()} ({platform.version()})",
        "versoes": versoes(),
    }


def garantir_fixtures(nomes: list[str]) -> dict[str, Path]:
    sys.path.insert(0, str(RAIZ / "scripts"))
    import fetch_fixtures  # noqa: PLC0415

    caminhos = {}
    faltando = [n for n in set(nomes) if not next(f for f in fetch_fixtures.FIXTURES if f.nome == n).arquivo_destino.exists()]
    if faltando:
        print(f"[bench] fixtures ausentes ({', '.join(faltando)}): baixando via scripts/fetch_fixtures.py")
        subprocess.run([PY, str(RAIZ / "scripts" / "fetch_fixtures.py")], check=True, cwd=RAIZ)
    for nome in set(nomes):
        caminhos[nome] = fetch_fixtures.caminho_da_fixture(nome)
    return caminhos


# ------------------------------------------------------------------- servidor
class Servidor:
    def __init__(self, env: dict[str, str], rotulo: str, *, afinidade: list[int] | None, arvore: Path = RAIZ) -> None:
        self.arvore = arvore
        self.porta = porta_livre()
        self.base = f"http://127.0.0.1:{self.porta}"
        DIR_RUNTIME.mkdir(parents=True, exist_ok=True)
        banco = DIR_RUNTIME / f"{rotulo}.db"
        for sufixo in ("", "-journal", "-wal", "-shm"):
            Path(str(banco) + sufixo).unlink(missing_ok=True)
        self.senha = secrets.token_urlsafe(18)
        self.email = "bench@visionepi.local"
        self.env = os.environ.copy() | CONFIG_BASE | env | {
            "PORT": str(self.porta),
            "SECRET_KEY": secrets.token_hex(32),
            "DATABASE_URL": f"sqlite:///{banco.as_posix()}",
            "SNAPSHOT_DIR": f"bench/runtime/{rotulo}-snapshots",
            "CLEANUP_DIRECTORIES": f"bench/runtime/{rotulo}-snapshots",
        }
        if afinidade:
            self.env["VISIONEPI_CPUS"] = ",".join(str(c) for c in afinidade)
        self.log = DIR_RUNTIME / f"{rotulo}.log"
        self.proc: subprocess.Popen | None = None

    def criar_usuario(self) -> None:
        subprocess.run(
            [PY, "-m", "flask", "--app", "wsgi", "users", "create", "--email", self.email, "--name", "Bench",
             "--role", "technical", "--password", self.senha],
            cwd=self.arvore, env=self.env, check=True, capture_output=True,
        )

    def subir(self) -> float:
        inicio = time.perf_counter()
        self.proc = subprocess.Popen(
            [PY, "run.py"], cwd=self.arvore, env=self.env, stdout=self.log.open("w", encoding="utf-8"), stderr=subprocess.STDOUT
        )
        import requests

        while time.perf_counter() - inicio < 180:
            if self.proc.poll() is not None:
                raise SystemExit(f"servidor morreu na subida; ver {self.log}")
            try:
                if requests.get(self.base + "/api/auth/me", timeout=1).status_code in (200, 401):
                    return round(time.perf_counter() - inicio, 2)
            except requests.RequestException:
                pass
            time.sleep(0.2)
        raise SystemExit("servidor não respondeu em 180 s")

    def parar(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()


# ------------------------------------------------------------------- uma rodada
def rodar(
    *, rotulo: str, perfil: str, fixtures: list[str], caminhos: dict[str, Path], duracao: float, aquecimento: float,
    env_extra: dict[str, str], afinidade_batata: list[int], soak_s: float = 0.0, arvore: Path = RAIZ,
    prioridade_alta: bool = True,
) -> dict[str, Any]:
    import psutil
    import requests
    from playwright.sync_api import sync_playwright

    env = dict(env_extra)
    afinidade = None
    if perfil == "batata":
        env |= {"OMP_NUM_THREADS": "2", "MKL_NUM_THREADS": "2", "OPENBLAS_NUM_THREADS": "2", "VISIONEPI_THREADS": "2",
                "CUDA_VISIBLE_DEVICES": ""}
        afinidade = afinidade_batata
    srv = Servidor(env, rotulo, afinidade=afinidade, arvore=arvore)
    srv.criar_usuario()
    resultado: dict[str, Any] = {"rotulo": rotulo, "perfil": perfil, "fixtures": fixtures, "afinidade": afinidade,
                                 "env_extra": env_extra, "duracao_s": duracao, "aquecimento_s": aquecimento,
                                 "arvore": str(arvore), "prioridade_alta": prioridade_alta}
    try:
        resultado["startup_s"] = srv.subir()
        sessao = requests.Session()
        sessao.post(srv.base + "/api/auth/login", json={"email": srv.email, "password": srv.senha}, timeout=10).raise_for_status()
        ids = []
        for i, nome in enumerate(fixtures, start=1):
            corpo = {"name": f"Fixture {i} ({nome})", "source_type": "Arquivo", "source": str(caminhos[nome]),
                     "fps": int(CONFIG_BASE["TARGET_FPS"]) if "TARGET_FPS" not in env_extra else int(env_extra["TARGET_FPS"]),
                     "width": 960, "height": 540}
            r = sessao.post(srv.base + "/api/cameras", json=corpo, timeout=10)
            r.raise_for_status()
            ids.append(r.json()["id"])
        t_start = time.perf_counter()
        for cid in ids:
            sessao.post(f"{srv.base}/api/cameras/{cid}/start", timeout=60).raise_for_status()
        # Primeiro frame publicado da câmera 1 = modelo carregado + 1ª inferência.
        while time.perf_counter() - t_start < 120:
            d = sessao.get(srv.base + "/api/diagnostics/pipeline?janela_s=5", timeout=10).json()
            if d["cameras"].get(str(ids[0]), {}).get("stats", {}).get("totais", {}).get("frames_publicados"):
                break
            time.sleep(0.25)
        resultado["primeiro_frame_s"] = round(time.perf_counter() - t_start, 2)
        resultado["modelos"] = d.get("modelos")

        # No Windows o python.exe do venv é um LANÇADOR que sobe o interpretador
        # real como filho: medir só o pid do Popen daria ~0% de CPU e 3 MB.
        raiz_proc = psutil.Process(srv.proc.pid)
        processos = [raiz_proc, *raiz_proc.children(recursive=True)]
        # Prioridade alta no servidor (os dois lados de toda comparação recebem
        # a mesma): a máquina de medição divide a CPU com outros processos que
        # não são deste projeto (registrados em `carga_de_fundo_pct`). Sem isto,
        # a baseline mediu a disputa por CPU, não o VisionEPI.
        if prioridade_alta:
            for p_ in processos:
                try:
                    p_.nice(psutil.HIGH_PRIORITY_CLASS if sys.platform == "win32" else -5)
                except (psutil.Error, OSError):
                    resultado["prioridade_alta"] = False
        for p_ in processos:
            p_.cpu_percent(None)
        psutil.cpu_percent(None)
        n_logicos = psutil.cpu_count(logical=True)

        def amostrar(t: float) -> dict[str, float]:
            cpu_srv = sum(p_.cpu_percent(None) for p_ in processos if p_.is_running())
            rss = sum(p_.memory_info().rss for p_ in processos if p_.is_running())
            total = psutil.cpu_percent(None) * n_logicos  # em "% de um núcleo", como o do servidor
            return {"t": round(t, 1), "cpu_pct": round(cpu_srv, 1), "rss_mb": round(rss / 2**20, 1),
                    "carga_de_fundo_pct": round(max(0.0, total - cpu_srv), 1)}
        with sync_playwright() as pw:
            navegador = pw.chromium.launch(headless=True)
            # O navegador também é parte do sistema medido: com só o servidor em
            # prioridade alta, o Chromium passava fome numa máquina carregada,
            # não acompanhava o stream e a idade do quadro media o buffer TCP.
            if prioridade_alta:
                for p_ in psutil.Process().children(recursive=True):
                    if p_.pid in {q.pid for q in processos}:
                        continue
                    try:
                        p_.nice(psutil.HIGH_PRIORITY_CLASS if sys.platform == "win32" else -5)
                    except (psutil.Error, OSError):
                        pass
            contexto = navegador.new_context(viewport={"width": 1366, "height": 768})
            contexto.add_cookies([{"name": c.name, "value": c.value, "url": srv.base} for c in sessao.cookies])
            contexto.add_init_script(JS_INIT)
            pagina = contexto.new_page()
            console_erros: list[str] = []
            pagina.on("console", lambda m: console_erros.append(m.text) if m.type == "error" else None)
            pagina.goto(srv.base + "/", wait_until="load")
            # Abre o foco da câmera 1, como o técnico faria.
            pagina.get_by_role("button", name=f"Configurar Fixture 1 ({fixtures[0]})").click(timeout=30000)
            pagina.wait_for_timeout(1000)

            time.sleep(aquecimento)
            amostras: list[dict[str, float]] = []
            marca = pagina.evaluate("() => ({lt: window.__bench.longtasks.length, c: window.__bench.commits, raf: window.__bench.raf,"
                                    " t: performance.now()})")
            pagina.evaluate("() => performance.clearResourceTimings()")
            pagina.evaluate("() => performance.setResourceTimingBufferSize(100000)")
            janela = soak_s or duracao
            # Dispara a sonda SEM esperar: a promessa fica em window e é colhida no fim.
            pagina.evaluate(f"() => {{ window.__sondaP = ({JS_SONDA})(['/api/cameras/{ids[0]}/video_feed', {int(janela * 1000)}]); }}")
            inicio = time.perf_counter()
            while time.perf_counter() - inicio < janela:
                amostras.append(amostrar(time.perf_counter() - inicio))
                time.sleep(1.0 if not soak_s else 10.0)
            estado_sonda = pagina.evaluate("() => window.__sondaP")
            fim_navegador = pagina.evaluate(
                "() => ({lt: window.__bench.longtasks, c: window.__bench.commits, raf: window.__bench.raf, t: performance.now(),"
                " erros: window.__bench.erros,"
                " sio: performance.getEntriesByType('resource').filter(e => e.name.includes('/socket.io/'))"
                "   .reduce((a, e) => a + (e.transferSize || e.encodedBodySize || 0), 0)})"
            )
            diag = sessao.get(f"{srv.base}/api/diagnostics/pipeline?janela_s={min(120, int(duracao))}", timeout=10).json()
            navegador.close()

        dt_nav = (fim_navegador["t"] - marca["t"]) / 1000.0
        longas = [d for s, d in fim_navegador["lt"][marca["lt"]:]]
        chegadas = estado_sonda.get("chegadas") or []
        intervalos = [b - a for a, b in zip(chegadas, chegadas[1:], strict=False)]
        resultado["navegador"] = {
            "fps_exibido_sonda": round(estado_sonda["frames"] / janela, 2),
            "quadros_repetidos": estado_sonda.get("dup"),
            "idade_quadro_ms": {"p50": pct(estado_sonda["idades"], 50), "p95": pct(estado_sonda["idades"], 95),
                                "p99": pct(estado_sonda["idades"], 99)},
            "decode_ms": {"p50": pct(estado_sonda["decode"], 50), "p95": pct(estado_sonda["decode"], 95)},
            "intervalo_entre_quadros_ms": {"p50": pct(intervalos, 50), "p95": pct(intervalos, 95), "p99": pct(intervalos, 99)},
            "video_bytes_por_s": round(estado_sonda["bytes"] / janela),
            "socketio_bytes_por_s": round(fim_navegador["sio"] / dt_nav) if dt_nav > 0 else None,
            "long_tasks": len(longas),
            "long_task_ms_total": round(sum(longas), 1),
            "react_commits_por_s": round((fim_navegador["c"] - marca["c"]) / dt_nav, 2) if dt_nav > 0 else None,
            "raf_fps": round((fim_navegador["raf"] - marca["raf"]) / dt_nav, 1) if dt_nav > 0 else None,
            "erros_console": console_erros[:20],
            "erros_js": fim_navegador["erros"][:20],
            "erro_sonda": estado_sonda.get("erro"),
        }
        cpus = [a["cpu_pct"] for a in amostras[1:]] or [0.0]
        fundo = [a["carga_de_fundo_pct"] for a in amostras[1:]] or [0.0]
        rss = [a["rss_mb"] for a in amostras]
        resultado["processo"] = {
            "cpu_pct_media": round(statistics.mean(cpus), 1),
            "cpu_pct_p95": pct(cpus, 95),
            # Outros processos da máquina, em % de um núcleo (1200 = 12 núcleos
            # lógicos cheios). Benchmark com fundo alto não compara com fundo baixo.
            "carga_de_fundo_pct_media": round(statistics.mean(fundo), 1),
            "rss_mb_inicio": rss[0] if rss else None,
            "rss_mb_fim": rss[-1] if rss else None,
            "rss_mb_max": max(rss) if rss else None,
            "amostras": amostras,
        }
        resultado["cameras"] = {}
        for i, cid in enumerate(ids):
            c = diag["cameras"].get(str(cid), {})
            st = c.get("stats", {})
            taxas = st.get("taxas_por_s", {})
            fonte = c.get("fonte_fps")
            resultado["cameras"][str(cid)] = {
                "fixture": fixtures[i],
                "fonte_fps": fonte,
                "fps_lido": taxas.get("frames_lidos"),
                "fps_publicado": taxas.get("frames_publicados"),
                "fps_inferencia": taxas.get("inferencias"),
                "fps_enviado": taxas.get("frames_enviados"),
                "frames_descartados_por_s": taxas.get("frames_descartados", 0.0),
                # Arquivo tocado abaixo do FPS dele = câmera lenta: o vídeo fica para trás do "tempo real".
                "fracao_do_tempo_real": round(taxas.get("frames_lidos", 0) / fonte, 3) if fonte else None,
                "bytes_video_por_s": taxas.get("bytes_video"),
                "etapas": st.get("etapas"),
            }
    finally:
        srv.parar()
    return resultado


# ------------------------------------------------------------------- relatório
ETAPAS_TABELA = ["captura", "espera_do_lock", "inferencia_epi", "inferencia_pessoa", "tracking", "pose", "regras", "alertas",
                 "anotacao", "encode", "emissao", "loop_total", "idade_publicacao"]


def tabela(resultados: list[dict[str, Any]]) -> str:
    linhas = []
    cab = f"{'rodada':28s} {'fps_lido':>8s} {'fps_inf':>8s} {'fps_pub':>8s} {'tempo_real':>10s} {'idade_p95':>9s} " \
          f"{'exib_fps':>8s} {'epi_p95':>8s} {'loop_p95':>8s} {'cpu%':>6s} {'rss_mb':>7s} {'fundo%':>7s}"
    linhas.append(cab)
    linhas.append("-" * len(cab))
    for r in resultados:
        cams = list(r.get("cameras", {}).values())
        if not cams:
            continue

        def media(chave, cams=cams):
            vals = [c.get(chave) for c in cams if c.get(chave) is not None]
            return round(statistics.mean(vals), 2) if vals else None

        def etapa(nome, campo="p95", cams=cams):
            vals = [c["etapas"][nome][campo] for c in cams if c.get("etapas") and nome in c["etapas"]]
            return round(statistics.mean(vals), 1) if vals else None

        nav = r.get("navegador", {})
        linhas.append(
            f"{r['rotulo']:28s} {media('fps_lido') or 0:8.2f} {media('fps_inferencia') or 0:8.2f} {media('fps_publicado') or 0:8.2f} "
            f"{media('fracao_do_tempo_real') or 0:10.2f} {nav.get('idade_quadro_ms', {}).get('p95') or 0:9.0f} "
            f"{nav.get('fps_exibido_sonda') or 0:8.2f} {etapa('inferencia_epi') or 0:8.1f} {etapa('loop_total') or 0:8.1f} "
            f"{r['processo']['cpu_pct_media']:6.0f} {r['processo']['rss_mb_max'] or 0:7.0f} "
            f"{r['processo'].get('carga_de_fundo_pct_media') or 0:7.0f}"
        )
    return "\n".join(linhas)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--perfis", default="atual,batata")
    ap.add_argument("--cameras", default="1,4", help="cenários: lista de 1 e/ou 4")
    ap.add_argument("--duracao", type=float, default=60.0)
    ap.add_argument("--aquecimento", type=float, default=15.0)
    ap.add_argument("--soak", type=float, default=0.0, help="segundos de soak (4 câmeras, perfil atual)")
    ap.add_argument("--env", action="append", default=[], help="KEY=VAL extra para o servidor")
    ap.add_argument("--rotulo", default="", help="sufixo do nome da rodada/arquivo")
    ap.add_argument("--arvores", default="", help="rotulo=caminho,... : compara árvores de código INTERCALADAS")
    ap.add_argument("--sem-prioridade", action="store_true", help="não eleva a prioridade do servidor")
    args = ap.parse_args()

    if args.duracao < 60 and not os.getenv("BENCH_PERMITE_CURTO"):
        print("[bench] duração mínima é 60 s (a missão exige); use BENCH_PERMITE_CURTO=1 só para depurar o script.")
        return 2
    env_extra = dict(item.split("=", 1) for item in args.env)
    perfis = [p.strip() for p in args.perfis.split(",") if p.strip()]
    cenarios = [int(c) for c in args.cameras.split(",") if c.strip()]
    if args.soak:
        perfis, cenarios = ["atual"], [4]
    nomes = sorted(set(FIXTURES_1CAM + FIXTURES_4CAM))
    caminhos = garantir_fixtures(nomes)

    maquina = info_da_maquina()
    afinidade_batata = nucleos_mais_lentos(2) if "batata" in perfis else []
    print(f"[bench] {maquina['cpu']} | {maquina['nucleos_logicos']} lógicos | {maquina['ram_gb']} GB | GPU: {maquina['gpu_cuda']}")
    if afinidade_batata:
        print(f"[bench] perfil batata: núcleos lógicos {afinidade_batata} (os 2 mais lentos medidos)")

    resultados = []
    carimbo = datetime.now().strftime("%Y%m%d-%H%M%S")
    arvores = [(item.split("=", 1)[0], Path(item.split("=", 1)[1]).resolve()) for item in args.arvores.split(",") if "=" in item]
    arvores = arvores or [("", RAIZ)]
    for perfil in perfis:
        for n in cenarios:
            # Árvores no laço de DENTRO: baseline e candidata rodam uma logo após
            # a outra, sob a mesma carga de fundo.
            for nome_arvore, arvore in arvores:
                fixtures = FIXTURES_1CAM if n == 1 else FIXTURES_4CAM
                rotulo = f"{perfil}-{n}cam" + (f"-{nome_arvore}" if nome_arvore else "") + (f"-{args.rotulo}" if args.rotulo else "")
                rotulo += "-soak" if args.soak else ""
                print(f"[bench] rodada {rotulo}: aquecimento {args.aquecimento:.0f} s + medição {args.soak or args.duracao:.0f} s")
                r = rodar(rotulo=rotulo, perfil=perfil, fixtures=fixtures, caminhos=caminhos, duracao=args.duracao,
                          aquecimento=args.aquecimento, env_extra=env_extra, afinidade_batata=afinidade_batata,
                          soak_s=args.soak, arvore=arvore, prioridade_alta=not args.sem_prioridade)
                resultados.append(r)
                print(tabela([r]).splitlines()[-1], flush=True)

    DIR_RESULTADOS.mkdir(parents=True, exist_ok=True)
    nome = f"{carimbo}" + (f"-{args.rotulo}" if args.rotulo else "") + ("-soak" if args.soak else "")
    destino = DIR_RESULTADOS / f"{nome}.json"
    destino.write_text(json.dumps({"carimbo": carimbo, "maquina": maquina, "afinidade_batata": afinidade_batata,
                                   "config_base": CONFIG_BASE, "resultados": resultados}, ensure_ascii=False, indent=1),
                       encoding="utf-8")
    print()
    print(tabela(resultados))
    print(f"\n[bench] resultado: {destino.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
