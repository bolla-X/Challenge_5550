"""Modo Evacuação (M3, MISSÃO 4): quem ainda está na planta e quantos já chegaram ao ponto de encontro.

O supervisor (ou o palco, pelo token) inicia; a partir daí cada observação das
câmeras acumula, em memória:

- a contagem atual por câmera e por zona e o total somado;
- a ÚLTIMA posição vista de cada track na planta (com o horário);
- o máximo de pessoas simultâneas vistas na câmera do ponto de encontro — é o
  que o sistema chama de "chegadas";
- uma série temporal amostrada a cada 5 s.

Ao encerrar, o relatório vira um JSON em disco, entra na cadeia de custódia
(elo "evacuacao": sha256 do arquivo) e a verificação o confere byte a byte.

Limites que vão no relatório do jeito que são:

- a contagem é POR CÂMERA: se duas câmeras enxergam a mesma pessoa, ela conta
  duas vezes (`AVISO_DUPLA_CONTAGEM` vem em TODO snapshot e relatório);
- track ID é rótulo de rastreio, nunca identidade: aqui não há nome, rosto nem
  foto, e o ID pode trocar quando a pessoa some e reaparece;
- "chegadas" é um MÁXIMO de pessoas simultâneas diante da câmera do ponto de
  encontro, não uma contagem de quem passou por ela.

O estado é do processo: reiniciar o servidor no meio da evacuação perde o que
foi acumulado (o relatório só existe depois de encerrar).
"""

from __future__ import annotations

import json
import logging
import math
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.custodia import _json_canonico, sha256_bytes

logger = logging.getLogger(__name__)

AVISO_DUPLA_CONTAGEM = "contagem por câmera — pode haver dupla contagem se as câmeras se sobrepõem"
AMOSTRA_SERIE_S = 5.0
# Análise mais velha que isto: a contagem daquela câmera é a de antes, não a de agora.
ANALISE_ATRASADA_S = 10.0
MAX_TRACKS_POR_CAMERA = 500
MAX_PONTOS_NO_RELATORIO = 120
PREFIXO_RELATORIO = "evacuacao_"


class EvacuacaoJaAtiva(RuntimeError):
    """Já existe uma evacuação em andamento."""


class EvacuacaoInativa(RuntimeError):
    """Não há evacuação em andamento."""


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _resumir_serie(serie: list[dict[str, Any]], maximo: int = MAX_PONTOS_NO_RELATORIO) -> list[dict[str, Any]]:
    """No máximo `maximo` pontos, sempre com o primeiro e o último (o pico fica em `maximo_por_camera`)."""
    if len(serie) <= maximo:
        return list(serie)
    passo = math.ceil(len(serie) / maximo)
    saida = serie[::passo]
    if saida[-1] is not serie[-1]:
        saida.append(serie[-1])
    return saida


