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
import re
import time
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

ARQUIVO_APROVADOS = "models/export/aprovados.json"
# Forma dinâmica primeiro (mesmo letterbox do PyTorch); a estática só se ela
# mesma tiver sido aprovada — caso do yolov8n de pessoa (98,25 %).
SUFIXOS = {
    "onnx": ("onnx-dyn", "onnx"),
    "openvino": ("openvino-dyn", "openvino"),
    # iGPU Intel pelo OpenVINO: FP32 primeiro (100 % no guarda), FP16 se só ele
    # estiver aprovado. O nome da aprovação carrega dispositivo e precisão
    # (`scripts/concordancia.py`, candidato `openvino-dyn@gpu-fp32:640`).
    "openvino-gpu": ("openvino-dyn@gpu-fp32", "openvino-dyn@gpu-fp16"),
}


# Diretório de export com o nome do peso de origem: `vyra_ppe_640_dyn`,
# `yolov8n_640`, `yolo11n-pose_640_dyn` (scripts/concordancia.py).
_EXPORT_DO_PESO = re.compile(r"^(?P<peso>.+)_\d{3,4}(?:_dyn)?(?:_int8)?$")


def _export_de_outro_peso(caminho: Path, peso_pt: str) -> bool:
    """A aprovação é do tipo de modelo ("epi"), não do peso: com
    `PPE_MODEL_PATH` apontando para outro `.pt` (o peso da Sprint 4, por
    exemplo), o `auto` carregaria em silêncio o export aprovado do Vyra. Recusa
    quando o diretório do export diz de qual peso veio e não é este."""
    for parte in caminho.parts:
        achou = _EXPORT_DO_PESO.match(parte)
        if achou:
            return achou.group("peso") != Path(peso_pt).stem
    return False


def _aprovados(base_dir: Path, modelo: str) -> dict[str, Any]:
    caminho = base_dir / ARQUIVO_APROVADOS
    try:
        return (json.loads(caminho.read_text(encoding="utf-8")) or {}).get(modelo, {})
    except (OSError, ValueError):
        return {}


def resolver_caminho(base_dir: Path, *, modelo: str, peso_pt: str, imgsz: int, pedido: str, ordem: str) -> tuple[str, str]:
    """(caminho a carregar, motivo) para o runtime pedido."""
    escolha = resolver(base_dir, modelo=modelo, peso_pt=peso_pt, imgsz=imgsz, pedido=pedido, ordem=ordem)
    return escolha["caminho"], escolha["motivo"]


def gpu_disponivel() -> bool:
    """Se o OpenVINO enxerga uma GPU (`openvino.Core().available_devices`)."""
    try:
        import openvino as ov

        return any(d.startswith("GPU") for d in ov.Core().available_devices)
    except Exception:  # noqa: BLE001
        return False


def _dispositivo_da_aprovacao(chave: str) -> tuple[str | None, str | None]:
    """`openvino-dyn@gpu-fp32:640` → ("GPU", "fp32"); sem `@` → (None, None)."""
    _, _, sufixo = chave.split(":")[0].partition("@")
    if not sufixo:
        return None, None
    dispositivo, _, precisao = sufixo.partition("-")
    return dispositivo.upper(), (precisao or None)


def resolver(base_dir: Path, *, modelo: str, peso_pt: str, imgsz: int, pedido: str, ordem: str) -> dict[str, Any]:
    """{caminho, motivo, dispositivo, precisao} para o runtime pedido."""
    escolha = _resolver(base_dir, modelo=modelo, peso_pt=peso_pt, imgsz=imgsz, pedido=pedido, ordem=ordem)
    caminho, motivo, chave = escolha
    dispositivo, precisao = _dispositivo_da_aprovacao(chave) if chave else (None, None)
    return {"caminho": caminho, "motivo": motivo, "dispositivo": dispositivo, "precisao": precisao}


def _resolver(base_dir: Path, *, modelo: str, peso_pt: str, imgsz: int, pedido: str, ordem: str) -> tuple[str, str, str | None]:
    pedido = (pedido or "pytorch").strip().lower()
    if pedido == "pytorch":
        return peso_pt, "PyTorch (pedido)", None
    candidatos = [c.strip() for c in ordem.split(",") if c.strip()] if pedido == "auto" else [pedido]
    aprovados = _aprovados(base_dir, modelo)
    for runtime in candidatos:
        if runtime == "pytorch":
            return peso_pt, "PyTorch (primeiro da ordem)", None
        if runtime == "openvino-gpu" and not gpu_disponivel():
            # Sem iGPU, o OpenVINO cairia na CPU — mais lento que o ONNX ali
            # (CPU-ms por análise 3.373 vs 2.926, docs/NEXT2026/BENCHMARKS.md).
            continue
        chave = next((f"{v}:{imgsz}" for v in SUFIXOS.get(runtime, (runtime,)) if f"{v}:{imgsz}" in aprovados), None)
        if not chave:
            continue
        registro = aprovados[chave]
        caminho = Path(registro.get("caminho", ""))
        if _export_de_outro_peso(caminho, peso_pt):
            continue
        if not caminho.is_absolute():
            caminho = base_dir / caminho
        if caminho.exists():
            return str(caminho), f"{runtime} aprovado (concordância {registro.get('concordancia')})", chave
    return peso_pt, f"PyTorch (nenhum de {candidatos} aprovado para imgsz={imgsz})", None


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


def aquecer_modelos(detectores: list[Any], formas: tuple[tuple[int, int], ...] = ((540, 960),)) -> dict[str, float]:
    """Uma inferência em cada modelo no BOOT, antes de qualquer câmera ligar.

    Medido no bench (perfil batata, docs/NEXT2026/CHANGELOG.md): sem isto, a
    primeira análise depois de ligar a câmera levava ~30 s — carga preguiçosa
    do modelo de pose, criação do predictor do ultralytics e recriação da
    sessão ONNX — e esses 30 s entravam inteiros na latência do primeiro
    alerta. Pago na subida do servidor, onde ninguém está esperando alerta.
    Falha aqui não derruba o boot: o detector já trata erro no `detect`.
    `formas` (altura, largura): na iGPU cada forma de entrada compila o seu
    kernel na primeira vez; o `scripts/preparar.py` aquece as das câmeras da demo.
    """
    quadros = [np.zeros((h, w, 3), dtype=np.uint8) for h, w in formas]
    tempos: dict[str, float] = {}
    for detector in detectores:
        if detector is None:
            continue
        inicio = time.perf_counter()
        try:
            detectar = getattr(detector, "detect_lote", None)
            for quadro in quadros:
                detectar([quadro]) if detectar else detector.detect(quadro)
        except Exception as exc:  # noqa: BLE001
            logger.warning("aquecimento_falhou", extra={"modelo": getattr(detector, "model_path", "?"), "error": str(exc)})
            continue
        tempos[str(getattr(detector, "model_path", type(detector).__name__))] = round((time.perf_counter() - inicio) * 1000.0, 1)
    logger.info("modelos_aquecidos", extra={"tempos_ms": tempos})
    return tempos

