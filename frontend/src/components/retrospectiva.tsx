import { useCallback, useEffect, useRef, useState } from "react";
import { useReducedMotion } from "motion/react";
import { PanelSkeleton } from "./common";

/**
 * Retrospectiva da Segurança (X7), estilo "stories": um card por vez, com
 * dados reais do turno ou da semana. Cada card exporta um PNG (1080×1350)
 * desenhado em canvas — sem lib de captura de tela. Nada individual.
 */

export type Cartao = { chave: string; titulo: string; valor: number | string; unidade: string; detalhe: string };
const zerado = (c: Cartao) => c.valor === 0 || c.valor === "0";

type Retro = { periodo: string; titulo: string; inicio: string; fim: string; cards: Cartao[] };

const DURACAO_MS = 6000;

function tokens() {
  const css = getComputedStyle(document.documentElement);
  const v = (n: string, p: string) => css.getPropertyValue(n).trim() || p;
  return { fundo: v("--surface", "#fff"), texto: v("--text", "#1a1a1c"), texto2: v("--text-2", "#5e5e64"), acento: v("--accent", "#0a66c2") };
}

function quebrar(ctx: CanvasRenderingContext2D, texto: string, largura: number): string[] {
  const linhas: string[] = [];
  let atual = "";
  for (const palavra of texto.split(" ")) {
    const teste = atual ? `${atual} ${palavra}` : palavra;
    if (ctx.measureText(teste).width > largura && atual) {
      linhas.push(atual);
      atual = palavra;
    } else {
      atual = teste;
    }
  }
  if (atual) linhas.push(atual);
  return linhas;
}

export function exportarPng(cartao: Cartao, retro: { titulo: string }, indice: number, total: number): Promise<Blob | null> {
  const W = 1080;
  const H = 1350;
  const canvas = document.createElement("canvas");
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext("2d");
  if (!ctx) return Promise.resolve(null);
  const t = tokens();
  ctx.fillStyle = t.fundo;
  ctx.fillRect(0, 0, W, H);
  const fonte = '"Geist Variable", system-ui, sans-serif';
  // Segmentos dos stories no topo.
  const seg = (W - 120 - (total - 1) * 10) / total;
  for (let i = 0; i < total; i += 1) {
    ctx.fillStyle = i <= indice ? t.acento : t.texto2;
    ctx.globalAlpha = i <= indice ? 1 : 0.25;
    ctx.fillRect(60 + i * (seg + 10), 60, seg, 6);
  }
  ctx.globalAlpha = 1;
  ctx.fillStyle = t.texto2;
  ctx.font = `500 36px ${fonte}`;
  ctx.fillText(`VisionEPI · ${retro.titulo}`, 60, 150);
  ctx.fillStyle = t.texto;
  ctx.font = `600 64px ${fonte}`;
  quebrar(ctx, cartao.titulo, W - 120).forEach((l, i) => ctx.fillText(l, 60, 300 + i * 76));
  const valor = `${cartao.valor}${cartao.unidade ? ` ${cartao.unidade}` : ""}`;
  ctx.font = `700 ${String(valor).length > 8 ? 150 : 240}px ${fonte}`;
  ctx.fillStyle = t.acento;
  ctx.fillText(valor, 52, 720);
  ctx.fillStyle = t.texto2;
  ctx.font = `400 44px ${fonte}`;
  quebrar(ctx, cartao.detalhe, W - 120).forEach((l, i) => ctx.fillText(l, 60, 830 + i * 58));
  ctx.font = `500 30px ${fonte}`;
  ctx.fillText("Dados do sistema · por setor e equipe, nunca por pessoa", 60, H - 70);
  return new Promise((resolve) => canvas.toBlob((b) => resolve(b), "image/png"));
}

function useRetro(periodo: string) {
  const [retro, setRetro] = useState<Retro | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const carregar = useCallback(() => {
    setErro(null);
    fetch(`/api/retrospectiva?periodo=${periodo}`, { credentials: "same-origin" })
      .then(async (r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return (await r.json()) as Retro;
      })
      // Cartões com dado do período primeiro; os ainda zerados vão para o fim (continuam lá, sem esconder).
      .then((d) => setRetro({ ...d, cards: [...d.cards].sort((a, b) => Number(zerado(a)) - Number(zerado(b))) }))
      .catch((e) => setErro(e instanceof Error ? e.message : "falha"));
  }, [periodo]);
  useEffect(carregar, [carregar]);
  return { retro, erro, carregar };
}

