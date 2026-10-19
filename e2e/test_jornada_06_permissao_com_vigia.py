"""Jornada 6 (MISSÃO 4, Fase 5 item 3): a permissão de trabalho com e sem vigia (NR-33).

Contra o servidor REAL com 4 câmeras de fixture (e2e/conftest.py). A zona controlada é o quadro inteiro da
Multidão (há gente sem EPI nela o tempo todo):

1. permissão de espaço confinado com a área do vigia num canto vazio -> ninguém é vigia -> alerta crítico
   `sem_vigia` (com o item da norma na resposta);
2. encerra e emite outra com a área do vigia cobrindo quem está na cena -> alguém ali é o vigia -> o alerta
   `sem_vigia` some.

É uma jornada de API (o formulário da tela é coberto pelo crawler de botões e por
test_missao4.py::test_rotas_novas_abrem_sem_erro_de_console[/permissoes]). A zona da câmera volta como estava.
Que o operador LÊ mas NÃO emite continua em test_missao4.py::test_m5_operador_le_mas_nao_emite.

Timeouts generosos para esta máquina lenta: alerta ao vivo até 240 s.
Movida de e2e/test_missao4.py (M5).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from conftest import alertas_ativos, esperar


def test_permissao_com_vigia(servidor):
    """Zona = quadro inteiro da Multidão. Área do vigia num canto vazio → sem vigia (crítico).
    Nova permissão com a área do vigia cobrindo quem está na cena → quem está nela é vigia, sem alerta."""
    tecnico = servidor.sessao("technical")
    cid = servidor.cameras["Multidão"]
    zona_antes = tecnico.get(f"{servidor.base}/api/cameras/{cid}/risk-area", timeout=20).json()
    tecnico.put(f"{servidor.base}/api/cameras/{cid}/risk-area",
                json={"polygon": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]], "name": "Espaço confinado E2E"}, timeout=20)
    agora = datetime.now(timezone.utc)
    base = {"camera_id": cid, "tipo": "espaco_confinado", "descricao": "Inspeção E2E", "responsavel": "Equipe E2E",
            "inicio": (agora - timedelta(minutes=1)).isoformat(), "fim": (agora + timedelta(hours=1)).isoformat(),
            "epis_exigidos": [], "exige_vigia": True}
    ids: list[int] = []
    try:
        sem_vigia = tecnico.post(f"{servidor.base}/api/permissoes",
                                 json=base | {"area_vigia": [[0.0, 0.0], [0.03, 0.0], [0.03, 0.03]]}, timeout=20)
        assert sem_vigia.status_code == 201, sem_vigia.text
        ids.append(sem_vigia.json()["id"])
        assert "33.3.4.1" in json.dumps(sem_vigia.json().get("norma"), ensure_ascii=False)
        esperar(lambda: any(a.get("rule") == "sem_vigia" and a.get("severity") == "critical"
                            for a in alertas_ativos(tecnico, servidor, "Multidão")), 240, msg="alerta sem_vigia não nasceu")
        assert tecnico.post(f"{servidor.base}/api/permissoes/{ids[-1]}/encerrar", timeout=20).status_code == 200
        com_vigia = tecnico.post(f"{servidor.base}/api/permissoes",
                                 json=base | {"area_vigia": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]}, timeout=20)
        assert com_vigia.status_code == 201, com_vigia.text
        ids.append(com_vigia.json()["id"])
        esperar(lambda: not any(a.get("rule") == "sem_vigia" for a in alertas_ativos(tecnico, servidor, "Multidão")), 240,
                msg="sem_vigia continuou com vigia na área")
    finally:
        for pid in ids:
            tecnico.post(f"{servidor.base}/api/permissoes/{pid}/encerrar", timeout=20)
        if zona_antes.get("polygon"):
            tecnico.put(f"{servidor.base}/api/cameras/{cid}/risk-area",
                        json={"polygon": zona_antes["polygon"], "name": zona_antes.get("name") or "Área de risco"}, timeout=20)
