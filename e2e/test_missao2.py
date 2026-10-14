"""Fluxos ponta a ponta da MISSÃO 2 (X1–X10). Mesmo servidor e câmeras do e2e/conftest.py."""

from __future__ import annotations

import re
import time

from conftest import RAIZ, entrar

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


def _abrir_foco(pagina, nome):
    pagina.get_by_role("button", name=f"Configurar {nome}").click(timeout=30_000)


def _aba(pagina, rotulo):
    aba = pagina.get_by_role("tab", name=rotulo)
    if aba.count():
        aba.click()
        return
    pagina.locator(".tabs-more > button").click()
    pagina.get_by_role("menuitem", name=rotulo).click()


def test_multidao_mostra_no_maximo_um_incidente_por_regra_e_zona(navegador, servidor):
    """P0.2: com TODOS os EPIs exigidos, a aba de alertas agrupa por (regra, zona), com os IDs."""
    contexto, pagina = _logado(navegador, servidor, viewport=(1366, 768))
    try:
        _abrir_foco(pagina, "Multidão")
        _aba(pagina, "Alertas")
        pagina.locator("[data-testid=incidente]").first.wait_for(timeout=240_000)
        time.sleep(4)
        resumos = pagina.locator("[data-testid=incidente]")
        chaves = [(r.get_attribute("data-titulo"), r.get_attribute("data-zona")) for r in resumos.all()]
        assert len(chaves) == len(set(chaves)), chaves
        # A pílula do vídeo mostra o incidente com os IDs de rastreio.
        pilula = pagina.locator("[data-testid=pilula-incidente]")
        pilula.wait_for(timeout=60_000)
        assert "Pessoa" in pilula.inner_text()
    finally:
        contexto.close()


def test_simulador_reprocessa_e_nunca_muda_alerta_real(navegador, servidor):
    """X2: reprocessar com outra regra mostra o simulado lado a lado com o real; os alertas reais não mudam."""
    tecnico = servidor.sessao("technical")
    cid = servidor.cameras["Multidão"]
    contexto, pagina = _logado(navegador, servidor)
    try:
        pagina.goto(f"{servidor.base}/simulador?camera={cid}")
        botao = pagina.locator("[data-testid=sim-rodar]")
        botao.wait_for(timeout=30_000)
        limite = time.monotonic() + 120
        while time.monotonic() < limite and botao.is_disabled():
            pagina.reload()
            botao.wait_for(timeout=30_000)
            time.sleep(3)
        reais_antes = tecnico.get(f"{servidor.base}/alerts?camera_id={cid}&limit=500", timeout=10).json()["count"]
        botao.click()
        pagina.locator("[data-testid=sim-numeros]").wait_for(timeout=60_000)
        pagina.locator("[data-testid=sim-linha]").wait_for()
        # Desliga todos os EPIs e a zona: a proposta não dispara nada.
        ligados = pagina.locator(".sim-chips .chip-toggle.on")
        while ligados.count():
            ligados.first.click()
        caixa = pagina.get_by_label(re.compile("Zona de risco"))
        if caixa.is_checked():
            caixa.uncheck()
        botao.click()
        pagina.wait_for_function("document.querySelector('[data-testid=sim-total]')?.dataset.valor === '0'", timeout=30_000)
        reais_depois = tecnico.get(f"{servidor.base}/alerts?camera_id={cid}&limit=500", timeout=10).json()["count"]
        assert reais_depois >= reais_antes  # o simulador nunca apaga nem resolve alerta real
        assert int(pagina.locator("[data-testid=sim-real]").get_attribute("data-valor")) >= 0
        assert servidor.sessao("operator").get(f"{servidor.base}/api/simulador/contexto?camera_id={cid}", timeout=10).status_code == 403
    finally:
        contexto.close()


