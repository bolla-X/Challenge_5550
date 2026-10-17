# API do VisionEPI: como um sistema externo consome

A API é a mesma que a interface usa. Dois endereços a descrevem, ambos para **Técnico ou
acima**:

| Endereço | O que é |
|---|---|
| `GET /api/openapi.json` | Documento OpenAPI 3.1, gerado das rotas do servidor (rota nova aparece sozinha). |
| `GET /api/docs` | Página HTML offline, sem CDN: operações por grupo, tipo de conta de cada uma e exemplo de `curl`. |

O documento diz, em cada operação, o **tipo de conta mínimo** (`x-conta-minima`: `operator`,
`technical` ou `supervisor`; `null` é rota sem login). A tabela de descrições curtas das rotas de
integração fica em `app/services/openapi_doc.py` (`ROTAS`); as demais rotas `/api/*` saem com a
primeira linha do docstring da view. Onde o decorador não conta a regra inteira (custódia,
evacuação por token do palco) a observação está em `ACESSO_EXPLICITO`.

## Autenticação

Sessão por cookie (`HttpOnly`, assinado pelo servidor). Não existe chave de API:

1. `POST /api/auth/login` com `{"email": "...", "password": "..."}` devolve o cookie `session`.
2. Envie o cookie em toda chamada seguinte. `requests.Session` e `curl -b cookies.txt` fazem isso.
3. `401` é sessão ausente ou vencida (entre de novo); `403` é conta sem o tipo mínimo da rota.
4. Excesso de tentativas de login devolve `retry_after` (segundos) no corpo.

Use uma **conta própria da integração**, com o menor tipo de conta que a tarefa pede (Técnico para
ler incidentes e verificar a cadeia inteira). Credenciais vêm de variável de ambiente ou cofre,
nunca do código. Com `python run.py --https` o certificado é autoassinado (fica em `instance/certs/`):
aponte `verify=` para ele em vez de desligar a verificação.

## Exemplo 1: login por sessão

```python
import os

import requests

BASE = os.environ.get("VISIONEPI_URL", "https://visionepi.local:5000")
CERTIFICADO = os.environ.get("VISIONEPI_CA")  # caminho do .pem; vazio usa a verificação padrão


def entrar() -> requests.Session:
    sessao = requests.Session()
    sessao.verify = CERTIFICADO or True
    resposta = sessao.post(
        f"{BASE}/api/auth/login",
        json={"email": os.environ["VISIONEPI_EMAIL"], "password": os.environ["VISIONEPI_SENHA"]},
        timeout=10,
    )
    resposta.raise_for_status()  # 401: credencial errada; 429: espere `retry_after`
    return sessao  # o cookie fica na sessão e segue em todas as chamadas
```

## Exemplo 2: incidentes ativos

`GET /api/incidentes?status=active` devolve `{"items": [...], "count": N}`, do mais recente para o
mais antigo. Cada incidente agrupa alertas da mesma regra e zona; `pessoas` são **rótulos de
rastreio** ("Pessoa 4"), nunca identidade.

```python
def incidentes_ativos(sessao: requests.Session, camera_id: int | None = None) -> list[dict]:
    parametros = {"status": "active", "limit": 100}
    if camera_id is not None:
        parametros["camera_id"] = camera_id
    resposta = sessao.get(f"{BASE}/api/incidentes", params=parametros, timeout=10)
    resposta.raise_for_status()
    return resposta.json()["items"]


if __name__ == "__main__":
    sessao = entrar()
    for incidente in incidentes_ativos(sessao):
        print(incidente["id"], incidente["titulo"], incidente["zona"], f'{incidente["pico_pessoas"]} pessoa(s) no pico')
```

Para reconhecer um incidente ("vi isto"): `POST /api/incidentes/{id}/reconhecer`. Isso mede o tempo
até a resposta e **não resolve** nada; o incidente fecha quando a violação acaba.

## Exemplo 3: verificar a cadeia de custódia

`GET /api/custodia/verificar` refaz a cadeia de SHA-256 das evidências. Sem parâmetro verifica a
cadeia inteira (Técnico ou acima); com `?incidente_id=N` confere só as evidências daquele incidente.

```python
def cadeia_integra(sessao: requests.Session, incidente_id: int | None = None) -> bool:
    parametros = {"incidente_id": incidente_id} if incidente_id is not None else {}
    resposta = sessao.get(f"{BASE}/api/custodia/verificar", params=parametros, timeout=120)
    resposta.raise_for_status()
    resultado = resposta.json()
    if resultado["adulterada"]:
        # `quebrado` aponta o primeiro elo com problema (registro alterado, conteúdo alterado, cadeia quebrada).
        print("Cadeia ADULTERADA no elo", resultado["quebrado"]["situacao"], resultado["quebrado"].get("ref"))
    elif resultado["ausentes"]:
        print(f'{resultado["ausentes"]} evidência(s) ausente(s) no disco, sem prova de adulteração')
    return bool(resultado["integra"])
```

`integra` é `true` só quando nenhum elo falha e nenhuma evidência sumiu. A verificação da cadeia
inteira lê todos os arquivos de evidência: use um `timeout` generoso e não a rode a cada segundo.

## Outras rotas úteis

| Para | Rota |
|---|---|
| Estado da planta (o mesmo do OPC UA e MQTT) | `GET /api/integracao/estado` |
| Alertas recentes, com filtros | `GET /alerts` (rota legada, sem prefixo `/api`) |
| Estado da evacuação | `GET /api/evacuacao` (Técnico ou acima; acionar e encerrar é do Supervisor) |
| Relatório do turno em JSON | `GET /api/relatorio/turno?horas=8` |
| Buscar nas trilhas gravadas | `GET /api/busca/trilhas?camera_id=1&zona=1&epi_ausente=helmet` |

Todas as respostas de erro trazem `error` em português do Brasil; o `code`, quando existe, é
estável e serve para tratar o erro em código.
