# Sprint 1: detecção de EPIs (16/04 a 04/05/2026)

> **Reconstruído a partir dos documentos de fase (sem commits na main).** O primeiro commit da `main` é de 19/07/2026. Esta sprint não tem commit,
> reunião, review ou retro registrados. O conteúdo vem de `docs/challenge/FASE1-DETECCAO-DE-EPIS.md` (entrega de 04/05/2026) e de
> `docs/challenge/CONSOLIDADO.md`. O PDF da fase está em `docs/pitch/FASE1-DETECCAO-DE-EPIS.pdf`.

## Objetivo da sprint

Detecção em tempo real de, no mínimo, capacete, óculos de proteção, protetor auricular, bota de segurança e colete refletivo, diferenciando
**em uso correto**, **em uso incorreto** e **ausente**. Demo funcional em vídeo ou stream. Métricas por classe: mAP@0,5, precisão, revocação e F1
(FASE1 §1).

## Sprint backlog

| Item | RF | Estado | Fonte |
|---|---|---|---|
| Detectar os 5 EPIs mínimos (o documento diz que são 7: capacete, colete, luvas, óculos, máscara, calçado, protetor auricular) | RF01 | Entregue | FASE1 §2 e §7 |
| Diferenciar correto, incorreto e ausente | RF03 | Entregue segundo a FASE1; ver nota abaixo | FASE1 §2 e §7 |
| Associar cada EPI a uma só pessoa (contenção da caixa e faixa vertical ideal) | RF03 | Entregue | FASE1 §2 |
| Rastrear pessoas com ID estável (IoU, distância entre centros como reserva) | RF02 | Entregue | FASE1 §2 |
| Piso de confiança por classe e filtro geométrico contra falso positivo de fundo | RF01 | Entregue | FASE1 §2 |
| Zona de risco configurável por câmera, desenhada no vídeo; rotação de câmera | RF04 | Entregue | FASE1 §2 |
| Demonstração em vídeo ou stream | RF01 | Entregue (vídeo institucional e demo ao vivo citados) | FASE1 §6 e §7 |
| Métricas por classe | RF01 | Entregue, com ressalva (abaixo) | FASE1 §3 |
| Relatório técnico e declaração de dataset com licenças | n/a | Entregue | FASE1 §7 |

**Nota sobre RF03 e RF16.** O `CONSOLIDADO.md` §2.1 e o relatório da Fase 4 §5 dizem que protetor auricular e "uso incorreto" foram adicionados
na fase final e que a distinção correto/incorreto/ausente estava pendente até a Sprint 4. A FASE1 marca os dois como entregues. O repositório
registra os dois na Sprint 4 (RF16); a divergência está em `docs/requisitos.md`.

## Incremento entregue

Detector de EPI com dois modelos YOLOv8 rodando no mesmo quadro, fundidos por IoU: o **Vyra** (`Hexmon/vyra-yolo-ppe-detection`, CC BY 4.0) e um
modelo **treinado pela equipe** no SH17 (8.099 imagens, 75.994 instâncias, CC BY-NC-SA 4.0, uso acadêmico). Detector de pessoa dedicado (YOLOv8n do COCO),
rastreador por IoU, associação exclusiva EPI e pessoa, zona de risco por câmera.

### Métricas medidas (`model.val()`, imgsz 640, GPU, 810 imagens de teste do SH17, FASE1 §3)

| EPI | Precisão | Revocação | F1 | mAP@0,5 |
|---|---|---|---|---|
| Capacete | 0,810 | 0,512 | 0,628 | 0,669 |
| Colete | 0,810 | 0,433 | 0,564 | 0,490 |
| Luvas | 0,678 | 0,527 | 0,593 | 0,570 |
| Óculos | 0,712 | 0,678 | 0,694 | 0,696 |
| Máscara | 0,837 | 0,588 | 0,691 | 0,696 |
| Calçado | 0,745 | 0,570 | 0,646 | 0,615 |
| Protetor auricular | 0,654 | 0,235 | 0,346 | 0,244 |
| Agregado (17 classes do SH17) | 0,733 | 0,588 | n/d | 0,621 |

- Detector de pessoa: mAP@0,5 **0,740**, precisão 0,759, revocação 0,698, F1 0,727 (FASE1 §3.2). A precisão está provavelmente subestimada (o
  detector achou 4.015 candidatos contra 1.536 marcados no gabarito).
- Velocidade: cerca de **19,5 quadros por segundo** com o pipeline completo, uma câmera, GPU RTX (FASE1 §3.2).
- Ensemble completo contra o mesmo teste: **pior em mAP@0,5** que o SH17 sozinho na maioria das classes (capacete 0,517 contra 0,669), com precisão
  maior em óculos (0,71 para 0,81) e máscara (0,84 para 0,94). O documento atribui isso ao gabarito ser do SH17 e não do Vyra (FASE1 §3.1).

## Review (reconstruída)

**Entregue, segundo o relatório de fase:** todos os itens do backlog marcados `[x]` (FASE1 §7).

**Limitações que o próprio relatório declara:**
- **Nenhuma classe atinge a meta sugerida de mAP@0,5 de 0,75.** "Gap real, não escondido."
- O protetor auricular é o item mais fraco: 17 instâncias no teste, revocação de 0,235.
- As métricas são contra o conjunto de teste do SH17, **não** contra imagens da planta real e não no terreno nativo do Vyra.
- O ensemble não é demonstrado melhor que o SH17 isolado neste teste.

**Feedback externo.** O `CONSOLIDADO.md` registra, sem data, o retorno da SPI: "Boa evolução do projeto, boa qualidade de detecção". O texto diz que foi
incorporado "nas fases seguintes"; não atribuo o retorno a uma sprint específica.

## Retrospectiva (reconstruída)

Não houve retro registrada. O que o relatório da fase registra como aprendizado, no próprio texto:

- **Funcionou:** associação geométrica exclusiva resolveu duas pessoas sobrepostas disputando o mesmo capacete; piso de confiança por classe e troca
  de modelo corrigiram a luva confundida com mão nua (FASE1 §4).
- **Não funcionou, ou não está provado:** o ensemble não superou o SH17 no gabarito do SH17; a leitura dos autores é que o gabarito mede mal o Vyra.
- **Próximos passos que o `CONSOLIDADO.md` §11 declara:** anotar um conjunto de teste próprio (ou usar o nativo do Vyra) para medir o Vyra no ensemble;
  construir um dataset próprio anotado, da planta ou de voluntários.

## Evidências no repositório

`docs/challenge/FASE1-DETECCAO-DE-EPIS.md`, `docs/pitch/FASE1-DETECCAO-DE-EPIS.pdf`, `docs/challenge/CONSOLIDADO.md`. O código que descreve essa fase
continua em `app/vision/` (ver a matriz de [../requisitos.md](../requisitos.md)).
