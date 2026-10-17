# MISSÃO 4 — VisionEPI pronto de empresa: QA total, Fábrica Conectada, CX e todos os caminhos testados

Repositório: https://github.com/bolla-X/Challenge_5550 (branch final: main)
Sessão noturna 100% autônoma: o dono está dormindo. Não pergunte nada, não peça teste manual, não sugira pedir algo a outras pessoas. Toda decisão está tomada abaixo; se algo bloquear, registre e siga para o próximo item. Objetivo: amanhecer com um produto que pareça de empresa, sem nenhum botão quebrado, com todas as funções testadas de ponta a ponta e tudo na main.

## PASSO 0 — Persistência e casa em ordem
1. Leia docs/NEXT2026/ (MISSAO-2.md, ESTADO.md, CHANGELOG.md, DEMO.md, BANCA.md, DESIGN.md) e o código.
2. Salve este prompt sem alterações em `docs/NEXT2026/MISSAO-4.md`. O ESTADO.md passa a apontar para a MISSAO-4 e é reescrito a cada marco: pronto, commit, como verificar, próximo passo exato. Se a sessão cair, a próxima retoma lendo só MISSAO-4.md + ESTADO.md.
3. Se o PR #18 estiver aberto, faça squash merge na main. Se a permissão barrar, não contorne: crie `missao-4` a partir da branch do #18 e registre que ele aguarda merge manual. Se der certo, crie `missao-4` a partir da main.
4. O PR #9 (`rebrand/calma`, conta lukiin-z) é do dono e o conteúdo já está na main. Feche com o comentário "Conteúdo já incorporado na main pelos PRs da missão NEXT 2026".
5. Crie e dê push na tag `pre-missao-4` no HEAD da main.

## REGRAS
Verdade
- Nada está pronto sem evidência executada. "O compilador aceitou" ≠ "a funcionalidade existe". Cada item exige teste unitário, E2E Playwright contra o servidor real e screenshot revisado na rubrica da MISSAO-2 (nota ≥ 4 em todos os itens).
- Antes de afirmar limitação de plataforma ou biblioteca, leia a doc oficial e cite a URL no CHANGELOG. Norma regulamentadora citada na UI ou nos docs: texto oficial do gov.br, URL citada, só o que estiver lá.
- "Não detectado" ≠ "ausente". ID de rastreio não é identidade: sem reconhecimento facial, sem nome vinculado a ID, sem ranking individual.
- Nada inventado na UI: nenhum cliente, depoimento, métrica de mercado, preço ou número que o sistema não produziu. Dado de demonstração é rotulado "demo".
- Não desligue testes nem afrouxe asserts de comportamento. Timeouts de espera podem ser ajustados para esta máquina lenta, desde que registrados no CHANGELOG.

Git e permissões
- Trabalhe em `missao-4`. São 3 PRs consolidados para a main, com squash merge feito por você:
  - PR8: "QA de base + Fábrica conectada";
  - PR9: "Experiência de empresa + Operação avançada";
  - PR10: "Todos os caminhos testados + entrega".
- Depois de cada merge, crie a tag `missao-4-prN` e recrie `missao-4` a partir da main.
- Se um merge for barrado pela permissão, não contorne: deixe o PR pronto, registre no ESTADO.md e continue a próxima fase empilhando na mesma branch (o PR seguinte inclui o anterior). No resumo final, liste o que aguarda merge manual.
- Ação negada pela permissão: não contorne com outro comando; registre e siga. Nunca use `| tail` ou outro pipe que esconda o código de saída de testes: grave em arquivo e confira o exit code.
- Sem GitHub Actions; não crie nem altere `.github/workflows`. Nunca force push nem reescreva histórico remoto. Rollback = `git revert` do squash commit.
- Commit + push a cada marco e antes de qualquer tarefa com mais de 10 minutos.
- Nunca commite `.env`, segredos, pesos, vídeos ou dados pessoais.

