# MISSÃO VisionEPI — FIAP NEXT 2026 (sessão nova, autossuficiente)

Repositório: https://github.com/bolla-X/Challenge_5550
Você trabalha 100% autônomo do início ao fim: sem pedir aprovação, sem pedir teste manual a ninguém, sem sugerir pedir algo a outras pessoas. Toda bifurcação já está decidida abaixo. Se algo bloquear, registre e siga para o próximo item. A final NÃO é hoje: não pegue atalho por prazo.

## PASSO 0 — Persistência da missão (primeira coisa)
1. Salve este prompt inteiro, sem alterar, em `docs/NEXT2026/MISSAO.md`.
2. Crie (ou atualize, se existir) `docs/NEXT2026/ESTADO.md` e reescreva-o a cada marco: o que está pronto, commit, comando de verificação, próximo passo exato. Sessões futuras retomam só com esses dois arquivos.
3. `git push -u origin next-2026 next-2026-pr2-wip wip-preservado-2026-10-12` (backup remoto; não abre PR). Se alguma não existir, registre.
4. Registre no ESTADO.md a carga de fundo da máquina (CPU% por processo de terceiros). Não encerre processos que não sejam seus.

## REGRAS DE VERDADE
1. Nada está "feito" sem evidência executada. "O compilador aceitou" ≠ "a funcionalidade existe". Toda afirmação de desempenho ou funcionamento leva o comando e o número/saída.
2. Antes de declarar limitação de plataforma ou biblioteca, leia a documentação oficial e cite a URL no CHANGELOG.
3. Nunca invente resultados, repositórios, citações ou texto de norma. Estimativa é rotulada como estimativa.
4. Não desligue testes nem afrouxe asserts.
5. "Não detectado" ≠ "ausente". A UI nunca afirma ausência de EPI quando o item está fora do enquadramento.
6. ID de rastreio não é identidade. Sem reconhecimento facial, sem nome de pessoa vinculado a ID, sem ranking individual.

## GIT
- Base: `feat/completo-com-rebrand`. Rollback total: tag `pre-next-2026` (já publicada).
- 4 PRs consolidados, nessa ordem, contra a base, cada um mergeado por você com `gh pr merge --squash --delete-branch` assim que o portão passar:
  - PR1: performance + benchmark
  - PR2: diferenciais F1–F10
  - PR3: funções criativas G1–G10
  - PR4: modo demo + confiabilidade + docs
  Depois de cada merge, recrie `next-2026` a partir da base atualizada.
- Portão de cada PR: pytest completo, `ruff check .`, `npm --prefix frontend run build`, E2E Playwright verdes, e nenhuma métrica principal do bench pior que 5% versus o PR anterior. Falhou e não corrige → `git revert` do commit culpado dentro da branch antes do merge.
- Rollback pós-merge: `git revert` do squash commit. Nunca force push, nunca reescrever histórico remoto.
- Sem GitHub Actions: não crie nem altere `.github/workflows`. Nunca commite `.env`, segredos, pesos `.pt`, vídeos ou dados pessoais.
- Ao testar Ultralytics 8.4, use sempre `YOLO_CONFIG_DIR` separado (a sessão anterior sobrescreveu o settings.json do usuário).

## ESTADO HERDADO (verifique tudo, não confie)
- `next-2026` (local, candidato ao PR1). Contém:
  - captura "último quadro vence" e agendador único de inferência em rodízio;
  - encode e overlay sob demanda, overlay desenhado em canvas no navegador;
  - telemetria por sala de foco e snapshot assíncrono;
  - controlador adaptativo e estados de feed;
  - pose yolo11n-pose por pessoa;
  - escolha de runtime via `models/export/aprovados.json` (ONNX dinâmico aprovado com 100% de concordância);
  - ByteTrack vendorizado (MIT) em config;
  - correção de afinidade de CPU em `run.py`/`wsgi.py`;
  - `scripts/bench.py`, `scripts/concordancia.py`, `scripts/comparar_trackers.py`;
  - docs AUDITORIA, PESQUISA, ATRIBUICOES e rascunho do CHANGELOG.
