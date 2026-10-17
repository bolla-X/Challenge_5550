"""Busca nas trilhas gravadas (M6): técnico ou acima. Só lê; nunca cria nem muda alerta.

`GET /api/busca/trilhas` filtra a trilha de UMA câmera (a mesma do simulador "E se?") e devolve
trechos contínuos de rótulos de rastreio ("Pessoa N", nunca identidade). Sem LLM: filtros
determinísticos em `app/services/busca_trilhas.py`.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Iterator

from flask import Blueprint, jsonify, request

from app.api.alerts import _pasta_do_clipe
from app.api.simulador import _worker
from app.extensions import db
from app.models import ROLE_TECHNICAL, Alert, Camera, Incidente
from app.services.busca_trilhas import MAX_PONTOS, AlertaDaBusca, Filtros, associar_clipes, buscar
from app.services.trilhas import numero
from app.utils.auth import require_role
from app.vision.person_compliance_matcher import PPE_KEYS
from app.vision.planta import homografia, poligono_na_planta, projetar

busca_bp = Blueprint("busca", __name__)

LIMITE_PADRAO = 50
LIMITE_MAXIMO = 200
PERMANENCIA_MAXIMA_S = 86400.0
MARGEM_DO_CLIPE_S = 10.0
_VERDADEIRO = {"1", "true", "sim", "on", "yes"}
_FALSO = {"", "0", "false", "nao", "não", "off", "no"}


class _ParametroInvalido(ValueError):
    def __init__(self, campo: str, mensagem: str) -> None:
        super().__init__(mensagem)
        self.campo = campo


def _numero(campo: str, rotulo: str, *, minimo: float = 0.0, maximo: float | None = None) -> float | None:
    bruto = (request.args.get(campo) or "").strip()
    if not bruto:
        return None
    try:
        valor = float(bruto.replace(",", "."))
    except ValueError:
        valor = math.nan
    if not math.isfinite(valor) or valor < minimo or (maximo is not None and valor > maximo):
        faixa = f"entre {minimo:g} e {maximo:g}" if maximo is not None else f"de {minimo:g} ou mais"
        raise _ParametroInvalido(campo, f"Informe {rotulo} como um número {faixa}.")
    return valor


def _instante(campo: str, rotulo: str) -> float | None:
    """ISO 8601 (sem fuso = UTC) ou segundos desde 1970."""
    bruto = (request.args.get(campo) or "").strip()
    if not bruto:
        return None
    try:
        return float(bruto)
    except ValueError:
        pass
    try:
        quando = datetime.fromisoformat(bruto)
    except ValueError as erro:
        raise _ParametroInvalido(campo, f"Informe {rotulo} como data e hora, por exemplo 2026-10-17T08:00:00-03:00.") from erro
    if quando.tzinfo is None:
        quando = quando.replace(tzinfo=timezone.utc)
    return quando.timestamp()


def _booleano(campo: str, rotulo: str) -> bool:
    bruto = (request.args.get(campo) or "").strip().lower()
    if bruto in _VERDADEIRO:
        return True
    if bruto in _FALSO:
        return False
    raise _ParametroInvalido(campo, f"Informe {rotulo} como 1 (ligado) ou 0 (desligado).")


def _epis_ausentes() -> frozenset[str]:
    chaves = [c.strip() for c in (request.args.get("epi_ausente") or "").split(",") if c.strip()]
    desconhecidas = [c for c in chaves if c not in PPE_KEYS]
    if desconhecidas:
        raise _ParametroInvalido("epi_ausente", f"EPI desconhecido: {', '.join(desconhecidas)}. Valores aceitos: {', '.join(PPE_KEYS)}.")
    return frozenset(chaves)


def _erro(campo: str, mensagem: str):
    return jsonify({"error": mensagem, "code": "busca_invalida", "campo": campo}), 400


def _filtros(poligono: list[tuple[float, float]]) -> tuple[Filtros, int]:
    de, ate = _instante("de", "o horário inicial"), _instante("ate", "o horário final")
    if de is not None and ate is not None and de >= ate:
        raise _ParametroInvalido("ate", "O horário final precisa ser depois do inicial.")
    vel_min = _numero("vel_min", "a velocidade mínima")
    vel_max = _numero("vel_max", "a velocidade máxima")
    if vel_min is not None and vel_max is not None and vel_min > vel_max:
        raise _ParametroInvalido("vel_max", "A velocidade máxima precisa ser maior ou igual à mínima.")
    limite = _numero("limite", "o limite de resultados", minimo=1, maximo=LIMITE_MAXIMO)
    zona = None
    if _booleano("zona", "o filtro de zona"):
        if len(poligono) < 3:
            raise _ParametroInvalido("zona", "Esta câmera não tem área de risco desenhada. Desenhe a zona ou desligue o filtro de zona.")
        zona = tuple((float(x), float(y)) for x, y in poligono)
    filtros = Filtros(
        de=de,
        ate=ate,
        zona=zona,
        permanencia_min_s=_numero("permanencia_min_s", "a permanência mínima, em segundos,", maximo=PERMANENCIA_MAXIMA_S) or 0.0,
        epi_ausente=_epis_ausentes(),
        vel_min=vel_min,
        vel_max=vel_max,
    )
    return filtros, int(limite or LIMITE_PADRAO)


def _lidos(registros: Iterator[dict[str, Any]], contagem: list[int]) -> Iterator[dict[str, Any]]:
    for registro in registros:
        contagem[0] += 1
        yield registro


def _epoch(quando: datetime) -> float:
    return (quando if quando.tzinfo else quando.replace(tzinfo=timezone.utc)).timestamp()


def _alertas_do_periodo(camera_id: int, resultados: list[dict[str, Any]]) -> list[AlertaDaBusca]:
    inicio = min(r["inicio"] for r in resultados) - MARGEM_DO_CLIPE_S
    fim = max(r["fim"] for r in resultados) + MARGEM_DO_CLIPE_S
    de, ate = datetime.fromtimestamp(inicio, tz=timezone.utc), datetime.fromtimestamp(fim, tz=timezone.utc)
    alertas = Alert.query.filter(Alert.camera_id == camera_id, Alert.created_at >= de, Alert.created_at <= ate).all()
    if not alertas:
        return []
    incidente_do_alerta: dict[int, int] = {}
    for inc in Incidente.query.filter(Incidente.camera_id == camera_id, Incidente.aberto_em <= ate).all():
        if inc.fechado_em is not None and _epoch(inc.fechado_em) < inicio:
            continue
        for alerta_id in inc.alert_ids or []:
            incidente_do_alerta.setdefault(int(alerta_id), inc.id)
    return [
        AlertaDaBusca(
            id=a.id,
            t=_epoch(a.created_at),
            rastreio=numero((a.metadata_json or {}).get("person_id")),
            incidente_id=incidente_do_alerta.get(a.id),
        )
        for a in alertas
    ]


def _tem_clipe(alerta_id: int) -> bool:
    return (_pasta_do_clipe(alerta_id) / "clip.json").exists()


def _na_planta(planta: dict[str, Any] | None, resultados: list[dict[str, Any]]) -> tuple[bool, list[dict[str, Any]]]:
    """Projeta os pontos dos trechos na planta. Sem calibração válida, devolve os trechos como estão."""
    if not planta:
        return False, resultados
    try:
        matriz = homografia(planta["pontos_camera"], planta["pontos_planta"])
        projetados = []
        for r in resultados:
            na_planta = projetar(matriz, [(x, y) for x, y, _ in r["pontos"]])
            pares = zip(na_planta, r["pontos"], strict=True)
            projetados.append(r | {"pontos_planta": [[round(x, 4), round(y, 4), ponto[2]] for (x, y), ponto in pares]})
        return True, projetados
    except (KeyError, TypeError, ValueError):
        return False, resultados


@busca_bp.get("/api/busca/trilhas")
@require_role(ROLE_TECHNICAL)
def buscar_trilhas():
    """Busca nas trilhas de uma câmera por zona, horário, permanência, EPI ausente e velocidade."""
    camera_id = request.args.get("camera_id", type=int)
    if camera_id is None:
        return _erro("camera_id", "Escolha a câmera da busca.")
    camera = db.session.get(Camera, camera_id)
    if camera is None:
        return jsonify({"error": "câmera não encontrada"}), 404
    worker = _worker(camera_id)
    if worker is None or worker.trilhas is None:
        return jsonify({"error": "câmera sem trilha gravada (ligue a câmera e espere algumas análises)"}), 409
    poligono = [tuple(p) for p in (worker.rule_engine.risk_polygon or [])]
    try:
        filtros, limite = _filtros(poligono)
    except _ParametroInvalido as erro:
        return _erro(erro.campo, str(erro))

    lidos = [0]
    todos = buscar(_lidos(worker.trilhas.ler(desde=filtros.de, ate=filtros.ate), lidos), filtros, camera_id=camera_id)
    itens = todos[:limite]
    if itens:
        itens = associar_clipes(itens, _alertas_do_periodo(camera_id, itens), _tem_clipe, margem_s=MARGEM_DO_CLIPE_S)
    planta_calibrada, itens = _na_planta(camera.planta, itens)
    zona_planta: list[list[float]] = []
    if planta_calibrada and len(poligono) >= 3:
        try:
            zona_planta = [list(p) for p in poligono_na_planta(poligono, camera.planta)]
        except (KeyError, TypeError, ValueError):
            zona_planta = []
    return jsonify({
        "camera": {
            "id": camera_id,
            "nome": camera.name,
            "planta_calibrada": planta_calibrada,
            "zona": [[round(x, 4), round(y, 4)] for x, y in poligono],
            "zona_planta": zona_planta,
        },
        "filtros": {
            "de": filtros.de,
            "ate": filtros.ate,
            "zona": filtros.zona is not None,
            "permanencia_min_s": filtros.permanencia_min_s,
            "epi_ausente": sorted(filtros.epi_ausente),
            "vel_min": filtros.vel_min,
            "vel_max": filtros.vel_max,
        },
        "registros_lidos": lidos[0],
        "total": len(todos),
        "limite": limite,
        "max_pontos": MAX_PONTOS,
        "items": itens,
    })
