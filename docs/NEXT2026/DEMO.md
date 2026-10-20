# DEMO: roteiro da final

Só entra aqui o que passou no E2E (`e2e/test_fluxos.py`, `e2e/test_missao2.py`),
com as **4 câmeras ligadas** e sem pausa de contorno. O teste que sustenta cada
momento está indicado.

**Última verificação: 15/10, `main` @ `d76941b`, sob carga** (27 % de CPU de
terceiros): E2E **36/36** com as 4 câmeras numa rodada só; clone limpo pelo
README com a fumaça **6/6 no OpenVINO e 6/6 no ONNX**. Detalhe em `ESTADO.md`.

**Cenas novas (MISSÃO 4, Fase 6): 6 das 18.** Cada uma reaproveita uma função da
MISSÃO 4 (saúde visual M1, torre/OPC UA M2, evacuação M3, regras M4, permissão M5,
primeiro acesso), mas as cenas em si **ainda não rodaram no E2E do palco**: o que
foi verificado é o servidor (`tests/test_palco.py`, `tests/test_evacuacao.py`) e o
`tsc`. Ensaie as seis **uma vez, na máquina da apresentação**, antes da banca;
as colunas "E2E" abaixo dizem "ensaiar" onde isso vale.

## Dia da apresentação (checklist)

1. **Véspera e manhã**, na máquina da apresentação: `python scripts/preparar.py --so-cache`.
2. Feche tudo o que não é a demo: Docker, Salesforce CLI, Teams, navegadores extras (CPU de terceiros foi a
   ameaça nº 1 em todas as medições).
3. Suba **antes** da banca e deixe no ar: `python run.py --demo --https` (≈ 1 min até a 1ª análise).
4. Anote as três senhas que o terminal imprime (não aparecem de novo).
5. Abra `https://127.0.0.1:5000`, entre como **supervisor**, confira em `/status` que tudo está "OK" (modelos, 4
   câmeras, OPC UA e MQTT "no ar"; LLM "desligado" é o esperado).
6. Ensaie uma vez as 6 cenas novas do palco (lista abaixo), com a webcam ligada para "Tape a câmera".
7. Entre apresentações: `flask --app wsgi demo reset` (< 10 s).
8. Plano B: o vídeo da Release `next-2026-demo` (baixe antes) e a tabela "Plano B por falha" abaixo.

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
- a demo escuta só em `127.0.0.1`: para o controle pelo celular, rode com `--https` (abre na rede local);
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
- Nas cenas **Portal**, **Tente enganar a IA**, **Tape a câmera**, **Queda** e
  **Permissão com vigia**, só a câmera da cena analisa:
  as outras ficam **"Pausada pela apresentação"** (o rodapé do palco diz quais)
  e voltam ao sair da cena. Fechar o palco no meio devolve as câmeras em ~8 s.
- Algumas cenas **mexem em dado real e desfazem ao sair**: "Tape a câmera" refaz a
  referência de saúde visual da webcam ao entrar; "Permissão com vigia" emite uma
  permissão de demonstração (responsável "Equipe de demonstração", janela de 1 h) e
  a encerra ao sair; "Evacuação" encerra e grava o relatório se o próprio palco a
  acionou. Uma evacuação acionada por outro caminho (a tela `/evacuacao`) **não** é
  encerrada ao navegar. Se o preparo falhar, o palco não cai: o rodapé mostra, em
  vermelho, o que **não** está acontecendo.
  Tempo até "Liberado" na cena, com `portal.mp4` e as 4 câmeras ligadas (10
  repetições, E2E): **p50 3,5 s, p95 5,9 s**. Fora do palco (`/portal`, as 4
  analisando): p50 13,4 s, p95 24,2 s — por isso o Portal se mostra pelo palco.

## Roteiro (18 cenas, ≈ 11 min estimados; as 12 originais levam ≈ 7 min)

