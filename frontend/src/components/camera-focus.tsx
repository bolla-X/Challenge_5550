import { useState } from "react";
import { Sidebar, OverlayControls } from "./features";
// Sidebar de features por câmera do mock (Passo 2, CameraSidebar) foi
// substituída pela Sidebar real: o backend ainda é single-source, então
// ligar/desligar aqui precisa refletir no backend de verdade (mesmo
// raciocínio do Checklist/Zona/Overlay/Modelo/Gráficos acima) — senão o
// toggle parece funcionar mas não muda nada na detecção real.
import { Tabs, Panel, Badge, EmptyState, type TabItem } from "./common";
import { VideoCard, RiskAreaEditorPanel } from "./video";
import { ChecklistPanel, ModelStatusPanel, SettingsPanel } from "./diagnostics";
import { RiskScoreCard } from "./risk-score";
import { AlertPanel, AlertHistoryPanel } from "./alerts";
import { ComplianceCard, PersonCard } from "./compliance";
import { TimelineCard } from "./timeline";
import { ExportPanel } from "./export";
import { useDashboardStore, type ViewMode } from "../store/dashboardStore";
import type { CameraMock } from "../api/types";

// Tendência de risco (aba "Gráficos" do Supervisor) também já existia real
// — RiskScoreCard em risk-score.tsx, ligado ao /risk-score do backend.
// O painel próprio que eu tinha aqui usava um número fixo do mock (por
// isso não subia com detecções reais); reaproveitado abaixo sem versão
// mock própria, mesmo raciocínio do Checklist/Zona/Overlay/Modelo.

// Checklist (preflight real: backend/banco/vídeo/modelo/limpeza/snapshots)
// e Overlay já existiam como componentes reais (ChecklistPanel em
// diagnostics.tsx, OverlayControls em features.tsx) — reaproveitados
// direto abaixo, sem versão mock própria pra esta tela.

function CameraConfigPanel({ camera }: { camera: CameraMock }) {
  return (
    <Panel title="Configuração da câmera" description="Fonte de vídeo e identificação — específico desta câmera.">
      <div className="settings-grid">
        <label>
          Nome
          <input type="text" defaultValue={camera.name} />
        </label>
        <label>
          Local
          <input type="text" defaultValue={camera.location} />
        </label>
        <label>
          Tipo de fonte
          <select defaultValue={camera.source_type}>
            <option>USB</option>
            <option>RTSP</option>
            <option>Arquivo</option>
          </select>
        </label>
        <label>
          Endereço / índice
          <input type="text" defaultValue={camera.source} />
        </label>
        <label>
          FPS alvo
          <input type="number" defaultValue={camera.fps} />
        </label>
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 14 }}>
        <button type="button" className="secondary small" onClick={() => alert("Conexão testada com sucesso (mock).")}>
          Testar conexão
        </button>
        <button type="button" className="secondary small" onClick={() => alert("Escolha de qual câmera copiar as features/parâmetros (mock).")}>
          Clonar configuração de outra câmera
        </button>
      </div>
      <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
        <button type="button" onClick={() => alert("Câmera salva (mock).")}>
          Salvar câmera
        </button>
        <button
          type="button"
          className="secondary small"
          style={{ color: "var(--danger)", borderColor: "rgba(239,68,68,.4)" }}
          onClick={() => confirm("Remover esta câmera do sistema?") && alert("Câmera removida (mock).")}
        >
          Remover câmera
        </button>
      </div>
    </Panel>
  );
}

// Parâmetros e Modelo também já existiam reais (SettingsPanel e
// ModelStatusPanel em diagnostics.tsx) — é o ModelStatusPanel que mostra o
// aviso "modelo YOLO carregado não possui classes de EPI" quando aplicável;
// a versão mock que eu tinha colocado aqui escondia esse aviso, por isso
// sumiu da tela até essa correção.

function LogsPanel({ camera }: { camera: CameraMock }) {
  return (
    <Panel title="Log de erros" description="Exceções e eventos técnicos desta câmera." action={<Badge>{camera.error_log.length}</Badge>}>
      <div className="row-list">
        {camera.error_log.length ? (
          camera.error_log.map((e, i) => (
            <div className="row-item" key={i}>
              <span className="row-dot warning" />
              <div>
                <strong>{e.msg}</strong>
                <span>{e.time}</span>
              </div>
            </div>
          ))
        ) : (
          <EmptyState>Nenhuma exceção registrada.</EmptyState>
        )}
      </div>
    </Panel>
  );
}

// Histórico de alertas, Pessoas (com status de risco por pessoa) e Timeline
// também já existiam reais: AlertHistoryPanel/AlertPanel em alerts.tsx,
// PersonCard em compliance.tsx, TimelineCard em timeline.tsx. Mesmo
// raciocínio dos outros — reaproveitados direto no TABS_BY_MODE abaixo.

