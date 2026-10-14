import { useEffect, useMemo, useRef, useState } from "react";
import { useReducedMotion } from "motion/react";
import { listarIncidentes } from "../../api/endpoints";
import type { Incidente } from "../../api/types";
import { PPE_LABELS } from "../../api/ppe";
import { paraDate } from "../../utils/datas";
import { EmptyState, PanelSkeleton } from "../common";
import { IlustracaoPlanta } from "../ilustracoes";
import { IncidentReplay } from "../replay";
import "./gemeo.css";
import { CenaGemeo, type Metricas, type Selecao } from "./cena3d";
import { Gemeo2D } from "./gemeo-2d";
import type { CameraDoGemeo, EstadoDoGemeo, PeNaPlanta } from "./tipos";

/**
 * Gêmeo digital da planta (X1, `/gemeo`). Cada pessoa é uma cápsula na cor do
 * estado (nunca foto), na posição que a homografia do G5 dá ao pé dela. O 3D
 * cai para uma planta 2D se o WebGL não existir (ou com `?2d=1`).
 */

const ROTULO_ESTADO: Record<PeNaPlanta["estado"], string> = {
  conforme: "Conforme",
  sem_epi: "Sem EPI exigido",
  zona: "Na zona de risco",
  emergencia: "Possível queda",
};

function webglDisponivel(): boolean {
  if (new URLSearchParams(window.location.search).get("2d") === "1") return false;
  try {
    const c = document.createElement("canvas");
    return Boolean(c.getContext("webgl2") || c.getContext("webgl"));
  } catch {
    return false;
  }
}

function useEstadoDoGemeo(intervaloMs = 500): { estado: EstadoDoGemeo | null; erro: string | null } {
  const [estado, setEstado] = useState<EstadoDoGemeo | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  useEffect(() => {
    let vivo = true;
    let timer = 0;
    const tick = () => {
      if (document.hidden) {
        timer = window.setTimeout(tick, intervaloMs * 4);
        return;
      }
      fetch("/api/gemeo", { credentials: "same-origin" })
        .then(async (r) => {
          if (!r.ok) throw new Error(`HTTP ${r.status}`);
          return (await r.json()) as EstadoDoGemeo;
        })
        .then((d) => {
          if (!vivo) return;
          setEstado(d);
          setErro(null);
        })
        .catch((e) => vivo && setErro(e instanceof Error ? e.message : "falha"))
        .finally(() => {
          if (vivo) timer = window.setTimeout(tick, intervaloMs);
        });
    };
    tick();
    return () => {
      vivo = false;
      window.clearTimeout(timer);
    };
  }, [intervaloMs]);
  return { estado, erro };
}

type EventoDaLinha = { ts: number; ppe: Record<string, string>; queda: boolean; zona: string | null };

function resumoDoEvento(e: EventoDaLinha): string {
  const faltando = Object.entries(e.ppe)
    .filter(([, s]) => s === "missing" || s === "incorrect")
    .map(([k]) => PPE_LABELS[k as keyof typeof PPE_LABELS] ?? k);
  const partes = [];
  if (e.queda) partes.push("possível queda");
  if (e.zona === "inside") partes.push("dentro da zona");
  partes.push(faltando.length ? `sem ${faltando.join(", ").toLowerCase()}` : "EPIs exigidos ok");
  return partes.join(" · ");
}

