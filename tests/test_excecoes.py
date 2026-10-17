"""Páginas de exceção (Missão 4, Fase 3 item 9): 404 de endereço desconhecido."""

from __future__ import annotations

import pytest

ROTAS_DO_SPA = ["/", "/dashboard", "/tv", "/torre", "/evacuacao", "/regras", "/permissoes", "/palco/controle"]


def test_pagina_desconhecida_serve_o_shell_com_404(client):
    resposta = client.get("/nao-existe")
    assert resposta.status_code == 404
    assert resposta.mimetype == "text/html"
    shell = client.get("/").data
    assert resposta.data == shell
    assert b'id="root"' in resposta.data
    assert resposta.headers["Cache-Control"] == "no-store"


def test_pagina_desconhecida_com_subcaminho_tambem_serve_o_shell(client):
    resposta = client.get("/painel/de/controle/")
    assert resposta.status_code == 404
    assert resposta.mimetype == "text/html"
    assert b'id="root"' in resposta.data


def test_404_do_shell_ignora_requisicao_condicional(client):
    etag = client.get("/").headers.get("ETag")
    cabecalhos = {"If-None-Match": etag} if etag else {}
    resposta = client.get("/nao-existe", headers=cabecalhos)
    assert resposta.status_code == 404
    assert b'id="root"' in resposta.data


def test_api_desconhecida_continua_json_404(client):
    resposta = client.get("/api/nao-existe")
    assert resposta.status_code == 404
    assert resposta.is_json
    assert resposta.get_json()["code"] == "not_found"


@pytest.mark.parametrize("caminho", ["/api", "/api/", "/api/cameras/x/y/z"])
def test_prefixo_api_nunca_vira_shell(client, caminho):
    resposta = client.get(caminho)
    assert resposta.status_code == 404
    assert resposta.is_json


@pytest.mark.parametrize(
    "caminho",
    ["/static/nao-existe", "/static/dist/assets/nao-existe", "/snapshots/x", "/alerts/nao-existe", "/events/x"],
)
def test_prefixos_reservados_nao_recebem_o_shell(client, caminho):
    resposta = client.get(caminho)
    assert resposta.status_code == 404
    assert b'id="root"' not in resposta.data


@pytest.mark.parametrize("caminho", ["/favicon.ico", "/robots.txt", "/foto.jpg", "/a/b/arquivo.map"])
def test_caminho_com_extensao_nao_recebe_o_shell(client, caminho):
    resposta = client.get(caminho)
    assert resposta.status_code == 404
    assert b'id="root"' not in resposta.data


def test_metodo_que_nao_e_get_nao_recebe_o_shell(client):
    resposta = client.post("/nao-existe")
    assert b'id="root"' not in resposta.data


def test_abort_404_dentro_de_rota_existente_nao_vira_shell(client):
    # /alerts/<id>/evidence casa com uma rota: o 404 dela é do recurso, não do endereço.
    resposta = client.get("/alerts/999999/evidence")
    assert resposta.status_code in (401, 404)
    assert b'id="root"' not in resposta.data


@pytest.mark.parametrize("caminho", ROTAS_DO_SPA)
def test_rotas_conhecidas_do_spa_seguem_200(client, caminho):
    resposta = client.get(caminho)
    assert resposta.status_code == 200
    assert b'id="root"' in resposta.data


def test_demo_injeta_o_script_de_tema_tambem_no_404(app):
    app.config["DEMO_MODE"] = True
    resposta = app.test_client().get("/nao-existe")
    assert resposta.status_code == 404
    assert b"visionepi-theme" in resposta.data