CPU (esta máquina é fraca; a da apresentação é muito melhor)
- Nada de benchmark nesta missão: não rode `bench.py` nem rodadas comparativas. Desempenho só é verificado como correção (funciona, sem erro).
- No máximo um servidor do VisionEPI e um navegador Playwright rodando ao mesmo tempo. E2E, QA de navegador e capturas rodam em série, nunca em paralelo, com 1 worker.
- Processos de teste com prioridade abaixo do normal e `VISIONEPI_THREADS=2`.
- Agentes em paralelo só para trabalho sem servidor: ler código, escrever código e testes, revisar copy e design, pesquisar docs.
- Suíte completa (pytest + E2E) só nos portões de PR e na Fase 5. Durante o desenvolvimento, rode apenas os testes afetados.
- Não reduza nenhuma feature por causa desta máquina. Se algo depender de tempo e falhar só por lentidão, registre como "sensível à carga — validar na máquina da apresentação" depois de confirmar que funciona isoladamente.

Orquestração
- Use a squad global (plugin squad como orquestrador, conforme o bloco SQUAD do ~/.claude/CLAUDE.md) e distribua o trabalho entre os agentes e plugins instalados:
  - squad build/fix/review para implementar, corrigir (reproduzir primeiro, com teste de regressão) e revisar;
  - QA My App e QA Bug Hunter para catalogar rotas e caçar bugs (o Bug Hunter só reporta; a correção vai para o squad fix);
  - playwright para navegador;
  - frontend-design e ui-design para interface;
  - os agentes cx e fontes (~/.claude/agents/squad/) para experiência do cliente e para citações de normas e licenças;
  - voltagent-qa-sec para segurança.
- Você continua dono da integração: cada entrega de agente passa pelo portão antes de entrar.

Aceite de feature
- Toda feature nova começa como protótipo mínimo. Entra se funcionar no E2E sem degradar o resto. Senão vira laboratório (desligada por padrão, rotulada) ou é descartada, sempre com registro.

## FASE 1 — QA de base do que já existe (PR8, parte 1)
1. QA My App: rode o init (ou sync, se já houver catálogo) para catalogar todas as rotas, formulários, botões, modais e guardas de papel.
2. Crawler "botão a botão", em `e2e/test_todos_os_botoes.py`:
   - para cada papel (sem sessão, operador, técnico, supervisor) e cada rota acessível, enumere todo elemento interativo visível (botão, link, aba, toggle, item de menu, atalho do command palette) e acione;
   - cada um precisa causar efeito verificável: navegação, abertura de painel ou modal, mudança de estado, download ou requisição bem-sucedida. Senão, precisa estar desabilitado com tooltip explicando o motivo;
   - botão sem efeito, erro no console, resposta 4xx/5xx inesperada, link quebrado ou texto cortado é bug.
   Gere `docs/NEXT2026/QA.md` com a matriz rota × papel × resultado.
3. Matriz de permissões: para cada endpoint REST e evento de socket, teste com cada papel e sem sessão. O resultado tem que bater com a tabela de papéis do README (operador restrito ao próprio setor). Qualquer divergência é bug de segurança e tem prioridade máxima.
4. QA Bug Hunter nos módulos centrais (pipeline, regras, incidentes, replay, privacidade, custódia, palco, portal). Cada bug confirmado vai para o squad fix com teste de regressão.
5. Revisão de copy em todas as telas: zero inglês remanescente, zero código interno (`missing_*`, nomes de classe), zero "(s)", zero "TODO" ou "em construção", decimal e hora no padrão pt-BR, terminologia consistente. Crie `docs/NEXT2026/GLOSSARIO.md` e aplique.

## FASE 2 — Fábrica conectada (PR8, parte 2)
M1. Saúde visual da câmera (sabotagem)
- A cada ~1 s, por câmera, compare um quadro reduzido em escala de cinza com a referência da calibração. Detecte:
  - obstrução: variância e brilho baixos ou cobertura uniforme;
  - escuro ou ofuscado: histograma;
  - desfoque: variância do Laplaciano;
  - câmera movida: ORB + homografia ou queda forte de similaridade.
