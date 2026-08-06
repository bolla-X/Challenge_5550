import { useEffect } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { subscribeToServerEvents, useDashboardStore } from "./store/dashboardStore";

const EASE = [0.16, 1, 0.3, 1] as const; // matches tokens.css --ease
import { Topbar, MessageBar } from "./components/layout";
import { Sidebar, OverlayControls } from "./components/features";
import { VideoCard, RiskAreaEditorPanel } from "./components/video";
import { ComplianceCard, PersonCard } from "./components/compliance";
import { RiskScoreCard } from "./components/risk-score";
import { AlertPanel, AlertHistoryPanel } from "./components/alerts";
import { TimelineCard } from "./components/timeline";
import { ChecklistPanel, SettingsPanel, ModelStatusPanel } from "./components/diagnostics";
import { CommandPalette } from "./components/command-palette";

export default function App() {
  const mode = useDashboardStore((s) => s.mode);
  const bootstrap = useDashboardStore((s) => s.bootstrap);
  const shouldReduceMotion = useReducedMotion();

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
        <main className="main">
          <div className="main-grid">
            <VideoCard />
            <div className="side-column">
              <RiskScoreCard />
              <AlertPanel />
              <ComplianceCard />
              <PersonCard />
              <TimelineCard />
            </div>
          </div>
          {/* Comunica que esse conteúdo técnico está se expandindo do fluxo
              atual, não um corte de contexto — height+opacity, sem slide. */}
          <AnimatePresence initial={false}>
            {mode === "technical" && (
              <motion.div
                className="technical-drawer"
                initial={shouldReduceMotion ? false : { height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={shouldReduceMotion ? { opacity: 0 } : { height: 0, opacity: 0 }}
                transition={{ duration: shouldReduceMotion ? 0.001 : 0.22, ease: EASE }}
                style={{ overflow: "hidden" }}
              >
                <ChecklistPanel />
                <OverlayControls />
                <RiskAreaEditorPanel />
                <SettingsPanel />
                <ModelStatusPanel />
                <AlertHistoryPanel />
              </motion.div>
            )}
          </AnimatePresence>
        </main>
      </div>
    </div>
  );
}
