# Roteiro de teste manual — VisionEPI

Guia para exercitar o sistema à mão, do zero até os casos de borda.

> **Não existem contas pré-criadas.** Não há usuário padrão, senha padrão, nem
> seed automático — em um sistema de segurança do trabalho isso seria uma porta
> aberta. Você cria as contas no passo 3 e as senhas são as que você escolher.

---

## 1. Preparar o ambiente (uma vez)

Requer **Python 3.11 ou 3.12** — não 3.13+. O `mediapipe` e o `numpy` fixados
não publicam wheel acima da 3.12 e o `pip install` falha antes de instalar.

```bash
python -m venv .venv && .venv\Scripts\activate && pip install -r requirements.txt
```

```bash
npm --prefix frontend install && npm --prefix frontend run build
```

## 2. Configurar e criar o banco

```bash
cp .env.example .env
```

O `.env.example` vem com `SECRET_KEY=` **vazio de propósito**. A aplicação se
recusa a subir sem uma chave real — é ela que assina a sessão de login, e uma
chave que constasse no repositório deixaria qualquer pessoa forjar acesso.
Gere a sua:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Cole o resultado em `SECRET_KEY=` no `.env` e crie o esquema:

```bash
flask --app wsgi db upgrade
```

> Se der erro de `SECRET_KEY`, é isso mesmo: a mensagem diz o que fazer. Não
> contorne com `FLASK_DEBUG=true` fora da sua máquina.

### Modelo de detecção (opcional para testar a interface)

Os pesos **não são versionados**. Sem eles o dashboard mostra aviso de "modelo
não suportado" e a detecção de EPI não roda — **o resto do sistema funciona
normalmente** (login, câmeras, alertas manuais, papéis, exportação).

