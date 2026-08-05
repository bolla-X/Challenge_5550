import { useDashboardStore } from "../store/dashboardStore";
import { Panel, EmptyState } from "./common";
import { listEvents } from "../api/endpoints";

function formatTime(value: string | null): string {
  if (!value) return new Date().toLocaleTimeString();
  return new Date(value).toLocaleTimeString();
}

export function EventTimelinePanel() {
  const timeline = useDashboardStore((s) => s.timeline);

  const refresh = async () => {
    try {
      const res = await listEvents({ limit: 80, eventType: "alert_resolved" });
      useDashboardStore.setState({ timeline: [...res.items].reverse() }, false, "refreshTimeline");
    } catch (error) {
      console.error(error);
    }
  };

  return (
    <Panel
      title="Linha do tempo"
      description="Somente alertas que já estiveram ativos e foram resolvidos. Sem duplicar o mesmo alerta."
      action={
        <button className="secondary small" type="button" onClick={() => refresh()}>
          Atualizar
        </button>
      }
    >
      <div className="timeline">
        {timeline.length === 0 ? (
          <EmptyState>Nenhum alerta resolvido neste ciclo.</EmptyState>
        ) : (
          timeline.map((event) => {
            const alert = (event.metadata?.alert as Record<string, unknown>) || {};
            const detail = [event.subject, alert.feature, alert.false_positive ? "falso positivo" : "resolvido"].filter(Boolean).join(" · ");
            return (
              <div className={`timeline-item ${event.severity || "info"}`} key={event.id}>
                <span className="timeline-time">{formatTime(event.created_at)}</span>
                <div>
                  <strong>{event.message}</strong>
                  <small>{detail || event.event_type || ""}</small>
                </div>
              </div>
            );
          })
        )}
      </div>
    </Panel>
  );
}
