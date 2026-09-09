"""Cadastro de câmera pela CLI, sem literal no código e sem senha no shell.

Contexto: as câmeras da planta são Dahua numa rede industrial de terceiro, e a
URL RTSP carrega `usuario:senha@host`. Duas coisas não podem acontecer:

1. **Endereço de câmera literal no código.** O repositório é público e o parque
   é de outra empresa; e um endereço embutido significa que trocar de câmera
   exige recompilar em vez de cadastrar.
2. **Senha em argumento de linha de comando.** `flask cameras add --senha X`
   deixa a senha no histórico do shell (`~/.bash_history`), na lista de
   processos (`ps aux`, visível a qualquer usuário da máquina) e no log de
   auditoria de quem administra o servidor. A credencial vem do `.env`, que é
   ignorado pelo git — nunca de `argv`.

O comando é o irmão de `flask users create`, que já existia: quem cria acesso
é quem já tem acesso, e nada nasce por seed automático.

Sobre `subtype`: a doc oficial da Dahua (Network Camera Web 3.0 Operation
Manual V2.1.5, p. 79) define "0 means main stream (Subtype=0) and 1 means sub
stream (Subtype=1)". O default do cadastro é **1** (substream) porque nesta
máquina CPU-only a resolução é a maior alavanca medida — 416→640 custou 42% do
FPS (docs/BENCH.md). Ver `test_subtype_padrao_e_substream`.

Nenhuma senha aqui é real: montada em runtime, como em test_credencial_rtsp.py.
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from app import create_app
from app.config import TestConfig, montar_url_rtsp
from app.extensions import db
from app.models import Camera

RAIZ = Path(__file__).resolve().parent.parent

USUARIO = "admin"
SENHA = "Nao" + "EhReal" + "123!"
HOST = "10.14.22.97"


def sem_senha(texto: str) -> bool:
    return SENHA not in texto


@pytest.fixture()
def app_cli():
    """App de teste com credencial RTSP na config, como viria do `.env`."""

    class Cfg(TestConfig):
        RTSP_USUARIO = USUARIO
        RTSP_SENHA = SENHA

    app = create_app(Cfg)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def rodar(app, *args):
    return app.test_cli_runner().invoke(args=list(args))


# ------------------------------------------------- montagem da URL ---------
def test_url_e_montada_com_a_credencial_da_config():
    url = montar_url_rtsp(host=HOST, usuario=USUARIO, senha=SENHA)

    partes = urlsplit(url)
    assert partes.scheme == "rtsp"
    assert partes.hostname == HOST
    assert partes.port == 554
    assert partes.username == USUARIO


def test_senha_com_caractere_especial_nao_estraga_a_url():
    """`@`, `:` e `/` na senha quebram a URL se não forem percent-encoded.

    A senha da planta é desconhecida nesta máquina. Se ela tiver um `@`, uma
    URL montada por concatenação ingênua faz o OpenCV ler o host errado — e o
    sintoma é "câmera não conecta", sem nada no log apontando a causa.
    """
    ruim = "p@ss:w/rd#1"
    url = montar_url_rtsp(host=HOST, usuario="ad@min", senha=ruim)

    partes = urlsplit(url)
    assert partes.hostname == HOST, f"host virou {partes.hostname!r} — credencial não foi codificada"
    assert partes.port == 554
    assert ruim not in url, "senha entrou crua na URL; precisa de percent-encoding"


def test_subtype_padrao_e_substream():
    """Default 1 = substream (doc oficial Dahua, p. 79).

    Justificativa medida: em CPU-only a resolução domina o custo do pipeline
    (416→640 = −42% de FPS, docs/BENCH.md). O substream entrega imagem menor
    direto da câmera, então não se paga o downscale nem o custo da resolução
    maior. Quem quiser o stream principal pede `--subtype 0` explicitamente.
    """
    url = montar_url_rtsp(host=HOST, usuario=USUARIO, senha=SENHA)

    assert parse_qs(urlsplit(url).query)["subtype"] == ["1"]


def test_subtype_e_canal_sao_parametrizaveis():
    url = montar_url_rtsp(host=HOST, usuario=USUARIO, senha=SENHA, canal=3, subtype=0, porta=5554)

    consulta = parse_qs(urlsplit(url).query)
    assert consulta["channel"] == ["3"]
    assert consulta["subtype"] == ["0"]
    assert urlsplit(url).port == 5554


def test_url_sem_credencial_quando_a_config_esta_vazia():
    """Sem `RTSP_USUARIO`/`RTSP_SENHA` a URL sai sem `userinfo`.

    A doc oficial da Dahua documenta essa forma: "If user name and password are
    not needed, then the URL can be: rtsp://ip:port/cam/realmonitor?channel=1&
    subtype=0". É também o formato do servidor RTSP local sem autenticação.
    """
    url = montar_url_rtsp(host=HOST, usuario="", senha="")

    assert "@" not in url, f"URL sem credencial não deveria ter userinfo: {url}"
    assert urlsplit(url).hostname == HOST


# ------------------------------------------------- o comando `add` ---------
def test_add_cadastra_a_camera_montando_a_url_da_config(app_cli):
    resultado = rodar(app_cli, "cameras", "add", "--name", "Fresa 1", "--host", HOST)

    assert resultado.exit_code == 0, resultado.output
    camera = Camera.query.filter_by(name="Fresa 1").one()
    assert camera.source_type == "RTSP"
    assert urlsplit(camera.source).hostname == HOST
    assert urlsplit(camera.source).username == USUARIO
    assert SENHA in camera.source, "a credencial real tem que ir pro banco, senão a câmera não conecta"


def test_add_nao_imprime_a_senha(app_cli):
    """A saída do comando vai pro terminal e frequentemente pra um log de setup."""
    resultado = rodar(app_cli, "cameras", "add", "--name", "Fresa 1", "--host", HOST)

    assert sem_senha(resultado.output), f"senha na saída do comando: {resultado.output}"
    assert HOST in resultado.output, "o host tem que aparecer: é a confirmação de que cadastrou a certa"


def test_add_nao_aceita_senha_por_argumento(app_cli):
    """Não existe `--senha`/`--password`/`--usuario`: é o ponto do exercício.

    Se a opção existir, alguém a usa — e a senha fica no histórico do shell e
    em `ps aux`. Este teste falha se alguém "facilitar" a vida adicionando-a.
    """
    comando = app_cli.cli.commands["cameras"].commands["add"]
    nomes = {p.name for p in comando.params} | {
        opcao for p in comando.params for opcao in p.opts
    }

    proibidos = {"senha", "password", "usuario", "user", "credencial", "--senha", "--password", "--usuario"}
    assert not (nomes & proibidos), f"opção de credencial na CLI: {sorted(nomes & proibidos)}"


def test_add_recusa_host_sem_credencial_configurada():
    """Sem credencial no `.env`, cadastrar Dahua silenciosamente daria uma
    câmera que nunca conecta. Falha alto, com a dica do que preencher."""
    app = create_app(TestConfig)  # RTSP_USUARIO/RTSP_SENHA vazios
    with app.app_context():
        db.create_all()
        resultado = rodar(app, "cameras", "add", "--name", "Fresa 1", "--host", HOST)
        db.session.remove()
        db.drop_all()

    assert resultado.exit_code != 0
    assert "RTSP_USUARIO" in resultado.output or "RTSP_SENHA" in resultado.output


def test_add_aceita_fonte_local_sem_credencial(app_cli):
    """Fixture e webcam também se cadastram por aqui — é o que o demo usa.

    Sem isto, subir o demo em modo fixture exigiria autenticar na API só pra
    inserir uma linha, e o runbook da sexta ficaria dependente da UI.
    """
    resultado = rodar(app_cli, "cameras", "add", "--name", "Demo", "--fonte", "tests/fixtures/bench.mp4")

    assert resultado.exit_code == 0, resultado.output
    camera = Camera.query.filter_by(name="Demo").one()
    assert camera.source == "tests/fixtures/bench.mp4"
    assert camera.source_type == "Arquivo"


def test_add_classifica_indice_usb_como_usb(app_cli):
    resultado = rodar(app_cli, "cameras", "add", "--name", "Webcam", "--fonte", "0")

    assert resultado.exit_code == 0, resultado.output
    assert Camera.query.filter_by(name="Webcam").one().source_type == "USB"


def test_add_exige_host_ou_fonte(app_cli):
    resultado = rodar(app_cli, "cameras", "add", "--name", "Sem fonte")

    assert resultado.exit_code != 0
    assert Camera.query.filter_by(name="Sem fonte").first() is None


def test_cada_camera_recebe_o_proprio_id(app_cli):
    """O escopo de câmera do Operador (corrigido na Fase 0) depende disso."""
    rodar(app_cli, "cameras", "add", "--name", "Fresa 1", "--host", HOST)
    rodar(app_cli, "cameras", "add", "--name", "Fresa 2", "--host", "10.14.22.98")

    ids = [c.id for c in Camera.query.order_by(Camera.id).all()]
    assert len(ids) == 2
    assert len(set(ids)) == 2, f"duas câmeras compartilhando id: {ids}"


# ------------------------------------------------- o comando `list` --------
def test_list_nao_imprime_a_senha(app_cli):
    rodar(app_cli, "cameras", "add", "--name", "Fresa 1", "--host", HOST)

    resultado = rodar(app_cli, "cameras", "list")

    assert resultado.exit_code == 0, resultado.output
    assert sem_senha(resultado.output), f"senha em `cameras list`: {resultado.output}"
    assert "Fresa 1" in resultado.output
    assert HOST in resultado.output


def test_list_sem_camera_ensina_o_proximo_comando(app_cli):
    resultado = rodar(app_cli, "cameras", "list")

    assert resultado.exit_code == 0
    assert "cameras add" in resultado.output


# ------------------------------------------------- sem literal no código --
def test_nenhum_endereco_de_camera_da_planta_no_codigo():
    """`app/` e `scripts/` não podem ter endereço da rede da planta embutido.

    Cadastro é dado, não código. Um IP de câmera literal num módulo significa
    que o parque da planta está descrito num repositório público e que trocar
    de câmera exige editar código.
    """
    # A faixa da planta. `docs/` e `tests/` ficam de fora de propósito: lá o
    # endereço é EXEMPLO documentado, e é o que este teste protege.
    padrao = re.compile(r"\b10\.14\.\d{1,3}\.\d{1,3}\b")

    culpados = []
    for pasta in ("app", "scripts"):
        for caminho in sorted((RAIZ / pasta).rglob("*.py")):
            texto = caminho.read_text(encoding="utf-8", errors="ignore")
            for achado in padrao.findall(texto):
                culpados.append(f"{caminho.relative_to(RAIZ)}: {achado}")

    assert culpados == [], f"endereço de câmera da planta embutido no código: {culpados}"
