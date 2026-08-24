import { useEffect } from "react";
import { subscribeToServerEvents, useDashboardStore, ROLE_ACCESS } from "./store/dashboardStore";
import { Topbar, MessageBar } from "./components/layout";
import { CameraGrid } from "./components/camera-grid";
import { OperatorKiosk } from "./components/operator-kiosk";
import { CameraFocus } from "./components/camera-focus";
import { CommandPalette } from "./components/command-palette";
import { Panel } from "./components/common";
import { LoginScreen } from "./components/login";

// Placeholder do dashboard agregado do Supervisor — o conteúdo de verdade
// (risco consolidado, ranking por criticidade, feed de alertas combinado,
// auditoria de falso positivo, exportação) é o próximo passo. Existir aqui
// evita a tela ficar em branco se alguém já clicar em "Visão geral" antes
// disso ser implementado.
function SupervisorOverviewPlaceholder({ onBack }: { onBack: () => void }) {
  return (
    <div style={{ padding: 20 }}>
      <button type="button" className="secondary small" onClick={onBack} style={{ marginBottom: 16 }}>
        ← Voltar pra grade
      </button>
      <Panel title="Visão geral — todas as câmeras" description="Dashboard agregado do Supervisor.">
        <p style={{ fontSize: 12.5, color: "var(--muted)" }}>Em construção — próximo passo.</p>
      </Panel>
    </div>
  );
}

function GridScreen() {
  const cameras = useDashboardStore((s) => s.cameras);
  const mode = useDashboardStore((s) => s.mode);
  const setScreen = useDashboardStore((s) => s.setScreen);
  const access = ROLE_ACCESS[mode];

  return (
    <div>
      <div className="view-bar">
        <div className="view-bar-left">
          <h2>Câmeras</h2>
          <span>
            {cameras.length} cadastrada{cameras.length === 1 ? "" : "s"}
          </span>
        </div>
        {access.hasOverview && (
          <button type="button" className="secondary small" onClick={() => setScreen("overview")}>
            Visão geral
          </button>
        )}
      </div>
      <CameraGrid />
    </div>
  );
}

export default function App() {
  const user = useDashboardStore((s) => s.user);
  const authChecked = useDashboardStore((s) => s.authChecked);
  const checkSession = useDashboardStore((s) => s.checkSession);
  const mode = useDashboardStore((s) => s.mode);
  const screen = useDashboardStore((s) => s.screen);
  const camId = useDashboardStore((s) => s.camId);
  const camerasLoading = useDashboardStore((s) => s.camerasLoading);
  const hasCameras = useDashboardStore((s) => s.cameras.length > 0);
  const bootstrap = useDashboardStore((s) => s.bootstrap);
  const loadCameras = useDashboardStore((s) => s.loadCameras);
  const setScreen = useDashboardStore((s) => s.setScreen);

  // Primeiro descobre QUEM está logado. Só depois vale a pena abrir socket e
  // buscar dados: sem sessão, tudo isso responderia 401.
  useEffect(() => {
    checkSession().catch((err) => console.error("[checkSession] failed", err));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!user) return;
    const unsubscribe = subscribeToServerEvents();
    bootstrap().catch((err) => console.error("[bootstrap] failed", err));
    loadCameras().catch((err) => console.error("[loadCameras] failed", err));
    return unsubscribe;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id]);

  if (!authChecked) {
    return <div className="login-shell" aria-busy="true" />;
  }
  if (!user) {
    return <LoginScreen />;
  }

  // Roteamento por papel: Operador sempre kiosk (trava aplicada em setMode
  // no store, screen já chega como "kiosk"); Técnico/Supervisor navegam
  // entre grid/foco/overview livremente dentro do próprio `screen`.
  let content;
  if (camerasLoading) {
    content = <div style={{ padding: 40, color: "var(--muted)", fontSize: 13 }}>Carregando câmeras…</div>;
  } else if (mode === "operator") {
    content =
      camId !== null ? (
        <OperatorKiosk camId={camId} />
      ) : (
        <div style={{ padding: 40, color: "var(--muted)", fontSize: 13 }}>
          Nenhuma câmera cadastrada ainda. Peça pro Técnico/Supervisor cadastrar uma câmera antes de você conseguir monitorar.
        </div>
      );
  } else if (screen === "focus" && hasCameras) {
    content = <CameraFocus />;
  } else if (screen === "overview" && ROLE_ACCESS[mode].hasOverview) {
    content = <SupervisorOverviewPlaceholder onBack={() => setScreen("grid")} />;
  } else {
    content = <GridScreen />;
  }

  return (
    <div className="shell">
      <CommandPalette />
      <Topbar />
      <MessageBar />
      {content}
    </div>
  );
}