def test_incidente_linha_causal_e_custodia_integra(navegador, servidor):
    """X3 + X4: o detalhe do incidente narra o que aconteceu com o ID e a cadeia de custódia fecha."""
    contexto, pagina = _logado(navegador, servidor, viewport=(1366, 768))
    try:
        _abrir_foco(pagina, "Multidão")
        _aba(pagina, "Alertas")
        pagina.locator("[data-testid=incidente-abrir]").first.click(timeout=240_000)
        detalhe = pagina.locator("[data-testid=incidente-detalhe]")
        detalhe.wait_for(timeout=10_000)
        passos = pagina.locator("[data-testid=linha-causal] li")
        passos.first.wait_for(timeout=30_000)
        assert re.search(r"apareceu|entrou|estava na|aproximou", passos.first.inner_text()), passos.first.inner_text()
        pagina.locator("[data-testid=verificar-integridade]").click()
        resultado = pagina.locator("[data-testid=custodia-resultado]")
        resultado.wait_for(timeout=30_000)
        assert "Adulteração" not in resultado.inner_text(), resultado.inner_text()
        assert resultado.get_attribute("data-integra") == "1", resultado.inner_text()
        # "ver quadro" abre o replay parado no instante do passo.
        ver = pagina.get_by_role("button", name="ver quadro").first
        if ver.count():
            ver.click()
            pagina.locator('canvas[aria-label="Replay do incidente"]').wait_for(timeout=30_000)
    finally:
        contexto.close()


def test_auditoria_verifica_a_cadeia_inteira(navegador, servidor):
    contexto, pagina = _logado(navegador, servidor)
    try:
        pagina.goto(f"{servidor.base}/auditoria")
        pagina.locator(".auditoria-tabela tbody tr").first.wait_for(timeout=60_000)
        pagina.locator("[data-testid=verificar-integridade]").click()
        resultado = pagina.locator("[data-testid=custodia-resultado]")
        resultado.wait_for(timeout=60_000)
        assert "Adulteração" not in resultado.inner_text()
    finally:
        contexto.close()


def test_raio_x_liga_pela_tecla_x(navegador, servidor):
    """X5: tecla X liga a camada que separa a confiança do modelo da decisão do sistema."""
    contexto, pagina = _logado(navegador, servidor, viewport=(1366, 768))
    try:
        _abrir_foco(pagina, "Multidão")
        video = pagina.locator("canvas.live-video").first
        video.wait_for(timeout=30_000)
        pagina.keyboard.press("x")
        pagina.wait_for_function("document.querySelector('canvas.live-video')?.dataset.raiox === '1'", timeout=60_000)
        assert pagina.locator("[data-testid=raiox-botao]").get_attribute("aria-pressed") == "true"
        pagina.keyboard.press("x")
        pagina.wait_for_function("document.querySelector('canvas.live-video')?.dataset.raiox === '0'", timeout=30_000)
    finally:
        contexto.close()


