from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Alert(db.Model):
    __tablename__ = "alerts"

    id = db.Column(db.Integer, primary_key=True)
    rule = db.Column(db.String(80), nullable=False, index=True)
    severity = db.Column(db.String(30), nullable=False, index=True)
    message = db.Column(db.String(255), nullable=False)
    feature = db.Column(db.String(80), nullable=True, index=True)
    status = db.Column(db.String(30), nullable=False, default="active", index=True)
    frame_ref = db.Column(db.String(240), nullable=True)
    metadata_json = db.Column(db.JSON, nullable=False, default=dict)
    occurrences = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, index=True)
    first_seen_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, index=True)
    last_seen_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, index=True)
    resolved_at = db.Column(db.DateTime(timezone=True), nullable=True, index=True)

    @property
    def key(self) -> str:
        metadata = self.metadata_json or {}
        subject = metadata.get("person_id") or metadata.get("subject") or "global"
        return f"{self.rule}:{self.feature or 'global'}:{subject}"

    def to_dict(self) -> dict:
        metadata = self.metadata_json or {}
        return {
            "id": self.id,
            "key": self.key,
            "rule": self.rule,
            "severity": self.severity,
            "message": self.message,
            "feature": self.feature,
            "status": self.status,
            "frame_ref": self.frame_ref,
            "metadata": metadata,
            "false_positive": bool(metadata.get("false_positive")),
            "occurrences": self.occurrences,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "first_seen_at": self.first_seen_at.isoformat() if self.first_seen_at else None,
            "last_seen_at": self.last_seen_at.isoformat() if self.last_seen_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }


class EventLog(db.Model):
    __tablename__ = "event_logs"

    id = db.Column(db.Integer, primary_key=True)
    event_type = db.Column(db.String(80), nullable=False, index=True)
    severity = db.Column(db.String(30), nullable=False, default="info", index=True)
    message = db.Column(db.String(255), nullable=False)
    subject = db.Column(db.String(120), nullable=True, index=True)
    metadata_json = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, index=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "event_type": self.event_type,
            "severity": self.severity,
            "message": self.message,
            "subject": self.subject,
            "metadata": self.metadata_json or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# Features padrão de uma câmera nova — mesmas chaves que o FeatureManager já
# usa hoje (ver app/services/feature_manager.py), só que agora por câmera em
# vez de globais. Todas ligadas por padrão: uma câmera recém-criada deveria
# "ver tudo" até alguém restringir deliberadamente (oposto do Operador vs.
# Técnico: aqui quem decide é o Técnico, então o padrão é permissivo).
# Features padrão de uma câmera nova — precisa bater exatamente com as 8
# chaves de FeatureManager.AVAILABLE_FEATURES (app/services/feature_manager.py)
# e com o default real do sistema hoje (.env: DEFAULT_FEATURES=ppe,helmet,
# vest,gloves,pose,falls,posture,risk_area — todas ligadas). Diverge daqui
# e uma câmera nova nasce com comportamento diferente do que o .env sempre
# gerou, o que quebra a paridade que o seed do Passo 1 promete.
DEFAULT_CAMERA_FEATURES = {
    "ppe": True,
    "helmet": True,
    "vest": True,
    "gloves": True,
    "pose": True,
    "falls": True,
    "posture": True,
    "risk_area": True,
}


class Camera(db.Model):
    __tablename__ = "cameras"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    location = db.Column(db.String(160), nullable=True)
    # "USB" (índice numérico em string), "RTSP" (URL) ou "Arquivo" (path) —
    # mesma distinção de fonte que MonitorService.parse_video_source já
    # entende; source_type é só pra UI (formulário/validação), o worker de
    # captura não olha pra ele, só pra `source`.
    source_type = db.Column(db.String(20), nullable=False, default="USB")
    source = db.Column(db.String(255), nullable=False)
    fps = db.Column(db.Integer, nullable=False, default=12)
    # Resolução de captura por câmera — antes era global (FRAME_WIDTH/
    # FRAME_HEIGHT no .env, uma só pra todas). Cada câmera tem hardware
    # diferente (ex.: webcam embutida 640x480 vs Logitech 1920x1080), então
    # forçar a mesma resolução pra todas ou reduz demais a de alta
    # qualidade, ou tenta um upscale impossível na de baixa qualidade.
    width = db.Column(db.Integer, nullable=False, default=960)
    height = db.Column(db.Integer, nullable=False, default=540)
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    features_json = db.Column(db.JSON, nullable=False, default=lambda: dict(DEFAULT_CAMERA_FEATURES))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, index=True)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "location": self.location,
            "source_type": self.source_type,
            "source": self.source,
            "fps": self.fps,
            "width": self.width,
            "height": self.height,
            "enabled": self.enabled,
            "features": self.features_json or dict(DEFAULT_CAMERA_FEATURES),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
