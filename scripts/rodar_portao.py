"""Roda repetições do `scripts/bench.py` em sequência, destacado da sessão.

    python scripts/rodar_portao.py --rotulo gate3 --reps 2,3 --perfis batata --cameras 4,1 \
        --arvores "base=...|K=V,pr1=...|K=V"

Existe porque sessões de agente/terminal que reiniciam matam o driver do
Playwright (processo filho) e deixam o bench bloqueado para sempre esperando
por ele — aconteceu em 13/10. Lançado com `Start-Process` (Windows) ou
`nohup`, este laço não depende de quem o chamou. Cada repetição escreve
`bench/results/<carimbo>-<rotulo>-r<N>.json` e um log em `bench/runtime/`;
`bench/runtime/<rotulo>.estado` diz em que ponto está.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


DOCKER_DESKTOP = Path(r"C:\Program Files\Docker\Docker\Docker Desktop.exe")


def liberar_docker() -> None:
    """Autorizado no ADENDO 1 (item 2): só WSL e Docker Desktop, nada mais."""
    subprocess.run(["wsl", "--shutdown"], capture_output=True, check=False)
    subprocess.run(["taskkill", "/IM", "Docker Desktop.exe", "/F"], capture_output=True, check=False)
    time.sleep(5)


def religar_docker() -> None:
    if DOCKER_DESKTOP.exists():
        subprocess.Popen([str(DOCKER_DESKTOP)], creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rotulo", required=True)
    ap.add_argument("--reps", default="1,2,3")
    ap.add_argument("--perfis", default="batata")
    ap.add_argument("--cameras", default="1,4")
    ap.add_argument("--arvores", required=True)
    ap.add_argument("--limite-por-rep-s", type=float, default=1800.0)
    ap.add_argument("--liberar-docker", action="store_true",
                    help="antes de cada repetição: wsl --shutdown e fecha o Docker Desktop; religa no fim (ADENDO 1, item 2)")
    args = ap.parse_args()

    estado = RAIZ / "bench" / "runtime" / f"{args.rotulo}.estado"
    estado.parent.mkdir(parents=True, exist_ok=True)
    for rep in [r.strip() for r in args.reps.split(",") if r.strip()]:
        rotulo = f"{args.rotulo}-r{rep}"
        # Ordem alternada entre repetições: a carga de fundo da máquina deriva
        # ao longo da rodada, e quem roda sempre por último paga a deriva.
        arvores = args.arvores.split(",")
        if int(rep) % 2 == 0:
            arvores = list(reversed(arvores))
        if args.liberar_docker:
            liberar_docker()
        log = RAIZ / "bench" / "runtime" / f"{rotulo}.bench.log"
        estado.write_text(f"rodando {rotulo} desde {time.strftime('%H:%M:%S')}\n", encoding="utf-8")
        with log.open("w", encoding="utf-8") as saida:
            proc = subprocess.Popen(
                [sys.executable, "-u", "scripts/bench.py", "--perfis", args.perfis, "--cameras", args.cameras,
                 "--arvores", ",".join(arvores), "--rotulo", rotulo],
                cwd=RAIZ, stdout=saida, stderr=subprocess.STDOUT,
            )
            try:
                codigo = proc.wait(timeout=args.limite_por_rep_s)
            except subprocess.TimeoutExpired:
                # Bench preso (driver do Playwright morto, servidor travado):
                # derruba a árvore inteira e segue para a próxima repetição.
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, check=False)
                codigo = "timeout"
        with estado.open("a", encoding="utf-8") as f:
            f.write(f"{rotulo}: {codigo} às {time.strftime('%H:%M:%S')}\n")
    if args.liberar_docker:
        religar_docker()
    with estado.open("a", encoding="utf-8") as f:
        f.write("FIM\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
