# Atribuições e licenças (NEXT 2026)

Nada abaixo é versionado no repositório, exceto o código vendorizado do
ByteTrack (com o aviso de licença junto). Vídeos e pesos são baixados/gerados
por comando; checksums e janelas de corte estão em `scripts/fetch_fixtures.py`.

## Vídeos de fixture

**Por que não Pexels** (preferência da missão): a busca e o download do
pexels.com responderam **HTTP 403** a este cliente automatizado (proteção
Cloudflare; testado com `curl` em 2026-10-12), e a API oficial exige chave.
Usamos o **Wikimedia Commons**, que já era a fonte das fixtures do projeto e
publica licença e autor por arquivo.

| Fixture (`tests/fixtures/`) | Origem | Autor | Licença | Recorte | Cenário |
|---|---|---|---|---|---|
| `bench.mp4` | [Building construction Moira Close Broadwater Farm Haringey 2025 13.webm](https://commons.wikimedia.org/wiki/File:Building_construction_Moira_Close_Broadwater_Farm_Haringey_2025_13.webm) | Acabashi | **CC BY-SA 4.0** | quadros 3596–3806, 1280×720 | pessoas **com** capacete e colete |
| `next_multidao.mp4` | [Video Codec Test pedestrian area 1080p25.y4m.webm](https://commons.wikimedia.org/wiki/File:Video_Codec_Test_pedestrian_area_1080p25.y4m.webm) | Taurus Media Technik | **CC0** | arquivo inteiro (375 quadros, 25 fps), 960×540 | **várias pessoas, sem EPI** |
| `next_queda.mp4` | [Bits & Pieces – BP152 Falling down the stairs (EYE FLM7636)](https://commons.wikimedia.org/wiki/File:Bits_%26_Pieces_-_BP152_Falling_down_the_stairs_-_EYE_FLM7636_-_OB_105118.ogv) | autor desconhecido (EYE Filmmuseum) | **Domínio público** | quadros 1300–1800 (t = 52–72 s), 720×576 | pessoa **caída** no chão + várias pessoas |

Candidatos baixados e **descartados** depois de inspecionar folhas de contato
(sem cena útil: entrevistas e animação): *Preventing Falls in Construction*
(CDC/NIOSH, PD), *Trabajos en bodegas* (NIOSH, PD), *Las Caídas Cuestan* (CDC,
PD — capacete detectado em 1 de 9 quadros), *Walking down the Trubarjeva street*
(CC BY 3.0). Nenhum foi usado.

A obra derivada (recorte/redimensionamento) de `bench.mp4` herda a CC BY-SA 4.0.

## Modelos

| Peso | Origem | Licença | Uso |
|---|---|---|---|
| `models/vyra_ppe.pt` | [Hexmon/vyra-yolo-ppe-detection](https://huggingface.co/Hexmon/vyra-yolo-ppe-detection) (YOLOv8m, 14 classes) | **CC-BY-4.0** (exige atribuição ao autor) | detecção de EPI |
| `models/yolov8n.pt` | [Ultralytics assets](https://github.com/ultralytics/assets/releases) | AGPL-3.0 (Ultralytics) | detecção de pessoa |
| `models/yolo11n-pose.pt` | [Ultralytics assets v8.3.0](https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n-pose.pt) — SHA-256 `869e83fc…19dc0` | AGPL-3.0 (Ultralytics) | pose multi-pessoa |

O pacote `ultralytics` é **AGPL-3.0** (https://github.com/ultralytics/ultralytics/blob/main/LICENSE).

## Código de terceiros vendorizado

| Diretório | Origem | Licença |
|---|---|---|
| `app/vision/bytetrack/` | `supervision` 0.30.9 (`supervision/tracker/byte_tracker/`), Roboflow | **MIT** — `app/vision/bytetrack/LICENSE.md` |
| `frontend/src/vendor/qrcodegen.ts` | [QR Code generator library (TypeScript)](https://github.com/nayuki/QR-Code-generator), Project Nayuki — `typescript-javascript/qrcodegen.ts` do branch `master` (baixado em 13/10/2026) | **MIT** — aviso de copyright e licença no cabeçalho do próprio arquivo; única alteração: `export default qrcodegen;` no fim |
