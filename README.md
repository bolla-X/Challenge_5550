# VisionEPI

Sistema de monitoramento de segurança industrial em tempo real, desenvolvido para o **Challenge 2026 — Metaindústria** (FIAP × SPI Integração). Usa visão computacional para detectar uso de EPIs, analisar postura e comportamento, e sinalizar risco antes que o incidente aconteça — não apenas registrar a infração depois do fato.

## O problema

O modelo tradicional de segurança industrial é reativo: inspeções periódicas, checklists manuais, punição depois do incidente. O VisionEPI propõe o oposto — monitoramento contínuo por IA, alertas em tempo real, e uma camada de tendência que aponta onde o risco está se acumulando antes de virar acidente.

## Funcionalidades

- **Detecção de EPIs em tempo real** — capacete, colete, luvas, óculos, máscara e calçado de segurança, via modelo YOLOv8 dedicado (Vyra, 14 classes). O segundo modelo para detecção de pessoa continua disponível para pesos que não trazem a classe `Person` (arquitetura dual-model opcional).
- **Multi-pessoa com identidade estável** — múltiplas pessoas detectadas e avaliadas no mesmo frame, cada uma com id que persiste entre frames (tracking por IoU). O EPI é associado à pessoa por geometria e de forma exclusiva: um capacete pertence a uma pessoa só, mesmo com as caixas se sobrepondo.
- **Multi-câmera de verdade** — um worker por câmera, modelos YOLO carregados uma única vez e compartilhados. Todo alerta, evento e mensagem de WebSocket carrega `camera_id`.
- **Análise de postura e quedas** — via MediaPipe Pose, sinalizando posturas suspeitas e pessoas caídas.
- **Área de risco configurável** — editor visual de zona de risco; alerta quando uma pessoa entra na área.
- **Ciclo de vida de alertas com histerese** — alertas são criados/resolvidos após N frames consecutivos (não a cada frame instável), evitando ruído de falso positivo.
- **Tendência de risco** — score agregado por categoria (os seis EPIs + quedas/postura/área de risco), opcionalmente filtrado por câmera, calculado sobre o histórico real de alertas em janela deslizante, com sparkline de 24h. Estatística honesta sobre o histórico — não é predição de IA, é isso que os dados sustentam hoje.
- **Command palette (Ctrl/Cmd+K)** — navegação rápida entre painéis, troca de modo, iniciar/parar monitoramento, sem precisar do mouse.
- **Alertas sonoros** — som curto para alertas críticos e para o retorno a "tudo certo", com mute persistente e sempre visível.
- **Autenticação real com papéis** — login por e-mail e senha (hash scrypt), sessão em cookie HttpOnly, e três papéis hierárquicos que decidem o que cada pessoa pode fazer. Sem cadastro público: quem cria acesso é quem já tem acesso.
- **Modo Operador / Técnico / Supervisor** — visão essencial para o campo (com ações reais de "avisei o colaborador" e "marcar falso positivo"), e um painel de diagnóstico completo (FPS, classes do modelo, diagnósticos de detecção) para quem precisa investigar.
- **Dashboard em tempo real** via WebSocket (Socket.IO) — feed de vídeo, conformidade por pessoa, linha do tempo de eventos, tudo atualizado ao vivo.

## Stack

**Backend**
- Python 3.11–3.12 · Flask · Flask-SQLAlchemy · Flask-Migrate (Alembic) · Flask-SocketIO
- gunicorn em produção (o servidor de desenvolvimento do Werkzeug nunca é usado fora de dev)
- Ultralytics YOLOv8 (detecção de EPI e de pessoa, dual-model)
- MediaPipe Pose (postura e quedas)
- SQLite (dev) / PostgreSQL (produção, via Docker)

**Frontend**
- React 18 + TypeScript + Vite
- Zustand (estado global, assinando os eventos WebSocket)
- Socket.IO client
- `motion` (animação declarativa), `@number-flow/react` (transição de números), `cmdk` (command palette)
- CSS global com design tokens próprios — direção visual "Autoridade Discreta": grafite + acento ciano industrial, tipografia mono para dados, cor usada com raridade

## Arquitetura

```
Flask (API REST + WebSocket)  ←→  React SPA (Vite)
        │
        ├── YOLOv8 — detecção de pessoa (COCO)
        ├── YOLOv8 — detecção de EPI (capacete/colete/luvas)
        ├── MediaPipe Pose — postura/quedas
        └── SQLite/PostgreSQL — alertas, eventos, histórico
```

Em desenvolvimento, o Vite roda como servidor separado (`:5173`) com proxy para o Flask (`:5000`). Em produção, o Flask serve o build estático do React diretamente.

## Como rodar

