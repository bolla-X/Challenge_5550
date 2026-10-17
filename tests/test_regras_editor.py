"""Editor de regras sem código (MISSÃO 4, M4): formato, avaliação, equivalência com as
regras nativas, teste no histórico e API.

A prova central é a EQUIVALÊNCIA: cada regra nativa, reescrita como definição do
editor, tem que produzir exatamente os mesmos alertas (regra, pessoa, severidade,
mensagem) que o RuleEngine produz sozinho — sobre as mesmas detecções sintéticas.
"""

from __future__ import annotations

import copy
import time
from collections import Counter
from dataclasses import replace
from datetime import datetime

import pytest
from app import create_app
from app.config import AuthTestConfig
from app.extensions import db
from app.models import ROLE_OPERATOR, ROLE_SUPERVISOR, ROLE_TECHNICAL, Camera
from app.services.auth_service import AuthService
from app.services.feature_manager import FeatureManager
from app.services.regras_editor import (
    AvaliadorDeRegras,
    RegraInvalida,
    compilar,
    fatos_ao_vivo,
    fatos_do_historico,
    regras_pre_carregadas,
    validar,
)
from app.services.regras_editor import (
    testar_no_historico as simular_regra,
)
from app.services.regras_repositorio import aplicar_regras
from app.services.risk_rules import PPE_RULES, RuleEngine
from app.vision.person_compliance_matcher import PPE_KEYS
from app.vision.schemas import BoundingBox, Detection, PoseLandmark, PoseResult

SENHA = "senha-forte-de-teste"
FEATURES = "ppe,helmet,vest,gloves,glasses,mask,safety_shoe,ear_protection,pose,falls,posture,risk_area"
ZONA = [(0.7, 0.1), (1, 0.1), (1, 1), (0.7, 1)]
FRAME = (540, 960, 3)


# ---------------------------------------------------------------- helpers ---
def regra_json(itens, op="E", **sobrescreve):
    regra = {
        "id": "r1", "nome": "Regra de teste", "ativa": True, "origem": "usuario", "camera_ids": None,
        "condicao": {"op": op, "itens": itens},
        "acoes": {"severidade": "high", "mensagem": "Alerta de teste", "fala": False, "integracao": False,
                  "escalonamento": {"supervisor_s": None, "tv_s": None}},
    }
    return regra | sobrescreve


def compilada(itens, op="E", **sobrescreve):
    return compilar(validar(regra_json(itens, op, **sobrescreve)))


def fato(pessoa_id="person_1", **kw):
    base = {"pessoa_id": pessoa_id, "rotulo": "Pessoa 1", "epi": {}, "evidencia": {}, "na_zona": False, "posturas": set(),
            "aproximando": False, "hora": "10:00", "permissao_ativa": False, "box": {"x1": 1, "y1": 2, "x2": 3, "y2": 4}}
    return base | kw


SEM_CAPACETE = {"tipo": "epi", "epi": "helmet", "estado": "ausente"}
NA_ZONA = {"tipo": "zona", "dentro": True}
CAIDA = {"tipo": "postura", "postura": "caida"}


def disparou(avaliador, fatos, agora, camera_id=None):
    return [a.rule for a in avaliador.avaliar(fatos, agora, camera_id)]


# ------------------------------------------------------------- validação ---
def test_regra_valida_vira_objeto_e_volta_igual_em_dict():
    regra = validar(regra_json([SEM_CAPACETE, {"op": "OU", "itens": [NA_ZONA, CAIDA]}]))
    assert regra.regra_id == "regra:r1"  # regra de usuário nunca usa o nome de uma nativa
    assert validar(regra.to_dict()) == regra
    assert regra.to_dict()["acoes"]["escalonamento"] == {"supervisor_s": None, "tv_s": None}


def _aninhar(n):
    grupo = {"op": "E", "itens": [NA_ZONA]}
    for _ in range(n - 1):
        grupo = {"op": "E", "itens": [grupo]}
    return grupo


def _mut(caminho, valor):
    def aplicar(regra):
        alvo = regra
        for parte in caminho[:-1]:
            alvo = alvo[parte]
        if valor is _APAGAR:
            alvo.pop(caminho[-1], None)
        else:
            alvo[caminho[-1]] = valor
        return regra
    return aplicar


