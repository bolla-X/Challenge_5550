# Vídeo pitch: roteiro de fala (5 minutos)

Slides: `VisionEPI-pitch.pptx` (e o PDF). Fale em ritmo calmo, cerca de 140 palavras
por minuto. Os trechos entre `[colchetes]` são ações, não fala. Os nomes e o curso
estão como `[...]` e precisam ser preenchidos.

| Tempo | Slide | Parte |
|---|---|---|
| 0:00 a 0:20 | 1 | Equipe e abertura |
| 0:20 a 0:50 | 2 | Desafio |
| 0:50 a 1:20 | 3 | Inovação |
| 1:20 a 1:50 | 4 e 5 | Arquitetura e tecnologias |
| **1:50 a 4:00** | 6 | **Demonstração** |
| 4:00 a 4:25 | 7 | O que falta |
| 4:25 a 4:45 | 8 | Códigos |
| 4:45 a 5:00 | 9 | Fechamento |

---

## 0:00 a 0:20 · Slide 1: equipe e abertura

"Olá, somos [nome 1], [nome 2] e [nome 3], do curso de [curso], e este é o
**VisionEPI**, nosso projeto do Challenge SPI da FIAP: um sistema que assiste às
câmeras da planta e avisa quando alguém está sem equipamento de proteção."

## 0:20 a 0:50 · Slide 2: desafio

"O problema é simples e sério: trabalhar sem capacete, colete ou luvas causa
acidentes graves. Só que uma planta tem muitas câmeras e poucas pessoas para
olhar todas o tempo todo. O que precisamos é saber, na hora, quem está sem EPI e
onde, barrar a entrada de quem não está protegido, e avisar sem encher o
supervisor de alertas falsos."

## 0:50 a 1:20 · Slide 3: inovação

"Quatro coisas nos diferenciam. Primeiro, dois modelos de visão trabalhando
juntos: um pronto e outro que treinamos com mais de oito mil imagens. Segundo, uma
portaria que só libera a entrada quando todos os EPIs exigidos são vistos, e que
na dúvida nega. Terceiro, um modelo de linguagem com visão que dá uma segunda
opinião, mas nunca decide sozinho. E quarto, alertas pensados para o supervisor:
agrupados por pessoa e sem ficar piscando."

## 1:20 a 1:50 · Slides 4 e 5: arquitetura e tecnologias

"O fluxo é este: a câmera envia o vídeo, o OpenCV captura os quadros, os modelos
YOLO detectam pessoas e EPIs, e o backend em Flask aplica as regras, cria os
alertas e grava no banco SQLite. Tudo chega em tempo real ao dashboard em React
por Socket.IO. Ao lado, e fora do caminho do vídeo, o Gemini dá a segunda opinião.
Usamos Python e TypeScript, PyTorch com a placa de vídeo, MediaPipe para a pose, e
mais de trezentos e setenta testes automatizados."

---

## 1:50 a 4:00 · Slide 6: demonstração (mais de 2 minutos)

[Passe para a gravação da tela. Fale por cima, sem pressa. Deixe a câmera rodando
e a conta de operador já criada.]

**1:50 · Início e câmera (25 s).**
"Entro como supervisor. A tela inicial tem dois blocos: Câmeras e Contas. Abro a
câmera. Cada pessoa recebe um número, aqui a Pessoa 1, e os alertas dela ficam
agrupados: sem capacete, sem colete, e assim por diante."

**2:15 · Zona de risco (20 s).**
"Cada câmera tem a sua zona de risco, desenhada direto no vídeo: clico para criar
um ponto e arrasto para mover. Quando alguém entra na área, o sistema alerta."

**2:35 · Alertas (20 s).**
"Se o supervisor já tratou tudo, clica em 'Resolver todos': os alertas vão para o
histórico, que tem filtros por câmera, tipo e severidade, e nada é apagado."

**2:55 · Portaria (45 s).** *[o momento mais importante]*
"Na aba Portaria, escolho quais EPIs são obrigatórios nesta câmera, por exemplo
capacete. Sem capacete, o veredito é 'ENTRADA NEGADA' e mostra o que falta.
[Coloque o capacete.] Com ele, 'ENTRADA LIBERADA'. Na dúvida, o sistema nega."

**3:40 · Operador e contas (20 s).**
"O operador, que só vê a câmera do setor dele, recebe a tela da portaria com o
veredito grande. E o supervisor cria essa conta em segundos: nome, e-mail, senha e
a câmera do operador."

*[Se a Gemini estiver ligada, acrescente 10 s: "aqui está a segunda opinião do
modelo de linguagem, com risco, justificativa e a ação sugerida."]*

---

## 4:00 a 4:25 · Slide 7: o que falta

"Hoje, cerca de oitenta por cento está funcional: detecção, câmeras, alertas,
portaria e contas. O que falta: ligar a chave da Gemini, para a segunda opinião
funcionar ao vivo; validar a detecção nas câmeras reais da planta, que já estão
conectadas; e o aviso externo por Telegram, que depende do bot da equipe."

## 4:25 a 4:45 · Slide 8: códigos

[Mostre rápido o editor ou o slide.] "Dois trechos: a regra da portaria, que nega
se qualquer EPI exigido não estiver confirmado, e o schema da resposta do modelo de
linguagem: se a resposta não cabe no schema, ela nunca vira alerta."

## 4:45 a 5:00 · Slide 9: fechamento

"Com isso, ganhamos menos acidentes, menos ruído para o supervisor e uma portaria
automática. Obrigado!"

---

## Antes de gravar

- Preencha os nomes e o curso no slide 1.
- **Não mostre o `.env`** nem as senhas das câmeras da planta.
- Crie a conta de operador, apague os alertas de teste e deixe um capacete ou colete
  à mão.
- Ensaie com cronômetro. A demonstração é o que mais estoura o tempo.
- Grave com a tela cheia e o microfone perto; suba no YouTube como **não listado** e
  teste o link numa janela anônima.
