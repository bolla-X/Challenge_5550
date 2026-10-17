"""M1 (MISSÃO 4): saúde visual da câmera — obstrução, escuridão, ofuscamento, desfoque e câmera movida.

Os quadros vêm das fixtures REAIS (bench, multidão, portal); as sabotagens são
derivadas deles (tampar, escurecer, estourar, borrar, girar o suporte). Sem a
fixture em disco o teste é pulado (`python scripts/fetch_fixtures.py`).

Duas regras de leitura:
- `bruto` é o que UMA medição concluiu; `estado()` é o confirmado, com histerese;
- a histerese é testada sem imagem (`Histerese` com o relógio na mão) e, uma vez,
  de ponta a ponta com quadros reais e relógio falso.
"""

from __future__ import annotations

import json

import cv2
import numpy as np
import pytest
from app.services.risk_rules import RuleAlert
from app.vision.saude_visual import Histerese, MonitorDeSaudeVisual
from scripts.fetch_fixtures import caminho_da_fixture

FIXTURES = ("bench", "multidao", "portal")
QUADROS_POR_FIXTURE = 30

# Gama que escurece cada cena sem deixá-la lisa (um quadro PRETO é obstruído, não escuro).
GAMA_ESCURA = {"bench": 6.0, "multidao": 3.0, "portal": 8.0}

_CACHE: dict[str, list[np.ndarray]] = {}


def _quadros_espacados(nome: str, quantos: int = QUADROS_POR_FIXTURE) -> list[np.ndarray]:
    """`quantos` quadros igualmente espaçados ao longo do vídeo inteiro."""
    if nome not in _CACHE:
        try:
            caminho = caminho_da_fixture(nome)
        except FileNotFoundError as erro:
            pytest.skip(str(erro).splitlines()[0])
        captura = cv2.VideoCapture(str(caminho))
        todos = []
        while True:
            ok, quadro = captura.read()
            if not ok:
                break
            todos.append(quadro)
        captura.release()
        indices = np.linspace(0, len(todos) - 1, quantos).astype(int)
        _CACHE[nome] = [todos[i] for i in indices]
    return _CACHE[nome]


@pytest.fixture(params=FIXTURES)
def cena(request) -> tuple[str, list[np.ndarray]]:
    return request.param, _quadros_espacados(request.param)


# ---------------------------------------------------------------- sabotagens derivadas do quadro


def _tampado(quadro: np.ndarray, bgr: tuple[int, int, int], ruido: float = 2.5) -> np.ndarray:
    """Cor chapada com ruído de sensor baixo: mão/fita (escuro) ou papel (claro) na frente da lente."""
    gerador = np.random.default_rng(0)
    base = np.full(quadro.shape, bgr, np.float32) + gerador.normal(0, ruido, quadro.shape)
    return np.clip(base, 0, 255).astype(np.uint8)


def _escurecido(quadro: np.ndarray, gama: float) -> np.ndarray:
    return (255 * (quadro / 255.0) ** gama).astype(np.uint8)


def _ofuscado(quadro: np.ndarray) -> np.ndarray:
    """Exposição estourada: ganho alto + pedestal. A cena ainda existe, só que quase toda branca."""
    return np.clip(quadro.astype(np.float32) * 3 + 80, 0, 255).astype(np.uint8)


def _desfocado(quadro: np.ndarray) -> np.ndarray:
    return cv2.GaussianBlur(quadro, (0, 0), 8)


def _movido(quadro: np.ndarray, dx: float, dy: float, graus: float) -> np.ndarray:
    """O suporte girou/deslizou: a cena inteira muda de lugar (dx, dy em fração do quadro)."""
    altura, largura = quadro.shape[:2]
    matriz = cv2.getRotationMatrix2D((largura / 2, altura / 2), graus, 1.0)
    matriz[0, 2] += dx * largura
    matriz[1, 2] += dy * altura
    return cv2.warpAffine(quadro, matriz, (largura, altura), borderMode=cv2.BORDER_REFLECT)


