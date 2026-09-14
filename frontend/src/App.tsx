import { useCallback, useEffect, useState } from "react";
import { subscribeToServerEvents, useDashboardStore, ROLE_ACCESS } from "./store/dashboardStore";
import { Topbar, MessageBar, ScreenHead } from "./components/layout";
import { CameraGrid, type EstadoDaCamera } from "./components/camera-grid";
import { OperatorKiosk } from "./components/operator-kiosk";
import { CameraFocus } from "./components/camera-focus";
import { CommandPalette } from "./components/command-palette";
import { Panel } from "./components/common";
import { LoginScreen } from "./components/login";

// Placeholder do dashboard agregado do Supervisor. O conteúdo de verdade
// (risco consolidado, ranking por criticidade, feed combinado, auditoria de
// falso positivo, exportação) é o próximo passo. Existir aqui evita a tela
// ficar em branco se alguém clicar em "Visão geral" antes disso.
function SupervisorOverviewPlaceholder({ onBack }: { onBack: () => void }) {
  return (
    <div className="screen">
      <ScreenHead
        title="Visão geral"
        sub="Todas as câmeras"
        actions={
          <button type="button" className="ghost" onClick={onBack}>
            Voltar para a grade
          </button>
        }
      />
      <Panel title="Dashboard agregado" description="Consolidado do Supervisor.">
        <p className="empty-state">Em construção, é o próximo passo.</p>
      </Panel>
    </div>
  );
}

function GridScreen() {
  const cameras = useDashboardStore((s) => s.cameras);
  const mode = useDashboardStore((s) => s.mode);
  const setScreen = useDashboardStore((s) => s.setScreen);
  const access = ROLE_ACCESS[mode];

  // Cada cartão consulta o status da própria câmera; a linha embaixo do
  // título só agrega o que os cartões já sabem.
  const [estados, setEstados] = useState<Record<number, EstadoDaCamera>>({});
  const onEstado = useCallback((id: number, estado: EstadoDaCamera) => {
    setEstados((prev) => (prev[id] === estado ? prev : { ...prev, [id]: estado }));
  }, []);
  const noAr = cameras.filter((c) => estados[c.id]?.running).length;
  const alertas = cameras.reduce((n, c) => n + (estados[c.id]?.alertas.length ?? 0), 0);
  const sub = cameras.length
    ? `${noAr} de ${cameras.length} no ar, ${alertas} alerta${alertas === 1 ? "" : "s"} ativo${alertas === 1 ? "" : "s"}`
    : null;

  return (
    <div className="screen">
      <ScreenHead
        title="Câmeras"
        sub={sub}
        actions={
          access.hasOverview ? (
            <button type="button" className="ghost" onClick={() => setScreen("overview")}>
              Visão geral
            </button>
          ) : undefined
        }
      />
      <CameraGrid onEstado={onEstado} />
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
    content = <p className="centered-empty">Carregando câmeras…</p>;
  } else if (mode === "operator") {
    content =
      camId !== null ? (
        <OperatorKiosk camId={camId} />
      ) : (
        <p className="centered-empty">
          Nenhuma câmera cadastrada ainda. Peça ao Técnico ou ao Supervisor para cadastrar a câmera do seu setor.
        </p>
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
