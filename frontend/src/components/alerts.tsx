import { useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import NumberFlow from "@number-flow/react";
import { useDashboardStore } from "../store/dashboardStore";
import { Panel, Badge, PanelSkeleton } from "./common";
import type { Alert } from "../api/types";

// Matches tokens.css --ease exactly — motion needs the numeric bezier, not
// the CSS var, so this is the one place it's duplicated.
const EASE = [0.16, 1, 0.3, 1] as const;
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

function AlertRow({
  alert,
  active,
  highlighted = false,
  reduceMotion = false,
  animated = false,
}: {
  alert: Alert;
  active: boolean;
  highlighted?: boolean;
  reduceMotion?: boolean;
  animated?: boolean;
}) {
  const markFalsePositive = useDashboardStore((s) => s.markFalsePositive);
  const meta = alert.metadata || {};
  const subject = (meta.person_label as string) || (meta.person_id as string) || (meta.subject as string) || "global";
  const cls = ["alert-row", alert.resolved_at ? "resolved" : "", alert.false_positive ? "false-positive" : ""].filter(Boolean).join(" ");

  if (!animated) {
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

  return (
    // Entrada/saída: comunica que essa linha específica apareceu/sumiu da
    // lista (não confundir com reordenação). Destaque de fundo: comunica
    // que essa é a linha que acabou de chegar via alert_created, distinta
    // de uma linha existente sendo apenas re-confirmada (alert_updated).
    <motion.div
      className={cls}
      layout={!reduceMotion}
      initial={reduceMotion ? false : { opacity: 0, y: -8 }}
      animate={{
        opacity: 1,
        y: 0,
        backgroundColor: highlighted ? "rgba(47, 212, 230, .14)" : "rgba(47, 212, 230, 0)",
      }}
      exit={reduceMotion ? { opacity: 0 } : { opacity: 0, height: 0, paddingTop: 0, paddingBottom: 0, marginTop: 0 }}
      transition={{
        duration: reduceMotion ? 0.001 : 0.2,
        ease: EASE,
        backgroundColor: { duration: 0.7, ease: "easeOut" },
      }}
    >
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
    </motion.div>
  );
}

/** Calm by default — a quiet, reassuring "all clear" moment, not an empty
 * div. Only grows louder (accent stripe per severity) with a real alert. */
export function AlertPanel() {
  const activeAlerts = useDashboardStore((s) => s.activeAlerts);
  const lastAlertCreatedId = useDashboardStore((s) => s.lastAlertCreatedId);
  const allClearAt = useDashboardStore((s) => s.allClearAt);
  const bootstrapping = useDashboardStore((s) => s.bootstrapping);
  const shouldReduceMotion = useReducedMotion();
  const sorted = useMemo(
    () => [...activeAlerts].sort((a, b) => (SEVERITY_ORDER[a.severity] ?? 9) - (SEVERITY_ORDER[b.severity] ?? 9)),
    [activeAlerts],
  );

  // Highlight is transient: fades itself out via the row's own 0.7s
  // background transition, this just clears the flag so it doesn't relight
  // if the row re-renders for an unrelated reason.
  const [highlightedId, setHighlightedId] = useState<number | null>(null);
  useEffect(() => {
    if (lastAlertCreatedId == null) return undefined;
    setHighlightedId(lastAlertCreatedId);
    const timer = setTimeout(() => setHighlightedId(null), 700);
    return () => clearTimeout(timer);
  }, [lastAlertCreatedId]);

  // Reconhecimento sutil de "voltou tudo certo" — só quando há um "antes"
  // real (allClearAt setado pelo store, nunca no boot). Cor, não confete:
  // tom sério do produto pedido explicitamente.
  const [celebrate, setCelebrate] = useState(false);
  useEffect(() => {
    if (allClearAt == null) return undefined;
    setCelebrate(true);
    const timer = setTimeout(() => setCelebrate(false), 900);
    return () => clearTimeout(timer);
  }, [allClearAt]);

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
      action={
        sorted.length ? (
          <Badge tone="error">
            <NumberFlow value={sorted.length} respectMotionPreference />
          </Badge>
        ) : undefined
      }
    >
      <div className="alert-card-body content-enter">
        {sorted.length ? (
          <AnimatePresence initial={false}>
            {sorted.map((alert) => (
              <AlertRow
                key={alert.id}
                alert={alert}
                active
                animated
                reduceMotion={Boolean(shouldReduceMotion)}
                highlighted={alert.id === highlightedId}
              />
            ))}
          </AnimatePresence>
        ) : (
          <div className="all-clear">
            <motion.div
              className="all-clear-badge"
              animate={
                celebrate && !shouldReduceMotion
                  ? { backgroundColor: ["rgba(34, 197, 94, .1)", "rgba(34, 197, 94, .4)", "rgba(34, 197, 94, .1)"] }
                  : {}
              }
              transition={{ duration: 0.9, ease: "easeOut" }}
            >
              <CheckIcon />
            </motion.div>
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
    <Panel id="panel-alert-history" title="Histórico recente" description="Auditoria local de alertas persistidos.">
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
