# MISSÃO 7 — Área de detecção por câmera (pedido da organização do NEXT)

Leia docs/NEXT2026/MISSAO-4.md, ESTADO.md, DEMO.md e o código das zonas (editor de áreas de risco e o pipeline do worker). Salve este prompt em docs/NEXT2026/MISSAO-7.md. Modo autônomo, sem perguntas.

## Objetivo
Cada câmera passa a ter dois tipos de área, configuráveis separadamente:
1. **Área de detecção** (nova): o único lugar onde o sistema procura pessoas. Fora dela, nada é detectado, rastreado ou alertado. Exemplo: a câmera mostra a plateia, mas só o "quadrado" do palco é analisado.
2. **Área de risco** (já existe): continua como está, com as regras atuais.

## Regras
- Valem as REGRAS DE VERDADE e o portão da MISSAO-4. Antes de afirmar limitação de biblioteca ou plataforma, leia a doc oficial e cite a URL.
- Crie e dê push na tag `pre-missao-7` na main. Branch `missao-7`, um único PR.
- Merge só com `gh pr merge --squash --delete-branch` e só se o portão completo passar. Se for negado pela permissão, não contorne: deixe o PR pronto e registre.
- Nenhuma outra feature. Não mude o comportamento de câmera sem área de detecção configurada.

## 1. Modelo de dados e API
- Por câmera: zero ou uma área de detecção, um polígono com no mínimo 3 pontos, guardado em coordenadas normalizadas (0–1).
- Sem área configurada = quadro inteiro (comportamento de hoje, compatível com bancos existentes, com migração se precisar).
- Endpoints para ler, salvar e remover, restritos a técnico ou acima. Valide a entrada: polígono não degenerado, pontos dentro de 0–1, área mínima.
- Persiste e é reaplicada depois de reconexão e reinício.

## 2. Pipeline
- Calcule o retângulo envolvente do polígono com 5% de margem. Rode a inferência (EPI, pessoas e pose) só nesse recorte e mapeie as caixas de volta para as coordenadas do quadro inteiro.
- Pessoa só é mantida se o ponto dos pés (centro da base da caixa) estiver dentro do polígono. EPI só é mantido se estiver associado a uma pessoa mantida. O tracker, as regras, os incidentes, a aproximação (F3), o mapa de calor, a planta e o 3D recebem só o que foi mantido.
- A saúde visual da câmera (M1: obstruída, movida, escura) continua usando o quadro inteiro.
- Testes unitários:
  - mapeamento de coordenadas recorte → quadro, inclusive com letterbox;
  - regra do ponto dos pés em polígonos convexos e côncavos;
  - pessoa com o corpo cruzando a borda;
  - câmera sem área configurada = resultado idêntico ao de hoje.

## 3. Interface
- No editor de áreas da câmera, um seletor "Área de detecção / Área de risco". A área de detecção pode ser desenhada arrastando um retângulo ou com cliques de polígono. Botões: salvar, refazer, remover (volta ao quadro inteiro).
- Visual: contorno neutro (não use cor de perigo, que é da área de risco), com rótulo "Área de detecção". Fora dela, a imagem fica escurecida no vídeo ao vivo, na tela de foco, no quiosque e nas capturas.
- Aviso no editor quando uma área de risco ficar total ou parcialmente fora da área de detecção: "Parte desta área de risco está fora da área de detecção e não será vigiada."
- Evidências (snapshot, clipe de replay, recortes de rótulo): a parte fora da área de detecção sai escurecida e desfocada. Isso entra na cadeia de custódia como hoje.
- Textos seguindo o MARCA.md e o GLOSSARIO.md. Adicione "Área de detecção" ao glossário.

## 4. Medição (registre no CHANGELOG)
Na fixture `next_multidao.mp4`, com uma área de detecção cobrindo cerca de um terço do quadro:
- tempo de inferência por análise com e sem área;
- pessoas detectadas fora da área (meta: zero);
- pessoas dentro da área: compare a contagem com a inferência no quadro inteiro restrita ao mesmo polígono e registre a diferença.

## 5. E2E e docs
- E2E: desenhar a área de detecção pela UI na câmera da multidão → nenhuma caixa nem contador fora dela → uma pessoa sem EPI dentro gera alerta → remover a área → volta a detectar no quadro inteiro.
- Crawler de botões nas telas alteradas e capturas nos dois temas com rubrica ≥ 4.
- Atualize DEMO.md e COLA-TIME.md (se existir): na preparação da arena, a ordem passa a ser (1) área de detecção, (2) áreas de risco, (3) calibração do 3D.

## 6. Entrega
Portão completo (pytest, ruff, build e typecheck, E2E completo, crawler, axe) → PR → squash na main → tag `final-next-2026-r3` → fumaça a partir da main.

Resumo de até 10 linhas:
- link do PR;
- tempo de inferência com e sem área;
- pessoas detectadas fora da área (deve ser 0);
- diferença na contagem dentro da área;
- os riscos para a arena.
