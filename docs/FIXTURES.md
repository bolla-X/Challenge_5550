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

## Adicionando uma fixture nova

Acrescente uma entrada em `FIXTURES` no `scripts/fetch_fixtures.py` e uma
seção aqui. Requisitos, sem exceção:

1. Licença **verificada na página do arquivo** na origem — não no resultado de
   busca, não em site agregador.
2. URL, autor, licença e SHA-256 registrados aqui.
3. Janela de corte em número de frame.
4. Entrada correspondente no `.gitignore`.
