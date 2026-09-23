# VisionEPI — Relatório Técnico: Fase 1 — Detecção de EPIs / EPCs

**Challenge 2026 — Innovation Challenge CUP — Parceria FIAP × SPI**
Engenharia da Computação, 3º ano. Entrega: 04/05/2026.

## Equipe

Lucas Baraldi Rodrigues · Lucas Zolla Assis · Pedro Costa Belisário · Vitor Pantarotto de Brito
Professor: Fabio Henrique Pimentel · Mentores SPI: Fernando Marcolina, Wendel de Almeida Passos

---

## 1. Escopo desta fase

Detecção em tempo real de, no mínimo, capacete, óculos de proteção, protetor auricular,
bota de segurança e colete refletivo, diferenciando **em uso correto**, **em uso
incorreto** e **ausente**. Demo funcional em vídeo/stream. Métricas por classe:
mAP@0.5, precisão, revocação e F1.

## 2. O que foi construído

- **Ensemble de dois modelos YOLOv8**, rodando no mesmo quadro: o **Vyra**
  (`Hexmon/vyra-yolo-ppe-detection`, pesos prontos, CC BY 4.0) e um modelo **treinado
  pela própria equipe** no dataset **SH17** (8.099 imagens, 75.994 instâncias, CC
  BY-NC-SA 4.0 — uso acadêmico), fundidos por IoU (mesmo rótulo + caixa sobreposta =
  mesma detecção, fica a de maior confiança).
- **7 classes de EPI**: capacete, colete, luvas, óculos, máscara, calçado de segurança e
  **protetor auricular** — cobrindo os 5 itens mínimos do escopo.
- **Três estados por item** (não dois): "ok", "incorreto" e "ausente". Implementado por
  geometria: cada EPI tem uma faixa vertical esperada dentro da caixa da pessoa (ex.:
  capacete no topo, calçado na base). Dentro da faixa = ok. Fora da faixa mas ainda
  sobre o corpo da pessoa (contenção real da caixa) = uso incorreto (ex.: capacete na
  mão, não na cabeça). Fora do corpo da pessoa = ausente. Um item incorreto nunca
  rebaixa quem já está "ok" com outro exemplar do mesmo tipo.
- **Associação geométrica exclusiva EPI↔pessoa**: pontuação por contenção da caixa +
  proximidade da faixa ideal, resolvendo duas pessoas sobrepostas disputando o mesmo
  capacete (o de maior pontuação leva; cada EPI serve no máximo uma pessoa).
- **Rastreador de pessoas** (IoU + distância entre centros como plano B): mantém o
  mesmo número de identificação mesmo quando a pessoa muda de postura ou é
  parcialmente ocluída.
- **Piso de confiança por classe** e **filtro geométrico** (EPI só conta se cair dentro
  de alguma pessoa detectada) — reduz falso positivo de objeto de fundo.
- **Zona de risco configurável por câmera**, desenhada no próprio vídeo.
- **Rotação de câmera**, para câmeras montadas de lado ou invertidas.

## 3. Métricas (mAP@0.5, precisão, revocação, F1 por classe)

Validação real (`model.val()`, Ultralytics, GPU, imgsz 640) do modelo SH17 no **conjunto
de teste** (810 imagens, nunca usadas em treino nem validação):

| EPI nosso | Classe SH17 | Precisão | Revocação | F1 | mAP@0.5 | mAP@0.5:0.95 |
|---|---|---|---|---|---|---|
| Capacete | helmet | 0,810 | 0,512 | 0,628 | 0,669 | 0,441 |
| Colete | safety-vest | 0,810 | 0,433 | 0,564 | 0,490 | 0,323 |
| Luvas | gloves | 0,678 | 0,527 | 0,593 | 0,570 | 0,351 |
| Óculos | glasses | 0,712 | 0,678 | 0,694 | 0,696 | 0,411 |
| Máscara | face-mask | 0,837 | 0,588 | 0,691 | 0,696 | 0,472 |
| Calçado | shoes | 0,745 | 0,570 | 0,646 | 0,615 | 0,332 |
| Protetor auricular | ear-acessorio | 0,654 | 0,235 | 0,346 | 0,244 | 0,151 |
| **Agregado (17 classes do SH17)** | — | 0,733 | 0,588 | — | 0,621 | 0,414 |

**Leitura honesta:** o **protetor auricular** é o item mais fraco — só 17 instâncias no
conjunto de teste, a classe mais rara do dataset, revocação de 0,235. Óculos e máscara
têm o melhor desempenho. Nenhuma classe atinge a meta sugerida de mAP@0.5 ≥ 0,75 —
gap real, não escondido.

⚠️ **Escopo da medição:** é o modelo SH17 **isolado**, no próprio conjunto de teste
dele — não o ensemble completo (Vyra + SH17 + gate de confiança) que roda em produção,
e não em imagens da planta real. Medir o ensemble num conjunto próprio anotado é o
próximo passo declarado.

- **FPS:** ~19,5 quadros/segundo com o pipeline completo, uma câmera, GPU (RTX). Cai
  com múltiplas câmeras simultâneas (ver relatório da Fase 4).

## 4. Matriz de confusão e análise de erros

A matriz de confusão do treino do SH17 (`F:\treino_sh17\runs\sh17_v1\weights\`) mostra
maior confusão entre classes anatômicas próximas (ex.: "ear" vs. "ear-acessorio", "face"
vs. "face-acessorio") — esperado, já que a diferença visual entre a parte do corpo nua e
o acessório que a protege é sutil em imagens de baixa resolução ou ângulo desfavorável.
Falso positivo mais notado em produção: o modelo nano anterior (substituído nesta fase)
confundia mão nua com luva; corrigido trocando de modelo e ligando o piso de confiança
por classe.

## 5. Inovações desta fase

- Ensemble de dois modelos (não um só), para cobrir classes que o principal detecta mal.
- Distinção correto/incorreto/ausente, não binária.
- Regra situacional: EPI exigido varia por câmera (ver Fase 3, modo portaria).
- Rotação de câmera e zona de risco configuráveis, sem exigir reinício do sistema.

## 6. Demonstração

Vídeo institucional (`docs/pitch/VisionEPI-institucional-90s.mp4`) e demonstração ao
vivo mostram a detecção rodando contra webcam e contra câmeras reais da planta parceira
(RTSP), com pessoas reais em tempo real.

## 7. Entregáveis desta fase

- [x] 5 EPIs mínimos detectados (na verdade, 7)
- [x] Diferenciação correto/incorreto/ausente
- [x] Demo funcional em vídeo/stream
- [x] Métricas reportadas por classe (mAP@0.5, precisão, revocação, F1)
- [x] Relatório técnico (este documento)
- [x] Declaração de dataset com licenças — ver §9 do `CONSOLIDADO.md`
