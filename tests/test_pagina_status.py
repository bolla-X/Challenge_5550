"""Página `/status` (MISSÃO 4, Fase 3 item 7): `GET /api/status` e o desempate da URL `/status`.

Três contratos:

1. `GET /api/status` é do técnico para cima (operador 403, sem sessão 401) e nunca
   cai por causa de uma sonda: componente que lança ou trava vira item "falha".
2. `/status` continua sendo o JSON legado do monitor para quem pede JSON (fetch,
   curl, os testes antigos) e passa a servir o shell do SPA para a navegação
   (`Accept: text/html`).
3. A chave do LLM nunca aparece na resposta, nem quando está configurada.
"""

from __future__ import annotations

import json
import threading
from collections import namedtuple

import pytest
from app import create_app
from app.config import AuthTestConfig
from app.extensions import db
from app.models import ROLE_OPERATOR, ROLE_SUPERVISOR, ROLE_TECHNICAL, Camera
from app.services.auth_service import AuthService
from app.services.status_do_sistema import (
    ATENCAO,
    DESLIGADO,
    FALHA,
    OK,
    ServicoDeStatus,
    coletar,
    tamanho_da_pasta,
)

SENHA = "senha-forte-de-teste"
NAVEGADOR = "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,*/*;q=0.8"
# Montada em partes: o literal inteiro dispararia a guarda de chave versionada (tests/test_onboarding.py).
CHAVE_DO_LLM = "AI" + "zaSyCHAVE-FALSA-QUE-NAO-PODE-VAZAR-123456"


@pytest.fixture()
def app(tmp_path):
    class Cfg(AuthTestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'status.db'}"
        SNAPSHOT_DIR = str(tmp_path / "snapshots")
        REPLAY_DIR = str(tmp_path / "clips")
        TRILHAS_DIR = str(tmp_path / "trilhas")

    app = create_app(Cfg)
    with app.app_context():
        db.create_all()
        db.session.add(Camera(name="Portaria", source_type="USB", source="0"))
        db.session.commit()
        app.extensions["monitor_service"].load_cameras_from_db()
        AuthService().create_user(email="op@fabrica.com", name="Op", password=SENHA, role=ROLE_OPERATOR, camera_id=1)
        AuthService().create_user(email="tec@fabrica.com", name="Tec", password=SENHA, role=ROLE_TECHNICAL)
        AuthService().create_user(email="sup@fabrica.com", name="Sup", password=SENHA, role=ROLE_SUPERVISOR)
        db.session.remove()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


def entrar(app, email: str):
    cliente = app.test_client()
    assert cliente.post("/api/auth/login", json={"email": email, "password": SENHA}).status_code == 200
    return cliente


@pytest.fixture()
def tecnico(app):
    return entrar(app, "tec@fabrica.com")


# ------------------------------------------------------------------ papéis --
def test_sem_sessao_e_401(app):
    assert app.test_client().get("/api/status").status_code == 401


def test_operador_recebe_403(app):
    resposta = entrar(app, "op@fabrica.com").get("/api/status")
    assert resposta.status_code == 403
    assert resposta.get_json()["code"] == "forbidden"


@pytest.mark.parametrize("email", ["tec@fabrica.com", "sup@fabrica.com"])
def test_tecnico_e_supervisor_veem_o_status(app, email):
    resposta = entrar(app, email).get("/api/status")
    assert resposta.status_code == 200
    assert resposta.headers["Cache-Control"] == "no-store"
    corpo = resposta.get_json()
    assert set(corpo["componentes"]) == {
        "modelos", "cameras", "banco", "opcua", "mqtt", "broker", "webhook", "llm", "disco",
    }
    assert corpo["gerado_em"]
    assert "construido_em" in corpo["versao"]
    for nome, componente in corpo["componentes"].items():
        assert componente["estado"] in {OK, ATENCAO, FALHA, DESLIGADO}, nome
        assert componente["resumo"], nome


# ------------------------------------------------------- conteúdo dos cartões --
def test_banco_responde_com_tempo(tecnico):
    banco = tecnico.get("/api/status").get_json()["componentes"]["banco"]
    assert banco["estado"] == OK
    assert banco["motor"] == "sqlite"
    assert banco["consulta_ms"] >= 0
    assert banco["arquivo"] == "status.db"


def test_camera_parada_aparece_com_o_nome(tecnico):
    cameras = tecnico.get("/api/status").get_json()["componentes"]["cameras"]
    assert [c["nome"] for c in cameras["cameras"]] == ["Portaria"]
    assert cameras["cameras"][0]["situacao"] == "parada"
    assert cameras["cameras"][0]["estado"] == DESLIGADO
    assert cameras["cameras"][0]["saude_visual"]["estado"] == "ok"


