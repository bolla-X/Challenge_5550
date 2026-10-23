# Sprint 3: notificação inteligente e multicâmera (23/06 a 24/08/2026)

> **Reconstruído a partir dos documentos de fase e a partir do histórico do git.** O escopo vem de
> `docs/challenge/FASE3-NOTIFICACAO-INTELIGENTE.md` (entrega de 24/08/2026) e de `docs/challenge/CONSOLIDADO.md`; o PDF da fase está em
> `docs/pitch/FASE3-NOTIFICACAO-INTELIGENTE.pdf`. Os commits da `main` dentro desta sprint vão de **19/07 a 24/08** (`docs/specs/gitlog-main.txt`);
> não há commits entre 23/06 e 18/07. Não houve reunião, review ou retro registrados.

## Objetivo da sprint

Notificação inteligente com pelo menos dois canais distintos (um perceptível pelo operador no campo), política de severidade explícita, dashboard
mínimo para gestão e latência ponta a ponta reportada e demonstrada (FASE3 §1).

## Sprint backlog

| Item | RF | Estado | Fonte |
|---|---|---|---|
| Política de severidade explícita (`critical`, `high`, `medium`) | RF07 | Entregue | FASE3 §2.1 |
| Alertas com ciclo de vida e histerese; "resolver todos" com soneca de 60 s | RF08 | Entregue | FASE3 §4 |
| Canal visual: alertas agrupados por pessoa, filtros, ações em lote, evidência | RF09 | Entregue | FASE3 §2.2 |
| Canal sonoro: apita quando a portaria libera ou nega, sintetizado por código | RF09 | Entregue | FASE3 §2.2 |
| Modo portaria: só libera com todos os EPIs; na dúvida, nega (nega em 3 quadros, libera em 8) | RF10 | Entregue | FASE3 §2.4 |
| Dashboard por perfil: operador, técnico, supervisor | RF13 | Entregue | FASE3 §2.3 |
| Autenticação com papéis, REST e WebSocket; operador restrito à câmera do setor | RF11 | Entregue | commits 24/08 |
| Multicâmera: interface, backend e escopo | RF12 | Entregue | commits 23 e 24/08 |
| Reconexão automática da fonte com backoff | RF14 | Entregue | commit `c24c011` |
| Latência E2E medida e reportada | n/a | Entregue (com gap declarado) | FASE3 §3 |
| Terceiro canal, Telegram | RF48 | **Não entregue `[~]`**: planejado, não implementado | FASE3 §2.2 e §5 |

## Incremento entregue

- Os dois canais, a política de severidade, três perfis de acesso e o modo portaria (FASE3).
- Interface multicâmera (grade, quiosque do operador, foco por câmera) e backend multicâmera (vídeo por câmera, resolução e FPS configuráveis, detecção
  de dispositivos) em 23/08.
- Vyra de 14 classes e detecção de óculos (24/08), revisão de qualidade em 10 itens, pose por pessoa com geometria em pixels, reconexão com backoff,
  autenticação real com papéis e escopo de câmera para o operador, captura destravada com duas webcams (24/08).

### Latência E2E (FASE3 §3)

Do início da captura (violação presente desde o primeiro quadro) até o alerta gravado no banco, 5 execuções:

| Execução | Latência | Alerta |
|---|---|---|
| 1ª (partida fria) | 5,97 s | crítico |
| 2ª | 1,22 s | alto |
| 3ª | 1,37 s | crítico |
| 4ª | 1,12 s | alto |
| 5ª | 1,18 s | alto |

Por severidade: **crítico 1,37 s contra meta de 1 s, 37 % acima da meta** (uma só amostra aquecida); **alto, média de 1,17 s contra meta de 5 s, dentro**.

## Commits da sprint (reconstruído a partir do histórico do git)

Autor é o *handle* gravado no git; nenhum foi mapeado para integrante.

