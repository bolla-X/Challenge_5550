# MISSÃO 2 — VisionEPI ABSURDO: funcionalidades fora da caixa + front SSS+++ + release na main

Repositório: https://github.com/bolla-X/Challenge_5550
Você trabalha 100% autônomo do início ao fim, sem pedir aprovação, sem pedir teste manual a ninguém e sem sugerir pedir algo a outras pessoas. Toda bifurcação está decidida abaixo; se algo bloquear, registre e siga para o próximo item. O objetivo é um projeto que deixe a banca da final do FIAP NEXT 2026 de queixo caído: funcionalidades que ninguém mais terá, um front de nível de produto premium e zero falha ao vivo.

## PASSO 0 — Contexto e persistência
1. Leia `docs/NEXT2026/` inteiro (MISSAO.md, ESTADO.md, CHANGELOG.md, DEMO.md, BANCA.md, AUDITORIA.md, BENCHMARKS.md) e o código. Estado herdado: PRs #10–#13 mergeados em `feat/completo-com-rebrand` (último `906c81e`). Já existem:
   - F1 replay, F3 aproximação, F4 privacidade, F5 diagnóstico, F6 celular como câmera, F7 mapa de calor, F9 relatório de turno, F10 prova de escala;
   - G1 portal, G2 desafio, G3 SOS por gesto, G4 pessoa imóvel, G5 planta baixa, G6 fala, G7 ergonomia, G8 Modo TV, G9 rotular, G10 NR-6;
   - modo `--demo`, OpenVINO na iGPU como runtime padrão.
2. Salve este prompt sem alterações em `docs/NEXT2026/MISSAO-2.md`. Reescreva o ESTADO.md apontando para a MISSAO-2 e atualize-o a cada marco (pronto, commit, como verificar, próximo passo exato). Sessões futuras retomam só com MISSAO-2.md + ESTADO.md.
3. Git:
   - Crie a tag `pre-missao-2` no HEAD de `feat/completo-com-rebrand` e a tag `main-pre-release` no HEAD de `main`; dê push nas duas.
   - Trabalhe em `next-2026`, recriada a partir de `feat/completo-com-rebrand`.
   - Faça 3 PRs consolidados, todos com squash merge feito por você (`gh pr merge --squash --delete-branch`):
     - PR5 "Funcionalidades fora da caixa" → `feat/completo-com-rebrand`
     - PR6 "Experiência SSS+++" → `feat/completo-com-rebrand`
     - PR7 "Release" → `main`
   - Depois de cada merge, recrie `next-2026`.
   - Sem GitHub Actions; não crie nem altere `.github/workflows`. Nunca force push nem reescreva histórico remoto. Rollback = `git revert` do squash commit.
   - Nunca commite `.env`, segredos, pesos `.pt` ou dados pessoais.

## REGRAS DE VERDADE
- Nada está pronto sem evidência executada. "O compilador aceitou" ≠ "a funcionalidade existe". Cada feature só é dada como pronta com:
  - teste unitário;
  - E2E Playwright passando contra o servidor real;
  - screenshot revisado por você.
- Antes de afirmar qualquer limitação de navegador, plataforma ou biblioteca, leia a doc oficial e cite a URL no CHANGELOG.
- "Não detectado" ≠ "ausente".
- ID de rastreio não é identidade: sem reconhecimento facial, sem nome vinculado a ID, sem ranking individual.
- Nada de métrica, depoimento ou dado inventado na UI. Tudo exibido vem do sistema ou é rotulado como "demo".
- Benchmark fica leve nesta missão. Uma rodada de `scripts/bench.py --rapido` por PR, e a feature volta para revisão se aumentar o CPU-ms por análise em mais de 10% na mediana de 3 execuções. Não abra investigações de desempenho além disso.

