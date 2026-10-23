# Requisitos e rastreabilidade — VisionEPI

Requisitos funcionais (RF) e não funcionais (RNF) do VisionEPI, com a matriz **RF → card do Trello → código → teste → sprint**.
Board: https://trello.com/b/zVZW2n1p/visionepi-challenge-3ecr. Cada requisito tem um card com o título exato da coluna "Card Trello".

## Como ler

- **Sprints** são as do Challenge, que a disciplina adotou (`docs/scrum/README.md`): S1 16/04 a 04/05, S2 05/05 a 22/06, S3 23/06 a 24/08,
  S4 25/08 a 23/10/2026. Os requisitos foram numerados na consolidação de 23/10; não existia lista numerada antes (não há backlog versionado
  anterior). A sprint de cada um segue o documento de fase ou o commit que o entregou.
- **Estado:** `Concluído` (há código, teste e evidência no repositório), `Em implementação` (itens desta sprint: código, tela e testes já existem no disco em
  23/10, mas **não executei os testes**; a execução verde fica registrada na [ata](scrum/ata-review-final-sprint4.md)), `Planejado` (não implementado; está aqui para
  ficar visível).
- **Caminhos** foram conferidos no repositório em 23/10/2026 (Glob e Grep), inclusive `tests/test_gestao_epi.py`, `tests/test_gestao_seed.py` e `e2e/test_es_sprint4.py`,
  que surgiram durante a redação. Onde diz "sem teste dedicado", o teste não existe.
- Onde um requisito foi medido, a fonte está na coluna "Evidência" da seção seguinte, nunca na matriz.

## Requisitos funcionais

