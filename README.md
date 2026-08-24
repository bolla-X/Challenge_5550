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

Edite o `.env`: comente `DATABASE_URL` para usar SQLite local, ou suba um Postgres via `docker compose up -d postgres` e mantenha a URL configurada.

Crie o esquema do banco:

```bash
flask --app wsgi db upgrade
```

Crie a primeira conta — sem ela não há como entrar:

```bash
flask --app wsgi users create --role supervisor
```

> Já tinha um banco criado pela versão anterior (que usava `db.create_all()`)? Rode `flask --app wsgi db stamp f6cd160ae4e0` **uma vez** antes do `upgrade` — assim o Alembic aplica só a migração nova (`camera_id`) em vez de tentar recriar tabelas que já existem.

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

Esse modelo já traz a classe `Person` (índice 11), então `MULTI_PERSON_DETECTION=false` desliga o segundo modelo YOLO (COCO, `PERSON_MODEL_PATH`) que antes rodava em paralelo só para suprir essa falta. Ele continua configurável: ligue `MULTI_PERSON_DETECTION=true` ao usar um modelo de EPI sem classe `person` (ex.: `models/epi_pretrained.pt`) — e, nesse caso, **limpe `YOLO_CLASSES`**, porque os índices em `.env.example` são específicos do Vyra.

Sem um modelo de EPI treinado/compatível configurado, o dashboard mostra aviso de "modelo não suportado" — o restante do sistema (detecção de pessoa, pose, área de risco) funciona normalmente mesmo assim.

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

## Testes

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