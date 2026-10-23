# Sprint 2: pose estimation (05/05 a 22/06/2026)

> **Reconstruído a partir dos documentos de fase (sem commits na main).** Não há commit, reunião, review ou retro registrados para esta sprint.
> O conteúdo vem de `docs/challenge/FASE2-POSE-ESTIMATION.md` (entrega de 22/06/2026) e de `docs/challenge/CONSOLIDADO.md`. O PDF da fase está em
> `docs/pitch/FASE2-POSE-ESTIMATION.pdf`.

## Objetivo da sprint

Pose estimation funcional integrada ao pipeline da Fase 1; classificação de pelo menos três categorias de postura (ergonomicamente inadequada, risco
imediato e aproximação de zona crítica); demo em vídeo; métricas PCK, acurácia de classificação e recall em postura de risco (FASE2 §1).

## Sprint backlog

| Item | RF | Estado | Fonte |
|---|---|---|---|
| Pose por pessoa (MediaPipe Pose) no mesmo quadro e no mesmo `CameraWorker` | RF05 | Entregue | FASE2 §2 e §4 |
| Risco imediato: queda por orientação do torso, medida em pixels | RF05 | Entregue | FASE2 §2 |
| Postura inadequada: cabeça à frente do eixo dos ombros, em fração do torso | RF05 | Entregue | FASE2 §2 |
| Aproximação de zona crítica: centro da caixa dentro do polígono | RF06 | Entregue | FASE2 §2 |
| Alerta de queda atribuído a uma pessoa ("Pessoa 3"), não a um evento global | RF05 | Entregue | FASE2 §2 |
| Demo funcional em vídeo | RF05 | Entregue | FASE2 §6 |
| Integração com a Fase 1 (mesmo stream) | RF05 | Entregue | FASE2 §4 |
| Métricas: PCK, acurácia, recall | n/a | **Parcial `[~]`**: PCK não medido | FASE2 §3 e §6 |
| Relatório técnico | n/a | Entregue | FASE2 §6 |

## Incremento entregue

| Categoria | Como é detectada | Severidade |
|---|---|---|
| Risco imediato (queda) | orientação do torso (ombro para quadril) mais horizontal que vertical, em pixels do quadro | Crítica |
| Ergonomicamente inadequada | cabeça projetada à frente do eixo dos ombros, em fração da altura do torso da própria pessoa | Média |
| Aproximação de zona crítica | centro da caixa da pessoa dentro do polígono de risco, por câmera | Alta |

Decisão registrada: geometria em pixels e em fração do torso da própria pessoa, não em coordenadas normalizadas, para o mesmo limiar não significar
coisas diferentes em pessoa perto ou longe da câmera (FASE2 §5).

### Métricas

- **PCK: não medido.** Exigiria imagens com articulações marcadas à mão, que o projeto não tem; o MediaPipe é de terceiros e a acurácia publicada
  pelo fabricante é a referência (FASE2 §3).
- **19 testes automatizados** da lógica de classificação, com geometria de referência conhecida (em pé, caído, inclinado, dentro e fora da zona, duas
  pessoas na cena): **100 % de acerto nos casos controlados**. O documento ressalva que isso comprova a lógica, não o recall em cenas reais.

### Nota de cronologia

O documento da Fase 2 tem data de entrega de 22/06/2026, mas descreve também um **teste ao vivo de 23/09/2026** ("véspera da banca"), com queda,
postura e zona disparando em cena real com evidência de imagem, e o ID da pessoa trocado no meio da queda. O texto foi, portanto, atualizado depois
da entrega. Esse teste é evidência da **Sprint 4** e não é contado como incremento da Sprint 2.

## Review (reconstruída)

**Entregue, segundo o relatório de fase:** cinco dos seis itens marcados `[x]`; o sexto, métricas, está `[~]` (FASE2 §6).

**Limitações declaradas:**
- PCK não medido; um recall numérico exige vídeo gravado e rotulado, roteiro cronometrado e árbitro externo.
- A lógica foi verificada em casos controlados; recall em cenas reais não foi medido.

## Retrospectiva (reconstruída)

Não houve retro registrada. O que o relatório da fase registra:

- **Corrigido nesta fase:** a limitação da versão anterior, de uma pose global por quadro e alerta de queda sem dono, virou pose por pessoa com ID do rastreador.
- **Não resolvido, e dito:** o rastreador por IoU perde continuidade quando a caixa muda muito, como numa queda; o documento descreve o mesmo indivíduo
  gerando alertas em nome de "Pessoa 2", "Pessoa 5" e "Pessoa 9" em poucos segundos (limitação do rastreamento, não da classificação).
- **Próximos passos declarados (`CONSOLIDADO.md` §11):** teste formal de recall de pose; rastreador mais robusto a mudança brusca de caixa.

## Evidências no repositório

`docs/challenge/FASE2-POSE-ESTIMATION.md`, `docs/pitch/FASE2-POSE-ESTIMATION.pdf`; testes atuais da lógica: `tests/test_pose_por_pessoa.py`,
`tests/test_pose_estimator_crop.py`, `tests/test_quedas.py` (o número "19 testes" vem do relatório e não foi reconferido aqui).
