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
from app import create_app
from app.config import TestConfig
from app.extensions import db
from sqlalchemy import create_engine, inspect, text

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


def test_env_example_liga_o_detector_de_pessoa():
    """Sem o segundo YOLO, o sistema documentado nao avalia ninguem.

    O projeto nasceu com `MULTI_PERSON_DETECTION=false` porque o modelo Vyra
    TEM a classe `Person` (indice 11). Medindo, a premissa nao se sustenta:
    36 celulas (3 fotos independentes de canteiro com pessoas de corpo inteiro
    x imgsz em {416, 640, 960, 1280} x conf em {0,35; 0,10; 0,02}, instancia
    nova do modelo a cada celula) devolveram ZERO deteccoes de `Person`, com
    confianca maxima 0,000 — inclusive na resolucao de treino.

    A causa esta na matriz de confusao publicada pelo proprio autor: `Person`
    tem ~277 instancias de validacao contra ~8.946 de `Hardhat`. E a menor
    classe real do dataset; funciona na distribuicao de treino dela e falha
    fora. Na mesma imagem, `yolov8n.pt` (COCO) acha as duas pessoas com 0,87 e
    0,73.

    Consequencia de deixar `false`: `person_compliance_matcher.py:83` recebe
    lista de pessoas vazia, o sistema desenha capacete e colete no video e
    nunca avalia a conformidade de ninguem — nenhum alerta de EPI e criado.

    Custo de deixar `true`, medido (docs/BENCH.md): -20% de FPS
    (24,32 -> 19,42 a imgsz=416). E o preco de o sistema funcionar.
    """
    assert ler_env_example()["MULTI_PERSON_DETECTION"] == "true"


def test_env_example_aponta_o_peso_de_pessoa_para_arquivo_local():
    """`PERSON_MODEL_PATH` precisa ser caminho, nao nome solto.

    Com `MULTI_PERSON_DETECTION=true` este peso passa a ser carregado de
    verdade. Um valor como `yolov8n.pt` (sem diretorio) faz o ultralytics
    baixar da internet no primeiro frame e gravar no diretorio de trabalho de
    quem rodou — fora de `models/`, que e o lugar ignorado pelo git.
    """
    caminho = ler_env_example()["PERSON_MODEL_PATH"]
    assert caminho.startswith("models/"), (
        f"PERSON_MODEL_PATH={caminho} nao aponta para models/. O peso cairia fora do "
        "diretorio ignorado pelo git e poderia ser commitado por acidente."
    )


def test_env_example_nao_entrega_chave_de_llm():
    """Chave de API so vive no .env, que e ignorado pelo git.

    O `.env.example` e versionado num repositorio PUBLICO. Uma chave real ali
    fica exposta para sempre no historico, mesmo se removida depois. O
    placeholder tem que ser vazio, e a ausencia dele desliga a camada LLM sem
    derrubar nada (ver AnalisadorDeRisco: provedor indisponivel devolve None).
    """
    valores = ler_env_example()
    assert "GEMINI_API_KEY" in valores, "o exemplo precisa DOCUMENTAR a variavel, mesmo vazia"
    assert valores["GEMINI_API_KEY"] == "", (
        "GEMINI_API_KEY no .env.example tem que ser placeholder VAZIO. "
        "Qualquer valor aqui vaza num repositorio publico."
    )


def test_nenhum_arquivo_versionado_carrega_chave_do_google():
    """Varredura: nada rastreado pelo git pode conter chave estilo Google.

    Trava o erro mais facil de cometer — colar a chave num script de teste, num
    doc de demo ou num notebook e commitar sem perceber.
    """
    import re
    import subprocess

    # DOIS formatos. `AIza...` e o antigo; o Google passou a emitir chave com
    # prefixo `AQ.`, e a chave que gravou os goldens desta fase e desse formato
    # novo — uma varredura que so conhecesse `AIza` deixaria passar exatamente a
    # chave que existe hoje nesta maquina.
    padroes = [
        re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),
        re.compile(r"\bAQ\.[A-Za-z0-9_\-]{20,}"),
    ]
    rastreados = subprocess.run(
        ["git", "ls-files"], cwd=RAIZ, capture_output=True, text=True, check=True
    ).stdout.split()

    culpados = []
    for relativo in rastreados:
        caminho = RAIZ / relativo
        if not caminho.is_file() or caminho.stat().st_size > 2_000_000:
            continue
        try:
            texto = caminho.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if any(p.search(texto) for p in padroes):
            culpados.append(relativo)

    assert culpados == [], f"chave estilo Google encontrada em arquivo versionado: {culpados}"


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

