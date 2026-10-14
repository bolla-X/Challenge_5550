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

## Marco atual: ADENDO 2, itens A e B prontos; próximo: bench do portão do PR5

| item | situação | evidência |
|---|---|---|
| Recuperação | pytest 649, ruff, build idênticos ao pré-reinício; wip `2116c1c` no remoto | CHANGELOG "ADENDO 2 / Recuperação" |
| A. Portal "Liberado" | p50 **5,6 s**, p95 **21,6 s** (antes 16,8 / 81,0) — **meta não atingida** | `bench/results/portal-liberado-adendo2-20261014.json`, CHANGELOG "ADENDO 2 / A" |
| B. Queda a 0,25× no palco | pronto; alerta ao vivo 12,9 s após entrar na cena | `test_camera_lenta.py`, `test_palco.py`, E2E `test_palco_queda_ao_vivo_em_camera_lenta`, BANCA 21 |
| P0.1–P0.3, X1–X10 | como antes (ver CHANGELOG); E2E 33/33 na rodada 8 pré-reinício | `e2e/` |

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
2. 1ª subida depois de reiniciar o notebook: ~4 min (compilação dos modelos na iGPU).
3. Regra dos 3 s sem inferência: 9 % dos intervalos passam de 3 s sob carga (máx. 5,2 s).

## Worktrees

- `../ch5550-antes` (tag `pre-missao-2`): medições "antes" e bench de referência.
- `../ch5550-pr6` (branch `pr6-wip`): edições da Fase C ainda não commitadas.

## Próximo passo exato

Bench intercalado "antes × PR5" (`scripts/rodar_portao.py --rotulo pr5gate
--reps 1,2,3 --perfis atual --cameras 1,4 --arvores "antes=../ch5550-antes,pr5=."`)
→ BENCHMARKS.md → portão completo numa rodada (pytest, ruff, build, E2E com 4
câmeras, axe) → PR5 → squash merge → recriar `next-2026` → Fase C (PR6).
