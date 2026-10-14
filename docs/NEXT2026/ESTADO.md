# ESTADO — MISSÃO 2

Retomar lendo só este arquivo e `MISSAO-2.md` (incluindo os ADENDOS 2 e 3 no
fim). Reescrito a cada marco. (A missão anterior, PRs #10–#13, está em
`MISSAO.md` e no CHANGELOG.)

## Rollback

- `pre-missao-2` = HEAD de `feat/completo-com-rebrand` antes da missão (`906c81e`).
- `main-pre-release` = HEAD de `main` antes do release (`6c3ed61`).

## Regras em vigor (ADENDOS 2 e 3)

- Commit + push de `next-2026` a cada marco e antes de tarefa longa em segundo plano.
- Ação negada pela permissão: não contornar; registrar aqui e seguir.
- Saída de teste sempre em arquivo, conferindo o exit code (nada de `| tail` escondendo o código).

## Marco atual: ADENDO 3, item 1 (fechar o PR6)

Feito e commitado em `next-2026`:
- 1.1 vídeo do palco conferido (142 s, 1920×1080, 12 cenas). Defeitos: o GIF
  começa no login, e o Portal mostrava a multidão. Regravar depois do item 1.2
  (o GIF passa a começar no palco).
- 1.2 `portal.mp4` (fetch_fixtures, recorte + vai-e-volta): close de um armador
  de frente, capacete e colete, quadros 7000–7084 do vídeo 13 do Moira Close
  (CC BY-SA 4.0), 16,6 s. Medido: pessoa 88 %, capacete ≥ 0,40 em 64 %, colete
  em 71 % das amostras. Candidatos descartados: plano da laje (de costas, atrás
  da tela: capacete 0/14), vídeo 21 do Moira Close (capacete raro), andaime
  (Coyau, sem colete, distante), NIOSH (entrevista).
- Demo sem webcam ganha a câmera "Portal" (portal.mp4); E2E: "Canteiro" toca portal.mp4.
- Palco: cada cena declara `ativas` ("todas" | "cena"); Portal e Enganar pausam
  as outras (pausa leve: sem análise, captura a 1 q/s, alertas preservados),
  status `pausa: "apresentacao"`, UI "Pausada pela apresentação"; lease de 8 s
  renovado pela tela do palco. Unitários em tests/test_palco.py.
- 1.3 cache do OpenVINO em `runtime/ov_cache` (`OV_CACHE_DIR`), GPU e CPU;
  `scripts/preparar.py --so-cache` aquece; `scripts/medir_partida.py --frio 3 --quente 3`.
  Doc: https://docs.openvino.ai/2025/openvino-workflow/running-inference/optimize-inference/optimizing-latency/model-caching-overview.html
  Hipótese a medir: o ultralytics compila com `device_name="AUTO"` sem cache a cada subida.

- Números: portal no palco **p50 3,5 s / p95 5,9 s** (meta atingida, depois de
  descartar o quadro pendente das pausadas); fora do palco p50 13,4 / p95 24,2 s
  (`bench/results/portal-adendo3-20261014.json`). Partida até a 1ª análise: frio
  mediana 67,8 s, cache aquecido 53,2 s (`bench/results/partida-adendo3-20261014.json`).
  CHANGELOG, DEMO e BANCA atualizados.

Em andamento: regravação do vídeo do palco (`e2e/video_do_palco.py`).

## Ações negadas pela permissão (não contornadas)

- 14/10: lançar o portão r3 com `nohup bash -c ... &` (comando combinado com
  edição e commit) foi negado. O portão seguiu pelo modo em segundo plano da
  própria ferramenta, como nas rodadas anteriores.

## Decisões em vigor

- Portal: 3 análises seguidas com tudo confirmado; até 2 análises SEM ninguém
  detectado no meio ficam neutras (`PORTAL_AUSENCIAS_TOLERADAS=2`); EPI faltando zera.
- Foco: `INFERENCIA_FRACAO_FOCO=0,5` fora do palco (inalterado pelo ADENDO 3).
- Queda: regra de 2 análises mantida; palco toca a gravação a 0,25× de 4 s em diante.
- SQLite em WAL; custódia em segundo commit, em lote.

## Ameaças conhecidas (para o resumo final)

1. Portal: o peso de EPI vê capacete com ≥ 0,40 só em ~64 % dos quadros mesmo
   de perto; números finais com portal.mp4 a registrar.
2. Subida a frio (antes: ~4 min); números com o cache novo a registrar.
3. Regra dos 3 s sem inferência: 9 % dos intervalos passam de 3 s sob carga (máx. 5,2 s).

## Worktrees

- `../ch5550-antes` (tag `pre-missao-2`): medições "antes" e bench de referência.

## Próximo passo exato

Feito desde o último marco: vídeo regravado e GIF no README; portão r2 verde
(664 unit, 36 E2E); capturas r7/r7b + galeria; cena da Queda também pausa as
outras (E2E isolado 2/2). Corpo do PR6 pronto no scratchpad da sessão (refazer
a partir do CHANGELOG "ADENDO 3" se perdido).

1. Conferir o portão r3 em `bench/runtime/portao-pr6-r3/` (ruff, pytest,
   build, e2e, bench — cada .txt termina com `exit=`). Se tudo 0: abrir o PR6
   `next-2026` → `feat/completo-com-rebrand` e `gh pr merge --squash`.
2. Ensaio da integração com a main em `../ch5550-release-ensaio` (branch local
   `release-main-ensaio`, merge de `origin/main` SEM commit, conflitos abertos
   em: .env.example, .gitignore, README.md, app/config.py,
   app/services/camera_worker.py, app/services/risk_rules.py,
   app/vision/person_compliance_matcher.py, app/vision/yolo_ppe_detector.py,
   app/static/dist/*, docs/SPRINT4.md, frontend/src/styles/global.css).
   Plano: pipeline/infra/UI/docs NEXT = versão nossa; incorporar da main
   `PPE_MISSING_POLICY` (padrão `ausencia`), classes negativas e `evidence` no
   matcher, 2º gatilho do LLM, estado "indisponível" no quiosque, docs/scripts/
   testes da Sprint 4; peso padrão continua Vyra e `visionepi_cppe_n416.pt`
   vira opção documentada no README; adaptar `tests/test_onboarding.py`; dist
   = rebuild. Registrar cada arquivo no CHANGELOG.
3. Depois: clone limpo, Release `next-2026-demo` com
   `bench/runtime/video-palco/palco.mp4`, `release-main` → PR7 → squash na
   main, E2E de fumaça e `run.py --demo` a partir da main.
