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
    def __init__(self, *, base_dir: Path | None = None, snapshot_dir: str = "runtime/snapshots", enabled: bool = True, jpeg_quality: int = 86) -> None:
        self.base_dir = Path(base_dir or BASE_DIR)
        self.snapshot_dir = snapshot_dir.strip() or "runtime/snapshots"
        self.enabled = bool(enabled)
        self.jpeg_quality = max(40, min(100, int(jpeg_quality)))
        self.repository = AlertRepository()

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
            return self.repository.update_frame_ref(alert, f"/snapshots/{filename}")
        except Exception as exc:  # noqa: BLE001
            logger.warning("snapshot_attach_failed", extra={"alert_id": alert.id, "error": str(exc)})
            return alert

    def info(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "directory": self.snapshot_dir,
            "absolute_directory": str(self.absolute_dir),
            "jpeg_quality": self.jpeg_quality,
        }
