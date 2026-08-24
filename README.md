# VisionEPI

Sistema de monitoramento de segurança industrial em tempo real, desenvolvido para o **Challenge 2026 — Metaindústria** (FIAP × SPI Integração). Usa visão computacional para detectar uso de EPIs, analisar postura e comportamento, e sinalizar risco antes que o incidente aconteça — não apenas registrar a infração depois do fato.

## O problema

O modelo tradicional de segurança industrial é reativo: inspeções periódicas, checklists manuais, punição depois do incidente. O VisionEPI propõe o oposto — monitoramento contínuo por IA, alertas em tempo real, e uma camada de tendência que aponta onde o risco está se acumulando antes de virar acidente.

## Funcionalidades

- **Detecção de EPIs em tempo real** — capacete, colete, luvas e óculos de proteção, via modelo YOLOv8 dedicado, rodando em paralelo a um segundo modelo para detecção de pessoa (arquitetura dual-model).
- **Multi-pessoa** — múltiplas pessoas detectadas e avaliadas simultaneamente no mesmo frame.
- **Análise de postura e quedas** — via MediaPipe Pose, sinalizando posturas suspeitas e pessoas caídas.
- **Área de risco configurável** — editor visual de zona de risco; alerta quando uma pessoa entra na área.
- **Ciclo de vida de alertas com histerese** — alertas são criados/resolvidos após N frames consecutivos (não a cada frame instável), evitando ruído de falso positivo.
- **Tendência de risco** — score agregado por categoria (capacete/colete/luvas/quedas/postura/área de risco), calculado sobre o histórico real de alertas em janela deslizante, com sparkline de 24h. Estatística honesta sobre o histórico — não é predição de IA, é isso que os dados sustentam hoje.
- **Command palette (Ctrl/Cmd+K)** — navegação rápida entre painéis, troca de modo, iniciar/parar monitoramento, sem precisar do mouse.
- **Alertas sonoros** — som curto para alertas críticos e para o retorno a "tudo certo", com mute persistente e sempre visível.
- **Modo Operador / Técnico** — visão essencial para o campo, e um painel de diagnóstico completo (FPS, classes do modelo, diagnósticos de detecção) para quem precisa investigar.
- **Dashboard em tempo real** via WebSocket (Socket.IO) — feed de vídeo, conformidade por pessoa, linha do tempo de eventos, tudo atualizado ao vivo.

## Stack

**Backend**
- Python 3.11 · Flask · Flask-SQLAlchemy · Flask-SocketIO
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
- Python 3.11+
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

Acesse `http://localhost:5000`.

Para desenvolvimento do frontend com hot-reload, rode `npm run dev` dentro de `frontend/` em paralelo ao `python run.py` — o Vite abre em `http://localhost:5173` e faz proxy das chamadas de API/WebSocket para o Flask.

### Configuração do modelo de EPI

O `.env` aponta `PPE_MODEL_PATH` para o modelo de detecção de EPI. O padrão é **`models/vyra_ppe.pt`** ([Hexmon/vyra-yolo-ppe-detection](https://huggingface.co/Hexmon/vyra-yolo-ppe-detection), YOLOv8m, 14 classes, licença **CC-BY-4.0 — exige atribuição ao autor**).

Os pesos **não são versionados** (`.gitignore: *.pt`): baixe o arquivo e salve em `models/vyra_ppe.pt`.

Esse modelo já traz a classe `Person` (índice 11), então `MULTI_PERSON_DETECTION=false` desliga o segundo modelo YOLO (COCO, `PERSON_MODEL_PATH`) que antes rodava em paralelo só para suprir essa falta. Ele continua configurável: ligue `MULTI_PERSON_DETECTION=true` ao usar um modelo de EPI sem classe `person` (ex.: `models/epi_pretrained.pt`) — e, nesse caso, **limpe `YOLO_CLASSES`**, porque os índices em `.env.example` são específicos do Vyra.

Sem um modelo de EPI treinado/compatível configurado, o dashboard mostra aviso de "modelo não suportado" — o restante do sistema (detecção de pessoa, pose, área de risco) funciona normalmente mesmo assim.

## Testes

```bash
pytest
```

## Estrutura do projeto

```
app/                    Backend Flask
  api/                  Blueprints REST (status, alerts, monitor, risk, ...)
  services/             Lógica de negócio (monitor, alertas, compliance, risk score)
  repositories/          Acesso a dados
  vision/                Detecção YOLO, pose, matching pessoa-EPI
  models.py              Modelos SQLAlchemy
frontend/                SPA React + TypeScript + Vite
  src/
    api/                 Cliente REST e tipos
    socket/               Cliente WebSocket
    store/                Estado global (Zustand)
    components/           Componentes por domínio (vídeo, alertas, features, etc.)
tests/                    Testes backend (pytest)
```

## Roadmap

- [ ] Tracking estável (`model.track(persist=True)`) no lugar da ordenação espacial atual
- [ ] Matching geométrico EPI–pessoa por posição real, não por ordem de detecção
- [ ] Autenticação nos endpoints REST sensíveis
- [ ] Retry/backoff no stream de vídeo

## Equipe

Desenvolvido para o Challenge 2026 (FIAP × SPI Integração), com mentoria de Fernando V. Marcolina e Wendel de Almeida Passos.