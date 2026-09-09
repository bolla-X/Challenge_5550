from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class RiskAreaConfig:
    enabled: bool
    polygon: list[tuple[float, float]]


# Caminho RTSP das Dahua, com `{canal}` e `{subtype}` como parâmetros — e NÃO
# com `subtype=0` fixo, que era o formato das URLs recebidas da planta. Fixar o
# subtype na string obriga a editar config pra alternar entre stream principal
# e substream, que é justamente a decisão de operação mais relevante aqui.
CAMINHO_RTSP_PADRAO = "/cam/realmonitor?channel={canal}&subtype={subtype}"

# Caracteres que podem ficar CRUS na credencial da URL.
#
# RFC 3986 §3.2.1: `userinfo = *( unreserved / pct-encoded / sub-delims / ":" )`
# — https://datatracker.ietf.org/doc/html/rfc3986#section-3.2.1
#
# Então só precisam de escape os que quebram o parse: `@` (separa userinfo do
# host), `/?#` (encerram a autoridade), `%` (introduz pct-encoded) e `:` (separa
# usuário de senha na convenção `user:pass`). Sub-delims são legais ali e ficam
# intactos DE PROPÓSITO: codificá-los sem necessidade só funcionaria se o
# cliente RTSP percent-DECODIFICASSE de volta, e essa é uma dependência que não
# vale a pena assumir sem ter medido. `quote` já preserva alfanumérico e `-._~`.
SEGUROS_NO_USERINFO = "!$&'()*+,;="


