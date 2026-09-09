"""O fio entre o `CameraWorker` e a camada LLM.

`ServicoDeRiscoLLM` está construído, testado e provado assíncrono
(`tests/test_llm_async.py`, `docs/SPRINT3.md`: FPS 19,53 -> 19,45, `submeter()`
a 11 microssegundos, 78 de 79 eventos descartados). **Ninguém o instancia no
boot.** Este arquivo especifica o fio, e `camera_worker.py` está a 34% de
cobertura, então vem antes da mudança (mesma regra de
`test_camera_worker_cache.py`).

As quatro invariantes que importam, e por quê:

1. **O disparo é no alerta CRIADO**, não em todo frame nem em alerta que só
   continua ativo. Um alerta ativo persiste por segundos; chamar a cada frame
   estouraria a cota do free tier e inundaria a tela.
2. **Nunca na thread do loop.** O pipeline está em 19,56 fps com uma câmera
   (docs/BENCH.md). Uma chamada de rede de segundos dentro do loop congelaria
   o vídeo na frente de quem está assistindo.
3. **A resposta é SEGUNDA OPINIÃO, em campo separado.** O LLM não cria, não
   resolve e não suprime alerta. Informa o operador; não decide. Um modelo de
   linguagem que apaga alerta de EPI é um risco de segurança do trabalho, não
   uma feature.
4. **Um único `cv2.imencode` por frame.** A BENCH.md registra que há exatamente
   um encode por frame e que o resultado é reaproveitado por todos os
   consumidores. O fio do LLM reaproveita esse mesmo JPEG — se codificasse de
   novo, acrescentaria 2,5 ms por frame com alerta ao caminho do frame.

Nada aqui abre câmera, carrega peso ou toca em rede: detectores, pose, fonte e
serviço de LLM são dublês injetados.
"""

from __future__ import annotations

import threading

import numpy as np
import pytest
from app import create_app
from app.config import TestConfig
from app.extensions import db
from app.llm import AnaliseRisco
from app.services.camera_worker import CameraWorker
from app.services.feature_manager import FeatureManager
from app.vision.schemas import BoundingBox, Detection, PoseResult

FRAME = np.zeros((540, 960, 3), dtype=np.uint8)


class SocketDuble:
    def __init__(self) -> None:
        self.eventos: list[tuple[str, object]] = []

    def emit(self, evento, payload=None, *args, **kwargs):  # noqa: ARG002
        self.eventos.append((evento, payload))

    def start_background_task(self, target, *args, **kwargs):  # noqa: ARG002
        return None

    def nomes(self) -> list[str]:
        return [nome for nome, _ in self.eventos]


def pessoa(track_id: int = 1) -> Detection:
    return Detection(
        label="person",
        confidence=0.9,
        box=BoundingBox(x1=10, y1=10, x2=110, y2=310),
        category="person",
        track_id=track_id,
    )


class DetectorDuble:
    model_path = "duble.pt"
    confidence = 0.35
    max_detections = 100

    def __init__(self, deteccoes: list[Detection] | None = None) -> None:
        self._deteccoes = deteccoes or []

    def detect(self, frame):  # noqa: ARG002
        return list(self._deteccoes)

    def diagnostics(self):
        return {"model_path": "duble.pt", "classes": {}, "error": None}

    def supported_ppe_classes(self):
        return {"helmet", "vest", "gloves", "glasses", "mask", "safety_shoe"}


class PoseDuble:
    def estimate(self, frame):  # noqa: ARG002
        return PoseResult(landmarks=[])

    def estimate_for_people(self, frame, people, *, max_people=4):  # noqa: ARG002
        return []


class FonteQueEntrega:
    """Dublê de `VideoStream` que sempre entrega o mesmo frame."""

    def __init__(self) -> None:
        self.source = "duble://entrega"
        self.width, self.height = 960, 540
        self.leituras = 0

    def read(self):
        self.leituras += 1
        return True, FRAME.copy()

    def status(self):
        from app.vision.video_stream import LIVE, StreamStatus

        return StreamStatus(
            state=LIVE,
            consecutive_failures=0,
            reconnect_attempts=0,
            total_reconnects=0,
            last_error=None,
            seconds_until_retry=0.0,
        )

    def release(self) -> None: ...

    def latest_frame(self):
        return None