- `next-2026-pr2-wip` (b344f5e, local): F1 replay, F3 aproximação, F4 privacidade, F5 diagnóstico, F7 mapa de calor, F9 relatório de turno, F10 prova de escala, Sobre/Licenças e "Iniciar" ligando todas as câmeras. Frontend não compilado e suíte completa não rodada.
- Já medido:
  - imgsz 416 reprovado no guarda (capacete com 8% de concordância vs 640) → default 640;
  - OpenVINO e ONNX estático reprovados (95,04%);
  - fixtures do Wikimedia Commons: `bench.mp4`, `next_multidao.mp4`, `next_queda.mp4`. O Pexels bloqueia download automatizado.
- Guarda de qualidade: concordância por classe (mesma classe, IoU ≥ 0,5) contra a referência PyTorch@640. Mínimo de 97% para troca de runtime e de 95% para mudança de resolução.

## FASE 1 — Fechar e mergear o PR1
1. Confira `bench/results`. Refaça, intercaladas e com o código congelado em worktree, as rodadas incompletas ou com CPU do servidor acima de 200% no perfil batata (2 núcleos fixados).
2. Adicione ao bench as métricas principais do portão:
   - FPS de análise por câmera;
   - idade da análise p50/p95 (da captura até o resultado publicado);
   - latência de alerta (do primeiro quadro com a violação na fixture até o evento chegar ao navegador).
   Mantenha as de vídeo como secundárias.
3. A sessão anterior anotou "640 fica em 72% de concordância", o que é impossível se 640 é a referência. Rode de novo, descubra o que gerou o número e corrija o registro.
4. OpenVINO: inspecione se o export "dinâmico" saiu mesmo com shape dinâmico. Se saiu estático, refaça com o letterbox retangular usado no ONNX dinâmico e rode o guarda uma vez. Se a CPU não for Intel, registre e pule.
5. Runtime: vence o aprovado no guarda com menor idade da análise p95 no perfil batata com 1 câmera. Empate dentro de 5% → PyTorch.
6. Tracker: ByteTrack vira default se reduzir fragmentações nas fixtures e seu custo p95 for ≤ 3% da inferência p95 no perfil batata. Senão, fica em config.
7. Confirme que o controlador adaptativo nunca reduz imgsz abaixo de 640. Ele só mexe em frequência de inferência, de pose e de UI.
8. Escreva `docs/NEXT2026/BENCHMARKS.md`: perfis atual e batata, 1 e 4 câmeras, carga de fundo e limitações.
9. Portão → PR1 squash → ESTADO.md.

## FASE 2 — PR2 (diferenciais F1–F10)
1. Traga `next-2026-pr2-wip` para a nova `next-2026` (rebase ou cherry-pick), preservando o PR1. Compile o frontend e rode a suíte completa antes de qualquer código novo.
2. F2: alerta de queda pela classe `Fall-Detected` do Vyra, atribuída à pessoa de maior sobreposição, e linha do tempo de conformidade por ID. E2E obrigatório com fixture real mostrando o alerta de queda no navegador atribuído a um ID. Se o Vyra não detectar queda em nenhuma fixture de licença livre testada, a queda sai do roteiro da demo e vai para o BANCA.md com explicação honesta.
3. F6 (celular como câmera via QR code): página `/cam` com `getUserMedia`; leia a doc de secure context e getUserMedia (MDN) e cite-a. HTTPS com certificado autoassinado gerado com o `cryptography` já instalado. QR por implementação pequena e de licença permissiva, registrada em ATRIBUICOES. Teste com Chromium usando `--use-fake-device-for-media-stream`. Se não ficar confiável, vira laboratório.
4. F8 (YOLOE-26, vocabulário aberto): só se o Ultralytics 8.4 carregar o Vyra e a suíte passar. Senão, registre e descarte.
5. E2E:
   - replay abre e toca;
   - pill de aproximação aparece;
   - privacidade só alternável por supervisor;
   - diagnóstico mostra o runtime ativo;
   - relatório de turno abre.
6. Screenshots Playwright de todas as rotas, nos dois temas, em 1920×1080 e 1366×768. Revise você mesmo e itere seguindo `.agents/skills` (`apple-design`, `design-taste-frontend`): visual clean, cor só para status, tema claro como padrão do modo demo.
7. Portão → PR2 squash → ESTADO.md.