### Pré-requisitos
- **Python 3.11 ou 3.12** — não 3.13+. `mediapipe==0.10.14` e `numpy==1.26.4` não publicam wheel para versões acima da 3.12, e `pip install` falha antes de instalar qualquer coisa.
- Node.js + npm
- (Opcional) Docker, se for usar PostgreSQL em vez de SQLite

### Backend

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux

pip install -r requirements.txt
copy .env.example .env          # Windows
# cp .env.example .env          # macOS/Linux
```

Edite o `.env`: gere a `SECRET_KEY` (a aplicação **não sobe** sem ela); mantenha `DATABASE_URL` comentada para usar SQLite local, ou suba um Postgres via `docker compose up -d postgres` e descomente a URL.

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Crie o esquema do banco:

```bash
flask --app wsgi db upgrade
```

Crie a primeira conta — sem ela não há como entrar:

```bash
flask --app wsgi users create --role supervisor
```

> **`AUTO_CREATE_TABLES` precisa estar `false`** (é o padrão do `.env.example`). Quem é dono do esquema é o Alembic. Com `true`, `create_app()` chama `db.create_all()` — e o CLI do Flask constrói a aplicação **antes** de executar o subcomando, então as tabelas nascem sem `alembic_version` e o `db upgrade` seguinte morre com `table alerts already exists`, **num clone limpo**. Se você ligou `AUTO_CREATE_TABLES=true` e caiu nesse erro, apague o banco (`instance/visionepi-dev.db`) e rode o `upgrade` de novo com a variável em `false`.
>
> Caso diferente: **já tinha um banco da versão anterior**, criado por `db.create_all()` quando ainda não havia migrações? Aí sim rode `flask --app wsgi db stamp f6cd160ae4e0` **uma vez** antes do `upgrade`, para o Alembic aplicar só as migrações novas em vez de recriar tabelas existentes. Isso **não** resolve o caso do clone limpo acima — são problemas distintos.

O caminho documentado acima é coberto por `tests/test_onboarding.py`.

### Frontend

```bash
cd frontend
npm install
npm run build
```

### Rodando tudo

```bash
python run.py
```

Acesse `http://localhost:5000`. A porta vem de `PORT` no `.env` e é a mesma usada por `run.py`, Dockerfile, docker-compose e pelo proxy do Vite.

`python run.py` é o servidor de **desenvolvimento**. Em produção quem serve é o gunicorn sobre `wsgi:app` — é o que o `Dockerfile` faz. `FLASK_DEBUG` nunca deve ser `true` fora da sua máquina: o modo debug do Werkzeug expõe um console interativo que executa código arbitrário.

Para desenvolvimento do frontend com hot-reload, rode `npm run dev` dentro de `frontend/` em paralelo ao `python run.py` — o Vite abre em `http://localhost:5173` e faz proxy das chamadas de API/WebSocket para o Flask.

### Configuração do modelo de EPI

