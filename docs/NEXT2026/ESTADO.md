# ESTADO — MISSÃO 4 (em andamento)

Retomar lendo **só** `MISSAO-4.md` + este arquivo. Detalhe técnico em `CHANGELOG.md`.

## Onde estamos

- Branch de trabalho: `missao-4` (criada da `main` em `75d0de6`).
- Passo 0 concluído (17/10):
  - PR #18 mergeado na `main` por squash (`75d0de6`);
  - PR #9 (`rebrand/calma`) fechado com o comentário pedido;
  - tag `pre-missao-4` = `75d0de6` (push feito);
  - `docs/NEXT2026/MISSAO-4.md` salvo sem alterações.

## Em andamento (commit `f5bb471`, wip)

- Fontes verificadas (NR-33, NR-35, NR-6, licenças asyncua/paho/amqtt, OPC UA, MQTT, OpenAPI, COCO): no CHANGELOG, seção MISSÃO 4.
- M3 backend pronto: `app/services/evacuacao.py`, `app/api/evacuacao.py` (registrado), elo `evacuacao` na custódia;
  `pytest tests/test_evacuacao.py tests/test_custodia.py` → 43 passed.
- Escritos, ainda sem ligação/E2E: `e2e/test_todos_os_botoes.py` (crawler), `frontend/src/components/evacuacao.tsx`,
  `torre.tsx`, `styles/missao4.css`, token `--sinal-amarelo`.
- Em execução por agentes (arquivos podem estar incompletos no wip): matriz de permissões
  (`tests/test_matriz_de_permissoes.py`), bug hunt (só relatório), revisão de copy + GLOSSARIO, M1
  `app/vision/saude_visual.py`, M2 `app/services/integracao/`, M4 regras do editor, M5 permissões de trabalho.
- Bugs de UI já vistos no crawler (técnico, grade): modal "Prova de escala" não fecha com Esc; `navigator.vibrate`
  sem gesto do usuário gera erro no console (`frontend/src/pwa.ts`); fetch abortado vira `console.error`.

## Próximo passo exato

1. Quando cada agente terminar: revisar o diff, rodar o teste do módulo, integrar no `camera_worker`/`MonitorService`
   (M1 saúde visual, M2 gerente de integração + `/api/integracao/estado`, M4 avaliador do editor, M5 avaliador de permissão),
   registrar blueprints e ligar as telas no `App.tsx`.
2. Corrigir as divergências da matriz de permissões e os bugs confirmados do bug hunt (squad fix, com regressão).
3. Crawler verde para os 4 papéis; E2E de M1 (MJPEG tampada), M2 (OPC UA/MQTT), M3, M4, M5.
4. Portão do PR8 → squash → tag `missao-4-pr8`.

## Rollback

- `pre-missao-4` = HEAD da `main` antes da missão. Ou `git revert` do squash de cada PR.

## Ações negadas pela permissão (não contornadas)

- (nenhuma até agora)

## Herdado da MISSÃO 2 (continua valendo)

- Antes da apresentação: `python scripts/preparar.py` (véspera e manhã: `--so-cache`),
  depois `python run.py --demo` e o roteiro de `DEMO.md`. Plano B: vídeo da Release
  https://github.com/bolla-X/Challenge_5550/releases/tag/next-2026-demo.
- Ameaça nº 1: CPU tomada por outros programas (Docker, Salesforce CLI, Teams).