# --------------------------------------------------------------------------
# Achado da Fase 5, exercitando o cenario do demo com DUAS cameras: com
# `AUTO_CREATE_TABLES=false` a aplicacao subia com ZERO workers.
#
# `load_cameras_from_db()` estava DENTRO do guard de AUTO_CREATE_TABLES, junto
# do `db.create_all()`. Sao duas coisas sem relacao: criar tabela e carregar os
# workers das cameras que ja estao no banco. Quem segue a recomendacao da
# AMBIENTE.md — Alembic dono do esquema, `AUTO_CREATE_TABLES=false` — subia com
# o dashboard morto: as cameras aparecem na lista (leitura direta do banco),
# mas `/api/cameras/<id>/start` devolve 409 "camera sem worker ativo" e a rota
# legada `/start` devolve 404, porque nao existe camera padrao.
#
# Medido no mesmo banco, com 2 cameras cadastradas:
#   AUTO_CREATE_TABLES=true  -> workers no boot: 2, camera padrao: 1
#   AUTO_CREATE_TABLES=false -> workers no boot: 0, camera padrao: None
def test_workers_carregam_no_boot_mesmo_com_alembic_dono_do_esquema(tmp_path):
    """Camera no banco tem que ganhar worker no boot, com create_all ou sem.

    Este e o caso de quem usa migracao de verdade em vez de `create_all()`.
    """
    from app.models import Camera

    banco = tmp_path / "com_camera.db"

    class ComCreateAll(TestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{banco.as_posix()}"
        AUTO_CREATE_TABLES = True

    # Primeiro boot cria o esquema e semeia uma camera.
    app = create_app(ComCreateAll)
    with app.app_context():
        db.create_all()
        db.session.add(Camera(name="Fresa 1", source_type="Arquivo", source="tests/fixtures/bench.mp4"))
        db.session.commit()

    class SemCreateAll(TestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{banco.as_posix()}"
        AUTO_CREATE_TABLES = False

    # Segundo boot, agora sem create_all: e aqui que os workers desapareciam.
    app = create_app(SemCreateAll)
    monitor = app.extensions["monitor_service"]

    assert len(monitor._workers) == 1, (
        "camera cadastrada no banco tem que ganhar worker no boot mesmo com "
        f"AUTO_CREATE_TABLES=false; workers={len(monitor._workers)}"
    )
    assert monitor._default_camera_id is not None, (
        "sem camera padrao, as rotas legadas (/start, /status) devolvem 404"
    )


def test_boot_nao_quebra_em_banco_sem_tabela(tmp_path):
    """Contraprova, e a razao pela qual a correcao precisa de guarda.

    `flask --app wsgi db upgrade` constroi a aplicacao ANTES de rodar a
    migracao. Num banco novo a tabela `cameras` ainda nao existe, entao
    carregar workers no boot sem proteger a consulta faria justamente o comando
    de onboarding morrer — o espelho do desvio #1 deste arquivo.
    """
    banco = tmp_path / "vazio.db"

    class SemNada(TestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{banco.as_posix()}"
        AUTO_CREATE_TABLES = False

    app = create_app(SemNada)  # nao deve levantar

    assert app.extensions["monitor_service"]._workers == {}

# --------------------------------------------------------------------------
# A versao de prompt em uso e uma decisao MEDIDA, nao uma preferencia: as 6
# chamadas reais da Fase 5 (docs/SPRINT3.md) mostraram a v2 melhor que a v1 nas
# 3 cenas. Na cena SEGURA, onde o YOLO acusa missing_helmet critical para duas
# pessoas de capacete, a v2 responde `epis_ausentes: []` e escreve "ambos
# utilizando capacete"; a v1 tambem nao lista helmet, mas afirma luvas, oculos
# e mascara ausentes a 0,90 de confianca — trocando dois falsos positivos por
# tres. Voltar o default para v1 sem medicao nova seria regressao silenciosa.
#
# Os testes checam o default do CODIGO e do .env.example, sem depender do
# `.env` da maquina que roda a suite (esse pode legitimamente estar em v1 para
# alguem comparando as duas versoes).
def test_versao_de_prompt_padrao_e_v2_no_env_example():
    assert ler_env_example()["LLM_PROMPT_VERSION"] == "v2", (
        "o .env.example e o que a pessoa copia; se ele disser v1, o sistema "
        "roda com a versao pior por default"
    )


def test_versao_de_prompt_padrao_e_v2_no_codigo():
    """O literal de fallback em `app/config.py`, nao o valor do ambiente.

    Lido do texto-fonte de proposito: `Config.LLM_PROMPT_VERSION` reflete o
    `.env` de quem roda a suite, e o que este teste protege e o default que
    vale quando nao ha `.env` nenhum.

    Nota sobre uma segunda copia do default: `ServicoDeRiscoLLM
    .a_partir_da_config` tem `config.get("LLM_PROMPT_VERSION", "v1")`. Esse
    `"v1"` esta MORTO enquanto `Config` definir a chave — verificado: com uma
    config real a versao efetiva sai `v2`, e o fallback so aparece se a chave
    for removida de `Config`. Fica registrado como armadilha latente, nao
    corrigido: mexer nisso e mudanca de codigo de producao.
    """
    fonte = (RAIZ / "app" / "config.py").read_text(encoding="utf-8")
    casa = re.search(
        r'LLM_PROMPT_VERSION\s*=\s*os\.getenv\(\s*"LLM_PROMPT_VERSION"\s*,\s*"(v\d+)"',
        fonte,
    )
    assert casa, "nao encontrei o default de LLM_PROMPT_VERSION em app/config.py"
    assert casa.group(1) == "v2", f"default no codigo esta em {casa.group(1)}, deveria ser v2"


def test_a_versao_padrao_aponta_para_um_prompt_que_existe():
    """Default apontando para arquivo inexistente falharia so em runtime."""
    from app.llm import versoes_de_prompt

    assert "v2" in versoes_de_prompt(), (
        f"app/llm/prompts/ tem {versoes_de_prompt()}; o default v2 nao existe la"
    )


# ---------------------------------------------------------------------------
# Descarte de frame atrasado: o limiar do grab
# ---------------------------------------------------------------------------
# Existe porque `CAP_PROP_BUFFERSIZE=1` e RECUSADO pelo backend FFMPEG (medido:
# `set()` -> False, `get()` -> 0.0, e 104 frames enfileirados depois de 10 s sem
# ler). Sem descarte o atraso do dashboard crescia +135 ms/s; com ele ficou
# estavel em 2,55 s, deriva -0 ms/s (docs/BENCH.md, Fase 7).
#
# O limiar separa "esse grab veio do buffer" de "esse grab esperou a rede". 5 ms
# foi calibrado contra localhost, e e o primeiro numero a mexer em campo — por
# isso vira variavel de ambiente, e por isso o default fica travado aqui: um
# valor errado nao quebra nada visivelmente, so degrada latencia ou FPS em
# silencio.
def test_limiar_do_grab_tem_default_de_5ms_no_codigo():
    """O literal de fallback em `app/config.py`, nao o valor do ambiente.

    Lido do texto-fonte de proposito: `Config.RTSP_LIMIAR_GRAB_MS` reflete o
    `.env` da maquina que roda a suite, e o que este teste protege e o default
    que vale quando nao ha `.env` nenhum.
    """
    fonte = (RAIZ / "app" / "config.py").read_text(encoding="utf-8")

    casamento = re.search(r'RTSP_LIMIAR_GRAB_MS\s*=\s*env_float\(\s*"RTSP_LIMIAR_GRAB_MS"\s*,\s*([0-9.]+)\s*\)', fonte)
    assert casamento, "RTSP_LIMIAR_GRAB_MS sumiu de app/config.py"
    assert float(casamento.group(1)) == 5.0, (
        f"default do limiar mudou para {casamento.group(1)} sem medicao nova. "
        "Alto demais, o descarte para cedo e a fila volta a crescer; baixo "
        "demais, ele confunde jitter com fila e descarta frame vivo."
    )


def test_limiar_do_grab_no_env_example_bate_com_o_codigo():
    """O `.env.example` e o que a pessoa copia: se ele discordar do codigo, o
    default efetivo passa a ser outro sem ninguem perceber."""
    assert float(ler_env_example()["RTSP_LIMIAR_GRAB_MS"]) == 5.0


def test_limiar_do_grab_chega_no_video_stream():
    """De nada adianta a variavel existir se o worker nao a repassar.

    Este e o teste que pega o esquecimento mais provavel: alguem adiciona a
    chave em `Config` e nao liga o fio ate o `VideoStream`.
    """
    import threading

    from app.config import TestConfig
    from app.services.camera_worker import CameraWorker
    from app.services.feature_manager import FeatureManager

    class DetectorMinimo:
        """So o que o construtor do worker toca: o `RuleEngine` recebe
        `supported_ppe_classes` como getter."""

        confidence = 0.35
        max_detections = 100

        def supported_ppe_classes(self):
            return set()

    class Cfg(TestConfig):
        RTSP_LIMIAR_GRAB_MS = 42.0

    app = create_app(Cfg)
    with app.app_context():
        worker = CameraWorker(
            app,
            socketio=None,
            feature_manager=FeatureManager.from_config(app.config),
            camera_id=1,
            source="rtsp://camera/1",
            fps=12,
            detector=DetectorMinimo(),
            person_detector=DetectorMinimo(),
            pose_estimator=None,
            inference_lock=threading.Lock(),
        )

    assert worker.video_stream.limiar_grab_ms == 42.0, (
        "RTSP_LIMIAR_GRAB_MS nao chegou ao VideoStream: ajustar o .env em campo "
        "nao teria efeito nenhum"
    )


# ---------------------------------------------------------------------------
# Fonte cega: limiar e janela de brilho
# ---------------------------------------------------------------------------
# MEDIDO: webcam cujo stream o Windows zera (outro app ja a tinha aberto)
# entrega media de pixel 0,01 a 0,034, maximo 3, com ganho da camera em 255.
# O limiar de 2.0 fica ~60x acima disso — o alvo e imagem ZERADA, nao escura.
#
# Os defaults ficam travados porque errar aqui falha em silencio nos dois
# sentidos: alto demais acusa fonte cega num turno noturno legitimo, baixo
# demais volta a aceitar stream preto sem avisar ninguem.
def test_limiar_de_brilho_tem_default_de_2_no_codigo():
    fonte = (RAIZ / "app" / "config.py").read_text(encoding="utf-8")

    casamento = re.search(r'FONTE_BRILHO_MINIMO\s*=\s*env_float\(\s*"FONTE_BRILHO_MINIMO"\s*,\s*([0-9.]+)\s*\)', fonte)
    assert casamento, "FONTE_BRILHO_MINIMO sumiu de app/config.py"
    assert float(casamento.group(1)) == 2.0, (
        f"default do limiar de brilho mudou para {casamento.group(1)} sem medicao nova. "
        "A webcam zerada media 0,01-0,034; subir muito acusa cena escura legitima, "
        "e descer para ~0 volta a aceitar stream preto em silencio."
    )


def test_janela_de_brilho_tem_default_de_5s_no_codigo():
    fonte = (RAIZ / "app" / "config.py").read_text(encoding="utf-8")

    casamento = re.search(r'FONTE_BRILHO_JANELA_S\s*=\s*env_float\(\s*"FONTE_BRILHO_JANELA_S"\s*,\s*([0-9.]+)\s*\)', fonte)
    assert casamento, "FONTE_BRILHO_JANELA_S sumiu de app/config.py"
    assert float(casamento.group(1)) == 5.0


def test_brilho_no_env_example_bate_com_o_codigo():
    """O `.env.example` e o que a pessoa copia: discordancia silenciosa troca
    o default efetivo sem ninguem perceber."""
    valores = ler_env_example()

    assert float(valores["FONTE_BRILHO_MINIMO"]) == 2.0
    assert float(valores["FONTE_BRILHO_JANELA_S"]) == 5.0


def test_limiar_e_janela_de_brilho_chegam_no_worker():
    """Pega o esquecimento mais provavel: adicionar a chave e nao ligar o fio."""
    import threading

    from app.config import TestConfig
    from app.services.camera_worker import CameraWorker
    from app.services.feature_manager import FeatureManager

    class DetectorMinimo:
        confidence = 0.35
        max_detections = 100

        def supported_ppe_classes(self):
            return set()

    class Cfg(TestConfig):
        FONTE_BRILHO_MINIMO = 7.5
        FONTE_BRILHO_JANELA_S = 11.0

    app = create_app(Cfg)
    with app.app_context():
        worker = CameraWorker(
            app,
            socketio=None,
            feature_manager=FeatureManager.from_config(app.config),
            camera_id=1,
            source="fonte-inexistente",
            fps=12,
            detector=DetectorMinimo(),
            person_detector=DetectorMinimo(),
            pose_estimator=None,
            inference_lock=threading.Lock(),
        )

    assert worker.brilho_minimo == 7.5, "FONTE_BRILHO_MINIMO nao chegou ao worker"
    assert worker.brilho_janela_s == 11.0, "FONTE_BRILHO_JANELA_S nao chegou ao worker"
    assert worker.diagnostico()["brilho_minimo"] == 7.5, (
        "o limiar em uso tem que aparecer no diagnostico: sem ele, quem le "
        '"fonte sem imagem" nao sabe contra que numero foi comparado'
    )
