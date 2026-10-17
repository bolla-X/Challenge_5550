# Marca VisionEPI

## O símbolo: "Cúpula"

Um único desenho que é, ao mesmo tempo, um **capacete de segurança** e uma **câmera dome**: a cúpula, a aba
solta embaixo e a lente vazada no centro. Diz em um traço o que o produto faz — câmeras que olham pela
segurança de quem trabalha — sem clip-art e sem mascote.

- Fontes: `frontend/public/marca/simbolo.svg`, `simbolo-escuro.svg`, `wordmark.svg`, `wordmark-escuro.svg`.
- No app: `frontend/src/components/brand.tsx` (`Mark`, `Wordmark`), sempre em `currentColor` — acompanha o tema.
- Favicon (`frontend/public/favicon.svg`), ícones do PWA (`frontend/public/icons/`) e imagem Open Graph
  (`frontend/public/og.png`) repetem o símbolo com cor fixa, porque não herdam variável CSS.

### Uso correto
- Uma cor só: `--text` sobre fundo claro, `--text` do tema escuro sobre fundo escuro.
- Área de proteção: a altura da lente (≈ 1/4 do símbolo) livre em volta.
- Tamanho mínimo: 16 px de altura (favicon); o nome desenhado, 12 px de altura.
- O símbolo é decorativo quando o nome está escrito ao lado (`aria-hidden`); sozinho, leva `aria-label="VisionEPI"`.

### Não fazer
- Colorir de verde/vermelho (cor no sistema é só para estado: conforme, perigo, parada).
- Sombra, contorno, gradiente, rotação ou deformação.
- Trocar a fonte do nome (o wordmark é Geist contornado: "Vision" mais pesado, "EPI" mais leve).

## Cores

Só os tokens de `frontend/src/styles/tokens.css`. A marca não tem cor própria: a única cor de interação é o
`--accent`; `--ok`, `--danger` e `--stop` são reservados para estado. A lâmpada amarela da torre de luz usa
`--sinal-amarelo` e não aparece em texto.

## Tom de voz: direto, humano, técnico sem jargão

1. **Diga o que aconteceu e o que fazer.** Uma frase para o fato, outra para a ação.
2. **Fale com quem está no chão de fábrica.** "Avisei o colaborador", não "acknowledge".
3. **Seja honesto sobre o limite.** Não detectado não é ausente; rótulo de rastreio não é identidade.
4. **Número só se o sistema mediu.** Dado de demonstração aparece rotulado.
5. **Sem jargão de máquina na tela.** Nada de `missing_helmet`, "payload", "frame", "fixture".

| Assim | Não assim |
|---|---|
| Sem conexão com o servidor. Tentando reconectar… | Failed to fetch |
| Sua sessão expirou. Entre de novo para continuar de onde parou. | 401 Unauthorized |
| Câmera obstruída: imagem sem detalhe há 3 s. | camera_obstruida detectada |
| Nenhuma evacuação registrada. Ao acionar, o painel mostra quantas pessoas cada câmera vê agora. | Lista vazia |
| Sem capacete · Pessoa 3 (visto sem o EPI) | missing_helmet person_3 |
| Contagem por câmera — pode haver dupla contagem se as câmeras se sobrepõem. | Total de pessoas: 14 |
| A câmera auxilia o vigia; não o substitui (NR-33, 33.3.4.1). | Vigia monitorado pela IA |
| Esta tela é para Técnico ou Supervisor. Peça a quem administra as contas. | 403 Forbidden |
| Postura e aproximação não ficam nas trilhas gravadas; esta regra não pode ser testada no histórico. | Resultado: 0 disparos |
| Esta página não existe. | Not Found |

A frase da evacuação mantém o travessão porque é texto exigido literalmente pela MISSÃO 4 (M3); no resto do
sistema o travessão não é usado (`e2e/test_estados.py`).
