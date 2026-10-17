import { mensagemDeErro } from "../utils/erros";
import { useEffect, useState } from "react";
import { Panel } from "./common";

/**
 * Planta baixa ao vivo (G5). Calibração: 4 cliques no CHÃO da imagem da
 * câmera e 4 nos pontos correspondentes da planta, na mesma ordem. Depois, os
 * pés de cada pessoa rastreada aparecem como pontos na planta, com a zona de
 * risco e o mapa de calor levados pela mesma homografia
 * (app/vision/planta.py). Ponto vazado = fora da área calibrada (extrapolação).
 */

type Ponto = [number, number];
type Pe = { track_id: number; x: number; y: number; dentro_da_calibracao: boolean; na_zona: boolean };
type Estado = {
  calibracao: { pontos_camera: Ponto[]; pontos_planta: Ponto[] } | null;
  pes: Pe[];
  zona: Ponto[];
  calor: [number, number, number][];
};

const CORES_DOS_PONTOS = ["#0A84FF", "#30B0C7", "#AF52DE", "#FF9F0A"];

/** Planta padrão das gravações de demonstração: um galpão de 40 × 25 m com grade de 5 m. */
function PlantaPadrao() {
  const linhasV = Array.from({ length: 7 }, (_, i) => (i + 1) * 125);
  const linhasH = Array.from({ length: 4 }, (_, i) => (i + 1) * 125);
  return (
    <g>
      <rect x="0" y="0" width="1000" height="625" fill="var(--sunken)" />
      {linhasV.map((x) => (
        <line key={`v${x}`} x1={x} y1="0" x2={x} y2="625" stroke="var(--hairline)" strokeWidth="1" />
      ))}
      {linhasH.map((y) => (
        <line key={`h${y}`} x1="0" y1={y} x2="1000" y2={y} stroke="var(--hairline)" strokeWidth="1" />
      ))}
      <rect x="2" y="2" width="996" height="621" fill="none" stroke="var(--text-2)" strokeWidth="4" />
      <text x="12" y="610" fontSize="18" fill="var(--text-2)">
        Planta padrão · grade de 5 m
      </text>
    </g>
  );
}

function Marcas({ pontos, w, h }: { pontos: Ponto[]; w: number; h: number }) {
  return (
    <>
      {pontos.map(([x, y], i) => (
        <g key={i}>
          <circle cx={x * w} cy={y * h} r={10} fill={CORES_DOS_PONTOS[i]} stroke="white" strokeWidth="2" />
          <text x={x * w} y={y * h + 5} fontSize="13" textAnchor="middle" fill="white" fontWeight="700">
            {i + 1}
          </text>
        </g>
      ))}
      {pontos.length > 1 && (
        <polygon points={pontos.map(([x, y]) => `${x * w},${y * h}`).join(" ")} fill="none" stroke="var(--accent)" strokeDasharray="6 4" strokeWidth="2" />
      )}
    </>
  );
}

function clique(e: React.MouseEvent<SVGSVGElement>): Ponto {
  const r = e.currentTarget.getBoundingClientRect();
  return [Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)), Math.min(1, Math.max(0, (e.clientY - r.top) / r.height))];
}