def test_modelos_dizem_runtime_pedido_e_se_aqueceram(tecnico):
    modelos = tecnico.get("/api/status").get_json()["componentes"]["modelos"]
    por_nome = {m["nome"]: m for m in modelos["modelos"]}
    assert {"epi", "pessoa"} <= set(por_nome)
    assert por_nome["epi"]["runtime_pedido"] == "pytorch"
    assert por_nome["epi"]["aquecido"] is False  # a suíte nunca chama `aquecer()`
    assert modelos["estado"] == ATENCAO
    # Só o nome do arquivo: o caminho absoluto da máquina não sai.
    assert "/" not in (por_nome["epi"]["arquivo"] or "") and "\\" not in (por_nome["epi"]["arquivo"] or "")


def test_integracoes_desligadas_dizem_como_ligar(tecnico):
    componentes = tecnico.get("/api/status").get_json()["componentes"]
    variaveis = (("opcua", "OPCUA_ATIVO"), ("mqtt", "MQTT_ATIVO"), ("broker", "MQTT_BROKER_EMBUTIDO"), ("webhook", "WEBHOOK_URL"))
    for chave, variavel in variaveis:
        assert componentes[chave]["estado"] == DESLIGADO
        assert componentes[chave]["como_ligar"] == variavel


def test_integracao_que_falhou_vira_falha_sem_segredo(app, tecnico):
    gerente = app.extensions["monitor_service"].integracao
    gerente.status = lambda: {  # type: ignore[method-assign]
        "opcua": {"ativo": True, "estado": "no_ar", "endpoint": "opc.tcp://127.0.0.1:4840/visionepi/", "erro": None},
        "mqtt": {"ativo": True, "estado": "falhou", "endpoint": "127.0.0.1:1883", "erro": "recusado em " + "rtsp://" + "admin:senha@host"},
        "broker": {"ativo": False, "estado": "desligado", "endpoint": None, "erro": None},
        "webhook": {
            "ativo": True, "estado": "no_ar", "endpoint": "https://erp.local:443/hook",
            "erro": None, "estatisticas": {"enviados": 3, "falhas": 0, "descartados": 0, "pendentes": 0, "ultimo_erro": None},
        },
    }
    componentes = tecnico.get("/api/status").get_json()["componentes"]
    assert componentes["opcua"]["estado"] == OK
    assert componentes["mqtt"]["estado"] == FALHA
    assert "senha" not in json.dumps(componentes["mqtt"])
    assert componentes["webhook"]["estatisticas"]["enviados"] == 3


def test_disco_tem_volumes_e_tamanho_das_pastas(app, tecnico, tmp_path):
    (tmp_path / "snapshots").mkdir()
    (tmp_path / "snapshots" / "a.jpg").write_bytes(b"x" * 1500)
    disco = tecnico.get("/api/status").get_json()["componentes"]["disco"]
    assert {"evidencias", "instancia"} == set(disco["volumes"])
    assert disco["volumes"]["evidencias"]["total_bytes"] > 0
    assert disco["pastas"]["imagens"] == {"existe": True, "bytes": 1500, "arquivos": 1, "parcial": False}
    assert disco["pastas"]["clipes"]["existe"] is False


def test_politicas_trazem_privacidade_e_retencao_do_config(app, tecnico):
    # Prazo largo: aqui se verifica o CONTEÚDO das políticas. Com o prazo real (2,5 s de relógio), a sonda de
    # câmeras pode não responder com a suíte inteira rodando e a lista sai vazia; o prazo tem teste próprio
    # (`test_sonda_que_trava_vira_falha_no_prazo`).
    app.extensions["status_do_sistema"] = ServicoDeStatus(app, prazo_s=30)
    resposta = tecnico.get("/api/status").get_json()
    politicas = resposta["politicas"]
    assert politicas["privacidade"]["padrao_ligada"] is True
    assert [c["nome"] for c in politicas["privacidade"]["cameras"]] == ["Portaria"], resposta["componentes"].get("cameras")
    retencao = politicas["retencao"]
    assert retencao["expira_sozinha"] is False
    assert retencao["replay_antes_s"] == 5.0 and retencao["replay_depois_s"] == 3.0
    assert retencao["trilhas_teto_mb"] == 64.0


# ---------------------------------------------------------- disco: limiares --
Uso = namedtuple("Uso", "total used free")


@pytest.mark.parametrize(
    ("livre_gib", "esperado"),
    [(200, OK), (80, ATENCAO), (20, FALHA)]  # de 1000 GiB: 20%, 8%, 2%,
)
def test_pouco_disco_muda_o_estado(app, livre_gib, esperado):
    total = 1000 * 1024**3
    servico = ServicoDeStatus(app, uso_de_disco=lambda _p: Uso(total, total - int(livre_gib * 1024**3), int(livre_gib * 1024**3)))
    with app.app_context():
        assert servico._sonda_disco()["estado"] == esperado