class ServicoLLMDuble:
    """Registra o que foi submetido, sem rede e sem thread.

    Espelha a assinatura real de `ServicoDeRiscoLLM.submeter`.
    """

    def __init__(self, *, habilitado: bool = True) -> None:
        self.habilitado = habilitado
        self.submissoes: list[tuple[int | None, bytes]] = []
        self.ao_concluir = None

    def submeter(self, *, camera_id, imagem_jpeg) -> bool:
        if not self.habilitado:
            return False
        self.submissoes.append((camera_id, imagem_jpeg))
        return True

    def estatisticas(self) -> dict[str, object]:
        return {"habilitado": self.habilitado, "aceitos": len(self.submissoes)}


class RodarAte:
    def __init__(self, continuar) -> None:
        self._continuar = continuar

    def is_set(self) -> bool:
        return bool(self._continuar())

    def set(self) -> None: ...

    def clear(self) -> None:
        self._continuar = lambda: False


def _montar(monkeypatch, *, servico_llm=None, deteccoes=None):
    class Cfg(TestConfig):
        # Alerta na PRIMEIRA detecção: o objeto do teste é o fio, não a
        # histerese (essa tem os testes dela em test_alert_state.py).
        ALERT_CREATE_AFTER_FRAMES = 1
        MULTI_PERSON_DETECTION = False
        SNAPSHOT_ENABLED = False
        CLEANUP_ON_MONITOR_START = False
        RTSP_FIXTURE_FALLBACK = ""

    app = create_app(Cfg)
    socket = SocketDuble()
    with app.app_context():
        db.create_all()
        worker = CameraWorker(
            app,
            socketio=socket,
            feature_manager=FeatureManager.from_config(app.config),
            camera_id=7,
            source="duble://entrega",
            fps=12,
            detector=DetectorDuble(deteccoes if deteccoes is not None else [pessoa()]),
            person_detector=DetectorDuble(),
            pose_estimator=PoseDuble(),
            inference_lock=threading.Lock(),
            servico_llm=servico_llm,
        )
        worker.video_stream = FonteQueEntrega()
        worker.socket_duble = socket
        monkeypatch.setattr("app.services.camera_worker.time.sleep", lambda _s: None)
        yield worker
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def servico():
    return ServicoLLMDuble()


@pytest.fixture()
def worker(monkeypatch, servico):
    yield from _montar(monkeypatch, servico_llm=servico)


@pytest.fixture()
def worker_sem_llm(monkeypatch):
    yield from _montar(monkeypatch, servico_llm=None)


def rodar(worker, frames: int) -> None:
    alvo = worker.video_stream.leituras + frames
    worker._running = RodarAte(lambda: worker.video_stream.leituras < alvo)
    worker._loop()


# ------------------------------------------- 1. dispara no alerta CRIADO ---
def test_alerta_criado_submete_uma_analise(worker, servico):
    rodar(worker, 1)

    assert len(servico.submissoes) == 1, (
        f"um alerta criado deveria submeter uma analise; submissoes={len(servico.submissoes)}"
    )
    camera_id, jpeg = servico.submissoes[0]
    assert camera_id == 7, "o camera_id tem que ir junto: o servico faz debounce POR camera"
    assert jpeg.startswith(b"\xff\xd8"), "tem que ser JPEG de verdade (SOI), nao o frame cru"


def test_frame_sem_alerta_novo_nao_submete(worker_sem_llm):
    """Sem detecção não há violação, logo não há alerta criado, logo nada vai."""
    servico = ServicoLLMDuble()
    worker_sem_llm.servico_llm = servico
    worker_sem_llm.detector = DetectorDuble([])

    rodar(worker_sem_llm, 3)

    assert servico.submissoes == [], "frame limpo nao pode gastar chamada"


def test_alerta_que_apenas_continua_ativo_nao_resubmete(worker, servico):
    """A cota do free tier é finita e um alerta ativo persiste por segundos.

    O disparo é na CRIAÇÃO. O debounce do serviço é a segunda linha de defesa,
    não a primeira.
    """
    rodar(worker, 12)

    assert len(servico.submissoes) == 1, (
        f"12 frames com o MESMO alerta ativo submeteram {len(servico.submissoes)} vezes"
    )


# ----------------------------------- 2. nunca na thread do loop ------------
def test_o_loop_nao_espera_a_analise(worker, servico):
    """`submeter` volta na hora; quem demora é o executor do serviço.

    Medido no bench: 11 microssegundos no caminho do frame (docs/SPRINT3.md).
    Aqui o que se trava é o desenho — o loop segue publicando frame no mesmo
    ciclo em que submeteu.
    """
    rodar(worker, 3)

    assert worker._frame_counter == 3, "submeter nao pode custar um frame"
    assert servico.submissoes, "e submeteu de fato"


