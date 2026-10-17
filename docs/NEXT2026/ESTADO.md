# ESTADO — MISSÃO 4 (em andamento)

Retomar lendo **só** `MISSAO-4.md` + este arquivo. Detalhe técnico em `CHANGELOG.md`.

## Onde estamos

- Branch de trabalho: `missao-4` (criada da `main` em `75d0de6`).
- Passo 0 concluído (17/10):
  - PR #18 mergeado na `main` por squash (`75d0de6`);
  - PR #9 (`rebrand/calma`) fechado com o comentário pedido;
  - tag `pre-missao-4` = `75d0de6` (push feito);
  - `docs/NEXT2026/MISSAO-4.md` salvo sem alterações.

## Pronto e verificado (branch `missao-4`; portão do PR9 rodando sobre `d250824`)

| Item | Evidência |
|---|---|
| Fase 1.3 matriz de permissões | `tests/test_matriz_de_permissoes.py` 1403 passed; 8 divergências de segurança corrigidas (D1–D8) + `focar`; `docs/NEXT2026/PERMISSOES.md` |
| Fase 1.4 bug hunt | 7 bugs confirmados (C1–C7) corrigidos com regressão: `tests/test_regressao_bug_hunt.py`, `tests/test_regressao_c1_poligono.py` |
| Fase 1.5 copy | revisão pt-BR em todas as telas + `docs/NEXT2026/GLOSSARIO.md` |
| M1 saúde visual | `tests/test_saude_visual.py` 83 passed; E2E `test_m1_*` (MJPEG tampada: 3,8 s até OBSTRUÍDA, 9,9 s até o alerta) |
| M2 integração | `tests/test_integracao_industrial.py` 73 + `tests/test_estado_da_planta.py` (OPC UA/MQTT reais); E2E `test_m2_*`; `docs/NEXT2026/INTEGRACAO.md` |
| M3 evacuação | `tests/test_evacuacao.py`; E2E `test_m3_*` (pela tela até o elo na custódia íntegra) |
| M4 editor de regras | `tests/test_regras_editor.py` 111 (equivalência com as 17 nativas); E2E `test_m4_*` (testada no histórico e disparando ao vivo) |
| M5 permissão de trabalho | `tests/test_permissoes.py` 52; E2E `test_m5_*` (sem vigia → crítico; com vigia → some) |

Telas novas: `/torre`, `/evacuacao`, `/regras`, `/permissoes` (E2E sem erro de console).

Também prontos (sem E2E próprio ainda, salvo onde indicado): Fase 3 itens 2 (primeiro acesso, E2E jornada 1),
3 (tour), 4 (ajuda), 5 (sino), 6 (busca global), 7 (/status, novidades), 8 (configurações), 9 (exceções, E2E),
10 (/produto), 11 (feedback). Segurança extra: logout desfeito por requisição em voo (corrigido).

## PR8 mergeado

- PR8 https://github.com/bolla-X/Challenge_5550/pull/19 → squash `44dafdc` na `main`; tag `missao-4-pr8`.
- Portão: ruff ✓; build/typecheck ✓; pytest 3095 passed ✓; E2E completo 56/60 na rodada única + 4 corrigidas e
  reexecutadas ✓; crawler 78 rotas×papéis com 0 botão morto ✓ (`QA.md`); axe ✓. A rodada completa de E2E foi antes
  da Fase 4 entrar (ressalva no PR).
- `missao-4` = `main` + merge (sem force push; equivale a recriar a branch).

## Próximo passo exato (PR9 → depois PR10)

Já na branch desde o PR8: E2E da Fase 4 (`e2e/test_fase4.py`), as 10 jornadas em arquivos próprios
(`e2e/test_jornada_01…10_*.py`), injeção de falhas (`e2e/test_falhas.py`), auditoria de segurança (72 testes em
`tests/test_seguranca_missao4.py`), identidade (`MARCA.md`).

1. **Portão do PR9.** A 1ª rodada (sobre `9aae8a1`) foi interrompida pelo fim da sessão: o log só tinha o
   progresso (8 F), sem nome nem traceback, e não dá para classificar falha sem nome. Rodada nova sobre `d250824`
   (dist gerado do HEAD, texto novo do erro de câmera), com `-rfEs`, junit em `bench/runtime/portao9b.xml` e
   inferências/s por câmera (`bench/runtime/e2e-inferencia.jsonl`, lido por `scripts/e2e_carga.py`).
   Cada falha recebe uma classe, registrada no CHANGELOG: (a) bug de produto → squad fix, reproduzir antes, com
   teste de regressão; (b) premissa errada do teste → corrigir o teste sem afrouxar o que ele verifica;
   (c) sensível à carga → só se passar isolado **e** a câmera tiver recebido < 1 inferência/s na espera.
   Se houver mudança de código, roda-se o portão completo de novo, numa rodada única, com build novo do HEAD.
2. Depois do portão: pytest completo, `QA.md` regenerado, PR9 aberto (com o commit que o portão completo testou
   e a verificação dirigida dos commits seguintes), squash, tag `missao-4-pr9`, `missao-4` = `main` + merge.
3. **PR10, item de copy (Fase 5):** unificar os 67 textos "Falha ao…" de `frontend/src` no formato
   "Não foi possível <verbo> <objeto>." (`GLOSSARIO.md`/`MARCA.md`) e criar um teste de copy que falha se
   "Falha ao" aparecer em `frontend/src`.
4. Fase 3 item 12 / Fase 5 item 6: capturas nos dois temas e 3 resoluções + rubrica + galeria.
5. Fase 5 item 7: clone limpo seguindo o README até `e2e/fumaca_demo.py` passar. Fase 5 item 1: QA My App
   (run-all), ou o motivo registrado de não ter sido possível.
6. Fase 6: cenas novas do `/palco`, vídeo (uma vez) + asset da Release `next-2026-demo`, README/DEMO/BANCA,
   portão final, PR10, tags `missao-4-pr10` e `final-next-2026`, fumaça a partir da `main`.

## Rollback

- `pre-missao-4` = HEAD da `main` antes da missão. Ou `git revert` do squash de cada PR.

## Ações negadas pela permissão (não contornadas)

- (nenhuma até agora)

## Herdado da MISSÃO 2 (continua valendo)

- Antes da apresentação: `python scripts/preparar.py` (véspera e manhã: `--so-cache`),
  depois `python run.py --demo` e o roteiro de `DEMO.md`. Plano B: vídeo da Release
  https://github.com/bolla-X/Challenge_5550/releases/tag/next-2026-demo.
- Ameaça nº 1: CPU tomada por outros programas (Docker, Salesforce CLI, Teams).
