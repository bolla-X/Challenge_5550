import { useEffect, useState } from "react";
import { useDashboardStore } from "../store/dashboardStore";
import { MuteToggle } from "./layout";
import { getCameraStatus, startCamera } from "../api/endpoints";
import type { Alert, MonitorStatus } from "../api/types";
import { PPE_KEYS, PPE_LABELS } from "../api/ppe";

// Só os itens de EPI viram chip de conformidade no rodapé: pose/quedas/
// postura/área de risco não têm um "objeto vestível" pra checar.
const COMPLIANCE_KEYS = PPE_KEYS;
const COMPLIANCE_LABELS = PPE_LABELS;

type KioskState = "ok" | "warn" | "critical";

function kioskStateFromAlerts(running: boolean, alerts: Alert[]): KioskState {
  if (!running) return "warn";
  if (alerts.some((a) => a.severity === "critical" || a.severity === "high")) return "critical";
  if (alerts.length > 0) return "warn";
  return "ok";
}

/**
 * Tela do Operador: monitor de status da câmera do setor dele. Vídeo via
 * /api/cameras/<id>/video_feed, status (running/alertas) via GET
 * /api/cameras/<id>/status com polling. Deliberadamente SEM sidebar, SEM
 * abas, SEM navegação: é um kiosk, não "mais uma tela do sistema".
 */
export function OperatorKiosk({ camId }: { camId: number }) {
  const camera = useDashboardStore((s) => s.cameras.find((c) => c.id === camId));
  const markFalsePositive = useDashboardStore((s) => s.markFalsePositive);
  const acknowledgeAlert = useDashboardStore((s) => s.acknowledgeAlert);
  const [actionPending, setActionPending] = useState<"ack" | "fp" | null>(null);
  const [status, setStatus] = useState<MonitorStatus | null>(null);
  const [starting, setStarting] = useState(false);

  useEffect(() => {
    setStatus(null);
    let cancelled = false;
    const refresh = () => {
      getCameraStatus(camId)
        .then((s) => {
          if (!cancelled) setStatus(s);
        })
        .catch(() => {
          if (!cancelled) setStatus(null);
        });
    };
    refresh();
    const interval = setInterval(refresh, 2000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [camId]);

  if (!camera) return null;

  const running = Boolean(status?.running);
  const activeAlerts = status?.active_alerts ?? [];
  const state = kioskStateFromAlerts(running, activeAlerts);
  const critical = activeAlerts.find((a) => a.severity === "critical" || a.severity === "high");
  const primaryAlert = critical || activeAlerts[0] || null;
  const hasAlert = running && activeAlerts.length > 0;

  const bannerTitle = !running ? "Monitoramento parado" : primaryAlert ? primaryAlert.message : "Tudo conforme";
  const bannerSub = !running
    ? "Inicie o monitoramento para começar a receber o feed em tempo real."
    : primaryAlert
      ? [primaryAlert.rule, primaryAlert.feature].filter(Boolean).join(" · ")
      : "Nenhum alerta ativo no momento.";

  const handleStart = () => {
    setStarting(true);
    startCamera(camId)
      .then(setStatus)
      .catch((err) => console.error(err))
      .finally(() => setStarting(false));
  };

  return (
    <div className="kiosk-wrap">
      <div className={`card kiosk-banner ${state}`} role="status">
        <span className="dot" />
        <div>
          <h2>{bannerTitle}</h2>
          <p>{bannerSub}</p>
        </div>
      </div>

      <div className={`card kiosk-video ${state === "critical" ? "critical" : ""}`.trim()}>
        <div className="over-video">
          <span className="over-pill">
            <span className={`dot ${running ? "ok" : "off"}`} />
            {running ? "Recebendo" : "Parado"}
          </span>
          <span className="over-pill">{camera.name}</span>
        </div>
        {running ? (
          <img src={`/api/cameras/${camId}/video_feed`} alt={`Vídeo de ${camera.name}`} />
        ) : (
          <div className="kiosk-video-empty">
            <p>{status === null ? "Carregando…" : "Sem sinal, monitoramento parado."}</p>
            <button type="button" className="primary" disabled={starting} onClick={handleStart}>
              {starting ? "Iniciando…" : "Iniciar"}
            </button>
          </div>
        )}
      </div>

      <div className="kiosk-footer">
        <div className="actions">
          {COMPLIANCE_KEYS.filter((key) => camera.features[key]).map((key) => {
            const violated = activeAlerts.some((a) => a.feature === key);
            return (
              <span key={key} className={`chip ${violated ? "miss" : "ok"}`}>
                <span className="dot" />
                {COMPLIANCE_LABELS[key]}
              </span>
            );
          })}
          {COMPLIANCE_KEYS.every((key) => !camera.features[key]) && <span className="chip">Nenhum recurso de EPI ativo nesta câmera</span>}
        </div>
        <MuteToggle />
      </div>

      {hasAlert && primaryAlert && (
        // Os dois botões batem no backend (POST /alerts/<id>/acknowledge e
        // /false-positive). O feedback vai pra MessageBar do store, não pra
        // um modal nativo que trava a tela inteira num kiosk.
        <div className="kiosk-actions">
          <button
            type="button"
            disabled={actionPending !== null}
            onClick={() => {
              setActionPending("ack");
              acknowledgeAlert(primaryAlert.id).finally(() => setActionPending(null));
            }}
          >
            {actionPending === "ack" ? "Registrando…" : "Avisei o colaborador"}
          </button>
          <button
            type="button"
            disabled={actionPending !== null}
            onClick={() => {
              setActionPending("fp");
              markFalsePositive(primaryAlert.id, "Reportado pelo Operador no kiosk").finally(() => setActionPending(null));
            }}
          >
            {actionPending === "fp" ? "Enviando…" : "Marcar falso positivo"}
          </button>
        </div>
      )}
    </div>
  );
}
