import type { CameraRecord } from "../api/types";
import type { EstadoDaCamera } from "./camera-grid";
import type { EstadoDoStream } from "./live-video";

/**
 * Os cinco estados do feed, inconfundíveis e na mesma ordem de prioridade em
 * toda tela (foco, quiosque, grade). Quem está olhando o projetor a 5 m precisa
 * saber, sem ler o resto: o vídeo é de agora? é gravação? caiu? está reduzido?
 *
 * - SEM SINAL: a câmera roda, mas nenhum quadro chega há > 3 s (ou a imagem
 *   está preta) — o pior caso, porque a tela parece "parada" e não "quebrada";
 * - RECONECTANDO: a fonte caiu e o backend está tentando voltar (backoff);
 * - GRAVAÇÃO: a fonte é um arquivo (fixture de demonstração), não câmera ao vivo;
 * - AO VIVO: câmera real entregando quadro.
 *
 * DEGRADADO não substitui nenhum destes: é um aviso À PARTE (o vídeo pode estar
 * AO VIVO e degradado ao mesmo tempo), e diz o que foi reduzido.
 */
/** 0.25 → "0,25×": a velocidade da gravação como a tela escreve. */
export function formatarVelocidade(v: number): string {
  return `${v.toLocaleString("pt-BR", { maximumFractionDigits: 2 })}×`;
}

export type ChaveDoFeed = "parado" | "sem_sinal" | "reconectando" | "gravacao" | "ao_vivo";

export function estadoDoFeed(
  estado: EstadoDaCamera,
  camera: Pick<CameraRecord, "source_type"> | undefined,
  stream?: EstadoDoStream,
): { chave: ChaveDoFeed; rotulo: string } {
  if (!estado.running) return { chave: "parado", rotulo: "Parado" };
  if (stream === "sem_sinal" || estado.diagnostico?.fonte_sem_imagem) return { chave: "sem_sinal", rotulo: "Sem sinal" };
  if (estado.modo === "reconectando" || stream === "reconectando") {
    return { chave: "reconectando", rotulo: `Reconectando${estado.tentativas ? ` · tentativa ${estado.tentativas + 1}` : ""}` };
  }
  if (estado.modo === "fixture" || camera?.source_type === "Arquivo") {
    const lenta = estado.velocidade !== undefined && estado.velocidade < 1;
    return { chave: "gravacao", rotulo: lenta ? `Gravação · ${formatarVelocidade(estado.velocidade as number)}` : "Gravação" };
  }
  return { chave: "ao_vivo", rotulo: "Ao vivo" };
}

export function FeedBadge({
  estado,
  camera,
  stream,
  className = "",
}: {
  estado: EstadoDaCamera;
  camera?: Pick<CameraRecord, "source_type">;
  stream?: EstadoDoStream;
  className?: string;
}) {
  const { chave, rotulo } = estadoDoFeed(estado, camera, stream);
  return (
    <span className={`feed-badge ${className}`.trim()} data-estado={chave} role="status" aria-live="polite">
      <span className="feed-badge-dot" aria-hidden="true" />
      {rotulo}
    </span>
  );
}

/** Aviso de degradação: o que o controlador adaptativo reduziu, em português. */
export function AvisoDegradado({ estado }: { estado: EstadoDaCamera }) {
  const modo = estado.adaptativo;
  if (!estado.running || !modo?.degradado) return null;
  return (
    <div className="aviso-degradado" role="status" data-testid="aviso-degradado">
      <strong>Degradado</strong>
      <span>{modo.reducoes.join(" · ")}</span>
    </div>
  );
}
