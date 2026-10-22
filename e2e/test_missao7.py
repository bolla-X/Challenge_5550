"""MISSÃO 7 — área de detecção por câmera, pela tela, contra o servidor real com as 4 câmeras.

Desenha a área (um retângulo arrastado sobre o vídeo, no terço do meio da câmera Multidão) → nenhuma pessoa nem
contagem fora dela → uma pessoa sem EPI dentro gera alerta → "Remover área" → volta a detectar no quadro inteiro.
"""

from __future__ import annotations

import json
import time

from conftest import entrar, esperar

# Terço do meio, altura inteira (o mesmo da medição em scripts/medir_area_de_deteccao.py).
X0, X1 = 0.34, 0.66


def _abrir_aba(pagina, rotulo: str) -> None:
    pagina.locator("[role=tablist]").first.wait_for(timeout=30_000)
    aba = pagina.get_by_role("tab", name=rotulo)
    if aba.count():
        aba.click()
        return
    pagina.locator(".tabs-more > button").click()
    pagina.get_by_role("menuitem", name=rotulo).click()


def _dentro(caixa: dict, largura: int, altura: int) -> bool:
    """Ponto dos pés (centro da base) no retângulo da área, em fração do quadro."""
    px = (caixa["x1"] + caixa["x2"]) / 2 / largura
    py = caixa["y2"] / altura
    return X0 <= px <= X1 and 0.0 <= py <= 1.0


def _pessoas(analise: dict) -> list[dict]:
    return [d for d in analise.get("detections") or [] if d.get("category") == "person"]


def _arrastar_retangulo(pagina, x0: float, y0: float, x1: float, y1: float) -> None:
    """Arrasta no editor, em coordenadas do VÍDEO (0–1), descontando as faixas do object-fit."""
    video = pagina.locator("canvas.live-video").first
    caixa = video.bounding_box()
    w, h = int(video.get_attribute("data-w")), int(video.get_attribute("data-h"))
    escala = min(caixa["width"] / w, caixa["height"] / h)
    ox = caixa["x"] + (caixa["width"] - w * escala) / 2
    oy = caixa["y"] + (caixa["height"] - h * escala) / 2

    def ponto(x, y):
        return ox + x * w * escala, oy + y * h * escala

    pagina.mouse.move(*ponto(x0, y0))
    pagina.mouse.down()
    for passo in range(1, 6):
        t = passo / 5
        pagina.mouse.move(*ponto(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t))
    pagina.mouse.up()


