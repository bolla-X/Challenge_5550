# VisionEPI — Relatório Técnico: Fase 3 — Notificação Inteligente

**Challenge 2026 — Innovation Challenge CUP — Parceria FIAP × SPI**
Engenharia da Computação, 3º ano. Entrega: 24/08/2026.

## Equipe

Lucas Baraldi Rodrigues · Lucas Zolla Assis · Pedro Costa Belisário · Vitor Pantarotto de Brito
Professor: Fabio Henrique Pimentel · Mentores SPI: Fernando Marcolina, Wendel de Almeida Passos

---

## 1. Escopo desta fase

Sistema de notificação inteligente com pelo menos dois canais distintos (um
obrigatoriamente perceptível pelo operador no campo). Política de severidade explícita.
Dashboard mínimo para gestão. Latência E2E reportada e demonstrada.

## 2. O que foi construído

### 2.1 Política de severidade explícita

Cada regra de alerta tem uma severidade fixa e documentada: `critical` (ex.: sem
capacete, pessoa caída), `high` (ex.: sem colete, sem óculos, dentro da zona de risco),
`medium` (ex.: sem luvas, sem máscara, sem calçado, sem protetor auricular, postura
suspeita). Alertas de **uso incorreto** (ver Fase 1) têm a mesma severidade do
correspondente "ausente" — uso incorreto não protege mais que a ausência.

### 2.2 Dois canais de notificação, distintos

1. **Visual**, no dashboard: alertas agrupados por pessoa, com filtro por indivíduo,
   histórico com filtros por câmera/tipo/situação/severidade, ações em lote ("avisei
   todos", "resolver todos"), evidência (foto do momento do alerta).
2. **Sonoro**, na tela do operador: apita quando a portaria libera ou nega a entrada —
   dois sons distintos, sintetizados por código (sem arquivo de áudio de terceiro) —
   **perceptível por quem está fisicamente no local**, sem depender de olhar a tela.

Um terceiro canal (**Telegram**) está **planejado, não implementado**: depende da
criação de um bot pela equipe fora do sistema (feito pelo BotFather do Telegram) e não
entrou a tempo desta entrega — decisão consciente de não arriscar instabilidade às
vésperas da apresentação ao vivo.

### 2.3 Dashboard mínimo para gestão

Três perfis de acesso, cada um vendo só o que precisa:

- **Operador**: só a câmera do próprio setor; se ela estiver em modo portaria, vê o
  veredito de entrada em tela cheia.
- **Técnico**: todas as câmeras, configuração completa (zona de risco, rotação,
  parâmetros, modo portaria).
- **Supervisor**: tudo do técnico, mais gráficos de tendência de risco, apagar alertas
  já resolvidos e a criação/gestão de contas de operador.

### 2.4 Modo portaria

Cada câmera pode exigir um conjunto próprio de EPIs; **só libera a entrada se todos
forem confirmados**; qualquer incerteza (feature desligada, classe não suportada pelo
modelo, pessoa fora do quadro) conta como reprovado — na dúvida, nega. Veredito
estabilizado por confirmação: nega em 3 quadros seguidos, libera em 8 — liberar por
engano é o erro mais caro, por isso pesa mais quadros.

## 3. Latência E2E, medida

Medida do **início real da captura** (violação já presente desde o primeiro quadro) até
o **alerta aparecer gravado no banco**, 5 execuções contra o sistema rodando de verdade:

| Execução | Latência | Alerta |
|---|---|---|
| 1ª (partida fria — carregando o modelo) | 5,97 s | crítico |
| 2ª | 1,22 s | alto |
| 3ª | 1,37 s | crítico |
| 4ª | 1,12 s | alto |
| 5ª | 1,18 s | alto |

**Com o sistema já aquecido: ~1,2 s de média.** Meta do guia: ≤1s para crítico, ≤5s
para alto. Ficamos **levemente acima da meta no crítico** (1,2 s vs. 1 s) e **dentro da
meta no alto**, com folga.

## 4. Inovações desta fase

- Alertas agrupados por pessoa (não uma lista solta), com filtro individual.
- "Resolver todos" com soneca de 60 s por pessoa (reconhecida por sobreposição de
  caixa, já que o número do rastreador pode mudar) — evita que a mesma violação recrie
  o alerta em menos de 1 segundo.
- Portaria com veredito assimétrico (nega rápido, libera devagar), decisão de
  engenharia deliberada para privilegiar segurança sobre conveniência.
- Contas de operador restritas por câmera, criadas pelo supervisor — sem cadastro
  público.

## 5. Entregáveis desta fase

- [x] 2 canais distintos de notificação (visual + sonoro), um perceptível em campo
- [x] Política de severidade explícita
- [x] Dashboard mínimo (na verdade, com 3 perfis diferenciados)
- [x] Latência E2E reportada e demonstrada (medição real, §3)
- [x] Relatório técnico (este documento)
- [~] Terceiro canal (Telegram): planejado, não implementado — limitação declarada
