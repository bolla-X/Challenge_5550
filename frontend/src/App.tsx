import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import { subscribeToServerEvents, useDashboardStore, ROLE_ACCESS } from "./store/dashboardStore";
import { Topbar, MessageBar, ScreenHead } from "./components/layout";
import { CameraGrid, totalDeIncidentes, type EstadoDaCamera } from "./components/camera-grid";
import { OperatorKiosk } from "./components/operator-kiosk";
import { GateKiosk } from "./components/gate";
import { AccountsScreen, SupervisorHome } from "./components/accounts";
import { CameraFocus } from "./components/camera-focus";
import { CommandPalette } from "./components/command-palette";
import { LoginScreen } from "./components/login";
import { ScaleProof } from "./components/scale-proof";
import { AboutScreen } from "./components/about";
import { PortalScreen } from "./components/portal";
import { TvScreen } from "./components/tv";
import { RotularScreen } from "./components/rotular";
import { DesafioScreen } from "./components/desafio";
import { PanelSkeleton } from "./components/common";
import { pluralizar } from "./utils/formato";

// Telas pesadas (three.js) só carregam quando abertas.
const GemeoScreen = lazy(() => import("./components/gemeo/gemeo-screen"));
const SimuladorScreen = lazy(() => import("./components/simulador"));
const AuditoriaScreen = lazy(() => import("./components/auditoria"));
const LigaScreen = lazy(() => import("./components/liga"));
const PalcoScreen = lazy(() => import("./components/palco"));
const PalcoControle = lazy(() => import("./components/palco").then((m) => ({ default: m.PalcoControle })));
const RetrospectivaScreen = lazy(() => import("./components/retrospectiva"));

function CarregandoTela() {
  return (
    <div className="screen" aria-busy="true">
      <PanelSkeleton lines={5} />
    </div>
  );
}

// Visão geral do Supervisor: o mesmo painel por setor do Modo TV (G8), com
// atalhos para as telas de tela cheia (abrem em outra aba, para a TV/totem).
function SupervisorOverview({ onBack }: { onBack: () => void }) {
  const atalhos: [string, string][] = [
    ["/tv", "Modo TV"],
    ["/gemeo", "Gêmeo digital"],
    ["/liga", "Liga de Setores"],
    ["/palco", "Apresentação"],
    ["/portal", "Portal de Entrada"],
    ["/desafio", "Você vs. a IA"],
    ["/rotular", "Rotular recortes"],
  ];
  return (
    <div className="screen">
      <ScreenHead
        title="Visão geral"
        sub="Por setor, nunca por pessoa"
        actions={
          <>
            {atalhos.map(([href, rotulo]) => (
              <a key={href} className="button ghost" href={href} target="_blank" rel="noopener noreferrer">
                {rotulo}
              </a>
            ))}
            <button type="button" className="ghost" onClick={onBack}>
              Voltar para a grade
            </button>
          </>
        }
      />
      <TvScreen embutido />
    </div>
  );
}