_APAGAR = object()
ITEM0 = ("condicao", "itens", 0)
INVALIDAS = [
    ("id com espaço", _mut(("id",), "a b"), "id:"),
    ("nome ausente", _mut(("nome",), _APAGAR), "nome: texto obrigatório"),
    ("origem desconhecida", _mut(("origem",), "outra"), "origem:"),
    ("pré-carregada com regra_id inventado", lambda r: r | {"origem": "pre_carregada", "regra_id": "nao_existe"}, "regra_id:"),
    ("camera_ids não é lista", _mut(("camera_ids",), "1"), "camera_ids:"),
    ("camera_id não inteiro", _mut(("camera_ids",), ["a"]), "camera_ids[0]"),
    ("severidade inválida", _mut(("acoes", "severidade"), "grave"), "acoes.severidade"),
    ("mensagem vazia", _mut(("acoes", "mensagem"), "  "), "acoes.mensagem"),
    ("fala não booleana", _mut(("acoes", "fala"), "sim"), "acoes.fala"),
    ("escalonamento negativo", _mut(("acoes", "escalonamento"), {"supervisor_s": -5}), "acoes.escalonamento.supervisor_s"),
    ("acoes ausente", _mut(("acoes",), _APAGAR), "acoes: obrigatório"),
    ("operador inválido", _mut(("condicao", "op"), "XOR"), "condicao.op"),
    ("grupo sem itens", _mut(("condicao", "itens"), []), "pelo menos um item"),
    ("bloco desconhecido", _mut(("condicao", "itens"), [{"tipo": "lua"}]), "bloco desconhecido"),
    ("epi inexistente", _mut(("condicao", "itens"), [{"tipo": "epi", "epi": "cueca", "estado": "ausente"}]), "condicao.itens[0].epi"),
    ("estado de epi inválido", _mut(("condicao", "itens"), [{"tipo": "epi", "epi": "helmet", "estado": "sujo"}]),
     "condicao.itens[0].estado"),
    ("zona não booleana", _mut(("condicao", "itens"), [{"tipo": "zona", "dentro": "sim"}]), "condicao.itens[0].dentro"),
    ("duração zero", _mut(("condicao", "itens"), [NA_ZONA, {"tipo": "duracao", "segundos": 0}]), "entre 1 e 3600"),
    ("duração acima de 1 h", _mut(("condicao", "itens"), [NA_ZONA, {"tipo": "duracao", "segundos": 3601}]), "entre 1 e 3600"),
    ("duração como texto", _mut(("condicao", "itens"), [NA_ZONA, {"tipo": "duracao", "segundos": "5"}]), "número inteiro"),
    ("grupo só com duração", _mut(("condicao", "itens"), [{"tipo": "duracao", "segundos": 5}]), "só tem blocos de duração"),
    ("postura inválida", _mut(("condicao", "itens"), [{"tipo": "postura", "postura": "dançando"}]), "condicao.itens[0].postura"),
    ("horário fora do relógio", _mut(("condicao", "itens"), [{"tipo": "horario", "de": "25:00", "ate": "06:00"}]), "HH:MM"),
    ("horário sem zero à esquerda", _mut(("condicao", "itens"), [{"tipo": "horario", "de": "8:00", "ate": "06:00"}]), "HH:MM"),
    ("janela vazia", _mut(("condicao", "itens"), [{"tipo": "horario", "de": "08:00", "ate": "08:00"}]), "não podem ser iguais"),
    ("permissão não booleana", _mut(("condicao", "itens"), [{"tipo": "permissao_ativa", "ativa": 1}]), "condicao.itens[0].ativa"),
    ("profundidade 4", _mut(("condicao",), _aninhar(4)), "até 3 níveis"),
    ("21 blocos", _mut(("condicao", "itens"), [NA_ZONA] * 21), "no máximo 20 blocos"),
]


@pytest.mark.parametrize("descricao, alterar, trecho", INVALIDAS, ids=[i[0] for i in INVALIDAS])
def test_regra_invalida_diz_o_que_esta_errado_em_pt_br(descricao, alterar, trecho):
    regra = alterar(copy.deepcopy(regra_json([SEM_CAPACETE])))
    with pytest.raises(RegraInvalida) as erro:
        validar(regra)
    assert trecho in str(erro.value)


def test_regra_que_nao_e_objeto_e_recusada():
    with pytest.raises(RegraInvalida, match="objeto JSON"):
        validar(["nao", "e", "um", "dict"])


def test_limites_exatos_sao_aceitos():
    validar(regra_json([NA_ZONA] * 20))  # 20 blocos
    validar(regra_json([NA_ZONA]) | {"condicao": _aninhar(3)})  # profundidade 3
    validar(regra_json([NA_ZONA, {"tipo": "duracao", "segundos": 3600}]))
    validar(regra_json([{"tipo": "horario", "de": "22:00", "ate": "06:00"}]))


# --------------------------------------------------------- E / OU / blocos ---
def test_e_ou_aninhado():
    # capacete ausente E (na zona OU caída)
    av = AvaliadorDeRegras([compilada([SEM_CAPACETE, {"op": "OU", "itens": [NA_ZONA, CAIDA]}])])
    sem = {"epi": {"helmet": "ausente"}}
    com = {"epi": {"helmet": "presente"}}
    casos = [
        (fato(**sem, na_zona=True), True),
        (fato(**sem, posturas={"caida"}), True),
        (fato(**sem), False),  # nenhum dos dois do OU
        (fato(**com, na_zona=True, posturas={"caida"}), False),  # o E do capacete falha
        (fato(epi={"helmet": "nao_verificado"}, na_zona=True), False),  # não verificado nunca é "ausente"
    ]
    for i, (f, esperado) in enumerate(casos):
        assert bool(disparou(av, [f], float(i))) is esperado, i


def test_ou_na_raiz_com_zona_fora():
    av = AvaliadorDeRegras([compilada([{"tipo": "zona", "dentro": False}, CAIDA], op="OU")])
    assert disparou(av, [fato(na_zona=False)], 0)
    assert not disparou(av, [fato(na_zona=True)], 1)
    assert disparou(av, [fato(na_zona=True, posturas={"caida"})], 2)


def test_aproximacao_e_postura_suspeita():
    av = AvaliadorDeRegras([compilada([{"tipo": "aproximacao"}, {"tipo": "postura", "postura": "suspeita"}], op="OU")])
    assert not disparou(av, [fato()], 0)
    assert disparou(av, [fato(aproximando=True)], 1)
    assert disparou(av, [fato(posturas={"suspeita"})], 2)
    assert not disparou(av, [fato(posturas={"caida"})], 3)


