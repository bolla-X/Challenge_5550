import { mensagemDeErro } from "../utils/erros";
import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";
import { EmptyState, Numero, PanelSkeleton } from "./common";
import { IlustracaoEscudo } from "./ilustracoes";
import { useReducedMotion } from "motion/react";
import { useDashboardStore } from "../store/dashboardStore";
import type { Incidente } from "../api/types";
import { listarIncidentes } from "../api/endpoints";
import { useCameraEstado } from "./camera-grid";
import { PortalScreen } from "./portal";
import { IncidenteDetalhe, VerificarIntegridade } from "./incidente-detalhe";
import { LigaResumo } from "./liga";
import { RetrospectivaStories } from "./retrospectiva";
import { QrSvg } from "./celular-qr";
import { QuadroDaCena, VideoDaCena } from "./palco-video";
import type { RegraDeExemplo } from "./palco-cenas";

const GemeoScreen = lazy(() => import("./gemeo/gemeo-screen"));
const SimuladorScreen = lazy(() => import("./simulador"));
// Cenas da MISSÃO 4 (saúde da câmera, evacuação, regras, permissão, torre, primeiro acesso): um pedaço só, carregado quando a primeira aparece.
const CenaTapeACamera = lazy(() => import("./palco-cenas").then((m) => ({ default: m.CenaTapeACamera })));
const CenaFabricaConectada = lazy(() => import("./palco-cenas").then((m) => ({ default: m.CenaFabricaConectada })));
const CenaEvacuacao = lazy(() => import("./palco-cenas").then((m) => ({ default: m.CenaEvacuacao })));
const CenaRegraSemCodigo = lazy(() => import("./palco-cenas").then((m) => ({ default: m.CenaRegraSemCodigo })));
const CenaPermissaoComVigia = lazy(() => import("./palco-cenas").then((m) => ({ default: m.CenaPermissaoComVigia })));
const CenaPrimeiroAcesso = lazy(() => import("./palco-cenas").then((m) => ({ default: m.CenaPrimeiroAcesso })));

/**
 * Modo Apresentação — palco (X6, `/palco`). As cenas seguem o DEMO.md; cada
 * uma tem uma legenda curta. Espaço ou → avança, ← volta; o celular (QR,
 * `/palco/controle`) faz o mesmo pelo servidor. Se o celular falhar, o
 * teclado continua mandando.
 */

type Cena = {
  chave: string;
  titulo: string;
  legenda: string;
  camera_id: number | null;
  raiox?: boolean;
  /** Cena que precisa de câmera de verdade (`ao_vivo`); `false` aqui = a câmera achada toca uma gravação. */
  camera_ao_vivo?: boolean;
  /** Só na cena "Regra sem código": a regra de exemplo, no formato do editor. */
  regra?: RegraDeExemplo;
};
type Estado = { cena: number; total: number; seq: number; chave: string; titulo: string; legenda: string; proxima: string | null };
/** O polling da tela também traz as câmeras que a cena pausou (`ativas: "cena"`) e, se o preparo da cena falhou, a legenda de contingência. */
type EstadoDaTela = Estado & { pausadas?: string[]; fallback?: string | null };

async function ir(acao: "proxima" | "anterior" | "ir", indice?: number, token?: string): Promise<Estado> {
  const r = await fetch("/api/palco/ir", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ acao, indice, t: token }),
  });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return (await r.json()) as Estado;
}

/** O servidor numera cada troca (`seq`): resposta atrasada de um polling
 * (ou de um `ir`) nunca volta a tela para uma cena mais antiga. */
function maisNovo(atual: Estado | null, d: Estado): Estado {
  if (!atual) return d;
  if (d.seq < atual.seq) return atual;
  return atual.seq === d.seq && atual.cena === d.cena ? atual : d;
}