export function RetrospectivaStories({ periodo = "turno", onFechar, autoplay = true }: { periodo?: string; onFechar?: () => void; autoplay?: boolean }) {
  const { retro, erro, carregar } = useRetro(periodo);
  const [indice, setIndice] = useState(0);
  const [pausado, setPausado] = useState(!autoplay);
  const reduzir = useReducedMotion();
  const total = retro?.cards.length ?? 0;
  const ir = useCallback((delta: number) => setIndice((i) => Math.max(0, Math.min(total - 1, i + delta))), [total]);
  const inicioRef = useRef(performance.now());

  useEffect(() => {
    inicioRef.current = performance.now();
    if (pausado || !total || indice >= total - 1) return undefined;
    const id = window.setTimeout(() => ir(1), DURACAO_MS);
    return () => window.clearTimeout(id);
  }, [indice, pausado, total, ir]);

  useEffect(() => {
    const tecla = (e: KeyboardEvent) => {
      if (e.key === "ArrowRight") ir(1);
      else if (e.key === "ArrowLeft") ir(-1);
      else if (e.key === "Escape") onFechar?.();
      else return;
      e.preventDefault();
    };
    window.addEventListener("keydown", tecla);
    return () => window.removeEventListener("keydown", tecla);
  }, [ir, onFechar]);

  const baixar = () => {
    if (!retro) return;
    const cartao = retro.cards[indice];
    exportarPng(cartao, retro, indice, total).then((blob) => {
      if (!blob) return;
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `visionepi-retrospectiva-${retro.periodo}-${cartao.chave}.png`;
      a.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 2000);
    });
  };

  if (erro) {
    return (
      <div className="retro" role="alert">
        <div className="retro-card">
          <p className="retro-kicker">Retrospectiva</p>
          <h2>Não foi possível montar a retrospectiva</h2>
          <button type="button" className="primary" onClick={carregar}>
            Tentar de novo
          </button>
        </div>
      </div>
    );
  }
  if (!retro) {
    return (
      <div className="retro" aria-busy="true">
        <div className="retro-card">
          <PanelSkeleton lines={4} />
        </div>
      </div>
    );
  }
  const cartao = retro.cards[indice];
  return (
    <div className="retro" data-testid="retrospectiva" data-indice={indice} data-total={total}>
      <div className="retro-segmentos" aria-hidden="true">
        {retro.cards.map((c, i) => (
          <span key={c.chave} className={i < indice ? "cheio" : i === indice ? "atual" : ""}>
            {i === indice && !pausado && !reduzir && <i style={{ animationDuration: `${DURACAO_MS}ms` }} />}
          </span>
        ))}
      </div>
      <article key={cartao.chave} className={`retro-card ${reduzir ? "" : "entra"}`} aria-roledescription="story" aria-label={`${indice + 1} de ${total}: ${cartao.titulo}`} data-testid="retro-card" data-chave={cartao.chave}>
        <p className="retro-kicker">{retro.titulo}</p>
        <h2>{cartao.titulo}</h2>
        <p className="retro-valor t-data">
          {cartao.valor}
          {cartao.unidade && <span className="retro-unidade"> {cartao.unidade}</span>}
        </p>
        <p className="retro-detalhe">{cartao.detalhe}</p>
        <button type="button" className="retro-zona anterior" aria-label="Card anterior" onClick={() => ir(-1)} />
        <button type="button" className="retro-zona proxima" aria-label="Próximo card" onClick={() => ir(1)} />
      </article>
      <div className="retro-acoes">
        <button type="button" className="ghost small" onClick={() => setPausado((p) => !p)}>
          {pausado ? "Continuar" : "Pausar"}
        </button>
        <button type="button" className="small" onClick={baixar} data-testid="retro-png">
          Baixar PNG
        </button>
        {onFechar && (
          <button type="button" className="ghost small" onClick={onFechar}>
            Fechar
          </button>
        )}
      </div>
    </div>
  );
}

export function RetrospectivaScreen() {
  const periodo = new URLSearchParams(window.location.search).get("periodo") === "semana" ? "semana" : "turno";
  return (
    <div className="screen retro-tela">
      <div className="screen-head">
        <h1>Retrospectiva da Segurança</h1>
        <div className="segmented" role="tablist">
          <a role="tab" aria-selected={periodo === "turno"} className={`button ${periodo === "turno" ? "active" : ""}`} href="/retrospectiva">
            Turno
          </a>
          <a role="tab" aria-selected={periodo === "semana"} className={`button ${periodo === "semana" ? "active" : ""}`} href="/retrospectiva?periodo=semana">
            Semana
          </a>
        </div>
        <div className="screen-actions">
          <a className="button ghost" href="/liga">
            Liga
          </a>
          <a className="button ghost" href="/">
            Painel
          </a>
        </div>
      </div>
      <RetrospectivaStories periodo={periodo} />
    </div>
  );
}

export default RetrospectivaScreen;
