"""Grava a cena 4 (demonstração) do storyboard: o app real, em modo demonstração, tema claro.

    python scripts/video/gravar_demo.py [--saida bench/runtime/video]

Sobe `run.py --demo` deste checkout (sem webcam, sem câmera IP, sem GEMINI_API_KEY),
espera as câmeras analisarem e a primeira segunda opinião existir, e só então grava
um contexto do Playwright 1920x1080 seguindo as sub-cenas 4a–4h de
docs/pitch/storyboard.md. Duas coisas são injetadas no DOM só para o vídeo:

- a barra de legenda fixa embaixo (`#legenda-video`), com o texto do storyboard;
- um cursor desenhado (`#cursor-video`): o Chromium headless não grava o ponteiro.

O app não sabe de nada disso (nada no código do app muda). Saída:
`<saida>/demo/4-demonstracao.webm` + `4-demonstracao.json` com o instante de
início de cada sub-cena (a montagem usa para conferir a duração).
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "e2e"))

from fumaca_demo import DemoEm  # noqa: E402

TAMANHO = {"width": 1920, "height": 1080}

INJECAO = r"""
(() => {
  const montar = () => {
    if (document.getElementById('legenda-video')) return;
    const estilo = document.createElement('style');
    estilo.textContent = `
      #legenda-video{position:fixed;left:50%;bottom:28px;transform:translateX(-50%);z-index:2147483647;
        max-width:1500px;padding:16px 30px;border-radius:16px;background:rgba(18,19,22,.86);color:#F5F5F7;
        font:500 30px/1.3 "Geist Variable","Segoe UI",system-ui,sans-serif;letter-spacing:-.01em;text-align:center;
        box-shadow:0 10px 30px rgba(16,17,20,.25);pointer-events:none;transition:opacity .35s}
      #legenda-video:empty{opacity:0}
      #cursor-video{position:fixed;left:0;top:0;width:26px;height:26px;z-index:2147483646;pointer-events:none;
        transform:translate(-100px,-100px);transition:transform .02s linear}
      #cursor-video svg{width:26px;height:26px;filter:drop-shadow(0 1px 2px rgba(0,0,0,.35))}
      #cursor-video.clique::after{content:"";position:absolute;left:-14px;top:-14px;width:28px;height:28px;border-radius:50%;
        border:3px solid #0A66C2;animation:pulso .45s ease-out forwards}
      @keyframes pulso{from{opacity:1;transform:scale(.4)}to{opacity:0;transform:scale(1.4)}}`;
    document.head.appendChild(estilo);
    const legenda = document.createElement('div');
    legenda.id = 'legenda-video';
    legenda.setAttribute('aria-hidden', 'true');
    legenda.textContent = sessionStorage.getItem('legenda-video') || '';
    document.body.appendChild(legenda);
    const cursor = document.createElement('div');
    cursor.id = 'cursor-video';
    cursor.innerHTML = '<svg viewBox="0 0 24 24"><path d="M4 2l15 11-7 1.2 4 7.3-2.6 1.4-4-7.4L4 20z" '
      + 'fill="#1A1A1C" stroke="#fff" stroke-width="1.4"/></svg>';
    document.body.appendChild(cursor);
    const pos = JSON.parse(sessionStorage.getItem('cursor-video') || '[960,540]');
    cursor.style.transform = `translate(${pos[0]}px,${pos[1]}px)`;
    addEventListener('mousemove', e => {
      cursor.style.transform = `translate(${e.clientX}px,${e.clientY}px)`;
      sessionStorage.setItem('cursor-video', JSON.stringify([e.clientX, e.clientY]));
    }, true);
    addEventListener('mousedown', () => {
      cursor.classList.remove('clique'); void cursor.offsetWidth; cursor.classList.add('clique');
    }, true);
  };
  if (document.body) montar(); else addEventListener('DOMContentLoaded', montar);
  try { localStorage.setItem('visionepi-theme', 'light'); } catch (e) {}
  ['operator','technical','supervisor'].forEach(p => { try { localStorage.setItem('visionepi-tour-visto-' + p, '1'); } catch (e) {} });
})();
"""


class Roteiro:
    def __init__(self, pagina, base: str) -> None:
        self.p, self.base = pagina, base
        self.inicio = time.monotonic()
        self.marcas: list[dict] = []

    def legenda(self, texto: str) -> None:
        self.p.evaluate("t => { sessionStorage.setItem('legenda-video', t); const l = document.getElementById('legenda-video');"
                        " if (l) l.textContent = t; }", texto)

    def cena(self, chave: str, texto: str) -> None:
        self.marcas.append({"cena": chave, "t": round(time.monotonic() - self.inicio, 2), "legenda": texto})
        self.legenda(texto)

    def esperar_ate(self, segundos_desde_o_inicio: float) -> None:
        falta = segundos_desde_o_inicio - (time.monotonic() - self.inicio)
        if falta > 0:
            time.sleep(falta)

    def ir(self, locator, pausa: float = 0.5) -> None:
        """Move o cursor até o elemento em ritmo humano e clica."""
        locator.wait_for(timeout=60_000)
        locator.scroll_into_view_if_needed()
        caixa = locator.bounding_box()
        self.p.mouse.move(caixa["x"] + caixa["width"] / 2, caixa["y"] + caixa["height"] / 2, steps=28)
        time.sleep(pausa)
        locator.click()

    def apontar(self, locator, pausa: float = 1.0) -> None:
        locator.wait_for(timeout=60_000)
        caixa = locator.bounding_box()
        self.p.mouse.move(caixa["x"] + caixa["width"] / 2, caixa["y"] + caixa["height"] / 2, steps=28)
        time.sleep(pausa)

    def digitar(self, locator, texto: str) -> None:
        self.ir(locator, 0.3)
        locator.press_sequentially(texto, delay=45)


def _aquecer(demo: DemoEm) -> None:
    """Antes de gravar: câmeras analisando, alerta ativo no Pátio e uma segunda opinião pronta."""
    s = demo.sessao("supervisor")
    cameras = {c["name"]: c["id"] for c in s.get(demo.base + "/api/cameras", timeout=10).json()}
    fim = time.monotonic() + 300
    while time.monotonic() < fim:
        estado = s.get(f"{demo.base}/api/cameras/{cameras['Pátio']}/status", timeout=20).json()
        if estado.get("active_alerts") and (estado.get("llm") or {}).get("ultima"):
            print("[demo] Pátio com alerta ativo e segunda opinião pronta", flush=True)
            return
        time.sleep(2)
    raise RuntimeError("o Pátio não teve alerta + segunda opinião em 300 s")


def gravar(saida: Path) -> Path:
    from playwright.sync_api import sync_playwright

    pasta = saida / "demo"
    shutil.rmtree(pasta, ignore_errors=True)
    pasta.mkdir(parents=True)
    python = RAIZ / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    demo = DemoEm(RAIZ, python)
    demo.subir()
    try:
        _aquecer(demo)
        with sync_playwright() as pw:
            navegador = pw.chromium.launch(headless=True)
            contexto = navegador.new_context(viewport=TAMANHO, record_video_dir=str(pasta / "_tmp"), record_video_size=TAMANHO,
                                             accept_downloads=True)
            contexto.add_init_script(INJECAO)
            p = contexto.new_page()
            r = Roteiro(p, demo.base)
            try:
                _roteiro(r, demo)
            finally:
                video = p.video
                contexto.close()
                navegador.close()
            destino = pasta / "4-demonstracao.webm"
            Path(video.path()).replace(destino)
            shutil.rmtree(pasta / "_tmp", ignore_errors=True)
            (pasta / "4-demonstracao.json").write_text(json.dumps(r.marcas, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"[demo] {destino.relative_to(RAIZ)} ({time.monotonic() - r.inicio:.0f} s)", flush=True)
            return destino
    finally:
        demo.parar()


def _roteiro(r: Roteiro, demo: DemoEm) -> None:
    p, base = r.p, demo.base
    # 4a — login e Início (15 s)
    p.goto(base + "/")
    r.cena("4a", "Modo demonstração: sem câmera IP e sem chave de API. Entramos como supervisora.")
    p.get_by_label("E-mail").wait_for(timeout=60_000)
    time.sleep(1.5)
    r.digitar(p.get_by_label("E-mail"), demo.emails["supervisor"])
    r.ir(p.get_by_label("Senha"), 0.3)
    p.get_by_label("Senha").fill(demo.senhas["supervisor"])
    r.ir(p.get_by_role("button", name="Entrar"))
    p.get_by_role("button", name=re.compile(r"^Câmeras")).first.wait_for(timeout=60_000)
    r.esperar_ate(15)

    # 4b — grade de câmeras (20 s)
    r.cena("4b", "Monitoramento em tempo real: quatro câmeras da demo, cada uma analisada ao vivo.")
    r.ir(p.get_by_role("button", name=re.compile(r"^Câmeras")).first)
    p.locator("canvas.live-video").first.wait_for(timeout=30_000)
    time.sleep(3)
    r.apontar(p.get_by_role("button", name=re.compile("Configurar Pátio")), 3)
    r.esperar_ate(35)

    # 4c — foco, incidentes e segunda opinião (30 s)
    r.cena("4c", "O alerta nasce da detecção e vira incidente, com os IDs de rastreio, nunca nomes.")
    r.ir(p.get_by_role("button", name=re.compile("Configurar Pátio")))
    p.locator("[role=tablist]").first.wait_for(timeout=30_000)
    time.sleep(4)
    _abrir_aba(r, "Alertas")
    p.locator("[data-testid=incidente]").first.wait_for(timeout=120_000)
    r.esperar_ate(51)
    r.cena("4c2", "A segunda opinião aparece rotulada \"modo demonstração\": sem chave, resposta fixa.")
    _abrir_aba(r, "Segunda opinião")
    p.locator("[data-testid=llm-modo-demonstracao]").wait_for(timeout=30_000)
    r.apontar(p.locator("[data-testid=llm-modo-demonstracao]"), 2)
    r.esperar_ate(65)

    # 4d — gestão: colaboradores e histórico (25 s)
    p.goto(base + "/gestao")
    p.locator("[data-testid=gestao]").wait_for(timeout=30_000)
    r.cena("4d", "Gestão de EPIs: cada colaborador tem a ficha de EPI, com o que recebeu e quando vence.")
    r.ir(p.locator("[data-testid=gestao-aba-colaboradores]"))
    linha = p.locator("[data-testid^=gestao-colaborador-]").nth(2)
    time.sleep(2)
    r.ir(linha)
    p.locator("[data-testid=gestao-historico]").wait_for(timeout=30_000)
    r.apontar(p.locator("[data-testid=gestao-historico]"), 4)
    r.esperar_ate(90)

    # 4e — catálogo (15 s)
    r.cena("4e", "Catálogo com CA e validade: vencido e a vencer aparecem antes de virar problema.")
    r.ir(p.locator("[data-testid=gestao-aba-catalogo]"))
    alvo = p.locator("[data-testid=gestao-tabela-epis]").get_by_text(re.compile(r"Vencido h")).first
    r.apontar(alvo, 3)
    r.esperar_ate(105)

    # 4f — entrega com CA vencido (15 s)
    r.cena("4f", "Entrega de EPI com CA vencido é bloqueada pela política da empresa.")
    r.ir(p.locator("[data-testid=gestao-aba-entregas]"))
    r.ir(p.locator("[data-testid=gestao-nova-entrega]"))
    form = p.locator("[data-testid=gestao-form-entrega]")
    form.wait_for(timeout=10_000)
    s = demo.sessao("supervisor")
    vencido = next(e for e in s.get(base + "/api/gestao/epis", timeout=10).json()["items"] if e["situacao_ca"] == "vencido")
    r.apontar(form.locator("[data-testid=gestao-entrega-colaborador]"), 0.4)
    form.locator("[data-testid=gestao-entrega-colaborador]").select_option(index=3)
    r.apontar(form.locator("[data-testid=gestao-entrega-epi]"), 0.4)
    form.locator("[data-testid=gestao-entrega-epi]").select_option(value=str(vencido["id"]))
    r.ir(form.get_by_role("button", name=re.compile("Registrar")).last)
    erro = form.get_by_role("alert").filter(has_text=re.compile("CA")).first
    erro.wait_for(timeout=10_000)
    r.apontar(erro, 2)
    r.esperar_ate(120)

    # 4g — ocorrência (15 s)
    r.cena("4g", "Ocorrência registrada com tipo, gravidade, setor e ação corretiva.")
    p.keyboard.press("Escape")
    r.ir(p.locator("[data-testid=gestao-aba-ocorrencias]"))
    r.ir(p.locator("[data-testid=gestao-nova-ocorrencia]"))
    form = p.locator("[data-testid=gestao-form-ocorrencia]")
    form.wait_for(timeout=10_000)
    form.get_by_label(re.compile("Tipo")).select_option("quase_acidente")
    form.get_by_label(re.compile("Gravidade")).select_option("alta")
    r.digitar(form.get_by_label(re.compile("Setor")), "Expedição")
    r.digitar(form.get_by_label(re.compile("Descrição")), "Empilhadeira passou rente à faixa de pedestres")
    r.ir(form.get_by_role("button", name=re.compile("Registrar")).last)
    p.get_by_text("Empilhadeira passou rente").first.wait_for(timeout=15_000)
    r.esperar_ate(135)

    # 4h — exportação e relatório mensal (15 s)
    r.cena("4h", "Tudo exporta em CSV, e o relatório mensal vai para a CIPA.")
    r.ir(p.locator("[data-testid=gestao-aba-relatorios]"))
    with p.expect_download():
        r.ir(p.locator("[data-testid=gestao-exportar-entregas]"))
    time.sleep(2.5)
    p.goto(base + "/relatorio/mensal")
    p.wait_for_load_state("load")
    r.esperar_ate(150)


def _abrir_aba(r: Roteiro, rotulo: str) -> None:
    p = r.p
    aba = p.get_by_role("tab", name=rotulo)
    if aba.count():
        r.ir(aba)
        return
    r.ir(p.locator(".tabs-more > button"))
    r.ir(p.get_by_role("menuitem", name=rotulo))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--saida", type=Path, default=RAIZ / "bench" / "runtime" / "video")
    args = ap.parse_args()
    gravar(args.saida.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