## FASE 3 — PR3 (funções criativas G1–G10)
Regras gerais:
- Implemente na ordem abaixo.
- Cada item primeiro vira protótipo mínimo medido no perfil batata. Entra se custar ≤ 10% do orçamento de frame e passar no seu teste; caso contrário, vira laboratório (desligado por padrão) ou é descartado, sempre com registro.
- Toda feature nova tem teste unitário e, se tiver UI, um E2E.

Princípios de gamificação (obrigatórios):
- Premiar só indicadores positivos: checagem no portal feita, alerta reconhecido rápido, falso positivo revisado, contribuição de rótulo, minutos de conformidade do setor.
- Nunca premiar "zero alertas", nunca penalizar quem gera ou reporta alerta.
- Pontuação só por equipe/setor/câmera. Nenhum ranking individual nem por ID de rastreio.

G1. Portal de Entrada (check-in de EPI)
- Rota `/portal` em tela cheia, ligada a uma câmera escolhida (na demo, a webcam do notebook como fonte 0; nos testes, fixture).
- A pessoa para diante da câmera e vê um checklist animado só dos EPIs exigidos para aquele setor (configurável por câmera).
- Cada item tem um de três estados: confirmado, faltando, ou "não verificável neste enquadramento" (luva ou calçado fora do quadro).
- Quando todos os itens exigidos e verificáveis estão confirmados por N quadros, aparece "Liberado". A checagem conta para a meta da equipe.
- Sem foto salva por padrão; se houver evidência, ela passa pelo F4.
- E2E com fixture.

G2. "Você vs. a IA" (treinamento e desafio da banca)
- Rota `/desafio`: toca clipes curtos (do F1 ou fixtures, sempre com desfoque F4), e o usuário clica nas pessoas com infração antes do tempo acabar. Depois o sistema revela as detecções da IA e o gabarito.
- O gabarito vem de alertas confirmados (não marcados como falso positivo) ou, nas fixtures, de um gabarito curado por você a partir de quadros extraídos, documentado em `docs/NEXT2026/GABARITO.md`.
- Mostra acertos, erros e tempo do humano versus a IA, de forma honesta (inclusive quando a IA erra).
- Placar da sessão sem nomes reais (apelido livre opcional que não fica salvo no banco).

G3. SOS por gesto
- Ambos os punhos acima da cabeça (keypoints de pose) por ≥ 3 s, atribuído a um ID, geram alerta crítico de emergência com histerese.
- Teste unitário com keypoints sintéticos é obrigatório.
- Para entrar no roteiro da demo, precisa também de verificação com um vídeo real de licença livre em que alguém ergue os braços. Sem esse vídeo, a feature entra no app, mas não no roteiro.

G4. Pessoa imóvel em zona de risco
- O track tem deslocamento abaixo de um limiar por mais de X s (configurável) dentro de uma zona → alerta "pessoa imóvel", com rótulo claro de que não é diagnóstico.
- Teste com fixture ou trecho em que alguém fica parado.

G5. Planta baixa ao vivo
- Calibração de homografia: o técnico clica 4 pontos na imagem da câmera e os 4 pontos correspondentes numa planta (upload de imagem ou uma planta SVG padrão gerada para as fixtures).
- Os pés de cada track são projetados como pontos ao vivo na planta, com zonas de risco e o mapa de calor (F7) também na planta.
- Teste unitário da projeção com pontos conhecidos.
- Planta multi-câmera se o custo couber.

G6. Alerta falado em pt-BR
- `speechSynthesis` do navegador com voz pt-BR para alertas críticos ("Atenção: pessoa sem capacete na câmera 2"), respeitando o mute existente.
- Leia a doc (MDN) e cite-a. Verifique se existe voz pt-BR offline na máquina; se não houver, use os bipes existentes como fallback.
- Fila e limite de taxa para não falar por cima.

G7. Ergonomia (estimativa)
- Ângulo de flexão do tronco (vetor quadril → ombros contra a vertical) por ID, com tempo acumulado acima de 45° e de 60°.
- Alerta de "postura de risco ergonômico (estimativa)" por duração configurável.
- Não afirme conformidade com RULA, REBA ou NR-17. Se citar a NR-17, cite a página oficial gov.br.

