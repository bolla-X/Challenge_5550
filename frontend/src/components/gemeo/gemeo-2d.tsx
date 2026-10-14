import type { CameraDoGemeo, PeNaPlanta } from "./tipos";

/**
 * Planta 2D do gêmeo: o mesmo conteúdo do 3D (setores, zonas, pessoas por
 * cor de estado), em SVG. Entra sozinha quando o WebGL não existe.
 */
const W = 1000;
const H = 625;

const CLASSE: Record<PeNaPlanta["estado"], string> = {
  conforme: "ok",
  sem_epi: "perigo",
  zona: "perigo",
  emergencia: "parada",
};

export function Gemeo2D({
  cameras,
  onPessoa,
  onZona,
}: {
  cameras: CameraDoGemeo[];
  onPessoa: (cam: CameraDoGemeo, pe: PeNaPlanta) => void;
  onZona: (cam: CameraDoGemeo) => void;
}) {
  const calibradas = cameras.filter((c) => c.calibrada && c.pontos_planta);
  const pts = (lista: [number, number][]) => lista.map(([x, y]) => `${x * W},${y * H}`).join(" ");
  return (
    <svg className="gemeo-2d" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Planta 2D com as pessoas rastreadas" data-testid="gemeo-2d">
      <rect x="0" y="0" width={W} height={H} className="gemeo-2d-piso" />
      {calibradas.map((cam) => {
        const quad = cam.pontos_planta as [number, number][];
        const cx = (quad.reduce((a, [x]) => a + x, 0) / 4) * W;
        const cy = (quad.reduce((a, [, y]) => a + y, 0) / 4) * H;
        return (
          <g key={cam.id}>
            <polygon points={pts(quad)} className="gemeo-2d-setor" />
            <text x={cx} y={cy} className="gemeo-2d-rotulo" textAnchor="middle">
              {cam.setor} · {cam.nome}
            </text>
            {cam.zona.length >= 3 && (
              <polygon
                points={pts(cam.zona)}
                className="gemeo-2d-zona"
                role="button"
                tabIndex={0}
                aria-label={`Zona ${cam.zona_nome ?? "de risco"} em ${cam.nome}`}
                onClick={() => onZona(cam)}
                onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onZona(cam)}
              />
            )}
          </g>
        );
      })}
      {calibradas.flatMap((cam) =>
        cam.pes.map((pe) => (
          <g
            key={`${cam.id}:${pe.track_id}`}
            className={`gemeo-2d-pessoa ${CLASSE[pe.estado]} ${pe.dentro_da_calibracao ? "" : "fora"}`}
            transform={`translate(${pe.x * W} ${pe.y * H})`}
            style={{ transition: "transform 400ms cubic-bezier(.23,1,.32,1)" }}
            role="button"
            tabIndex={0}
            aria-label={`Pessoa ${pe.track_id} em ${cam.nome}`}
            onClick={() => onPessoa(cam, pe)}
            onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onPessoa(cam, pe)}
          >
            {pe.estado !== "conforme" && <circle r="20" className="anel" />}
            <circle r="12" />
            <text y="-18" textAnchor="middle">
              {pe.track_id}
            </text>
          </g>
        )),
      )}
    </svg>
  );
}
