"""Laboratório "celular em área de risco" (M9): regra pura com detecções sintéticas, desligada por padrão."""

from __future__ import annotations

import pytest
from app.config import Config
from app.services.lab_celular import (
    LIMIAR_PADRAO,
    REGRA,
    avaliar_celular,
    e_celular,
)
from app.vision.schemas import BoundingBox, Detection

QUADRO = (480, 640, 3)  # altura, largura, canais
AREA_DIREITA = [(0.5, 0.0), (1.0, 0.0), (1.0, 1.0), (0.5, 1.0)]  # metade direita do quadro


def _pessoa(x1, y1, x2, y2, track_id=3) -> Detection:
    return Detection(label="person", category="person", confidence=0.9, box=BoundingBox(x1, y1, x2, y2), class_id=0, track_id=track_id)


def _celular(x1, y1, x2, y2, confianca=0.8) -> Detection:
    return Detection(label="cell phone", category="cell phone", confidence=confianca, box=BoundingBox(x1, y1, x2, y2), class_id=67)


# Pessoa e celular dentro da metade direita (centro do celular em x = 500 → 0,78 do quadro).
PESSOA = _pessoa(400, 100, 600, 460)
CELULAR_NA_AREA = _celular(480, 200, 520, 260)


def _avaliar(deteccoes, *, ativo=True, limiar=LIMIAR_PADRAO, poligono=AREA_DIREITA, quadro=QUADRO):
    return avaliar_celular(deteccoes, ativo=ativo, limiar=limiar, poligono=poligono, forma_do_quadro=quadro)


def test_desligado_nao_muda_nada_nem_com_celular_perfeito():
    assert _avaliar([PESSOA, CELULAR_NA_AREA], ativo=False) == []


def test_desligado_por_padrao_na_configuracao():
    assert Config.LAB_CELULAR_ATIVO is False, "o laboratório só liga por LAB_CELULAR_ATIVO=true"
    assert Config.LAB_CELULAR_CONF_MIN == LIMIAR_PADRAO


def test_ligado_celular_na_area_com_pessoa_vira_alerta_medio():
    (alerta,) = _avaliar([PESSOA, CELULAR_NA_AREA])
    assert alerta.rule == REGRA == "celular_em_area"
    assert alerta.severity == "medium"
    assert alerta.message == "Celular em uso na área de risco · Pessoa 3"
    assert alerta.feature == "celular"
    assert alerta.key == "celular_em_area:celular:person_3"
    assert alerta.metadata["person_label"] == "Pessoa 3" and alerta.metadata["laboratorio"] is True
    assert alerta.metadata["celular_confianca"] == 0.8
    assert alerta.metadata["point"] == {"x": 0.7812, "y": 0.4792}


def test_confianca_abaixo_do_limiar_nao_alerta_e_igual_ao_limiar_alerta():
    assert _avaliar([PESSOA, _celular(480, 200, 520, 260, confianca=0.49)]) == []
    assert len(_avaliar([PESSOA, _celular(480, 200, 520, 260, confianca=0.5)])) == 1
    assert len(_avaliar([PESSOA, _celular(480, 200, 520, 260, confianca=0.3)], limiar=0.25)) == 1


def test_celular_fora_da_area_de_risco_nao_alerta():
    na_esquerda = _celular(100, 200, 140, 260)  # centro x = 120 → 0,19 do quadro
    pessoa_larga = _pessoa(50, 100, 600, 460)  # contém o celular, mas a área de risco é só a metade direita
    assert _avaliar([pessoa_larga, na_esquerda]) == []


def test_celular_sem_pessoa_por_perto_nao_alerta():
    assert _avaliar([CELULAR_NA_AREA]) == []
    assert _avaliar([_pessoa(10, 10, 100, 100), CELULAR_NA_AREA]) == [], "pessoa longe do celular"


def test_pessoa_sem_celular_nao_alerta():
    assert _avaliar([PESSOA]) == []


def test_sem_area_de_risco_ou_sem_quadro_nao_avalia():
    assert _avaliar([PESSOA, CELULAR_NA_AREA], poligono=None) == []
    assert _avaliar([PESSOA, CELULAR_NA_AREA], poligono=[]) == []
    assert _avaliar([PESSOA, CELULAR_NA_AREA], quadro=None) == []


def test_celular_entre_duas_pessoas_aninhadas_fica_com_a_de_menor_caixa():
    grande = _pessoa(380, 50, 620, 470, track_id=1)
    pequena = _pessoa(450, 150, 560, 400, track_id=2)
    (alerta,) = _avaliar([grande, pequena, CELULAR_NA_AREA])
    assert alerta.message.endswith("Pessoa 2")


def test_duas_pessoas_com_celular_geram_dois_alertas_um_por_pessoa():
    a = _pessoa(330, 100, 440, 460, track_id=5)
    b = _pessoa(500, 100, 620, 460, track_id=6)
    alertas = _avaliar([a, b, _celular(360, 200, 400, 250), _celular(540, 200, 580, 250)])
    assert sorted(x.message.rsplit(" · ", 1)[1] for x in alertas) == ["Pessoa 5", "Pessoa 6"]
    assert len({x.key for x in alertas}) == 2


def test_varios_celulares_na_mesma_pessoa_contam_uma_vez_com_a_maior_confianca():
    alertas = _avaliar([PESSOA, _celular(450, 150, 480, 190, 0.6), _celular(480, 200, 520, 260, 0.9)])
    assert len(alertas) == 1 and alertas[0].metadata["celular_confianca"] == 0.9


def test_pessoa_sem_track_usa_o_indice_no_rotulo():
    sem_track = _pessoa(400, 100, 600, 460, track_id=None)
    (alerta,) = _avaliar([sem_track, CELULAR_NA_AREA])
    assert alerta.message == "Celular em uso na área de risco · Pessoa 0"
    assert alerta.metadata["person_id"] == "person_0"


def test_so_o_rotulo_cell_phone_conta_como_celular():
    capacete_com_id_67 = Detection(label="helmet", category="ppe", confidence=0.9, class_id=67, box=BoundingBox(480, 200, 520, 260))
    assert not e_celular(capacete_com_id_67)
    assert e_celular(CELULAR_NA_AREA)
    assert _avaliar([PESSOA, capacete_com_id_67]) == []


@pytest.mark.parametrize("quadro", [(480, 640), (480, 640, 3), (1080, 1920, 3)])
def test_forma_do_quadro_com_ou_sem_canais(quadro):
    altura, largura = quadro[:2]
    pessoa = _pessoa(int(largura * 0.6), int(altura * 0.2), int(largura * 0.95), int(altura * 0.95))
    celular = _celular(int(largura * 0.75), int(altura * 0.4), int(largura * 0.8), int(altura * 0.5))
    assert len(_avaliar([pessoa, celular], quadro=quadro)) == 1