- Cada tipo gera alerta com histerese e badge de estado ("OBSTRUÍDA", "MOVIDA"…). Botão "redefinir referência" para técnico ou acima.
- Testes com quadros sintéticos derivados das fixtures. No E2E, a fonte MJPEG de teste passa a servir quadros tampados no meio do teste; meça o tempo até o alerta.
- Cena do palco "tape a câmera", usando a webcam na demo.

M2. Integração industrial
- Servidor OPC UA opcional (asyncua; verifique e registre a licença) com nós por câmera (estado, incidentes ativos por regra, conformidade, último alerta) e um nó global "planta em alarme".
- Publicador MQTT opcional (paho-mqtt) com `visionepi/<camera>/alerta` e `visionepi/planta/estado`, e webhook HTTP configurável. Tudo desligado por padrão e ligado no modo demo. Para a demo offline, um broker MQTT embutido em Python com licença permissiva; sem opção confiável, demonstre só o OPC UA.
- Porta ocupada ou falha de rede nunca derruba o app: degrada com aviso na página de status.
- "Torre de luz virtual" (verde/amarelo/vermelho + sirene visual) no Modo TV e em `/torre`, refletindo o mesmo estado publicado.
- Testes de integração com clientes OPC UA e MQTT lendo os valores ao disparar alerta por fixture.
- `docs/NEXT2026/INTEGRACAO.md`: como um CLP ou SCADA consome (endpoint, nós, tópicos, exemplo).

M3. Modo Evacuação
- Botão de emergência (supervisor e palco) que mostra:
  - pessoas detectadas agora por zona e câmera;
  - última posição vista na planta;
  - chegadas na câmera do ponto de encontro;
  - cronômetro.
- Rótulo sempre visível: "contagem por câmera — pode haver dupla contagem se as câmeras se sobrepõem".
- Ao encerrar, o relatório da evacuação entra na cadeia de custódia (X3).

M4. Editor de regras sem código
- Blocos de condição (zona, EPI presente/ausente, duração, postura, aproximação, horário, permissão ativa) combinados com E/OU, e blocos de ação (severidade, fala, MQTT/OPC UA, escalonamento).
- Compila para o motor de regras existente, sem um segundo caminho de execução.
- "Testar no histórico" usando o simulador X2 antes de ativar.
- As regras atuais aparecem como pré-carregadas.
- Testes de equivalência: cada regra antiga reescrita no editor gera os mesmos alertas nas fixtures.

M5. Permissão de Trabalho digital
- Zona, janela de horário, responsável (texto livre, sem vínculo com tracks), EPIs exigidos e "exige vigia" (NR-33, citação oficial).
- Os EPIs que o modelo detecta são fiscalizados; os que ele não detecta aparecem como "verificação manual" no checklist, sem fingir checagem.
- Regra do vigia: pessoa na zona confinada sem ninguém na área de vigia gera alerta crítico. Entrar na zona fora da janela gera "sem permissão ativa".

Portão do PR8: pytest completo, ruff, build e typecheck, E2E completo com 4 câmeras numa rodada única, crawler de botões verde, axe sem violações sérias ou críticas → squash na main → tag `missao-4-pr8`.

## FASE 3 — Experiência de empresa / CX (PR9, parte 1)
Use o agente cx como dono desta fase, com ui-design e frontend-design. Siga `.agents/skills` (apple-design, design-taste-frontend) e o DESIGN.md: clean, premium, cor só para estado, tema claro como padrão do demo, escuro impecável.
1. Identidade:
   - wordmark e símbolo originais em SVG, com favicon, ícones de PWA e imagem Open Graph;
   - tom de voz em `docs/NEXT2026/MARCA.md`: direto, humano, técnico sem jargão.
