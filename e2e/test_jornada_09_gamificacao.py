"""Jornada 9 (MISSÃO 4, Fase 5 item 3): a gamificação, do check-in no portal aos cartões da retrospectiva.

Contra o servidor REAL com 4 câmeras de fixture (e2e/conftest.py), no setor "Canteiro" (câmera do portal):

1. `test_checkin_no_portal_cumpre_a_missao_pontua_na_liga_e_aparece_na_retrospectiva`: o supervisor configura
   a missão do turno "um check-in a mais"; o portal da Canteiro (com portaria de capacete e colete) libera;
   a missão é cumprida; os pontos de experiência da planta sobem (check-in vale 10); a Liga mostra a missão
   cumprida, o nível e o placar do setor; a `/retrospectiva` do turno mostra os cartões de check-ins, missões
   cumpridas e nível, e a API dela traz os mesmos números;
2. `test_liga_missao_cumprida_celebra_e_pontua_o_setor`: a mesma ideia com a missão de rótulo (revisar um
   recorte duvidoso), e a TELA celebra ("Missão cumprida") ao vivo;
3. `test_retrospectiva_exporta_card_em_png`: cada cartão vira um PNG 1080x1350.

Tudo é por setor, nunca por pessoa: a retrospectiva não traz "Pessoa N".
Timeouts generosos para esta máquina lenta: login 60 s; portal liberar até 240 s; missão e pontos 60 s;
recorte na fila 240 s.
Os testes 2 e 3 foram movidos de e2e/test_missao2.py (X8 e X7), sem duplicar; o 1 é novo.
"""

from __future__ import annotations

import re
import struct
from pathlib import Path

from conftest import entrar, esperar

CARTOES_DA_RETROSPECTIVA = {"checkins", "missoes", "nivel"}


def _estado_da_liga(sessao, servidor) -> dict:
    return sessao.get(f"{servidor.base}/api/liga", timeout=20).json()


def _medir_o_turno(supervisor, servidor, tipo: str) -> tuple[int, int]:
    """(quanto o turno já tem do tipo, XP da planta): mede com uma missão-sonda que nunca se cumpre."""
    sonda = supervisor.post(f"{servidor.base}/api/liga/missoes", json={"titulo": "sonda", "tipo": tipo, "alvo": 10000},
                            timeout=20).json()["missao"]["id"]
    estado = _estado_da_liga(supervisor, servidor)
    supervisor.delete(f"{servidor.base}/api/liga/missoes/{sonda}", timeout=20)
    return next(m["feito"] for m in estado["missoes"] if m["id"] == sonda), estado["planta"]["xp"]


def test_checkin_no_portal_cumpre_a_missao_pontua_na_liga_e_aparece_na_retrospectiva(navegador, servidor):
    supervisor = servidor.sessao("supervisor")
    tecnico = servidor.sessao("technical")
    cid = servidor.cameras["Canteiro"]
    feitos, xp_antes = _medir_o_turno(supervisor, servidor, "checkin_portal")
    titulo = "Mais um check-in no portal (E2E)"
    criada = supervisor.post(f"{servidor.base}/api/liga/missoes", json={"titulo": titulo, "tipo": "checkin_portal", "alvo": feitos + 1},
                             timeout=20)
    assert criada.status_code == 201, criada.text
    missao_id = criada.json()["missao"]["id"]
    assert tecnico.post(f"{servidor.base}/api/liga/missoes", json={"titulo": "x", "tipo": "checkin_portal", "alvo": 1},
                        timeout=20).status_code == 403, "só o supervisor configura a missão"
    assert tecnico.put(f"{servidor.base}/api/cameras/{cid}/gate", json={"required": ["helmet", "vest"]}, timeout=20).status_code == 200
    contexto = navegador.new_context(viewport={"width": 1366, "height": 768})
    try:
        pagina = contexto.new_page()
        entrar(pagina, servidor, "supervisor")
        pagina.get_by_role("button", name=re.compile(r"^Câmeras")).first.wait_for(timeout=60_000)

        # 1. Check-in: o portal confirma capacete e colete e libera.
        pagina.goto(f"{servidor.base}/portal?camera={cid}")
        pagina.locator("[data-testid=portal]").wait_for(timeout=60_000)
        pagina.wait_for_function("document.querySelector('[data-testid=portal]')?.dataset.veredito === 'approved'", timeout=240_000)
        assert pagina.locator("[data-testid=portal-titulo]").inner_text() == "Liberado"

        # 2. A missão do turno é cumprida e o XP da planta sobe (um check-in vale 10 pontos).
        def missao_cumprida():
            estado = _estado_da_liga(supervisor, servidor)
            return next((m for m in estado["missoes"] if m["id"] == missao_id and m["cumprida"]), None) and estado

        estado = esperar(missao_cumprida, 60, 1, msg="a missão do check-in não foi cumprida")
        assert estado["planta"]["xp"] >= xp_antes + 10, (xp_antes, estado["planta"])
        setor = next(s for s in estado["setores"] if s["por_tipo"].get("checkin_portal"))
        assert setor["pontos"] >= 10, setor

        # 3. A Liga mostra a missão cumprida, o nível da planta e o setor no placar.
        pagina.goto(servidor.base + "/liga")
        pagina.locator("[data-testid=liga-placar]").wait_for(timeout=60_000)
        cumprida = pagina.locator("[data-testid=liga-missao][data-cumprida='1']", has_text=titulo)
        cumprida.first.wait_for(timeout=30_000)
        assert "Cumprida" in cumprida.first.inner_text()
        assert "pontos de experiência" in pagina.locator("[data-testid=liga-nivel]").inner_text()
        placar = pagina.locator("[data-testid=liga-placar]").inner_text()
        assert setor["setor"] in placar and "Check-ins no portal" in placar, placar

        # 4. A retrospectiva do turno mostra os cartões e nenhuma pessoa.
        pagina.goto(servidor.base + "/retrospectiva")
        cartao = pagina.locator("[data-testid=retro-card]")
        cartao.wait_for(timeout=30_000)
        pagina.get_by_role("button", name="Pausar").click()
        total = int(pagina.locator("[data-testid=retrospectiva]").get_attribute("data-total"))
        vistos = [cartao.get_attribute("data-chave")]
        for _ in range(total - 1):
            pagina.keyboard.press("ArrowRight")
            esperar(lambda: cartao.get_attribute("data-chave") != vistos[-1], 10, 0.2, msg="a retrospectiva não avançou de cartão")
            vistos.append(cartao.get_attribute("data-chave"))
        assert CARTOES_DA_RETROSPECTIVA <= set(vistos) and len(vistos) == len(set(vistos)), vistos
        assert "Pessoa " not in pagina.locator("[data-testid=retrospectiva]").inner_text()
    finally:
        contexto.close()
        supervisor.delete(f"{servidor.base}/api/liga/missoes/{missao_id}", timeout=20)
        tecnico.put(f"{servidor.base}/api/cameras/{cid}/gate", json={"required": None}, timeout=20)
    # A API da retrospectiva traz os mesmos números que os cartões mostram.
    cartoes = {c["chave"]: c for c in supervisor.get(f"{servidor.base}/api/retrospectiva", timeout=20).json()["cards"]}
    assert cartoes["checkins"]["valor"] >= 1 and cartoes["missoes"]["valor"] >= 1, cartoes


