# Matriz de permissões (MISSÃO 4, Fase 1, item 3)

Cada endpoint REST registrado no app (`app.url_map`, todas as regras e métodos,
exceto `static`) e cada evento de socket, medido com **sem sessão**, **operador**
(da câmera 1), **operador acessando a câmera 2**, **operador sem setor**,
**técnico** e **supervisor**.

- Teste: `tests/test_matriz_de_permissoes.py` (Flask test client sobre o app real,
  sem pipeline de visão). Rodar: `VISIONEPI_THREADS=2 python -m pytest tests/test_matriz_de_permissoes.py -q`
  (cerca de 9 min nesta máquina; cada célula monta um app novo para que rotas que
  apagam câmera/usuário não contaminem a seguinte).
- Teste-guarda: `test_toda_rota_registrada_esta_na_tabela` **falha** se aparecer
  rota (método + regra) sem linha na tabela de expectativas, e se sobrar linha sem
  rota. `test_todo_evento_de_socket_esta_classificado` faz o mesmo para `socketio.on`.
- Para regerar a medição: `VISIONEPI_MATRIZ_DUMP=<arquivo.jsonl>` grava o status de cada célula.

## Fonte de verdade do esperado

Escrito à mão, **não** copiado do que o código devolve, nesta ordem:

1. README, seção "Autenticação e papéis": papéis hierárquicos (supervisor ⊇ técnico ⊇
   operador); operador restrito à câmera do próprio setor (lista de câmeras, vídeo,
   alertas, evidências, linha do tempo e score de risco só daquela área); operador
   sem setor **não vê nada**; "todas as rotas da API exigem sessão"; WebSocket também
   exige sessão e o escopo vale nele (rooms).
2. `app/utils/auth.py`: sem sessão 401; papel insuficiente 403 (`require_role`);
   câmera fora do setor 404 (`erro_fora_do_escopo`); operador sem setor 403
   (`sem_camera_atribuida`) em rota de câmera, ou lista vazia em listagem.
3. Rotas que o README não lista (evacuação, regras, permissões de trabalho, rótulos,
   escala, laboratório, simulador, privacidade, custódia, metas da TV, apagar
   alertas, missões): o esperado é o declarado na docstring do módulo ou pelo
   coordenador da missão; a coluna "Confere?" diz "README omisso".

## Legenda

| Símbolo | Significado |
|---|---|
| `401` `403` `404` | status exato exigido e medido |
| `200`, `201`, `400`, `409`... | o pedido **passou da autorização e do escopo** e chegou na regra de negócio; o número é o status medido (o corpo do pedido é inválido ou o recurso é de teste de propósito, para não ter efeito colateral real) |
| **200 ≠ 404/403** em negrito | **DIVERGÊNCIA** (bug de segurança): o medido é o primeiro valor, o esperado vem depois |
| "Op. fora" | o mesmo operador (câmera 1) pedindo o recurso da câmera 2. Rota sem recurso por câmera repete o valor do operador |
| "Op. sem setor" | operador sem `camera_id` |

Técnico e supervisor são medidos contra o recurso da câmera 2, justamente a que o
operador não alcança.

## Resumo executivo

- Medido: toda linha da tabela x 6 papéis (inclui variantes com token), 13 listagens x 4 papéis para o conteúdo, e `connect`/`focar`/`revalidate` por papel. Última rodada completa: ver "Rodada de referência" no fim.
- **8 células divergentes de segurança**, todas com `xfail(strict=True)`, em **7 rotas**, **de dois defeitos**:
  1. `GET /snapshots/<arquivo>` não aplica escopo de câmera (2 células).
  2. Seis rotas devolvem o dado do **parque inteiro** ao operador **sem setor**, porque `camera_scope()` devolve `None` para ele (igual ao técnico) e elas não têm a guarda `_operador_sem_setor()`.
- 1 defeito de robustez (não é autorização): `focar` com payload que não é objeto levanta `AttributeError`.
- Nenhum 500 nem exceção não tratada em nenhuma célula REST.

### Divergências

