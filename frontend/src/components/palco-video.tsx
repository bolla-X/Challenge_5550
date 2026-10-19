import { incidenteCritico, useCameraEstado } from "./camera-grid";
import type { EstadoDaCamera } from "./camera-grid";
import { formatarVelocidade } from "./feed-status";
import { rotuloDoIncidente } from "../utils/incidentes";
import { LiveVideo } from "./live-video";

/** Vídeo de uma câmera na cena do palco (compartilhado entre `palco.tsx` e as cenas de `palco-cenas.tsx`). */

export function VideoDaCena({ cameraId }: { cameraId: number }) {
  return <QuadroDaCena cameraId={cameraId} estado={useCameraEstado(cameraId)} />;
}

/** Vídeo da cena com a pílula do incidente e, em câmera lenta, a velocidade
 * que o SERVIDOR informa (`video.velocidade`) — nunca a que a cena pediu. */
export function QuadroDaCena({ cameraId, estado }: { cameraId: number; estado: EstadoDaCamera }) {
  const inc = incidenteCritico(estado);
  const lenta = estado.velocidade !== undefined && estado.velocidade < 1;
  return (
    <div className="palco-video" data-testid="palco-video">
      <LiveVideo cameraId={cameraId} label="Vídeo da cena" />
      {lenta && (
        <span className="over-pill palco-velocidade" data-testid="palco-velocidade">
          {`GRAVAÇÃO · ${formatarVelocidade(estado.velocidade as number)}`}
        </span>
      )}
      {inc && (
        <span className="over-pill alert palco-pilula" role="status" data-testid="pilula-incidente">
          <span className="dot" />
          {rotuloDoIncidente(inc)}
        </span>
      )}
    </div>
  );
}
