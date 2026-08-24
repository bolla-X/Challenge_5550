from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Callable, Iterable

logger = logging.getLogger(__name__)


class StorageCleanupService:
    """Remove artefatos temporários de execuções anteriores.

    O objetivo é manter ciclos de teste limpos sem apagar banco de dados,
    modelos ou arquivos de configuração — nem EVIDÊNCIA ainda referenciada.
    """

    def __init__(
        self,
        base_dir: Path,
        directories: Iterable[str],
        enabled: bool = True,
        protected_files: Callable[[], set[str]] | None = None,
    ) -> None:
        self.base_dir = Path(base_dir).resolve()
        self.directories = [item.strip() for item in directories if item and item.strip()]
        self.enabled = enabled
        # Nomes de arquivo que NÃO podem ser apagados mesmo estando num
        # diretório de limpeza. Sem isso, todo start de monitoramento apagava
        # runtime/snapshots inteiro — inclusive os snapshots que alertas
        # antigos ainda apontam via `frame_ref`, deixando
        # GET /alerts/<id>/evidence com 404 permanente.
        self.protected_files = protected_files

    def cleanup_startup_artifacts(self) -> dict:
        if not self.enabled:
            return {"enabled": False, "removed_files": 0, "cleaned_directories": [], "preserved_files": 0}

        try:
            protected = self._protected_names()
        except Exception as exc:  # noqa: BLE001
            # Se não dá pra saber o que está protegido, NÃO apaga nada. Apagar
            # "na dúvida" destrói evidência de forma irreversível; pular a
            # limpeza só deixa lixo em disco.
            logger.warning("cleanup_skipped_protection_lookup_failed", extra={"error": str(exc)})
            return {"enabled": True, "removed_files": 0, "cleaned_directories": [], "preserved_files": 0, "skipped": True}

        removed_files = 0
        preserved_files = 0
        cleaned: list[str] = []
        for raw_directory in self.directories:
            target = (self.base_dir / raw_directory).resolve()
            if not self._is_safe_target(target):
                logger.warning("cleanup_skipped_unsafe_path", extra={"path": str(target)})
                continue

            target.mkdir(parents=True, exist_ok=True)
            for child in target.iterdir():
                if child.name in protected:
                    preserved_files += 1
                    continue
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

        result = {
            "enabled": True,
            "removed_files": removed_files,
            "cleaned_directories": cleaned,
            "preserved_files": preserved_files,
        }
        logger.info("startup_artifacts_cleaned", extra=result)
        return result

    def _protected_names(self) -> set[str]:
        return self.protected_files() if self.protected_files is not None else set()

    def _is_safe_target(self, target: Path) -> bool:
        try:
            target.relative_to(self.base_dir)
        except ValueError:
            return False
        blocked = {self.base_dir, self.base_dir / "app", self.base_dir / "models", self.base_dir / "tests"}
        return target not in {item.resolve() for item in blocked}
