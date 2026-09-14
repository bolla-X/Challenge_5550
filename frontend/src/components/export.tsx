import { useDashboardStore } from "../store/dashboardStore";
import { Panel, EmptyState } from "./common";
import type { Alert, TimelineEvent } from "../api/types";

// CSV puro, sem lib: poucas colunas, escapar vírgula/aspas/quebra de linha
// é suficiente (RFC 4180 na medida do que esses dados realmente têm).
function csvField(value: unknown): string {
  const s = value == null ? "" : String(value);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

function toCsv(header: string[], rows: unknown[][]): string {
  return [header, ...rows].map((row) => row.map(csvField).join(",")).join("\r\n");
}

// Backend grava UTC mas o SQLite devolve o datetime naive na leitura, sem
// sufixo de timezone. Sem forçar "Z" aqui, o Date() do JS interpretaria como
// horário LOCAL. Saída DD/MM/AAAA HH:MM:SS, sem microssegundos.
function formatDateTimeLocal(value: string | null | undefined): string {
  if (!value) return "";
  const hasOffset = /Z$|[+-]\d\d:\d\d$/.test(value);
  const date = new Date(hasOffset ? value : `${value}Z`);
  if (Number.isNaN(date.getTime())) return value;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(date.getDate())}/${pad(date.getMonth() + 1)}/${date.getFullYear()} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

// BOM na frente do Blob: sem ele o Excel no Windows abre o CSV como Latin-1
// e corrompe acento.
function downloadCsv(filename: string, csv: string) {
  const blob = new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

/** Exportação client-side pura: serializa o que já está carregado no store.
 * Exportadas também pro botão "Exportar" da barra do aplicativo. */
export function exportAlertsCsv(alertHistory: Alert[]) {
  const header = ["id", "severidade", "feature", "mensagem", "status", "falso_positivo", "criado_em", "resolvido_em"];
  const rows = alertHistory.map((a) => [
    a.id,
    a.severity,
    a.feature ?? "",
    a.message,
    a.status,
    a.false_positive ? "sim" : "não",
    formatDateTimeLocal(a.created_at),
    formatDateTimeLocal(a.resolved_at),
  ]);
  downloadCsv(`visionepi-alertas-${Date.now()}.csv`, toCsv(header, rows));
}

export function exportTimelineCsv(timeline: TimelineEvent[]) {
  const header = ["horario", "severidade", "mensagem", "detalhe"];
  const rows = timeline.map((e) => [formatDateTimeLocal(e.created_at), e.severity ?? "", e.message, e.subject ?? e.event_type]);
  downloadCsv(`visionepi-timeline-${Date.now()}.csv`, toCsv(header, rows));
}

export function ExportPanel() {
  const alertHistory = useDashboardStore((s) => s.alertHistory);
  const timeline = useDashboardStore((s) => s.timeline);

  return (
    <Panel id="panel-export" title="Exportação" description="CSV do que está carregado agora: histórico de alertas e linha do tempo.">
      <div className="row-list">
        <div className="row-item">
          <div className="row-detail">
            <strong>Histórico de alertas</strong>
            <span>
              {alertHistory.length} registro{alertHistory.length === 1 ? "" : "s"} carregado{alertHistory.length === 1 ? "" : "s"}
            </span>
          </div>
        </div>
        <div className="row-item">
          <div className="row-detail">
            <strong>Linha do tempo</strong>
            <span>
              {timeline.length} registro{timeline.length === 1 ? "" : "s"} carregado{timeline.length === 1 ? "" : "s"}
            </span>
          </div>
        </div>
      </div>
      <div className="actions actions-top">
        <button type="button" className="small" disabled={!alertHistory.length} onClick={() => exportAlertsCsv(alertHistory)}>
          Exportar histórico de alertas (CSV)
        </button>
        <button type="button" className="small" disabled={!timeline.length} onClick={() => exportTimelineCsv(timeline)}>
          Exportar linha do tempo (CSV)
        </button>
      </div>
      {!alertHistory.length && !timeline.length && <EmptyState>Nada carregado ainda para exportar.</EmptyState>}
    </Panel>
  );
}