## FASE A — PR5: consertos que afetam a demo (fazer primeiro)
P0.1 Prioridade da câmera em foco
O E2E anterior só passou pausando as outras câmeras, ou seja, na demo real o Portal não chega a "Liberado" com 4 câmeras ligadas. Corrija no produto:
- o agendador de inferência passa a usar rodízio ponderado;
- a câmera em foco na UI (portal, tela de foco, Modo Apresentação) recebe pelo menos 50% das vagas de inferência;
- as demais dividem o resto, sem starvation (cada câmera recebe ao menos 1 inferência a cada 3 s).
Remova dos E2E todas as pausas de câmera adicionadas para contornar a disputa. Portal, queda e aproximação precisam passar com 4 câmeras ligadas.

P0.2 Alertas em incidentes
- Agrupe alertas por (câmera, regra, zona) em incidentes, com contagem de pessoas envolvidas e lista de IDs.
- Re-associação de ID: um track novo que surge a até 1,5× a largura da caixa de onde um track sumiu, em até 2 s, herda o ID antigo.
- Meça nas fixtures a quantidade de incidentes antes e depois e registre.
- Na `next_multidao.mp4` com todos os EPIs ligados, o painel deve mostrar no máximo 1 incidente por regra por zona.
- Depois disso, a demo volta a ligar todos os EPIs exigidos.

P0.3 `.env.example`
- Corrija `YOLO_IMGSZ=416` para 640.
- Se suas permissões negarem o arquivo, inspecione `.claude/settings*.json`. Se houver uma regra de negação com padrão amplo como `.env*`, estreite-a para negar `.env` e `.env.*` exceto `.env.example`. Nunca leia nem altere o `.env` real.
- Registre a mudança de permissão no CHANGELOG.

## FASE B — PR5: funcionalidades fora da caixa (nesta ordem)
Toda feature tem que funcionar offline no modo demo, a menos que esteja marcada como online.

X1. Gêmeo digital 3D da fábrica — o momento "uau"
- Use three.js (MIT), com a versão fixada.
- Mostre uma planta isométrica com piso, as zonas de risco como volumes translúcidos e o cone de visão de cada câmera.
- Cada pessoa aparece como um avatar estilizado: cápsula com a cor do estado de conformidade, nunca foto. A posição vem da homografia do G5, com interpolação suave entre análises.
- Clicar numa pessoa abre a linha do tempo e o replay dela. Clicar numa zona mostra o histórico.
- Câmera orbital com limites e um botão "visão de drone".
- Fallback 2D automático se o WebGL falhar.
- Pausar a renderização quando a aba estiver oculta. Meça o tempo de quadro no Playwright e ajuste até ficar em ≤ 33 ms (30 fps) no perfil normal.
- Rota `/gemeo`. Também vira uma cena do Modo Apresentação.

X2. Simulador "E se?" de regras
- Grave trilhas compactas por câmera (posição dos pés, ID, estado dos EPIs, a cada análise) num arquivo rotativo com teto de tamanho, sem imagem.
- Na UI, o técnico edita uma zona (arrasta vértices), muda o tempo de histerese ou liga e desliga um EPI exigido, e reprocessa as últimas N horas.
- O resultado mostra quantos alertas teriam disparado, comparado com os que dispararam de fato, numa linha do tempo lado a lado.
- O simulador é determinístico, roda isolado e nunca altera alertas reais.
- Rota `/simulador`, para técnico ou acima.

X3. Cadeia de custódia das evidências
- Cada evidência (snapshot, clipe, evento de alerta, mudança de privacidade) entra numa cadeia SHA-256 encadeada: hash do conteúdo + hash anterior.
- Botão "Verificar integridade" no incidente e numa página de auditoria.
- Teste obrigatório: adulterar 1 byte de um clipe faz a verificação apontar exatamente o elo quebrado.
- Na banca, isso vira o argumento de LGPD e prova jurídica.

X4. Linha causal do incidente
Uma narrativa determinística, sem LLM, montada a partir dos eventos do ID. Exemplo: "13:02:10 aproximou-se da Zona A (projeção ~4 s) → 13:02:14 entrou sem capacete → permaneceu 38 s → 13:02:52 postura de risco → alerta reconhecido em 6 s". Cada passo leva ao quadro correspondente do replay.

