# VisionEPI — Relatório Técnico: Fase 2 — Pose Estimation

**Challenge 2026 — Innovation Challenge CUP — Parceria FIAP × SPI**
Engenharia da Computação, 3º ano. Entrega: 22/06/2026.

## Equipe

Lucas Baraldi Rodrigues · Lucas Zolla Assis · Pedro Costa Belisário · Vitor Pantarotto de Brito
Professor: Fabio Henrique Pimentel · Mentores SPI: Fernando Marcolina, Wendel de Almeida Passos

---

## 1. Escopo desta fase

Pose estimation funcional integrada ao pipeline da Fase 1. Classificação de pelo menos
três categorias de postura: ergonomicamente inadequada, de risco imediato e de
aproximação a zona crítica. Demo funcional em vídeo. Métricas: PCK, acurácia de
classificação e recall em postura de risco.

## 2. O que foi construído

Pose por pessoa (**MediaPipe Pose**), integrada ao **mesmo pipeline e ao mesmo quadro**
da Fase 1 — sem recodificar a imagem, sem stream separado. O rastreador de pessoas da
Fase 1 também identifica de quem é cada pose: um alerta de queda já sai atribuído a
"Pessoa 3", não a um evento global sem dono (limitação da versão anterior, corrigida
nesta fase).

**As três categorias exigidas pelo escopo, implementadas exatamente como pedido:**

| Categoria | Como é detectada | Severidade |
|---|---|---|
| **Risco imediato** (queda) | Orientação do torso (vetor ombro→quadril) mais horizontal que vertical, medido em **pixels** do frame (não em coordenadas normalizadas — evita que o mesmo limiar signifique coisas diferentes em pessoa perto/longe da câmera) | Crítica |
| **Ergonomicamente inadequada** (postura suspeita) | Cabeça projetada à frente do eixo dos ombros, em **fração da altura do próprio torso da pessoa** (não do frame) | Média |
| **Aproximação a zona crítica** | Centro da caixa da pessoa dentro do polígono de risco, configurável por câmera, desenhado diretamente no vídeo pelo supervisor/técnico | Alta |

## 3. Métricas

- **PCK (Percentage of Correct Keypoints): não medido.** Exigiria um conjunto de
  imagens com a posição real de cada articulação marcada manualmente — não existe no
  projeto e não havia tempo hábil de construir um até esta entrega. O MediaPipe Pose é
  um modelo de terceiros, não treinado pela equipe; a acurácia publicada pelo próprio
  fabricante (Google) é a referência válida para esse número específico, já que mede a
  qualidade do modelo de pose em si, não da nossa integração.
- **Verificação da lógica de classificação:** 19 testes automatizados (`pytest`) cobrem
  os três cenários com geometria de referência conhecida — pessoa em pé, pessoa caída,
  postura inclinada, dentro/fora da zona de risco, inclusive com duas pessoas na cena
  simultaneamente. **100% de acerto** nos casos controlados. Isso comprova que a lógica
  de decisão está correta; não substitui uma medição de recall em cenas reais e
  variadas, que depende de imagens ou vídeos rotulados que o projeto não possui.
- **Recall em postura de risco (cena real):** não medido de forma automática, pela
  mesma razão. Fica registrado como próximo passo um teste ao vivo estruturado (pessoa
  em pé, caindo com segurança, postura ruim, entrando na zona), com os resultados
  anotados manualmente.

## 4. Integração com a Fase 1

- Mesmo `CameraWorker`, mesmo lock de inferência, sem duplicar o custo de captura.
- O `PersonTracker` da Fase 1 dá o `track_id` que a pose usa para dizer de quem é o
  alerta.
- Generalização: a pose não depende de vídeo de treino específico — é avaliada ao vivo,
  contra webcam e contra câmeras da planta real (não só contra vídeos gravados de
  demonstração), o que a Fase 4 confirma funcionando.

## 5. Inovações desta fase

- Pose **por pessoa**, não uma pose global por frame (limitação corrigida nesta fase).
- Geometria em pixels e em fração do torso da própria pessoa, não em coordenadas
  normalizadas do frame — evita que o mesmo limiar acerte para uma pessoa e erre para
  outra só por estar mais perto ou mais longe da câmera.
- As três categorias do escopo mínimo, todas com severidade e mensagem próprias, já
  integradas ao mesmo sistema de alertas da Fase 3.

## 6. Entregáveis desta fase

- [x] Pose estimation funcional, integrada à Fase 1
- [x] 3 categorias mínimas classificadas
- [x] Demo funcional em vídeo
- [x] Integração com Fase 1 (mesmo stream)
- [~] Métricas: PCK não medido (limitação declarada, §3); lógica de classificação
      verificada por 19 testes automatizados
- [x] Relatório técnico (este documento)
