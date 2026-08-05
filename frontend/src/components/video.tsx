import { useEffect, useRef } from "react";
import { useDashboardStore } from "../store/dashboardStore";
import { Panel, Badge } from "./common";
import { useVideoStreamLabel } from "./layout";

export function VideoPanel() {
  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const riskEditorActive = useDashboardStore((s) => s.riskEditorActive);
  const riskEditorPoints = useDashboardStore((s) => s.riskEditorPoints);
  const addRiskEditorPoint = useDashboardStore((s) => s.addRiskEditorPoint);
  const video = useVideoStreamLabel();

  const draw = () => {
    const canvas = canvasRef.current;
    const wrap = wrapRef.current;
    if (!canvas || !wrap) return;
    const rect = wrap.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.max(1, Math.floor(rect.width * dpr));
    canvas.height = Math.max(1, Math.floor(rect.height * dpr));
    canvas.style.width = `${rect.width}px`;
    canvas.style.height = `${rect.height}px`;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, rect.width, rect.height);
    if (!riskEditorPoints.length) return;
    ctx.lineWidth = 2;
    ctx.strokeStyle = "#f59e0b";
    ctx.fillStyle = "rgba(245, 158, 11, .12)";
    ctx.beginPath();
    riskEditorPoints.forEach((point, index) => {
      const x = point.x * rect.width;
      const y = point.y * rect.height;
      if (index === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    if (riskEditorPoints.length >= 3) ctx.closePath();
    ctx.stroke();
    if (riskEditorPoints.length >= 3) ctx.fill();
    riskEditorPoints.forEach((point, index) => {
      const x = point.x * rect.width;
      const y = point.y * rect.height;
      ctx.beginPath();
      ctx.arc(x, y, 5, 0, Math.PI * 2);
      ctx.fillStyle = "#f59e0b";
      ctx.fill();
      ctx.fillStyle = "#07111f";
      ctx.font = "bold 11px system-ui";
      ctx.fillText(String(index + 1), x + 8, y - 8);
    });
  };

  useEffect(() => {
    draw();
    window.addEventListener("resize", draw);
    return () => window.removeEventListener("resize", draw);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [riskEditorPoints]);

  const handleClick = (event: React.MouseEvent<HTMLCanvasElement>) => {
    if (!riskEditorActive) return;
    const rect = event.currentTarget.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    const x = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width));
    const y = Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height));
    addRiskEditorPoint({ x: Math.round(x * 10000) / 10000, y: Math.round(y * 10000) / 10000 });
  };

  return (
    <Panel
      title="Feed ao vivo"
      description="O vídeo permanece limpo: apenas detecção visual. Status, conformidade e pessoas ficam fora do frame."
      className="video-panel"
      action={<Badge tone={video.status}>{video.label}</Badge>}
    >
      <div className={`video-wrap ${riskEditorActive ? "editing-risk" : ""}`.trim()} ref={wrapRef}>
        <img src="/video_feed" alt="Feed de vídeo VisionEPI" onLoad={draw} />
        <canvas
          ref={canvasRef}
          className={`risk-editor-canvas ${riskEditorActive ? "" : "hidden"}`.trim()}
          aria-label="Editor visual de área de risco"
          onClick={handleClick}
        />
      </div>
    </Panel>
  );
}

export function RiskAreaEditorPanel() {
  const { riskArea, riskEditorActive, riskEditorPoints, toggleRiskEditor, clearRiskEditorPoints, resetRiskEditorFromServer, updateRiskArea, showMessage } =
    useDashboardStore();

  const save = async () => {
    if (riskEditorPoints.length < 3) {
      showMessage("Área de risco precisa de pelo menos 3 pontos.", "warning");
      return;
    }
    try {
      await updateRiskArea({ name: riskArea?.name || "Área de risco", polygon: riskEditorPoints });
    } catch {
      // message already set by the store action
    }
  };

  const statusText = riskArea
    ? `${riskArea.name} · ${riskEditorPoints.length} ponto(s) · modo ${riskEditorActive ? "editando" : "visualização"}`
    : "Área atual não carregada.";

  return (
    <Panel
      title="Editor de área de risco"
      description="Clique no vídeo para criar pontos normalizados. Salve para aplicar no backend."
      className="technical-only"
    >
      <div className="risk-editor-actions">
        <button className="secondary small" type="button" onClick={toggleRiskEditor}>
          {riskEditorActive ? "Encerrar edição" : "Editar no vídeo"}
        </button>
        <button className="secondary small" type="button" onClick={clearRiskEditorPoints}>
          Limpar pontos
        </button>
        <button className="secondary small" type="button" onClick={resetRiskEditorFromServer}>
          Recarregar
        </button>
        <button className="small" type="button" onClick={() => save().catch(console.error)}>
          Salvar zona
        </button>
      </div>
      <div className="risk-editor-status">{statusText}</div>
    </Panel>
  );
}
