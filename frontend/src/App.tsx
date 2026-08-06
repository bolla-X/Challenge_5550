import { useEffect, useState } from "react";
import { motion } from "motion/react";
import { subscribeToServerEvents, useDashboardStore } from "./store/dashboardStore";
import { Topbar, MessageBar } from "./components/layout";
import { Sidebar, OverlayControls } from "./components/features";
import { VideoCard, RiskAreaEditorPanel } from "./components/video";
import { ComplianceCard, PersonCard } from "./components/compliance";
import { RiskScoreCard } from "./components/risk-score";
import { AlertPanel, AlertHistoryPanel } from "./components/alerts";
import { TimelineCard } from "./components/timeline";
import { ChecklistPanel, SettingsPanel, ModelStatusPanel } from "./components/diagnostics";
import { CommandPalette } from "./components/command-palette";
import { Tabs } from "./components/common";

// O vídeo nunca desmonta (evita reconectar o stream MJPEG a cada troca de
// modo) — só a proporção do grid muda. As abas trocam qual painel completo
// aparece na side-column; estado de aba fica aqui (App nunca desmonta) em
// vez de no zustand store, então sobrevive a alternar de modo e voltar, mas
// não precisa (nem deve) persistir em localStorage — ver dashboardStore.
const OPERATOR_TABS = [
  { key: "risk", label: "Risco", content: <RiskScoreCard /> },
  { key: "alerts", label: "Alertas", content: <AlertPanel /> },
  { key: "compliance", label: "Conformidade", content: <ComplianceCard /> },
  { key: "people", label: "Pessoas", content: <PersonCard /> },
  { key: "timeline", label: "Timeline", content: <TimelineCard /> },
];

const TECHNICAL_TABS = [
  { key: "checklist", label: "Checklist", content: <ChecklistPanel /> },
  { key: "overlay", label: "Overlay", content: <OverlayControls /> },
  { key: "zone", label: "Zona", content: <RiskAreaEditorPanel /> },
  { key: "settings", label: "Parâmetros", content: <SettingsPanel /> },
  { key: "model", label: "Modelo", content: <ModelStatusPanel /> },
  { key: "history", label: "Histórico", content: <AlertHistoryPanel /> },
];

export default function App() {
  const mode = useDashboardStore((s) => s.mode);
  const bootstrap = useDashboardStore((s) => s.bootstrap);
  const [operatorTab, setOperatorTab] = useState(OPERATOR_TABS[0].key);
  const [technicalTab, setTechnicalTab] = useState(TECHNICAL_TABS[0].key);

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
            {mode === "operator" ? (
              <Tabs tabs={OPERATOR_TABS} active={operatorTab} onChange={setOperatorTab} idPrefix="operator" />
            ) : (
              <Tabs tabs={TECHNICAL_TABS} active={technicalTab} onChange={setTechnicalTab} idPrefix="technical" />
            )}
          </motion.div>
        </main>
      </div>
    </div>
  );
}
