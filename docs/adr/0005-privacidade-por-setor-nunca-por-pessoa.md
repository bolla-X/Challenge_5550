# ADR 0005: Privacidade "por setor, nunca por pessoa" (desfoque de rosto, sem reconhecimento facial)

- **Status:** aceito (vigente)
- **Data:** 14/10/2026 (entrada na `main` pelo squash do PR7, `a6d303b`). A regra foi escrita no prompt da missão do NEXT 2026
  (`docs/NEXT2026/MISSAO.md`, regra 6) e implementada nos PRs 1 a 6 da branch, cujos commits individuais não estão na `main`.

## Contexto

As imagens de câmeras de planta mostram trabalhadores reais. O guia do Challenge classifica isso como informação sensível
(`docs/challenge/FASE4-VALIDACAO-INDUSTRIAL.md` §4). O sistema precisa mostrar replay e evidência sem expor rosto e sem virar vigilância de
indivíduos.

## Decisão

- **ID de rastreio não é identidade.** Sem reconhecimento facial, sem nome de pessoa vinculado a ID, sem ranking individual.
- **Desfoque de rosto em tudo que sai do worker** (`app/vision/privacidade.py`): quadro do stream, miniatura, snapshot do alerta, clipe de
  replay e a imagem enviada à segunda opinião do LLM. Ligado por padrão; só o supervisor desliga
  (`e2e/test_fluxos.py::test_privacidade_so_o_supervisor_altera`). A inferência continua no quadro original; o desfoque é sobre o que pessoas veem.
- Pixelização em vez de só desfoque gaussiano: reduzir para poucos blocos e ampliar descarta a informação e custa menos.
- Pontuação, metas, Liga de Setores e Modo TV são **por setor ou equipe**, com indicadores positivos (`docs/NEXT2026/GLOSSARIO.md`).
- Contagem de evacuação é por câmera e zona, com aviso de dupla contagem.

## Consequências

- Limitação declarada no código: **quem o detector de pessoa não viu não é desfocado**.
- O desfoque usa os keypoints de cabeça da pose quando existem e, sem pose, o terço superior da caixa; a margem cresce com a idade da análise.
- O módulo Gestão de EPIs (ADR 0008) herda a regra: colaborador não tem coluna que ligue a câmera, ID de rastreio ou imagem.
- Não substitui parecer jurídico: o repositório cita a LGPD como motivação (`app/vision/privacidade.py`), mas não há análise formal de conformidade
  nos documentos.

## Alternativas

- Reconhecimento facial para vincular infração a uma pessoa: **excluída por regra de projeto**; não há registro de análise comparativa.
- Desfoque só no que é exportado (e não no stream): **sem registro**; o código desfoca todas as saídas.
