# Artefatos Scrum do VisionEPI

Índice dos artefatos do projeto. Board no Trello (público): https://trello.com/b/zVZW2n1p/visionepi-challenge-3ecr, com as listas
Product Backlog, Sprint 1, Sprint 2, Sprint 3, Sprint 4, Concluído e Reviews/Atas.

| Artefato | Arquivo |
|---|---|
| Product Backlog priorizado | [product-backlog.md](product-backlog.md) |
| Sprint 1: detecção de EPIs | [sprint-1.md](sprint-1.md) |
| Sprint 2: pose estimation | [sprint-2.md](sprint-2.md) |
| Sprint 3: notificação inteligente e multicâmera | [sprint-3.md](sprint-3.md) |
| Sprint 4: do relatório de IA ao produto, até a entrega de 23/10 | [sprint-4.md](sprint-4.md) |
| Definition of Done praticado | [definition-of-done.md](definition-of-done.md) |
| Ata da Review Final da Sprint 4 | [ata-review-final-sprint4.md](ata-review-final-sprint4.md) |

Requisitos e matriz de rastreabilidade: [../requisitos.md](../requisitos.md). Arquitetura: [../arquitetura.md](../arquitetura.md).

## Calendário das sprints

A disciplina adotou as sprints do Challenge (decisão registrada em `docs/specs/ESTADO-es-sprint4.md`, item 6). As datas de entrega vêm de
`docs/challenge/CONSOLIDADO.md`; o início de cada sprint é o dia seguinte à entrega anterior.

| Sprint | Período | Entrega | Tema | Documento de fase |
|---|---|---|---|---|
| 1 | 16/04 a 04/05/2026 | 04/05 | Detecção de EPIs | `docs/challenge/FASE1-DETECCAO-DE-EPIS.md` |
| 2 | 05/05 a 22/06/2026 | 22/06 | Pose estimation | `docs/challenge/FASE2-POSE-ESTIMATION.md` |
| 3 | 23/06 a 24/08/2026 | 24/08 | Notificação inteligente | `docs/challenge/FASE3-NOTIFICACAO-INTELIGENTE.md` |
| 4 | 25/08 a 23/10/2026 | banca do Challenge em 23/09; FIAP NEXT em outubro; esta entrega em 23/10 | Validação industrial e produto | `docs/challenge/FASE4-VALIDACAO-INDUSTRIAL.md` |

O início do projeto foi em 16/04/2026. O primeiro commit da `main` é de 19/07/2026, dentro da Sprint 3.

## Como as marcas aparecem nos artefatos

- **Reconstruído a partir dos documentos de fase (sem commits na main):** Sprints 1 e 2. O repositório só tem commits a partir de 19/07.
  O conteúdo vem dos relatórios de fase e do `CONSOLIDADO.md`.
- **Reconstruído a partir do histórico do git:** o que foi montado a partir de `docs/specs/gitlog-main.txt` (Sprints 3 e 4).
- **Reviews e retrospectivas das Sprints 1 a 3 são reconstruídas.** Não houve registro de reunião, review ou retro nessas sprints. O que está
  escrito vem do que cada documento de fase declara como entregue (`[x]`), pendente (`[~]`), não medido ou "planejado, não implementado".
  **Nenhuma fala, presença ou decisão de reunião foi inventada.** Papéis de Product Owner e Scrum Master não estão registrados em nenhum
  documento e por isso não são atribuídos aqui.
- Autoria de commit: o git guarda *handles* (`bolla-X`, `lukiin-z`, `lucas-baraldi`, `Lucas Zolla Assis`, `laszo`, `Lucas Baraldi`). Eles são
  citados como estão; **não há mapeamento de handle para integrante**.

## Equipe

Quem vale é o que o grupo informou para esta entrega:

| Integrante | RM |
|---|---|
| Pedro Gonçalves | 557936 |
| Lucas Baraldi | 555407 |
| Lucas Zolla | 557952 |
| Vitor Pantarotto | 554961 |

## Divergências registradas (os documentos antigos não foram reescritos)

1. **Nome de integrante.** `docs/challenge/CONSOLIDADO.md` e os relatórios de fase traziam outro sobrenome para o integrante do RM 557936; o
   grupo informou "Pedro Gonçalves". Em 23/10/2026 os documentos antigos foram corrigidos para "Pedro Gonçalves" (registro na ata da review final).
2. **Numeração das sprints de IA.** Os documentos da disciplina de IA chamam de "Sprint 3" (camada LLM) o trabalho com commits de 09/09 e de
   "Sprint 4" o de 28/09 (`docs/SPRINT3.md`, `docs/SPRINT4.md`). Pelas datas desta disciplina (Sprint 3 termina em 24/08), os dois caem na
   **Sprint 4**. Os arquivos mantêm os nomes originais; a [Sprint 4](sprint-4.md) os trata como "relatório de IA, camada LLM" e "relatório de
   IA, peso próprio".
3. **Professor.** O relatório de fase do Challenge cita o professor Fabio Henrique Pimentel; o prompt desta entrega cita o professor Hercules Lima
   Ramos como avaliador da Sprint 4 de Engenharia de Software (`docs/specs/es-sprint4.md`).

## Legenda de cores dos cards (Trello)

Verde: Sprint 1. Amarelo: Sprint 2. Laranja: Sprint 3. Azul: Sprint 4. Roxo: processo e Scrum. O Trello não permitiu nomear as labels pela integração
usada; a legenda é esta. Cada requisito (RF e RNF) tem um card com o título `RFnn — nome curto` ou `RNFnn — nome curto`, igual à coluna "Card Trello"
da matriz de `docs/requisitos.md`.
