# Sprint 4 — ensemble de EPI, câmera de planta real, rotação e GPU

Registro do que mudou nesta sprint e por quê. Contexto: o time saiu de testar
com webcam/quarto pra rodar contra **câmeras de verdade da planta (RTSP,
Dahua + um sensor SICK)**, e isso expôs três problemas que o cenário de teste
não mostrava — modelo fraco em óculos/luva, câmera montada física de lado, e
processamento CPU-only travando com múltiplas câmeras reais.

## 1. Ensemble de dois modelos de EPI

**Problema:** o Vyra (modelo principal, YOLOv8m) acerta capacete/colete bem,
mas óculos/luva/máscara são as classes mais fracas do dataset dele.

**Mudança:** `app/vision/ensemble_ppe_detector.py` (novo) roda o Vyra + um
segundo modelo (`Tanishjain9/yolov8n-ppe-detection-6classes`, MIT, YOLOv8n) no
mesmo frame e funde as detecções por IoU (mesmo label + caixa sobreposta =
mesma coisa, mantém a de maior confiança). `MonitorService` decide sozinho:
`PPE_EXTRA_MODELS` vazio no `.env` = comportamento antigo (um modelo só).

**Problema descoberto durante o teste:** o modelo extra (nano, dataset
pequeno) deu **"Gloves" com 0.78 de confiança numa mão NUA** levantada — o
Vyra, no mesmo frame, se absteve corretamente. Falso positivo de luva é o
pior erro possível aqui: o sistema marca uma pessoa desprotegida como
protegida.

**Correção:** `PPE_EXTRA_MODELS_EXCLUDE_LABELS=gloves` — a classe "gloves"
some da saída do(s) modelo(s) extra(s) e fica só a cargo do Vyra (mais
conservador, recall menor mas sem alucinação). Implementado traduzindo
label→id de classe *daquele peso especifico* em `MonitorService.__init__`.

## 2. Falso positivo em objeto de fundo

**Problema:** com o piso de confiança baixo (necessário pra pegar óculos/luva
fracos), capacete/luva passaram a disparar em mochila, pano amarelo, objeto
qualquer no fundo da cena — nada a ver com uma pessoa.

**Correção**, dois filtros novos em `CameraWorker._gate_ppe_to_people`:
- **Piso de confiança por classe** (`PPE_CONF_MIN_BY_CLASS`): capacete/colete
  exigem 0.40 (a detecção errada tinha só 0.27-0.40), luva/máscara 0.30,
  óculos fica permissivo em 0.15 porque é a classe mais fraca.
- **Sobreposição obrigatória com pessoa** (`PPE_REQUIRE_PERSON_OVERLAP` +
  `PPE_PERSON_OVERLAP_MIN=0.35`): a caixa do EPI só conta se cair dentro de
  uma pessoa detectada. Mata detecção solta no fundo sem precisar confiar só
  no piso de confiança.

## 3. Rotação de câmera

**Problema:** uma das câmeras da planta (Fresa 2) está fisicamente montada de
lado — confirmado capturando um frame real e comparando as duas rotações
possíveis lado a lado. Isso quebra o MediaPipe Pose (assume corpo vertical) e
a heurística de "pessoa caída" (`torso_orientation`), que passa a disparar em
qualquer pessoa em pé numa câmera rotacionada.

**Mudança:**
- `Camera.rotation` (novo campo, migração `cb34b695d668_rotacao_por_camera`,
  0/90/180/270, default 0)
- `CameraWorker._aplicar_rotacao()` corrige o frame **logo após a captura,
  antes de qualquer detecção** — YOLO, Pose, overlay e o vídeo mostrado na
  tela veem a mesma imagem já corrigida, nunca a torta
- Editável em runtime via `PUT /api/cameras/:id {"rotation": 90}`, no
  cadastro (`cameras add --rotacao 90`), e agora também **pela interface**
  (painel "Configurar" da câmera, campo "Orientação da câmera")

## 4. GPU (CUDA) — opcional, fora do `requirements.txt`

A máquina de teste tem uma NVIDIA RTX 5070, mas o `torch` que o
`requirements.txt` instala é CPU-only de propósito (funciona em qualquer
máquina, sem exigir GPU nem driver CUDA pra clonar e rodar). Quem tiver GPU
NVIDIA e quiser acelerar:

```bash
pip uninstall torch torchvision
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
```

Depois, no `.env`:
```
YOLO_DEVICE=0
YOLO_HALF=true
```

Medido nesta sprint: Vyra caiu de **131ms/frame (CPU) pra ~15ms (GPU)** — mais
de 100x. `YOLO_HALF` (FP16) foi testado e **não deu ganho medível** nesta GPU
(o gargalo real não é o YOLO — ver próximo item), mas fica ligado por ser
prática padrão em inferência e não ter custo.

**Novo `YOLO_HALF`** em `app/vision/yolo_ppe_detector.py` e `app/config.py`:
só tem efeito com `YOLO_DEVICE` apontando pra GPU — em CPU o detector ignora
sozinho (a maioria dos kernels de CPU não tem caminho FP16 otimizado).