function NumerosDoSistema() {
  const [n, setN] = useState<{ cameras: number; noAr: number; pessoas: number; incidentes: number } | null>(null);
  useEffect(() => {
    fetch("/api/gemeo", { credentials: "same-origin" })
      .then((r) => r.json())
      .then((d) => {
        const cams = d.cameras as { rodando: boolean; pes: unknown[]; incidentes: unknown[] }[];
        setN({
          cameras: cams.length,
          noAr: cams.filter((c) => c.rodando).length,
          pessoas: cams.reduce((s, c) => s + c.pes.length, 0),
          incidentes: cams.reduce((s, c) => s + c.incidentes.length, 0),
        });
      })
      .catch(() => setN(null));
  }, []);
  if (!n) return null;
  return (
    <dl className="palco-numeros" aria-label="Agora, nesta máquina">
      <div>
        <dt>câmeras no ar</dt>
        <dd className="t-data">
          {n.noAr}/{n.cameras}
        </dd>
      </div>
      <div>
        <dt>pessoas na planta</dt>
        <dd className="t-data"><Numero valor={n.pessoas} /></dd>
      </div>
      <div>
        <dt>incidentes ativos</dt>
        <dd className="t-data"><Numero valor={n.incidentes} /></dd>
      </div>
    </dl>
  );
}

function IncidenteDaCena({ cameraId, regra }: { cameraId: number | null; regra?: string }) {
  const [inc, setInc] = useState<Incidente | null | undefined>(undefined);
  const achou = inc != null;
  useEffect(() => {
    if (achou) return undefined;
    let vivo = true;
    const buscar = () =>
      listarIncidentes({ cameraId, regra, limit: 1 })
        .then((r) => vivo && setInc(r.items[0] ?? null))
        .catch(() => vivo && setInc(null));
    buscar();
    // Até o primeiro aparecer: a gravação da cena acabou de recomeçar.
    const id = window.setInterval(buscar, 3000);
    return () => {
      vivo = false;
      window.clearInterval(id);
    };
  }, [cameraId, regra, achou]);
  if (inc === undefined) return <PanelSkeleton lines={5} />;
  if (inc === null)
    return (
      <EmptyState ilustracao={<IlustracaoEscudo />} titulo="Nenhum incidente registrado ainda nesta câmera">
        Volte a esta cena em instantes: a câmera continua analisando.
      </EmptyState>
    );
  return <IncidenteDetalhe incidente={inc} inline onClose={() => undefined} />;
}

/**
 * Cena "Queda" (ADENDO 2): a gravação da queda toca AO VIVO a 0,25× (o
 * servidor reduz e informa; o rótulo fica sobre o vídeo) e o alerta aparece
 * na hora. A queda da gravação fica ~0,8 s no chão: em tempo real, duas
 * análises seguidas (a regra de emergência) não cabem nisso numa máquina sem
 * GPU dedicada. Quando o alerta chega, o replay do incidente entra ao lado,
 * como continuação da cena.
 */
function CenaDaQueda({ cameraId }: { cameraId: number }) {
  const estado = useCameraEstado(cameraId);
  const queda = (estado.incidentes ?? []).some((i) => i.rule === "fall_detected");
  const [viu, setViu] = useState(false);
  useEffect(() => {
    if (queda) setViu(true);
  }, [queda]);
  return (
    <div className={`palco-queda${viu ? " com-replay" : ""}`} data-testid="palco-queda">
      <QuadroDaCena cameraId={cameraId} estado={estado} />
      {viu && (
        <div className="palco-queda-replay">
          <IncidenteDaCena cameraId={cameraId} regra="fall_detected" />
        </div>
      )}
    </div>
  );
}

