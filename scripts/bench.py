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

# Configuração de referência, igual para toda árvore comparada. `YOLO_IMGSZ`
# é 640 porque é a referência do guarda de qualidade (416 e 512 reprovados,
# docs/NEXT2026/CHANGELOG.md §4.3). `DETECTION_EVERY_N_FRAMES` fica de FORA:
# cada árvore usa o próprio default, e a baseline recebe o 3 do `.env.example`
# dela por `--arvores base=...|DETECTION_EVERY_N_FRAMES=3`.
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
    "YOLO_IMGSZ": "640",
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

# A câmera 1 é sempre a `multidao`: pedestres, ninguém de capacete, violação
# desde o quadro 0 (gabarito em bench/primeira_violacao.json). É nela que a
# latência de alerta é medida. A `bench` (operários com capacete e colete) não
# tem violação clara de capacete e não serve de âncora.
FIXTURES_1CAM = ["multidao"]
FIXTURES_4CAM = ["multidao", "bench", "queda", "bench"]
GABARITO = RAIZ / "bench" / "primeira_violacao.json"
SOCKETIO_CLIENTE = RAIZ / "frontend" / "node_modules" / "socket.io-client" / "dist" / "socket.io.min.js"

# Ouvinte de alertas independente do frontend (vale para qualquer árvore):
# cliente Socket.IO oficial, injetado na página, mesma origem e mesmo cookie.
# `recebido_ms` é o relógio de parede do navegador, a mesma máquina do servidor.
JS_OUVIR_ALERTAS = r"""
() => new Promise((ok) => {
  window.__alertas = [];
  const s = io({transports: ['polling'], withCredentials: true});
  s.on('alert_created', (a) => window.__alertas.push({recebido_ms: Date.now(), camera_id: a.camera_id, rule: a.rule, id: a.id}));
  s.on('connect', () => ok(true));
  setTimeout(() => ok(false), 15000);
})
"""

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
  // Mesmo leitor do player (frontend/src/socket/multipart.ts): buffer com
  // deslocamento (sem cópia quadrática) e "último quadro vence" no decode.
  const st = {frames: 0, bytes: 0, idades: [], decode: [], chegadas: [], dup: 0, descartados: 0, erro: null};
  window.__sonda = st;
  const ctrl = new AbortController();
  let ultimoId = null;
  let buf = new Uint8Array(1 << 20), ini = 0, fim = 0;
  const empurrar = (p) => {
    if (p.length > buf.length - fim) {
      const usado = fim - ini;
      if (usado + p.length <= buf.length) buf.copyWithin(0, ini, fim);
      else { const n = new Uint8Array(Math.max(buf.length * 2, (usado + p.length) * 2)); n.set(buf.subarray(ini, fim)); buf = n; }
      ini = 0; fim = usado;
    }
    buf.set(p, fim); fim += p.length;
  };
  const sep = () => {
    for (let i = ini; i + 3 < fim; i++) if (buf[i] === 13 && buf[i+1] === 10 && buf[i+2] === 13 && buf[i+3] === 10) return i;
    return -1;
  };
  const td = new TextDecoder();
  const canvas = new OffscreenCanvas(32, 32); const ctx = canvas.getContext('2d');
  let decodificando = false, proximo = null;
  const decodificar = (item) => {
    if (decodificando) { if (proximo) st.descartados++; proximo = item; return; }
    decodificando = true;
    const t0 = performance.now();
    createImageBitmap(new Blob([item.jpeg], {type: 'image/jpeg'})).then((bmp) => {
      ctx.drawImage(bmp, 0, 0, 32, 32); bmp.close();
      st.decode.push(performance.now() - t0);
      st.chegadas.push(performance.now());
      if (item.ts) st.idades.push(Date.now() - item.ts);
      st.frames++;
    }).catch(() => {}).finally(() => { decodificando = false; const s2 = proximo; proximo = null; if (s2) decodificar(s2); });
  };
  try {
    const resp = await fetch(url, {signal: ctrl.signal, credentials: 'same-origin'});
    const reader = resp.body.getReader();
    const limite = performance.now() + durMs;
    while (performance.now() < limite) {
      const {value, done} = await reader.read();
      if (done) break;
      st.bytes += value.length;
      empurrar(value);
      let maisNovo = null;
      for (;;) {
        const h = sep(); if (h < 0) break;
        const cab = td.decode(buf.subarray(ini, h));
        const m = /Content-Length:\s*(\d+)/i.exec(cab);
        if (!m) { ini = h + 4; continue; }
        const corpoIni = h + 4, corpoFim = corpoIni + parseInt(m[1], 10);
        if (fim < corpoFim) break;
        const jpeg = buf.slice(corpoIni, corpoFim);
        ini = corpoFim;
        if (/application\/json/i.test(cab)) continue;
        const ts = /X-Capture-Ts:\s*([\d.]+)/i.exec(cab);
        const id = /X-Frame-Id:\s*(-?\d+)/i.exec(cab);
        if (id && id[1] === ultimoId) st.dup++;
        ultimoId = id ? id[1] : null;
        if (maisNovo) st.descartados++;
        maisNovo = {jpeg, ts: ts ? parseFloat(ts[1]) : null};
      }
      if (maisNovo) decodificar(maisNovo);
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


def nucleos_eficientes(n: int = 2) -> list[int] | None:
    """Os `n` últimos núcleos da classe de eficiência mais baixa (E-cores), pela topologia.

    `GetSystemCpuSetInformation` (Windows 10+): "CPU Sets with higher numerical
    values of [EfficiencyClass] have home processors that are faster but less
    power-efficient" (https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-system_cpu_set_information).
    Determinístico, ao contrário de cronometrar sob carga de fundo — que numa
    rodada escolheu um P-core com HT e um E-core juntos. Um núcleo lógico por
    núcleo físico (sem irmão de HT). None fora do Windows ou sem a API.
    """
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        import struct
        from ctypes import wintypes

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        tamanho = wintypes.ULONG(0)
        k32.GetSystemCpuSetInformation(None, 0, ctypes.byref(tamanho), None, 0)
        buf = ctypes.create_string_buffer(tamanho.value)
        if not k32.GetSystemCpuSetInformation(buf, tamanho.value, ctypes.byref(tamanho), None, 0):
            return None
        conjuntos, desloc = [], 0
        while desloc < tamanho.value:
            tam, tipo = struct.unpack_from("<II", buf, desloc)
            if tipo == 0:  # CpuSetInformation
                _id, _grupo, logico, nucleo, _llc, _numa, eficiencia, _flags = struct.unpack_from("<IHBBBBBB", buf, desloc + 8)
                conjuntos.append((eficiencia, nucleo, logico))
            desloc += tam
    except (OSError, AttributeError, struct.error):
        return None
    if not conjuntos:
        return None
    menor = min(e for e, _, _ in conjuntos)
    por_nucleo: dict[int, int] = {}
    for e, nucleo, logico in conjuntos:
        if e == menor:
            por_nucleo.setdefault(nucleo, logico)
    logicos = sorted(por_nucleo.values())
    return logicos[-n:] if len(logicos) >= n else None


def nucleos_mais_lentos(n: int = 2) -> list[int]:
    """Os `n` núcleos lógicos mais lentos, por um laço de Python preso em cada um.

    Só como reserva de `nucleos_eficientes` (sem a API do Windows): sob carga de
    fundo a cronometragem muda de rodada para rodada.

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


def latencias_de_alerta(sessao, base: str, ids: list[int], fixtures: list[str], alertas: list[dict[str, Any]],
                        *, decorrido_s: float) -> dict[str, Any]:
    """Do primeiro quadro com a violação (gabarito) até o `alert_created` chegar ao navegador.

    Âncora: instante em que o SERVIDOR leu o quadro do gabarito
    (`/api/diagnostics/pipeline?quadro=K`). Fim: `Date.now()` no navegador ao
    receber o evento. Mesma máquina, mesmo relógio de parede. Sem alerta da
    regra na rodada inteira → `latencia_ms` None e `sem_alerta_em_s` diz por
    quanto tempo se esperou (é um limite inferior, não um número).
    """
    gabarito = json.loads(GABARITO.read_text(encoding="utf-8")) if GABARITO.exists() else {}
    saida: dict[str, Any] = {}
    for cid, fixture in zip(ids, fixtures, strict=True):
        for regra, info in gabarito.get(fixture, {}).items():
            quadro = int(info["quadro"])
            d = sessao.get(f"{base}/api/diagnostics/pipeline?janela_s=5&quadro={quadro}", timeout=10).json()
            ts = d["cameras"].get(str(cid), {}).get("ts_quadro_ms")
            primeiro = next((a for a in alertas if a.get("camera_id") == cid and a.get("rule") == regra), None)
            saida[f"{cid}:{regra}"] = {
                "camera_id": cid, "fixture": fixture, "regra": regra, "quadro": quadro, "ts_quadro_ms": ts,
                "recebido_ms": primeiro["recebido_ms"] if primeiro else None,
                "latencia_ms": round(primeiro["recebido_ms"] - ts, 1) if primeiro and ts else None,
                "sem_alerta_em_s": None if primeiro else round(decorrido_s, 1),
            }
    return saida


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

        raiz_proc = psutil.Process(srv.proc.pid)
        n_logicos = psutil.cpu_count(logical=True)
        with sync_playwright() as pw:
            navegador = pw.chromium.launch(headless=True)
            contexto = navegador.new_context(viewport={"width": 1366, "height": 768})
            contexto.add_cookies([{"name": c.name, "value": c.value, "url": srv.base} for c in sessao.cookies])
            contexto.add_init_script(JS_INIT)
            pagina = contexto.new_page()
            console_erros: list[str] = []
            pagina.on("console", lambda m: console_erros.append(m.text) if m.type == "error" else None)
            pagina.goto(srv.base + "/", wait_until="load")
            # O ouvinte de alertas conecta ANTES das câmeras ligarem: o primeiro
            # alerta pode nascer durante o aquecimento e não pode ser perdido.
            pagina.add_script_tag(path=str(SOCKETIO_CLIENTE))
            resultado["ouvinte_de_alertas_conectado"] = bool(pagina.evaluate(JS_OUVIR_ALERTAS))

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
            processos = [raiz_proc, *raiz_proc.children(recursive=True)]
            # Prioridade alta no servidor E no navegador (os dois lados de toda
            # comparação recebem a mesma): a máquina de medição divide a CPU com
            # processos que não são deste projeto (`carga_de_fundo_pct`). Com só o
            # servidor em prioridade alta, o Chromium passava fome e a idade do
            # quadro media o buffer TCP.
            if prioridade_alta:
                for p_ in processos:
                    try:
                        p_.nice(psutil.HIGH_PRIORITY_CLASS if sys.platform == "win32" else -5)
                    except (psutil.Error, OSError):
                        resultado["prioridade_alta"] = False
                for p_ in psutil.Process().children(recursive=True):
                    if p_.pid in {q.pid for q in processos}:
                        continue
                    try:
                        p_.nice(psutil.HIGH_PRIORITY_CLASS if sys.platform == "win32" else -5)
                    except (psutil.Error, OSError):
                        pass
            for p_ in processos:
                p_.cpu_percent(None)
            psutil.cpu_percent(None)

            def amostrar(t: float) -> dict[str, float]:
                cpu_srv = sum(p_.cpu_percent(None) for p_ in processos if p_.is_running())
                rss = sum(p_.memory_info().rss for p_ in processos if p_.is_running())
                total = psutil.cpu_percent(None) * n_logicos  # em "% de um núcleo", como o do servidor
                return {"t": round(t, 1), "cpu_pct": round(cpu_srv, 1), "rss_mb": round(rss / 2**20, 1),
                        "carga_de_fundo_pct": round(max(0.0, total - cpu_srv), 1)}

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
            # O player da UI (LiveVideo) publica o que EXIBIU em window.__visionepiVideo.
            # Na baseline a UI usa <img> e não há registro: fica None.
            ui_video = pagina.evaluate(
                "() => { const r = (window.__visionepiVideo || {}); const k = Object.keys(r)[0]; if (!k) return null;"
                " const x = r[k]; return {exibidos: x.exibidos, idades: x.idades.slice(), descartados: x.descartadosNoCliente}; }"
            )
            alertas_recebidos = pagina.evaluate("() => window.__alertas || []")
            diag = sessao.get(f"{srv.base}/api/diagnostics/pipeline?janela_s={min(120, int(duracao))}", timeout=10).json()
            resultado["latencia_alerta"] = latencias_de_alerta(sessao, srv.base, ids, fixtures, alertas_recebidos,
                                                               decorrido_s=time.perf_counter() - t_start)
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
            "descartados_no_cliente": estado_sonda.get("descartados"),
            "ui_player": None if not ui_video else {
                "exibidos_total": ui_video["exibidos"],
                "idade_quadro_ms": {"p50": pct(ui_video["idades"], 50), "p95": pct(ui_video["idades"], 95)},
                "descartados_no_cliente": ui_video["descartados"],
            },
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
            idade_analise = (st.get("etapas") or {}).get("idade_analise") or {}
            resultado["cameras"][str(cid)] = {
                "fixture": fixtures[i],
                # Métricas principais do portão (ver docs/NEXT2026/MISSAO.md).
                "fps_analise": taxas.get("analises_publicadas"),
                "idade_analise_ms": {"p50": idade_analise.get("p50"), "p95": idade_analise.get("p95"), "n": idade_analise.get("n")},
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
                 "anotacao", "encode", "emissao", "loop_total", "idade_publicacao", "idade_analise"]


def latencia_da_camera_1(r: dict[str, Any]) -> dict[str, Any] | None:
    """A latência de alerta da câmera 1 (a `multidao`), se o gabarito cobre a fixture dela."""
    cameras = list(r.get("cameras", {}))
    if not cameras:
        return None
    primeira = int(cameras[0])
    return next((v for v in (r.get("latencia_alerta") or {}).values() if v.get("camera_id") == primeira), None)


def tabela(resultados: list[dict[str, Any]]) -> str:
    linhas = []
    # As 4 primeiras colunas de número são as do portão (FPS de análise por
    # câmera, idade da análise p50/p95, latência de alerta da câmera 1).
    cab = f"{'rodada':28s} {'fps_anal':>8s} {'idAn_p50':>8s} {'idAn_p95':>8s} {'alerta_ms':>9s} " \
          f"{'fps_lido':>8s} {'fps_pub':>8s} {'tempo_real':>10s} {'idade_p95':>9s} " \
          f"{'exib_fps':>8s} {'epi_p95':>8s} {'cpu%':>6s} {'rss_mb':>7s} {'fundo%':>7s}"
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
        lat = latencia_da_camera_1(r)
        if lat is None:
            alerta = f"{'-':>9s}"
        elif lat["latencia_ms"] is None:
            alerta = f"{'>' + str(int(lat['sem_alerta_em_s'])) + 's':>9s}"
        else:
            alerta = f"{lat['latencia_ms']:9.0f}"
        linhas.append(
            f"{r['rotulo']:28s} {media('fps_analise') or 0:8.2f} {etapa('idade_analise', 'p50') or 0:8.0f} "
            f"{etapa('idade_analise') or 0:8.0f} {alerta} "
            f"{media('fps_lido') or 0:8.2f} {media('fps_publicado') or 0:8.2f} "
            f"{media('fracao_do_tempo_real') or 0:10.2f} {nav.get('idade_quadro_ms', {}).get('p95') or 0:9.0f} "
            f"{nav.get('fps_exibido_sonda') or 0:8.2f} {etapa('inferencia_epi') or 0:8.1f} "
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
    ap.add_argument("--arvores", default="",
                    help="rotulo=caminho[|K=V;K=V],... : compara árvores (ou configs) INTERCALADAS")
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
    afinidade_batata = (nucleos_eficientes(2) or nucleos_mais_lentos(2)) if "batata" in perfis else []
    print(f"[bench] {maquina['cpu']} | {maquina['nucleos_logicos']} lógicos | {maquina['ram_gb']} GB | GPU: {maquina['gpu_cuda']}")
    if afinidade_batata:
        print(f"[bench] perfil batata: núcleos lógicos {afinidade_batata} (2 E-cores pela topologia, ou os 2 mais lentos medidos)")

    resultados = []
    carimbo = datetime.now().strftime("%Y%m%d-%H%M%S")
    arvores = []
    for item in [i for i in args.arvores.split(",") if "=" in i]:
        nome_arvore, resto = item.split("=", 1)
        caminho, _, extras = resto.partition("|")
        env_arvore = dict(par.split("=", 1) for par in extras.split(";") if "=" in par)
        arvores.append((nome_arvore, Path(caminho).resolve(), env_arvore))
    arvores = arvores or [("", RAIZ, {})]
    for perfil in perfis:
        for n in cenarios:
            # Árvores no laço de DENTRO: baseline e candidata rodam uma logo após
            # a outra, sob a mesma carga de fundo.
            for nome_arvore, arvore, env_arvore in arvores:
                fixtures = FIXTURES_1CAM if n == 1 else FIXTURES_4CAM
                rotulo = f"{perfil}-{n}cam" + (f"-{nome_arvore}" if nome_arvore else "") + (f"-{args.rotulo}" if args.rotulo else "")
                rotulo += "-soak" if args.soak else ""
                print(f"[bench] rodada {rotulo}: aquecimento {args.aquecimento:.0f} s + medição {args.soak or args.duracao:.0f} s")
                r = rodar(rotulo=rotulo, perfil=perfil, fixtures=fixtures, caminhos=caminhos, duracao=args.duracao,
                          aquecimento=args.aquecimento, env_extra=env_extra | env_arvore, afinidade_batata=afinidade_batata,
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
