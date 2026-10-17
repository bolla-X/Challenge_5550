import { mensagemDeErro } from "../utils/erros";
import { useEffect, useRef, useState } from "react";
import { useReducedMotion } from "motion/react";
import { useDashboardStore } from "../store/dashboardStore";
import { playCelebrationChime } from "../audio/chime";
import { EmptyState, Numero, PanelSkeleton } from "./common";
import { IlustracaoFila } from "./ilustracoes";

/**
 * Liga de Setores (X8): temporada semanal, nível da planta e missões do turno.
 * Só indicadores positivos e só por setor (regras em app/services/liga.py).
 */

export type MissaoEstado = {
  id: number;
  titulo: string;
  tipo: string;
  alvo: number;
  ate_hora: string | null;
  setor: string | null;
  feito: number;
  cumprida: boolean;
  progresso: number;
};
export type EstadoDaLiga = {
  temporada: { inicio: string; fim: string; semana: number; ano: number };
  setores: { setor: string; pontos: number; por_tipo: Record<string, number> }[];
  planta: { nivel: number; xp: number; xp_do_nivel: number; xp_do_proximo: number; progresso: number };
  turno: { nome: string; inicio: string; fim: string };
  missoes: MissaoEstado[];
  pontos: Record<string, number>;
  rotulos: Record<string, string>;
};

export function useLiga(intervaloMs = 5000): { liga: EstadoDaLiga | null; erro: string | null; recarregar: () => void } {
  const [liga, setLiga] = useState<EstadoDaLiga | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [n, setN] = useState(0);
  useEffect(() => {
    let vivo = true;
    const tick = () =>
      fetch("/api/liga", { credentials: "same-origin" })
        .then(async (r) => {
          if (!r.ok) throw new Error("o servidor não respondeu");
          return (await r.json()) as EstadoDaLiga;
        })
        .then((d) => {
          if (!vivo) return;
          setLiga(d);
          setErro(null);
        })
        .catch((e) => vivo && setErro(mensagemDeErro(e, "erro desconhecido")));
    tick();
    const id = window.setInterval(tick, intervaloMs);
    return () => {
      vivo = false;
      window.clearInterval(id);
    };
  }, [intervaloMs, n]);
  return { liga, erro, recarregar: () => setN((x) => x + 1) };
}

/** Confete leve (canvas, ~1,4 s) — não roda com prefers-reduced-motion. */
function confete(host: HTMLElement) {
  const canvas = document.createElement("canvas");
  canvas.className = "confete";
  canvas.setAttribute("aria-hidden", "true");
  const dpr = window.devicePixelRatio || 1;
  canvas.width = host.clientWidth * dpr;
  canvas.height = host.clientHeight * dpr;
  host.appendChild(canvas);
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  const css = getComputedStyle(document.documentElement);
  const cores = ["--accent", "--ok", "--text-3"].map((v) => css.getPropertyValue(v).trim() || "#888");
  const pedacos = Array.from({ length: 42 }, (_, i) => ({
    x: canvas.width * (0.3 + Math.random() * 0.4),
    y: canvas.height * 0.35,
    vx: (Math.random() - 0.5) * 9 * dpr,
    vy: (-5 - Math.random() * 6) * dpr,
    r: Math.random() * Math.PI,
    cor: cores[i % cores.length],
  }));
  const inicio = performance.now();
  const passo = (t: number) => {
    const k = (t - inicio) / 1400;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    for (const p of pedacos) {
      p.x += p.vx;
      p.y += p.vy;
      p.vy += 0.35 * dpr;
      p.r += 0.15;
      ctx.save();
      ctx.globalAlpha = Math.max(0, 1 - k);
      ctx.translate(p.x, p.y);
      ctx.rotate(p.r);
      ctx.fillStyle = p.cor;
      ctx.fillRect(-4 * dpr, -2 * dpr, 8 * dpr, 4 * dpr);
      ctx.restore();
    }
    if (k < 1) requestAnimationFrame(passo);
    else canvas.remove();
  };
  requestAnimationFrame(passo);
}

/** Celebra quando o nível sobe ou uma missão é cumprida (só a transição, nunca na 1ª leitura). */
export function useCelebracao(liga: EstadoDaLiga | null, hostRef: React.RefObject<HTMLElement>) {
  const anterior = useRef<{ nivel: number; cumpridas: Set<number> } | null>(null);
  const reduzir = useReducedMotion();
  const [aviso, setAviso] = useState<string | null>(null);
  useEffect(() => {
    if (!liga) return;
    const cumpridas = new Set(liga.missoes.filter((m) => m.cumprida).map((m) => m.id));
    const antes = anterior.current;
    anterior.current = { nivel: liga.planta.nivel, cumpridas };
    if (!antes) return;
    const novaMissao = liga.missoes.find((m) => m.cumprida && !antes.cumpridas.has(m.id));
    const subiu = liga.planta.nivel > antes.nivel;
    if (!novaMissao && !subiu) return;
    setAviso(subiu ? `A planta subiu para o nível ${liga.planta.nivel}` : `Missão cumprida: ${novaMissao?.titulo}`);
    window.setTimeout(() => setAviso(null), 4000);
    if (!reduzir && hostRef.current) confete(hostRef.current);
    if (!useDashboardStore.getState().muted) playCelebrationChime();
  }, [liga, reduzir, hostRef]);
  return aviso;
}