def test_palco_pelo_teclado_e_pelo_celular(navegador, playwright_sessao, servidor):
    """X6: todas as cenas pelo teclado; o celular (Chromium emulando celular) avança e volta pelo token do QR."""
    contexto, pagina = _logado(navegador, servidor)
    try:
        pagina.goto(f"{servidor.base}/palco")
        palco = pagina.locator("[data-testid=palco]")
        palco.wait_for(timeout=30_000)
        for _ in range(20):
            pagina.keyboard.press("ArrowLeft")
        pagina.wait_for_function("document.querySelector('[data-testid=palco]')?.dataset.cena === '0'", timeout=15_000)
        total = int(pagina.locator(".palco-indice").inner_text().split("/")[1])
        vistos = []
        for i in range(1, total):
            pagina.keyboard.press("ArrowRight")
            try:
                pagina.wait_for_function(f"document.querySelector('[data-testid=palco]')?.dataset.cena === '{i}'", timeout=15_000)
            except Exception as exc:
                foco = pagina.evaluate("document.activeElement && document.activeElement.outerHTML.slice(0, 200)")
                raise AssertionError(f"cena {i} não veio; tela em {palco.get_attribute('data-cena')} "
                                     f"({palco.get_attribute('data-chave')}), foco em {foco}") from exc
            pagina.locator("[data-testid=palco-cena]").wait_for()
            vistos.append(palco.get_attribute("data-chave"))
            time.sleep(1.5)
        assert len(set(vistos)) == total - 1
        assert not [e for e in pagina.erros_console if "Error" in e], pagina.erros_console

        url = pagina.locator("[data-testid=palco-qr]").get_attribute("data-url")
        caminho = url[url.index("/palco/controle"):]
        celular = navegador.new_context(**playwright_sessao.devices["Pixel 7"])
        try:
            fone = celular.new_page()
            fone.goto(servidor.base + caminho)
            fone.locator("[data-testid=controle-cena]").wait_for(timeout=30_000)
            fone.locator("[data-testid=controle-anterior]").click()
            pagina.wait_for_function(f"document.querySelector('[data-testid=palco]')?.dataset.cena === '{total - 2}'", timeout=15_000)
            fone.locator("[data-testid=controle-anterior]").click()
            pagina.wait_for_function(f"document.querySelector('[data-testid=palco]')?.dataset.cena === '{total - 3}'", timeout=15_000)
            fone.locator("[data-testid=controle-proxima]").click()
            pagina.wait_for_function(f"document.querySelector('[data-testid=palco]')?.dataset.cena === '{total - 2}'", timeout=15_000)
            assert fone.locator("[data-testid=controle-cena]").inner_text() == pagina.locator("[data-testid=palco-titulo]").inner_text()
        finally:
            celular.close()
        # Celular fora: o teclado continua mandando.
        pagina.keyboard.press("ArrowRight")
        pagina.wait_for_function(f"document.querySelector('[data-testid=palco]')?.dataset.cena === '{total - 1}'", timeout=15_000)
        for _ in range(20):
            pagina.keyboard.press("ArrowLeft")
        pagina.wait_for_function("document.querySelector('[data-testid=palco]')?.dataset.cena === '0'", timeout=15_000)
    finally:
        contexto.close()


def test_palco_queda_ao_vivo_em_camera_lenta(navegador, servidor):
    """ADENDO 2: a cena "Queda" toca a gravação a 0,25× com o rótulo sobre o vídeo, e o alerta sai ao vivo."""
    contexto, pagina = _logado(navegador, servidor)
    tecnico = servidor.sessao("technical")
    try:
        roteiro = tecnico.get(f"{servidor.base}/api/palco/roteiro", timeout=10).json()
        indice = next(i for i, c in enumerate(roteiro["cenas"]) if c["chave"] == "queda")
        assert roteiro["cenas"][indice]["camera_id"] == servidor.cameras["Queda"]
        pagina.goto(f"{servidor.base}/palco")
        pagina.locator("[data-testid=palco]").wait_for(timeout=30_000)
        inicio = time.monotonic()
        assert tecnico.post(f"{servidor.base}/api/palco/ir", json={"acao": "ir", "indice": indice}, timeout=10).ok
        pagina.wait_for_function("document.querySelector('[data-testid=palco]')?.dataset.chave === 'queda'", timeout=15_000)
        rotulo = pagina.locator("[data-testid=palco-velocidade]")
        rotulo.wait_for(timeout=15_000)
        assert rotulo.inner_text() == "GRAVAÇÃO · 0,25×"
        # O alerta de queda aparece AO VIVO, na pílula sobre o vídeo da cena.
        pilula = pagina.locator("[data-testid=pilula-incidente]", has_text="Queda")
        pilula.wait_for(timeout=120_000)
        segundos = time.monotonic() - inicio
        print(f"\n[palco] queda ao vivo a 0,25× em {segundos:.1f} s desde entrar na cena")
        # O rótulo continua sobre o vídeo no instante do alerta.
        assert rotulo.is_visible() and rotulo.inner_text() == "GRAVAÇÃO · 0,25×"
        caixa_video = pagina.locator("[data-testid=palco-video]").bounding_box()
        caixa_rotulo = rotulo.bounding_box()
        assert caixa_video["x"] <= caixa_rotulo["x"]
        assert caixa_rotulo["y"] + caixa_rotulo["height"] <= caixa_video["y"] + caixa_video["height"]
        # Continuação da cena: o replay do incidente entra ao lado.
        pagina.locator(".palco-queda-replay").wait_for(timeout=15_000)
        pasta = RAIZ / "bench" / "runtime" / "e2e-capturas"
        pasta.mkdir(parents=True, exist_ok=True)
        pagina.screenshot(path=str(pasta / "palco-queda-camera-lenta.png"))
        # Saindo da cena, a gravação volta a 1×.
        tecnico.post(f"{servidor.base}/api/palco/ir", json={"acao": "proxima"}, timeout=10)
        video = tecnico.get(f"{servidor.base}/api/cameras/{servidor.cameras['Queda']}/status", timeout=10).json()["video"]
        assert video["velocidade"] == 1.0
        assert not [e for e in pagina.erros_console if "Error" in e], pagina.erros_console
    finally:
        tecnico.post(f"{servidor.base}/api/palco/ir", json={"acao": "ir", "indice": 0}, timeout=10)
        contexto.close()


