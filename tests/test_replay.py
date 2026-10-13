"""Replay de incidente (F1): memória limitada, janela antes/depois, nada fabricado."""

from __future__ import annotations

import json

import numpy as np
from app.services.replay import BufferDeReplay, ClipePendente, gravar_clipe


def _quadro(valor: int = 0):
    rng = np.random.default_rng(valor)
    return rng.integers(0, 255, (540, 960, 3), dtype=np.uint8)


def test_buffer_respeita_janela_de_tempo_e_reduz_resolucao():
    buf = BufferDeReplay(segundos=2.0, fps_max=10.0, lado=480)
    for i in range(50):  # 5 s a 10 fps
        buf.gravar(_quadro(i), 1000.0 + i * 100.0, {"v": i})
    estado = buf.estado()
    assert estado["janela_s"] <= 2.0
    assert estado["quadros"] <= 21
    assert buf.entre(0, 1e9)[0].escala == 0.5, "960 -> 480 de lado maior"


def test_buffer_respeita_teto_de_bytes():
    buf = BufferDeReplay(segundos=60.0, fps_max=10.0, max_bytes=200_000)
    for i in range(100):
        buf.gravar(_quadro(i), i * 100.0, None)
    assert buf.estado()["bytes"] <= 200_000
    assert buf.estado()["quadros"] >= 1


def test_deve_gravar_limita_a_taxa():
    buf = BufferDeReplay(fps_max=10.0)
    buf.gravar(_quadro(), 1000.0, None)
    assert not buf.deve_gravar(1030.0), "a 10 fps, 30 ms depois ainda não"
    assert buf.deve_gravar(1100.0)


def test_clipe_tem_so_os_quadros_gravados_na_janela(tmp_path):
    buf = BufferDeReplay(segundos=10.0, fps_max=10.0)
    # Buraco proposital entre 1,5 s e 3,0 s: câmera travou.
    instantes = [i * 100.0 for i in range(15)] + [3000.0 + i * 100.0 for i in range(20)]
    for t in instantes:
        buf.gravar(_quadro(int(t)), t, {"t": t})
    pendente = ClipePendente(alert_id=7, t0_ms=4000.0, inicio_ms=-1000.0, fim_ms=7000.0,
                             alerta={"rule": "missing_helmet", "message": "Sem capacete",
                                     "metadata": {"person_label": "Pessoa 3", "confirmation_frames": 8}})
    clipe = gravar_clipe(tmp_path, pendente, buf.entre(pendente.inicio_ms, pendente.fim_ms), camera_id=2)

    assert clipe["total"] == len(instantes), "nenhum quadro inventado para preencher o buraco"
    rel = [q["rel_ms"] for q in clipe["quadros"]]
    assert -1500.0 not in rel and min(r for r in rel if r > -2500) >= -1000.0
    assert clipe["pessoa"] == "Pessoa 3"
    assert clipe["evidencias"]["confirmation_frames"] == 8
    disco = json.loads((tmp_path / "alert_7" / "clip.json").read_text(encoding="utf-8"))
    assert disco["total"] == clipe["total"]
    assert (tmp_path / "alert_7" / "0000.jpg").exists()
