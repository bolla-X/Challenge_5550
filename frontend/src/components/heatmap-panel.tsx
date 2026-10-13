import { useEffect, useRef, useState } from "react";
import { Panel } from "./common";

/**
 * Mapa de calor de risco (F7): onde, na imagem desta câmera, aconteceram
 * violações de EPI e entradas na zona de risco — com meia-vida, então mostra
 * o turno recente. Fundo: o quadro atual da câmera (já com privacidade).
 */
type Mapa = { colunas: number; linhas: number; meia_vida_s: number; eventos: number; grade: number[][] };

// Rampa de UMA cor (laranja de perigo), intensidade por opacidade: cor só para
// status, e células frias somem em vez de pintar a imagem inteira de azul.
function cor(v: number): string {
  return `rgba(255, 120, 40, ${Math.min(0.85, v * 0.85).toFixed(3)})`;
}

export function HeatmapPanel({ cameraId }: { cameraId: number }) {
  const [mapa, setMapa] = useState<Mapa | null>(null);
  const [tick, setTick] = useState(0);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    let vivo = true;
    const atualizar = () => {
      fetch(`/api/cameras/${cameraId}/mapa-de-calor`, { credentials: "same-origin" })
        .then((r) => (r.ok ? r.json() : null))
        .then((d) => vivo && d && setMapa(d as Mapa))
        .catch(() => undefined);
      setTick((t) => t + 1);
    };
    atualizar();
    const id = window.setInterval(atualizar, 5000);
    return () => {
      vivo = false;
      window.clearInterval(id);
    };
  }, [cameraId]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !mapa) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(canvas.clientWidth * dpr);
    canvas.height = Math.round(canvas.clientHeight * dpr);
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const cw = canvas.width / mapa.colunas;
    const ch = canvas.height / mapa.linhas;
    mapa.grade.forEach((linha, y) =>
      linha.forEach((v, x) => {
        if (v <= 0.02) return;
        ctx.fillStyle = cor(v);
        ctx.fillRect(x * cw, y * ch, Math.ceil(cw), Math.ceil(ch));
      }),
    );
  }, [mapa]);

  return (
    <Panel
      id="panel-heatmap"
      title="Mapa de calor de risco"
      description={
        mapa
          ? `${mapa.eventos} registro(s) de violação ou entrada na zona; o peso cai à metade a cada ${Math.round(mapa.meia_vida_s / 60)} min.`
          : "Carregando…"
      }
    >
      <div className="heatmap-frame">
        <img src={`/api/cameras/${cameraId}/frame.jpg?t=${tick}`} alt="Quadro atual da câmera" />
        <canvas ref={canvasRef} aria-label="Concentração de violações sobre a imagem" />
      </div>
      {mapa && mapa.eventos === 0 && <p className="status-text">Nenhuma violação registrada nesta janela.</p>}
    </Panel>
  );
}
