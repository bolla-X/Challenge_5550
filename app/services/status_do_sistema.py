"""Saúde do sistema para a página `/status` (`GET /api/status`, técnico ou acima).

Cada componente tem a sua SONDA: uma função sem argumentos que devolve um item
`{"estado", "resumo", ...}`. O coletor roda todas em paralelo, cada uma numa
thread daemon, e espera no máximo `prazo_s` no total. Sonda que lança ou que não
responde no prazo vira um item "falha" em português; nenhuma derruba a rota nem
a deixa pendurada (o monitor, o banco ou uma pasta lenta não podem congelar a
tela que existe para diagnosticar exatamente isso).

Estados (vocabulário único, a tela mapeia cada um para ponto + texto):

    ok         funcionando
    atencao    funciona, mas pede olho (pouco disco, sem chave, modelo sem aquecer)
    falha      não funciona
    desligado  desligado de propósito (integração opcional, LLM)

Segredos: nenhuma sonda lê chave ou URL com credencial. O LLM só diz se há
chave (`ProvedorGemini.configurado`), nunca qual; o webhook usa o `endpoint`
que o gerente já devolve sem query nem credenciais; mensagens de exceção não
vão para a resposta (só para o log).
"""

from __future__ import annotations

import logging
import os
import shutil
import threading
import time
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import Flask
from sqlalchemy import text as sql_text

from app.config import BASE_DIR
from app.extensions import db
from app.llm import ProvedorGemini, redigir_segredos

logger = logging.getLogger(__name__)

OK, ATENCAO, FALHA, DESLIGADO = "ok", "atencao", "falha", "desligado"

PRAZO_TOTAL_S = 2.5
# Quanto uma sonda de pasta anda antes de desistir e marcar a medida como parcial.
ORCAMENTO_DE_PASTA_S = 1.0
MAXIMO_DE_ARQUIVOS_POR_PASTA = 200_000
VALIDADE_DO_TAMANHO_DE_PASTA_S = 30.0
BANCO_LENTO_MS = 500.0
GIB = 1024**3
# Disco: abaixo disto a evidência nova pode deixar de ser gravada.
LIVRE_ATENCAO_BYTES, LIVRE_ATENCAO_FRACAO = 5 * GIB, 0.10
LIVRE_FALHA_BYTES, LIVRE_FALHA_FRACAO = 1 * GIB, 0.05

Sonda = Callable[[], dict[str, Any]]


def item(estado: str, resumo: str, **detalhes: Any) -> dict[str, Any]:
    return {"estado": estado, "resumo": resumo, **detalhes}


def _falha_da_sonda(motivo: str) -> dict[str, Any]:
    return item(FALHA, motivo)


def coletar(
    sondas: Mapping[str, Sonda],
    *,
    prazo_s: float = PRAZO_TOTAL_S,
    relogio: Callable[[], float] = time.monotonic,
) -> dict[str, dict[str, Any]]:
    """Roda todas as sondas em paralelo, com prazo total. Nunca lança."""
    resultados: dict[str, dict[str, Any]] = {}
    terminadas: dict[str, threading.Event] = {nome: threading.Event() for nome in sondas}

    def executar(nome: str, sonda: Sonda) -> None:
        try:
            resultados[nome] = sonda()
        except Exception:  # noqa: BLE001  (a sonda é o limite: erro dela é dado, não exceção)
            logger.warning("status_sonda_falhou", extra={"componente": nome}, exc_info=True)
            resultados[nome] = _falha_da_sonda("Falha ao consultar este componente.")
        finally:
            terminadas[nome].set()

    for nome, sonda in sondas.items():
        threading.Thread(target=executar, args=(nome, sonda), daemon=True, name=f"status-{nome}").start()

    limite = relogio() + prazo_s
    for nome, evento in terminadas.items():
        evento.wait(max(0.0, limite - relogio()))
        if not evento.is_set():
            logger.warning("status_sonda_sem_resposta", extra={"componente": nome, "prazo_s": prazo_s})
            resultados.setdefault(nome, _falha_da_sonda("Sem resposta no prazo. O componente pode estar travado."))
    # Cópia na ordem das sondas: uma thread atrasada não altera o que já foi lido.
    return {nome: dict(resultados[nome]) for nome in sondas if nome in resultados}


