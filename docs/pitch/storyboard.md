# Storyboard — vídeo da Sprint 4 (Engenharia de Software, 3ECR)

Vídeo **sem narração e sem áudio**. Todo o conteúdo vai por cartelas e por uma barra de legenda fixa embaixo.
Formato: 1920x1080, MP4 H.264, 30 fps. Duração-alvo: **4:35** (limite do enunciado: 5:00; faixa do grupo: 4:00 a
4:45).

Como reproduzir: `scripts/video/README.md` (cartelas e demo gravadas com Playwright, montagem com ffmpeg). O vídeo
não é versionado.

Regras de texto: legenda curta (até ~80 caracteres por linha, no máximo 2 linhas), tempo de leitura de pelo menos
4 s por legenda; números só os que estão medidos nos documentos do repositório, com a fonte entre parênteses no
próprio storyboard.

| # | Cena | Tipo | Início | Duração | O que aparece |
|---|---|---|---|---|---|
| 1 | Abertura | cartela | 0:00 | 15 s | Nome do projeto, turma, integrantes com RM |
| 2 | Problema | cartela | 0:15 | 25 s | O problema da Metaindústria |
| 3 | Solução e arquitetura | cartela | 0:40 | 30 s | A solução e a arquitetura numa imagem |
| 4 | Demonstração | gravação do app | 1:10 | 150 s | Fluxos principais em modo demonstração, tema claro |
| 5 | Impacto esperado | cartela | 3:40 | 20 s | O que muda para a Metaindústria |
| 6 | Evolução das 4 sprints | cartela | 4:00 | 25 s | Do protótipo ao produto |
| 7 | Encerramento | cartela | 4:25 | 10 s | Repositório, Trello, equipe |
| | **Total** | | | **275 s = 4:35** | |

## 1. Abertura (15 s)

- Título: **VisionEPI**
- Subtítulo: Gestão de EPIs e segurança industrial para a Metaindústria
- Linha: FIAP · Engenharia de Software · Turma 3ECR · Sprint 4 · Prof. Hercules Lima Ramos
- Integrantes: Pedro Gonçalves — RM 557936 · Lucas Baraldi — RM 555407 · Lucas Zolla — RM 557952 ·
  Vitor Pantarotto — RM 554961

## 2. Problema (25 s)

- Título: O problema
- Três pontos, entrando um por vez (8 s cada):
  1. A segurança é reativa: inspeção periódica, checklist manual, punição depois do incidente.
  2. A ficha de EPI fica no papel: entrega sem histórico, troca vencida e CA vencido passam despercebidos.
  3. A ocorrência é registrada depois do fato, sem ligação com o que as câmeras já mostravam.

## 3. Solução e arquitetura (30 s)

- Título: A solução
- Frase: Câmeras comuns que enxergam EPI, queda e área de risco ao vivo, e uma ficha de EPI digital no mesmo sistema.
- Diagrama (uma imagem): Câmeras (RTSP, USB, gravação) → Visão (YOLO EPI + pessoa + pose) → Regras e histerese →
  Alertas e incidentes → Flask (REST + Socket.IO) → Painel React. Ao lado, fora do caminho do quadro: segunda opinião
  LLM (Gemini; sem chave, modo demonstração). Embaixo: Gestão de EPIs (colaboradores, catálogo com CA, entregas,
  ocorrências, CSV), separada da visão. Banco SQLite/PostgreSQL.
- Rodapé: Por setor, nunca por pessoa: a visão não identifica ninguém.

## 4. Demonstração (150 s)

Gravada com o app em `python run.py --demo` (tema claro, sem câmera IP, sem `GEMINI_API_KEY`). Cursor visível, pausas
para leitura. Legendas na barra fixa embaixo:

| Sub-cena | Duração | Tela | Legenda |
|---|---|---|---|
| 4a | 15 s | Login → Início do supervisor | Modo demonstração: sem câmera IP e sem chave de API. Entramos como supervisora. |
| 4b | 20 s | Grade de câmeras | Monitoramento em tempo real: quatro câmeras da demo, cada uma analisada ao vivo. |
| 4c | 30 s | Foco de uma câmera, incidentes, segunda opinião | O alerta nasce da detecção. A segunda opinião aparece rotulada "modo demonstração". |
| 4d | 25 s | Gestão de EPIs → Colaboradores → histórico | Cada colaborador tem a ficha de EPI: o que recebeu, quando, e o que vence. |
| 4e | 15 s | Catálogo de EPIs | Catálogo com CA e validade: vencido e a vencer aparecem antes de virar problema. |
| 4f | 15 s | Entregas → tentativa com CA vencido | Entrega de EPI com CA vencido é bloqueada pela política da empresa. |
| 4g | 15 s | Ocorrências → registrar | Ocorrência registrada com gravidade, setor e ação corretiva. |
| 4h | 15 s | Relatórios e exportação → CSV; relatório mensal | Tudo exporta em CSV, e o relatório mensal vai para a CIPA. |

## 5. Impacto esperado (20 s)

- Título: Impacto esperado
- Medido no projeto (com fonte):
  - Primeiro alerta em cerca de 2 s no perfil "batata" (2 núcleos de eficiência); antes, 38 s (README, NEXT 2026).
  - Precisão do alerta "sem capacete": 0,39 → 0,85 em 236 pessoas anotadas (docs/SPRINT4.md).
- Esperado (não medido em planta):
  - Ficha de EPI digital, com histórico e exportação (NR-6, item 6.5.1 d).
  - CA vencido e troca vencida visíveis antes da entrega.
  - Ocorrência com ação corretiva rastreável.

## 6. Evolução das 4 sprints (25 s)

Quatro colunas, entrando da esquerda para a direita:

- **Sprint 1 (até 04/05/2026)**: detecção de EPIs, rastreio de pessoas, zona de risco.
- **Sprint 2 (até 22/06/2026)**: pose por pessoa, queda e postura.
- **Sprint 3 (até 24/08/2026)**: painel React, alertas com severidade, portaria, login com papéis, multicâmera.
- **Sprint 4 (até 23/10/2026)**: segunda opinião LLM, peso treinado, final do FIAP NEXT, gestão de EPIs, modo
  demonstração reprodutível.
- Rodapé: Cronograma: docs/challenge/CONSOLIDADO.md. Sprints 1 e 2 reconstruídas dos documentos de fase.

## 7. Encerramento (10 s)

- VisionEPI
- github.com/bolla-X/Challenge_5550
- Trello: trello.com/b/zVZW2n1p
- Pedro Gonçalves · Lucas Baraldi · Lucas Zolla · Vitor Pantarotto — 3ECR