def _monitor(referencia: np.ndarray, **kwargs) -> MonitorDeSaudeVisual:
    monitor = MonitorDeSaudeVisual(**kwargs)
    monitor.definir_referencia(referencia)
    return monitor


# ---------------------------------------------------------------- classificação de uma medição


@pytest.mark.parametrize(
    "bgr", [(10, 10, 10), (25, 40, 60), (238, 240, 240)], ids=["preto", "marrom-fita", "branco-papel"]
)
def test_lente_tampada_e_obstruida_seja_escura_ou_clara(cena, bgr):
    nome, quadros = cena
    monitor = _monitor(quadros[0])
    medicao = monitor.observar(_tampado(quadros[len(quadros) // 2], bgr), agora=0.0)
    assert medicao["bruto"] == "obstruida", (nome, medicao["metricas"])
    assert medicao["metricas"]["desvio"] < 6.0


def test_escura(cena):
    nome, quadros = cena
    monitor = _monitor(quadros[0])
    medicao = monitor.observar(_escurecido(quadros[len(quadros) // 2], GAMA_ESCURA[nome]), agora=0.0)
    assert medicao["bruto"] == "escura", (nome, medicao["metricas"])


def test_ofuscada(cena):
    nome, quadros = cena
    monitor = _monitor(quadros[0])
    medicao = monitor.observar(_ofuscado(quadros[len(quadros) // 2]), agora=0.0)
    assert medicao["bruto"] == "ofuscada", (nome, medicao["metricas"])


def test_desfocada_e_relativa_a_referencia(cena):
    nome, quadros = cena
    monitor = _monitor(quadros[0])
    medicao = monitor.observar(_desfocado(quadros[len(quadros) // 2]), agora=0.0)
    assert medicao["bruto"] == "desfocada", (nome, medicao["metricas"])
    assert medicao["metricas"]["nitidez_relativa"] < 0.35
    # a MESMA nitidez, sem referência mais nítida para comparar, não é desfoque
    sem_referencia = MonitorDeSaudeVisual()
    assert sem_referencia.observar(_desfocado(quadros[0]), agora=0.0)["bruto"] == "ok"


@pytest.mark.parametrize(
    ("dx", "dy", "graus"),
    [(0.15, 0.0, 0.0), (0.0, 0.2, 0.0), (0.25, 0.1, 5.0), (-0.2, 0.05, -6.0), (0.0, 0.0, 6.0)],
    ids=["x15", "y20", "x25-y10-rot5", "x-20-rot-6", "so-rotacao-6"],
)
def test_camera_movida(cena, dx, dy, graus):
    """Câmera mexida logo depois de definida a referência: translação de 15–25 % e/ou rotação."""
    nome, quadros = cena
    monitor = _monitor(quadros[0])
    medicao = monitor.observar(_movido(quadros[0], dx, dy, graus), agora=0.0)
    assert medicao["bruto"] == "movida", (nome, medicao["metricas"])
    assert medicao["metricas"]["inliers"] >= 8


def test_movida_tem_prioridade_sobre_obstruida_so_quando_ha_cena_para_comparar(cena):
    """Quadro preto contra referência rica: obstruída (prioridade máxima), não movida."""
    nome, quadros = cena
    monitor = _monitor(quadros[0])
    medicao = monitor.observar(_tampado(quadros[0], (10, 10, 10)), agora=0.0)
    assert medicao["bruto"] == "obstruida"


def test_prioridade_obstruida_movida_escura_ofuscada_desfocada(cena):
    _, quadros = cena
    monitor = _monitor(quadros[0])
    classificar = monitor._classificar
    assert classificar("obstruida", True, 0.01) == "obstruida"
    assert classificar("escura", True, 0.01) == "movida"
    assert classificar("ofuscada", True, 0.01) == "movida"
    assert classificar("escura", False, 0.01) == "escura"
    assert classificar("ofuscada", False, 0.01) == "ofuscada"
    # desfoque só entra numa imagem sem outro problema
    assert classificar("ok", True, 0.01) == "movida"
    assert classificar("ok", False, 0.01) == "desfocada"
    assert classificar("ok", False, 0.9) == "ok"


# ---------------------------------------------------------------- pessoas andando NÃO são sabotagem


def test_zero_falso_positivo_em_30_quadros_espacados(cena):
    """30 quadros consecutivos do MESMO vídeo (pessoas se mexendo), referência adotada sozinha no primeiro."""
    nome, quadros = cena
    monitor = MonitorDeSaudeVisual()
    for segundo, quadro in enumerate(quadros):
        medicao = monitor.observar(quadro, agora=float(segundo))
        assert medicao is not None
        assert medicao["bruto"] == "ok", (nome, segundo, medicao["metricas"])
        assert monitor.estado()["estado"] == "ok"
        assert monitor.alertas() == []


def test_pessoas_andando_nao_disparam_movida_com_qualquer_referencia(cena):
    """Cada quadro do vídeo faz de referência em vez do primeiro: a estabilidade não depende de um bom momento."""
    nome, quadros = cena
    for indice_da_referencia in range(0, len(quadros), 3):
        monitor = _monitor(quadros[indice_da_referencia])
        for segundo, quadro in enumerate(quadros):
            medicao = monitor.observar(quadro, agora=float(segundo))
            assert medicao["bruto"] == "ok", (nome, indice_da_referencia, segundo, medicao["metricas"])


def test_quadro_identico_a_referencia_nao_pede_orb(cena):
    """Miniaturas quase idênticas: a câmera não se mexeu e não se gasta ORB (deslocamento fica 0, conclusivo)."""
    _, quadros = cena
    monitor = _monitor(quadros[0])
    medicao = monitor.observar(quadros[0], agora=0.0)
    assert medicao["metricas"]["correlacao"] > 0.99
    assert medicao["metricas"]["conclusivo"] == 1.0
    assert medicao["metricas"]["inliers"] == 0


# ---------------------------------------------------------------- referência


def test_primeira_observacao_sem_referencia_adota_o_quadro(cena):
    _, quadros = cena
    monitor = MonitorDeSaudeVisual()
    assert not monitor.tem_referencia
    assert monitor.estado()["tem_referencia"] is False

    medicao = monitor.observar(quadros[0], agora=0.0)
    assert medicao["referencia_automatica"] is True
    assert medicao["bruto"] == "ok"
    assert monitor.tem_referencia
    estado = monitor.estado()
    assert estado["tem_referencia"] is True and estado["referencia_automatica"] is True

    # a segunda medição já compara, e não anuncia nova adoção
    assert monitor.observar(quadros[1], agora=1.0)["referencia_automatica"] is False

    monitor.definir_referencia(quadros[0])
    assert monitor.estado()["referencia_automatica"] is False


def test_camera_que_sobe_tampada_nao_deixa_a_cena_de_verdade_virar_movida(cena):
    """A referência adotada sozinha num quadro obstruído é provisória: vale até o primeiro quadro bom."""
    _, quadros = cena
    monitor = MonitorDeSaudeVisual()
    assert monitor.observar(_tampado(quadros[0], (10, 10, 10)), agora=0.0)["bruto"] == "obstruida"
    for segundo, quadro in enumerate(quadros[:8], start=1):
        medicao = monitor.observar(quadro, agora=float(segundo))
        assert medicao["bruto"] == "ok", (segundo, medicao["metricas"])
    assert monitor.estado()["referencia_automatica"] is True


def test_definir_referencia_zera_o_estado_confirmado(cena):
    _, quadros = cena
    monitor = _monitor(quadros[0])
    tampado = _tampado(quadros[0], (10, 10, 10))
    for segundo in range(4):
        monitor.observar(tampado, agora=float(segundo))
    assert monitor.estado()["estado"] == "obstruida"
    monitor.definir_referencia(quadros[0])
    assert monitor.estado()["estado"] == "ok"
    assert monitor.alertas() == []


def test_serializar_e_carregar_referencia_ida_e_volta(cena):
    _, quadros = cena
    original = _monitor(quadros[0])
    png = original.serializar_referencia()
    assert png[:8] == b"\x89PNG\r\n\x1a\n"

    recarregado = MonitorDeSaudeVisual()
    recarregado.carregar_referencia(png)
    assert recarregado.tem_referencia
    assert recarregado.estado()["referencia_automatica"] is False
    assert recarregado.serializar_referencia() == png

    # a referência recarregada se comporta igual à original, inclusive para detectar câmera movida
    for i, quadro in enumerate(quadros[:5]):
        a, b = original.observar(quadro, agora=float(i)), recarregado.observar(quadro, agora=float(i))
        assert a["metricas"] == b["metricas"]
    assert recarregado.observar(_movido(quadros[0], 0.2, 0.05, 5), agora=10.0)["bruto"] == "movida"


def test_serializar_sem_referencia_e_png_invalido_falham_com_clareza():
    monitor = MonitorDeSaudeVisual()
    with pytest.raises(ValueError, match="Sem referência"):
        monitor.serializar_referencia()
    with pytest.raises(ValueError, match="PNG"):
        monitor.carregar_referencia(b"isto nao e um png")
    assert not monitor.tem_referencia


# ---------------------------------------------------------------- throttle e relógio


def test_no_maximo_uma_medicao_por_intervalo_e_sem_tocar_no_quadro():
    monitor = MonitorDeSaudeVisual(intervalo_s=1.0)
    quadro = np.full((90, 160, 3), 128, np.uint8)
    quadro[::2] = 40  # alguma textura
    assert monitor.observar(quadro, agora=0.0) is not None
    # `None` no lugar do quadro: se o monitor encostasse nele, levantaria erro
    assert monitor.observar(None, agora=0.4) is None
    assert monitor.observar(None, agora=0.99) is None
    assert monitor.observar(quadro, agora=1.0) is not None
    assert monitor.observar(None, agora=1.5) is None
    assert monitor.observar(quadro, agora=2.0) is not None


def test_usa_o_relogio_injetado_quando_agora_nao_e_passado():
    hora = [100.0]
    monitor = MonitorDeSaudeVisual(relogio=lambda: hora[0])
    quadro = np.zeros((90, 160, 3), np.uint8)
    assert monitor.observar(quadro) is not None
    hora[0] = 100.5
    assert monitor.observar(None) is None
    hora[0] = 101.0
    assert monitor.observar(quadro) is not None


def test_quadro_em_cinza_e_quadro_pequeno_funcionam():
    monitor = MonitorDeSaudeVisual()
    cinza = (np.random.default_rng(1).random((60, 100)) * 255).astype(np.uint8)
    medicao = monitor.observar(cinza, agora=0.0)
    assert medicao["bruto"] == "ok"
    assert monitor.tem_referencia


# ---------------------------------------------------------------- histerese (sem imagem)


def _alimentar(histerese: Histerese, sequencia: list[tuple[float, str]]) -> list[str]:
    estados = []
    for agora, bruto in sequencia:
        histerese.avancar(bruto, agora)
        estados.append(histerese.estado)
    return estados


def test_histerese_confirma_so_apos_3s_e_libera_so_apos_3s_de_ok():
    h = Histerese(confirmar_s=3.0, liberar_s=3.0)
    ruins = _alimentar(h, [(t, "obstruida") for t in (0.0, 1.0, 2.0, 3.0)])
    assert ruins == ["ok", "ok", "ok", "obstruida"]
    assert h.desde == 0.0, "`desde` é o início da sequência, não o instante da confirmação"

    boas = _alimentar(h, [(t, "ok") for t in (4.0, 5.0, 6.0, 7.0)])
    assert boas == ["obstruida", "obstruida", "obstruida", "ok"]
    assert h.desde is None


def test_histerese_um_quadro_bom_no_meio_zera_a_confirmacao():
    h = Histerese(confirmar_s=3.0, liberar_s=3.0)
    estados = _alimentar(h, [(0.0, "escura"), (1.0, "escura"), (2.0, "ok"), (3.0, "escura"), (4.0, "escura"), (5.0, "escura")])
    assert set(estados) == {"ok"}, "a contagem recomeçou em t=3; só confirma em t=6"
    h.avancar("escura", 6.0)
    assert h.estado == "escura"


def test_histerese_um_quadro_ruim_no_meio_zera_a_liberacao():
    h = Histerese(confirmar_s=3.0, liberar_s=3.0)
    _alimentar(h, [(t, "ofuscada") for t in (0.0, 1.0, 2.0, 3.0)])
    assert h.estado == "ofuscada"
    estados = _alimentar(h, [(4.0, "ok"), (5.0, "ok"), (6.0, "ofuscada"), (7.0, "ok"), (8.0, "ok"), (9.0, "ok")])
    assert set(estados) == {"ofuscada"}
    h.avancar("ok", 10.0)
    assert h.estado == "ok"


def test_histerese_troca_de_tipo_confirmado_sem_passar_por_ok():
    h = Histerese(confirmar_s=3.0, liberar_s=3.0)
    _alimentar(h, [(t, "obstruida") for t in (0.0, 1.0, 2.0, 3.0)])
    estados = _alimentar(h, [(4.0, "desfocada"), (5.0, "desfocada"), (6.0, "desfocada"), (7.0, "desfocada")])
    assert estados == ["obstruida", "obstruida", "obstruida", "desfocada"]
    assert h.desde == 4.0


def test_histerese_tipo_que_muda_no_meio_da_confirmacao_reinicia_a_contagem():
    h = Histerese(confirmar_s=3.0, liberar_s=3.0)
    estados = _alimentar(h, [(0.0, "escura"), (1.0, "escura"), (2.0, "desfocada"), (3.0, "desfocada"), (4.0, "desfocada")])
    assert set(estados) == {"ok"}
    h.avancar("desfocada", 5.0)
    assert h.estado == "desfocada"


def test_histerese_confirmacao_e_em_segundos_nao_em_quadros():
    """Mesma oclusão, câmera de 25 fps ou de 2: o que conta é o tempo."""
    lenta, rapida = Histerese(3.0, 3.0), Histerese(3.0, 3.0)
    _alimentar(lenta, [(t, "obstruida") for t in (0.0, 2.9)])
    _alimentar(rapida, [(i * 0.5, "obstruida") for i in range(7)])  # 7 quadros, t=0..3
    assert lenta.estado == "ok"
    assert rapida.estado == "obstruida"


def test_histerese_quadro_inconclusivo_nao_confirma_nem_libera_movida():
    h = Histerese(confirmar_s=3.0, liberar_s=3.0)
    h.avancar("movida", 0.0)
    h.avancar("ok", 1.0, inconclusivo=True)  # multidão na frente: não prova que a câmera voltou
    h.avancar("ok", 2.0, inconclusivo=True)
    h.avancar("movida", 3.0)
    assert h.estado == "movida" and h.desde == 0.0

    for t in (4.0, 5.0, 6.0, 7.0):
        h.avancar("ok", t, inconclusivo=True)
    assert h.estado == "movida", "inconclusivo nunca libera"
    for t in (8.0, 9.0, 10.0, 11.0):
        h.avancar("ok", t)  # conclusivo: a cena bate com a referência
    assert h.estado == "ok"


def test_histerese_inconclusivo_continua_valendo_como_ok_para_os_outros_tipos():
    h = Histerese(confirmar_s=3.0, liberar_s=3.0)
    _alimentar(h, [(t, "obstruida") for t in (0.0, 1.0, 2.0, 3.0)])
    for t in (4.0, 5.0, 6.0, 7.0):
        h.avancar("ok", t, inconclusivo=True)
    assert h.estado == "ok", "senão uma multidão impediria para sempre a câmera de sair de OBSTRUÍDA"


# ---------------------------------------------------------------- ponta a ponta + alertas


def _sabotagem(tipo: str, nome: str, quadro: np.ndarray) -> np.ndarray:
    return {
        "obstruida": lambda: _tampado(quadro, (10, 10, 10)),
        "movida": lambda: _movido(quadro, 0.2, 0.05, 5.0),
        "escura": lambda: _escurecido(quadro, GAMA_ESCURA[nome]),
        "ofuscada": lambda: _ofuscado(quadro),
        "desfocada": lambda: _desfocado(quadro),
    }[tipo]()


@pytest.mark.parametrize(
    ("tipo", "severidade", "rotulo"),
    [
        ("obstruida", "high", "OBSTRUÍDA"),
        ("movida", "high", "MOVIDA"),
        ("escura", "medium", "ESCURA"),
        ("ofuscada", "medium", "OFUSCADA"),
        ("desfocada", "medium", "DESFOCADA"),
    ],
)
def test_de_ponta_a_ponta_confirma_em_3s_e_gera_alerta_compativel_com_rule_alert(tipo, severidade, rotulo):
    quadros = _quadros_espacados("bench")
    hora = [0.0]
    monitor = _monitor(quadros[0], relogio=lambda: hora[0])
    sabotado = _sabotagem(tipo, "bench", quadros[0])

    for segundo in range(3):
        hora[0] = float(segundo)
        assert monitor.observar(sabotado)["estado"] == "ok", "ainda confirmando"
        assert monitor.alertas() == []
    hora[0] = 3.0
    assert monitor.observar(sabotado)["estado"] == tipo

    estado = monitor.estado()
    assert estado["estado"] == tipo and estado["rotulo"] == rotulo
    assert estado["desde"] == 0.0 and estado["tem_referencia"] is True

    alertas = monitor.alertas()
    assert len(alertas) == 1
    alerta = RuleAlert(**alertas[0])
    assert alerta.rule == f"camera_{tipo}"
    assert alerta.severity == severidade
    assert alerta.feature == "saude_visual"
    assert alerta.metadata["subject"] == "camera"
    assert alerta.metadata["metricas"] == estado["metricas"]
    assert alerta.key == f"camera_{tipo}:saude_visual:camera"
    assert alerta.message.startswith("Câmera ") and alerta.message.endswith("há 3 s")
    assert tipo[:5] in alerta.message.lower().replace("ú", "u").replace("ç", "c")


def test_mensagem_de_obstruida_em_pt_br():
    quadros = _quadros_espacados("bench")
    monitor = _monitor(quadros[0])
    tampado = _tampado(quadros[0], (10, 10, 10))
    for segundo in range(4):
        monitor.observar(tampado, agora=float(segundo))
    assert monitor.alertas()[0]["message"] == "Câmera obstruída — imagem sem detalhe há 3 s"


def test_camera_movida_se_confirma_com_quadros_reais_seguidos_e_libera_quando_volta():
    quadros = _quadros_espacados("bench")
    monitor = _monitor(quadros[0])
    # o suporte girou logo depois da referência; os quadros seguintes do vídeo (pessoas se mexendo) vêm todos deslocados
    for segundo, quadro in enumerate(quadros[:6]):
        monitor.observar(_movido(quadro, 0.2, 0.05, 5.0), agora=float(segundo))
    assert monitor.estado()["estado"] == "movida"
    assert monitor.alertas()[0]["rule"] == "camera_movida"

    # voltou ao lugar: 3 s de quadros que batem com a referência liberam o estado
    for segundo, quadro in enumerate(quadros[:5], start=10):
        monitor.observar(quadro, agora=float(segundo))
    assert monitor.estado()["estado"] == "ok"
    assert monitor.alertas() == []


def test_estado_e_alertas_sao_serializaveis_em_json(cena):
    nome, quadros = cena
    monitor = _monitor(quadros[0])
    tampado = _tampado(quadros[0], (10, 10, 10))
    for segundo in range(4):
        monitor.observar(tampado, agora=float(segundo))
    json.dumps(monitor.estado())
    json.dumps(monitor.alertas())
    for valor in monitor.estado()["metricas"].values():
        assert type(valor) in (int, float), "numpy escalar não vai para o JSON do dashboard"


def test_estado_inicial_sem_nenhuma_medicao():
    estado = MonitorDeSaudeVisual().estado()
    assert estado == {
        "estado": "ok",
        "rotulo": "OK",
        "desde": None,
        "metricas": {},
        "tem_referencia": False,
        "referencia_automatica": False,
    }
    assert MonitorDeSaudeVisual().alertas() == []
