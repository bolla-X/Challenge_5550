"""Gravador assíncrono: fora do loop, com fila limitada e sem morrer com erro."""

from __future__ import annotations

import threading

from app import create_app
from app.config import TestConfig
from app.services.gravador_assincrono import GravadorAssincrono


def test_executa_no_contexto_da_app_e_sobrevive_a_erro():
    app = create_app(TestConfig)
    gravador = GravadorAssincrono(app)
    feitos: list[str] = []

    def explode():
        raise RuntimeError("disco cheio")

    def anota(valor):
        from flask import current_app

        feitos.append(f"{valor}:{current_app.name}")

    gravador.enfileirar(explode)
    gravador.enfileirar(anota, "depois")
    assert gravador.esperar_vazio()
    assert feitos == [f"depois:{app.name}"], "o erro da primeira tarefa não pode parar a segunda"
    assert gravador.ultimo_erro == "disco cheio"


def test_fila_cheia_descarta_e_conta_em_vez_de_bloquear_o_loop():
    app = create_app(TestConfig)
    gravador = GravadorAssincrono(app, tamanho=2)
    trava = threading.Event()
    gravador.enfileirar(trava.wait)  # ocupa o thread
    aceitos = [gravador.enfileirar(lambda: None) for _ in range(5)]
    trava.set()
    assert aceitos.count(False) >= 2, aceitos
    assert gravador.descartados == aceitos.count(False)
    assert gravador.esperar_vazio()
