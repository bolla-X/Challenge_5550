import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useDashboardStore } from "../store/dashboardStore";
import { Panel } from "./common";
import { useVideoStreamLabel } from "./layout";

function CameraOffIcon() {
  return (
    <svg viewBox="0 0 24 24">
      <path d="M3 3l18 18M9 7h6l2 3h2a1 1 0 0 1 1 1v7a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1v-4M4 7h1" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="12" cy="14" r="3" />
    </svg>
  );
}

/**
 * Camada do editor de área de risco: desenha o polígono em edição e captura os
 * cliques. Fica por cima do <img> do feed, dentro de um contêiner `position:
 * relative` (o `.video-frame`).
 *
 * As coordenadas são normalizadas em relação ao VÍDEO, não ao contêiner: o <img>
 * usa `object-fit: contain`, então quando a fonte não é 16:9 (ex.: câmera girada
 * em pé) sobram faixas pretas, e normalizar pelo contêiner deslocaria a zona.
 */
export function RiskEditorCanvas({ wrapRef }: { wrapRef: React.RefObject<HTMLDivElement | null> }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const riskEditorActive = useDashboardStore((s) => s.riskEditorActive);
  const riskEditorPoints = useDashboardStore((s) => s.riskEditorPoints);
  const addRiskEditorPoint = useDashboardStore((s) => s.addRiskEditorPoint);
  const moveRiskEditorPoint = useDashboardStore((s) => s.moveRiskEditorPoint);
  const arrastando = useRef<number | null>(null);

  // Retângulo (em px do contêiner) que o vídeo realmente ocupa.
  const areaDoVideo = () => {
    const wrap = wrapRef.current;
    if (!wrap) return null;
    const box = wrap.getBoundingClientRect();
    const img = wrap.querySelector("img");
    const nw = img?.naturalWidth || 0;
    const nh = img?.naturalHeight || 0;
    if (!nw || !nh) return { x: 0, y: 0, w: box.width, h: box.height, box };
    const scale = Math.min(box.width / nw, box.height / nh);
    const w = nw * scale;
    const h = nh * scale;
    return { x: (box.width - w) / 2, y: (box.height - h) / 2, w, h, box };
  };

  const draw = () => {
    const canvas = canvasRef.current;
    const area = areaDoVideo();
    if (!canvas || !area) return;
    const { box } = area;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.max(1, Math.floor(box.width * dpr));
    canvas.height = Math.max(1, Math.floor(box.height * dpr));
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, box.width, box.height);
    if (!riskEditorPoints.length) return;
    const px = (p: { x: number; y: number }) => [area.x + p.x * area.w, area.y + p.y * area.h] as const;
    ctx.lineWidth = 2;
    ctx.strokeStyle = "#f59e0b";
    ctx.fillStyle = "rgba(245, 158, 11, .12)";
    ctx.beginPath();
    riskEditorPoints.forEach((p, i) => {
      const [x, y] = px(p);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    if (riskEditorPoints.length >= 3) ctx.closePath();
    ctx.stroke();
    if (riskEditorPoints.length >= 3) ctx.fill();
    riskEditorPoints.forEach((p, i) => {
      const [x, y] = px(p);
      ctx.beginPath();
      ctx.arc(x, y, 5, 0, Math.PI * 2);
      ctx.fillStyle = "#f59e0b";
      ctx.fill();
      ctx.fillStyle = "#f8fafc";
      ctx.font = "bold 11px system-ui";
      ctx.fillText(String(i + 1), x + 8, y - 8);
    });
  };

  useEffect(() => {
    draw();
    const img = wrapRef.current?.querySelector("img");
    window.addEventListener("resize", draw);
    img?.addEventListener("load", draw);
    return () => {
      window.removeEventListener("resize", draw);
      img?.removeEventListener("load", draw);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [riskEditorPoints, riskEditorActive]);

  // Posição do ponteiro em coordenadas do vídeo (0..1) e em px do canvas.
  const posicao = (event: React.PointerEvent<HTMLCanvasElement>) => {
    const area = areaDoVideo();
    if (!area || !area.w || !area.h) return null;
    const box = event.currentTarget.getBoundingClientRect();
    const px = event.clientX - box.left;
    const py = event.clientY - box.top;
    return { area, px, py, x: (px - area.x) / area.w, y: (py - area.y) / area.h };
  };

  // Ponto já existente sob o ponteiro (raio de 12 px), ou -1.
  const pontoPerto = (pos: NonNullable<ReturnType<typeof posicao>>) => {
    let melhor = -1;
    let menor = 12;
    riskEditorPoints.forEach((p, i) => {
      const d = Math.hypot(pos.area.x + p.x * pos.area.w - pos.px, pos.area.y + p.y * pos.area.h - pos.py);
      if (d <= menor) {
        menor = d;
        melhor = i;
      }
    });
    return melhor;
  };

  const arredondar = (v: number) => Math.round(Math.max(0, Math.min(1, v)) * 10000) / 10000;

  // Duas ações no mesmo canvas: apertar EM CIMA de um ponto e arrastar o move;
  // apertar em espaço vazio cria um ponto novo.
  const handlePointerDown = (event: React.PointerEvent<HTMLCanvasElement>) => {
    if (!riskEditorActive) return;
    const pos = posicao(event);
    if (!pos) return;
    const perto = pontoPerto(pos);
    if (perto >= 0) {
      arrastando.current = perto;
      event.currentTarget.setPointerCapture(event.pointerId);
      return;
    }
    if (pos.x < 0 || pos.x > 1 || pos.y < 0 || pos.y > 1) return; // faixa preta
    addRiskEditorPoint({ x: arredondar(pos.x), y: arredondar(pos.y) });
  };

  const handlePointerMove = (event: React.PointerEvent<HTMLCanvasElement>) => {
    if (!riskEditorActive) return;
    const pos = posicao(event);
    if (!pos) return;
    if (arrastando.current !== null) {
      moveRiskEditorPoint(arrastando.current, { x: arredondar(pos.x), y: arredondar(pos.y) });
      return;
    }
    event.currentTarget.style.cursor = pontoPerto(pos) >= 0 ? "grab" : "crosshair";
  };

  const handlePointerUp = (event: React.PointerEvent<HTMLCanvasElement>) => {
    if (arrastando.current === null) return;
    arrastando.current = null;
    event.currentTarget.releasePointerCapture(event.pointerId);
  };

  return (
    <canvas
      ref={canvasRef}
      className={`risk-editor-canvas ${riskEditorActive ? "" : "hidden"}`.trim()}
      aria-label="Editor visual de área de risco"
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onPointerCancel={handlePointerUp}
    />
  );
}

/**
 * Video card — the product's central element, treated as a designed
 * surface rather than a black box. Stopped state shows a real empty state
 * (icon badge + copy + embedded Start action) instead of ever fetching the
 * backend's own baked-in placeholder frame (/video_feed always renders
 * "monitoramento parado" as pixels when the loop isn't running — we avoid
 * mounting <img> at all until running, so that never reaches the screen).
 */
const EASE = [0.16, 1, 0.3, 1] as const; // matches tokens.css --ease

export function VideoCard() {
  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const running = useDashboardStore((s) => s.running);
  const bootstrapping = useDashboardStore((s) => s.bootstrapping);
  const start = useDashboardStore((s) => s.start);
  const shouldReduceMotion = useReducedMotion();
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
  }, [riskEditorPoints, running]);

  const handleClick = (event: React.MouseEvent<HTMLCanvasElement>) => {
    if (!riskEditorActive) return;
    const rect = event.currentTarget.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    const x = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width));
    const y = Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height));
    addRiskEditorPoint({ x: Math.round(x * 10000) / 10000, y: Math.round(y * 10000) / 10000 });
  };

  if (bootstrapping) {
    return (
      <section id="panel-video" className="card video-card">
        <div className="video-frame">
          <div className="skeleton-block video-skeleton" />
        </div>
      </section>
    );
  }

  return (
    <section id="panel-video" className="card video-card">
      <div className={`video-frame ${riskEditorActive ? "editing-risk" : ""}`.trim()} ref={wrapRef}>
        {/* Comunica "o feed ligou/desligou" com um cross-fade — opacity
            só, sem scale/slide: o vídeo é o elemento mais importante da
            tela, não pode competir com a própria transição. */}
        <AnimatePresence initial={false}>
          {running ? (
            <motion.div
              key="live"
              initial={shouldReduceMotion ? false : { opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: shouldReduceMotion ? 0.001 : 0.25, ease: EASE }}
            >
              <span className="video-live-dot">
                <span className={`status-dot ${video.status}`} /> {video.label}
              </span>
              <img src="/video_feed" alt="Feed de vídeo VisionEPI" onLoad={draw} />
              <canvas
                ref={canvasRef}
                className={`risk-editor-canvas ${riskEditorActive ? "" : "hidden"}`.trim()}
                aria-label="Editor visual de área de risco"
                onClick={handleClick}
              />
            </motion.div>
          ) : (
            <motion.div
              key="empty"
              className="video-empty"
              initial={shouldReduceMotion ? false : { opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: shouldReduceMotion ? 0.001 : 0.25, ease: EASE }}
            >
              <div className="video-empty-badge">
                <CameraOffIcon />
              </div>
              <h3>Aguardando conexão de vídeo</h3>
              <p>Inicie o monitoramento para começar a receber o feed em tempo real.</p>
              <button type="button" id="startBtn" onClick={() => start().catch((err) => console.error(err))}>
                Iniciar
              </button>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </section>
  );
}

export function RiskAreaEditorPanel() {
  const { riskArea, riskEditorActive, riskEditorPoints, toggleRiskEditor, clearRiskEditorPoints, resetRiskEditorFromServer, updateRiskArea, showMessage } =
    useDashboardStore();
  const [saving, setSaving] = useState(false);

  const save = async () => {
    if (riskEditorPoints.length < 3) {
      showMessage("Área de risco precisa de pelo menos 3 pontos.", "warning");
      return;
    }
    setSaving(true);
    try {
      await updateRiskArea({ name: riskArea?.name || "Área de risco", polygon: riskEditorPoints });
    } catch {
      // message already set by the store action
    } finally {
      setSaving(false);
    }
  };

  const statusText = riskArea
    ? `${riskArea.name} · ${riskEditorPoints.length} ponto(s) · modo ${riskEditorActive ? "editando" : "visualização"}`
    : "Área atual não carregada.";

  return (
    <Panel id="panel-risk-area" title="Editor de área de risco" description="Clique no vídeo para criar um ponto. Arraste um ponto existente para movê-lo.">
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
        <button className={`small ${saving ? "is-pending" : ""}`.trim()} type="button" disabled={saving} onClick={() => save().catch(console.error)}>
          {saving ? "Salvando…" : "Salvar zona"}
        </button>
      </div>
      <div className="risk-editor-status">{statusText}</div>
    </Panel>
  );
}
