# Resumo da avaliação por pessoa (gerado)

Gerado por `scripts/resumir_avaliacao.py` a partir de `docs/avaliacao/*.json`. Positivo = pessoa SEM o EPI (o que gera alerta). P = precisão, R = revocação.

## 1. Seleção na validação (143 imagens) — o teste não participa

| configuração | conf | pessoas R | política | capacete P | capacete R | capacete F1 | colete P | colete R | colete F1 | F1 médio | ms/img |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Sprint 4 + COCO p/ pessoa | 0,25 | 0,85 | ausencia | 0,75 | 0,87 | 0,80 | 0,81 | 0,81 | 0,81 | **0,81** | 97 |
| Sprint 4 + COCO p/ pessoa | 0,25 | 0,85 | evidencia | 1,00 | 0,51 | 0,68 | 0,87 | 0,75 | 0,81 | **0,74** | 97 |
| Sprint 4 + COCO p/ pessoa | 0,35 | 0,84 | ausencia | 0,76 | 0,91 | 0,83 | 0,78 | 0,81 | 0,79 | **0,81** | 98 |
| Sprint 4 + COCO p/ pessoa | 0,35 | 0,84 | evidencia | 1,00 | 0,24 | 0,39 | 0,88 | 0,74 | 0,80 | **0,60** | 98 |
| Sprint 4 + COCO p/ pessoa | 0,50 | 0,78 | ausencia | 0,77 | 0,89 | 0,82 | 0,78 | 0,75 | 0,76 | **0,79** | 105 |
| Sprint 4 + COCO p/ pessoa | 0,50 | 0,78 | evidencia | 1,00 | 0,13 | 0,24 | 0,92 | 0,70 | 0,79 | **0,51** | 105 |
| Sprint 4 (VisionEPI n, 1 modelo) | 0,25 | 0,91 | ausencia | 0,76 | 0,93 | 0,84 | 0,76 | 0,84 | 0,80 | **0,82** | 48 |
| Sprint 4 (VisionEPI n, 1 modelo) | 0,25 | 0,91 | evidencia | 1,00 | 0,62 | 0,77 | 0,89 | 0,80 | 0,84 | **0,80** | 48 |
| Sprint 4 (VisionEPI n, 1 modelo) | 0,35 | 0,90 | ausencia | 0,80 | 0,98 | 0,88 | 0,74 | 0,84 | 0,79 | **0,83** | 47 |
| Sprint 4 (VisionEPI n, 1 modelo) | 0,35 | 0,90 | evidencia | 1,00 | 0,27 | 0,42 | 0,90 | 0,75 | 0,82 | **0,62** | 47 |
| Sprint 4 (VisionEPI n, 1 modelo) | 0,50 | 0,87 | ausencia | 0,71 | 0,98 | 0,82 | 0,76 | 0,81 | 0,78 | **0,80** | 47 |
| Sprint 4 (VisionEPI n, 1 modelo) | 0,50 | 0,87 | evidencia | 1,00 | 0,13 | 0,24 | 0,96 | 0,70 | 0,81 | **0,52** | 47 |
| Sprint 3 (Vyra m + COCO n) | 0,35 | 0,84 | ausencia | 0,45 | 0,93 | 0,60 | 0,43 | 0,91 | 0,58 | **0,59** | 358 |
| Sprint 3 (Vyra m + COCO n) | 0,35 | 0,84 | evidencia | — | 0,00 | — | — | 0,00 | — | **—** | 358 |
| Vyra + classes NO-* | 0,35 | 0,84 | ausencia | 0,45 | 0,93 | 0,60 | 0,43 | 0,91 | 0,58 | **0,59** | 352 |
| Vyra + classes NO-* | 0,35 | 0,84 | evidencia | 0,86 | 0,13 | 0,23 | 1,00 | 0,32 | 0,48 | **0,36** | 352 |

## 2. Teste (141 imagens, 236 pessoas) — ponta a ponta, IC 95% por reamostragem de cenas

### Sprint 3 (Vyra m + COCO n) — pessoas: R 0,79 · P 0,78 · 354 ms/imagem

