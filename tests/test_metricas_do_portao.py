"""Métricas principais do portão: FPS de análise, idade da análise e a âncora
da latência de alerta (instante de captura do K-ésimo quadro).

São números que decidem merge (`docs/NEXT2026/MISSAO.md`, portão de cada PR),
então o que eles medem fica preso aqui em vez de só no bench.
"""

from __future__ import annotations

import threading
import time

import numpy as np
from app.services.pipeline_stats import QUADROS_INICIAIS, EstatisticasDoPipeline
from app.vision.captura_continua import CapturaContinua
from app.vision.schemas import FrameAnalysis


def test_ts_do_quadro_guarda_os_primeiros_quadros_e_limpa_no_restart():
    stats = EstatisticasDoPipeline()
    for i in range(QUADROS_INICIAIS + 10):
        stats.quadro_lido(1000.0 + i)

    assert stats.ts_do_quadro(0) == 1000.0
    assert stats.ts_do_quadro(QUADROS_INICIAIS - 1) == 1000.0 + QUADROS_INICIAIS - 1
    # Limitado: depois do teto não guarda mais (memória fixa por câmera).
    assert stats.ts_do_quadro(QUADROS_INICIAIS) is None
    assert stats.ts_do_quadro(-1) is None

    stats.limpar()
    assert stats.ts_do_quadro(0) is None


class FonteFalsa:
    """Fonte que não é arquivo (sem `source` str): a captura não cadencia."""

    def __init__(self, n: int) -> None:
        self.restantes = n
        self.lidos = threading.Event()

    def read(self):
        if self.restantes <= 0:
            self.lidos.set()
            time.sleep(0.01)
            return False, None
        self.restantes -= 1
        return True, np.zeros((4, 4, 3), dtype=np.uint8)


def test_captura_registra_o_instante_de_cada_quadro_lido_em_ordem():
    stats = EstatisticasDoPipeline()
    fonte = FonteFalsa(5)
    captura = CapturaContinua(lambda: fonte, stats=stats)
    antes = time.time() * 1000.0
    captura.iniciar()
    assert fonte.lidos.wait(2.0)
    captura.parar()
    depois = time.time() * 1000.0

    instantes = [stats.ts_do_quadro(i) for i in range(5)]
    assert all(t is not None for t in instantes)
    assert instantes == sorted(instantes)
    assert antes <= instantes[0] <= instantes[-1] <= depois
    assert stats.ts_do_quadro(5) is None


def test_idade_da_analise_mede_do_quadro_analisado_e_nao_do_quadro_de_video(real_monitor_app):
    from app.services.camera_worker import CameraWorker
    from app.services.feature_manager import FeatureManager

    monitor = real_monitor_app.extensions["monitor_service"]
    worker = CameraWorker(
        real_monitor_app,
        socketio=None,
        feature_manager=FeatureManager.from_config(real_monitor_app.config),
        camera_id=7,
        source="fonte-inexistente-nunca-aberta",
        fps=12,
        detector=monitor.detector,
        person_detector=monitor.person_detector,
        pose_estimator=monitor.pose_estimator,
        inference_lock=threading.Lock(),
    )
    capturado_ha_800ms = time.time() * 1000.0 - 800.0
    worker._receber_analise(FrameAnalysis(detections=[], pose=None, risk_events=[], poses=[]), capturado_ha_800ms)
    assert worker._ts_analise_ms == capturado_ha_800ms

    worker._registrar_analise_publicada(worker._ts_analise_ms)

    resumo = worker.stats.resumo(30)
    idade = resumo["etapas"]["idade_analise"]
    assert idade["n"] == 1
    assert 800.0 <= idade["p50"] < 2000.0
    assert resumo["totais"]["analises_publicadas"] == 1


def test_api_devolve_o_instante_do_quadro_pedido(real_monitor_app, real_monitor_client):
    from app.extensions import db
    from app.models import Camera

    camera = Camera(name="Fixture", source_type="Arquivo", source="fixture-inexistente.mp4")
    db.session.add(camera)
    db.session.commit()
    monitor = real_monitor_app.extensions["monitor_service"]
    monitor.load_cameras_from_db()
    monitor._get_worker(camera.id).stats.quadro_lido(123456.0)

    dados = real_monitor_client.get("/api/diagnostics/pipeline?quadro=0").get_json()
    assert dados["cameras"][str(camera.id)]["ts_quadro_ms"] == 123456.0
    sem_parametro = real_monitor_client.get("/api/diagnostics/pipeline").get_json()
    assert "ts_quadro_ms" not in sem_parametro["cameras"][str(camera.id)]


class FonteQuePula(FonteFalsa):
    def __init__(self, n: int) -> None:
        super().__init__(n)
        self.convertidos = 0
        self.pulados = 0

    def read(self):
        ok, frame = super().read()
        if ok:
            self.convertidos += 1
        return ok, frame

    def pular(self):
        if self.restantes <= 0:
            return False
        self.restantes -= 1
        self.pulados += 1
        time.sleep(0.002)
        return True


def test_captura_so_converte_na_taxa_util_e_conta_todos_os_quadros():
    """Acima da taxa útil a fonte só avança (grab): tempo real sem conversão inútil."""
    stats = EstatisticasDoPipeline()
    fonte = FonteQuePula(300)
    captura = CapturaContinua(lambda: fonte, stats=stats, taxa_util=lambda: 10.0)
    inicio = time.monotonic()
    captura.iniciar()
    assert fonte.lidos.wait(5.0)
    captura.parar()
    duracao = time.monotonic() - inicio

    assert fonte.pulados > fonte.convertidos, (fonte.pulados, fonte.convertidos)
    assert fonte.convertidos <= 10 * duracao + 3
    totais = stats.resumo(30)["totais"]
    assert totais["frames_lidos"] == 300, "pulado também é lido da fonte"
    assert totais["frames_pulados"] == fonte.pulados
    assert stats.ts_do_quadro(299) is not None, "o índice da âncora de latência não pode ter buraco"


def test_sem_taxa_util_converte_todos():
    stats = EstatisticasDoPipeline()
    fonte = FonteQuePula(20)
    captura = CapturaContinua(lambda: fonte, stats=stats)
    captura.iniciar()
    assert fonte.lidos.wait(3.0)
    captura.parar()
    assert (fonte.convertidos, fonte.pulados) == (20, 0)


class GravacaoFalsa(FonteQuePula):
    """Parece arquivo para a captura: `source` é caminho e há `fps_da_fonte`."""

    source = "gravacao.mp4"
    fps_da_fonte = 50.0


def test_gravacao_sem_espectador_desacelera_em_vez_de_decodificar_tudo():
    stats = EstatisticasDoPipeline()
    fonte = GravacaoFalsa(10_000)
    captura = CapturaContinua(lambda: fonte, stats=stats, taxa_util=lambda: 5.0, ritmo_de_gravacao=lambda: 5.0)
    captura.iniciar()
    time.sleep(1.0)
    captura.parar()
    assert fonte.pulados == 0, "gravação desacelera; não decodifica quadro para jogar fora"
    assert 3 <= fonte.convertidos <= 8, fonte.convertidos


def test_gravacao_com_espectador_segue_o_relogio():
    stats = EstatisticasDoPipeline()
    fonte = GravacaoFalsa(10_000)
    captura = CapturaContinua(lambda: fonte, stats=stats, ritmo_de_gravacao=lambda: None)
    captura.iniciar()
    time.sleep(1.0)
    captura.parar()
    assert fonte.convertidos >= 35, f"tempo real a 50 fps; leu {fonte.convertidos} em 1 s"
