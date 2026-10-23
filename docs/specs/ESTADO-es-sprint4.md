# ESTADO — ES Sprint 4 (entrega 23/10/2026)

Retomar lendo `es-sprint4.md` (critérios) + este arquivo.

## Fase 0 — inventário (medido em 23/10/2026)

| Item | Achado | Como foi visto |
|---|---|---|
| G.1 rebrand | `git merge-base --is-ancestor origin/feat/completo-com-rebrand origin/main` → **exit 1**: o rebrand não está na main. Não mesclado. O dono confirmou: "A main já tem tudo, baseie-se nela". | comando no terminal |
| G.2 branch | `es-sprint4-entrega` criada de `main` = `origin/main` = `a4df215` (MISSÃO 7, #22) | `git switch -c es-sprint4-entrega main` |
| Workflows | não há `.github/` no repositório | `git ls-files` |
| Stack | Flask + Flask-SQLAlchemy + Alembic + Flask-SocketIO; YOLOv8 (Vyra) + YOLOv8n pessoa + YOLO11n-pose; OpenVINO/ONNX; MediaPipe; Gemini opcional; React 18 + TS + Vite + Zustand; `app/static/dist` é versionado | README, `requirements.txt`, `frontend/package.json`, `git ls-files` |
| Banco | SQLite (dev/demo) / PostgreSQL (Docker); 19 migrações Alembic; 18 tabelas em `app/models.py` | `migrations/versions`, `app/models.py` |
| Modo demo | já existe: `python run.py --demo` (banco isolado `instance/demo/demo.db`, contas com senha gerada impressa só no terminal, câmeras das gravações, webcam opcional como "Portal", LLM desligado) | `app/demo.py`, `app/demo_ambiente.py` |
| Gravações | **não versionadas**: `scripts/fetch_fixtures.py` baixa do Wikimedia Commons (licenças em `docs/FIXTURES.md`) | `docs/FIXTURES.md` |
| Pesos | Vyra/yolov8n/yolo11n-pose **não versionados** (baixados por `scripts/preparar.py` com SHA-256); `models/visionepi_cppe_n416.pt` versionado | `scripts/preparar.py` |
| LLM sem chave | camada desliga; não há fallback de demonstração | `app/services/llm_risk_service.py`, `frontend/src/components/llm-panel.tsx` |
| Gestão de EPIs | **não existe**: nenhum modelo de colaborador, catálogo com CA/validade, entrega ou ocorrência manual | `rg colaborador|certificado de aprova` em `app/` → 0 modelos |
| Telas | 25 rotas de tela cheia + grade/foco/kiosk/início do supervisor (`frontend/src/App.tsx`) | leitura |
| Testes | 120+ arquivos pytest em `tests/`; E2E Python/Playwright em `e2e/` (servidor real); `e2e/fumaca_demo.py` = fumaça do clone limpo (câmera → análise → vídeo → Portal "Liberado") | `git ls-files` |
| Lint | back: `ruff check .`; front: não há ESLint, o `tsc -b` do `npm run build` é a checagem | `pyproject.toml`, `package.json` |
| Links | nenhum link de Trello, Figma ou vídeo no repo; `docs/challenge/CONSOLIDADO.md` diz que o planejamento foi no Trello, sem URL | `rg trello.com|figma.com|youtu` |
| Scrum | não há backlog, review, retro nem DoD versionados | `rg` em `docs/` |
| Cronograma | `docs/challenge/CONSOLIDADO.md`: início 16/04/2026; Sprint 1 04/05; Sprint 2 22/06; Sprint 3 24/08; Sprint 4 e banca 23/09 | leitura |
| git log | 1º commit da main em 19/07/2026; Sprints 1 e 2 não têm commits na main | `git log --reverse --date=short main` |
| Equipe | `CONSOLIDADO.md` lista "Pedro Costa Belisário"; o prompt da entrega diz "Pedro Gonçalves — RM 557936". Vale o prompt (é do grupo); a divergência fica registrada, o documento antigo não é reescrito | leitura |

## Decisões tomadas pela sessão (o prompt não decidia; opção mais conservadora)

1. **Gestão de EPIs é módulo novo e separado da visão.** Tabelas próprias (colaboradores, catálogo, entregas,
   ocorrências). Nada liga colaborador a ID de rastreio ou a imagem: o princípio "por setor, nunca por pessoa" da
   visão continua valendo. Ficha de EPI é cadastro administrativo (NR-6), não vigilância.
2. **Dados simulados são marcados como simulados** (nomes fictícios, CAs e fabricantes fictícios) — nunca parecem
   registro real.
3. **Amostra versionada**: um recorte curto e leve derivado de `bench.mp4` (Commons, CC BY-SA 4.0, atribuição
   mantida). A demo usa as gravações completas quando existem; a amostra só entra quando elas faltam. O caminho
   oficial do README continua `scripts/preparar.py` (pesos com SHA-256), que precisa de internet uma vez.
4. **Fallback de LLM só na demo**: sem `GEMINI_API_KEY`, provedor determinístico rotulado "modo demonstração"; com a
   chave, o Gemini real. Fora da demo o comportamento não muda (sem chave = camada desligada).
5. **Front lint = `tsc -b`.** Não entra ESLint (dependência nova sem necessidade).
6. **Sprints da disciplina = sprints do Challenge** (cronograma do CONSOLIDADO); a Sprint 4 da disciplina vai até
   23/10 e inclui a final do NEXT. Sprints 1 e 2: reconstruídas dos documentos de fase (não há commits).

## Pronto e verificado

(preenchido à medida que cada critério fecha, com comando e saída)

| Critério | Evidência |
|---|---|
| F1.8 segredos | `git grep -I -E "AIza…|ghp_…|github_pat_…|sk-…|BEGIN … PRIVATE KEY|xox…|AKIA…" HEAD` → exit 1 (nada). Histórico (`git log --all -p -G …`): só `tests/test_pagina_status.py` (`"AI" + "zaSyCHAVE-FALSA-QUE-NAO-PODE-VAZAR-123456"`) e `tests/test_llm.py` (`"AIza" + "Sy" + "FALSA" * 6`), falsos de propósito. `.env` não é versionado; `.env.example` tem `GEMINI_API_KEY=` vazio. Nada a remover. |
| F1.3 fallback LLM | `tests/test_llm_demo_fallback.py` (4 testes) + `tests/test_llm.py`, `test_llm_async.py`, `test_camera_worker_llm.py`: 88 passed; `tests/test_pagina_status.py` falhou 1 vez sob carga (sonda de câmera com prazo 2,5 s enquanto outro agente rodava pytest) e passou isolado: **38 passed in 42.55s** |
| F1.2 amostra | `amostras/canteiro_amostra.mp4`: `ffprobe` → h264 640x360 12/1, 7,0 s, 469.317 bytes; atribuição em `amostras/LICENCA.md` |
| F5.3 cartelas | `scripts/video/gravar_cartelas.py` → 6 `.webm` VP8 1920x1080 (17,7 / 27,3 / 31,8 / 21,3 / 27,8 / 11,8 s) |
| F1.4/F1.5 seed e gestão (dev-backend) | migração `a8b9c0d1e2f3` (down `d3e4f5a6b7c8`, `compare_metadata` sem diferença); 1ª rodada: `test_gestao_seed` 14 passed, matriz+auth+openapi+onboarding+demo 1875 passed; após a revisão: `test_gestao_epi` 84 passed, `test_gestao_seed` 21 passed, risk score+relatório mensal+openapi+onboarding 103 passed, matriz 1785 passed |
| F1.6 tela `/gestao` (dev-frontend) | `npm --prefix frontend run build` ✓ (2m10s; depois 1m36s), `tests/test_copy_do_frontend.py` 1 passed |
| F1.7 lint | `ruff check .` → All checks passed! (depois de `--fix` de 2 I001 em arquivos novos); front: `tsc -b` no build ✓ |
| F1.9 pytest (1º passe, antes das correções da revisão) | `pytest -q` → **3494 passed, 8 warnings in 1221.06s** |
| F1.10 E2E da entrega | `e2e/test_es_sprint4.py`: 1ª rodada 9 passed / 2 failed (defeitos do teste: regex `(?i)` não vale em JS; Setor é input) → corrigido → **11 passed in 55.25s**; após as correções da revisão: **11 passed in 142.36s** |
| Portão da squad (rodada 1) | auditor (sem STOP; S1 alto privacidade, S2–S7 médios, S8 adiado, S9–S12 baixos), UX (1 bloqueador foco, 6 importantes), CX (P0 senhas/LLM/relatório/porta), UI-design (2 P1 CSS) → todos os itens aceitos corrigidos na rodada 2, exceto S8 (fuso via `zoneinfo` exige `tzdata` no Windows = dependência nova; fica como limitação) |
| F4.2/F4.3 Trello | board novo e público criado pelo MCP: https://trello.com/b/zVZW2n1p/visionepi-challenge-3ecr ; listas Product Backlog, Sprint 1–4, Concluído, Reviews/Atas. Limitação: o MCP não renomeia etiquetas (só cria) → cores com legenda no card "Legenda do board" |

## Ações negadas pela permissão (não contornadas)

- `git -C <repo> switch -c ...` foi recusado pelo dono; refeito sem `-C`, já no diretório do projeto.
