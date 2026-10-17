# ESTADO — MISSÃO 4 (em andamento)

Retomar lendo **só** `MISSAO-4.md` + este arquivo. Detalhe técnico em `CHANGELOG.md`.

## Onde estamos

- Branch de trabalho: `missao-4` (criada da `main` em `75d0de6`).
- Passo 0 concluído (17/10):
  - PR #18 mergeado na `main` por squash (`75d0de6`);
  - PR #9 (`rebrand/calma`) fechado com o comentário pedido;
  - tag `pre-missao-4` = `75d0de6` (push feito);
  - `docs/NEXT2026/MISSAO-4.md` salvo sem alterações.

## Pronto e verificado (branch `missao-4`, último commit `54f1b53`)

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

## Em andamento

- Crawler botão a botão nos 4 papéis (`e2e/test_todos_os_botoes.py`) rodando; resultado vai para `docs/NEXT2026/QA.md`.
- Agentes: identidade visual (Fase 3.1), páginas de exceção (3.9), primeiro acesso (3.2).

## Próximo passo exato

1. Corrigir o que o crawler apontar e rodar de novo até zero botão morto/erro de console.
2. Ligar no `App.tsx` as entregas dos agentes da Fase 3 (exceções, `/primeiro-acesso`, marca).
3. Portão do PR8: pytest completo, ruff, build, E2E completo (4 câmeras), crawler, axe → PR8 → squash → tag `missao-4-pr8`.

## Rollback

- `pre-missao-4` = HEAD da `main` antes da missão. Ou `git revert` do squash de cada PR.

## Ações negadas pela permissão (não contornadas)

- (nenhuma até agora)

## Herdado da MISSÃO 2 (continua valendo)

- Antes da apresentação: `python scripts/preparar.py` (véspera e manhã: `--so-cache`),
  depois `python run.py --demo` e o roteiro de `DEMO.md`. Plano B: vídeo da Release
  https://github.com/bolla-X/Challenge_5550/releases/tag/next-2026-demo.
- Ameaça nº 1: CPU tomada por outros programas (Docker, Salesforce CLI, Teams).