2. Primeiro acesso (onboarding):
   - assistente para supervisor: cadastrar câmera → capturar referência → calibrar planta → desenhar zonas → definir EPIs por setor → criar usuários (senha temporária exibida uma vez; sem envio de e-mail) → checklist "pronto para operar";
   - progresso salvo, retomável e pulável;
   - no modo demo, já vem concluído, com opção "refazer".
3. Tour guiado por papel: curto, pulável, lembra que já foi visto e tem um botão "rever tour".
4. Central de ajuda `/ajuda`: artigos curtos por tarefa, com busca, e um "?" contextual em cada tela levando ao artigo certo. Sem conteúdo genérico.
5. Central de notificações: sino com histórico, filtros por severidade e câmera, marcar como lido, link para o incidente.
6. Busca global no command palette: câmeras, incidentes, IDs de rastreio, regras, permissões, telas e artigos de ajuda.
7. Página `/status`, com saúde de modelos e runtime, câmeras, banco, OPC UA, MQTT, LLM e espaço em disco, e uma página "Novidades" com o changelog dentro do app.
8. Configurações reorganizadas em seções (Conta, Planta, Câmeras, Regras, Integrações, Privacidade, Usuários), com layout único.
9. Páginas de exceção desenhadas: 404, erro do servidor, sem conexão (o PWA mostra estado offline), sessão expirada (volta para onde estava após o login) e acesso negado (explica qual papel tem acesso).
10. Página pública `/produto`, ligada a partir do login:
    - hero com o GIF ou vídeo do palco;
    - problema, como funciona, diferenciais;
    - privacidade e LGPD;
    - integrações;
    - formulário de contato salvo localmente e visível ao supervisor em "Contatos".
    Sem clientes, depoimentos, métricas de mercado ou preços.
11. "Enviar feedback" dentro do app, salvo localmente, com tela de leitura para o supervisor.
12. Revisão de design por tela (plugin ui-design: critique, acessibilidade, consistência do design system). Corrija tudo abaixo de 4 na rubrica.

## FASE 4 — Operação avançada (PR9, parte 2; protótipo primeiro)
M6. Busca nas trilhas (sem LLM)
Filtros de zona, horário, permanência mínima, EPI ausente, velocidade e câmera. Cada resultado abre o replay quando houver clipe; quando não houver, mostra a trilha na planta.

M7. Escalonamento
Alerta crítico não reconhecido em X s vai para o supervisor (PWA). Em Y s, vai para TV e torre (vermelho piscando). Prazos configuráveis no editor M4. O tempo até reconhecer entra na Liga como indicador positivo.

M8. Antes/depois de intervenção + ROI
Comparação em janelas iguais, com tamanho de amostra e o aviso "correlação não é causa". O ROI usa só custos e premissas digitados pelo usuário; estatística oficial só com fonte citada.

M9. Uso de celular em área operacional
Classe "cell phone" do COCO. Só entra como regra se detectar de forma estável em fixture de licença livre com celular visível; senão, laboratório.

M10. Relatório mensal para a CIPA
Imprimível ou PDF, com indicadores, incidentes por zona e regra, intervenções, permissões e evacuações. Nada individual.

M11. API documentada
OpenAPI das rotas públicas, `/api/docs` (técnico ou acima) e exemplos de integração.

Portão do PR9 (mesmo do PR8) → squash na main → tag `missao-4-pr9`.