| política | EPI | P | R | F1 | VP | FP | FN | VN | IC95 P | IC95 R | alerta em pessoa não anotada |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ausencia | capacete | 0,39 | 0,87 | 0,54 | 33 | 52 | 5 | 101 | [0,25; 0,57] | [0,78; 0,95] | 46 |
| ausencia | colete | 0,34 | 0,79 | 0,47 | 46 | 91 | 12 | 59 | [0,18; 0,57] | [0,66; 0,95] | 45 |
| ausencia | luvas | 0,27 | 0,86 | 0,41 | 30 | 81 | 5 | 6 | [0,12; 0,58] | [0,76; 1,00] | 53 |
| ausencia | óculos | 0,38 | 0,91 | 0,53 | 30 | 50 | 3 | 1 | [0,15; 0,90] | [0,76; 1,00] | 53 |
| evidencia | capacete | — | 0,00 | — | 0 | 0 | 38 | 153 | — | [0,00; 0,00] | 0 |
| evidencia | colete | — | 0,00 | — | 0 | 0 | 58 | 150 | — | [0,00; 0,00] | 0 |
| evidencia | luvas | — | 0,00 | — | 0 | 0 | 35 | 87 | — | [0,00; 0,00] | 0 |
| evidencia | óculos | — | 0,00 | — | 0 | 0 | 33 | 51 | — | [0,00; 0,00] | 0 |

### Vyra + classes NO-* — pessoas: R 0,79 · P 0,78 · 357 ms/imagem

| política | EPI | P | R | F1 | VP | FP | FN | VN | IC95 P | IC95 R | alerta em pessoa não anotada |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ausencia | capacete | 0,39 | 0,87 | 0,54 | 33 | 52 | 5 | 101 | [0,25; 0,57] | [0,78; 0,95] | 46 |
| ausencia | colete | 0,34 | 0,79 | 0,47 | 46 | 91 | 12 | 59 | [0,18; 0,57] | [0,66; 0,95] | 45 |
| ausencia | luvas | 0,27 | 0,86 | 0,41 | 30 | 81 | 5 | 6 | [0,12; 0,58] | [0,76; 1,00] | 53 |
| ausencia | óculos | 0,38 | 0,91 | 0,53 | 30 | 50 | 3 | 1 | [0,15; 0,90] | [0,76; 1,00] | 53 |
| evidencia | capacete | 1,00 | 0,32 | 0,48 | 12 | 0 | 26 | 153 | [1,00; 1,00] | [0,15; 0,52] | 1 |
| evidencia | colete | 0,93 | 0,24 | 0,38 | 14 | 1 | 44 | 149 | [0,82; 1,00] | [0,11; 0,40] | 0 |
| evidencia | luvas | — | 0,00 | — | 0 | 0 | 35 | 87 | — | [0,00; 0,00] | 0 |
| evidencia | óculos | — | 0,00 | — | 0 | 0 | 33 | 51 | — | [0,00; 0,00] | 0 |

### Sprint 4 (VisionEPI n, 1 modelo) — pessoas: R 0,81 · P 0,82 · 49 ms/imagem

| política | EPI | P | R | F1 | VP | FP | FN | VN | IC95 P | IC95 R | alerta em pessoa não anotada |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ausencia | capacete | 0,85 | 0,92 | 0,89 | 35 | 6 | 3 | 147 | [0,69; 0,98] | [0,84; 1,00] | 24 |
| ausencia | colete | 0,87 | 0,69 | 0,77 | 40 | 6 | 18 | 144 | [0,76; 0,97] | [0,53; 0,88] | 18 |
| ausencia | luvas | 0,65 | 0,89 | 0,75 | 31 | 17 | 4 | 70 | [0,45; 0,84] | [0,75; 1,00] | 40 |
| ausencia | óculos | 0,74 | 0,94 | 0,83 | 31 | 11 | 2 | 40 | [0,56; 0,90] | [0,79; 1,00] | 41 |
| ausencia | calçado | 0,44 | 0,79 | 0,56 | 11 | 14 | 3 | 86 | [0,19; 0,65] | [0,60; 1,00] | 30 |
| evidencia | capacete | 0,71 | 0,13 | 0,22 | 5 | 2 | 33 | 151 | [0,33; 1,00] | [0,03; 0,27] | 0 |
| evidencia | colete | 0,93 | 0,66 | 0,77 | 38 | 3 | 20 | 147 | [0,82; 1,00] | [0,50; 0,85] | 2 |
| evidencia | luvas | 1,00 | 0,20 | 0,33 | 7 | 0 | 28 | 87 | [1,00; 1,00] | [0,08; 0,38] | 1 |
| evidencia | óculos | 1,00 | 0,12 | 0,22 | 4 | 0 | 29 | 51 | [1,00; 1,00] | [0,00; 0,26] | 0 |
| evidencia | calçado | — | 0,00 | — | 0 | 0 | 14 | 100 | — | [0,00; 0,00] | 0 |