def test_area_de_deteccao_pela_tela_ate_remover(pagina, servidor):
    tecnico = servidor.sessao("technical")
    cid = servidor.cameras["Multidão"]
    base = f"{servidor.base}/api/cameras/{cid}"
    tecnico.delete(f"{base}/area-deteccao", timeout=20)  # parte do quadro inteiro, mesmo depois de outra rodada

    entrar(pagina, servidor, "technical")
    pagina.get_by_role("button", name="Configurar Multidão").click(timeout=30_000)
    video = pagina.locator("canvas.live-video").first
    esperar(lambda: int(video.get_attribute("data-frames") or 0) >= 5, 120, 0.5, msg="o vídeo não chegou ao canvas")

    # Antes: no quadro inteiro há gente com os pés FORA do terço do meio (a gravação tem gente nos três terços).
    def alguem_fora():
        a = tecnico.get(f"{base}/analysis", timeout=20).json()
        return any(not _dentro(p["box"], 960, 540) for p in _pessoas(a))

    esperar(alguem_fora, 180, 1, msg="sem área, devia haver pessoa fora do terço do meio")

    # 1. Desenha pela tela: aba Áreas → Área de detecção → Retângulo → arrastar → Salvar área.
    _abrir_aba(pagina, "Áreas")
    pagina.get_by_test_id("areas-tipo-deteccao").click()
    pagina.get_by_test_id("areas-modo-retangulo").click()
    assert pagina.get_by_test_id("deteccao-remover").is_disabled()  # nada salvo ainda
    pagina.get_by_test_id("deteccao-desenhar").click()
    _arrastar_retangulo(pagina, X0, 0.0, X1, 1.0)
    ultimo_alerta = max([a["id"] for a in tecnico.get(f"{servidor.base}/alerts",
                                                       params={"camera_id": cid, "limit": 500}, timeout=20).json()["items"]]
                        or [0])
    pagina.get_by_test_id("deteccao-salvar").click()
    pagina.get_by_test_id("deteccao-status").filter(has_text="Área de detecção salva, 4 pontos.").wait_for(timeout=20_000)

    estado = tecnico.get(f"{base}/area-deteccao", timeout=20).json()["area_deteccao"]
    assert estado["ativa"] is True and len(estado["polygon"]) == 4, estado
    xs = sorted(p["x"] for p in estado["polygon"])
    assert abs(xs[0] - X0) < 0.02 and abs(xs[-1] - X1) < 0.02, estado  # o que foi arrastado é o que ficou salvo

    # O vídeo ao vivo passa a escurecer fora da área (o overlay traz o polígono que está valendo).
    esperar(lambda: video.get_attribute("data-area"), 30, 0.5, msg="o overlay não trouxe a área de detecção")
    area_no_video = json.loads(video.get_attribute("data-area"))
    assert len(area_no_video) == 4

    # 2. Nenhuma caixa nem contagem fora dela: análises seguidas, todas só com pés dentro (a primeira pode ainda
    # ser de uma inferência que começou antes do clique, por isso espera a primeira "limpa").
    def analise_limpa_com_gente():
        a = tecnico.get(f"{base}/analysis", timeout=20).json()
        pessoas = _pessoas(a)
        return a if pessoas and all(_dentro(p["box"], 960, 540) for p in pessoas) else None

    esperar(analise_limpa_com_gente, 120, 1, msg="nenhuma análise com gente só dentro da área")
    vistas = 0
    fim = time.monotonic() + 30
    while time.monotonic() < fim:
        a = tecnico.get(f"{base}/analysis", timeout=20).json()
        fora = [p for p in _pessoas(a) if not _dentro(p["box"], 960, 540)]
        assert not fora, f"pessoa fora da área de detecção na análise: {fora}"
        contagem = a.get("compliance", {}).get("people") or []
        assert all(_dentro(p["box"], 960, 540) for p in contagem), f"contador com gente de fora: {contagem}"
        vistas += len(_pessoas(a))
        time.sleep(1)
    assert vistas > 0, "a área cobre gente na gravação: devia haver pessoas dentro"

    # 3. Uma pessoa sem EPI DENTRO gera alerta (alerta novo, depois de salvar a área).
    def alerta_novo_dentro():
        itens = tecnico.get(f"{servidor.base}/alerts", params={"camera_id": cid, "limit": 200}, timeout=20).json()["items"]
        novos = [a for a in itens if a["id"] > ultimo_alerta and (a.get("metadata") or {}).get("person_box")]
        return [a for a in novos if _dentro(a["metadata"]["person_box"], 960, 540)]

    novos = esperar(alerta_novo_dentro, 240, 2, msg="nenhum alerta novo de pessoa dentro da área")
    assert novos[0]["message"], novos[0]

    # 4. Remover área → volta ao quadro inteiro (e volta a ver gente fora do terço do meio).
    pagina.get_by_test_id("deteccao-remover").click()
    pagina.get_by_test_id("deteccao-status").filter(has_text="Sem área de detecção").wait_for(timeout=20_000)
    assert tecnico.get(f"{base}/area-deteccao", timeout=20).json()["area_deteccao"]["ativa"] is False
    esperar(lambda: video.get_attribute("data-area") == "", 30, 0.5, msg="o vídeo continuou escurecido")
    esperar(alguem_fora, 180, 1, msg="depois de remover a área, devia voltar a detectar no quadro inteiro")
    assert not [e for e in pagina.erros_console if "favicon" not in e], pagina.erros_console


def test_aviso_de_area_de_risco_fora_da_area_de_deteccao(pagina, servidor):
    """O editor avisa quando a área de risco fica (em parte) fora da área de detecção."""
    tecnico = servidor.sessao("technical")
    cid = servidor.cameras["Multidão"]
    base = f"{servidor.base}/api/cameras/{cid}"
    zona_antes = tecnico.get(f"{base}/risk-area", timeout=20).json()["risk_area"]["polygon"]
    tecnico.put(f"{base}/area-deteccao", json={"polygon": [{"x": 0.0, "y": 0.0}, {"x": 0.2, "y": 0.0},
                                                            {"x": 0.2, "y": 0.3}, {"x": 0.0, "y": 0.3}]}, timeout=20)
    try:
        entrar(pagina, servidor, "technical")
        pagina.get_by_role("button", name="Configurar Multidão").click(timeout=30_000)
        _abrir_aba(pagina, "Áreas")
        pagina.get_by_test_id("areas-tipo-deteccao").click()
        aviso = pagina.get_by_test_id("aviso-risco-fora")
        aviso.wait_for(timeout=20_000)
        assert aviso.inner_text() == "Parte desta área de risco está fora da área de detecção e não será vigiada."
        assert tecnico.get(f"{base}/area-deteccao", timeout=20).json()["area_deteccao"]["risco_fora"] is True
    finally:
        tecnico.delete(f"{base}/area-deteccao", timeout=20)
        assert tecnico.get(f"{base}/risk-area", timeout=20).json()["risk_area"]["polygon"] == zona_antes
