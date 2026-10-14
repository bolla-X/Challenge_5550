"""Rodízio ponderado do agendador (MISSÃO 2, P0.1).

A câmera em foco na UI recebe pelo menos 50 % das inferências; as outras
dividem o resto e nenhuma fica mais de `espera_max_s` sem análise. O teste
chama `_escolher` direto, com relógio simulado: cada inferência "custa" um
passo fixo, e todas as câmeras têm sempre um quadro novo esperando — o pior
caso de disputa, como 4 câmeras de gravação ligadas.
"""

from __future__ import annotations

from collections import Counter

import pytest
from app.services.agendador_de_inferencia import AgendadorDeInferencia, _Slot


def _nada(*_args):
    return None


class _Relogio:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def _simular(focadas: set[int], *, cameras=(1, 2, 3, 4), custo_s=0.4, passos=600, espera_max_s=2.5):
    relogio = _Relogio()
    ag = AgendadorDeInferencia(focadas=lambda: focadas, espera_max_s=espera_max_s, relogio=relogio)
    # Sem thread: monta os slots como `registrar` faria (ele também liga o laço).
    for cid in cameras:
        slot = _Slot(cid, _nada, _nada)
        slot.ultimo_servico = relogio.t
        ag._slots[cid] = slot
        ag._ordem.append(cid)
    ordem: list[tuple[float, int]] = []
    for _ in range(passos):
        for slot in ag._slots.values():
            slot.pendente = True  # sempre há quadro novo
        with ag._cond:
            escolhidos = ag._escolher()
        assert len(escolhidos) == 1
        ordem.append((relogio.t, escolhidos[0].camera_id))
        relogio.t += custo_s
    return ordem, ag


def _maior_espera(ordem: list[tuple[float, int]], cid: int) -> float:
    tempos = [t for t, c in ordem if c == cid]
    return max(b - a for a, b in zip(tempos, tempos[1:], strict=False))


def test_sem_foco_divide_igual():
    ordem, _ = _simular(set())
    contagem = Counter(c for _, c in ordem)
    assert max(contagem.values()) - min(contagem.values()) <= 1


def test_camera_em_foco_recebe_pelo_menos_metade():
    ordem, ag = _simular({2})
    contagem = Counter(c for _, c in ordem)
    assert contagem[2] / len(ordem) >= 0.5, contagem
    # As outras dividem o resto por igual (±1).
    outras = [contagem[c] for c in (1, 3, 4)]
    assert max(outras) - min(outras) <= 1, contagem
    assert ag.estado()["em_foco"] == [2]
    assert ag.estado()["por_camera"]["2"]["servidos_em_foco"] == contagem[2]


def test_nenhuma_camera_fica_mais_de_3_s_sem_inferencia():
    # Inferência de 0,5 s (pior p50 medido com 4 câmeras no PR3): o ciclo
    # ponderado sozinho já serve cada outra a cada 3 s; a guarda segura o resto.
    ordem, _ = _simular({1}, custo_s=0.5)
    for cid in (2, 3, 4):
        assert _maior_espera(ordem, cid) <= 3.0, (cid, _maior_espera(ordem, cid))


def test_inferencia_lenta_foco_vence_e_as_outras_tem_espera_limitada():
    """Com 0,9 s por inferência não dá para ter foco ≥ 50 % E cada outra a cada 3 s.

    Decisão (CHANGELOG, P0.1): o foco vence; as outras continuam em rodízio,
    com espera limitada a uma volta (2 × 3 vagas), nunca paradas.
    """
    ordem, _ = _simular({1}, custo_s=0.9)
    contagem = Counter(c for _, c in ordem)
    assert contagem[1] / len(ordem) >= 0.5, contagem
    for cid in (2, 3, 4):
        assert _maior_espera(ordem, cid) <= 2 * 3 * 0.9 + 1e-6, cid


def test_duas_cameras_em_foco_dividem_a_metade_do_foco():
    ordem, _ = _simular({1, 2})
    contagem = Counter(c for _, c in ordem)
    assert (contagem[1] + contagem[2]) / len(ordem) >= 0.5
    assert abs(contagem[1] - contagem[2]) <= 1


