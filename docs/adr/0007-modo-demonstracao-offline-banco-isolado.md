# ADR 0007: Modo demonstração offline com banco isolado

- **Status:** aceito (vigente; estendido nesta entrega pelos ADRs 0008, 0009 e 0010)
- **Data:** 14/10/2026 (squash do PR7, `a6d303b`; fumaça da demo na `main` em `d76941b`). O modo nasceu no PR4 da branch do NEXT 2026.

## Contexto

A banca e o avaliador precisam ver o sistema funcionando sem câmera IP, sem planta real, sem rede e sem sujar o banco do dia a dia. Uma demo
que depende de configuração manual falha na frente do público (ameaça nº 1 registrada: CPU tomada por outros programas).

## Decisão

- `python run.py --demo` (`run.py`, `app/demo_ambiente.py`, `app/demo.py`):
  - prepara o ambiente **antes** do `create_app()`: banco `instance/demo/demo.db` recriado a cada subida, `SECRET_KEY` gerada na hora,
    `HOST=127.0.0.1`, autenticação ligada, OPC UA e broker MQTT embutido ligados, recursos de visão ligados;
  - semeia câmeras a partir das gravações (Canteiro/Obra, Pátio/Expedição, Escada/Manutenção), a webcam opcional como **Portal** (Portaria)
    e três contas (`supervisor@`, `tecnico@`, `operador@demo.local`) com **senha gerada e impressa só no terminal**;
  - zona e planta do Pátio, metas por setor e missões da Liga prontas; o primeiro acesso já vem concluído.
- `flask --app wsgi demo reset` limpa alertas, eventos, incidentes, custódia, pontos da Liga e fila de rótulos em menos de 10 s (medido
  7,7 a 9,7 s o comando inteiro).
- Desta entrega: a demo também semeia a Gestão de EPIs (`app/services/gestao_seed.py`, ADR 0008).

## Consequências

- As senhas valem só para aquela execução; reiniciar o servidor recria o banco e **apaga áreas desenhadas** (a preparação da arena se refaz).
- Tempo de subida até a primeira análise: mediana 53 s com o cache aquecido, 68 s a frio (`scripts/medir_partida.py`, 14/10).
- As gravações completas não são versionadas (licenças em `docs/FIXTURES.md`); `scripts/fetch_fixtures.py` as baixa. A amostra versionada do
  ADR 0010 cobre a ausência delas.
- O texto de `docs/NEXT2026/DEMO.md` ainda diz "LLM desligado" na demo; desde o ADR 0009 isso não vale mais (ver relatório de inconsistências).

## Alternativas

- Rodar a demo sobre o banco normal: **rejeitada** (mistura dados e exporia contas).
- Senhas fixas de demonstração: **rejeitada**; senha gerada e impressa só no terminal.
- O "modo fixture" de 09/09 (a câmera RTSP morta passa a tocar uma gravação) é outra coisa: resiliência de fonte, não modo de apresentação.
