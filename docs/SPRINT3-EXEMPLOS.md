# Sprint 3: exemplos de entrada e saída

Respostas **reais** do `gemini-3.6-flash`, gravadas em `tests/goldens/` por
`scripts/gravar_goldens.py`. As imagens de entrada não ficam no git (origem, autor e
licença em [FIXTURES.md](FIXTURES.md); baixe com `python scripts/fetch_fixtures.py`).
A resposta abaixo é a **validada** pelo schema, não o texto cru.

> Três imagens mostram que o fluxo funciona. **Não** medem acurácia.

## Situação SEGURA (`segura.jpg`)

**Entrada:** Dois trabalhadores de capacete e colete, canteiro de demolição com escavadeira.

**O que a imagem mostra:** Os dois usam capacete e colete. O YOLO sozinho acusava `missing_helmet` para os dois (falso positivo crítico).

### Prompt v1: 30.3 s

```json
{
  "nivel_risco": "alto",
  "epis_ausentes": [
    "gloves",
    "glasses",
    "mask"
  ],
  "justificativa": "Os trabalhadores estão próximos a uma operação de demolição ativa com projeção de poeira e detritos sem utilizar óculos de proteção, máscara respiratória e luvas de segurança.",
  "confianca": 0.9,
  "acao_recomendada": "Paralisar momentaneamente a atividade para fornecer e exigir o uso imediato de óculos de segurança, luvas de proteção e máscara respiratória aos operários no local."
}
```

### Prompt v2: 23.9 s

```json
{
  "nivel_risco": "medio",
  "epis_ausentes": [],
  "justificativa": "Foram observados dois trabalhadores na área de demolição, ambos utilizando capacete e colete refletivo. EPIs como luvas, óculos e máscara não puderam ser confirmados devido à distância e ao ângulo dos trabalhadores.",
  "confianca": 0.8,
  "acao_recomendada": "Verificar em campo o uso de óculos de proteção e luvas, garantindo também o afastamento seguro da zona de queda de escombros da escavadeira."
}
```

## Situação de RISCO (`risco.jpg`)

**Entrada:** Obra de ponte com escavadeira e rolo compactador em operação, cerca de 9 pessoas.

**O que a imagem mostra:** Ninguém usa capacete nem colete.

### Prompt v1: 29.3 s

```json
{
  "nivel_risco": "alto",
  "epis_ausentes": [
    "helmet",
    "vest",
    "safety_shoe",
    "gloves"
  ],
  "justificativa": "Trabalhadores na pista de obras atuando próximos a máquinas pesadas e realizando trabalhos manuais sem o uso de capacete de proteção, colete de alta visibilidade, calçados de segurança e luvas.",
  "confianca": 0.95,
  "acao_recomendada": "Paralisar as atividades para fornecer e exigir o uso imediato de capacetes, coletes refletivos, calçados de segurança e luvas a toda a equipe no canteiro."
}
```

### Prompt v2: 38.5 s

```json
{
  "nivel_risco": "alto",
  "epis_ausentes": [
    "helmet",
    "vest"
  ],
  "justificativa": "Cerca de 10 pessoas trabalham e transitam em canteiro de obras viárias próximo a máquinas pesadas sem o uso de capacetes de segurança nem coletes refletivos. Devido à distância do plano da foto, não é possível confirmar com certeza a ausência de luvas, óculos ou calçados adequados.",
  "confianca": 0.85,
  "acao_recomendada": "Exigir o uso imediato de capacete de proteção e colete refletivo para todos os trabalhadores atuantes na área de tráfego de máquinas pesadas."
}
```

## Situação AMBÍGUA (`ambigua.jpg`)

**Entrada:** Três trabalhadores de capacete, ninguém de colete, concretagem em área cercada.

**O que a imagem mostra:** Colete é obrigatório nessa atividade? Isso é norma, não detecção.

### Prompt v1: 16.2 s

```json
{
  "nivel_risco": "alto",
  "epis_ausentes": [
    "gloves",
    "glasses"
  ],
  "justificativa": "Os trabalhadores estão manuseando concreto úmido e ferramentas com as mãos desprotegidas, o que gera risco de queimaduras químicas por cimento e dermatites, além da ausência de óculos de segurança contra respingos.",
  "confianca": 0.95,
  "acao_recomendada": "Interromper a concretagem para fornecer e exigir o uso imediato de luvas impermeáveis e óculos de segurança por todos os trabalhadores."
}
```

### Prompt v2: 25.5 s

```json
{
  "nivel_risco": "medio",
  "epis_ausentes": [
    "gloves",
    "glasses"
  ],
  "justificativa": "Três trabalhadores atuam na concretagem utilizando capacete de segurança, porém observam-se mãos desnudas sem luvas em contato direto/próximo ao concreto fresco e ausência de óculos de proteção.",
  "confianca": 0.85,
  "acao_recomendada": "Orientar a equipe para o uso imediato de luvas de proteção impermeáveis e óculos de segurança no manuseio de massa de concreto."
}
```