| # | Rota | Papel | Esperado (README) | Medido | Onde |
|---|---|---|---|---|---|
| D1 | `GET /snapshots/<arquivo>` | operador fora do setor | 404 | **200** (entrega a imagem) | `app/api/diagnostics.py::get_snapshot` |
| D2 | `GET /snapshots/<arquivo>` | operador sem setor | 403 | **200** (entrega a imagem) | idem |
| D3 | `GET /api/gemeo` | operador sem setor | nada (200 vazio ou 403) | **200 com as 2 câmeras** (planta, pés, incidentes) | `app/api/gemeo.py` |
| D4 | `GET /api/tv` | operador sem setor | nada | **200 com os 2 setores** | `app/api/tv.py` |
| D5 | `GET /risk-score` | operador sem setor | nada | **200 com 3 de 3 alertas do parque** | `app/api/risk.py::_camera_id` |
| D6 | `GET /risk-score/trend` | operador sem setor | nada | **200 com a tendência do parque** | idem |
| D7 | `GET /api/relatorio/turno` | operador sem setor | nada | **200 com 3 de 3 alertas** | `app/api/relatorio.py::_parametros` |
| D8 | `GET /relatorio/turno` (HTML) | operador sem setor | nada | **200 com os nomes das 2 câmeras** | idem |

Mesma causa raiz de D5 a D8 (inferida da leitura do código, **não medida**: exigiria
LLM ligado): `POST/GET /api/relatorio/turno/resumo` usam o mesmo `_parametros()`, com
chave de cache `horas:None` para o operador sem setor, ou seja, o resumo do parque inteiro.

## Exceções à regra "sem sessão = 401" (cada uma lida no código)

| Rota | Sem sessão | Por que é legítima |
|---|---|---|
| `GET /`, `/dashboard`, `/dashboard/`, `/portal`, `/tv`, `/rotular`, `/desafio`, `/gemeo`, `/simulador`, `/auditoria`, `/palco`, `/palco/controle`, `/retrospectiva`, `/liga`, `/evacuacao`, `/torre`, `/regras`, `/permissoes` | 200 | todas servem o mesmo `index.html` do build React (`status.index`): HTML estático sem dado; os dados vêm de `/api/*`, que dão 401. O controle de tela é do frontend |
| `GET /sw.js`, `GET /manifest.webmanifest` | 200 | arquivos estáticos do PWA, pedidos pelo navegador antes de qualquer login |
| `GET /static/<arquivo>` | 200 | pasta do build; `test_estaticos_so_expoem_o_build_e_a_pagina_do_celular` trava o conteúdo (`cam.html` e `dist/`) e a travessia de diretório |
| `GET /cam` | 200 | página do celular-câmera: HTML estático, o token vai na URL |
| `POST /api/celular/<token>/quadro` | 404 (token desconhecido) | o celular não tem sessão; só aceita quadro de token de câmera existente e em monitoramento, com limite de tamanho e taxa. Token desconhecido nunca vira 401 |
| `POST /api/auth/login` | 400 sem corpo | é o próprio login |
| `POST /api/auth/logout` | 200 | idempotente, não expõe nada |
| `GET /api/auth/me` | 200 com `user: null` | o frontend chama no boot para decidir se mostra o login |
| `GET /api/palco/estado`, `POST /api/palco/ir` com `?t=<token>` | 200 / 400 | o celular de controle do palco não tem login; o token do QR só muda a cena |
| `POST /api/evacuacao/iniciar` e `/encerrar` com `?t=` ou corpo `{"t"}` | 400 / 409 | mesmo token do palco (supervisor **ou** token). O token **não** abre `GET /api/evacuacao*`, `/api/palco/controle`, alertas nem vídeo (testado) |
| `POST /api/demo/reset` | **403** (não 401) | só existe com `DEMO_MODE`; autoriza o `X-Demo-Token` do terminal da demo ou sessão de supervisor; sem nenhum dos dois, 403 por desenho |
| Qualquer rota acima com token **errado** | 403 para todos os papéis | a rota decide pelo token antes da sessão |

`test_demais_rotas_da_api_nao_tem_excecao_alem_das_documentadas` trava a lista: uma
rota nova de `/api` pública falha lá.

## Matriz REST

Colunas: **Sem sessão · Operador · Op. fora · Op. sem setor · Técnico · Supervisor**.

### Autenticação e usuários