| ID | Requisito | Sprint | Estado | Evidência / fonte |
|---|---|---|---|---|
| RF01 | Detectar EPIs por câmera em tempo real (capacete, colete, luvas, óculos, máscara, calçado) | S1 | Concluído | `docs/challenge/FASE1-DETECCAO-DE-EPIS.md` §3 (mAP@0,5 por classe; nenhuma atinge 0,75) |
| RF02 | Detectar pessoas e rastreá-las com ID estável (ID de rastreio, não identidade) | S1 | Concluído | FASE1 §3.2 (pessoa: mAP@0,5 = 0,740); `docs/NEXT2026/CHANGELOG.md` §4.5 (comparação de trackers) |
| RF03 | Associar cada EPI a uma pessoa de forma exclusiva e dar um estado por EPI | S1 | Concluído | FASE1 §2 (associação geométrica exclusiva) |
| RF04 | Configurar a zona de risco por câmera, desenhada no vídeo | S1 | Concluído | FASE1 §2; migração `cd57c8841519` |
| RF05 | Estimar pose por pessoa: queda e postura suspeita | S2 | Concluído | `docs/challenge/FASE2-POSE-ESTIMATION.md` §2 e §3 (19 testes da lógica; PCK não medido) |
| RF06 | Alertar presença de pessoa na zona de risco | S2 | Concluído | FASE2 §2 (centro da caixa dentro do polígono) |
| RF07 | Severidade explícita por regra (`critical`, `high`, `medium`, `low`, `info`) | S3 | Concluído | `docs/challenge/FASE3-NOTIFICACAO-INTELIGENTE.md` §2.1 |
| RF08 | Ciclo de vida do alerta com histerese (cria e resolve após N confirmações) | S3 | Concluído | FASE3; histerese passou a contar detecção, não iteração (`b834d7d`, `f379910`, 09/09) |
| RF09 | Notificação por dois canais: visual no painel e sonoro no campo | S3 | Concluído | FASE3 §2.2 (terceiro canal, Telegram, é o RF48) |
| RF10 | Modo portaria: libera só com todos os EPIs exigidos; na dúvida, nega | S3 | Concluído | FASE3 §2.4 (nega em 3 quadros, libera em 8) |
| RF11 | Autenticação com três papéis (operador, técnico, supervisor) em REST e WebSocket | S3 | Concluído | commits `6bfeb41`, `4a0e039` (24/08); README, "Autenticação e papéis" |
| RF12 | Multicâmera: um worker por câmera, escopo do operador à câmera do setor | S3 | Concluído | commits `bd6e016`, `aa852cc`, `204206f`, `2d74e96` (23 e 24/08) |
| RF13 | Painel em tempo real por perfil (grade, foco, quiosque do operador) | S3 | Concluído | FASE3 §2.3 |
| RF14 | Reconexão automática da fonte de vídeo com backoff e teto | S3 | Concluído | commit `c24c011` (24/08); README, Roadmap |
| RF15 | Modo fixture visível: fonte morta passa a tocar uma gravação, rotulada na tela | S4 | Concluído | commit `6dcccb5` (09/09); README, diagrama |
| RF16 | Estado "uso incorreto" e protetor auricular (7ª classe) | S4 | Concluído | `docs/challenge/FASE4-VALIDACAO-INDUSTRIAL.md` §5 (testado ao vivo, webcam) |
| RF17 | Estado "não verificado" e política `PPE_MISSING_POLICY` (ausente não é não visto) | S4 | Concluído | `docs/SPRINT4.md` §5 (F1 médio: ausência 0,83 x evidência 0,62) |
| RF18 | Segunda opinião de um LLM multimodal, assíncrona, que nunca cria alerta | S4 | Concluído | `docs/SPRINT3.md` (FPS -0,4 %); ADR 0003; **não medido** em conjunto anotado |
| RF19 | Avaliar o alerta por pessoa em conjunto anotado, com IC por cenas | S4 | Concluído | `docs/SPRINT4.md` §6 (precisão "sem capacete" 0,39 para 0,85) |
| RF20 | Agrupar alertas em incidentes e contar a linha causal só com o registrado | S4 | Concluído | README, destaques; CHANGELOG do NEXT |
| RF21 | Cadeia de custódia SHA-256 das evidências, com verificação | S4 | Concluído | README, destaques |
| RF22 | Replay do incidente com rosto desfocado | S4 | Concluído | README; `e2e/test_fluxos.py::test_replay_do_incidente_abre_e_toca` |
| RF23 | Queda atribuída a um ID de rastreio e pré-alerta de aproximação da zona | S4 | Concluído | CHANGELOG do NEXT, F2 e F3 |
| RF24 | Gêmeo digital 3D e 2D da planta e mapa de calor | S4 | Concluído | README; galeria `docs/NEXT2026/galeria/` |
| RF25 | Simulador "E se?" sobre o histórico, sem tocar nos alertas reais | S4 | Concluído | README |
| RF26 | Portal de Entrada e "Você vs. a IA" (EPI confirmado, faltando ou não verificável, com o porquê) | S4 | Concluído | `docs/NEXT2026/DEMO.md` (Liberado p50 3,5 s, p95 5,9 s na cena do palco) |
| RF27 | Saúde visual da câmera (obstruída, movida, escura, ofuscada, desfocada) | S4 | Concluído | CHANGELOG, M1 (3,8 s até OBSTRUÍDA, 9,9 s até o alerta) |
| RF28 | Fábrica conectada: OPC UA, MQTT, webhook com proteção SSRF e torre de luz | S4 | Concluído | `docs/NEXT2026/INTEGRACAO.md`; CHANGELOG, M2 |
| RF29 | Modo Evacuação: contagem por câmera e zona, cronômetro, relatório na custódia | S4 | Concluído | CHANGELOG, M3 |
| RF30 | Editor de regras sem código, compilado para o mesmo motor, com teste no histórico | S4 | Concluído | CHANGELOG, M4 |
| RF31 | Permissão de trabalho com vigia (NR-33): a câmera auxilia, não substitui | S4 | Concluído | CHANGELOG, "Fontes verificadas" e M5 |
| RF32 | Relatório de turno (NR-6) e relatório mensal para a CIPA | S4 | Concluído | CHANGELOG, M10; `e2e/test_fluxos.py::test_relatorio_de_turno_abre` |
| RF33 | Liga de Setores, Modo TV e retrospectiva, só com indicadores positivos e por setor | S4 | Concluído | README; `docs/NEXT2026/GLOSSARIO.md` |
| RF34 | Modo Apresentação (palco) com controle pelo celular | S4 | Concluído | `docs/NEXT2026/DEMO.md` (18 cenas) |
| RF35 | Área de detecção por câmera (só ali o sistema procura pessoas) | S4 | Concluído | CHANGELOG, MISSÃO 7 (0 pessoas fora da área; sem ganho de tempo) |
| RF36 | Celular como câmera, via QR e HTTPS local | S4 | Concluído | CHANGELOG, F6 |
| RF37 | Página de status do sistema e API documentada (`/api/docs`) | S4 | Concluído | README, MISSÃO 4 |
| RF38 | Modo demonstração reprodutível, offline, com banco isolado e contas geradas | S4 | Concluído | ADR 0007; `e2e/fumaca_demo.py` 6/6 (CHANGELOG, Entrega MISSÃO 4) |
| RF39 | Amostra de vídeo versionada para a demo subir sem baixar gravações | S4 | Em implementação | ADR 0010; `app/demo.py` já chama `fonte_da_gravacao`; sem teste dedicado e sem prova de subida num clone sem as gravações |
| RF40 | Fallback determinístico do LLM na demo, sinalizado como "modo demonstração" | S4 | Concluído | ADR 0009; `tests/test_llm_demo_fallback.py` |
| RF41 | Colaboradores com histórico de EPIs (busca, filtro por setor, detalhe, cadastro e edição) | S4 | Em implementação | contrato `docs/specs/es-sprint4-contrato-gestao.md` |
| RF42 | Catálogo de EPIs com CA, validade do CA, fabricante e vida útil; situação do CA | S4 | Em implementação | idem |
| RF43 | Entregas e devoluções de EPI; bloqueio de entrega com CA vencido ou para colaborador desligado; troca prevista | S4 | Em implementação | idem |
| RF44 | Ocorrências de segurança (tipo, gravidade, status, ação corretiva) | S4 | Em implementação | idem |
| RF45 | Exportação CSV de colaboradores, EPIs, entregas, ocorrências e alertas | S4 | Em implementação | idem |
| RF46 | Seed idempotente de dados simulados da Metaindústria, automático na demo ou por comando | S4 | Em implementação | idem (`flask --app wsgi gestao semear`) |
| RF47 | Permissões da Gestão: técnico lê e registra, supervisor cadastra, operador recebe 403 | S4 | Em implementação | idem |
| RF48 | Notificação por Telegram (terceiro canal) | S3 | Planejado | FASE3 §2.2: "planejado, não implementado" |
| RF49 | Medir o LLM no conjunto anotado (`scripts/avaliar_llm_dataset.py`, pronto) | S4 | Planejado | `docs/SPRINT4.md` §8: falta rodar com chave |
| RF50 | Dataset anotado das câmeras da planta, por duas pessoas | S4 | Planejado | README, Roadmap; SPRINT4 §8 |
| RF51 | Pose por pessoa com instância própria em modo de stream (ganho medido de 2,25x, não aplicado) | S4 | Planejado | README, Roadmap; `docs/SPRINT3.md` |
| RF52 | Parâmetros da câmera em runtime sem reconstruir o worker | S4 | Planejado | README, Roadmap |
| RF53 | Agrupar por pessoa o ruído de alertas na multidão (5 por pessoa) | S4 | Planejado | README, Roadmap |

