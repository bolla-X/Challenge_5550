# ADR 0009: Fallback determinístico do LLM só no modo demonstração

- **Status:** aceito (implementado em 23/10/2026: `app/llm/__init__.py`, `app/services/llm_risk_service.py`, `tests/test_llm_demo_fallback.py`)
- **Data:** 23/10/2026

## Contexto

Sem `GEMINI_API_KEY` a camada LLM desligava (`docs/SPRINT3.md`, "Degradação e segredo"). Numa demo sem chave o avaliador nunca via o caminho
alerta, segunda opinião, painel. O critério F1.3 da spec exige que a demo rode **sem a chave** e sinalize isso na interface, e que **com** a
chave o comportamento seja o real. Um mock que finge analisar a imagem seria desonesto.

## Decisão

- `ProvedorDemonstracao` (`app/llm/__init__.py`): resposta **fixa**, que não olha a imagem e diz isso na própria justificativa
  ("Modo demonstração: resposta fixa, sem GEMINI_API_KEY. A imagem não foi analisada por um LLM."), `confianca` 0,0. Passa pelo mesmo
  `validar()` do schema que a resposta do Gemini.
- Só entra quando `DEMO_MODE` **e** `LLM_DEMO_FALLBACK` estão ligados (`llm_risk_service.fallback_de_demonstracao`, fonte única
  também para a sonda do `/status`), o que só `app/demo_ambiente.py` faz, e quando não há chave. Um `.env` com `LLM_DEMO_FALLBACK=true`
  fora da demo não liga nada (achado S9 da auditoria; teste `test_flag_de_fallback_fora_da_demo_nao_liga_nada`). O ADR 0003 continua
  valendo: a resposta vai para `segunda_opiniao` e nunca cria, resolve ou suprime alerta.
- O payload que sai para o painel e o socket é `AnaliseDeDemonstracao`, com `modo: "demonstracao"` (achado S10). O schema do Gemini
  continua recusando esse campo: o modelo real não consegue se declarar demonstração.
- A interface sinaliza: o painel mostra "Modo demonstração · resposta fixa, sem chave do Gemini" (`frontend/src/components/llm-panel.tsx`,
  `data-testid="llm-modo-demonstracao"`) e `/status` reporta `modo = "demonstracao"` (`app/services/status_do_sistema.py`).
- Com `GEMINI_API_KEY` no terminal, o Gemini real vale **mesmo na demo**. Fora da demo, sem chave, a camada continua **desligada**.
  Os quatro casos têm teste: `tests/test_llm_demo_fallback.py`.

## Consequências

- A tela de demonstração mostra o fluxo completo sem rede, mas o texto da segunda opinião é sempre o mesmo e não prova análise nenhuma.
  Não há medição de acurácia do LLM neste modo, e o relatório não pode usá-lo como evidência de qualidade do modelo de linguagem.
- Mudança de perfil da demo: antes o LLM ficava desligado nela. Agora, **se a máquina tiver `GEMINI_API_KEY` no ambiente do terminal,
  a demo envia ao Gemini o quadro de cada alerta criado** (com o debounce de 15 s por câmera), inclusive da webcam opcional. Sem a
  chave, nada sai da máquina. O código do loop de câmera não mudou; mudou a configuração (achado S11 da auditoria).
- `docs/NEXT2026/DEMO.md` foi atualizado: em `/status` o esperado passou de "desligado" para "Modo demonstração".

## Alternativas

- Resposta que descreve a imagem sem analisá-la: **rejeitada** (finge análise).
- Manter o LLM desligado na demo (estado anterior): **rejeitada**; o avaliador não veria a segunda opinião.
- Resposta aleatória ou variável: **rejeitada**; o fallback é determinístico para ser testável.