| Método | Rota | Sem sessão | Op. | Op. fora | Op. s/ setor | Téc. | Sup. | Confere? |
|---|---|---|---|---|---|---|---|---|
| POST | `/api/auth/login` | 400 | 400 | 400 | 400 | 400 | 400 | Sim (pública: é o login) |
| POST | `/api/auth/logout` | 200 | 200 | 200 | 200 | 200 | 200 | Sim (pública) |
| GET | `/api/auth/me` | 200 | 200 | 200 | 200 | 200 | 200 | Sim (pública, `user:null`) |
| POST | `/api/auth/password` | 401 | 400 | 400 | 400 | 400 | 400 | Sim (qualquer logado; 400 = senha nova fraca) |
| GET | `/api/users` | 401 | 403 | 403 | 403 | 403 | 200 | Sim (gerir usuários: supervisor) |
| POST | `/api/users` | 401 | 403 | 403 | 403 | 403 | 400 | Sim |
| PATCH | `/api/users/<id>` | 401 | 403 | 403 | 403 | 403 | 200 | Sim |
| DELETE | `/api/users/<id>` | 401 | 403 | 403 | 403 | 403 | 200 | Sim |

### Alertas, incidentes, permissões de trabalho

| Método | Rota | Sem sessão | Op. | Op. fora | Op. s/ setor | Téc. | Sup. | Confere? |
|---|---|---|---|---|---|---|---|---|
| GET | `/alerts` | 401 | 200 | 200 | 200 | 200 | 200 | Sim (escopo no conteúdo, ver abaixo) |
| GET | `/alerts/<id>/evidence` | 401 | 200 | 404 | 403 | 200 | 200 | Sim |
| GET | `/api/alerts/<id>/clip` | 401 | 200 | 404 | 403 | 200 | 200 | Sim |
| GET | `/api/alerts/<id>/clip/<n>.jpg` | 401 | 200 | 404 | 403 | 200 | 200 | Sim |
| POST | `/alerts/<id>/false-positive` | 401 | 200 | 404 | 403 | 200 | 200 | Sim (operador pode, só no setor) |
| POST | `/alerts/<id>/acknowledge` | 401 | 200 | 404 | 403 | 200 | 200 | Sim |
| POST | `/alerts/acknowledge-all` | 401 | 200 | 200 | 403 | 200 | 200 | Sim (operador só no setor, testado) |
| POST | `/alerts/resolve-active` | 401 | 403 | 403 | 403 | 200 | 200 | README omisso (técnico+, docstring) |
| DELETE | `/alerts/resolved` | 401 | 403 | 403 | 403 | 403 | 200 | README omisso (só supervisor, docstring) |
| GET | `/api/incidentes` | 401 | 200 | 200 | 200 | 200 | 200 | Sim (escopo no conteúdo) |
| GET | `/api/incidentes/<id>` | 401 | 200 | 404 | 403 | 200 | 200 | Sim |
| POST | `/api/incidentes/<id>/reconhecer` | 401 | 200 | 404 | 403 | 200 | 200 | Sim |
| GET | `/api/incidentes/<id>/linha-causal` | 401 | 200 | 404 | 403 | 200 | 200 | Sim |
| GET | `/snapshots/<arquivo>` | 401 | 200 | **200 ≠ 404** | **200 ≠ 403** | 200 | 200 | **NÃO (D1, D2)** |
| GET | `/events` | 401 | 200 | 200 | 200 | 200 | 200 | Sim (escopo no conteúdo) |
| GET | `/api/permissoes` | 401 | 200 | 200 | 200 | 200 | 200 | Sim (escopo no conteúdo) |
| POST | `/api/permissoes` | 401 | 403 | 403 | 403 | 400 | 400 | Sim (técnico+, 400 = corpo vazio) |
| GET | `/api/permissoes/<id>` | 401 | 200 | 404 | 403 | 200 | 200 | Sim |
| POST | `/api/permissoes/<id>/encerrar` | 401 | 403 | 403 | 403 | 200 | 200 | Sim (técnico+) |
| POST | `/api/permissoes/<id>/cancelar` | 401 | 403 | 403 | 403 | 200 | 200 | Sim (técnico+) |
| GET | `/api/cameras/<id>/zona-controlada` | 401 | 200 | 404 | 403 | 200 | 200 | Sim |
| PUT | `/api/cameras/<id>/zona-controlada` | 401 | 403 | 403 | 403 | 200 | 200 | Sim (técnico+) |

### Câmeras