G8. Modo TV / Andon + metas da equipe
- Rota `/tv`: legível a 5 m, com estado de cada câmera, conformidade atual por setor, sequência de minutos com 100% dos EPIs exigidos por setor e conquistas do setor (ex.: "turno com 100% capacete", "todas as checagens do portal feitas").
- Metas configuráveis por supervisor, só no nível de setor.
- Animação discreta e com `prefers-reduced-motion` respeitado.

G9. Aprendizado ativo
- Detecções com confiança entre 0,25 e 0,5 geram recortes desfocados (F4) numa fila limitada.
- Rota `/rotular`: o técnico confirma ou rejeita cada recorte com teclado (atalhos ← →) ou toque.
- Exporta zip no formato de dataset YOLO, com README e licença dos dados.
- Contador de contribuições da equipe entra no G8.
- Sem treino dentro do app.

G10. Relatório mapeado à NR-6
- No relatório de turno (F9), cada tipo de infração de EPI é ligado ao requisito correspondente da NR-6.
- Leia o texto oficial da NR-6 no gov.br, cite a URL e use só trechos que existam lá. Se algum mapeamento não for sustentado pelo texto, deixe-o de fora.

Laboratório (só depois de G1–G10, desligado por padrão):
- "Pergunte à planta": perguntas em linguagem natural sobre o histórico de alertas, usando a integração de LLM existente.
- Somente leitura, com consultas restritas a um conjunto fixo de agregações parametrizadas (nunca SQL livre gerado pelo modelo).
- Chave só no backend, resposta rotulada como gerada, e funcionamento sem internet não é exigido.

Portão → PR3 squash → ESTADO.md.

## FASE 4 — PR4 (demo, confiabilidade, docs)
1. `python run.py --demo` offline. Ele:
   - cria um banco isolado;
   - cria usuários de demo com senha gerada e impressa só no terminal;
   - carrega câmeras de fixture rotuladas "GRAVAÇÃO" e a webcam rotulada "AO VIVO" quando existir;
   - usa tema claro.
2. `flask demo reset` em menos de 10 s.
3. Roteiro de 5 minutos contendo só momentos que passaram no E2E, na ordem antes → durante → depois:
   - Portal (G1, com um jurado);
   - tracking e EPI;
   - aproximação (F3) e entrada na zona;
   - planta baixa (G5);
   - SOS por gesto, se verificado;
   - replay com privacidade (F1/F4);
   - diagnóstico (F5);
   - prova de escala (F10);
   - "Você vs. a IA" (G2, com um jurado);
   - Modo TV (G8).
4. Soak de 20 min com 4 câmeras (crescimento de RSS < 10%, sem erros no console). Testes de falha: modelo ausente, fonte inválida, webcam ausente, LLM fora do ar, banco indisponível.
5. Docs:
   - `docs/NEXT2026/DEMO.md`: roteiro minuto a minuto, o que deve aparecer em cada momento, reset e plano B por falha.
   - `docs/NEXT2026/BANCA.md`: as 15 perguntas mais difíceis com respostas sustentadas por números medidos, incluindo os riscos da gamificação e como o design os evita, além de LGPD e licenças.
   - README atualizado e CHANGELOG final.
6. Portão → PR4 squash → ESTADO.md.

## PARADA E RESUMO
Pare quando os 4 PRs estiverem mergeados com portões verdes e o restante for só baixo impacto, bloqueado ou reprovado no guarda.

Resumo final em até 25 linhas:
- links dos PRs;
- tabela antes/depois com idade da análise p95, latência de alerta e FPS de análise no perfil batata;
- features que entraram, as que foram para laboratório e as descartadas, com o motivo;
- os 3 maiores riscos remanescentes para a apresentação.

---

# ADENDO 1

PARE o ciclo de benchmark. Leia este adendo, acrescente-o ao final de docs/NEXT2026/MISSAO.md como "ADENDO 1" e siga em modo autônomo.

## Diagnóstico
A máquina está saturada por processos de terceiros, então tempos de relógio (FPS, idade, latência) medem a carga de fundo e não o VisionEPI. Com ~4 análises por rodada, comparações de FPS de análise não têm validade estatística. Correção de registro: "FPS de análise 0,06 vs 0,08 da base" é regressão nominal, não melhoria; reescreva no CHANGELOG como "inconclusivo sob saturação (n≈4 análises)".