const TABS_BY_MODE: Record<Exclude<ViewMode, "operator">, TabItem[]> = {
  technical: [
    { key: "checklist", label: "Checklist", content: <ChecklistPanel /> },
    { key: "alerts", label: "Alertas", content: <AlertPanel /> },
    { key: "compliance", label: "Conformidade", content: <ComplianceCard /> },
    { key: "people", label: "Pessoas", content: <PersonCard /> },
    { key: "timeline", label: "Timeline", content: <TimelineCard /> },
    { key: "overlay", label: "Overlay", content: <OverlayControls /> },
    { key: "zone", label: "Zona", content: <RiskAreaEditorPanel /> },
    { key: "camconfig", label: "Config. câmera", content: <></> },
    { key: "settings", label: "Parâmetros", content: <SettingsPanel /> },
    { key: "model", label: "Modelo", content: <ModelStatusPanel /> },
    { key: "logs", label: "Logs", content: <></> },
    { key: "history", label: "Histórico", content: <AlertHistoryPanel /> },
  ],
  supervisor: [
    { key: "trend", label: "Gráficos", content: <RiskScoreCard /> },
    { key: "checklist", label: "Checklist", content: <ChecklistPanel /> },
    { key: "alerts", label: "Alertas", content: <AlertPanel /> },
    { key: "compliance", label: "Conformidade", content: <ComplianceCard /> },
    { key: "people", label: "Pessoas", content: <PersonCard /> },
    { key: "timeline", label: "Timeline", content: <TimelineCard /> },
    { key: "overlay", label: "Overlay", content: <OverlayControls /> },
    { key: "zone", label: "Zona", content: <RiskAreaEditorPanel /> },
    { key: "camconfig", label: "Config. câmera", content: <></> },
    { key: "settings", label: "Parâmetros", content: <SettingsPanel /> },
    { key: "model", label: "Modelo", content: <ModelStatusPanel /> },
    { key: "logs", label: "Logs", content: <></> },
    { key: "history", label: "Histórico", content: <AlertHistoryPanel /> },
    { key: "export", label: "Exportação", content: <ExportPanel /> },
  ],
};

/**
 * Foco individual de uma câmera — Técnico/Supervisor (mock). Reaproveita
 * <Sidebar> real (backend single-source) pra features + os mesmos componentes de card
 * (Panel/Badge/Tabs) já usados no resto do app. Operador nunca chega aqui.
 */
export function CameraFocus() {
  const camId = useDashboardStore((s) => s.camId);
  const cameras = useDashboardStore((s) => s.cameras);
  const setCamId = useDashboardStore((s) => s.setCamId);
  const setScreen = useDashboardStore((s) => s.setScreen);
  const mode = useDashboardStore((s) => s.mode);
  const camera = cameras.find((c) => c.id === camId);
  const [activeTab, setActiveTab] = useState<string>(mode === "supervisor" ? "trend" : "checklist");

  if (!camera || mode === "operator") return null;

  // Preenche o conteúdo real das abas que dependem da câmera selecionada
  // (as outras já vêm prontas no TABS_BY_MODE acima, incluindo os
  // painéis reais conectados ao backend — checklist/overlay/zona/
  // parâmetros/modelo não mudam por câmera porque o backend ainda é
  // single-source; só camconfig/logs/trend usam dado do mock por câmera).
  const tabs = TABS_BY_MODE[mode].map((tab) => {
    if (tab.key === "camconfig") return { ...tab, content: <CameraConfigPanel camera={camera} /> };
    if (tab.key === "logs") return { ...tab, content: <LogsPanel camera={camera} /> };
    return tab;
  });

  return (
    <>
      <div className="focus-topstrip">
        <button type="button" className="secondary small" onClick={() => setScreen("grid")}>
          ← Voltar pra grade
        </button>
        <div className="focus-cam-select">
          {cameras.map((c) => (
            <button
              key={c.id}
              type="button"
              className={`focus-cam-pill ${c.id === camId ? "active" : ""}`.trim()}
              onClick={() => setCamId(c.id)}
            >
              Cam {c.id}
            </button>
          ))}
        </div>
        <div className="focus-title">
          câmera: <b>{camera.name}</b>
        </div>
      </div>
      <div className="shell-body">
        <Sidebar />
        <main className="main">
          <div>
            {/* Backend ainda é single-source (ver conversa: "usa os modelos
                que já tem, mesma câmera em todos por enquanto") — o mesmo
                VideoCard real (feed + YOLO + botão Iniciar) aparece em
                qualquer câmera do mock que você abrir aqui. Quando o
                backend ganhar multi-source de verdade, troca por um feed
                por camId. */}
            <VideoCard />
          </div>
          <div className="side-column">
            <Tabs tabs={tabs} active={activeTab} onChange={setActiveTab} idPrefix={`focus-${camId}`} />
          </div>
        </main>
      </div>
    </>
  );
}
