# QA — VisionEPI (MISSÃO 4)


<!-- crawler:inicio -->
## Crawler botão a botão — última rodada 17/10/2026 02:43

Rotas × papéis × temas varridos: **37**. Elementos interativos: **328**. Botões sem efeito: **1**. Problemas: **82**.

| rota | papel | tema | elementos | acionados | desabilitados | sem efeito | erros de console | 4xx/5xx | resultado |
|---|---|---|---|---|---|---|---|---|---|
| auditoria | operator | light | 3 | 3 | 0 | 1 | 1 | 2 | 12 problemas |
| desafio | operator | light | 1 | 1 | 0 | 0 | 0 | 0 | OK |
| evacuacao | operator | light | 0 | 0 | 0 | 0 | 1 | 1 | 2 problemas |
| gemeo-2d | operator | light | 2 | 2 | 0 | 0 | 0 | 0 | OK |
| gemeo | operator | light | 3 | 3 | 0 | 0 | 0 | 0 | OK |
| kiosk | operator | light | 9 | 7 | 1 | 0 | 1 | 0 | 1 problema |
| liga | operator | light | 2 | 2 | 0 | 0 | 0 | 0 | OK |
| palco | operator | light | 0 | 0 | 0 | 0 | 1 | 2 | 3 problemas |
| permissoes | operator | light | 1 | 1 | 0 | 0 | 0 | 0 | OK |
| portal | operator | light | 1 | 1 | 0 | 0 | 0 | 0 | OK |
| regras | operator | light | 0 | 0 | 0 | 0 | 1 | 1 | 2 problemas |
| retrospectiva | operator | light | 8 | 8 | 0 | 0 | 0 | 0 | OK |
| rotular | operator | light | 0 | 0 | 0 | 0 | 0 | 0 | OK |
| simulador | operator | light | 0 | 0 | 0 | 0 | 1 | 0 | 1 problema |
| torre | operator | light | 0 | 0 | 0 | 0 | 0 | 0 | OK |
| tv | operator | light | 0 | 0 | 0 | 0 | 0 | 0 | OK |
| login | sem_sessao | light | 1 | 0 | 1 | 0 | 0 | 0 | 1 problema |
| palco-controle-sem-token | sem_sessao | light | 2 | 0 | 2 | 0 | 1 | 1 | 4 problemas |
| grade | supervisor | light | 18 | 16 | 1 | 0 | 1 | 0 | 1 problema |
| auditoria | technical | light | 2 | 2 | 0 | 0 | 0 | 0 | OK |
| desafio | technical | light | 1 | 1 | 0 | 0 | 0 | 0 | OK |
| evacuacao | technical | light | 0 | 0 | 0 | 0 | 0 | 0 | OK |
| foco-canteiro | technical | light | 64 | 61 | 2 | 0 | 0 | 0 | OK |
| foco-multidao | technical | light | 127 | 124 | 2 | 0 | 1 | 0 | 55 problemas |
| gemeo-2d | technical | light | 2 | 2 | 0 | 0 | 0 | 0 | OK |
| gemeo | technical | light | 3 | 3 | 0 | 0 | 0 | 0 | OK |
| grade | technical | light | 8 | 6 | 1 | 0 | 0 | 0 | OK |
| liga | technical | light | 2 | 2 | 0 | 0 | 0 | 0 | OK |
| palco | technical | light | 0 | 0 | 0 | 0 | 0 | 0 | OK |
| permissoes | technical | light | 4 | 4 | 0 | 0 | 0 | 0 | OK |
| portal | technical | light | 1 | 1 | 0 | 0 | 0 | 0 | OK |
| regras | technical | light | 37 | 37 | 0 | 0 | 0 | 0 | OK |
| retrospectiva | technical | light | 8 | 8 | 0 | 0 | 0 | 0 | OK |
| rotular | technical | light | 3 | 3 | 0 | 0 | 0 | 0 | OK |
| simulador | technical | light | 15 | 13 | 2 | 0 | 0 | 0 | OK |
| torre | technical | light | 0 | 0 | 0 | 0 | 0 | 0 | OK |
| tv | technical | light | 0 | 0 | 0 | 0 | 0 | 0 | OK |

Detalhe de cada rota em `bench/runtime/crawler/<papel>-<tema>-<rota>.json` (fora do git).

### auditoria · operator · light

- resposta inesperada ao acionar Verificar integridade: GET api/custodia/verificar → 403
- botão sem efeito: Tentar de novo
- resposta inesperada ao acionar Tentar de novo: GET api/custodia/verificar → 403
- resposta inesperada ao acionar Tentar de novo: GET api/custodia/verificar → 403
- resposta inesperada ao acionar Tentar de novo: GET api/custodia/verificar → 403
- resposta inesperada ao acionar Tentar de novo: GET api/custodia/verificar → 403
- resposta inesperada ao acionar Tentar de novo: GET api/custodia/verificar → 403
- resposta inesperada ao acionar Tentar de novo: GET api/custodia/verificar → 403
- resposta inesperada ao acionar Tentar de novo: GET api/custodia/verificar → 403
- resposta inesperada ao acionar Tentar de novo: GET api/custodia/verificar → 403
- erro no console: Failed to load resource: the server responded with a status of 403 (FORBIDDEN)
- resposta GET api/custodia?limit=100 → 403

### evacuacao · operator · light