function ConteudoDaCena({ cena }: { cena: Cena }) {
  switch (cena.chave) {
    case "abertura":
    case "encerramento":
      return (
        <div className="palco-hero">
          <h1>{cena.chave === "abertura" ? "VisionEPI" : "Obrigado"}</h1>
          <p>{cena.legenda}</p>
          <NumerosDoSistema />
        </div>
      );
    case "portal":
    case "enganar":
      return <PortalScreen cameraId={cena.camera_id} desafioInicial={cena.chave === "enganar"} />;
    case "queda":
      return cena.camera_id != null ? <CenaDaQueda cameraId={cena.camera_id} /> : <IncidenteDaCena cameraId={null} regra="fall_detected" />;
    case "raiox":
      return cena.camera_id != null ? <VideoDaCena cameraId={cena.camera_id} /> : <p className="palco-vazio">Câmera da cena não cadastrada.</p>;
    case "tape_camera":
      return (
        <Suspense fallback={<PanelSkeleton lines={4} />}>
          <CenaTapeACamera cameraId={cena.camera_id} aoVivo={cena.camera_ao_vivo === true} />
        </Suspense>
      );
    case "fabrica":
      return (
        <Suspense fallback={<PanelSkeleton lines={4} />}>
          <CenaFabricaConectada />
        </Suspense>
      );
    case "evacuacao":
      return (
        <Suspense fallback={<PanelSkeleton lines={4} />}>
          <CenaEvacuacao />
        </Suspense>
      );
    case "regra":
      return (
        <Suspense fallback={<PanelSkeleton lines={4} />}>
          <CenaRegraSemCodigo regra={cena.regra ?? null} cameraId={cena.camera_id} />
        </Suspense>
      );
    case "permissao":
      return (
        <Suspense fallback={<PanelSkeleton lines={4} />}>
          <CenaPermissaoComVigia cameraId={cena.camera_id} />
        </Suspense>
      );
    case "primeiro_acesso":
      return (
        <Suspense fallback={<PanelSkeleton lines={4} />}>
          <CenaPrimeiroAcesso />
        </Suspense>
      );
    case "gemeo":
      return (
        <Suspense fallback={<PanelSkeleton lines={4} />}>
          <GemeoScreen embutido />
        </Suspense>
      );
    case "incidente":
      return <IncidenteDaCena cameraId={cena.camera_id} />;
    case "custodia":
      return (
        <div className="card palco-cartao">
          <div className="card-body">
            <VerificarIntegridade />
          </div>
        </div>
      );
    case "simulador":
      return (
        <Suspense fallback={<PanelSkeleton lines={4} />}>
          <SimuladorScreen />
        </Suspense>
      );
    case "liga":
      return <LigaResumo />;
    case "retrospectiva":
      return <RetrospectivaStories periodo="turno" />;
    default:
      return null;
  }
}

function QrDoControle() {
  const [url, setUrl] = useState<{ texto: string; aviso: string | null } | null>(null);
  useEffect(() => {
    fetch("/api/palco/controle", { credentials: "same-origin" })
      .then((r) => r.json())
      .then((d) => setUrl({ texto: d.url_lan || `${window.location.origin}${d.caminho}`, aviso: d.aviso }))
      .catch(() => setUrl(null));
  }, []);
  if (!url) return null;
  return (
    <aside className="palco-qr" data-testid="palco-qr" data-url={url.texto}>
      <QrSvg texto={url.texto} rotulo="QR code do controle da apresentação pelo celular" />
      <span>Controle pelo celular</span>
      {url.aviso && (
        <small>
          Em HTTP, só esta máquina alcança. Para o celular: <code>python run.py --demo --https</code>
        </small>
      )}
    </aside>
  );
}

