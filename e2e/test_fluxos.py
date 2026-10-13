"""Fluxos ponta a ponta da missão (seção 8). Ver e2e/conftest.py."""

from __future__ import annotations

import time

from conftest import entrar


def _abrir_camera(pagina, nome: str) -> None:
    pagina.get_by_role("button", name=f"Configurar {nome}").click(timeout=30_000)


def _quadros_exibidos(pagina) -> int:
    return int(pagina.locator("canvas.live-video").first.get_attribute("data-frames") or 0)


def test_login_e_video_aparece(pagina, servidor):
    entrar(pagina, servidor, "technical")
    _abrir_camera(pagina, "Canteiro")
    video = pagina.locator("canvas.live-video").first
    video.wait_for(timeout=30_000)
    limite = time.monotonic() + 90
    while time.monotonic() < limite and _quadros_exibidos(pagina) < 10:
        time.sleep(0.5)
    assert _quadros_exibidos(pagina) >= 10, "o vídeo não chegou ao canvas"
    assert video.get_attribute("data-estado") == "ao_vivo"
    # Fixture de arquivo é GRAVAÇÃO, nunca "ao vivo" na tela.
    assert pagina.locator(".feed-badge").first.get_attribute("data-estado") == "gravacao"


def test_alerta_surge_para_pessoa_sem_epi(pagina, servidor):
    entrar(pagina, servidor, "technical")
    _abrir_camera(pagina, "Multidão")
    # O pill de alerta crítico/alto sobre o vídeo (camera-focus.tsx).
    alerta = pagina.locator(".over-pill.alert")
    alerta.wait_for(timeout=240_000)
    assert "Sem" in alerta.inner_text(), alerta.inner_text()


def test_operador_nao_ve_outra_camera(pagina, servidor):
    entrar(pagina, servidor, "operator")
    pagina.locator("canvas.live-video").first.wait_for(timeout=30_000)
    assert pagina.locator("canvas.live-video").count() == 1
    assert pagina.locator("canvas.live-video").first.get_attribute("data-camera") == str(servidor.cameras["Multidão"])
    for nome in ("Canteiro", "Rede"):
        cid = servidor.cameras[nome]
        for rota in ("video_feed", "frame.jpg", "status"):
            resposta = pagina.request.get(f"{servidor.base}/api/cameras/{cid}/{rota}")
            assert resposta.status == 404, f"operador acessou {rota} da câmera {nome}: {resposta.status}"


def test_queda_da_fonte_mostra_reconectando_e_volta(pagina, servidor):
    entrar(pagina, servidor, "technical")
    _abrir_camera(pagina, "Rede")
    badge = pagina.locator(".feed-badge").first
    limite = time.monotonic() + 90
    while time.monotonic() < limite and badge.get_attribute("data-estado") != "ao_vivo":
        time.sleep(0.5)
    assert badge.get_attribute("data-estado") == "ao_vivo", "a fonte de rede nunca ficou ao vivo"

    servidor.fonte_rede.parar()
    vistos: set[str] = set()
    limite = time.monotonic() + 90
    while time.monotonic() < limite and not ({"reconectando", "sem_sinal"} & vistos):
        vistos.add(badge.get_attribute("data-estado") or "")
        time.sleep(0.3)
    assert {"reconectando", "sem_sinal"} & vistos, f"queda da fonte não apareceu na tela: {vistos}"

    servidor.fonte_rede.iniciar()
    limite = time.monotonic() + 120
    while time.monotonic() < limite and badge.get_attribute("data-estado") != "ao_vivo":
        time.sleep(0.5)
    assert badge.get_attribute("data-estado") == "ao_vivo", "a fonte voltou e a tela não"
