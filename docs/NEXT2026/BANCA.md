# BANCA — as 15 perguntas mais difíceis

Respostas curtas, sustentadas por números medidos neste repositório. Onde o
número veio de uma máquina saturada, a resposta diz isso. Fontes:
`docs/NEXT2026/BENCHMARKS.md`, `docs/NEXT2026/CHANGELOG.md`, `bench/results/`.

## Desempenho

**1. "Isso roda em tempo real num computador comum?"**
O vídeo, sim: ele é publicado a 7–8 quadros/s por câmera, com a análise
desacoplada da exibição. A análise, não a cada quadro: no perfil "batata" (2
núcleos de eficiência, sem GPU dedicada), com a iGPU Intel, são **1,44
análises/s em 1 câmera e 0,34 por câmera em 4** (mediana de 3 repetições). O
alerta de "sem capacete" chega à tela em **1,9 s** (1 câmera) e **3,2 s** (4
câmeras), contados a partir do primeiro quadro com a violação. Antes da missão,
era **38 s** em 1 câmera, e em 4 câmeras nenhum alerta saía em 91 s.
Ressalva: a máquina tinha 13–42 % de CPU de terceiros durante as rodadas, então
os números de relógio são indicativos.

**2. "Como vocês sabem que a otimização não piorou a detecção?"**
Toda troca de runtime passa por um guarda: concordância por classe, IoU ≥ 0,5,
contra o mesmo peso em PyTorch@640. O mínimo é **97 %**; o OpenVINO na iGPU
(FP32) deu **100 %** no EPI, na pessoa e na pose (no esqueleto, erro de
keypoint p95 = 0,0 em 459 pares). Quando o guarda reprova, a troca não entra: o
INT8 e o imgsz 416/512 ficaram de fora assim. Ver `scripts/concordancia.py`.

**3. "E se a máquina não tiver GPU Intel?"**
O resolvedor de runtime pula para ONNX, e o Diagnóstico mostra qual runtime e
qual dispositivo estão rodando. Se a GPU não compila o modelo, ele cai para a
CPU sozinho e o Diagnóstico mostra "CPU (fallback da GPU)". O PR2 cortou o
CPU-ms por análise em ~70 % em relação ao PR1 (ONNX), medido pelo CPU do
processo e não pelo relógio: de 4.110 para 1.197 ms em 1 câmera.

## Detecção e honestidade

**4. "Seu modelo vê luva e calçado? E máscara?"**
O Vyra (CC-BY-4.0) tem as classes. Na tela, cada EPI aparece como detectado,
ausente, "não suportado pelo modelo" ou "não verificável neste enquadramento"
(portal) — e não detectado não é tratado como ausente quando a parte do corpo
não está no quadro.

**5. "Quantos falsos alarmes?"**
Ainda é o ponto fraco, e o número é este: no servidor do E2E (4 gravações em
loop), ~1.000 alertas em 16 min. A causa é ter 5 alertas por pessoa (um por
EPI) e um conjunto novo a cada troca de ID do rastreador numa multidão. A
histerese segura o falso positivo de um quadro só (cria com 8 quadros OU 2 s
com ≥ 2 confirmações; resolve com 20 OU 6 s com ≥ 3). O botão "Falso positivo"
grava a marca, e o relatório conta quantos foram marcados.

**6. "Queda: e se o modelo errar?"**
Queda é emergência e é breve no vídeo. Medimos a 4 análises/s: na gravação de
queda, a classe aparece em sequência (até 4 análises seguidas); nas gravações
sem queda, só isolada (0 pares seguidos em 93 análises). Por isso a regra de
emergência pede 2 análises seguidas, e não 8. A amostra é pequena (3
gravações), e o risco de falso alarme numa planta real está registrado.

## Gamificação

**7. "Gamificar segurança não incentiva esconder acidente?"**
É o maior risco, e o desenho o evita:
- só se premia indicador **positivo**: minuto conforme com gente na câmera,
  check-in no portal, alerta reconhecido, rótulo revisado;
- **nunca** se premia "zero alertas": minuto sem ninguém é neutro;
- quem gera ou reporta alerta nunca perde ponto;
- não há ranking por pessoa nem por ID: tudo é por setor (Modo TV);
- a conquista "todos os alertas críticos reconhecidos" exige ter havido alerta
  reconhecido.

**8. "E o 'Você vs. a IA'?"**
O gabarito foi curado à mão (GABARITO.md), com a mesma regra de pontuação para
a pessoa e para a IA. O placar mostra quando a IA erra, e duas das três
rodadas são "pegadinha" (ninguém sem capacete). O apelido é opcional e não vai
ao banco.

## LGPD e privacidade

**9. "Vocês identificam trabalhadores?"**
Não:
- não há reconhecimento facial nem nome ligado a ID;
- "Pessoa 7" é um número de rastreio por posição, que muda quando a pessoa sai
  do quadro;
- o rosto sai desfocado em tudo que deixa o servidor (vídeo, replay,
  evidência, recortes do aprendizado ativo), e só o supervisor desliga o
  desfoque — a ação fica registrada e aparece no relatório.

**10. "E os recortes para treinar o modelo?"**
Saem do quadro com olhos e nariz desfocados. Sem keypoints de rosto, o recorte
não é feito. Com a privacidade ligada, óculos, máscara e protetor auricular nem
entram na fila, porque só se veem no rosto. O zip exporta apenas os
confirmados, com um README de origem e licença.

**11. "Base legal?"**
O sistema trata imagem para segurança do trabalho; quem implanta precisa de
base legal e transparência com os trabalhadores (fora do escopo do software).
O software ajuda com minimização: desfoque por padrão, sem identidade, replay
curto (8 s) gravado já desfocado, nada é gravado no portal, e as evidências têm limpeza
configurável.

## NR e conformidade

**12. "Isso substitui a inspeção da NR-6?"**
Não. O relatório liga cada infração ao item **literal** da NR-6 (6.5.1 e;
6.6.1 a; Anexo I A.1, B.1, C.1, F.1, G.1), lido no gov.br. Colete de alta
visibilidade e máscara ficam como "sem item sustentado pelo texto", com o
motivo. É indicação do requisito relacionado, não parecer.

**13. "E ergonomia — é NR-17?"**
Não afirmamos. É uma estimativa por pose 2D (flexão do tronco acima de 45°/60°
por tempo), e o alerta diz "estimativa; não é RULA, REBA nem NR-17".

## Licenças e dependências

**14. "Posso vender isso?"**
Cada modelo e gravação aparece com a licença na tela Sobre e em
`ATRIBUICOES.md`:
- Vyra: CC-BY-4.0, exige atribuição;
- YOLOv8n e YOLO11n-pose: AGPL-3.0 (Ultralytics), o que importa para
  distribuição comercial;
- descartamos o YOLOE/MobileCLIP porque a licença do MobileCLIP é só para
  pesquisa.

## Demo

**15. "E se algo falhar na demo?"**
Cada momento do roteiro passou no E2E. O `flask demo reset` volta tudo em
menos de 10 s, e o DEMO.md tem um plano B por falha (webcam ausente, câmera
caindo, sem internet). A demo é offline: LLM desligado, gravações locais e
banco isolado.
