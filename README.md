# VisionEPI

Sistema modular de monitoramento inteligente com visão computacional em tempo real para detecção de EPIs, análise de postura, identificação de quedas, permanência em área de risco, alertas operacionais ativos/resolvidos e dashboard com WebSocket.

## Dashboard

O dashboard está disponível nas rotas:

```bash
http://localhost:5000/
http://localhost:5000/dashboard
```

Arquivos usados pelo Flask:

```txt
app/templates/index.html
app/static/styles.css
app/static/app.js
```

Também existe uma cópia em `dashboard/` na raiz do projeto para facilitar localização e inspeção visual.

## Stack

- Python
- OpenCV
- Ultralytics YOLO
- MediaPipe Pose
- Flask REST API
- Flask-SocketIO
- PostgreSQL com SQLAlchemy
- HTML, CSS e JavaScript
- Pytest
- Docker opcional

## Arquitetura

```text
VisionEPI/
├── app/
│   ├── api/                  # Endpoints REST e stream MJPEG
│   ├── repositories/         # Persistência de alertas
│   ├── services/             # Orquestração, features, regras, alertas
│   ├── static/               # CSS/JS do dashboard
│   ├── templates/            # HTML do dashboard
│   ├── utils/                # Logging estruturado
│   ├── vision/               # Stream, YOLO, MediaPipe, schemas, anotação
│   ├── config.py             # Configuração por .env
│   ├── extensions.py         # SQLAlchemy e SocketIO
│   ├── models.py             # Modelo Alert
│   └── __init__.py           # App factory
├── tests/                    # Testes pytest
├── run.py                    # Execução local
├── wsgi.py                   # Entrada para deploy WSGI
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── .env.example
```

## Funcionalidades implementadas

- Captura de webcam ou vídeo local via `VideoStream`.
- Detecção YOLO com retorno de bounding boxes, labels, confiança e class ID.
- Normalização de labels de EPIs: `helmet`, `vest`, `gloves`.
- MediaPipe Pose Estimation com landmarks corporais.
- Regras para:
  - sem capacete: crítico;
  - sem colete: alto;
  - sem luvas: médio;
  - pessoa caída: crítico;
  - postura suspeita: médio;
  - pessoa em área de risco simulada: alto.
- Persistência de alertas no banco.
- Emissão de eventos via WebSocket:
  - `alert_created`
  - `alert_updated`
  - `alert_resolved`
  - `active_alerts`
  - `compliance_state`
  - `model_diagnostics`
  - `analysis`
  - `monitor_status`
  - `features_updated`
- Dashboard com:
  - feed de vídeo anotado em tempo real;
  - feedback de conformidade atual por capacete, colete, luvas, pose e área de risco;
  - diagnóstico do modelo YOLO carregado;
  - alertas ativos que desaparecem quando a condição normal retorna;
  - histórico recente persistido;
  - botões iniciar/parar;
  - painel para selecionar features lidas pelo backend.
- Testes básicos de API e regras com mock de detecção.

## Observação crítica sobre o modelo YOLO de EPIs

O sistema agora diagnostica o modelo carregado e informa no dashboard se as classes de EPI estão disponíveis. O arquivo `.env` usa `PPE_MODEL_PATH=yolov8n.pt` como padrão para execução inicial, mas esse modelo é genérico/COCO e normalmente não reconhece capacete, colete e luvas industriais como classes próprias.

Com um modelo incompatível, o dashboard exibirá `não suportado pelo modelo` para capacete/colete/luvas. Isso evita falso feedback de detecção. Para uso real, treine ou forneça um modelo customizado com classes compatíveis, por exemplo:

```text
person
helmet
vest
gloves
```

Depois aponte:

```env
PPE_MODEL_PATH=/caminho/para/seu/modelo_epi.pt
```

Aliases aceitos pelo normalizador incluem `hardhat`, `hard_hat`, `safety helmet`, `safety vest`, `reflective vest`, `glove` e `safety gloves`. Internamente todos são normalizados para `helmet`, `vest` ou `gloves`.

