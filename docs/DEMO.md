# Roteiro do demo — sexta

Máquina: AMD Ryzen 7 5700X, **CPU-only** (`torch 2.14.0+cpu`,
`torch.cuda.is_available() == False`), Windows 10 Pro 10.0.19045, Python
3.11.9. Todo número deste documento foi medido nesta máquina.

## Se você só tem 30 segundos antes de apresentar, leia isto

Quatro coisas foram descobertas medindo, tarde, e cada uma teria estragado a
apresentação de um jeito diferente:

1. **A tela demora, e não está travada.** Boot frio até o primeiro alerta são
   **~35 s**: `run.py` leva **17 s** até o navegador responder (carrega os dois
   pesos YOLO e o MediaPipe), e o botão **Iniciar bloqueia por 7,6 s** antes de
   devolver. Os dois parecem congelamento e não são. **Não clique duas vezes** —
   espere. O roteiro reserva 3 minutos para chegar ao primeiro alerta, então há
   folga de sobra.
2. **`LLM_TIMEOUT_S=8` abortaria 100% das chamadas.** A API do Gemini recusa
   deadline abaixo de **10 s** (`HTTP 400`, *"Minimum allowed deadline is
   10s"*), e as 6 chamadas reais levaram de **16 a 38 segundos**. O default
   agora é **30 s**. Se alguém "otimizar" isso de volta para 8, a camada de
   segunda opinião gasta cota e nunca produz nada — pior que desligada. E é o
   que faz o desenho assíncrono valer: 27 s de latência mediana não custam **um
   único frame**, porque a chamada roda fora da thread de captura.
3. **`AUTO_CREATE_TABLES=false` subia com ZERO workers** — corrigido, mas saiba
   o sintoma. A aplicação subia, o login funcionava, a lista de câmeras
   aparecia, e **nada iniciava**: todo `start` devolvia `409 sem worker ativo`.
   Se você vir isso, é porque está rodando código anterior ao commit `8f227df`.

4. **O vídeo ficava fluido e ATRASADO ao mesmo tempo — CORRIGIDO, mas saiba
   reconhecer.** Em fonte RTSP os frames que o pipeline não consumia
   enfileiravam e nada os descartava (`CAP_PROP_BUFFERSIZE=1` é recusado pelo
   backend FFMPEG: `set()` devolve `False`, e 104 frames ficavam na fila). O
   atraso crescia **+8,1 s a cada minuto**, sem teto. Agora o `VideoStream`
   descarta frame atrasado em fonte de rede, e medido no mesmo cenário:
   **13,5 s → 2,55 s de atraso, com a deriva em −0 ms/s**
   ([BENCH.md](BENCH.md), Fase 7). Se ainda assim a tela responder cada vez
   mais tarde, é sinal de outra coisa — reporte, não degrade o pipeline no
   escuro.

E a moldura de tudo: **até esta sexta, o RTSP nunca tinha sido exercitado
contra as câmeras da planta** (próxima seção). Agora vai ser, e o runbook de
campo é o que transforma isso em passos com critério de parada — com o modo
fixture como plano B pronto.

---

## ⚠️ A declaração que precisa aparecer no slide

**O RTSP nunca foi exercitado contra as câmeras da planta.**

Não é ressalva de rodapé, é o limite do que este trabalho prova:

- **Não há rota desta máquina para `10.14.0.0/16`.** Os 5 endereços da planta
  dão timeout. Medido: abrir `rtsp://10.14.22.97:554/...` demora 5 s e falha
  (com o teto de abertura; sem ele eram 34 s).
- **A credencial das câmeras nunca entrou nesta máquina** além do `.env`, que é
  ignorado pelo git. Nenhum teste, log, relatório ou commit a contém.
- **O que foi validado é o caminho RTSP contra um servidor local** (mediamtx
  com usuário e senha, ver [abaixo](#servidor-rtsp-local)): abrir, ler frames,
  matar o servidor, religar, reconectar sozinho, e cair em modo fixture quando
  não religa.

O que isso **não** autoriza dizer: que é só trocar a URL. O que muda da bancada
para a planta e não está coberto por nenhuma medição daqui:

| Diferença | Por que pode quebrar |
|---|---|
| Latência e perda de pacote de uma rede industrial de terceiro | O servidor local é `localhost`: 0 ms, 0% de perda. `leitura` p95 já saltou de 1,89 ms (arquivo) para 109 ms (RTSP local) — numa rede real esse número é desconhecido. |
| Autenticação real da Dahua | mediamtx e Dahua não são o mesmo servidor. O formato da URL é o mesmo (doc oficial, p. 79) e o mecanismo de credencial funciona; a implementação de auth do fabricante não foi exercitada. |
| Perfil/codec do H.264 da câmera | O publicador local **imita** um perfil Dahua (D1 704x576, 15 fps, 512 kbps, GOP 30 — ver [BENCH.md](BENCH.md), Fase 6), mas os parâmetros são **típicos**, não lidos das câmeras. A Dahua usa encoder de hardware, com outro rate control e sem o lookahead do x264 — que sozinho somava 2,0 s de atraso na bancada. O passo (a) do runbook confere a resolução e o FPS reais. |
| **Atraso acumulado** | Corrigido contra o servidor local (13,5 s → 2,55 s, deriva zerada), mas o descarte foi calibrado no perfil da bancada. Numa rede com jitter e perda, o limiar que separa "veio do buffer" de "esperou a rede" (5 ms) pode precisar de outro valor. O passo (a) mede os dois lados para você comparar. |
| Firewall, VLAN, NAT, ONVIF, limite de sessões simultâneas | Nada disso existe em `localhost`. |
| `subtype=1` (substream) existir e estar habilitado na câmera | O default do cadastro é substream por medição de custo; se a câmera tiver o substream desligado, a URL não abre. Aí é `--subtype 0`. |

**O plano da sexta é ao vivo, dentro da rede da planta, com as câmeras reais** —
e é a primeira vez que qualquer uma das linhas acima será exercitada de
verdade. Por isso o [runbook de campo](#runbook-de-campo--dentro-da-planta-na-ordem-com-o-comando-exato)
existe, e por isso ele sonda antes de cadastrar: cada passo tem um critério de
parada.

**O modo fixture continua sendo o plano B, e continua pronto.** Se a sondagem
falhar, o demo segue com a fonte de demonstração — que é o único caminho
validado ponta a ponta nesta máquina. Trocar para ele não é improviso, é o
comportamento projetado. Diga a declaração acima de qualquer jeito, os dois
cenários: ela é sobre o que estava *provado antes de entrar na fábrica*.

---

## Antes de qualquer coisa: as duas armadilhas do ambiente

Já custaram tempo antes. Checar leva 20 segundos.

### 1. `python` do PATH é 3.10.6 — o venv é obrigatório

```bash
python --version                      # 3.10.6  <- NAO use este
./.venv/Scripts/python.exe --version  # 3.11.9  <- este
```

`mediapipe==0.10.14` e `numpy==1.26.4` não publicam wheel para 3.13+, e o venv
foi criado com `py -3.11`. Rodar `python run.py` com o Python do PATH usa outro
interpretador, sem as dependências. **Sempre** `./.venv/Scripts/python.exe`.

### 2. Build do frontend desatualizado serve UI velha

`app/static/dist/` é versionado. O Flask serve o que está ali, não o que está
em `frontend/src/`. Se alguém alterou o frontend e não rebuildou, a tela do
demo é a antiga — sem nenhum erro visível.

```bash
npm --prefix frontend run build
git status --short app/static/dist    # vazio = o build commitado esta em dia
```

Saída limpa significa que o build é reprodutível e igual ao versionado.

---

## Qual roteiro usar: webcam (hoje) ou campo (sexta)

Dois roteiros, sem sobreposição. Escolha pela pergunta que você quer responder:

| você quer... | use | onde |
|---|---|---|
| ensaiar o fluxo e a narração **sem a rede da planta** | **teste local com webcam** | logo abaixo |
| conectar nas câmeras Dahua **dentro da fábrica** | **runbook de campo** | [seção (a)–(e)](#runbook-de-campo--dentro-da-planta-na-ordem-com-o-comando-exato) |
| ter imagem garantida quando tudo mais falhar | **modo fixture** | [seção do modo fixture](#demo-em-modo-fixture) |

Os três usam a **mesma base de código** e o mesmo cadastro: o que muda é a
fonte (`--fonte 0` para webcam, `--host` para Dahua, `--fonte
tests/fixtures/bench.mp4` para fixture). Não há caminho especial de webcam.

---

## Teste local com webcam — ensaio de hoje, sem rede nenhuma

### 1. Descobrir o índice

```bash
./.venv/Scripts/python.exe scripts/sondar_cameras.py --usb 0 --usb 1 --pessoas
```

A mesma sonda do campo, agora aceitando índice USB. Reporta resolução, **FPS
real medido** e o enquadramento da pessoa, e grava o quadro em
`runtime/sondagem/`. Se não souber quais índices existem, o dashboard tem
"Adicionar câmera" com descoberta automática (ou
`GET /api/cameras/discover?max_index=3`).

Medido nesta máquina com uma **Logi C920e** no índice 0:

```
alvo      sub  554  abriu   resolucao  fps decl  fps real  abrir ms  pessoas  alt %
usb-0       -    -    sim     640x480      0.00     14.39       670        0    0.0
```

> **`fps decl` = 0,00 é normal em webcam.** O DirectShow não reporta a taxa; o
> que vale é o `fps real`. E o DirectShow é o backend certo aqui: medido, abrir
> o índice 0 custou **2,52 s** nele contra **10,22 s** no MSMF. O projeto já
> escolhe DirectShow para fonte `int` no Windows.

### 2. Cadastrar

Não existe opção nova: `--fonte` com o índice já classifica como USB.

```bash
./.venv/Scripts/flask.exe --app wsgi cameras add --name "Webcam bancada" \
  --local "Mesa" --fonte 0 --largura 640 --altura 480
```

### 3. Subir e conferir na tela

```bash
./.venv/Scripts/python.exe run.py
```

Login, **Iniciar**, e o rodapé do card mostra `<fps> · <resolução>` — para a
C920e, algo como `8.9 fps · 640x480`.

> ⚠️ **Entre como Técnico para ver o diagnóstico.** O modo da interface é o
> **papel** de quem logou, e não há seletor: o painel **Modelo YOLO**, com
> `Detecções (30s)`, não aparece para Supervisor. Verificado no DOM.

### 4. O que esperar

| cenário | medido |
|---|---|
| 1 webcam sozinha | **~8,9 fps** a 640x480 |
| webcam + 1 RTSP ao mesmo tempo | 4,9 a 7,7 cada, 9,9 a 14,7 agregado |

**Webcam não acumula atraso.** Ao contrário do RTSP, o driver USB entrega só o
quadro corrente: parando de ler por 10 s, a webcam devolveu **1** frame
instantâneo e bloqueou, contra **104** do RTSP ([BENCH.md](BENCH.md), Fase 8).
Por isso o descarte de frame atrasado fica **desligado** em USB — ligá-lo só
jogaria fora quadro bom.

### 5. Se a imagem vier preta

Aconteceu nesta bancada e custou tempo. A câmera **abre e entrega frames**
normalmente; só a imagem é preta (média de pixel 0,02). Descarte software
primeiro, é rápido:

```bash
powershell -Command "(Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\webcam').Value"
```

`Allow` aqui e no `HKLM` equivalente significa que **não é permissão**. Aí
sobra o físico: tampa/obturador da lente, ou modo privacidade no utilitário do
fabricante (LogiTune, nas Logitech). Nenhum ajuste de `YOLO_CONFIDENCE`
conserta lente tampada — e o painel diz isso sozinho: `Detecções (30s)` em
**NENHUMA** com `Fonte agora` mostrando resolução e FPS saudáveis.

---

## Runbook de campo — dentro da planta, na ordem, com o comando exato

Cinco passos. Os três primeiros levam ~8 minutos e são sempre executados; os
dois últimos são condicionais, e cada um só entra se o sintoma dele aparecer.

**Se qualquer passo até o (b) falhar, o demo segue em modo fixture** — não
tente consertar rede na frente do avaliador. O caminho está
[abaixo](#demo-em-modo-fixture) e é o que está validado ponta a ponta.

Antes de tudo, os 20 segundos de sempre: `./.venv/Scripts/python.exe --version`
tem que dizer **3.11.9**, e `git status --short app/static/dist` tem que sair
**vazio** (ver [as duas armadilhas](#antes-de-qualquer-coisa-as-duas-armadilhas-do-ambiente)).
E preencha `RTSP_USUARIO`/`RTSP_SENHA` no `.env` — nunca na linha de comando,
que fica no histórico do shell e em `ps aux`.

---

### (a) Sondar os 5 endereços, nos dois subtypes — 3 min

Um comando só. Troque os endereços pelos 5 da planta:

```bash
./.venv/Scripts/python.exe scripts/sondar_cameras.py --pessoas \
  10.14.22.97 10.14.22.98 10.14.22.99 10.14.22.100 10.14.22.101
```

Ele faz, para cada endereço **e para `subtype=0` e `subtype=1`**: testa TCP 554,
abre com o mesmo backend e o mesmo teto de 5 s que o worker usa, lê um frame,
mede o **FPS real** (não o declarado) e grava o primeiro quadro em
`runtime/sondagem/`. Com `--pessoas` roda também o YOLO de pessoa e reporta
quantas achou e a altura da maior caixa em % do quadro.

```
alvo                       sub  554  abriu   resolucao  fps decl  fps real  abrir ms  pessoas  alt %
10.14.22.97                  0   ok    sim   1920x1080     25.00     24.91       310        3   62.4
10.14.22.97                  1   ok    sim     704x576     15.00     14.97       288        3   61.8
10.14.22.98                  0   ok    sim   1920x1080     25.00     24.88       295        1   14.2
...
```

Três colunas decidem, e cada uma manda para um lugar diferente:

| o que aparece | o que significa | o que fazer |
|---|---|---|
| `554 = NAO` | não há rota, ou firewall | pare nesse endereço. Se **todos** derem isso, modo fixture |
| `abriu = NAO` com `554 = ok` | credencial errada, ou caminho diferente | confira `RTSP_USUARIO`/`RTSP_SENHA`. **Não fique tentando variações** |
| `abriu = NAO` só no `sub 1` | o substream está desabilitado nessa câmera | cadastre essa com `--subtype 0` |
| `fps real` << `fps decl` | a rede não entrega o que a câmera anuncia | é o número que vale; use-o no passo (c) |
| `alt %` baixo (< 25%) | a pessoa é pequena no quadro | evite essa câmera: EPI é objeto pequeno **dentro** da pessoa |

> **O `fps real` continua sendo a coluna mais importante, mesmo depois do
> conserto da fila.** Quando a câmera entrega mais fps do que o pipeline
> consome, o excedente é **descartado** (frame velho não vai para a tela) —
> medido: atraso estável em 2,55 s com deriva de −0 ms/s, contra 13,5 s e
> subindo antes ([BENCH.md](BENCH.md), Fase 7). O que você perde não é mais
> latência, é **taxa de análise**: os frames descartados não são inspecionados.
> Se `fps real` for muito maior que o do passo (c), vale baixar o FPS **na
> câmera** — economiza banda e não muda o que o sistema enxerga.

---

### (b) Escolher as 2 melhores e cadastrar — 2 min

Olhe as imagens de `runtime/sondagem/` lado a lado. **O critério é
enquadramento de pessoa, não resolução.** Capacete e óculos são objetos
pequenos dentro da pessoa: uma câmera 1080p com a pessoa ocupando 15% da altura
detecta pior que uma D1 com a pessoa ocupando 60%. A coluna `alt %` já ordena
isso; as imagens confirmam ângulo e oclusão, que nenhuma métrica pega.

```bash
./.venv/Scripts/flask.exe --app wsgi cameras add --name "Fresa 1" --host 10.14.22.97 --local "Setor A"
./.venv/Scripts/flask.exe --app wsgi cameras add --name "Prensa 2" --host 10.14.22.99 --local "Setor B"
./.venv/Scripts/flask.exe --app wsgi cameras list
```

O `subtype` sai de `RTSP_SUBTYPE` no `.env`, cujo default é **1 (substream)**.
A saída mostra `rtsp://***@10.14.22.97:554/...` — a senha não aparece, e não
deve.

**Suba o teto de tentativas antes de apresentar.** O default `2` foi calibrado
para "a rede não responde"; se a rede da planta está acessível, vale insistir
na câmera real em vez de trocar para a fixture na primeira oscilação:

```bash
# no .env
RTSP_MAX_TENTATIVAS=5
```

#### Escolher o subtype: pelo ENQUADRAMENTO, não pelo FPS

**Não escolha subtype por desempenho.** Escolha pela pessoa no quadro, usando a
tabela do passo (a): a coluna `alt %` e as imagens em `runtime/sondagem/`.

A regra curta, por câmera:

| o que a sondagem mostrou | use |
|---|---|
| `alt %` ≥ ~25% no substream | **`subtype=1`** (o default) — está bom, não mexa |
| `alt %` baixo no sub e maior no main | **`subtype=0`**, sem culpa |
| substream não abriu (`abriu = NAO` só no `sub 1`) | **`subtype=0`**, é a única opção |
| enquadramento igual nos dois | **`subtype=1`**, aí sim pela banda da rede |

```bash
./.venv/Scripts/flask.exe --app wsgi cameras add --name "Fresa 1" --host 10.14.22.97 --subtype 0
```

**Stream principal é escolha aceitável, não plano B.** Isso é medição, não
opinião ([BENCH.md](BENCH.md), Fase 6): medianas de 3 execuções, **14,76 fps no
substream contra 15,17 no principal** — empate dentro do ruído. Prefira o
principal sempre que ele enquadrar melhor a pessoa; prefira o substream quando
o enquadramento empatar, para poupar banda da rede da planta.

O motivo de o FPS empatar é contraintuitivo e vale saber, porque é o que
liberta a decisão: **a resolução da fonte não chega ao modelo.** `YOLO_IMGSZ`
fixa o **lado maior** da entrada da rede, então 1080p e D1 viram tensores do
mesmo lado maior. O que muda é o **aspecto**: D1 é 4:3 e vira `416x352`; 1080p
é 16:9 e vira `416x256`, 38% menos pixels. Medido isolado, o **4:3 custa +27%
de inferência** — ou seja, o substream é *mais caro* no YOLO e mais barato em
decode, anotação e encode (−79%, −58%, −78%). Os dois efeitos quase se anulam.

> Versões anteriores deste runbook diziam "conte com FPS pior (416→640 derrubou
> o FPS em 42%)". **Estava errado**: aqueles 42% são de `YOLO_IMGSZ`, que é
> outro botão — trocar o subtype não mexe nele. Se você lembrar dessa
> orientação, esqueça: ela fazia aceitar imagem pior de graça.

O que a planta ainda pode mudar: o raciocínio do aspecto pressupõe substream
**4:3**. Se a coluna `resolucao` do passo (a) mostrar um substream **16:9**
(640x360, 704x396), ele volta a ser estritamente mais barato — e aí o
`subtype=1` ganha pelos dois critérios.

---

### (c) Rodar 60 s e medir o FPS real — 2 min

```bash
./.venv/Scripts/python.exe run.py
```

Login, **Iniciar** em cada câmera (o botão bloqueia ~7,6 s; não clique duas
vezes), e deixe rodando 60 segundos antes de olhar o número — a janela de FPS
é de 5 s e a de detecções é de 30 s.

**Leia na própria tela, sem terminal.** Cada card de câmera mostra no rodapé
`<fps> · <largura>x<altura>`: o FPS vem do **loop de captura**, não da taxa de
telemetria, e a resolução é a do frame que **chegou** — que pode não ser a do
cadastro, porque em RTSP o backend ignora a resolução pedida. No painel
**Modelo YOLO** (modo Técnico) há a linha `Detecções (30s)` com a contagem por
classe.

O que esperar, medido nesta máquina com o perfil de substream Dahua
([BENCH.md](BENCH.md), Fase 6):

| | FPS por câmera | agregado |
|---|---|---|
| 1 câmera | ~14,7 | ~14,7 |
| **2 câmeras** | **5,8 a 7,9 cada** | **11,6 a 15,6** |

**Faixa, não ponto** — e a faixa é larga de verdade: o mesmo cenário de 1
câmera variou de 13 a 16 fps entre execuções, e o ensaio de 2 câmeras deu 11,6
no harness de pipeline e 15,6 no worker real (7,9 + 7,7), ambos medidos.
Se você vir 12 ou 15, os dois são normais; **abaixo de ~5 por câmera** é que
vale ir para o passo (d).
**Duas câmeras não dobram nada** — a inferência é serializada pelo
`inference_lock` e cada uma recebe metade (`espera_lock` medido em 221 ms).

Compare com o `fps real` do passo (a): se o pipeline estiver **abaixo** do que
a câmera entrega, o atraso cresce (ver o aviso no passo a) e você precisa do
passo (d) mesmo que a imagem pareça fluida.

---

### (d) SE o FPS estiver ruim: a ordem de degradação

Um degrau por vez, **medindo depois de cada um** — e nunca durante a
apresentação. Ganhos medidos nesta máquina, 1 câmera, fonte no perfil de
substream Dahua, mediana de 2 execuções em ordens invertidas (ida e volta) para
a deriva térmica não virar diferença entre os degraus:

| # | mudança | FPS | ganho | o que se perde |
|---|---|---|---|---|
| — | base: `YOLO_IMGSZ=416`, `DETECTION_EVERY_N_FRAMES=3`, pose on | 16,5 | — | — |
| **1** | `DETECTION_EVERY_N_FRAMES=5` | **26,7** | **+61%** | alerta demora ~0,4 s a mais para confirmar |
| **2** | `POSE_PER_PERSON=false` + tirar `pose` de `DEFAULT_FEATURES` | 20,8 | **+26%** | **queda e postura deixam de existir**. EPI não é afetado |
| **3** | `YOLO_IMGSZ=320` | 21,0 | **+27%** | detecção de objeto pequeno: capacete e óculos, que são o demo |
| **4** | parar uma das câmeras | ~16,5 na que sobra | **+156%** por câmera | metade do parque |

**Faça na ordem.** Ela não é por tamanho de ganho, é por **custo do que se
perde**:

- O degrau 1 é quase de graça: com a histerese contando detecção (não iteração
  de loop), 3 confirmações a `every_n=5` levam ~0,94 s contra ~0,56 s a
  `every_n=3`. É o maior ganho e o menor prejuízo — comece por ele, e talvez
  pare aí.
- O degrau 2 remove uma **feature de segurança inteira** (queda), mas não toca
  na detecção de EPI, que é o que está sendo demonstrado.
- O degrau 3 ataca justamente o que o demo mostra. A 416 o modelo já perde
  capacete que acharia a 640; a 320 perde mais. **Último recurso.**
- O degrau 4 é o único que ataca a contenção de verdade, porque o gargalo é o
  `inference_lock` — mas custa uma câmera.

Depois de cada degrau, os dois números da tela (FPS do card e `Detecções (30s)`
do painel) dizem se valeu: FPS subiu **e** a contagem por classe continua
parecida? Bom. FPS subiu e a contagem despencou? Você comprou fluidez com
detecção — volte um degrau.

---

### (e) SE a detecção não pegar EPI: o que verificar ANTES de mexer em confiança

Baixar `YOLO_CONFIDENCE` é a primeira ideia de todo mundo e quase sempre a
errada: ela não faz o modelo enxergar o que não está na imagem, só transforma
ruído em caixa. Antes disso, cinco checagens, na ordem, cada uma com onde
olhar:

1. **O modelo está vendo ALGUMA coisa?** Painel **Modelo YOLO** → `Detecções
   (30s)`. Se disser **NENHUMA** e o FPS do card estiver saudável, o problema
   não é confiança — é fonte, enquadramento, ou o modelo estar errado para esta
   cena.

   Se disser algo, **leia a proporção entre as classes, não o total**. No
   ensaio contra o servidor local a leitura foi
   `helmet: 2 · person: 37 · vest: 127`: o modelo está claramente vivo, vê
   pessoa e colete o tempo todo, e **quase nunca capacete** — com todo mundo
   de capacete branco na imagem. Isso não é falta de confiança, é objeto
   pequeno demais no quadro (a pessoa ocupava 21% a 28% da altura). Vá para o
   item 3, não para o `YOLO_CONFIDENCE`.
2. **A fonte está entregando o que você acha?** Mesmo painel, linha `Fonte
   agora`. Resolução minúscula ou FPS no chão explicam detecção ruim sozinhos.
   Isso separa "é o modelo" de "é a fonte" em 5 segundos, que é para isso que
   os dois números estão lado a lado.
3. **A pessoa está grande o bastante?** Volte à coluna `alt %` do passo (a).
   Abaixo de ~25% da altura do quadro, o capacete tem poucos pixels e **nenhum
   ajuste de confiança resolve**. A correção é trocar de câmera (passo b) ou
   subir para `subtype=0` — o custo em FPS é ~zero, ver acima.
4. **O EPI da fábrica é o que o modelo conhece?** O Vyra foi treinado em
   `Hardhat`, `Safety Vest`, `Gloves`, `Goggles`, `Mask`. Capacete de aba total,
   colete refletivo de outro padrão, luva de raspa escura, óculos de sobrepor:
   são objetos que o dataset dele pode simplesmente não ter. Compare a lista
   `Classes carregadas` do painel com o que as pessoas estão vestindo. Se o EPI
   da planta não estiver representado, **isso não é bug e não se resolve na
   sexta** — é retreino, e a resposta honesta é dizer isso.
5. **Iluminação e ângulo.** Contraluz (janela ou portão atrás da pessoa),
   câmera muito alta olhando para o topo da cabeça, ou EPI da mesma cor do
   fundo. Compare o quadro salvo em `runtime/sondagem/` com as fotos onde o
   modelo comprovadamente funciona (`tests/fixtures/cenas/`).

Só depois disso, e sabendo o que está comprando, `YOLO_CONFIDENCE` mais baixo
(0,35 → 0,25). E diga em voz alta que baixou: com o modelo já produzindo **dois
falsos positivos de "sem capacete"** na cena SEGURA ([SPRINT3.md](SPRINT3.md)),
menos confiança significa mais falso positivo, não mais acerto.

---

## Demo em modo fixture

**É o plano B, e ele não é envergonhado:** é o único caminho validado
ponta a ponta nesta máquina.

### Preparo (uma vez, na noite anterior)

```bash
./.venv/Scripts/python.exe scripts/fetch_fixtures.py           # baixa a fixture e as 3 cenas
./.venv/Scripts/python.exe scripts/fetch_fixtures.py --check   # confirma: "OK: 1 fixture(s) e 3 cena(s)"
npm --prefix frontend run build
AUTO_CREATE_TABLES=false ./.venv/Scripts/flask.exe --app wsgi db upgrade
./.venv/Scripts/flask.exe --app wsgi users create --email supervisor@visionepi.local --name "Supervisor Demo" --role supervisor
```

Tempos **medidos** neste preparo, num banco novo: `--check` 0,3 s, build 4,2 s,
`db upgrade` 1,6 s (4 migrações). O `users create` é humano — ver abaixo.

> ⚠️ **`users create` PRECISA de terminal interativo.** Ele não recebe a senha
> por argumento (de propósito: argumento fica no histórico do shell e em
> `ps aux`), então **prompta** — duas vezes, senha e confirmação. Medido: com a
> entrada fechada ele fica **esperando para sempre**, e mandar a senha por pipe
> (`printf 'senha\nsenha\n' | flask ... users create`) **também não funciona**:
> o prompt oculto do Click lê o console direto no Windows, não o stdin.
>
> Se você precisa da conta dentro de um script (CI, provisionamento), use a
> rota programática:
>
> ```bash
> ./.venv/Scripts/python.exe -c "
> from app import create_app
> from app.services.auth_service import AuthService
> app = create_app()
> with app.app_context():
>     AuthService().create_user(email='supervisor@visionepi.local',
>                               name='Supervisor Demo',
>                               password='TROQUE_ESTA_SENHA', role='supervisor')"
> ```
>
> Para trocar a senha depois: `flask --app wsgi users set-password --email ...`
> (que prompta do mesmo jeito, e pelo mesmo motivo).

> `AUTO_CREATE_TABLES=false` no `db upgrade` **não é opcional** num banco novo:
> com `true` o `create_app()` roda `db.create_all()` antes do subcomando e o
> Alembic colide com as tabelas que ele mesmo deveria criar
> (`table alerts already exists`). Ver [AMBIENTE.md](AMBIENTE.md), desvio #1.

### Forçar modo fixture — duas formas, escolha pelo que quer mostrar

**(a) A fixture como fonte, direto.** Mais confiável; a câmera fica "ao vivo"
num arquivo. Use se o objetivo é só ter imagem estável na tela.

```bash
./.venv/Scripts/flask.exe --app wsgi cameras add --name "Setor A - demo" --fonte tests/fixtures/bench.mp4
```

**(b) O fallback acontecendo de verdade**, com o badge âmbar "modo fixture".
Use se o objetivo é mostrar a resiliência: cadastre uma câmera num endereço da
planta, que não responde desta máquina.

```bash
# --fonte com a URL inteira: NAO exige credencial no .env
./.venv/Scripts/flask.exe --app wsgi cameras add --name "Fresa 1" --local "Setor A" \
  --fonte "rtsp://10.14.22.97:554/cam/realmonitor?channel=1&subtype=1"
```

> ⚠️ **Por que `--fonte` e não `--host` aqui.** `--host` monta a URL a partir de
> `RTSP_USUARIO`/`RTSP_SENHA` e **falha alto** se essas variáveis não estiverem
> no `.env`:
>
> ```
> Error: RTSP_USUARIO e RTSP_SENHA não estão no .env. Sem credencial a câmera
> seria cadastrada e nunca conectaria.
> ```
>
> Isso está certo para a câmera de verdade (passo 4 do runbook), e é ruído para
> este cenário: a câmera não responde de todo jeito, então a credencial não
> muda nada. `--fonte` evita ter que inventar credencial só para demonstrar o
> fallback. Um `.env` novo, copiado do `.env.example`, tem as duas variáveis
> **vazias** — então `--host` falha até você preenchê-las.

Tempo até o modo fixture assumir, **medido** contra `10.14.22.97` (que não tem
rota desta máquina), com 39 frames publicados 3 s depois da troca em todos os
casos. Cada tentativa custa o teto de abertura de 5 s:

| `RTSP_MAX_TENTATIVAS` | tempo até `modo=fixture` | |
|---|---|---|
| 1 | 5,3 s | mais rápido; quase não tolera queda passageira |
| **2** | **10,9 s** | **default** |
| 3 | 17,0 s | |
| 5 | 33,2 s | default anterior |

**Por que 2, e o que se perde.** Com 5 são 33 segundos de tela mostrando
"reconectando" antes de aparecer qualquer imagem — no projetor, na frente do
avaliador, é o pior cenário possível. Com 2 são 11 s, que cabem numa frase de
contexto enquanto acontece.

O custo é real e vale dizer em voz alta: **quanto menor o teto, mais cedo o
sistema desiste da câmera de verdade.** Numa rede instável, uma queda
passageira de 15 s passa a virar troca para a fonte de demonstração em vez de
uma reconexão. Para operação contínua na planta, `5` é a escolha melhor — e é
o que o passo 5 do runbook manda fazer se a rede responder.

(Antes do teto de abertura de fonte de rede, o mesmo fallback levava mais de
150 s — ver [BENCH.md](BENCH.md).)

---

## Roteiro cronometrado — 12 minutos

Tempos de máquina **medidos** num ensaio do zero, com banco novo (o resto do
roteiro é narração, no seu ritmo):

| etapa | medido |
|---|---|
| `run.py` até o navegador responder | **17 s** |
| login (`POST /api/auth/login`) | 156 ms |
| `GET /api/cameras` | 5 ms |
| **`POST /api/cameras/<id>/start`** | **7,6 s — bloqueia** |
| até `modo=fixture` depois do start | 6,6 s |
| até o **primeiro alerta** depois do start | 9,6 s (`missing_gloves`, `medium`) |
| **boot frio → primeiro alerta na tela** | **≈ 35 s** |

O roteiro abaixo dá 3 minutos para chegar ao primeiro alerta, contra os ~35 s
medidos. A folga é de propósito.

| t | O que dizer / fazer | Comando |
|---|---|---|
| **0:00** | Sobe a aplicação. **Leva ~17 s até o navegador responder** — carrega os dois pesos YOLO e o MediaPipe; não é travamento. Deixe o terminal visível: a única WARNING é o cookie não-Secure, esperado em `http://localhost`. | `./.venv/Scripts/python.exe run.py` |
| **0:30** | Login como supervisor. O cabeçalho mostra nome e papel; `backend` e `conexão` ficam verdes. Não existe "criar conta": num sistema de segurança do trabalho, quem cria acesso é quem já tem. | navegador em `http://127.0.0.1:5000` |
| **1:30** | **A declaração.** Diga, antes de qualquer demonstração: sem rota para a rede da planta, o RTSP real nunca foi exercitado; o que está validado é o caminho RTSP contra servidor local, e o demo roda em modo fixture. Dizer isso no começo compra credibilidade para todo o resto. | — |
| **2:00** | Inicia o monitoramento. **O botão fica ~7,6 s sem responder** — a chamada de start limpa artefatos, resolve alertas velhos e tenta a fonte antes de voltar. É esperado; não clique duas vezes. Depois vem vídeo com caixas de EPI e pose. Aponte o badge da câmera. | botão Iniciar |
| **3:00** | Alerta aparecendo. Mostre a severidade, o snapshot de evidência e a linha do tempo. Diga o número: a histerese exige 3 detecções, não 3 iterações de loop — o fix derrubou 76 alertas para 26 em 7 s de vídeo e ainda ganhou 9,2% de FPS. | — |
| **4:30** | Marque um alerta como falso positivo. Mostre que o histórico sobrevive. | — |
| **5:30** | **Resiliência.** Se estiver no cenário (b), a câmera já entrou em modo fixture na frente de todos. Senão, mostre o ciclo com o servidor local (seção abaixo) ou o log da prova. Frase: "uma câmera morta não derruba as outras nem o processo — e a tela diz de qual fonte está lendo". | — |
| **7:00** | **Números.** [BENCH.md](BENCH.md): 19,56 fps com 1 câmera a 416; resolução é a maior alavanca (416→640 = −42%); multi-câmera **não escala** e a contenção medida é o `inference_lock` (134 a 237 ms de espera pura com 2 câmeras). Diga que é medição, não estimativa. | — |
| **9:00** | **Camada LLM.** Segunda opinião multimodal, fora do caminho do frame: `submeter()` custa 9 a 13 microssegundos e o re-bench com a camada ligada ficou dentro do ruído. O LLM **não** cria, resolve nem suprime alerta. Sem `GEMINI_API_KEY` a camada nasce desligada e o resto funciona. | — |
| **10:30** | **O achado do relatório de IA.** [SPRINT3.md](SPRINT3.md): na cena SEGURA o YOLO produz **dois falsos positivos de "sem capacete"** — os dois trabalhadores estão de capacete branco, visível a olho nu. É a falha que justifica ter segunda opinião na arquitetura. A coluna do LLM está **vazia por ausência de chave**, e vazia é a resposta honesta. | — |
| **11:30** | Fechamento: o que está medido, o que está inferido, o que não foi verificado. Nunca apresente as três categorias como uma. | — |

---

## Servidor RTSP local

O que substitui a câmera da planta na bancada. **Nenhum dublê de teste cobre o
caminho do `cv2.VideoCapture` sobre RTSP** — por isso ele existe.

### Por que mediamtx como servidor, e ffmpeg só como publicador

O requisito é servir **com usuário e senha**. A
[documentação oficial do ffmpeg](https://ffmpeg.org/ffmpeg-protocols.html),
seção RTSP, lista para o **muxer** apenas `rtsp_transport`, `rtsp_flags`,
`min_port`, `max_port`, `buffer_size` e `pkt_size` — **nenhuma opção de
autenticação**. Usuário e senha aparecem só no **demuxer**, isto é, para o
ffmpeg *conectar* num servidor, não para exigir credencial de quem conecta
nele. Então ffmpeg não serve como servidor autenticado.

mediamtx tem autenticação interna por usuário e permissão. Em troca, ele **não
tem fonte de arquivo local** (a `mediamtx.yml` de referência lista as fontes
aceitas e nenhuma é arquivo), então alguém precisa publicar o vídeo — e aí o
ffmpeg é o publicador.

Versões usadas: mediamtx **v1.21.0** (`mediamtx_v1.21.0_windows_amd64.zip`,
27.490.986 bytes, SHA-256
`8a58a9b8c25ee99a96c23dc0a17f39ace3072c01d2e148329073c64ddf83493d`) e ffmpeg
**n8.1.2** (build estático BtbN). Nenhum dos dois entra no `requirements.txt`:
são ferramenta de bancada, não dependência do produto.

### Comandos

`mediamtx-demo.yml` — a senha é **sintética**, criada para o teste:

```yaml
rtspAddress: :554
rtmp: false
hls: false
webrtc: false
srt: false
api: false
authMethod: internal
authInternalUsers:
  # O usuario `any` do arquivo de referencia foi REMOVIDO: sem isso, anonimo
  # leria o stream e a credencial na URL nao provaria nada.
  - user: demo
    # Escolha uma senha SINTETICA. A que produziu as medicoes abaixo tinha `@`
    # e `#` de proposito, para exercitar o percent-encoding da credencial.
    pass: <SENHA_SINTETICA>
    ips: []
    permissions:
      - action: publish
      - action: read
paths:
  cam/realmonitor:
    source: publisher
```

```bash
# 1. servidor
./mediamtx.exe mediamtx-demo.yml

# 2a. publicador SIMPLES: bench.mp4 em loop, como ela e (1280x720)
#     (a fixture e FMP4/MPEG-4 parte 2; `-stream_loop -1` repete sem fim,
#      `-re` entrega na taxa nativa em vez de o mais rapido possivel)
./ffmpeg.exe -re -stream_loop -1 -i tests/fixtures/bench.mp4 \
  -an -c:v libx264 -preset ultrafast -tune zerolatency -g 30 -pix_fmt yuv420p \
  -f rtsp -rtsp_transport tcp \
  "rtsp://usuario:senha@localhost:554/cam/realmonitor"

# 2b. publicador PERFIL DAHUA (substream D1): e o que produziu os numeros da
#     Fase 6 da BENCH.md. Use este para ensaiar o que a planta vai entregar.
#     `-pkt_size 1200` NAO e opcional: sem ele o mediamtx reempacota os RTP
#     ("packets are too big, 1460 > 1440") e o decoder do leitor recebe
#     bytestream truncado, com "error while decoding MB" em rajada.
./ffmpeg.exe -re -stream_loop -1 -i tests/fixtures/bench.mp4 -an \
  -vf "scale=704:576,fps=15" \
  -c:v libx264 -profile:v main -preset veryfast -bf 0 \
  -g 30 -keyint_min 30 -sc_threshold 0 \
  -b:v 512k -maxrate 512k -bufsize 1024k -pix_fmt yuv420p \
  -f rtsp -rtsp_transport tcp -pkt_size 1200 \
  "rtsp://usuario:senha@localhost:554/cam/realmonitor"

# 3. conferir o que o servidor esta entregando, com a MESMA sonda do campo
./.venv/Scripts/python.exe scripts/sondar_cameras.py \
  --url "rtsp://usuario:senha@localhost:554/cam/realmonitor?channel=1&subtype=1"
```

> `usuario:senha` e `<SENHA_SINTETICA>` acima são placeholders de propósito, e
> `usuario:senha@` é exatamente o placeholder que
> `tests/test_credencial_rtsp.py` reconhece como documentação. Esse teste varre
> todo arquivo **rastreado pelo git** procurando `usuario:senha@` em URL, e
> reprovou duas versões deste documento: a primeira trazia a senha sintética
> literal, a segunda um `<SENHA_URLENCODED>` que o regex também pega. O teste
> funcionando. Substitua na hora de rodar, sem commitar.
>
> Detalhe que vale saber: como a varredura usa `git ls-files`, ela só vê o
> arquivo **depois** de ele ser rastreado — um documento novo passa a ser
> auditado no commit, não antes.
>
> A credencial vai **percent-encoded** na URL (`@` → `%40`, `#` → `%23`).
> É o que `montar_url_rtsp` faz, e o teste contra o servidor local confirmou
> que ffmpeg e OpenCV decodificam de volta antes de autenticar. Uma senha com
> `@` cru deslocaria o host e o sintoma seria "a câmera não conecta", sem nada
> no log apontando a causa.

### O que foi provado com ele

Todos os itens abaixo foram observados, não inferidos.

**Abre, lê, e a credencial é o que dá acesso:**

| cenário | `isOpened` | frames lidos |
|---|---|---|
| COM credencial | `True` | **10** (1280x720, abertura em 1.193 ms) |
| SEM credencial | `False` | 0 |
| senha ERRADA | `False` | 0 |

O log do mediamtx registra `failed to authenticate: authentication failed` nos
dois últimos. Sem os negativos, o primeiro não provaria nada sobre credencial.

**Ciclo completo de resiliência**, com o `CameraWorker` real sobre
`cv2.VideoCapture` real:

```
[   4.5s] servidor RTSP no ar (mediamtx + publicador ffmpeg)
[   6.5s] OK  1. ao vivo pela URL RTSP com credencial
[   6.5s] servidor RTSP MORTO
[   9.8s] OK  2. backoff disparou e o estado aparece (reconectando)
[   9.8s]     state=reconnecting proxima_em=0.38s erro='Frame indisponível'
[  14.3s] servidor RTSP no ar
[  15.3s] OK  3. religou e reconectou sozinho, sem intervencao
[  15.3s]     total_reconnects=1 frames=29
[  15.3s] servidor RTSP MORTO
[  37.6s] OK  4. sem religar, caiu em MODO FIXTURE
[  41.6s]     OK  4b. o demo CONTINUA: frames 62 -> 110 em 4 s
[  41.6s]     state=live modo=fixture
[  41.6s]     OK  5. credencial redigida em 4 saidas com URL RTSP real
[  41.6s]     modos anunciados: ao_vivo, reconectando, ao_vivo, reconectando, fixture
VEREDITO: OK
```

**FPS: RTSP local vs arquivo local, 1 e 2 câmeras.** É o número mais próximo do
comportamento na planta que esta máquina consegue produzir.

| cenário | leitura p50 | leitura p95 | FPS/câmera | agregado |
|---|---|---|---|---|
| 1 câm, arquivo, **CPU livre** | 0,79 | 1,32 | 17,99 | 17,99 |
| 1 câm, arquivo, publicador ativo | 0,93 | 1,89 | 13,67 | 13,67 |
| 1 câm, **RTSP local** | 2,19 | **109,32** | 12,44 | 12,44 |
| 2 câm, arquivo, CPU livre | 1,09 | 2,16 | 8,02 + 8,01 | 16,02 |
| 2 câm, arquivo, publicador ativo | 1,10 | 2,09 | 8,32 + 8,32 | 16,63 |
| 2 câm, **RTSP local** | 2,37 | **207,00** | 7,83 + 6,96 | 13,93 |

Leitura, e a única honesta:

- **O confundidor primeiro.** O publicador ffmpeg encoda H.264 1280x720@30 na
  **mesma CPU**. Isolado: 17,99 → 13,67 fps, ou seja **−24,0%** só pelo
  publicador. Por isso as comparações válidas são entre linhas de **mesma carga
  de fundo**.
- **Custo da fonte RTSP, mesma carga:** 1 câmera 13,67 → 12,44 = **−9,0%**;
  2 câmeras 16,63 → 13,93 = **−16,2%**.
- **O p50 engana, o p95 é o número.** `leitura` p50 sobe pouco (0,93 → 2,19 ms)
  mas o p95 salta 58x (1,89 → 109,32 ms) e o máximo chegou a 2.231 ms com 2
  câmeras. É a fonte de rede esperando pelo próximo pacote — a cauda que uma
  fonte de arquivo simplesmente não tem.
- **Na planta deve ser melhor que 12,44 fps** — o encoder roda *dentro* da
  Dahua, não neste Ryzen. Isso é **INFERIDO**, não medido: seria preciso a
  câmera real para saber.

---

## Duas câmeras em modo fixture, ao mesmo tempo

O cenário real da sexta, medido — antes desta fase todo o teste de fallback
havia sido com **uma** câmera. Duas câmeras em endereços da planta (sem rota),
ambas caindo em fixture, ambas decodificando o mesmo arquivo em loop:

| | 60 s | 180 s |
|---|---|---|
| câmera 1 | 7,69 fps | 6,45 fps |
| câmera 2 | 7,69 fps | 6,45 fps |
| **agregado** | **15,38 fps** | **12,89 fps** |
| voltas na fixture, por câmera | 2,2 | 5,5 |

- **As duas rodam de verdade em paralelo, e dividem em partes iguais.** Em 48
  janelas de 5 s, **nenhuma** ficou com uma câmera parada, e a razão
  `cam1/cam2` ficou entre 0,85 e 1,17 — quase sempre exatamente 1,00. É o
  `inference_lock` alternando, como a [BENCH.md](BENCH.md) já media.
- **O tempo até as duas caírem em fixture foi 12,6 s** (com
  `RTSP_MAX_TENTATIVAS=1`), e não 5,3 s: cada câmera paga o teto de abertura de
  5 s, e os dois `open()` não se sobrepõem. Com o default `2`, conte ~20 s para
  as duas.
- **Não vaza.** Em 180 s: handles **−1,69/min** e threads **−0,78/min** (ambos
  caindo), RSS com deriva de +2,48 MB/min contra 31 MB de amplitude de ruído
  entre amostras — indistinguível de plano. O degrau único de ~75 MB no início
  é inicialização, não crescimento.
- Uma nota sobre a premissa: o loop **não reabre** o arquivo a cada volta. Ele
  rebobina com `CAP_PROP_POS_FRAMES` (`VideoStream.em_loop`), justamente para
  não pagar release+open a cada 7 s de vídeo. É por isso que os handles ficam
  planos.
- Variação entre execuções é grande (15,38 vs 12,89 agregado para o **mesmo**
  cenário), então trate esses números como faixa, não como ponto.

E os **dois badges corretos ao mesmo tempo** no navegador: topbar em "modo
fixture — fonte de demonstração", os dois cards com o badge âmbar "modo
fixture" e o rodapé "fonte de demonstração", cada um com sua própria imagem da
fixture.

---

## Se algo der errado no demo

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| Tela do dashboard parece antiga | build do frontend desatualizado | `npm --prefix frontend run build` e recarregue com Ctrl+Shift+R |
| `ModuleNotFoundError: mediapipe` | rodou com o `python` do PATH (3.10.6) | use `./.venv/Scripts/python.exe` |
| `table alerts already exists` no `db upgrade` | `AUTO_CREATE_TABLES=true` | `AUTO_CREATE_TABLES=false ./.venv/Scripts/flask.exe --app wsgi db upgrade` |
| 4 erros `404` no console do navegador | rotas legadas (`/status`, `/settings`, `/overlay`, `/risk-area`) operam sobre "a câmera padrão" e não há câmera cadastrada | cadastre uma câmera; não são erros de JavaScript |
| Badge âmbar "modo fixture" quando se esperava ao vivo | a fonte configurada não respondeu N vezes | é o comportamento correto. Diga isso: o sistema continua e informa de qual fonte está lendo |
| Vídeo travando | inferência é o gargalo, não a captura | confira o FPS no rodapé do card e siga a [ordem de degradação](#d-se-o-fps-estiver-ruim-a-ordem-de-degradação). Nunca mexa nisso durante a apresentação |
| **Vídeo fluido mas ATRASADO** (a pessoa se move e a tela responde segundos depois) | era a fila de frame do RTSP, **corrigida** (Fase 7). Se voltar, o descarte não está alcançando a fila | reinicie o monitoramento (zera a fila) e confira o `fps real` do passo (a) contra o FPS do card. Persistindo, baixe o FPS **na câmera** e reporte: o limiar do descarte pode não servir para essa rede |
| **`Detecções (30s)` diz NENHUMA** | modelo, fonte ou enquadramento — nesta ordem de probabilidade | siga o [passo (e)](#e-se-a-detecção-não-pegar-epi-o-que-verificar-antes-de-mexer-em-confiança). **Não** baixe `YOLO_CONFIDENCE` antes das 5 checagens |
| Card mostra resolução diferente da cadastrada | normal em RTSP: o backend FFMPEG ignora a resolução pedida | o número do card é o real. Se for pequeno demais para EPI, veja `subtype=0` no passo (b) |
| Câmera "parada" sem erro | worker sem câmera habilitada | `cameras list` e confira `ativa` |
| Todas as câmeras dão 409 "sem worker ativo" | corrigido nesta fase: `load_cameras_from_db()` só rodava com `AUTO_CREATE_TABLES=true`. Se ainda acontecer, é câmera com `enabled=false` | `cameras list` e confira `ativa`; em último caso reinicie o servidor |
| `flask users create` parece travado | está esperando a senha no prompt, que não ecoa | digite a senha e Enter; duas vezes. Não funciona por pipe |
| Sem alerta nenhum | `MULTI_PERSON_DETECTION=false` | tem que ser `true`: a classe `Person` do Vyra não generaliza (36 células testadas, zero detecções) |

---

## Forçar cada modo, resumido

```bash
# fixture como fonte (mais confiavel)
./.venv/Scripts/flask.exe --app wsgi cameras add --name "Demo" --fonte tests/fixtures/bench.mp4

# fallback visivel em ~11 s (default RTSP_MAX_TENTATIVAS=2; use 1 para ~5 s)
./.venv/Scripts/flask.exe --app wsgi cameras add --name "Fresa 1" --host 10.14.22.97

# webcam USB
./.venv/Scripts/flask.exe --app wsgi cameras add --name "Webcam" --fonte 0
```

A camada LLM liga com `LLM_ENABLED=true` **e** `GEMINI_API_KEY` no `.env`. Sem
chave ela nasce desligada e o resto do sistema funciona normalmente — é
degradação explícita, não erro. `LLM_ENABLED=false` é o default.