function GridScreen() {
  const cameras = useDashboardStore((s) => s.cameras);
  const mode = useDashboardStore((s) => s.mode);
  const setScreen = useDashboardStore((s) => s.setScreen);
  const access = ROLE_ACCESS[mode];
  const [escala, setEscala] = useState(false);

  // Cada cartão consulta o status da própria câmera; a linha embaixo do
  // título só agrega o que os cartões já sabem.
  const [estados, setEstados] = useState<Record<number, EstadoDaCamera>>({});
  const onEstado = useCallback((id: number, estado: EstadoDaCamera) => {
    setEstados((prev) => (prev[id] === estado ? prev : { ...prev, [id]: estado }));
  }, []);
  const noAr = cameras.filter((c) => estados[c.id]?.running).length;
  const incidentes = cameras.reduce((n, c) => n + totalDeIncidentes(estados[c.id]), 0);
  const sub = cameras.length
    ? `${noAr} de ${cameras.length} no ar, ${pluralizar(incidentes, "incidente")} ${incidentes === 1 ? "ativo" : "ativos"}`
    : null;

  return (
    <div className="screen">
      <ScreenHead
        title="Câmeras"
        sub={sub}
        actions={
          <>
            {access.canConfigure && (
              <button type="button" className="ghost" onClick={() => setEscala(true)}>
                Prova de escala
              </button>
            )}
            {access.hasOverview && (
              <button type="button" className="ghost" onClick={() => setScreen("overview")}>
                Visão geral
              </button>
            )}
          </>
        }
      />
      <CameraGrid onEstado={onEstado} />
      {escala && <ScaleProof onClose={() => setEscala(false)} />}
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
  const cameras = useDashboardStore((s) => s.cameras);
  const camerasLoading = useDashboardStore((s) => s.camerasLoading);
  const hasCameras = useDashboardStore((s) => s.cameras.length > 0);
  const bootstrap = useDashboardStore((s) => s.bootstrap);
  const loadCameras = useDashboardStore((s) => s.loadCameras);
  const setScreen = useDashboardStore((s) => s.setScreen);

  // Tecla X: Modo Raio-X (X5) em qualquer tela com vídeo ao vivo.
  useEffect(() => {
    const tecla = (e: KeyboardEvent) => {
      if (e.key !== "x" && e.key !== "X") return;
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      const alvo = e.target as HTMLElement | null;
      if (alvo && (alvo.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(alvo.tagName))) return;
      useDashboardStore.getState().alternarRaioX();
    };
    window.addEventListener("keydown", tecla);
    return () => window.removeEventListener("keydown", tecla);
  }, []);

  // Primeiro descobre QUEM está logado. Só depois vale a pena abrir socket e
  // buscar dados: sem sessão, tudo isso responderia 401.
  useEffect(() => {
    checkSession().catch((err) => console.error("[checkSession] failed", err));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!user) return;
    const unsubscribe = subscribeToServerEvents();
    let ativo = true;
    // Falha de REDE (fetch abortado por navegação, servidor ocupado) não é erro
    // do app: tenta de novo em 2 s enquanto a tela estiver montada. Outras
    // falhas continuam como erro no console.
    const carregar = (nome: string, fn: () => Promise<unknown>, tentativa = 0): void => {
      fn().catch((err) => {
        const rede = err instanceof TypeError && /fetch/i.test(err.message);
        if (rede && ativo && tentativa < 5) {
          console.warn(`[${nome}] rede indisponível, tentando de novo`, err);
          window.setTimeout(() => ativo && carregar(nome, fn, tentativa + 1), 2000);
        } else if (!rede || ativo) {
          console.error(`[${nome}] failed`, err);
        }
      });
    };
    carregar("bootstrap", bootstrap);
    carregar("loadCameras", loadCameras);
    return () => {
      ativo = false;
      unsubscribe();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id]);

  // Controle da apresentação pelo celular: sem login, só com o token do QR (X6).
  if (window.location.pathname.startsWith("/palco/controle")) {
    return (
      <main id="conteudo">
        <Suspense fallback={<CarregandoTela />}>
          <PalcoControle />
        </Suspense>
      </main>
    );
  }

  if (!authChecked) {
    return <div className="login-shell" aria-busy="true" />;
  }
  if (!user) {
    return (
      <main id="conteudo">
        <LoginScreen />
      </main>
    );
  }

  // Roteamento por papel: Operador sempre kiosk (trava aplicada em setMode
  // no store, screen já chega como "kiosk"); Técnico/Supervisor navegam
  // entre grid/foco/overview livremente dentro do próprio `screen`.
  // Telas de tela cheia por endereço (PR3): sem barra superior, para TV/totem.
  if (window.location.pathname.startsWith("/desafio")) {
    return (
      <main id="conteudo">
        <DesafioScreen />
      </main>
    );
  }
  if (window.location.pathname.startsWith("/rotular")) {
    return (
      <main id="conteudo">
        <RotularScreen />
      </main>
    );
  }
  if (window.location.pathname.startsWith("/gemeo")) {
    return (
      <main id="conteudo">
        <Suspense fallback={<CarregandoTela />}>
          <GemeoScreen />
        </Suspense>
      </main>
    );
  }
  if (window.location.pathname.startsWith("/palco")) {
    return (
      <main id="conteudo">
        <Suspense fallback={<CarregandoTela />}>
          <PalcoScreen />
        </Suspense>
      </main>
    );
  }
  if (window.location.pathname.startsWith("/liga")) {
    return (
      <main id="conteudo">
        <Suspense fallback={<CarregandoTela />}>
          <LigaScreen />
        </Suspense>
      </main>
    );
  }
  if (window.location.pathname.startsWith("/retrospectiva")) {
    return (
      <main id="conteudo">
        <Suspense fallback={<CarregandoTela />}>
          <RetrospectivaScreen />
        </Suspense>
      </main>
    );
  }
  if (window.location.pathname.startsWith("/auditoria")) {
    return (
      <main id="conteudo">
        <Suspense fallback={<CarregandoTela />}>
          <AuditoriaScreen />
        </Suspense>
      </main>
    );
  }
  if (window.location.pathname.startsWith("/simulador")) {
    return (
      <main id="conteudo">
        <Suspense fallback={<CarregandoTela />}>
          <SimuladorScreen />
        </Suspense>
      </main>
    );
  }
  if (window.location.pathname.startsWith("/tv")) {
    return (
      <main id="conteudo">
        <TvScreen />
      </main>
    );
  }
  if (window.location.pathname.startsWith("/portal")) {
    return <main id="conteudo">{camerasLoading ? <CarregandoTela /> : <PortalScreen />}</main>;
  }

  let content;
  if (camerasLoading) {
    content = <CarregandoTela />;
  } else if (mode === "operator") {
    content =
      camId !== null ? (
        cameras.find((c) => c.id === camId)?.gate_required ? <GateKiosk camId={camId} /> : <OperatorKiosk camId={camId} />
      ) : (
        <p className="centered-empty">
          Nenhuma câmera cadastrada ainda. Peça ao Técnico ou ao Supervisor para cadastrar a câmera do seu setor.
        </p>
      );
  } else if (screen === "sobre") {
    content = <AboutScreen />;
  } else if (mode === "supervisor" && screen === "home") {
    content = <SupervisorHome />;
  } else if (mode === "supervisor" && screen === "accounts") {
    content = <AccountsScreen />;
  } else if (screen === "focus" && hasCameras) {
    content = <CameraFocus />;
  } else if (screen === "overview" && ROLE_ACCESS[mode].hasOverview) {
    content = <SupervisorOverview onBack={() => setScreen("grid")} />;
  } else {
    content = (
      <>
        {mode === "supervisor" && (
          <div className="screen" style={{ paddingBottom: 0 }}>
            <button type="button" className="ghost small" onClick={() => setScreen("home")}>
              ← Início
            </button>
          </div>
        )}
        <GridScreen />
      </>
    );
  }

  return (
    <div className="shell">
      <CommandPalette />
      <Topbar />
      <MessageBar />
      <main id="conteudo">{content}</main>
    </div>
  );
}