def montar_url_rtsp(
    *,
    host: str,
    usuario: str,
    senha: str,
    porta: int = 554,
    canal: int = 1,
    subtype: int = 1,
    caminho: str = CAMINHO_RTSP_PADRAO,
) -> str:
    """URL RTSP no formato Dahua, com a credencial percent-encoded.

    Formato e semântica conforme a documentação oficial da Dahua (Network
    Camera Web 3.0 Operation Manual V2.1.5, p. 79):

        rtsp://username:password@ip:port/cam/realmonitor?channel=1&subtype=0

    e, literalmente: "Subtype: The bit stream type; 0 means main stream
    (Subtype=0) and 1 means sub stream (Subtype=1)". As URLs recebidas da
    planta usam `subtype=0`, ou seja, o stream PRINCIPAL.

    O default aqui é `subtype=1` (substream) por medição, não por gosto: nesta
    máquina CPU-only a resolução de inferência é a maior alavanca do pipeline
    (416→640 derruba o FPS em 42%, docs/BENCH.md). Substream entrega imagem
    menor já da câmera, então economiza banda e o custo do downscale. Quem
    precisar do detalhe do stream principal pede `subtype=0` explicitamente.

    O escape da credencial é obrigatório: a mesma doc mostra o `usuario:senha`
    entre `//` e `@`, e uma senha com `@` — plenamente legal — deslocaria o host
    se entrasse crua. O sintoma seria "a câmera não conecta", sem nada no log
    apontando a causa. Escapa-se o mínimo (ver `SEGUROS_NO_USERINFO`).
    """
    # Um `.env` mais antigo trazia `subtype=0` FIXO no caminho. `str.format`
    # sobre string sem placeholder devolve a string intacta, então `--subtype 1`
    # seria aceito e não faria nada — falha silenciosa, o pior tipo. Falha alto.
    faltando = [chave for chave in ("{canal}", "{subtype}") if chave not in caminho]
    if faltando:
        raise ValueError(
            f"RTSP_CAMINHO precisa dos parâmetros {' e '.join(faltando)}. "
            f"Está como {caminho!r}, que ignoraria --canal/--subtype em silêncio. "
            f"Use: {CAMINHO_RTSP_PADRAO}"
        )

    credencial = ""
    if usuario or senha:
        usuario_seguro = quote(usuario, safe=SEGUROS_NO_USERINFO)
        senha_segura = quote(senha, safe=SEGUROS_NO_USERINFO)
        credencial = f"{usuario_seguro}:{senha_segura}@"
    return f"rtsp://{credencial}{host}:{int(porta)}{caminho.format(canal=int(canal), subtype=int(subtype))}"


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
    # Valores que aparecem NO PROPRIO REPOSITORIO — qualquer um que leia o
    # projeto os conhece. Checar so o default do codigo nao bastava: o
    # .env.example (que o README manda copiar) entrega outro literal, e a
    # aplicacao subia com chave publica.
    SECRET_KEYS_PUBLICAS = frozenset({"dev-secret-change-me", "change-me", "changeme", "secret", ""})
    # Abaixo disto a chave e curta demais pra assinatura de sessao.
    SECRET_KEY_MIN_LENGTH = 32

    # Porta única, lida daqui por run.py, Dockerfile, docker-compose e pelo
    # proxy do Vite. Antes o run.py escutava 5003 enquanto Dockerfile/compose/
    # README falavam em 5000 — o container subia com a porta publicada errada
    # e ninguém alcançava a aplicação.
    # Autenticacao. Desligar so faz sentido em teste automatizado; num
    # ambiente com camera apontada pra pessoas, exigir login e o padrao.
    AUTH_REQUIRED = env_bool("AUTH_REQUIRED", True)
    # Sessao assinada com SECRET_KEY, em cookie HttpOnly (o JS da pagina
    # nao le, entao XSS nao rouba a sessao).
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    # LIGUE em producao (exige HTTPS). Fica desligado por padrao porque
    # cookie Secure nao viaja em http://localhost e quebraria o dev.
    SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", False)
    PERMANENT_SESSION_LIFETIME = timedelta(hours=env_int("SESSION_HOURS", 12))

    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = env_int("PORT", 5000)
    # Werkzeug em modo debug expõe console interativo = execução remota de
    # código. Nunca liga sozinho: só com FLASK_DEBUG explícito no ambiente.
    DEBUG = env_bool("FLASK_DEBUG", False)
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        "sqlite:///visionepi-dev.db",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    AUTO_CREATE_TABLES = env_bool("AUTO_CREATE_TABLES", True)

    VIDEO_SOURCE = os.getenv("VIDEO_SOURCE", "0")
    FRAME_WIDTH = env_int("FRAME_WIDTH", 960)
    FRAME_HEIGHT = env_int("FRAME_HEIGHT", 540)
    TARGET_FPS = env_int("TARGET_FPS", 12)
    JPEG_QUALITY = env_int("JPEG_QUALITY", 80)

    # --- cameras RTSP da planta ------------------------------------------
    # A CREDENCIAL VIVE SO NO .env. Ela nao aparece em `.env.example`, nao vai
    # pra argumento de linha de comando (`ps aux` e historico do shell) e sai
    # redigida de qualquer log/payload (ver app.llm.redigir_segredos).
    RTSP_USUARIO = os.getenv("RTSP_USUARIO", "")
    RTSP_SENHA = os.getenv("RTSP_SENHA", "")
    RTSP_PORTA = env_int("RTSP_PORTA", 554)
    RTSP_CAMINHO = os.getenv("RTSP_CAMINHO", CAMINHO_RTSP_PADRAO)
    # 1 = substream. Ver a justificativa medida em `montar_url_rtsp`.
    RTSP_SUBTYPE = env_int("RTSP_SUBTYPE", 1)
    # Fonte de reserva do MODO FIXTURE. Depois de RTSP_MAX_TENTATIVAS falhas de
    # reconexao, o worker assume este arquivo em loop e ANUNCIA que assumiu
    # (status()["video"]["modo"] == "fixture"). E o seguro do demo: sem rota
    # para a rede da planta, uma camera RTSP fica indisponivel para sempre e
    # nao ha imagem nenhuma na tela. Vazio desliga o fallback.
    RTSP_FIXTURE_FALLBACK = os.getenv("RTSP_FIXTURE_FALLBACK", "tests/fixtures/bench.mp4")
    # 2, e nao 5: medido contra um endereco da planta sem rota, cada tentativa
    # custa o teto de abertura de 5 s, entao 1->5,3 s, 2->10,9 s, 3->17,0 s,
    # 5->33,2 s ate o modo fixture assumir. 33 s de tela parada num projetor e
    # o pior cenario de apresentacao. Em rede instavel, suba de volta para 5.
    RTSP_MAX_TENTATIVAS = env_int("RTSP_MAX_TENTATIVAS", 2)

    # --- camada LLM (segunda opiniao multimodal) --------------------------
    # SEM CHAVE O SISTEMA FUNCIONA NORMALMENTE, sem a camada. E degradacao
    # explicita, nao erro. `false` por padrao de proposito: o demo nao pode
    # depender disto para subir, e ligar por acidente sem rede so gera log de
    # timeout. A chave vive so no .env e nunca e lida para variavel local aqui
    # — quem decide e ProvedorGemini.configurado.
    LLM_ENABLED = env_bool("LLM_ENABLED", False)
    # 30 s, e nao os 8 s originais, por DUAS razoes medidas:
    # 1. a API recusa deadline abaixo de 10 s ("Manually set deadline 8s is
    #    too short. Minimum allowed deadline is 10s.", HTTP 400).
    # 2. o gemini-3.6-flash respondeu em 22,9 s e 26,8 s nas cenas reais.
    #    Com 8 s, TODA chamada seria abortada e a camada nunca produziria
    #    nada — pior que estar desligada, porque gastaria cota para nada.
    # O timeout continua sendo teto, nao alvo: estourou, ignora o evento e
    # segue. Nada disto entra no caminho do frame.
    LLM_TIMEOUT_S = env_float("LLM_TIMEOUT_S", 30.0)
    # Janela minima entre duas analises da MESMA camera. A fixture de 7 s gera
    # 26 alertas mesmo apos o fix da Fase 1; sem debounce seria uma chamada por
    # alerta.
    LLM_DEBOUNCE_S = env_float("LLM_DEBOUNCE_S", 15.0)
    LLM_PROMPT_VERSION = os.getenv("LLM_PROMPT_VERSION", "v2")

    PPE_MODEL_PATH = os.getenv("PPE_MODEL_PATH", "models/vyra_ppe.pt")
    # Modelo dedicado a detectar "person" (classe 0 COCO). Só é necessário quando
    # PPE_MODEL_PATH aponta pra um modelo de EPI sem classe "person" própria
    # (ex: epi_pretrained.pt). O Vyra já traz "Person" (classe 11), então roda
    # desligado por padrão — ver MULTI_PERSON_DETECTION abaixo.
    PERSON_MODEL_PATH = os.getenv("PERSON_MODEL_PATH", "yolov8n.pt")
    YOLO_CONFIDENCE = env_float("YOLO_CONFIDENCE", 0.35)
    YOLO_DEVICE = os.getenv("YOLO_DEVICE", None)
    YOLO_CLASSES = os.getenv("YOLO_CLASSES", "")
    YOLO_MAX_DETECTIONS = env_int("YOLO_MAX_DETECTIONS", 100)
    # Lado maior da imagem que entra na rede. O ultralytics usa 640 quando não
    # se diz nada, e é o custo dominante do pipeline: medido nesta máquina
    # (CPU, sem CUDA), o YOLOv8m leva 327 ms/frame a 640 contra 135 ms a 320 —
    # 2,4x. Abaixar melhora FPS e piora objetos pequenos/distantes, então é
    # escolha de operação, não constante: fica no .env.
    YOLO_IMGSZ = env_int("YOLO_IMGSZ", 640)
    # Roda a detecção 1 frame a cada N; os intermediários reaproveitam as
    # últimas caixas. Serve para desacoplar a fluidez do vídeo da velocidade da
    # inferência — com N=1 o comportamento é exatamente o de antes.
    DETECTION_EVERY_N_FRAMES = env_int("DETECTION_EVERY_N_FRAMES", 1)
    # Segundos entre gravações de um alerta que continua ativo. Cada gravação
    # é um commit (9,2 ms aqui) feito DENTRO do loop de captura, e antes
    # acontecia por alerta a cada frame — o vídeo travava justamente quando
    # havia infração. Criar e resolver seguem imediatos. 0 volta ao antigo.
    ALERT_TOUCH_INTERVAL_SECONDS = env_float("ALERT_TOUCH_INTERVAL_SECONDS", 2.0)
    # Quantas vezes por segundo a telemetria (analysis/compliance) vai pro
    # navegador. O VÍDEO não passa por aqui — ele é MJPEG com as caixas já
    # desenhadas — então baixar isto não deixa a imagem menos fluida; evita
    # que ~26 KB por evento por câmera afoguem o browser a 24 FPS.
    TELEMETRY_HZ = env_float("TELEMETRY_HZ", 8.0)
    # Diagnostico: a cada N frames, loga quanto cada etapa do loop custou.
    # 0 = desligado (padrao). Use quando o video estiver travado pra ver ONDE
    # o tempo vai, em vez de adivinhar pelo FPS medio.
    PROFILE_FRAMES = env_int("PROFILE_FRAMES", 0)
    MULTI_PERSON_DETECTION = env_bool("MULTI_PERSON_DETECTION", False)

    # Uma pose POR PESSOA (recorte da caixa) em vez de uma pose global do
    # frame. E o que permite atribuir queda/postura a um individuo. Custa N
    # inferencias por frame, entao POSE_MAX_PEOPLE limita o pior caso.
    POSE_PER_PERSON = env_bool("POSE_PER_PERSON", True)
    POSE_MAX_PEOPLE = env_int("POSE_MAX_PEOPLE", 4)
    POSE_MIN_DETECTION_CONFIDENCE = env_float("POSE_MIN_DETECTION_CONFIDENCE", 0.5)
    POSE_MIN_TRACKING_CONFIDENCE = env_float("POSE_MIN_TRACKING_CONFIDENCE", 0.5)

    ALERT_COOLDOWN_SECONDS = env_int("ALERT_COOLDOWN_SECONDS", 0)
    ALERT_CREATE_AFTER_FRAMES = env_int("ALERT_CREATE_AFTER_FRAMES", 3)
    ALERT_RESOLVE_AFTER_FRAMES = env_int("ALERT_RESOLVE_AFTER_FRAMES", 5)
    SOCKETIO_CORS_ALLOWED_ORIGINS = os.getenv("SOCKETIO_CORS_ALLOWED_ORIGINS", "*")
    SOCKETIO_ASYNC_MODE = os.getenv("SOCKETIO_ASYNC_MODE", "threading")

    CLEANUP_ON_MONITOR_START = env_bool("CLEANUP_ON_MONITOR_START", True)
    CLEANUP_DIRECTORIES = os.getenv("CLEANUP_DIRECTORIES", "runtime/snapshots,runtime/frames,runtime/tmp")
    SNAPSHOT_DIR = os.getenv("SNAPSHOT_DIR", "runtime/snapshots")
    SNAPSHOT_ENABLED = env_bool("SNAPSHOT_ENABLED", True)
    SNAPSHOT_JPEG_QUALITY = env_int("SNAPSHOT_JPEG_QUALITY", 86)
    TIMELINE_LIMIT = env_int("TIMELINE_LIMIT", 80)
    RISK_AREA_NAME = os.getenv("RISK_AREA_NAME", "Área de risco")

    OVERLAY_SHOW_BOXES = env_bool("OVERLAY_SHOW_BOXES", True)
    OVERLAY_SHOW_LABELS = env_bool("OVERLAY_SHOW_LABELS", True)
    OVERLAY_SHOW_CONFIDENCE = env_bool("OVERLAY_SHOW_CONFIDENCE", True)
    OVERLAY_SHOW_POSE = env_bool("OVERLAY_SHOW_POSE", True)
    OVERLAY_SHOW_RISK_AREA = env_bool("OVERLAY_SHOW_RISK_AREA", True)

    DEFAULT_FEATURES = os.getenv(
        "DEFAULT_FEATURES",
        "ppe,helmet,vest,gloves,glasses,mask,safety_shoe,pose,falls,posture,risk_area",
    )
    RISK_AREA_POLYGON = os.getenv("RISK_AREA_POLYGON", "0.70,0.10;0.98,0.10;0.98,0.95;0.70,0.95")

    @staticmethod
    def parse_video_source(value: str | int) -> str | int:
        if isinstance(value, int):
            return value
        return int(value) if str(value).isdigit() else value

    @classmethod
    def get_video_source(cls) -> str | int:
        return cls.parse_video_source(cls.VIDEO_SOURCE)

    @classmethod
    def get_enabled_feature_keys(cls) -> set[str]:
        return {item.strip() for item in cls.DEFAULT_FEATURES.split(",") if item.strip()}

    @classmethod
    def get_yolo_classes(cls) -> list[int] | None:
        raw = cls.YOLO_CLASSES.strip()
        if not raw:
            return None
        classes: list[int] = []
        for item in raw.split(","):
            item = item.strip()
            if item:
                classes.append(int(item))
        return classes

    @classmethod
    def get_risk_area_config(cls) -> RiskAreaConfig:
        polygon: list[tuple[float, float]] = []
        for pair in cls.RISK_AREA_POLYGON.split(";"):
            x, y = pair.split(",")
            polygon.append((float(x), float(y)))
        return RiskAreaConfig(enabled=True, polygon=polygon)


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    AUTO_CREATE_TABLES = False
    # Cada teste foca no proprio assunto; exigir login em todos so adicionaria
    # ruido. Quem exercita a autenticacao de verdade e tests/test_auth.py, que
    # sobe com AUTH_REQUIRED=True e verifica rota por rota — inclusive uma
    # varredura que falha se aparecer rota nova desprotegida.
    AUTH_REQUIRED = False
    DEFAULT_FEATURES = "ppe,helmet,vest,gloves,glasses,mask,safety_shoe,pose,falls,posture,risk_area"
    # Explicito, e nao herdado: um .env com LLM_ENABLED=true na maquina de quem
    # roda a suite nao pode fazer os testes tentarem rede.
    LLM_ENABLED = False


class AuthTestConfig(TestConfig):
    """TestConfig com autenticacao LIGADA."""

    AUTH_REQUIRED = True
    SECRET_KEY = "chave-de-teste-nao-usada-em-lugar-nenhum"
