# Roteiro do demo — sexta

Máquina: AMD Ryzen 7 5700X, **CPU-only** (`torch 2.14.0+cpu`,
`torch.cuda.is_available() == False`), Windows 10 Pro 10.0.19045, Python
3.11.9. Todo número deste documento foi medido nesta máquina.

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
| Perfil/codec do H.264 da câmera | O publicador local usa `libx264 -preset ultrafast`. A Dahua usa o encoder dela, com outro perfil e outro intervalo de keyframe. |
| Firewall, VLAN, NAT, ONVIF, limite de sessões simultâneas | Nada disso existe em `localhost`. |
| `subtype=1` (substream) existir e estar habilitado na câmera | O default do cadastro é substream por medição de custo; se a câmera tiver o substream desligado, a URL não abre. Aí é `--subtype 0`. |

**Portanto o demo roda em modo fixture.** RTSP é upgrade oportunístico, nunca
requisito.

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

## Runbook de sondagem — 5 minutos, sexta de manhã

Rode **antes** do demo. Cada passo tem o que fazer se falhar. Se qualquer passo
falhar, **o demo segue em modo fixture** — não tente consertar rede na frente
do avaliador.

### Passo 1 — a rede responde? (30 s)

```bash
ping -n 2 10.14.22.97
```

- **Responde** → passo 2.
- **Timeout / "Host de destino inacessível"** → **pare aqui.** Não há rota.
  Vá para [Demo em modo fixture](#demo-em-modo-fixture). É o resultado
  esperado: foi exatamente isso que aconteceu em toda esta bancada.

### Passo 2 — a porta 554 aceita conexão? (30 s)

```bash
powershell -Command "Test-NetConnection 10.14.22.97 -Port 554 -InformationLevel Quiet"
```

- **`True`** → passo 3.
- **`False`** → o host responde mas o RTSP não. Firewall, porta diferente, ou
  serviço RTSP desabilitado na câmera. Tente `-Port 80` para confirmar que a
  câmera está viva; se estiver, é bloqueio de porta e **não** se resolve na
  hora. Vá para modo fixture.

### Passo 3 — abre e lê um frame? (2 min)

O teste que importa. Preencha `RTSP_USUARIO`/`RTSP_SENHA` no `.env` primeiro
(nunca em linha de comando: fica no histórico do shell e em `ps aux`).

```bash
./.venv/Scripts/python.exe -c "
import cv2
from app.config import Config, montar_url_rtsp
from app.llm import redigir_segredos
url = montar_url_rtsp(host='10.14.22.97', usuario=Config.RTSP_USUARIO,
                      senha=Config.RTSP_SENHA, porta=Config.RTSP_PORTA,
                      canal=1, subtype=Config.RTSP_SUBTYPE)
print('tentando:', redigir_segredos(url))
cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG,
                       [int(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC), 5000,
                        int(cv2.CAP_PROP_READ_TIMEOUT_MSEC), 5000])
print('abriu:', cap.isOpened())
ok, frame = cap.read()
print('leu frame:', ok, frame.shape if ok else None)
cap.release()"
```

- **`abriu: True` e `leu frame: True`** → passo 4. Anote o `shape`: é a
  resolução do substream.
- **`abriu: True`, `leu frame: False`** → autenticou e não entrega vídeo.
  Tente `subtype=0` (stream principal): o substream pode estar desabilitado na
  câmera. Se `0` funcionar, cadastre com `--subtype 0` e conte com FPS pior
  (resolução maior custa: 416→640 derrubou o FPS em 42% nesta máquina).
- **`abriu: False`** → credencial errada, ou caminho diferente. **Não fique
  tentando variações.** Modo fixture.

### Passo 4 — cadastra (1 min)

```bash
./.venv/Scripts/flask.exe --app wsgi cameras add --name "Fresa 1" --host 10.14.22.97 --local "Setor A"
./.venv/Scripts/flask.exe --app wsgi cameras list
```

A credencial é montada de `RTSP_USUARIO`/`RTSP_SENHA` do `.env`. A saída mostra
`rtsp://***@10.14.22.97:554/...` — a senha não aparece, e não deve.

### Passo 5 — se der tudo certo (1 min)

Suba, faça login, inicie o monitoramento e confirme que o badge da câmera diz
**recebendo** (verde) e não "modo fixture" (âmbar). Se disser modo fixture, a
fonte caiu depois de cadastrada: o demo continua, com fonte de demonstração.

---

## Demo em modo fixture

**É este o caminho padrão.** Não é plano B envergonhado: é o que está validado
ponta a ponta nesta máquina.

### Preparo (uma vez, na noite anterior)

```bash
./.venv/Scripts/python.exe scripts/fetch_fixtures.py           # baixa a fixture e as 3 cenas
./.venv/Scripts/python.exe scripts/fetch_fixtures.py --check   # confirma: "OK: 1 fixture(s) e 3 cena(s)"
npm --prefix frontend run build
AUTO_CREATE_TABLES=false ./.venv/Scripts/flask.exe --app wsgi db upgrade
./.venv/Scripts/flask.exe --app wsgi users create --email supervisor@visionepi.local --name "Supervisor Demo" --role supervisor
```

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
Use se o objetivo é mostrar a resiliência. Cadastre a câmera da planta (que não
responde) e baixe o teto de tentativas no `.env`:

```bash
# no .env:  RTSP_MAX_TENTATIVAS=1
./.venv/Scripts/flask.exe --app wsgi cameras add --name "Fresa 1" --host 10.14.22.97
```

Tempo até o modo fixture assumir, **medido** contra `10.14.22.97` (que não tem
rota desta máquina), com 39 frames publicados 3 s depois da troca em todos os
casos:

| `RTSP_MAX_TENTATIVAS` | tempo até `modo=fixture` |
|---|---|
| 1 | **5,3 s** |
| 3 | 17,0 s |
| 5 (default) | 33,2 s |

Com o default são 33 s de tela mostrando "reconectando" antes de aparecer
imagem. Para apresentar, use `1`. (Antes do teto de abertura de fonte de rede,
isso levava mais de 150 s — ver [BENCH.md](BENCH.md).)

---

## Roteiro cronometrado — 12 minutos

| t | O que dizer / fazer | Comando |
|---|---|---|
| **0:00** | Sobe a aplicação. Deixe o terminal visível: a única WARNING é o cookie não-Secure, esperado em `http://localhost`. | `./.venv/Scripts/python.exe run.py` |
| **0:30** | Login como supervisor. O cabeçalho mostra nome e papel; `backend` e `conexão` ficam verdes. Não existe "criar conta": num sistema de segurança do trabalho, quem cria acesso é quem já tem. | navegador em `http://127.0.0.1:5000` |
| **1:30** | **A declaração.** Diga, antes de qualquer demonstração: sem rota para a rede da planta, o RTSP real nunca foi exercitado; o que está validado é o caminho RTSP contra servidor local, e o demo roda em modo fixture. Dizer isso no começo compra credibilidade para todo o resto. | — |
| **2:00** | Inicia o monitoramento. Vídeo com caixas de EPI e pose. Aponte o badge da câmera. | botão Iniciar |
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

# 2. publicador: bench.mp4 em loop, re-encodado para H.264
#    (a fixture e FMP4/MPEG-4 parte 2; `-stream_loop -1` repete sem fim,
#     `-re` entrega na taxa nativa em vez de o mais rapido possivel)
./ffmpeg.exe -re -stream_loop -1 -i tests/fixtures/bench.mp4 \
  -an -c:v libx264 -preset ultrafast -tune zerolatency -g 30 -pix_fmt yuv420p \
  -f rtsp -rtsp_transport tcp \
  "rtsp://usuario:senha@localhost:554/cam/realmonitor"
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

## Se algo der errado no demo

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| Tela do dashboard parece antiga | build do frontend desatualizado | `npm --prefix frontend run build` e recarregue com Ctrl+Shift+R |
| `ModuleNotFoundError: mediapipe` | rodou com o `python` do PATH (3.10.6) | use `./.venv/Scripts/python.exe` |
| `table alerts already exists` no `db upgrade` | `AUTO_CREATE_TABLES=true` | `AUTO_CREATE_TABLES=false ./.venv/Scripts/flask.exe --app wsgi db upgrade` |
| 4 erros `404` no console do navegador | rotas legadas (`/status`, `/settings`, `/overlay`, `/risk-area`) operam sobre "a câmera padrão" e não há câmera cadastrada | cadastre uma câmera; não são erros de JavaScript |
| Badge âmbar "modo fixture" quando se esperava ao vivo | a fonte configurada não respondeu N vezes | é o comportamento correto. Diga isso: o sistema continua e informa de qual fonte está lendo |
| Vídeo travando | inferência é o gargalo, não a captura | baixe `YOLO_IMGSZ` (416 já é o default) ou `DETECTION_EVERY_N_FRAMES=2`. Nunca mexa nisso durante a apresentação |
| Câmera "parada" sem erro | worker sem câmera habilitada | `cameras list` e confira `ativa` |
| Sem alerta nenhum | `MULTI_PERSON_DETECTION=false` | tem que ser `true`: a classe `Person` do Vyra não generaliza (36 células testadas, zero detecções) |

---

## Forçar cada modo, resumido

```bash
# fixture como fonte (mais confiavel)
./.venv/Scripts/flask.exe --app wsgi cameras add --name "Demo" --fonte tests/fixtures/bench.mp4

# fallback visivel em ~5 s  (.env: RTSP_MAX_TENTATIVAS=1)
./.venv/Scripts/flask.exe --app wsgi cameras add --name "Fresa 1" --host 10.14.22.97

# webcam USB
./.venv/Scripts/flask.exe --app wsgi cameras add --name "Webcam" --fonte 0
```

A camada LLM liga com `LLM_ENABLED=true` **e** `GEMINI_API_KEY` no `.env`. Sem
chave ela nasce desligada e o resto do sistema funciona normalmente — é
degradação explícita, não erro. `LLM_ENABLED=false` é o default.
