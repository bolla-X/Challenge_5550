# Registros de decisão de arquitetura (ADRs)

Formato de cada ADR: título, status, data, contexto, decisão, consequências, alternativas. A **data** é a do commit que introduziu a
decisão (veja `docs/specs/gitlog-main.txt`); quando a decisão entrou na `main` por um squash, vale a data do squash e o ADR diz isso. As
decisões desta sprint levam 23/10/2026.

| ADR | Decisão | Status | Data |
|---|---|---|---|
| [0001](0001-flask-socketio-spa-react.md) | Flask + Socket.IO no backend, SPA React servida pelo próprio Flask | aceito | 05/08/2026 |
| [0002](0002-yolo-vyra-e-detector-de-pessoa.md) | YOLO Vyra para EPI + detector de pessoa dedicado (`MULTI_PERSON_DETECTION=true`) | aceito | 09/09/2026 |
| [0003](0003-llm-segunda-opiniao-assincrona.md) | LLM como segunda opinião assíncrona que nunca cria alerta | aceito | 09/09/2026 |
| [0004](0004-alembic-dono-do-esquema.md) | Alembic é o dono do esquema do banco | aceito | 08/09/2026 |
| [0005](0005-privacidade-por-setor-nunca-por-pessoa.md) | Privacidade "por setor, nunca por pessoa" | aceito | 14/10/2026 |
| [0006](0006-runtime-openvino-onnx-com-guarda-de-concordancia.md) | Runtime OpenVINO/ONNX só entre exports aprovados por um guarda de concordância | aceito | 14/10/2026 |
| [0007](0007-modo-demonstracao-offline-banco-isolado.md) | Modo demonstração offline com banco isolado | aceito | 14/10/2026 |
| [0008](0008-gestao-de-epis-cadastro-separado-da-visao.md) | Gestão de EPIs como cadastro administrativo separado da visão | aceito (testes escritos, execução a confirmar) | 23/10/2026 |
| [0009](0009-fallback-deterministico-do-llm-so-na-demo.md) | Fallback determinístico do LLM só na demo | aceito | 23/10/2026 |
| [0010](0010-amostra-de-video-versionada-cc-by-sa.md) | Amostra de vídeo versionada sob CC BY-SA 4.0 | aceito (sem teste dedicado) | 23/10/2026 |

## Como ler as datas

- 0001 a 0004 têm commit próprio na `main` (hash no cabeçalho de cada ADR).
- 0005 a 0007 chegaram à `main` pelo squash do PR7 (`a6d303b`, 14/10/2026). A decisão foi tomada nos PRs 1 a 6 da branch do NEXT 2026,
  cujos commits individuais não estão na `main`; por isso a data é a do squash.
- 0008 a 0010 são desta entrega (ES Sprint 4, 23/10/2026).

Visão geral da arquitetura: [../arquitetura.md](../arquitetura.md). Requisitos e rastreabilidade: [../requisitos.md](../requisitos.md).
