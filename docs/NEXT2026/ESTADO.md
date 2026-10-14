# ESTADO — MISSÃO 2

Retomar lendo só este arquivo e `MISSAO-2.md`. Reescrito a cada marco.
(A missão anterior, PRs #10–#13, está em `MISSAO.md` e no CHANGELOG.)

## Rollback

- `pre-missao-2` = HEAD de `feat/completo-com-rebrand` antes da missão (`906c81e`).
- `main-pre-release` = HEAD de `main` antes do release (`6c3ed61`).

## Marco atual: PR5 (Fases A + B) no portão

| item | situação | evidência |
|---|---|---|
| P0.1 rodízio ponderado | pronto; foco 52–58 % sob carga | `test_agendador_ponderado.py` (11), `diagnostico_foco.py`, E2E sem pausas |
| P0.2 incidentes + re-associação | pronto; multidão: máx. 1 incidente por regra+zona | `test_incidentes.py`, `test_reassociacao.py`, `contar_incidentes.py` |
| P0.3 `.env.example` 640 | pronto | `test_onboarding.py` |
| X1–X10 | código + unitários + E2E (ver tabela no CHANGELOG) | `e2e/test_missao2.py` |

Rodada 3 do E2E: 28/33; as 5 falhas levaram a quatro consertos (evidência por
análise, continuidade da queda, verificação paralela, pastas isoladas) — ver
CHANGELOG "Achados no caminho". Rodada 4 em execução.

## Decisões em vigor

- Foco = `video_feed` aberto ou consulta recente do portal (lease 3 s); foco alterna com atrasados.
- Emergência: 1 ficha de 2 s por detecção de queda; gravação a 4 fps durante a confirmação; regra de 2 análises mantida.
- Queda herda o sujeito de queda vista há ≤ 5 s a ≤ 1,5 largura.
- Evidência: um quadro e um replay por análise, compartilhados (`quadros_em`).
- SQLite em WAL; custódia em segundo commit, em lote.

## Worktrees

- `../ch5550-antes` (tag `pre-missao-2`): medições "antes" e bench de referência.
- `../ch5550-pr6` (branch `pr6-wip`): edições da Fase C ainda não commitadas.

## Próximo passo exato

E2E verde → bench `--rapido` ×3 intercalado com `../ch5550-antes` → commit →
PR5 → squash merge → recriar `next-2026` → aplicar a worktree do PR6.