| Data | Commit | Handle | O que |
|---|---|---|---|
| 19/07 | `e1e483a` | bolla-X | "Adicionar projeto VisionEPI V5" (protótipo, primeiro commit da `main`) |
| 05/08 | `292695a` | lukiin-z | Initial commit: frontend React + TS + Vite |
| 05/08 | `d771ca7` | lukiin-z | Merge: resolve conflitos mantendo a versão migrada para React |
| 05/08 | `d224bd0` | lukiin-z | Remove artefatos de runtime e pesos do controle de versão |
| 05/08 | `e1e144f` | lukiin-z | Redesign completo: direção "Autoridade Discreta" |
| 06/08 | `07d5ed8` | lukiin-z | Motion, som e UX: chimes, sparkline, command palette, skeletons, acessibilidade |
| 06/08 | `655c10e` | lukiin-z | Perfis: Supervisor, mute por perfil |
| 06/08 | `8f10da5` | lukiin-z | Layout e scroll, polimento visual, motion e perfis (Operador, Técnico, Supervisor) |
| 23/08 | `bd6e016` | bolla-X | Interface multicâmera: grade, quiosque do operador, foco por câmera (dados de câmera ainda simulados) |
| 23/08 | `3469904` | laszo | Merge do PR #1 (interface multicâmera) |
| 23/08 | `aa852cc` | Lucas Zolla Assis | Backend e frontend: bug de vídeo por câmera, resolução e FPS configuráveis, detecção de dispositivos |
| 23/08 | `d9b2207` | laszo | Merge do PR #2 (backend multicâmera) |
| 24/08 | `e4cd04c` | lucas-baraldi | Modelo Vyra (14 classes) e detecção de óculos de proteção |
| 24/08 | `c3b5ffa` | lucas-baraldi | Revisão de qualidade em 10 itens: bugs, segurança, performance e testes |
| 24/08 | `f7b29c0` | lucas-baraldi | Uma pose por pessoa e geometria de queda em pixels |
| 24/08 | `c24c011` | lucas-baraldi | Reconexão automática com backoff na captura |
| 24/08 | `6bfeb41` | lucas-baraldi | Autenticação real com papéis, cobrindo REST e WebSocket |
| 24/08 | `4a0e039` | lucas-baraldi | Achados da auditoria: chave pública, revogação de sessão, vazamento entre contas |
| 24/08 | `204206f` | lucas-baraldi | Operador restrito à câmera do setor |
| 24/08 | `2d74e96` | lucas-baraldi | Destrava o vídeo e habilita multicâmera com duas webcams |

Os demais commits da janela (merges dos PRs #3 a #8, correções de `.gitignore`, `.env.example` e fim de linha) estão em `docs/specs/gitlog-main.txt`.

## Review (reconstruída)

**Entregue, segundo o relatório de fase:** 5 dos 6 itens `[x]` (FASE3 §5). **Não entregue:** o terceiro canal, Telegram (`[~]`).

**Limitações declaradas:**
- Latência do alerta crítico **37 % acima da meta**; "gap real, declarado sem suavizar".
- Telegram "planejado, não implementado": depende de um bot criado fora do sistema e "não entrou a tempo", para não arriscar instabilidade às vésperas da
  apresentação.

## Retrospectiva (reconstruída)

Não houve retro registrada. O que os documentos e o histórico mostram:

- **Funcionou:** autenticação auditada logo depois de entregue (`4a0e039` corrige chave pública, revogação de sessão e vazamento entre contas
  achados na auditoria); portaria assimétrica por decisão deliberada de engenharia (liberar por engano é o erro mais caro).
- **Atrito de integração, do git:** `e3049f2`, `2cfdb68`, `8626484` e `79fe127` (23/08) limpam `.gitignore` corrompido, `.DS_Store`, `.env.save` e
  reaplicam "correções perdidas"; `35c0c67` e `29e0ffc` (24/08) removem CR soltos e uma linha duplicada que o merge do PR #4 introduziu (o `35c0c67` também
  adiciona o `.gitattributes`). É leitura dos títulos dos commits, não de uma retro.
- **Decisão sobre risco:** o Telegram ficou de fora de propósito; o valor de 3 quadros para criar alerta foi mantido por ser o já validado em uso,
  "para não introduzir mudança de comportamento na véspera da apresentação" (`CONSOLIDADO.md` §10, item 6).
- **Próximo passo declarado:** implementar o canal Telegram; reduzir a troca de ID do rastreador em quedas.

## Evidências no repositório

`docs/challenge/FASE3-NOTIFICACAO-INTELIGENTE.md`, `docs/pitch/FASE3-NOTIFICACAO-INTELIGENTE.pdf`, `docs/specs/gitlog-main.txt`; testes: `tests/test_auth.py`,
`tests/test_escopo_camera.py`, `tests/test_modo_portaria.py`, `tests/test_alert_state.py`.
