"""Primeiro acesso do supervisor (MISSÃO 4, Fase 3).

Dois tipos de verdade convivem aqui, e nunca se misturam:

- o que a pessoa MARCOU (`feito`, `pulado`, `pendente`), gravado em
  `EstadoDoOnboarding.passos`;
- o que o sistema DETECTA sozinho no banco e no disco (há câmera? há planta
  calibrada?), recalculado a cada leitura e nunca gravado.

O estado mostrado ao usuário é o que existe de verdade: se a detecção diz que o
passo está cumprido, ele aparece como `feito` mesmo sem marcação; marcar `feito`
um passo que a detecção não vê vale para a barra de progresso, mas o checklist
"pronto para operar" só mostra ✓ no que foi detectado.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Camera, EstadoDoOnboarding, User, utc_now
from app.utils.texto import pluralizar

logger = logging.getLogger(__name__)

# Ordem do assistente. `pronto` é o último: o checklist final, sem detecção própria.
PASSOS = ("camera", "referencia", "planta", "zonas", "epis", "usuarios", "pronto")
PASSO_FINAL = "pronto"
PASSOS_DO_CHECKLIST = tuple(p for p in PASSOS if p != PASSO_FINAL)

PENDENTE, FEITO, PULADO = "pendente", "feito", "pulado"
ESTADOS = frozenset({PENDENTE, FEITO, PULADO})

ID_UNICO = 1
TOLERANCIA_DO_POLIGONO = 1e-3


class PassoDesconhecido(ValueError):
    pass


class EstadoInvalido(ValueError):
    pass


@dataclass(frozen=True)
class Deteccao:
    feito: bool
    detalhe: str


# ------------------------------------------------------------------ detecção --
def caminho_da_referencia(config: Mapping[str, Any], instance_path: str, camera_id: int) -> Path:
    """Onde a saúde visual guarda a imagem de referência da câmera.

    Mesma regra de `CameraWorker._caminho_da_referencia` (o teste
    `test_caminho_da_referencia_e_o_do_worker` trava os dois juntos).
    """
    pasta = Path(config.get("SAUDE_VISUAL_DIR") or Path(instance_path) / "referencias")
    return pasta / f"camera_{camera_id}.png"


def _planta_calibrada(planta: Any) -> bool:
    if not isinstance(planta, dict):
        return False
    return all(isinstance(planta.get(k), list) and len(planta[k]) == 4 for k in ("pontos_camera", "pontos_planta"))


def _poligono(valor: Any) -> list[tuple[float, float]] | None:
    """[x, y] ou {x, y} -> lista de pares arredondados; formato estranho vira None."""
    try:
        pontos = []
        for p in valor:
            x, y = (p["x"], p["y"]) if isinstance(p, dict) else p
            pontos.append((round(float(x), 3), round(float(y), 3)))
        return pontos or None
    except (TypeError, ValueError, KeyError):
        return None


def _poligono_padrao(config: Mapping[str, Any]) -> list[tuple[float, float]] | None:
    """O `RISK_AREA_POLYGON` do ambiente ("x,y;x,y;..."), que vale para a câmera sem zona própria."""
    return _poligono([par.split(",") for par in str(config.get("RISK_AREA_POLYGON") or "").split(";") if par.strip()])


def _zona_propria(camera: Camera, padrao: list[tuple[float, float]] | None) -> bool:
    if camera.risk_polygon is None:
        return False
    desenhada = _poligono(camera.risk_polygon)
    if desenhada is None:
        return False
    if padrao is None or len(padrao) != len(desenhada):
        return True
    return any(
        abs(a[0] - b[0]) > TOLERANCIA_DO_POLIGONO or abs(a[1] - b[1]) > TOLERANCIA_DO_POLIGONO
        for a, b in zip(desenhada, padrao)
    )


def detectar(*, config: Mapping[str, Any], instance_path: str) -> dict[str, Deteccao]:
    """O que já existe, passo a passo. Só lê; nunca grava."""
    cameras = Camera.query.order_by(Camera.id.asc()).all()
    n = len(cameras)

    com_referencia = [c for c in cameras if caminho_da_referencia(config, instance_path, c.id).is_file()]
    com_planta = [c for c in cameras if _planta_calibrada(c.planta)]
    padrao = _poligono_padrao(config)
    com_zona = [c for c in cameras if _zona_propria(c, padrao)]
    com_portaria = [c for c in cameras if c.gate_required]
    contas = User.query.filter_by(active=True).count()
    outras = max(0, contas - 1)

    if not config.get("SAUDE_VISUAL_ATIVA", True):
        referencia = Deteccao(False, "A saúde visual está desligada neste ambiente.")
    elif com_referencia:
        referencia = Deteccao(True, f"{pluralizar(len(com_referencia), 'câmera')} com imagem de referência.")
    else:
        referencia = Deteccao(False, "Nenhuma câmera tem imagem de referência ainda.")

    return {
        "camera": Deteccao(n > 0, f"{pluralizar(n, 'câmera cadastrada', 'câmeras cadastradas')}." if n else "Nenhuma câmera cadastrada."),
        "referencia": referencia,
        "planta": Deteccao(
            bool(com_planta),
            f"{pluralizar(len(com_planta), 'câmera')} com a planta calibrada." if com_planta else "Nenhuma câmera com a planta calibrada.",
        ),
        "zonas": Deteccao(
            bool(com_zona),
            f"{pluralizar(len(com_zona), 'câmera')} com zona de risco própria."
            if com_zona
            else "Todas as câmeras usam a zona de risco padrão.",
        ),
        "epis": Deteccao(
            bool(com_portaria),
            f"{pluralizar(len(com_portaria), 'câmera')} com EPIs exigidos na portaria."
            if com_portaria
            else "Nenhuma câmera tem EPIs exigidos na portaria.",
        ),
        "usuarios": Deteccao(
            outras > 0,
            f"{pluralizar(outras, 'conta')} além da sua." if outras else "Só a sua conta existe.",
        ),
    }


# -------------------------------------------------------------------- leitura --
def _marcados(linha: EstadoDoOnboarding | None) -> dict[str, str]:
    marcados = {p: PENDENTE for p in PASSOS}
    for passo, estado in ((linha.passos if linha else None) or {}).items():
        if passo in marcados and estado in ESTADOS:
            marcados[passo] = estado
    return marcados


def _estado_real(marcado: str, deteccao: Deteccao | None) -> str:
    """Detectado vence a marcação: o que existe de verdade não aparece como pendente."""
    return FEITO if deteccao is not None and deteccao.feito else marcado


def montar_estado(*, config: Mapping[str, Any], instance_path: str) -> dict[str, Any]:
    linha = db.session.get(EstadoDoOnboarding, ID_UNICO)
    marcados = _marcados(linha)
    deteccoes = detectar(config=config, instance_path=instance_path)

    passos = []
    for passo in PASSOS:
        d = deteccoes.get(passo)
        passos.append(
            {
                "passo": passo,
                "estado": _estado_real(marcados[passo], d),
                "marcado": marcados[passo],
                "detectado": None if d is None else d.feito,
                "detalhe": None if d is None else d.detalhe,
            }
        )

    feitos = sum(1 for p in passos if p["estado"] == FEITO)
    pulados = sum(1 for p in passos if p["estado"] == PULADO)
    itens = [{"passo": p, "ok": deteccoes[p].feito, "detalhe": deteccoes[p].detalhe} for p in PASSOS_DO_CHECKLIST]
    pendentes = sum(1 for i in itens if not i["ok"])

    return {
        "passos": passos,
        "ordem": list(PASSOS),
        "proximo_passo": next((p["passo"] for p in passos if p["estado"] == PENDENTE), None),
        "progresso": {"total": len(PASSOS), "feitos": feitos, "pulados": pulados, "resolvidos": feitos + pulados},
        "checklist": {"itens": itens, "pendentes": pendentes, "pronto_para_operar": pendentes == 0},
        "concluido": bool(linha and linha.concluido_em),
        "concluido_em": linha.concluido_em.isoformat() if linha and linha.concluido_em else None,
        "atualizado_em": linha.atualizado_em.isoformat() if linha and linha.atualizado_em else None,
        "atualizado_por": linha.atualizado_por if linha else None,
    }


# ------------------------------------------------------------------- escrita --
def _gravar(alterar, *, por: str) -> None:
    """Cria a linha única na primeira escrita e aplica `alterar(linha)`.

    Duas primeiras escritas ao mesmo tempo colidem na chave `id = 1`: a segunda
    desfaz e repete, agora encontrando a linha da primeira.
    """
    for tentativa in (1, 2):
        linha = db.session.get(EstadoDoOnboarding, ID_UNICO)
        if linha is None:
            linha = EstadoDoOnboarding(id=ID_UNICO, passos={p: PENDENTE for p in PASSOS})
            db.session.add(linha)
        alterar(linha)
        linha.atualizado_por = por[:180]
        linha.atualizado_em = utc_now()
        try:
            db.session.commit()
            return
        except IntegrityError:
            db.session.rollback()
            if tentativa == 2:
                raise


def definir_estado(passo: str, estado: str, *, por: str) -> None:
    if passo not in PASSOS:
        raise PassoDesconhecido("Passo desconhecido.")
    if estado not in ESTADOS:
        raise EstadoInvalido('Estado inválido. Use "feito", "pulado" ou "pendente".')

    def alterar(linha: EstadoDoOnboarding) -> None:
        linha.passos = {**_marcados(linha), passo: estado}  # objeto novo: o JSON mutado no lugar não é detectado
        if passo == PASSO_FINAL:
            linha.concluido_em = utc_now() if estado == FEITO else None

    _gravar(alterar, por=por)
    logger.info("onboarding_passo", extra={"passo": passo, "estado": estado})


def concluir(*, por: str) -> None:
    definir_estado(PASSO_FINAL, FEITO, por=por)


def refazer(*, por: str) -> None:
    def alterar(linha: EstadoDoOnboarding) -> None:
        linha.passos = {p: PENDENTE for p in PASSOS}
        linha.concluido_em = None

    _gravar(alterar, por=por)
    logger.info("onboarding_refeito")


def marcar_tudo_concluido(*, por: str) -> None:
    """Modo demo: a banca não vê o assistente na primeira tela (o "refazer" continua disponível)."""

    def alterar(linha: EstadoDoOnboarding) -> None:
        linha.passos = {p: FEITO for p in PASSOS}
        linha.concluido_em = utc_now()

    _gravar(alterar, por=por)