X5. Modo Raio-X
Uma camada alternável sobre o vídeo com:
- esqueleto da pose;
- barras de confiança por classe;
- trilhas fantasma dos últimos 5 s de cada pessoa, desbotando;
- vetor de velocidade do F3;
- a decisão final do sistema separada da confiança bruta do modelo.
Atalho: tecla X.

X6. Modo Apresentação (palco) com controle pelo celular
- Rota `/palco`. Cenas pré-roteiradas seguindo o DEMO.md, com legenda curta em cada cena; espaço ou → avança, ← volta.
- No modo demo, cada cena prepara o próprio estado de forma determinística (câmera em foco, gatilhos de fixture).
- Um QR code na tela abre `/palco/controle` no celular (HTTPS do F6), com botões grandes de anterior/próximo e o nome da cena atual.
- Se o celular falhar, o teclado continua funcionando.
- E2E: percorrer todas as cenas pelo teclado e pelo controle (Chromium emulando celular).

X7. Retrospectiva da Segurança (estilo "Wrapped")
- Stories animados de fim de turno e de semana, com dados reais: horas de conformidade da equipe, setor destaque, alertas reconhecidos mais rápido, contribuições de rótulo, missões cumpridas.
- Cada card pode ser exportado como PNG.
- Abre no Modo TV ao fim do turno.
- Nada individual.

X8. Gamificação de verdade, em nível de equipe
- Liga de Setores com temporadas semanais. A pontuação vem só de indicadores positivos:
  - check-in no portal;
  - alerta reconhecido rápido;
  - falso positivo revisado;
  - rótulo contribuído;
  - minutos de conformidade.
  Nunca premiar "zero alertas" nem penalizar quem gera ou reporta alerta.
- Missões da equipe por turno (ex.: "100% dos check-ins antes das 8h", "revisar 20 rótulos"), configuráveis pelo supervisor.
- Nível da planta (XP acumulada), com celebração discreta ao subir de nível ou cumprir missão: confete leve e som curto, respeitando o mute e `prefers-reduced-motion`.
- Aparece no Modo TV, na Visão geral e na Retrospectiva.

X9. "Tente enganar a IA" no Portal
- Um modo desafio do G1 em que o visitante tenta passar com um "EPI falso" (boné no lugar do capacete etc.).
- O sistema mostra o que detectou e por quê (Raio-X).
- Placar anônimo da sessão: tentativas, quantas enganaram, quantas foram pegas. Mostre com honestidade quando a IA for enganada.

X10. PWA do supervisor
- O app vira instalável, com manifesto, service worker de shell offline e ícones originais.
- Com o app aberto: vibração e notificação local em alerta crítico.
- Leia e cite a doc da MDN sobre Notifications e Service Worker (exigem secure context).
- Push com o app fechado não entra (exigiria serviço externo); registre isso.

Laboratório (desligado por padrão, só se sobrar tempo depois do PR6): comando de voz. Antes, verifique e cite se o reconhecimento de fala do navegador funciona offline. Se depender de servidor externo, marque como online-only.

## FASE C — PR6: experiência SSS+++
1. Leia e siga `.agents/skills` (incluindo `apple-design` e `design-taste-frontend`). Direção: clean, premium, estilo Apple; cor usada só para estado; tema claro como padrão do demo e escuro impecável. Nada de cara de template ou de dashboard genérico.
2. Sistema de design consolidado:
   - tokens de cor, tipografia, espaçamento (grade de 4/8), raio, sombra e movimento (durações e curvas nomeadas);
   - fontes self-hosted com licença OFL (offline);
   - ícones consistentes;
   - componentes únicos para botão, card, badge de estado, tabela, modal, toast, skeleton e estado vazio;
   - documentar em `docs/NEXT2026/DESIGN.md`.
3. Movimento:
   - View Transitions entre rotas, com fallback (cite a doc);
   - entrada de alerta, números animados e transições de painel;
   - tudo respeitando `prefers-reduced-motion`.
