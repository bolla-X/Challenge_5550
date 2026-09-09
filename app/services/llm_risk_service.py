"""Disparo assíncrono da análise multimodal, fora do caminho do frame.

Por que este arquivo existe separado de `app/llm/`: aquele pacote não conhece
Flask, thread nem câmera — só transforma bytes em `AnaliseRisco`. Este aqui
decide **quando** vale a pena gastar uma chamada, e garante que gastar essa
chamada nunca segure o loop de captura.

Três regras, cada uma vinda de um número medido:

1. **Nunca no caminho do frame.** O pipeline está em 19,56 fps com uma câmera
   (`docs/BENCH.md`). Uma chamada de rede de segundos dentro do loop
   congelaria o vídeo na frente de quem está assistindo.
2. **Uma em voo por câmera, e DESCARTE em vez de fila.** Depois do fix da
   Fase 1 a fixture de 7 s ainda gera 26 alertas. Enfileirar transformaria
   isso em 26 chamadas atrasadas — a fila cresce enquanto a violação persiste,
   e as respostas chegam descrevendo uma cena que já passou. Descartar mantém
   a análise sempre sobre o presente.
3. **Debounce por câmera.** A cota do free tier é finita e a tela do
   supervisor também.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

from app.llm import AnalisadorDeRisco, AnaliseRisco, ProvedorGemini

logger = logging.getLogger(__name__)


def _executor_em_thread(funcao: Callable[[], None]) -> None:
    """Executor padrão: uma thread daemon por chamada.

    Daemon de propósito — se a aplicação está encerrando, uma análise de risco
    pendente não é motivo para segurar o processo. E thread por chamada basta
    porque o teto é uma em voo por câmera: com o alvo de demo de 1 a 2 câmeras,
    nunca há mais de duas vivas.
    """
    threading.Thread(target=funcao, daemon=True).start()


class ServicoDeRiscoLLM:
    """Recebe eventos de alerta e decide se vale uma análise multimodal.

    `submeter()` volta imediatamente e devolve `True` (aceito) ou `False`
    (descartado). Nunca levanta: quem chama é o worker da câmera.
    """

    def __init__(
        self,
        analisador: AnalisadorDeRisco,
        *,
        executor: Callable[[Callable[[], None]], None] | None = None,
        relogio: Callable[[], float] = time.monotonic,
        debounce_s: float = 15.0,
        versao: str = "v1",
        habilitado: bool = True,
    ) -> None:
        self.analisador = analisador
        self.executor = executor or _executor_em_thread
        self.relogio = relogio
        self.debounce_s = float(debounce_s)
        self.versao = versao
        self.habilitado = bool(habilitado)

        # Quem consome o resultado. Fica como atributo (e não no construtor)
        # porque o consumidor é o worker, que nasce depois do serviço.
        self.ao_concluir: Callable[[AnaliseRisco], None] | None = None

        self._trava = threading.Lock()
        self._em_voo: set[int] = set()
        self._ultimo_disparo: dict[int, float] = {}

        self.aceitos = 0
        self.descartados_em_voo = 0
        self.descartados_debounce = 0
        self.invalidos = 0
        self.erros_de_callback = 0

    # ----------------------------------------------------------- leitura ---
    def em_voo(self, camera_id: int) -> bool:
        with self._trava:
            return camera_id in self._em_voo

    def estatisticas(self) -> dict[str, object]:
        with self._trava:
            return {
                "habilitado": self.habilitado,
                "versao_prompt": self.versao,
                "debounce_s": self.debounce_s,
                "aceitos": self.aceitos,
                "descartados_em_voo": self.descartados_em_voo,
                "descartados_debounce": self.descartados_debounce,
                "invalidos": self.invalidos,
                "erros_de_callback": self.erros_de_callback,
                "em_voo": sorted(self._em_voo),
            }

    # ----------------------------------------------------------- escrita ---
    def submeter(self, *, camera_id: int, imagem_jpeg: bytes) -> bool:
        """Aceita ou descarta. Retorna na hora — nada de rede aqui."""
        if not self.habilitado:
            return False

        with self._trava:
            if camera_id in self._em_voo:
                self.descartados_em_voo += 1
                logger.debug("llm_descartado", extra={"motivo": "em_voo", "camera_id": camera_id})
                return False

            agora = self.relogio()
            ultimo = self._ultimo_disparo.get(camera_id)
            if ultimo is not None and (agora - ultimo) < self.debounce_s:
                self.descartados_debounce += 1
                logger.debug("llm_descartado", extra={"motivo": "debounce", "camera_id": camera_id})
                return False

            self._em_voo.add(camera_id)
            self._ultimo_disparo[camera_id] = agora
            self.aceitos += 1

        self.executor(lambda: self._executar(camera_id, imagem_jpeg))
        return True

    def _executar(self, camera_id: int, imagem_jpeg: bytes) -> None:
        """Roda no executor. Libera o slot no `finally`, sempre."""
        try:
            analise = self.analisador.analisar(imagem_jpeg, versao=self.versao)
            if analise is None:
                # Falha, timeout ou schema inválido: evento ignorado com log.
                # Nunca vira alerta — resposta que não cabe no schema não pode
                # inventar violação de segurança.
                with self._trava:
                    self.invalidos += 1
                logger.info("llm_evento_ignorado", extra={"camera_id": camera_id})
                return

            consumidor = self.ao_concluir
            if consumidor is None:
                return
            try:
                consumidor(analise)
            except Exception:  # noqa: BLE001  (bug do consumidor nao derruba o worker)
                with self._trava:
                    self.erros_de_callback += 1
                logger.exception("llm_callback_falhou", extra={"camera_id": camera_id})
        finally:
            with self._trava:
                self._em_voo.discard(camera_id)

    # ----------------------------------------------------------- fabrica ---
    @classmethod
    def a_partir_da_config(cls, config) -> ServicoDeRiscoLLM:
        """Monta o serviço a partir da config do Flask.

        Sem `GEMINI_API_KEY` o serviço nasce **desligado** e nada acontece — é
        degradação explícita, não erro. A chave não é lida para variável local
        nem logada: quem decide é `ProvedorGemini.configurado`.
        """
        provedor = ProvedorGemini(timeout_s=float(config.get("LLM_TIMEOUT_S", 8.0)))
        pedido = bool(config.get("LLM_ENABLED", False))
        if pedido and not provedor.configurado:
            logger.warning("llm_sem_chave", extra={"hint": "defina GEMINI_API_KEY no .env"})
        return cls(
            analisador=AnalisadorDeRisco(provedor=provedor),
            debounce_s=float(config.get("LLM_DEBOUNCE_S", 15.0)),
            versao=str(config.get("LLM_PROMPT_VERSION", "v1")),
            habilitado=pedido and provedor.configurado,
        )