### Sprint 4 + COCO p/ pessoa — pessoas: R 0,79 · P 0,78 · 101 ms/imagem

| política | EPI | P | R | F1 | VP | FP | FN | VN | IC95 P | IC95 R | alerta em pessoa não anotada |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ausencia | capacete | 0,87 | 0,87 | 0,87 | 33 | 5 | 5 | 148 | [0,70; 1,00] | [0,78; 0,95] | 36 |
| ausencia | colete | 0,83 | 0,67 | 0,74 | 39 | 8 | 19 | 142 | [0,69; 0,95] | [0,51; 0,85] | 30 |
| ausencia | luvas | 0,64 | 0,86 | 0,73 | 30 | 17 | 5 | 70 | [0,46; 0,83] | [0,76; 1,00] | 48 |
| ausencia | óculos | 0,73 | 0,91 | 0,81 | 30 | 11 | 3 | 40 | [0,55; 0,90] | [0,76; 1,00] | 52 |
| ausencia | calçado | 0,38 | 0,57 | 0,46 | 8 | 13 | 6 | 87 | [0,16; 0,60] | [0,33; 1,00] | 40 |
| evidencia | capacete | 0,71 | 0,13 | 0,22 | 5 | 2 | 33 | 151 | [0,33; 1,00] | [0,03; 0,27] | 0 |
| evidencia | colete | 0,92 | 0,60 | 0,73 | 35 | 3 | 23 | 147 | [0,82; 1,00] | [0,44; 0,80] | 5 |
| evidencia | luvas | 1,00 | 0,23 | 0,37 | 8 | 0 | 27 | 87 | [1,00; 1,00] | [0,10; 0,41] | 0 |
| evidencia | óculos | 1,00 | 0,12 | 0,22 | 4 | 0 | 29 | 51 | [1,00; 1,00] | [0,00; 0,26] | 0 |
| evidencia | calçado | — | 0,00 | — | 0 | 0 | 14 | 100 | — | [0,00; 0,00] | 0 |

## 3. Subconjuntos do teste (política ausência)

| configuração | subconjunto | imagens | pessoas | capacete: alertas falsos / pessoas de capacete | capacete: violações achadas | colete: alertas falsos / pessoas de colete | colete: violações achadas |
|---|---|---|---|---|---|---|---|
| Sprint 3 (Vyra m + COCO n) | completo | 141 | 236 | 52 / 153 | 33 / 38 | 91 / 150 | 46 / 58 |
| Sprint 3 (Vyra m + COCO n) | sem_A_terraco | 94 | 190 | 40 / 108 | 33 / 38 | 51 / 105 | 46 / 58 |
| Sprint 3 (Vyra m + COCO n) | uma_por_cena | 81 | 171 | 30 / 95 | 33 / 38 | 50 / 90 | 45 / 54 |
| Sprint 3 (Vyra m + COCO n) | industrial_uma_por_cena | 54 | 118 | 27 / 92 | 0 / 0 | 49 / 89 | 5 / 5 |
| Sprint 4 (VisionEPI n, 1 modelo) | completo | 141 | 236 | 6 / 153 | 35 / 38 | 6 / 150 | 40 / 58 |
| Sprint 4 (VisionEPI n, 1 modelo) | sem_A_terraco | 94 | 190 | 6 / 108 | 35 / 38 | 6 / 105 | 40 / 58 |
| Sprint 4 (VisionEPI n, 1 modelo) | uma_por_cena | 81 | 171 | 6 / 95 | 35 / 38 | 6 / 90 | 40 / 54 |
| Sprint 4 (VisionEPI n, 1 modelo) | industrial_uma_por_cena | 54 | 118 | 3 / 92 | 0 / 0 | 5 / 89 | 1 / 5 |

