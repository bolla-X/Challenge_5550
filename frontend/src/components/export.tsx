import { useDashboardStore } from "../store/dashboardStore";
import { Panel, EmptyState } from "./common";

// CSV puro, sem lib — poucas colunas, escapar vírgula/aspas/quebra de linha
// é suficiente, não precisa de parser completo (RFC 4180 na medida do que
// esses dados realmente têm: texto livre em `mensagem`).
function csvField(value: unknown): string {
  const s = value == null ? "" : String(value);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

function toCsv(header: string[], rows: unknown[][]): string {
  return [header, ...rows].map((row) => row.map(csvField).join(",")).join("\r\n");
}

// Backend grava UTC (utc_now() em app/models.py) mas o SQLite devolve o
// datetime naive na leitura — .isoformat() sai sem sufixo de timezone
// (ex: "2026-08-06T16:54:47.491761"). Sem forçar "Z" aqui, o Date() do JS
// interpretaria esse valor como horário LOCAL, não UTC, adiantando/
// atrasando a hora exibida. DD/MM/AAAA HH:MM:SS, sem microssegundos —
// ilegível numa reunião do jeito que vinha (pedido explícito).
function formatDateTimeLocal(value: string | null | undefined): string {
  if (!value) return "";
  const hasOffset = /Z$|[+-]\d\d:\d\d$/.test(value);
  const date = new Date(hasOffset ? value : `${value}Z`);
  if (Number.isNaN(date.getTime())) return value;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(date.getDate())}/${pad(date.getMonth() + 1)}/${date.getFullYear()} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

// BOM (﻿) na frente do Blob: sem ele o Excel no Windows abre o CSV como
// Latin-1 e corrompe acento (severidade, mensagem etc.) — pedido explícito.
function downloadCsv(filename: string, csv: string) {
  const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

/** Exportação client-side pura — sem endpoint novo no backend, só serializa
 * o que já está carregado no store (alertHistory / timeline). É por isso que
 * o botão exporta "o que está na tela", não um relatório sob demanda: pedir
 * um range de datas arbitrário precisaria de uma rota nova no Flask, fora do
 * escopo desta rodada. */
export function ExportPanel() {
  const alertHistory = useDashboardStore((s) => s.alertHistory);
  const timeline = useDashboardStore((s) => s.timeline);

  const exportAlerts = () => {
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
  };

  const exportTimeline = () => {
    const header = ["horario", "severidade", "mensagem", "detalhe"];
    const rows = timeline.map((e) => [formatDateTimeLocal(e.created_at), e.severity ?? "", e.message, e.subject ?? e.event_type]);
    downloadCsv(`visionepi-timeline-${Date.now()}.csv`, toCsv(header, rows));
  };

  return (
    <Panel id="panel-export" title="Exportação" description="CSV do que está carregado agora — histórico de alertas e linha do tempo.">
      <div className="row-list">
        <div className="row-item">
          <div>
            <strong>Histórico de alertas</strong>
            <span>{alertHistory.length} registro{alertHistory.length === 1 ? "" : "s"} carregado{alertHistory.length === 1 ? "" : "s"}</span>
          </div>
        </div>
        <div className="row-item">
          <div>
            <strong>Linha do tempo</strong>
            <span>{timeline.length} registro{timeline.length === 1 ? "" : "s"} carregado{timeline.length === 1 ? "" : "s"}</span>
          </div>
        </div>
      </div>
      <div className="risk-editor-actions">
        <button type="button" className="secondary small" disabled={!alertHistory.length} onClick={exportAlerts}>
          Exportar histórico de alertas (CSV)
        </button>
        <button type="button" className="secondary small" disabled={!timeline.length} onClick={exportTimeline}>
          Exportar linha do tempo (CSV)
        </button>
      </div>
      {!alertHistory.length && !timeline.length && <EmptyState>Nada carregado ainda pra exportar.</EmptyState>}
    </Panel>
  );
}