# --------------------------- 3. segunda opiniao em campo separado ----------
def _analise() -> AnaliseRisco:
    return AnaliseRisco(
        nivel_risco="alto",
        confianca=0.8,
        epis_ausentes=["helmet"],
        justificativa="Trabalhador sem capacete em area de circulacao de veiculo.",
        acao_recomendada="Interromper e fornecer capacete.",
    )


def test_a_resposta_entra_em_campo_separado(worker):
    rodar(worker, 1)

    worker._consumir_analise_llm(_analise())

    analise = worker.latest_analysis() or {}
    assert "segunda_opiniao" in analise, (
        f"a resposta do LLM precisa de campo proprio; latest_analysis tem {sorted(analise)}"
    )
    segunda = analise["segunda_opiniao"]
    assert segunda["nivel_risco"] == "alto"
    assert segunda["epis_ausentes"] == ["helmet"]


def test_o_llm_nao_cria_nem_resolve_nem_suprime_alerta(worker):
    """A invariante mais importante do arquivo.

    Um modelo de linguagem que apaga alerta de EPI e um risco de seguranca do
    trabalho. Ele informa o operador; nao decide.
    """
    rodar(worker, 1)
    antes = worker.alert_state_service.active_alerts()
    assert antes, "o cenario precisa ter alerta ativo para o teste valer"

    # Uma analise que discorda de tudo: nenhum EPI ausente, risco baixo.
    discordante = AnaliseRisco(
        nivel_risco="baixo",
        confianca=0.95,
        epis_ausentes=[],
        justificativa="Trabalhador esta de capacete; a caixa do detector ficou deslocada.",
        acao_recomendada="Nenhuma.",
    )
    worker._consumir_analise_llm(discordante)

    depois = worker.alert_state_service.active_alerts()
    assert [a["id"] for a in depois] == [a["id"] for a in antes], (
        "o LLM mexeu no conjunto de alertas ativos"
    )
    assert all(a["status"] == "active" for a in depois), "o LLM resolveu alerta"
    assert not any(a.get("false_positive") for a in depois), "o LLM marcou falso positivo"


def test_a_segunda_opiniao_e_anunciada_no_socket(worker):
    rodar(worker, 1)
    worker.socket_duble.eventos.clear()

    worker._consumir_analise_llm(_analise())

    assert "llm_segunda_opiniao" in worker.socket_duble.nomes(), (
        f"eventos emitidos: {sorted(set(worker.socket_duble.nomes()))}"
    )


def test_status_expoe_o_estado_da_camada_llm(worker):
    rodar(worker, 1)

    llm = worker.status().get("llm")
    assert llm is not None, "o dashboard precisa saber se a camada esta ligada"
    assert llm["habilitado"] is True


# --------------------------------- 4. um encode por frame -----------------
def test_um_unico_imencode_por_frame(worker, monkeypatch):
    """Caracterização, e trava contra regressão.

    A BENCH.md registra UM encode por frame (2,5 ms), reaproveitado por todos
    os consumidores. O fio do LLM reaproveita o mesmo JPEG; se codificasse de
    novo, acrescentaria 2,5 ms ao caminho do frame justamente nos frames com
    alerta — os que mais importam.
    """
    import cv2

    original = cv2.imencode
    chamadas = {"n": 0}

    def contando(*args, **kwargs):
        chamadas["n"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr("app.services.camera_worker.cv2.imencode", contando)

    rodar(worker, 4)

    assert chamadas["n"] == 4, f"esperava 1 encode por frame em 4 frames, houve {chamadas['n']}"


# ------------------------------- degradacao ------------------------------
def test_sem_servico_o_loop_roda_igual(worker_sem_llm):
    """`LLM_ENABLED=false` é o default. O demo não pode depender disto."""
    rodar(worker_sem_llm, 4)

    assert worker_sem_llm._frame_counter == 4
    assert (worker_sem_llm.latest_analysis() or {}).get("segunda_opiniao") is None


def test_servico_que_levanta_nao_derruba_o_loop(worker):
    """Nem bug no serviço, nem provedor fora do ar, podem parar a câmera."""

    class ServicoQueExplode(ServicoLLMDuble):
        def submeter(self, *, camera_id, imagem_jpeg):
            raise RuntimeError("provedor fora do ar")

    worker.servico_llm = ServicoQueExplode()

    rodar(worker, 3)

    assert worker._frame_counter == 3, "o loop tem que continuar publicando frame"