def test_liga_missao_cumprida_celebra_e_pontua_o_setor(navegador, servidor):
    """X8: missão configurada pelo supervisor; um rótulo revisado cumpre, a tela celebra; ponto vai para o setor."""
    supervisor = servidor.sessao("supervisor")
    # Alvo = o que já foi feito neste turno + 1 (outro teste pode ter revisado um recorte antes).
    feitos, _ = _medir_o_turno(supervisor, servidor, "rotulo")
    r = supervisor.post(f"{servidor.base}/api/liga/missoes",
                        json={"titulo": "Revisar mais 1 recorte (E2E)", "tipo": "rotulo", "alvo": feitos + 1}, timeout=20)
    assert r.status_code == 201, r.text
    missao_id = r.json()["missao"]["id"]
    assert servidor.sessao("technical").post(f"{servidor.base}/api/liga/missoes", json={"titulo": "x", "tipo": "rotulo", "alvo": 1},
                                             timeout=20).status_code == 403
    contexto = navegador.new_context(viewport={"width": 1920, "height": 1080})
    try:
        pagina = contexto.new_page()
        entrar(pagina, servidor, "supervisor")
        pagina.get_by_role("button", name=re.compile(r"^Câmeras")).first.wait_for(timeout=60_000)
        pagina.goto(f"{servidor.base}/liga")
        pagina.locator("[data-testid=liga-placar]").wait_for(timeout=30_000)
        pagina.locator("[data-testid=liga-nivel]").wait_for(timeout=30_000)
        pagina.wait_for_timeout(1500)  # a primeira leitura não celebra; só a mudança depois dela
        tecnico = servidor.sessao("technical")
        item = esperar(lambda: (resposta := tecnico.get(f"{servidor.base}/api/rotulos/proximo", timeout=20)).status_code == 200
                       and (resposta.json() or {}).get("item"), 240, 3, msg="nenhum recorte chegou à fila")
        assert tecnico.post(f"{servidor.base}/api/rotulos/{item['id']}", json={"decisao": "confirmar"}, timeout=20).status_code == 200
        aviso = pagina.locator(".liga-aviso")
        aviso.wait_for(timeout=30_000)
        assert "Missão cumprida" in aviso.inner_text()
        estado = _estado_da_liga(supervisor, servidor)
        assert any(m["id"] == missao_id and m["cumprida"] for m in estado["missoes"])
        assert sum(s["pontos"] for s in estado["setores"]) > 0
    finally:
        contexto.close()
        supervisor.delete(f"{servidor.base}/api/liga/missoes/{missao_id}", timeout=20)


def test_retrospectiva_exporta_card_em_png(navegador, servidor):
    """X7: stories com dados reais; cada card vira um PNG 1080×1350."""
    contexto = navegador.new_context(viewport={"width": 1366, "height": 768}, accept_downloads=True)
    try:
        pagina = contexto.new_page()
        entrar(pagina, servidor, "supervisor")
        pagina.get_by_role("button", name=re.compile(r"^Câmeras")).first.wait_for(timeout=60_000)
        pagina.goto(f"{servidor.base}/retrospectiva?periodo=semana")
        card = pagina.locator("[data-testid=retro-card]")
        card.wait_for(timeout=30_000)
        assert "Pessoa " not in pagina.locator("[data-testid=retrospectiva]").inner_text()
        with pagina.expect_download() as baixado:
            pagina.locator("[data-testid=retro-png]").click()
        dados = Path(baixado.value.path()).read_bytes()
        assert dados[:8] == b"\x89PNG\r\n\x1a\n"
        largura, altura = struct.unpack(">II", dados[16:24])
        assert (largura, altura) == (1080, 1350)
        # Pausa o avanço automático e confere que → avança um card.
        pagina.get_by_role("button", name="Pausar").click()
        antes = int(pagina.locator("[data-testid=retrospectiva]").get_attribute("data-indice"))
        pagina.keyboard.press("ArrowRight")
        pagina.wait_for_function(
            f"document.querySelector('[data-testid=retrospectiva]')?.dataset.indice === '{antes + 1}'", timeout=10_000
        )
    finally:
        contexto.close()
