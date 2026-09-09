"""Integração assíncrona da camada LLM: o que impede o demo de travar.

O pipeline já satura a CPU — 19,56 fps com uma câmera (`docs/BENCH.md`). Uma
chamada de rede de segundos dentro do loop de captura congelaria o vídeo. E
depois do fix da Fase 1 a fixture de 7 s ainda gera 26 alertas: chamar o
Gemini em cada um estoura a cota do free tier e inunda a tela.

Daí as três regras que este arquivo trava:

1. **Nunca no caminho do frame.** `submeter()` retorna imediatamente; quem
   executa é o executor injetado.
2. **No máximo uma em voo por câmera.** Chegou outra enquanto a primeira não
   voltou? **Descarta** — não enfileira. Fila só empurra o atraso para frente
   e, num alerta que se repete, cresce sem limite.
3. **Debounce por janela de tempo, por câmera.** Duas câmeras não competem
   entre si.

Tudo determinístico: executor e relógio são injetados, e nenhum teste toca a
rede.
"""

from __future__ import annotations

import json

from app.llm import AnalisadorDeRisco, AnaliseRisco, ProvedorFake
from app.services.llm_risk_service import ServicoDeRiscoLLM

RESPOSTA = json.dumps(
    {
        "nivel_risco": "alto",
        "epis_ausentes": ["helmet"],
        "justificativa": "Trabalhador sem capacete proximo a escavadeira em operacao.",
        "confianca": 0.77,
        "acao_recomendada": "Interromper e fornecer capacete.",
    }
)


class Relogio:
    """Relógio controlado: nada de `sleep` em teste."""

    def __init__(self) -> None:
        self.agora = 1000.0

    def __call__(self) -> float:
        return self.agora

    def avanca(self, segundos: float) -> None:
        self.agora += segundos


class ExecutorImediato:
    """Roda a tarefa na hora, mas ainda pelo caminho do executor."""

    def __init__(self) -> None:
        self.tarefas = 0

    def __call__(self, funcao) -> None:
        self.tarefas += 1
        funcao()


class ExecutorQueSegura:
    """Guarda a tarefa sem rodar — simula chamada AINDA em voo."""

    def __init__(self) -> None:
        self.pendentes: list = []

    def __call__(self, funcao) -> None:
        self.pendentes.append(funcao)

    def liberar(self) -> None:
        pendentes, self.pendentes = self.pendentes, []
        for funcao in pendentes:
            funcao()


def servico(provedor_resposta=RESPOSTA, *, executor=None, relogio=None, debounce=15.0):
    return ServicoDeRiscoLLM(
        analisador=AnalisadorDeRisco(provedor=ProvedorFake(provedor_resposta)),
        executor=executor or ExecutorImediato(),
        relogio=relogio or Relogio(),
        debounce_s=debounce,
        versao="v1",
    )


# ------------------------------------------------------- caminho aceito ----
def test_primeira_submissao_e_aceita_e_produz_analise():
    recebidas = []
    svc = servico()
    svc.ao_concluir = recebidas.append

    assert svc.submeter(camera_id=1, imagem_jpeg=b"jpeg") is True
    assert svc.aceitos == 1
    assert len(recebidas) == 1
    assert isinstance(recebidas[0], AnaliseRisco)
    assert recebidas[0].nivel_risco == "alto"


def test_submeter_nao_bloqueia_o_chamador():
    """Com executor que segura a tarefa, `submeter` volta na hora."""
    executor = ExecutorQueSegura()
    svc = servico(executor=executor)

    assert svc.submeter(camera_id=1, imagem_jpeg=b"jpeg") is True
    assert svc.em_voo(1) is True, "a tarefa nem rodou ainda"
    assert executor.pendentes, "a tarefa foi para o executor, nao para a thread do chamador"


# ------------------------------------------------------------- descarte ----
def test_segunda_submissao_com_uma_em_voo_e_descartada():
    """Descarta, nao enfileira. Fila cresceria sem limite num alerta repetido."""
    executor = ExecutorQueSegura()
    svc = servico(executor=executor)

    assert svc.submeter(camera_id=1, imagem_jpeg=b"a") is True
    assert svc.submeter(camera_id=1, imagem_jpeg=b"b") is False
    assert svc.submeter(camera_id=1, imagem_jpeg=b"c") is False

    assert svc.aceitos == 1
    assert svc.descartados_em_voo == 2
    assert len(executor.pendentes) == 1, "nada foi enfileirado"


