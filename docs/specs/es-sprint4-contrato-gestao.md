# Contrato — módulo "Gestão de EPIs" (critérios F1.4, F1.5, F1.6)

Fonte única para o backend (`app/`) e o frontend (`frontend/`). Mudou aqui, mudou nos dois.

## Princípios

- Módulo **separado da visão**. Nenhuma coluna liga colaborador a ID de rastreio, câmera ou imagem. O texto da tela
  diz isso ("Cadastro administrativo: não é ligado às câmeras").
- Sem CPF, sem foto, sem dado sensível: matrícula, nome, setor, função, admissão.
- Dados do seed são **simulados**: nomes fictícios, fabricantes "fictícios", CAs na faixa `9xxxxx` com
  `ficticio=true`. A tela mostra o selo "Dados simulados" quando há registro do seed.
- Papéis: **Técnico ou mais** lê tudo, registra entrega, devolução e ocorrência, e exporta. **Supervisor** cadastra
  e edita colaborador e item do catálogo. **Operador** recebe 403 em todas as rotas `/api/gestao/*` (o kiosk não
  precisa disto). Sem sessão: 401.
- Datas em ISO 8601 (`YYYY-MM-DD` para datas de calendário, `...T...+00:00` para instantes).
- Erros: `{"error": "<mensagem em pt-BR>", "code": "<codigo>"}` com 400/404/409.

## Modelos (tabelas novas, migração Alembic nova a partir do head atual)

| Tabela | Campos |
|---|---|
| `colaboradores` | id, matricula (único), nome, setor, funcao, admissao (date), ativo (bool), ficticio (bool), criado_em |
| `epis_catalogo` | id, nome, categoria (chave de EPI do app: `helmet`, `vest`, `gloves`, `glasses`, `mask`, `safety_shoe`, `ear_protection` ou `outro`), ca (texto, único), validade_ca (date), fabricante, vida_util_dias (int), ficticio, criado_em |
| `entregas_epi` | id, codigo (único, ex. `SEED-ENT-0001` ou `ENT-<uuid curto>`), colaborador_id (FK), epi_id (FK), **ca_na_entrega** e **epi_nome_na_entrega** (registro legal congelado: o CA e o nome do dia da entrega; editar o catálogo depois não os muda), quantidade (int ≥ 1), entregue_em (date), troca_prevista_em (date = entregue_em + vida_util_dias), devolvido_em (date, nulo), motivo (`admissao`, `substituicao`, `perda`, `dano`), observacao, registrado_por, ficticio, criado_em |
| `ocorrencias` | id, codigo (único), tipo (`acidente`, `quase_acidente`, `condicao_insegura`, `ato_inseguro`), gravidade (`baixa`, `media`, `alta`, `critica`), setor, descricao, ocorrida_em (instante), status (`aberta`, `em_tratamento`, `encerrada`), colaborador_id (FK, nulo), acao_corretiva, alerta_id (int, nulo, sem FK como `Alert`), registrada_por, encerrada_em, ficticio, criado_em |

Situações calculadas no servidor (nunca gravadas), com `hoje` = data local do servidor:

- CA: `vencido` se `validade_ca < hoje`; `a_vencer` se `≤ 30 dias`; senão `valido`. Também `dias_para_vencer`.
- Entrega: `devolvido` se `devolvido_em`; `troca_vencida` se `troca_prevista_em < hoje`; senão `vigente`.

Regra de negócio: **não registra entrega de EPI com CA vencido** (409, `code=ca_vencido`). É política da empresa, não
uma exigência literal da norma. A data de entrega nunca é futura, então "vencido antes da entrega" e "vencido hoje" são a
mesma checagem. Devolução de entrega já devolvida: 409 `ja_devolvido`. **Colaborador desligado** (`ativo=false`) continua
legível (cadastro, histórico), mas não recebe entrega nova: 409 `colaborador_inativo` (devolver continua permitido).

