"""Captura as evidencias de execucao do dashboard (Sprint 4) com Playwright.

Pre-requisitos: app rodando (python run.py) com a camera cadastrada sobre
tests/fixtures/demo_sprint4.mp4 (scripts/montar_video_demo.py) e as contas
supervisor/tecnico/operador criadas. Playwright NAO esta no requirements.txt
(so serve para gerar evidencia): pip install playwright.

    CHROMIUM=/caminho/do/chrome python scripts/capturar_evidencias.py
"""

import asyncio
import os

from playwright.async_api import async_playwright

CH = os.getenv("CHROMIUM") or None
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "evidencias", "app")
SENHA = os.getenv("SENHA_DEMO", "")
async def login(ctx, email):
    pg = await ctx.new_page()
    await pg.goto("http://127.0.0.1:5000/")
    await pg.fill("input[type=email]", email)
    await pg.fill("input[type=password]", SENHA)
    await pg.click("button[type=submit]")
    await pg.wait_for_timeout(3500)
    return pg
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path=CH)
        tela = {"width": 1600, "height": 1000}
        ctx = await b.new_context(viewport=tela, record_video_dir=OUT + "/video", record_video_size=tela)
        pg = await login(ctx, "supervisor@visionepi.local")
        await pg.screenshot(path=f"{OUT}/01_grade_parada.jpg", quality=85, type="jpeg")
        await pg.click("text=Iniciar")
        await pg.wait_for_timeout(12000)
        await pg.screenshot(path=f"{OUT}/02_grade_rodando.jpg", quality=85, type="jpeg")
        await pg.click("text=Configurar")
        await pg.wait_for_timeout(2500)
        for i in range(10):
            await pg.screenshot(path=f"{OUT}/03_foco_t{i:02d}.jpg", quality=85, type="jpeg")
            await pg.wait_for_timeout(4000)
        tabs = await pg.eval_on_selector_all("[role=tab]", "els=>els.map(e=>e.innerText.trim())")
        print("tabs", tabs)
        for t in tabs:
            try:
                await pg.click(f"[role=tab]:has-text('{t}')")
                await pg.wait_for_timeout(1500)
                await pg.screenshot(path=f"{OUT}/04_aba_{t.split()[0].lower()}.jpg", quality=85, type="jpeg")
            except Exception as e:
                print("aba", t, e)
        await ctx.close()
        for email, nome in [("operador@visionepi.local","05_operador"),("tecnico@visionepi.local","06_tecnico")]:
            c2 = await b.new_context(viewport={"width":1600,"height":1000})
            pg2 = await login(c2, email)
            await pg2.wait_for_timeout(5000)
            await pg2.screenshot(path=f"{OUT}/{nome}.jpg", quality=85, type="jpeg")
            await c2.close()
        await b.close()
asyncio.run(main())
