# ESTADO — MISSÃO 2

Retomar lendo só este arquivo e `MISSAO-2.md` (incluindo o ADENDO 2 no fim).
Reescrito a cada marco. (A missão anterior, PRs #10–#13, está em `MISSAO.md` e
no CHANGELOG.)

## Rollback

- `pre-missao-2` = HEAD de `feat/completo-com-rebrand` antes da missão (`906c81e`).
- `main-pre-release` = HEAD de `main` antes do release (`6c3ed61`).

## Regra do ADENDO 2

Commit + push de `next-2026` (`origin/next-2026`) a cada marco e antes de
qualquer tarefa > 10 min em segundo plano.

## Marco atual: PR6 (Fase C) na rodada final de capturas

- PR5 = https://github.com/bolla-X/Challenge_5550/pull/14 (squash `69de586`).
- PR6 em `next-2026`: sistema de design, ícones Phosphor, estados, View
  Transitions; revisão visual em 6 rodadas (r1–r6) pela demo, crítica com notas
  em `docs/NEXT2026/galeria/index.md`, regras novas em DESIGN.md; README de
  vitrine; `scripts/preparar.py`; `e2e/video_do_palco.py` (MP4 + GIF).
- Unitários 658 verdes depois das mudanças (última rodada completa antes das
  correções de layout; o portão roda tudo de novo).

## Decisões em vigor

- Portal: 3 análises seguidas com tudo confirmado; até 2 análises SEM ninguém
  detectado no meio ficam neutras (`PORTAL_AUSENCIAS_TOLERADAS=2`); EPI faltando zera.
- Foco: `INFERENCIA_FRACAO_FOCO=0,5` (0,7 medido: quebra a regra dos 3 s em ~25 % dos intervalos).
- Queda: regra de 2 análises mantida; palco toca a gravação a 0,25× de 4 s em diante.
- Foco = `video_feed` aberto ou consulta recente do portal (lease 3 s); foco alterna com atrasados.
- Evidência: um quadro e um replay por análise, compartilhados (`quadros_em`).
- SQLite em WAL; custódia em segundo commit, em lote.

## Ameaças conhecidas (para o resumo final)

1. Portal com a gravação `bench.mp4`: p95 21,6 s (análises que veem trabalhador
   distante sem capacete zeram a confirmação). Com webcam diante de uma pessoa: não medido.
2. Subida com o cache dos modelos frio: ~4 min (compilação na iGPU; causa do cache frio não identificada).
3. Regra dos 3 s sem inferência: 9 % dos intervalos passam de 3 s sob carga (máx. 5,2 s).

## Worktrees

- `../ch5550-antes` (tag `pre-missao-2`): medições "antes" e bench de referência.
- `../ch5550-pr6` (branch `pr6-wip`): edições da Fase C ainda não commitadas.

## Próximo passo exato

r6 → conferir as telas de nota baixa → `scripts/galeria.py --rodada r6 --antes r0`
→ `e2e/video_do_palco.py` (copiar o GIF para `docs/NEXT2026/galeria/readme/`)
→ portão (pytest, ruff, build, E2E 4 câmeras + axe) → `bench.py --rapido` → PR6
→ squash → Fase D (clone limpo, Release com o vídeo, PR7).
