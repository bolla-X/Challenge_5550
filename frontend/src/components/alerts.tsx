import { useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import NumberFlow from "@number-flow/react";
import { useDashboardStore } from "../store/dashboardStore";
import { Panel, Badge, PanelSkeleton } from "./common";
import type { Alert } from "../api/types";
import { acknowledgeAllAlerts, deleteResolvedAlerts, listAlerts, resolveActiveAlerts } from "../api/endpoints";
import { PPE_KEYS, PPE_LABELS } from "../api/ppe";

const NIVEL: Record<string, number> = { operator: 1, technical: 2, supervisor: 3 };
const TIPOS_DE_ALERTA: { value: string; label: string }[] = [
  ...PPE_KEYS.map((key) => ({ value: key, label: PPE_LABELS[key] })),
  { value: "falls", label: "Quedas" },
  { value: "posture", label: "Postura" },
  { value: "risk_area", label: "Área de risco" },
];

// Matches tokens.css --ease exactly — motion needs the numeric bezier, not
// the CSS var, so this is the one place it's duplicated.
const EASE = [0.16, 1, 0.3, 1] as const;
// tokens.css only defines one curve (the ease-out above); exits use Motion's
// built-in ease-in instead of inventing an unvalidated reverse bezier.
const EASE_IN = "easeIn" as const;
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
      initial={reduceMotion ? false : { opacity: 0, y: -4, scale: 0.98 }}
      animate={{
        opacity: 1,
        y: 0,
        scale: 1,
        backgroundColor: highlighted ? "rgba(47, 212, 230, .14)" : "rgba(47, 212, 230, 0)",
      }}
      exit={
        reduceMotion
          ? { opacity: 0 }
          : { opacity: 0, height: 0, paddingTop: 0, paddingBottom: 0, marginTop: 0, transition: { duration: 0.2, ease: EASE_IN } }
      }
      transition={{
        duration: reduceMotion ? 0.001 : 0.22,
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
  const user = useDashboardStore((s) => s.user);
  const camId = useDashboardStore((s) => s.camId);
  const showMessage = useDashboardStore((s) => s.showMessage);
  const [ocupado, setOcupado] = useState(false);
  const nivel = NIVEL[user?.role ?? ""] ?? 0;

  const reconhecerTodos = () => {
    setOcupado(true);
    acknowledgeAllAlerts(camId)
      .then((r) => showMessage(r.acknowledged ? `${r.acknowledged} alerta(s) marcados como tratados.` : "Nenhum alerta pendente de aviso.", "ok"))
      .catch((err) => showMessage(err instanceof Error ? err.message : "Falha ao reconhecer alertas.", "error"))
      .finally(() => setOcupado(false));
  };

  const resolverTodos = () => {
    if (
      !window.confirm(
        "Resolver todos os alertas ativos desta câmera?\n\nEles vão para o histórico (nada é apagado). Se a violação continuar, o mesmo alerta fica quieto por 1 minuto e depois volta.",
      )
    )
      return;
    setOcupado(true);
    resolveActiveAlerts(camId)
      .then((r) =>
        showMessage(
          r.silencio_s > 0
            ? `${r.active_before} alerta(s) encerrados. Não voltam por ${Math.round(r.silencio_s)} s enquanto a violação continuar.`
            : `${r.active_before} alerta(s) ativo(s) encerrados.`,
          "ok",
        ),
      )
      .catch((err) => showMessage(err instanceof Error ? err.message : "Falha ao resolver alertas.", "error"))
      .finally(() => setOcupado(false));
  };

  const [pessoaFiltro, setPessoaFiltro] = useState<string | null>(null);
  const sorted = useMemo(
    () => [...activeAlerts].sort((a, b) => (SEVERITY_ORDER[a.severity] ?? 9) - (SEVERITY_ORDER[b.severity] ?? 9)),
    [activeAlerts],
  );
  // Agrupa por pessoa: uma pessoa com 5 violações vira UM grupo, não 5 linhas soltas.
  const grupos = useMemo(() => {
    const mapa = new Map<string, Alert[]>();
    for (const alert of sorted) {
      const meta = alert.metadata || {};
      const nome = (meta.person_label as string) || (meta.person_id as string) || "Geral";
      mapa.set(nome, [...(mapa.get(nome) ?? []), alert]);
    }
    return [...mapa.entries()].sort(
      (a, b) => (SEVERITY_ORDER[a[1][0].severity] ?? 9) - (SEVERITY_ORDER[b[1][0].severity] ?? 9) || b[1].length - a[1].length,
    );
  }, [sorted]);
  const gruposVisiveis = pessoaFiltro ? grupos.filter(([nome]) => nome === pessoaFiltro) : grupos;
  useEffect(() => {
    if (pessoaFiltro && !grupos.some(([nome]) => nome === pessoaFiltro)) setPessoaFiltro(null);
  }, [grupos, pessoaFiltro]);

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
      {sorted.length > 0 && nivel >= 1 && (
        <div className="filter-row" style={{ marginBottom: 8 }}>
          <button type="button" className="secondary small" disabled={ocupado} onClick={reconhecerTodos}>
            Avisei todos
          </button>
          {nivel >= 2 && (
            <button type="button" className="secondary small" disabled={ocupado} onClick={resolverTodos}>
              Resolver todos
            </button>
          )}
        </div>
      )}
      <div className="alert-card-body content-enter">
        {sorted.length ? (
          <>
            {grupos.length > 1 && (
              <div className="filter-row" style={{ marginBottom: 8, flexWrap: "wrap" }}>
                <button type="button" className={`secondary small${pessoaFiltro === null ? " active" : ""}`} onClick={() => setPessoaFiltro(null)}>
                  Todas ({grupos.length})
                </button>
                {grupos.map(([nome, itens]) => (
                  <button
                    key={nome}
                    type="button"
                    className={`secondary small${pessoaFiltro === nome ? " active" : ""}`}
                    onClick={() => setPessoaFiltro(pessoaFiltro === nome ? null : nome)}
                  >
                    {nome} · {itens.length}
                  </button>
                ))}
              </div>
            )}
            {gruposVisiveis.map(([nome, itens]) => (
              <details key={nome} open={gruposVisiveis.length <= 3 || pessoaFiltro === nome} className="alert-group">
                <summary>
                  <span className={`alert-stripe ${itens[0].severity}`} style={{ display: "inline-block", width: 4, height: 14, marginRight: 8 }} />
                  <strong>{nome}</strong> — {itens.length} alerta(s)
                </summary>
                <AnimatePresence initial={false}>
                  {itens.map((alert) => (
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
              </details>
            ))}
          </>
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
  const cameras = useDashboardStore((st) => st.cameras);
  const user = useDashboardStore((st) => st.user);
  const showMessage = useDashboardStore((st) => st.showMessage);
  const nivel = NIVEL[user?.role ?? ""] ?? 0;

  const [statusFilter, setStatusFilter] = useState("");
  const [severityFilter, setSeverityFilter] = useState("");
  const [cameraFilter, setCameraFilter] = useState("");
  const [tipoFilter, setTipoFilter] = useState("");
  const [antigos, setAntigos] = useState("");
  const [itens, setItens] = useState<Alert[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [apagando, setApagando] = useState(false);

  // Filtra NO SERVIDOR: o histórico chega a milhares de linhas e um filtro só no
  // navegador enxergaria apenas as últimas dezenas.
  const carregar = () =>
    listAlerts({
      limit: 200,
      status: statusFilter || undefined,
      severity: severityFilter || undefined,
      cameraId: cameraFilter ? Number(cameraFilter) : null,
      feature: tipoFilter || undefined,
    })
      .then((res) => setItens(res.items))
      .catch(() => undefined)
      .finally(() => setCarregando(false));

  useEffect(() => {
    setCarregando(true);
    carregar();
    const timer = setInterval(carregar, 10000);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter, severityFilter, cameraFilter, tipoFilter]);

  const apagarResolvidos = () => {
    const escopo = cameraFilter
      ? `da câmera "${cameras.find((c) => String(c.id) === cameraFilter)?.name ?? cameraFilter}"`
      : "de TODAS as câmeras";
    const idade = antigos ? ` com mais de ${antigos} dias` : "";
    if (
      !window.confirm(
        `Apagar DEFINITIVAMENTE os alertas já resolvidos ${escopo}${idade}?\n\nAlertas ativos não são tocados. Isso não pode ser desfeito.`,
      )
    )
      return;
    setApagando(true);
    deleteResolvedAlerts({ cameraId: cameraFilter ? Number(cameraFilter) : null, olderThanDays: antigos ? Number(antigos) : undefined })
      .then((r) => {
        showMessage(`${r.deleted} alerta(s) resolvidos apagados.`, "ok");
        return carregar();
      })
      .catch((err) => showMessage(err instanceof Error ? err.message : "Falha ao apagar alertas.", "error"))
      .finally(() => setApagando(false));
  };

  return (
    <Panel id="panel-alert-history" title="Histórico recente" description="Auditoria local de alertas persistidos.">
      <div className="filter-row">
        <select value={cameraFilter} onChange={(e) => setCameraFilter(e.target.value)} aria-label="Câmera">
          <option value="">Todas as câmeras</option>
          {cameras.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <select value={tipoFilter} onChange={(e) => setTipoFilter(e.target.value)} aria-label="Tipo de alerta">
          <option value="">Todos os tipos</option>
          {TIPOS_DE_ALERTA.map((t) => (
            <option key={t.value} value={t.value}>
              {t.label}
            </option>
          ))}
        </select>
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} aria-label="Situação">
          <option value="">Todos</option>
          <option value="active">Ativos</option>
          <option value="resolved">Resolvidos</option>
        </select>
        <select value={severityFilter} onChange={(e) => setSeverityFilter(e.target.value)} aria-label="Severidade">
          <option value="">Todas severidades</option>
          <option value="critical">Crítico</option>
          <option value="high">Alto</option>
          <option value="medium">Médio</option>
          <option value="low">Baixo</option>
          <option value="info">Info</option>
        </select>
      </div>
      {nivel >= 3 && (
        <div className="filter-row" style={{ marginTop: 8 }}>
          <select value={antigos} onChange={(e) => setAntigos(e.target.value)} aria-label="Idade dos resolvidos a apagar">
            <option value="">Apagar: todos os resolvidos</option>
            <option value="7">Apagar: resolvidos há +7 dias</option>
            <option value="30">Apagar: resolvidos há +30 dias</option>
          </select>
          <button type="button" className="secondary small" disabled={apagando} onClick={apagarResolvidos}>
            {apagando ? "Apagando…" : "Apagar resolvidos"}
          </button>
        </div>
      )}
      <div className="alerts history">
        {itens.length ? (
          itens.map((alert) => <AlertRow key={alert.id} alert={alert} active={false} />)
        ) : (
          <div className="all-clear">
            <div className="all-clear-badge">
              <CheckIcon />
            </div>
            <span>{carregando ? "Carregando…" : "Nenhum registro."}</span>
          </div>
        )}
      </div>
    </Panel>
  );
}
