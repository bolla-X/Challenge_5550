import { useEffect, useState } from "react";
import { useDashboardStore } from "../store/dashboardStore";
import { Panel, EmptyState } from "./common";
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
              <input
                type="checkbox"
                checked={Boolean(draft[key])}
                onChange={(e) => setDraft((prev) => ({ ...prev, [key]: e.target.checked }))}
              />
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
      <Panel title="Modelo YOLO" className="technical-only">
        <div className="model-status">Aguardando diagnóstico.</div>
      </Panel>
    );
  }
  const statusClass = model.error ? "error" : model.ppe_ready ? "ok" : "warn";
  const statusText = model.ppe_ready ? "Modelo PPE completo" : model.error ? "Modelo indisponível" : "Modelo PPE incompleto";
  const supported = model.supported_ppe;
  const classes = model.classes || [];

  return (
    <Panel title="Modelo YOLO" className="technical-only">
      <div className={`model-status ${statusClass}`}>
        <strong>{statusText}</strong>
        <br />
        arquivo: {model.model_path || "indefinido"}
        <br />
        pessoa: {model.person_supported ? "suportado" : "não suportado"}
        <br />
        multi-pessoa: {model.multi_person_detection ? "ativo" : "inativo"}
        <br />
        máx. detecções: {model.max_detections ?? "-"}
        <br />
        capacete: {supported?.helmet ? "suportado" : "não suportado"}
        <br />
        colete: {supported?.vest ? "suportado" : "não suportado"}
        <br />
        luvas: {supported?.gloves ? "suportado" : "não suportado"}
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
