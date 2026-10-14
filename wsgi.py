import os

# Afinidade de CPU ANTES de qualquer import pesado (ver app/utils/limites_de_cpu.py).
# Medido: aplicada só dentro do create_app, ela se perdia assim que a primeira
# câmera rodava um `cv2.resize` (o OpenCV desta máquina usa o Concurrency
# Runtime do Windows, inicializado nos imports com a máscara antiga).
if os.getenv("VISIONEPI_CPUS", "").strip():
    import psutil

    psutil.Process().cpu_affinity([int(c) for c in os.environ["VISIONEPI_CPUS"].split(",") if c.strip().isdigit()])

import sys

if sys.argv[-2:] == ["demo", "reset"]:
    # `flask --app wsgi demo reset` precisa caber em 10 s (missão, Fase 4). O app
    # completo leva 9–20 s só para importar e montar nesta máquina (OpenVINO,
    # OpenCV, modelos); o reset só conversa com o servidor da demo por HTTP.
    # Então este comando ganha um Flask mínimo, sem importar o pacote `app`
    # (cujo __init__ carrega tudo): o módulo da demo é lido pelo caminho.
    import importlib.util
    from pathlib import Path

    import click
    from flask import Flask

    _spec = importlib.util.spec_from_file_location("demo_ambiente", Path(__file__).parent / "app" / "demo_ambiente.py")
    _demo = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_demo)
    app = Flask(__name__)

    @app.cli.group("demo")
    def _grupo_demo() -> None:
        """Modo demonstração (python run.py --demo)."""

    @_grupo_demo.command("reset")
    def _reset() -> None:
        """Volta a demo ao começo (< 10 s): histórico limpo, câmeras religadas."""
        r = _demo.resetar_pelo_terminal(int(os.getenv("PORT", "5000")))
        click.echo(f"[demo] reset em {r['segundos']} s ({r.get('via', 'servidor')}).")
else:
    from app import create_app

    app = create_app()
