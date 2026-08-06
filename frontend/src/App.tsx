import { useEffect } from "react";
import { motion } from "motion/react";
import { subscribeToServerEvents, useDashboardStore, type ViewMode } from "./store/dashboardStore";
import { Topbar, MessageBar } from "./components/layout";
import { Sidebar, OverlayControls } from "./components/features";
import { VideoCard, RiskAreaEditorPanel } from "./components/video";
import { ComplianceCard, PersonCard } from "./components/compliance";
import { RiskScoreCard } from "./components/risk-score";
import { AlertPanel, AlertHistoryPanel } from "./components/alerts";
import { TimelineCard } from "./components/timeline";
import { ChecklistPanel, SettingsPanel, ModelStatusPanel } from "./components/diagnostics";
import { ExportPanel } from "./components/export";
import { CommandPalette } from "./components/command-palette";
import { Tabs, type TabItem } from "./components/common";

// O vídeo nunca desmonta (evita reconectar o stream MJPEG a cada troca de
// perfil) — só a proporção do grid muda. As abas trocam qual painel completo
// aparece na side-column; estado de aba ativa fica em activeTabByMode no
// store (Fase 4: precisa ser lido pelo cmdk também, não só pelo App), mas
// não persiste em localStorage — só o perfil em si (mode) persiste.
const OPERATOR_TABS: TabItem[] = [
  { key: "risk", label: "Risco", content: <RiskScoreCard /> },
  { key: "alerts", label: "Alertas", content: <AlertPanel /> },
  { key: "compliance", label: "Conformidade", content: <ComplianceCard /> },
  { key: "people", label: "Pessoas", content: <PersonCard /> },
  { key: "timeline", label: "Timeline", content: <TimelineCard /> },
];

const TECHNICAL_TABS: TabItem[] = [
  { key: "checklist", label: "Checklist", content: <ChecklistPanel /> },
  { key: "overlay", label: "Overlay", content: <OverlayControls /> },
  { key: "zone", label: "Zona", content: <RiskAreaEditorPanel /> },
  { key: "settings", label: "Parâmetros", content: <SettingsPanel /> },
  { key: "model", label: "Modelo", content: <ModelStatusPanel /> },
  { key: "history", label: "Histórico", content: <AlertHistoryPanel /> },
];

// Sem controles de calibração/checklist — é o perfil de gestão de risco:
// tendência, histórico e exportação, reaproveitando os mesmos componentes
// já usados em Operador/Técnico (nenhum deles é técnico-only por natureza).
const SUPERVISOR_TABS: TabItem[] = [
  { key: "trend", label: "Tendência", content: <RiskScoreCard /> },
  { key: "history", label: "Histórico", content: <AlertHistoryPanel /> },
  { key: "export", label: "Exportação", content: <ExportPanel /> },
];

const TABS_BY_MODE: Record<ViewMode, TabItem[]> = {
  operator: OPERATOR_TABS,
  technical: TECHNICAL_TABS,
  supervisor: SUPERVISOR_TABS,
};

export default function App() {
  const mode = useDashboardStore((s) => s.mode);
  const bootstrap = useDashboardStore((s) => s.bootstrap);
  const activeTabByMode = useDashboardStore((s) => s.activeTabByMode);
  const setActiveTab = useDashboardStore((s) => s.setActiveTab);

  useEffect(() => {
    const unsubscribe = subscribeToServerEvents();
    bootstrap().catch((err) => console.error("[bootstrap] failed", err));
    return unsubscribe;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="shell">
      <CommandPalette />
      <Topbar />
      <MessageBar />
      <div className="shell-body">
        <Sidebar />
        {/* data-mode escolhe a proporção do grid instantaneamente (fr não
            interpola de forma confiável); a prop `layout` nos dois filhos
            é quem anima o FLIP resultante. */}
        <main className="main" data-mode={mode}>
          <motion.div className="stage" layout>
            <VideoCard />
          </motion.div>
          <motion.div className="side-column" layout>
            <Tabs tabs={TABS_BY_MODE[mode]} active={activeTabByMode[mode]} onChange={(key) => setActiveTab(mode, key)} idPrefix={mode} />
          </motion.div>
        </main>
      </div>
    </div>
  );
}
