# Glossário de texto do VisionEPI

Um termo por conceito, em toda tela, mensagem de erro, linha do tempo, relatório
e CSV. Vale para tudo que o usuário lê. Não vale para `logger.*`, comentários e
nomes de código (chaves de API, props, rotas, `data-testid`): esses ficam como
estão.

Escolha feita pelo que já predominava no código (`frontend/src`, `app/`): o
termo da coluna 1 aparece muito mais vezes que os da coluna 3.

## Termos oficiais

| Termo oficial | Definição curta | Evitar |
|---|---|---|
| **Incidente** | Alertas agrupados por regra e zona (três pessoas sem capacete na Zona A são um incidente). É o que a tela principal lista. | ocorrência, evento (reservado à linha do tempo), caso, ticket |
| **Alerta** | Um registro individual de regra violada, por pessoa. Vários alertas formam um incidente. | notificação (exceto a do navegador), aviso (reservado a "avisei"), anomalia |
| **Reconhecer** | Ação humana sobre um **incidente**: "vi isto". Mede o tempo até a resposta. | confirmar, tratar, dar ciência, acknowledge |
| **Avisei o colaborador** | Ação humana sobre um **alerta**: registra que a pessoa foi avisada. Na TV e na linha do tempo: "colaborador avisado". | tratado, reconhecido (para alerta), acknowledged |
| **Resolver / resolvido** | Alerta encerrado: a violação parou ou alguém o encerrou ("Resolver todos"). Nada é apagado. | encerrar, fechar, dispensar, baixar |
| **Apagar** | Remoção definitiva de dado. Sempre com confirmação. | excluir, deletar, remover (remover = tirar a câmera do cadastro) |
| **Confirmado** | O **sistema** validou a condição por análises seguidas (histerese, item do portal). Nunca para ação humana. | reconhecido, aprovado (para o sistema) |
| **Falso positivo** | Alerta que a pessoa marcou como errado. | falso alarme, erro de detecção |
| **Câmera** | A fonte de vídeo cadastrada: cartão da grade, lista lateral, configuração. | setor (para uma câmera só), feed, stream |
| **Setor** | Área ou equipe da planta que agrupa câmeras: Visão geral, Modo TV, Liga de Setores, "câmera do setor" do Operador. Pontuação e metas são por setor, nunca por pessoa. | usar "setor" como nome de cartão de câmera |
| **Pessoa N** | Número de rastreio por posição. Não identifica ninguém. | funcionário, trabalhador, ID de pessoa, nome |
| **Colaborador** | Quem recebe o aviso do alerta ("Avisei o colaborador"). | funcionário, trabalhador |
| **EPI** | Equipamento de proteção individual. Rótulos: Capacete, Colete, Luvas, Óculos, Máscara, Calçado, Protetor auricular. | PPE, helmet, vest, gloves (chaves de API nunca aparecem) |
| **Sem capacete** (ausência) | Classe negativa do modelo: a pessoa foi vista sem o EPI. Escrita "Sem capacete", "Sem colete"… | no_helmet, ausente (isolado), faltando (só no Portal) |
| **Recurso** | Cada detecção que se liga ou desliga numa câmera (Capacete, Pose, Quedas…). A barra lateral se chama "Recursos". Perfil = conjunto de recursos (Básico, EPI, Risco, Completo). | feature, função, módulo |
| **Área de risco** | O polígono desenhado na câmera onde a presença gera alerta. | região de risco, zona de perigo |
| **Zona** | O nome dessa região num incidente ("Zona A", "Fora da zona"). | usar como sinônimo de câmera |
| **Quadro** | Uma imagem do vídeo. | frame |
| **Imagem** | O que a câmera entrega ("sem imagem", "receber a imagem"). | feed |
| **Gravação de demonstração** | Vídeo gravado no lugar de câmera ao vivo. Na tela: "Gravação" ou "Fonte de demonstração". | fixture, modo fixture, mock |
| **Imagem de evidência** | O quadro guardado quando o alerta nasce, com SHA-256 na cadeia de custódia. | snapshot |
| **Replay** | Os quadros gravados de 5 s antes a 3 s depois do alerta. | clipe (só no código), vídeo do alerta |
| **Linha causal** | O que aconteceu com um ID de rastreio dentro de um incidente. | timeline causal |
| **Linha do tempo** | Eventos do sistema, em ordem. | timeline, log |
| **Registros** | Histórico de erros da câmera. | logs, log de erros |
| **Rótulo** | Classe confirmada por uma pessoa numa imagem recortada (aprendizado ativo). | label |
| **Camadas do vídeo** | O que se desenha sobre a imagem: caixas, rótulos, confiança, pose, zona. | overlay, bounding box |
| **Portaria** | Modo da câmera que libera ou nega a entrada por EPI. | gate |
| **Portal de Entrada** | A tela de check-in dessa câmera. | portal (sozinho), gate |
| **Tipo de conta** | Operador, Técnico ou Supervisor. | papel, perfil, role |
| **Operador / Técnico / Supervisor** | Os três tipos de conta, nesta capitalização. | usuário comum, admin |
| **Tendência de risco** | Frequência recente de alertas por categoria. Estatística, não previsão. | score de risco (só no código) |
| **Cartão** | Cada card da Retrospectiva. | card, story |
| **Pontos de experiência** | Pontuação da planta na Liga (nível). | XP |

