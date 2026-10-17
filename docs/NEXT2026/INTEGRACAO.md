# Integração industrial — como um CLP ou SCADA consome o VisionEPI

O VisionEPI publica o **estado da planta** a cada segundo e cada **alerta novo** em
três canais, todos opcionais e desligados por padrão:

| Canal | Liga com | Endereço padrão | Para quê |
|---|---|---|---|
| OPC UA (servidor) | `OPCUA_ATIVO=true` | `opc.tcp://127.0.0.1:4840/visionepi/` | SCADA/CLP lê nós (pull ou subscription) |
| MQTT (publicador) | `MQTT_ATIVO=true` | broker em `MQTT_HOST:MQTT_PORTA` (1883) | barramento de eventos da fábrica |
| Webhook HTTP | `WEBHOOK_URL=https://...` | — | sistema de chamados, ERP, Teams/Slack via integrador |

No modo demo (`python run.py --demo`) o OPC UA e o MQTT sobem ligados, com um
**broker MQTT embutido** (amqtt, MIT) em `127.0.0.1:1883` — tudo offline.

O mesmo estado alimenta a **torre de luz virtual** em `/torre` e no Modo TV:
o que a torre mostra é exatamente o que o CLP lê.

## Regras da torre

| Cor | Quando |
|---|---|
| vermelho | algum alerta crítico ativo (queda, sem capacete, sem vigia…) **ou** câmera obstruída/movida |
| amarelo | alerta não crítico ativo, câmera sem sinal, ou imagem escura/ofuscada/desfocada |
| verde | nenhum alerta ativo e todas as câmeras com imagem |

`sirene = true` quando a torre está vermelha **e** há alerta crítico ainda não
reconhecido ("avisei o colaborador"). Reconhecer cala a sirene; a torre só volta
a verde quando a violação acaba. `PlantaEmAlarme` = torre vermelha.

## OPC UA

- Namespace `urn:visionepi` — **leia o índice pelo URI** (`GetNamespaceIndex`),
  não fixe o número (no servidor de hoje é 2).
- Todos os NodeIds são do tipo string. Somente leitura: escrita e chamada de
  método voltam `BadUserAccessDenied`.

| BrowsePath (a partir de Objects) | NodeId | Tipo |
|---|---|---|
| `Planta/PlantaEmAlarme` | `ns=<i>;s=Planta.PlantaEmAlarme` | Boolean |
| `Planta/Torre` | `ns=<i>;s=Planta.Torre` | String: `verde` \| `amarelo` \| `vermelho` |
| `Cameras/Camera_<id>/Estado` | `ns=<i>;s=Cameras.Camera_<id>.Estado` | String: `ok` \| `atencao` \| `alarme` \| `offline` |
| `Cameras/Camera_<id>/Conformidade` | `ns=<i>;s=Cameras.Camera_<id>.Conformidade` | Double 0–1 (NaN sem pessoas) |
| `Cameras/Camera_<id>/UltimoAlerta` | `ns=<i>;s=Cameras.Camera_<id>.UltimoAlerta` | String (vazia se não houver) |
| `Cameras/Camera_<id>/IncidentesAtivos/<regra>` | `ns=<i>;s=Cameras.Camera_<id>.IncidentesAtivos.<regra>` | Int32, criado na 1ª ocorrência |

`<regra>` é o código da regra (`missing_helmet`, `fall_detected`, `sem_vigia`,
`camera_obstruida`, `regra:<id>` do editor…); `.` e `/` viram `_`.

Exemplo (Python, asyncua):

```python
from asyncua.sync import Client

with Client("opc.tcp://192.168.0.50:4840/visionepi/") as c:
    i = c.get_namespace_index("urn:visionepi")
    if c.get_node(f"ns={i};s=Planta.PlantaEmAlarme").read_value():
        print("parar a esteira")
```

Num CLP com cliente OPC UA (ex.: bloco `UA_Connect`/`UA_ReadList` de IEC 61131-3),
leia `Planta.PlantaEmAlarme` e ligue a uma saída digital de intertravamento ou à
torre física.

## MQTT

| Tópico | QoS | Retain | Corpo (JSON UTF-8) |
|---|---|---|---|
| `visionepi/planta/estado` | 1 | **sim** | `{"planta_em_alarme", "torre", "sirene", "cameras": [...], "ts"}` |
| `visionepi/<camera_id>/alerta` | 1 | não | `{"id", "camera_id", "regra", "severidade", "mensagem", "ts"}` |

O estado é retido (quem assina depois recebe o último na hora); alerta é evento e
não é retido, para um assinante novo não ver alerta velho como atual. Assine
`visionepi/#` para tudo. Exemplo:

```bash
mosquitto_sub -h 127.0.0.1 -t "visionepi/#" -v
```

Limite conhecido (amqtt 0.12.1): um assinante que entra depois pode receber a
mensagem retida duas vezes (QoS 0 e QoS 1, mesmo conteúdo). O conteúdo é idêntico.

## Webhook

`POST` `application/json` a cada alerta novo:
`{"tipo": "alerta", "camera_id": 1, "alerta": {...}, "ts": "<ISO UTC>"}`.

Proteção contra SSRF: só `http`/`https`, sem usuário/senha na URL, sem seguir
redirecionamento; destinos de link-local (169.254.0.0/16, metadados de nuvem),
multicast e 0.0.0.0 são sempre recusados; loopback e redes privadas só com
`WEBHOOK_PERMITIR_REDE_LOCAL=true`. O host é resolvido e validado a cada envio
(fecha DNS rebinding).

## Status e falhas

`GET /api/integracao/estado` (logado) devolve o estado e o status de cada canal
(`no_ar`, `desligado`, `falhou` + motivo em pt-BR). Porta ocupada, broker fora ou
rede caída **nunca derrubam o app**: o canal aparece como `falhou` e o MQTT se
reconecta sozinho quando o broker volta (fila de até 200 mensagens).

## Segurança — leia antes de ligar em produção

- O OPC UA sobe com política `NoSecurity` (sem certificado, sem usuário) e o
  broker embutido é anônimo, sem TLS: **use só em rede de chão de fábrica
  isolada**. Para produção: OPC UA `Basic256Sha256` com certificado e MQTT com
  TLS e credencial num broker da planta.
- Nada publicado identifica pessoa: só contagens por regra, conformidade
  agregada e a mensagem do alerta (com rótulo de rastreio, nunca nome).

## Licenças

asyncua (LGPL-3.0, usada como biblioteca sem modificação), paho-mqtt
(EPL-2.0 ou BSD-3-Clause) e amqtt (MIT) — fontes no CHANGELOG (MISSÃO 4) e em
`ATRIBUICOES.md`.
