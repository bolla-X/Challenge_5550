"""PWA do supervisor (X10): service worker na raiz, manifesto e ícones no build."""

from __future__ import annotations

import json
from pathlib import Path

DIST = Path(__file__).resolve().parent.parent / "app" / "static" / "dist"


def test_service_worker_e_manifesto_saem_da_raiz_sem_login(client):
    sw = client.get("/sw.js")
    assert sw.status_code == 200 and "javascript" in sw.content_type
    assert sw.headers["Cache-Control"] == "no-cache"
    assert b"/api/" in sw.data  # a regra de nunca guardar dado de API está no próprio arquivo
    m = client.get("/manifest.webmanifest")
    assert m.status_code == 200 and m.content_type.startswith("application/manifest+json")
    manifesto = json.loads(m.data)
    assert manifesto["display"] == "standalone" and manifesto["start_url"] == "/"
    for icone in manifesto["icons"]:
        caminho = DIST / icone["src"].removeprefix("/static/dist/")
        assert caminho.exists(), icone["src"]
    assert any(i["purpose"] == "maskable" for i in manifesto["icons"])
