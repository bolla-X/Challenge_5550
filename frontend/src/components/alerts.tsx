import { useMemo, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useDashboardStore } from "../store/dashboardStore";
import { Panel, PanelSkeleton } from "./common";
import type { Alert } from "../api/types";

// Mesma curva de tokens.css (--ease-out). Motion precisa do bezier numérico.
const EASE = [0.23, 1, 0.32, 1] as const;
const SEVERITY_ORDER: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3, info: 4 };

function formatTime(value: string | null): string {
  const date = value ? new Date(value) : new Date();
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function formatDateTime(value: string | null): string {
  const date = value ? new Date(value) : new Date();
  return date.toLocaleString([], { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

/** Linha de alerta: ponto, título, contexto e horário à direita. Crítico e
 * alto tingem a linha e acendem o ponto; médio acende só o ponto. */
function AlertRow({ alert, active, reduceMotion = false, animated = false }: { alert: Alert; active: boolean; reduceMotion?: boolean; animated?: boolean }) {
  const markFalsePositive = useDashboardStore((s) => s.markFalsePositive);
  const meta = alert.metadata || {};
  const subject = (meta.person_label as string) || (meta.person_id as string) || (meta.subject as string) || "global";
  const cls = ["alert-row", alert.severity, alert.resolved_at ? "resolved" : "", alert.false_positive ? "false-positive" : ""].filter(Boolean).join(" ");
  const contexto = [alert.rule, subject].filter(Boolean).join(" · ");
  const resolvido = alert.resolved_at ? `, resolvido ${formatDateTime(alert.resolved_at)}` : "";
  const temAcao = Boolean(alert.frame_ref) || alert.false_positive || active;

  const body = (
    <>
      <span className="dot" />
      <div className="alert-row-body">
        <strong>{alert.message}</strong>
        <div className="alert-row-meta">
          {contexto}
          {resolvido}
        </div>
        {temAcao && (
          <div className="alert-row-actions">
            {alert.frame_ref && (
              <a className="evidence-link" href={`/alerts/${alert.id}/evidence`} target="_blank" rel="noopener noreferrer">
                Ver evidência
              </a>
            )}
            {alert.false_positive ? (
              <span className="t-secondary">Falso positivo</span>
            ) : (
              active && (
                <button className="ghost small" type="button" onClick={() => markFalsePositive(alert.id)}>
                  Falso positivo
                </button>
              )
            )}
          </div>
        )}
      </div>
      <span className="alert-row-time" title={`Visto às ${formatDateTime(alert.last_seen_at)}`}>
        {formatTime(alert.last_seen_at)}
      </span>
    </>
  );

  if (!animated) return <div className={cls}>{body}</div>;

  // Entra com opacidade e escala de 0,98 para 1 em 200 ms, curva de saída,
  // e para. Nada pulsa depois disso.
  return (
    <motion.div
      className={cls}
      layout={!reduceMotion}
      initial={reduceMotion ? false : { opacity: 0, scale: 0.98 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: reduceMotion ? 0 : 0.2, ease: EASE }}
    >
      {body}
    </motion.div>
  );
}

/** Calmo por padrão. Só ganha cor com um alerta real. */
export function AlertPanel() {
  const activeAlerts = useDashboardStore((s) => s.activeAlerts);
  const bootstrapping = useDashboardStore((s) => s.bootstrapping);
  const shouldReduceMotion = useReducedMotion();
  const sorted = useMemo(
    () => [...activeAlerts].sort((a, b) => (SEVERITY_ORDER[a.severity] ?? 9) - (SEVERITY_ORDER[b.severity] ?? 9)),
    [activeAlerts],
  );

  if (bootstrapping) {
    return (
      <Panel id="panel-alerts" title="Alertas ativos" description="Somem automaticamente quando a condição normal é confirmada.">
        <PanelSkeleton lines={2} />
      </Panel>
    );
  }

  return (
    <Panel
      id="panel-alerts"
      title="Alertas ativos"
      description="Somem automaticamente quando a condição normal é confirmada."
      action={sorted.length ? <span className="chip miss">{sorted.length}</span> : undefined}
    >
      <div className="alert-list content-enter">
        {sorted.length ? (
          <AnimatePresence initial={false}>
            {sorted.map((alert) => (
              <AlertRow key={alert.id} alert={alert} active animated reduceMotion={Boolean(shouldReduceMotion)} />
            ))}
          </AnimatePresence>
        ) : (
          <div className="all-clear">
            <span className="dot" />
            Nenhum alerta ativo nesta câmera.
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
    <Panel id="panel-alert-history" title="Histórico recente" description="Auditoria local de alertas persistidos.">
      <div className="filter-row">
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} aria-label="Filtrar por situação">
          <option value="">Todos</option>
          <option value="active">Ativos</option>
          <option value="resolved">Resolvidos</option>
        </select>
        <select value={severityFilter} onChange={(e) => setSeverityFilter(e.target.value)} aria-label="Filtrar por severidade">
          <option value="">Todas severidades</option>
          <option value="critical">Crítico</option>
          <option value="high">Alto</option>
          <option value="medium">Médio</option>
          <option value="low">Baixo</option>
          <option value="info">Info</option>
        </select>
      </div>
      <div className="alert-list">
        {filtered.length ? (
          filtered.map((alert) => <AlertRow key={alert.id} alert={alert} active={false} />)
        ) : (
          <div className="all-clear">
            <span className="dot" />
            Nenhum alerta registrado com esse filtro.
          </div>
        )}
      </div>
    </Panel>
  );
}
