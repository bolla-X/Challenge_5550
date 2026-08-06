from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any

import cv2
from flask import Flask
from sqlalchemy import text as sql_text
from flask_socketio import SocketIO

from app.config import BASE_DIR, Config
from app.extensions import db
from app.repositories.alert_repository import AlertRepository
from app.repositories.event_repository import EventRepository
from app.services.alert_state_service import AlertStateService
from app.services.compliance_service import ComplianceService
from app.services.feature_manager import FeatureManager
from app.services.risk_rules import RuleEngine
from app.services.risk_score_service import compute_risk_score
from app.services.storage_cleanup_service import StorageCleanupService
from app.services.snapshot_service import SnapshotService
from app.vision.annotator import FrameAnnotator
from app.vision.pose_estimator import MediaPipePoseEstimator
from app.vision.schemas import FrameAnalysis
from app.vision.video_stream import VideoStream
from app.vision.yolo_ppe_detector import YoloPPEDetector

logger = logging.getLogger(__name__)


class MonitorService:
    def __init__(self, app: Flask, socketio: SocketIO, feature_manager: FeatureManager) -> None:
        self.app = app
        self.socketio = socketio
        self.feature_manager = feature_manager
        self._running = threading.Event()
        self._thread_lock = threading.RLock()
        self._task = None
        self._latest_jpeg: bytes | None = None
        self._latest_analysis: dict[str, Any] | None = None
        self._last_error: str | None = None
        self._frame_counter = 0
        self._last_risk_score_emit_at = 0.0
        self.risk_score_interval_seconds = 30

        risk_polygon = self._parse_risk_polygon(app.config.get("RISK_AREA_POLYGON", Config.RISK_AREA_POLYGON))
        self.risk_area_name = str(app.config.get("RISK_AREA_NAME", "Área de risco"))
        self.video_stream = VideoStream(
            source=Config.parse_video_source(app.config.get("VIDEO_SOURCE", "0")),
            width=app.config.get("FRAME_WIDTH", 960),
            height=app.config.get("FRAME_HEIGHT", 540),
        )
        self.detector = YoloPPEDetector(
            model_path=app.config.get("PPE_MODEL_PATH", "yolov8n.pt"),
            confidence=app.config.get("YOLO_CONFIDENCE", 0.35),
            device=app.config.get("YOLO_DEVICE"),
            classes=self._parse_yolo_classes(app.config.get("YOLO_CLASSES", "")),
            max_detections=app.config.get("YOLO_MAX_DETECTIONS", 100),
            require_person=False,  # person vem do self.person_detector, abaixo
        )
        # Modelo de EPI dedicado (ex.: epi_pretrained.pt) não detecta "person".
        # Um segundo YOLO (COCO, classe 0) roda em paralelo pra suprir isso.
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
        self.rule_engine = RuleEngine(
            feature_manager=feature_manager,
            cooldown_seconds=app.config.get("ALERT_COOLDOWN_SECONDS", 0),
            risk_polygon=risk_polygon,
            supported_ppe_getter=self.detector.supported_ppe_classes,
        )
        self.alert_state_service = AlertStateService(
            AlertRepository(),
            socketio,
            create_after_frames=app.config.get("ALERT_CREATE_AFTER_FRAMES", 3),
            resolve_after_frames=app.config.get("ALERT_RESOLVE_AFTER_FRAMES", 5),
        )
        self.compliance_service = ComplianceService(feature_manager, self.rule_engine)
        cleanup_dirs = str(app.config.get("CLEANUP_DIRECTORIES", "runtime/snapshots,runtime/frames,runtime/tmp")).split(",")
        self.cleanup_service = StorageCleanupService(
            base_dir=Path(BASE_DIR),
            directories=cleanup_dirs,
            enabled=bool(app.config.get("CLEANUP_ON_MONITOR_START", True)),
        )
        self.snapshot_service = SnapshotService(
            base_dir=Path(BASE_DIR),
            snapshot_dir=str(app.config.get("SNAPSHOT_DIR", "runtime/snapshots")),
            enabled=bool(app.config.get("SNAPSHOT_ENABLED", True)),
            jpeg_quality=int(app.config.get("SNAPSHOT_JPEG_QUALITY", 86)),
        )
        self.event_repository = EventRepository()
        self._last_cleanup: dict[str, Any] | None = None
        self.overlay_options = {
            "boxes": bool(app.config.get("OVERLAY_SHOW_BOXES", True)),
            "labels": bool(app.config.get("OVERLAY_SHOW_LABELS", True)),
            "confidence": bool(app.config.get("OVERLAY_SHOW_CONFIDENCE", True)),
            "pose": bool(app.config.get("OVERLAY_SHOW_POSE", True)),
            "risk_area": bool(app.config.get("OVERLAY_SHOW_RISK_AREA", True)),
        }
        self.annotator = FrameAnnotator(risk_polygon=risk_polygon)

    def start(self) -> dict[str, Any]:
        with self._thread_lock:
            if self._running.is_set():
                return self.status()
            self._last_cleanup = self.cleanup_service.cleanup_startup_artifacts()
            try:
                stale_count = AlertRepository().resolve_all_active(reason="monitor_start_reset")
                self._last_cleanup = (self._last_cleanup or {}) | {"resolved_stale_alerts": stale_count}
            except Exception as exc:  # noqa: BLE001
                logger.warning("stale_alert_cleanup_failed", extra={"error": str(exc)})
            self.alert_state_service.reset()
            self.socketio.emit("active_alerts", {"items": [], "count": 0})
            self._latest_jpeg = None
            self._latest_analysis = None
            self._last_error = None
            self._frame_counter = 0
            self._running.set()
            self._task = self.socketio.start_background_task(self._loop)
            logger.info("monitor_started", extra={"cleanup": self._last_cleanup})
            self._emit_timeline_event("monitor_started", "Monitoramento iniciado", "info", metadata={"cleanup": self._last_cleanup})
            self.socketio.emit("monitor_status", self.status())
            return self.status()

    def stop(self) -> dict[str, Any]:
        self._running.clear()
        self.video_stream.release()
        try:
            resolved_payloads = self.alert_state_service.resolve_all(reason="monitor_stopped")
            for payload in resolved_payloads:
                self._emit_resolved_alert_event_once(payload, false_positive=False)
        except Exception as exc:  # noqa: BLE001
            logger.warning("alert_state_stop_resolution_failed", extra={"error": str(exc)})
        logger.info("monitor_stopped")
        self._emit_timeline_event("monitor_stopped", "Monitoramento parado", "info")
        status = self.status()
        self.socketio.emit("monitor_status", status)
        return status

    def status(self) -> dict[str, Any]:
        return {
            "running": self._running.is_set(),
            "frame_counter": self._frame_counter,
            "last_error": self._last_error,
            "features": self.feature_manager.as_dict(),
            "model": self._safe_model_diagnostics(),
            "active_alerts": self.alert_state_service.active_alerts(),
            "cleanup": self._last_cleanup,
            "overlay": self.overlay_options,
            "settings": self.settings(),
            "risk_area": self.risk_area_state(),
            "snapshot": self.snapshot_service.info(),
        }

    def preflight(self) -> dict[str, Any]:
        checks: list[dict[str, Any]] = []

        checks.append({
            "key": "backend",
            "label": "Backend",
            "status": "ok",
            "message": "API Flask respondendo",
        })
        checks.append({
            "key": "websocket",
            "label": "WebSocket",
            "status": "ok",
            "message": "SocketIO inicializado",
        })

        try:
            db.session.execute(sql_text("SELECT 1"))
            checks.append({"key": "database", "label": "Banco", "status": "ok", "message": "Conexão validada"})
        except Exception as exc:  # noqa: BLE001
            checks.append({"key": "database", "label": "Banco", "status": "error", "message": str(exc)})

        source = self.video_stream.source
        video_message = f"Fonte configurada: {source}"
        video_status = "ok"
        if isinstance(source, str) and not source.isdigit() and not source.startswith(("rtsp://", "http://", "https://")):
            video_status = "ok" if Path(source).exists() else "warning"
            video_message = "Arquivo de vídeo encontrado" if Path(source).exists() else f"Arquivo não encontrado: {source}"
        checks.append({"key": "video", "label": "Vídeo", "status": video_status, "message": video_message})

        model = self._safe_model_diagnostics()
        if model.get("error"):
            model_status = "error"
        elif model.get("ppe_ready"):
            model_status = "ok"
        elif model.get("warning"):
            model_status = "warning"
        else:
            model_status = "ok"
        checks.append({
            "key": "model",
            "label": "Modelo YOLO",
            "status": model_status,
            "message": model.get("warning") or "Modelo carregado",
        })

        cleanup_dirs = self.cleanup_service.directories
        checks.append({
            "key": "cleanup",
            "label": "Limpeza de testes",
            "status": "ok" if self.cleanup_service.enabled else "warning",
            "message": "Limpa ao iniciar: " + ", ".join(cleanup_dirs),
        })
        checks.append({
            "key": "snapshots",
            "label": "Evidências",
            "status": "ok" if self.snapshot_service.enabled else "warning",
            "message": f"Snapshots em {self.snapshot_service.snapshot_dir}",
        })

        summary = {
            "ok": sum(1 for item in checks if item["status"] == "ok"),
            "warning": sum(1 for item in checks if item["status"] == "warning"),
            "error": sum(1 for item in checks if item["status"] == "error"),
        }
        return {"checks": checks, "summary": summary, "can_start": summary["error"] == 0}

    def latest_jpeg(self) -> bytes | None:
        with self._thread_lock:
            return self._latest_jpeg

    def latest_analysis(self) -> dict[str, Any] | None:
        with self._thread_lock:
            return self._latest_analysis


    def _attach_snapshots_and_log_events(self, alert_state: dict[str, Any], frame) -> None:
        created_ids = {item.get("id") for item in alert_state.get("created", []) if item.get("id")}
        if created_ids:
            for runtime_state in self.alert_state_service._states.values():  # runtime state owns the live SQLAlchemy object
                alert = runtime_state.alert
                if alert is None or alert.id not in created_ids:
                    continue
                updated_alert = self.snapshot_service.attach_to_alert(alert, frame)
                payload = updated_alert.to_dict()
                runtime_state.alert = updated_alert
                self.socketio.emit("alert_updated", payload)
                # Linha do tempo registra apenas alertas que saíram do estado ativo.
        for payload in alert_state.get("resolved", []):
            self._emit_resolved_alert_event_once(payload)

    def _emit_resolved_alert_event_once(self, payload: dict[str, Any], *, false_positive: bool = False) -> dict[str, Any] | None:
        subject = (payload.get("metadata") or {}).get("person_label") or (payload.get("metadata") or {}).get("person_id") or payload.get("feature")
        try:
            event = self.event_repository.create_alert_resolved_once(
                alert_payload=payload,
                message=("Falso positivo resolvido: " if false_positive else "Alerta resolvido: ") + str(payload.get("message") or "Alerta"),
                severity="info",
                subject=subject,
                metadata={"false_positive": bool(false_positive)},
            )
            if event is None:
                return None
            event_payload = event.to_dict()
            self.socketio.emit("timeline_event", event_payload)
            return event_payload
        except Exception as exc:  # noqa: BLE001
            logger.warning("resolved_timeline_event_failed", extra={"alert_id": payload.get("id"), "error": str(exc)})
            return None

    def _emit_timeline_event(
        self,
        event_type: str,
        message: str,
        severity: str = "info",
        *,
        subject: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        try:
            event = self.event_repository.create(
                event_type=event_type,
                message=message,
                severity=severity,
                subject=subject,
                metadata=metadata or {},
            )
            payload = event.to_dict()
            self.socketio.emit("timeline_event", payload)
            return payload
        except Exception as exc:  # noqa: BLE001
            logger.warning("timeline_event_failed", extra={"event_type": event_type, "error": str(exc)})
            return None

    @staticmethod
    def _parse_yolo_classes(raw: str | None) -> list[int] | None:
        if not raw:
            return None
        return [int(item.strip()) for item in str(raw).split(",") if item.strip()]

    @staticmethod
    def _parse_risk_polygon(raw: str) -> list[tuple[float, float]]:
        polygon: list[tuple[float, float]] = []
        for pair in str(raw).split(";"):
            x, y = pair.split(",")
            polygon.append((float(x), float(y)))
        return polygon

    def _loop(self) -> None:
        target_fps = max(1, int(self.app.config.get("TARGET_FPS", 12)))
        frame_interval = 1.0 / target_fps
        jpeg_quality = int(self.app.config.get("JPEG_QUALITY", 80))

        with self.app.app_context():
            while self._running.is_set():
                start_time = time.perf_counter()
                try:
                    ok, frame = self.video_stream.read()
                    if not ok or frame is None:
                        self._last_error = "Frame indisponível"
                        time.sleep(0.2)
                        continue

                    analysis = self._analyze_frame(frame)
                    rule_alerts = self.rule_engine.evaluate(analysis.detections, analysis.pose, frame.shape)
                    alert_state = self.alert_state_service.process(rule_alerts)
                    model_diagnostics = self._safe_model_diagnostics()
                    compliance_state = self.compliance_service.build_state(
                        detections=analysis.detections,
                        pose=analysis.pose,
                        frame_shape=frame.shape,
                        model_diagnostics=model_diagnostics,
                        active_alerts=alert_state["active"],
                    )

                    enabled_map = {item.key: item.enabled for item in self.feature_manager.list()}
                    annotated = self.annotator.annotate(frame, analysis.detections, analysis.pose, enabled_map, compliance_state, self.overlay_options)
                    self._attach_snapshots_and_log_events(alert_state, annotated)
                    alert_state["active"] = self.alert_state_service.active_alerts()
                    encode_ok, buffer = cv2.imencode(".jpg", annotated, [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality])
                    if encode_ok:
                        with self._thread_lock:
                            self._latest_jpeg = buffer.tobytes()
                            self._latest_analysis = analysis.to_dict() | {
                                "alerts": alert_state["active"],
                                "alert_changes": alert_state["changed"],
                                "alert_resolved": alert_state["resolved"],
                                "compliance": compliance_state,
                                "model": model_diagnostics,
                            }
                            self._frame_counter += 1

                    payload = self.latest_analysis() or {}
                    self.socketio.emit("analysis", payload)
                    self.socketio.emit("compliance_state", compliance_state)
                    self.socketio.emit("model_diagnostics", model_diagnostics)
                    self._maybe_emit_risk_score()
                    self._last_error = None
                except Exception as exc:  # noqa: BLE001
                    self._last_error = str(exc)
                    logger.exception("monitor_loop_error", extra={"error": str(exc)})
                    time.sleep(1.0)

                elapsed = time.perf_counter() - start_time
                time.sleep(max(0.0, frame_interval - elapsed))

    def _analyze_frame(self, frame) -> FrameAnalysis:
        detections = []
        pose = None
        if self._needs_yolo_detection():
            detections = self.detector.detect(frame)
            if self.app.config.get("MULTI_PERSON_DETECTION", True):
                detections = detections + self.person_detector.detect(frame)
        if self.feature_manager.is_enabled("pose"):
            pose = self.pose_estimator.estimate(frame)
        return FrameAnalysis(detections=detections, pose=pose, risk_events=[])

    def _needs_yolo_detection(self) -> bool:
        return bool(
            self.app.config.get("MULTI_PERSON_DETECTION", True)
            or self.feature_manager.is_enabled("ppe")
            or self.feature_manager.is_enabled("risk_area")
        )

    def _safe_model_diagnostics(self) -> dict[str, Any]:
        if not self._needs_yolo_detection():
            return {
                "model_path": self.detector.model_path,
                "ppe_ready": False,
                "supported_ppe": {"helmet": False, "vest": False, "gloves": False},
                "person_supported": False,
                "warning": "YOLO desativado pelas features atuais",
                "error": None,
            }
        diagnostics = dict(self.detector.diagnostics())
        multi_person = bool(self.app.config.get("MULTI_PERSON_DETECTION", True))
        person_supported = False
        warning_parts = [diagnostics.get("warning")] if diagnostics.get("warning") else []
        if multi_person:
            person_diagnostics = self.person_detector.diagnostics()
            person_supported = bool(person_diagnostics.get("person_supported"))
            diagnostics["person_model_path"] = self.person_detector.model_path
            if not person_supported:
                warning_parts.append(
                    f"Modelo de pessoa ({self.person_detector.model_path}) não possui classe 'person'."
                    if not person_diagnostics.get("error")
                    else f"Modelo de pessoa indisponível: {person_diagnostics.get('error')}"
                )
        diagnostics["person_supported"] = person_supported
        diagnostics["ppe_ready"] = bool(diagnostics.get("ppe_ready")) and (person_supported if multi_person else True)
        diagnostics["warning"] = " ".join(warning_parts) or None
        diagnostics["ppe_feature_enabled"] = self.feature_manager.is_enabled("ppe")
        diagnostics["multi_person_detection"] = multi_person
        return diagnostics

    def _maybe_emit_risk_score(self) -> None:
        # ponytail: throttle por relógio, não por contagem de frame — TARGET_FPS
        # é configurável em runtime, contar frames faria o intervalo derrapar.
        now = time.time()
        if now - self._last_risk_score_emit_at < self.risk_score_interval_seconds:
            return
        self._last_risk_score_emit_at = now
        try:
            self.socketio.emit("risk_score", compute_risk_score())
        except Exception as exc:  # noqa: BLE001
            logger.warning("risk_score_emit_failed", extra={"error": str(exc)})

    def settings(self) -> dict[str, Any]:
        return {
            "video_source": str(self.video_stream.source),
            "target_fps": int(self.app.config.get("TARGET_FPS", 12)),
            "jpeg_quality": int(self.app.config.get("JPEG_QUALITY", 80)),
            "yolo_confidence": float(self.detector.confidence),
            "yolo_max_detections": int(self.detector.max_detections),
            "multi_person_detection": bool(self.app.config.get("MULTI_PERSON_DETECTION", True)),
            "alert_create_after_frames": int(self.alert_state_service.create_after_frames),
            "alert_resolve_after_frames": int(self.alert_state_service.resolve_after_frames),
            "cleanup_on_monitor_start": bool(self.cleanup_service.enabled),
            "snapshot_enabled": bool(self.snapshot_service.enabled),
            "snapshot_jpeg_quality": int(self.snapshot_service.jpeg_quality),
            "risk_area_name": self.risk_area_name,
        }

    def update_settings(self, updates: dict[str, Any]) -> dict[str, Any]:
        allowed_ints = {
            "target_fps": ("TARGET_FPS", 1, 60),
            "jpeg_quality": ("JPEG_QUALITY", 40, 100),
            "yolo_max_detections": ("YOLO_MAX_DETECTIONS", 1, 300),
            "alert_create_after_frames": ("ALERT_CREATE_AFTER_FRAMES", 1, 60),
            "alert_resolve_after_frames": ("ALERT_RESOLVE_AFTER_FRAMES", 1, 120),
            "snapshot_jpeg_quality": ("SNAPSHOT_JPEG_QUALITY", 40, 100),
        }
        for key, (config_key, minimum, maximum) in allowed_ints.items():
            if key not in updates:
                continue
            value = max(minimum, min(maximum, int(updates[key])))
            self.app.config[config_key] = value
            if key == "yolo_max_detections":
                self.detector.max_detections = value
            elif key == "alert_create_after_frames":
                self.alert_state_service.create_after_frames = value
            elif key == "alert_resolve_after_frames":
                self.alert_state_service.resolve_after_frames = value
            elif key == "snapshot_jpeg_quality":
                self.snapshot_service.jpeg_quality = value

        if "yolo_confidence" in updates:
            value = max(0.05, min(0.95, float(updates["yolo_confidence"])))
            self.app.config["YOLO_CONFIDENCE"] = value
            self.detector.confidence = value
        if "multi_person_detection" in updates:
            self.app.config["MULTI_PERSON_DETECTION"] = bool(updates["multi_person_detection"])
        if "cleanup_on_monitor_start" in updates:
            self.cleanup_service.enabled = bool(updates["cleanup_on_monitor_start"])
        if "snapshot_enabled" in updates:
            self.snapshot_service.enabled = bool(updates["snapshot_enabled"])
        if "risk_area_name" in updates and str(updates["risk_area_name"]).strip():
            self.risk_area_name = str(updates["risk_area_name"]).strip()[:80]
        self._emit_timeline_event("settings_updated", "Configurações runtime atualizadas", "info", metadata={"updates": list(updates.keys())})
        self.socketio.emit("settings_updated", self.settings())
        return self.settings()


    def risk_area_state(self) -> dict[str, Any]:
        return {
            "name": self.risk_area_name,
            "polygon": [{"x": round(float(x), 4), "y": round(float(y), 4)} for x, y in self.rule_engine.risk_polygon],
            "enabled": self.feature_manager.is_enabled("risk_area"),
        }

    def update_risk_area(self, payload: dict[str, Any]) -> dict[str, Any]:
        raw_polygon = payload.get("polygon")
        if not isinstance(raw_polygon, list) or len(raw_polygon) < 3:
            raise ValueError("polygon deve conter pelo menos 3 pontos")
        polygon: list[tuple[float, float]] = []
        for point in raw_polygon:
            if isinstance(point, dict):
                x, y = point.get("x"), point.get("y")
            elif isinstance(point, (list, tuple)) and len(point) >= 2:
                x, y = point[0], point[1]
            else:
                raise ValueError("cada ponto deve conter x e y")
            xf = max(0.0, min(1.0, float(x)))
            yf = max(0.0, min(1.0, float(y)))
            polygon.append((xf, yf))
        self.rule_engine.risk_polygon = polygon
        self.annotator.risk_polygon = polygon
        if str(payload.get("name", "")).strip():
            self.risk_area_name = str(payload.get("name")).strip()[:80]
        state = self.risk_area_state()
        self._emit_timeline_event("risk_area_updated", "Área de risco atualizada", "info", metadata=state)
        self.socketio.emit("risk_area_updated", state)
        return state

    def get_overlay(self) -> dict[str, bool]:
        return dict(self.overlay_options)

    def update_overlay(self, updates: dict[str, Any]) -> dict[str, bool]:
        for key in ("boxes", "labels", "confidence", "pose", "risk_area"):
            if key in updates:
                self.overlay_options[key] = bool(updates[key])
        self.socketio.emit("overlay_updated", self.get_overlay())
        return self.get_overlay()
