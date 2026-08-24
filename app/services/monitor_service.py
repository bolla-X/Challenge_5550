from __future__ import annotations

import threading
from typing import Any

from flask import Flask
from flask_socketio import SocketIO

from app.config import Config
from app.models import Camera
from app.services.camera_worker import CameraWorker
from app.services.feature_manager import FeatureManager
from app.vision.pose_estimator import MediaPipePoseEstimator
from app.vision.yolo_ppe_detector import YoloPPEDetector


class CameraNotFoundError(LookupError):
    pass


class MonitorService:
    """Gerenciador de câmeras — Fase A, Passo 4.

    Carrega os modelos YOLO/pose UMA ÚNICA VEZ (compartilhados entre todos
    os workers, ver docstring de CameraWorker) e mantém um CameraWorker por
    câmera cadastrada no banco (app.models.Camera, enabled=True).

    Compatibilidade com rotas antigas: todo método de instância aceita
    `camera_id: int | None = None`. Quando None, opera sobre a "câmera
    padrão" (a de menor id, tipicamente a semeada no Passo 1) — é assim que
    /start, /stop, /status etc continuam funcionando sem mudar nem uma
    linha em app/api/*.py. camera_id explícito só passa a ser usado pelas
    rotas a partir do Passo 5.

    Limitação conhecida deste passo (documentada, não escondida): Alert e
    EventLog ainda não têm coluna camera_id — alertas/eventos de câmeras
    diferentes caem juntos no mesmo histórico por enquanto. Corrigido no
    Passo 5 (camera_id em toda API/evento).
    """

    def __init__(self, app: Flask, socketio: SocketIO, feature_manager: FeatureManager) -> None:
        self.app = app
        self.socketio = socketio
        self.feature_manager = feature_manager  # segue controlando a câmera padrão via /features, como sempre

        # ---- modelos compartilhados: criados 1x, injetados em cada worker ----
        self.detector = YoloPPEDetector(
            model_path=app.config.get("PPE_MODEL_PATH", "yolov8n.pt"),
            confidence=app.config.get("YOLO_CONFIDENCE", 0.35),
            device=app.config.get("YOLO_DEVICE"),
            classes=CameraWorker._parse_yolo_classes(app.config.get("YOLO_CLASSES", "")),
            max_detections=app.config.get("YOLO_MAX_DETECTIONS", 100),
            require_person=False,
        )
        # Segundo YOLO (COCO, classe 0) usado APENAS quando
        # MULTI_PERSON_DETECTION=true — isto e, quando PPE_MODEL_PATH aponta pra
        # um modelo de EPI sem classe "person" propria (ex: epi_pretrained.pt).
        # Com o Vyra, que ja detecta "Person", fica ocioso.
        # Mesmo par de modelos, compartilhado por todas as cameras.
        self.person_detector = YoloPPEDetector(
            model_path=app.config.get("PERSON_MODEL_PATH", "yolov8n.pt"),
            confidence=app.config.get("YOLO_CONFIDENCE", 0.35),
            device=app.config.get("YOLO_DEVICE"),
            classes=[0],
            max_detections=app.config.get("YOLO_MAX_DETECTIONS", 100),
        )
        self.pose_estimator = MediaPipePoseEstimator(
            min_detection_confidence=app.config.get("POSE_MIN_DETECTION_CONFIDENCE", 0.5),
            min_tracking_confidence=app.config.get("POSE_MIN_TRACKING_CONFIDENCE", 0.5),
        )
        # Serializa chamadas de inferência entre workers (ver CameraWorker).
        self._inference_lock = threading.Lock()

        self._workers: dict[int, CameraWorker] = {}
        self._workers_lock = threading.RLock()
        self._default_camera_id: int | None = None

    # ---- ciclo de vida dos workers -----------------------------------------
    def load_cameras_from_db(self) -> None:
        """Sincroniza self._workers com a tabela `cameras`. Chamado no boot
        (app/__init__.py, dentro do app_context) e de novo sempre que o CRUD
        de câmeras cria/edita/remove uma linha — assim uma câmera nova já
        ganha worker, e uma câmera EDITADA (fonte/fps/resolução) recebe um
        worker novo com a config atualizada, sem precisar reiniciar o
        servidor. Se a câmera estava rodando antes da edição, o worker novo
        já sobe rodando também — senão a edição pareceria salvar mas não
        mudar nada de verdade até o próximo restart."""
        with self._workers_lock:
            db_cameras = Camera.query.filter_by(enabled=True).order_by(Camera.id.asc()).all()
            db_camera_ids = {c.id for c in db_cameras}
            default_id = db_cameras[0].id if db_cameras else None

            # remove workers de câmeras que sumiram ou foram desabilitadas
            for camera_id in list(self._workers.keys()):
                if camera_id not in db_camera_ids:
                    self._stop_and_discard_worker(camera_id)

            for camera in db_cameras:
                existing = self._workers.get(camera.id)
                if existing is None:
                    # câmera nova — cria worker do zero, ainda parado
                    self._workers[camera.id] = self._build_worker(camera, is_default=camera.id == default_id)
                    continue
                if self._worker_config_changed(existing, camera):
                    was_running = existing.status().get("running", False)
                    self._stop_and_discard_worker(camera.id)
                    new_worker = self._build_worker(camera, is_default=camera.id == default_id)
                    self._workers[camera.id] = new_worker
                    if was_running:
                        new_worker.start()

            self._default_camera_id = default_id

    @staticmethod
    def _worker_config_changed(worker: CameraWorker, camera: Camera) -> bool:
        current_source = str(worker.video_stream.source)
        new_source = str(Config.parse_video_source(camera.source))
        return (
            current_source != new_source
            or worker.target_fps != camera.fps
            or worker.video_stream.width != camera.width
            or worker.video_stream.height != camera.height
        )

    def _build_worker(self, camera: Camera, *, is_default: bool) -> CameraWorker:
        # A câmera padrão (menor id) usa o FeatureManager GLOBAL compartilhado
        # — é o que faz a rota /features (PATCH global) continuar controlando
        # exatamente essa câmera, sem quebrar o frontend atual. Câmeras
        # adicionais recebem seu próprio FeatureManager, seedado do banco
        # (Camera.features_json) — ainda não há rota pra editar isso em
        # runtime além do PUT /api/cameras (que grava no banco, mas não
        # empurra pro worker já rodando — limitação conhecida, resolvida
        # quando /features ganhar suporte a camera_id no Passo 5).
        feature_manager = self.feature_manager if is_default else FeatureManager.from_camera_features(camera.features_json or {})
        return CameraWorker(
            self.app,
            self.socketio,
            feature_manager,
            camera_id=camera.id,
            source=Config.parse_video_source(camera.source),
            fps=camera.fps,
            width=camera.width,
            height=camera.height,
            detector=self.detector,
            person_detector=self.person_detector,
            pose_estimator=self.pose_estimator,
            inference_lock=self._inference_lock,
        )

    def _stop_and_discard_worker(self, camera_id: int) -> None:
        worker = self._workers.pop(camera_id, None)
        if worker is not None:
            try:
                worker.stop()
            except Exception:  # noqa: BLE001
                pass

    def _get_worker(self, camera_id: int | None) -> CameraWorker:
        target_id = camera_id if camera_id is not None else self._default_camera_id
        with self._workers_lock:
            worker = self._workers.get(target_id) if target_id is not None else None
        if worker is None:
            raise CameraNotFoundError(f"câmera {target_id!r} não encontrada ou sem worker ativo")
        return worker

    def start_all(self) -> dict[int, dict[str, Any]]:
        with self._workers_lock:
            workers = dict(self._workers)
        return {camera_id: worker.start() for camera_id, worker in workers.items()}

    def stop_all(self) -> dict[int, dict[str, Any]]:
        with self._workers_lock:
            workers = dict(self._workers)
        return {camera_id: worker.stop() for camera_id, worker in workers.items()}

    def status_all(self) -> dict[int, dict[str, Any]]:
        with self._workers_lock:
            workers = dict(self._workers)
        return {camera_id: worker.status() for camera_id, worker in workers.items()}

    # ---- delegação por câmera (camera_id=None => câmera padrão) -----------
    def start(self, camera_id: int | None = None) -> dict[str, Any]:
        return self._get_worker(camera_id).start()

    def stop(self, camera_id: int | None = None) -> dict[str, Any]:
        return self._get_worker(camera_id).stop()

    def status(self, camera_id: int | None = None) -> dict[str, Any]:
        return self._get_worker(camera_id).status()

    def preflight(self, camera_id: int | None = None) -> dict[str, Any]:
        return self._get_worker(camera_id).preflight()

    def latest_jpeg(self, camera_id: int | None = None) -> bytes | None:
        return self._get_worker(camera_id).latest_jpeg()

    def latest_analysis(self, camera_id: int | None = None) -> dict[str, Any] | None:
        return self._get_worker(camera_id).latest_analysis()

    def settings(self, camera_id: int | None = None) -> dict[str, Any]:
        return self._get_worker(camera_id).settings()

    def update_settings(self, updates: dict[str, Any], camera_id: int | None = None) -> dict[str, Any]:
        return self._get_worker(camera_id).update_settings(updates)

    def get_overlay(self, camera_id: int | None = None) -> dict[str, bool]:
        return self._get_worker(camera_id).get_overlay()

    def update_overlay(self, updates: dict[str, Any], camera_id: int | None = None) -> dict[str, bool]:
        return self._get_worker(camera_id).update_overlay(updates)

    def risk_area_state(self, camera_id: int | None = None) -> dict[str, Any]:
        return self._get_worker(camera_id).risk_area_state()

    def update_risk_area(self, payload: dict[str, Any], camera_id: int | None = None) -> dict[str, Any]:
        return self._get_worker(camera_id).update_risk_area(payload)

    # ---- atributos que as rotas acessam direto (sempre a câmera padrão) ---
    @property
    def snapshot_service(self):
        return self._get_worker(None).snapshot_service

    @property
    def alert_state_service(self):
        return self._get_worker(None).alert_state_service

    @property
    def video_stream(self):
        return self._get_worker(None).video_stream