O `.env` aponta `PPE_MODEL_PATH` para o modelo de detecção de EPI. O padrão é **`models/vyra_ppe.pt`** ([Hexmon/vyra-yolo-ppe-detection](https://huggingface.co/Hexmon/vyra-yolo-ppe-detection), YOLOv8m, 14 classes, licença **CC-BY-4.0 — exige atribuição ao autor**).

Os pesos **não são versionados** (`.gitignore: *.pt`): baixe o arquivo e salve em `models/vyra_ppe.pt`.

Esse modelo tem a classe `Person` no índice 11 — mas veja a ressalva abaixo antes de confiar nela.

#### A classe `Person` do Vyra não generaliza — use `MULTI_PERSON_DETECTION=true`

O modelo **tem** a classe `Person`, e por isso o projeto nasceu com `MULTI_PERSON_DETECTION=false`. Medindo, a premissa não se sustenta:

- **36 células testadas** (3 fotos independentes de canteiro de obra com pessoas de corpo inteiro × `imgsz` ∈ {416, 640, 960, 1280} × `conf` ∈ {0,35; 0,10; 0,02}, instância nova do modelo a cada célula): **zero detecções de `Person`**. Nas mesmas imagens o modelo detecta `Hardhat` e `Safety Vest` normalmente.
- Somando ~650 quadros amostrados de quatro vídeos de segurança do trabalho (CDC/NIOSH), também **zero** `Person`.
- A causa está na **matriz de confusão publicada pelo próprio autor** ([confusion_matrix.png](https://huggingface.co/Hexmon/vyra-yolo-ppe-detection/blob/main/confusion_matrix.png)): `Person` tem ~**277 instâncias** de validação contra ~**8.946** de `Hardhat`. É a menor classe real do dataset — ~32x menos suportada. Ela funciona na distribuição de treino dela e falha fora.
- Para comparação, na mesma imagem `yolov8n.pt` (COCO) detecta as duas pessoas com confiança **0,87** e **0,73**.

**Consequência:** com `MULTI_PERSON_DETECTION=false`, `person_compliance_matcher.py:83` recebe lista de pessoas vazia. O sistema desenha capacetes e coletes no vídeo e **nunca avalia a conformidade de ninguém** — nenhum alerta de EPI é criado.

Por isso **`MULTI_PERSON_DETECTION=true` é o padrão** do `.env.example`, travado por `tests/test_onboarding.py`. O custo é declarado, não escondido: **−20% de FPS** (24,32 → 19,42 a `imgsz=416`, ver [docs/BENCH.md](docs/BENCH.md)). É o preço de o sistema fazer o que promete.

Isso exige o segundo peso, também não versionado. Baixe uma vez e mova para `models/`:

```bash
python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"
```

`PERSON_MODEL_PATH` aponta para `models/yolov8n.pt` de propósito: com o nome solto (`yolov8n.pt`), o ultralytics baixa o peso no diretório de trabalho de quem rodou — fora de `models/`, que é o único lugar ignorado pelo git.

#### `YOLO_IMGSZ=416` está abaixo da resolução de treino

O `args.yaml` publicado com os pesos registra `imgsz: 640`. O projeto infere a **416** por custo — a 640 o YOLO custa **166 ms** contra **82 ms** (medido, [docs/BENCH.md](docs/BENCH.md)). O preço da economia é detecção: na foto de teste, a 416 o modelo encontra **1** caixa e a 640 encontra **2**, e o capacete só aparece a partir de 640.

#### Classes detectadas que nenhuma regra consome

`Fall-Detected` (0) e `Safety Cone` (12) estão em `YOLO_CLASSES`, são detectadas, **desenhadas no vídeo** (`annotator.py:77,90`) e vão no payload do WebSocket — mas **nenhuma regra as lê**. Quem decide "pessoa caiu" é exclusivamente a geometria de landmarks do MediaPipe (`risk_rules.py:230-243`); a detecção de queda do YOLO é sinal não consumido.

Removê-las de `YOLO_CLASSES` **não economizaria nada**: o filtro `classes=` do ultralytics é aplicado **depois** do NMS (`ultralytics/utils/ops.py:273`), então o forward pass calcula as 14 classes de qualquer jeito. Por isso elas continuam ali.

#### Alternativa

Ligue `MULTI_PERSON_DETECTION=true` também ao usar um modelo de EPI sem classe `person` (ex.: `models/epi_pretrained.pt`) — e, nesse caso, **limpe `YOLO_CLASSES`**, porque os índices em `.env.example` são específicos do Vyra.

Sem um modelo de EPI treinado/compatível configurado, o dashboard mostra aviso de "modelo não suportado" — o restante do sistema (detecção de pessoa, pose, área de risco) funciona normalmente mesmo assim.

#### OpenVINO e ONNX: avaliados e não adotados

O código aceita `PPE_MODEL_PATH` apontando para um diretório `*_openvino_model`, mas o `requirements.txt` **não instala OpenVINO** — ele foi avaliado e rejeitado (commit `2d74e96`). O ONNX foi medido nesta máquina com o `best.onnx` que o próprio Hexmon publica: **33% mais lento** que o PyTorch, não os "up to 3x" que a documentação da Ultralytics anuncia. Números em [docs/BENCH.md](docs/BENCH.md). `onnxruntime` **não** está no `requirements.txt`.

## Autenticação e papéis

Todas as rotas da API exigem sessão. Os três papéis são **hierárquicos** —
supervisor pode tudo que o técnico pode, e assim por diante:

| | Operador | Técnico | Supervisor |
|---|---|---|---|
| Ver vídeo, alertas, conformidade, linha do tempo | ✅ | ✅ | ✅ |
| Iniciar/parar monitoramento | ✅ | ✅ | ✅ |
| Marcar falso positivo / avisar colaborador | ✅ | ✅ | ✅ |
| Cadastrar e configurar câmeras | — | ✅ | ✅ |
| Alterar configurações, overlay e área de risco | — | ✅ | ✅ |
| Gerir usuários | — | — | ✅ |

O Operador é restrito à **câmera do setor dele** (`User.camera_id`, definido pelo supervisor): lista de câmeras, vídeo, alertas, evidências, linha do tempo e score de risco vêm só daquela área, e ele não consegue iniciar nem parar o monitoramento de outra. Uma conta de operador **sem setor atribuído não vê nada** até o supervisor definir — deixar passar daria acesso amplo justamente à conta incompleta. Técnico e Supervisor veem o parque inteiro, porque é o trabalho deles.

Comandos de gestão:

```bash
flask --app wsgi users create --role operator --camera-id 1
```

```bash
flask --app wsgi users list
```

```bash
flask --app wsgi users set-password --email pessoa@empresa.com
```

Detalhes que importam para a avaliação de segurança:

- Senha nunca é persistida nem registrada em log — só o hash **scrypt** do werkzeug.
- Sessão em cookie **HttpOnly** (JavaScript da página não lê, então XSS não rouba a sessão) e **SameSite=Lax**. Atrás de HTTPS, ligue `SESSION_COOKIE_SECURE=true`.
- A aplicação **não sobe** com uma `SECRET_KEY` que conste no repositório (`change-me` do `.env.example`, o default do `config.py`, e afins) nem com uma chave curta demais. Esse segredo assina a sessão: com um valor público, qualquer pessoa forja o cookie de um supervisor sem credencial.
- E-mail inexistente e senha errada devolvem a **mesma** resposta, e o custo de verificação é constante — não dá para descobrir quais contas existem.
- Cinco tentativas erradas travam a conta por um tempo que dobra a cada rodada (até 30 min).
- Desativar uma pessoa, ou trocar a senha dela, **revoga todas as sessões** já emitidas — inclusive um cookie que tivesse sido copiado. Cada sessão carrega a `session_epoch` vigente no login, e o servidor compara a cada request.
- Sair encerra a sessão **naquele navegador**, não em todos: derrubar tudo a cada logout expulsaria a pessoa do kiosk do chão de fábrica quando ela saísse do desktop. Para revogar em todos os lugares (conta comprometida), troque a senha.
- O socket revalida a sessão a cada 30 s. Sem isso, uma conexão já aberta seguiria recebendo vídeo e alertas depois de o acesso ser revogado.
- O **WebSocket** também exige sessão — proteger só o REST deixaria o feed de análise e alertas acessível pela porta dos fundos.
- O **escopo de câmera vale no WebSocket também**, via rooms do Socket.IO (`app/utils/salas.py`). Técnico e Supervisor entram na sala `parque`; o Operador entra só em `camera:<id>` do setor dele; Operador sem setor não entra em sala nenhuma. Antes disso, todo `emit` era broadcast: o operador que recebia 404 ao pedir outra área por HTTP recebia `analysis`, `compliance_state` e `active_alerts` daquela área pelo socket, ~12 vezes por segundo. Coberto por `tests/test_escopo_socket.py`.

## Testes

Roteiro de teste **manual** (do zero até os casos de borda), em [`docs/TESTE-MANUAL.md`](docs/TESTE-MANUAL.md).

Verificação automatizada:

```bash
pytest
```

Lint:

```bash
ruff check .
```

Typecheck do frontend:

```bash
npm --prefix frontend run build
```

## Estrutura do projeto

```
app/                    Backend Flask
  api/                  Blueprints REST (status, alerts, cameras, monitor, risk, ...)
  services/             Lógica de negócio (monitor, workers, alertas, compliance, risk score)
  repositories/         Acesso a dados
  vision/               Detecção YOLO, tracking, pose, matching pessoa-EPI
  models.py             Modelos SQLAlchemy
migrations/             Migrações Alembic (Flask-Migrate)
frontend/               SPA React + TypeScript + Vite
  src/
    api/                Cliente REST, tipos e chaves de EPI
    socket/             Cliente WebSocket
    store/              Estado global (Zustand)
    components/         Componentes por domínio (vídeo, alertas, features, etc.)
tests/                  Testes backend (pytest)
```

## Roadmap

- [x] Tracking estável de pessoa entre frames — feito com um tracker IoU por câmera (`app/vision/person_tracker.py`) em vez de `model.track(persist=True)`: o estado do tracker do Ultralytics vive dentro do objeto do modelo, e os modelos aqui são compartilhados entre câmeras.
- [x] Matching geométrico EPI–pessoa por posição real, com atribuição exclusiva
- [x] Autenticação nos endpoints REST sensíveis — login com papéis, cobrindo REST e WebSocket
- [ ] Retry/backoff no stream de vídeo (uma fonte RTSP que cai fica em "Frame indisponível" indefinidamente)
- [ ] Pose por pessoa — hoje o MediaPipe roda uma pose global por frame, então alertas de queda/postura não são atribuíveis a um indivíduo quando há mais de um em cena
- [ ] Feature por câmera em runtime — `PUT /api/cameras/<id>` grava no banco, mas o worker em execução só relê a configuração quando é reconstruído (mudança de fonte/fps/resolução)

## Equipe

Desenvolvido para o Challenge 2026 (FIAP × SPI Integração), com mentoria de Fernando V. Marcolina e Wendel de Almeida Passos.