import { useMemo, useState } from "react";
import { useDashboardStore } from "../store/dashboardStore";
import { Panel, Badge, EmptyState } from "./common";
import type { Alert } from "../api/types";

const SEVERITY_ORDER: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3, info: 4 };

function formatDate(value: string | null): string {
  if (!value) return new Date().toLocaleString();
  return new Date(value).toLocaleString();
}

function AlertCard({ alert, active }: { alert: Alert; active: boolean }) {
  const markFalsePositive = useDashboardStore((s) => s.markFalsePositive);
  const meta = alert.metadata || {};
  const subject = (meta.person_label as string) || (meta.person_id as string) || (meta.subject as string) || "global";
  const cls = ["alert", alert.severity, alert.status, alert.false_positive ? "false-positive" : ""].filter(Boolean).join(" ");

  return (
    <div className={cls}>
      <strong>{alert.message}</strong>
      <div>
        {alert.rule || ""} · {alert.feature || ""} · {alert.severity || ""} · {alert.status || "active"} · {subject}
      </div>
      <span className="alert-time">
        visto: {formatDate(alert.last_seen_at)}
        {alert.resolved_at ? ` · resolvido: ${formatDate(alert.resolved_at)}` : ""}
      </span>
      <div className="alert-actions">
        {alert.frame_ref ? (
          <a className="evidence-link" href={`/alerts/${alert.id}/evidence`} target="_blank" rel="noopener noreferrer">
            Ver evidência
          </a>
        ) : (
          <span className="muted">Sem snapshot</span>
        )}
        {alert.false_positive ? (
          <span className="false-positive-label">Falso positivo</span>
        ) : active ? (
          <button className="secondary small" type="button" onClick={() => markFalsePositive(alert.id)}>
            Falso positivo
          </button>
        ) : null}
      </div>
    </div>
  );
}

export function ActiveAlertsPanel() {
  const activeAlerts = useDashboardStore((s) => s.activeAlerts);
  const sorted = useMemo(
    () => [...activeAlerts].sort((a, b) => (SEVERITY_ORDER[a.severity] ?? 9) - (SEVERITY_ORDER[b.severity] ?? 9)),
    [activeAlerts],
  );
  return (
    <Panel
      title="Alertas ativos"
      description="Somem automaticamente quando a condição normal é confirmada."
      className={`alert-panel ${sorted.length ? "has-active-alerts" : ""}`.trim()}
      action={<Badge tone={sorted.length ? "error" : "ok"}>{sorted.length}</Badge>}
    >
      <div className="alerts">
        {sorted.length ? sorted.map((alert) => <AlertCard key={alert.id} alert={alert} active />) : <EmptyState>Nenhum alerta ativo.</EmptyState>}
      </div>
    </Panel>
  );
}

export function AlertHistoryPanel() {
  const alertHistory = useDashboardStore((s) => s.alertHistory);
  const [statusFilter, setStatusFilter] = useState("");
  const [severityFilter, setSeverityFilter] = useState("");

  const filtered = alertHistory.filter((alert) => {
    if (statusFilter && alert.status !== statusFilter) return false;
    if (severityFilter && alert.severity !== severityFilter) return false;
    return true;
  });

  return (
    <Panel title="Histórico recente" description="Auditoria local de alertas persistidos." className="technical-only">
      <div className="filter-row">
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">Todos</option>
          <option value="active">Ativos</option>
          <option value="resolved">Resolvidos</option>
        </select>
        <select value={severityFilter} onChange={(e) => setSeverityFilter(e.target.value)}>
          <option value="">Todas severidades</option>
          <option value="critical">Crítico</option>
          <option value="high">Alto</option>
          <option value="medium">Médio</option>
          <option value="low">Baixo</option>
          <option value="info">Info</option>
        </select>
      </div>
      <div className="alerts history">
        {filtered.length ? filtered.map((alert) => <AlertCard key={alert.id} alert={alert} active={false} />) : <EmptyState>Nenhum registro.</EmptyState>}
      </div>
    </Panel>
  );
}
