# BANCA: as perguntas mais difíceis

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

**5. "Quantos falsos alarmes? A tela não vira uma árvore de Natal?"**
Era o ponto fraco: um alerta por EPI por pessoa, e um conjunto novo a cada
troca de ID. Na MISSÃO 2 o painel passou a mostrar **incidentes** por (câmera,
regra, zona), com os IDs envolvidos, e um track novo que surge perto de onde
outro sumiu, em até 2 s, herda o ID. Medido na gravação da multidão com os 7
EPIs ligados (150 s, servidor real): antes, até **64 alertas** ao mesmo tempo
no painel; depois, no máximo **11 incidentes**, **1 por regra e zona**. O
alerta por pessoa continua existindo como evidência (replay, custódia). A
histerese segura o falso positivo de um quadro só, e o botão "Falso positivo"
grava a marca.

**6. "Queda: e se o modelo errar?"**
Queda é emergência e é breve no vídeo. Medimos a 4 análises/s: na gravação de
queda, a classe aparece em sequência (até 4 análises seguidas); nas gravações
sem queda, só isolada (0 pares seguidos em 93 análises). Por isso a regra de
emergência pede 2 análises seguidas, e não 8. A amostra é pequena (3
gravações), e o risco de falso alarme numa planta real está registrado.
Limite medido: na gravação a pessoa fica ~0,8 s no chão; com o vídeo aberto em
tempo real e 4 câmeras numa máquina carregada, duas análises não cabem nisso.
Não afrouxamos a regra (um falso positivo da `multidao` chegou a 0,84 num
quadro só): no palco, a gravação da queda toca a 0,25×, com o rótulo na tela
(ver a pergunta 21). Numa câmera real, quem cai fica no chão bem mais que 0,8 s.

## Gamificação

**7. "Gamificar segurança não incentiva esconder acidente?"**
É o maior risco, e o desenho o evita:
- só se premia indicador **positivo**: minuto conforme com gente na câmera,
  check-in no portal, alerta reconhecido, rótulo revisado;
- **nunca** se premia "zero alertas": minuto sem ninguém é neutro;
- quem gera ou reporta alerta nunca perde ponto;
- não há ranking por pessoa nem por ID: tudo é por setor (Modo TV);
- a conquista "todos os alertas críticos tiveram o colaborador avisado" exige
  ter havido alerta com colaborador avisado.

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

