# Product Backlog

Itens = requisitos de [../requisitos.md](../requisitos.md) (RF e RNF), com sprint e estado em 23/10/2026. Cada item tem um card no Trello com o título
`RFnn — nome curto` (lista Product Backlog para o que não foi feito; lista da sprint ou Concluído para o resto).

## Como a prioridade foi atribuída

Não existe backlog versionado anterior a esta entrega, então **a priorização abaixo foi feita na consolidação de 23/10 e não é o registro de uma
priorização original**. O critério:

- **Alta:** sem isto o sistema não resolve o problema da Metaindústria (ver o EPI faltando, alertar a tempo, controlar quem vê o quê, saber quem
  recebeu que EPI) ou compromete confiança e segurança dos dados.
- **Média:** sustenta a operação, a medição e a confiança no resultado.
- **Baixa:** diferencial, útil na apresentação e na operação avançada, mas o problema se resolve sem ele.

Dentro de cada faixa a ordem segue o fluxo do problema: ver, decidir, notificar, registrar.

## Prioridade alta

| ID | Item | Sprint | Estado |
|---|---|---|---|
| RF01 | Detectar EPIs por câmera em tempo real | S1 | Concluído |
| RF02 | Detectar pessoas e rastreá-las com ID estável | S1 | Concluído |
| RF03 | Associar EPI a pessoa e dar um estado por EPI | S1 | Concluído |
| RF16 | Uso incorreto e protetor auricular | S4 | Concluído |
| RF17 | Estado "não verificado" (ausente não é não visto) | S4 | Concluído |
| RF05 | Pose por pessoa: queda e postura suspeita | S2 | Concluído |
| RF06 | Alertar presença na zona de risco | S2 | Concluído |
| RF07 | Severidade explícita por regra | S3 | Concluído |
| RF08 | Ciclo de vida do alerta com histerese | S3 | Concluído |
| RF09 | Notificação visual e sonora | S3 | Concluído |
| RF11 | Login com três papéis, em REST e WebSocket | S3 | Concluído |
| RF12 | Multicâmera e escopo do operador | S3 | Concluído |
| RF13 | Painel por perfil em tempo real | S3 | Concluído |
| RF41 | Colaboradores e histórico de EPIs | S4 | Concluído |
| RF42 | Catálogo de EPIs com CA e validade | S4 | Concluído |
| RF43 | Entregas e devoluções de EPI | S4 | Concluído |
| RF44 | Ocorrências de segurança | S4 | Concluído |
| RF45 | Exportação CSV | S4 | Concluído |
| RF46 | Seed idempotente da Gestão | S4 | Concluído |
| RF47 | Permissões da Gestão | S4 | Concluído |
| RF38 | Modo demonstração offline | S4 | Concluído |
| RF50 | Dataset anotado da planta (única forma de afirmar acurácia lá) | S4 | Planejado, não feito |
| RNF01 | Privacidade por setor, nunca por pessoa | S4 | Concluído |
| RNF02 | Controle de acesso verificado | S4 | Concluído |
| RNF03 | Segredos fora do repositório | S4 | Concluído |
| RNF04 | Caminho do frame sem espera | S4 | Concluído |

## Prioridade média

| ID | Item | Sprint | Estado |
|---|---|---|---|
| RF04 | Zona de risco por câmera | S1 | Concluído |
| RF10 | Modo portaria | S3 | Concluído |
| RF14 | Reconexão com backoff | S3 | Concluído |
| RF15 | Modo fixture visível | S4 | Concluído |
| RF18 | Segunda opinião do LLM | S4 | Concluído |
| RF19 | Avaliação por pessoa | S4 | Concluído |
| RF20 | Incidentes e linha causal | S4 | Concluído |
| RF21 | Cadeia de custódia | S4 | Concluído |
| RF23 | Queda por ID e pré-alerta de aproximação | S4 | Concluído |
| RF27 | Saúde visual da câmera | S4 | Concluído |
| RF28 | Fábrica conectada (OPC UA, MQTT, webhook) | S4 | Concluído |
| RF29 | Modo Evacuação | S4 | Concluído |
| RF31 | Permissão de trabalho com vigia | S4 | Concluído |
| RF32 | Relatórios de turno e mensal | S4 | Concluído |
| RF35 | Área de detecção por câmera | S4 | Concluído |
| RF37 | Status do sistema e API documentada | S4 | Concluído |
| RF39 | Amostra de vídeo versionada | S4 | Concluído |
| RF40 | Fallback do LLM na demo | S4 | Concluído |
| RF48 | Notificação por Telegram | S3 | Planejado, não feito |
| RF49 | Medir o LLM no conjunto anotado | S4 | Planejado, não feito |
| RF53 | Agrupar alertas por pessoa na multidão | S4 | Planejado, não feito |
| RNF05 | Guarda de concordância para trocar runtime | S4 | Concluído |
| RNF06 | Operação offline | S4 | Concluído |
| RNF07 | Esquema sob Alembic | S4 | Concluído |
| RNF08 | Design system e acessibilidade | S4 | Concluído |
| RNF09 | Degradação explícita | S4 | Concluído |
| RNF10 | Instalação reproduzível | S4 | Concluído |
| RNF12 | Dado simulado rotulado | S4 | Concluído |
| RNF14 | Portão de qualidade | S4 | Concluído |

## Prioridade baixa

| ID | Item | Sprint | Estado |
|---|---|---|---|
| RF22 | Replay do incidente com rosto desfocado | S4 | Concluído |
| RF24 | Gêmeo digital e mapa de calor | S4 | Concluído |
| RF25 | Simulador "E se?" | S4 | Concluído |
| RF26 | Portal de Entrada e "Você vs. a IA" | S4 | Concluído |
| RF30 | Editor de regras sem código | S4 | Concluído |
| RF33 | Liga de Setores, Modo TV e retrospectiva | S4 | Concluído |
| RF34 | Modo Apresentação | S4 | Concluído |
| RF36 | Celular como câmera | S4 | Concluído |
| RF51 | Pose por pessoa em modo stream (ganho de 2,25x medido) | S4 | Planejado, não feito |
| RF52 | Parâmetros da câmera em runtime | S4 | Planejado, não feito |
| RNF11 | Licenças e atribuições | S4 | Concluído |
| RNF13 | Textos pt-BR consistentes | S4 | Concluído |

## Contagem (conferível contra `docs/requisitos.md`)

53 requisitos funcionais e 14 não funcionais. Dos RF: 6 planejados e não feitos (RF48 a RF53), 8 "em implementação" na data (RF39 e RF41 a RF47: código e testes existem no disco, execução verde a confirmar na ata), 39 concluídos.
Dos RNF: 1 em implementação (RNF12), 13 concluídos. "Concluído" quer dizer que há código, teste e evidência no repositório; a avaliação do avaliador ainda
vem depois (ver `ata-review-final-sprint4.md`).

## Fora do backlog por decisão

- Mesclar `feat/completo-com-rebrand` na entrega (desnecessário: o conteúdo já entrou na `main` pelo squash do PR7, `a6d303b`; ver `docs/specs/ESTADO-es-sprint4.md`).
- Reconhecimento facial e qualquer vínculo entre colaborador e ID de rastreio (ADR 0005 e 0008).