def test_permissao_ativa():
    sem_permissao = AvaliadorDeRegras([compilada([NA_ZONA, {"tipo": "permissao_ativa", "ativa": False}])])
    com_permissao = AvaliadorDeRegras([compilada([NA_ZONA, {"tipo": "permissao_ativa", "ativa": True}])])
    for permissao in (False, True):
        f = fato(na_zona=True, permissao_ativa=permissao)
        assert bool(disparou(sem_permissao, [f], 0)) is (not permissao)
        assert bool(disparou(com_permissao, [f], 0)) is permissao


@pytest.mark.parametrize("hora, esperado", [
    ("22:00", True), ("23:30", True), ("00:00", True), ("05:59", True), ("06:00", False), ("12:00", False), ("21:59", False),
])
def test_horario_atravessando_a_meia_noite(hora, esperado):
    av = AvaliadorDeRegras([compilada([{"tipo": "horario", "de": "22:00", "ate": "06:00"}])])
    assert bool(disparou(av, [fato(hora=hora)], 0)) is esperado


@pytest.mark.parametrize("hora, esperado", [("07:59", False), ("08:00", True), ("16:59", True), ("17:00", False)])
def test_horario_no_mesmo_dia(hora, esperado):
    av = AvaliadorDeRegras([compilada([{"tipo": "horario", "de": "08:00", "ate": "17:00"}])])
    assert bool(disparou(av, [fato(hora=hora)], 0)) is esperado


def test_regra_inativa_e_regra_de_outra_camera_nao_disparam():
    inativa = compilada([NA_ZONA], ativa=False)
    da_camera_2 = compilada([NA_ZONA], id="r2", camera_ids=[2])
    av = AvaliadorDeRegras([inativa, da_camera_2])
    f = fato(na_zona=True)
    assert disparou(av, [f], 0, camera_id=1) == []
    assert disparou(av, [f], 0, camera_id=2) == ["regra:r2"]


# ----------------------------------------------------------------- duração ---
def test_duracao_exige_condicao_continua_com_relogio_falso():
    relogio = {"t": 0.0}
    av = AvaliadorDeRegras([compilada([SEM_CAPACETE, {"tipo": "duracao", "segundos": 5}])], relogio=lambda: relogio["t"])
    ausente, presente = fato(epi={"helmet": "ausente"}), fato(epi={"helmet": "presente"})

    def passo(t, f):
        relogio["t"] = t
        return [a.rule for a in av.avaliar([f])]  # sem `agora`: usa o relógio injetado

    assert passo(0.0, ausente) == []
    assert passo(4.9, ausente) == []
    assert passo(5.0, ausente) == ["regra:r1"]
    assert passo(6.0, ausente) == ["regra:r1"]
    assert passo(7.0, presente) == []  # interrompeu
    assert passo(8.0, ausente) == []  # recomeça do zero
    assert passo(12.9, ausente) == []
    assert passo(13.0, ausente) == ["regra:r1"]


def test_duracao_zera_quando_a_pessoa_sai_de_cena_e_e_por_pessoa():
    av = AvaliadorDeRegras([compilada([NA_ZONA, {"tipo": "duracao", "segundos": 3}])])
    a, b = fato("person_1", na_zona=True), fato("person_2", rotulo="Pessoa 2", na_zona=True)
    assert disparou(av, [a], 0) == []
    assert disparou(av, [a, b], 2) == []  # b começou agora
    assert [x.metadata["person_id"] for x in av.avaliar([a, b], 3)] == ["person_1"]
    assert [x.metadata["person_id"] for x in av.avaliar([a, b], 5)] == ["person_1", "person_2"]
    av.avaliar([], 6)  # ninguém em cena: os relógios morrem
    assert disparou(av, [a], 7) == []
    assert disparou(av, [a], 9) == []
    assert disparou(av, [a], 10) == ["regra:r1"]


def test_duracao_vale_para_o_grupo_que_a_contem():
    # na zona E (capacete ausente OU caída, por 3 s): a zona não precisa durar, o OU sim.
    grupo = {"op": "OU", "itens": [SEM_CAPACETE, CAIDA, {"tipo": "duracao", "segundos": 3}]}
    av = AvaliadorDeRegras([compilada([NA_ZONA, grupo])])
    f = fato(na_zona=True, epi={"helmet": "ausente"})
    assert disparou(av, [f], 0) == []
    assert disparou(av, [f], 3) == ["regra:r1"]
    # sai da zona: o E derruba, mas o relógio do OU interno CONTINUA (o grupo dele segue verdadeiro)
    assert disparou(av, [fato(na_zona=False, epi={"helmet": "ausente"})], 4) == []
    assert disparou(av, [f], 5) == ["regra:r1"]
    # o OU fica falso: relógio zera
    assert disparou(av, [fato(na_zona=True, epi={"helmet": "presente"})], 6) == []
    assert disparou(av, [f], 7) == []
    assert disparou(av, [f], 10) == ["regra:r1"]


def test_varios_blocos_de_duracao_no_mesmo_grupo_vale_o_maior():
    av = AvaliadorDeRegras([compilada([NA_ZONA, {"tipo": "duracao", "segundos": 2}, {"tipo": "duracao", "segundos": 6}])])
    f = fato(na_zona=True)
    assert disparou(av, [f], 0) == []
    assert disparou(av, [f], 5) == []
    assert disparou(av, [f], 6) == ["regra:r1"]


