import { useEffect, useMemo, useRef, useState } from "react";
import { useDashboardStore } from "../store/dashboardStore";
import { playGateApprovedChime } from "../audio/chime";
import { LiveVideo } from "./live-video";
import { useCameraEstado } from "./camera-grid";
import { getPortal, startCamera } from "../api/endpoints";
import type { PortalItem, PortalState } from "../api/types";
import { PPE_LABELS } from "../api/ppe";
import { EnganarIA } from "./enganar-ia";
import { pluralizar } from "../utils/formato";

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

function Item({ item, indice, explicar }: { item: PortalItem; indice: number; explicar: boolean }) {
  const nome = PPE_LABELS[item.key as keyof typeof PPE_LABELS] ?? item.key;
  return (
    <li className={`portal-item ${item.estado}`} style={{ animationDelay: `${indice * 70}ms` }} data-testid={`portal-item-${item.key}`} data-estado={item.estado}>
      <span className="portal-marca" aria-hidden="true" />
      <span className="portal-nome">{nome}</span>
      <span className="portal-estado">
        {ROTULO_ESTADO[item.estado]}
        {item.motivo ? <small> · {item.motivo}</small> : null}
        {explicar && item.explicacao ? <small className="portal-explicacao"> · {item.explicacao}</small> : null}
      </span>
    </li>
  );
}

export function PortalScreen({ cameraId, desafioInicial }: { cameraId?: number | null; desafioInicial?: boolean } = {}) {
  const cameras = useDashboardStore((s) => s.cameras);
  const camId = useMemo(() => {
    const pedida = cameraId ?? cameraDaUrl();
    if (pedida != null && cameras.some((c) => c.id === pedida)) return pedida;
    return (cameras.find((c) => c.gate_required) ?? cameras[0])?.id ?? null;
  }, [cameras, cameraId]);
  const camera = cameras.find((c) => c.id === camId);
  const portal = usePortal(camId);
  // X9: `?desafio=1` (ou o botão) liga o modo "Tente enganar a IA" com o Raio-X.
  const [desafio, setDesafio] = useState(() => desafioInicial ?? new URLSearchParams(window.location.search).get("desafio") === "1");
  const raioX = useDashboardStore((s) => s.raioX);
  useEffect(() => {
    if (desafio && !useDashboardStore.getState().raioX) useDashboardStore.getState().alternarRaioX();
  }, [desafio]);

  if (camId == null || !camera) return <p className="centered-empty">Nenhuma câmera disponível para o portal.</p>;
  const veredito = portal?.verdict ?? "waiting";
  const titulo =
    veredito === "approved" ? "Liberado" : veredito === "denied" ? "Confira seus EPIs" : veredito === "off" ? "Portal desligado" : "Posicione-se diante da câmera";

  return (
    <div className={`portal ${veredito}`} data-testid="portal" data-veredito={veredito}>
      <header className="portal-cabeca">
        <span className="portal-camera">{camera.name} · Portal de Entrada</span>
        <span className="portal-contagem t-data" data-testid="portal-checkins">
          {pluralizar(portal?.checkins ?? 0, "check-in")} neste turno
        </span>
        <button type="button" className={`ghost small ${desafio ? "active" : ""}`} aria-pressed={desafio} onClick={() => setDesafio((d) => !d)} data-testid="portal-desafio">
          Tente enganar a IA
        </button>
      </header>
      <div className="portal-corpo">
        <div className="portal-video card">
          <LiveVideo cameraId={camId} label={`Vídeo de ${camera.name}`} />
          <IniciarSeParada camId={camId} />
        </div>
        <section className="portal-lado" aria-live="polite">
          <h1 className="portal-titulo" data-testid="portal-titulo">{titulo}</h1>
          {veredito === "off" ? (
            <p className="muted">Escolha os EPIs exigidos na aba “Portaria” da câmera para ligar o portal.</p>
          ) : (
            <ol className="portal-lista">
              {(portal?.itens.length ? portal.itens : (portal?.required ?? []).map((k) => ({ key: k, estado: "nao_verificavel", motivo: "aguardando pessoa" }) as PortalItem)).map(
                (item, i) => <Item key={item.key} item={item} indice={i} explicar={desafio || raioX} />,
              )}
            </ol>
          )}
          <p className="portal-nota muted">Nenhuma foto é salva. “Não verificável” não conta como confirmado nem como falta.</p>
          {desafio && <EnganarIA portal={portal} />}
        </section>
      </div>
    </div>
  );
}

/** "Iniciar câmera" só aparece com a câmera parada: ligada, o vídeo fala por si. */
export function IniciarSeParada({ camId }: { camId: number }) {
  const estado = useCameraEstado(camId);
  const [iniciando, setIniciando] = useState(false);
  if (estado.running) return null;
  return (
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
  );
}
