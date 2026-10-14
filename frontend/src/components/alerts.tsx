import { useEffect, useMemo, useState } from "react";
import { IlustracaoEscudo, IlustracaoGrafico } from "./ilustracoes";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useDashboardStore } from "../store/dashboardStore";
import { EmptyState, Panel, PanelSkeleton } from "./common";
import type { Alert, Incidente } from "../api/types";
import {
  acknowledgeAllAlerts,
  deleteResolvedAlerts,
  getCameraStatus,
  listAlerts,
  reconhecerIncidente,
  resolveActiveAlerts,
} from "../api/endpoints";
import { pessoasDoIncidente, zonaDoIncidente } from "../utils/incidentes";
import { IncidenteDetalhe } from "./incidente-detalhe";
import { PPE_KEYS, PPE_LABELS } from "../api/ppe";
import { paraDate } from "../utils/datas";
import { IncidentReplay } from "./replay";

const NIVEL: Record<string, number> = { operator: 1, technical: 2, supervisor: 3 };
const TIPOS_DE_ALERTA: { value: string; label: string }[] = [
  ...PPE_KEYS.map((key) => ({ value: key, label: PPE_LABELS[key] })),
  { value: "falls", label: "Quedas" },
  { value: "posture", label: "Postura" },
  { value: "risk_area", label: "Área de risco" },
];

// Mesma curva de tokens.css (--ease-out). Motion precisa do bezier numérico.
const EASE = [0.23, 1, 0.32, 1] as const;
const SEVERITY_ORDER: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3, info: 4 };

