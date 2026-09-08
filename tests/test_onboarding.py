"""O caminho de instalação documentado tem que funcionar num clone limpo.

Estes testes existem por causa de uma falha real, reproduzida numa máquina
zerada: seguindo o README à risca, `flask --app wsgi db upgrade` morria com
`sqlite3.OperationalError: table alerts already exists`.

A causa não é o Alembic. É a ORDEM: o CLI do Flask constrói a aplicação antes
de executar o subcomando, e `create_app()` chama `db.create_all()` quando
`AUTO_CREATE_TABLES` está ligado. Quando o Alembic começa, as tabelas já
existem e `alembic_version` está vazia — então ele tenta aplicar a migração
inicial do zero e colide com o que o `create_all()` acabou de criar.

O `db stamp` que o README sugeria cobria só quem já tinha banco de uma versão
anterior. Quem clona hoje caía direto no erro.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

from app import create_app
from app.config import TestConfig
from app.extensions import db

RAIZ = Path(__file__).resolve().parent.parent


def ler_env_example() -> dict[str, str]:
    """Le o `.env.example` como o `python-dotenv` leria: CHAVE=valor, sem comentario."""
    valores: dict[str, str] = {}
    for linha in (RAIZ / ".env.example").read_text(encoding="utf-8").splitlines():
        limpa = linha.strip()
        if not limpa or limpa.startswith("#"):
            continue
        casamento = re.match(r"^([A-Z0-9_]+)=(.*)$", limpa)
        if casamento:
            valores[casamento.group(1)] = casamento.group(2).split("#")[0].strip()
    return valores


def test_env_example_nao_liga_auto_create_tables():
    """O default distribuido nao pode quebrar `flask --app wsgi db upgrade`.

    Com `AUTO_CREATE_TABLES=true`, quem copia o `.env.example` (que e o que o
    README manda fazer) e roda o `db upgrade` documentado recebe
    `table alerts already exists` e nao consegue instalar o projeto.

    O dono do esquema e o Alembic. `create_all()` e atalho de desenvolvimento e
    precisa ser opt-in, nao o padrao que todo mundo herda.
    """
    assert ler_env_example()["AUTO_CREATE_TABLES"] == "false"


def test_env_example_aponta_para_peso_que_o_requirements_instala():
    """`PPE_MODEL_PATH` nao pode apontar para um runtime que nao e instalado.

    O `.env.example` apontava para um diretorio `*_openvino_model`, mas o
    `requirements.txt` deliberadamente NAO instala OpenVINO — e explica por que
    num comentario. O README, por sua vez, documenta `models/vyra_ppe.pt`.
    Os dois discordavam entre si; quem seguisse o `.env.example` nao subia.
    """
    caminho = ler_env_example()["PPE_MODEL_PATH"]
    assert caminho.endswith(".pt"), (
        f"PPE_MODEL_PATH={caminho} aponta para um runtime que o requirements.txt nao instala. "
        "Ver docs/AMBIENTE.md, desvio #2."
    )


def test_create_all_cria_tabelas_sem_registrar_versao_no_alembic(tmp_path):
    """Caracterizacao: documenta POR QUE o default acima precisa ser `false`.

    Este teste NAO afirma o comportamento desejado — afirma o comportamento
    ATUAL de `create_all()`, que e criar todas as tabelas e deixar
    `alembic_version` inexistente. E exatamente esse estado que faz o
    `db upgrade` seguinte tentar aplicar a migracao inicial e colidir.

    Se um dia `create_all()` passar a carimbar a versao, este teste quebra — e
    quebrar e o comportamento certo, porque a premissa do fix tera mudado.
    """
    banco = tmp_path / "onboarding.db"

    class ConfigComCreateAll(TestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{banco.as_posix()}"
        AUTO_CREATE_TABLES = True

    app = create_app(ConfigComCreateAll)
    with app.app_context():
        db.session.remove()

    motor = create_engine(f"sqlite:///{banco.as_posix()}")
    inspetor = inspect(motor)
    tabelas = set(inspetor.get_table_names())
    motor.dispose()

    assert {"alerts", "cameras", "event_logs", "users"} <= tabelas, (
        f"create_all() deveria ter criado o esquema inteiro; criou {sorted(tabelas)}"
    )
    assert "alembic_version" not in tabelas, (
        "create_all() passou a criar alembic_version. A premissa do fix de onboarding mudou: "
        "reveja docs/AMBIENTE.md e o README."
    )


@pytest.mark.parametrize("chave", ["SECRET_KEY", "DATABASE_URL"])
def test_env_example_nao_entrega_valor_pronto_para_segredo_nem_para_banco(chave):
    """`SECRET_KEY` vazia e `DATABASE_URL` comentada sao decisoes, nao descuido.

    A aplicacao se recusa a subir com qualquer `SECRET_KEY` que conste no
    repositorio (`app/__init__.py::_validar_secret_key`), entao entregar um
    valor pronto no exemplo so produziria instalacao que nao sobe. E
    `DATABASE_URL` comentada e o que faz o clone limpo cair em SQLite sem
    precisar de Postgres.
    """
    valores = ler_env_example()
    if chave == "SECRET_KEY":
        assert valores.get("SECRET_KEY", "") == ""
    else:
        assert "DATABASE_URL" not in valores


def test_migracoes_aplicam_do_zero_quando_alembic_e_o_dono_do_esquema(tmp_path):
    """O caminho documentado, ponta a ponta, sem `create_all()` no meio.

    Roda o Alembic contra um banco vazio e afirma que o esquema nasce completo
    E com a versao carimbada. E a contraprova do teste de caracterizacao acima:
    com `AUTO_CREATE_TABLES=false`, o `db upgrade` do README funciona.
    """
    from flask_migrate import upgrade

    banco = tmp_path / "migrado.db"

    class ConfigSemCreateAll(TestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{banco.as_posix()}"
        AUTO_CREATE_TABLES = False

    app = create_app(ConfigSemCreateAll)
    with app.app_context():
        upgrade(directory=str(RAIZ / "migrations"))

    motor = create_engine(f"sqlite:///{banco.as_posix()}")
    inspetor = inspect(motor)
    tabelas = set(inspetor.get_table_names())
    with motor.connect() as conexao:
        versoes = [linha[0] for linha in conexao.execute(text("select version_num from alembic_version"))]
    motor.dispose()

    assert {"alerts", "cameras", "event_logs", "users", "alembic_version"} <= tabelas
    assert versoes, "alembic_version ficou vazia: o esquema nao esta carimbado"