- erro no console: Failed to load resource: the server responded with a status of 403 (FORBIDDEN)
- resposta GET api/evacuacao → 403

### kiosk · operator · light

- erro no console: TypeError: Failed to fetch
    at Z (http://127.0.0.1:50388/static/dist/assets/index-BRKCSXIl.js:61:46408)
    at PS (http://127.0.0.1:50388/static/dist/assets/index-BRKCSXIl.js:61:46954)
    at stop (http://127.0.0.1:50388/static/dist/assets/index-BRKCSXIl.js:61:56669)
    at h (http://127.0.0.1:50

### palco · operator · light

- erro no console: Failed to load resource: the server responded with a status of 403 (FORBIDDEN)
- resposta GET api/palco/controle → 403
- resposta GET api/palco/estado → 403

### regras · operator · light

- erro no console: Failed to load resource: the server responded with a status of 403 (FORBIDDEN)
- resposta GET api/regras → 403

### simulador · operator · light

- erro no console: [loadCameras] failed TypeError: Cannot read properties of null (reading 'items')
    at http://127.0.0.1:50388/static/dist/assets/index-BRKCSXIl.js:61:53970
    at r (http://127.0.0.1:50388/static/dist/assets/index-BRKCSXIl.js:41:58919)
    at loadCameras (http://127.0.0.1:50388/static/dist/assets/i

### login · sem_sessao · light

- desabilitado sem explicação: Entrar

### palco-controle-sem-token · sem_sessao · light

- desabilitado sem explicação: Anterior
- desabilitado sem explicação: Próxima
- erro no console: Failed to load resource: the server responded with a status of 401 (UNAUTHORIZED)
- resposta GET api/palco/estado?t= → 401

### grade · supervisor · light

- erro no console: TypeError: Failed to fetch
    at Z (http://127.0.0.1:50388/static/dist/assets/index-BRKCSXIl.js:61:46408)
    at PS (http://127.0.0.1:50388/static/dist/assets/index-BRKCSXIl.js:61:46954)
    at stop (http://127.0.0.1:50388/static/dist/assets/index-BRKCSXIl.js:61:56669)
    at h (http://127.0.0.1:50

### foco-multidao · technical · light

- elemento interativo sem nome acessível: button|#1
- elemento interativo sem nome acessível: button|#2
- elemento interativo sem nome acessível: button|#3
- elemento interativo sem nome acessível: button|#4
- elemento interativo sem nome acessível: button|#5
- elemento interativo sem nome acessível: button|#6
- elemento interativo sem nome acessível: button|#7
- elemento interativo sem nome acessível: button|#8
- elemento interativo sem nome acessível: button|#9
- elemento interativo sem nome acessível: button|#10
- elemento interativo sem nome acessível: button|#11
- elemento interativo sem nome acessível: button|#12
- elemento interativo sem nome acessível: button|#13
- elemento interativo sem nome acessível: button|#14
- elemento interativo sem nome acessível: button|#15
- elemento interativo sem nome acessível: button|#16
- elemento interativo sem nome acessível: button|#17
- elemento interativo sem nome acessível: button|#18
- elemento interativo sem nome acessível: button|#19
- elemento interativo sem nome acessível: button|#20
- elemento interativo sem nome acessível: button|#21
- elemento interativo sem nome acessível: button|#22
- elemento interativo sem nome acessível: button|#23
- elemento interativo sem nome acessível: button|#24
- elemento interativo sem nome acessível: button|#25
- elemento interativo sem nome acessível: button|#26
- elemento interativo sem nome acessível: button|#27
- elemento interativo sem nome acessível: button|#28
- elemento interativo sem nome acessível: button|#29
- elemento interativo sem nome acessível: button|#30
- elemento interativo sem nome acessível: button|#31
- elemento interativo sem nome acessível: button|#32
- elemento interativo sem nome acessível: button|#33
- elemento interativo sem nome acessível: button|#34
- elemento interativo sem nome acessível: button|#35
- elemento interativo sem nome acessível: button|#36
- elemento interativo sem nome acessível: button|#37
- elemento interativo sem nome acessível: button|#38
- elemento interativo sem nome acessível: button|#39
- elemento interativo sem nome acessível: button|#40
- elemento interativo sem nome acessível: button|#41
- elemento interativo sem nome acessível: button|#42
- elemento interativo sem nome acessível: button|#43
- elemento interativo sem nome acessível: button|#44
- elemento interativo sem nome acessível: button|#45
- elemento interativo sem nome acessível: button|#46
- elemento interativo sem nome acessível: button|#47
- elemento interativo sem nome acessível: button|#48
- elemento interativo sem nome acessível: button|#49
- elemento interativo sem nome acessível: button|#50
- elemento interativo sem nome acessível: button|#51
- elemento interativo sem nome acessível: button|#52
- elemento interativo sem nome acessível: button|#53
- elemento interativo sem nome acessível: button|#54
- erro no console: TypeError: Failed to fetch
    at Z (http://127.0.0.1:50388/static/dist/assets/index-BRKCSXIl.js:61:46408)
    at PS (http://127.0.0.1:50388/static/dist/assets/index-BRKCSXIl.js:61:46954)
    at stop (http://127.0.0.1:50388/static/dist/assets/index-BRKCSXIl.js:61:56669)
    at h (http://127.0.0.1:50
<!-- crawler:fim -->