## Requisitos não funcionais

| ID | Requisito | Sprint | Estado | Evidência / fonte |
|---|---|---|---|---|
| RNF01 | Privacidade: por setor, nunca por pessoa; desfoque de rosto em toda saída; sem reconhecimento facial | S4 | Concluído | ADR 0005 |
| RNF02 | Controle de acesso verificado endpoint a endpoint e evento a evento | S4 | Concluído | CHANGELOG, "matriz de permissões" (1.403 casos; 8 divergências achadas e corrigidas) |
| RNF03 | Segredos fora do repositório e das saídas (chave do Google, credencial RTSP, `SECRET_KEY`) | S4 | Concluído | commit `9737ad4` (credencial RTSP redigida, 09/09); README, "Autenticação e papéis" |
| RNF04 | O caminho do frame nunca espera por rede ou LLM | S4 | Concluído | ADR 0003; `docs/BENCH.md` |
| RNF05 | Troca de runtime ou de resolução só com concordância mínima contra a referência | S4 | Concluído | ADR 0006 |
| RNF06 | Operar offline depois de um preparo com internet | S4 | Concluído | `docs/NEXT2026/DEMO.md`; ADR 0007 |
| RNF07 | Esquema do banco sob migração (Alembic) | S4 | Concluído | ADR 0004 |
| RNF08 | Design system único, tema claro e escuro, contraste AA, sem tela em construção | S4 | Concluído | `docs/NEXT2026/DESIGN.md` |
| RNF09 | Degradação explícita sob falha de fonte, de modelo ou de chave | S4 | Concluído | README, Roadmap (retry com teto, modo fixture, LLM sem chave) |
| RNF10 | Instalação reproduzível: pesos conferidos por SHA-256 e clone limpo verificado | S4 | Concluído | `scripts/preparar.py`; CHANGELOG, "Teste de clone limpo" |
| RNF11 | Licenças e atribuições registradas | S4 | Concluído | `docs/NEXT2026/ATRIBUICOES.md`, `docs/FIXTURES.md`, `amostras/LICENCA.md` |
| RNF12 | Dado simulado sempre rotulado como simulado | S4 | Em implementação | ADR 0008; contrato |
| RNF13 | Textos em pt-BR com um termo por conceito | S4 | Concluído | `docs/NEXT2026/GLOSSARIO.md`; CHANGELOG, PR10 |
| RNF14 | Qualidade medida por portão (pytest, ruff, build, E2E, crawler, axe) antes de cada merge | S4 | Concluído | `docs/scrum/definition-of-done.md` |

