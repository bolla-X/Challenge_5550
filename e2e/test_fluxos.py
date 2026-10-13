"""Fluxos ponta a ponta da missão (seção 8). Ver e2e/conftest.py."""

from __future__ import annotations

import re
import time

from conftest import entrar


def _abrir_camera(pagina, nome: str) -> None:
    pagina.get_by_role("button", name=f"Configurar {nome}").click(timeout=30_000)


def _abrir_aba(pagina, rotulo: str) -> None:
    """Abre uma aba do foco, inclusive as que ficam no menu "Mais"."""
    aba = pagina.get_by_role("tab", name=rotulo)
    if aba.count():
        aba.click()
        return
    pagina.locator(".tabs-more > button").click()
    pagina.get_by_role("menuitem", name=rotulo).click()


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

    Fixture real (`next_queda`, domínio público): o modelo vê a pessoa caída em
    janelas curtas (a maior, 6,0–6,9 s do clipe de 20 s). Com 4 câmeras
    dividindo o agendador, a câmera "Queda" faz poucas análises nessa janela e a
    histerese (que não é afrouxada para o teste) quase nunca confirma — por isso
    as outras câmeras ficam paradas durante o teste e voltam no fim.
    """
    tecnico = servidor.sessao("technical")
    outras = [cid for nome, cid in servidor.cameras.items() if nome != "Queda"]
    for cid in outras:
        tecnico.post(f"{servidor.base}/api/cameras/{cid}/stop", timeout=30)
    try:
        entrar(pagina, servidor, "technical")
        _abrir_camera(pagina, "Queda")
        queda = servidor.cameras["Queda"]
        tecnico.post(f"{servidor.base}/api/cameras/{queda}/stop", timeout=30)
        tecnico.post(f"{servidor.base}/api/cameras/{queda}/start", timeout=60).raise_for_status()
        alerta = pagina.locator(".over-pill.alert", has_text="Queda detectada")
        alerta.wait_for(timeout=300_000)
        texto = alerta.inner_text()
        assert "Pessoa" in texto, texto
    finally:
        for cid in outras:
            tecnico.post(f"{servidor.base}/api/cameras/{cid}/start", timeout=60)


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
        _abrir_aba(pagina, "Config. câmera")
        pagina.locator("[data-testid=celular-qr] svg.qr").wait_for(timeout=30_000)
        assert caminho in pagina.locator("[data-testid=celular-qr] code").inner_text()
    finally:
        contexto.close()
        tecnico.post(f"{servidor.base}/api/cameras/{cid}/stop", timeout=30)


def _abrir_camera_como(pagina, servidor, papel: str, nome: str) -> None:
    entrar(pagina, servidor, papel)
    if papel == "supervisor":
        pagina.get_by_role("button", name=re.compile(r"^Câmeras")).first.click(timeout=30_000)
    _abrir_camera(pagina, nome)


def test_replay_do_incidente_abre_e_toca(pagina, servidor):
    """F1: alerta com clipe → "Ver replay" abre o player e os quadros avançam."""
    _abrir_camera_como(pagina, servidor, "technical", "Multidão")
    _abrir_aba(pagina, "Alertas")
    botao = pagina.get_by_role("button", name="Ver replay").first
    canvas = pagina.locator('canvas[aria-label="Replay do incidente"]')
    limite = time.monotonic() + 240
    while time.monotonic() < limite:
        botao.wait_for(timeout=max(1_000, int((limite - time.monotonic()) * 1000)))
        botao.click()
        try:
            canvas.wait_for(timeout=10_000)
            break
        except Exception:  # noqa: BLE001  (clipe ainda sendo fechado: tenta de novo)
            pagina.keyboard.press("Escape")
            time.sleep(3)
    total = int(canvas.get_attribute("data-total") or 0)
    assert total > 1, f"clipe com {total} quadro(s)"
    primeiro = int(canvas.get_attribute("data-quadro") or 0)
    limite = time.monotonic() + 15
    while time.monotonic() < limite and int(canvas.get_attribute("data-quadro") or 0) == primeiro:
        time.sleep(0.3)
    assert int(canvas.get_attribute("data-quadro") or 0) != primeiro, "o replay não avançou"


def test_pill_de_aproximacao_aparece(pagina, servidor):
    """F3: pessoa andando em direção à zona → pílula amarela de projeção antes de entrar.

    PPE desligado nesta câmera durante o teste: a pílula crítica de EPI tem
    precedência sobre a de aproximação, como deve ser.
    """
    tecnico = servidor.sessao("technical")
    cid = servidor.cameras["Multidão"]
    tecnico.patch(f"{servidor.base}/features?camera_id={cid}", json={"features": {"ppe": False}}, timeout=10)
    zona = [{"x": 0.6, "y": 0.0}, {"x": 1.0, "y": 0.0}, {"x": 1.0, "y": 1.0}, {"x": 0.6, "y": 1.0}]
    antes = tecnico.get(f"{servidor.base}/api/cameras/{cid}/risk-area", timeout=10).json()
    tecnico.put(f"{servidor.base}/api/cameras/{cid}/risk-area", json={"polygon": zona, "name": "Zona E2E"}, timeout=10)
    try:
        _abrir_camera_como(pagina, servidor, "technical", "Multidão")
        pill = pagina.locator("[data-testid=pre-alerta]")
        pill.wait_for(timeout=180_000)
        assert "projeção" in pill.inner_text()
    finally:
        tecnico.patch(f"{servidor.base}/features?camera_id={cid}", json={"features": {"ppe": True}}, timeout=10)
        poligono = (antes.get("risk_area") or antes).get("polygon") or []
        tecnico.put(f"{servidor.base}/api/cameras/{cid}/risk-area", json={"polygon": poligono}, timeout=10)


def test_privacidade_so_o_supervisor_altera(pagina, servidor):
    """F4: técnico vê o estado e o botão desabilitado (e a API nega); supervisor troca."""
    cid = servidor.cameras["Canteiro"]
    assert servidor.sessao("technical").patch(f"{servidor.base}/api/cameras/{cid}/privacidade",
                                              json={"ativa": False}, timeout=10).status_code == 403

    _abrir_camera_como(pagina, servidor, "technical", "Canteiro")
    _abrir_aba(pagina, "Config. câmera")
    assert pagina.locator("[data-testid=privacidade-estado]").inner_text() == "ligado"
    assert pagina.locator("[data-testid=privacidade-botao]").is_disabled()

    pagina.context.clear_cookies()
    _abrir_camera_como(pagina, servidor, "supervisor", "Canteiro")
    _abrir_aba(pagina, "Config. câmera")
    pagina.once("dialog", lambda d: d.accept())
    pagina.locator("[data-testid=privacidade-botao]").click()
    estado = pagina.locator("[data-testid=privacidade-estado]")
    limite = time.monotonic() + 15
    while time.monotonic() < limite and estado.inner_text() != "desligado":
        time.sleep(0.3)
    assert estado.inner_text() == "desligado"
    pagina.locator("[data-testid=privacidade-botao]").click()  # religa (sem confirmação)
    limite = time.monotonic() + 15
    while time.monotonic() < limite and estado.inner_text() != "ligado":
        time.sleep(0.3)
    assert estado.inner_text() == "ligado"


def test_diagnostico_mostra_o_runtime_ativo(pagina, servidor):
    """F5: a aba Diagnóstico diz qual runtime (e dispositivo) está executando cada modelo."""
    _abrir_camera_como(pagina, servidor, "technical", "Canteiro")
    _abrir_aba(pagina, "Diagnóstico")
    linha = pagina.locator("[data-testid=runtime-epi]")
    linha.wait_for(timeout=30_000)
    texto = linha.inner_text()
    assert re.search(r"PYTORCH|ONNX|OPENVINO", texto), texto


def test_relatorio_de_turno_abre(pagina, servidor):
    """F9: o relatório do turno abre (link da barra) e traz o título e os números."""
    entrar(pagina, servidor, "supervisor")
    pagina.get_by_role("button", name=re.compile(r"^Câmeras")).first.wait_for(timeout=30_000)  # login concluído
    pagina.goto(servidor.base + "/relatorio/turno")
    pagina.get_by_role("heading", name="Relatório de turno").wait_for(timeout=30_000)
