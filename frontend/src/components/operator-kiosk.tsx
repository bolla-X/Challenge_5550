import { useEffect, useState } from "react";

import { useDashboardStore } from "../store/dashboardStore";

import { MuteToggle } from "./layout";

import { getCameraStatus, startCamera } from "../api/endpoints";

import type { Alert, MonitorStatus } from "../api/types";

import { PPE_KEYS, PPE_LABELS } from "../api/ppe";



// Só os itens de EPI (helmet/vest/gloves) viram chip de conformidade no

// rodapé — pose/quedas/postura/área de risco não têm um "objeto vestível"

// pra checar visualmente, então ficariam sem sentido como ✓/✗ pro Operador.

const COMPLIANCE_KEYS = PPE_KEYS;

const COMPLIANCE_LABELS = PPE_LABELS;



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

 * Tela do Operador — monitor de status da câmera do setor dele. Tudo real

 * agora (Fase A, Passo 6): vídeo via /api/cameras/<id>/video_feed, status

 * (running/alertas) via GET /api/cameras/<id>/status com polling — cada

 * câmera é isolada de verdade: cada CameraWorker guarda seu próprio

 * AlertStateService e todo alerta/evento nasce com `camera_id` (coluna real

 * em app/models.py + migração a1b2c3d4e5f6).

 * Deliberadamente SEM sidebar, SEM abas, SEM navegação — é um kiosk, não

 * "mais uma tela do sistema".

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



  const handleStart = () => {

    setStarting(true);

    startCamera(camId)

      .then(setStatus)

      .catch((err) => console.error(err))

      .finally(() => setStarting(false));

  };



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

          <span className={`status-dot ${running ? "ok" : "warn"}`} />

          {running ? "recebendo" : "parado"}

        </span>

        <span className="kiosk-cam-name">{camera.name}</span>

        {running ? (

          <img src={`/api/cameras/${camId}/video_feed`} alt={`Feed de vídeo — ${camera.name}`} />

        ) : (

          <div className="kiosk-video-empty">

            <p>{status === null ? "Carregando…" : "Sem sinal — monitoramento parado."}</p>

            <button type="button" disabled={starting} onClick={handleStart}>

              {starting ? "Iniciando…" : "Iniciar"}

            </button>

          </div>

        )}

      </div>



      <div className="kiosk-footer">

        <div className="kiosk-compliance-row">

          {COMPLIANCE_KEYS.filter((key) => camera.features[key]).map((key) => {

            const violated = activeAlerts.some((a) => a.feature === key);

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



      {hasAlert && primaryAlert && (

        // Os dois botões batem no backend de verdade agora

        // (POST /alerts/<id>/acknowledge e /false-positive). Antes eram

        // window.alert() em cima de uma fila em memória que nenhuma tela lia —

        // o operador achava que tinha reportado algo que ninguém receberia.

        // O feedback vai pra MessageBar do store, não pra um modal nativo que

        // trava a tela inteira num kiosk de chão de fábrica.

        <div className="kiosk-report-row">

          <button

            type="button"

            className="kiosk-report-btn"

            disabled={actionPending !== null}

            onClick={() => {

              setActionPending("ack");

              acknowledgeAlert(primaryAlert.id).finally(() => setActionPending(null));

            }}

          >

            {actionPending === "ack" ? "Registrando…" : "✓ Avisei o colaborador"}

          </button>

          <button

            type="button"

            className="kiosk-report-btn"

            disabled={actionPending !== null}

            onClick={() => {

              setActionPending("fp");

              markFalsePositive(primaryAlert.id, "Reportado pelo Operador no kiosk").finally(() => setActionPending(null));

            }}

          >

            {actionPending === "fp" ? "Enviando…" : "🚩 Marcar falso positivo"}

          </button>

        </div>

      )}

    </div>

  );

}