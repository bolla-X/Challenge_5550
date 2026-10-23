# ADR 0001: Flask + Socket.IO no backend, SPA React servida pelo próprio Flask

- **Status:** aceito (vigente)
- **Data:** 05/08/2026 (commit `292695a`, "Initial commit: VisionEPI com frontend React + TS + Vite"; resolução do conflito com a versão anterior em `d771ca7`)

## Contexto

O primeiro commit da `main` (`e1e483a`, 19/07/2026, "Adicionar projeto VisionEPI V5") é o protótipo. Em 05/08 o frontend foi migrado para
React + TypeScript + Vite e o merge manteve "a versão migrada para React" (`d771ca7`). O sistema precisa de duas coisas ao mesmo tempo:
inferência de visão em Python (YOLO, OpenCV, MediaPipe) e uma interface que atualiza ao vivo (vídeo, alertas, conformidade por pessoa).

## Decisão

- Backend em **Flask** (REST) com **Flask-SocketIO** para a telemetria ao vivo (`app/__init__.py`, `app/extensions.py`;
  `SOCKETIO_ASYNC_MODE` padrão `threading`).
- Frontend **React 18 + TypeScript + Vite** em `frontend/`, com estado global em Zustand assinando os eventos do socket.
- Em produção o **Flask serve o build estático** (`app/static/dist`, versionado no git). Em desenvolvimento o Vite roda em `:5173` com proxy
  para o Flask em `:5000`.
- O **vídeo vai por HTTP multipart (MJPEG)**, não pelo socket; o socket carrega só metadados (análise, alertas, conformidade). O cliente
  Socket.IO força `polling` (`frontend/src/socket/client.ts`).

## Consequências

- Um processo e uma origem servem API, socket e tela: um comando (`python run.py`) sobe tudo. O avaliador não precisa de Node para rodar
  a demo, porque o `dist` já vem no repositório (`docs/specs/ESTADO-es-sprint4.md`).
- O `dist` versionado entra no diff a cada build e exigiu cuidado com `.gitattributes` (o `palco.gif` do build foi corrompido por
  conversão de fim de linha; GIF, WebP, ICO e vídeo passaram a `binary`, `docs/NEXT2026/CHANGELOG.md`, "Fase 1 — correções de UI").
- Mover o vídeo para o socket piora: com o cliente em polling, binário vai em base64 (cerca de +33 %), `docs/NEXT2026/PESQUISA.md` §9
  e CHANGELOG §4.1 ("Socket.IO binário — não adotado").
- Com `threading`, o servidor de desenvolvimento do Werkzeug nunca vai para produção: quem serve é o gunicorn sobre `wsgi:app` (README).

## Alternativas

- Socket.IO binário como transporte de vídeo: **rejeitada** pelo motivo acima.
- Frontend servido só pelo Vite: **mantida apenas em desenvolvimento**.
- Outro framework de backend (por exemplo FastAPI): **sem registro** de comparação nos documentos do repositório; a escolha do Flask vem
  do protótipo de 19/07 (conteúdo desse commit não foi inspecionado na redação deste ADR).