def test_disco_que_nao_mede_vira_falha_do_volume(app):
    def quebra(_pasta):
        raise OSError("sem acesso")

    with app.app_context():
        disco = ServicoDeStatus(app, uso_de_disco=quebra)._sonda_disco()
    assert disco["estado"] == FALHA


def test_tamanho_da_pasta_para_no_orcamento(tmp_path):
    for i in range(10):
        (tmp_path / f"{i}.bin").write_bytes(b"x" * 10)
    completo = tamanho_da_pasta(tmp_path)
    assert completo == {"existe": True, "bytes": 100, "arquivos": 10, "parcial": False}
    assert tamanho_da_pasta(tmp_path, maximo_de_arquivos=3)["parcial"] is True
    assert tamanho_da_pasta(tmp_path / "nao-existe")["existe"] is False


# ------------------------------------------------------------------- sondas --
def test_sonda_que_lanca_nao_derruba_a_rota(app, tecnico, monkeypatch):
    def quebra(self):
        raise RuntimeError("segredo-interno-do-banco")

    monkeypatch.setattr(ServicoDeStatus, "_sonda_banco", quebra)
    resposta = tecnico.get("/api/status")
    assert resposta.status_code == 200
    componentes = resposta.get_json()["componentes"]
    assert componentes["banco"]["estado"] == FALHA
    assert componentes["banco"]["resumo"] == "Falha ao consultar este componente."
    assert "segredo-interno-do-banco" not in resposta.get_data(as_text=True)
    assert componentes["cameras"]["estado"] in {OK, ATENCAO, FALHA, DESLIGADO}  # as outras seguem


def test_monitor_sem_os_metodos_novos_nao_derruba_a_rota(app, tecnico):
    """Monitor reduzido (o stub das rotas legadas): cada cartão degrada sozinho."""

    class MonitorMinimo:
        pass

    app.extensions["monitor_service"] = MonitorMinimo()
    resposta = tecnico.get("/api/status")
    assert resposta.status_code == 200
    componentes = resposta.get_json()["componentes"]
    assert componentes["modelos"]["estado"] == DESLIGADO
    assert componentes["opcua"]["estado"] == DESLIGADO
    assert componentes["banco"]["estado"] == OK


def test_sonda_que_trava_vira_falha_no_prazo(app, monkeypatch):
    liberar = threading.Event()
    monkeypatch.setattr(ServicoDeStatus, "_sonda_cameras", lambda self: liberar.wait(10) or {})
    servico = ServicoDeStatus(app, prazo_s=0.3)
    try:
        corpo = servico.montar()
    finally:
        liberar.set()
    assert corpo["componentes"]["cameras"]["estado"] == FALHA
    assert "Sem resposta" in corpo["componentes"]["cameras"]["resumo"]
    assert corpo["componentes"]["banco"]["estado"] == OK


def test_coletar_isola_cada_sonda():
    def boa():
        return {"estado": OK, "resumo": "ok"}

    def ruim():
        raise ValueError("x")

    resultado = coletar({"a": boa, "b": ruim}, prazo_s=1.0)
    assert resultado["a"]["estado"] == OK
    assert resultado["b"]["estado"] == FALHA