# -------------------------------------------------- alerta (forma e conteúdo) ---
def test_alerta_do_editor_tem_a_forma_do_alerta_nativo():
    av = AvaliadorDeRegras([compilada([NA_ZONA, SEM_CAPACETE], id="r9")])
    f = fato(na_zona=True, epi={"helmet": "ausente"}, evidencia={"helmet": "negativa_detectada"})
    (alerta,) = av.avaliar([f], 0)
    assert (alerta.rule, alerta.severity) == ("regra:r9", "high")
    assert alerta.message == "Alerta de teste · Pessoa 1 (visto sem o EPI)"
    assert alerta.feature == "helmet"  # um único EPI na regra: a chave dele
    assert alerta.key == "regra:r9:helmet:person_1"
    meta = alerta.metadata
    assert (meta["person_id"], meta["person_label"], meta["person_box"], meta["na_zona"]) == ("person_1", "Pessoa 1", f["box"], True)
    assert meta["regra_editor_id"] == "r9"
    assert meta["acoes"]["severidade"] == "high" and meta["acoes"]["escalonamento"] == {"supervisor_s": None, "tv_s": None}


def test_feature_generica_quando_a_regra_nao_e_de_um_unico_epi():
    (alerta,) = AvaliadorDeRegras([compilada([NA_ZONA])]).avaliar([fato(na_zona=True)], 0)
    assert alerta.feature == "regras"


# ------------------------------------------------- equivalência com o motor ---
def _manager():
    return FeatureManager.from_config({"DEFAULT_FEATURES": FEATURES})


def _pessoa(track, caixa):
    return Detection(label="person", confidence=0.9, box=BoundingBox(*caixa), category="person", track_id=track)


def _item(label, caixa, conf=0.8):
    return Detection(label=label, confidence=conf, box=BoundingBox(*caixa), category="ppe")


# Onde pôr cada EPI DENTRO da caixa da pessoa mas FORA da faixa esperada dele
# (altura relativa 0 = topo, 1 = pés): é o "em uso incorreto" do matcher.
_ALTURA_INCORRETA = {"helmet": 0.6, "glasses": 0.6, "mask": 0.6, "ear_protection": 0.6, "vest": 0.96, "gloves": 0.05, "safety_shoe": 0.3}


def _cena_completa():
    """3 pessoas: P1 fora da zona sem nenhum EPI; P2 na zona com todos os EPIs mal
    posicionados (+ colete negado); P3 fora da zona, capacete negado. Poses: P1 caída,
    P2 em pé, P3 com a cabeça projetada (postura suspeita)."""
    p1, p2, p3 = (100, 100, 200, 400), (700, 100, 820, 400), (400, 100, 500, 400)
    detecoes = [_pessoa(1, p1), _pessoa(2, p2), _pessoa(3, p3)]
    for i, chave in enumerate(PPE_KEYS):
        cy = 100 + int(300 * _ALTURA_INCORRETA[chave])
        detecoes.append(_item(chave, (705 + i * 14, cy - 5, 715 + i * 14, cy + 5)))
    detecoes.append(_item("no_vest", (730, 200, 790, 260)))  # P2: colete negado (e colete mal posto)
    detecoes.append(_item("no_helmet", (430, 100, 470, 130)))  # P3: capacete negado
    return detecoes, [_pose(1, caida=True), _pose(2), _pose(3, nariz_dx=100)]


def _pose(track, *, caida=False, nariz_dx=0):
    altura, largura = FRAME[:2]
    ombro, quadril = ((300, 400), (500, 405)) if caida else ((400, 200), (405, 350))
    nariz = (ombro[0] + nariz_dx - (40 if caida else 0), ombro[1] - (0 if caida else 40))

    def lm(nome, p):
        return PoseLandmark(name=nome, x=p[0] / largura, y=p[1] / altura, z=0.0, visibility=0.9)

    return PoseResult(
        landmarks=[lm("left_shoulder", (ombro[0] - 20, ombro[1])), lm("right_shoulder", (ombro[0] + 20, ombro[1])),
                   lm("left_hip", (quadril[0] - 15, quadril[1])), lm("right_hip", (quadril[0] + 15, quadril[1])), lm("nose", nariz)],
        person_id=f"person_{track}", track_id=track)


def _pose_global_caida():
    pose = _pose(1, caida=True)
    return replace(pose, person_id=None, track_id=None)


def _motor():
    motor = RuleEngine(_manager(), cooldown_seconds=0, risk_polygon=ZONA)
    motor.agora_local = lambda: datetime(2026, 10, 17, 10, 0)
    return motor


def _so_o_editor(regras):
    """Motor com as regras nativas silenciadas e só as do editor ativas.

    Desligar a nativa pelo FeatureManager não serve de controle: o feature desligado
    também zera o estado que o matcher entrega ao editor (status "disabled")."""
    motor = _motor()
    for nome in ("_evaluate_ppe", "_evaluate_pose", "_evaluate_quedas_do_modelo", "_evaluate_risk_area"):
        setattr(motor, nome, lambda *a, **k: [])
    motor.avaliador_do_editor = AvaliadorDeRegras([compilar(replace(r, ativa=True)) for r in regras])
    return motor


def _resumo(alertas):
    return Counter((a.rule, a.metadata.get("person_id"), a.severity, a.message) for a in alertas)


def _analisar(motor, detecoes, poses):
    return motor.analyze(detecoes, poses[0] if poses else None, FRAME, poses=poses).alerts


PRE_CARREGADAS = regras_pre_carregadas()