def test_retrospectiva_exporta_card_em_png(navegador, servidor):
    """X7: stories com dados reais; cada card vira um PNG 1080×1350."""
    import struct

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
        dados = open(baixado.value.path(), "rb").read()
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


def test_liga_missao_cumprida_celebra_e_pontua_o_setor(navegador, servidor):
    """X8: missão configurada pelo supervisor; um rótulo revisado cumpre, a tela celebra; ponto vai para o setor."""
    supervisor = servidor.sessao("supervisor")
    # Alvo = o que já foi feito neste turno + 1 (outro teste pode ter revisado um recorte antes).
    sonda = supervisor.post(f"{servidor.base}/api/liga/missoes", json={"titulo": "sonda", "tipo": "rotulo", "alvo": 10000},
                            timeout=10).json()["missao"]["id"]
    feitos = next(m["feito"] for m in supervisor.get(f"{servidor.base}/api/liga", timeout=10).json()["missoes"] if m["id"] == sonda)
    supervisor.delete(f"{servidor.base}/api/liga/missoes/{sonda}", timeout=10)
    r = supervisor.post(f"{servidor.base}/api/liga/missoes",
                        json={"titulo": "Revisar mais 1 recorte (E2E)", "tipo": "rotulo", "alvo": feitos + 1}, timeout=10)
    assert r.status_code == 201, r.text
    missao_id = r.json()["missao"]["id"]
    assert servidor.sessao("technical").post(f"{servidor.base}/api/liga/missoes", json={"titulo": "x", "tipo": "rotulo", "alvo": 1},
                                             timeout=10).status_code == 403
    contexto, pagina = _logado(navegador, servidor, papel="supervisor")
    try:
        pagina.goto(f"{servidor.base}/liga")
        pagina.locator("[data-testid=liga-placar]").wait_for(timeout=30_000)
        time.sleep(6)  # primeira leitura (sem celebração)
        tecnico = servidor.sessao("technical")
        limite = time.monotonic() + 240
        item = None
        while time.monotonic() < limite:
            resposta = tecnico.get(f"{servidor.base}/api/rotulos/proximo", timeout=10)
            if resposta.status_code == 200 and (resposta.json() or {}).get("item"):
                item = resposta.json()["item"]
                break
            time.sleep(3)
        assert item, "nenhum recorte chegou à fila"
        assert tecnico.post(f"{servidor.base}/api/rotulos/{item['id']}", json={"decisao": "confirmar"}, timeout=10).status_code == 200
        aviso = pagina.locator(".liga-aviso")
        aviso.wait_for(timeout=30_000)
        assert "Missão cumprida" in aviso.inner_text()
        estado = supervisor.get(f"{servidor.base}/api/liga", timeout=10).json()
        assert any(m["id"] == missao_id and m["cumprida"] for m in estado["missoes"])
        assert sum(s["pontos"] for s in estado["setores"]) > 0
    finally:
        contexto.close()
        supervisor.delete(f"{servidor.base}/api/liga/missoes/{missao_id}", timeout=10)


