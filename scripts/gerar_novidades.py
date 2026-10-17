"""Gera `frontend/src/novidades.json` (a tela "Novidades" do app) a partir do CHANGELOG.

    python scripts/gerar_novidades.py           # grava o JSON (só se mudou)
    python scripts/gerar_novidades.py --check   # não grava; sai 1 se o JSON está desatualizado

Fonte: `docs/NEXT2026/CHANGELOG.md`. Só entram as seções `### Novidades: <título> (dd/mm/aaaa)`
que ficam dentro de `# MISSÃO 2` e `# MISSÃO 4`, e só os itens `- **Título.** Frase.`:
o CHANGELOG é técnico (números de medição, nomes de arquivo, decisões), e a tela é de
quem usa o sistema. Por isso a extração é por marcador, não por heurística de texto, e cada
item passa por uma checagem: backtick, nome de arquivo ou número seguido de unidade (ms, fps,
%, MB...) derrubam a geração com a linha apontada, em vez de irem para a tela.

Idempotente: não há carimbo de geração no JSON, e o arquivo só é regravado quando o conteúdo muda.
Rode de novo depois de editar o CHANGELOG e faça commit do JSON (ele é lido pelo build do Vite).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parent.parent
CHANGELOG = RAIZ / "docs" / "NEXT2026" / "CHANGELOG.md"
SAIDA = RAIZ / "frontend" / "src" / "novidades.json"
MISSOES = ("2", "4")

_MISSAO = re.compile(r"^# MISSÃO (\d+)\b")
_BLOCO = re.compile(r"^### Novidades: (?P<titulo>.+?) \((?P<dia>\d{2})/(?P<mes>\d{2})/(?P<ano>\d{4})\)\s*$")
_ITEM = re.compile(r"^- \*\*(?P<titulo>[^*]+?)\*\*\s+(?P<texto>\S.*)$")
_PROIBIDO = (
    (re.compile(r"`"), "código entre crases"),
    (re.compile(r"\.(py|tsx?|jsx?|md|json|css|html|ya?ml|toml|jsonl|pt|onnx|mp4)\b", re.IGNORECASE), "nome de arquivo"),
    (re.compile(r"\d\s?(ms|fps|%|×|MB|GB|KB|min/|p50|p95|p99)\b|\d\s?%"), "número de medição"),
    (re.compile(r"\bPR\d+\b|\bP0\.\d\b|\bADENDO\b"), "marcador interno"),
)


class ErroDeNovidade(ValueError):
    pass


def _conferir(linha: int, titulo: str, texto: str) -> None:
    for padrao, motivo in _PROIBIDO:
        achado = padrao.search(f"{titulo} {texto}")
        if achado:
            raise ErroDeNovidade(f"CHANGELOG.md:{linha}: {motivo} ({achado.group(0)!r}) não vai para a tela Novidades.")


def extrair(markdown: str) -> dict[str, Any]:
    """Lê o texto do CHANGELOG e devolve `{"missoes": [...]}` na ordem da mais nova para a mais velha."""
    missoes: list[dict[str, Any]] = []
    missao: str | None = None
    atual: dict[str, Any] | None = None
    em_comentario = False
    em_codigo = False
    for numero, bruta in enumerate(markdown.splitlines(), start=1):
        linha = bruta.rstrip()
        if linha.lstrip().startswith("```"):
            em_codigo = not em_codigo
            continue
        if em_codigo:  # "# comentário" de um bloco de código não é título
            continue
        if em_comentario:
            em_comentario = "-->" not in linha
            continue
        if linha.lstrip().startswith("<!--"):
            em_comentario = "-->" not in linha
            continue
        if linha.startswith("# "):
            achou = _MISSAO.match(linha)
            missao = achou.group(1) if achou and achou.group(1) in MISSOES else None
            atual = None
            continue
        if linha.startswith("#"):
            bloco = _BLOCO.match(linha) if missao else None
            atual = None
            if bloco:
                atual = {
                    "missao": f"Missão {missao}",
                    "titulo": bloco["titulo"].strip(),
                    "data": f"{bloco['ano']}-{bloco['mes']}-{bloco['dia']}",
                    "itens": [],
                }
                missoes.append(atual)
            continue
        if atual is None:
            continue
        item = _ITEM.match(linha)
        if item:
            titulo, texto = item["titulo"].strip().rstrip("."), item["texto"].strip()
            _conferir(numero, titulo, texto)
            atual["itens"].append({"titulo": titulo, "texto": texto})
    vazias = [m["titulo"] for m in missoes if not m["itens"]]
    if vazias:
        raise ErroDeNovidade(f"Seção de novidades sem itens: {', '.join(vazias)}.")
    # Mais recente primeiro; desempate pela ordem do número da missão (4 antes de 2).
    missoes.sort(key=lambda m: (m["data"], m["missao"]), reverse=True)
    return {"missoes": missoes}


def serializar(dados: dict[str, Any]) -> str:
    return json.dumps(dados, ensure_ascii=False, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="não grava; sai 1 se o JSON está desatualizado")
    parser.add_argument("--changelog", type=Path, default=CHANGELOG)
    parser.add_argument("--saida", type=Path, default=SAIDA)
    args = parser.parse_args(argv)

    try:
        texto = serializar(extrair(args.changelog.read_text(encoding="utf-8")))
    except ErroDeNovidade as erro:
        print(erro, file=sys.stderr)
        return 2
    atual = args.saida.read_text(encoding="utf-8") if args.saida.is_file() else None
    if atual == texto:
        print(f"{args.saida.name}: já está em dia.")
        return 0
    if args.check:
        print(f"{args.saida.name}: desatualizado. Rode python scripts/gerar_novidades.py.", file=sys.stderr)
        return 1
    args.saida.write_text(texto, encoding="utf-8", newline="\n")
    print(f"{args.saida.name}: gravado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