## Higiene de benchmark (substitui a regra dos 5%)
1. Antes de cada rodada, meça por 30 s a CPU de processos de terceiros e grave no JSON.
2. [OPCIONAL — autorizado] Antes de cada rodada: `wsl --shutdown` e encerrar o Docker Desktop. Religue o Docker Desktop ao terminar a rodada. Não toque em nenhum outro processo de terceiros.
3. Métricas de portão sob saturação, por serem menos sensíveis à disputa:
   - CPU-ms do processo do servidor por análise concluída;
   - CPU-ms por quadro publicado;
   - contadores determinísticos (encodes por quadro, emissões de socket por quadro, cópias evitadas).
   Tempos de relógio seguem no relatório, rotulados "sob saturação — indicativo".
4. Sempre 3 repetições, com ordem base/novo alternada. Uma métrica só reprova se a mediana do novo for pior que a da base em mais de 10% e as 3 repetições concordarem na direção.
5. Teto: no máximo 2 rodadas de bench por decisão. Se não decidir em 2, vale o default mais simples (PyTorch, tracker IoU), registrado como "inconclusivo".
6. Números absolutos para o BENCHMARKS.md final e para a banca só valem se a CPU de terceiros estiver abaixo de 15% na rodada. Se isso não acontecer até o PR4, o BENCHMARKS.md diz isso explicitamente, e o DEMO.md inclui um comando `python scripts/bench.py --rapido` (≤ 5 min) para rodar na máquina da apresentação antes da final.

## Decisões imediatas
A. Encerre a comparação de spinning com o que já tiver. Defaults:
   - spinning desligado, a menos que reduza CPU-ms por análise em mais de 10% nas 3 repetições;
   - runtime: o aprovado no guarda com menor CPU-ms por análise no perfil batata com 1 câmera; empate dentro de 10% → PyTorch.
B. PR1: se pytest, ruff, build e os E2E passarem e nenhuma métrica do item 3 reprovar pela regra do item 4, abra e mergeie o PR1 agora (squash) e atualize o ESTADO.md.
C. Resolva o "640 = 72% de concordância" em uma execução de no máximo 10 minutos e registre a explicação.

## Duas alavancas grandes (logo após o merge do PR1, antes do PR2, em branch própria que entra no PR2)
L1. OpenVINO na iGPU Intel
1. Leia a doc oficial do export OpenVINO da Ultralytics e a do plugin GPU do OpenVINO; cite as URLs.
2. Refaça o export com shape dinâmico de verdade e o mesmo letterbox retangular do ONNX dinâmico. Inspecione o modelo exportado para confirmar o shape.
3. Rode o guarda de concordância (≥ 97%) para os dispositivos CPU e GPU, em FP32 e FP16.
4. Aprovado no guarda e com menor CPU-ms do servidor por análise → entra no `auto` com prioridade máxima, com fallback garantido.
5. O dispositivo ativo aparece no painel de diagnóstico.
6. Se o plugin GPU não enxergar a iGPU, registre a saída de `openvino.Core().available_devices` e a página da doc, e siga.

L2. Modo batata com modelo de EPI leve
1. Busque no Hugging Face e no GitHub modelos de detecção de EPI em YOLO tamanho n ou s, com pesos públicos e licença permissiva compatível. Busque também um conjunto de teste de EPI rotulado e público com licença compatível, cobrindo capacete e colete no mínimo.
2. Avalie o Vyra e cada candidato no MESMO conjunto rotulado: mAP50 e recall por classe, com mapeamento explícito de nomes de classe.
3. O candidato vira o modelo do "modo batata" se:
   - o recall de capacete e de colete ficar no máximo 5 pontos abaixo do Vyra;
   - a inferência levar no máximo 1/3 do tempo do Vyra no perfil batata.
4. Ele fica selecionável por config e pelo controlador adaptativo, como degrau máximo de degradação, com o banner DEGRADADO informando "modelo leve". O Vyra continua como default de qualidade.
5. Sem candidato aprovado ou sem conjunto rotulado de licença compatível → registre o que foi tentado e siga.
6. Não treine nem faça fine-tune nesta máquina.

Depois disso, siga o MISSAO.md a partir da Fase 2 (PR2), usando a higiene de benchmark deste adendo em todos os portões seguintes. Mantenha o ESTADO.md atualizado a cada marco.
