"""Pré-alerta de aproximação: projeção cinemática até a zona de risco."""

from __future__ import annotations

from app.services.aproximacao import EstimadorDeAproximacao, ponto_no_poligono, tempo_ate_entrar

ZONA = [(0.7, 0.1), (0.98, 0.1), (0.98, 0.95), (0.7, 0.95)]


def andar(est, track_id, inicio, velocidade, passos, dt=0.25, t0=0.0):
    x, y = inicio
    for i in range(passos):
        est.atualizar([(track_id, (x + velocidade[0] * dt * i, y + velocidade[1] * dt * i))], t0 + dt * i)


def test_tempo_ate_entrar_em_linha_reta():
    # A 0,2 da borda, a 0,1/s: entra em 2 s.
    assert abs(tempo_ate_entrar((0.5, 0.5), (0.1, 0.0), ZONA) - 2.0) < 1e-9
    assert tempo_ate_entrar((0.5, 0.5), (-0.1, 0.0), ZONA) is None, "andando para longe não entra"


def test_ponto_no_poligono():
    assert ponto_no_poligono((0.8, 0.5), ZONA)
    assert not ponto_no_poligono((0.5, 0.5), ZONA)


def test_quem_caminha_para_a_zona_gera_aviso_com_rotulo_honesto():
    est = EstimadorDeAproximacao(limite_s=3.0)
    andar(est, 7, (0.40, 0.5), (0.1, 0.0), passos=5)  # termina em x=0,50; borda em 0,70
    avisos = est.avisos(ZONA)
    assert [a["track_id"] for a in avisos] == [7]
    assert 1.5 <= avisos[0]["segundos_ate_entrar"] <= 2.5
    assert avisos[0]["metodo"] == "projecao_cinematica"


def test_longe_demais_ou_devagar_nao_avisa():
    est = EstimadorDeAproximacao(limite_s=3.0)
    andar(est, 1, (0.05, 0.5), (0.05, 0.0), passos=5)   # 0,6 de distância a 0,05/s = 12 s
    andar(est, 2, (0.65, 0.5), (0.001, 0.0), passos=5)  # parado na borda
    assert est.avisos(ZONA) == []


def test_quem_ja_esta_dentro_nao_e_aproximacao():
    est = EstimadorDeAproximacao()
    andar(est, 3, (0.75, 0.5), (0.1, 0.0), passos=5)
    assert est.avisos(ZONA) == [], "dentro da zona é o alerta de área de risco, não pré-alerta"


def test_uma_caixa_que_tremeu_nao_basta():
    est = EstimadorDeAproximacao(amostras_minimas=3)
    est.atualizar([(9, (0.5, 0.5))], 0.0)
    est.atualizar([(9, (0.6, 0.5))], 0.25)  # salto num quadro só
    assert est.avisos(ZONA) == []


def test_track_sumido_expira():
    est = EstimadorDeAproximacao(validade_s=2.0)
    andar(est, 4, (0.40, 0.5), (0.1, 0.0), passos=5)
    est.atualizar([], 10.0)
    assert est.avisos(ZONA) == []


def test_analises_espacadas_ainda_projetam():
    """Máquina carregada: uma análise a cada 2 s ainda forma trilha (antes a trilha expirava em 2 s)."""
    est = EstimadorDeAproximacao()
    for i, x in enumerate((0.30, 0.42, 0.54, 0.66)):
        est.atualizar([(5, (x, 0.5))], i * 2.0)
    avisos = est.avisos(ZONA)
    assert [a["track_id"] for a in avisos] == [5]


def test_quem_nao_esta_na_analise_atual_nao_avisa():
    est = EstimadorDeAproximacao()
    andar(est, 4, (0.40, 0.5), (0.1, 0.0), passos=5)
    est.atualizar([(99, (0.1, 0.1))], 10.0)  # a pessoa 4 não foi vista agora
    assert all(a["track_id"] != 4 for a in est.avisos(ZONA))