| Método | Rota | Sem sessão | Op. | Op. fora | Op. s/ setor | Téc. | Sup. | Confere? |
|---|---|---|---|---|---|---|---|---|
| GET | `/api/cameras/discover` | 401 | 403 | 403 | 403 | 200 | 200 | Sim (configurar câmeras: técnico+) |
| GET | `/api/cameras` | 401 | 200 | 200 | 200 | 200 | 200 | Sim (escopo no conteúdo) |
| GET | `/api/cameras/<id>` | 401 | 200 | 404 | 403 | 200 | 200 | Sim |
| POST | `/api/cameras` | 401 | 403 | 403 | 403 | 201 | 201 | Sim |
| PUT, PATCH | `/api/cameras/<id>` | 401 | 403 | 403 | 403 | 200 | 200 | Sim |
| DELETE | `/api/cameras/<id>` | 401 | 403 | 403 | 403 | 200 | 200 | Sim |
| GET | `/api/cameras/<id>/status` | 401 | 200 | 404 | 403 | 200 | 200 | Sim |
| POST | `/api/cameras/<id>/start` | 401 | 200 | 404 | 403 | 200 | 200 | Sim (iniciar/parar: operador, só no setor) |
| POST | `/api/cameras/<id>/stop` | 401 | 200 | 404 | 403 | 200 | 200 | Sim |
| GET | `/api/cameras/<id>/video_feed` | 401 | 200 | 404 | 403 | 200 | 200 | Sim |
| GET | `/api/cameras/<id>/frame.jpg` | 401 | 200 | 404 | 403 | 200 | 200 | Sim |
| GET | `/api/cameras/<id>/analysis` | 401 | 200 | 404 | 403 | 200 | 200 | Sim |
| GET | `/api/cameras/<id>/conformidade-por-id` | 401 | 200 | 404 | 403 | 200 | 200 | Sim |
| GET | `/api/cameras/<id>/conformidade-por-id/<pessoa>` | 401 | 404* | 404 | 403 | 404* | 404* | Sim (*404 de negócio, "ID de rastreio não visto"; o 404 de escopo tem outro texto e é distinguido) |
| GET | `/api/cameras/<id>/planta` | 401 | 200 | 404 | 403 | 200 | 200 | Sim |
| PUT | `/api/cameras/<id>/planta` | 401 | 403 | 403 | 403 | 200 | 200 | Sim |
| GET | `/api/cameras/<id>/mapa-de-calor` | 401 | 200 | 404 | 403 | 200 | 200 | Sim |
| GET | `/api/cameras/<id>/saude-visual` | 401 | 200 | 404 | 403 | 200 | 200 | Sim (coordenador: logado com escopo) |
| POST | `/api/cameras/<id>/saude-visual/referencia` | 401 | 403 | 403 | 403 | 409* | 409* | Sim (técnico+; *câmera sem quadro para virar referência) |
| PATCH | `/api/cameras/<id>/privacidade` | 401 | 403 | 403 | 403 | 403 | 200 | README omisso (só supervisor, docstring) |
| GET | `/api/cameras/<id>/gate` | 401 | 200 | 404 | 403 | 200 | 200 | Sim |
| GET | `/api/cameras/<id>/portal` | 401 | 200 | 404 | 403 | 200 | 200 | Sim |
| PUT | `/api/cameras/<id>/gate` | 401 | 403 | 403 | 403 | 200 | 200 | Sim |
| GET | `/api/cameras/<id>/risk-area` | 401 | 200 | 404 | 403 | 200 | 200 | Sim |
| PUT, PATCH | `/api/cameras/<id>/risk-area` | 401 | 403 | 403 | 403 | 200 | 200 | Sim (área de risco: técnico+) |
| GET | `/api/cameras/<id>/celular` | 401 | 403 | 403 | 403 | 409 | 409 | README omisso (técnico+, docstring; 409 = câmera não é do tipo Celular) |
| GET | `/features?camera_id=<id>` | 401 | 200 | 404 | 403 | 200 | 200 | Sim |
| GET | `/features` (sem câmera) | 401 | 200 | 200 | 200 | 200 | 200 | **Ambíguo (A1)** |
| PUT, PATCH | `/features` | 401 | 403 | 403 | 403 | 200 | 200 | Sim |
| GET | `/api/custodia/verificar?incidente_id=<id>` | 401 | 200 | 404 | 403 | 200 | 200 | Sim |
| GET | `/api/custodia/verificar` (cadeia inteira) | 401 | 403 | 403 | 403 | 200 | 200 | README omisso (técnico+, docstring) |
| GET | `/api/custodia` | 401 | 403 | 403 | 403 | 200 | 200 | README omisso (técnico+) |

