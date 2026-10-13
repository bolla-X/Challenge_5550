from __future__ import annotations

import threading
from typing import Any

from flask import Flask
from flask_socketio import SocketIO

from app.config import BASE_DIR, Config
from app.extensions import db
from app.models import Camera
from app.services.agendador_de_inferencia import AgendadorDeInferencia
from app.services.camera_worker import CameraWorker
from app.services.controlador_adaptativo import ControladorAdaptativo
from app.services.feature_manager import FeatureManager
from app.services.gravador_assincrono import GravadorAssincrono
from app.services.llm_risk_service import ServicoDeRiscoLLM
from app.utils.limites_de_cpu import manter_afinidade
from app.utils.salas import SALA_PARQUE, sala_da_camera
from app.vision.ensemble_ppe_detector import EnsemblePPEDetector
from app.vision.pose_estimator import MediaPipePoseEstimator
from app.vision.runtime_do_modelo import aquecer_modelos, garantir_runtime, resolver_caminho
from app.vision.yolo_pose_detector import YoloPoseDetector
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
        # Runtime: só export aprovado no guarda de qualidade; senão o .pt.
        peso_epi = str(app.config.get("PPE_MODEL_PATH", "yolov8n.pt"))
        caminho_epi, motivo_epi = resolver_caminho(
            BASE_DIR, modelo="epi", peso_pt=peso_epi, imgsz=int(app.config.get("YOLO_IMGSZ", 640)),
            pedido=str(app.config.get("PPE_RUNTIME", "pytorch")), ordem=str(app.config.get("RUNTIME_ORDEM", "pytorch")),
        )
        detector_principal = YoloPPEDetector(
            model_path=caminho_epi,
            confidence=app.config.get("YOLO_CONFIDENCE", 0.35),
            device=app.config.get("YOLO_DEVICE"),
            classes=CameraWorker._parse_yolo_classes(app.config.get("YOLO_CLASSES", "")),
            max_detections=app.config.get("YOLO_MAX_DETECTIONS", 100),
            require_person=False,
            imgsz=app.config.get("YOLO_IMGSZ", 640),
            half=app.config.get("YOLO_HALF", True),
        )
        # PPE_EXTRA_MODELS vazio => self.detector e o detector unico de sempre.
        # Com um ou mais caminhos, envelopa tudo num ensemble que roda todos no
        # mesmo frame e funde o resultado (ver EnsemblePPEDetector). Cada extra
        # roda SEM YOLO_CLASSES: aquele filtro sao indices do Vyra.
        extras_raw = str(app.config.get("PPE_EXTRA_MODELS", "") or "")
        extra_paths = [p.strip() for p in extras_raw.split(",") if p.strip()]
        if extra_paths:
            extra_imgsz = app.config.get("PPE_EXTRA_MODELS_IMGSZ", 0) or app.config.get("YOLO_IMGSZ", 640)
            # Classes que NENHUM modelo extra deve contribuir — confirmado por
            # diagnostico manual: o epi_pretrained.pt (nano, dataset pequeno)
            # deu "Gloves" 0.78 numa mao NUA levantada (o Vyra, no mesmo frame,
            # se absteve certo). Falso positivo de luva e o pior tipo de erro
            # aqui: o sistema marca a pessoa como protegida quando nao esta.
            # Em vez de confiar no piso de confianca (a deteccao errada saiu
            # com 0.78, acima de qualquer piso razoavel), a classe some da
            # saida do(s) extra(s) e fica so a cargo do Vyra.
            excluir_raw = str(app.config.get("PPE_EXTRA_MODELS_EXCLUDE_LABELS", "") or "")
            excluir_labels = {item.strip() for item in excluir_raw.split(",") if item.strip()}
            extras = []
            for path in extra_paths:
                extra = YoloPPEDetector(
                    model_path=path,
                    confidence=app.config.get("YOLO_CONFIDENCE", 0.35),
                    device=app.config.get("YOLO_DEVICE"),
                    classes=None,
                    max_detections=app.config.get("YOLO_MAX_DETECTIONS", 100),
                    require_person=False,
                    imgsz=extra_imgsz,
                    augment=app.config.get("PPE_EXTRA_MODELS_AUGMENT", True),
                    half=app.config.get("YOLO_HALF", True),
                )
                if excluir_labels:
                    # Forca o load aqui (1x, no boot) pra traduzir label -> id
                    # DESTE peso especifico antes do primeiro detect().
                    nomes = extra.model.names
                    mantidos = [
                        class_id
                        for class_id, raw_nome in nomes.items()
                        if YoloPPEDetector.normalize_label(str(raw_nome)) not in excluir_labels
                    ]
                    extra.classes = mantidos or None
                extras.append(extra)
            self.detector = EnsemblePPEDetector([detector_principal, *extras])
        else:
            self.detector = detector_principal
        # Segundo YOLO (COCO, classe 0) usado APENAS quando
        # MULTI_PERSON_DETECTION=true — isto e, quando PPE_MODEL_PATH aponta pra
        # um modelo de EPI sem classe "person" propria (ex: epi_pretrained.pt).
        # Com o Vyra, que ja detecta "Person", fica ocioso.
        # Mesmo par de modelos, compartilhado por todas as cameras.
        # Com ByteTrack o detector entrega a partir de 0,1: a caixa fraca só
        # continua um track existente, nunca cria pessoa (ByteTrackPessoas).
        confianca_pessoa = 0.1 if str(app.config.get("TRACKER", "iou")).lower() == "bytetrack" else app.config.get(
            "YOLO_CONFIDENCE", 0.35
        )
        peso_pessoa = str(app.config.get("PERSON_MODEL_PATH", "yolov8n.pt"))
        caminho_pessoa, motivo_pessoa = resolver_caminho(
            BASE_DIR, modelo="pessoa", peso_pt=peso_pessoa, imgsz=int(app.config.get("YOLO_IMGSZ", 640)),
            pedido=str(app.config.get("PERSON_RUNTIME", "pytorch")), ordem=str(app.config.get("RUNTIME_ORDEM", "pytorch")),
        )
        self.person_detector = YoloPPEDetector(
            model_path=caminho_pessoa,
            confidence=confianca_pessoa,
            device=app.config.get("YOLO_DEVICE"),
            classes=[0],
            max_detections=app.config.get("YOLO_MAX_DETECTIONS", 100),
            imgsz=app.config.get("YOLO_IMGSZ", 640),
            half=app.config.get("YOLO_HALF", True),
        )
        # POSE_BACKEND=yolo: UMA passada de YOLO-pose por inferência para todas
        # as pessoas; cada esqueleto é associado ao track do detector de pessoa
        # por IoU (ver yolo_pose_detector.associar_esqueletos). O detector de
        # pessoa NÃO é trocado: o yolo11n-pose concordou só 83,8% com o yolov8n
        # nas caixas de pessoa (scripts/concordancia.py, CHANGELOG).
        self.pose_detector = (
            YoloPoseDetector(
                str(app.config.get("POSE_MODEL_PATH", "models/yolo11n-pose.pt")),
                confidence=app.config.get("YOLO_CONFIDENCE", 0.35),
                device=app.config.get("YOLO_DEVICE"),
                max_detections=app.config.get("YOLO_MAX_DETECTIONS", 100),
                imgsz=app.config.get("POSE_IMGSZ", 640),
            )
            if str(app.config.get("POSE_BACKEND", "mediapipe")).lower() == "yolo"
            else None
        )
        self.pose_estimator = MediaPipePoseEstimator(
            min_detection_confidence=app.config.get("POSE_MIN_DETECTION_CONFIDENCE", 0.5),
            min_tracking_confidence=app.config.get("POSE_MIN_TRACKING_CONFIDENCE", 0.5),
        )
        # Escolha do runtime registrada para o painel de diagnóstico; o teste de
        # carga + 1 inferência (com volta ao .pt se falhar) só fora dos testes.
        self.runtimes = {"epi": {"pedido": app.config.get("PPE_RUNTIME"), "motivo": motivo_epi},
                         "pessoa": {"pedido": app.config.get("PERSON_RUNTIME"), "motivo": motivo_pessoa}}
        if not app.config.get("TESTING"):
            self.runtimes["epi"]["ativo"] = garantir_runtime(detector_principal, peso_epi)
            self.runtimes["pessoa"]["ativo"] = garantir_runtime(self.person_detector, peso_pessoa)
        self.aquecimento_ms: dict[str, float] = {}
        # Serializa chamadas de inferência entre workers (ver CameraWorker).
        self._inference_lock = threading.Lock()
        # Um thread de inferência para todas as câmeras (ver
        # agendador_de_inferencia.py). None = loop síncrono de antes.
        self.agendador = (
            AgendadorDeInferencia(lote=bool(app.config.get("INFERENCIA_LOTE", False)))
            if app.config.get("INFERENCIA_ASSINCRONA", True)
            else None
        )

        # ---- camada LLM: um servico POR camera ---------------------------
        # Um por camera, e nao um compartilhado, porque `ao_concluir` e um
        # atributo unico do servico e nao recebe camera_id: com uma instancia
        # so, o callback de uma camera sobrescreveria o da outra e a segunda
        # opiniao apareceria na camera errada. Custa quase nada — o cliente do
        # Gemini nasce sob demanda (ProvedorGemini nao cria cliente no
        # __init__), entao uma instancia por camera e um punhado de atributos,
        # sem rede e sem SDK carregado.
        # O debounce e o "uma em voo" ja sao por camera no desenho do servico,
        # entao a semantica nao muda.
        self._llm_habilitado = bool(app.config.get("LLM_ENABLED", False))

        self._workers: dict[int, CameraWorker] = {}
        self.espectadores: dict[int, int] = {}

        # ---- controlador adaptativo ("modo batata") -----------------------
        self.controlador = ControladorAdaptativo(
            n_base=max(1, int(app.config.get("DETECTION_EVERY_N_FRAMES", 1))),
            # Com o agendador assíncrono, detectar a cada N quadros não alivia
            # nada quando a inferência é o gargalo: o slot de cada câmera já
            # guarda só o quadro mais novo e é servido assim que a anterior
            # acaba. Os degraus de N só atrasariam os úteis (6 s cada: 3
            # leituras de 2 s) — por isso, no assíncrono, a escada começa na pose.
            n_max=(max(1, int(app.config.get("DETECTION_EVERY_N_FRAMES", 1))) if self.agendador is not None
                   else max(1, int(app.config.get("ADAPTATIVO_N_MAX", 6)))),
            pose_k_max=3 if self.pose_detector is not None else 1,
            telemetria_base_hz=float(app.config.get("TELEMETRY_HZ", 8.0)),
            limite_alto_ms=float(app.config.get("ADAPTATIVO_LIMITE_ALTO_MS", 1500.0)),
            limite_baixo_ms=float(app.config.get("ADAPTATIVO_LIMITE_BAIXO_MS", 600.0)),
        )
        # Snapshot de alerta gravado fora do loop da câmera (um thread para todas).
        self.gravador = GravadorAssincrono(app) if self.agendador is not None and not app.config.get("TESTING") else None
        self._parar_adaptativo = threading.Event()
        self._thread_adaptativo: threading.Thread | None = None
        if app.config.get("ADAPTATIVO", True) and self.agendador is not None and not app.config.get("TESTING"):
            self._thread_adaptativo = threading.Thread(target=self._laco_adaptativo, name="controlador-adaptativo", daemon=True)
            self._thread_adaptativo.start()
        self._workers_lock = threading.RLock()
        self._default_camera_id: int | None = None

    # ---- ciclo de vida dos workers -----------------------------------------
    def aquecer(self) -> dict[str, float]:
        """Uma inferência em cada modelo (EPI, pessoa, pose) antes de servir.

        Chamado pelo `run.py`, não pelo construtor: o `wsgi.py` também é
        importado pelos comandos `flask users ...`, que não precisam de modelo.
        Ver `aquecer_modelos` para o número que motivou isto.
        """
        self.aquecimento_ms = aquecer_modelos([self.detector, self.person_detector, self.pose_detector])
        return self.aquecimento_ms

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
        # `fonte_configurada`, e NAO `video_stream.source`: em modo fixture o
        # worker troca a fonte de video em runtime (ver
        # CameraWorker._assumir_fonte_reserva). Comparando com a fonte trocada,
        # todo `load_cameras_from_db()` — que roda a cada CRUD de camera — veria
        # "a fonte mudou", reconstruiria o worker e derrubaria o modo fixture no
        # meio do demo, com a camera voltando a tentar a fonte morta do zero.
        current_source = str(worker.fonte_configurada)
        new_source = str(Config.parse_video_source(camera.source))
        return (
            current_source != new_source
            or worker.target_fps != camera.fps
            or worker.video_stream.width != camera.width
            or worker.video_stream.height != camera.height
            or worker.rotation != int(camera.rotation or 0)
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
            rotation=int(camera.rotation or 0),
            risk_polygon=camera.risk_polygon,
            gate_required=camera.gate_required,
            detector=self.detector,
            person_detector=self.person_detector,
            pose_estimator=self.pose_estimator,
            pose_detector=self.pose_detector,
            inference_lock=self._inference_lock,
            servico_llm=self._criar_servico_llm(),
            agendador=self.agendador,
            gravador=self.gravador,
        )

    def _criar_servico_llm(self):
        """Servico de segunda opiniao para UMA camera, ou None.

        `None` quando LLM_ENABLED=false ou nao ha GEMINI_API_KEY — que e o
        default. A fabrica do servico ja resolve isso: sem chave ela devolve um
        servico com `habilitado=False`, e ai nao vale carregar nada.
        """
        if not self._llm_habilitado:
            return None
        servico = ServicoDeRiscoLLM.a_partir_da_config(self.app.config)
        return servico if servico.habilitado else None

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

    def features_of(self, camera_id: int | None = None) -> FeatureManager:
        """FeatureManager que de fato governa a câmera: o global para a padrão,
        o próprio worker para as demais."""
        return self._get_worker(camera_id).feature_manager

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

    def latest_jpeg_versionado(self, camera_id: int | None = None) -> tuple[bytes | None, int]:
        return self._get_worker(camera_id).latest_jpeg_versionado()

    def _laco_adaptativo(self) -> None:
        while not self._parar_adaptativo.wait(2.0):
            try:
                manter_afinidade()
                self.tique_adaptativo()
            except Exception:  # noqa: BLE001  (o controlador nunca derruba o monitor)
                pass

    def tique_adaptativo(self) -> bool:
        """Uma leitura do controlador. Devolve True se o nível mudou (e aplica)."""
        with self._workers_lock:
            workers = [w for w in self._workers.values() if w._running.is_set()]
        idades = [
            w.stats.resumo(10.0)["etapas"].get("idade_na_inferencia", {}).get("p95")
            for w in workers
        ]
        idades = [v for v in idades if v is not None]
        if not self.controlador.avaliar(max(idades) if idades else None):
            return False
        self._aplicar_adaptativo(workers)
        return True

    def _aplicar_adaptativo(self, workers) -> None:
        cfg = self.controlador.configuracao()
        resumo = self.controlador.resumo()
        for worker in workers:
            worker.detect_every_n = int(cfg["n"])
            worker.pose_a_cada_k = int(cfg.get("pose_k", 1))
            worker._intervalo_telemetria = 1.0 / float(cfg["telemetria_hz"]) if cfg["telemetria_hz"] else 0.0
            worker.modo_adaptativo = resumo
        self.socketio.emit("modo_adaptativo", resumo, to=SALA_PARQUE)
        for worker in workers:
            self.socketio.emit("modo_adaptativo", resumo | {"camera_id": worker.camera_id}, to=sala_da_camera(worker.camera_id))

    def registrar_espectador(self, camera_id: int, delta: int) -> None:
        """Quantos streams abertos por câmera (diagnóstico; o encode já é sob demanda)."""
        with self._workers_lock:
            self.espectadores[camera_id] = max(0, self.espectadores.get(camera_id, 0) + delta)
            worker = self._workers.get(camera_id)
            if worker is not None:
                worker.espectadores = self.espectadores[camera_id]

    def worker_da_camera(self, camera_id: int | None = None) -> CameraWorker:
        """O worker em si — para o gerador do MJPEG e o diagnóstico do pipeline."""
        return self._get_worker(camera_id)

    def diagnostico_do_pipeline(
        self, camera_ids: list[int] | None = None, janela_s: float = 30.0, quadro: int | None = None
    ) -> dict[str, Any]:
        """Percentis por etapa e taxas de cada câmera, mais o estado dos modelos."""
        with self._workers_lock:
            workers = dict(self._workers)
        cameras = {}
        for camera_id, worker in workers.items():
            if camera_ids is not None and camera_id not in camera_ids:
                continue
            cameras[str(camera_id)] = {
                "running": worker._running.is_set(),
                "fonte_fps": worker.video_stream.fps_da_fonte,
                "alvo_fps": worker.target_fps,
                "detectar_a_cada_n": worker.detect_every_n,
                "espectadores": self.espectadores.get(camera_id, 0),
                "stats": worker.stats.resumo(janela_s),
            }
            if quadro is not None:
                cameras[str(camera_id)]["ts_quadro_ms"] = worker.stats.ts_do_quadro(quadro)
        detectores = {"epi": self.detector, "pessoa": self.person_detector}
        if self.pose_detector is not None:
            detectores["pose"] = self.pose_detector
        modelos = {
            nome: {
                "caminho": getattr(det, "model_path", None),
                "imgsz": getattr(det, "imgsz", None),
                "carga_ms": getattr(det, "load_ms", None),
                "runtime": getattr(det, "runtime", None),
                "escolha": self.runtimes.get(nome),
                "aquecimento_ms": self.aquecimento_ms.get(str(getattr(det, "model_path", ""))),
            }
            for nome, det in detectores.items()
        }
        return {
            "cameras": cameras,
            "modelos": modelos,
            "agendador": self.agendador.estado() if self.agendador is not None else None,
            "adaptativo": self.controlador.resumo(),
        }

    def latest_analysis(self, camera_id: int | None = None) -> dict[str, Any] | None:
        return self._get_worker(camera_id).latest_analysis()

    def settings(self, camera_id: int | None = None) -> dict[str, Any]:
        return self._get_worker(camera_id).settings()

    def update_settings(self, updates: dict[str, Any], camera_id: int | None = None) -> dict[str, Any]:
        return self._get_worker(camera_id).update_settings(updates)

    def get_overlay(self, camera_id: int | None = None) -> dict[str, Any]:
        return self._get_worker(camera_id).get_overlay()

    def update_overlay(self, updates: dict[str, Any], camera_id: int | None = None) -> dict[str, Any]:
        return self._get_worker(camera_id).update_overlay(updates)

    def limpar_alertas_ativos(self, camera_id: int | None = None) -> dict[str, Any]:
        """Resolve os alertas ativos de UMA camera (ou de todas).

        Camera rodando: pede ao worker, que resolve na propria thread. Camera
        parada: nao ha dono do estado, entao resolve direto no banco.
        """
        from app.repositories.alert_repository import AlertRepository

        with self._workers_lock:
            workers = dict(self._workers)
        alvo_ids = [camera_id] if camera_id is not None else list(workers)
        pedidos: list[int] = []
        direto = 0
        for cid in alvo_ids:
            worker = workers.get(cid)
            if worker is not None and worker._running.is_set():
                worker.pedir_limpeza_alertas()
                pedidos.append(cid)
            else:
                direto += AlertRepository().resolve_all_active(reason="manual_clear", camera_id=cid)
        return {"pedidos": pedidos, "resolvidos_direto": direto}

    def risk_area_state(self, camera_id: int | None = None) -> dict[str, Any]:
        return self._get_worker(camera_id).risk_area_state()

    def update_risk_area(self, payload: dict[str, Any], camera_id: int | None = None) -> dict[str, Any]:
        worker = self._get_worker(camera_id)
        state = worker.update_risk_area(payload)
        # Persiste na câmera: sem isto a zona voltava pro padrão do .env a cada
        # reinício e toda câmera acabava com o mesmo polígono.
        camera = db.session.get(Camera, worker.camera_id)
        if camera is not None:
            camera.risk_polygon = [[p["x"], p["y"]] for p in state["polygon"]]
            db.session.commit()
        return state

    def gate_state(self, camera_id: int) -> dict[str, Any]:
        return self._get_worker(camera_id).gate_state()

    def update_gate(self, camera_id: int, required: list[str] | None) -> dict[str, Any]:
        """Liga/desliga a portaria e persiste (funciona com a câmera parada)."""
        camera = db.session.get(Camera, camera_id)
        if camera is None:
            raise LookupError("câmera não encontrada")
        camera.gate_required = required
        db.session.commit()
        try:
            self._get_worker(camera_id).set_gate(required)
        except LookupError:
            pass  # sem worker ativo: vale no próximo start
        return {"camera_id": camera_id, "required": required or [], "enabled": required is not None}

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
