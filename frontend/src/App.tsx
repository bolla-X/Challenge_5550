import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import { subscribeToServerEvents, useDashboardStore, ROLE_ACCESS } from "./store/dashboardStore";
import { Topbar, MessageBar, ScreenHead } from "./components/layout";
import { CameraGrid, totalDeIncidentes, type EstadoDaCamera } from "./components/camera-grid";
import { OperatorKiosk } from "./components/operator-kiosk";
import { GateKiosk } from "./components/gate";
import { AccountsScreen, SupervisorHome } from "./components/accounts";
import { CameraFocus } from "./components/camera-focus";
import { CommandPalette } from "./components/command-palette";
import { TourGuiado } from "./components/tour";
import { BotaoDeAjuda } from "./components/ajuda";
import { artigoDaTela } from "./ajuda/artigos";
import { LoginScreen } from "./components/login";
import { ScaleProof } from "./components/scale-proof";
import { AboutScreen } from "./components/about";
import { PortalScreen } from "./components/portal";
import { TvScreen } from "./components/tv";
import { RotularScreen } from "./components/rotular";
import { DesafioScreen } from "./components/desafio";
import { PanelSkeleton } from "./components/common";
import { AcessoNegado, PaginaNaoEncontrada } from "./components/excecoes";
import { pluralizar } from "./utils/formato";

// Telas pesadas (three.js) só carregam quando abertas.
const GemeoScreen = lazy(() => import("./components/gemeo/gemeo-screen"));
const SimuladorScreen = lazy(() => import("./components/simulador"));
const AuditoriaScreen = lazy(() => import("./components/auditoria"));
const LigaScreen = lazy(() => import("./components/liga"));
const PalcoScreen = lazy(() => import("./components/palco"));
const PalcoControle = lazy(() => import("./components/palco").then((m) => ({ default: m.PalcoControle })));
const RetrospectivaScreen = lazy(() => import("./components/retrospectiva"));
const EvacuacaoScreen = lazy(() => import("./components/evacuacao"));
const TorreScreen = lazy(() => import("./components/torre"));
const RegrasScreen = lazy(() => import("./components/regras"));
const PermissoesScreen = lazy(() => import("./components/permissoes"));
const OnboardingScreen = lazy(() => import("./components/onboarding"));
const ProdutoScreen = lazy(() => import("./components/produto"));
const CaixaDeEntradaScreen = lazy(() => import("./components/caixa-de-entrada"));
const AjudaScreen = lazy(() => import("./components/ajuda"));
const PaginaStatus = lazy(() => import("./components/pagina-status"));
const NovidadesScreen = lazy(() => import("./components/novidades"));
const ConfiguracoesScreen = lazy(() => import("./components/configuracoes"));
const IntervencoesScreen = lazy(() => import("./components/intervencoes"));
const BuscaTrilhasScreen = lazy(() => import("./components/busca-trilhas"));

// Marcado no `pagehide`/`beforeunload`: a partir daí, fetch abortado é esperado.
let saindoDaPagina = false;
if (typeof window !== "undefined") {
  const marcar = () => {
    saindoDaPagina = true;
  };
  window.addEventListener("beforeunload", marcar);
  window.addEventListener("pagehide", marcar);
}

const PREFIXOS_CONHECIDOS = [
  "/palco", "/desafio", "/rotular", "/gemeo", "/liga", "/retrospectiva", "/auditoria", "/simulador", "/evacuacao",
  "/permissoes", "/regras", "/torre", "/tv", "/portal", "/dashboard", "/primeiro-acesso", "/produto", "/caixa-de-entrada", "/ajuda", "/status", "/novidades", "/configuracoes", "/intervencoes", "/busca",
];

