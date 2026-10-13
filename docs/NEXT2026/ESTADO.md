# ESTADO — missão NEXT 2026

Retomar lendo só este arquivo e `MISSAO.md`. Reescrito a cada marco.

## Marco atual: PASSO 0 concluído → FASE 1 em andamento

| Item | Situação | Evidência |
|---|---|---|
| MISSAO.md salvo | feito | `docs/NEXT2026/MISSAO.md` |
| Backup remoto | feito | `git push -u origin next-2026 next-2026-pr2-wip wip-preservado-2026-10-12` → 3 `[new branch]` (13/10/2026) |
| Carga de fundo registrada | feito | tabela abaixo |

## Branches

- Base dos PRs: `origin/feat/completo-com-rebrand` (`e3a8af7`). Tag de rollback: `pre-next-2026`.
- `next-2026` (`6385e0f` + commits desta sessão): candidato ao PR1.
- `next-2026-pr2-wip` (`b344f5e`): F1/F3/F4/F5/F7/F9/F10, ainda não compilado.

## Carga de fundo da máquina (13/10/2026 ~05:50, amostra de 5 s)

Máquina: Intel i7-1355U (2 P-cores + 8 E-cores, 12 lógicos), 15,7 GB RAM (1,8 GB livres), sem GPU.

| Processo de terceiros | CPU (% de 1 núcleo) | O que é |
|---|---|---|
| ffmpeg (PID 8840) | 470 % | encode `libx264 -preset veryslow` de outro projeto (`fe-diaria`) |
| python 3.14 (PID 30404) | 93 % | teste de outro projeto (`plantio-arvore`) |
| node (PID 2788) | 54 % | `sf data delete bulk` de outro projeto (`agentes-rachel`) |
| msedge (vários) | ~150 % somados | navegador do usuário |
| claude (vários) | ~50 % somados | apps Claude |

Nenhum foi encerrado (não são desta missão). Toda medição de desempenho desta
sessão registra `carga_de_fundo_pct` e compara candidatos **intercalados**.

## Achados ao verificar o estado herdado

1. O "640 fica em 72 %" herdado é um rótulo trocado: 72,03 % é o total de
   **pytorch:512** em `bench/results/concordancia-epi-20261013-005918.json`.
   (Re-execução do guarda pendente para fechar o registro.)
2. `openvino-dyn:640` deu exatamente o mesmo 95,04 % do ONNX estático — indício
   de que o export "dinâmico" saiu estático (passo 4 da Fase 1).
3. `.env.example` e `CONFIG_BASE` do `scripts/bench.py` ainda usam
   `YOLO_IMGSZ=416`, contradizendo a decisão registrada (640). A corrigir no PR1.
4. Rodadas `batata` de `20261013-010705-pr1.json` têm CPU do servidor 500–680 %
   (afinidade não aplicada; corrigido depois em `d5ecd86`) → inválidas.
   `20261013-020530-gate1.json` (não commitado) tem batata a 172–195 % → válido.

## Próximo passo exato

Fase 1, itens 2–3: instrumentar `idade_analise`, `fps_analise` e latência de
alerta no worker e no `scripts/bench.py`; re-rodar o guarda de 640.