## Matriz de rastreabilidade: RF → card Trello → código → teste → sprint

Os testes da Gestão existem no disco, mas não foram executados por quem escreveu este documento.

| RF | Card Trello | Código | Teste | Sprint |
|---|---|---|---|---|
| RF01 | `RF01 — Detecção de EPIs em tempo real` | `app/vision/yolo_ppe_detector.py`, `app/vision/ensemble_ppe_detector.py` | `tests/test_yolo_ppe_detector.py`, `tests/test_ppe_defaults.py` | S1 |
| RF02 | `RF02 — Pessoas e rastreio com ID estável` | `app/vision/person_tracker.py`, `app/vision/reassociacao.py` | `tests/test_person_tracking.py`, `tests/test_reassociacao.py`, `tests/test_rastreio_modelo_unico.py` | S1 |
| RF03 | `RF03 — Associação exclusiva EPI e pessoa` | `app/vision/person_compliance_matcher.py`, `app/services/compliance_service.py` | `tests/test_person_tracking.py`, `tests/test_matcher_evidencia.py` | S1 |
| RF04 | `RF04 — Zona de risco por câmera` | `app/services/risk_rules.py`, `app/api/cameras.py`, `migrations/versions/cd57c8841519_zona_de_risco_por_camera.py` | `tests/test_zona_de_risco_por_camera.py`, `tests/test_regressao_c1_poligono.py` | S1 |
| RF05 | `RF05 — Pose, queda e postura` | `app/vision/pose_estimator.py`, `app/vision/yolo_pose_detector.py`, `app/vision/quedas.py` | `tests/test_pose_estimator_crop.py`, `tests/test_pose_por_pessoa.py`, `tests/test_pose_yolo.py`, `tests/test_quedas.py` | S2 |
| RF06 | `RF06 — Presença em zona de risco` | `app/services/risk_rules.py` | `tests/test_rules.py`, `tests/test_zona_de_risco_por_camera.py` | S2 |
| RF07 | `RF07 — Severidade explícita` | `app/services/risk_rules.py` | `tests/test_rules.py` | S3 |
| RF08 | `RF08 — Alertas com histerese` | `app/services/alert_state_service.py`, `app/repositories/alert_repository.py` | `tests/test_alert_state.py`, `tests/test_alert_repository.py`, `tests/test_alertas_em_lote.py` | S3 |
| RF09 | `RF09 — Notificação visual e sonora` | `frontend/src/audio/chime.ts`, `frontend/src/components/alerts.tsx` | `e2e/test_fluxos.py`, `e2e/test_jornada_02_turno_do_operador.py` | S3 |
| RF10 | `RF10 — Modo portaria` | `app/services/gate_service.py`, `frontend/src/components/gate.tsx` | `tests/test_modo_portaria.py` | S3 |
| RF11 | `RF11 — Login com três papéis` | `app/services/auth_service.py`, `app/api/auth.py`, `app/utils/auth.py` | `tests/test_auth.py`, `tests/test_auth_revogacao.py` | S3 |
| RF12 | `RF12 — Multicâmera e escopo do operador` | `app/api/cameras.py`, `app/services/monitor_service.py`, `app/services/camera_worker.py`, `app/utils/salas.py`, `app/cli.py` | `tests/test_cameras_api.py`, `tests/test_escopo_camera.py`, `tests/test_escopo_socket.py`, `tests/test_cameras_cli.py` | S3 |
| RF13 | `RF13 — Painel por perfil em tempo real` | `frontend/src/App.tsx`, `frontend/src/components/camera-grid.tsx`, `frontend/src/components/camera-focus.tsx`, `frontend/src/components/operator-kiosk.tsx` | `e2e/test_fluxos.py`, `e2e/test_jornada_02_turno_do_operador.py`, `e2e/test_es_sprint4.py::test_monitoramento_em_tempo_real_video_chega_ao_canvas`, `::test_dashboard_inicio_mostra_resumo_da_gestao` | S3 |
| RF14 | `RF14 — Reconexão com backoff` | `app/vision/video_stream.py`, `app/vision/captura_continua.py` | `tests/test_video_stream.py`, `tests/test_camera_worker_falha_de_fonte.py` | S3 |
| RF15 | `RF15 — Modo fixture visível` | `app/services/camera_worker.py`, `frontend/src/components/feed-status.tsx` | `tests/test_camera_worker_falha_de_fonte.py`, `tests/test_falhas_da_demo.py`, `e2e/test_falhas.py` | S4 |
| RF16 | `RF16 — Uso incorreto e protetor auricular` | `app/vision/person_compliance_matcher.py`, `app/services/risk_rules.py` | `tests/test_person_tracking.py` | S4 |
| RF17 | `RF17 — Estado não verificado` | `app/vision/person_compliance_matcher.py`, `app/config.py` (`PPE_MISSING_POLICY`) | `tests/test_matcher_evidencia.py`, `tests/test_camera_worker_llm_nao_verificado.py` | S4 |
| RF18 | `RF18 — Segunda opinião do LLM` | `app/llm/__init__.py`, `app/llm/prompts/v2.md`, `app/services/llm_risk_service.py`, `frontend/src/components/llm-panel.tsx` | `tests/test_llm.py`, `tests/test_llm_async.py`, `tests/test_llm_goldens.py`, `tests/test_camera_worker_llm.py` | S4 |
| RF19 | `RF19 — Avaliação por pessoa` | `app/vision/avaliacao.py`, `scripts/avaliar_dataset.py`, `docs/avaliacao/RESUMO.md` | `tests/test_avaliacao.py` | S4 |
| RF20 | `RF20 — Incidentes e linha causal` | `app/services/incidentes.py`, `app/services/linha_causal.py`, `app/api/incidentes.py`, `frontend/src/components/incidente-detalhe.tsx` | `tests/test_incidentes.py`, `tests/test_linha_causal.py`, `e2e/test_jornada_03_incidente_completo.py` | S4 |
| RF21 | `RF21 — Cadeia de custódia` | `app/services/custodia.py`, `app/api/custodia.py`, `frontend/src/components/auditoria.tsx` | `tests/test_custodia.py`, `e2e/test_jornada_04_investigacao.py` | S4 |
| RF22 | `RF22 — Replay com rosto desfocado` | `app/services/replay.py`, `app/vision/privacidade.py`, `frontend/src/components/replay.tsx` | `tests/test_replay.py`, `tests/test_privacidade.py`, `e2e/test_fluxos.py` | S4 |
| RF23 | `RF23 — Queda por ID e aproximação` | `app/vision/quedas.py`, `app/services/aproximacao.py` | `tests/test_quedas.py`, `tests/test_aproximacao.py`, `e2e/test_fluxos.py` | S4 |
| RF24 | `RF24 — Gêmeo digital e mapa de calor` | `app/api/gemeo.py`, `app/vision/planta.py`, `app/services/mapa_de_calor.py`, `frontend/src/components/gemeo/gemeo-screen.tsx` | `tests/test_gemeo.py`, `tests/test_planta.py`, `tests/test_mapa_de_calor.py` | S4 |
| RF25 | `RF25 — Simulador E se` | `app/services/simulador.py`, `app/api/simulador.py`, `frontend/src/components/simulador.tsx` | `tests/test_simulador.py`, `e2e/test_fluxos.py` | S4 |
| RF26 | `RF26 — Portal de Entrada e Você vs. a IA` | `app/services/desafio.py`, `app/api/desafio.py`, `frontend/src/components/portal.tsx`, `frontend/src/components/enganar-ia.tsx` | `tests/test_portal.py`, `tests/test_desafio.py`, `e2e/test_fluxos.py` | S4 |
| RF27 | `RF27 — Saúde visual da câmera` | `app/vision/saude_visual.py` | `tests/test_saude_visual.py`, `e2e/test_missao4.py` | S4 |
| RF28 | `RF28 — Fábrica conectada` | `app/services/integracao/`, `app/services/andon.py`, `app/api/integracao.py`, `frontend/src/components/torre.tsx` | `tests/test_integracao_industrial.py`, `tests/test_andon.py`, `e2e/test_jornada_07_integracao_industrial.py` | S4 |
| RF29 | `RF29 — Modo Evacuação` | `app/services/evacuacao.py`, `app/api/evacuacao.py`, `frontend/src/components/evacuacao.tsx` | `tests/test_evacuacao.py`, `e2e/test_jornada_05_evacuacao.py` | S4 |
| RF30 | `RF30 — Editor de regras sem código` | `app/services/regras_editor.py`, `app/services/regras_repositorio.py`, `app/api/regras.py`, `frontend/src/components/regras.tsx` | `tests/test_regras_editor.py` | S4 |
| RF31 | `RF31 — Permissão de trabalho com vigia` | `app/services/permissoes.py`, `app/api/permissoes.py`, `frontend/src/components/permissoes.tsx` | `tests/test_permissoes.py`, `e2e/test_jornada_06_permissao_com_vigia.py` | S4 |
| RF32 | `RF32 — Relatórios de turno e mensal` | `app/services/nr6.py`, `app/services/relatorio_mensal.py`, `app/api/relatorio.py` | `tests/test_nr6.py`, `tests/test_relatorio_turno.py`, `tests/test_relatorio_mensal.py` | S4 |
| RF33 | `RF33 — Liga, Modo TV e retrospectiva` | `app/services/liga.py`, `app/services/retrospectiva.py`, `app/api/liga.py`, `app/api/tv.py`, `frontend/src/components/liga.tsx`, `frontend/src/components/tv.tsx` | `tests/test_liga.py`, `tests/test_tv.py`, `e2e/test_jornada_09_gamificacao.py` | S4 |
| RF34 | `RF34 — Modo Apresentação` | `app/services/palco.py`, `app/services/palco_preparos.py`, `app/api/palco.py`, `frontend/src/components/palco.tsx` | `tests/test_palco.py`, `e2e/test_jornada_10_apresentacao.py` | S4 |
| RF35 | `RF35 — Área de detecção por câmera` | `app/vision/area_de_deteccao.py`, `migrations/versions/d3e4f5a6b7c8_area_de_deteccao.py` | `tests/test_area_de_deteccao.py`, `e2e/test_missao7.py` | S4 |
| RF36 | `RF36 — Celular como câmera` | `app/vision/fonte_celular.py`, `app/api/celular.py`, `frontend/src/components/celular-qr.tsx` | `tests/test_celular.py`, `e2e/test_fluxos.py` | S4 |
| RF37 | `RF37 — Status do sistema e API documentada` | `app/services/status_do_sistema.py`, `app/api/status.py`, `app/api/openapi.py`, `app/services/openapi_doc.py`, `frontend/src/components/pagina-status.tsx` | `tests/test_pagina_status.py`, `tests/test_openapi.py` | S4 |
| RF38 | `RF38 — Modo demonstração offline` | `run.py`, `app/demo.py`, `app/demo_ambiente.py`, `app/api/demo.py` | `tests/test_demo.py`, `tests/test_falhas_da_demo.py`, `e2e/fumaca_demo.py` | S4 |
| RF39 | `RF39 — Amostra de vídeo versionada` | `amostras/canteiro_amostra.mp4`, `amostras/LICENCA.md`, `app/demo_ambiente.py` (`fonte_da_gravacao`) | sem teste dedicado | S4 |
| RF40 | `RF40 — Fallback do LLM na demo` | `app/llm/__init__.py` (`ProvedorDemonstracao`), `app/services/llm_risk_service.py`, `app/services/status_do_sistema.py`, `frontend/src/components/llm-panel.tsx` | `tests/test_llm_demo_fallback.py`, `e2e/test_es_sprint4.py::test_segunda_opiniao_sem_chave_e_rotulada_modo_demonstracao` | S4 |
| RF41 | `RF41 — Colaboradores e histórico de EPIs` | `app/api/gestao.py`, `app/services/gestao_epi.py`, `app/models.py` (`Colaborador`), `frontend/src/components/gestao/colaboradores.tsx` | `tests/test_gestao_epi.py` (filtros, detalhe, `test_colaborador_mostra_entregas_vigentes_e_pendencias`), `e2e/test_es_sprint4.py::test_colaborador_tem_historico_de_epis` | S4 |
| RF42 | `RF42 — Catálogo de EPIs com CA` | `app/api/gestao.py`, `app/services/gestao_epi.py`, `app/models.py` (`EpiCatalogo`), `frontend/src/components/gestao/catalogo.tsx` | `tests/test_gestao_epi.py` (`test_situacao_do_ca_nos_limites`, `test_catalogo_recusa_ca_repetido_e_valida_categoria_e_vida_util`), `e2e/test_es_sprint4.py::test_catalogo_mostra_ca_e_situacao_da_validade` | S4 |
| RF43 | `RF43 — Entregas e devoluções de EPI` | `app/api/gestao.py`, `app/services/gestao_epi.py`, `app/models.py` (`EntregaEpi`), `frontend/src/components/gestao/entregas.tsx` | `tests/test_gestao_epi.py::test_ca_vencido_bloqueia_a_entrega_com_409_e_texto_de_politica_da_empresa`, `::test_devolucao_marca_a_data_e_devolver_de_novo_da_409`, `::test_colaborador_desligado_continua_legivel_mas_nao_recebe_entrega`; `e2e/test_es_sprint4.py::test_entrega_com_ca_vencido_e_bloqueada_e_valida_e_registrada` | S4 |
| RF44 | `RF44 — Ocorrências de segurança` | `app/api/gestao.py`, `app/services/gestao_epi.py`, `app/models.py` (`Ocorrencia`), `frontend/src/components/gestao/ocorrencias.tsx` | `tests/test_gestao_epi.py::test_ocorrencia_nasce_aberta_com_instante_em_utc`, `::test_encerrar_preenche_a_data_reabrir_limpa_e_encerrar_de_novo_mantem`; `e2e/test_es_sprint4.py::test_ocorrencia_registrada_aparece_na_lista` | S4 |
| RF45 | `RF45 — Exportação CSV` | `app/api/gestao.py` (`exportar_csv`), `app/services/gestao_epi.py`, `frontend/src/components/gestao/relatorios.tsx` | `tests/test_gestao_epi.py::test_csv_tem_bom_ponto_e_virgula_nome_de_arquivo_e_cabecalho_de_download`, `::test_csv_neutraliza_formula_digitada_pelo_usuario`; `e2e/test_es_sprint4.py::test_exportacao_csv_e_relatorio_mensal` | S4 |
| RF46 | `RF46 — Seed idempotente da Gestão` | `app/services/gestao_seed.py`, `app/cli.py` (`gestao semear`), `app/demo.py`, `migrations/versions/a8b9c0d1e2f3_gestao_de_epis.py` | `tests/test_gestao_seed.py::test_rodar_duas_vezes_nao_duplica_nada`, `::test_e_deterministico_mesma_entrada_mesmo_resultado`, `::test_comando_semear_imprime_criados_e_existentes_e_e_idempotente` | S4 |
| RF47 | `RF47 — Permissões da Gestão` | `app/api/gestao.py`, `app/utils/auth.py` | `tests/test_gestao_epi.py::test_leitura_sem_sessao_401_operador_403_tecnico_ok`, `::test_tecnico_nao_cadastra_colaborador_nem_item_mas_registra_entrega_e_ocorrencia`, `::test_operador_nao_escreve_em_lugar_nenhum`; `tests/test_matriz_de_permissoes.py` | S4 |
| RF48 | `RF48 — Notificação por Telegram` | nenhum (não implementado) | nenhum | S3 |
| RF49 | `RF49 — Medir o LLM no conjunto anotado` | `scripts/avaliar_llm_dataset.py` (pronto, não rodado) | `tests/test_avaliacao.py` (régua por pessoa; a medição com chave nunca rodou) | S4 |
| RF50 | `RF50 — Dataset anotado da planta` | nenhum | nenhum | S4 |
| RF51 | `RF51 — Pose por pessoa em modo stream` | `app/vision/pose_estimator.py` (hoje `static_image_mode=True`) | `tests/test_pose_por_pessoa.py` (cobre o estado atual) | S4 |
| RF52 | `RF52 — Parâmetros da câmera em runtime` | nenhum (o worker relê a configuração só ao ser reconstruído) | nenhum | S4 |
| RF53 | `RF53 — Agrupar alertas por pessoa na multidão` | nenhum | nenhum | S4 |

