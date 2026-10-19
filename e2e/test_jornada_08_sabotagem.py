"""Jornada 8 (MISSÃO 4, Fase 5 item 3): a sabotagem da câmera (M1), da lente tampada à recuperação.

Contra o servidor REAL com 4 câmeras de fixture (e2e/conftest.py), na câmera "Rede" (fonte MJPEG por HTTP,
`e2e/fonte_mjpeg.py`, que passa a servir quadros tampados no meio do teste):

1. a câmera forma a referência de saúde visual e fica `ok`;
2. a fonte tampa -> a saúde visual acusa OBSTRUÍDA -> nasce o alerta `camera_obstruida` -> o cartão da câmera
   mostra o selo OBSTRUÍDA na tela;
3. a fonte destampa -> volta a `ok` e o alerta resolve (a lente liberada fecha o incidente sozinha).

Os tempos (tampar até o estado e até o alerta) vão para bench/runtime/missao4-tempos.jsonl.
Timeouts generosos para esta máquina lenta: referência 180 s; obstruída 90 s; alerta 120 s;
recuperação 120 s e 180 s; login e selo na tela 60 s.
Movida de e2e/test_missao4.py (M1). Que só o técnico redefine a referência continua em
test_missao4.py::test_m1_redefinir_referencia_so_tecnico.
"""

from __future__ import annotations

import time

from conftest import alertas_ativos, entrar, esperar, registrar_tempo


def test_tampar_a_camera_alerta_e_recupera(pagina, servidor):
    tecnico = servidor.sessao("technical")
    cid = servidor.cameras["Rede"]
    url = f"{servidor.base}/api/cameras/{cid}/saude-visual"
    esperar(lambda: (r := tecnico.get(url, timeout=20).json()).get("tem_referencia") and r.get("estado") == "ok" and r,
            180, msg="a câmera Rede não ficou com referência e estado ok")
    servidor.fonte_rede.tampar()
    inicio = time.monotonic()
    try:
        esperar(lambda: tecnico.get(url, timeout=20).json().get("estado") == "obstruida", 90, 0.5,
                msg="saúde visual não acusou OBSTRUÍDA")
        t_estado = time.monotonic() - inicio
        esperar(lambda: any(a.get("rule") == "camera_obstruida" for a in alertas_ativos(tecnico, servidor, "Rede")), 120, 0.5,
                msg="alerta camera_obstruida não nasceu")
        t_alerta = time.monotonic() - inicio
        registrar_tempo("m1_tampar_ate_estado", t_estado)
        registrar_tempo("m1_tampar_ate_alerta", t_alerta)
        # A tela mostra o badge no cartão da câmera.
        entrar(pagina, servidor, "technical")
        badge = pagina.locator("[data-testid=saude-badge][data-estado=obstruida]")
        badge.first.wait_for(timeout=60_000)
        assert "OBSTRU" in badge.first.inner_text().upper()
    finally:
        servidor.fonte_rede.destampar()
    esperar(lambda: tecnico.get(url, timeout=20).json().get("estado") == "ok", 120, msg="não voltou a OK ao destampar")
    esperar(lambda: not any(a.get("rule") == "camera_obstruida" for a in alertas_ativos(tecnico, servidor, "Rede")), 180,
            msg="alerta camera_obstruida não resolveu ao destampar")
