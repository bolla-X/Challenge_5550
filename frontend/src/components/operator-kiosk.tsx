import { useDashboardStore } from "../store/dashboardStore";
import { MuteToggle, useVideoStreamLabel } from "./layout";
import type { Alert } from "../api/types";

// Só os itens de EPI (helmet/vest/gloves) viram chip de conformidade no
// rodapé — pose/quedas/postura/área de risco não têm um "objeto vestível"
// pra checar visualmente, então ficariam sem sentido como ✓/✗ pro Operador.
const COMPLIANCE_KEYS: ("helmet" | "vest" | "gloves")[] = ["helmet", "vest", "gloves"];
const COMPLIANCE_LABELS: Record<string, string> = { helmet: "Capacete", vest: "Colete", gloves: "Luvas" };

function CheckIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M5 13l4 4L19 7" />
    </svg>
  );
}
function CrossIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M6 6l12 12M18 6L6 18" />
    </svg>
  );
}
function WarningIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 9v4M12 17h.01" />
      <path d="M10.3 3.9 2.5 18a2 2 0 0 0 1.7 3h15.6a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" />
    </svg>
  );
}

type KioskState = "ok" | "warn" | "critical";

function kioskStateFromAlerts(running: boolean, alerts: Alert[]): KioskState {
  if (!running) return "warn";
  if (alerts.some((a) => a.severity === "critical")) return "critical";
  if (alerts.length > 0) return "warn";
  return "ok";
}

/**
 * Tela do Operador — monitor de status da câmera do setor dele. Vídeo,
 * conformidade e alertas vêm do backend REAL (único, ver conversa: "usa os
 * modelos que já tem, mesma câmera em todos por enquanto" — o backend
 * ainda é single-source, então qualquer camId mostra o mesmo feed físico).
 * Só nome/local/quais EPIs essa câmera "liga" continuam vindo do mock, até
 * o backend ganhar câmeras de verdade. Deliberadamente SEM sidebar, SEM
 * abas, SEM navegação — é um kiosk, não "mais uma tela do sistema".
 */
export function OperatorKiosk({ camId }: { camId: number }) {
  const camera = useDashboardStore((s) => s.cameras.find((c) => c.id === camId));
  const reportFalsePositive = useDashboardStore((s) => s.reportFalsePositive);
  const running = useDashboardStore((s) => s.running);
  const bootstrapping = useDashboardStore((s) => s.bootstrapping);
  const start = useDashboardStore((s) => s.start);
  const compliance = useDashboardStore((s) => s.compliance);
  const activeAlerts = useDashboardStore((s) => s.activeAlerts);
  const video = useVideoStreamLabel();

  if (!camera) return null;

  const state = kioskStateFromAlerts(running, activeAlerts);
  const critical = activeAlerts.find((a) => a.severity === "critical");
  const primaryAlert = critical || activeAlerts[0] || null;
  const hasAlert = running && activeAlerts.length > 0;

  const bannerIcon = state === "ok" ? <CheckIcon /> : <WarningIcon />;
  const bannerTitle = !running ? "Monitoramento parado" : primaryAlert ? primaryAlert.message : "Tudo conforme";
  const bannerSub = !running
    ? "Inicie o monitoramento pra começar a receber o feed em tempo real."
    : primaryAlert
      ? `${primaryAlert.rule} · ${primaryAlert.feature ?? ""}`
      : "Nenhum alerta ativo no momento.";

  return (
    <div className="kiosk-wrap">
      <div className={`kiosk-status-banner ${state}`}>
        <div className="kiosk-status-icon">{bannerIcon}</div>
        <div className="kiosk-status-text">
          <h2>{bannerTitle}</h2>
          <p>{bannerSub}</p>
        </div>
      </div>

      <div className={`kiosk-video-wrap ${state === "critical" ? "critical" : ""}`.trim()}>
        <span className="kiosk-live-tag">
          <span className={`status-dot ${running ? video.status : "warn"}`} />
          {running ? video.label : "parado"}
        </span>
        <span className="kiosk-cam-name">{camera.name}</span>
        {running ? (
          <img src="/video_feed" alt={`Feed de vídeo — ${camera.name}`} />
        ) : (
          <div className="kiosk-video-empty">
            <p>{bootstrapping ? "Carregando…" : "Sem sinal — monitoramento parado."}</p>
            {!bootstrapping && (
              <button type="button" onClick={() => start().catch((err) => console.error(err))}>
                Iniciar
              </button>
            )}
          </div>
        )}
      </div>

      <div className="kiosk-footer">
        <div className="kiosk-compliance-row">
          {COMPLIANCE_KEYS.filter((key) => camera.features[key]).map((key) => {
            const card = compliance?.ppe[key];
            const violated = card ? card.status === "missing" || card.status === "critical" : false;
            return (
              <span key={key} className={`kiosk-chip ${violated ? "bad" : "ok"}`}>
                {violated ? <CrossIcon /> : <CheckIcon />}
                {COMPLIANCE_LABELS[key]}
              </span>
            );
          })}
          {COMPLIANCE_KEYS.every((key) => !camera.features[key]) && <span className="kiosk-chip">Nenhuma feature de EPI ativa nesta câmera</span>}
        </div>
        <MuteToggle />
      </div>

      {hasAlert && (
        <div className="kiosk-report-row">
          <button type="button" className="kiosk-report-btn" onClick={() => alert("Marcado: colaborador avisado (mock, ainda não persiste).")}>
            ✓ Avisei o colaborador
          </button>
          <button
            type="button"
            className="kiosk-report-btn"
            onClick={() => {
              if (primaryAlert) reportFalsePositive(camera.id, primaryAlert.message);
              alert("Enviado pra fila de auditoria do Supervisor.");
            }}
          >
            🚩 Marcar falso positivo
          </button>
        </div>
      )}
    </div>
  );
}