## FASE 5 — Todos os caminhos testados (PR10)
1. QA My App: sync e depois run-all em todas as rotas do catálogo atualizado.
2. Crawler botão a botão de novo: todos os papéis × todas as rotas × os dois temas, incluindo as telas novas. Meta: zero botão morto, zero erro de console e zero 4xx/5xx inesperado.
3. Jornadas ponta a ponta, uma por arquivo E2E, todas contra o servidor real com 4 câmeras:
   1. primeiro acesso completo do supervisor até "pronto para operar";
   2. turno do operador: login → setor dele → alerta → reconhecer → marcar falso positivo → logout;
   3. incidente completo: detecção → incidente agrupado → replay → linha causal → custódia verificada → relatório de turno;
   4. investigação: busca nas trilhas → replay → simulador "E se?" com regra editada;
   5. evacuação: acionar → contagem → encerrar → relatório na custódia;
   6. permissão de trabalho com vigia: emitir → entrada sem vigia → alerta → entrada com vigia → sem alerta;
   7. integração: alerta → nó OPC UA e tópico MQTT atualizados → torre vermelha → reconhecimento → torre verde;
   8. sabotagem: tapar a câmera → alerta → destapar → recupera;
   9. gamificação: check-in no portal → missão cumprida → XP → Retrospectiva;
   10. apresentação: `/palco` do início ao fim pelo teclado e pelo controle no celular emulado.
4. Injeção de falhas: câmera cai e volta, modelo ausente, banco travado, LLM fora, porta OPC UA ocupada, broker MQTT fora, webcam ausente, sessão expirada no meio de uma ação. Cada uma com mensagem clara e recuperação.
5. Segurança (voltagent-qa-sec): autorização em todo endpoint novo, CSRF e CORS, validação de entrada (zonas, regras, uploads, URLs de webhook — bloquear destinos internos indevidos), segredos fora de logs, dependências com vulnerabilidade conhecida. Corrija o que for alto ou crítico.
6. Visual final: capturas de todas as rotas e estados nos dois temas, em 1920×1080, 1366×768 e 390×844. Rubrica com nota ≥ 4 em tudo. Galeria em `docs/NEXT2026/galeria/` atualizada com antes/depois.
7. Teste de clone limpo da branch, seguindo o README à risca, até `e2e/fumaca_demo.py` passar.

## FASE 6 — Entrega
1. `/palco`: novas cenas só com o que passou no E2E (tapar a câmera, torre e OPC UA, evacuação, regra criada no editor e testada no histórico, permissão com vigia, onboarding em 30 s).
2. Regrave o vídeo do palco uma única vez, já no final, e atualize o asset da Release `next-2026-demo`.
3. Atualize README (vitrine), DEMO.md (roteiro + "Dia da apresentação"), BANCA.md (perguntas novas: CLP/SCADA, sabotagem, evacuação, editor de regras, NR-33/NR-35, LGPD do onboarding), QA.md, INTEGRACAO.md, MARCA.md e CHANGELOG.
4. Portão completo numa rodada única: pytest, ruff, build e typecheck, E2E completo + as 10 jornadas + crawler + axe → PR10 → squash na main → tags `missao-4-pr10` e `final-next-2026`.
5. Smoke test a partir da main atualizada: `python run.py --demo` + `e2e/fumaca_demo.py` + jornada 10 (palco).

## Ordem de prioridade se o tempo ou o limite acabar
Fase 1 > M1–M3 > Fase 3 itens 1, 2, 9 e 12 > M4–M5 > resto da Fase 3 > Fase 5 itens 2–3 > M6–M11 > o restante.
Ao fim de cada fase: tudo commitado e com push, PR aberto (ou mergeado) e ESTADO.md com o próximo passo exato.

## Resumo final (até 35 linhas)
- links dos PRs, tags e Release, e quais PRs aguardam merge manual;
- tabela de cada item (Fase 1, M1–M11, Fase 3 itens 1–12, Fase 5 itens 1–7) com status: pronto com E2E, laboratório ou descartado, e o motivo;
- bugs encontrados pelo QA (quantidade por gravidade) e quantos foram corrigidos com teste de regressão;
- crawler: rotas × papéis cobertos e botões mortos restantes (meta: 0);
- resultado das 10 jornadas;
- itens marcados "sensível à carga — validar na máquina da apresentação";
- as 3 maiores ameaças restantes para a apresentação.
