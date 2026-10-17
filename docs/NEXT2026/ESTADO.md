# ESTADO — MISSÃO 4 (em andamento)

Retomar lendo **só** `MISSAO-4.md` + este arquivo. Detalhe técnico em `CHANGELOG.md`.

## Onde estamos

- Branch de trabalho: `missao-4` (criada da `main` em `75d0de6`).
- Passo 0 concluído (17/10):
  - PR #18 mergeado na `main` por squash (`75d0de6`);
  - PR #9 (`rebrand/calma`) fechado com o comentário pedido;
  - tag `pre-missao-4` = `75d0de6` (push feito);
  - `docs/NEXT2026/MISSAO-4.md` salvo sem alterações.

## Próximo passo exato

Fase 1 (PR8 parte 1): matriz de permissões, bug hunt, revisão de copy e crawler
`e2e/test_todos_os_botoes.py`; em paralelo, módulos M1–M3 sem servidor.

## Rollback

- `pre-missao-4` = HEAD da `main` antes da missão. Ou `git revert` do squash de cada PR.

## Ações negadas pela permissão (não contornadas)

- (nenhuma até agora)

## Herdado da MISSÃO 2 (continua valendo)

- Antes da apresentação: `python scripts/preparar.py` (véspera e manhã: `--so-cache`),
  depois `python run.py --demo` e o roteiro de `DEMO.md`. Plano B: vídeo da Release
  https://github.com/bolla-X/Challenge_5550/releases/tag/next-2026-demo.
- Ameaça nº 1: CPU tomada por outros programas (Docker, Salesforce CLI, Teams).