export function PlantaPanel({ cameraId, podeEditar }: { cameraId: number; podeEditar: boolean }) {
  const [estado, setEstado] = useState<Estado | null>(null);
  const [editando, setEditando] = useState(false);
  const [noVideo, setNoVideo] = useState<Ponto[]>([]);
  const [naPlanta, setNaPlanta] = useState<Ponto[]>([]);
  const [erro, setErro] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let vivo = true;
    const carregar = () =>
      fetch(`/api/cameras/${cameraId}/planta`, { credentials: "same-origin" })
        .then((r) => r.json())
        .then((d: Estado) => vivo && setEstado(d))
        .catch(() => undefined);
    carregar();
    const id = window.setInterval(() => {
      carregar();
      setTick((t) => t + 1);
    }, 1000);
    return () => {
      vivo = false;
      window.clearInterval(id);
    };
  }, [cameraId]);

  const salvar = (corpo: object) =>
    fetch(`/api/cameras/${cameraId}/planta`, {
      method: "PUT",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(corpo),
    }).then(async (r) => {
      if (!r.ok) throw new Error((await r.json().catch(() => ({})))?.error ?? "Falha ao salvar a calibração.");
      setEditando(false);
      setNoVideo([]);
      setNaPlanta([]);
      setErro(null);
    });

  const calibrada = Boolean(estado?.calibracao);
  const emCalibracao = editando || (!calibrada && podeEditar);

  return (
    <Panel
      id="panel-planta"
      title="Planta baixa"
      description={
        emCalibracao
          ? "Clique 4 pontos no chão do vídeo e os mesmos 4 na planta, na mesma ordem."
          : "Pés de cada pessoa rastreada, ao vivo. Número = rastreio, não identidade."
      }
    >
      {erro && <p className="status-text error">{erro}</p>}
      {emCalibracao ? (
        <div className="planta-calibracao" data-testid="planta-calibracao">
          <figure>
            <svg viewBox="0 0 960 540" className="planta-svg" onClick={(e) => noVideo.length < 4 && setNoVideo([...noVideo, clique(e)])} data-testid="planta-video">
              <image href={`/api/cameras/${cameraId}/frame.jpg?t=${Math.floor(tick / 5)}`} x="0" y="0" width="960" height="540" preserveAspectRatio="none" />
              <Marcas pontos={noVideo} w={960} h={540} />
            </svg>
            <figcaption className="muted">Vídeo: {noVideo.length}/4</figcaption>
          </figure>
          <figure>
            <svg viewBox="0 0 1000 625" className="planta-svg" onClick={(e) => naPlanta.length < 4 && setNaPlanta([...naPlanta, clique(e)])} data-testid="planta-mapa-calibracao">
              <PlantaPadrao />
              <Marcas pontos={naPlanta} w={1000} h={625} />
            </svg>
            <figcaption className="muted">Planta: {naPlanta.length}/4</figcaption>
          </figure>
          <div className="actions">
            <button
              type="button"
              className="primary"
              disabled={noVideo.length < 4 || naPlanta.length < 4}
              onClick={() => salvar({ pontos_camera: noVideo, pontos_planta: naPlanta }).catch((e) => setErro(mensagemDeErro(e, "Falha ao carregar os dados.")))}
            >
              Salvar calibração
            </button>
            <button
              type="button"
              className="ghost"
              onClick={() => {
                setNoVideo([]);
                setNaPlanta([]);
              }}
            >
              Recomeçar
            </button>
            {calibrada && (
              <button type="button" className="ghost" onClick={() => setEditando(false)}>
                Cancelar
              </button>
            )}
          </div>
        </div>
      ) : !calibrada ? (
        <p className="empty-state">Planta não calibrada. Um técnico calibra em 8 cliques.</p>
      ) : (
        <>
          <svg viewBox="0 0 1000 625" className="planta-svg" data-testid="planta-ao-vivo">
            <PlantaPadrao />
            {(estado?.calor ?? []).map(([x, y, v], i) => (
              <circle key={`c${i}`} cx={x * 1000} cy={y * 625} r={22} fill="var(--danger)" opacity={0.08 + v * 0.35} />
            ))}
            {(estado?.zona ?? []).length >= 3 && (
              <polygon
                points={(estado?.zona ?? []).map(([x, y]) => `${x * 1000},${y * 625}`).join(" ")}
                fill="var(--tint-danger)"
                stroke="var(--danger)"
                strokeWidth="3"
              />
            )}
            {(estado?.pes ?? []).map((p) => (
              <g key={p.track_id} data-testid="planta-pe" className="planta-pe">
                <circle
                  cx={p.x * 1000}
                  cy={p.y * 625}
                  r={14}
                  fill={p.dentro_da_calibracao ? (p.na_zona ? "var(--danger)" : "var(--text)") : "none"}
                  stroke={p.na_zona ? "var(--danger)" : "var(--text)"}
                  strokeWidth="3"
                />
                <text x={p.x * 1000} y={p.y * 625 - 22} fontSize="20" textAnchor="middle" fill="var(--text)">
                  {p.track_id}
                </text>
              </g>
            ))}
          </svg>
          {podeEditar && (
            <div className="actions">
              <button type="button" className="ghost" onClick={() => setEditando(true)}>
                Recalibrar
              </button>
              <button type="button" className="ghost" onClick={() => salvar({ pontos_camera: null }).catch((e) => setErro(mensagemDeErro(e, "Falha ao carregar os dados.")))}>
                Apagar calibração
              </button>
            </div>
          )}
        </>
      )}
    </Panel>
  );
}