Códigos de erro (além dos já citados): 400 `campo_invalido` (campo ausente ou inválido), 400 `data_invalida` (entrega ou devolução
no futuro, devolução antes da entrega, ocorrência mais de 5 min à frente do relógio), 400 `filtro_invalido` (filtro de
consulta fora da lista ou `colaborador_id`/`epi_id` não numérico), **400 `vinculo_proibido`** (ocorrência com `colaborador_id`
**e** `alerta_id`: ocorrência ligada a um alerta da câmera não identifica pessoa), 404 `colaborador_nao_encontrado`,
`epi_nao_encontrado`, `entrega_nao_encontrada`, `ocorrencia_nao_encontrada`, `alerta_nao_encontrado`, `recurso_desconhecido`, 409
`matricula_duplicada`, `ca_duplicado`, **`duplicado`** (corrida na gravação: dois pedidos com a mesma chave única).

Validações: matrícula é gravada em MAIÚSCULAS (a repetida vale em qualquer caixa); datas de calendário aceitam só ano de
1900 a (ano atual + 1); `busca` usa os 100 primeiros caracteres e `%`/`_` valem como texto; PUT é parcial (o que não vier fica como está).

Listagens (`colaboradores`, `epis`, `entregas`, `ocorrencias`) têm teto de 1000 itens e trazem **`truncado: bool`** (há mais do que
o devolvido). O detalhe do colaborador traz `entregas_truncado`. A exportação CSV tem teto de 50000 linhas e, se passar, responde
com o cabeçalho `X-Registros-Truncados: true`.

Trilha de edição: PUT de colaborador, PUT de item (inclui renovar a validade do CA) e PUT de ocorrência gravam um `EventLog`
(`gestao_colaborador_editado`, `gestao_epi_editado`, `gestao_ocorrencia_atualizada`) com `subject`/`metadata.por` = quem, e
`metadata.antes`/`depois` só com os campos que mudaram (na ocorrência, `status` e `encerrada_em` anterior, inclusive na reabertura).
Sem mudança, nada é gravado.

## Rotas

| Método | Rota | Papel | Corpo / query | Resposta |
|---|---|---|---|---|
| GET | `/api/gestao/resumo` | técnico | — | `{colaboradores_ativos, epis_no_catalogo, entregas_vigentes, trocas_vencidas, cas_vencidos, cas_a_vencer, ocorrencias_abertas, ocorrencias_30d, alertas_30d, alertas_simulados_30d, simulados: bool}` (`alertas_30d` é o total, inclui os simulados; `alertas_simulados_30d` diz quantos deles são histórico de demonstração) |
| GET | `/api/gestao/colaboradores` | técnico | `busca`, `setor`, `ativo` | `{items: [Colaborador + {entregas_vigentes, pendencias}], count, truncado, setores: [..]}` (`pendencias` é um número: entregas em aberto com troca vencida ou com CA vencido) |
| POST | `/api/gestao/colaboradores` | supervisor | matricula, nome, setor, funcao, admissao | 201 `{colaborador}`; 409 `matricula_duplicada` |
| GET | `/api/gestao/colaboradores/<id>` | técnico | — | `{colaborador, entregas: [Entrega], entregas_truncado, ocorrencias: [Ocorrencia]}` (entregas do mais recente ao mais antigo = histórico) |
| PUT | `/api/gestao/colaboradores/<id>` | supervisor | campos acima + ativo | `{colaborador}` |
| GET | `/api/gestao/epis` | técnico | `categoria`, `situacao` | `{items: [Epi + {situacao_ca, dias_para_vencer, entregas_vigentes}], count, truncado}` |
| POST | `/api/gestao/epis` | supervisor | nome, categoria, ca, validade_ca, fabricante, vida_util_dias | 201 `{epi}`; 409 `ca_duplicado` |
| PUT | `/api/gestao/epis/<id>` | supervisor | idem | `{epi}` |
| GET | `/api/gestao/entregas` | técnico | `colaborador_id`, `epi_id`, `situacao` | `{items: [Entrega], count, truncado}` |
| POST | `/api/gestao/entregas` | técnico | colaborador_id, epi_id, quantidade, entregue_em, motivo, observacao | 201 `{entrega}`; 409 `ca_vencido` |
| POST | `/api/gestao/entregas/<id>/devolucao` | técnico | devolvido_em (opcional, padrão hoje) | `{entrega}`; 409 `ja_devolvido` |
| GET | `/api/gestao/ocorrencias` | técnico | `status`, `tipo`, `setor` | `{items: [Ocorrencia], count, truncado}` |
| POST | `/api/gestao/ocorrencias` | técnico | tipo, gravidade, setor, descricao, ocorrida_em, colaborador_id? **ou** alerta_id? (nunca os dois: 400 `vinculo_proibido`) | 201 `{ocorrencia}` |
| PUT | `/api/gestao/ocorrencias/<id>` | técnico | status, acao_corretiva | `{ocorrencia}` (status `encerrada` preenche `encerrada_em`) |
| GET | `/api/gestao/exportar/<recurso>.csv` | técnico | recurso ∈ `colaboradores`, `epis`, `entregas`, `ocorrencias`, `alertas` | CSV `text/csv; charset=utf-8`, BOM UTF-8, separador `;`, `Content-Disposition: attachment; filename=visionepi-<recurso>-<AAAA-MM-DD>.csv` |