@pytest.mark.parametrize("pre", PRE_CARREGADAS, ids=[r.regra_id for r in PRE_CARREGADAS])
def test_equivalencia_de_cada_regra_nativa_com_a_pre_carregada(pre):
    detecoes, poses = _cena_completa()
    nativa = [a for a in _analisar(_motor(), detecoes, poses) if a.rule == pre.regra_id]
    editor = _analisar(_so_o_editor([pre]), detecoes, poses)
    assert nativa, f"a cena não exercita {pre.regra_id}: a comparação seria vazia"
    assert _resumo(editor) == _resumo(nativa)


def test_equivalencia_do_conjunto_inteiro_de_pre_carregadas():
    detecoes, poses = _cena_completa()
    nomes = {r.regra_id for r in PRE_CARREGADAS}
    nativa = [a for a in _analisar(_motor(), detecoes, poses) if a.rule in nomes]
    editor = _analisar(_so_o_editor(PRE_CARREGADAS), detecoes, poses)
    assert len(nativa) > 20
    assert _resumo(editor) == _resumo(nativa)
    # a feature do alerta (chave do alerta e "resolver ao desligar") também é a da nativa
    assert Counter((a.rule, a.feature) for a in editor) == Counter((a.rule, a.feature) for a in nativa)


@pytest.mark.parametrize("nome", ["fallen_person", "suspicious_posture"])
def test_equivalencia_da_pose_global_sem_caixa_de_pessoa(nome):
    pre = next(r for r in PRE_CARREGADAS if r.regra_id == nome)
    pose = _pose_global_caida() if nome == "fallen_person" else replace(_pose(3, nariz_dx=100), person_id=None, track_id=None)
    nativa = [a for a in _analisar(_motor(), [], [pose]) if a.rule == nome]
    editor = _analisar(_so_o_editor([pre]), [], [pose])
    assert nativa
    assert nativa[0].message == {"fallen_person": "Pessoa caída detectada", "suspicious_posture": "Postura suspeita detectada"}[nome]
    assert nativa[0].metadata["subject"] == "global_pose"  # sem rótulo de pessoa
    assert _resumo(editor) == _resumo(nativa)


def test_equivalencia_sem_ninguem_em_cena_e_com_pessoa_conforme():
    conforme = [_pessoa(1, (100, 100, 200, 400))] + [
        _item(chave, (130, 100 + int(300 * z), 170, 110 + int(300 * z))) for chave, z in
        {"helmet": 0.08, "vest": 0.42, "gloves": 0.62, "glasses": 0.1, "mask": 0.14, "safety_shoe": 0.95, "ear_protection": 0.09}.items()
    ]
    for detecoes, poses in (([], []), (conforme, [_pose(1)])):
        assert _analisar(_so_o_editor(PRE_CARREGADAS), detecoes, poses) == [] == [
            a for a in _analisar(_motor(), detecoes, poses) if a.rule in {r.regra_id for r in PRE_CARREGADAS}
        ]


def test_features_desligadas_silenciam_a_pre_carregada_como_a_nativa():
    detecoes, poses = _cena_completa()
    motor = _so_o_editor(PRE_CARREGADAS)
    motor.feature_manager.update({"helmet": False, "falls": False, "risk_area": False})
    nomes = {r.regra_id for r in PRE_CARREGADAS}
    nativa = _motor()
    nativa.feature_manager.update({"helmet": False, "falls": False, "risk_area": False})
    esperado = [a for a in _analisar(nativa, detecoes, poses) if a.rule in nomes]
    assert esperado and not any(a.rule.endswith("helmet") or a.rule in ("fallen_person", "risk_area_presence") for a in esperado)
    assert _resumo(_analisar(motor, detecoes, poses)) == _resumo(esperado)


def test_sem_avaliador_o_motor_nao_muda():
    detecoes, poses = _cena_completa()
    antes = _resumo(_analisar(_motor(), detecoes, poses))
    motor = _motor()
    motor.avaliador_do_editor = AvaliadorDeRegras([])  # avaliador sem regras também não acrescenta nada
    assert _resumo(_analisar(motor, detecoes, poses)) == antes


def test_pre_carregadas_cobrem_todas_as_nativas_e_nascem_desligadas():
    nomes = {r.regra_id for r in PRE_CARREGADAS}
    assert nomes == ({f"missing_{k}" for k in PPE_RULES} | {f"incorrect_{k}" for k in PPE_RULES}
                     | {"risk_area_presence", "fallen_person", "suspicious_posture"})
    assert all(not r.ativa and r.origem == "pre_carregada" for r in PRE_CARREGADAS)
    assert {r.acoes.mensagem for r in PRE_CARREGADAS if r.regra_id == "missing_helmet"} == {"Sem capacete"}


# ---------------------------------------------------------------- fatos ---
def test_fatos_ao_vivo_normaliza_status_aproximacao_e_hora():
    people = [
        {"id": "person_3", "track_id": 3, "label": "Pessoa 3", "box": {"x1": 1}, "risk_area": {"status": "inside"},
         "ppe": {"helmet": {"status": "ok"}, "vest": {"status": "missing", "evidence": "negativa_detectada"},
                 "gloves": {"status": "incorrect"}, "mask": {"status": "unverified"}, "glasses": {"status": "disabled"}}},
        {"id": "person_4", "track_id": 4, "label": "Pessoa 4", "box": {}, "risk_area": {"status": "outside"}, "ppe": {}},
    ]
    f3, f4 = fatos_ao_vivo(people, {"person_3": {"caida"}}, [{"track_id": 3}], datetime(2026, 10, 17, 23, 5), True)
    assert f3["epi"]["helmet"] == "presente" and f3["epi"]["vest"] == "ausente" and f3["epi"]["gloves"] == "incorreto"
    assert f3["epi"]["mask"] == f3["epi"]["glasses"] == f3["epi"]["safety_shoe"] == "nao_verificado"
    assert f3["evidencia"]["vest"] == "negativa_detectada"
    assert (f3["na_zona"], f3["posturas"], f3["aproximando"], f3["hora"], f3["permissao_ativa"]) == (True, {"caida"}, True, "23:05", True)
    assert (f4["na_zona"], f4["posturas"], f4["aproximando"]) == (False, set(), False)