function DetalhePessoa({ sel, onReplay }: { sel: Extract<Selecao, { tipo: "pessoa" }>; onReplay: (id: number) => void }) {
  const [eventos, setEventos] = useState<EventoDaLinha[] | null>(null);
  const pessoa = `person_${sel.pe.track_id}`;
  useEffect(() => {
    let vivo = true;
    setEventos(null);
    fetch(`/api/cameras/${sel.camera_id}/conformidade-por-id/${encodeURIComponent(pessoa)}`, { credentials: "same-origin" })
      .then((r) => (r.ok ? r.json() : { eventos: [] }))
      .then((d) => vivo && setEventos((d.eventos as EventoDaLinha[]) ?? []))
      .catch(() => vivo && setEventos([]));
    return () => {
      vivo = false;
    };
  }, [sel.camera_id, pessoa]);
  return (
    <div className="gemeo-detalhe" data-testid="gemeo-detalhe-pessoa">
      <p className="gemeo-detalhe-kicker">ID de rastreio · {sel.camera_nome}</p>
      <h2>Pessoa {sel.pe.track_id}</h2>
      <p className={`gemeo-estado ${sel.pe.estado}`}>
        <span className="dot" />
        {ROTULO_ESTADO[sel.pe.estado]}
        {sel.pe.faltando.length > 0 && ` · ${sel.pe.faltando.map((k) => PPE_LABELS[k as keyof typeof PPE_LABELS] ?? k).join(", ")}`}
      </p>
      {sel.pe.alert_id != null && (
        <button type="button" className="primary small" onClick={() => onReplay(sel.pe.alert_id as number)}>
          Ver replay do alerta
        </button>
      )}
      <h3>Linha do tempo</h3>
      {eventos === null ? (
        <PanelSkeleton lines={3} />
      ) : eventos.length ? (
        <ol className="gemeo-linha" data-testid="gemeo-linha">
          {[...eventos].reverse().slice(0, 8).map((e) => (
            <li key={e.ts}>
              <time>{new Date(e.ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</time>
              <span>{resumoDoEvento(e)}</span>
            </li>
          ))}
        </ol>
      ) : (
        <p className="muted">Sem mudanças registradas para este ID ainda.</p>
      )}
      <p className="gemeo-nota">O número é de rastreio desta câmera, não identifica ninguém.</p>
    </div>
  );
}

function DetalheZona({ sel }: { sel: Extract<Selecao, { tipo: "zona" }> }) {
  const [itens, setItens] = useState<Incidente[] | null>(null);
  useEffect(() => {
    let vivo = true;
    setItens(null);
    listarIncidentes({ cameraId: sel.camera_id, limit: 200 })
      .then((r) => vivo && setItens(r.items.filter((i) => i.zona === (sel.zona_nome ?? i.zona) && i.rule === "risk_area_presence")))
      .catch(() => vivo && setItens([]));
    return () => {
      vivo = false;
    };
  }, [sel.camera_id, sel.zona_nome]);
  const pessoas = (itens ?? []).reduce((n, i) => n + i.pessoas.length, 0);
  return (
    <div className="gemeo-detalhe" data-testid="gemeo-detalhe-zona">
      <p className="gemeo-detalhe-kicker">Zona de risco · {sel.camera_nome}</p>
      <h2>{sel.zona_nome ?? "Zona de risco"}</h2>
      {itens === null ? (
        <PanelSkeleton lines={3} />
      ) : (
        <>
          <dl className="gemeo-numeros">
            <div>
              <dt>Entradas registradas</dt>
              <dd className="t-data">{itens.length}</dd>
            </div>
            <div>
              <dt>Pessoas envolvidas</dt>
              <dd className="t-data">{pessoas}</dd>
            </div>
          </dl>
          {itens.length ? (
            <ol className="gemeo-linha">
              {itens.slice(0, 8).map((i) => (
                <li key={i.id}>
                  <time>{paraDate(i.aberto_em).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</time>
                  <span>
                    {i.pessoas.length} pessoa{i.pessoas.length === 1 ? "" : "s"}
                    {i.status === "active" ? " · agora" : ""}
                  </span>
                </li>
              ))}
            </ol>
          ) : (
            <p className="muted">Ninguém entrou nesta zona desde que o sistema subiu.</p>
          )}
        </>
      )}
    </div>
  );
}

function Legenda() {
  return (
    <ul className="gemeo-legenda" aria-label="Legenda">
      <li className="conforme">
        <span className="dot" />
        Conforme
      </li>
      <li className="sem_epi">
        <span className="dot" />
        Sem EPI ou na zona
      </li>
      <li className="emergencia">
        <span className="dot" />
        Possível queda
      </li>
    </ul>
  );
}

export function GemeoScreen({ embutido = false }: { embutido?: boolean }) {
  const { estado, erro } = useEstadoDoGemeo();
  const hostRef = useRef<HTMLDivElement>(null);
  const cenaRef = useRef<CenaGemeo | null>(null);
  const reduzir = Boolean(useReducedMotion());
  const [modo, setModo] = useState<"3d" | "2d">(() => (webglDisponivel() ? "3d" : "2d"));
  const [drone, setDrone] = useState(false);
  const [sel, setSel] = useState<Selecao>(null);
  const [replay, setReplay] = useState<number | null>(null);
  const [metricas, setMetricas] = useState<Metricas | null>(null);

  useEffect(() => {
    if (modo !== "3d" || !hostRef.current) return undefined;
    let cena: CenaGemeo;
    try {
      cena = new CenaGemeo(hostRef.current, { aoSelecionar: setSel, reduzirMovimento: reduzir });
    } catch (e) {
      console.warn("[gemeo] WebGL indisponível, usando a planta 2D", e);
      setModo("2d");
      return undefined;
    }
    cenaRef.current = cena;
    const id = window.setInterval(() => setMetricas(cena.metricas()), 1000);
    return () => {
      window.clearInterval(id);
      cena.destruir();
      cenaRef.current = null;
    };
  }, [modo, reduzir]);

  useEffect(() => {
    if (estado && cenaRef.current) cenaRef.current.atualizar(estado.cameras);
  }, [estado]);

  useEffect(() => {
    cenaRef.current?.visaoDeDrone(drone);
  }, [drone]);

  const cameras: CameraDoGemeo[] = estado?.cameras ?? [];
  const calibradas = cameras.filter((c) => c.calibrada);
  const pessoas = useMemo(
    () => calibradas.flatMap((c) => c.pes.map((pe) => ({ cam: c, pe }))),
    [calibradas],
  );
  const foraDoPadrao = pessoas.filter(({ pe }) => pe.estado !== "conforme").length;

  const selecionar = (cam: CameraDoGemeo, pe: PeNaPlanta) =>
    setSel({ tipo: "pessoa", camera_id: cam.id, camera_nome: cam.nome, pe });

  return (
    <div className={`gemeo ${embutido ? "embutido" : ""}`} data-testid="gemeo">
      {!embutido && (
        <header className="gemeo-topo">
          <div>
            <h1>Gêmeo digital</h1>
            <p className="screen-sub">
              {estado
                ? `${pessoas.length} pessoa${pessoas.length === 1 ? "" : "s"} em ${calibradas.length} câmera${calibradas.length === 1 ? "" : "s"} calibrada${calibradas.length === 1 ? "" : "s"}${foraDoPadrao ? ` · ${foraDoPadrao} fora do padrão` : ""}`
                : ""}
            </p>
          </div>
          <div className="gemeo-acoes">
            <Legenda />
            {modo === "3d" && (
              <button type="button" className={`ghost ${drone ? "active" : ""}`} aria-pressed={drone} onClick={() => setDrone((d) => !d)}>
                Visão de drone
              </button>
            )}
            <a className="button ghost" href="/">
              Painel
            </a>
          </div>
        </header>
      )}
      <div className="gemeo-corpo">
        <div
          className="gemeo-viewport"
          ref={hostRef}
          data-testid="gemeo-viewport"
          data-modo={modo}
          data-pessoas={pessoas.length}
          data-quadros={metricas?.quadros ?? 0}
          data-intervalo-p95={metricas ? metricas.intervaloP95.toFixed(1) : ""}
          data-desenho-p95={metricas ? metricas.desenhoP95.toFixed(1) : ""}
          data-pausado={metricas?.pausado ? "1" : "0"}
          data-escala={metricas ? metricas.escala.toFixed(2) : ""}
        >
          {modo === "2d" && (
            <Gemeo2D cameras={cameras} onPessoa={selecionar} onZona={(cam) => setSel({ tipo: "zona", camera_id: cam.id, camera_nome: cam.nome, zona_nome: cam.zona_nome })} />
          )}
          {estado && calibradas.length === 0 && (
            <div className="gemeo-vazio">
              <EmptyState
                ilustracao={<IlustracaoPlanta />}
                titulo="Nenhuma câmera calibrada na planta"
                acao={
                  <a className="button primary" href="/">
                    Ir para as câmeras
                  </a>
                }
              >
                Calibre uma câmera na aba Planta (4 cliques no chão do vídeo e 4 na planta) e ela aparece aqui.
              </EmptyState>
            </div>
          )}
          {erro && !estado && (
            <div className="gemeo-vazio" role="alert">
              <h2>Não foi possível ler a planta</h2>
              <p>O servidor não respondeu ({erro}). A tela tenta de novo sozinha a cada meio segundo.</p>
            </div>
          )}
          {modo === "2d" && <span className="gemeo-selo">Planta 2D (sem WebGL)</span>}
        </div>
        <aside className="gemeo-lado" aria-label="Detalhes">
          {sel?.tipo === "pessoa" ? (
            <DetalhePessoa sel={sel} onReplay={setReplay} />
          ) : sel?.tipo === "zona" ? (
            <DetalheZona sel={sel} />
          ) : (
            <div className="gemeo-detalhe">
              <p className="gemeo-detalhe-kicker">Planta ao vivo</p>
              <h2>Toque numa pessoa ou numa zona</h2>
              <p className="muted">A pessoa abre a linha do tempo e o replay; a zona, o histórico de entradas.</p>
            </div>
          )}
          {pessoas.length > 0 && (
            <ul className="gemeo-pessoas" aria-label="Pessoas na planta">
              {pessoas.slice(0, 40).map(({ cam, pe }) => (
                <li key={`${cam.id}:${pe.track_id}`}>
                  <button type="button" className={`gemeo-pessoa ${pe.estado}`} data-testid="gemeo-pessoa" onClick={() => selecionar(cam, pe)}>
                    <span className="dot" />
                    <span>{`Pessoa ${pe.track_id}`}</span>
                    <span className="t-secondary">{cam.nome}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </aside>
      </div>
      {replay != null && <IncidentReplay alertId={replay} onClose={() => setReplay(null)} />}
    </div>
  );
}

export default GemeoScreen;