4. Estados:
   - todo carregamento tem skeleton;
   - todo vazio tem ilustração SVG original e uma ação;
   - todo erro tem recuperação.
   - Busque e elimine qualquer "em construção", "TODO", lorem ou placeholder visível (grep + screenshot).
5. Acessibilidade: axe-core via Playwright sem violações sérias ou críticas em todas as rotas, contraste AA nos dois temas e navegação completa por teclado nas rotas principais.
6. README de vitrine: imagem e GIF de topo gerados a partir das capturas, com destaques e um "como rodar em 3 comandos".
7. Ciclo de revisão visual, obrigatório, no mínimo 2 iterações por rota:
   - capture todas as rotas e estados importantes (vazio, carregando, alerta crítico, degradado, sem sinal) nos dois temas, em 1920×1080, 1366×768 e 390×844 (celular);
   - critique cada captura por escrito contra esta rubrica, com nota de 0 a 5 por item: hierarquia, alinhamento, espaçamento, contraste e legibilidade a 5 m, consistência com o sistema de design, densidade, "parece template?" e "uma banca ficaria impressionada?";
   - corrija tudo abaixo de 4 e capture de novo.
8. Galeria: `docs/NEXT2026/galeria/` com as capturas finais em WebP (≤ 250 KB cada), o antes/depois das telas que mais mudaram e um `index.md` com todas as imagens e as notas finais da rubrica.

## FASE D — testes, vídeo de backup e release
1. Portão de cada PR: pytest completo, ruff, build e typecheck do frontend, E2E completo em rodada única com 4 câmeras ligadas e sem pausas de contorno, axe e a rodada rápida de bench.
2. Teste de clone limpo:
   - clone o repositório num diretório temporário;
   - siga o README à risca (venv nova, instalação, download de pesos, `python run.py --demo`);
   - rode um E2E de fumaça contra esse clone.
   Qualquer passo que falhar é bug do README ou do setup: corrija.
3. Vídeo de backup da demo:
   - grave com Playwright o Modo Apresentação percorrendo todas as cenas em 1920×1080;
   - converta para MP4 (ffmpeg, se disponível; senão mantenha WebM e registre);
   - publique como asset de uma GitHub Release `next-2026-demo` via `gh release create`, sem Actions;
   - cite o link no DEMO.md como plano B.
4. Atualize DEMO.md (novo roteiro com Palco, Gêmeo 3D, Raio-X, Simulador, Custódia, Tente enganar a IA e Retrospectiva, mais o plano B), BANCA.md (perguntas novas sobre gamificação, custódia, simulador e 3D) e CHANGELOG.
5. PR7 Release:
   - crie `release-main` a partir de `feat/completo-com-rebrand` e faça `git merge origin/main -X ours`, para que o conteúdo final do VisionEPI prevaleça nos conflitos e as mudanças de `main` sem conflito sejam incorporadas;
   - liste no CHANGELOG cada arquivo onde a versão da `main` foi descartada;
   - rode o portão completo e o teste de clone limpo, agora em `main`;
   - abra o PR `release-main` → `main` e faça squash merge;
   - rollback = tag `main-pre-release`.

## PARADA E RESUMO
Pare quando PR5, PR6 e PR7 estiverem mergeados com portões verdes e a galeria e o vídeo publicados. Funcionalidade que não ficar confiável sai do roteiro, fica desligada por padrão e é registrada; ela não vai para a demo.

Resumo final em até 30 linhas:
- links dos PRs e da Release;
- caminho da galeria;
- tabela com cada feature X1–X10, os itens P0 e o status (pronto com E2E, laboratório ou descartada, e o motivo);
- contagem de incidentes na multidão, antes e depois;
- tempo até "Liberado" no Portal com 4 câmeras ligadas;
- resultado do teste de clone limpo;
- as 3 maiores ameaças restantes para a apresentação.

## ADENDO 2 — retomada depois do reinício do PC (14/10/2026)

O PC reiniciou no meio da sessão anterior, durante o bench intercalado "antes × PR5".

