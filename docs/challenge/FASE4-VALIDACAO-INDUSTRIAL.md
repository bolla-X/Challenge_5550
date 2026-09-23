# VisionEPI — Relatório Técnico: Fase 4 — Validação em Ambiente Industrial Simulado

**Challenge 2026 — Innovation Challenge CUP — Parceria FIAP × SPI**  
Engenharia da Computação, 3º ano. Entrega: 23/09/2026 (banca final).

## Equipe

Lucas Baraldi Rodrigues · Lucas Zolla Assis · Pedro Costa Belisário · Vitor Pantarotto de Brito  
Professor: Fabio Henrique Pimentel · Mentores SPI: Fernando Marcolina, Wendel de Almeida Passos

---

## 1. Escopo desta fase

Solução completa integrada e testada no ambiente simulado da Metaindústria. Pitch final
de 5 minutos com demo ao vivo. Documento técnico consolidado das quatro fases. Operação
contínua de pelo menos 30 minutos sem reinicialização manual.

## 2. Conexão com câmeras reais

O sistema foi testado contra as **câmeras RTSP reais de uma planta industrial
parceira** (protocolo Dahua). **Resultado: conectou em todas, e rodou em todas ao mesmo
tempo, sem cair.**

**Achado observável, registrado honestamente:** a latência da rede **Wi-Fi** até as
câmeras prejudicou a detecção de forma perceptível — quadros mais espaçados e alguma
degradação de qualidade da imagem — mas o sistema **continuou funcionando**, sem travar
nem reiniciar sozinho. Isso é evidência de robustez de engenharia (o sistema degrada
graciosamente sob rede ruim, não quebra), mas também um limite real de performance que
uma rede cabeada ou um AP dedicado por câmera resolveria.

## 3. Operação contínua

Testado **30 minutos seguidos, sem reinicialização manual** — funcionou de forma
estável durante todo o período, cumprindo o mínimo exigido pelo escopo desta fase.

## 4. Confidencialidade das câmeras reais

As câmeras da planta real mostram trabalhadores e instalações reais — informação
sensível conforme a política do guia (§2.5, "imagens de instalações industriais
reais", "identificadores de funcionários"). **Usadas só em demonstração ao vivo, com
autorização da empresa parceira**: nenhuma imagem delas foi armazenada, publicada ou
incluída em vídeo, slide, print ou neste repositório. Todo material público da entrega
(vídeo institucional, demonstração gravada, slides) usa exclusivamente fontes públicas
(Wikimedia Commons, licenças CC BY / domínio público, ver `docs/FIXTURES.md`) ou a
própria webcam da equipe.

## 5. O que entrou nesta fase final, fechando lacunas do escopo mínimo da Fase 1

- **Protetor auricular** (7ª classe de EPI), fechando o mínimo de 5 EPIs exigido.
- **Distinção uso correto/incorreto/ausente**, fechando outra exigência do escopo
  mínimo da Fase 1 que ainda estava pendente até esta entrega.
- As duas foram **testadas ao vivo antes desta entrega**, contra webcam real: os
  alertas `incorrect_helmet`, `incorrect_mask` e `missing_ear_protection` apareceram
  corretamente na tela, com a mensagem certa e a severidade certa.

## 6. Integração end-to-end, demonstrada

O fluxo completo — câmera → detecção → pose → regras → alerta → portaria → dashboard —
roda como um sistema único, sem etapas manuais entre uma fase e outra. A demonstração ao
vivo (e o vídeo institucional de 90 s, `docs/pitch/VisionEPI-institucional-90s.mp4`)
mostra: detecção com identificação de pessoa, zona de risco, histórico de alertas,
modo portaria negando e liberando entrada, tela do operador e criação de conta pelo
supervisor — todas as quatro fases trabalhando juntas na mesma execução.

## 7. Pitch final e comunicação

Slides em `docs/pitch/VisionEPI-pitch-v3.pptx`/`.pdf`. Vídeo institucional de 90 segundos
com narração, trilha licenciada (CC BY 4.0, "Wallpaper" de Kevin MacLeod) e declaração
explícita de que as imagens de demonstração são públicas. Roteiro de apoio para a
apresentação ao vivo em `docs/pitch/ROTEIRO-DE-FALA.md`.

⚠️ **Risco declarado:** a gravação completa (`VisionEPI-pitch-completo.mp4`) tem
aproximadamente 10 minutos, acima dos 5 minutos exatos pedidos para o pitch. Decisão
consciente da equipe, sabendo do risco na rubrica de Comunicação.

## 8. Entregáveis desta fase

- [x] Solução completa integrada, testada contra câmeras reais
- [x] Operação contínua de 30+ minutos sem reinicialização manual
- [x] Documento técnico consolidado das quatro fases (`CONSOLIDADO.md`)
- [x] Pitch final com demo ao vivo preparado
- [x] Vídeo institucional de 90 segundos
- [x] Relatório técnico desta fase (este documento)
- [~] Pitch dentro de 5 minutos exatos: gravação de apoio ficou em ~10 min (risco
      declarado, §7); a apresentação ao vivo será cronometrada separadamente