### Rotas legadas ("câmera padrão": o operador cai no setor dele)

| Método | Rota | Sem sessão | Op. | Op. fora | Op. s/ setor | Téc. | Sup. | Confere? |
|---|---|---|---|---|---|---|---|---|
| GET | `/status` | 401 | 200 | 200 | 403 | 200 | 200 | Sim |
| GET | `/preflight` | 401 | 200 | 200 | 403 | 200 | 200 | Sim |
| GET | `/model` | 401 | 200 | 200 | 403 | 200 | 200 | Sim |
| GET | `/video_feed` | 401 | 200 | 200 | 403 | 200 | 200 | Sim |
| GET | `/analysis/latest` | 401 | 200 | 200 | 403 | 200 | 200 | Sim |
| POST | `/start` | 401 | 200 | 200 | 403 | 200 | 200 | Sim (`?todas=1` do operador fica no setor, testado) |
| POST | `/stop` | 401 | 200 | 200 | 403 | 200 | 200 | Sim (idem) |
| GET | `/settings` | 401 | 200 | 200 | 403 | 200 | 200 | Sim |
| PATCH | `/settings` | 401 | 403 | 403 | 403 | 200 | 200 | Sim (configurações: técnico+) |
| GET | `/overlay` | 401 | 200 | 200 | 403 | 200 | 200 | Sim |
| PATCH | `/overlay` | 401 | 403 | 403 | 403 | 200 | 200 | Sim |
| GET | `/risk-area` | 401 | 200 | 200 | 403 | 200 | 200 | Sim |
| PATCH | `/risk-area` | 401 | 403 | 403 | 403 | 200 | 200 | Sim |
| GET | `/api/diagnostics/pipeline` | 401 | 200 | 200 | 200 | 200 | 200 | Sim (escopo no conteúdo) |
| GET | `/api/integracao/estado` | 401 | 200 | 200 | 403 | 200 | 200 | Sim (escopo no conteúdo) |

### Agregados, relatórios e painéis

| Método | Rota | Sem sessão | Op. | Op. fora | Op. s/ setor | Téc. | Sup. | Confere? |
|---|---|---|---|---|---|---|---|---|
| GET | `/api/gemeo` | 401 | 200 | 200 | **200 ≠ vazio** | 200 | 200 | **NÃO (D3)** |
| GET | `/api/tv` | 401 | 200 | 200 | **200 ≠ vazio** | 200 | 200 | **NÃO (D4)** |
| GET | `/risk-score` | 401 | 200 | 200 | **200 ≠ vazio** | 200 | 200 | **NÃO (D5)** |
| GET | `/risk-score/trend` | 401 | 200 | 200 | **200 ≠ vazio** | 200 | 200 | **NÃO (D6)** |
| GET | `/api/relatorio/turno` | 401 | 200 | 200 | **200 ≠ vazio** | 200 | 200 | **NÃO (D7)** |
| GET | `/relatorio/turno` | 401 | 200 | 200 | **200 ≠ vazio** | 200 | 200 | **NÃO (D8)** |
| POST | `/api/relatorio/turno/resumo` | 401 | 200 | 200 | 200 | 200 | 200 | Sim no status; ver nota sobre D5-D8 |
| GET | `/api/relatorio/turno/resumo` | 401 | 200 | 200 | 200 | 200 | 200 | idem |
| GET | `/api/liga` | 401 | 200 | 200 | 200 | 200 | 200 | **Ambíguo (A2)** |
| GET | `/api/retrospectiva` | 401 | 200 | 200 | 200 | 200 | 200 | **Ambíguo (A2)** |
| GET | `/api/tv/metas` | 401 | 200 | 200 | 200 | 200 | 200 | **Ambíguo (A3)** |
| GET | `/api/palco/roteiro` | 401 | 200 | 200 | 200 | 200 | 200 | **Ambíguo (A3)** |
| GET | `/api/desafio/rodadas` | 401 | 404* | 404* | 404* | 404* | 404* | README omisso (qualquer logado; *404 = gravações de demonstração ausentes, controlado no teste) |
| GET | `/api/desafio/<id>/quadro/<k>.jpg` | 401 | 404* | 404* | 404* | 404* | 404* | idem |
| POST | `/api/desafio/<id>/resposta` | 401 | 404* | 404* | 404* | 404* | 404* | idem |

### Gestão: supervisor, técnico, integração

