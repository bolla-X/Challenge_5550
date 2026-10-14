import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useReducedMotion } from "motion/react";
import { useDashboardStore } from "../store/dashboardStore";
import type { Incidente } from "../api/types";
import { listarIncidentes } from "../api/endpoints";
import { incidenteCritico, useCameraEstado } from "./camera-grid";
import { rotuloDoIncidente } from "../utils/incidentes";
import { LiveVideo } from "./live-video";
import { PortalScreen } from "./portal";
import { IncidenteDetalhe, VerificarIntegridade } from "./incidente-detalhe";
import { LigaResumo } from "./liga";
import { RetrospectivaStories } from "./retrospectiva";
import { QrSvg } from "./celular-qr";

const GemeoScreen = lazy(() => import("./gemeo/gemeo-screen"));
const SimuladorScreen = lazy(() => import("./simulador"));

/**
 * Modo Apresentação — palco (X6, `/palco`). As cenas seguem o DEMO.md; cada
 * uma tem uma legenda curta. Espaço ou → avança, ← volta; o celular (QR,
 * `/palco/controle`) faz o mesmo pelo servidor. Se o celular falhar, o
 * teclado continua mandando.
 */

type Cena = { chave: string; titulo: string; legenda: string; camera_id: number | null; raiox?: boolean };
type Estado = { cena: number; total: number; seq: number; chave: string; titulo: string; legenda: string; proxima: string | null };

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

function VideoDaCena({ cameraId }: { cameraId: number }) {
  const estado = useCameraEstado(cameraId);
  const inc = incidenteCritico(estado);
  return (
    <div className="palco-video" data-testid="palco-video">
      <LiveVideo cameraId={cameraId} label="Vídeo da cena" />
      {inc && (
        <span className="over-pill alert palco-pilula" role="status" data-testid="pilula-incidente">
          <span className="dot" />
          {rotuloDoIncidente(inc)}
        </span>
      )}
    </div>
  );
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
        <dd className="t-data">{n.pessoas}</dd>
      </div>
      <div>
        <dt>incidentes ativos</dt>
        <dd className="t-data">{n.incidentes}</dd>
      </div>
    </dl>
  );
}

function IncidenteDaCena({ cameraId }: { cameraId: number | null }) {
  const [inc, setInc] = useState<Incidente | null | undefined>(undefined);
  useEffect(() => {
    listarIncidentes({ cameraId, limit: 1 })
      .then((r) => setInc(r.items[0] ?? null))
      .catch(() => setInc(null));
  }, [cameraId]);
  if (inc === undefined) return <p className="status-text">Buscando o incidente mais recente…</p>;
  if (inc === null) return <p className="palco-vazio">Nenhum incidente registrado ainda nesta câmera — volte a esta cena em instantes.</p>;
  return <IncidenteDetalhe incidente={inc} inline onClose={() => undefined} />;
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
    case "raiox":
    case "queda":
      return cena.camera_id != null ? <VideoDaCena cameraId={cena.camera_id} /> : <p className="palco-vazio">Câmera da cena não cadastrada.</p>;
    case "gemeo":
      return (
        <Suspense fallback={<p className="status-text">Carregando o gêmeo…</p>}>
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
        <Suspense fallback={<p className="status-text">Carregando o simulador…</p>}>
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
      {url.aviso && <small>{url.aviso}</small>}
    </aside>
  );
}

export function PalcoScreen() {
  const [cenas, setCenas] = useState<Cena[] | null>(null);
  const [estado, setEstado] = useState<Estado | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [mostrarQr, setMostrarQr] = useState(true);
  const reduzir = useReducedMotion();
  const local = useRef<number | null>(null);

  useEffect(() => {
    fetch("/api/palco/roteiro", { credentials: "same-origin" })
      .then(async (r) => {
        if (!r.ok) throw new Error(r.status === 401 ? "Entre como técnico ou supervisor." : `HTTP ${r.status}`);
        return r.json();
      })
      .then((d) => {
        setCenas(d.cenas);
        setEstado(d.estado);
      })
      .catch((e) => setErro(e instanceof Error ? e.message : "falha"));
  }, []);

  // O celular muda a cena pelo servidor: a tela acompanha.
  useEffect(() => {
    const id = window.setInterval(() => {
      fetch("/api/palco/estado", { credentials: "same-origin" })
        .then((r) => (r.ok ? r.json() : null))
        .then((d: Estado | null) => {
          if (d) {
            local.current = null;
            setEstado((atual) => (atual && atual.seq === d.seq && atual.cena === d.cena ? atual : d));
          }
        })
        .catch(() => undefined);
    }, 500);
    return () => window.clearInterval(id);
  }, []);

  const mover = useCallback(
    (acao: "proxima" | "anterior") => {
      ir(acao)
        .then(setEstado)
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
    const tick = () =>
      fetch(`/api/palco/estado?t=${encodeURIComponent(token)}`)
        .then(async (r) => {
          if (!r.ok) throw new Error(r.status === 403 ? "Link expirado: leia o QR da tela de novo." : `HTTP ${r.status}`);
          return (await r.json()) as Estado;
        })
        .then((d) => {
          setEstado(d);
          setErro(null);
        })
        .catch((e) => setErro(e instanceof Error ? e.message : "sem conexão"));
    tick();
    const id = window.setInterval(tick, 800);
    return () => window.clearInterval(id);
  }, [token]);
  const mover = (acao: "proxima" | "anterior") => {
    setOcupado(true);
    if (navigator.vibrate) navigator.vibrate(15);
    ir(acao, undefined, token)
      .then(setEstado)
      .catch(() => setErro("Não chegou ao servidor. Use o teclado do notebook."))
      .finally(() => setOcupado(false));
  };
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
        <button type="button" className="controle-anterior" disabled={ocupado || !estado || estado.cena === 0} onClick={() => mover("anterior")} data-testid="controle-anterior">
          Anterior
        </button>
        <button type="button" className="primary controle-proxima-botao" disabled={ocupado || !estado || estado.proxima === null} onClick={() => mover("proxima")} data-testid="controle-proxima">
          Próxima
        </button>
      </div>
    </div>
  );
}

export default PalcoScreen;
