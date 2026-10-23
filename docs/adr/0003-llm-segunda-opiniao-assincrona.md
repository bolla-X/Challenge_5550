# ADR 0003: LLM como segunda opinião assíncrona que nunca cria alerta

- **Status:** aceito (vigente)
- **Data:** 09/09/2026 (esquema e provedor `9b2f995`, disparo assíncrono `0950df0`, ligação no boot `fd97d46`)

## Contexto

Na cena "segura" da Sprint 3, o YOLO acusou `missing_helmet` crítico para dois trabalhadores de capacete branco. O LLM (Gemini) corrigiu os
dois falsos positivos (`docs/SPRINT3.md`). Mas a latência real foi de **16 a 38 s** por chamada (mediana das 6 chamadas cerca de 27,4 s),
e a API recusa prazo abaixo de 10 s (HTTP 400). Uma chamada dessas dentro do laço de captura congelaria o vídeo por meio minuto.
Além disso, resposta de LLM pode vir truncada, com campo inventado ou em prosa.

## Decisão

- `app/llm/` recebe bytes de imagem e devolve `AnaliseRisco` validada por schema, ou `None`; não conhece Flask, banco nem socket. O
  provedor fica atrás da interface `ProvedorMultimodal` (Gemini real, dublê de teste e, desde esta entrega, o provedor de demonstração).
- `app/services/llm_risk_service.py` decide quando gastar uma chamada: disparo no alerta **criado** (e, desde 28/09, quando capacete ou
  colete ficam "não verificado" por 3 detecções), **uma chamada em voo por câmera**, debounce de 15 s e **descarte em vez de fila**.
  Reaproveita o JPEG que o laço já codificou (um `imencode` por quadro).
- O resultado vai para o campo `segunda_opiniao` e para o evento de socket `llm_segunda_opiniao`. **O LLM não cria, não resolve e não
  suprime alerta.** Um teste manda uma análise que discorda de tudo e exige o conjunto de alertas idêntico.
- Sem `GEMINI_API_KEY` o serviço nasce desligado (`LLM_ENABLED=false` por padrão; `TestConfig` força `False`). Modelo com versão fixa
  (`gemini-3.6-flash`): o `gemini-2.0-flash` anterior foi aposentado (a API responde 404) e um alias "latest" mudaria o significado dos goldens.

## Consequências

- Custo em FPS dentro do ruído: 19,53 para 19,45 (-0,4 %) no bench com latência simulada; no `CameraWorker._loop`, +2,3 %, -1,7 % e -2,2 %
  em três execuções. `submeter()` custa 9 a 13 microssegundos. Na janela medida, 79 eventos submetidos: 1 aceito, 78 descartados.
- Três cenas **não sustentam afirmação de acurácia**; a medição no conjunto anotado (`scripts/avaliar_llm_dataset.py`) está pronta e
  **não foi rodada** por falta de acesso à API no ambiente da Sprint 4 (`docs/SPRINT4.md` §7).
- A resposta do LLM depende de rede, cota e disponibilidade (9 tentativas falharam antes de fechar os 6 goldens: 503 e estouros de leitura).

## Alternativas

- Chamada síncrona no laço: **rejeitada** (congela o vídeo).
- Fila de chamadas: **rejeitada**; 26 alertas de 7 s de vídeo gerariam 26 chamadas atrasadas descrevendo uma cena que já passou.
- LLM como árbitro que suprime ou cria alerta: **rejeitada**; um modelo de linguagem que apaga alerta de EPI é risco de segurança do trabalho.
- Alias `gemini-flash-latest`: **rejeitada** (golden precisa significar a mesma coisa daqui a um mês).
