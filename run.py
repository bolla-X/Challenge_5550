import os

# Afinidade de CPU ANTES de qualquer import pesado (ver app/utils/limites_de_cpu.py).
# Medido: aplicada só dentro do create_app, ela se perdia assim que a primeira
# câmera rodava um `cv2.resize` (o OpenCV desta máquina usa o Concurrency
# Runtime do Windows, inicializado nos imports com a máscara antiga).
if os.getenv("VISIONEPI_CPUS", "").strip():
    import psutil

    psutil.Process().cpu_affinity([int(c) for c in os.environ["VISIONEPI_CPUS"].split(",") if c.strip().isdigit()])

import sys

# Modo demonstração: o ambiente (banco isolado etc.) precisa existir ANTES do
# create_app(), que roda abaixo no import. Ver app/demo.py.
DEMO = "--demo" in sys.argv
if DEMO:
    import importlib.util
    from pathlib import Path as _Path

    _spec = importlib.util.spec_from_file_location("demo_ambiente", _Path(__file__).parent / "app" / "demo_ambiente.py")
    _modulo = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_modulo)
    _modulo.preparar_ambiente()

from app import create_app  # noqa: E402
from app.config import Config  # noqa: E402
from app.extensions import socketio  # noqa: E402

app = create_app()

if __name__ == "__main__":
    # Servidor de DESENVOLVIMENTO. Em produção quem serve é o gunicorn sobre
    # wsgi:app (ver Dockerfile) — nunca este arquivo.
    #
    # allow_unsafe_werkzeug e debug são coisas SEPARADAS, e confundi-las quebra
    # um dos dois lados:
    #   - allow_unsafe_werkzeug=True é fixo aqui porque este arquivo só existe
    #     pra rodar o servidor de desenvolvimento; quem executa `python run.py`
    #     já escolheu isso. Condicioná-lo ao debug faria o comando documentado
    #     no README simplesmente não subir.
    #   - debug liga o console interativo do Werkzeug, que executa código
    #     arbitrário de quem alcançar a porta. Esse fica atrás de FLASK_DEBUG,
    #     desligado por padrão.
    # Modelos aquecidos ANTES de servir: sem isto a 1ª análise depois de ligar
    # a câmera levava ~30 s no perfil batata (ver aquecer_modelos).
    import argparse

    parser = argparse.ArgumentParser(description="VisionEPI (servidor de desenvolvimento)")
    parser.add_argument("--https", action="store_true",
                        help="HTTPS com certificado autoassinado na rede local (celular como câmera exige contexto seguro)")
    parser.add_argument("--demo", action="store_true",
                        help="modo demonstração: banco isolado, contas e câmeras de demo, offline (ver docs/NEXT2026/DEMO.md)")
    args = parser.parse_args()
    if args.demo:
        import logging
        import socket

        from app.demo import imprimir_acessos, semear

        # Porta ocupada: avisar ANTES do seed e do aquecimento (antes, o erro só vinha no socketio.run).
        with socket.socket() as teste:
            try:
                teste.bind((Config.HOST if Config.HOST not in ("0.0.0.0", "") else "127.0.0.1", Config.PORT))
            except OSError:
                raise SystemExit(f"[demo] A porta {Config.PORT} já está em uso por outro programa. Use outra: "
                                 '(PowerShell) $env:PORT="5050"; depois rode de novo  ·  (macOS/Linux) '
                                 "PORT=5050 .venv/bin/python run.py --demo") from None
        # Uma linha por requisição empurrava as senhas para fora do terminal.
        logging.getLogger("werkzeug").setLevel(logging.WARNING)
        info = semear(app)
        with app.app_context():
            app.extensions["monitor_service"].load_cameras_from_db()
        imprimir_acessos(info, Config.PORT)

    if Config.AQUECER_MODELOS_NO_BOOT:
        app.extensions["monitor_service"].aquecer()
    if args.demo:
        with app.app_context():
            app.extensions["monitor_service"].start_all()
        imprimir_acessos(info, Config.PORT, pronto=True)
    host, ssl_context = Config.HOST, None
    if args.https:
        from pathlib import Path

        from app.api.celular import _ip_da_lan
        from app.config import BASE_DIR
        from app.utils.https_local import garantir_certificado

        ip = _ip_da_lan()
        ssl_context = tuple(str(p) for p in garantir_certificado(Path(BASE_DIR) / "instance" / "certs", [ip] if ip else []))
        # O celular precisa alcançar esta máquina pela rede: escuta em todas as
        # interfaces (a autenticação continua valendo para tudo, menos /cam).
        if host in ("127.0.0.1", "localhost"):
            host = "0.0.0.0"
        print(f"[VisionEPI] HTTPS ligado. No celular: https://{ip or '<ip-desta-maquina>'}:{Config.PORT} "
              "(aceite o aviso de certificado autoassinado uma vez).", flush=True)
    socketio.run(
        app,
        host=host,
        port=Config.PORT,
        debug=Config.DEBUG,
        allow_unsafe_werkzeug=True,
        ssl_context=ssl_context,
    )