def test_em_voo_e_liberado_depois_da_conclusao():
    executor = ExecutorQueSegura()
    relogio = Relogio()
    svc = servico(executor=executor, relogio=relogio)

    svc.submeter(camera_id=1, imagem_jpeg=b"a")
    executor.liberar()

    assert svc.em_voo(1) is False
    relogio.avanca(99.0)
    assert svc.submeter(camera_id=1, imagem_jpeg=b"b") is True


def test_debounce_descarta_dentro_da_janela():
    relogio = Relogio()
    svc = servico(relogio=relogio, debounce=15.0)

    assert svc.submeter(camera_id=1, imagem_jpeg=b"a") is True

    relogio.avanca(5.0)
    assert svc.submeter(camera_id=1, imagem_jpeg=b"b") is False
    relogio.avanca(9.0)
    assert svc.submeter(camera_id=1, imagem_jpeg=b"c") is False
    assert svc.descartados_debounce == 2

    relogio.avanca(2.0)  # total 16 s > 15 s
    assert svc.submeter(camera_id=1, imagem_jpeg=b"d") is True
    assert svc.aceitos == 2


def test_cameras_sao_independentes():
    """Debounce e 'em voo' sao POR camera: uma nao pode calar a outra."""
    executor = ExecutorQueSegura()
    svc = servico(executor=executor)

    assert svc.submeter(camera_id=1, imagem_jpeg=b"a") is True
    assert svc.submeter(camera_id=2, imagem_jpeg=b"b") is True
    assert svc.submeter(camera_id=1, imagem_jpeg=b"c") is False

    assert svc.aceitos == 2
    assert svc.descartados_em_voo == 1


# ---------------------------------------------------------- degradacao -----
def test_analise_invalida_nao_chega_no_callback():
    """Resposta fora do schema nao pode virar alerta. Nao chama o callback."""
    recebidas = []
    svc = servico("isso nao e json nenhum")
    svc.ao_concluir = recebidas.append

    assert svc.submeter(camera_id=1, imagem_jpeg=b"jpeg") is True
    assert recebidas == []
    assert svc.invalidos == 1
    assert svc.em_voo(1) is False, "mesmo invalida, a analise tem que liberar o slot"


def test_excecao_no_callback_nao_escapa_nem_trava_o_slot():
    """Bug no consumidor nao pode derrubar o worker nem travar a camera."""

    def explode(_analise):
        raise RuntimeError("bug de quem consome")

    svc = servico()
    svc.ao_concluir = explode

    assert svc.submeter(camera_id=1, imagem_jpeg=b"jpeg") is True
    assert svc.em_voo(1) is False
    assert svc.erros_de_callback == 1


def test_servico_desligado_descarta_tudo_sem_chamar_provedor():
    """`LLM_ENABLED=false` e o estado normal de quem nao tem chave."""
    provedor = ProvedorFake(RESPOSTA)
    svc = ServicoDeRiscoLLM(
        analisador=AnalisadorDeRisco(provedor=provedor),
        executor=ExecutorImediato(),
        relogio=Relogio(),
        debounce_s=15.0,
        versao="v1",
        habilitado=False,
    )

    assert svc.submeter(camera_id=1, imagem_jpeg=b"jpeg") is False
    assert svc.aceitos == 0
    assert provedor.chamadas == [], "desligado nao pode nem construir a chamada"


def test_estatisticas_expostas_para_o_relatorio():
    executor = ExecutorQueSegura()
    svc = servico(executor=executor)
    svc.submeter(camera_id=1, imagem_jpeg=b"a")
    svc.submeter(camera_id=1, imagem_jpeg=b"b")

    estatisticas = svc.estatisticas()
    assert estatisticas["aceitos"] == 1
    assert estatisticas["descartados_em_voo"] == 1
    assert estatisticas["descartados_debounce"] == 0
    assert estatisticas["invalidos"] == 0
    assert estatisticas["habilitado"] is True