export function NivelDaPlanta({ planta }: { planta: EstadoDaLiga["planta"] }) {
  return (
    <div className="liga-nivel" data-testid="liga-nivel">
      <span className="liga-kicker">Nível da planta</span>
      <strong className="liga-nivel-numero t-data"><Numero valor={planta.nivel} /></strong>
      <div className="liga-barra" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(planta.progresso * 100)} aria-label="Progresso até o próximo nível">
        <span style={{ transform: `scaleX(${planta.progresso})` }} />
      </div>
      <span className="muted t-data">
        {planta.xp} pontos de experiência · faltam {planta.xp_do_proximo - planta.xp} para o nível {planta.nivel + 1}
      </span>
    </div>
  );
}

export function Missoes({ missoes, compacto = false }: { missoes: MissaoEstado[]; compacto?: boolean }) {
  if (!missoes.length) {
    return (
      <EmptyState ilustracao={<IlustracaoFila />} titulo="Nenhuma missão ativa">
        O supervisor configura as missões do turno da equipe nesta tela.
      </EmptyState>
    );
  }
  return (
    <ul className={`liga-missoes ${compacto ? "compacto" : ""}`} aria-label="Missões do turno">
      {missoes.map((m) => (
        <li key={m.id} className={m.cumprida ? "cumprida" : ""} data-testid="liga-missao" data-cumprida={m.cumprida ? "1" : "0"}>
          <div className="liga-missao-linha">
            <span>{m.titulo}</span>
            <strong className="t-data">
              {m.cumprida ? "Cumprida" : `${m.feito} / ${m.alvo}`}
            </strong>
          </div>
          <div className="liga-barra" aria-hidden="true">
            <span style={{ transform: `scaleX(${m.progresso})` }} />
          </div>
        </li>
      ))}
    </ul>
  );
}

export function Placar({ liga, limite = 8 }: { liga: EstadoDaLiga; limite?: number }) {
  const lider = liga.setores[0]?.pontos ?? 0;
  return (
    <ol className="liga-placar" aria-label={`Liga de Setores, semana ${liga.temporada.semana}`} data-testid="liga-placar">
      {liga.setores.slice(0, limite).map((s, i) => (
        <li key={s.setor}>
          <span className="liga-pos t-data">{i + 1}</span>
          <div className="liga-setor">
            <strong>{s.setor}</strong>
            <span className="muted">
              {Object.entries(s.por_tipo)
                .map(([tipo, n]) => `${liga.rotulos[tipo] ?? tipo}: ${n}`)
                .join(" · ") || "sem pontos ainda nesta temporada"}
            </span>
            <span className="liga-barra fina" aria-hidden="true">
              <span style={{ transform: `scaleX(${lider ? s.pontos / lider : 0})` }} />
            </span>
          </div>
          <strong className="liga-pontos t-data"><Numero valor={s.pontos} /></strong>
        </li>
      ))}
    </ol>
  );
}

/** Bloco compacto para o Modo TV e a Visão geral. */
export function LigaResumo() {
  const { liga } = useLiga();
  const hostRef = useRef<HTMLDivElement>(null);
  const aviso = useCelebracao(liga, hostRef);
  if (!liga) return <PanelSkeleton lines={3} />;
  return (
    <section className="liga-resumo" ref={hostRef} data-testid="liga-resumo">
      <header>
        <h2>Liga de Setores</h2>
        <span className="muted">Semana {liga.temporada.semana} · só indicadores positivos</span>
      </header>
      <div className="liga-resumo-grade">
        <Placar liga={liga} limite={4} />
        <div className="liga-resumo-lado">
          <NivelDaPlanta planta={liga.planta} />
          <Missoes missoes={liga.missoes} compacto />
        </div>
      </div>
      {aviso && (
        <div className="liga-aviso" role="status">
          {aviso}
        </div>
      )}
    </section>
  );
}