export function PalcoScreen() {
  const [cenas, setCenas] = useState<Cena[] | null>(null);
  const [estado, setEstado] = useState<Estado | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [mostrarQr, setMostrarQr] = useState(true);
  // Fora do `estado`: `maisNovo` ignora respostas da mesma cena, e a lista
  // de pausadas tem de acompanhar o servidor a cada consulta.
  const [pausadas, setPausadas] = useState<string[]>([]);
  // Idem: a contingência chega depois da troca de cena (o preparo roda em thread) e some sozinha ao sair dela.
  const [contingencia, setContingencia] = useState<string | null>(null);
  const reduzir = useReducedMotion();
  const local = useRef<number | null>(null);

  useEffect(() => {
    fetch("/api/palco/roteiro", { credentials: "same-origin" })
      .then(async (r) => {
        if (!r.ok) throw new Error(r.status === 401 ? "Entre como técnico ou supervisor." : "Falha ao carregar a apresentação.");
        return r.json();
      })
      .then((d) => {
        setCenas(d.cenas);
        setEstado(d.estado);
      })
      .catch((e) => setErro(mensagemDeErro(e, "Falha ao carregar a apresentação.")));
  }, []);

  // O celular muda a cena pelo servidor: a tela acompanha.
  useEffect(() => {
    const id = window.setInterval(() => {
      fetch("/api/palco/estado", { credentials: "same-origin" })
        .then((r) => (r.ok ? r.json() : null))
        .then((d: EstadoDaTela | null) => {
          if (d) {
            local.current = null;
            setEstado((atual) => maisNovo(atual, d));
            setPausadas(d.pausadas ?? []);
            setContingencia(d.fallback ?? null);
          }
        })
        .catch(() => undefined);
    }, 500);
    return () => window.clearInterval(id);
  }, []);

  const mover = useCallback(
    (acao: "proxima" | "anterior") => {
      ir(acao)
        .then((d) => setEstado((atual) => maisNovo(atual, d)))
        .catch(() => {
          // Servidor fora: o teclado ainda troca a cena nesta tela.
          setEstado((atual) => {
            if (!atual || !cenas) return atual;
            const cena = Math.max(0, Math.min(cenas.length - 1, atual.cena + (acao === "proxima" ? 1 : -1)));
            local.current = cena;
            return { ...atual, cena, chave: cenas[cena].chave, titulo: cenas[cena].titulo, legenda: cenas[cena].legenda, seq: atual.seq };
          });
        });
    },
    [cenas],
  );

  useEffect(() => {
    const tecla = (e: KeyboardEvent) => {
      const alvo = e.target as HTMLElement | null;
      if (alvo && ["INPUT", "TEXTAREA", "SELECT"].includes(alvo.tagName)) return;
      if (e.key === "ArrowRight" || e.key === " " || e.key === "PageDown") {
        e.preventDefault();
        mover("proxima");
      } else if (e.key === "ArrowLeft" || e.key === "PageUp") {
        e.preventDefault();
        mover("anterior");
      } else if (e.key === "q" || e.key === "Q") {
        setMostrarQr((m) => !m);
      }
    };
    window.addEventListener("keydown", tecla, { capture: true });
    return () => window.removeEventListener("keydown", tecla, { capture: true });
  }, [mover]);

  const cena = cenas && estado ? cenas[estado.cena] : null;

  // Raio-X da cena: liga ao entrar numa cena que pede, desliga ao sair.
  useEffect(() => {
    if (!cena) return;
    const store = useDashboardStore.getState();
    if (Boolean(cena.raiox) !== store.raioX) store.alternarRaioX();
  }, [cena]);

  if (erro) {
    return (
      <div className="palco" role="alert">
        <div className="palco-hero">
          <h1>Apresentação</h1>
          <p>{erro}</p>
          <a className="button primary" href="/">
            Entrar
          </a>
        </div>
      </div>
    );
  }
  if (!cena || !estado) return <div className="palco" aria-busy="true" />;

  return (
    <div className="palco" data-testid="palco" data-cena={estado.cena} data-chave={cena.chave}>
      <header className="palco-topo">
        <span className="palco-marca">VisionEPI</span>
        <ol className="palco-pontos" aria-label={`Cena ${estado.cena + 1} de ${estado.total}`}>
          {(cenas ?? []).map((c, i) => (
            <li key={c.chave} className={i === estado.cena ? "atual" : i < estado.cena ? "feita" : ""} title={c.titulo} />
          ))}
        </ol>
        <span className="palco-indice t-data">
          {estado.cena + 1}/{estado.total}
        </span>
      </header>
      <main key={cena.chave} className={`palco-cena ${reduzir ? "" : "entra"}`} data-testid="palco-cena">
        <ConteudoDaCena cena={cena} />
      </main>
      <footer className="palco-legenda" aria-live="polite">
        <strong data-testid="palco-titulo">{cena.titulo}</strong>
        <span>{cena.legenda}</span>
        {contingencia && (
          <small className="palco-contingencia" data-testid="palco-contingencia" role="status">
            {contingencia}
          </small>
        )}
        {pausadas.length > 0 && (
          <small className="palco-pausadas" data-testid="palco-pausadas">
            {pausadas.length === 1 ? `${pausadas[0]}: pausada` : `${pausadas.join(", ")}: pausadas`} pela apresentação
          </small>
        )}
        {estado.proxima && <small className="palco-proxima">a seguir: {estado.proxima} →</small>}
      </footer>
      {mostrarQr && <QrDoControle />}
    </div>
  );
}