| cena | o que fazer | o que aparece | E2E |
|---|---|---|---|
| 1 VisionEPI | abrir | câmeras no ar, pessoas na planta e incidentes ativos **agora**, nesta máquina | `test_palco_pelo_teclado_e_pelo_celular` |
| 2 Portal de Entrada | um jurado diante da webcam (sem webcam: a gravação `portal.mp4`); as outras câmeras pausam | só os EPIs exigidos; confirmado / faltando / "não verificável neste enquadramento"; "Liberado" com tudo confirmado (p50 3,5 s na cena); check-in conta para a Liga | `test_portal_no_palco_pausa_as_outras_e_libera` |
| 3 Tente enganar a IA | escolher "Boné no lugar do capacete", **Valendo!** | o que o modelo viu e por quê ("o modelo viu com 0,31 (abaixo do piso 0,40) e descartou"); placar da sessão, inclusive quando a IA é enganada | `test_tente_enganar_a_ia_mostra_o_veredito_e_o_placar` |
| 4 Raio-X | olhar o Pátio | esqueleto, barras de confiança por classe com o piso, detecções descartadas, trilhas de 5 s, vetor de velocidade, decisão separada da confiança | `test_raio_x_liga_pela_tecla_x` |
| 5 Tape a câmera | tapar a lente da webcam com a mão; esperar o alerta; destapar (sem webcam: ver "Plano B") | vídeo grande da webcam com o selo "Imagem OK"; tampada, vira "OBSTRUÍDA" (selo vermelho) e o alerta "Câmera obstruída"; destapada, volta a "Imagem OK". A referência da câmera é refeita ao entrar na cena. Confirmação e liberação de 3 s por padrão (valor de projeto, ainda não cronometrado no palco) | ensaiar |
| 6 Gêmeo digital | arrastar para orbitar; "Visão de drone"; tocar numa pessoa | cápsulas na cor do estado; linha do tempo e replay da pessoa | `test_gemeo_3d_mostra_pessoas_e_desenha_a_30_fps` |
| 7 Queda | esperar ~13 s (a gravação toca a 0,25×; dizer em voz alta que é câmera lenta e por quê — BANCA 21) | a queda AO VIVO com "GRAVAÇÃO · 0,25×" sobre o vídeo, a pílula "Queda detectada · Pessoa N" e, ao lado, o incidente com linha causal e replay | `test_palco_queda_ao_vivo_em_camera_lenta` |
| 8 Evacuação | clicar **Acionar evacuação**; deixar o cronômetro correr alguns segundos; **Encerrar e gravar relatório** (ou seguir para a próxima cena, que encerra sozinha) | cronômetro, pessoas por câmera e a soma, o aviso de dupla contagem; ao encerrar: "Relatório nº N" e "Registrado na cadeia de custódia" (o elo entra na cadeia que a cena 10 verifica) | ensaiar |
| 9 Incidente e linha causal | trocar de ID nas abas; "ver quadro"; **Reconhecer** | "13:02:10 aproximou-se… → entrou na zona sem capacete → permaneceu 38 s → reconhecido em 6 s"; reconhecer rápido dá ponto ao setor | `test_incidente_linha_causal_e_custodia_integra` |
| 10 Cadeia de custódia | **Verificar integridade** | "Evidências íntegras" e o hash do último elo | `test_auditoria_verifica_a_cadeia_inteira` |
| 11 Simulador "E se?" | arrastar um vértice da zona, **Reprocessar** | quantos alertas teriam disparado, lado a lado com os reais | `test_simulador_reprocessa_e_nunca_muda_alerta_real` |
| 12 Regra sem código | só olhar (**Testar de novo** repete o teste) | a regra "Sem capacete por 5 s na zona de risco" em blocos (Zona, EPI, Duração), a frase "Como a regra se lê" e o resultado de "Testar no histórico" na câmera Pátio (disparos, pessoas, linha do tempo); se a trilha ainda for curta, a **mensagem real do servidor**, nunca um número combinado | ensaiar |
| 13 Permissão com vigia | só olhar; o alerta depende de a gravação do Pátio ter alguém na zona sem ninguém na área do vigia | a permissão de demonstração (nº PT, "Equipe de demonstração", válida até), "A câmera auxilia o vigia; não o substitui (NR-33, 33.3.4.1)" e, quando acontecer, o alerta "Sem vigia". Ao sair, a permissão é encerrada. Não foi medido quanto tempo o alerta leva a aparecer: se não vier, explique a regra em vez de esperar | ensaiar |
| 14 Fábrica conectada | olhar a torre; se houver um cliente OPC UA à mão, mostrar o nó (`INTEGRACAO.md`) | a torre de luz grande, OPC UA e MQTT "no ar" e a linha "o mesmo estado que um CLP lê em `Planta.PlantaEmAlarme`: verdadeiro/falso", com o valor de agora | ensaiar |
| 15 Primeiro acesso em 30 s | só mostrar (o "30 s" é a meta do roteiro; não foi cronometrado, não o cite como medido) | logado como **supervisor**: os 7 passos com "Encontrado: …" do que o sistema detectou agora; como técnico: a trilha estática e "No produto, cada passo detecta sozinho o que já está pronto." | ensaiar |
| 16 Liga de Setores | olhar o placar | pontos que entraram na demo (check-in, reconhecimento), missões do turno, nível da planta | `test_liga_missao_cumprida_celebra_e_pontua_o_setor` |
| 17 Retrospectiva | deixar rodar ou → | stories do turno com dados reais; **Baixar PNG** | `test_retrospectiva_exporta_card_em_png` |
| 18 Obrigado | — | os números do momento, de novo | — |

