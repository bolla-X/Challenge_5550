"""Baixa e prepara as fixtures de vídeo usadas pelo bench e pelos testes.

Fixture de vídeo NÃO é versionada — mesmo motivo dos pesos `.pt`: o repositório
é público, o arquivo é grande, e git com binário grande é ruim de todo jeito.
Cada pessoa reproduz com um comando:

    python scripts/fetch_fixtures.py

O que este script garante, e por que cada garantia existe:

- **SHA-256 da ORIGEM, não do derivado.** O `.mp4` recortado é produzido pelo
  codec instalado na máquina de quem roda, então o hash dele varia por versão
  de OpenCV/FFmpeg. Validar o derivado daria falso alarme. O que precisa ser
  idêntico entre máquinas é o material de entrada — esse sim é checado.
- **Janela de corte fixa em número de FRAME, não em segundo.** Segundo depende
  de arredondamento de FPS; frame não. Duas máquinas recortam exatamente os
  mesmos quadros, que é o que torna o benchmark comparável.
- **Download idempotente.** Se a origem já está no disco com o hash certo, não
  baixa de novo. 152 MB não se baixa duas vezes por distração.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import cv2

RAIZ = Path(__file__).resolve().parent.parent
DIR_FIXTURES = RAIZ / "tests" / "fixtures"
DIR_ORIGEM = DIR_FIXTURES / "_source"
DIR_CENAS = DIR_FIXTURES / "cenas"

# O Wikimedia recusa o User-Agent padrao do urllib com HTTP 403. A politica
# deles exige identificacao: https://meta.wikimedia.org/wiki/User-Agent_policy
USER_AGENT = "VisionEPI-fixtures/1.0 (FIAP Challenge 2026; +https://github.com/bolla-X/Challenge_5550)"


@dataclass(frozen=True)
class Fixture:
    """Uma fixture derivada de um arquivo de origem publico."""

    nome: str
    destino: str
    url: str
    sha256_origem: str
    frame_inicial: int
    frame_final: int
    largura: int
    altura: int
    licenca: str
    autor: str
    pagina: str
    por_que: str

    @property
    def arquivo_origem(self) -> Path:
        return DIR_ORIGEM / self.url.rsplit("/", 1)[-1]

    @property
    def arquivo_destino(self) -> Path:
        return DIR_FIXTURES / self.destino


FIXTURES: tuple[Fixture, ...] = (
    Fixture(
        nome="bench",
        destino="bench.mp4",
        url="https://upload.wikimedia.org/wikipedia/commons/f/f4/Building_construction_Moira_Close_Broadwater_Farm_Haringey_2025_13.webm",
        sha256_origem="363c0dc47800d27a894a26bbbf570729d5e7c4a190f33fdd092a37aa546c6b46",
        # t = 120,0 s a 127,0 s do original (29,97 fps). Escolhida por medicao, nao
        # por acaso: e a janela onde o Vyra detecta capacete E colete ao mesmo tempo
        # em que ha pessoa de corpo inteiro em quadro — em t=124,7 s sao 2 pessoas,
        # 2 capacetes e 2 coletes simultaneos.
        frame_inicial=3596,
        frame_final=3806,
        largura=1280,
        altura=720,
        licenca="CC BY-SA 4.0",
        autor="Acabashi",
        pagina="https://commons.wikimedia.org/wiki/File:Building_construction_Moira_Close_Broadwater_Farm_Haringey_2025_13.webm",
        por_que="Canteiro de obra real, capacete e colete visiveis, pessoa de corpo inteiro.",
    ),
)


@dataclass(frozen=True)
class Cena:
    """Imagem estatica de canteiro, usada pelos golden tests da camada LLM.

    Sao IMAGENS, nao video: as tres cenas da Sprint 3 precisam ser
    deterministicas e inspecionaveis a olho, e um frame de video escolhido por
    indice muda de conteudo se a fixture for regerada com outro codec.
    """

    nome: str
    destino: str
    url: str
    sha256_origem: str
    lado_maior: int
    licenca: str
    autor: str
    pagina: str
    por_que: str

    @property
    def arquivo_origem(self) -> Path:
        return DIR_ORIGEM / self.url.rsplit("/", 1)[-1].replace("%2C", ",")

    @property
    def arquivo_destino(self) -> Path:
        return DIR_CENAS / self.destino


CENAS: tuple[Cena, ...] = (
    Cena(
        nome="segura",
        destino="segura.jpg",
        url="https://upload.wikimedia.org/wikipedia/commons/0/01/Grand_Canyon_NP-_Demolition_of_Maswik_South_Lodging_Complex_1165_-_47990656061.jpg",
        sha256_origem="35a4a05ccb5675867d33fcd28dab1a58d40ac8f3968b4bc974a604d38247ac76",
        lado_maior=1280,
        licenca="CC BY 2.0",
        autor="Grand Canyon NPS",
        pagina="https://commons.wikimedia.org/wiki/File:Grand_Canyon_NP-_Demolition_of_Maswik_South_Lodging_Complex_1165_-_47990656061.jpg",
        por_que="Dois trabalhadores com capacete E colete de alta visibilidade, canteiro de demolicao.",
    ),
    Cena(
        nome="risco",
        destino="risco.jpg",
        url="https://upload.wikimedia.org/wikipedia/commons/0/01/Working_on_the_approaches_to_the_Pashad_bridge_across_the_Kunar_River%2C_Afghanistan.JPG",
        sha256_origem="cce11ecb351f7c98efe7454327c0461cda31cc2f11d8155d2ec05721bd525777",
        lado_maior=1280,
        licenca="Public domain",
        autor="Brian Boisvert",
        pagina="https://commons.wikimedia.org/wiki/File:Working_on_the_approaches_to_the_Pashad_bridge_across_the_Kunar_River,_Afghanistan.JPG",
        por_que="Obra de ponte com escavadeira e rolo compactador; ~9 pessoas, nenhuma de capacete ou colete.",
    ),
    Cena(
        nome="ambigua",
        destino="ambigua.jpg",
        url="https://upload.wikimedia.org/wikipedia/commons/2/22/US_Navy_091022-N-2571C-042_Seabees_use_a_long_board_to_screed_wet_concrete.jpg",
        sha256_origem="2a670226bf2664aad3d2034dd1c063ab43380fd41a4665aab7f2fd53f9162c8e",
        lado_maior=1280,
        licenca="Public domain",
        autor="U.S. Navy photo by Religious Program Specialist 2nd Class Kirk Cogswell",
        pagina="https://commons.wikimedia.org/wiki/File:US_Navy_091022-N-2571C-042_Seabees_use_a_long_board_to_screed_wet_concrete.jpg",
        por_que=(
            "Tres trabalhadores, TODOS de capacete — mas o YOLO perde justamente o do primeiro "
            "plano, cortado na borda, e ninguem usa colete. E a cena onde YOLO e LLM tem mais "
            "chance de discordar."
        ),
    ),
)


def sha256(caminho: Path) -> str:
    digest = hashlib.sha256()
    with caminho.open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
            digest.update(bloco)
    return digest.hexdigest()


def baixar(fixture: Fixture | Cena) -> None:
    origem = fixture.arquivo_origem
    if origem.exists():
        atual = sha256(origem)
        if atual == fixture.sha256_origem:
            print(f"  origem ja presente e integra: {origem.name}")
            return
        print(f"  origem presente mas com hash diferente ({atual[:12]}...), rebaixando")

    DIR_ORIGEM.mkdir(parents=True, exist_ok=True)
    print(f"  baixando {fixture.url}")
    requisicao = urllib.request.Request(fixture.url, headers={"User-Agent": USER_AGENT})
    parcial = origem.with_suffix(origem.suffix + ".parcial")
    with urllib.request.urlopen(requisicao, timeout=120) as resposta, parcial.open("wb") as saida:
        total = int(resposta.headers.get("Content-Length") or 0)
        lidos = 0
        while bloco := resposta.read(1024 * 256):
            saida.write(bloco)
            lidos += len(bloco)
            if total:
                print(f"\r  {lidos / 1e6:6.1f} / {total / 1e6:.1f} MB", end="", flush=True)
    print()

    obtido = sha256(parcial)
    if obtido != fixture.sha256_origem:
        parcial.unlink(missing_ok=True)
        raise SystemExit(
            f"SHA-256 nao confere para {fixture.nome}.\n"
            f"  esperado: {fixture.sha256_origem}\n"
            f"  obtido:   {obtido}\n"
            "O arquivo na origem pode ter sido substituido. Nao vou usar um arquivo\n"
            "que nao e o que esta documentado em docs/FIXTURES.md."
        )
    parcial.replace(origem)
    print(f"  SHA-256 confere: {obtido[:16]}...")


def recortar(fixture: Fixture) -> None:
    origem, destino = fixture.arquivo_origem, fixture.arquivo_destino
    captura = cv2.VideoCapture(str(origem))
    if not captura.isOpened():
        raise SystemExit(f"OpenCV nao conseguiu abrir {origem}. Instalacao de codec incompleta?")

    fps = captura.get(cv2.CAP_PROP_FPS)
    destino.parent.mkdir(parents=True, exist_ok=True)
    escritor = cv2.VideoWriter(
        str(destino), cv2.VideoWriter_fourcc(*"mp4v"), fps, (fixture.largura, fixture.altura)
    )
    if not escritor.isOpened():
        captura.release()
        raise SystemExit(f"OpenCV nao conseguiu escrever {destino} com o codec mp4v.")

    captura.set(cv2.CAP_PROP_POS_FRAMES, fixture.frame_inicial)
    escritos = 0
    for _ in range(fixture.frame_final - fixture.frame_inicial):
        ok, quadro = captura.read()
        if not ok:
            break
        escritor.write(cv2.resize(quadro, (fixture.largura, fixture.altura)))
        escritos += 1
    captura.release()
    escritor.release()

    esperados = fixture.frame_final - fixture.frame_inicial
    if escritos != esperados:
        raise SystemExit(f"Esperava {esperados} quadros, escrevi {escritos}. Fixture incompleta.")
    print(
        f"  {destino.relative_to(RAIZ)}: {escritos} quadros, "
        f"{fixture.largura}x{fixture.altura}, {fps:.2f} fps, {escritos / fps:.1f}s, "
        f"{destino.stat().st_size / 1e6:.1f} MB"
    )


def preparar_cena(cena: Cena) -> None:
    """Reduz o lado maior para `lado_maior`, PRESERVANDO a proporcao.

    Esticar para um formato fixo deformaria a cena — e pessoa deformada muda o
    que o modelo multimodal ve. O objetivo aqui e limitar custo de token e
    aproximar a resolucao de uma camera, nao bater um formato exato.
    """
    imagem = cv2.imread(str(cena.arquivo_origem))
    if imagem is None:
        raise SystemExit(f"OpenCV nao conseguiu abrir {cena.arquivo_origem}")
    altura, largura = imagem.shape[:2]
    escala = cena.lado_maior / max(altura, largura)
    if escala < 1:
        nova = (int(round(largura * escala)), int(round(altura * escala)))
        imagem = cv2.resize(imagem, nova, interpolation=cv2.INTER_AREA)
    cena.arquivo_destino.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(cena.arquivo_destino), imagem, [int(cv2.IMWRITE_JPEG_QUALITY), 92]):
        raise SystemExit(f"Nao consegui gravar {cena.arquivo_destino}")
    print(
        f"  {cena.arquivo_destino.relative_to(RAIZ)}: {imagem.shape[1]}x{imagem.shape[0]}, "
        f"{cena.arquivo_destino.stat().st_size / 1e3:.0f} kB"
    )


def caminho_da_cena(nome: str) -> Path:
    """Caminho da cena, ou erro dizendo como obte-la."""
    cena = next((item for item in CENAS if item.nome == nome), None)
    if cena is None:
        raise KeyError(f"Cena desconhecida: {nome}. Conhecidas: {[c.nome for c in CENAS]}")
    if not cena.arquivo_destino.exists():
        raise FileNotFoundError(
            f"Cena '{nome}' ausente em {cena.arquivo_destino.relative_to(RAIZ)}. "
            "Ela nao e versionada (repositorio publico). Gere com: "
            "python scripts/fetch_fixtures.py — origem, licenca e checksum em docs/FIXTURES.md."
        )
    return cena.arquivo_destino


def caminho_da_fixture(nome: str) -> Path:
    """Devolve o caminho da fixture, ou levanta erro dizendo como obte-la.

    Usada pelo bench e pelos testes. A mensagem existe para que quem clonar o
    repositorio e rodar o bench descubra o que fazer pela propria mensagem de
    erro, sem precisar ler documentacao.
    """
    fixture = next((f for f in FIXTURES if f.nome == nome), None)
    if fixture is None:
        raise KeyError(f"Fixture desconhecida: {nome}. Conhecidas: {[f.nome for f in FIXTURES]}")
    if not fixture.arquivo_destino.exists():
        raise FileNotFoundError(
            f"Fixture '{nome}' ausente em {fixture.arquivo_destino.relative_to(RAIZ)}.\n"
            "Ela nao e versionada (repositorio publico, arquivo grande). Gere com:\n"
            "    python scripts/fetch_fixtures.py\n"
            "Origem, licenca e checksum estao em docs/FIXTURES.md."
        )
    return fixture.arquivo_destino


def main() -> int:
    analisador = argparse.ArgumentParser(description="Baixa e prepara as fixtures de video.")
    analisador.add_argument(
        "--check", action="store_true", help="So verifica se as fixtures existem; nao baixa nada."
    )
    argumentos = analisador.parse_args()

    if argumentos.check:
        faltando = [f.nome for f in FIXTURES if not f.arquivo_destino.exists()]
        faltando += [f"cena:{c.nome}" for c in CENAS if not c.arquivo_destino.exists()]
        if faltando:
            print(f"FALTANDO: {', '.join(faltando)} — rode: python scripts/fetch_fixtures.py")
            return 1
        print(f"OK: {len(FIXTURES)} fixture(s) e {len(CENAS)} cena(s) presente(s).")
        return 0

    for fixture in FIXTURES:
        print(f"\n[{fixture.nome}] {fixture.licenca}, {fixture.autor}")
        baixar(fixture)
        recortar(fixture)
    for cena in CENAS:
        print(f"\n[cena:{cena.nome}] {cena.licenca}, {cena.autor}")
        baixar(cena)
        preparar_cena(cena)
    print("\nPronto. Detalhes de licenca e atribuicao em docs/FIXTURES.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
