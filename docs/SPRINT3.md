# Sprint 3 — camada LLM multimodal

Máquina: AMD Ryzen 7 5700X, CPU-only, `torch 2.14.0+cpu`, Windows 10,
Python 3.11.9. Cenas em `tests/fixtures/cenas/` — origem, autor, licença e
checksum em [FIXTURES.md](FIXTURES.md).

## O que a camada é

`app/llm/` recebe bytes de imagem e devolve `AnaliseRisco` validada, ou `None`.
Não conhece Flask, banco nem socket. `app/services/llm_risk_service.py` decide
**quando** vale gastar uma chamada e garante que gastar essa chamada nunca
segure o loop de captura.

A regra que organiza o módulo: **resposta que não cabe no schema não pode virar
alerta.** Um modelo de linguagem devolve JSON truncado, campo alucinado, prosa
no lugar de JSON. Se qualquer um desses gerar um `Alert` no banco, o sistema
passa a inventar violação de segurança — pior do que não ter camada LLM.
`AnalisadorDeRisco.analisar` nunca levanta: devolve `None` e registra.

## Sprint 2 (YOLO puro) — medido nas 3 cenas

`imgsz=416`, `conf=0.35`, `MULTI_PERSON_DETECTION=true`. Status por pessoa via
`PersonComplianceMatcher`.

| cena | pessoas | EPIs detectados | veredito do YOLO | verdade observável |
|---|---|---|---|---|
| **segura** | 2 | `vest` 0,57 · `vest` 0,39 | `vest: ok` para as 2; **`helmet: missing` para as 2** | ambos usam capacete **e** colete |
| **risco** | 6 | nenhum | os 6 sem nada: helmet, vest, gloves, glasses, mask, safety_shoe | ~9 pessoas, nenhuma de capacete ou colete |
| **ambígua** | 3 | `helmet` 0,59 · 0,58 · 0,54 | `helmet: ok` para as 3; `vest: missing` para as 3 | 3 de capacete, nenhuma de colete |

### O achado mais importante desta tabela

**Na cena SEGURA, o YOLO produz dois falsos positivos de "sem capacete".** Os
dois trabalhadores estão de capacete branco, visível a olho nu, e o Vyra não
detecta nenhum dos dois a `imgsz=416`. O sistema criaria dois alertas
`missing_helmet` de severidade `critical` sobre pessoas em conformidade.

Isso não é ruído estatístico — é a falha que justifica ter uma segunda opinião
na arquitetura. E é coerente com o que já estava medido: o `imgsz=416` está
abaixo da resolução de treino do modelo (640, ver `args.yaml`), e a
[BENCH.md](BENCH.md) registra que a 416 o modelo perde caixa que acha a 640.

Na cena **risco** o YOLO acerta: não há EPI e ele reporta ausência de tudo. Na
**ambígua** ele acerta os capacetes e reporta colete ausente — o que é
factualmente verdadeiro; se é *violação* depende de a atividade exigir colete,
e isso o detector não tem como saber.

## Sprint 3 (YOLO + LLM) — PENDENTE DE CHAVE DE API

**Esta coluna está vazia, e vazia é a resposta honesta.** Não há
`GEMINI_API_KEY` nesta máquina — verificado no `.env` e no ambiente. Sem a
chave não existe chamada real, e sem chamada real não existe golden. Inventar
uma resposta plausível aqui produziria uma tabela bonita e falsa.

| cena | v1 | v2 |
|---|---|---|
| segura | — | — |
| risco | — | — |
| ambígua | — | — |

Para preencher, com a chave no `.env` (arquivo ignorado pelo git):

```bash
python scripts/fetch_fixtures.py    # baixa as 3 cenas
python scripts/gravar_goldens.py    # 6 chamadas reais, uma vez
pytest tests/test_llm_goldens.py    # 18 asserções sobre as respostas gravadas
```

O que já está pronto e verificado, esperando só a chave:

