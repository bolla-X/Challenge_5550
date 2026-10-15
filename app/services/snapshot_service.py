from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from app.config import BASE_DIR
from app.models import Alert
from app.repositories.alert_repository import AlertRepository

logger = logging.getLogger(__name__)


class SnapshotService:
    def __init__(
        self,
        *,
        base_dir: Path | None = None,
        snapshot_dir: str = "runtime/snapshots",
        enabled: bool = True,
        jpeg_quality: int = 86,
        custodia: bool = True,
    ) -> None:
        self.base_dir = Path(base_dir or BASE_DIR)
        self.snapshot_dir = snapshot_dir.strip() or "runtime/snapshots"
        self.enabled = bool(enabled)
        self.jpeg_quality = max(40, min(100, int(jpeg_quality)))
        self.repository = AlertRepository()
        self.custodia = bool(custodia)

    @property
    def absolute_dir(self) -> Path:
        path = Path(self.snapshot_dir)
        return path if path.is_absolute() else self.base_dir / path

    def attach_to_alert(self, alert: Alert, frame: np.ndarray | None) -> Alert:
        if not self.enabled or frame is None:
            return alert
        try:
            self.absolute_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            safe_rule = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in alert.rule)[:60]
            filename = f"alert_{alert.id}_{safe_rule}_{timestamp}.jpg"
            filepath = self.absolute_dir / filename
            ok = cv2.imwrite(str(filepath), frame, [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality])
            if not ok:
                logger.warning("snapshot_write_failed", extra={"alert_id": alert.id, "path": str(filepath)})
                return alert
            alert = self.repository.update_frame_ref(alert, f"/snapshots/{filename}")
            if self.custodia:
                from app.services.custodia import registrar_snapshot

                registrar_snapshot(alert, filepath)
            return alert
        except Exception as exc:  # noqa: BLE001
            logger.warning("snapshot_attach_failed", extra={"alert_id": alert.id, "error": str(exc)})
            return alert

    def attach_to_alerts(self, alerts: list[Alert], frame: np.ndarray | None) -> list[Alert]:
        """Um quadro para vários alertas da mesma análise (mesmo instante): um arquivo, um commit, um elo."""
        if not alerts:
            return []
        if len(alerts) == 1:
            return [self.attach_to_alert(alerts[0], frame)]
        if not self.enabled or frame is None:
            return alerts
        try:
            self.absolute_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            filename = f"alert_{alerts[0].id}_lote{len(alerts)}_{timestamp}.jpg"
            filepath = self.absolute_dir / filename
            if not cv2.imwrite(str(filepath), frame, [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality]):
                logger.warning("snapshot_write_failed", extra={"alert_id": alerts[0].id, "path": str(filepath)})
                return alerts
            for alerta in alerts:
                alerta.frame_ref = f"/snapshots/{filename}"
                alerta.metadata_json = {**(alerta.metadata_json or {}), "snapshot_available": True}
            from app.extensions import db

            db.session.commit()
            if self.custodia:
                from app.services.custodia import registrar_snapshot

                registrar_snapshot(alerts[0], filepath, alert_ids=[a.id for a in alerts])
            return alerts
        except Exception as exc:  # noqa: BLE001
            logger.warning("snapshot_attach_failed", extra={"alert_id": alerts[0].id, "error": str(exc)})
            return alerts

    def info(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "directory": self.snapshot_dir,
            "absolute_directory": str(self.absolute_dir),
            "jpeg_quality": self.jpeg_quality,
        }
