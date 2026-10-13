# Gabarito do “Você vs. a IA” (G2)

Curado à mão em 13/10/2026, olhando os quadros reduzidos a 960×540 das gravações
de demonstração (as mesmas do E2E e do bench). O código está em
`app/services/desafio.py` (`RODADAS`); este arquivo explica as escolhas.

Pergunta das três rodadas: **quem está sem capacete?** Cada pessoa inteira no
quadro recebe uma caixa aproximada e a marca “sem capacete” ou “com capacete”.
Pessoa cortada pela borda é **neutra**: clicar nela (ou a IA apontá-la) não conta
acerto nem erro — não dá para afirmar o que há fora do quadro.

| rodada | gravação, quadro | pessoas | sem capacete | por quê |
|---|---|---|---|---|
| `canteiro-94` | `bench.mp4`, 94 | 4 | 0 | os quatro operários usam capacete branco e colete — rodada “pegadinha”: a resposta certa é não clicar |
| `multidao-168` | `next_multidao.mp4`, 168 | 5 + 1 neutra | 5 | calçada de pedestres tratada como “área de obra” para o exercício; ninguém usa capacete; a pessoa de vermelho na borda direita está cortada (neutra) |
| `canteiro-157` | `bench.mp4`, 157 | 3 | 0 | os três operários visíveis usam capacete e colete |

Pontuação (igual para a pessoa e para a IA): acerto = apontar uma pessoa “sem
capacete” (uma vez cada); erro = apontar alguém com capacete ou o chão; perdido =
pessoa “sem capacete” que ficou sem apontar. A IA aponta quem sai com capacete
`missing` no mesmo casamento EPI↔pessoa dos alertas.

Limites conhecidos: as caixas são aproximadas (marcadas a olho); três rodadas é
pouco para medir alguma coisa — o placar é para treinamento e conversa com a
banca, não é métrica de qualidade do modelo (essa está em `scripts/concordancia.py`
e em BENCHMARKS.md).
