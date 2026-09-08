# Ambiente verificado — Fase -2

Registro do ambiente em que este repositório foi clonado, instalado e
executado do zero. Todo número aqui foi observado, não estimado.

Data: 2026-09-08 · commit de partida: `ffcfca2` (`main`) · branch de trabalho:
`challenge/hardening-sexta`

## Máquina

| Item | Valor exato |
|---|---|
| SO | Windows 10 Pro 10.0.19045.6466 (x64) |
| Shell usado | Git Bash / MINGW64_NT-10.0-19045 (o README documenta `cmd`) |
| CPU | AMD Ryzen 7 5700X 8-Core (16 threads lógicas) |
| GPU para inferência | **nenhuma** — `torch.cuda.is_available() == False`, `torch 2.14.0+cpu` |
| Python | **3.11.9** (`py -3.11`, instalação Microsoft Store) |
| Python no PATH | 3.10.6 — **não** é o usado; o venv foi criado explicitamente com `py -3.11` |
| Node | v24.16.0 |
| npm | 11.13.0 |
| git | 2.48.1.windows.1 |

O projeto exige Python 3.11–3.12: `mediapipe==0.10.14` e `numpy==1.26.4` não
publicam wheel para 3.13+. A máquina tem 3.11.9 disponível, então o requisito
está satisfeito — mas `python` sem sufixo aponta para 3.10.6, e criar o venv
com ele seria um erro silencioso. Use sempre `py -3.11`.

## Versões instaladas (as que importam)

```
Flask 3.0.3          Flask-SocketIO 5.3.6   Flask-SQLAlchemy 3.1.1
Flask-Migrate 4.0.7  SQLAlchemy 2.0.52      alembic 1.19.2
ultralytics 8.3.40   torch 2.14.0+cpu       mediapipe 0.10.14
numpy 1.26.4         opencv-python 4.10.0.84
gunicorn 22.0.0      pytest 8.3.3           ruff 0.6.9
```

`requirements.txt` fixa só parte da árvore; transitivas resolveram para as
versões acima nesta data (`torch 2.14.0`, `pandas 3.0.5`, `protobuf 4.25.9`).
Outra máquina, outro dia, pode resolver diferente.

## Modelo de EPI

Não é versionado (`.gitignore: *.pt`, e `models/` inteiro).

| Item | Valor |
|---|---|
| Origem | https://huggingface.co/Hexmon/vyra-yolo-ppe-detection |
| Arquivo remoto | `best.pt` |
| Destino local | `models/vyra_ppe.pt` |
| Tamanho | 52.056.210 bytes (bate com o `content-length` da resposta) |
| SHA-256 | `2b33d4d016f9751c5a25f4a72ce050e0a7e4e140b11c1669978d7154003a4f61` |
| Licença | `cc-by-4.0` (confirmada na API do HF, não só no README) — **exige atribuição ao autor** |

A atribuição já consta no `README.md` (seção "Configuração do modelo de EPI")
e no `.env.example`. Mantê-la é obrigação de licença, não estilo.

## Passos executados

Comandos adaptados do README (que assume `cmd`) para o shell efetivamente
usado. O que muda é só a invocação do interpretador.

```bash
git clone https://github.com/bolla-X/Challenge_5550
git checkout -b challenge/hardening-sexta

py -3.11 -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.txt

# .env gerado a partir do .env.example com duas alterações (ver abaixo)

AUTO_CREATE_TABLES=false ./.venv/Scripts/flask.exe --app wsgi db upgrade
./.venv/Scripts/flask.exe --app wsgi users create --email supervisor@visionepi.local --name "Supervisor Demo" --role supervisor

npm --prefix frontend install
npm --prefix frontend run build

./.venv/Scripts/python.exe run.py
```

### `.env` — o que foi alterado em relação ao `.env.example`

1. `SECRET_KEY` — gerada com `secrets.token_hex(32)` (64 caracteres). A
   aplicação recusa subir com qualquer literal que conste no repositório ou com
   menos de 32 caracteres (`app/__init__.py::_validar_secret_key`). A chave
   está só no `.env`, que é ignorado pelo git — confirmado com
   `git check-ignore -v .env`.