### Recuperação (antes de qualquer outra coisa)
1. `git status` e `git worktree list`. Rode `git worktree prune`. Encerre só processos seus que tenham sobrado (servidor do VisionEPI, Chromium do Playwright, bench) e libere portas e arquivos `.db` presos.
2. Se houver alteração sem commit em `next-2026`, faça commit agora ("wip: recuperação pós-reinício") e `git push -u origin next-2026`.
3. Regra nova, vale até o fim da missão: commit + push da branch de trabalho a cada marco e antes de qualquer tarefa com mais de 10 minutos rodando em segundo plano. Nada importante fica só no disco local.
4. Rode pytest completo, ruff e build, para confirmar que o estado em disco é o mesmo que passou antes do reinício (649 unitários, E2E 33/33 na rodada 8). Se algo divergir, investigue antes de seguir.

### Ajustes antes do merge do PR5
A. Tempo até "Liberado" no Portal
- Meça com o E2E do portal repetido 10 vezes, com 4 câmeras ligadas, e registre p50 e p95.
- Meta: p50 ≤ 5 s e p95 ≤ 10 s.
- Se não atingir, aumente o peso da câmera em foco no agendador (até 70% das vagas, mantendo a regra de nenhuma câmera ficar mais de 3 s sem inferência) e/ou reduza as confirmações exigidas no portal para 3 quadros, se cada item continuar exigindo confirmação estável. Meça de novo.
- Registre no CHANGELOG os números antes e depois.

B. Queda na demo
- Mantenha a regra de 2 análises seguidas.
- No modo demo, a cena "Queda" do `/palco` passa a tocar a gravação da queda ao vivo a 0,25× da velocidade original, com o rótulo "GRAVAÇÃO · 0,25×" sempre visível sobre o vídeo, e o alerta aparece ao vivo. O replay do incidente continua como continuação da cena.
- E2E: o alerta de queda aparece na cena do palco com o rótulo de velocidade visível (verifique o texto do rótulo no DOM).
- No BANCA.md, inclua a pergunta "Vocês detectam uma queda que dura menos de 1 segundo ao vivo?" com a resposta honesta e medida: taxa de análise por câmera, duração da queda na fixture, por que a demo usa 0,25× e o que melhoraria isso (mais análises por segundo ou hardware dedicado).

### Depois
1. Refaça o bench intercalado "antes × PR5" (3 repetições, 1 e 4 câmeras), seguindo a regra de bench leve da MISSAO-2.
2. Rode o portão completo do PR5 numa rodada única: pytest, ruff, build, E2E com 4 câmeras sem pausas de contorno, axe. Abra o PR5 e faça squash merge.
3. Siga a MISSAO-2 a partir da Fase C (PR6) e depois a Fase D (PR7 → main), atualizando o ESTADO.md a cada marco.

## ADENDO 3 — fechar o PR6 e a Fase D com integração honesta com a main (14/10/2026)

Leia docs/NEXT2026/MISSAO-2.md e docs/NEXT2026/ESTADO.md. Acrescente este texto ao final da MISSAO-2.md como "ADENDO 3" e continue em modo autônomo até o merge final na main, sem perguntar nada.

### Regras deste adendo
- Ação negada pela permissão (apagar branch remota, rm -rf etc.): não tente contornar com outro comando. Registre no ESTADO.md e siga. Para pastas temporárias, use nomes novos em vez de apagar.
- Commit + push da branch de trabalho a cada marco e antes de qualquer tarefa longa em segundo plano.
- Nunca use `| tail` ou pipe que esconda o código de saída de testes. Grave a saída em arquivo e confira o exit code.