def test_motor_alimenta_a_aproximacao_e_a_permissao_pelo_contexto():
    motor = _motor()
    motor.avaliador_do_editor = AvaliadorDeRegras(
        [compilada([{"tipo": "aproximacao"}, {"tipo": "permissao_ativa", "ativa": False}])]
    )
    detecoes = [_pessoa(7, (100, 100, 200, 400))]
    assert [a for a in _analisar(motor, detecoes, []) if a.rule.startswith("regra:")] == []
    motor.contexto_do_editor.update(pre_alertas=[{"track_id": 7}], permissao_ativa=False)
    assert [a.rule for a in _analisar(motor, detecoes, []) if a.rule.startswith("regra:")] == ["regra:r1"]
    motor.contexto_do_editor.update(permissao_ativa=True)
    assert [a for a in _analisar(motor, detecoes, []) if a.rule.startswith("regra:")] == []


def test_motor_passa_a_hora_local_do_servidor_ao_horario():
    motor = _motor()
    motor.avaliador_do_editor = AvaliadorDeRegras([compilada([{"tipo": "horario", "de": "22:00", "ate": "06:00"}])])
    detecoes = [_pessoa(1, (100, 100, 200, 400))]
    motor.agora_local = lambda: datetime(2026, 10, 17, 23, 0)
    assert any(a.rule == "regra:r1" for a in _analisar(motor, detecoes, []))
    motor.agora_local = lambda: datetime(2026, 10, 17, 12, 0)
    assert not any(a.rule == "regra:r1" for a in _analisar(motor, detecoes, []))


# ------------------------------------------------------ testar no histórico ---
T0 = datetime(2026, 10, 17, 23, 30).timestamp()  # hora local 23:30


def _trilha(n=60, *, helmet="m", cx=0.8, passo=0.5, t0=T0):
    return [{"t": t0 + i * passo, "p": [[1, cx, 0.9, cx, 0.6, {"helmet": helmet, "vest": "o"}]]} for i in range(n)]


def _testar(itens, registros=None, **kw):
    registros = _trilha() if registros is None else registros
    return simular_regra(validar(regra_json(itens)), registros, T0, T0 + 30, **kw)


def test_historico_simulavel_conta_disparo_depois_da_histerese():
    r = _testar([SEM_CAPACETE])
    assert (r["simulavel"], r["motivo"], r["disparos"], r["pessoas"]) == (True, None, 1, 1)
    assert sum(c for _t, c in r["linha_do_tempo"]) == 1
    assert _testar([{"tipo": "epi", "epi": "helmet", "estado": "presente"}])["disparos"] == 0


def test_historico_respeita_duracao_horario_e_zona():
    assert _testar([SEM_CAPACETE, {"tipo": "duracao", "segundos": 10}])["disparos"] == 1
    assert _testar([SEM_CAPACETE, {"tipo": "duracao", "segundos": 40}])["disparos"] == 0  # a trilha só tem 30 s
    assert _testar([SEM_CAPACETE, {"tipo": "horario", "de": "22:00", "ate": "06:00"}])["disparos"] == 1
    janela_diurna = _testar([SEM_CAPACETE, {"tipo": "horario", "de": "08:00", "ate": "17:00"}])
    assert janela_diurna["simulavel"] and janela_diurna["disparos"] == 0
    zona = [(0.7, 0.0), (1.0, 0.0), (1.0, 1.0), (0.7, 1.0)]
    assert _testar([NA_ZONA], zona=zona)["disparos"] == 1
    assert _testar([NA_ZONA], registros=_trilha(cx=0.2), zona=zona)["disparos"] == 0


@pytest.mark.parametrize("itens, trecho", [
    ([CAIDA], "postura"),
    ([{"tipo": "aproximacao"}], "aproximação"),
    ([NA_ZONA], "zona"),  # sem polígono
    ([{"tipo": "permissao_ativa", "ativa": False}], "permissão ativa"),
    ([{"tipo": "epi", "epi": "gloves", "estado": "ausente"}], "gloves"),  # EPI que não foi gravado
])
def test_historico_diz_quando_nao_da_para_simular_em_vez_de_fingir(itens, trecho):
    r = _testar(itens)
    assert r["simulavel"] is False and trecho in r["motivo"]
    assert (r["disparos"], r["linha_do_tempo"], r["pessoas"]) == (0, [], 0)


def test_historico_nao_simulavel_se_qualquer_bloco_do_grupo_nao_tem_dado():
    r = _testar([SEM_CAPACETE, {"op": "OU", "itens": [NA_ZONA, CAIDA]}], zona=[(0, 0), (1, 0), (1, 1)])
    assert r["simulavel"] is False and "postura" in r["motivo"]


def test_historico_permissao_informada_pelo_chamador_vira_simulavel():
    r = _testar([SEM_CAPACETE, {"tipo": "permissao_ativa", "ativa": False}], permissao_ativa=False)
    assert r["simulavel"] and r["disparos"] == 1


def test_historico_ignora_ativa_e_camera_da_regra_e_aceita_dict():
    regra = regra_json([SEM_CAPACETE], ativa=False, camera_ids=[99])
    r = simular_regra(regra, _trilha(), T0, T0 + 30)
    assert r["simulavel"] and r["disparos"] == 1