Se sobrar tempo: Modo TV (`/tv`), relatório do turno (NR-6), `/rotular`,
celular como câmera. Para um roteiro mais curto (≈ 8 min, estimado), pule com → as cenas 8, 12, 13,
14 e 15; a 5 só vale com a webcam ligada.

### Falas das cenas novas (curtas, para dizer em voz alta)

- **5 Tape a câmera:** "Cegar uma câmera é a sabotagem mais simples, e o modelo continuaria
  dizendo 'nenhuma violação'. Vou tapar a lente. [tapa] Em poucos segundos o sistema acusa
  'obstruída' em vez de ficar calado. [destapa] Voltou sozinho."
- **8 Evacuação:** "Na emergência a pergunta é 'quantos estão onde?'. [aciona] A contagem é por
  câmera, nunca por pessoa, e a tela avisa que pode haver dupla contagem se duas câmeras se
  sobrepõem. [encerra] O relatório entra na cadeia de custódia."
- **12 Regra sem código:** "O técnico monta a regra em blocos, sem programar. Antes de ativar,
  testa na trilha gravada: este é o resultado real da câmera, não uma estimativa. Se a trilha for
  curta, o sistema diz isso em vez de inventar número."
- **13 Permissão com vigia:** "Espaço confinado exige permissão e vigia. A câmera confere: gente
  na zona e ninguém na área do vigia vira alerta crítico. Ela auxilia o vigia; não o substitui
  (NR-33, 33.3.4.1)."
- **14 Fábrica conectada:** "A torre mostra exatamente o que o CLP lê por OPC UA ou MQTT: um
  estado só, calculado num lugar só."
- **15 Primeiro acesso:** "O assistente leva da primeira câmera à planta pronta, e cada passo
  detecta sozinho o que já está feito, em vez de confiar em marcação manual."

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
| webcam desligada na cena "Tape a câmera" | a cena usa o Portal gravado (ou a primeira câmera ao vivo cadastrada) e avisa "Esta câmera toca uma gravação: tapar a lente não muda nada" | pular a cena com → (as outras não dependem dela) ou ligar a webcam e subir a demo de novo; não tape a tela esperando efeito |
| legenda em vermelho no rodapé de uma cena nova | o preparo da cena falhou (referência da câmera, permissão); o palco segue e o texto diz o que **não** está acontecendo | falar só do que está na tela e olhar o log do servidor depois |
| "Acionar evacuação" desligado | a tela não obteve a chave do palco (conta sem perfil de técnico) | entrar como supervisor e recarregar `/palco`; ou acionar em `/evacuacao` (essa evacuação não é encerrada ao sair da cena) |
| "Regra sem código" mostra uma mensagem em vez de números | a câmera ainda não tem trilha gravada (acabou de ligar) ou o EPI estava desligado na gravação | esperar ~1 min com as câmeras no ar e **Testar de novo**; ler a mensagem como ela vem |
| "Primeiro acesso" só traz a trilha estática | conta técnica (o assistente é do supervisor) | entrar como supervisor e recarregar `/palco` |
| "Liberado" demora no Portal | o modelo vê o capacete em ~2 de cada 3 quadros; um quadro sem ele zera a sequência | esperar (p95 na cena: 5,9 s); com jurado, pedir que fique de frente e parado |
| câmera para / some | pílula "Reconectando, tentativa N"; volta sozinha | esperar ~10 s ou "Iniciar câmera" |
| tela estranha | — | `flask --app wsgi demo reset` e recarregar |
| sem WebGL no projetor | o gêmeo cai para a planta 2D sozinho | seguir |
| sem internet | nada muda: a demo é offline | — |
| porta 5000 ocupada | `run.py` não sobe | `PORT=5050` nos dois comandos |
| GPU Intel indisponível | runtime cai para ONNX/CPU (aparece no Diagnóstico; fumaça 6/6 nesse caminho em clone limpo, 15/10) | seguir; a análise fica mais lenta, o vídeo não |

## Vídeo de backup (plano B)

O Modo Apresentação percorrendo as **18 cenas** (as 12 originais e as 6 da MISSÃO 4), em 1920×1080
(202 s, H.264, regravado em 20/10/2026; a queda saiu ao vivo em 12 s nessa gravação):
**https://github.com/bolla-X/Challenge_5550/releases/tag/next-2026-demo**
(asset `visionepi-palco-demo.mp4`). Baixe **antes** da apresentação e deixe no
notebook: a demo é offline, o plano B também tem de ser.

Gravado com `python e2e/video_do_palco.py` contra `python run.py --demo` (sem
webcam): começa na abertura, o Portal chega a "Liberado" com a gravação
`portal.mp4` e a queda sai ao vivo a 0,25×. Regravar depois de mudar o palco:
o mesmo comando gera `bench/runtime/video-palco/palco.mp4` e o GIF do README.
