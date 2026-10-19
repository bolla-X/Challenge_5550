"""Jornada 10 (MISSÃO 4, Fase 5 item 3): a apresentação do `/palco`, do início ao fim, pelo teclado e pelo celular.

Contra o servidor REAL com 4 câmeras de fixture (e2e/conftest.py):

1. o técnico abre o `/palco` em tela cheia (1920x1080) e percorre TODAS as cenas com a seta para a direita
   (cada cena é diferente da anterior e não deixa erro no console);
2. o controle no celular emulado (390x844, toque) entra pelo token do QR do palco, volta duas cenas, avança uma
   e mostra o mesmo título que o palco; o palco anda junto (o estado da apresentação mora no servidor);
3. com o celular fora, o teclado continua mandando: vai à última cena e volta à primeira.

Timeouts generosos para esta máquina lenta: login 60 s; cada cena 15 s; controle do celular 30 s.
Movida e adaptada de e2e/test_missao2.py (X6): o celular agora é 390x844 (antes, o perfil "Pixel 7") e a
espera fixa de 1,5 s por cena virou uma pausa curta para a cena desenhar.
"""

from __future__ import annotations

import re

from conftest import entrar


def _cena_atual(pagina, indice: int, timeout: int = 15_000) -> None:
    pagina.wait_for_function(f"document.querySelector('[data-testid=palco]')?.dataset.cena === '{indice}'", timeout=timeout)


def test_palco_do_inicio_ao_fim_pelo_teclado_e_pelo_celular(navegador, servidor):
    contexto = navegador.new_context(viewport={"width": 1920, "height": 1080})
    try:
        pagina = contexto.new_page()
        pagina.erros_console = []
        pagina.on("console", lambda m: pagina.erros_console.append(m.text) if m.type == "error" else None)
        entrar(pagina, servidor, "technical")
        pagina.get_by_role("button", name=re.compile("Configurar|Câmeras")).first.wait_for(timeout=60_000)

        # 1. Teclado: volta ao início e anda cena por cena até o fim.
        pagina.goto(f"{servidor.base}/palco")
        palco = pagina.locator("[data-testid=palco]")
        palco.wait_for(timeout=30_000)
        for _ in range(20):
            pagina.keyboard.press("ArrowLeft")
        _cena_atual(pagina, 0)
        total = int(pagina.locator(".palco-indice").inner_text().split("/")[1])
        assert total > 2, f"roteiro com {total} cena(s)"
        vistos: list[str] = []
        for i in range(1, total):
            pagina.keyboard.press("ArrowRight")
            try:
                _cena_atual(pagina, i)
            except Exception as exc:  # noqa: BLE001  (diagnóstico: onde o foco e a tela ficaram)
                foco = pagina.evaluate("document.activeElement && document.activeElement.outerHTML.slice(0, 200)")
                raise AssertionError(f"cena {i} não veio; tela em {palco.get_attribute('data-cena')} "
                                     f"({palco.get_attribute('data-chave')}), foco em {foco}") from exc
            pagina.locator("[data-testid=palco-cena]").wait_for()
            vistos.append(palco.get_attribute("data-chave"))
            pagina.wait_for_timeout(800)  # a cena desenha antes de seguir: erro de renderização aparece no console
        assert len(vistos) == total - 1 and len(set(vistos)) == total - 1, vistos  # cada cena é diferente da anterior
        assert not [e for e in pagina.erros_console if "Error" in e], pagina.erros_console

        # 2. Celular emulado (390x844, toque): entra pelo token do QR, sem sessão, e conduz o palco.
        url = pagina.locator("[data-testid=palco-qr]").get_attribute("data-url")
        caminho = url[url.index("/palco/controle"):]
        celular = navegador.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True, device_scale_factor=3)
        try:
            fone = celular.new_page()
            fone.goto(servidor.base + caminho)
            fone.locator("[data-testid=controle-cena]").wait_for(timeout=30_000)
            fone.locator("[data-testid=controle-anterior]").click()
            _cena_atual(pagina, total - 2)
            fone.locator("[data-testid=controle-anterior]").click()
            _cena_atual(pagina, total - 3)
            fone.locator("[data-testid=controle-proxima]").click()
            _cena_atual(pagina, total - 2)
            assert fone.locator("[data-testid=controle-cena]").inner_text() == pagina.locator("[data-testid=palco-titulo]").inner_text()
        finally:
            celular.close()

        # 3. Celular fora: o teclado continua mandando, até a última cena e de volta à primeira.
        pagina.keyboard.press("ArrowRight")
        _cena_atual(pagina, total - 1)
        for _ in range(20):
            pagina.keyboard.press("ArrowLeft")
        _cena_atual(pagina, 0)
    finally:
        contexto.close()
