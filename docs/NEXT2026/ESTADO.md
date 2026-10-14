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

## Marco atual: PR5 mergeado; PR6 (Fase C) em revisão visual

- PR5 = https://github.com/bolla-X/Challenge_5550/pull/14, squash `69de586` em
  `feat/completo-com-rebrand`. Portão: pytest 658, ruff, build, E2E 34/34 com 4
  câmeras e axe; bench intercalado passa (ver BENCHMARKS "Portão do PR5").
- `next-2026` recriada: squash do PR5 + o trabalho da Fase C (merge `6dbc2cc`
  conferido: o diff contra o squash é só o do PR6). Branches `pr6` e `pr6-wip`
  ficaram no remoto (a exclusão foi negada pela permissão).
- Capturas: `python e2e/capturas_de_tela.py --rodada rN --folhas` (3 tamanhos ×
  2 temas, estados forçados nomeados `forcado-*`); "antes" do PR6 em
  `bench/runtime/capturas/r0` (1920×1080 claro, código do PR5).
- Ameaças A/B do PR5: ver "Ameaças conhecidas".

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

Rodada r1 de capturas → crítica escrita por tela (rubrica da Fase C, nota 0–5)
em `docs/NEXT2026/galeria/index.md` → corrigir o que ficar abaixo de 4 → r2 →
`scripts/galeria.py --rodada r2 --antes r0` → README de vitrine → portão → PR6.
