import { useEffect, useMemo, useState } from "react";
import qrcodegen from "../vendor/qrcodegen";
import { Panel } from "./common";

type Pareamento = { caminho: string; url_lan: string | null; https: boolean; aviso: string | null };

/** QR como SVG: um <path> com um quadradinho por módulo escuro, borda de 4 módulos (norma do QR). */
export function QrSvg({ texto, rotulo = "QR code para abrir a câmera no celular" }: { texto: string; rotulo?: string }) {
  const caminho = useMemo(() => {
    const qr = qrcodegen.QrCode.encodeText(texto, qrcodegen.QrCode.Ecc.MEDIUM);
    const partes: string[] = [];
    for (let y = 0; y < qr.size; y++) {
      for (let x = 0; x < qr.size; x++) {
        if (qr.getModule(x, y)) partes.push(`M${x + 4},${y + 4}h1v1h-1z`);
      }
    }
    return { d: partes.join(""), lado: qr.size + 8 };
  }, [texto]);
  return (
    <svg
      className="qr"
      viewBox={`0 0 ${caminho.lado} ${caminho.lado}`}
      role="img"
      aria-label={rotulo}
      shapeRendering="crispEdges"
    >
      <rect width="100%" height="100%" fill="#FFFFFF" />
      <path d={caminho.d} fill="#000000" />
    </svg>
  );
}

/**
 * Pareamento do celular como câmera (F6). O QR leva ao endereço desta máquina
 * na rede local; o celular só libera a câmera em HTTPS (contexto seguro).
 */
export function CelularQr({ cameraId }: { cameraId: number }) {
  const [par, setPar] = useState<Pareamento | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    let vivo = true;
    fetch(`/api/cameras/${cameraId}/celular`, { credentials: "same-origin" })
      .then(async (r) => {
        const d = await r.json();
        if (!vivo) return;
        if (r.ok) setPar(d as Pareamento);
        else setErro(d.error || "Não foi possível obter o pareamento.");
      })
      .catch(() => vivo && setErro("Não foi possível obter o pareamento."));
    return () => {
      vivo = false;
    };
  }, [cameraId]);

  const url = par ? par.url_lan || `${window.location.origin}${par.caminho}` : null;
  return (
    <Panel title="Celular como câmera" description="Leia o QR code com a câmera do celular e toque em Iniciar câmera.">
      {erro && <p className="status-text error">{erro}</p>}
      {url && (
        <div className="celular-qr" data-testid="celular-qr">
          <QrSvg texto={url} />
          <div className="celular-qr-texto">
            <code>{url}</code>
            {par?.aviso && <p className="status-text error">{par.aviso}</p>}
            <p className="hint">O link vale só para esta câmera. Quem tiver o link pode enviar imagem para ela; não dá acesso ao painel.</p>
          </div>
        </div>
      )}
    </Panel>
  );
}
