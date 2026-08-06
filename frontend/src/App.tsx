import { useEffect } from "react";
import { subscribeToServerEvents, useDashboardStore } from "./store/dashboardStore";
import { Topbar, MessageBar } from "./components/layout";
import { Sidebar, OverlayControls } from "./components/features";
import { VideoCard, RiskAreaEditorPanel } from "./components/video";
import { ComplianceCard, PersonCard } from "./components/compliance";
import { AlertPanel, AlertHistoryPanel } from "./components/alerts";
import { TimelineCard } from "./components/timeline";
import { ChecklistPanel, SettingsPanel, ModelStatusPanel } from "./components/diagnostics";

export default function App() {
  const mode = useDashboardStore((s) => s.mode);
  const bootstrap = useDashboardStore((s) => s.bootstrap);

  useEffect(() => {
    const unsubscribe = subscribeToServerEvents();
    bootstrap().catch((err) => console.error("[bootstrap] failed", err));
    return unsubscribe;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="shell">
      <Topbar />
      <MessageBar />
      <div className="shell-body">
        <Sidebar />
        <main className="main">
          <div className="main-grid">
            <VideoCard />
            <div className="side-column">
              <AlertPanel />
              <ComplianceCard />
              <PersonCard />
              <TimelineCard />
            </div>
          </div>
          {mode === "technical" && (
            <div className="technical-drawer">
              <ChecklistPanel />
              <OverlayControls />
              <RiskAreaEditorPanel />
              <SettingsPanel />
              <ModelStatusPanel />
              <AlertHistoryPanel />
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