def _como_pasta(config: Mapping[str, Any], chave: str, padrao: str) -> Path:
    pasta = Path(str(config.get(chave) or padrao))
    return pasta if pasta.is_absolute() else Path(BASE_DIR) / pasta


def tamanho_da_pasta(
    pasta: Path,
    *,
    orcamento_s: float = ORCAMENTO_DE_PASTA_S,
    maximo_de_arquivos: int = MAXIMO_DE_ARQUIVOS_POR_PASTA,
    relogio: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Bytes e arquivos de uma pasta, sem seguir link e sem passar do orçamento de tempo."""
    if not pasta.is_dir():
        return {"existe": False, "bytes": 0, "arquivos": 0, "parcial": False}
    limite = relogio() + orcamento_s
    total = arquivos = 0
    parcial = False
    pendentes = [str(pasta)]
    while pendentes and not parcial:
        try:
            with os.scandir(pendentes.pop()) as entradas:
                for entrada in entradas:
                    if arquivos >= maximo_de_arquivos or relogio() > limite:
                        parcial = True
                        break
                    try:
                        if entrada.is_dir(follow_symlinks=False):
                            pendentes.append(entrada.path)
                        elif entrada.is_file(follow_symlinks=False):
                            total += entrada.stat(follow_symlinks=False).st_size
                            arquivos += 1
                    except OSError:
                        continue  # arquivo apagado no meio da leitura
        except OSError:
            continue
    return {"existe": True, "bytes": total, "arquivos": arquivos, "parcial": parcial}


class ServicoDeStatus:
    """Monta o retrato do sistema. Não guarda estado além do cache do tamanho das pastas."""

    def __init__(
        self,
        app: Flask,
        *,
        agora: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        relogio: Callable[[], float] = time.monotonic,
        uso_de_disco: Callable[[str], Any] = shutil.disk_usage,
        prazo_s: float = PRAZO_TOTAL_S,
    ) -> None:
        self._app = app
        self._agora = agora
        self._relogio = relogio
        self._uso_de_disco = uso_de_disco
        self._prazo_s = prazo_s
        self._tranca = threading.Lock()
        self._cache_de_pastas: dict[str, tuple[float, dict[str, Any]]] = {}

    # ------------------------------------------------------------- montagem --
    def montar(self) -> dict[str, Any]:
        sondas: dict[str, Sonda] = {
            "modelos": self._sonda_modelos,
            "cameras": self._sonda_cameras,
            "banco": self._sonda_banco,
            "opcua": lambda: self._sonda_integracao("opcua", "OPC UA", "OPCUA_ATIVO"),
            "mqtt": lambda: self._sonda_integracao("mqtt", "MQTT", "MQTT_ATIVO"),
            "broker": lambda: self._sonda_integracao("broker", "Broker MQTT embutido", "MQTT_BROKER_EMBUTIDO"),
            "webhook": lambda: self._sonda_integracao("webhook", "Webhook", "WEBHOOK_URL"),
            "llm": self._sonda_llm,
            "disco": self._sonda_disco,
        }
        # Cada sonda precisa do contexto do app: elas rodam em threads próprias.
        componentes = coletar(
            {nome: self._no_contexto(sonda) for nome, sonda in sondas.items()}, prazo_s=self._prazo_s, relogio=self._relogio
        )
        politicas = self._politicas(componentes.get("cameras"))
        return {
            "gerado_em": self._agora().isoformat(),
            "versao": self._versao(),
            "componentes": componentes,
            "politicas": politicas,
        }

    def _no_contexto(self, sonda: Sonda) -> Sonda:
        def dentro() -> dict[str, Any]:
            with self._app.app_context():
                try:
                    return sonda()
                finally:
                    db.session.remove()

        return dentro

    def _monitor(self) -> Any:
        monitor = self._app.extensions.get("monitor_service")
        if monitor is None:
            raise RuntimeError("monitor ausente")
        return monitor

    # --------------------------------------------------------------- sondas --
    def _sonda_modelos(self) -> dict[str, Any]:
        monitor = self._monitor()
        if not hasattr(monitor, "diagnostico_do_pipeline"):
            return item(DESLIGADO, "Este monitor não informa a saúde dos modelos.")
        diag = monitor.diagnostico_do_pipeline([])  # sem câmeras: só os modelos, o agendador e o controlador
        modelos = []
        for nome, dados in (diag.get("modelos") or {}).items():
            escolha = dados.get("escolha") or {}
            runtime = dados.get("runtime")
            aquecimento = dados.get("aquecimento_ms")
            modelos.append(
                {
                    "nome": nome,
                    "arquivo": Path(str(dados.get("caminho") or "")).name or None,
                    "runtime": runtime,
                    "runtime_pedido": escolha.get("pedido"),
                    "runtime_validado": escolha.get("ativo"),
                    "dispositivo": dados.get("dispositivo"),
                    "carga_ms": dados.get("carga_ms"),
                    "aquecimento_ms": aquecimento,
                    "aquecido": aquecimento is not None,
                }
            )
        adaptativo = diag.get("adaptativo") or {}
        if not modelos:
            return item(ATENCAO, "Nenhum modelo informado.", modelos=[])
        voltou_ao_pytorch = [m["nome"] for m in modelos if "fallback" in str(m["runtime_validado"] or "")]
        sem_aquecer = [m["nome"] for m in modelos if not m["aquecido"]]
        if voltou_ao_pytorch:
            resumo = "Um modelo voltou ao PyTorch porque o runtime escolhido falhou."
            estado = ATENCAO
        elif sem_aquecer:
            resumo = "Modelos ainda sem aquecimento: a primeira análise pode demorar."
            estado = ATENCAO
        else:
            resumo, estado = "Modelos carregados e aquecidos.", OK
        return item(
            estado,
            resumo,
            modelos=modelos,
            degradado=bool(adaptativo.get("degradado")),
            motivo_da_degradacao=adaptativo.get("motivo"),
            agendador=(diag.get("agendador") or {}).get("modo"),
        )

    def _sonda_cameras(self) -> dict[str, Any]:
        from app.models import Camera

        monitor = self._monitor()
        estados = monitor.status_all() if hasattr(monitor, "status_all") else {}
        cadastradas = Camera.query.order_by(Camera.id.asc()).all()
        cameras = []
        for camera in cadastradas:
            estado_da_camera = estados.get(camera.id) or {}
            cameras.append(self._situacao_da_camera(camera, estado_da_camera))
        if not cameras:
            return item(ATENCAO, "Nenhuma câmera cadastrada.", cameras=[])
        sem_sinal = [c for c in cameras if c["situacao"] == "sem_sinal"]
        com_aviso = [c for c in cameras if c["estado"] == ATENCAO]
        no_ar = [c for c in cameras if c["situacao"] in ("no_ar", "apresentacao")]
        resumo = f"{len(no_ar)} de {len(cameras)} no ar"
        if sem_sinal:
            return item(FALHA, f"{resumo}; {len(sem_sinal)} sem sinal.", cameras=cameras)
        if com_aviso:
            return item(ATENCAO, f"{resumo}; {len(com_aviso)} com aviso de imagem.", cameras=cameras)
        return item(OK, resumo + ".", cameras=cameras)

    @staticmethod
    def _situacao_da_camera(camera: Any, estado: Mapping[str, Any]) -> dict[str, Any]:
        video = estado.get("video") or {}
        saude = estado.get("saude_visual") or {"estado": "ok", "rotulo": "OK"}
        if not estado.get("running"):
            situacao, resumo = "parada", DESLIGADO
        elif video.get("state") in ("reconnecting", "unavailable"):
            situacao, resumo = "sem_sinal", FALHA
        elif estado.get("pausa"):
            situacao, resumo = "apresentacao", OK
        else:
            situacao, resumo = "no_ar", (OK if saude.get("estado", "ok") == "ok" else ATENCAO)
        diagnostico = estado.get("diagnostico") or {}
        return {
            "id": camera.id,
            "nome": camera.name,
            "situacao": situacao,
            "estado": resumo,
            "saude_visual": {"estado": saude.get("estado", "ok"), "rotulo": saude.get("rotulo", "OK")},
            "fps": diagnostico.get("fps") if situacao != "parada" else None,
            "privacidade_ativa": (estado.get("privacidade") or {}).get("ativa"),
            "tentativas_de_reconexao": video.get("reconnect_attempts") if situacao == "sem_sinal" else None,
        }

    def _sonda_banco(self) -> dict[str, Any]:
        inicio = self._relogio()
        db.session.execute(sql_text("SELECT 1")).scalar()
        ms = (self._relogio() - inicio) * 1000.0
        motor = db.engine
        detalhes: dict[str, Any] = {"motor": motor.dialect.name, "consulta_ms": round(ms, 1)}
        arquivo = motor.url.database if motor.dialect.name == "sqlite" else None
        if arquivo and arquivo != ":memory:" and Path(arquivo).is_file():
            detalhes["arquivo"] = Path(arquivo).name
            detalhes["bytes"] = Path(arquivo).stat().st_size
        if ms > BANCO_LENTO_MS:
            return item(ATENCAO, "O banco respondeu, mas devagar.", **detalhes)
        return item(OK, "Banco respondendo.", **detalhes)

    def _sonda_integracao(self, chave: str, nome: str, config_chave: str) -> dict[str, Any]:
        monitor = self._monitor()
        gerente = getattr(monitor, "integracao", None)
        if gerente is None:
            return item(DESLIGADO, f"{nome}: este monitor não tem integração industrial.", como_ligar=config_chave)
        situacao = (gerente.status() or {}).get(chave) or {}
        estado_bruto = situacao.get("estado")
        endpoint = situacao.get("endpoint")
        erro = redigir_segredos(str(situacao["erro"])) if situacao.get("erro") else None
        detalhes = {"endpoint": endpoint, "erro": erro, "como_ligar": config_chave}
        if "estatisticas" in situacao:
            detalhes["estatisticas"] = situacao["estatisticas"]
        if not situacao.get("ativo"):
            return item(DESLIGADO, f"{nome} desligado.", **detalhes)
        if estado_bruto == "no_ar":
            return item(OK, f"{nome} no ar.", **detalhes)
        return item(FALHA, f"{nome} não está no ar.", **detalhes)

    def _sonda_llm(self) -> dict[str, Any]:
        config = self._app.config
        ligado = bool(config.get("LLM_ENABLED", False))
        # Só o booleano sai daqui: a chave nunca é lida para dentro da resposta.
        tem_chave = ProvedorGemini().configurado
        detalhes = {
            "ligado": ligado,
            "tem_chave": tem_chave,
            "versao_do_prompt": str(config.get("LLM_PROMPT_VERSION", "")),
            "intervalo_minimo_s": config.get("LLM_DEBOUNCE_S"),
            "limite_de_espera_s": config.get("LLM_TIMEOUT_S"),
            "como_ligar": "LLM_ENABLED e GEMINI_API_KEY",
        }
        if not ligado:
            return item(DESLIGADO, "Segunda opinião desligada. O resto do sistema funciona normalmente.", **detalhes)
        if not tem_chave:
            return item(ATENCAO, "Ligada, mas sem chave configurada: a segunda opinião não roda.", **detalhes)
        return item(OK, "Segunda opinião ligada, com chave configurada.", **detalhes)

    def _sonda_disco(self) -> dict[str, Any]:
        config = self._app.config
        pastas = {
            "imagens": _como_pasta(config, "SNAPSHOT_DIR", "runtime/snapshots"),
            "clipes": _como_pasta(config, "REPLAY_DIR", "runtime/clips"),
            "trilhas": Path(str(config.get("TRILHAS_DIR") or Path(self._app.instance_path) / "trilhas")),
        }
        volumes = {
            "evidencias": pastas["imagens"],
            "instancia": Path(self._app.instance_path),
        }
        medidas = {nome: self._volume(pasta) for nome, pasta in volumes.items()}
        tamanhos = {nome: self._tamanho_com_cache(pasta) for nome, pasta in pastas.items()}
        piores = [m for m in medidas.values() if m.get("estado") != OK]
        if any(m["estado"] == FALHA for m in piores):
            estado, resumo = FALHA, "Pouquíssimo espaço livre: novas evidências podem não ser gravadas."
        elif piores:
            estado, resumo = ATENCAO, "Pouco espaço livre."
        else:
            estado, resumo = OK, "Espaço em disco suficiente."
        return item(estado, resumo, volumes=medidas, pastas=tamanhos)

    def _volume(self, pasta: Path) -> dict[str, Any]:
        # A pasta pode ainda não existir (nenhum alerta gravado): sobe até uma que exista.
        alvo = pasta
        while not alvo.exists() and alvo != alvo.parent:
            alvo = alvo.parent
        try:
            uso = self._uso_de_disco(str(alvo))
        except OSError:
            return {"estado": FALHA, "resumo": "Não foi possível medir o disco."}
        livre_fracao = uso.free / uso.total if uso.total else 0.0
        if uso.free < LIVRE_FALHA_BYTES or livre_fracao < LIVRE_FALHA_FRACAO:
            estado = FALHA
        elif uso.free < LIVRE_ATENCAO_BYTES or livre_fracao < LIVRE_ATENCAO_FRACAO:
            estado = ATENCAO
        else:
            estado = OK
        return {
            "estado": estado,
            "total_bytes": uso.total,
            "usado_bytes": uso.used,
            "livre_bytes": uso.free,
            "livre_fracao": round(livre_fracao, 4),
        }

    def _tamanho_com_cache(self, pasta: Path) -> dict[str, Any]:
        agora = self._relogio()
        chave = str(pasta)
        with self._tranca:
            guardado = self._cache_de_pastas.get(chave)
            if guardado and agora - guardado[0] < VALIDADE_DO_TAMANHO_DE_PASTA_S:
                return guardado[1]
        medida = tamanho_da_pasta(pasta, relogio=self._relogio)
        with self._tranca:
            self._cache_de_pastas[chave] = (agora, medida)
        return medida

    # ------------------------------------------------------------- políticas --
    def _politicas(self, cameras: Mapping[str, Any] | None) -> dict[str, Any]:
        """Privacidade e retenção reais, lidas do config e do estado dos workers.

        A retenção diz a verdade: o sistema NÃO expira evidência sozinho. O que
        existe é o recorte do replay, o teto rotativo das trilhas e o apagar
        manual de alertas resolvidos.
        """
        config = self._app.config
        privacidade = [
            {"id": c["id"], "nome": c["nome"], "ativa": c.get("privacidade_ativa")}
            for c in ((cameras or {}).get("cameras") or [])
        ]
        trilhas_mb = float(config.get("TRILHAS_MB_POR_ARQUIVO", 16) or 0)
        trilhas_arquivos = int(config.get("TRILHAS_ARQUIVOS", 4) or 0)
        return {
            "privacidade": {"padrao_ligada": bool(config.get("PRIVACIDADE_PADRAO", True)), "cameras": privacidade},
            "retencao": {
                "expira_sozinha": False,
                "imagem_de_evidencia": bool(config.get("SNAPSHOT_ENABLED", True)),
                "replay": bool(config.get("REPLAY_ATIVO", True)),
                "replay_antes_s": config.get("REPLAY_ANTES_S"),
                "replay_depois_s": config.get("REPLAY_DEPOIS_S"),
                "trilhas_teto_mb": trilhas_mb * trilhas_arquivos,
                "trilhas_mb_por_arquivo": trilhas_mb,
                "trilhas_arquivos": trilhas_arquivos,
                "cadeia_de_custodia": bool(config.get("CUSTODIA_ATIVA", True)),
                "limpa_ao_ligar_a_camera": bool(config.get("CLEANUP_ON_MONITOR_START", True)),
            },
        }

    def _versao(self) -> dict[str, Any]:
        """Data do build do painel (o `index.html` que o Vite emite). Sem git: nada de subprocesso."""
        index = Path(self._app.static_folder or "") / "dist" / "index.html"
        try:
            construido = datetime.fromtimestamp(index.stat().st_mtime, tz=timezone.utc).isoformat()
        except OSError:
            construido = None
        return {"construido_em": construido}
