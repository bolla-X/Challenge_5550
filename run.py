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
    socketio.run(
        app,
        host=Config.HOST,
        port=Config.PORT,
        debug=Config.DEBUG,
        allow_unsafe_werkzeug=True,
    )