# ---------------------------------------------------------------------- LLM --
def test_llm_desligado_por_padrao(tecnico, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    llm = tecnico.get("/api/status").get_json()["componentes"]["llm"]
    assert llm["estado"] == DESLIGADO
    assert llm["ligado"] is False and llm["tem_chave"] is False


def test_llm_ligado_sem_chave_pede_atencao(app, tecnico, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    app.config["LLM_ENABLED"] = True
    llm = tecnico.get("/api/status").get_json()["componentes"]["llm"]
    assert llm["estado"] == ATENCAO
    assert llm["tem_chave"] is False


def test_llm_com_chave_nunca_vaza_a_chave(app, tecnico, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", CHAVE_DO_LLM)
    app.config["LLM_ENABLED"] = True
    resposta = tecnico.get("/api/status")
    llm = resposta.get_json()["componentes"]["llm"]
    assert llm["estado"] == OK and llm["tem_chave"] is True
    texto = resposta.get_data(as_text=True)
    assert CHAVE_DO_LLM not in texto
    assert "AI" + "za" not in texto


# ------------------------------------------------- /status: JSON x página --
def test_status_legado_segue_json_para_fetch(app, tecnico):
    for cabecalhos in ({}, {"Accept": "application/json"}, {"Accept": "*/*"}):
        resposta = tecnico.get("/status", headers=cabecalhos)
        assert resposta.status_code == 200, cabecalhos
        assert resposta.is_json, cabecalhos
        corpo = resposta.get_json()
        assert corpo["system"] == "VisionEPI"
        assert "running" in corpo


def test_status_legado_sem_sessao_continua_401_em_json(app):
    resposta = app.test_client().get("/status", headers={"Accept": "application/json"})
    assert resposta.status_code == 401
    assert resposta.get_json()["code"] == "unauthenticated"


def test_status_com_accept_html_serve_o_shell(app):
    anonimo = app.test_client()
    pagina = anonimo.get("/status", headers={"Accept": NAVEGADOR})
    assert pagina.status_code == 200
    assert pagina.mimetype == "text/html"
    assert pagina.get_data() == anonimo.get("/", headers={"Accept": NAVEGADOR}).get_data()


def test_status_com_html_logado_tambem_serve_o_shell(tecnico):
    pagina = tecnico.get("/status", headers={"Accept": NAVEGADOR})
    assert pagina.mimetype == "text/html"


def test_fetch_com_cabecalho_xhr_nunca_recebe_o_shell(app):
    resposta = app.test_client().get("/status", headers={"Accept": NAVEGADOR, "X-Requested-With": "XMLHttpRequest"})
    assert resposta.status_code == 401
    assert resposta.is_json


@pytest.mark.parametrize("caminho", ["/novidades", "/configuracoes"])
def test_novas_telas_servem_o_shell_com_200(app, caminho):
    resposta = app.test_client().get(caminho, headers={"Accept": NAVEGADOR})
    assert resposta.status_code == 200
    assert resposta.mimetype == "text/html"


# ------------------------------------------------- Novidades (gerador do JSON) --
def _gerador():
    import importlib.util
    from pathlib import Path

    caminho = Path(__file__).resolve().parent.parent / "scripts" / "gerar_novidades.py"
    spec = importlib.util.spec_from_file_location("gerar_novidades", caminho)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


CHANGELOG_DE_EXEMPLO = """\
# MISSÃO 2 (`MISSAO-2.md`)

### Novidades: Funções novas (14/10/2026)

<!-- comentário
- **Fora.** Não entra, está num comentário.
-->

- **Gêmeo digital.** A planta em 3D com as câmeras.
- **Raio-X.** Aperte X para ver por que a IA decidiu.

## PR5 — detalhes técnicos

- **Rodízio.** 12 ms por quadro em `agendador.py` não entra.

# MISSÃO 3 — fora do escopo

### Novidades: Outra (01/01/2026)

- **Não entra.** Missão 3 não é lida.

# MISSÃO 4 — Empresa

### Novidades: Pronto (17/10/2026)

- **Status.** Saúde dos componentes.

```python
# MISSÃO 9 num bloco de código não é título
```
"""


def test_gerador_le_so_as_secoes_de_novidades_das_missoes_2_e_4():
    dados = _gerador().extrair(CHANGELOG_DE_EXEMPLO)
    assert [(m["missao"], m["data"]) for m in dados["missoes"]] == [("Missão 4", "2026-10-17"), ("Missão 2", "2026-10-14")]
    assert [i["titulo"] for i in dados["missoes"][1]["itens"]] == ["Gêmeo digital", "Raio-X"]
    assert dados["missoes"][1]["itens"][0]["texto"] == "A planta em 3D com as câmeras."


@pytest.mark.parametrize(
    "item",
    [
        "- **Ruim.** Veja `codigo` aqui.",
        "- **Ruim.** Em app/servico.py roda.",
        "- **Ruim.** Caiu de 30 ms para 12 ms.",
        "- **Ruim.** Ficou 71% mais leve.",
        "- **Ruim.** Entrou no PR5.",
    ],
)
def test_gerador_recusa_numero_de_medicao_arquivo_e_codigo(item):
    gerador = _gerador()
    texto = f"# MISSÃO 2\n\n### Novidades: X (14/10/2026)\n\n{item}\n"
    with pytest.raises(gerador.ErroDeNovidade):
        gerador.extrair(texto)


def test_novidades_json_do_repositorio_esta_em_dia_com_o_changelog():
    """Esquecer de rodar `python scripts/gerar_novidades.py` depois de editar o CHANGELOG falha aqui."""
    assert _gerador().main(["--check"]) == 0


def test_gerador_e_idempotente(tmp_path):
    gerador = _gerador()
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(CHANGELOG_DE_EXEMPLO, encoding="utf-8")
    saida = tmp_path / "novidades.json"
    args = ["--changelog", str(changelog), "--saida", str(saida)]
    assert gerador.main(args) == 0
    primeira = saida.read_text(encoding="utf-8")
    marca = saida.stat().st_mtime_ns
    assert gerador.main(args) == 0
    assert saida.read_text(encoding="utf-8") == primeira
    assert saida.stat().st_mtime_ns == marca  # não regravou
    assert gerador.main([*args, "--check"]) == 0
    saida.write_text("{}\n", encoding="utf-8")
    assert gerador.main([*args, "--check"]) == 1