def test_fatos_do_historico_traduz_codigos_da_trilha():
    (f,) = fatos_do_historico({"t": T0, "p": [[5, 0.8, 0.9, 0.8, 0.6, {"helmet": "m", "vest": "i", "gloves": "o", "mask": "n"}]]},
                              zona=[(0.7, 0), (1, 0), (1, 1), (0.7, 1)])
    assert (f["pessoa_id"], f["rotulo"], f["na_zona"], f["hora"]) == (5, "Pessoa 5", True, "23:30")
    assert (f["epi"]["helmet"], f["epi"]["vest"], f["epi"]["gloves"], f["epi"]["mask"], f["epi"]["glasses"]) == (
        "ausente", "incorreto", "presente", "nao_verificado", "nao_verificado")


# -------------------------------------------------------------------- API ---
@pytest.fixture()
def api(tmp_path):
    """App com autenticação LIGADA (DB em arquivo: cada request roda no próprio contexto)."""
    class Config(AuthTestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'regras.db'}"

    app = create_app(Config)
    if "regras" not in app.blueprints:
        from app.api.regras import regras_bp

        app.register_blueprint(regras_bp)
    with app.app_context():
        db.create_all()
        for papel in (ROLE_OPERATOR, ROLE_TECHNICAL, ROLE_SUPERVISOR):
            AuthService().create_user(email=f"{papel}@fabrica.com", name=papel.title(), password=SENHA, role=papel)
        db.session.remove()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


def _cliente(app, papel=None):
    cliente = app.test_client()
    if papel:
        resposta = cliente.post("/api/auth/login", json={"email": f"{papel}@fabrica.com", "password": SENHA})
        assert resposta.status_code == 200, resposta.get_json()
    return cliente


ROTAS = [
    ("get", "/api/regras"), ("post", "/api/regras"), ("put", "/api/regras/x"), ("delete", "/api/regras/x"),
    ("post", "/api/regras/x/ativar"), ("post", "/api/regras/x/desativar"), ("post", "/api/regras/testar"),
]


@pytest.mark.parametrize("metodo, caminho", ROTAS)
def test_api_sem_sessao_401_e_operador_403(api, metodo, caminho):
    assert getattr(_cliente(api), metodo)(caminho, json={}).status_code == 401
    assert getattr(_cliente(api, ROLE_OPERATOR), metodo)(caminho, json={}).status_code == 403


def test_api_tecnico_faz_o_crud(api):
    c = _cliente(api, ROLE_TECHNICAL)
    lista = c.get("/api/regras").get_json()
    assert len(lista["regras"]) == len(PRE_CARREGADAS) and all(r["protegida"] and not r["ativa"] for r in lista["regras"])
    assert lista["limites"] == {"profundidade": 3, "blocos": 20}

    corpo = regra_json([SEM_CAPACETE, NA_ZONA], id="minha", ativa=False)
    criada = c.post("/api/regras", json=corpo)
    assert criada.status_code == 201
    assert criada.get_json()["regra"]["regra_id"] == "regra:minha" and criada.get_json()["regra"]["protegida"] is False
    assert c.post("/api/regras", json=corpo).status_code == 409  # mesmo id

    gerada = c.post("/api/regras", json={k: v for k, v in corpo.items() if k != "id"}).get_json()["regra"]
    assert len(gerada["id"]) == 12  # id gerado pelo servidor

    editada = c.put("/api/regras/minha", json=regra_json([CAIDA], nome="Outro nome", ativa=False))
    assert editada.status_code == 200 and editada.get_json()["regra"]["nome"] == "Outro nome"
    assert editada.get_json()["regra"]["condicao"]["itens"] == [CAIDA]

    assert c.post("/api/regras/minha/ativar").get_json()["regra"]["ativa"] is True
    visto = {r["id"]: r for r in c.get("/api/regras").get_json()["regras"]}
    assert visto["minha"]["ativa"] is True
    assert c.post("/api/regras/minha/desativar").get_json()["regra"]["ativa"] is False

    assert c.delete("/api/regras/minha").status_code == 200
    assert c.delete("/api/regras/minha").status_code == 404
    assert c.put("/api/regras/minha", json=corpo).status_code == 404
    assert c.post("/api/regras/nao-existe/ativar").status_code == 404


def test_api_valida_com_400_e_mensagem_pt_br(api):
    c = _cliente(api, ROLE_TECHNICAL)
    itens = [{"tipo": "duracao", "segundos": 5}, NA_ZONA, {"tipo": "epi", "epi": "x", "estado": "ausente"}]
    resposta = c.post("/api/regras", json=regra_json(itens))
    assert resposta.status_code == 400
    assert resposta.get_json()["code"] == "regra_invalida" and "condicao.itens[2].epi" in resposta.get_json()["error"]
    assert c.post("/api/regras", data="não é json", content_type="text/plain").status_code == 400
    c.post("/api/regras", json=regra_json([NA_ZONA], id="ok"))
    assert c.put("/api/regras/ok", json=regra_json([], op="E")).status_code == 400
    assert c.post("/api/regras", json=regra_json([NA_ZONA], id="pre_inventada")).status_code == 400  # prefixo reservado


