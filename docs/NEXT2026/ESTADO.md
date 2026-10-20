# ESTADO — MISSÃO 4 (fechada em 20/10/2026)

Retomar lendo **só** `MISSAO-4.md` + este arquivo. Detalhe técnico em `CHANGELOG.md`.

## Onde estamos

- Branch de trabalho: `missao-4` (criada da `main` em `75d0de6`).
- Passo 0 concluído (17/10):
  - PR #18 mergeado na `main` por squash (`75d0de6`);
  - PR #9 (`rebrand/calma`) fechado com o comentário pedido;
  - tag `pre-missao-4` = `75d0de6` (push feito);
  - `docs/NEXT2026/MISSAO-4.md` salvo sem alterações.

## Pronto e verificado (PR8 e PR9 na `main`; PR10 abaixo)

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

## PR9 mergeado

- PR9 https://github.com/bolla-X/Challenge_5550/pull/20 → squash `2ede29a` na `main` (o `gh pr merge` deu erro
  transitório de GraphQL duas vezes; merge feito pelo endpoint REST oficial); tag `missao-4-pr9`.
- Portão: E2E completo numa rodada única em `0257acd`: 71 passed, 0 falhas, 2 skips; crawler 78 rotas×papéis, 834
  elementos, 0 problemas (`QA.md`). Commits seguintes só de `tests/` e `docs/`: pytest completo em `f443076`
  **3205 passed**, ruff limpo. Classificação de cada falha no CHANGELOG ("Portão do PR9").
- `missao-4` = `main` + merge (sem force push).

## PR10 mergeado — MISSÃO 4 fechada

- PR10 https://github.com/bolla-X/Challenge_5550/pull/21 → squash `4ca2a7e` na `main`; tags `missao-4-pr10` e
  `final-next-2026` (as duas em `4ca2a7e`). `missao-4` = `main` + merge.
- Portão final em `d14f5c8` (rodada única, na tomada): E2E 75 passed, 0 falhas, 2 skips; crawler 78 rotas × papéis,
  820 elementos, 0 problemas; pytest 3208 passed; ruff limpo.
- A partir da `main` (`4ca2a7e`): `e2e/fumaca_demo.py --raiz .` **6/6** (demo no ar em 26 s) e jornada 10 (palco
  pelo teclado e pelo celular) **1 passed**.
- Vídeo de backup: https://github.com/bolla-X/Challenge_5550/releases/tag/next-2026-demo (18 cenas, 202 s).

## Próximo passo exato

Nada pendente da MISSÃO 4 que dê para fazer de forma autônoma. Única pendência: o QA My App (abaixo), que depende de
você rodar `/qa-my-app:init` e depois `/qa-my-app:run-all`.

## Rollback

- `pre-missao-4` = HEAD da `main` antes da missão. Ou `git revert` do squash de cada PR.

## Bloqueios de ambiente

- 17–19/10: duas rodadas completas do portão do PR9 invalidadas por suspensão da máquina (tampa fechada e espera
  moderna na bateria; Kernel-Power 506/507 no log do Windows). O portão precisa de ~2 h com a máquina **na tomada e
  com a tampa aberta**. Detalhe no CHANGELOG ("Portão do PR9").

## Depende de você (não dá para rodar de forma autônoma)

- **QA My App (Fase 1 item 1 e Fase 5 item 1): nunca rodou.** O `/qa-my-app:init` (e o `run-all`) só aceita
  invocação explícita do usuário: o skill recusa a chamada do agente ("disable-model-invocation") e pede para não
  reproduzir o fluxo por outro meio. Não foi contornado. Para fechar: rode `/qa-my-app:init` no Claude Code, depois
  `/qa-my-app:run-all`. Cobertura que existe hoje na mesma área, sem substituir o catálogo: crawler botão a botão
  (`e2e/test_todos_os_botoes.py`, 78 rotas × papéis, `QA.md`) e matriz de permissões
  (`tests/test_matriz_de_permissoes.py`, 1633 casos).

## Ações negadas pela permissão (não contornadas)

- (nenhuma até agora)

## Herdado da MISSÃO 2 (continua valendo)

- Antes da apresentação: `python scripts/preparar.py` (véspera e manhã: `--so-cache`),
  depois `python run.py --demo` e o roteiro de `DEMO.md`. Plano B: vídeo da Release
  https://github.com/bolla-X/Challenge_5550/releases/tag/next-2026-demo.
- Ameaça nº 1: CPU tomada por outros programas (Docker, Salesforce CLI, Teams).
