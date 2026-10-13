"""Escolha do runtime do modelo no startup, com fallback garantido para PyTorch.

Só entra um runtime alternativo que tenha PASSADO no guarda de qualidade
(`scripts/concordancia.py`, que grava `models/export/aprovados.json`):
concordância ≥ 97 % com a referência PyTorch@640 para troca de runtime.

`PPE_RUNTIME` / `PERSON_RUNTIME`:
- `pytorch` — o `.pt` de sempre;
- `onnx` / `openvino` — o export aprovado, se existir; senão PyTorch (com aviso);
- `auto` — o primeiro aprovado na ordem `RUNTIME_ORDEM` (a ordem é decidida
  pelo bench com o servidor real, não por bancada — ver CHANGELOG).

Depois de escolhido, `garantir_runtime` carrega o modelo e roda UMA inferência
num quadro preto. Se o runtime alternativo falhar ali (DLL ausente, versão
incompatível), o detector volta ao `.pt` antes de a primeira câmera subir — em
vez de a câmera rodar sem detecção nenhuma e a falha aparecer só no log.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

ARQUIVO_APROVADOS = "models/export/aprovados.json"
SUFIXOS = {"onnx": "onnx-dyn", "openvino": "openvino-dyn"}


def _aprovados(base_dir: Path, modelo: str) -> dict[str, Any]:
    caminho = base_dir / ARQUIVO_APROVADOS
    try:
        return (json.loads(caminho.read_text(encoding="utf-8")) or {}).get(modelo, {})
    except (OSError, ValueError):
        return {}


def resolver_caminho(base_dir: Path, *, modelo: str, peso_pt: str, imgsz: int, pedido: str, ordem: str) -> tuple[str, str]:
    """(caminho a carregar, motivo) para o runtime pedido."""
    pedido = (pedido or "pytorch").strip().lower()
    if pedido == "pytorch":
        return peso_pt, "PyTorch (pedido)"
    candidatos = [c.strip() for c in ordem.split(",") if c.strip()] if pedido == "auto" else [pedido]
    aprovados = _aprovados(base_dir, modelo)
    for runtime in candidatos:
        if runtime == "pytorch":
            return peso_pt, "PyTorch (primeiro da ordem)"
        chave = f"{SUFIXOS.get(runtime, runtime)}:{imgsz}"
        registro = aprovados.get(chave)
        if not registro:
            continue
        caminho = Path(registro.get("caminho", ""))
        if not caminho.is_absolute():
            caminho = base_dir / caminho
        if caminho.exists():
            return str(caminho), f"{runtime} aprovado (concordância {registro.get('concordancia')})"
    return peso_pt, f"PyTorch (nenhum de {candidatos} aprovado para imgsz={imgsz})"


def garantir_runtime(detector: Any, peso_pt: str) -> str:
    """Carrega e testa o detector; volta ao `.pt` se o runtime alternativo falhar."""
    if str(detector.model_path) == str(peso_pt):
        return "pytorch"
    try:
        detector.detect_lote([np.zeros((540, 960, 3), dtype=np.uint8)])
        erro = (detector.diagnostics() or {}).get("error")
        if erro:
            raise RuntimeError(erro)
        return detector.runtime
    except Exception as exc:  # noqa: BLE001
        logger.warning("runtime_alternativo_falhou_voltando_ao_pytorch",
                       extra={"model_path": detector.model_path, "error": str(exc)})
        detector.model_path = peso_pt
        detector.__dict__.pop("model", None)  # cached_property: recarrega do .pt
        detector._last_diagnostics = None
        detector._sessao_onnx_ajustada = False
        return "pytorch (fallback)"