def test_so_cameras_pendentes_sao_servidas():
    relogio = _Relogio()
    ag = AgendadorDeInferencia(focadas=lambda: {1}, relogio=relogio)
    for cid in (1, 2):
        ag._slots[cid] = _Slot(cid, _nada, _nada)
        ag._ordem.append(cid)
    ag._slots[2].pendente = True
    with ag._cond:
        escolhidos = ag._escolher()
    assert [s.camera_id for s in escolhidos] == [2]
    with ag._cond:
        assert ag._escolher() == []


def test_fonte_de_foco_com_erro_nao_para_o_agendador():
    def explode():
        raise RuntimeError("socket fora")

    ag = AgendadorDeInferencia(focadas=explode)
    ag._slots[1] = _Slot(1, _nada, _nada)
    ag._ordem.append(1)
    ag._slots[1].pendente = True
    with ag._cond:
        assert [s.camera_id for s in ag._escolher()] == [1]


def test_monitor_considera_video_aberto_e_consulta_do_portal():
    from types import SimpleNamespace

    from app.services.monitor_service import MonitorService

    monitor = SimpleNamespace(espectadores={}, _foco_lease={}, _foco_lease_s=3.0)
    assert MonitorService.cameras_em_foco(monitor) == set()
    monitor.espectadores[7] = 1
    MonitorService.marcar_foco(monitor, 9)
    assert MonitorService.cameras_em_foco(monitor) == {7, 9}
    monitor.espectadores[7] = 0
    monitor._foco_lease[9] = 0.0  # lease vencido
    assert MonitorService.cameras_em_foco(monitor) == set()


def test_prioridade_de_confirmacao_e_uma_vaga_so():
    """Análise com sinal de queda: a próxima vaga é da câmera dela, mesmo fora de foco — só UMA."""
    relogio = _Relogio()
    ag = AgendadorDeInferencia(focadas=lambda: {1}, relogio=relogio)
    for cid in (1, 2, 3, 4):
        ag._slots[cid] = _Slot(cid, _nada, _nada)
        ag._ordem.append(cid)
    ag.priorizar(3, 2.0)
    servidos = []
    for _ in range(4):
        for slot in ag._slots.values():
            slot.pendente = True
        with ag._cond:
            servidos.append(ag._escolher()[0].camera_id)
        relogio.t += 0.4
    assert servidos[0] == 3
    assert servidos[1:].count(3) == 0 or servidos[1] != 3  # não monopoliza
    assert servidos.count(1) >= 2  # o foco segue com a metade


def test_maquina_lenta_o_foco_ainda_fica_com_metade():
    """Com 1,4 s por inferência a guarda das outras dispararia sempre; o foco não cai a 1/4."""
    ordem, _ = _simular({2}, custo_s=1.4)
    contagem = Counter(c for _, c in ordem)
    assert contagem[2] / len(ordem) >= 0.5, contagem
    outras = [contagem[c] for c in (1, 3, 4)]
    assert min(outras) > 0 and max(outras) - min(outras) <= 1, contagem  # ninguém para de ser servido


def test_em_prioridade_acaba_sozinha():
    relogio = _Relogio()
    ag = AgendadorDeInferencia(relogio=relogio)
    ag.priorizar(7, 2.0)
    assert ag.em_prioridade(7) and not ag.em_prioridade(8)
    relogio.t = 2.01
    assert not ag.em_prioridade(7)


def test_estado_informa_a_maior_espera_de_cada_camera():
    ordem, ag = _simular({1}, custo_s=0.5)
    for cid in (2, 3, 4):
        assert ag.estado()["por_camera"][str(cid)]["maior_espera_s"] == pytest.approx(_maior_espera(ordem, cid))


def test_fracao_do_foco_configuravel_ate_70_por_cento():
    """ADENDO 2: o foco pode levar até 70 % das vagas quando ninguém está atrasado."""
    ag = AgendadorDeInferencia(focadas=lambda: {1}, fracao_foco=0.7)
    for cid in (1, 2, 3, 4):
        ag.registrar(cid, lambda f, m: None, lambda r, t: None)
    ag.parar()
    pesos = ag.pesos({1})
    assert pesos[1] / sum(pesos.values()) == pytest.approx(0.7)
    assert AgendadorDeInferencia(fracao_foco=0.95).fracao_foco == 0.7  # teto
    assert AgendadorDeInferencia(fracao_foco=0.1).fracao_foco == 0.5  # piso: o foco nunca abaixo de 50 %