- **`scripts/gravar_goldens.py`** chama a API uma vez por cena e versão, e
  congela `resposta_crua`, `modelo`, `latencia_ms` e `bytes_imagem` em
  `tests/goldens/`. Recusa sobrescrever sem `--forcar` — golden trocado sem
  intenção vira teste que sempre passa. A chave não entra no arquivo.
- **`tests/test_llm_goldens.py`** roda 3 cenas × 2 versões **offline**: a
  resposta real atravessa o schema, revalidar dá o mesmo resultado, e o golden
  registra procedência. Hoje: **18 skipped**, com mensagem apontando o comando.
  Não passa em falso.
- A latência real de cada chamada é gravada e vem para esta seção.

### O que esperar de v1 e v2, e como saber se a expectativa estava errada

`prompts/v1.md` pede a análise e o formato. `prompts/v2.md` mantém o mesmo
schema e muda o critério de decisão: distingue "ausente" de "não visível",
exige contar pessoas antes, calibra `confianca` por checagem e pondera
exigência por atividade. O diff de intenção completo está no próprio `v2.md`.

Expectativa registrada **antes** de rodar, para poder ser refutada: na cena
ambígua, `v2` deve reportar **menos** EPIs ausentes e confiança mais baixa que
`v1`. Se reportar exatamente o mesmo, a instrução não pegou — e isso também é
resultado a publicar.

E o teste real da camada é a cena **segura**: se o LLM disser que há capacete
onde o YOLO disse que não há, a segunda opinião pagou-se. Se concordar com o
YOLO e confirmar os dois falsos positivos, a camada não acrescenta nada nessa
falha — e o relatório vai dizer isso.

## A integração assíncrona, medida

A CPU já está saturada: 19,56 fps com o pipeline inteiro em uma câmera. A
chamada LLM **não entra no caminho do frame**.

Desenho: disparo por evento, no máximo **uma chamada em voo por câmera**,
debounce por janela de tempo, e **descarte em vez de fila** quando já houver
uma em voo.

Por que descarte e não fila: enfileirar 26 alertas de 7 s de vídeo produziria
26 chamadas atrasadas, com a fila crescendo enquanto a violação persiste e as
respostas chegando para descrever uma cena que já passou. Descartar mantém a
análise sempre sobre o presente.

**Prova** (`python scripts/bench_llm.py --frames 250`, provedor simulando
1500 ms de latência, aquecimento de 12 quadros descartado):

| | LLM desligado | LLM ligado |
|---|---|---|
| **FPS** | **19,53** | **19,45** |
| `submeter()` p50 / máx | 0,003 / 0,004 ms | **0,011 / 0,016 ms** |
| chamadas ao provedor | 0 | 1 |
| aceitos | 0 | 1 |
| descartados — uma em voo | 0 | **6** |
| descartados — debounce | 0 | **72** |
| inválidos | 0 | 0 |

**Delta de FPS: −0,4%**, dentro do ruído entre execuções. A chamada no caminho
do frame custa **11 microssegundos** — é só marcar o slot e entregar ao
executor.

**79 eventos submetidos, 1 aceito, 78 descartados.** Com `debounce=15 s` sobre
~13 s de janela medida, uma única chamada cabe. É o comportamento pretendido:
sem o descarte, seriam 79 chamadas ao free tier por 7 segundos de vídeo.

O provedor deste bench **simula** a latência com `sleep`, de propósito: com a
API real o número dependeria de rede, cota e humor do serviço, e o bench
deixaria de ser reprodutível. O que está sob prova é o desenho — que uma
chamada lenta, qualquer que seja a origem da lentidão, não segura o loop.

## Degradação e segredo

- Sem `GEMINI_API_KEY`, o serviço nasce **desligado** e o resto do sistema
  funciona normalmente. É degradação explícita, não erro.
- Falha, timeout ou schema inválido: evento ignorado com log, contador
  `invalidos`, e **nenhum** callback. O slot de "em voo" é liberado no
  `finally`, em todos os caminhos.
- Exceção no consumidor não escapa nem trava a câmera.
- A chave vive só no `.env`. `redigir_segredos()` remove padrão de chave do
  Google de qualquer mensagem antes de virar log, e há um teste que **varre
  todos os arquivos versionados** procurando `AIza...`. Esse teste pegou um
  problema real: a chave falsa que eu havia escrito literal no próprio arquivo
  de teste.
