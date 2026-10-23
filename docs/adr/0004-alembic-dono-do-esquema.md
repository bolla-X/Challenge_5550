# ADR 0004: Alembic é o dono do esquema do banco

- **Status:** aceito (vigente)
- **Data:** 08/09/2026 (teste que reproduz o defeito `e51d952`, vermelho; correção `73edc00`, "Alembic passa a ser o dono do esquema por padrão")

## Contexto

Com `AUTO_CREATE_TABLES=true`, `create_app()` chama `db.create_all()`. O CLI do Flask constrói a aplicação **antes** de executar o subcomando,
então as tabelas nascem sem `alembic_version` e o `flask --app wsgi db upgrade` seguinte morre com `table alerts already exists`, **num clone
limpo** (README, nota sobre `AUTO_CREATE_TABLES`). O defeito foi caracterizado por teste antes da correção (padrão "teste VERMELHO, fix VERDE").

## Decisão

- Padrão `AUTO_CREATE_TABLES=false` (`.env.example`); quem cria e evolui o esquema é o Alembic (Flask-Migrate), em `migrations/versions/`.
- Toda tabela ou coluna nova entra por migração. Hoje são 20 arquivos, do esquema inicial `f6cd160ae4e0` até `a8b9c0d1e2f3` (Gestão de EPIs,
  desta entrega, que parte de `d3e4f5a6b7c8`, área de detecção).
- Bancos antigos criados por `create_all` recebem `flask --app wsgi db stamp f6cd160ae4e0` uma vez, antes do `upgrade`.
- Exceção deliberada: o modo demonstração liga `AUTO_CREATE_TABLES=true` (`app/demo_ambiente.py`) porque o banco isolado é recriado do zero a
  cada subida (ver ADR 0007).
- O caminho documentado de instalação é coberto por `tests/test_onboarding.py`.

## Consequências

- O README precisa do passo `flask --app wsgi db upgrade` e da criação da primeira conta (`flask --app wsgi users create --role supervisor`).
- Mudança de modelo sem migração falha cedo, em vez de divergir silenciosamente entre bancos.
- Dois mundos coexistem: banco do dia a dia (Alembic) e banco da demo (`create_all`). Qualquer teste de migração precisa olhar o primeiro.

## Alternativas

- `db.create_all()` no boot (comportamento original): **rejeitada**, quebra o `upgrade` num clone limpo.
- Migração manual por SQL: **sem registro** de avaliação nos documentos.
