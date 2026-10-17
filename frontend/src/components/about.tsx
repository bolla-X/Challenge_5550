import { useDashboardStore } from "../store/dashboardStore";
import { ScreenHead } from "./layout";

/**
 * Sobre / Licenças: o que o VisionEPI usa e sob quais termos. Modelo, vídeos de
 * demonstração e bibliotecas com a licença que cada projeto declara (link para
 * o arquivo de licença de cada um). Fonte de verdade das atribuições:
 * docs/NEXT2026/ATRIBUICOES.md.
 */
type Item = { nome: string; papel: string; licenca: string; link: string; nota?: string };

const MODELOS: Item[] = [
  {
    nome: "Vyra YOLO PPE Detection (Hexmon)",
    papel: "Detecção de EPI: YOLOv8m, 14 classes",
    licenca: "CC-BY-4.0 (exige atribuição ao autor)",
    link: "https://huggingface.co/Hexmon/vyra-yolo-ppe-detection",
  },
  { nome: "YOLOv8n (Ultralytics)", papel: "Detecção de pessoa", licenca: "AGPL-3.0", link: "https://github.com/ultralytics/assets/releases" },
  { nome: "YOLO11n-pose (Ultralytics)", papel: "Pose multi-pessoa", licenca: "AGPL-3.0", link: "https://github.com/ultralytics/assets/releases" },
];

const VIDEOS: Item[] = [
  {
    nome: "Building construction Moira Close, Broadwater Farm (2025)",
    papel: "Canteiro com capacete e colete",
    licenca: "CC BY-SA 4.0, Acabashi",
    link: "https://commons.wikimedia.org/wiki/File:Building_construction_Moira_Close_Broadwater_Farm_Haringey_2025_13.webm",
  },
  {
    nome: "Video Codec Test: pedestrian area 1080p25",
    papel: "Várias pessoas sem EPI",
    licenca: "CC0, Taurus Media Technik",
    link: "https://commons.wikimedia.org/wiki/File:Video_Codec_Test_pedestrian_area_1080p25.y4m.webm",
  },
  {
    nome: "Bits & Pieces BP152: Falling down the stairs (EYE Filmmuseum)",
    papel: "Pessoa caída",
    licenca: "Domínio público",
    link: "https://commons.wikimedia.org/wiki/File:Bits_%26_Pieces_-_BP152_Falling_down_the_stairs_-_EYE_FLM7636_-_OB_105118.ogv",
  },
];

const BIBLIOTECAS: Item[] = [
  { nome: "Ultralytics", papel: "Inferência YOLO", licenca: "AGPL-3.0", link: "https://github.com/ultralytics/ultralytics/blob/main/LICENSE" },
  {
    nome: "ByteTrack (derivado de roboflow/supervision 0.30.9)",
    papel: "Rastreador experimental, incluído no código do projeto",
    licenca: "MIT, Roboflow",
    link: "https://github.com/roboflow/supervision/blob/develop/LICENSE.md",
  },
  { nome: "PyTorch", papel: "Execução padrão do modelo", licenca: "BSD-3-Clause", link: "https://github.com/pytorch/pytorch/blob/main/LICENSE" },
  { nome: "ONNX Runtime", papel: "Execução alternativa aprovada", licenca: "MIT", link: "https://github.com/microsoft/onnxruntime/blob/main/LICENSE" },
  { nome: "OpenCV", papel: "Captura, imagem e JPEG", licenca: "Apache-2.0", link: "https://github.com/opencv/opencv/blob/4.x/LICENSE" },
  { nome: "MediaPipe", papel: "Pose (caminho alternativo)", licenca: "Apache-2.0", link: "https://github.com/google-ai-edge/mediapipe/blob/master/LICENSE" },
  { nome: "Flask / Flask-SocketIO", papel: "Servidor e tempo real", licenca: "BSD-3-Clause / MIT", link: "https://github.com/miguelgrinberg/Flask-SocketIO/blob/main/LICENSE" },
  { nome: "React, Zustand, socket.io-client, Motion, cmdk", papel: "Interface", licenca: "MIT", link: "https://github.com/facebook/react/blob/main/LICENSE" },
  { nome: "Geist / Geist Mono", papel: "Tipografia", licenca: "SIL Open Font License 1.1", link: "https://github.com/vercel/geist-font/blob/main/OFL.txt" },
];

function Lista({ titulo, itens }: { titulo: string; itens: Item[] }) {
  return (
    <section className="sobre-secao">
      <h2>{titulo}</h2>
      <ul>
        {itens.map((item) => (
          <li key={item.nome}>
            <div>
              <a href={item.link} target="_blank" rel="noopener noreferrer">
                {item.nome}
              </a>
              <span className="t-secondary">{item.papel}</span>
            </div>
            <span className="sobre-licenca">{item.licenca}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function AboutScreen() {
  const setScreen = useDashboardStore((s) => s.setScreen);
  return (
    <div className="screen sobre">
      <ScreenHead
        title="Sobre e licenças"
        sub="VisionEPI, FIAP NEXT 2026. Modelos, gravações de demonstração e bibliotecas, com a licença declarada por cada projeto."
        actions={
          <button type="button" className="ghost" onClick={() => setScreen("grid")}>
            Voltar
          </button>
        }
      />
      <Lista titulo="Modelos" itens={MODELOS} />
      <Lista titulo="Gravações usadas na demonstração" itens={VIDEOS} />
      <Lista titulo="Software" itens={BIBLIOTECAS} />
      <p className="t-secondary sobre-nota">
        Privacidade: o vídeo sai com rosto desfocado por padrão; nada aqui reconhece pessoas: o "Pessoa N" é um rastreio por posição.
        Detalhes de origem, recorte e checksum das gravações em docs/NEXT2026/ATRIBUICOES.md.
      </p>
    </div>
  );
}
