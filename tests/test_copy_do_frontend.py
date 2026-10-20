"""Regra de copy do frontend (docs/NEXT2026/GLOSSARIO.md e MARCA.md): erro se escreve
"Não foi possível <verbo> <objeto>.", nunca "Falha ao <verbo>".

O frontend não tem suíte própria (package.json sem script de teste), então a
regra é vigiada daqui, lendo `frontend/src` como texto. Se este teste falhar,
reescreva a mensagem no formato do GLOSSARIO em vez de mudar o teste.
"""

from __future__ import annotations

from pathlib import Path

FONTE = Path(__file__).resolve().parent.parent / "frontend" / "src"


def test_frontend_nao_usa_falha_ao_nas_mensagens():
    arquivos = sorted(FONTE.rglob("*.ts")) + sorted(FONTE.rglob("*.tsx"))
    assert arquivos, f"nenhum arquivo .ts/.tsx em {FONTE}"
    achados = [
        f"{arq.relative_to(FONTE)}:{n}: {linha.strip()[:120]}"
        for arq in arquivos
        for n, linha in enumerate(arq.read_text(encoding="utf-8").splitlines(), start=1)
        if "Falha ao" in linha
    ]
    assert achados == [], "use \"Não foi possível <verbo> <objeto>.\" (GLOSSARIO.md):\n" + "\n".join(achados)