| Método | Rota | Sem sessão | Op. | Op. fora | Op. s/ setor | Téc. | Sup. | Confere? |
|---|---|---|---|---|---|---|---|---|
| PUT | `/api/tv/metas/<setor>` | 401 | 403 | 403 | 403 | 403 | 200 | README omisso (só supervisor, docstring) |
| POST | `/api/liga/missoes` | 401 | 403 | 403 | 403 | 403 | 201 | README omisso (só supervisor) |
| DELETE | `/api/liga/missoes/<id>` | 401 | 403 | 403 | 403 | 403 | 200 | idem |
| GET | `/api/escala` | 401 | 403 | 403 | 403 | 200 | 200 | README omisso (técnico+) |
| POST | `/api/escala` | 401 | 403 | 403 | 403 | 409* | 409* | idem (*fixture ausente, controlado) |
| DELETE | `/api/escala` | 401 | 403 | 403 | 403 | 200 | 200 | idem |
| GET | `/api/lab/pergunte` | 401 | 403 | 403 | 403 | 409* | 409* | README omisso (técnico+; *laboratório desligado, controlado) |
| POST | `/api/lab/pergunte` | 401 | 403 | 403 | 403 | 409* | 409* | idem |
| GET | `/api/rotulos/proximo` | 401 | 403 | 403 | 403 | 200 | 200 | README omisso (técnico+, docstring) |
| GET | `/api/rotulos/<id>.jpg` | 401 | 403 | 403 | 403 | 404* | 404* | idem (*recorte inexistente) |
| POST | `/api/rotulos/<id>` | 401 | 403 | 403 | 403 | 404* | 404* | idem |
| GET | `/api/rotulos/dataset.zip` | 401 | 403 | 403 | 403 | 200 | 200 | idem |
| GET | `/api/simulador/contexto` | 401 | 403 | 403 | 403 | 200 | 200 | README omisso (técnico+, docstring) |
| POST | `/api/simulador` | 401 | 403 | 403 | 403 | 200 | 200 | idem |
| GET | `/api/regras` | 401 | 403 | 403 | 403 | 200 | 200 | Sim (coordenador: técnico+) |
| POST | `/api/regras` | 401 | 403 | 403 | 403 | 400 | 400 | idem |
| PUT, DELETE | `/api/regras/<id>` | 401 | 403 | 403 | 403 | 404* | 404* | idem (*regra inexistente) |
| POST | `/api/regras/<id>/ativar`, `/desativar` | 401 | 403 | 403 | 403 | 404* | 404* | idem |
| POST | `/api/regras/testar` | 401 | 403 | 403 | 403 | 400 | 400 | idem |

### Palco, evacuação, demo, celular

| Método | Rota | Sem sessão | Op. | Op. fora | Op. s/ setor | Téc. | Sup. | Confere? |
|---|---|---|---|---|---|---|---|---|
| GET | `/api/palco/estado` | 401 | 403 | 403 | 403 | 200 | 200 | Sim (técnico+ **ou** token) |
| GET | `/api/palco/estado?t=<token>` | 200 | 200 | 200 | 200 | 200 | 200 | Sim (token do QR) |
| GET | `/api/palco/estado?t=<errado>` | 403 | 403 | 403 | 403 | 403 | 403 | Sim |
| POST | `/api/palco/ir` | 401 | 403 | 403 | 403 | 400 | 400 | Sim |
| POST | `/api/palco/ir?t=<token>` | 400 | 400 | 400 | 400 | 400 | 400 | Sim (corpo inválido de propósito: 400 = passou da autorização) |
| POST | `/api/palco/ir?t=<errado>` | 403 | 403 | 403 | 403 | 403 | 403 | Sim |
| GET | `/api/palco/controle` | 401 | 403 | 403 | 403 | 200 | 200 | Sim (técnico+; o token não abre) |
| POST | `/api/evacuacao/iniciar` | 401 | 403 | 403 | 403 | 403 | 400 | Sim (supervisor **ou** token; 400 = corpo inválido de propósito) |
| POST | `/api/evacuacao/iniciar` (`?t=` ou corpo `t`) | 400 | 400 | 400 | 400 | 400 | 400 | Sim |
| POST | `/api/evacuacao/iniciar?t=<errado>` | 403 | 403 | 403 | 403 | 403 | 403 | Sim |
| POST | `/api/evacuacao/encerrar` | 401 | 403 | 403 | 403 | 403 | 409 | Sim (409 = não há evacuação ativa) |
| POST | `/api/evacuacao/encerrar` (`?t=` ou corpo `t`) | 409 | 409 | 409 | 409 | 409 | 409 | Sim |
| POST | `/api/evacuacao/encerrar?t=<errado>` | 403 | 403 | 403 | 403 | 403 | 403 | Sim |
| GET | `/api/evacuacao` | 401 | 403 | 403 | 403 | 200 | 200 | Sim (técnico+) |
| GET | `/api/evacuacao/relatorios` | 401 | 403 | 403 | 403 | 200 | 200 | Sim |
| GET | `/api/evacuacao/relatorios/<n>` | 401 | 403 | 403 | 403 | 404* | 404* | Sim (*relatório inexistente) |
| POST | `/api/demo/reset` | **403** | 403 | 403 | 403 | 403 | 200 | Sim (supervisor ou `X-Demo-Token`; o reset real é substituído no teste porque apaga `instance/demo`) |
| POST | `/api/celular/<token>/quadro` | 404 | 404 | 404 | 404 | 404 | 404 | Sim (token desconhecido) |

