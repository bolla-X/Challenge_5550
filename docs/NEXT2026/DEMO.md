# DEMO: roteiro da final

Só entra aqui o que passou no E2E (`e2e/test_fluxos.py`, `e2e/test_missao2.py`),
com as **4 câmeras ligadas** e sem pausa de contorno. O teste que sustenta cada
momento está indicado.

**Última verificação: 15/10, `main` @ `d76941b`, sob carga** (27 % de CPU de
terceiros): E2E **36/36** com as 4 câmeras numa rodada só; clone limpo pelo
README com a fumaça **6/6 no OpenVINO e 6/6 no ONNX**. Detalhe em `ESTADO.md`.

## Antes da banca (uma vez, com internet)

```bash
python scripts/preparar.py
```

Baixa pesos e gravações, aprova os runtimes rápidos e **aquece o cache do
OpenVINO** (`runtime/ov_cache/`, fora do git). Depois disso tudo é offline.
**Na véspera e na manhã da apresentação**, na máquina da apresentação, rode de
novo só o aquecimento (~1 min):

```bash
python scripts/preparar.py --so-cache
```

Ele compila os três modelos na iGPU nas formas das câmeras da demo e o
OpenVINO guarda o compilado (doc:
https://docs.openvino.ai/2025/openvino-workflow/running-inference/optimize-inference/optimizing-latency/model-caching-overview.html).
Trocou de máquina, de driver da GPU ou de versão do OpenVINO: rode de novo.

## Subir

```bash
python run.py --demo --https
```

- `--https` é o que deixa o **celular** alcançar o notebook (controle do palco
  e celular como câmera). Aceite o aviso do certificado autoassinado uma vez,
  no notebook e no celular. Sem `--https` tudo funciona no notebook; só o
  celular fica de fora (o teclado continua mandando no palco);
- cria `instance/demo/demo.db` do zero, isolado do banco do dia a dia;
- imprime **só no terminal** três contas (`supervisor@`, `tecnico@`,
  `operador@demo.local`) com senha gerada agora — anote antes de projetar;
- câmeras: Canteiro (Obra), Pátio (Expedição) e Escada (Manutenção), das
  gravações, rotuladas **GRAVAÇÃO**, calibradas na mesma planta (gêmeo 3D); a
  webcam vira **Portal** (Portaria), **AO VIVO**; sem webcam, o Portal toca a
  gravação `portal.mp4` (um trabalhador de capacete e colete, de perto);
- **todos os EPIs exigidos** ligados (o painel agrupa em incidentes);
- quatro missões de turno da equipe (Liga de Setores);
- tema claro (projetor); LLM desligado.
- **Tempo de subida** até a primeira análise publicada (`scripts/medir_partida.py`,
  3 rodadas cada, 14/10): **com o cache aquecido, mediana 53 s** (50–67 s);
  **a frio** (pasta de cache nova e vazia), **mediana 68 s** (58–76 s). O caso de
  ~4 min do ADENDO 2 foi logo depois de reiniciar o PC (caches do sistema e do
  driver frios) e não se repetiu com pasta de cache nova. Mesmo assim: rode
  `scripts/preparar.py --so-cache`, suba a demo **antes** da banca e deixe no ar.

Abra `https://127.0.0.1:5000`, entre como **supervisor** e vá para
`/palco` (atalho na Visão geral: "Apresentação").

## O palco

- **Espaço** ou **→** avança, **←** volta; **Q** mostra/esconde o QR.
- O QR (canto inferior direito) abre `/palco/controle` no celular: botões
  grandes de anterior/próxima e o nome da cena. O link vale só para mudar a cena.
- **X** liga/desliga o Raio-X em qualquer vídeo.
- Cada cena prepara o próprio estado: a câmera certa em foco, o Raio-X quando
  pede, e a gravação da queda recomeça (de 4 s) a **0,25×** ao entrar na cena,
  com "GRAVAÇÃO · 0,25×" sobre o vídeo; ao sair, volta a 1×.
- Nas cenas **Portal**, **Tente enganar a IA** e **Queda**, só a câmera da cena analisa:
  as outras ficam **"Pausada pela apresentação"** (o rodapé do palco diz quais)
  e voltam ao sair da cena. Fechar o palco no meio devolve as câmeras em ~8 s.
  Tempo até "Liberado" na cena, com `portal.mp4` e as 4 câmeras ligadas (10
  repetições, E2E): **p50 3,5 s, p95 5,9 s**. Fora do palco (`/portal`, as 4
  analisando): p50 13,4 s, p95 24,2 s — por isso o Portal se mostra pelo palco.

## Roteiro (≈ 7 min)

| cena | o que fazer | o que aparece | E2E |
|---|---|---|---|
| 1 VisionEPI | abrir | câmeras no ar, pessoas na planta e incidentes ativos **agora**, nesta máquina | `test_palco_pelo_teclado_e_pelo_celular` |
| 2 Portal de Entrada | um jurado diante da webcam (sem webcam: a gravação `portal.mp4`); as outras câmeras pausam | só os EPIs exigidos; confirmado / faltando / "não verificável neste enquadramento"; "Liberado" com tudo confirmado (p50 3,5 s na cena); check-in conta para a Liga | `test_portal_no_palco_pausa_as_outras_e_libera` |
| 3 Tente enganar a IA | escolher "Boné no lugar do capacete", **Valendo!** | o que o modelo viu e por quê ("o modelo viu com 0,31 (abaixo do piso 0,40) e descartou"); placar da sessão, inclusive quando a IA é enganada | `test_tente_enganar_a_ia_mostra_o_veredito_e_o_placar` |
| 4 Raio-X | olhar o Pátio | esqueleto, barras de confiança por classe com o piso, detecções descartadas, trilhas de 5 s, vetor de velocidade, decisão separada da confiança | `test_raio_x_liga_pela_tecla_x` |
| 5 Gêmeo digital | arrastar para orbitar; "Visão de drone"; tocar numa pessoa | cápsulas na cor do estado; linha do tempo e replay da pessoa | `test_gemeo_3d_mostra_pessoas_e_desenha_a_30_fps` |
| 6 Queda | esperar ~13 s (a gravação toca a 0,25×; dizer em voz alta que é câmera lenta e por quê — BANCA 21) | a queda AO VIVO com "GRAVAÇÃO · 0,25×" sobre o vídeo, a pílula "Queda detectada · Pessoa N" e, ao lado, o incidente com linha causal e replay | `test_palco_queda_ao_vivo_em_camera_lenta` |
| 7 Incidente e linha causal | trocar de ID nas abas; "ver quadro"; **Reconhecer** | "13:02:10 aproximou-se… → entrou na zona sem capacete → permaneceu 38 s → reconhecido em 6 s"; reconhecer rápido dá ponto ao setor | `test_incidente_linha_causal_e_custodia_integra` |
| 8 Cadeia de custódia | **Verificar integridade** | "Evidências íntegras" e o hash do último elo | `test_auditoria_verifica_a_cadeia_inteira` |
| 9 Simulador "E se?" | arrastar um vértice da zona, **Reprocessar** | quantos alertas teriam disparado, lado a lado com os reais | `test_simulador_reprocessa_e_nunca_muda_alerta_real` |
| 10 Liga de Setores | olhar o placar | pontos que entraram na demo (check-in, reconhecimento), missões do turno, nível da planta | `test_liga_missao_cumprida_celebra_e_pontua_o_setor` |
| 11 Retrospectiva | deixar rodar ou → | stories do turno com dados reais; **Baixar PNG** | `test_retrospectiva_exporta_card_em_png` |
| 12 Obrigado | — | os números do momento, de novo | — |

Se sobrar tempo: Modo TV (`/tv`), relatório do turno (NR-6), `/rotular`,
celular como câmera.

## Reset entre apresentações (< 10 s)

```bash
flask --app wsgi demo reset
```

Limpa alertas, incidentes, eventos, clipes, a cadeia de custódia, os pontos da
Liga e a fila de rótulos; recria os workers e religa as câmeras. As contas e as
missões continuam. Sem servidor no ar, limpa direto o banco da demo.

## Números ao vivo (≤ 5 min)

```bash
python scripts/bench.py --rapido
```

## Plano B por falha

| falha | o que acontece | o que fazer |
|---|---|---|
| tudo falhou | — | tocar o **vídeo de backup** da demo (seção abaixo) |
| celular não abre o controle | sem `--https`, ou outra rede | seguir pelo teclado do notebook (→ / ←) |
| webcam não abre | o Portal toca a gravação `portal.mp4` | seguir; dizer que é gravação (o selo GRAVAÇÃO está na tela) |
| "Liberado" demora no Portal | o modelo vê o capacete em ~2 de cada 3 quadros; um quadro sem ele zera a sequência | esperar (p95 na cena: 5,9 s); com jurado, pedir que fique de frente e parado |
| câmera para / some | pílula "Reconectando, tentativa N"; volta sozinha | esperar ~10 s ou "Iniciar câmera" |
| tela estranha | — | `flask --app wsgi demo reset` e recarregar |
| sem WebGL no projetor | o gêmeo cai para a planta 2D sozinho | seguir |
| sem internet | nada muda: a demo é offline | — |
| porta 5000 ocupada | `run.py` não sobe | `PORT=5050` nos dois comandos |
| GPU Intel indisponível | runtime cai para ONNX/CPU (aparece no Diagnóstico; fumaça 6/6 nesse caminho em clone limpo, 15/10) | seguir; a análise fica mais lenta, o vídeo não |

## Vídeo de backup (plano B)

O Modo Apresentação percorrendo as 12 cenas, em 1920×1080 (138 s, H.264):
**https://github.com/bolla-X/Challenge_5550/releases/tag/next-2026-demo**
(asset `visionepi-palco-demo.mp4`). Baixe **antes** da apresentação e deixe no
notebook: a demo é offline, o plano B também tem de ser.

Gravado com `python e2e/video_do_palco.py` contra `python run.py --demo` (sem
webcam): começa na abertura, o Portal chega a "Liberado" com a gravação
`portal.mp4` e a queda sai ao vivo a 0,25×. Regravar depois de mudar o palco:
o mesmo comando gera `bench/runtime/video-palco/palco.mp4` e o GIF do README.
