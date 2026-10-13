import os

# Afinidade de CPU ANTES de qualquer import pesado (ver app/utils/limites_de_cpu.py).
# Medido: aplicada só dentro do create_app, ela se perdia assim que a primeira
# câmera rodava um `cv2.resize` (o OpenCV desta máquina usa o Concurrency
# Runtime do Windows, inicializado nos imports com a máscara antiga).
if os.getenv("VISIONEPI_CPUS", "").strip():
    import psutil

    psutil.Process().cpu_affinity([int(c) for c in os.environ["VISIONEPI_CPUS"].split(",") if c.strip().isdigit()])

from app import create_app
from app.config import Config
from app.extensions import socketio

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
    args = parser.parse_args()

    if Config.AQUECER_MODELOS_NO_BOOT:
        app.extensions["monitor_service"].aquecer()
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