Rotas públicas de shell, `sw.js`, manifesto e `/cam`: 200 para todos (ver "Exceções").

## Conteúdo: o escopo vale nos dados (não só no status)

Status 200 não prova escopo. `test_o_conteudo_respeita_o_escopo_de_camera` semeia a
câmera 1 com 1 alerta e a câmera 2 com 2 alertas (números diferentes, para uma soma
vazada não parecer a câmera certa) e compara o **conteúdo**:

| Listagem | Operador (câm. 1) | Op. sem setor | Técnico/Supervisor | Resultado |
|---|---|---|---|---|
| `/api/cameras` | só a 1 | vazio | as 2 | ok |
| `/alerts` | só a 1 (`?camera_id=2` não amplia) | vazio | as 2 | ok |
| `/events` | só a 1 | vazio | as 2 | ok |
| `/api/incidentes` | só a 1 | vazio | as 2 | ok |
| `/api/permissoes` | só a 1 | vazio | as 2 | ok |
| `/api/diagnostics/pipeline` | no máximo a 1 | vazio | no máximo as 2 | ok |
| `/api/integracao/estado` | no máximo a 1 | 403 | no máximo as 2 | ok |
| `/api/gemeo` | só a 1 | **as 2** | as 2 | **D3** |
| `/api/tv` | só o setor 1 | **os 2** | os 2 | **D4** |
| `/risk-score` | 1 alerta | **3 alertas** | 3 | **D5** |
| `/risk-score/trend` | tem dado | **tem dado** | tem dado | **D6** |
| `/api/relatorio/turno` | 1 alerta (`?camera_id=2` não amplia) | **3** | 3 | **D7** |
| `/relatorio/turno` (HTML) | só "Portaria" | **os 2 nomes** | os 2 | **D8** |

Também testados e verdes: operador não marca falso positivo nem reconhece incidente
de outro setor (e o alerta/incidente fica intacto); `POST /alerts/acknowledge-all` do
operador só marca o setor dele; `POST /start?todas=1` e `/stop?todas=1` do operador
não ligam nem param a câmera dos outros; sessão desativada cai em 401 na chamada seguinte.

## Matriz de socket

| Evento | Sem sessão | Operador (câm. 1) | Op. fora (câm. 2) | Op. sem setor | Técnico | Supervisor | Confere? |
|---|---|---|---|---|---|---|---|
| `connect` | recusado | conecta; recebe só `camera:1` | não recebe a câmera 2 | conecta; não recebe nada | conecta; sala `parque` (recebe tudo) | idem técnico | Sim |
| `focar` câmera do setor | n/a (recusado no connect) | `{ok: true}` e recebe a telemetria | `{ok: false}`, sem telemetria | `{ok: false}` | `{ok: true}` (qualquer câmera) | idem | Sim |
| `focar` payload inválido (`None`, `{}`, câmera nula/texto/lista) | n/a | `{ok: false}` | | `{ok: false}` | `{ok: false}` | `{ok: false}` | Sim |
| `focar` payload que não é objeto (`"texto"`) | n/a | **AttributeError** | | **AttributeError** | **AttributeError** | **AttributeError** | **BUG-ROBUSTEZ** (não é de autorização) |
| `focar` depois de desativado | n/a | | | | `{ok: false}` | | Sim |
| `revalidate` sessão válida | n/a | mantém | | mantém | mantém | mantém | Sim |
| `revalidate` sessão revogada (desativada ou senha trocada) | n/a | desconecta | | desconecta | desconecta | desconecta | Sim |