Para testar a detecção de verdade, baixe
[Hexmon/vyra-yolo-ppe-detection](https://huggingface.co/Hexmon/vyra-yolo-ppe-detection)
e salve como `models/vyra_ppe.pt`. Licença **CC-BY-4.0** — exige atribuição.

## 3. Criar as três contas

Senha mínima: **10 caracteres**. O comando pergunta a senha sem exibi-la.

```bash
flask --app wsgi users create --email supervisor@empresa.com --name "Nome do Supervisor" --role supervisor
```

```bash
flask --app wsgi users create --email tecnico@empresa.com --name "Nome do Tecnico" --role technical
```

O Operador precisa de **câmera atribuída** — sem setor ele não vê nada, por
desenho. Crie primeiro a câmera (passo 5) e depois volte aqui, ou crie sem
`--camera-id` e atribua depois pelo Supervisor:

```bash
flask --app wsgi users create --email operador@empresa.com --name "Nome do Operador" --role operator --camera-id 1
```

Conferir quem existe:

```bash
flask --app wsgi users list
```

## 4. Subir a aplicação

```bash
python run.py
```

Abra `http://localhost:5000`. Deve aparecer a **tela de login** — se aparecer o
dashboard direto, algo está errado.

---

## 5. Roteiro por perfil

### Supervisor — vê tudo, gere pessoas

| Ação | Resultado esperado |
|---|---|
| Entrar | Topbar mostra nome + "Supervisor" + botão Sair |
| Grade de câmeras | Vê **todas** as câmeras cadastradas |
| "Adicionar câmera" → USB | Detecta índices reais conectados; escolher um preenche a resolução nativa |
| "Adicionar câmera" → RTSP | Aceita `rtsp://...` digitado |
| Aba "Visão geral" | Só o Supervisor tem esse botão |
| Exportação CSV | Baixa histórico de alertas e linha do tempo |

Gestão de pessoas é por API (a tela ainda não existe):

```bash
curl -b cookie.txt http://localhost:5000/api/users
```

### Técnico — configura, não gere pessoas

| Ação | Resultado esperado |
|---|---|
| Grade de câmeras | Vê **todas** |
| Editar câmera, features, overlay, área de risco | Funciona |
| `GET /api/users` | **403** com `required_role: supervisor` |

### Operador — só o setor dele

Entre com a conta de operador **atribuída à câmera 1**:

| Ação | Resultado esperado |
|---|---|
| Tela inicial | **Kiosk** direto, sem grade nem abas |
| Lista de câmeras | Só a câmera do setor |
| Botão "Adicionar câmera" | **Não aparece** |
| Alertas | Só os da câmera dele |
| "✓ Avisei o colaborador" | Registra na linha do tempo, alerta **continua ativo** |
| "🚩 Marcar falso positivo" | Alerta é resolvido |

---

## 6. Casos de borda que vale exercitar

São os pontos onde o sistema já falhou e que agora têm comportamento definido.

### Escopo de câmera

Logado como Operador da câmera 1, tente alcançar a câmera 2 pela URL:

```bash
curl -b operador.txt http://localhost:5000/api/cameras/2
```

**Esperado: 404** — não 403. Para ele aquela câmera simplesmente não existe;
um 403 confirmaria que ela existe e que ele não pode vê-la.

Tente parar o monitoramento do outro setor:

```bash
curl -b operador.txt -X POST http://localhost:5000/api/cameras/2/stop
```

**Esperado: 404.** Era o pior caso — derrubar a vigilância de uma área alheia.

### Operador sem setor

Crie um operador **sem** `--camera-id` e entre com ele.

**Esperado:** lista de câmeras vazia, `/status` responde **403** com
`code: sem_camera_atribuida`, e a topbar mostra "sem setor — peça ao supervisor".
Ele não cai na câmera de menor id.

### Bloqueio por tentativas

Erre a senha **5 vezes** na tela de login.

**Esperado:** a partir da 6ª, mensagem de "muitas tentativas" (HTTP 429) — e
**nem a senha certa entra** durante o bloqueio. O tempo dobra a cada rodada,
até 30 min. Um login correto antes do limite zera o contador.

### Revogação de sessão

Com o Operador logado em uma aba, troque a senha dele pelo Supervisor:

```bash
flask --app wsgi users set-password --email operador@empresa.com
```

**Esperado:** o próximo clique na aba dele cai para a tela de login. Trocar a
senha derruba **todas** as sessões, inclusive um cookie que tivesse sido
copiado — é a resposta padrão a uma conta comprometida.

O mesmo vale ao **desativar** a pessoa. Já o **logout** encerra a sessão apenas
naquele navegador: sair no desktop não pode derrubar o kiosk do chão de fábrica.

### Queda de stream

Cadastre uma câmera RTSP com endereço inválido (`rtsp://192.0.2.1/x`) e inicie
o monitoramento.

**Esperado:** a topbar mostra `reconectando (tentativa N)` e depois
`sem sinal — nova tentativa em Xs`. O intervalo cresce (0,5 s → 30 s) em vez de
martelar a fonte. Se a fonte voltar, o feed volta sozinho.

Com uma câmera USB: inicie, **desconecte o cabo**, aguarde, reconecte.

### Evidência de alerta

Com detecção rodando, provoque um alerta (entre no campo sem capacete). Abra o
alerta e clique na evidência.

**Esperado:** a foto do momento aparece. Pare e inicie o monitoramento de novo,
e abra a evidência do alerta **antigo** — ela ainda deve existir. A limpeza de
startup preserva o que o histórico referencia.

### Múltiplas pessoas

Com duas pessoas no enquadramento, uma **com** capacete e outra **sem**:

**Esperado:** um único alerta, apontando a pessoa certa. Peça para as duas se
cruzarem — o alerta deve continuar seguindo a mesma pessoa, sem "resolver e
criar" a cada cruzamento.

---

## 7. Voltar ao zero

```bash
rm -rf instance runtime && flask --app wsgi db upgrade
```

Apaga banco e artefatos de execução, e recria o esquema vazio. As contas somem
junto — recrie pelo passo 3.

---

## 8. Verificação automatizada

```bash
pytest
```

```bash
ruff check .
```

```bash
npm --prefix frontend run build
```

Os três devem passar limpos (173 testes).
