import { useEffect, useRef, useState } from "react";
import { desenharOverlay, type Overlay } from "./live-video";

/**
 * Replay do incidente (F1): os quadros que o servidor GRAVOU de 5 s antes a
 * 3 s depois do alerta, com o overlay de cada um. Nada é interpolado nem
 * inventado — cada quadro mostra o próprio horário relativo, e buraco de
 * gravação (câmera travou) aparece como salto no contador.
 */
type QuadroDoClipe = { i: number; ts_ms: number; rel_ms: number; overlay: Overlay | null; escala: number };
type Clipe = {
  alert_id: number;
  camera_id: number | null;
  total: number;
  quadros: QuadroDoClipe[];
  pessoa: string | null;
  regra: string | null;
  mensagem: string | null;
  severidade: string | null;
  evidencias: Record<string, unknown>;
  janela_ms: [number, number];
};

const ROTULOS_DE_EVIDENCIA: Record<string, string> = {
  confirmation_frames: "Confirmações (detecções seguidas)",
  present_labels: "O que o modelo viu na pessoa",
  supported_ppe: "EPIs que o modelo sabe detectar",
  person_box: "Caixa da pessoa",
  method: "Método",
};

function formatarEvidencia(valor: unknown): string {
  if (Array.isArray(valor)) return valor.length ? valor.join(", ") : "nada";
  if (valor && typeof valor === "object") return Object.entries(valor).map(([k, v]) => `${k}=${v}`).join(" ");
  return String(valor);
}

