"""Baixa e extrai o dataset Construction-PPE (Ultralytics) usado na Sprint 4.

Mesmo contrato de ``fetch_fixtures.py``: nada disso e versionado, o SHA-256 da
ORIGEM e conferido, e o download e idempotente.

| Campo | Valor |
|---|---|
| Origem | https://docs.ultralytics.com/datasets/detect/construction-ppe/ |
| Arquivo | construction-ppe.zip (178,4 MB) |
| Licenca | AGPL-3.0 (arquivo LICENSE dentro do zip) |
| Divisao | train 1132 · val 143 · test 141 imagens |
| Classes | helmet, gloves, vest, boots, goggles, none (= torso sem colete), Person, no_helmet, no_goggle, no_gloves, no_boots |

    python scripts/baixar_dataset.py
    python scripts/baixar_dataset.py --check
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import urllib.request
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
URL = "https://github.com/ultralytics/assets/releases/download/v0.0.0/construction-ppe.zip"
SHA256 = "bef8dcb599aa4e9d9f5e602cb6fa7143d3c84d7f6a0ff40463d7f2a4c2632ccc"
ZIP = RAIZ / "tests" / "fixtures" / "_source" / "construction-ppe.zip"
DESTINO = RAIZ / "datasets" / "construction-ppe"
ESPERADO = {"train": 1132, "val": 143, "test": 141}

YAML = """# Gerado por scripts/baixar_dataset.py
path: {raiz}
train: images/train
val: images/val
test: images/test
names:
  0: helmet
  1: gloves
  2: vest
  3: boots
  4: goggles
  5: none
  6: Person
  7: no_helmet
  8: no_goggle
  9: no_gloves
  10: no_boots
"""


def _sha(caminho: Path) -> str:
    h = hashlib.sha256()
    with caminho.open("rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def conferir() -> list[str]:
    problemas = []
    for split, n in ESPERADO.items():
        achado = len(list((DESTINO / "images" / split).glob("*")))
        if achado != n:
            problemas.append(f"{split}: {achado} imagens, esperado {n}")
    return problemas


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    if args.check:
        problemas = conferir()
        print("OK: construction-ppe completo" if not problemas else "\n".join(problemas))
        return 1 if problemas else 0

    if not ZIP.exists() or _sha(ZIP) != SHA256:
        ZIP.parent.mkdir(parents=True, exist_ok=True)
        print(f"baixando {URL}")
        urllib.request.urlretrieve(URL, ZIP)
    if _sha(ZIP) != SHA256:
        print(f"SHA-256 nao confere para {ZIP}", file=sys.stderr)
        return 1
    with zipfile.ZipFile(ZIP) as z:
        z.extractall(DESTINO)
    (RAIZ / "datasets" / "cppe.yaml").write_text(YAML.format(raiz=DESTINO.as_posix()), encoding="utf-8")
    problemas = conferir()
    print("OK" if not problemas else "\n".join(problemas))
    return 1 if problemas else 0


if __name__ == "__main__":
    raise SystemExit(main())
