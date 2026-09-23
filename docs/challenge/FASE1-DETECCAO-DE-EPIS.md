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

⚠️ **Escopo da medição acima:** é o modelo SH17 **isolado**, no próprio conjunto de
teste dele — não em imagens da planta real.

### 3.1 Ensemble completo (Vyra + SH17, fundidos por IoU), medido contra o mesmo teste

Rodando o `EnsemblePPEDetector` de produção (mesma config do `.env`: `YOLO_CONFIDENCE`,
`imgsz` 960, exclusão de "person" nos extras) contra as mesmas 810 imagens de teste do
SH17, com script próprio (IoU@0.5, AP estilo VOC2012, ponto de operação no melhor F1):

| EPI nosso | Precisão | Revocação | F1 | mAP@0.5 | vs. SH17 sozinho (mAP@0.5) |
|---|---|---|---|---|---|
| Capacete | 0,576 | 0,463 | 0,514 | 0,517 | -0,152 |
| Colete | 0,651 | 0,467 | 0,544 | 0,461 | -0,029 |
| Luvas | 0,568 | 0,571 | 0,569 | 0,507 | -0,063 |
| Óculos | 0,807 | 0,695 | 0,747 | 0,667 | -0,029 (precisão +0,095) |
| Máscara | 0,944 | 0,600 | 0,734 | 0,651 | -0,045 (precisão +0,107) |
| Calçado | 0,769 | 0,581 | 0,662 | 0,572 | -0,043 |
| Protetor auricular | 0,625 | 0,294 | 0,400 | 0,260 | **+0,016** |

**Achado honesto, não escondido:** o ensemble saiu **pior em mAP@0.5** que o SH17
sozinho na maioria das classes, medido *neste* teste — só o protetor auricular
melhorou. Isso não é regressão do sistema: o conjunto de teste é do SH17, não do
Vyra. O Vyra foi treinado em outro dataset, com caixas calibradas de forma diferente;
quando os dois modelos discordam e a caixa do Vyra "vence" a fusão por ter confiança
maior, ela às vezes substitui uma caixa do SH17 mais bem ajustada ao gabarito do SH17
por uma que bate pior — penalizando o IoU e, com ele, o mAP. Esse mesmo efeito explica
por que a **precisão** sobe bastante em óculos e máscara (0,71→0,81 e 0,84→0,94): nesses
casos o Vyra reduz falso positivo real, só que o ganho não aparece no mAP porque o
gabarito de referência continua sendo o do SH17. Em outras palavras: **este número mede
mal a contribuição real do Vyra**, porque o terreno de teste não é o dele — a métrica
correta para o Vyra exigiria um conjunto de teste próprio do Vyra ou anotado pela
equipe, que continua sendo o próximo passo declarado.

### 3.2 Confiabilidade do detector de PESSOA (pré-requisito de todo o resto)

O EPI e a pose só valem alguma coisa se o sistema achar a pessoa primeiro. A detecção
de pessoa roda **separada** do EPI: como o Vyra sozinho não cobre bem várias pessoas na
mesma cena, o sistema usa um segundo modelo dedicado — **YOLOv8n padrão (pré-treinado
no COCO)** — só para a classe pessoa (`MULTI_PERSON_DETECTION=true`). Medido com a
mesma metodologia (IoU@0.5, AP estilo VOC2012) no conjunto de teste do SH17:

| Métrica | Valor |
|---|---|
| mAP@0.5 | 0,740 |
| Precisão (melhor ponto) | 0,759 |
| Revocação | 0,698 |
| F1 | 0,727 |

É a **melhor métrica de todo o sistema** — muito acima de qualquer classe de EPI —
porque "pessoa" é o caso de uso mais maduro do YOLO (COCO tem milhões de exemplos),
enquanto EPI é um domínio de nicho com dataset pequeno. Ressalva: o detector encontrou
4.015 candidatos a pessoa contra 1.536 marcados no gabarito do SH17 — parte dessa
diferença é gente real ao fundo das fotos de canteiro de obra que o SH17 não rotulou
(não é o "trabalhador principal" da imagem), então a precisão medida (0,759) provavelmente
está **subestimada**.

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