2. `PPE_MODEL_PATH` — de `models/vyra_ppe_openvino_model` para
   `models/vyra_ppe.pt` (ver desvio #2).

`DATABASE_URL` já vinha comentado no `.env.example`, então o banco é SQLite
(`instance/visionepi-dev.db`) sem nenhuma edição. Postgres não foi levantado.

## Desvios encontrados no caminho documentado

Dois pontos em que seguir o README literalmente numa máquina limpa **não
funciona**. Nenhum foi corrigido nesta fase — só registrado.

### 1. `flask --app wsgi db upgrade` falha num clone limpo

Rodando exatamente o comando do README:

```
sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) table alerts already exists
[SQL: CREATE TABLE alerts ( ... )]
```

**Causa:** `AUTO_CREATE_TABLES=true` (o default do `.env.example`) faz
`create_app()` chamar `db.create_all()` — e o `flask` CLI constrói a app
**antes** de executar o subcomando. Quando o Alembic começa, as tabelas já
existem e `alembic_version` está vazia, então ele tenta aplicar a migração
inicial do zero e colide.

O README documenta um `db stamp f6cd160ae4e0` como contorno, mas apenas para
quem *já tinha* um banco da versão anterior — não para quem clona hoje.

**Contorno usado (sem tocar em código):** `AUTO_CREATE_TABLES=false` só na
invocação do `db upgrade`. `python-dotenv` não sobrescreve variável já
presente no ambiente (`load_dotenv(..., override=False)` é o default), então a
variável do shell vence. Com isso o Alembic é o dono do schema desde o começo:

```
Running upgrade  -> f6cd160ae4e0, esquema inicial: alerts, event_logs, cameras
Running upgrade f6cd160ae4e0 -> a1b2c3d4e5f6, camera_id em alerts e event_logs
Running upgrade a1b2c3d4e5f6 -> b2c3d4e5f6a7, tabela de usuarios (autenticacao real)
Running upgrade b2c3d4e5f6a7 -> c3d4e5f6a7b8, epoca de sessao em users
```

Depois disso `AUTO_CREATE_TABLES=true` volta a ser inofensivo: `create_all()`
não recria tabela existente.

### 2. `PPE_MODEL_PATH` default aponta para um runtime que não está instalado

O `.env.example` traz `PPE_MODEL_PATH=models/vyra_ppe_openvino_model`, mas o
`requirements.txt` **não instala OpenVINO** — e explica por quê, em comentário:
dentro do worker real ele ficou mais lento que o PyTorch (435–614 ms contra
237 ms) e não publica wheel para Apple Silicon.

O README, por sua vez, diz que o padrão é `models/vyra_ppe.pt`. README e
`.env.example` discordam entre si. Foi seguido o README (`.pt`), que é o único
que funciona com as dependências declaradas.

## Artefatos desta fase (estado ORIGINAL, sem nenhuma alteração de código)

### `pytest`

```
platform win32 -- Python 3.11.9, pytest-8.3.3, pluggy-1.6.0
configfile: pyproject.toml
collected 175 items
...
======================= 175 passed in 73.34s (0:01:13) ========================
```
exit code 0 · **175 passed, 0 failed, 0 skipped**

### `ruff check .`

```
All checks passed!
```
exit code 0 · ruff 0.6.9

### `npm --prefix frontend run build`

```
> tsc -b && vite build
✓ 563 modules transformed.
../app/static/dist/index.html                 0.41 kB │ gzip:   0.28 kB
../app/static/dist/assets/index-DcUOtV-B.css 30.87 kB │ gzip:   6.54 kB
../app/static/dist/assets/index-CY14XRx8.js 460.86 kB │ gzip: 148.42 kB
✓ built in 2.91s
```
exit code 0. `app/static/dist/` é versionado e o rebuild saiu **byte-idêntico**
ao commitado (`git status` limpo, mesmos hashes de arquivo) — o build é
reprodutível nesta máquina.

### Servidor subindo (`python run.py`)

```
{"level": "WARNING", "logger": "app", "message": "session_cookie_not_secure",
 "hint": "Atrás de HTTPS, defina SESSION_COOKIE_SECURE=true no .env."}
 * Serving Flask app 'app'
 * Debug mode: off
{"level": "INFO", "logger": "werkzeug", "message": "WARNING: This is a development
 server... * Running on http://127.0.0.1:5000"}
```

`Debug mode: off` — `FLASK_DEBUG` não está ligado. A única WARNING é o cookie
não-Secure, esperado em `http://localhost`. **Zero registros de nível ERROR**
em toda a sessão.

### Login

Pela API:

| Cenário | Resultado |
|---|---|
| `POST /api/auth/login` senha errada | **401** |
| `POST /api/auth/login` senha certa | **200**, devolve `role: supervisor` |
| `GET /api/auth/me` com sessão | **200** com o usuário |
| `GET /api/auth/me` sem sessão | 200 `{"user": null}` — sonda intencional do frontend, não vazamento |
| Cookie de sessão | `HttpOnly` presente; `Secure` false (correto em http local) |

Log do servidor: `login_success` registrado, senha nunca aparece.

Nenhuma rota da API responde sem sessão — verificado uma a uma:

```
/status /alerts /events /features /settings /risk-score /model
/preflight /analysis/latest /video_feed /overlay /risk-area  -> todas 401
/api/cameras /api/users                                       -> 401
```

Houve **1** `socket_rejected_unauthenticated` no log: o navegador tentou abrir
o WebSocket ainda na tela de login. É o controle funcionando.

### Dashboard

Login pela interface com a conta criada: o dashboard carrega, o cabeçalho
mostra `Supervisor Demo / Supervisor`, os indicadores `backend` e `conexão`
ficam verdes (o WebSocket autenticou) e o estado é `parado` com
"0 câmeras cadastradas" — não há seed automático, é o comportamento esperado.

Os 4 erros no console do navegador são os 4 `404` de `/status`, `/settings`,
`/overlay` e `/risk-area`: rotas legadas que operam sobre "a câmera padrão" e
caem no handler de `CameraNotFoundError` porque nenhuma câmera existe ainda.
Documentado em `app/__init__.py`. Não são erros de JavaScript.

## Conta criada

`supervisor@visionepi.local` · papel `supervisor` · senha local de demo,
trocável com `flask --app wsgi users set-password`. A senha vive só no banco
local (`instance/`, ignorado pelo git) como hash scrypt — não está neste
documento nem em nenhum commit.

## MEDIDO / INFERIDO / NÃO VERIFICADO

**MEDIDO** (executado nesta máquina, saída observada)
- 175 testes passando em 73,34 s; `ruff` sem nenhum achado; build do frontend
  em 2,91 s e byte-idêntico ao commitado.
- Servidor sobe, `Debug mode: off`, zero ERROR no log.
- Login rejeita senha errada (401) e aceita a correta (200); todas as 14 rotas
  testadas devolvem 401 sem sessão; WebSocket autentica e rejeita anônimo.
- `db upgrade` falha num clone limpo com `AUTO_CREATE_TABLES=true`, e passa com
  `false`. As 4 migrações aplicam em ordem.
- Máquina sem CUDA: `torch.cuda.is_available() == False`.
- Hash e tamanho do peso do modelo conferem com a origem.

**INFERIDO** (raciocínio a partir do código lido, não executado isoladamente)
- A causa do desvio #1 ser a ordem `create_app()` → subcomando do Alembic vem
  de ler `app/__init__.py` e da mensagem de erro; não instrumentei a ordem de
  chamada.
- O `socket_rejected_unauthenticated` ser da tentativa na tela de login é a
  leitura mais direta do encadeamento no log, não uma correlação provada.

**NÃO VERIFICADO** (segue em aberto — nada aqui sustenta afirmação)
- **O pipeline de visão nunca rodou.** Nenhuma câmera foi cadastrada, o
  monitoramento nunca foi iniciado, YOLO e MediaPipe **nunca executaram uma
  inferência sequer**. Que o modelo carrega, que as 14 classes são lidas, que
  o FPS é X — nada disso está provado. É o objeto da Fase 0.
- Multi-câmera, tracker IoU, matching EPI-pessoa, histerese de alerta e área de
  risco só foram exercitados pelos testes unitários existentes, nunca ponta a
  ponta com vídeo real.
- Postgres, Docker e gunicorn não foram levantados.
- Escopo de câmera do operador não foi testado com uma conta de operador real
  (só existe a conta supervisor).
- As 3 vulnerabilidades reportadas por `npm install` (1 moderate, 2 high) não
  foram investigadas.
