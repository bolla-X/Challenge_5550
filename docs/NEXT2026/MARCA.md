# MARCA: identidade do VisionEPI

Fontes: `frontend/public/marca/` (`simbolo.svg`, `simbolo-escuro.svg`,
`wordmark.svg`, `wordmark-escuro.svg`). No app, o símbolo e o logotipo moram em
`frontend/src/components/brand.tsx` (`Mark`, `Wordmark`), desenhados em SVG
inline com `currentColor`.

## O símbolo: Cúpula

Uma cúpula sobre uma aba solta, com uma lente vazada. O mesmo desenho é o
**capacete de segurança** (proteção) e a **câmera dome** (o olhar). É o produto
numa forma: a câmera que verifica o EPI.

Geometria, em grade de 32:

- cúpula: semicírculo de raio 11, centro (16, 19,5);
- aba: pílula de 28 × 3 (y 21 a 24), solta da cúpula por 1,5;
- lente: furo de raio 3,5 em (16, 14). A parede da cúpula e a faixa até a base
  têm as mesmas 2 unidades.

Sem gradiente, sem traço, sem cor de estado. Cor no VisionEPI só diz estado
(`DESIGN.md`), então a marca é monocromática.

## Logotipo

"Vision" em Geist 640 e "EPI" em Geist 440, contornados em curva (Geist é SIL
OFL 1.1; contornar letras para logotipo é uso permitido). A troca de peso
separa as duas palavras sem espaço nem cor. Nunca redigite o nome numa fonte
para imitar o logotipo: use o SVG.

**Assinatura** (símbolo + logotipo): a aba do símbolo assenta na linha de base
do nome; o símbolo tem 1,35 × a altura das maiúsculas; a distância entre os
dois é **um diâmetro da lente**.

## Área de proteção e tamanhos mínimos

- Em volta do símbolo e da assinatura, deixe livre **um diâmetro da lente**
  (7/32 da caixa do símbolo). Nada de texto, borda ou outra marca dentro disso.
- Símbolo: mínimo **16 px** (favicon). Abaixo de 24 px, sempre sozinho, sem o nome.
- Logotipo: mínimo **12 px** de altura (na barra do app ele tem 14 px).
- Ícones de app: símbolo com cerca de 60 % da largura da placa; no maskable,
  dentro do círculo seguro de 80 %.

## Cores (só tokens)

| fundo | marca | tokens |
|---|---|---|
| claro | tinta | `--text` sobre `--canvas` ou `--surface` |
| escuro | papel | `--text` (escuro) sobre `--canvas` (escuro) |
| ícone de app | papel sobre placa tinta | `--canvas` claro sobre `--text` claro |

No componente, a marca herda `currentColor`, então segue o tema sozinha. Os
arquivos fixos (favicon, PNGs, `og.png`) usam os valores desses mesmos tokens.

## Uso correto e incorreto

Correto:

- símbolo sozinho em favicon, ícone de app e login;
- assinatura na barra, no material de apresentação e na imagem de prévia;
- uma cor só, com contraste dos tokens acima.

Incorreto:

- pintar o símbolo com `--danger`, `--ok`, `--accent` ou gradiente;
- colar a aba na cúpula, preencher a lente ou girar o símbolo;
- esticar, contornar com traço, pôr sombra ou brilho;
- colocar o símbolo dentro de outra forma (círculo, escudo) fora dos ícones de app;
- usar sobre foto ou vídeo sem placa sólida por trás;
- escrever "Vision EPI", "VISIONEPI" ou "VisionEpi". O nome é **VisionEPI**.

## Arquivos derivados

| arquivo | conteúdo |
|---|---|
| `frontend/public/favicon.svg` | símbolo sem placa; cor muda com `prefers-color-scheme` |
| `frontend/public/icons/icone-192.png`, `icone-512.png` | placa arredondada, cantos transparentes (`any`) |
| `frontend/public/icons/icone-mascaravel-512.png` | sangra até a borda (`maskable`) |
| `frontend/public/icons/apple-touch-icon.png` | 180 px, quadrado opaco (o iOS arredonda) |
| `frontend/public/og.png` | 1200 × 630: assinatura e "Verificação de EPI e risco com visão computacional." |

Os PNGs foram gerados da mesma geometria do SVG, com o matplotlib/Agg que já
estava no `.venv` (nenhuma dependência nova).

## Tom de voz

**Direto, humano, técnico sem jargão.** Quem lê está no chão de fábrica ou
supervisionando uma planta: quer saber o que aconteceu, onde, e o que fazer.

- Diga o fato e a ação. Uma frase, verbo concreto.
- Fale de pessoas, setores e câmeras, nunca de códigos internos (`missing_vest`).
- Não prometa o que a visão computacional não garante. Limitação se diz em
  voz alta, sem esconder em rodapé.
- Erro: o que falhou e o que fazer. Sem culpa no usuário, sem "Ops!".
- Sem exclamação, sem emoji, sem travessão como separador.
- Um termo por conceito (`GLOSSARIO.md`).

### Assim / não assim

Exemplos tirados da interface (`frontend/src/components`). "Assim" é o texto
atual ou a reescrita recomendada; "não assim" é o que evitar.

| situação | assim | não assim |
|---|---|---|
| limitação honesta (busca) | "Nenhum incidente ativo inclui a Pessoa 3 agora. Isso não quer dizer que ela não esteja na câmera: o ID é um rastreio por posição e não identifica ninguém." (`busca-global.ts`) | "Pessoa 3 não encontrada." |
| limitação honesta (EPI) | "Capacete não detectado na pessoa 2." Não detectado não é ausente: a câmera pode não ver o capacete por ângulo, luz ou oclusão. | "Pessoa 2 está sem capacete." |
| alerta crítico | "Capacete ausente, pessoa 2" na pílula sobre o vídeo, com o tempo decorrido ao lado (`REBRAND-NOTAS.md`, foco com alerta) | "ALERTA!!! Violação de EPI detectada (missing_helmet)" |
| estado vazio, incidentes | "Nenhum incidente ativo" (`alerts.tsx`) | "Nada por aqui :)" |
| estado vazio, câmeras | "Nenhuma câmera USB respondendo agora. Conecte uma e clique em \"Testar de novo\"." (`camera-grid.tsx`) | "Erro: dispositivo não encontrado." |
| erro com ação | "Não foi possível redefinir a referência." + "Tentar de novo" (`camera-focus.tsx`, `auditoria.tsx`) | "Ocorreu um erro inesperado." |
| erro de câmera | "Não foi possível iniciar a câmera." (`camera-focus.tsx`, aplicado no commit 521bafe) | frase sem artigo e sem ponto, no estilo "Falha ao iniciar câmera" (texto antigo) |
| permissão | "A auditoria é para o técnico ou o supervisor." (`auditoria.tsx`) | "403 Forbidden" |
| confirmação | "Colaborador avisado em 3 alertas." (`alerts.tsx`) | "Operação realizada com sucesso!" |
| promessa do produto | "Roda inteiro nesta máquina, sem internet." (`login.tsx`) | "Segurança 100% garantida com IA de ponta." |