- Zero rede e zero SDK nos testes, verificado empiricamente bloqueando
  `socket` e o import de `google.genai` — a suíte passa igual nos dois casos.

## Medido e NÃO adotado

Três decisões em que o número existe e a mudança não foi feita. Estão aqui
porque um relatório que só mostra o que deu certo não é auditável.

### ONNX: a doc anuncia até 3x em CPU; nesta máquina foi 26% mais lento

A documentação da Ultralytics não impõe fabricante para ONNX e declara "up to
3x CPU speedup" ([integrations/onnx](https://docs.ultralytics.com/integrations/onnx/)).
Medido com o `best.onnx` que o próprio Hexmon publica, sem exportar nada:

| | PyTorch `.pt` | ONNX | delta |
|---|---|---|---|
| `yolo_epi` p50 | 160,55 ms | 213,12 ms | **+32,7%** |
| FPS | 11,67 | 8,63 | **−26,1%** |

`onnxruntime` foi instalado só no venv local para a medição e **não** entrou no
`requirements.txt`. Ecoa o que já havia acontecido com o OpenVINO, rejeitado no
commit `2d74e96` por ser mais lento no worker real.

### `static_image_mode`: 2,25x de ganho medido, e não aplicado

O MediaPipe Pose roda com `static_image_mode=True` no caminho por pessoa.
Trocar para o modo de stream, medido em 21 recortes reais da fixture:

| modo | p50 | poses encontradas |
|---|---|---|
| `True` (atual) | 34,10 ms | 11/21 |
| `False` | **15,14 ms** | 15/21 |

Não aplicado, e a razão é a documentação oficial
([solutions/pose.md#static_image_mode](https://github.com/google-ai-edge/mediapipe/blob/master/docs/solutions/pose.md#static_image_mode)):

> "If set to `true`, person detection runs every input image, **ideal for
> processing a batch of static, possibly unrelated, images**."

É exatamente o que `estimate_for_people` alimenta — recortes de pessoas
**diferentes**, alternadamente, na mesma instância. As 4 poses extras do modo
stream não são prova de acurácia: são igualmente compatíveis com "detectou
melhor" e com "arrastou landmarks do recorte anterior". E a fixture não contém
queda, então o empate no veredito não exercita o caso discriminante.

O caminho que daria os dois — uma instância MediaPipe por pessoa rastreada, em
modo de stream — está registrado em [BENCH.md](BENCH.md) como próximo passo.

### A classe `Person` do Vyra não generaliza

36 células testadas (3 fotos independentes de canteiro com pessoas de corpo
inteiro × `imgsz` 416/640/960/1280 × `conf` 0,35/0,10/0,02, instância nova do
modelo a cada célula): **zero detecções**, confiança máxima 0,000, inclusive na
resolução de treino.

Causa na matriz de confusão publicada pelo próprio autor: `Person` tem ~**277**
instâncias de validação contra ~**8.946** de `Hardhat`. É a menor classe real
do dataset. Na mesma imagem, `yolov8n.pt` (COCO) acha as duas pessoas com 0,87
e 0,73.

Por isso `MULTI_PERSON_DETECTION=true` é o padrão, ao custo declarado de
**−20% de FPS**. Sem ele o sistema desenha EPI no vídeo e nunca avalia ninguém.

## O que 3 cenas NÃO sustentam

Três imagens não sustentam afirmação de acurácia, em nenhuma direção. O que
elas sustentam é **existência**: que o pipeline atravessa, que o schema
rejeita o que deve rejeitar, que a integração não derruba o FPS, e que existe
ao menos um caso real — a cena segura, dois falsos positivos de capacete — em
que o detector sozinho erra de forma que um supervisor notaria.

Qualquer número de precisão ou revocação exigiria um conjunto anotado, com
dezenas a centenas de cenas e concordância entre anotadores. Não existe neste
projeto, e o relatório não vai fingir que existe.
