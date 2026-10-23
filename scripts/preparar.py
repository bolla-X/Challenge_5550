"""Deixa um clone limpo pronto para `python run.py --demo` (uma vez, com internet).

    python scripts/preparar.py              # pesos + gravações + exports aprovados
    python scripts/preparar.py --sem-exports

1. Baixa os três pesos para `models/` e confere o SHA-256 de cada um (os
   arquivos `.pt` são pickle: só carrega o que bate com o hash conhecido):
   - EPI: Hexmon/vyra-yolo-ppe-detection (`best.pt`, YOLOv8m, CC-BY-4.0, exige
     atribuição ao autor);
   - pessoa e pose: Ultralytics (`yolov8n.pt`, `yolo11n-pose.pt`, AGPL-3.0).
2. Baixa as gravações de demonstração (`scripts/fetch_fixtures.py`).
3. Exporta e aprova os runtimes rápidos (`scripts/concordancia.py` para EPI,
   pessoa e esqueleto). Sem isso o `auto` cai no PyTorch, que funciona mas é
   bem mais lento numa máquina sem GPU dedicada.
4. Aquece o cache do OpenVINO (`runtime/ov_cache/`, ou `OV_CACHE_DIR`): compila
   os três modelos no dispositivo escolhido, nas formas das câmeras da demo, e
   o OpenVINO guarda o compilado. A subida seguinte do `run.py --demo` lê do
   cache em vez de compilar (números no DEMO.md). Rode de novo depois de trocar
   de máquina, de driver da GPU ou de versão do OpenVINO. Só ele:
   `python scripts/preparar.py --so-cache`.

Já baixado e com o hash certo = pulado. Nada aqui lê ou escreve o `.env`.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import secrets
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
MODELOS = RAIZ / "models"

PESOS = [
    ("vyra_ppe.pt", "https://huggingface.co/Hexmon/vyra-yolo-ppe-detection/resolve/main/best.pt",
     "2b33d4d016f9751c5a25f4a72ce050e0a7e4e140b11c1669978d7154003a4f61"),
    ("yolov8n.pt", "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.pt",
     "f59b3d833e2ff32e194b5bb8e08d211dc7c5bdf144b90d2c8412c47ccfc83b36"),
    ("yolo11n-pose.pt", "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n-pose.pt",
     "869e83fcdffdc7371fa4e34cd8e51c838cc729571d1635e5141e3075e9319dc0"),
]


def sha256(caminho: Path) -> str:
    h = hashlib.sha256()
    with caminho.open("rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def baixar_peso(nome: str, url: str, esperado: str) -> None:
    destino = MODELOS / nome
    if destino.exists() and sha256(destino) == esperado:
        print(f"[preparar] {nome}: já está aqui", flush=True)
        return
    parcial = destino.with_suffix(destino.suffix + ".parcial")
    print(f"[preparar] {nome}: baixando de {url}", flush=True)
    with urllib.request.urlopen(url, timeout=60) as resposta, parcial.open("wb") as saida:  # noqa: S310 (URL fixa acima)
        while bloco := resposta.read(1 << 20):
            saida.write(bloco)
    obtido = sha256(parcial)
    if obtido != esperado:
        parcial.unlink()
        raise SystemExit(f"[preparar] {nome}: SHA-256 não confere ({obtido}); arquivo descartado, nada foi carregado")
    parcial.replace(destino)


def aquecer_cache_openvino() -> None:
    """Sobe o app num banco temporário (sem câmeras) e aquece os modelos nas formas da demo."""
    banco = Path(tempfile.mkdtemp(prefix="visionepi-preparar-")) / "preparar.db"
    os.environ.update({"VISIONEPI_DOTENV": "0", "DATABASE_URL": f"sqlite:///{banco.as_posix()}", "AUTO_CREATE_TABLES": "true",
                       "LLM_ENABLED": "false", "SECRET_KEY": secrets.token_hex(32)})
    sys.path.insert(0, str(RAIZ))
    from app import create_app
    from app.vision.runtime_do_modelo import aquecer_modelos
    from app.vision.yolo_ppe_detector import pasta_do_cache_openvino

    inicio = time.monotonic()
    monitor = create_app().extensions["monitor_service"]
    monitor.validar_runtimes()
    # 960x540 (Canteiro, Pátio), 960x720 (Portal gravado) e 640x480 (webcam do Portal).
    tempos = aquecer_modelos([monitor.detector, monitor.person_detector, monitor.pose_detector],
                             formas=((540, 960), (720, 960), (480, 640)))
    print(f"[preparar] cache do OpenVINO em {pasta_do_cache_openvino()} aquecido em {time.monotonic() - inicio:.0f} s "
          f"({len(tempos)} modelos)", flush=True)


# Os candidatos que o app de fato usa (`RUNTIME_ORDEM=openvino-gpu,onnx,pytorch`
# em app/config.py), um por runtime: OpenVINO dinâmico na iGPU (FP32, FP16 se só
# ele passar), na CPU, e ONNX dinâmico para máquina sem iGPU Intel. A lista
# PADRÃO do concordancia.py é a varredura de pesquisa (estáticos, 416/320,
# INT8) e NÃO os inclui: o teste de clone limpo (ADENDO 3) terminou sem nenhum
# runtime aprovado para o EPI, que então rodaria em PyTorch.
CANDIDATOS_DO_APP = "openvino-dyn@gpu-fp32:640,openvino-dyn@gpu-fp16:640,openvino-dyn@cpu-fp32:640,onnx-dyn:640"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sem-exports", action="store_true", help="pula a exportação/aprovação dos runtimes rápidos")
    ap.add_argument("--so-cache", action="store_true", help="só aquece o cache do OpenVINO (pesos e exports já prontos)")
    args = ap.parse_args()
    if args.so_cache:
        aquecer_cache_openvino()
        return 0
    MODELOS.mkdir(exist_ok=True)
    for nome, url, esperado in PESOS:
        baixar_peso(nome, url, esperado)
    subprocess.run([sys.executable, "scripts/fetch_fixtures.py"], cwd=RAIZ, check=True)
    if not args.sem_exports:
        # Sem auto-instalação do ultralytics: ela chama o `pip` de OUTRO Python
        # (visto no clone limpo: tentou instalar no Python global). O que falta
        # vai no requirements.txt.
        ambiente = os.environ.copy() | {"YOLO_AUTOINSTALL": "false"}
        for modelo in ("epi", "pessoa", "esqueleto"):
            print(f"[preparar] exportando e aprovando o runtime de {modelo} (alguns minutos)", flush=True)
            subprocess.run([sys.executable, "scripts/concordancia.py", "--modelo", modelo, "--candidatos", CANDIDATOS_DO_APP],
                           cwd=RAIZ, check=True, env=ambiente)
    # Em processo separado: o app lê a configuração do ambiente no import.
    subprocess.run([sys.executable, "scripts/preparar.py", "--so-cache"], cwd=RAIZ, check=True)
    # O Python que rodou este script (o do venv), não um `python` solto que seria o global.
    python = Path(sys.executable)
    python = python.relative_to(RAIZ) if python.is_relative_to(RAIZ) else python
    print(f"[preparar] pronto. Agora: {python} run.py --demo", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
