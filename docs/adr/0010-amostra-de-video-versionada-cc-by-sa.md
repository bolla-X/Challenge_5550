# ADR 0010: Amostra de vídeo versionada sob CC BY-SA 4.0

- **Status:** aceito; integração feita em `app/demo.py` (confirmada em 23/10/2026), **sem teste dedicado** e sem prova de subida num clone sem as gravações
- **Data:** 23/10/2026

## Contexto

As gravações da demo não são versionadas: `scripts/fetch_fixtures.py` as baixa do Wikimedia Commons com checksum (licenças em
`docs/FIXTURES.md`). Um clone que ainda não rodou o script não conseguia subir `run.py --demo` ("gravações ausentes em tests/fixtures").
O critério F1.2 da spec pede uma amostra curta e leve no repositório, com webcam opcional.

## Decisão

- `amostras/canteiro_amostra.mp4`: 7 s, 640x360, 12 fps, H.264, sem áudio, cerca de 0,5 MB. Recorte (frames 3596 a 3806) da `bench.mp4`,
  que vem de "Building construction Moira Close Broadwater Farm Haringey 2025 13.webm", autor **Acabashi**, licença **CC BY-SA 4.0**.
  Atribuição, mudanças e o comando `ffmpeg` que a gerou estão em `amostras/LICENCA.md`.
- A amostra é **obra derivada, distribuída sob a mesma licença**. É a única gravação que o repositório redistribui.
- Só entra **no lugar** de uma gravação que não foi baixada: `fonte_da_gravacao(arquivo)` devolve a gravação de `tests/fixtures/` se existir;
  senão a amostra. `preparar_ambiente()` avisa no terminal quais câmeras tocam a amostra.
- O caminho oficial do README continua `scripts/preparar.py` (pesos com SHA-256, gravações, aprovação de runtimes), que precisa de
  internet uma vez.

## Consequências

- Os **pesos dos modelos continuam fora do repositório** (`.gitignore: *.pt`, exceto `models/visionepi_cppe_n416.pt`). A amostra resolve o
  vídeo, não a necessidade de baixar Vyra, yolov8n e yolo11n-pose. Portanto "roda sem internet num clone recém-feito" **não** é afirmado.
- Com uma amostra de 7 s em laço, todas as câmeras sem gravação completa mostram a mesma cena; os números de incidentes e alertas dessa
  condição não representam a demo completa.
- A licença CC BY-SA 4.0 vale para esse arquivo; este ADR não altera a licença do restante do repositório e não contém análise jurídica.
- Pendência: cobrir com teste (hoje não há teste dedicado da amostra) e provar a subida num clone sem as gravações. O Portal usa `portal.mp4` ou, sem ele, a
  câmera Canteiro; a amostra só substitui as três gravações do Canteiro, Pátio e Escada.

## Alternativas

- Versionar todas as gravações: **rejeitada** (tamanho e licenças variadas; ver `docs/FIXTURES.md`).
- Gerar vídeo sintético: **sem registro**; a regra do projeto é só imagem real de fonte licenciada (`docs/challenge/CONSOLIDADO.md` §8).
- Exigir sempre `fetch_fixtures.py`: **mantido como caminho oficial**; a amostra é só o plano B de subida.
