# ADR 0008: Gestão de EPIs como cadastro administrativo separado da visão

- **Status:** aceito (código, telas e testes existem em 23/10/2026; a execução verde está na ata; contrato em `docs/specs/es-sprint4-contrato-gestao.md`)
- **Data:** 23/10/2026

## Contexto

A Sprint 4 de Engenharia de Software pede "gestão de EPIs e segurança industrial": colaboradores com histórico de EPIs, catálogo com CA e
validade, entregas, ocorrências e exportação. O inventário de 23/10 (`docs/specs/ESTADO-es-sprint4.md`) mostrou que **não existia** nenhum
modelo de colaborador, catálogo com CA, entrega ou ocorrência manual; só alertas da visão. O ADR 0005 proíbe ligar pessoa a ID de rastreio.

## Decisão

- **Módulo novo e separado da visão**: tabelas próprias (`colaboradores`, `epis_catalogo`, `entregas_epi`, `ocorrencias`; migração
  `a8b9c0d1e2f3`), serviço `app/services/gestao_epi.py`, rotas `app/api/gestao.py` sob `/api/gestao/*`, seed `app/services/gestao_seed.py`,
  tela `/gestao` (`frontend/src/components/gestao.tsx` e `gestao/`).
- **Nenhuma coluna liga colaborador a ID de rastreio, câmera ou imagem.** A tela diz: "Cadastro administrativo: não é ligado às câmeras".
  Sem CPF, sem foto: matrícula, nome, setor, função, admissão. A ficha de EPI é cadastro (NR-6), não vigilância.
- Regras de negócio no servidor (`app/services/gestao_epi.py`): **não registra entrega de EPI com CA vencido** (409 `ca_vencido`) nem para
  colaborador desligado (409 `colaborador_inativo`); devolução repetida dá 409 `ja_devolvido`. Ler não é usar: cadastro, histórico e relatório
  continuam legíveis. O bloqueio por CA vencido é **política da empresa**, não exigência literal da norma: o código cita a NR-6 (item 6.5.1,
  registro do fornecimento, e 6.5.1.1, relatórios de sistema eletrônico), que é o que a exportação CSV atende. Situação do CA (`valido`, `a_vencer` em até 30 dias, `vencido`) e da entrega (`vigente`, `troca_vencida`, `devolvido`) são
  **calculadas**, nunca gravadas.
- Papéis: técnico ou mais lê, registra entrega, devolução e ocorrência e exporta; supervisor cadastra e edita colaborador e item do catálogo;
  operador recebe 403 (o quiosque não usa o módulo); sem sessão, 401.
- Exportação CSV (`/api/gestao/exportar/<recurso>.csv`): UTF-8 com BOM, separador `;`, nome com a data.
- **Dados do seed são simulados e marcados como simulados** (nomes fictícios, fabricantes "fictícios", CAs na faixa `9xxxxx` com
  `ficticio=true`); a tela mostra o selo "Dados simulados".

## Consequências

- Não existe cruzamento "colaborador x violação detectada pela câmera". É limitação **intencional**. O único vínculo com a visão é
  opcional e de evento: `ocorrencias.alerta_id` (inteiro, sem FK, como `Alert` já faz), nunca de pessoa.
- Uma tabela nova obriga migração (ADR 0004) e entrada na matriz de permissões (teste-guarda `tests/test_matriz_de_permissoes.py`). A rota de
  tela `/gestao` também precisa ser conhecida em `app/api/status.py` para o servidor devolver o shell em vez de 404.
- A exportação `alertas` reaproveita o histórico de alertas existente; os alertas semeados são **resolvidos**, com `metadata_json.simulado`
  verdadeiro, e nenhum cai nas últimas 24 h, para o painel ao vivo não mudar.

## Alternativas

- Ligar colaborador a ID de rastreio ou reconhecer o rosto para registrar a infração em nome de alguém: **rejeitada** (ADR 0005).
- Reaproveitar o modelo `User` (contas do sistema) como colaborador: **sem registro** de avaliação; o contrato separa cadastro administrativo de
  conta de acesso.
- Integrar um sistema externo de SST: **fora do escopo** da spec.
