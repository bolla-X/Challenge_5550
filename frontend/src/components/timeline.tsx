import { motion, useReducedMotion } from "motion/react";
import { useDashboardStore } from "../store/dashboardStore";
import { Panel, EmptyState, PanelSkeleton } from "./common";
import { listEvents } from "../api/endpoints";

// Mesma curva de tokens.css (--ease-out).
const EASE = [0.23, 1, 0.32, 1] as const;

function formatTime(value: string | number | null): string {
  const date = value == null ? new Date() : new Date(value);
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

// Backend sempre prefixa a mensagem com "Alerta resolvido:" ou "Falso
// positivo resolvido:" (monitor_service.py). Redundante aqui porque o
// cabeçalho do painel já diz "alertas resolvidos". Só exibição.
function stripResolvedPrefix(message: string): string {
  return message.replace(/^(Falso positivo resolvido|Alerta resolvido):\s*/, "");
}

/** Uma trilha de 8 px com as marcas posicionadas pelo horário e três
 * horários embaixo. Sem régua, sem grade. */
function TimelineTrack({ items }: { items: { id: number; severity: string; at: number; label: string }[] }) {
  const min = Math.min(...items.map((i) => i.at));
  const max = Math.max(...items.map((i) => i.at));
  const span = max - min || 1;
  return (
    <div className="timeline-track-wrap">
      <div className="timeline-track" aria-hidden="true">
        {items.map((item) => (
          <span
            key={item.id}
            className={`timeline-mark ${item.severity}`}
            title={item.label}
            // Posição na trilha é calculada em runtime a partir do horário do evento.
            style={{ left: `${((item.at - min) / span) * 100}%` }}
          />
        ))}
      </div>
      <div className="timeline-axis">
        <span>{formatTime(min)}</span>
        <span>{formatTime((min + max) / 2)}</span>
        <span>{formatTime(max)}</span>
      </div>
    </div>
  );
}

export function TimelineCard() {
  const timeline = useDashboardStore((s) => s.timeline);
  const bootstrapping = useDashboardStore((s) => s.bootstrapping);
  const shouldReduceMotion = useReducedMotion();

  if (bootstrapping) {
    return (
      <Panel id="panel-timeline" title="Linha do tempo" description="Alertas que já estiveram ativos e foram resolvidos.">
        <PanelSkeleton lines={3} />
      </Panel>
    );
  }

  const refresh = async () => {
    try {
      const res = await listEvents({ limit: 80, eventType: "alert_resolved" });
      useDashboardStore.setState({ timeline: [...res.items].reverse() }, false, "refreshTimeline");
    } catch (error) {
      console.error(error);
    }
  };

  const marks = timeline.map((event) => ({
    id: event.id,
    severity: event.severity || "info",
    at: event.created_at ? new Date(event.created_at).getTime() : Date.now(),
    label: `${formatTime(event.created_at)} ${stripResolvedPrefix(event.message)}`,
  }));

  return (
    <Panel
      id="panel-timeline"
      title="Linha do tempo"
      description="Alertas que já estiveram ativos e foram resolvidos."
      action={
        <button className="ghost small" type="button" onClick={() => refresh()}>
          Atualizar
        </button>
      }
    >
      {timeline.length === 0 ? (
        <EmptyState>Nenhum alerta resolvido neste ciclo.</EmptyState>
      ) : (
        <>
          {marks.length >= 2 && <TimelineTrack items={marks} />}
          <div className="timeline-list">
            {timeline.map((event, index) => {
              const alert = (event.metadata?.alert as Record<string, unknown>) || {};
              const feature = typeof alert.feature === "string" ? alert.feature : null;
              const detail = [event.subject, feature && feature !== event.subject ? feature : null, alert.false_positive ? "falso positivo" : null]
                .filter(Boolean)
                .join(", ");
              return (
                // Stagger só no mount inicial: com key estável, um item que já
                // está montado nunca reexecuta `initial`. Limitado aos 10
                // primeiros pra não alongar listas longas.
                <motion.div
                  className="timeline-row"
                  key={event.id}
                  initial={shouldReduceMotion ? false : { opacity: 0, scale: 0.98 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ duration: shouldReduceMotion ? 0 : 0.2, ease: EASE, delay: shouldReduceMotion ? 0 : Math.min(index, 10) * 0.03 }}
                >
                  <span className={`dot ${event.severity || "info"}`} />
                  <div className="timeline-row-body">
                    <strong>{stripResolvedPrefix(event.message)}</strong>
                    <small>{detail || event.event_type || ""}</small>
                  </div>
                  <span className="timeline-time">{formatTime(event.created_at)}</span>
                </motion.div>
              );
            })}
          </div>
        </>
      )}
    </Panel>
  );
}
