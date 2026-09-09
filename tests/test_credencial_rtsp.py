"""Credencial de câmera RTSP nunca sai do processo.

Contexto: as 4 câmeras Dahua da planta ficam numa rede industrial de terceiro,
e a URL RTSP carrega `usuario:senha@host` embutido. `Camera.source` guarda essa
URL inteira, no banco. Este repositório é **público**.

Uma senha de rede industrial vazada não é um bug de conveniência: é acesso ao
parque de câmeras de outra empresa. Então a regra é dura — a senha não aparece
em arquivo versionado, log, payload de socket, resposta de API, mensagem de
erro ou tela. Nem mascarada parcialmente.

Os quatro caminhos de saída rastreados no código:

1. `Camera.to_dict()` -> resposta de `GET /api/cameras`
2. `CameraWorker.status()` -> payload de socket `monitor_status`
3. logs de `VideoStream` (5 pontos)
4. `_last_error` / `VideoStreamError` -> mensagem de erro que volta no status

E um risco funcional que anda junto: o frontend preenche o formulário de edição
com `camera.source`. Se a API devolve a URL redigida e o formulário salva de
volta, a credencial real é sobrescrita por `***`. O penúltimo teste trava isso.

Nenhum valor de senha aqui é real: são montados em runtime, como a chave falsa
do Gemini em `tests/test_llm.py`.
"""

from __future__ import annotations

import json
import re
import subprocess
import threading
from pathlib import Path

import pytest
from app import create_app
from app.config import TestConfig
from app.extensions import db
from app.llm import redigir_segredos
from app.models import Camera
from app.services.camera_worker import CameraWorker
from app.services.feature_manager import FeatureManager
from app.vision.video_stream import VideoStream

RAIZ = Path(__file__).resolve().parent.parent

# Montados em runtime de proposito: escritos literais, virariam credencial
# embutida em arquivo versionado — exatamente o que a varredura acusa.
USUARIO = "admin"
SENHA = "Nao" + "EhReal" + "123!"
HOST = "10.14.22.97"
CAMINHO = "/cam/realmonitor?channel=1&subtype=0"
# Concatenado, nao interpolado: uma f-string com usuario e senha entre chaves
# deixaria no texto-fonte exatamente o formato que a varredura procura, e
# este arquivo acusaria a si mesmo.
URL_COM_SENHA = "rtsp://" + USUARIO + ":" + SENHA + "@" + HOST + ":554" + CAMINHO
# Para os testes que exercitam o caminho de FALHA: a porta 1 em localhost
# recusa na hora, enquanto 10.14.x fica ~60 s por tentativa no OpenCV.
URL_QUE_FALHA_RAPIDO = "rtsp://" + USUARIO + ":" + SENHA + "@127.0.0.1:1/falha"


def sem_senha(texto: str) -> bool:
    return SENHA not in texto


class DetectorDuble:
    # `status()` chama `_safe_model_diagnostics`, que le model_path dos dois
    # detectores. Sem o atributo o teste falharia por AttributeError e
    # pareceria vazamento.
    model_path = "duble.pt"
    confidence = 0.35
    max_detections = 100

    def detect(self, frame):  # noqa: ARG002
        return []

    def diagnostics(self):
        return {"model_path": "duble.pt", "classes": {}, "error": None}

    def supported_ppe_classes(self):
        return {"helmet"}


class PoseDuble:
    def estimate(self, frame):  # noqa: ARG002
        return None

    def estimate_for_people(self, frame, people, *, max_people=4):  # noqa: ARG002
        return []


# ------------------------------------------------------ funcao de redacao ---
def test_redigir_remove_a_credencial_da_url():
    redigida = redigir_segredos(URL_COM_SENHA)

    assert sem_senha(redigida), f"senha sobreviveu: {redigida}"
    assert HOST in redigida, "o host tem que sobrar: e ele que identifica a camera no log"
    assert "channel=1" in redigida, "o caminho tem que sobrar para diagnostico"


def test_redacao_nao_deixa_pedaco_da_senha():
    """Mascaramento parcial nao conta. Nada da senha pode sobrar."""
    redigida = redigir_segredos(URL_COM_SENHA)

    for tamanho in range(4, len(SENHA) + 1):
        for inicio in range(len(SENHA) - tamanho + 1):
            pedaco = SENHA[inicio : inicio + tamanho]
            assert pedaco not in redigida, f"pedaco '{pedaco}' sobrou em {redigida}"


@pytest.mark.parametrize(
    "url",
    [
        "rtsp://10.14.22.96:554/video",
        "rtsp://10.14.22.97:554/cam/realmonitor?channel=1",
        "0",
        "tests/fixtures/bench.mp4",
    ],
)
def test_redacao_nao_estraga_fonte_sem_credencial(url):
    """Fonte sem senha tem que passar intacta — senao o log fica inutil."""
    assert redigir_segredos(url) == url


# ------------------------------------------------ saida 1: API / to_dict ---
def test_to_dict_da_camera_nao_carrega_a_senha():
    camera = Camera(name="Fresa 1", source_type="RTSP", source=URL_COM_SENHA)

    payload = json.dumps(camera.to_dict())

    assert sem_senha(payload), f"senha na resposta da API: {payload}"
    assert HOST in payload, "o host deve continuar visivel para identificar a camera"


def test_api_de_cameras_nao_devolve_a_senha():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        db.session.add(Camera(name="Fresa 1", source_type="RTSP", source=URL_COM_SENHA))
        db.session.commit()
        resposta = app.test_client().get("/api/cameras")
        corpo = resposta.get_data(as_text=True)
        db.session.remove()
        db.drop_all()

    assert resposta.status_code == 200
    assert sem_senha(corpo), "GET /api/cameras devolveu a senha"


