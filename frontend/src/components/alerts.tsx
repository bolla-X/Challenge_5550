import { useMemo, useState } from "react";
import { useDashboardStore } from "../store/dashboardStore";
import { Panel, Badge } from "./common";
import type { Alert } from "../api/types";

const SEVERITY_ORDER: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3, info: 4 };

function formatDate(value: string | null): string {
  if (!value) return new Date().toLocaleString();
  return new Date(value).toLocaleString();
}

function CheckIcon() {
  return (
    <svg viewBox="0 0 24 24">
      <path d="M5 13l4 4L19 7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function AlertRow({ alert, active }: { alert: Alert; active: boolean }) {
  const markFalsePositive = useDashboardStore((s) => s.markFalsePositive);
  const meta = alert.metadata || {};
  const subject = (meta.person_label as string) || (meta.person_id as string) || (meta.subject as string) || "global";
  const cls = ["alert-row", alert.resolved_at ? "resolved" : "", alert.false_positive ? "false-positive" : ""].filter(Boolean).join(" ");

  return (
    <div className={cls}>
      <span className={`alert-stripe ${alert.severity}`} />
      <div className="alert-row-body">
        <strong>{alert.message}</strong>
        <div className="alert-row-meta">
          {alert.rule} · {alert.feature} · {subject}
        </div>
        <span className="alert-row-time">
          visto: {formatDate(alert.last_seen_at)}
          {alert.resolved_at ? ` · resolvido: ${formatDate(alert.resolved_at)}` : ""}
        </span>
        <div className="alert-row-actions">
          {alert.frame_ref && (
            <a className="evidence-link" href={`/alerts/${alert.id}/evidence`} target="_blank" rel="noopener noreferrer">
              Ver evidência
            </a>
          )}
          {alert.false_positive ? (
            <span className="false-positive-label">Falso positivo</span>
          ) : (
            active && (
              <button className="secondary small" type="button" onClick={() => markFalsePositive(alert.id)}>
                Falso positivo
              </button>
            )
          )}
        </div>
      </div>
    </div>
  );
}

/** Calm by default — a quiet, reassuring "all clear" moment, not an empty
 * div. Only grows louder (accent stripe per severity) with a real alert. */
export function AlertPanel() {
  const activeAlerts = useDashboardStore((s) => s.activeAlerts);
  const sorted = useMemo(
    () => [...activeAlerts].sort((a, b) => (SEVERITY_ORDER[a.severity] ?? 9) - (SEVERITY_ORDER[b.severity] ?? 9)),
    [activeAlerts],
  );

  return (
    <Panel title="Alertas ativos" description="Somem automaticamente quando a condição normal é confirmada." action={sorted.length ? <Badge tone="error">{sorted.length}</Badge> : undefined}>
      <div className="alert-card-body">
        {sorted.length ? (
          sorted.map((alert) => <AlertRow key={alert.id} alert={alert} active />)
        ) : (
          <div className="all-clear">
            <div className="all-clear-badge">
              <CheckIcon />
            </div>
            <div>
              <strong>Tudo certo por aqui</strong>
              <span>Nenhum alerta ativo no momento.</span>
            </div>
          </div>
        )}
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
    <Panel title="Histórico recente" description="Auditoria local de alertas persistidos.">
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
        {filtered.length ? (
          filtered.map((alert) => <AlertRow key={alert.id} alert={alert} active={false} />)
        ) : (
          <div className="all-clear">
            <div className="all-clear-badge">
              <CheckIcon />
            </div>
            <span>Nenhum registro.</span>
          </div>
        )}
      </div>
    </Panel>
  );
}