## Alertas ativos e resolução automática

O sistema separa operação em tempo real de histórico:

```text
Alertas ativos   -> aparecem no painel principal e somem quando a violação é resolvida
Histórico recente -> permanece salvo no banco com status active/resolved
```

Variáveis de controle:

```env
ALERT_CREATE_AFTER_FRAMES=3
ALERT_RESOLVE_AFTER_FRAMES=5
```

Isso evita poluição visual e reduz oscilação. Um alerta só nasce após alguns frames consecutivos com problema e só desaparece após alguns frames consecutivos sem o problema.

## Setup local

### 1. Criar ambiente virtual

```bash
python -m venv .venv
source .venv/bin/activate
# Windows:
# .venv\Scripts\activate
```

### 2. Instalar dependências

```bash
pip install -r requirements.txt
```

### 3. Configurar ambiente

```bash
cp .env.example .env
```

Para desenvolvimento sem PostgreSQL, remova ou comente `DATABASE_URL` no `.env`. O sistema cairá para SQLite local.

Para PostgreSQL local, mantenha:

```env
DATABASE_URL=postgresql+psycopg2://visionepi:visionepi@localhost:5432/visionepi
```

### 4. Subir PostgreSQL com Docker

```bash
docker compose up -d postgres
```

### 5. Executar aplicação

```bash
python run.py
```

Acesse:

```text
http://localhost:5000
```

## Uso com vídeo local

No `.env`:

```env
VIDEO_SOURCE=/caminho/video.mp4
```

Para webcam:

```env
VIDEO_SOURCE=0
```

## API REST

### Status

```http
GET /status
```

Resposta:

```json
{
  "system": "VisionEPI",
  "running": false,
  "frame_counter": 0,
  "last_error": null,
  "features": {}
}
```

### Listar alertas

```http
GET /alerts?limit=100
GET /alerts?status=active
GET /alerts?status=resolved
```

### Iniciar monitoramento

```http
POST /start
```

### Parar monitoramento

```http
POST /stop
```

### Listar features

```http
GET /features
```

### Atualizar features

```http
PATCH /features
Content-Type: application/json

{
  "features": {
    "helmet": true,
    "vest": false,
    "gloves": true,
    "pose": true,
    "falls": true,
    "posture": false,
    "risk_area": true
  }
}
```

## Features disponíveis

| Key | Função |
|---|---|
| `ppe` | Ativa/desativa processamento YOLO de EPIs |
| `helmet` | Regra de capacete |
| `vest` | Regra de colete |
| `gloves` | Regra de luvas |
| `pose` | Ativa/desativa MediaPipe |
| `falls` | Regra de queda |
| `posture` | Regra de postura inadequada |
| `risk_area` | Regra de área de risco simulada |

## WebSocket

Eventos emitidos pelo servidor:

```text
alert_created      # novo alerta operacional ativo
alert_updated      # alerta ainda ativo, last_seen/occurrences atualizados
alert_resolved     # alerta resolvido; frontend remove da lista ativa
active_alerts      # snapshot dos alertas ativos
compliance_state   # feedback atual por feature
model_diagnostics  # classes suportadas pelo modelo YOLO
analysis
monitor_status
features_updated
```

## Área de risco simulada

A área de risco é definida por coordenadas normalizadas no `.env`:

```env
RISK_AREA_POLYGON=0.70,0.10;0.98,0.10;0.98,0.95;0.70,0.95
```

Formato:

```text
x1,y1;x2,y2;x3,y3;x4,y4
```

Onde `x` e `y` vão de `0.0` a `1.0` em relação à largura e altura do frame.

## Testes

```bash
pytest
```

Cobertura dos testes:

- endpoints `/status`, `/start`, `/stop`, `/alerts`, `/features`;
- criação, atualização, resolução e listagem de alertas;
- regras de EPI com mock de detecção;
- regra de queda com mock de landmarks;
- regra de área de risco com bounding box simulada.

## Deploy

### Docker completo

```bash
cp .env.example .env
docker compose up --build
```

### Produção

Para produção, recomenda-se:

- substituir `SECRET_KEY`;
- usar PostgreSQL gerenciado;
- desativar `AUTO_CREATE_TABLES` e usar migrations;
- usar modelo YOLO customizado de EPIs;
- configurar CORS do SocketIO com domínio específico;
- usar Nginx na frente do app;
- executar com worker compatível com WebSocket.

## Expansão futura

Pontos preparados para extensão:

- novos EPIs no `FeatureManager`, `ComplianceService` e aliases do `YoloPPEDetector`;
- novas regras no `RuleEngine`;
- novos modelos no pacote `app/vision`;
- persistência adicional em novos repositories;
- autenticação e multi-câmera por novos blueprints e serviços;
- filas assíncronas para processamento distribuído.

## Sprint 1 de UX operacional

Esta versão reorganiza o dashboard para reduzir poluição visual no vídeo. O frame agora fica reservado para informações visuais de detecção: bounding boxes, labels, confiança, pose e zona de risco. Status de conformidade, modelo, alertas, checklist e cards de pessoas ficam fora do vídeo.

### Melhorias aplicadas

- Layout dividido em visão operacional e visão técnica.
- Modo Operador: mostra o essencial para uso em campo.
- Modo Técnico: exibe FPS, frames, diagnóstico do modelo, classes YOLO e histórico.
- Barra superior de status: backend, WebSocket, monitor, vídeo, frames e FPS visual.
- Checklist pré-start em `GET /preflight`.
- Cards de conformidade fora do vídeo.
- Cards de pessoas/detecções fora do vídeo.
- Perfis rápidos de features: Básico, EPI, Risco e Completo.
- Painel de alertas ativos separado do histórico.
- Mensagem operacional persistente para modelo YOLO incompatível ou incompleto.
- Limpeza automática de artefatos temporários no início do monitoramento.
- Resolução automática de alertas ativos antigos ao iniciar um novo ciclo de teste.

### Limpeza automática de arquivos de teste

Ao executar `POST /start`, o sistema limpa os diretórios configurados em:

```env
CLEANUP_ON_MONITOR_START=true
CLEANUP_DIRECTORIES=runtime/snapshots,runtime/frames,runtime/tmp
SNAPSHOT_DIR=runtime/snapshots
```

A limpeza remove arquivos antigos de snapshots, frames temporários e arquivos de teste, sem apagar banco, modelos, código-fonte ou configurações.

### Checklist pré-start

```http
GET /preflight
```

Retorna validações de:

- Backend
- WebSocket
- Banco
- Fonte de vídeo configurada
- Modelo YOLO
- Limpeza automática

O checklist exibe avisos sem bloquear testes quando o problema não é crítico, por exemplo modelo PPE ainda não carregado.

## Atualização Sprint 2 — multi-pessoa e UX técnica

### Correção multi-pessoa

O sistema agora roda YOLO como base de detecção multi-pessoa quando `MULTI_PERSON_DETECTION=true`, mesmo que a feature de EPI esteja desligada. Isso corrige o caso em que apenas uma pessoa aparecia quando o fluxo dependia somente do MediaPipe Pose.

Pontos técnicos:

- YOLO retorna múltiplas bounding boxes por frame.
- `YOLO_MAX_DETECTIONS` controla o limite máximo de caixas aceitas por inferência.
- MediaPipe Pose permanece como pose global/auxiliar, pois a solução usada no projeto não é a base principal para multi-pessoa.
- Alertas de EPI e área de risco agora recebem `person_id` quando há múltiplas pessoas.
- Cards externos ao vídeo mostram uma linha por pessoa detectada.

Configuração recomendada:

```env
MULTI_PERSON_DETECTION=true
YOLO_MAX_DETECTIONS=100
```

### Sprint 2 implementado

Incluído:

- Endpoint `GET /model` para diagnóstico do modelo carregado.
- Endpoint `GET /settings` para configurações runtime.
- Endpoint `PATCH /settings` para ajustes rápidos sem editar `.env`.
- Endpoint `GET /overlay` para estado dos overlays.
- Endpoint `PATCH /overlay` para ligar/desligar boxes, labels, confiança, pose e zona de risco.
- Filtros no histórico de alertas por status e severidade.
- Controles técnicos de overlay no dashboard.
- Painel de configurações rápidas no modo Técnico.
- Cards multi-pessoa fora do vídeo.