# ----------------------------------------- saida 2: payload de socket ------
def test_status_do_worker_nao_carrega_a_senha():
    """`status()` vai para o socket em `monitor_status` a cada transicao."""
    app = create_app(TestConfig)
    with app.app_context():
        worker = CameraWorker(
            app,
            socketio=None,
            feature_manager=FeatureManager.from_config(app.config),
            camera_id=1,
            source=URL_COM_SENHA,
            fps=12,
            detector=DetectorDuble(),
            person_detector=DetectorDuble(),
            pose_estimator=PoseDuble(),
            inference_lock=threading.Lock(),
        )
        payload = json.dumps(worker.status())

    assert sem_senha(payload), f"senha no payload de monitor_status: {payload}"


# ------------------------------------------------------ saida 3: logs -----
def test_logs_do_video_stream_nao_carregam_a_senha(caplog):
    fluxo = VideoStream(source=URL_QUE_FALHA_RAPIDO, width=640, height=480)
    with caplog.at_level("DEBUG"):
        # Nao abre nada: exercita o caminho de log de FALHA, que e o que roda
        # quando a rede da planta nao responde.
        fluxo.read()

    texto = "\n".join(
        registro.getMessage() + json.dumps(registro.__dict__, default=str)
        for registro in caplog.records
    )
    assert sem_senha(texto), "senha apareceu em log do VideoStream"


# -------------------------------------------- saida 4: mensagem de erro ---
def test_mensagem_de_erro_de_conexao_nao_carrega_a_senha():
    fluxo = VideoStream(source=URL_QUE_FALHA_RAPIDO, width=640, height=480)
    fluxo.read()  # falha: o host nao responde nesta maquina

    erro = fluxo.status().last_error or ""
    assert erro, "esperava alguma mensagem de erro para inspecionar"
    assert sem_senha(erro), f"senha na mensagem de erro: {erro}"


# ----------------------------------- risco funcional: salvar o redigido ---
def test_salvar_source_redigido_nao_apaga_a_credencial_real():
    """O formulario do frontend e preenchido com o que a API devolveu.

    Se a API devolve `***` e o formulario salva de volta, a credencial real
    morre e a camera para de conectar — com a causa invisivel, porque a tela
    mostra exatamente o que foi salvo.
    """
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        camera = Camera(name="Fresa 1", source_type="RTSP", source=URL_COM_SENHA)
        db.session.add(camera)
        db.session.commit()
        camera_id = camera.id

        devolvido = camera.to_dict()["source"]
        resposta = app.test_client().patch(f"/api/cameras/{camera_id}", json={"source": devolvido})

        db.session.expire_all()
        guardado = db.session.get(Camera, camera_id).source
        db.session.remove()
        db.drop_all()

    assert resposta.status_code in (200, 409), f"PATCH devolveu {resposta.status_code}"
    assert guardado == URL_COM_SENHA, (
        "salvar de volta o valor redigido apagou a credencial real; "
        f"ficou: {guardado}"
    )


# ------------------------------------------------------------ varredura ---
def test_nenhum_arquivo_versionado_carrega_credencial_em_url():
    """Nada rastreado pelo git pode ter `usuario:senha@` numa URL.

    Mesmo padrao do teste de chave do Gemini. Pega o erro mais facil: colar a
    URL completa da camera num script, num doc de demo ou no .env.example.
    """
    padrao = re.compile(r"rtsp://[^/\s:@]+:[^/\s@]+@")
    # Placeholder de documentacao nao e credencial. Sem esta lista, o
    # proprio regex em app/llm e a docstring deste arquivo — que existem
    # justamente para EXPLICAR o formato — fariam a varredura falhar.
    # `username:password@` e o placeholder LITERAL da doc oficial da Dahua
    # (Network Camera Web 3.0 Operation Manual V2.1.5, p. 79), citada em
    # `montar_url_rtsp` para justificar o formato e a semantica do subtype.
    exemplos = ("usuario:senha@", "user:pass@", "USUARIO:SENHA@", "***@", "username:password@")
    rastreados = subprocess.run(
        ["git", "ls-files"], cwd=RAIZ, capture_output=True, text=True, check=True
    ).stdout.split()

    culpados = []
    for relativo in rastreados:
        caminho = RAIZ / relativo
        if not caminho.is_file() or caminho.stat().st_size > 2_000_000:
            continue
        try:
            texto = caminho.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for achado in padrao.findall(texto) or padrao.finditer(texto):
            trecho = achado if isinstance(achado, str) else achado.group(0)
            if not any(exemplo in trecho for exemplo in exemplos):
                culpados.append(f"{relativo}: {trecho}")
                break

    assert culpados == [], f"credencial embutida em URL, em arquivo versionado: {culpados}"


def test_env_example_nao_entrega_credencial_de_camera():
    valores = {}
    for linha in (RAIZ / ".env.example").read_text(encoding="utf-8").splitlines():
        limpa = linha.strip()
        if not limpa or limpa.startswith("#"):
            continue
        casa = re.match(r"^([A-Z0-9_]+)=(.*)$", limpa)
        if casa:
            valores[casa.group(1)] = casa.group(2).split("#")[0].strip()

    for chave in ("RTSP_USUARIO", "RTSP_SENHA"):
        assert chave in valores, f"o exemplo precisa DOCUMENTAR {chave}, mesmo vazia"
        assert valores[chave] == "", f"{chave} no .env.example tem que ser placeholder VAZIO"
