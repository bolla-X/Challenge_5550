from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)


class StorageCleanupService:
    """Remove artefatos temporários de execuções anteriores.

    O objetivo é manter ciclos de teste limpos sem apagar banco de dados,
    modelos ou arquivos de configuração.
    """

    def __init__(self, base_dir: Path, directories: Iterable[str], enabled: bool = True) -> None:
        self.base_dir = Path(base_dir).resolve()
        self.directories = [item.strip() for item in directories if item and item.strip()]
        self.enabled = enabled

    def cleanup_startup_artifacts(self) -> dict:
        if not self.enabled:
            return {"enabled": False, "removed_files": 0, "cleaned_directories": []}

        removed_files = 0
        cleaned: list[str] = []
        for raw_directory in self.directories:
            target = (self.base_dir / raw_directory).resolve()
            if not self._is_safe_target(target):
                logger.warning("cleanup_skipped_unsafe_path", extra={"path": str(target)})
                continue

            target.mkdir(parents=True, exist_ok=True)
            for child in target.iterdir():
                try:
                    if child.is_dir():
                        count = sum(1 for item in child.rglob("*") if item.is_file())
                        shutil.rmtree(child)
                        removed_files += count
                    else:
                        child.unlink()
                        removed_files += 1
                except OSError as exc:
                    logger.warning("cleanup_delete_failed", extra={"path": str(child), "error": str(exc)})
            cleaned.append(str(target.relative_to(self.base_dir)))

        result = {"enabled": True, "removed_files": removed_files, "cleaned_directories": cleaned}
        logger.info("startup_artifacts_cleaned", extra=result)
        return result

    def _is_safe_target(self, target: Path) -> bool:
        try:
            target.relative_to(self.base_dir)
        except ValueError:
            return False
        blocked = {self.base_dir, self.base_dir / "app", self.base_dir / "models", self.base_dir / "tests"}
        return target not in {item.resolve() for item in blocked}
