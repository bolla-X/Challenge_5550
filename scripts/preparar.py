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

Já baixado e com o hash certo = pulado. Nada aqui lê ou escreve o `.env`.
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sem-exports", action="store_true", help="pula a exportação/aprovação dos runtimes rápidos")
    args = ap.parse_args()
    MODELOS.mkdir(exist_ok=True)
    for nome, url, esperado in PESOS:
        baixar_peso(nome, url, esperado)
    subprocess.run([sys.executable, "scripts/fetch_fixtures.py"], cwd=RAIZ, check=True)
    if not args.sem_exports:
        for modelo in ("epi", "pessoa", "esqueleto"):
            print(f"[preparar] exportando e aprovando o runtime de {modelo} (alguns minutos)", flush=True)
            subprocess.run([sys.executable, "scripts/concordancia.py", "--modelo", modelo], cwd=RAIZ, check=True)
    print("[preparar] pronto. Agora: python run.py --demo", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