// Telas de tela cheia que exigem um tipo de conta mínimo (o mesmo que a API
// exige). Quem não tem o tipo vê "acesso negado" explicado, sem a tela chamar
// a API e colecionar 403 (crawler da MISSÃO 4).
const PAPEL_MINIMO: [string, "technical" | "supervisor", string][] = [
  ["/auditoria", "technical", "a auditoria da cadeia de custódia"],
  ["/simulador", "technical", "o simulador de regras"],
  ["/regras", "technical", "o editor de regras"],
  ["/evacuacao", "technical", "o Modo Evacuação"],
  ["/rotular", "technical", "a fila de rótulos"],
  ["/palco", "technical", "o Modo Apresentação"],
  ["/primeiro-acesso", "supervisor", "o primeiro acesso"],
  ["/caixa-de-entrada", "supervisor", "a caixa de entrada"],
  ["/status", "technical", "a página de status"],
  ["/intervencoes", "technical", "o antes e depois das intervenções"],
  ["/busca", "technical", "a busca nas trilhas"],
];
const NIVEL: Record<string, number> = { operator: 1, technical: 2, supervisor: 3 };

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
    ["/torre", "Torre de luz"],
    ["/evacuacao", "Evacuação"],
    ["/regras", "Editor de regras"],
    ["/permissoes", "Permissões de trabalho"],
    ["/primeiro-acesso", "Primeiro acesso"],
    ["/caixa-de-entrada", "Caixa de entrada"],
    ["/status", "Status do sistema"],
    ["/configuracoes", "Configurações"],
    ["/novidades", "Novidades"],
    ["/intervencoes", "Antes e depois"],
    ["/busca", "Busca nas trilhas"],
    ["/relatorio/mensal", "Relatório mensal (CIPA)"],
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
        // Saindo da página (link, recarga): o navegador aborta o fetch em voo.
        // Não é falha do app nem da rede — nada a registrar (visto no crawler).
        if (saindoDaPagina) return;
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

  // Página pública do produto: sem login, como o controle do palco.
  if (window.location.pathname.startsWith("/produto")) {
    return (
      <main id="conteudo">
        <Suspense fallback={<CarregandoTela />}>
          <ProdutoScreen />
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

  // Endereço que nenhuma tela trata: página 404 desenhada (o servidor já
  // responde 404 com o shell; ver app/api/status.py).
  const caminho = window.location.pathname;
  const conhecida =
    caminho === "/" || PREFIXOS_CONHECIDOS.some((x) => caminho === x || caminho.startsWith(`${x}/`));
  if (!conhecida) {
    return (
      <main id="conteudo">
        <PaginaNaoEncontrada endereco={caminho} />
      </main>
    );
  }
  // "?" contextual nas telas de tela cheia (as do painel têm "Ajuda" na barra superior).
  // Telas de exibição (palco, TV, torre, portal, retrospectiva) ficam limpas: nada sobre a imagem.
  const exibicao = ["/palco", "/tv", "/torre", "/portal", "/retrospectiva", "/desafio"].some((x) => caminho.startsWith(x));
  const artigoDaRota = caminho !== "/" && !exibicao ? artigoDaTela(`/${caminho.split("/")[1]}`) : undefined;
  const ajudaFlutuante = artigoDaRota ? (
    <div className="ajuda-flutuante">
      <BotaoDeAjuda artigo={artigoDaRota} />
    </div>
  ) : null;
  const exigencia = PAPEL_MINIMO.find(([prefixo]) => caminho === prefixo || caminho.startsWith(`${prefixo}/`));
  if (exigencia && (NIVEL[user.role] ?? 0) < NIVEL[exigencia[1]]) {
    return (
      <main id="conteudo">
        <AcessoNegado papelExigido={exigencia[1]} recurso={exigencia[2]} />
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
        {ajudaFlutuante}
        <DesafioScreen />
      </main>
    );
  }
  if (window.location.pathname.startsWith("/rotular")) {
    return (
      <main id="conteudo">
        {ajudaFlutuante}
        <RotularScreen />
      </main>
    );
  }
  if (window.location.pathname.startsWith("/gemeo")) {
    return (
      <main id="conteudo">
        {ajudaFlutuante}
        <Suspense fallback={<CarregandoTela />}>
          <GemeoScreen />
        </Suspense>
      </main>
    );
  }
  if (window.location.pathname.startsWith("/palco")) {
    return (
      <main id="conteudo">
        {ajudaFlutuante}
        <Suspense fallback={<CarregandoTela />}>
          <PalcoScreen />
        </Suspense>
      </main>
    );
  }
  if (window.location.pathname.startsWith("/liga")) {
    return (
      <main id="conteudo">
        {ajudaFlutuante}
        <Suspense fallback={<CarregandoTela />}>
          <LigaScreen />
        </Suspense>
      </main>
    );
  }
  if (window.location.pathname.startsWith("/retrospectiva")) {
    return (
      <main id="conteudo">
        {ajudaFlutuante}
        <Suspense fallback={<CarregandoTela />}>
          <RetrospectivaScreen />
        </Suspense>
      </main>
    );
  }
  if (window.location.pathname.startsWith("/auditoria")) {
    return (
      <main id="conteudo">
        {ajudaFlutuante}
        <Suspense fallback={<CarregandoTela />}>
          <AuditoriaScreen />
        </Suspense>
      </main>
    );
  }
  if (window.location.pathname.startsWith("/simulador")) {
    return (
      <main id="conteudo">
        {ajudaFlutuante}
        <Suspense fallback={<CarregandoTela />}>
          <SimuladorScreen />
        </Suspense>
      </main>
    );
  }
  if (window.location.pathname.startsWith("/evacuacao")) {
    return (
      <main id="conteudo">
        {ajudaFlutuante}
        <Suspense fallback={<CarregandoTela />}>
          <EvacuacaoScreen />
        </Suspense>
      </main>
    );
  }
  if (window.location.pathname.startsWith("/status")) {
    return (
      <main id="conteudo">
        {ajudaFlutuante}
        <Suspense fallback={<CarregandoTela />}>
          <PaginaStatus />
        </Suspense>
      </main>
    );
  }
  if (window.location.pathname.startsWith("/novidades")) {
    return (
      <main id="conteudo">
        {ajudaFlutuante}
        <Suspense fallback={<CarregandoTela />}>
          <NovidadesScreen />
        </Suspense>
      </main>
    );
  }
  if (window.location.pathname.startsWith("/configuracoes")) {
    return (
      <main id="conteudo">
        {ajudaFlutuante}
        <Suspense fallback={<CarregandoTela />}>
          <ConfiguracoesScreen />
        </Suspense>
      </main>
    );
  }
  if (window.location.pathname.startsWith("/busca")) {
    return (
      <main id="conteudo">
        {ajudaFlutuante}
        <Suspense fallback={<CarregandoTela />}>
          <BuscaTrilhasScreen />
        </Suspense>
      </main>
    );
  }
  if (window.location.pathname.startsWith("/intervencoes")) {
    return (
      <main id="conteudo">
        {ajudaFlutuante}
        <Suspense fallback={<CarregandoTela />}>
          <IntervencoesScreen />
        </Suspense>
      </main>
    );
  }
  if (window.location.pathname.startsWith("/ajuda")) {
    return (
      <main id="conteudo">
        {ajudaFlutuante}
        <Suspense fallback={<CarregandoTela />}>
          <AjudaScreen />
        </Suspense>
      </main>
    );
  }
  if (window.location.pathname.startsWith("/caixa-de-entrada")) {
    return (
      <main id="conteudo">
        {ajudaFlutuante}
        <Suspense fallback={<CarregandoTela />}>
          <CaixaDeEntradaScreen />
        </Suspense>
      </main>
    );
  }
  if (window.location.pathname.startsWith("/primeiro-acesso")) {
    return (
      <main id="conteudo">
        {ajudaFlutuante}
        <Suspense fallback={<CarregandoTela />}>
          <OnboardingScreen />
        </Suspense>
      </main>
    );
  }
  if (window.location.pathname.startsWith("/permissoes")) {
    return (
      <main id="conteudo">
        {ajudaFlutuante}
        <Suspense fallback={<CarregandoTela />}>
          <PermissoesScreen />
        </Suspense>
      </main>
    );
  }
  if (window.location.pathname.startsWith("/regras")) {
    return (
      <main id="conteudo">
        {ajudaFlutuante}
        <Suspense fallback={<CarregandoTela />}>
          <RegrasScreen />
        </Suspense>
      </main>
    );
  }
  if (window.location.pathname.startsWith("/torre")) {
    return (
      <main id="conteudo">
        {ajudaFlutuante}
        <Suspense fallback={<CarregandoTela />}>
          <TorreScreen />
        </Suspense>
      </main>
    );
  }
  if (window.location.pathname.startsWith("/tv")) {
    return (
      <main id="conteudo">
        {ajudaFlutuante}
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
      <TourGuiado />
      <Topbar />
      <MessageBar />
      <main id="conteudo">{content}</main>
    </div>
  );
}