### Observação sobre pose multi-pessoa

A contagem e os cards multi-pessoa vêm do YOLO. A pose continua sendo global/auxiliar com MediaPipe. Para pose multi-pessoa real em produção, a evolução correta é integrar um modelo de pose multi-pessoa, como YOLO pose, mantendo MediaPipe apenas como fallback.

## Atualização Sprint 3 — operação, evidências e área de risco editável

Incluído:

- Editor visual de área de risco no modo Técnico.
- Endpoint `GET /risk-area`.
- Endpoint `PATCH /risk-area`.
- Linha do tempo operacional no dashboard.
- Endpoint `GET /events`.
- Snapshots automáticos de evidência ao criar alertas.
- Endpoint `GET /snapshots/<arquivo>` para visualizar evidência.
- Botão `Falso positivo` em cada alerta.
- Endpoint `POST /alerts/<id>/false-positive`.
- Eventos persistidos em `event_logs`.
- Limpeza de snapshots antigos mantida no início do monitoramento.

### Área de risco editável

No modo Técnico, use `Editor de área de risco`:

1. Clique em `Editar no vídeo`.
2. Clique no feed para adicionar pontos.
3. Use pelo menos 3 pontos.
4. Clique em `Salvar zona`.

O backend aplica a área imediatamente em runtime. A persistência definitiva continua sendo recomendada pelo `.env` em produção:

```env
RISK_AREA_POLYGON=0.70,0.10;0.98,0.10;0.98,0.95;0.70,0.95
RISK_AREA_NAME=Área de risco
```

Formato do endpoint:

```http
PATCH /risk-area
Content-Type: application/json

{
  "name": "Esteira 01",
  "polygon": [
    {"x": 0.70, "y": 0.10},
    {"x": 0.98, "y": 0.10},
    {"x": 0.98, "y": 0.95},
    {"x": 0.70, "y": 0.95}
  ]
}
```

### Evidências por snapshot

Quando um alerta é criado, o sistema salva uma imagem em:

```env
SNAPSHOT_DIR=runtime/snapshots
SNAPSHOT_ENABLED=true
SNAPSHOT_JPEG_QUALITY=86
```

O dashboard mostra `Ver evidência` no card do alerta. Ao iniciar novo monitoramento, os snapshots antigos são removidos se `CLEANUP_ON_MONITOR_START=true`.

### Falso positivo

O botão `Falso positivo` marca o alerta no histórico sem apagar o registro. O alerta recebe metadata:

```json
{
  "false_positive": true,
  "false_positive_reason": "Marcado pelo operador no dashboard",
  "false_positive_at": "..."
}
```

Se o alerta ainda estiver ativo, ele é resolvido automaticamente para não permanecer poluindo a tela.

### Linha do tempo

A timeline registra eventos como:

- monitoramento iniciado;
- monitoramento parado;
- alerta criado;
- alerta resolvido;
- área de risco atualizada;
- configurações alteradas;
- falso positivo marcado.

Endpoint:

```http
GET /events?limit=80
```


## Atualização UX / Timeline / Evidências

- O botão `Ver evidência` agora usa o endpoint seguro `GET /alerts/<id>/evidence`, que busca o snapshot pelo alerta salvo no banco.
- A linha do tempo operacional mostra apenas alertas que estiveram ativos e foram resolvidos.
- A deduplicação da linha do tempo usa `alert_id`; o mesmo alerta não aparece duas vezes após reload, WebSocket ou atualização manual.
- O checklist pré-start foi removido da visão do Operador e fica disponível apenas no modo Técnico.
- As features analisadas ficam em uma faixa horizontal com ícones SVG e status textual.
- O vídeo permanece reservado para detecção visual; cards de features, conformidade, pessoas e timeline ficam fora do frame.
