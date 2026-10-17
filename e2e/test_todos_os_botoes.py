"""Crawler "botão a botão" (MISSÃO 4, Fase 1 item 2 e Fase 5 item 2).

Para cada papel (sem sessão, operador, técnico, supervisor) e cada rota, enumera
todo elemento interativo VISÍVEL (botão, link, aba, toggle, item de menu, item
do command palette) e aciona um por um. Cada um precisa causar um efeito
verificável:

- navegação (URL muda) ou nova aba;
- download;
- requisição à API respondida com sucesso;
- mudança de estado na tela (diálogo/menu aberto, aria-expanded/pressed/selected,
  itens novos, tema, foco levado a um campo inválido).

Sem efeito, só vale se estiver DESABILITADO com explicação (title,
aria-describedby ou texto de ajuda). Também é bug: erro no console, resposta
4xx/5xx inesperada e texto cortado sem reticências.

Este arquivo roda por último na suíte (ordem alfabética) porque aciona botões
que mudam estado global (pausar câmera, privacidade, recursos); ao fim de cada
rota as câmeras voltam a ser ligadas pela API.

Resultado por rota em `bench/runtime/crawler/*.json`; o último teste consolida
a matriz rota × papel × resultado em `docs/NEXT2026/QA.md`.

Variáveis: `E2E_CRAWLER_TEMAS=light,dark` (padrão: light) e
`E2E_CRAWLER_ROTAS=grade,tv` para rodar só algumas rotas.
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

import pytest

from conftest import RAIZ

SAIDA = RAIZ / "bench" / "runtime" / "crawler"
QA_MD = RAIZ / "docs" / "NEXT2026" / "QA.md"

SELETOR = ("button, a[href], [role=tab], [role=switch], [role=menuitem], [role=menuitemradio], [role=checkbox], "
           "input[type=checkbox], input[type=radio], summary, select, [role=option]")

# Elementos que NÃO são acionados no loop genérico, com o motivo. Cada entrada
# é coberta por um teste dedicado (citado) ou pelo passo final da rota.
NAO_ACIONAR: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^Sair$|^Saindo"), "acionado ao fim da rota (encerra a sessão): test_sair_encerra_a_sessao"),
    (re.compile(r"(?i)\b(excluir|remover|apagar)\b.*\b(c[âa]mera|usu[áa]ri|conta)"),
     "destrutivo sobre dados da suíte: coberto por tests/test_cameras_api.py e tests/test_auth.py"),
    (re.compile(r"(?i)^desativar\b|redefinir senha|trocar senha|revogar"),
     "destrutivo sobre contas da suíte: coberto por tests/test_auth_revogacao.py"),
    (re.compile(r"(?i)reiniciar a demo|resetar a demo"), "reinicia o servidor da demo: coberto por tests/test_demo.py"),
]

# Respostas 4xx esperadas (não são bug): login sem sessão consulta /api/auth/me.
RESPOSTAS_ESPERADAS = [
    (re.compile(r"/api/auth/me$"), {401}),
]

JS_ENUMERAR = """(sel) => {
  const vis = (el) => {
    const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && s.opacity !== '0';
  };
  const nome = (el) => {
    const lb = el.getAttribute('aria-labelledby');
    const porId = lb ? lb.split(/\\s+/).map((i) => document.getElementById(i)?.innerText || '').join(' ') : '';
    return (el.getAttribute('aria-label') || porId || el.innerText || el.getAttribute('title') || el.value
            || el.querySelector('img')?.alt || '').replace(/\\s+/g, ' ').trim().slice(0, 80);
  };
  const vistos = {};
  return [...document.querySelectorAll(sel)].filter(vis).filter((el) => !el.closest('[aria-hidden=true],[inert]'))
    .map((el) => {
      const papel = el.getAttribute('role') || el.tagName.toLowerCase();
      const n = nome(el);
      const base = papel + '|' + n;
      vistos[base] = (vistos[base] || 0) + 1;
      const desc = el.getAttribute('aria-describedby');
      const explicacao = (el.getAttribute('title') || (desc ? (document.getElementById(desc)?.innerText || '') : '')
                          || el.getAttribute('data-motivo') || '').trim();
      const desabilitado = el.disabled === true || el.getAttribute('aria-disabled') === 'true';
      const s = getComputedStyle(el);
      const cortado = el.scrollWidth > el.clientWidth + 2 && ['hidden', 'clip'].includes(s.overflowX)
                      && s.textOverflow !== 'ellipsis' && el.children.length === 0;
      return {chave: base + '#' + vistos[base], papel, nome: n, desabilitado, explicacao, cortado,
              href: el.getAttribute('href'), alvo: el.getAttribute('target'), download: el.hasAttribute('download')};
    });
}"""

JS_ASSINATURA_LEVE = """() => {
  const vis = (el) => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  return JSON.stringify({u: location.pathname + location.search,
    camadas: document.querySelectorAll('[role=dialog],dialog[open],[role=alertdialog],[role=menu],[role=listbox],[cmdk-root]').length,
    titulos: [...document.querySelectorAll('h1,h2')].filter(vis).map((e) => e.innerText.trim()).join('|')});
}"""

JS_ASSINATURA = """(sel) => {
  const vis = (el) => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const itens = [...document.querySelectorAll(sel)].filter(vis)
    .map((e) => (e.getAttribute('aria-label') || e.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 40));
  const estados = [...document.querySelectorAll('[aria-expanded],[aria-pressed],[aria-selected],[aria-checked],[aria-current],'
                    + 'input[type=checkbox],input[type=radio],details,select')]
    .map((e) => [e.getAttribute('aria-expanded'), e.getAttribute('aria-pressed'), e.getAttribute('aria-selected'),
                 e.getAttribute('aria-checked'), e.getAttribute('aria-current'), e.checked, e.open, e.value].join());
  const camadas = document.querySelectorAll('[role=dialog],dialog[open],[role=alertdialog],[role=menu],[role=listbox],'
                    + '[role=tooltip],[cmdk-root],.toast,[data-sonner-toast]').length;
  const titulos = [...document.querySelectorAll('h1,h2,h3,[role=heading]')].filter(vis).map((e) => e.innerText.trim()).join('|');
  const a = document.activeElement;
  const campo = a && ['INPUT', 'TEXTAREA', 'SELECT'].includes(a.tagName);
  const foco = campo ? (a.name || a.id || a.getAttribute('aria-label') || a.tagName) : '';
  const raiz = document.documentElement;
  return JSON.stringify({u: location.pathname + location.search + location.hash, itens: itens.join('|'), estados: estados.join('|'),
    camadas, titulos, foco, tema: raiz.dataset.theme || '', classes: raiz.className + '|' + document.body.className,
    invalidos: document.querySelectorAll(':invalid').length, rolagem: Math.round(window.scrollY / 50)});
}"""


def _temas() -> list[str]:
    return [t.strip() for t in os.environ.get("E2E_CRAWLER_TEMAS", "light").split(",") if t.strip()]


def _rotas_por_papel(servidor) -> dict[str, list[tuple[str, str, str | None]]]:
    """(nome, url, preparo) — `preparo` é o rótulo do botão que leva à tela de estado interno (sem URL própria)."""
    multidao, canteiro = servidor.cameras["Multidão"], servidor.cameras["Canteiro"]
    comuns_tela_cheia = [
        ("tv", "/tv", None),
        ("gemeo", "/gemeo", None),
        ("gemeo-2d", "/gemeo?2d=1", None),
        ("liga", "/liga", None),
        ("retrospectiva", "/retrospectiva", None),
        ("palco", "/palco", None),
        ("portal", f"/portal?camera={canteiro}", None),
        ("desafio", "/desafio", None),
        ("rotular", "/rotular", None),
        ("simulador", f"/simulador?camera={multidao}", None),
        ("auditoria", "/auditoria", None),
    ]
    painel = [
        ("grade", "/", None),
        ("foco-canteiro", "/", "Configurar Canteiro"),
        ("foco-multidao", "/", "Configurar Multidão"),
    ]
    return {
        "sem_sessao": [("login", "/", None), ("palco-controle-sem-token", "/palco/controle", None)],
        "operator": [("kiosk", "/", None)] + comuns_tela_cheia,
        "technical": painel + comuns_tela_cheia,
        "supervisor": painel + [("inicio-supervisor", "/", "__inicio__")] + comuns_tela_cheia,
    }


def _casos():
    # Os nomes das rotas dependem do servidor; aqui só o produto papel × tema.
    return [(papel, tema) for papel in ("sem_sessao", "operator", "technical", "supervisor") for tema in _temas()]


def _resposta_esperada(url: str, status: int) -> bool:
    return any(p.search(url) and status in codigos for p, codigos in RESPOSTAS_ESPERADAS)


class Rastro:
    """Coleta console, respostas e popups de UMA página."""

    def __init__(self, pagina) -> None:
        self.erros_console: list[str] = []
        self.respostas: list[tuple[str, str, int, float]] = []
        self.dialogos = 0
        self.downloads = 0
        self.em_voo = 0
        pagina.on("request", self._saiu)
        pagina.on("requestfinished", self._chegou)
        pagina.on("requestfailed", self._chegou)
        pagina.on("console", lambda m: self.erros_console.append(m.text[:300]) if m.type == "error" else None)
        pagina.on("pageerror", lambda e: self.erros_console.append(f"pageerror: {str(e)[:300]}"))
        pagina.on("response", self._resposta)
        pagina.on("dialog", self._dialogo)
        pagina.on("download", self._download)

    @staticmethod
    def _conta(r) -> bool:
        return "/api/" in r.url and "/video_feed" not in r.url and "/socket.io/" not in r.url

    def _saiu(self, r) -> None:
        if self._conta(r):
            self.em_voo += 1

    def _chegou(self, r) -> None:
        if self._conta(r):
            self.em_voo = max(0, self.em_voo - 1)

    def esperar_rede(self, pagina, limite_s: float = 6.0) -> None:
        """Não recarrega a tela com requisição pendente: abortá-la viraria erro de console do crawler, não do app."""
        fim = time.monotonic() + limite_s
        while self.em_voo and time.monotonic() < fim:
            pagina.wait_for_timeout(100)

    def _resposta(self, r) -> None:
        url = r.url
        if "/socket.io/" in url or url.endswith((".js", ".css", ".woff2", ".png", ".svg", ".webp")):
            return
        self.respostas.append((r.request.method, url, r.status, time.monotonic()))

    def _dialogo(self, d) -> None:
        self.dialogos += 1
        d.dismiss()

    def _download(self, _d) -> None:
        self.downloads += 1


def _login(pagina, servidor, papel: str) -> None:
    pagina.goto(servidor.base + "/")
    pagina.get_by_label("E-mail").wait_for(timeout=60_000)
    pagina.get_by_label("E-mail").fill(servidor.emails[papel])
    pagina.get_by_label("Senha").fill(servidor.senhas[papel])
    pagina.get_by_role("button", name="Entrar").click()
    pagina.locator("main#conteudo").wait_for(timeout=60_000)
    pagina.wait_for_function("() => !document.querySelector('input[type=password]')", timeout=60_000)


def _abrir(pagina, servidor, url: str, preparo: str | None) -> None:
    pagina.goto(servidor.base + url)
    pagina.wait_for_load_state("domcontentloaded")
    pagina.wait_for_timeout(2500)
    if preparo == "__inicio__":
        botao = pagina.get_by_role("button", name=re.compile(r"Início"))
        if botao.count():
            botao.first.click()
            pagina.wait_for_timeout(1500)
    elif preparo:
        pagina.get_by_role("button", name=preparo).click(timeout=30_000)
        pagina.wait_for_timeout(2500)


def _localizar(pagina, chave: str):
    """Encontra de novo o elemento pela chave estável `papel|nome#ordem`."""
    papel_nome, ordem = chave.rsplit("#", 1)
    alvo_ordem = int(ordem)
    indice = pagina.evaluate(
        """([sel, alvo, ordem]) => {
          const vis = (el) => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
            return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && s.opacity !== '0'; };
          const nome = (el) => { const lb = el.getAttribute('aria-labelledby');
            const porId = lb ? lb.split(/\\s+/).map((i) => document.getElementById(i)?.innerText || '').join(' ') : '';
            return (el.getAttribute('aria-label') || porId || el.innerText || el.getAttribute('title') || el.value
                    || el.querySelector('img')?.alt || '').replace(/\\s+/g, ' ').trim().slice(0, 80); };
          const todos = [...document.querySelectorAll(sel)];
          let n = 0;
          for (let i = 0; i < todos.length; i++) {
            const el = todos[i];
            if (!vis(el) || el.closest('[aria-hidden=true],[inert]')) continue;
            if ((el.getAttribute('role') || el.tagName.toLowerCase()) + '|' + nome(el) === alvo) {
              n += 1;
              if (n === ordem) return i;
            }
          }
          return -1;
        }""",
        [SELETOR, papel_nome, alvo_ordem],
    )
    return None if indice < 0 else pagina.locator(SELETOR).nth(indice)


def _efeito(pagina, contexto, rastro: Rastro, antes: str, url_antes: str, paginas_antes: int, inicio: float,
            downloads_antes: int, dialogos_antes: int) -> tuple[str | None, list[str]]:
    """Devolve (efeito, problemas). Espera até ~2,5 s por qualquer sinal."""
    problemas: list[str] = []
    limite = time.monotonic() + 2.5
    efeito = None
    while time.monotonic() < limite and efeito is None:
        pagina.wait_for_timeout(250)
        if len(contexto.pages) > paginas_antes:
            efeito = "nova aba"
        elif rastro.downloads > downloads_antes:
            efeito = "download"
        elif rastro.dialogos > dialogos_antes:
            efeito = "diálogo do navegador"
        elif pagina.url != url_antes:
            efeito = "navegação"
        else:
            depois_req = [r for r in rastro.respostas if r[3] >= inicio and "/api/" in r[1]]
            ok = [r for r in depois_req if r[2] < 400]
            ruins = [r for r in depois_req if r[2] >= 400 and not _resposta_esperada(r[1], r[2])]
            if ruins:
                problemas += [f"{m} {u.split('://', 1)[-1].split('/', 1)[-1]} → {s}" for m, u, s, _ in ruins]
            if pagina.evaluate(JS_ASSINATURA, SELETOR) != antes:
                efeito = "mudança de estado"
            elif ok and any(m != "GET" for m, *_ in ok):
                efeito = "requisição ok"
    if efeito is None:
        depois_req = [r for r in rastro.respostas if r[3] >= inicio and "/api/" in r[1] and r[2] < 400]
        if depois_req:
            efeito = "requisição ok"
    return efeito, problemas


class _SoUmaOpcao(Exception):
    pass


def _acionar(alvo, item: dict) -> None:
    if item["papel"] == "select":
        opcoes = alvo.locator("option").evaluate_all("os => os.map(o => o.value)")
        atual = alvo.input_value()
        outra = next((o for o in opcoes if o != atual), None)
        if outra is None:
            raise _SoUmaOpcao()
        alvo.select_option(outra, timeout=5000)
    else:
        alvo.scroll_into_view_if_needed(timeout=5000)
        alvo.click(timeout=5000)


def _restaurar_cameras(servidor) -> None:
    tecnico = servidor.sessao("technical")
    for cid in servidor.cameras.values():
        try:
            if not tecnico.get(f"{servidor.base}/api/cameras/{cid}/status", timeout=10).json().get("running"):
                tecnico.post(f"{servidor.base}/api/cameras/{cid}/start", timeout=60)
        except Exception:  # noqa: BLE001  (restauração é melhor esforço; o próximo teste acusa se ficou parada)
            pass


def _varrer_rota(navegador, servidor, papel: str, tema: str, nome: str, url: str, preparo: str | None) -> dict:
    contexto = navegador.new_context(viewport={"width": 1366, "height": 768}, color_scheme=tema,
                                     accept_downloads=True)
    contexto.add_init_script(f"try{{localStorage.setItem('visionepi-theme','{tema}')}}catch(e){{}}")
    resultado = {"papel": papel, "tema": tema, "rota": nome, "url": url, "elementos": [], "erros_console": [],
                 "respostas_ruins": [], "texto_cortado": [], "bugs": []}
    try:
        pagina = contexto.new_page()
        rastro = Rastro(pagina)
        if papel != "sem_sessao":
            _login(pagina, servidor, papel)
        _abrir(pagina, servidor, url, preparo)
        base = pagina.evaluate(JS_ENUMERAR, SELETOR)
        resultado["texto_cortado"] = sorted({e["nome"] for e in base if e["cortado"]})
        for item in base:
            registro = {"chave": item["chave"], "nome": item["nome"], "papel": item["papel"]}
            motivo = next((m for p, m in NAO_ACIONAR if p.search(item["nome"])), None)
            if motivo:
                registro |= {"resultado": "não acionado", "motivo": motivo}
                resultado["elementos"].append(registro)
                continue
            if item["desabilitado"]:
                ok = bool(item["explicacao"])
                registro |= {"resultado": "desabilitado com explicação" if ok else "desabilitado SEM explicação",
                             "motivo": item["explicacao"]}
                if not ok:
                    resultado["bugs"].append(f"desabilitado sem explicação: {item['nome'] or item['chave']}")
                resultado["elementos"].append(registro)
                continue
            if not item["nome"]:
                resultado["bugs"].append(f"elemento interativo sem nome acessível: {item['chave']}")
            alvo = _localizar(pagina, item["chave"])
            if alvo is None:
                # Sumiu depois de acionar o anterior (ex.: menu fechado). Reabre a rota e tenta de novo.
                _abrir(pagina, servidor, url, preparo)
                alvo = _localizar(pagina, item["chave"])
            if alvo is None:
                registro |= {"resultado": "não reencontrado (lista dinâmica)"}
                resultado["elementos"].append(registro)
                continue
            leve_antes = pagina.evaluate(JS_ASSINATURA_LEVE)
            antes = pagina.evaluate(JS_ASSINATURA, SELETOR)
            url_antes, paginas_antes = pagina.url, len(contexto.pages)
            downloads_antes, dialogos_antes = rastro.downloads, rastro.dialogos
            inicio = time.monotonic()
            erro_clique = None
            for tentativa in range(2):
                try:
                    _acionar(alvo, item)
                    erro_clique = None
                    break
                except _SoUmaOpcao:
                    erro_clique = "select com uma opção só"
                    break
                except Exception as exc:  # noqa: BLE001
                    linhas = str(exc).splitlines()
                    erro_clique = (linhas[0] + " " + " ".join(x.strip() for x in linhas if "intercepts" in x)[:200])[:300]
                    if tentativa == 0:
                        rastro.esperar_rede(pagina)
                        _abrir(pagina, servidor, url, preparo)
                        alvo = _localizar(pagina, item["chave"])
                        if alvo is None:
                            break
                        antes = pagina.evaluate(JS_ASSINATURA, SELETOR)
                        url_antes, paginas_antes = pagina.url, len(contexto.pages)
                        inicio = time.monotonic()
            if erro_clique == "select com uma opção só":
                registro |= {"resultado": erro_clique}
                resultado["elementos"].append(registro)
                continue
            if erro_clique is not None or alvo is None:
                registro |= {"resultado": "falhou ao acionar", "motivo": erro_clique or "sumiu ao reabrir"}
                resultado["bugs"].append(f"não foi possível acionar: {item['nome']} ({registro['motivo']})")
                resultado["elementos"].append(registro)
                rastro.esperar_rede(pagina)
                _abrir(pagina, servidor, url, preparo)
                continue
            efeito, problemas = _efeito(pagina, contexto, rastro, antes, url_antes, paginas_antes, inicio,
                                        downloads_antes, dialogos_antes)
            registro |= {"resultado": efeito or "SEM EFEITO"}
            if efeito is None:
                resultado["bugs"].append(f"botão sem efeito: {item['nome'] or item['chave']}")
            for p in problemas:
                resultado["bugs"].append(f"resposta inesperada ao acionar {item['nome']}: {p}")
            resultado["elementos"].append(registro)
            # Volta ao estado da rota: fecha abas novas, camadas abertas e, se navegou ou a tela
            # mudou (estado interno do SPA), reabre a rota.
            for extra in contexto.pages[paginas_antes:]:
                extra.close()
            rastro.esperar_rede(pagina)
            if pagina.url != url_antes or efeito == "navegação":
                _abrir(pagina, servidor, url, preparo)
            elif pagina.evaluate(JS_ASSINATURA_LEVE) != leve_antes:
                pagina.keyboard.press("Escape")
                pagina.wait_for_timeout(300)
                if pagina.evaluate(JS_ASSINATURA_LEVE) != leve_antes:
                    _abrir(pagina, servidor, url, preparo)
        resultado["erros_console"] = sorted(set(rastro.erros_console))
        ruins = [(m, u, s) for m, u, s, _ in rastro.respostas if s >= 400 and not _resposta_esperada(u, s)]
        resultado["respostas_ruins"] = sorted({f"{m} {u.split('://', 1)[-1].split('/', 1)[-1]} → {s}" for m, u, s in ruins})
        resultado["bugs"] += [f"erro no console: {e}" for e in resultado["erros_console"]]
        resultado["bugs"] += [f"resposta {r}" for r in resultado["respostas_ruins"]
                              if not any(r in b for b in resultado["bugs"])]
        resultado["bugs"] += [f"texto cortado: {t}" for t in resultado["texto_cortado"]]
    finally:
        contexto.close()
        if papel != "sem_sessao":
            _restaurar_cameras(servidor)
    return resultado


def _gravar(resultado: dict) -> None:
    SAIDA.mkdir(parents=True, exist_ok=True)
    arquivo = SAIDA / f"{resultado['papel']}-{resultado['tema']}-{resultado['rota']}.json"
    arquivo.write_text(json.dumps(resultado, indent=1, ensure_ascii=False), encoding="utf-8")


def _filtro_de_rotas() -> set[str] | None:
    bruto = os.environ.get("E2E_CRAWLER_ROTAS", "").strip()
    return {r.strip() for r in bruto.split(",") if r.strip()} or None


@pytest.mark.parametrize(("papel", "tema"), _casos())
def test_todos_os_botoes(navegador, servidor, papel, tema):
    filtro = _filtro_de_rotas()
    rotas = [r for r in _rotas_por_papel(servidor)[papel] if filtro is None or r[0] in filtro]
    falhas: dict[str, list[str]] = {}
    for nome, url, preparo in rotas:
        resultado = _varrer_rota(navegador, servidor, papel, tema, nome, url, preparo)
        _gravar(resultado)
        if resultado["bugs"]:
            falhas[nome] = resultado["bugs"]
    assert not falhas, json.dumps(falhas, indent=1, ensure_ascii=False)[:8000]


def test_sair_encerra_a_sessao(pagina, servidor):
    """O botão "Sair", que o loop genérico não aciona, leva de volta ao login."""
    for papel in ("operator", "technical", "supervisor"):
        pagina.context.clear_cookies()
        _login(pagina, servidor, papel)
        pagina.get_by_role("button", name="Sair").click(timeout=30_000)
        pagina.get_by_label("E-mail").wait_for(timeout=30_000)


def test_paleta_de_comandos_todos_os_itens(navegador, servidor):
    """Cada item do command palette (Ctrl+K) leva a algum lugar."""
    contexto = navegador.new_context(viewport={"width": 1366, "height": 768})
    resultado = {"papel": "supervisor", "tema": "light", "rota": "paleta", "url": "/ (Ctrl+K)", "elementos": [],
                 "erros_console": [], "respostas_ruins": [], "texto_cortado": [], "bugs": []}
    try:
        pagina = contexto.new_page()
        rastro = Rastro(pagina)
        _login(pagina, servidor, "supervisor")
        pagina.wait_for_timeout(2500)
        pagina.keyboard.press("Control+k")
        pagina.locator("[cmdk-item]").first.wait_for(timeout=10_000)
        itens = pagina.locator("[cmdk-item]").evaluate_all("els => els.map(e => e.innerText.replace(/\\s+/g,' ').trim())")
        pagina.keyboard.press("Escape")
        for texto in itens:
            if any(p.search(texto) for p, _ in NAO_ACIONAR):
                resultado["elementos"].append({"nome": texto, "resultado": "não acionado"})
                continue
            pagina.goto(servidor.base + "/")
            pagina.wait_for_timeout(2000)
            pagina.keyboard.press("Control+k")
            item = pagina.locator("[cmdk-item]").filter(has_text=texto).first
            item.wait_for(timeout=10_000)
            pagina.wait_for_timeout(200)
            antes = pagina.evaluate(JS_ASSINATURA, SELETOR)
            url_antes, paginas_antes = pagina.url, len(contexto.pages)
            inicio = time.monotonic()
            item.click()
            efeito, problemas = _efeito(pagina, contexto, rastro, antes, url_antes, paginas_antes, inicio,
                                        rastro.downloads, rastro.dialogos)
            # Um item que só fecha a paleta não tem efeito: a assinatura voltaria à da tela sem a paleta.
            resultado["elementos"].append({"nome": texto, "resultado": efeito or "SEM EFEITO"})
            if efeito is None:
                resultado["bugs"].append(f"item da paleta sem efeito: {texto}")
            resultado["bugs"] += problemas
            for extra in contexto.pages[paginas_antes:]:
                extra.close()
        resultado["erros_console"] = sorted(set(rastro.erros_console))
        resultado["bugs"] += [f"erro no console: {e}" for e in resultado["erros_console"]]
    finally:
        contexto.close()
    _gravar(resultado)
    assert not resultado["bugs"], json.dumps(resultado["bugs"], indent=1, ensure_ascii=False)


def test_zz_relatorio_qa():
    """Consolida bench/runtime/crawler/*.json em docs/NEXT2026/QA.md (matriz rota × papel × resultado)."""
    arquivos = sorted(SAIDA.glob("*.json"))
    if not arquivos:
        pytest.skip("crawler não rodou nesta sessão")
    linhas = []
    total_el, total_bugs, mortos = 0, 0, 0
    for arq in arquivos:
        r = json.loads(arq.read_text(encoding="utf-8"))
        els = r["elementos"]
        acionados = sum(1 for e in els if e["resultado"] not in ("não acionado",) and not e["resultado"].startswith("desabilitado"))
        sem_efeito = sum(1 for e in els if e["resultado"] == "SEM EFEITO")
        desab = sum(1 for e in els if e["resultado"].startswith("desabilitado"))
        total_el += len(els)
        total_bugs += len(r["bugs"])
        mortos += sem_efeito
        status = "OK" if not r["bugs"] else f"{len(r['bugs'])} problema{'s' if len(r['bugs']) != 1 else ''}"
        linhas.append(f"| {r['rota']} | {r['papel']} | {r['tema']} | {len(els)} | {acionados} | {desab} | {sem_efeito} | "
                      f"{len(r['erros_console'])} | {len(r['respostas_ruins'])} | {status} |")
    detalhes = []
    for arq in arquivos:
        r = json.loads(arq.read_text(encoding="utf-8"))
        if r["bugs"]:
            detalhes.append(f"\n### {r['rota']} · {r['papel']} · {r['tema']}\n")
            detalhes += [f"- {b}" for b in r["bugs"]]
    agora = datetime.now().strftime("%d/%m/%Y %H:%M")
    texto = QA_MD.read_text(encoding="utf-8") if QA_MD.exists() else ""
    inicio_marca, fim_marca = "<!-- crawler:inicio -->", "<!-- crawler:fim -->"
    bloco = "\n".join([
        inicio_marca,
        f"## Crawler botão a botão — última rodada {agora}",
        "",
        f"Rotas × papéis × temas varridos: **{len(arquivos)}**. Elementos interativos: **{total_el}**. "
        f"Botões sem efeito: **{mortos}**. Problemas: **{total_bugs}**.",
        "",
        "| rota | papel | tema | elementos | acionados | desabilitados | sem efeito | erros de console | 4xx/5xx | resultado |",
        "|---|---|---|---|---|---|---|---|---|---|",
        *linhas,
        "",
        "Detalhe de cada rota em `bench/runtime/crawler/<papel>-<tema>-<rota>.json` (fora do git).",
        *detalhes,
        fim_marca,
    ])
    if inicio_marca in texto:
        antes, resto = texto.split(inicio_marca, 1)
        texto = antes + bloco + resto.split(fim_marca, 1)[1]
    else:
        texto = (texto or "# QA — VisionEPI (MISSÃO 4)\n\n") + "\n" + bloco + "\n"
    QA_MD.write_text(texto, encoding="utf-8")
    assert Path(QA_MD).exists()
