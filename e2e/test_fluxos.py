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


def test_queda_do_modelo_chega_ao_navegador_com_id(pagina, servidor):
    """F2: a classe `fall_detected` do Vyra vira alerta crítico atribuído a um ID de rastreio.

    Fixture real (`next_queda`, domínio público): a pessoa caída é vista pelo
    modelo em janelas curtas (a maior, 6,0–6,9 s do clipe). O alerta tem de
    chegar à tela com "Pessoa N".
    """
    entrar(pagina, servidor, "technical")
    _abrir_camera(pagina, "Queda")
    alerta = pagina.locator(".over-pill.alert", has_text="Queda detectada")
    alerta.wait_for(timeout=300_000)
    texto = alerta.inner_text()
    assert "Pessoa" in texto, texto


def test_celular_vira_camera_pelo_link_do_qr(navegador, servidor):
    """F6: página /cam sem login, só com o token; quadros chegam ao servidor; QR aparece para o técnico.

    Câmera falsa do Chromium (--use-fake-device-for-media-stream). Em
    127.0.0.1 a página já é contexto seguro, então o teste roda em HTTP; no
    celular de verdade é preciso HTTPS (run.py --https).
    """
    tecnico = servidor.sessao("technical")
    r = tecnico.post(servidor.base + "/api/cameras", json={"name": "Celular", "source_type": "Celular", "source": "x",
                                                          "fps": 12, "width": 960, "height": 540}, timeout=10)
    r.raise_for_status()
    cid = r.json()["id"]
    tecnico.post(f"{servidor.base}/api/cameras/{cid}/start", timeout=60).raise_for_status()
    caminho = tecnico.get(f"{servidor.base}/api/cameras/{cid}/celular", timeout=10).json()["caminho"]

    celular = navegador.new_context(viewport={"width": 390, "height": 844})  # sem cookie de sessão
    try:
        pagina_cel = celular.new_page()
        pagina_cel.goto(servidor.base + caminho)
        pagina_cel.get_by_role("button", name="Iniciar câmera").click()
        estado = pagina_cel.locator("#estado")
        limite = time.monotonic() + 60
        while time.monotonic() < limite and "quadros" not in (estado.inner_text() or ""):
            time.sleep(0.5)
        assert "quadros" in estado.inner_text(), estado.inner_text()
        assert estado.get_attribute("data-estado") == "enviando"

        limite = time.monotonic() + 60
        lidos = 0
        while time.monotonic() < limite and lidos < 10:
            d = tecnico.get(f"{servidor.base}/api/diagnostics/pipeline?janela_s=30", timeout=10).json()
            lidos = d["cameras"][str(cid)]["stats"]["totais"].get("frames_lidos", 0)
            time.sleep(1)
        assert lidos >= 10, f"servidor recebeu só {lidos} quadros do celular"
    finally:
        celular.close()

    contexto = navegador.new_context(viewport={"width": 1366, "height": 768})
    try:
        pagina = contexto.new_page()
        entrar(pagina, servidor, "technical")
        _abrir_camera(pagina, "Celular")
        pagina.get_by_role("tab", name="Config. câmera").click()
        pagina.locator("[data-testid=celular-qr] svg.qr").wait_for(timeout=30_000)
        assert caminho in pagina.locator("[data-testid=celular-qr] code").inner_text()
    finally:
        contexto.close()
        tecnico.post(f"{servidor.base}/api/cameras/{cid}/stop", timeout=30)
