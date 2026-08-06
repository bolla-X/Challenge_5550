import { useDashboardStore } from "../store/dashboardStore";
import { Panel, EmptyState, PanelSkeleton } from "./common";
import { listEvents } from "../api/endpoints";

function formatTime(value: string | null): string {
  if (!value) return new Date().toLocaleTimeString();
  return new Date(value).toLocaleTimeString();
}

// Backend sempre prefixa a mensagem com "Alerta resolvido:" ou "Falso
// positivo resolvido:" (monitor_service.py) — redundante aqui porque o
// cabeçalho do painel já diz "alertas resolvidos". Só formatação de
// exibição, não mexe no dado.
function stripResolvedPrefix(message: string): string {
  return message.replace(/^(Falso positivo resolvido|Alerta resolvido):\s*/, "");
}

export function TimelineCard() {
  const timeline = useDashboardStore((s) => s.timeline);
  const bootstrapping = useDashboardStore((s) => s.bootstrapping);

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

  return (
    <Panel
      id="panel-timeline"
      title="Linha do tempo"
      description="Alertas que já estiveram ativos e foram resolvidos."
      action={
        <button className="secondary small" type="button" onClick={() => refresh()}>
          Atualizar
        </button>
      }
    >
      {timeline.length === 0 ? (
        <EmptyState>Nenhum alerta resolvido neste ciclo.</EmptyState>
      ) : (
        <div className="timeline-list">
          {timeline.map((event) => {
            const alert = (event.metadata?.alert as Record<string, unknown>) || {};
            // Todo item aqui já é "resolvido" (o cabeçalho do painel diz
            // isso) — a metadata só precisa acrescentar o que muda de item
            // pra item: subject/feature (deduplicados quando iguais) e se
            // foi falso positivo.
            const feature = typeof alert.feature === "string" ? alert.feature : null;
            const detail = [event.subject, feature && feature !== event.subject ? feature : null, alert.false_positive ? "falso positivo" : null]
              .filter(Boolean)
              .join(" · ");
            return (
              <div className="timeline-row" key={event.id}>
                <span className={`timeline-dot ${event.severity || "info"}`} />
                <div className="timeline-row-body">
                  <span className="timeline-time">{formatTime(event.created_at)}</span>
                  <strong>{stripResolvedPrefix(event.message)}</strong>
                  <small>{detail || event.event_type || ""}</small>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </Panel>
  );
}