class Evacuacao:
    """Estado da evacuação em memória. Thread-safe: o amostrador, as rotas e o palco chamam ao mesmo tempo."""

    def __init__(self, amostra_s: float = AMOSTRA_SERIE_S) -> None:
        self._lock = threading.RLock()
        self._amostra_s = float(amostra_s)
        self._sessao = 0
        self._zerar()

    def _zerar(self) -> None:
        self._ativa = False
        self._inicio = 0.0
        self._por = ""
        self._ponto: int | None = None
        self._ultimas: dict[int, dict[Any, dict[str, Any]]] = {}
        self._maximo_por_camera: dict[int, int] = {}
        self._nomes: dict[int, str] = {}
        self._chegadas = 0
        self._maximo_total = 0
        self._serie: list[dict[str, Any]] = []
        self._proxima_amostra = 0.0

    # ------------------------------------------------------------- estado
    @property
    def ativa(self) -> bool:
        with self._lock:
            return self._ativa

    @property
    def sessao(self) -> int:
        """Muda a cada `iniciar`: quem amostra em segundo plano sabe que a evacuação dele acabou."""
        with self._lock:
            return self._sessao

    @property
    def ponto_de_encontro_camera_id(self) -> int | None:
        with self._lock:
            return self._ponto

    def iniciar(self, por: str, ponto_de_encontro_camera_id: int | None, agora: float) -> dict[str, Any]:
        with self._lock:
            if self._ativa:
                raise EvacuacaoJaAtiva("já existe uma evacuação em andamento")
            self._zerar()
            self._ativa = True
            self._sessao += 1
            self._inicio = float(agora)
            self._por = por
            self._ponto = ponto_de_encontro_camera_id
            self._proxima_amostra = self._inicio  # a primeira observação já entra na série
            return {"ativa": True, "inicio": _iso(self._inicio), "iniciada_por": por,
                    "ponto_de_encontro_camera_id": self._ponto}

    # ------------------------------------------------------------- observar
    def observar(self, cameras_info: list[dict[str, Any]], agora: float) -> None:
        """Acumula máximos, últimas posições e a série. Sem efeito se não há evacuação."""
        with self._lock:
            if self._ativa:
                self._acumular(cameras_info, float(agora))

    def _acumular(self, cameras_info: list[dict[str, Any]], agora: float) -> None:
        total = 0
        por_camera: dict[str, int] = {}
        for cam in cameras_info:
            cid = cam["id"]
            self._nomes[cid] = str(cam.get("nome") or f"Câmera {cid}")
            online = bool(cam.get("online", True))
            pessoas = int(cam.get("pessoas") or 0) if online else 0
            total += pessoas
            por_camera[str(cid)] = pessoas
            self._maximo_por_camera[cid] = max(self._maximo_por_camera.get(cid, 0), pessoas)
            if cid == self._ponto:
                self._chegadas = max(self._chegadas, pessoas)
            # A posição é a da ANÁLISE: se a câmera parou de analisar, o horário velho é o que vale.
            visto = min(float(cam.get("ts_ultima_analise") or agora), agora)
            tracks = self._ultimas.setdefault(cid, {})
            for pe in (cam.get("pes_na_planta") or []) if online else []:
                track_id = pe.get("track_id")
                if track_id is None:
                    continue
                tracks[track_id] = {"x": pe.get("x"), "y": pe.get("y"), "visto_em": visto}
            if len(tracks) > MAX_TRACKS_POR_CAMERA:
                tracks.pop(min(tracks, key=lambda t: tracks[t]["visto_em"]))
        self._maximo_total = max(self._maximo_total, total)
        if agora >= self._proxima_amostra:
            self._serie.append({
                "t_s": round(agora - self._inicio, 1),
                "total": total,
                "por_camera": por_camera,
                "ponto_de_encontro": por_camera.get(str(self._ponto)) if self._ponto is not None else None,
            })
            self._proxima_amostra = agora + self._amostra_s

    # ------------------------------------------------------------- snapshot
    def snapshot(self, cameras_info: list[dict[str, Any]], agora: float) -> dict[str, Any]:
        with self._lock:
            if not self._ativa:
                return {"ativa": False, "aviso": AVISO_DUPLA_CONTAGEM}
            self._acumular(cameras_info, float(agora))
            visiveis = {
                (cam["id"], pe.get("track_id"))
                for cam in cameras_info if cam.get("online", True)
                for pe in cam.get("pes_na_planta") or []
            }
            cameras = []
            for cam in cameras_info:
                online = bool(cam.get("online", True))
                ts = cam.get("ts_ultima_analise")
                idade = round(max(0.0, agora - float(ts)), 1) if ts else None
                cameras.append({
                    "id": cam["id"],
                    "nome": self._nomes[cam["id"]],
                    "online": online,
                    "pessoas": int(cam.get("pessoas") or 0) if online else 0,
                    "zonas": dict(cam.get("zonas") or {}) if online else {},
                    "maximo": self._maximo_por_camera.get(cam["id"], 0),
                    "idade_analise_s": idade,
                    # Sem horário (laço síncrono) não dá para afirmar atraso: fica False.
                    "desatualizada": bool(online and idade is not None and idade > ANALISE_ATRASADA_S),
                })
            posicoes = [
                {"camera_id": cid, "track_id": tid, "x": p["x"], "y": p["y"], "visto_em": _iso(p["visto_em"]),
                 "ha_s": round(max(0.0, agora - p["visto_em"]), 1), "visivel_agora": (cid, tid) in visiveis}
                for cid, tracks in sorted(self._ultimas.items())
                for tid, p in sorted(tracks.items(), key=lambda item: str(item[0]))
            ]
            return {
                "ativa": True,
                "inicio": _iso(self._inicio),
                "iniciada_por": self._por,
                "segundos": round(max(0.0, agora - self._inicio), 1),
                "ponto_de_encontro_camera_id": self._ponto,
                "cameras": cameras,
                "total": sum(c["pessoas"] for c in cameras),
                "aviso": AVISO_DUPLA_CONTAGEM,
                "ultimas_posicoes": posicoes,
                "chegadas_ponto_de_encontro": self._chegadas if self._ponto is not None else None,
                "serie": list(self._serie),
            }

    # ------------------------------------------------------------- encerrar
    def encerrar(self, por: str, agora: float, cameras_info: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        """Fecha a evacuação e devolve o relatório (puro: gravar em disco é `arquivar_relatorio`).

        `cameras_info` é opcional: uma última observação antes de fechar, para o
        pico e a série não perderem o final.
        """
        with self._lock:
            if not self._ativa:
                raise EvacuacaoInativa("não há evacuação em andamento")
            if cameras_info is not None:
                self._acumular(cameras_info, float(agora))
            fim = float(agora)
            relatorio: dict[str, Any] = {
                "inicio": _iso(self._inicio),
                "fim": _iso(fim),
                "duracao_s": round(max(0.0, fim - self._inicio), 1),
                "iniciada_por": self._por,
                "encerrada_por": por,
                "ponto_de_encontro_camera_id": self._ponto,
                "maximo_por_camera": [
                    {"camera_id": cid, "nome": self._nomes.get(cid, f"Câmera {cid}"), "maximo": n}
                    for cid, n in sorted(self._maximo_por_camera.items())
                ],
                "total_maximo_somado": self._maximo_total,
                "chegadas_ponto_de_encontro": self._chegadas if self._ponto is not None else None,
                "serie_temporal": _resumir_serie(self._serie),
                "aviso": AVISO_DUPLA_CONTAGEM,
            }
            relatorio["sha256"] = sha256_do_relatorio(relatorio)
            self._ativa = False
            return relatorio


def sha256_do_relatorio(relatorio: dict[str, Any]) -> str:
    """sha256 do JSON canônico, sem o próprio `sha256` e sem `numero` (posição no arquivo, atribuída ao gravar)."""
    corpo = {k: v for k, v in relatorio.items() if k not in ("sha256", "numero")}
    return sha256_bytes(_json_canonico(corpo))


# ------------------------------------------------------------- relatórios em disco
def pasta_dos_relatorios(app) -> Path:
    return Path(str(app.config.get("EVACUACAO_DIR") or Path(app.instance_path) / "evacuacoes")).resolve()


def numero_do_arquivo(caminho: Path) -> int | None:
    nome = caminho.stem
    if caminho.suffix != ".json" or not nome.startswith(PREFIXO_RELATORIO):
        return None
    resto = nome[len(PREFIXO_RELATORIO):]
    return int(resto) if resto.isdigit() else None


def _numeros(pasta: Path) -> list[int]:
    if not pasta.is_dir():
        return []
    return sorted(n for n in (numero_do_arquivo(a) for a in pasta.iterdir()) if n is not None)


def gravar_relatorio(relatorio: dict[str, Any], pasta: Path) -> Path:
    """Grava `evacuacao_<n>.json` (n = próximo livre). Criação exclusiva: nunca sobrescreve um relatório."""
    pasta.mkdir(parents=True, exist_ok=True)
    while True:
        numeros = _numeros(pasta)
        numero = (numeros[-1] if numeros else 0) + 1
        caminho = pasta / f"{PREFIXO_RELATORIO}{numero}.json"
        # Legível (vai para a banca e para impressão); o sha256 do relatório é de outro JSON, o canônico.
        dados = json.dumps(relatorio | {"numero": numero}, sort_keys=True, ensure_ascii=False, indent=2).encode("utf-8")
        try:
            with caminho.open("xb") as arquivo:
                arquivo.write(dados)
        except FileExistsError:  # outro processo gravou no mesmo instante: tenta o próximo número
            continue
        return caminho


def arquivar_relatorio(relatorio: dict[str, Any], pasta: Path, *, custodia_ativa: bool = True) -> tuple[Path, bool]:
    """Grava o JSON e registra o elo "evacuacao". Devolve (arquivo, registrado na custódia?)."""
    caminho = gravar_relatorio(relatorio, pasta)
    if not custodia_ativa:
        return caminho, False
    from app.services.custodia import registrar_evacuacao

    return caminho, registrar_evacuacao(caminho) is not None


def resumo_do_relatorio(relatorio: dict[str, Any]) -> dict[str, Any]:
    chaves = ("numero", "inicio", "fim", "duracao_s", "iniciada_por", "encerrada_por", "ponto_de_encontro_camera_id",
              "total_maximo_somado", "chegadas_ponto_de_encontro", "sha256")
    return {k: relatorio.get(k) for k in chaves}


def ler_relatorio(pasta: Path, numero: int) -> dict[str, Any] | None:
    caminho = pasta / f"{PREFIXO_RELATORIO}{int(numero)}.json"
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def ultimo_resumo(pasta: Path) -> dict[str, Any] | None:
    """Resumo do relatório mais novo (lê só ele) — sobrevive a reinício do servidor, porque vem do disco."""
    numeros = _numeros(pasta)
    relatorio = ler_relatorio(pasta, numeros[-1]) if numeros else None
    return resumo_do_relatorio(relatorio | {"numero": numeros[-1]}) if relatorio is not None else None


def listar_relatorios(pasta: Path) -> list[dict[str, Any]]:
    """Resumos, do mais novo para o mais velho. Arquivo ilegível é pulado (e logado), não derruba a lista."""
    resumos = []
    for numero in reversed(_numeros(pasta)):
        relatorio = ler_relatorio(pasta, numero)
        if relatorio is None:
            logger.warning("evacuacao_relatorio_ilegivel", extra={"numero": numero})
            continue
        resumos.append(resumo_do_relatorio(relatorio | {"numero": numero}))
    return resumos


# ------------------------------------------------------------- câmeras -> cameras_info
def _zonas(worker: Any, pessoas: list[dict[str, Any]]) -> dict[str, int]:
    nome = getattr(worker, "risk_area_name", None)
    poligono = getattr(getattr(worker, "rule_engine", None), "risk_polygon", None)
    if not nome or not poligono:
        return {}
    return {str(nome): sum(1 for p in pessoas if (p.get("risk_area") or {}).get("status") == "inside")}


def coletar_cameras_info(monitor_service: Any) -> list[dict[str, Any]]:
    """Lê os workers SEM mexer no laço deles: só getters e atributos já publicados.

    Precisa de app context (uma consulta aos nomes das câmeras). Cada leitura é
    uma referência a um objeto que o worker substitui em vez de alterar
    (`latest_analysis()` e `pes_na_planta`), então não há trava nem cópia
    pesada. O que não existe no worker (dublê de teste, versão antiga) vira o
    padrão: câmera offline, zero pessoas.

    - `pessoas`: pessoas em `compliance.people` da última análise (câmera parada = 0);
    - `zonas`: `{nome da zona de risco: pessoas dentro}`, só se a câmera tem zona;
    - `pes_na_planta`: só `x`, `y` e `track_id` — sem estado de EPI nem nada de identidade;
    - `ts_ultima_analise`: epoch em segundos de `_ts_analise_ms` (atributo interno do
      worker; None no laço síncrono, que não o preenche).
    """
    from app.models import Camera

    trava = getattr(monitor_service, "_workers_lock", None)
    if trava is not None:
        with trava:
            workers = dict(getattr(monitor_service, "_workers", None) or {})
    else:
        workers = dict(getattr(monitor_service, "_workers", None) or {})
    nomes = {c.id: c.name for c in Camera.query.all()} if workers else {}
    info = []
    for camera_id, worker in sorted(workers.items()):
        rodando = getattr(worker, "_running", None)
        online = bool(rodando.is_set()) if rodando is not None else False
        analise = worker.latest_analysis() if online and hasattr(worker, "latest_analysis") else None
        pessoas = list(((analise or {}).get("compliance") or {}).get("people") or [])
        ts_ms = getattr(worker, "_ts_analise_ms", None)
        info.append({
            "id": camera_id,
            "nome": nomes.get(camera_id) or f"Câmera {camera_id}",
            "pessoas": len(pessoas) if online else 0,
            "zonas": _zonas(worker, pessoas) if online else {},
            "pes_na_planta": [
                {"x": pe.get("x"), "y": pe.get("y"), "track_id": pe.get("track_id")}
                for pe in list(getattr(worker, "pes_na_planta", None) or []) if online
            ],
            "ts_ultima_analise": (ts_ms / 1000.0) if ts_ms else None,
            "online": online,
        })
    return info
