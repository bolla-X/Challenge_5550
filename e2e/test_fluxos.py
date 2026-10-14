"""Fluxos ponta a ponta da missão (seção 8). Ver e2e/conftest.py."""

from __future__ import annotations

import re
import time

from conftest import RAIZ, entrar


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


def _todas_ligadas(servidor) -> None:
    """Prova que o teste passou com as 4 câmeras de fixture ligadas (sem pausa de contorno)."""
    tecnico = servidor.sessao("technical")
    for nome in ("Multidão", "Canteiro", "Rede", "Queda"):
        estado = tecnico.get(f"{servidor.base}/api/cameras/{servidor.cameras[nome]}/status", timeout=10).json()
        assert estado.get("running"), f"câmera {nome} não estava ligada: {estado}"


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

    Fixture real (`next_queda`, domínio público): a pessoa fica no chão ~0,8 s
    (6,2–7,0 s do clipe de 20 s). A regra de emergência exige DUAS análises
    seguidas; com o vídeo aberto a gravação anda em tempo real e, com 4 câmeras
    numa máquina carregada, duas análises não cabem nesse 0,8 s (medido na
    rodada 4: 5 min, só avistamentos isolados). Sem ninguém vendo, a gravação
    anda na taxa útil (comportamento padrão, CHANGELOG do PR2) e a queda
    confirma. Por isso o teste espera na GRADE (sem tela de foco) e só depois
    abre a câmera para conferir o evento, com o ID, na aba "Quedas e postura".
    As 4 câmeras seguem ligadas o tempo todo.
    """
    tecnico = servidor.sessao("technical")
    entrar(pagina, servidor, "technical")
    queda = servidor.cameras["Queda"]
    tecnico.post(f"{servidor.base}/api/cameras/{queda}/stop", timeout=30)
    tecnico.post(f"{servidor.base}/api/cameras/{queda}/start", timeout=60).raise_for_status()
    limite = time.monotonic() + 300
    quedas: list = []
    while time.monotonic() < limite and not quedas:
        r = tecnico.get(f"{servidor.base}/alerts", params={"camera_id": queda, "feature": "falls", "limit": 5}, timeout=30)
        quedas = [a for a in r.json().get("items", []) if a.get("rule") == "fall_detected"]
        if not quedas:
            time.sleep(2)
    assert quedas, "nenhuma queda confirmada em 5 min com as 4 câmeras ligadas"
    _todas_ligadas(servidor)

    _abrir_camera(pagina, "Queda")
    _abrir_aba(pagina, "Quedas e postura")
    painel = pagina.locator("#panel-safety-events")
    linha = painel.get_by_text(re.compile(r"Queda detectada")).first
    linha.wait_for(timeout=30_000)
    assert "Pessoa" in painel.inner_text(), painel.inner_text()


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
    # Com mais de 3 pessoas com alerta, a lista agrupa por pessoa em grupos
    # recolhidos (alerts.tsx): abre o primeiro para o botão ficar visível.
    grupo_fechado = pagina.locator("details.alert-group:not([open]) > summary").first
    limite = time.monotonic() + 240
    while time.monotonic() < limite:
        if not botao.is_visible() and grupo_fechado.count():
            grupo_fechado.click()
        try:
            botao.wait_for(timeout=5_000)
        except Exception:  # noqa: BLE001  (grupo sumiu ou ainda sem alerta: tenta de novo)
            continue
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
    precedência sobre a de aproximação, como deve ser. As 4 câmeras seguem
    ligadas (rodízio ponderado, P0.1).
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
        _todas_ligadas(servidor)
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

    # Sai da página ANTES de limpar: uma requisição em andamento (polling) que
    # termina depois da limpeza devolve o cookie de sessão — visto na captura
    # da falha (a página voltou logada como técnico).
    pagina.goto("about:blank")
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


# Web Speech falsa (G6): grava o que seria falado. Headless não tem voz, e o
# teste precisa provar a frase, a voz pt-BR e o limite de taxa — não o áudio.
_FALA_FALSA = """
window.__falas = [];
const voz = {name: "Falsa pt-BR", lang: "pt-BR", localService: true, default: true, voiceURI: "falsa"};
const falsa = {
  speaking: false, pending: false, paused: false,
  getVoices() { return [voz]; },
  speak(u) {
    window.__falas.push({texto: u.text, lang: u.lang, t: Date.now()});
    this.speaking = true;
    setTimeout(() => { this.speaking = false; u.onend && u.onend(); }, 1500);
  },
  cancel() { this.speaking = false; },
  addEventListener() {}, removeEventListener() {},
};
Object.defineProperty(window, "speechSynthesis", {value: falsa, configurable: true});
window.SpeechSynthesisUtterance = function (texto) { this.text = texto; };
"""


def test_alerta_critico_e_falado_em_pt_br_sem_falar_por_cima(navegador, servidor):
    """G6: alerta crítico vira frase pt-BR com a câmera; intervalo mínimo entre frases."""
    contexto = navegador.new_context(viewport={"width": 1366, "height": 768})
    contexto.add_init_script(_FALA_FALSA)
    try:
        pagina = contexto.new_page()
        entrar(pagina, servidor, "technical")
        _abrir_camera(pagina, "Multidão")
        pagina.wait_for_function("window.__falas.length >= 1", timeout=180_000)
        time.sleep(20)
        falas = pagina.evaluate("window.__falas")
        assert all(f["lang"] == "pt-BR" for f in falas), falas
        assert falas[0]["texto"].startswith("Atenção: "), falas[0]
        # Fala alertas críticos de QUALQUER câmera (a frase diz qual), não só da aberta.
        nomes = tuple(servidor.cameras)
        assert any(f"na câmera {n}." in falas[0]["texto"] for n in nomes), falas[0]
        intervalos = [b["t"] - a["t"] for a, b in zip(falas, falas[1:], strict=False)]
        assert all(i >= 3_900 for i in intervalos), intervalos
        assert len({f["texto"] for f in falas}) == len(falas), "a mesma frase repetiu dentro de 30 s"

        # Mudo: nada mais é falado.
        pagina.get_by_role("button", name="Silenciar som de alertas").click()
        antes = pagina.evaluate("window.__falas.length")
        time.sleep(15)
        assert pagina.evaluate("window.__falas.length") == antes
    finally:
        contexto.close()


def test_portal_de_entrada_confirma_itens_e_libera(navegador, servidor):
    """G1: `/portal` mostra só os EPIs exigidos, item a item, e libera quando confirma."""
    tecnico = servidor.sessao("technical")
    cid = servidor.cameras["Canteiro"]
    assert tecnico.put(f"{servidor.base}/api/cameras/{cid}/gate", json={"required": ["helmet", "vest"]},
                       timeout=10).status_code == 200
    # Liberar exige 3 análises seguidas com tudo confirmado. As 4 câmeras
    # seguem ligadas: o portal mantém a câmera em foco (P0.1).
    contexto = navegador.new_context(viewport={"width": 1366, "height": 768})
    try:
        pagina = contexto.new_page()
        entrar(pagina, servidor, "technical")
        pagina.get_by_role("button", name=re.compile("Configurar")).first.wait_for(timeout=30_000)
        pagina.goto(f"{servidor.base}/portal?camera={cid}")
        portal = pagina.locator("[data-testid=portal]")
        portal.wait_for(timeout=30_000)
        # Só os exigidos aparecem.
        pagina.locator("[data-testid=portal-item-helmet]").wait_for(timeout=30_000)
        assert pagina.locator("[data-testid=portal-item-gloves]").count() == 0
        # Algum item chega a "confirmado" e, com tudo confirmado, "Liberado".
        inicio = time.monotonic()
        pagina.locator("[data-testid^=portal-item-][data-estado=confirmado]").first.wait_for(timeout=180_000)
        pagina.wait_for_function(
            "document.querySelector('[data-testid=portal]')?.dataset.veredito === 'approved'", timeout=240_000
        )
        # Tempo até "Liberado" com as 4 câmeras ligadas (resumo da MISSÃO 2).
        segundos = time.monotonic() - inicio
        print(f"\n[portal] Liberado em {segundos:.1f} s com 4 câmeras ligadas")
        (RAIZ / "bench" / "runtime" / "portal-liberado.txt").write_text(f"{segundos:.1f}\n", encoding="utf-8")
        assert pagina.locator("[data-testid=portal-titulo]").inner_text() == "Liberado"
        assert int(pagina.locator("[data-testid=portal-checkins]").inner_text().split()[0]) >= 1
        _todas_ligadas(servidor)
    finally:
        contexto.close()
        tecnico.put(f"{servidor.base}/api/cameras/{cid}/gate", json={"required": None}, timeout=10)


def test_modo_tv_mostra_setores_e_metas_do_supervisor(navegador, servidor):
    """G8: `/tv` mostra um bloco por setor; meta só o supervisor define (técnico: 403)."""
    assert servidor.sessao("technical").put(f"{servidor.base}/api/tv/metas/Canteiro",
                                            json={"minutos_conformes": 5}, timeout=10).status_code == 403
    r = servidor.sessao("supervisor").put(f"{servidor.base}/api/tv/metas/Canteiro",
                                          json={"minutos_conformes": 120, "checkins_portal": 10}, timeout=10)
    assert r.status_code == 200, r.text
    contexto = navegador.new_context(viewport={"width": 1920, "height": 1080})
    try:
        pagina = contexto.new_page()
        entrar(pagina, servidor, "supervisor")
        pagina.get_by_role("button", name=re.compile(r"^Câmeras")).first.wait_for(timeout=30_000)
        pagina.goto(f"{servidor.base}/tv")
        bloco = pagina.locator('[data-testid="tv-setor-Canteiro"]')
        bloco.wait_for(timeout=30_000)
        assert "/ 120" in bloco.inner_text()
        texto = pagina.locator("[data-testid=tv]").inner_text()
        assert "Pessoa " not in texto, "o Modo TV não mostra nada por pessoa"
    finally:
        contexto.close()


def test_rotular_recorte_com_teclado_e_exportar_zip(pagina, servidor):
    """G9: recorte duvidoso chega à fila, → confirma, e o zip YOLO traz o rótulo."""
    import io
    import zipfile

    entrar(pagina, servidor, "technical")
    pagina.get_by_role("button", name=re.compile("Configurar")).first.wait_for(timeout=30_000)
    pagina.goto(f"{servidor.base}/rotular")
    item = pagina.locator("[data-testid=rotular-item]")
    item.wait_for(timeout=240_000)
    ident = item.get_attribute("data-id")
    pagina.keyboard.press("ArrowRight")
    pagina.wait_for_function(
        f"document.querySelector('[data-testid=rotular-item]')?.dataset.id !== '{ident}'", timeout=30_000
    )
    zipado = servidor.sessao("technical").get(f"{servidor.base}/api/rotulos/dataset.zip", timeout=30)
    assert zipado.status_code == 200
    with zipfile.ZipFile(io.BytesIO(zipado.content)) as z:
        assert f"labels/train/{ident}.txt" in z.namelist()
        assert "data.yaml" in z.namelist()
    assert servidor.sessao("operator").get(f"{servidor.base}/api/rotulos/proximo", timeout=10).status_code == 403


def test_planta_baixa_calibra_com_8_cliques_e_mostra_pes(pagina, servidor):
    """G5: 4 cliques no chão do vídeo + 4 na planta → pés das pessoas ao vivo na planta."""
    cid = servidor.cameras["Multidão"]
    try:
        _abrir_camera_como(pagina, servidor, "technical", "Multidão")
        _abrir_aba(pagina, "Planta")
        video = pagina.locator("[data-testid=planta-video]")
        mapa = pagina.locator("[data-testid=planta-mapa-calibracao]")
        video.wait_for(timeout=30_000)
        for alvo, pontos in ((video, [(0.05, 0.55), (0.95, 0.55), (0.98, 0.98), (0.02, 0.98)]),
                             (mapa, [(0.1, 0.1), (0.9, 0.1), (0.9, 0.9), (0.1, 0.9)])):
            caixa = alvo.bounding_box()
            for x, y in pontos:
                pagina.mouse.click(caixa["x"] + x * caixa["width"], caixa["y"] + y * caixa["height"])
        pagina.get_by_role("button", name="Salvar calibração").click()
        pagina.locator("[data-testid=planta-ao-vivo]").wait_for(timeout=30_000)
        pagina.locator("[data-testid=planta-pe]").first.wait_for(timeout=120_000)
    finally:
        servidor.sessao("technical").put(f"{servidor.base}/api/cameras/{cid}/planta",
                                         json={"pontos_camera": None}, timeout=10)


def test_voce_vs_ia_mostra_placar_honesto(pagina, servidor):
    """G2: rodada "pegadinha" (ninguém sem capacete): sem clicar, a pessoa acerta tudo; o placar mostra a IA também."""
    entrar(pagina, servidor, "technical")
    pagina.get_by_role("button", name=re.compile("Configurar")).first.wait_for(timeout=30_000)
    pagina.goto(f"{servidor.base}/desafio")
    pagina.locator("[data-testid=desafio-comecar]").click(timeout=30_000)
    pagina.locator("[data-testid=desafio-responder]").click(timeout=60_000)
    pagina.locator("[data-testid=desafio-resultado]").wait_for(timeout=120_000)
    humano = pagina.locator("[data-testid=desafio-linha-humano]").inner_text()
    assert "0 / 0" in humano, humano  # canteiro-94: ninguém sem capacete
    assert pagina.locator("[data-testid=desafio-linha-ia]").count() == 1
    assert "1 rodada" in pagina.locator("[data-testid=desafio-placar]").inner_text()


def test_prova_de_escala_sobe_cameras_virtuais_e_remove(pagina, servidor):
    """F10: câmeras virtuais com workers reais mostram números desta máquina e somem no fim."""
    entrar(pagina, servidor, "technical")
    pagina.get_by_role("button", name="Prova de escala").click(timeout=30_000)
    dialogo = pagina.get_by_role("dialog")
    dialogo.get_by_label("Câmeras").fill("2")
    dialogo.get_by_role("button", name="Iniciar").click()
    linhas = dialogo.locator("table.escala-tabela tbody tr:not(.escala-media)")
    try:
        pagina.wait_for_function(
            """() => [...document.querySelectorAll('table.escala-tabela tbody tr:not(.escala-media)')]
                     .filter(tr => parseFloat(tr.children[2].textContent) > 0).length >= 2""",
            timeout=120_000,
        )
        assert linhas.count() == 2
    finally:
        dialogo.get_by_role("button", name="Encerrar e remover").click()
    linhas.first.wait_for(state="detached", timeout=60_000)