### 1. Fechar o PR6
1. Confira o MP4 e o GIF do palco gerados em segundo plano: duração, resolução e se todas as cenas aparecem (extraia 1 quadro por cena e revise). Se estiverem com defeito, grave de novo. Copie o GIF para `docs/NEXT2026/galeria/readme/palco.gif` (≤ 8 MB; se passar, reduza fps ou tamanho). Confirme que todas as imagens referenciadas no README existem no repositório.
2. Portal com cenário realista:
   - crie a fixture `portal.mp4` derivada, recortando e ampliando um único trabalhador de capacete e colete de uma fixture existente (ou de outro vídeo de licença livre do Wikimedia Commons, com uma pessoa de perto), com 15–30 s e a licença registrada em ATRIBUICOES;
   - meça com o E2E do portal repetido 10 vezes, 4 câmeras ligadas, e registre p50 e p95 com essa fixture;
   - no `/palco`, cada cena declara quais câmeras ficam ativas. Durante a cena do Portal, as câmeras fora da cena ficam pausadas e a UI mostra "pausada pela apresentação"; ao sair da cena, voltam. Meça de novo no palco;
   - fora do palco, o comportamento do agendador continua o mesmo (foco com 50%);
   - meta no palco: p50 ≤ 5 s e p95 ≤ 10 s. Registre os números finais no CHANGELOG, no DEMO.md e no BANCA.md, mesmo se não bater a meta.
3. Partida a frio:
   - leia a doc oficial do OpenVINO sobre cache de modelo (propriedade CACHE_DIR) e cite a URL;
   - ative o cache em `runtime/ov_cache/` (fora do git) e faça o `scripts/preparar.py` aquecer o cache;
   - meça a subida do `python run.py --demo` a frio e com o cache aquecido, até a primeira análise publicada, 3 vezes cada;
   - registre os números no DEMO.md, com a instrução de rodar `scripts/preparar.py` antes da apresentação.
4. Portão completo do PR6 numa rodada única: pytest completo, ruff, build e typecheck, E2E completo com 4 câmeras e axe nos dois temas, e `bench.py --rapido`.
5. Rode as capturas finais de novo só nas telas alteradas depois da última rodada, atualize a galeria e as notas da rubrica, abra o PR6 e faça squash merge em `feat/completo-com-rebrand`.

### 2. Fase D (como na MISSAO-2), com esta mudança na integração com a main
1. Teste de clone limpo seguindo o README à risca, até `python run.py --demo` e um E2E de fumaça contra o clone. Corrija o que falhar.
2. Publique a Release `next-2026-demo` com o MP4 do palco como asset (`gh release create`, sem Actions) e cite o link no DEMO.md.
3. Integração com a main, substituindo o `-X ours` da MISSAO-2:
   - crie `release-main` a partir de `feat/completo-com-rebrand` e faça `git merge origin/main` sem estratégia automática;
   - resolva os conflitos arquivo por arquivo:
     - interface, infraestrutura, pipeline e docs do NEXT: vale a versão da `feat/completo-com-rebrand`;
     - mudanças funcionais da main que não conflitam com o comportamento atual (ex.: correções, conteúdo da Sprint 4): incorpore;
     - modelo/peso de EPI padrão: mantenha o atual da `feat/completo-com-rebrand`, porque todas as medições, guardas e E2E foram feitos com ele. Se o peso definido pela main existir e carregar, exponha-o como opção de config documentada no README.
   - para cada um dos arquivos em conflito, registre no CHANGELOG uma linha com o arquivo, a versão que ficou e o motivo; nada da main é descartado sem registro;
   - rode o portão completo e o teste de clone limpo em `release-main`;
   - abra o PR7 `release-main` → `main` e faça squash merge (rollback: tag `main-pre-release`);
   - depois do merge, rode um E2E de fumaça e `python run.py --demo` partindo da própria `main` atualizada.
4. Atualize o ESTADO.md: a `main` passa a ser a branch final da apresentação.

### Resumo final (até 30 linhas)
- links dos PRs 6 e 7 e da Release;
- p50/p95 do portal com `portal.mp4`, no palco e fora dele;
- tempo de subida a frio e com o cache aquecido;
- tabela das decisões de conflito com a main (arquivo → versão que ficou);
- resultado do clone limpo na main;
- as 3 maiores ameaças restantes para a apresentação.
