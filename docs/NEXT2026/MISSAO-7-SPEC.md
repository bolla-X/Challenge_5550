# Spec — MISSÃO 7: área de detecção por câmera

Estruturação de `MISSAO-7.md` (o prompt, sem mudança de conteúdo). Em caso de dúvida, vale o prompt.

## Objetivo

Cada câmera passa a ter dois tipos de área, configuráveis separadamente: a **área de detecção** (nova, o único
lugar onde o sistema procura pessoas; fora dela nada é detectado, rastreado ou alertado) e a **área de risco** (já
existe, continua como está).

## Critérios de aceite

### M7.1 Modelo de dados e API
- M7.1.1 Por câmera, zero ou uma área de detecção: polígono com ≥ 3 pontos, em coordenadas normalizadas 0–1.
- M7.1.2 Sem área = quadro inteiro (comportamento de hoje); bancos existentes continuam funcionando (migração Alembic).
- M7.1.3 Endpoints para ler, salvar e remover; salvar e remover só para técnico ou acima.
- M7.1.4 Validação: polígono não degenerado, pontos dentro de 0–1, área mínima.
- M7.1.5 Persiste e é reaplicada depois de reconexão e reinício.

### M7.2 Pipeline
- M7.2.1 Retângulo envolvente do polígono com 5 % de margem; inferência (EPI, pessoas e pose) só nesse recorte; caixas
  mapeadas de volta para o quadro inteiro. **Desvio registrado (22/10):** 5 % nos lados e embaixo, 30 % em cima
  (`MARGEM_TOPO`): com 5 %, quem tem os pés na borda de cima chega ao modelo sem cabeça e gera "sem capacete" falso
  (auditoria, A2). Custo: recorte maior. A medição do CHANGELOG foi feita com essa margem.
- M7.2.2 Pessoa mantida só se o ponto dos pés (centro da base da caixa) estiver dentro do polígono.
- M7.2.3 EPI mantido só se associado a uma pessoa mantida.
- M7.2.4 Tracker, regras, incidentes, aproximação (F3), mapa de calor, planta e 3D recebem só o que foi mantido.
- M7.2.5 Saúde visual (M1) continua usando o quadro inteiro.
- M7.2.6 Testes unitários: recorte → quadro (com letterbox); ponto dos pés em polígono convexo e côncavo; pessoa
  cruzando a borda; câmera sem área = resultado idêntico ao de hoje.

### M7.3 Interface
- M7.3.1 Seletor "Área de detecção / Área de risco" no editor de áreas da câmera.
- M7.3.2 Área de detecção desenhada arrastando um retângulo ou com cliques de polígono; botões salvar, refazer,
  remover (volta ao quadro inteiro).
- M7.3.3 Contorno neutro (sem a cor de perigo) com rótulo "Área de detecção".
- M7.3.4 Fora da área, imagem escurecida no vídeo ao vivo, na tela de foco, no quiosque e nas capturas.
- M7.3.5 Aviso no editor quando uma área de risco fica total ou parcialmente fora da área de detecção: "Parte desta
  área de risco está fora da área de detecção e não será vigiada."
- M7.3.6 Evidências (snapshot, clipe de replay, recortes de rótulo): fora da área sai escurecido e desfocado; entra
  na cadeia de custódia como hoje.
- M7.3.7 Textos seguindo MARCA.md e GLOSSARIO.md; "Área de detecção" no glossário.

### M7.4 Medição (no CHANGELOG), fixture `next_multidao.mp4`, área ≈ 1/3 do quadro
- M7.4.1 Tempo de inferência por análise com e sem área.
- M7.4.2 Pessoas detectadas fora da área (meta: zero).
- M7.4.3 Pessoas dentro da área: contagem contra a inferência no quadro inteiro restrita ao mesmo polígono, com a
  diferença registrada.

### M7.5 E2E e docs
- M7.5.1 E2E: desenhar a área de detecção pela UI na câmera Multidão → nenhuma caixa nem contador fora dela → pessoa
  sem EPI dentro gera alerta → remover a área → volta a detectar no quadro inteiro.
- M7.5.2 Crawler de botões nas telas alteradas; capturas nos dois temas com rubrica ≥ 4.
- M7.5.3 DEMO.md (e COLA-TIME.md, se existir): preparação da arena na ordem (1) área de detecção, (2) áreas de
  risco, (3) calibração do 3D.

### M7.6 Entrega
- M7.6.1 Portão completo: pytest, ruff, build e typecheck, E2E completo, crawler, axe.
- M7.6.2 PR único da `missao-7` → `gh pr merge --squash --delete-branch` (só com o portão verde) → tag
  `final-next-2026-r3` → fumaça a partir da `main`.
- M7.6.3 Resumo de até 10 linhas (PR, tempos com e sem área, pessoas fora da área, diferença dentro, riscos).

## Fora do escopo
- Qualquer outra feature.
- Mudar o comportamento de câmera sem área de detecção configurada.
- Contornar permissão negada (merge negado: PR pronto e registro).
- Qualquer coisa fora dos itens listados.

## Ramos pré-decididos e rollback
- Antes de afirmar limitação de biblioteca ou plataforma: doc oficial lida e URL citada.
- Merge negado pela permissão: não contornar; deixar o PR pronto e registrar no ESTADO.md.
- Valem as regras de verdade e o portão da MISSAO-4 (sem desligar teste, sem afrouxar assert; timeouts só com
  registro no CHANGELOG; E2E em série, 1 worker; um servidor e um navegador por vez).
- Rollback: tag `pre-missao-7` (HEAD da `main` antes da missão) ou `git revert` do squash.
- COLA-TIME.md não existe no repositório (verificado em 22/10): só o DEMO.md é atualizado.
