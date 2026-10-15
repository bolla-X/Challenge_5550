# ESTADO — MISSÃO 2 (encerrada)

**A branch da apresentação é a `main`.** Ela recebeu, pelo PR7, o VisionEPI do
NEXT 2026 (`feat/completo-com-rebrand`, PRs #10–#15) integrado com a Sprint 4
de IA que só existia na `main`. Retomar lendo este arquivo e `MISSAO-2.md`
(ADENDOS 2 e 3 no fim); o detalhe de tudo está em `CHANGELOG.md`.

## Antes da apresentação (na máquina dela)

```bash
python scripts/preparar.py
```

e, na véspera e na manhã, `python scripts/preparar.py --so-cache`. Depois
`python run.py --demo` e o roteiro de `DEMO.md`. Plano B: o vídeo da Release
https://github.com/bolla-X/Challenge_5550/releases/tag/next-2026-demo (baixar antes).

## Rollback

- `main-pre-release` = HEAD da `main` antes do release (`6c3ed61`).
- `pre-missao-2` = HEAD de `feat/completo-com-rebrand` antes da missão (`906c81e`).
- Ou `git revert` do squash do PR7.

## Números que valem (14/10, máquina i7-1355U com iGPU Intel)

- Portal até "Liberado" com `portal.mp4` e 4 câmeras (10×): **no palco p50 3,5 s
  / p95 5,9 s**; fora do palco p50 13,4 s / p95 24,2 s.
- Subida até a 1ª análise: a frio mediana 67,8 s; com cache aquecido 53,2 s.
- Queda ao vivo no palco (0,25×, outras câmeras pausadas): 19–22 s desde
  entrar na cena (E2E isolado 2/2).

## Decisões em vigor

- Peso de EPI padrão: **Vyra** (`models/vyra_ppe.pt`, OpenVINO na iGPU). O peso
  da Sprint 4 (`models/visionepi_cppe_n416.pt`) é opção documentada no README.
- `PPE_MISSING_POLICY=ausencia` (padrão; = comportamento medido).
- Palco: Portal, "Tente enganar a IA" e Queda pausam as outras câmeras.
- Portal: 3 análises seguidas com tudo confirmado; EPI faltando zera.
- Foco fora do palco: ≥ 50 % das vagas do agendador.

## Ameaças conhecidas

1. **CPU da máquina tomada por outros programas.** Com 80–100 % de CPU de
   terceiros, a câmera em foco chegou a 3 inferências em 73 s e o pré-alerta de
   aproximação não saiu (E2E). Na apresentação: fechar tudo que não for a demo
   (Docker, Salesforce CLI, Teams, navegadores extras).
2. Portal fora do palco é lento (p95 24 s): o peso vê o capacete em ~64 % dos
   quadros; mostrar o Portal pelo palco.
3. Subida leva ~1 min mesmo com cache: subir a demo antes e deixar no ar.

## Ações negadas pela permissão (não contornadas)

- 14/10: lançar o portão com `nohup bash -c ... &` foi negado; o portão seguiu
  pelo modo em segundo plano da ferramenta.

## Worktrees e pastas de apoio (fora do repositório)

- `../ch5550-release-ensaio`: worktree do `release-main` (integração).
- `../ch5550-clone-1`, `-2`, `-3`: testes de clone limpo (README à risca).
- `../ch5550-antes`: medições "antes" da missão.
