# Definition of Done praticado

Este é o DoD que o projeto **de fato pratica**, inferido de três fontes: o padrão de commits "teste VERMELHO, depois fix VERDE" em
`docs/specs/gitlog-main.txt`, as regras de verdade e o portão das missões do NEXT 2026 (`docs/NEXT2026/MISSAO.md`, `MISSAO-7.md`,
`ESTADO.md`, `CHANGELOG.md`) e `docs/NEXT2026/QA.md`. **Não foi um documento aprovado pelo grupo antes das sprints**: é a prática descrita depois,
para ser usada como checklist nos cards do Trello (seção final).

## 1. Para qualquer mudança de comportamento

1. **Teste que reproduz primeiro.** Bug ou regra nova começa por um teste que falha pelo motivo certo, commitado como VERMELHO, e o commit seguinte o
   deixa VERDE. Exemplos no git: `e51d952` e `73edc00` (instalação), `e790469` e `ec41617` (escopo de câmera no WebSocket), `0769c97` e `a42d2e5`
   (detector de pessoa), `b834d7d` e `f379910` (histerese), `558d423` e `0a42644` (estado "não verificado").
2. **Nada está "feito" sem evidência executada.** "O compilador aceitou" não é "a funcionalidade existe". Afirmação de desempenho ou
   funcionamento leva o comando e o número ou a saída (`docs/NEXT2026/MISSAO.md`, regras de verdade).
3. **Não desligar teste nem afrouxar assert.** Quando o teste estava errado, ele é corrigido para ficar mais forte e a mudança é registrada
   (exemplos no CHANGELOG: `test_toda_rota_exige_sessao`, `test_arquivo_local_nao_recebe_timeout`).
4. **Limitação de plataforma ou biblioteca só se afirma depois de ler a documentação oficial** e citar a URL (CHANGELOG, "Fontes verificadas").
5. **Comparação de desempenho** usa medições intercaladas e repetidas; reprova só se a mediana do novo for mais de 10 % pior e as 3 repetições
   concordarem (`scripts/resumo_cpu.py`). Número colhido com a máquina disputada é rotulado "sob saturação, indicativo".

## 2. Portão de qualidade antes do merge

Cada item abaixo foi rodado em todo PR de missão do NEXT 2026 (`CHANGELOG.md`, "Portão"):

| Item | Comando |
|---|---|
| Testes unitários e de integração | `pytest` (22/10/2026, MISSÃO 7: 3.288 aprovados) |
| Lint do backend | `ruff check .` |
| Build e checagem de tipos do frontend | `npm --prefix frontend run build` (`tsc -b` e Vite); não há ESLint |
| E2E com servidor real | `python -m pytest e2e -q` (22/10/2026: 76 aprovados, 1 falha sensível a carga, 2 ignorados) |
| Crawler botão a botão | `e2e/test_todos_os_botoes.py` (rodada de 20/10: 78 rotas por papel e tema, 820 elementos, 0 sem efeito; resultado em `docs/NEXT2026/QA.md`) |
| Acessibilidade | `e2e/test_acessibilidade.py` (axe-core, zero violação séria ou crítica, nos dois temas) |
| Fumaça a partir do clone limpo ou da `main` | `python e2e/fumaca_demo.py --raiz .` (6 verificações) |

Falha que aparece só sob carga é **classificada com evidência** (reproduzida isolada, log, carga de terceiros medida) e registrada; não é
silenciada nem o teste é enfraquecido (CHANGELOG, "Portão do PR9" e "Portão da MISSÃO 7").

## 3. Segurança e dados

- Toda rota ou evento de socket novo entra na matriz de permissões; o teste-guarda `tests/test_matriz_de_permissoes.py` **falha** para rota sem
  classificação. Operador só vê a câmera do setor.
- Nenhuma chave, senha, `.env`, peso `.pt` (exceto o peso versionado da Sprint 4), vídeo ou dado pessoal é commitado. Há testes que varrem o
  repositório por chave do Google (`tests/test_onboarding.py`).
- Credencial de câmera nunca sai do processo: redigida em toda saída (`tests/test_credencial_rtsp.py`).
- Dados de demonstração são marcados como simulados; ID de rastreio não é identidade (ADR 0005).
- Nenhum workflow de CI é criado ou alterado (sem GitHub Actions).

## 4. Interface

- Tema claro e escuro; cor só para estado; contraste AA (`scripts/check_contrast.py`).
- Toda tela tem os quatro estados: carregando, vazio, erro com "tentar de novo" e pronto. `e2e/test_estados.py` procura "em construção", TODO,
  lorem, placeholder e travessão em todas as rotas.
- Textos em pt-BR, um termo por conceito (`docs/NEXT2026/GLOSSARIO.md`); `tests/test_copy_do_frontend.py` trava "Falha ao" no frontend.
- Revisão visual por captura de tela, nos dois temas e em 3 tamanhos, com rubrica (`docs/NEXT2026/galeria/index.md`).

## 5. Documentação e revisão

- O CHANGELOG registra, para cada mudança: **o que mudou, por quê, evidência (comando e número) e o que foi rejeitado**.
- Decisão com consequência duradoura vira ADR (`docs/adr/`).
- O relatório diz o que **não** foi medido ou não funcionou ("achado honesto"): PCK não medido, Telegram não implementado, LLM não medido no conjunto anotado.
- Revisões por papel quando há tela ou norma: auditor, fontes (norma, licença, limitação de plataforma), UX e CX (CHANGELOG, MISSÃO 7).
- O estado da sessão fica em arquivo (`docs/NEXT2026/ESTADO.md`, `docs/specs/ESTADO-es-sprint4.md`) para a próxima sessão retomar.

## 6. Integração

- Um PR consolidado por missão, mergeado por `gh pr merge --squash --delete-branch`, só com o portão verde. Falhou e não corrige: reverter o
  commit culpado dentro da branch antes do merge, nunca mesclar com a regressão vermelha.
- Mudança aditiva no fluxo câmera, YOLO e alerta; regressão desse fluxo rodada antes do merge.
- Tag de marco depois do merge (`pre-missao-7`, `missao-4-pr10`, `final-next-2026`) e fumaça a partir da `main`.
- Rollback: tag anterior ou `git revert` do squash; nunca force push.
- Esta entrega: `[skip ci]` em toda mensagem de commit e no título do squash (`docs/specs/es-sprint4.md`, G.3).

## Checklist para os cards do Trello

Copiar em cada card de requisito:

- [ ] Teste que falha antes (VERMELHO) e passa depois (VERDE), ou teste novo que cobre o requisito
- [ ] `pytest` verde no que o card toca; `ruff check .` limpo
- [ ] `npm --prefix frontend run build` ok, se o card mexe no frontend
- [ ] E2E do fluxo verde (Playwright com servidor real), se o card tem tela
- [ ] Rota ou evento novo classificado na matriz de permissões
- [ ] Texto da tela em pt-BR conforme o glossário; tema claro e escuro conferidos
- [ ] Sem segredo, peso, vídeo ou dado pessoal no commit
- [ ] Evidência registrada (comando e número) no CHANGELOG, no ESTADO ou na ata
- [ ] Limitação declarada onde houver ("não medido", "não testado em ...")