export function IncidentReplay({
  alertId,
  cameraName,
  onClose,
  irParaMs,
}: {
  alertId: number;
  cameraName?: string;
  onClose: () => void;
  /** Abre parado no quadro mais próximo deste instante (epoch ms) — passo da linha causal (X4). */
  irParaMs?: number;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [clipe, setClipe] = useState<Clipe | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [indice, setIndice] = useState(0);
  const [tocando, setTocando] = useState(true);
  const imagens = useRef<HTMLImageElement[]>([]);

  useEffect(() => {
    let vivo = true;
    fetch(`/api/alerts/${alertId}/clip`, { credentials: "same-origin" })
      .then(async (r) => {
        if (!r.ok) throw new Error(r.status === 404 ? "O replay é gravado 3 s depois do alerta. Tente de novo em instantes." : `HTTP ${r.status}`);
        return (await r.json()) as Clipe;
      })
      .then((dados) => {
        if (!vivo) return;
        imagens.current = dados.quadros.map((q) => {
          const img = new Image();
          img.src = `/api/alerts/${alertId}/clip/${q.i}.jpg`;
          return img;
        });
        setClipe(dados);
        if (irParaMs != null && dados.quadros.length) {
          const alvo = dados.quadros.reduce((m, q, i) => (Math.abs(q.ts_ms - irParaMs) < Math.abs(dados.quadros[m].ts_ms - irParaMs) ? i : m), 0);
          setIndice(alvo);
          setTocando(false);
        } else {
          setIndice(0);
        }
      })
      .catch((e: Error) => vivo && setErro(e.message));
    return () => {
      vivo = false;
    };
  }, [alertId, irParaMs]);

  // Toca no ritmo REAL da gravação: o intervalo até o próximo quadro é a
  // diferença dos instantes de captura, não um FPS fixo.
  useEffect(() => {
    if (!clipe || !tocando || clipe.total < 2) return undefined;
    const atual = clipe.quadros[indice];
    const proximo = clipe.quadros[(indice + 1) % clipe.total];
    const espera = indice + 1 < clipe.total ? Math.min(1000, Math.max(30, proximo.ts_ms - atual.ts_ms)) : 900;
    const id = window.setTimeout(() => setIndice((i) => (i + 1) % clipe.total), espera);
    return () => window.clearTimeout(id);
  }, [clipe, indice, tocando]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const img = imagens.current[indice];
    if (!canvas || !img || !clipe) return;
    const desenhar = () => {
      const ctx = canvas.getContext("2d");
      if (!ctx || !img.naturalWidth) return;
      const dpr = window.devicePixelRatio || 1;
      canvas.width = Math.round(canvas.clientWidth * dpr);
      canvas.height = Math.round(canvas.clientHeight * dpr);
      const escala = Math.min(canvas.width / img.naturalWidth, canvas.height / img.naturalHeight);
      const w = img.naturalWidth * escala;
      const h = img.naturalHeight * escala;
      const dx = (canvas.width - w) / 2;
      const dy = (canvas.height - h) / 2;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, dx, dy, w, h);
      const ov = clipe.quadros[indice].overlay;
      if (ov && ov.w) desenharOverlay(ctx, ov, dx, dy, w / ov.w);
    };
    if (img.complete) desenhar();
    else img.onload = desenhar;
  }, [indice, clipe]);

  const quadro = clipe?.quadros[indice];
  const momento = clipe ? clipe.quadros.reduce((m, q, i) => (Math.abs(q.rel_ms) < Math.abs(clipe.quadros[m].rel_ms) ? i : m), 0) : 0;

  return (
    <div className="modal-scrim" onClick={onClose}>
      <div className="card modal replay-modal" role="dialog" aria-labelledby="replay-titulo" onClick={(e) => e.stopPropagation()}>
        <header className="replay-cab">
          <div>
            <h2 id="replay-titulo">{clipe?.mensagem ?? "Replay do incidente"}</h2>
            <p className="t-secondary">
              {[cameraName, clipe?.pessoa, quadro ? new Date(quadro.ts_ms).toLocaleTimeString("pt-BR") : null].filter(Boolean).join(" · ")}
            </p>
          </div>
          <button type="button" className="ghost small" onClick={onClose}>
            Fechar
          </button>
        </header>
        {erro ? (
          <p className="status-text" role="status">
            {erro}
          </p>
        ) : !clipe ? (
          <p className="status-text">Carregando replay…</p>
        ) : clipe.total === 0 ? (
          <p className="status-text">Nenhum quadro foi gravado nessa janela — a câmera não entregou imagem.</p>
        ) : (
          <>
            <div className="replay-video">
              <canvas ref={canvasRef} aria-label="Replay do incidente" data-quadro={indice} data-total={clipe.total} />
              <span className={`replay-tempo ${Math.abs(quadro?.rel_ms ?? 1e9) < 150 ? "agora" : ""}`.trim()}>
                {quadro ? `${quadro.rel_ms >= 0 ? "+" : ""}${(quadro.rel_ms / 1000).toFixed(1)} s` : ""}
                {indice === momento ? " · momento do alerta" : ""}
              </span>
            </div>
            <div className="replay-controles">
              <button type="button" className="small" onClick={() => setTocando((t) => !t)}>
                {tocando ? "Pausar" : "Tocar"}
              </button>
              <input
                type="range"
                min={0}
                max={clipe.total - 1}
                value={indice}
                aria-label="Posição no replay"
                onChange={(e) => {
                  setTocando(false);
                  setIndice(Number(e.target.value));
                }}
              />
              <span className="t-data">
                quadro {indice + 1} de {clipe.total}
              </span>
            </div>
            <section className="replay-evidencias">
              <h3>Evidências que sustentaram o alerta</h3>
              <dl>
                {Object.entries(clipe.evidencias).map(([chave, valor]) => (
                  <div key={chave}>
                    <dt>{ROTULOS_DE_EVIDENCIA[chave] ?? chave}</dt>
                    <dd>{formatarEvidencia(valor)}</dd>
                  </div>
                ))}
                <div>
                  <dt>Janela gravada</dt>
                  <dd>
                    {(clipe.janela_ms[0] / 1000).toFixed(0)} s a +{(clipe.janela_ms[1] / 1000).toFixed(0)} s do alerta, {clipe.total} quadros reais
                  </dd>
                </div>
              </dl>
              <p className="t-secondary">O ID é um rastreio por posição, não uma identidade. Rostos desfocados pelo modo privacidade.</p>
            </section>
          </>
        )}
      </div>
    </div>
  );
}