def test_api_pre_carregada_nao_se_edita_nem_exclui_mas_se_ativa(api):
    c = _cliente(api, ROLE_TECHNICAL)
    assert c.delete("/api/regras/pre_missing_helmet").status_code == 409
    assert c.delete("/api/regras/pre_missing_helmet").get_json()["code"] == "regra_protegida"
    pre = next(r for r in c.get("/api/regras").get_json()["regras"] if r["id"] == "pre_missing_helmet")
    assert c.put("/api/regras/pre_missing_helmet", json=pre).status_code == 409
    assert c.post("/api/regras/pre_missing_helmet/ativar").get_json()["regra"]["ativa"] is True
    assert {r["id"]: r["ativa"] for r in c.get("/api/regras").get_json()["regras"]}["pre_missing_helmet"] is True
    # duplicar = POST de uma cópia como regra de usuário
    copia = c.post("/api/regras", json=pre | {"id": "copia", "origem": "pre_carregada", "regra_id": "missing_helmet"})
    assert copia.status_code == 201 and copia.get_json()["regra"]["origem"] == "usuario"
    assert copia.get_json()["regra"]["regra_id"] == "regra:copia"


# ---- com o MonitorService real: aplicação no motor e "testar no histórico" ----
@pytest.fixture()
def monitor_api(real_monitor_app, tmp_path):
    from app.api.regras import regras_bp

    if "regras" not in real_monitor_app.blueprints:
        real_monitor_app.register_blueprint(regras_bp)
    real_monitor_app.config["TRILHAS_DIR"] = str(tmp_path)
    cam = Camera(name="Pátio", source_type="Arquivo", source="x.mp4")
    db.session.add(cam)
    db.session.commit()
    monitor = real_monitor_app.extensions["monitor_service"]
    monitor.load_cameras_from_db()
    worker = monitor.worker_da_camera(cam.id)
    # O getter real consultaria o modelo YOLO; aqui todos os EPIs contam como suportados.
    worker.rule_engine.supported_ppe_getter = lambda: set(PPE_KEYS)
    return real_monitor_app, real_monitor_app.test_client(), worker, cam.id


def test_aplicar_regras_entrega_o_avaliador_ao_motor_de_cada_camera(monitor_api):
    app, client, worker, camera_id = monitor_api
    assert worker.rule_engine.avaliador_do_editor is None
    client.post("/api/regras", json=regra_json([SEM_CAPACETE], id="r1"))
    avaliador = worker.rule_engine.avaliador_do_editor
    assert avaliador is not None and [c.regra.id for c in avaliador.regras] == ["r1"]
    assert worker.rule_engine.contexto_do_editor["camera_id"] == camera_id
    detecoes = [_pessoa(2, (100, 100, 200, 400))]
    alertas = worker.rule_engine.analyze(detecoes, None, FRAME).alerts
    assert [a.message for a in alertas if a.rule == "regra:r1"] == ["Alerta de teste · Pessoa 2"]
    client.post("/api/regras/r1/desativar")  # desativada: o motor para de executá-la
    assert worker.rule_engine.avaliador_do_editor is None
    assert not [a for a in worker.rule_engine.analyze(detecoes, None, FRAME).alerts if a.rule.startswith("regra:")]


def test_aplicar_regras_com_monitor_sem_workers_nao_quebra(app, client):
    assert aplicar_regras(app) == 0  # DummyMonitor: sem `_workers`


def test_api_testar_no_historico(monitor_api):
    _app, client, worker, camera_id = monitor_api
    agora = time.time()
    for i in range(30):
        pessoa = {"id": "person_1", "box": {"x1": 100, "y1": 200, "x2": 180, "y2": 400},
                  "ppe": {"helmet": {"status": "missing"}, "vest": {"status": "ok"}}}
        worker.trilhas.registrar(agora - 30 + i, [pessoa], 960, 540)
    corpo = {"camera_id": camera_id, "horas": 1, "regra": {k: v for k, v in regra_json([SEM_CAPACETE]).items() if k not in ("id", "nome")}}
    r = client.post("/api/regras/testar", json=corpo)
    assert r.status_code == 200, r.get_json()
    dados = r.get_json()
    assert dados["simulavel"] is True and dados["disparos"] == 1 and dados["registros"] == 30 and dados["pessoas"] == 1
    assert sum(c for _t, c in dados["linha_do_tempo"]) == 1
    # a regra não é gravada nem aplicada só por ter sido testada
    assert [r_["id"] for r_ in client.get("/api/regras").get_json()["regras"] if r_["origem"] == "usuario"] == []

    nao_simulavel = client.post("/api/regras/testar", json=corpo | {"regra": regra_json([CAIDA])}).get_json()
    assert nao_simulavel["simulavel"] is False and "postura" in nao_simulavel["motivo"]


@pytest.mark.parametrize("corpo, status", [
    ({"horas": 1, "regra": regra_json([NA_ZONA])}, 400),  # sem camera_id
    ({"camera_id": 1, "horas": 0, "regra": regra_json([NA_ZONA])}, 400),
    ({"camera_id": 1, "horas": 25, "regra": regra_json([NA_ZONA])}, 400),
    ({"camera_id": 1, "horas": "x", "regra": regra_json([NA_ZONA])}, 400),
    ({"camera_id": 1, "horas": 1}, 400),  # sem regra
    ({"camera_id": 1, "horas": 1, "regra": regra_json([])}, 400),  # regra inválida
    ({"camera_id": 999, "horas": 1, "regra": regra_json([NA_ZONA])}, 404),
])
def test_api_testar_valida_a_entrada(monitor_api, corpo, status):
    _app, client, _worker, camera_id = monitor_api
    assert camera_id == 1
    assert client.post("/api/regras/testar", json=corpo).status_code == status
