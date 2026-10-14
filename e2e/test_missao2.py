"""Fluxos ponta a ponta da MISSÃO 2 (X1–X10). Mesmo servidor e câmeras do e2e/conftest.py."""

from __future__ import annotations

import re
import time

from conftest import entrar

CALIBRACAO = {"pontos_camera": [[0.05, 0.55], [0.95, 0.55], [0.98, 0.98], [0.02, 0.98]],
              "pontos_planta": [[0.42, 0.08], [0.95, 0.08], [0.95, 0.62], [0.42, 0.62]]}
ZONA = [{"x": 0.6, "y": 0.5}, {"x": 1.0, "y": 0.5}, {"x": 1.0, "y": 1.0}, {"x": 0.6, "y": 1.0}]


def _logado(navegador, servidor, papel="technical", viewport=(1920, 1080)):
    contexto = navegador.new_context(viewport={"width": viewport[0], "height": viewport[1]})
    pagina = contexto.new_page()
    pagina.erros_console = []
    pagina.on("console", lambda m: pagina.erros_console.append(m.text) if m.type == "error" else None)
    entrar(pagina, servidor, papel)
    pagina.get_by_role("button", name=re.compile("Configurar|Câmeras")).first.wait_for(timeout=60_000)
    return contexto, pagina


class _Calibrada:
    """Multidão calibrada na planta e com zona durante o teste; volta como estava no fim."""

    def __init__(self, servidor):
        self.servidor = servidor
        self.tecnico = servidor.sessao("technical")
        self.cid = servidor.cameras["Multidão"]

    def __enter__(self):
        base = self.servidor.base
        self.zona_antes = self.tecnico.get(f"{base}/api/cameras/{self.cid}/risk-area", timeout=10).json()
        self.tecnico.put(f"{base}/api/cameras/{self.cid}/planta", json=CALIBRACAO, timeout=10).raise_for_status()
        self.tecnico.put(f"{base}/api/cameras/{self.cid}/risk-area", json={"polygon": ZONA, "name": "Doca"}, timeout=10)
        return self

    def __exit__(self, *exc):
        base = self.servidor.base
        self.tecnico.put(f"{base}/api/cameras/{self.cid}/planta", json={"pontos_camera": None}, timeout=10)
        poligono = (self.zona_antes.get("risk_area") or self.zona_antes).get("polygon") or []
        self.tecnico.put(f"{base}/api/cameras/{self.cid}/risk-area", json={"polygon": poligono}, timeout=10)


def test_gemeo_3d_mostra_pessoas_e_desenha_a_30_fps(navegador_gpu, servidor):
    """X1: WebGL de verdade (GPU), pessoas da homografia, tempo de quadro p95 ≤ 33 ms com as 4 câmeras ligadas."""
    with _Calibrada(servidor):
        contexto, pagina = _logado(navegador_gpu, servidor)
        try:
            pagina.goto(f"{servidor.base}/gemeo")
            viewport = pagina.locator("[data-testid=gemeo-viewport]")
            viewport.wait_for(timeout=60_000)
            assert viewport.get_attribute("data-modo") == "3d"
            pagina.wait_for_function(
                "Number(document.querySelector('[data-testid=gemeo-viewport]').dataset.pessoas) >= 1", timeout=180_000
            )
            pagina.wait_for_function(
                "Number(document.querySelector('[data-testid=gemeo-viewport]').dataset.quadros) >= 240", timeout=60_000
            )
            time.sleep(2)
            intervalo = float(viewport.get_attribute("data-intervalo-p95") or 999)
            desenho = float(viewport.get_attribute("data-desenho-p95") or 999)
            print(f"\n[gemeo] intervalo p95 {intervalo} ms, desenho p95 {desenho} ms, escala {viewport.get_attribute('data-escala')}")
            assert intervalo <= 33.4, f"quadro p95 {intervalo} ms (> 33 ms)"

            # Clique numa pessoa (pela lista acessível): linha do tempo do ID.
            pagina.locator("[data-testid=gemeo-pessoa]").first.click()
            detalhe = pagina.locator("[data-testid=gemeo-detalhe-pessoa]")
            detalhe.wait_for(timeout=10_000)
            assert "ID de rastreio" in detalhe.inner_text()

            # Aba oculta: o laço de desenho para.
            pagina.evaluate("""() => {
                Object.defineProperty(document, 'hidden', {configurable: true, get: () => true});
                document.dispatchEvent(new Event('visibilitychange'));
            }""")
            pagina.wait_for_function(
                "document.querySelector('[data-testid=gemeo-viewport]').dataset.pausado === '1'", timeout=5_000
            )
            antes = int(viewport.get_attribute("data-quadros") or 0)
            time.sleep(1.5)
            assert int(viewport.get_attribute("data-quadros") or 0) == antes, "desenhou com a aba oculta"
            assert not pagina.erros_console, pagina.erros_console
        finally:
            contexto.close()


def test_gemeo_cai_para_2d_sem_webgl_e_zona_mostra_historico(navegador, servidor):
    """X1: sem WebGL (`?2d=1` força), a planta 2D mostra as mesmas pessoas; clicar na zona abre o histórico."""
    with _Calibrada(servidor):
        contexto, pagina = _logado(navegador, servidor, viewport=(1366, 768))
        try:
            pagina.goto(f"{servidor.base}/gemeo?2d=1")
            pagina.locator("[data-testid=gemeo-2d]").wait_for(timeout=60_000)
            assert pagina.locator("[data-testid=gemeo-viewport]").get_attribute("data-modo") == "2d"
            pagina.locator(".gemeo-2d-pessoa").first.wait_for(timeout=180_000)
            pagina.locator(".gemeo-2d-zona").first.dispatch_event("click")
            zona = pagina.locator("[data-testid=gemeo-detalhe-zona]")
            zona.wait_for(timeout=10_000)
            assert "Doca" in zona.inner_text()
        finally:
            contexto.close()
