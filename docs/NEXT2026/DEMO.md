# DEMO — roteiro de 5 minutos

Só entra aqui o que passou no E2E (`e2e/test_fluxos.py`), na ordem
**antes → durante → depois**. O teste que sustenta cada momento está indicado.
O SOS por gesto (G3) **não** entra: não há vídeo de licença livre com alguém
erguendo os braços para verificá-lo com vídeo real.

## Antes da banca (uma vez, com internet)

```bash
python scripts/fetch_fixtures.py
```

Baixa as gravações de demonstração para `tests/fixtures/`. Depois disso tudo é
offline.

## Subir

```bash
python run.py --demo
```

- cria `instance/demo/demo.db` do zero, isolado do banco do dia a dia;
- imprime **só no terminal** três contas (`supervisor@`, `tecnico@`,
  `operador@demo.local`) com senha gerada agora — anote antes de projetar;
- câmeras:
  - Canteiro (setor Obra), Pátio (Expedição) e Escada (Manutenção), da
    gravação, com o rótulo **GRAVAÇÃO**;
  - a webcam do notebook vira **Portal** (Portaria), com o rótulo **AO VIVO**;
- sem webcam, o Portal usa a gravação do Canteiro;
- EPIs ligados: capacete, colete e luvas — óculos, máscara, calçado e protetor
  auricular ficam desligados na demo para não encher a tela de alertas;
- tema claro (melhor no projetor); LLM desligado;
- boot até responder: ~70 s nesta máquina (aquecimento dos modelos na iGPU).

Abra `http://127.0.0.1:5000` e entre como **supervisor**.

## Roteiro (5 min)

| min | momento | o que fazer | o que deve aparecer | E2E |
|---|---|---|---|---|
| 0:00 | **Portal de Entrada** (G1) — *antes* | em outra aba: `/portal`; um jurado para diante da webcam | checklist só com Capacete e Colete; cada item confirmado / faltando / "não verificável neste enquadramento"; "Liberado" com tudo confirmado; contador de check-ins sobe | `test_portal_de_entrada_confirma_itens_e_libera` |
| 0:40 | **Tracking e EPI** — *durante* | Câmeras → Pátio | caixas "Pessoa N" (número de rastreio, não identidade); pílula de alerta "Sem capacete — Pessoa N"; rosto desfocado | `test_alerta_surge_para_pessoa_sem_epi`, `test_login_e_video_aparece` |
| 1:20 | **Aproximação e zona** (F3) | no Pátio, olhar a faixa da direita | pílula amarela "Aproximação · Pessoa N · ~X s (projeção cinemática)" antes de entrar; depois "Pessoa em área de risco" | `test_pill_de_aproximacao_aparece` |
| 1:50 | **Planta baixa** (G5) | aba Planta (já calibrada) | pontos de cada pessoa na planta, zona vermelha, calor | `test_planta_baixa_calibra_com_8_cliques_e_mostra_pes` |
| 2:20 | **Replay com privacidade** (F1/F4) | aba Alertas → abrir o grupo de uma pessoa → Ver replay | clipe de ~8 s com a caixa e o rosto desfocado; a privacidade só o supervisor desliga | `test_replay_do_incidente_abre_e_toca`, `test_privacidade_so_o_supervisor_altera` |
| 2:50 | **Diagnóstico** (F5) — *depois* | aba Diagnóstico | "OPENVINO em GPU" nos três modelos; FPS e idade da análise medidos | `test_diagnostico_mostra_o_runtime_ativo` |
| 3:20 | **Prova de escala** (F10) | grade → Prova de escala → 4 → Iniciar | tabela com vídeo e análise por câmera virtual, números desta máquina; "Encerrar e remover" | `test_prova_de_escala_sobe_cameras_virtuais_e_remove` |
| 3:50 | **Você vs. a IA** (G2) | `/desafio`, um jurado joga 1 rodada | depois do tempo: gabarito, acertos/erros da pessoa e da IA com a mesma regra | `test_voce_vs_ia_mostra_placar_honesto` |
| 4:30 | **Modo TV** (G8) | `/tv` (ou Visão geral) | um bloco por setor: conformidade agora, minutos seguidos com 100 %, metas, check-ins do portal | `test_modo_tv_mostra_setores_e_metas_do_supervisor` |

Se sobrar tempo: Relatório do turno (com a NR-6) e `/rotular`.

## Reset entre apresentações (< 10 s)

Em outro terminal, na pasta do projeto:

```bash
flask --app wsgi demo reset
```

Medido nesta máquina: 7,7–9,7 s o comando inteiro, dos quais 0,6–2,6 s no
servidor. O comando:

- limpa alertas, eventos, clipes e a fila de rótulos;
- recria os workers (zera histerese, Andon, portal e sinais);
- religa as câmeras.

As contas continuam as mesmas. Sem servidor no ar, o comando limpa direto o
banco da demo.

## Números ao vivo (≤ 5 min)

```bash
python scripts/bench.py --rapido
```

Perfil atual, 1 e 4 câmeras, 60 s cada. Os números do BENCHMARKS.md vieram de
uma máquina com 13–42 % de CPU de terceiros; este comando mede **na máquina da
banca**.

## Plano B por falha

| falha | o que acontece | o que fazer |
|---|---|---|
| webcam não abre | o Portal usa a gravação do Canteiro (mensagem no terminal) | seguir o roteiro; o Portal mostra itens da gravação |
| câmera para / some | pílula "Reconectando, tentativa N"; volta sozinha | esperar ~10 s ou "Iniciar câmera" na tela dela |
| tela travada / estranha | — | `flask --app wsgi demo reset` (< 10 s) e recarregar a página |
| sem internet | nada muda: a demo é offline | — |
| porta 5000 ocupada | `run.py` não sobe | `PORT=5050 python run.py --demo` (e `PORT=5050` também no reset) |
| "o banco da demo está em uso" | outra demo já está rodando | fechar a outra (Ctrl+C) |
| GPU Intel indisponível | runtime cai para ONNX/CPU (aparece no Diagnóstico) | seguir; a análise fica mais lenta, o vídeo não |
| queda não aparece na Escada | a queda da gravação dura ~1 s; o alerta exige 2 análises seguidas | não está no roteiro; se perguntarem, mostrar o E2E `test_queda_do_modelo_chega_ao_navegador_com_id` |
