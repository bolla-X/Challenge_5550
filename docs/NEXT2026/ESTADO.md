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

## Marco atual: PR5 no portão verde, aberto para squash merge

| item | situação | evidência |
|---|---|---|
| Recuperação | pytest 649, ruff, build idênticos ao pré-reinício; wip `2116c1c` no remoto | CHANGELOG "ADENDO 2 / Recuperação" |
| A. Portal "Liberado" | p50 **5,6 s**, p95 **21,6 s** (antes 16,8 / 81,0) — **meta não atingida** | `bench/results/portal-liberado-adendo2-20261014.json`, CHANGELOG "ADENDO 2 / A" |
| B. Queda a 0,25× no palco | pronto; alerta ao vivo 12,9 s após entrar na cena | `test_camera_lenta.py`, `test_palco.py`, E2E `test_palco_queda_ao_vivo_em_camera_lenta`, BANCA 21 |
| Bench antes × PR5 | passa (pior: +6 % CPU/análise, 1 câmera) | BENCHMARKS "Portão do PR5" |
| Portão do PR5 (rodada única, 14/10) | pytest 658, ruff, build (dist idêntico), E2E 34/34 com 4 câmeras e axe claro/escuro | `bench/runtime/portao-pr5/` (local) |

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

Squash merge do PR5 → recriar `next-2026` de `feat/completo-com-rebrand` →
trazer a branch `pr6` (Fase C já rebaseada sobre o PR5, commit `6cb3f78` +
capturas/galeria) → capturas r1 → revisão escrita → correções → r2 → galeria
e README → portão → PR6.
