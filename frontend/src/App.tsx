import { useEffect } from "react";
import { subscribeToServerEvents, useDashboardStore } from "./store/dashboardStore";
import { TopBar, MessageBar, StatusRibbon } from "./components/layout";
import { FeatureStrip, OverlayControls } from "./components/features";
import { VideoPanel, RiskAreaEditorPanel } from "./components/video";
import { ComplianceMatrix, PersonCards } from "./components/compliance";
import { ActiveAlertsPanel, AlertHistoryPanel } from "./components/alerts";
import { EventTimelinePanel } from "./components/timeline";
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
    <div className={`app ${mode === "technical" ? "technical-mode" : "operator-mode"}`}>
      <TopBar />
      <MessageBar />
      <StatusRibbon />
      <FeatureStrip />

      <main className="layout">
        <section className="main-column">
          <VideoPanel />
          <section className="grid-two">
            <ComplianceMatrix />
            <PersonCards />
          </section>
        </section>

        <aside className="side-column">
          <ActiveAlertsPanel />
          <EventTimelinePanel />
          <ChecklistPanel />
          <OverlayControls />
          <RiskAreaEditorPanel />
          <SettingsPanel />
          <ModelStatusPanel />
          <AlertHistoryPanel />
        </aside>
      </main>
    </div>
  );
}
