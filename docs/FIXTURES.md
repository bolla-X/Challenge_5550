# Fixtures de vídeo

Fixtures de vídeo **não são versionadas**. Mesmo motivo dos pesos `.pt`: o
repositório é público, o arquivo é grande, e binário grande em git é ruim de
todo jeito. Elas são reproduzidas por um comando:

```bash
python scripts/fetch_fixtures.py
```

Verificar sem baixar nada:

```bash
python scripts/fetch_fixtures.py --check
```

O bench e os testes que dependem de fixture falham com mensagem apontando esse
comando — não com `FileNotFoundError` cru.

## `tests/fixtures/bench.mp4`

Usada por `scripts/bench_pipeline.py`. É a entrada fixa que torna o benchmark
comparável entre execuções e entre máquinas.

| Campo | Valor |
|---|---|
| Origem | [Building construction Moira Close Broadwater Farm Haringey 2025 13.webm](https://commons.wikimedia.org/wiki/File:Building_construction_Moira_Close_Broadwater_Farm_Haringey_2025_13.webm) |
| URL do arquivo | `https://upload.wikimedia.org/wikipedia/commons/f/f4/Building_construction_Moira_Close_Broadwater_Farm_Haringey_2025_13.webm` |
| **Autor** | **Acabashi** |
| **Licença** | **CC BY-SA 4.0** |
| SHA-256 da origem | `363c0dc47800d27a894a26bbbf570729d5e7c4a190f33fdd092a37aa546c6b46` |
| Origem: dimensões / duração / tamanho | 1920x1080, 393 s, 152,5 MB |
| Janela recortada | frames **3596 – 3806** (t ≈ 120,0 s a 127,0 s) |
| Resultado | 210 quadros, 1280x720, 29,97 fps, 7,0 s, ~27 MB |

### Atribuição

Este material é derivado de obra de **Acabashi**, publicada no Wikimedia
Commons sob **CC BY-SA 4.0**. O recorte e o redimensionamento produzidos por
`scripts/fetch_fixtures.py` são uma obra derivada; se algum dia for
redistribuída, precisa manter a atribuição e a mesma licença.

**Ela não é redistribuída por este repositório.** O arquivo nunca entra no git
(`.gitignore: tests/fixtures/*.mp4`, `tests/fixtures/_source/`); cada pessoa
baixa direto do Commons ao rodar o script. Por isso a fixture serve para
**medição interna**, e não para material de apresentação — para slides e para
as cenas da Sprint 3 usamos material próprio, gravado pela equipe.

### Por que este vídeo, e não outro

A escolha foi por medição, não por conveniência. Foram varridos, com o próprio
`models/vyra_ppe.pt`, quatro vídeos de domínio público de segurança do trabalho
(CDC/NIOSH) somando ~650 frames amostrados: **nenhum** produziu detecção de
`Hardhat` ou `Safety Vest` — são majoritariamente entrevista em ambiente
fechado, onde o modelo só devolve classes `NO-*`.

Este vídeo é canteiro de obra real, plano aberto, com pessoa de corpo inteiro.
A janela 3596–3806 foi escolhida porque é onde capacete e colete aparecem
**junto** com pessoa em quadro: em t ≈ 124,7 s do original há 2 pessoas, 2
capacetes e 2 coletes simultâneos.

Conteúdo medido na fixture final (amostragem a cada 15 quadros, `imgsz=640`,
`conf=0.35`):

| | |
|---|---|
| Pessoas por frame (YOLOv8n COCO) | 0 a 2 |
| `Safety Vest` (Vyra) | 28 detecções |
| `Hardhat` (Vyra) | 4 detecções |
| Frames com pessoa + colete + capacete | 120, 135, 150 |

### Por que o checksum é da origem, e não do `.mp4`

O `.mp4` é produzido pelo codec instalado na máquina de quem roda o script, e
o hash dele varia com a versão de OpenCV/FFmpeg. Validar o derivado geraria
falso alarme. O que precisa ser idêntico entre máquinas é o **material de
entrada** — esse é validado. O recorte é determinístico porque a janela está
fixada em número de **frame**, não em segundo: segundo depende de
arredondamento de FPS, frame não.

## Cenas da Sprint 3 — `tests/fixtures/cenas/`

Três **imagens estáticas** de canteiro, usadas pelos golden tests da camada
LLM. São imagens e não vídeo de propósito: as cenas precisam ser
determinísticas e inspecionáveis a olho, e um frame de vídeo escolhido por
índice muda de conteúdo se a fixture for regerada com outro codec.

Mesmo padrão da fixture de bench: **fora do git**, baixadas por
`scripts/fetch_fixtures.py`, SHA-256 validado na origem. Redimensionadas com o
lado maior em 1280 px **preservando a proporção** — esticar para um formato
fixo deformaria as pessoas, e pessoa deformada muda o que o modelo multimodal
vê.

### `segura.jpg` — 1280x866

| | |
|---|---|
| Origem | [Grand Canyon NP- Demolition of Maswik South Lodging Complex 1165](https://commons.wikimedia.org/wiki/File:Grand_Canyon_NP-_Demolition_of_Maswik_South_Lodging_Complex_1165_-_47990656061.jpg) |
| **Autor** | **Grand Canyon NPS** |
| **Licença** | **CC BY 2.0** |
| SHA-256 da origem | `35a4a05ccb5675867d33fcd28dab1a58d40ac8f3968b4bc974a604d38247ac76` |
| Origem | 4824x3264 |

Dois trabalhadores com capacete **e** colete de alta visibilidade, canteiro de
demolição com escavadeira. O YOLO detecta `Hardhat` 1 + `Safety Vest` 1.

### `risco.jpg` — 1280x854

| | |
|---|---|
| Origem | [Working on the approaches to the Pashad bridge across the Kunar River, Afghanistan](https://commons.wikimedia.org/wiki/File:Working_on_the_approaches_to_the_Pashad_bridge_across_the_Kunar_River,_Afghanistan.JPG) |
| **Autor** | **Brian Boisvert** |
| **Licença** | **Domínio público** |
| SHA-256 da origem | `cce11ecb351f7c98efe7454327c0461cda31cc2f11d8155d2ec05721bd525777` |
| Origem | 1600x1067 |

Obra de ponte com escavadeira e rolo compactador em operação. O COCO detecta
**9 pessoas**; nenhuma de capacete ou colete. O único `Hardhat` que o Vyra
devolve sai a `0,30` de confiança e é falso positivo.

### `ambigua.jpg` — 1280x914

| | |
|---|---|
| Origem | [US Navy 091022-N-2571C-042 Seabees use a long board to screed wet concrete](https://commons.wikimedia.org/wiki/File:US_Navy_091022-N-2571C-042_Seabees_use_a_long_board_to_screed_wet_concrete.jpg) |
| **Autor** | **U.S. Navy photo by Religious Program Specialist 2nd Class Kirk Cogswell** |
| **Licença** | **Domínio público** |
| SHA-256 da origem | `2a670226bf2664aad3d2034dd1c063ab43380fd41a4665aab7f2fd53f9162c8e` |
| Origem | 2100x1500 |

Três trabalhadores, **todos de capacete**, ninguém de colete, concretagem
dentro de área cercada.

Correção de uma medição anterior: eu havia registrado que o YOLO perdia o
capacete do primeiro plano. Isso foi medido na imagem original **esticada**
para 1280x720 com `imgsz=640`. Na resolução real desta cena (1280x914,
proporção preservada) e na config do pipeline (`imgsz=416`, `conf=0.35`), o
Vyra encontra **os três** capacetes — 0,59, 0,58 e 0,54. O redimensionamento
que preserva proporção ajudou.

A ambiguidade real da cena é outra, e é melhor: o YOLO acerta os capacetes e
marca `vest: missing` para as três pessoas. Colete é exigido nessa atividade,
dentro de área cercada, sem tráfego de veículo? É julgamento, não detecção — e
é exatamente onde uma camada de linguagem pode acrescentar ou estragar.

### Atribuição

`segura.jpg` deriva de obra de **Grand Canyon NPS** sob **CC BY 2.0** — exige
atribuição, mantida aqui e em `docs/SPRINT3.md`. As outras duas são domínio
público (obras do governo federal dos EUA); a atribuição ao autor é cortesia,
não obrigação.

Nenhuma das três é redistribuída por este repositório
(`.gitignore: tests/fixtures/cenas/`): cada pessoa baixa da origem ao rodar o
script.

## Adicionando uma fixture nova

Acrescente uma entrada em `FIXTURES` no `scripts/fetch_fixtures.py` e uma
seção aqui. Requisitos, sem exceção:

1. Licença **verificada na página do arquivo** na origem — não no resultado de
   busca, não em site agregador.
2. URL, autor, licença e SHA-256 registrados aqui.
3. Janela de corte em número de frame.
4. Entrada correspondente no `.gitignore`.
