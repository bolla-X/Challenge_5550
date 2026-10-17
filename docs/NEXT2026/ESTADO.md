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

Também prontos (sem E2E próprio ainda, salvo onde indicado): Fase 3 itens 2 (primeiro acesso, E2E jornada 1),
3 (tour), 4 (ajuda), 5 (sino), 6 (busca global), 7 (/status, novidades), 8 (configurações), 9 (exceções, E2E),
10 (/produto), 11 (feedback). Segurança extra: logout desfeito por requisição em voo (corrigido).

## Em andamento

- **Portão do PR8** sobre o commit `ad13411`: ruff ✓; pytest completo 2771 passed + os 4 que falharam corrigidos e
  reexecutados isolados ✓ (guardas de segredo em teste novo, exceção pública `/api/contatos`, regressão do C3 no
  `_loop_assincrono`); build ✓; E2E completo (`pytest e2e`: 4 câmeras + crawler + axe) rodando.
- Agentes da Fase 4 (sem servidor): M6+M11, M7+M8, M10+M9. Identidade visual (3.1) finalizando.

## Próximo passo exato

1. Ler o resultado do E2E do portão (`scratchpad/portao_e2e.log`); corrigir o que falhar e reexecutar só o que falhou.
2. Branch `pr8` no commit verificado → PR8 "QA de base + Fábrica conectada" → squash → tag `missao-4-pr8` →
   recriar `missao-4` a partir da `main` e trazer o que veio depois (merge da antiga `missao-4`).
3. Integrar M6–M11 (registrar blueprints, matriz, rotas), Fase 3 item 12 (revisão visual), PR9.

## Rollback

- `pre-missao-4` = HEAD da `main` antes da missão. Ou `git revert` do squash de cada PR.

## Ações negadas pela permissão (não contornadas)

- (nenhuma até agora)

## Herdado da MISSÃO 2 (continua valendo)

- Antes da apresentação: `python scripts/preparar.py` (véspera e manhã: `--so-cache`),
  depois `python run.py --demo` e o roteiro de `DEMO.md`. Plano B: vídeo da Release
  https://github.com/bolla-X/Challenge_5550/releases/tag/next-2026-demo.
- Ameaça nº 1: CPU tomada por outros programas (Docker, Salesforce CLI, Teams).
