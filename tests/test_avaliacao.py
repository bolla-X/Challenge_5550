"""Especifica a avaliacao por PESSOA usada na Sprint 4.

A pergunta que o sistema responde em campo nao e "achei a caixa do capacete?"
(mAP), e sim "esta pessoa esta sem capacete?". Por isso a metrica e por pessoa:
o ground truth de cada pessoa anotada vira presente / ausente / nao_visivel por
EPI, a pessoa prevista e casada com a anotada por IoU, e so entao se conta
acerto e erro do ALERTA.
"""

from __future__ import annotations

import pytest
from app.vision.avaliacao import (
    AUSENTE,
    NAO_VISIVEL,
    PRESENTE,
    Matriz,
    casar_pessoas,
    contar,
    ground_truth_por_pessoa,
    ler_rotulos_yolo,
)
from app.vision.schemas import BoundingBox

# Classes do dataset Construction-PPE (Ultralytics), na ordem do data.yaml.
NOMES = ["helmet", "gloves", "vest", "boots", "goggles", "none", "Person", "no_helmet", "no_goggle", "no_gloves", "no_boots"]


def _linha(classe: int, x1, y1, x2, y2, w=1000, h=1000) -> str:
    cx, cy = (x1 + x2) / 2 / w, (y1 + y2) / 2 / h
    return f"{classe} {cx} {cy} {(x2 - x1) / w} {(y2 - y1) / h}"


def test_ler_rotulos_converte_yolo_normalizado_para_pixels(tmp_path):
    arquivo = tmp_path / "a.txt"
    arquivo.write_text(_linha(6, 100, 200, 300, 800) + "\n\n", encoding="utf-8")
    caixas = ler_rotulos_yolo(arquivo, NOMES, largura=1000, altura=1000)
    assert len(caixas) == 1
    nome, caixa = caixas[0]
    assert nome == "Person"
    assert (caixa.x1, caixa.y1, caixa.x2, caixa.y2) == (100, 200, 300, 800)


def test_ground_truth_distingue_presente_ausente_e_nao_visivel():
    pessoa = BoundingBox(100, 100, 300, 900)
    caixas = [
        ("Person", pessoa),
        ("helmet", BoundingBox(150, 100, 250, 160)),
        ("none", BoundingBox(120, 250, 280, 500)),  # "none" = torso sem colete
    ]
    gt = ground_truth_por_pessoa(caixas)
    assert len(gt) == 1
    status = gt[0].status
    assert status["helmet"] == PRESENTE
    assert status["vest"] == AUSENTE
    # Luva nao anotada nem como presente nem como ausente: nao da para julgar.
    assert status["gloves"] == NAO_VISIVEL


def test_uma_luva_sem_protecao_ja_e_ausencia():
    """Uma mao de luva e outra nua e violacao: a negativa vence."""
    pessoa = BoundingBox(0, 0, 200, 800)
    caixas = [
        ("Person", pessoa),
        ("gloves", BoundingBox(10, 400, 50, 450)),
        ("no_gloves", BoundingBox(150, 400, 190, 450)),
    ]
    assert ground_truth_por_pessoa(caixas)[0].status["gloves"] == AUSENTE


def test_epi_vai_para_a_pessoa_que_o_contem():
    esquerda = BoundingBox(0, 0, 200, 800)
    direita = BoundingBox(400, 0, 600, 800)
    caixas = [
        ("Person", esquerda),
        ("Person", direita),
        ("no_helmet", BoundingBox(450, 0, 550, 80)),
    ]
    gt = ground_truth_por_pessoa(caixas)
    por_x = sorted(gt, key=lambda p: p.caixa.x1)
    assert por_x[0].status["helmet"] == NAO_VISIVEL
    assert por_x[1].status["helmet"] == AUSENTE


def test_casar_pessoas_e_exclusivo_e_exige_iou_minimo():
    gt = [BoundingBox(0, 0, 100, 300), BoundingBox(500, 0, 600, 300)]
    previstas = [
        BoundingBox(5, 5, 105, 305),  # casa com gt[0]
        BoundingBox(2, 0, 98, 290),  # tambem sobrepoe gt[0], mas gt[0] ja foi
        BoundingBox(900, 0, 1000, 300),  # nao casa com ninguem
    ]
    pares = casar_pessoas(gt, previstas, iou_minimo=0.5)
    assert len(pares) == 1
    (i_gt, i_prev), = pares.items()
    assert i_gt == 0
    assert i_prev in (0, 1)


def test_matriz_calcula_precisao_revocacao_f1():
    m = Matriz(vp=8, fp=2, fn=4, vn=10)
    assert m.precisao == pytest.approx(0.8)
    assert m.revocacao == pytest.approx(8 / 12)
    assert m.f1 == pytest.approx(2 * 0.8 * (8 / 12) / (0.8 + 8 / 12))


def test_matriz_vazia_nao_divide_por_zero():
    m = Matriz()
    assert m.precisao is None
    assert m.revocacao is None
    assert m.f1 is None


def test_contar_trata_violacao_como_classe_positiva():
    """Positivo = pessoa SEM o EPI (e o que gera alerta)."""
    m = Matriz()
    contar(m, verdade=AUSENTE, alerta=True)  # vp
    contar(m, verdade=PRESENTE, alerta=True)  # fp: alerta sobre quem esta de EPI
    contar(m, verdade=AUSENTE, alerta=False)  # fn: violacao perdida
    contar(m, verdade=PRESENTE, alerta=False)  # vn
    contar(m, verdade=NAO_VISIVEL, alerta=True)  # nao entra: nao ha verdade
    assert (m.vp, m.fp, m.fn, m.vn) == (1, 1, 1, 1)
    assert m.sem_verdade_com_alerta == 1


def test_verdade_por_imagem():
    from app.vision.avaliacao import verdade_por_imagem

    assert verdade_por_imagem([{"helmet": PRESENTE}, {"helmet": AUSENTE}], "helmet") == AUSENTE
    assert verdade_por_imagem([{"helmet": PRESENTE}, {"helmet": NAO_VISIVEL}], "helmet") == PRESENTE
    assert verdade_por_imagem([{"helmet": NAO_VISIVEL}], "helmet") == NAO_VISIVEL
    assert verdade_por_imagem([], "helmet") == NAO_VISIVEL


def test_llm_so_desempata_onde_o_yolo_nao_verificou():
    from app.vision.avaliacao import alerta_combinado

    regra = "yolo_ou_llm_nos_nao_verificados"
    # YOLO viu o EPI em todos: o LLM dizendo "ausente" NAO cria alerta.
    assert alerta_combinado(["ok", "ok"], {"helmet"}, "helmet", regra=regra) is False
    # YOLO viu a negativa: alerta, diga o LLM o que disser.
    assert alerta_combinado(["missing"], set(), "helmet", regra=regra) is True
    # So "nao verificado": o LLM decide.
    assert alerta_combinado(["unverified", "ok"], {"helmet"}, "helmet", regra=regra) is True
    assert alerta_combinado(["unverified"], {"vest"}, "helmet", regra=regra) is False
    # LLM fora do ar (None) nunca vira alerta.
    assert alerta_combinado(["unverified"], None, "helmet", regra=regra) is False
