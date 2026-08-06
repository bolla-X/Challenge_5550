import { useEffect, useState } from "react";
import { useDashboardStore } from "../store/dashboardStore";
import { Badge, Panel, EmptyState } from "./common";
import { getPreflight } from "../api/endpoints";
import type { PreflightCheck, RuntimeSettings } from "../api/types";

const STATUS_LABEL: Record<string, string> = { ok: "OK", warning: "Aviso", error: "Erro" };

export function ChecklistPanel() {
  const [checks, setChecks] = useState<PreflightCheck[]>([]);

  const refresh = async () => {
    try {
      const res = await getPreflight();
      setChecks(res.checks);
    } catch {
      setChecks([{ key: "preflight", label: "Checklist", status: "error", message: "Falha ao executar checklist" }]);
    }
  };

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <Panel
      id="panel-checklist"
      title="Checklist pré-start"
      description="Validação rápida antes de iniciar um ciclo de teste."
      className="technical-only"
      action={
        <button className="secondary small" type="button" onClick={() => refresh()}>
          Atualizar
        </button>
      }
    >
      <div className="checklist">
        {checks.length ? (
          checks.map((item) => (
            <div className={`check-item ${item.status}`} key={item.key}>
              <span className="check-status">{STATUS_LABEL[item.status] || item.status}</span>
              <div>
                <strong>{item.label}</strong>
                <small>{item.message}</small>
              </div>
            </div>
          ))
        ) : (
          <EmptyState>Checklist indisponível.</EmptyState>
        )}
      </div>
    </Panel>
  );
}

const SETTINGS_FIELDS: [keyof RuntimeSettings, string, "number" | "checkbox", string?][] = [
  ["target_fps", "FPS alvo", "number"],
  ["jpeg_quality", "Qualidade JPEG", "number"],
  ["yolo_confidence", "Confiança YOLO", "number", "0.05"],
  ["yolo_max_detections", "Máx. detecções YOLO", "number"],
  ["alert_create_after_frames", "Frames para criar alerta", "number"],
  ["alert_resolve_after_frames", "Frames para resolver alerta", "number"],
  ["snapshot_jpeg_quality", "Qualidade do snapshot", "number"],
  ["multi_person_detection", "Multi-pessoa via YOLO", "checkbox"],
  ["cleanup_on_monitor_start", "Limpar arquivos ao iniciar", "checkbox"],
  ["snapshot_enabled", "Salvar snapshot de alerta", "checkbox"],
];

export function SettingsPanel() {
  const settings = useDashboardStore((s) => s.settings);
  const updateSettings = useDashboardStore((s) => s.updateSettings);
  const [draft, setDraft] = useState<Partial<RuntimeSettings>>({});

  useEffect(() => {
    if (settings) setDraft(settings);
  }, [settings]);

  if (!settings) return null;

  const save = () => updateSettings(draft).catch(console.error);

  return (
    <Panel
      id="panel-settings"
      title="Configurações rápidas"
      description="Aplicadas em runtime quando possível. Persistência definitiva continua no .env."
      className="technical-only"
      action={
        <button className="secondary small" type="button" onClick={save}>
          Salvar
        </button>
      }
    >
      <div className="settings-grid">
        {SETTINGS_FIELDS.map(([key, label, type, step]) => (
          <label key={key}>
            <span>{label}</span>
            {type === "checkbox" ? (
              <span className="switch">
                <input
                  type="checkbox"
                  checked={Boolean(draft[key])}
                  onChange={(e) => setDraft((prev) => ({ ...prev, [key]: e.target.checked }))}
                />
                <span className="switch-track">
                  <span className="switch-thumb" />
                </span>
              </span>
            ) : (
              <input
                type="number"
                step={step || "1"}
                value={String(draft[key] ?? "")}
                onChange={(e) => setDraft((prev) => ({ ...prev, [key]: Number(e.target.value) }))}
              />
            )}
          </label>
        ))}
      </div>
    </Panel>
  );
}

export function ModelStatusPanel() {
  const model = useDashboardStore((s) => s.model);
  if (!model) {
    return (
      <Panel id="panel-model" title="Modelo YOLO" className="technical-only">
        <div className="model-status">Aguardando diagnóstico.</div>
      </Panel>
    );
  }
  const statusTone = model.error ? "error" : model.ppe_ready ? "ok" : "warn";
  const statusText = model.ppe_ready ? "Modelo PPE completo" : model.error ? "Modelo indisponível" : "Modelo PPE incompleto";
  const supported = model.supported_ppe;
  const classes = model.classes || [];
  const yesNo = (v: boolean | undefined) => (v ? "suportado" : "não suportado");

  return (
    <Panel id="panel-model" title="Modelo YOLO" className="technical-only" action={<Badge tone={statusTone}>{statusText}</Badge>}>
      <div className="status-list">
        <div className="status-row"><span className="status-row-label">Arquivo</span><span className="status-row-value">{model.model_path || "indefinido"}</span></div>
        <div className="status-row"><span className="status-row-label">Pessoa</span><span className="status-row-value">{yesNo(model.person_supported)}</span></div>
        <div className="status-row"><span className="status-row-label">Multi-pessoa</span><span className="status-row-value">{model.multi_person_detection ? "ativo" : "inativo"}</span></div>
        <div className="status-row"><span className="status-row-label">Máx. detecções</span><span className="status-row-value">{model.max_detections ?? "-"}</span></div>
        <div className="status-row"><span className="status-row-label">Capacete</span><span className="status-row-value">{yesNo(supported?.helmet)}</span></div>
        <div className="status-row"><span className="status-row-label">Colete</span><span className="status-row-value">{yesNo(supported?.vest)}</span></div>
        <div className="status-row"><span className="status-row-label">Luvas</span><span className="status-row-value">{yesNo(supported?.gloves)}</span></div>
      </div>
      <details>
        <summary>Classes carregadas</summary>
        <div className="class-list">
          {classes.length ? (
            classes.slice(0, 140).map((item) => (
              <span className="class-chip" key={`${item.id}`}>
                {item.id} · {item.normalized || item.name}
              </span>
            ))
          ) : (
            <span className="class-chip">Nenhuma classe disponível</span>
          )}
        </div>
      </details>
    </Panel>
  );
}