/** Controle pelo celular (`/palco/controle?t=…`): sem login, só com o token do QR. */
export function PalcoControle() {
  const token = new URLSearchParams(window.location.search).get("t") ?? "";
  const [estado, setEstado] = useState<Estado | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);
  useEffect(() => {
    if (!token) return undefined;
    const tick = () =>
      fetch(`/api/palco/estado?t=${encodeURIComponent(token)}`)
        .then(async (r) => {
          if (!r.ok) throw new Error(r.status === 403 ? "Link expirado: leia o QR da tela de novo." : "O servidor não respondeu.");
          return (await r.json()) as Estado;
        })
        .then((d) => {
          setEstado(d);
          setErro(null);
        })
        .catch((e) => setErro(mensagemDeErro(e, "sem conexão")));
    tick();
    const id = window.setInterval(tick, 800);
    return () => window.clearInterval(id);
  }, [token]);
  const mover = (acao: "proxima" | "anterior") => {
    setOcupado(true);
    if (navigator.vibrate && (navigator as Navigator & { userActivation?: { hasBeenActive: boolean } }).userActivation?.hasBeenActive !== false) navigator.vibrate(15);
    ir(acao, undefined, token)
      .then(setEstado)
      .catch(() => setErro("Não chegou ao servidor. Use o teclado do notebook."))
      .finally(() => setOcupado(false));
  };
  if (!token) {
    return (
      <div className="controle" data-testid="palco-controle">
        <p className="controle-kicker">VisionEPI · controle da apresentação</p>
        <h1>Abra pelo QR code</h1>
        <p className="controle-proxima">
          Este controle funciona só pelo QR code que aparece na tela do palco: ele traz a chave da apresentação.
        </p>
      </div>
    );
  }
  const aguardando = !estado ? "Aguardando a conexão com o palco" : undefined;
  return (
    <div className="controle" data-testid="palco-controle">
      <p className="controle-kicker">VisionEPI · controle da apresentação</p>
      {estado ? (
        <>
          <p className="controle-indice t-data">
            {estado.cena + 1} de {estado.total}
          </p>
          <h1 data-testid="controle-cena">{estado.titulo}</h1>
          {estado.proxima && <p className="controle-proxima">a seguir: {estado.proxima}</p>}
        </>
      ) : (
        <h1>{erro ? "Sem conexão" : "Conectando…"}</h1>
      )}
      {erro && (
        <p className="controle-erro" role="alert">
          {erro}
        </p>
      )}
      <div className="controle-botoes">
        <button type="button" className="controle-anterior" disabled={ocupado || !estado || estado.cena === 0} title={aguardando ?? (estado?.cena === 0 ? "Esta é a primeira cena" : undefined)} onClick={() => mover("anterior")} data-testid="controle-anterior">
          Anterior
        </button>
        <button type="button" className="primary controle-proxima-botao" disabled={ocupado || !estado || estado.proxima === null} title={aguardando ?? (estado?.proxima === null ? "Esta é a última cena" : undefined)} onClick={() => mover("proxima")} data-testid="controle-proxima">
          Próxima
        </button>
      </div>
    </div>
  );
}

export default PalcoScreen;
