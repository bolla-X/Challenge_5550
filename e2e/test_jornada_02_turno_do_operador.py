"""Jornada 2 (MISSÃO 4, Fase 5 item 3): o turno do operador, do login ao "Sair".

Contra o servidor REAL com 4 câmeras de fixture (e2e/conftest.py). O operador do E2E nasce vinculado à
câmera "Multidão" (várias pessoas sem capacete: gera alerta crítico sem ninguém fazer nada).

Passos: login -> vê só a câmera do setor dele (as outras 3 dão 404, inclusive pela API) -> um alerta
aparece no quiosque -> "Avisei o colaborador" (reconhecer) -> "Marcar falso positivo" -> "Sair" volta ao
login e `/api/auth/me` fica sem usuário.

Cada ação é provada pela resposta real do servidor (a requisição que o botão dispara) e pela lista de
alertas da API, não só pela mensagem na tela.

Timeouts generosos para esta máquina lenta: login 60 s; o primeiro alerta ao vivo até 240 s.
"""

from __future__ import annotations

from conftest import entrar, esperar

OUTRAS_CAMERAS = ("Canteiro", "Rede", "Queda")


def test_turno_do_operador_login_alerta_reconhece_falso_positivo_e_sai(navegador, servidor):
    operador = servidor.sessao("operator")
    multidao = servidor.cameras["Multidão"]
    contexto = navegador.new_context(viewport={"width": 1366, "height": 768})
    try:
        pagina = contexto.new_page()
        entrar(pagina, servidor, "operator")

        # 1. Vê só a câmera do setor dele: um vídeo, o da Multidão, e as outras três não existem para ele.
        video = pagina.locator("canvas.live-video")
        video.first.wait_for(timeout=60_000)
        assert video.count() == 1
        assert video.first.get_attribute("data-camera") == str(multidao)
        pagina.get_by_text("Multidão", exact=True).first.wait_for(timeout=30_000)
        for nome in OUTRAS_CAMERAS:
            for rota in ("video_feed", "frame.jpg", "status"):
                resposta = pagina.request.get(f"{servidor.base}/api/cameras/{servidor.cameras[nome]}/{rota}")
                assert resposta.status == 404, f"operador acessou {rota} da câmera {nome}: {resposta.status}"

        # 2. Um alerta aparece: o quiosque troca "Tudo conforme" pelo aviso e libera os dois botões.
        avisei = pagina.get_by_role("button", name="Avisei o colaborador")
        avisei.wait_for(timeout=240_000)
        assert pagina.get_by_text("Tudo conforme").count() == 0

        # 3. "Avisei o colaborador": o servidor marca o alerta como reconhecido (sem resolvê-lo).
        with pagina.expect_response(lambda r: r.request.method == "POST" and "/acknowledge" in r.url, timeout=60_000) as resposta:
            avisei.click()
        assert resposta.value.status == 200, resposta.value.text()
        reconhecido = resposta.value.json()["alert"]
        assert reconhecido["acknowledged"] is True and reconhecido["camera_id"] == multidao, reconhecido
        pagina.get_by_text("Registrado: colaborador avisado.").wait_for(timeout=15_000)

        # 4. "Marcar falso positivo" no alerta que o quiosque mostra: sai da lista de ativos e fica marcado no histórico.
        falso = pagina.get_by_role("button", name="Marcar falso positivo")
        with pagina.expect_response(lambda r: r.request.method == "POST" and "/false-positive" in r.url, timeout=240_000) as resposta:
            falso.click(timeout=240_000)
        assert resposta.value.status == 200, resposta.value.text()
        marcado = resposta.value.json()["alert"]
        assert marcado["false_positive"] is True and marcado["camera_id"] == multidao, marcado
        pagina.get_by_text("Alerta marcado como falso positivo.").wait_for(timeout=15_000)
        esperar(lambda: any(a["id"] == marcado["id"] for a in operador.get(
            f"{servidor.base}/alerts", params={"camera_id": multidao, "false_positive": "true", "limit": 200}, timeout=20,
        ).json()["items"]), 30, 1, msg="o falso positivo não apareceu no histórico da API")

        # 5. "Sair" volta ao login e a API já não sabe quem é.
        pagina.get_by_role("button", name="Sair").click()
        pagina.get_by_label("E-mail").wait_for(timeout=30_000)
        assert pagina.request.get(f"{servidor.base}/api/auth/me").json()["user"] is None
        assert pagina.locator("canvas.live-video").count() == 0, "o vídeo do setor ficou na tela depois do logout"
    finally:
        contexto.close()