function formatTime(value: string | null): string {
  return paraDate(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function formatDateTime(value: string | null): string {
  return paraDate(value).toLocaleString([], { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

/** Linha de alerta: ponto, título, contexto e horário à direita. Crítico e
 * alto tingem a linha e acendem o ponto; médio acende só o ponto. */
function AlertRow({ alert, active, reduceMotion = false, animated = false }: { alert: Alert; active: boolean; reduceMotion?: boolean; animated?: boolean }) {
  const markFalsePositive = useDashboardStore((s) => s.markFalsePositive);
  const nomeDaCamera = useDashboardStore((s) => s.cameras.find((c) => c.id === alert.camera_id)?.name);
  const [replayAberto, setReplayAberto] = useState(false);
  const meta = alert.metadata || {};
  const subject = (meta.person_label as string) || (meta.person_id as string) || (meta.subject as string) || "global";
  const cls = ["alert-row", alert.severity, alert.resolved_at ? "resolved" : "", alert.false_positive ? "false-positive" : ""].filter(Boolean).join(" ");
  const contexto = [alert.rule, subject].filter(Boolean).join(" · ");
  const resolvido = alert.resolved_at ? `, resolvido ${formatDateTime(alert.resolved_at)}` : "";
  const temAcao = true;

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
            <button className="ghost small" type="button" onClick={() => setReplayAberto(true)}>
              Ver replay
            </button>
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
      {replayAberto && <IncidentReplay alertId={alert.id} cameraName={nomeDaCamera} onClose={() => setReplayAberto(false)} />}
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

/** Cabeçalho de um incidente: título, zona, IDs de rastreio e "Reconhecer". */
function IncidenteResumo({ inc, total, podeReconhecer }: { inc: Incidente | null; total: number; podeReconhecer: boolean }) {
  const showMessage = useDashboardStore((s) => s.showMessage);
  const nomeDaCamera = useDashboardStore((s) => s.cameras.find((c) => c.id === inc?.camera_id)?.name);
  const [ocupado, setOcupado] = useState(false);
  const [aberto, setAberto] = useState(false);
  if (!inc) {
    return (
      <summary>
        <strong>Outros alertas</strong> ({total})
      </summary>
    );
  }
  const reconhecer = (e: React.MouseEvent) => {
    e.preventDefault();
    setOcupado(true);
    reconhecerIncidente(inc.id)
      .then((r) =>
        showMessage(
          r.primeira_vez ? `Incidente reconhecido em ${Math.round(r.incidente.reconhecido_em_s ?? 0)} s.` : "Este incidente já tinha sido reconhecido.",
          "ok",
        ),
      )
      .catch((err) => showMessage(err instanceof Error ? err.message : "Falha ao reconhecer.", "error"))
      .finally(() => setOcupado(false));
  };
  const zona = zonaDoIncidente(inc);
  const pessoas = pessoasDoIncidente(inc, 6);
  return (
    <summary data-testid="incidente" data-incidente={inc.id} data-titulo={inc.titulo} data-zona={inc.zona}>
      <span className={`alert-stripe ${inc.severity}`} />
      <span className="incidente-resumo">
        <strong>{inc.titulo}</strong>
        {zona && <span className="incidente-zona">{zona}</span>}
        {pessoas && <span className="t-secondary">{pessoas}</span>}
      </span>
      {inc.reconhecido_em ? (
        <span className="chip ok" style={{ marginLeft: 8 }}>Reconhecido</span>
      ) : (
        podeReconhecer && (
          <button type="button" className="ghost small" style={{ marginLeft: 8 }} disabled={ocupado} onClick={reconhecer}>
            Reconhecer
          </button>
        )
      )}
      <button
        type="button"
        className="ghost small"
        data-testid="incidente-abrir"
        onClick={(e) => {
          e.preventDefault();
          setAberto(true);
        }}
      >
        Linha causal
      </button>
      {aberto && <IncidenteDetalhe incidente={inc} nomeDaCamera={nomeDaCamera} onClose={() => setAberto(false)} />}
    </summary>
  );
}

export function AlertPanel() {
  const activeAlerts = useDashboardStore((s) => s.activeAlerts);
  const activeIncidents = useDashboardStore((s) => s.activeIncidents);
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

  // Rede de segurança: o socket pode ficar mudo (servidor reiniciado com a aba
  // aberta, rede que caiu) sem a tela perceber. A lista confere com o servidor a
  // cada 2 s, a mesma fonte da pílula de alerta sobre o vídeo, e nunca diverge.
  useEffect(() => {
    if (camId == null) return undefined;
    let cancelado = false;
    const conferir = () =>
      getCameraStatus(camId)
        .then((st) => {
          if (!cancelado && useDashboardStore.getState().camId === camId) {
            useDashboardStore.setState(
              { activeAlerts: st.active_alerts ?? [], activeIncidents: st.active_incidents ?? [] },
              false,
              "poll:active_alerts",
            );
          }
        })
        .catch(() => undefined);
    const timer = setInterval(conferir, 2000);
    return () => {
      cancelado = true;
      clearInterval(timer);
    };
  }, [camId]);

  const sorted = useMemo(
    () => [...activeAlerts].sort((a, b) => (SEVERITY_ORDER[a.severity] ?? 9) - (SEVERITY_ORDER[b.severity] ?? 9)),
    [activeAlerts],
  );
  // Agrupa por INCIDENTE (regra + zona, P0.2): três pessoas sem capacete viram
  // um grupo com os IDs, não três linhas — e uma troca de ID não abre outro.
  const grupos = useMemo(() => {
    const porIncidente = new Map<number, Alert[]>();
    const soltos: Alert[] = [];
    for (const alert of sorted) {
      const id = Number((alert.metadata || {}).incidente_id);
      if (Number.isFinite(id) && id > 0) porIncidente.set(id, [...(porIncidente.get(id) ?? []), alert]);
      else soltos.push(alert);
    }
    const lista: [Incidente | null, Alert[]][] = [...activeIncidents]
      .sort((a, b) => (SEVERITY_ORDER[a.severity] ?? 9) - (SEVERITY_ORDER[b.severity] ?? 9))
      .map((inc) => [inc, porIncidente.get(inc.id) ?? []]);
    const conhecidos = new Set(activeIncidents.map((i) => i.id));
    for (const [id, itens] of porIncidente) if (!conhecidos.has(id)) soltos.push(...itens);
    if (soltos.length) lista.push([null, soltos]);
    return lista;
  }, [sorted, activeIncidents]);

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
      title="Incidentes ativos"
      description="Alertas agrupados por regra e zona. Somem quando a condição normal é confirmada."
      action={grupos.length ? <span className="chip miss">{grupos.length}</span> : undefined}
    >
      {sorted.length > 0 && nivel >= 1 && (
        <div className="filter-row" style={{ marginBottom: 8 }}>
          <button type="button" className="ghost small" disabled={ocupado} onClick={reconhecerTodos}>
            Avisei todos
          </button>
          {nivel >= 2 && (
            <button type="button" className="ghost small" disabled={ocupado} onClick={resolverTodos}>
              Resolver todos
            </button>
          )}
        </div>
      )}
      <div className="alert-list content-enter">
        {sorted.length ? (
          <>
            {grupos.map(([inc, itens]) => (
              <details key={inc ? inc.id : "soltos"} open={grupos.length <= 3} className="alert-group">
                <IncidenteResumo inc={inc} total={itens.length} podeReconhecer={nivel >= 1} />
                <AnimatePresence initial={false}>
                  {itens.map((alert) => (
                    <AlertRow key={alert.id} alert={alert} active animated reduceMotion={Boolean(shouldReduceMotion)} />
                  ))}
                </AnimatePresence>
              </details>
            ))}
          </>
        ) : (
          <EmptyState ilustracao={<IlustracaoEscudo />} titulo="Nenhum incidente ativo">
            Quando uma regra for confirmada nesta câmera, o incidente aparece aqui, com os IDs envolvidos.
          </EmptyState>
        )}
      </div>
    </Panel>
  );
}

/** Aba dedicada a queda e postura suspeita — separada da lista geral de
 * alertas porque esses dois eventos são o que a demo ao vivo mais precisa
 * destacar, e o painel "Alertas ativos" some sozinho assim que a pessoa
 * levanta ou corrige a postura. Aqui mostra também o que já foi resolvido
 * nos últimos minutos, pra o evento não sumir da tela no meio da demo. */
export function SafetyEventsPanel() {
  const camId = useDashboardStore((s) => s.camId);
  const [itens, setItens] = useState<Alert[]>([]);
  const [carregando, setCarregando] = useState(true);

  useEffect(() => {
    if (camId == null) return undefined;
    let cancelado = false;
    const carregar = () =>
      Promise.all([
        listAlerts({ limit: 30, cameraId: camId, feature: "falls" }),
        listAlerts({ limit: 30, cameraId: camId, feature: "posture" }),
      ])
        .then(([quedas, posturas]) => {
          if (cancelado) return;
          const combinado = [...quedas.items, ...posturas.items].sort(
            (a, b) => new Date(b.last_seen_at ?? 0).getTime() - new Date(a.last_seen_at ?? 0).getTime(),
          );
          setItens(combinado);
        })
        .catch(() => undefined)
        .finally(() => {
          if (!cancelado) setCarregando(false);
        });
    carregar();
    const timer = setInterval(carregar, 5000);
    return () => {
      cancelado = true;
      clearInterval(timer);
    };
  }, [camId]);

  if (carregando && itens.length === 0) {
    return (
      <Panel id="panel-safety-events" title="Quedas e postura" description="Eventos de queda e postura suspeita, ativos e recentes.">
        <PanelSkeleton lines={2} />
      </Panel>
    );
  }

  return (
    <Panel
      id="panel-safety-events"
      title="Quedas e postura"
      description="Eventos de queda e postura suspeita, ativos e recentes."
      action={itens.length ? <span className="chip miss">{itens.length}</span> : undefined}
    >
      <div className="alert-list">
        {itens.length ? (
          itens.map((alert) => <AlertRow key={alert.id} alert={alert} active={alert.status === "active"} />)
        ) : (
          <EmptyState ilustracao={<IlustracaoEscudo />} titulo="Nenhuma queda ou postura suspeita">
            Eventos de queda e de postura ficam aqui por alguns minutos, mesmo depois de resolvidos.
          </EmptyState>
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
          <button type="button" className="ghost small" disabled={apagando} onClick={apagarResolvidos}>
            {apagando ? "Apagando…" : "Apagar resolvidos"}
          </button>
        </div>
      )}
      <div className="alert-list">
        {itens.length ? (
          itens.map((alert) => <AlertRow key={alert.id} alert={alert} active={false} />)
        ) : (
          carregando ? (
            <PanelSkeleton lines={4} />
          ) : (
            <EmptyState
              ilustracao={<IlustracaoGrafico />}
              titulo="Nenhum registro com esses filtros"
              acao={
                <button
                  type="button"
                  className="small"
                  onClick={() => {
                    setStatusFilter("");
                    setSeverityFilter("");
                    setCameraFilter("");
                    setTipoFilter("");
                  }}
                >
                  Limpar filtros
                </button>
              }
            >
              O histórico guarda todos os alertas, inclusive os resolvidos.
            </EmptyState>
          )
        )}
      </div>
    </Panel>
  );
}