## Formato

- **Plural com a contagem certa**, nunca "(s)": "1 alerta", "2 alertas"; "1
  recorte confirmado", "2 recortes confirmados". No frontend use `pluralizar` de
  `frontend/src/utils/formato.ts`; no backend, `pluralizar` de
  `app/utils/texto.py` (mesma regra).
- **Número decimal com vírgula**: "1,5 s", "0,35", "87,3%". No frontend, `decimal`
  de `frontend/src/utils/formato.ts`; no backend, `.replace(".", ",")` na
  mensagem. Milhar com ponto ("1.234 análises").
- **Hora em pt-BR, 24 h**: `horaCurta`, `horaCompleta` e `dataHoraCurta` de
  `frontend/src/utils/datas.ts`. Não chame `toLocaleTimeString([])`: ele segue o
  idioma do navegador.
- **Unidade separada por espaço**: "30 s", "12 fps", "24 h", "5 m". Não "30s".
- **Erro**: "Falha ao <verbo>." (ex.: "Falha ao salvar a câmera."). Sem rede:
  "Sem conexão com o servidor." (`mensagemDeErro` em
  `frontend/src/utils/erros.ts`; o texto nativo do navegador vem em inglês).
  Nunca mostrar "HTTP 500", `str(exc)` de exceção Python sem necessidade, nomes de
  campo da API ("'name' é obrigatório") nem rotas ("POST /api/...").
- **Chave crua nunca aparece**: classe do modelo, recurso, severidade, situação
  e regra passam por mapa de rótulos. Os mapas ficam em `frontend/src/api/ppe.ts`
  (`ROTULOS_DE_CLASSE`, `ROTULOS_DE_RECURSO`, `ROTULOS_DE_SEVERIDADE`,
  `ROTULOS_DE_SITUACAO`; EPI em `PPE_LABELS`) e, no backend, em
  `app/vision/person_compliance_matcher.py` (`PPE_LABELS`) e
  `app/vision/annotator.py` (`FrameAnnotator.rotulo_pt`). Não crie outro mapa:
  estenda estes.
- **Sem texto provisório visível**: nada de "TODO", "em construção", "lorem" ou
  "em breve". Se a função não existe, o texto diz o que o usuário pode fazer.

## Siglas e palavras que ficam como estão

Nomes próprios e termos sem tradução corrente em português do Brasil: EPI, YOLO,
MediaPipe, ONNX, OpenVINO, PyTorch, RTSP, USB, HTTPS, QR code, SHA-256, FPS, JPEG,
PNG, CSV, NR-6, LGPD, LLM, Raio-X, Wi-Fi, check-in, checklist, webcam, "p50/p95"
(percentis) e os títulos originais de obras na tela "Sobre". Variáveis de
ambiente e comandos que o Técnico precisa digitar (`LLM_ENABLED`,
`python run.py --https`) aparecem só onde são a instrução para corrigir.

## Como conferir

```
rg -n "\(s\)|Failed to|Loading|HTTP \$\{|toFixed\(" frontend/src --glob "!vendor/**"
rg -n "\(s\)|feature|frame|snapshot" app --glob "*.py"   # só nas strings visíveis
```

Mensagens de `logger.*` e comentários podem ter inglês e termos técnicos: não são
copy de interface.