## 5. Por que "ligar a GPU" não resolveu a fluidez sozinho

Perfilamos o loop por frame (`PROFILE_FRAMES` no `.env`, já existia) e o
gargalo real **não é o YOLO** — é:

| Etapa | Custo medido |
|---|---|
| Pose (MediaPipe, sempre CPU) | ~100-140ms |
| Gravação de alerta (commit no banco) | ~40-90ms |
| Encode do vídeo (JPEG) | ~35-55ms |
| YOLO (GPU) | ~15-35ms |

GPU não acelera o MediaPipe Pose. As mudanças que atacam isso de verdade:
- `POSE_MAX_PEOPLE`: 4 → **2** (menos gente processada por frame = mais fps)
- `YOLO_IMGSZ`: 416 → **960** (quase de graça na GPU agora, melhora muito
  detecção de gente/EPI longe da câmera — o problema real de câmera de
  planta)
- `DETECTION_EVERY_N_FRAMES` foi testado em **1** (detecta todo frame) e
  **revertido pra 3**: com tudo rodando a cada frame, o loop ficou lento o
  bastante pra fonte RTSP perder referência de frame-chave e o vídeo saiu
  com um efeito fantasma/duplicado (corrupção de decode, não bug nosso).

## 6. Rede da planta — fora do nosso controle

Medido com `ping` direto nos IPs das câmeras:

| Câmera | Situação |
|---|---|
| Fresa 1 (10.14.22.97) | 13-96ms, 0% perda — ok |
| Fresa 2 (10.14.22.98) | 23-**214ms**, jitter grande |
| SICK (10.14.22.96) | 48-**284ms**, jitter grande |
| Tenda (10.14.22.99) | **16% de pacote perdido**, roteador intermediário (`10.14.22.248`) recusando |
| Sala 4 (10.14.24.6) | **100% perdido**, sem rota desta máquina |

Isso é infraestrutura de rede da planta, não nosso pipeline. Nenhuma
otimização de software resolve 200ms de jitter ou pacote perdido antes de
chegar na câmera.

## 7. Câmera IP real — SICK Visionary-B Two

Cadastrada, mas **não faz sentido rodar o pipeline de EPI nela**: é um sensor
3D dedicado de segurança (Time-of-Flight) com a própria análise de distância
e zona de perigo já embutida no stream (os retângulos verde/amarelo/vermelho
com metros vêm do sensor, não do nosso YOLO). Cadastrada só pra referência.

## 8. Correção de isolamento de teste

`TestConfig` não zerava `RTSP_USUARIO`/`RTSP_SENHA` como já fazia com
`LLM_ENABLED`, então configurar a credencial real da planta no `.env` (pra
cadastrar as câmeras Dahua) quebrava
`test_add_recusa_host_sem_credencial_configurada` — o teste assumia os dois
vazios. Corrigido em `app/config.py` seguindo o padrão que já existia pro LLM.

## 9. Pesquisa de modelos e datasets

`docs/PESQUISA-MODELOS-DATASETS.md` (novo) — levantamento de modelos/datasets
de EPI com mais classes que o Vyra (SH17, Roboflow Safety_PPE, Construction
Site Safety, etc.) e bases correlatas de segurança industrial (fogo/fumaça,
objetos de canteiro, comportamento inseguro). Referência pra evolução futura,
não implementado nesta sprint.

---

## Novas variáveis de ambiente

| Variável | Default | O que faz |
|---|---|---|
| `PPE_EXTRA_MODELS` | (vazio) | Modelos de EPI extras, fundidos com o principal (ensemble) |
| `PPE_EXTRA_MODELS_IMGSZ` | 960 | Resolução de entrada dos extras |
| `PPE_EXTRA_MODELS_AUGMENT` | true | TTA nos extras (+recall, ~2x custo) |
| `PPE_EXTRA_MODELS_EXCLUDE_LABELS` | `gloves` | Classes que nenhum extra pode contribuir |
| `PPE_CONF_MIN_BY_CLASS` | `helmet:0.40,vest:0.40,gloves:0.30,mask:0.30,glasses:0.15` | Piso de confiança por classe |
| `PPE_REQUIRE_PERSON_OVERLAP` | true | EPI só conta se cair dentro de uma pessoa |
| `PPE_PERSON_OVERLAP_MIN` | 0.35 | Containment mínimo pra contar |
| `YOLO_HALF` | true | FP16 na GPU (ignorado em CPU) |

## Migração de banco

`cb34b695d668_rotacao_por_camera.py` — coluna `cameras.rotation` (int,
default 0). Rodar `flask --app wsgi db upgrade`.

## Arquivos novos

- `app/vision/ensemble_ppe_detector.py`
- `docs/PESQUISA-MODELOS-DATASETS.md`
- `docs/SPRINT4.md` (este arquivo)
- `migrations/versions/cb34b695d668_rotacao_por_camera.py`