Também: cookie forjado e usuário desativado são recusados no `connect`.

Eventos **emitidos** pelo servidor (`saude_visual`, `analysis`, `active_alerts`, `timeline_event`...)
não são handlers `socketio.on`, então o guard de socket não os enxerga: o escopo deles vem de
`emitir_para_camera`/`emitir_para_foco` (`app/utils/salas.py`), exercitado aqui pela sonda do `connect` e
em profundidade por `tests/test_escopo_socket.py`. Um `socketio.emit` novo sem `to=`/sala continuaria
passando em qualquer guard automático; só revisão de código pega.

## Pontos ambíguos (decisão do dono do produto)

O README não diz, e o código deixa passar. A matriz fixa o comportamento **atual**
como esperado (200) e marca aqui para decisão; se a resposta for "operador só do
setor", viram divergência e a linha da tabela muda.

- **A1** `GET /features` sem `camera_id`: devolve as chaves globais de detectores a qualquer logado, inclusive operador sem setor. É configuração, não dado de um setor.
- **A2** `GET /api/liga` e `GET /api/retrospectiva`: ranking e tempos por setor de **todos** os setores, para qualquer logado. É gamificação entre setores por desenho, mas o operador vê nomes e pontos de setores que não são o dele (e o operador sem setor também).
- **A3** `GET /api/tv/metas` (metas de todos os setores) e `GET /api/palco/roteiro` (ids e nomes das cenas/câmeras): qualquer logado. `GET /api/tv`, ao contrário, é escopado por setor, o que sugere que o operador não devia ver metas de outros.

## Defeito de desenho observado (causa das divergências D3 a D8)

`camera_scope()` devolve `None` tanto para "vê o parque inteiro" (técnico, supervisor) quanto
para "ainda não tem setor, não vê nada" (operador sem `camera_id`), e cada rota precisa lembrar
de chamar `_operador_sem_setor()` à parte. Seis rotas esqueceram. O ponto de costura que falta é
um único resultado que distinga os dois casos (por exemplo um tipo/sentinela "sem acesso" que as
listagens sejam obrigadas a tratar), em vez de `None` ambíguo.

## Rodada de referência

`VISIONEPI_THREADS=2 python -m pytest tests/test_matriz_de_permissoes.py -q` — resultado e
tempo no relatório da sessão. As 12 células `xfail` são: D1 a D8 (BUG-SEG) e 4 de `focar` com
payload que não é objeto (BUG-ROBUSTEZ). Ao corrigir qualquer uma, o XPASS estrito derruba o
teste e obriga a apagar a entrada em `DIVERGENCIAS` / `DIVERGENCIAS_DE_CONTEUDO`.

## Correções e decisões da MISSÃO 4 (17/10/2026)

**Corrigido (eram divergências de segurança da matriz acima):**

- D1/D2 — `GET /snapshots/<arquivo>` agora localiza o alerta dono da imagem (`frame_ref`) e aplica o mesmo
  escopo de `/alerts/<id>/evidence`: fora do setor 404, sem setor 403; arquivo sem alerta não é servido.
- D3–D8 — `/api/gemeo`, `/api/tv`, `/risk-score`, `/risk-score/trend`, `/api/relatorio/turno`,
  `/relatorio/turno` e `/api/relatorio/turno/resumo` (GET e POST) passam pelo decorator único
  `exige_setor` (`app/utils/auth.py`): operador sem setor recebe 403. A matriz usa o perfil `PARQUE`.
- `focar` com payload que não é objeto responde `{"ok": false}` em vez de estourar `AttributeError`.

**Decisões de contrato (o README não decidia; opção registrada):**

- A1 `GET /features`: continua visível a qualquer logado — é a configuração dos detectores, não dado de setor.
- A2 `GET /api/liga` e `/api/retrospectiva`: continuam mostrando todos os setores — a Liga é gamificação ENTRE
  setores por desenho, só com indicadores positivos e nada por pessoa.
- A3 `GET /api/tv/metas` e `/api/palco/roteiro`: continuam visíveis — metas são alvos definidos pelo
  supervisor e o roteiro é o da apresentação; nenhum dos dois carrega imagem, pessoa ou alerta de outro setor.