### Matriz dos requisitos não funcionais

| RNF | Card Trello | Onde é garantido | Teste | Sprint |
|---|---|---|---|---|
| RNF01 | `RNF01 — Privacidade por setor` | `app/vision/privacidade.py`, `docs/NEXT2026/MARCA.md` | `tests/test_privacidade.py`, `e2e/test_fluxos.py::test_privacidade_so_o_supervisor_altera` | S4 |
| RNF02 | `RNF02 — Controle de acesso verificado` | `app/utils/auth.py`, `app/utils/salas.py`, `docs/NEXT2026/PERMISSOES.md` | `tests/test_matriz_de_permissoes.py`, `tests/test_seguranca_missao4.py`, `tests/test_escopo_socket.py`, `tests/test_auth_revogacao.py` | S4 |
| RNF03 | `RNF03 — Segredos fora do repositório` | `app/llm/__init__.py` (`redigir_segredos`), `app/config.py`, `.env.example` | `tests/test_onboarding.py`, `tests/test_credencial_rtsp.py`, `tests/test_llm.py` | S4 |
| RNF04 | `RNF04 — Caminho do frame sem espera` | `app/services/llm_risk_service.py`, `app/services/gravador_assincrono.py`, `app/services/agendador_de_inferencia.py` | `tests/test_llm_async.py`, `tests/test_gravador_assincrono.py`, `tests/test_agendador_ponderado.py` | S4 |
| RNF05 | `RNF05 — Guarda de concordância` | `scripts/concordancia.py`, `app/vision/runtime_do_modelo.py` | `tests/test_runtime_do_modelo.py` | S4 |
| RNF06 | `RNF06 — Operação offline` | `app/demo_ambiente.py`, `scripts/preparar.py` | `e2e/fumaca_demo.py` | S4 |
| RNF07 | `RNF07 — Esquema sob Alembic` | `migrations/versions/` | `tests/test_onboarding.py` | S4 |
| RNF08 | `RNF08 — Design system e acessibilidade` | `frontend/src/styles/tokens.css`, `scripts/check_contrast.py` | `e2e/test_acessibilidade.py`, `e2e/test_estados.py`, `e2e/test_es_sprint4.py::test_gestao_no_tema_escuro` | S4 |
| RNF09 | `RNF09 — Degradação explícita` | `app/services/camera_worker.py`, `app/llm/__init__.py` | `tests/test_camera_worker_falha_de_fonte.py`, `tests/test_falhas_da_demo.py`, `e2e/test_falhas.py` | S4 |
| RNF10 | `RNF10 — Instalação reproduzível` | `scripts/preparar.py`, `scripts/fetch_fixtures.py`, `requirements.txt` | `tests/test_onboarding.py`, `e2e/fumaca_demo.py` | S4 |
| RNF11 | `RNF11 — Licenças e atribuições` | `docs/NEXT2026/ATRIBUICOES.md`, `docs/FIXTURES.md`, `amostras/LICENCA.md` | sem teste automatizado | S4 |
| RNF12 | `RNF12 — Dado simulado rotulado` | `app/services/gestao_seed.py`, `frontend/src/components/gestao.tsx` ("Dados simulados") | `tests/test_gestao_seed.py::test_alertas_historicos_sao_resolvidos_marcados_e_nenhum_nas_ultimas_24h`, `tests/test_gestao_epi.py::test_resumo_avisa_quando_ha_registro_simulado` | S4 |
| RNF13 | `RNF13 — Textos pt-BR consistentes` | `docs/NEXT2026/GLOSSARIO.md` | `tests/test_copy_do_frontend.py`, `e2e/test_estados.py` | S4 |
| RNF14 | `RNF14 — Portão de qualidade` | `docs/scrum/definition-of-done.md` | `e2e/test_todos_os_botoes.py`, `tests/test_matriz_de_permissoes.py` | S4 |

## Notas de consistência

- **RF16 e a Fase 1.** O relatório da Fase 1 (entrega de 04/05) marca como entregues os 7 EPIs e a distinção correto/incorreto/ausente
  (`FASE1` §2 e §7). O `CONSOLIDADO.md` §2.1 e o relatório da Fase 4 §5 dizem que protetor auricular e "uso incorreto" entraram na fase final
  e que a distinção estava "pendente até esta entrega". Aqui vale o texto da Fase 4: RF03 (associação e estado por EPI) é S1 e RF16 é S4.
- **RF18 e a Fase 4.** O `CONSOLIDADO.md` §6 e §8 diz "sem componente de LLM" na arquitetura entregue em 23/09. O LLM foi ligado no boot em
  09/09 (`fd97d46`). Os dois textos convivem; vale o código.
- **Contagem de testes.** O `CONSOLIDADO.md` cita 378 testes; o portão da MISSÃO 7 (22/10) registra 3.288 aprovados. Números de datas diferentes.