function NovaMissao({ onCriada }: { onCriada: () => void }) {
  const [titulo, setTitulo] = useState("");
  const [tipo, setTipo] = useState("checkin_portal");
  const [alvo, setAlvo] = useState(5);
  const [ateHora, setAteHora] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const criar = (e: React.FormEvent) => {
    e.preventDefault();
    fetch("/api/liga/missoes", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ titulo, tipo, alvo, ate_hora: ateHora || null }),
    })
      .then(async (r) => {
        if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error ?? "Falha ao criar a missão.");
        setTitulo("");
        setErro(null);
        onCriada();
      })
      .catch((err) => setErro(mensagemDeErro(err, "Falha ao criar a missão.")));
  };
  return (
    <form className="liga-nova" onSubmit={criar}>
      <label className="field">
        <span>Missão</span>
        <input value={titulo} onChange={(e) => setTitulo(e.target.value)} placeholder="Ex.: 100% dos check-ins antes das 8h" required />
      </label>
      <label className="field">
        <span>Conta</span>
        <select value={tipo} onChange={(e) => setTipo(e.target.value)}>
          <option value="checkin_portal">Check-ins no portal</option>
          <option value="reconhecido_rapido">Incidentes reconhecidos em até 1 min</option>
          <option value="rotulo">Rótulos revisados</option>
          <option value="minuto_conforme">Minutos conformes</option>
        </select>
      </label>
      <label className="field">
        <span>Alvo no turno</span>
        <input type="number" min={1} max={10000} value={alvo} onChange={(e) => setAlvo(Number(e.target.value))} />
      </label>
      <label className="field">
        <span>Até (opcional)</span>
        <input type="time" value={ateHora} onChange={(e) => setAteHora(e.target.value)} />
      </label>
      <button type="submit" className="primary">
        Criar missão
      </button>
      {erro && <p className="status-text error">{erro}</p>}
    </form>
  );
}

export function LigaScreen() {
  const { liga, erro, recarregar } = useLiga();
  const user = useDashboardStore((s) => s.user);
  const hostRef = useRef<HTMLDivElement>(null);
  const aviso = useCelebracao(liga, hostRef);
  const supervisor = user?.role === "supervisor";
  const desativar = (id: number) =>
    fetch(`/api/liga/missoes/${id}`, { method: "DELETE", credentials: "same-origin" }).then(recarregar);
  return (
    <div className="screen liga" ref={hostRef} data-testid="liga">
      <div className="screen-head">
        <h1>Liga de Setores</h1>
        <span className="screen-sub">
          {liga ? `Temporada da semana ${liga.temporada.semana}, turno ${liga.turno.nome}` : <span className="skeleton-block skeleton-inline" />}
        </span>
        <div className="screen-actions">
          <a className="button ghost" href="/retrospectiva">
            Retrospectiva
          </a>
          <a className="button ghost" href="/">
            Painel
          </a>
        </div>
      </div>
      {erro && !liga && (
        <div className="sim-erro" role="alert">
          Não foi possível carregar a liga ({erro}).
          <button type="button" className="ghost small" onClick={recarregar}>
            Tentar de novo
          </button>
        </div>
      )}
      {!liga ? (
        // Skeleton no formato final: placar à esquerda, nível e missões à direita.
        <div className="liga-grade" aria-busy="true">
          <section className="card">
            <div className="card-body">
              <PanelSkeleton lines={7} />
            </div>
          </section>
          <div className="liga-lado">
            <section className="card">
              <div className="card-body">
                <PanelSkeleton lines={3} />
              </div>
            </section>
            <section className="card">
              <div className="card-body">
                <PanelSkeleton lines={4} />
              </div>
            </section>
          </div>
        </div>
      ) : (
        <div className="liga-grade">
          <section className="card">
            <div className="card-head">
              <div>
                <h2>Placar da temporada</h2>
                <p>Pontos por setor: check-in no portal {liga.pontos.checkin_portal}, reconhecer em até 1 min {liga.pontos.reconhecido_rapido}, falso positivo revisado {liga.pontos.falso_positivo_revisado}, rótulo {liga.pontos.rotulo}, minuto conforme {liga.pontos.minuto_conforme}. Nunca negativo.</p>
              </div>
            </div>
            <div className="card-body">
              <Placar liga={liga} />
            </div>
          </section>
          <div className="liga-lado">
            <section className="card">
              <div className="card-body">
                <NivelDaPlanta planta={liga.planta} />
              </div>
            </section>
            <section className="card">
              <div className="card-head">
                <div>
                  <h2>Missões do turno</h2>
                  <p>Configuradas pelo supervisor; valem para a equipe, não para uma pessoa.</p>
                </div>
              </div>
              <div className="card-body">
                <Missoes missoes={liga.missoes} />
                {supervisor && liga.missoes.length > 0 && (
                  <details className="liga-gerenciar">
                    <summary>Desativar missão</summary>
                    <ul>
                      {liga.missoes.map((m) => (
                        <li key={m.id}>
                          {m.titulo}
                          <button type="button" className="ghost small" onClick={() => desativar(m.id)}>
                            Desativar
                          </button>
                        </li>
                      ))}
                    </ul>
                  </details>
                )}
                {supervisor && <NovaMissao onCriada={recarregar} />}
              </div>
            </section>
          </div>
        </div>
      )}
      {aviso && (
        <div className="liga-aviso" role="status">
          {aviso}
        </div>
      )}
    </div>
  );
}

export default LigaScreen;
