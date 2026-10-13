import { useEffect, useMemo, useRef, useState } from "react";
import { useDashboardStore } from "../store/dashboardStore";
import { playGateApprovedChime } from "../audio/chime";
import { LiveVideo } from "./live-video";
import { getPortal, startCamera } from "../api/endpoints";
import type { PortalItem, PortalState } from "../api/types";
import { PPE_LABELS } from "../api/ppe";

/**
 * Portal de Entrada (G1), em `/portal?camera=N`: a pessoa para diante da câmera
 * e vê só os EPIs exigidos para aquele setor, cada um como confirmado, faltando
 * ou "não verificável neste enquadramento". Libera quando todo item
 * verificável está confirmado por algumas análises seguidas (o servidor decide;
 * a tela só mostra). Nenhuma foto é salva; o check-in conta para a meta do setor.
 */

const ROTULO_ESTADO: Record<PortalItem["estado"], string> = {
  confirmado: "Confirmado",
  faltando: "Faltando",
  nao_verificavel: "Não verificável neste enquadramento",
};

function cameraDaUrl(): number | null {
  const valor = new URLSearchParams(window.location.search).get("camera");
  return valor && /^\d+$/.test(valor) ? Number(valor) : null;
}

function usePortal(camId: number | null): PortalState | null {
  const [estado, setEstado] = useState<PortalState | null>(null);
  const anterior = useRef<PortalState["verdict"] | null>(null);
  useEffect(() => {
    if (camId == null) return;
    let vivo = true;
    const tick = () =>
      getPortal(camId)
        .then((p) => {
          if (!vivo) return;
          setEstado(p);
          if (anterior.current !== null && anterior.current !== "approved" && p.verdict === "approved" && !useDashboardStore.getState().muted) {
            playGateApprovedChime();
          }
          anterior.current = p.verdict;
        })
        .catch(() => vivo && setEstado(null));
    tick();
    const id = window.setInterval(tick, 600);
    return () => {
      vivo = false;
      window.clearInterval(id);
    };
  }, [camId]);
  return estado;
}

function Item({ item, indice }: { item: PortalItem; indice: number }) {
  const nome = PPE_LABELS[item.key as keyof typeof PPE_LABELS] ?? item.key;
  return (
    <li className={`portal-item ${item.estado}`} style={{ animationDelay: `${indice * 70}ms` }} data-testid={`portal-item-${item.key}`} data-estado={item.estado}>
      <span className="portal-marca" aria-hidden="true" />
      <span className="portal-nome">{nome}</span>
      <span className="portal-estado">
        {ROTULO_ESTADO[item.estado]}
        {item.motivo ? <small> · {item.motivo}</small> : null}
      </span>
    </li>
  );
}

export function PortalScreen() {
  const cameras = useDashboardStore((s) => s.cameras);
  const camId = useMemo(() => {
    const pedida = cameraDaUrl();
    if (pedida != null && cameras.some((c) => c.id === pedida)) return pedida;
    return (cameras.find((c) => c.gate_required) ?? cameras[0])?.id ?? null;
  }, [cameras]);
  const camera = cameras.find((c) => c.id === camId);
  const portal = usePortal(camId);
  const [iniciando, setIniciando] = useState(false);

  if (camId == null || !camera) return <p className="centered-empty">Nenhuma câmera disponível para o portal.</p>;
  const veredito = portal?.verdict ?? "waiting";
  const titulo =
    veredito === "approved" ? "Liberado" : veredito === "denied" ? "Confira seus EPIs" : veredito === "off" ? "Portal desligado" : "Posicione-se diante da câmera";

  return (
    <div className={`portal ${veredito}`} data-testid="portal" data-veredito={veredito}>
      <header className="portal-cabeca">
        <span className="portal-camera">{camera.name} · Portal de Entrada</span>
        <span className="portal-contagem t-data" data-testid="portal-checkins">
          {portal?.checkins ?? 0} check-in{portal?.checkins === 1 ? "" : "s"} neste turno
        </span>
      </header>
      <div className="portal-corpo">
        <div className="portal-video card">
          <LiveVideo cameraId={camId} label={`Vídeo de ${camera.name}`} />
          <button
            type="button"
            className="ghost small portal-iniciar"
            disabled={iniciando}
            onClick={() => {
              setIniciando(true);
              startCamera(camId).finally(() => setIniciando(false));
            }}
          >
            {iniciando ? "Iniciando…" : "Iniciar câmera"}
          </button>
        </div>
        <section className="portal-lado" aria-live="polite">
          <h1 className="portal-titulo" data-testid="portal-titulo">{titulo}</h1>
          {veredito === "off" ? (
            <p className="muted">Escolha os EPIs exigidos na aba “Portaria” da câmera para ligar o portal.</p>
          ) : (
            <ol className="portal-lista">
              {(portal?.itens.length ? portal.itens : (portal?.required ?? []).map((k) => ({ key: k, estado: "nao_verificavel", motivo: "aguardando pessoa" }) as PortalItem)).map(
                (item, i) => <Item key={item.key} item={item} indice={i} />,
              )}
            </ol>
          )}
          <p className="portal-nota muted">Nenhuma foto é salva. “Não verificável” não conta como confirmado nem como falta.</p>
        </section>
      </div>
    </div>
  );
}