**"Quanto tempo a pessoa espera no Portal até 'Liberado'?"**
Medido com o E2E repetido 10 vezes, as 4 câmeras ligadas e a gravação de um
trabalhador de capacete e colete de perto (`portal.mp4`): na cena do Portal do
palco, **p50 3,5 s e p95 5,9 s**; fora do palco, com as 4 câmeras analisando ao
mesmo tempo, **p50 13,4 s e p95 24,2 s**. A diferença é de propósito e é
honesta: no palco, a cena pausa as outras câmeras ("pausada pela
apresentação"), como um portal de verdade teria a sua própria máquina. O que
segura o tempo é o modelo: ele vê o capacete em ~64 % dos quadros desse vídeo,
e uma análise que vê a pessoa SEM o capacete zera a confirmação — liberar por
engano é o erro caro, então não afrouxamos isso para ganhar segundos. Antes de
uma correção achada na própria medição (quadros velhos das câmeras pausadas
passavam na frente), o palco dava p50 7,3 s e p95 13,9 s.

**15. "E se algo falhar na demo?"**
Cada momento do roteiro passou no E2E. O `flask demo reset` volta tudo em
menos de 10 s, e o DEMO.md tem um plano B por falha (webcam ausente, câmera
caindo, sem internet). A demo é offline: LLM desligado, gravações locais e
banco isolado.


## Funcionalidades da MISSÃO 2

**16. "Pontos e níveis não viram pressão para esconder problema?"**
A Liga só soma, e só por setor: check-in no portal (10), incidente reconhecido
em até 1 min (15) ou 3 min (5), falso positivo revisado (5), rótulo
contribuído (2), minuto conforme com gente na câmera (1). Não existe ponto
negativo, "zero alertas" não vale nada e reportar um alerta nunca custa ponto.
As missões são da equipe, configuradas pelo supervisor. A celebração é um
confete de 1,4 s e três notas baixas, desligados pelo mudo e por
`prefers-reduced-motion`. Regras e testes: `app/services/liga.py`,
`tests/test_liga.py`.

**17. "Essa cadeia de custódia vale como prova?"**
Ela prova que nada mudou depois de entrar na cadeia: cada evidência (alerta,
quadro, replay, troca de privacidade) tem um SHA-256 do conteúdo encadeado ao
elo anterior, e a verificação aponta o primeiro elo que não fecha. O teste
adultera 1 byte de um JPEG do replay e a verificação aponta exatamente aquele
elo e aquele arquivo. Limite honesto: sem âncora externa, quem tem acesso de
escrita ao banco e ao disco pode refazer a cadeia inteira. Por isso a tela
mostra o hash do último elo para anotar no relatório do turno (âncora fora do
sistema). Não é carimbo de tempo de autoridade certificadora.

**18. "O simulador 'E se?' reroda o modelo?"**
Não. Ele reprocessa as **trilhas** que o sistema gravou (posição dos pés, ID e
estado de cada EPI a cada análise, sem imagem) com outra zona, outra histerese
ou outros EPIs, usando a mesma lógica de histerese do serviço de alertas. É
determinístico e nunca toca em alerta real. A prova de que ele simula a mesma
coisa: com a regra de hoje, ele reproduz os alertas reais (21 de 21, 16 de 16
por regra numa janela de 5 min da demo). Limite: o que o modelo não viu na
época, o simulador também não vê.

**19. "O 3D é só enfeite?"**
É a planta de verdade alimentada pela homografia da calibração (4 cliques no
chão do vídeo e 4 na planta): cada pessoa aparece onde o pé dela está, na cor
do estado (conforme, sem EPI, na zona, possível queda), nunca como foto. Clicar
na pessoa abre a linha do tempo e o replay; clicar na zona, o histórico de
entradas. Sem WebGL, cai para a planta 2D. Medido com a GPU da máquina e as 4
câmeras inferindo: 16,7 ms por quadro no p95 (60 fps). Na demo, as três
gravações são de lugares diferentes; a calibração delas numa planta só é uma
aproximação de demonstração.

**20. "E se a IA for enganada com um boné?"**
É uma cena da apresentação: o visitante declara a tentativa, fica diante da
câmera com o Raio-X ligado e o sistema mostra o que viu e por quê ("o modelo viu com 0,31 (abaixo do piso 0,40) e descartou"). O placar da sessão conta quantas
vezes a IA foi enganada, sem esconder. Cada caso desses é o que alimenta a
fila de rótulos.

**21. "Vocês detectam uma queda que dura menos de 1 segundo ao vivo?"**
Nesta máquina, não com confiança — e por isso a demo mostra a gravação a
0,25×, com "GRAVAÇÃO · 0,25×" escrito sobre o vídeo. Os números (14/10, 4
câmeras ligadas, notebook sem GPU dedicada, com outros programas rodando):
2,4–2,8 análises por segundo no total; a câmera que está na tela leva 43–49 %
delas (~1,1–1,3 análise/s), as outras ~0,45/s cada. Na gravação de
demonstração a pessoa fica **~0,8 s no chão** (6,2–7,0 s do clipe). A regra de
emergência pede **2 análises seguidas** vendo a queda (um quadro sozinho já deu
falso positivo com 0,84 numa gravação sem queda), e a primeira análise leva ~1 s
para voltar — em tempo real cabe no máximo uma análise nesses 0,8 s. A 0,25×
os 0,8 s viram ~3,2 s, cabem 3–4 análises, e o alerta sai ao vivo (medido no
E2E: 12,9 s depois de entrar na cena, contando a gravação até a queda). O que
melhoraria: mais análises por segundo por câmera — GPU dedicada, menos
câmeras por máquina ou um modelo menor para a câmera de risco — sem afrouxar a
regra. E numa planta de verdade quem cai fica no chão bem mais que 0,8 s; o
caso difícil é a gravação, não o acidente.

## Funcionalidades da MISSÃO 4

**22. "Isso conversa com o CLP/SCADA da fábrica?"**
Sim, por padrão aberto: um servidor OPC UA (nó `Planta.PlantaEmAlarme`, `Planta.Torre` e, por câmera, estado,
conformidade, último alerta e incidentes ativos por regra), MQTT (`visionepi/planta/estado` retido e
`visionepi/<camera>/alerta`) e webhook HTTP. Na demo, o OPC UA e um broker MQTT embutido sobem em 127.0.0.1, sem
internet. Testado com clientes OPC UA e MQTT reais lendo o alarme. Limite honesto: o OPC UA sobe sem criptografia
(NoSecurity) e só aceita leitura anônima — para produção, política com certificado e broker da planta com TLS
(`docs/NEXT2026/INTEGRACAO.md`).

**23. "E se alguém tapar ou virar a câmera?"**
A saúde visual compara, uma vez por segundo, uma miniatura do quadro com a referência da câmera: imagem lisa
(obstruída), escura, ofuscada, sem nitidez (desfocada) ou enquadramento mudado (movida). Cada estado precisa de 3 s
seguidos para confirmar e 3 s de normalidade para liberar. Medido no E2E com a câmera de rede tampada no meio do teste:
3,8 s até "OBSTRUÍDA" e 9,9 s até o alerta. Limite: "movida" só dispara com evidência geométrica; com a cena muito
renovada desde a referência, fica inconclusiva (nunca alarme falso) — o técnico redefine a referência.

**24. "Como funciona a evacuação? Vocês contam pessoas?"**
Cada câmera conta quantas pessoas vê agora; o painel soma, mostra a última posição vista na planta e o pico no ponto
de encontro, com cronômetro. O aviso fica sempre na tela: contagem por câmera — pode haver dupla contagem se as
câmeras se sobrepõem. Não identifica ninguém: o número ao lado do ponto é rótulo de rastreio. Ao encerrar, o relatório
entra na cadeia de custódia.

**25. "Dá para criar regra sem programar?"**
Sim: blocos de condição (zona, EPI presente/ausente, duração, postura, aproximação, horário, permissão ativa)
combinados com E/OU, e ações (severidade, fala, integração, escalonamento). A regra compila para o MESMO motor das
regras nativas — não existe um segundo caminho. Antes de ativar, "testar no histórico" reprocessa as trilhas gravadas
e diz quantas vezes teria disparado; postura e aproximação não ficam nas trilhas, e a tela diz isso em vez de inventar.
As 17 regras nativas reescritas no editor geram exatamente os mesmos alertas (teste de equivalência).

**26. "E a NR-33 (espaço confinado) e a NR-35 (altura)?"**
A permissão de trabalho digital registra zona, janela, responsável, EPIs e se exige vigia. Pessoa no espaço confinado
sem ninguém na área de vigia gera alerta crítico; entrar fora da janela gera "sem permissão ativa". O que a NR-33 diz e
nós repetimos (texto oficial no gov.br): o vigia fica fora do espaço confinado e não faz outras tarefas, e a câmera
pode auxiliá-lo, mas não substitui o vigia nem o campo visual dele (33.3.4.1). EPI não é campo mínimo da PET da norma —
por isso o sistema separa "fiscalizado pela câmera" de "verificação manual". Não emitimos a PET legal: é apoio.

**27. "O que a pessoa nova precisa fazer no primeiro dia? E os dados dela (LGPD)?"**
O supervisor tem um assistente de primeiro acesso que detecta sozinho o que já está pronto (câmera, referência,
planta, zona, EPIs, contas) e mostra o checklist "pronto para operar" só com o que foi detectado. A conta criada no
assistente recebe senha temporária exibida uma única vez, nunca gravada em claro nem registrada em log, sem envio de
e-mail. O formulário de contato da página pública guarda só nome, empresa, e-mail e mensagem, com consentimento
explícito, nesta instalação; o supervisor pode excluir. Nada é por pessoa nos painéis e não há reconhecimento facial.

**28. "Como vocês testaram tudo isso?"**
Cerca de 3.100 testes unitários e de API, uma matriz de permissões com ~1.400 casos (todo endpoint × todo tipo de
conta, inclusive o operador fora do setor e sem setor — achou e corrigiu 8 falhas de escopo), um caçador de bugs que só
reporta (7 bugs confirmados e corrigidos com teste de regressão), um crawler que clica em todo botão de toda tela com
cada tipo de conta (0 botões sem efeito no portão) e jornadas ponta a ponta com 4 câmeras de gravação no servidor real.
