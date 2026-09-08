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


def sha256(caminho: Path) -> str:
    digest = hashlib.sha256()
    with caminho.open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
            digest.update(bloco)
    return digest.hexdigest()


def baixar(fixture: Fixture) -> None:
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
        if faltando:
            print(f"FALTANDO: {', '.join(faltando)} — rode: python scripts/fetch_fixtures.py")
            return 1
        print(f"OK: {len(FIXTURES)} fixture(s) presente(s).")
        return 0

    for fixture in FIXTURES:
        print(f"\n[{fixture.nome}] {fixture.licenca}, {fixture.autor}")
        baixar(fixture)
        recortar(fixture)
    print("\nPronto. Detalhes de licenca e atribuicao em docs/FIXTURES.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
