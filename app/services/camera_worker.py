from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any

import cv2
from flask import Flask
from flask_socketio import SocketIO
from sqlalchemy import text as sql_text

from app.config import BASE_DIR, Config
from app.extensions import db
from app.repositories.alert_repository import AlertRepository
from app.repositories.event_repository import EventRepository
from app.services.alert_state_service import AlertStateService
from app.services.compliance_service import ComplianceService
from app.services.feature_manager import FeatureManager
from app.services.risk_rules import RuleEngine
from app.services.risk_score_service import compute_risk_score
from app.services.snapshot_service import SnapshotService
from app.services.storage_cleanup_service import StorageCleanupService
from app.vision.annotator import FrameAnnotator
from app.vision.person_tracker import PersonTracker
from app.vision.pose_estimator import MediaPipePoseEstimator
from app.vision.schemas import FrameAnalysis, PoseResult
from app.vision.video_stream import VideoStream
from app.vision.yolo_ppe_detector import YoloPPEDetector

logger = logging.getLogger(__name__)


class CameraWorker:
    """Captura + análise + estado de UMA câmera.

    Fase A, Passo 4: os modelos YOLO/pose (detector/person_detector/
    pose_estimator) e o `inference_lock` agora são INJETADOS pelo
    MonitorService, não mais criados aqui — carregados uma única vez e
    compartilhados entre todos os workers, pra não multiplicar VRAM por
    câmera. `source`, `fps` e `feature_manager` também passam a ser
    parâmetros por-câmera (vindos de app.models.Camera) em vez de lidos
    direto do app.config global — cada câmera tem sua própria fonte de
    vídeo e seu próprio conjunto de features ligadas.

    O `inference_lock` serializa as chamadas de inferência entre workers
    (um por vez usa a GPU pros modelos compartilhados) — captura de frame
    de cada câmera continua paralela, só a etapa de "rodar o modelo em
    cima do frame" é serializada. Numa GPU só, isso é seguro por natureza
    (ela já processa um kernel por vez) e evita qualquer risco de dois
    threads chamando forward() no mesmo objeto de modelo ao mesmo tempo.
    """

    def __init__(
        self,
        app: Flask,
        socketio: SocketIO,
        feature_manager: FeatureManager,
        *,
        camera_id: int | None,
        source: str | int,
        fps: int,
        width: int = 960,
        height: int = 540,
        detector: YoloPPEDetector,
        person_detector: YoloPPEDetector,
        pose_estimator: MediaPipePoseEstimator,
        inference_lock: threading.Lock,
    ) -> None:
        self.app = app
        self.socketio = socketio
        self.feature_manager = feature_manager
        self.camera_id = camera_id
        self.target_fps = max(1, int(fps))
        self._running = threading.Event()
        self._thread_lock = threading.RLock()
        self._task = None
        self._latest_jpeg: bytes | None = None
        self._latest_analysis: dict[str, Any] | None = None
        self._last_error: str | None = None
        # Ultimo estado de captura JA comunicado — so emite evento na transicao,
        # nao a cada frame ruim (a 12 FPS seriam 12 eventos por segundo).
        self._last_stream_state: str | None = None
        self._frame_counter = 0
        self._last_risk_score_emit_at = 0.0
        self.risk_score_interval_seconds = 30

        # Área de risco/polígono ainda vem do .env global — cada câmera ter
        # sua própria zona configurável fica pro backlog de câmera-config
        # (o CameraConfigPanel mock do frontend já reserva esse espaço).
        risk_polygon = self._parse_risk_polygon(app.config.get("RISK_AREA_POLYGON", Config.RISK_AREA_POLYGON))
        self.risk_area_name = str(app.config.get("RISK_AREA_NAME", "Área de risco"))
        self.video_stream = VideoStream(
            source=source,
            width=width,
            height=height,
        )
        # Modelos compartilhados — injetados, não criados aqui (ver docstring).
        self.detector = detector
        self.person_detector = person_detector
        self.pose_estimator = pose_estimator
        self.inference_lock = inference_lock
        # Um tracker POR câmera (ver docstring de PersonTracker): os modelos
        # YOLO são compartilhados, então o estado de tracking não pode morar
        # dentro deles.
        self.person_tracker = PersonTracker()
        # Detecção intercalada (ver Config.DETECTION_EVERY_N_FRAMES). Contador
        # e último resultado são POR câmera: cada uma tem seu próprio ritmo, e
        # misturar as caixas de uma com as da outra seria pior que o lag.
        # Contador PRÓPRIO: `_frame_counter` conta frames publicados e sai no
        # status: reaproveitá-lo aqui faria a contagem andar em dobro.
        self.detect_every_n = max(1, int(app.config.get("DETECTION_EVERY_N_FRAMES", 1)))
        self._detect_counter = 0
        self._cached_analysis: FrameAnalysis | None = None
        # Telemetria (ver _deve_emitir_telemetria e Config.TELEMETRY_HZ).
        hz = float(app.config.get("TELEMETRY_HZ", 8.0))
        self._intervalo_telemetria = (1.0 / hz) if hz > 0 else 0.0
        self._ultima_telemetria = 0.0
        self._ultimo_diagnostico: tuple | None = None
        # Perfil por etapa do loop (ver _perf_fim). Número de frames por
        # relatório; 0 desliga e os métodos saem na primeira linha.
        self._perf_ativo = max(0, int(app.config.get("PROFILE_FRAMES", 0)))
        self._perf_t = 0.0
        self._perf_atual: dict[str, float] = {}
        self._perf_soma: dict[str, float] = {}
        self._perf_n = 0
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
            camera_id=camera_id,
            intervalo_touch=app.config.get("ALERT_TOUCH_INTERVAL_SECONDS", 2.0),
        )
        self.compliance_service = ComplianceService(feature_manager, self.rule_engine)
        cleanup_dirs = str(app.config.get("CLEANUP_DIRECTORIES", "runtime/snapshots,runtime/frames,runtime/tmp")).split(",")
        self.cleanup_service = StorageCleanupService(
            base_dir=Path(BASE_DIR),
            directories=cleanup_dirs,
            enabled=bool(app.config.get("CLEANUP_ON_MONITOR_START", True)),
            # Preserva snapshots que alertas do historico ainda referenciam.
            protected_files=AlertRepository().referenced_frame_filenames,
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
                stale_count = AlertRepository().resolve_all_active(
                    reason="monitor_start_reset",
                    camera_id=self.camera_id,
                )
                self._last_cleanup = (self._last_cleanup or {}) | {"resolved_stale_alerts": stale_count}
            except Exception as exc:  # noqa: BLE001
                logger.warning("stale_alert_cleanup_failed", extra={"error": str(exc)})
            self.alert_state_service.reset()
            self.socketio.emit("active_alerts", {"camera_id": self.camera_id, "items": [], "count": 0})
            self._latest_jpeg = None
            self._latest_analysis = None
            self._last_error = None
            self._frame_counter = 0
            # Sem isto, a câmera volta exibindo as caixas da sessão anterior
            # até a primeira inferência nova concluir.
            self._detect_counter = 0
            self._cached_analysis = None
            self._last_stream_state = None
            self.person_tracker.reset()
            self._running.set()
            self._task = self.socketio.start_background_task(self._loop)
            logger.info("monitor_started", extra={"camera_id": self.camera_id, "cleanup": self._last_cleanup})
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
        logger.info("monitor_stopped", extra={"camera_id": self.camera_id})
        self._emit_timeline_event("monitor_stopped", "Monitoramento parado", "info")
        status = self.status()
        self.socketio.emit("monitor_status", status)
        return status

    def status(self) -> dict[str, Any]:
        return {
            "camera_id": self.camera_id,
            "running": self._running.is_set(),
            "frame_counter": self._frame_counter,
            "last_error": self._last_error,
            # Estado da captura (live/reconnecting/unavailable + backoff): sem
            # isso o dashboard so via "Frame indisponivel" e nao distinguia
            # "caiu agora" de "morta ha 10 minutos".
            "video": self.video_stream.status().to_dict(),
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

    def latest_jpeg_versionado(self) -> tuple[bytes | None, int]:
        """O frame e um número que muda a cada frame novo.

        O stream MJPEG usa a versão para mandar cada frame UMA vez. Antes ele
        reenviava `latest_jpeg` num relógio próprio, sem saber se havia frame
        novo: como esse relógio e o do worker não são sincronizados, o mesmo
        quadro ia repetido e outros eram pulados. No navegador isso aparece
        como engasgo — imagem parada e depois um salto — mesmo com a contagem
        de quadros parecendo alta, porque as repetições contam.
        """
        with self._thread_lock:
            return self._latest_jpeg, self._frame_counter

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
        metadata = payload.get("metadata") or {}
        subject = metadata.get("person_label") or metadata.get("person_id") or payload.get("feature")
        try:
            event = self.event_repository.create_alert_resolved_once(
                alert_payload=payload,
                message=(
                    ("Falso positivo resolvido: " if false_positive else "Alerta resolvido: ")
                    + str(payload.get("message") or "Alerta")
                ),
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
                camera_id=self.camera_id,
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
        target_fps = self.target_fps
        frame_interval = 1.0 / target_fps
        jpeg_quality = int(self.app.config.get("JPEG_QUALITY", 80))

        with self.app.app_context():
            while self._running.is_set():
                start_time = time.perf_counter()
                self._perf_inicio()
                try:
                    ok, frame = self.video_stream.read()
                    self._perf_marca("captura")
                    if not ok or frame is None:
                        self._handle_capture_failure()
                        continue

                    analysis = self._analyze_frame(frame)
                    self._perf_marca("analise")
                    # UMA passada de regras por frame. O resultado (alertas +
                    # estado por pessoa) alimenta tanto o AlertStateService
                    # quanto o ComplianceService — que antes refazia todo o
                    # trabalho por conta própria.
                    evaluation = self.rule_engine.analyze(
                        analysis.detections,
                        analysis.pose,
                        frame.shape,
                        poses=analysis.poses,
                    )
                    self._perf_marca("regras")
                    alert_state = self.alert_state_service.process(evaluation.alerts)
                    self._perf_marca("alertas")
                    model_diagnostics = self._safe_model_diagnostics()
                    compliance_state = self.compliance_service.build_state(
                        detections=analysis.detections,
                        pose=analysis.pose,
                        frame_shape=frame.shape,
                        model_diagnostics=model_diagnostics,
                        active_alerts=alert_state["active"],
                        evaluation=evaluation,
                    )

                    enabled_map = {item.key: item.enabled for item in self.feature_manager.list()}
                    annotated = self.annotator.annotate(
                        frame,
                        analysis.detections,
                        analysis.poses or ([analysis.pose] if analysis.pose else []),
                        enabled_map,
                        compliance_state,
                        self.overlay_options,
                    )
                    self._perf_marca("anotacao")
                    self._attach_snapshots_and_log_events(alert_state, annotated)
                    alert_state["active"] = self.alert_state_service.active_alerts()
                    encode_ok, buffer = cv2.imencode(".jpg", annotated, [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality])
                    self._perf_marca("encode")
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

                    # camera_id em TODO payload: o dashboard usa isso pra
                    # descartar o que não é da câmera em foco. Sem o carimbo,
                    # duas câmeras rodando sobrescreviam o estado uma da outra
                    # a cada frame.
                    if self._last_stream_state not in (None, "live"):
                        self._last_stream_state = "live"
                        self._emit_timeline_event(
                            "camera_reconnected",
                            "Sinal restabelecido",
                            "info",
                            metadata=self.video_stream.status().to_dict(),
                        )
                        self.socketio.emit("monitor_status", self.status())

                    # Telemetria com taxa própria, separada da do vídeo. O
                    # `analysis` sozinho pesa ~26 KB (detecções + landmarks de
                    # pose por pessoa); mandá-lo a 24 FPS por duas câmeras
                    # empurrava ~1,2 MB/s pro navegador, e cada evento dispara
                    # re-render. As caixas que aparecem no vídeo NÃO dependem
                    # disto — vêm desenhadas no MJPEG.
                    #
                    # Mudança de alerta fura o intervalo: quando alguém tira o
                    # capacete, o painel tem que reagir na hora, não no
                    # próximo tique.
                    mudou_alerta = bool(alert_state["changed"] or alert_state["resolved"])
                    if mudou_alerta or self._deve_emitir_telemetria():
                        payload = self.latest_analysis() or {}
                        self.socketio.emit("analysis", payload | {"camera_id": self.camera_id})
                        self.socketio.emit("compliance_state", compliance_state | {"camera_id": self.camera_id})
                        self._emitir_diagnostico_se_mudou(model_diagnostics)
                    self._maybe_emit_risk_score()
                    self._perf_marca("emissao")
                    self._perf_fim()
                    self._last_error = None
                except Exception as exc:  # noqa: BLE001
                    self._last_error = str(exc)
                    logger.exception("monitor_loop_error", extra={"camera_id": self.camera_id, "error": str(exc)})
                    time.sleep(1.0)

                elapsed = time.perf_counter() - start_time
                time.sleep(max(0.0, frame_interval - elapsed))

    # ------------------------------------------------------- perfil do loop -
    # Diagnóstico de "por que o vídeo está travado". FPS médio engana: quadros
    # repetidos inflam a contagem e uma etapa cara esconde-se na média. Ligado
    # por PROFILE_FRAMES no .env (0 = desligado, sem custo).
    def _perf_inicio(self) -> None:
        if not self._perf_ativo:
            return
        self._perf_t = time.perf_counter()
        self._perf_atual = {}

    def _perf_marca(self, etapa: str) -> None:
        if not self._perf_ativo:
            return
        agora = time.perf_counter()
        self._perf_atual[etapa] = (agora - self._perf_t) * 1000.0
        self._perf_t = agora

    def _perf_fim(self) -> None:
        if not self._perf_ativo:
            return
        for etapa, ms in self._perf_atual.items():
            self._perf_soma[etapa] = self._perf_soma.get(etapa, 0.0) + ms
        self._perf_n += 1
        if self._perf_n < self._perf_ativo:
            return
        media = {k: round(v / self._perf_n, 1) for k, v in sorted(self._perf_soma.items(), key=lambda kv: -kv[1])}
        total = round(sum(media.values()), 1)
        logger.warning(
            "perfil_do_frame",
            extra={
                "camera_id": self.camera_id,
                "frames": self._perf_n,
                "ms_por_etapa": media,
                "ms_total": total,
                "fps_possivel": round(1000.0 / total, 1) if total else None,
            },
        )
        self._perf_soma, self._perf_n = {}, 0

    def _deve_emitir_telemetria(self) -> bool:
        """True no máximo TELEMETRY_HZ vezes por segundo."""
        if self._intervalo_telemetria <= 0:
            return True
        agora = time.perf_counter()
        if agora - self._ultima_telemetria < self._intervalo_telemetria:
            return False
        self._ultima_telemetria = agora
        return True

    def _emitir_diagnostico_se_mudou(self, diagnostics: dict[str, Any]) -> None:
        """Só manda o diagnóstico do modelo quando ele muda de verdade.

        São ~1,3 KB com a lista das 14 classes — conteúdo que só muda se
        alguém trocar de modelo ou o carregamento falhar. Reenviar a cada
        frame era puro desperdício de banda e de re-render.
        """
        assinatura = (
            diagnostics.get("model_path"),
            diagnostics.get("ppe_ready"),
            diagnostics.get("error"),
            diagnostics.get("warning"),
            diagnostics.get("raw_class_count"),
        )
        if assinatura == self._ultimo_diagnostico:
            return
        self._ultimo_diagnostico = assinatura
        self.socketio.emit("model_diagnostics", diagnostics | {"camera_id": self.camera_id})

    def _handle_capture_failure(self) -> None:
        """Frame nao veio. Anota o estado, avisa a UI quando ele MUDA e dorme
        o tempo certo — nem loop apertado, nem parado alem do backoff."""
        estado = self.video_stream.status()
        self._last_error = estado.last_error or "Frame indisponível"

        if estado.state != self._last_stream_state:
            self._last_stream_state = estado.state
            if estado.state in ("reconnecting", "unavailable"):
                self._emit_timeline_event(
                    "camera_disconnected",
                    f"Sinal perdido — tentando reconectar (tentativa {estado.reconnect_attempts + 1})",
                    "warning",
                    metadata=estado.to_dict(),
                )
            self.socketio.emit("monitor_status", self.status())

        # Dentro da janela de backoff nao adianta girar a 12 FPS; fora dela,
        # 0.2s mantem a resposta rapida quando a fonte volta.
        time.sleep(min(max(estado.seconds_until_retry, 0.2), 1.0))

    def _analyze_frame(self, frame) -> FrameAnalysis:
        # Detecção intercalada: com detect_every_n > 1, os frames do meio
        # reaproveitam as caixas da última inferência em vez de rodar o modelo.
        # O vídeo continua saindo na taxa de captura (fluido) enquanto a
        # detecção anda no ritmo que a máquina aguenta.
        #
        # O que isso custa: as caixas ficam até (N-1) frames defasadas em
        # relação ao vídeo. Como EPI não aparece e some entre frames, a
        # conformidade não muda; o que "atrasa" é a caixa acompanhar alguém em
        # movimento. Por isso o padrão é 1 — quem liga escolhe essa troca.
        self._detect_counter += 1
        if self.detect_every_n > 1 and self._cached_analysis is not None:
            if self._detect_counter % self.detect_every_n != 0:
                return self._cached_analysis

        detections = []
        pose = None
        poses: list[PoseResult] = []
        # inference_lock: modelos são compartilhados entre workers (Passo 4)
        # — serializa quem usa a GPU por vez. Numa GPU só isso não perde
        # paralelismo real (ela já processa um kernel de cada vez), só evita
        # dois threads chamando forward() no mesmo objeto simultaneamente.
        self._perf_marca("espera_do_lock_pre")
        with self.inference_lock:
            self._perf_marca("espera_do_lock")
            if self._needs_yolo_detection():
                detections = self.detector.detect(frame)
                self._perf_marca("yolo")
                if self.app.config.get("MULTI_PERSON_DETECTION", True):
                    # Só as pessoas passam pelo tracker — EPIs são associados
                    # geometricamente a elas (PersonComplianceMatcher), não
                    # rastreados por conta própria.
                    people = self.person_tracker.update(self.person_detector.detect(frame))
                    detections = detections + people
            if self.feature_manager.is_enabled("pose"):
                poses = self._estimate_poses(frame, detections)
                self._perf_marca("pose")
                # `pose` continua sendo a primeira (ou a global) pra nao quebrar
                # quem ja lia esse campo — frontend inclusive.
                pose = poses[0] if poses else None
        analise = FrameAnalysis(detections=detections, pose=pose, risk_events=[], poses=poses)
        self._cached_analysis = analise
        return analise

    def _estimate_poses(self, frame, detections) -> list[PoseResult]:
        """Uma pose por pessoa quando ha caixa de pessoa; senao, a global.

        A pose global cobre o caso em que o modelo nao detectou ninguem mas o
        MediaPipe ainda encontra um corpo — comportamento de sempre, mantido
        como rede de seguranca.
        """
        if not bool(self.app.config.get("POSE_PER_PERSON", True)):
            global_pose = self.pose_estimator.estimate(frame)
            return [global_pose] if global_pose.found else []

        pessoas = [item for item in detections if item.label == "person" or item.category == "person"]
        pessoas.sort(key=lambda item: item.track_id if item.track_id is not None else 0)
        alvos = [
            (
                f"person_{item.track_id}" if item.track_id is not None else f"person_{indice}",
                item.track_id,
                item.box,
            )
            for indice, item in enumerate(pessoas, start=1)
        ]
        if alvos:
            poses = self.pose_estimator.estimate_for_people(
                frame,
                alvos,
                max_people=int(self.app.config.get("POSE_MAX_PEOPLE", 4)),
            )
            if poses:
                return poses

        global_pose = self.pose_estimator.estimate(frame)
        return [global_pose] if global_pose.found else []

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
            self.socketio.emit("risk_score", compute_risk_score(camera_id=self.camera_id))
        except Exception as exc:  # noqa: BLE001
            logger.warning("risk_score_emit_failed", extra={"error": str(exc)})

    def settings(self) -> dict[str, Any]:
        return {
            "camera_id": self.camera_id,
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
        self._emit_timeline_event(
            "settings_updated",
            "Configurações runtime atualizadas",
            "info",
            metadata={"updates": list(updates.keys())},
        )
        self.socketio.emit("settings_updated", self.settings())
        return self.settings()

    def risk_area_state(self) -> dict[str, Any]:
        return {
            "camera_id": self.camera_id,
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

    def get_overlay(self) -> dict[str, Any]:
        return {"camera_id": self.camera_id, **self.overlay_options}

    def update_overlay(self, updates: dict[str, Any]) -> dict[str, Any]:
        for key in ("boxes", "labels", "confidence", "pose", "risk_area"):
            if key in updates:
                self.overlay_options[key] = bool(updates[key])
        self.socketio.emit("overlay_updated", self.get_overlay())
        return self.get_overlay()
