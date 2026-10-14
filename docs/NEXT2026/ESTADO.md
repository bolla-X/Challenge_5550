# ESTADO — MISSÃO 2

Retomar lendo só este arquivo e `MISSAO-2.md`. Reescrito a cada marco.
(A missão anterior, PRs #10–#13, está em `MISSAO.md` e no CHANGELOG.)

## Rollback

- `pre-missao-2` = HEAD de `feat/completo-com-rebrand` antes da missão (`906c81e`).
- `main-pre-release` = HEAD de `main` antes do release (`6c3ed61`).

## Marco atual: FASE A (PR5) — consertos que afetam a demo

| item | situação | evidência |
|---|---|---|
| P0.1 rodízio ponderado | código + 8 testes unitários; pausas removidas dos E2E | `tests/test_agendador_ponderado.py`; E2E pendente |
| P0.2 incidentes + re-associação | código + 10 + 8 testes; medição antes/depois rodando | `tests/test_incidentes.py`, `tests/test_reassociacao.py`, `scripts/contar_incidentes.py` |
| P0.3 `.env.example` | 640 + teste; permissão estreitada | `tests/test_onboarding.py::test_env_example_infere_a_640` |

## Decisões em vigor

- Foco = câmera com `video_feed` aberto (foco, portal, quiosque, palco) ou consulta recente do portal (lease 3 s).
- Agendador: *smooth weighted round-robin*; foco soma peso = nº das outras (≥ 50 %); guarda de 2,5 s.
- Incidente = (câmera, regra, zona); zona = nome da área de risco se a pessoa está dentro, "Fora da zona" se não, "Toda a câmera" sem zona.
- Re-associação: 1,5 × largura da caixa, 2 s (config `REASSOCIAR_*`).

## Como verificar

- Unitários: `.venv\Scripts\python.exe -m pytest tests -q`.
- E2E: `.venv\Scripts\python.exe -m pytest e2e -q` (4 câmeras, sem pausas).
- Incidentes: `python scripts/contar_incidentes.py --fixture multidao --rotulo depois` (e `--raiz ../ch5550-antes --rotulo antes`).

## Próximo passo exato

Concluir a medição de incidentes, ligar todos os EPIs na demo, rodar o E2E com 4 câmeras; depois X1 (gêmeo 3D).
