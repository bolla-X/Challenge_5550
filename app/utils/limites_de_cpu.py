"""Teto de threads e afinidade de CPU para o processo inteiro.

Existe para o perfil "batata" do `scripts/bench.py` e para quem roda numa
máquina fraca de verdade: PyTorch, OpenCV e OpenMP criam, por padrão, um thread
por núcleo lógico cada um. Numa máquina de 2 núcleos isso é oversubscription —
três pools brigando pelos mesmos 2 núcleos — e a latência piora em vez de
melhorar.

`VISIONEPI_THREADS=N` limita torch/OpenCV a N threads. `VISIONEPI_CPUS=0,2`
prende o processo nesses núcleos lógicos (via psutil, que funciona no Windows,
onde não há `taskset`). `OMP_NUM_THREADS` precisa estar no ambiente ANTES de o
processo carregar a libgomp, por isso quem o define é quem lança o processo
(o bench), não esta função.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def aplicar_limites_de_cpu() -> dict[str, object]:
    aplicado: dict[str, object] = {}
    bruto = os.getenv("VISIONEPI_THREADS", "").strip()
    if bruto.isdigit() and int(bruto) > 0:
        n = int(bruto)
        try:
            import torch

            torch.set_num_threads(n)
            aplicado["torch_threads"] = n
        except Exception as exc:  # noqa: BLE001
            logger.warning("limite_torch_falhou", extra={"error": str(exc)})
        try:
            import cv2

            cv2.setNumThreads(n)
            aplicado["opencv_threads"] = n
        except Exception as exc:  # noqa: BLE001
            logger.warning("limite_opencv_falhou", extra={"error": str(exc)})

    cpus = [c.strip() for c in os.getenv("VISIONEPI_CPUS", "").split(",") if c.strip().isdigit()]
    if cpus:
        try:
            import psutil

            psutil.Process().cpu_affinity([int(c) for c in cpus])
            aplicado["afinidade"] = [int(c) for c in cpus]
        except Exception as exc:  # noqa: BLE001
            logger.warning("afinidade_falhou", extra={"error": str(exc)})
    if aplicado:
        logger.info("limites_de_cpu", extra=aplicado)
    return aplicado