def test_tente_enganar_a_ia_mostra_o_veredito_e_o_placar(navegador, servidor):
    """X9: tentativa no portal com o Raio-X; o resultado diz com honestidade se enganou ou foi pego."""
    tecnico = servidor.sessao("technical")
    cid = servidor.cameras["Canteiro"]
    tecnico.put(f"{servidor.base}/api/cameras/{cid}/gate", json={"required": ["helmet", "vest"]}, timeout=10)
    contexto, pagina = _logado(navegador, servidor, viewport=(1366, 768))
    try:
        pagina.goto(f"{servidor.base}/portal?camera={cid}&desafio=1")
        pagina.locator("[data-testid=enganar]").wait_for(timeout=30_000)
        pagina.locator("[data-testid^=portal-item-][data-estado=confirmado]").first.wait_for(timeout=180_000)
        pagina.locator("[data-testid=enganar-bone]").click()
        pagina.locator("[data-testid=enganar-comecar]").click()
        resultado = pagina.locator("[data-testid=enganar-resultado]")
        resultado.wait_for(timeout=30_000)
        assert resultado.get_attribute("data-resultado") in ("enganou", "pegou")
        assert pagina.locator("[data-testid=enganar-placar] dd").first.get_attribute("data-valor") == "1"
        assert pagina.locator(".portal-explicacao").count() >= 1
        assert pagina.locator("canvas.live-video").first.get_attribute("data-raiox") == "1"
    finally:
        contexto.close()
        tecnico.put(f"{servidor.base}/api/cameras/{cid}/gate", json={"required": None}, timeout=10)


def test_pwa_instala_e_avisa_alerta_critico(navegador, servidor):
    """X10: manifesto e service worker (contexto seguro: localhost) e aviso local de alerta crítico com o app aberto."""
    contexto = navegador.new_context(viewport={"width": 1366, "height": 768})
    contexto.grant_permissions(["notifications"], origin=servidor.base)
    # O Chromium headless responde "denied" a Notification.permission mesmo com a
    # permissão concedida (não há onde mostrar a notificação). O teste então simula
    # um navegador que permitiu e grava as chamadas a showNotification — prova o
    # caminho do NOSSO código; a exibição é do sistema operacional.
    contexto.add_init_script("""
        Object.defineProperty(Notification, 'permission', {get: () => 'granted', configurable: true});
        window.__mostradas = [];
        const original = ServiceWorkerRegistration.prototype.showNotification;
        ServiceWorkerRegistration.prototype.showNotification = function (titulo, opcoes) {
            window.__mostradas.push({titulo, tag: opcoes && opcoes.tag});
            return Promise.resolve();
        };
    """)
    try:
        pagina = contexto.new_page()
        entrar(pagina, servidor, "technical")
        pagina.get_by_role("button", name=re.compile("Configurar")).first.wait_for(timeout=60_000)
        escopo = pagina.evaluate("navigator.serviceWorker.ready.then(r => r.scope)")
        assert escopo == servidor.base + "/"
        manifesto = pagina.evaluate("fetch('/manifest.webmanifest').then(r => r.json())")
        assert manifesto["display"] == "standalone"
        assert pagina.locator("[data-testid=notificacoes]").get_attribute("data-estado") == "granted"
        _abrir_foco(pagina, "Multidão")
        pagina.wait_for_function("(window.__mostradas || []).length >= 1", timeout=240_000)
        primeira = pagina.evaluate("window.__mostradas[0]")
        assert primeira["titulo"].startswith("Alerta crítico"), primeira
    finally:
        contexto.close()