`Entrega` serializada: `{id, codigo, colaborador: {id, matricula, nome, setor}, epi: {id, nome, categoria, ca, situacao_ca},
quantidade, entregue_em, troca_prevista_em, devolvido_em, motivo, observacao, registrado_por, situacao, ficticio}`.

Em `epi` da entrega, `nome` e `ca` vêm do registro CONGELADO da entrega; `situacao_ca` (`valido`, `a_vencer`, `vencido`) é a
situação ATUAL do item do catálogo (a tela usa para o selo "CA vencido" sem reescrever o que foi entregue).

`Ocorrencia` serializada: todos os campos + `colaborador: {id, nome, matricula} | null`.

O servidor já responde 404 com o shell para endereço de SPA desconhecido (`app/api/status.py`): a rota de tela
**`/gestao`** precisa ser conhecida lá também.

## Seed idempotente (`app/services/gestao_seed.py`)

- Comando único: `flask --app wsgi gestao semear` (imprime quantos registros criou, quantos já existiam e quantos ignorou).
  Fora do modo demo (`DEMO_MODE`) o comando **recusa**, a menos que receba `--dados-ficticios` (grava 40 alertas e demais dados
  FICTÍCIOS no banco configurado).
- `python run.py --demo` chama o mesmo seed automaticamente depois de criar câmeras e contas.
- Idempotência por chave natural: `matricula`, `ca`, `codigo`, `seed_id`. Rodar duas vezes não duplica nada (teste prova).
  Se a chave já existe como registro REAL (`ficticio=false`), o seed a ignora ("ignorado: registro real") e não pendura nada nela.
- Realismo: nenhuma entrega antes da admissão; o motivo `admissao` só aparece em entrega até 30 dias depois da admissão (os
  veteranos têm reposições: `substituicao`, `perda`, `dano`).
- Determinístico: `random.Random(5550)`; datas relativas a `hoje`.
- Conteúdo (Metaindústria, setores das câmeras da demo + 2): Obra, Expedição, Manutenção, Portaria, Usinagem,
  Almoxarifado. **24 colaboradores**; **10 itens no catálogo** (capacete, colete refletivo, luva de vaqueta, luva
  nitrílica, óculos incolor, respirador PFF2, calçado de segurança, protetor auricular tipo plug, protetor tipo
  concha, cinto tipo paraquedista), com **1 CA vencido** e **2 a vencer em 30 dias**; **~60 entregas** nos últimos
  12 meses (histórico por colaborador, algumas devolvidas por substituição, algumas com troca vencida);
  **15 ocorrências** nos últimos 90 dias (tipos e gravidades variados, 4 abertas, 3 em tratamento, o resto
  encerrado com ação corretiva); **alertas históricos**: 40 `Alert` **resolvidos**, criados entre 2 e 30 dias atrás,
  com `metadata_json = {"simulado": true, "seed_id": "SEED-ALR-00xx"}`, regras e features que o app já usa
  (`missing_helmet`/`missing_vest`/`missing_gloves` com a feature correspondente, `risk_area_presence`,
  `fall_detected`; ver `app/services/risk_rules.py`), `camera_id` das câmeras existentes (nulo se não
  houver câmera). Nenhum alerta do seed é `active` e nenhum cai nas últimas 24 h, e o cálculo de risco ao vivo **exclui** alerta com
  `metadata_json.simulado` verdadeiro: o painel ao vivo não muda. O relatório mensal mantém os números, devolve
  `alertas_simulados: N` (e `alertas.simulados`) e a página mostra "Este relatório inclui N alertas simulados (histórico de
  demonstração, sem vídeo)." quando N > 0.
