import { useEffect, useRef, useState } from "react";
import { LeitorMultipart } from "../socket/multipart";
import { useDashboardStore } from "../store/dashboardStore";
import { useAreaDeteccao } from "../store/areaDeteccaoStore";
import { desenharRaioX, HistoricoDePes, type RaioX } from "./raiox";
import { decimal } from "../utils/formato";

/**
 * Player de vídeo ao vivo em <canvas>, com o overlay desenhado NO NAVEGADOR.
 *
 * Antes o servidor desenhava caixas, pose e zona no próprio pixel e codificava
 * um JPEG por quadro, com ou sem alguém assistindo — a anotação era a etapa
 * mais cara do loop depois da inferência (ver docs/NEXT2026/BENCHMARKS.md).
 * Agora o stream (`video_feed?meta=1`) traz o quadro CRU e, antes dele, uma
 * parte JSON com as detecções; este componente desenha os dois.
 *
 * Estado de alta frequência (quadro, overlay, contadores) vive em refs, fora
 * do React: nenhum re-render por quadro. O React só re-renderiza quando o
 * estado do stream muda (ao vivo → sem sinal → reconectando).
 *
 * Por que fetch + ReadableStream e não <img>: com <img> o navegador não expõe
 * quando cada quadro chega, então não há como saber a idade do quadro na tela,
 * detectar travamento nem alinhar o overlay ao quadro certo.
 */

type Caixa = {
  l: string;
  n: string | null;
  c: number;
  b: [number, number, number, number];
  t: number | null;
  k: string;
  r: boolean;
  /** Segundos até entrar na zona de risco (pré-alerta), ou null. */
  a?: number | null;
};
export type Overlay = {
  v: number;
  w: number;
  h: number;
  caixas: Caixa[];
  poses: [number, number][][];
  zona: [number, number][];
  zona_ativa: boolean;
  /** Área de detecção (MISSÃO 7), normalizada; vazia ou ausente = quadro inteiro. */
  area?: [number, number][];
  opcoes: Record<string, boolean>;
  /** Dados do Modo Raio-X (X5); servidor anterior não manda. */
  raiox?: RaioX;
};

export type EstadoDoStream = "conectando" | "ao_vivo" | "sem_sinal" | "reconectando";

export type EstatisticasDoVideo = {
  exibidos: number;
  fps: number;
  idadeP50: number | null;
  idadeP95: number | null;
  ultimoQuadroEm: number;
  estado: EstadoDoStream;
};

// Registro global, lido pelo painel de diagnóstico e pelo bench (Playwright).
// Fora do React de propósito: escrever aqui a cada quadro não custa render.
type Registro = {
  chegadas: number[];
  idades: number[];
  exibidos: number;
  descartadosNoCliente: number;
  estado: EstadoDoStream;
  ultimo: number;
};
const REGISTRO: Record<string, Registro> = {};
(window as unknown as { __visionepiVideo: typeof REGISTRO }).__visionepiVideo = REGISTRO;

function percentil(valores: number[], p: number): number | null {
  if (!valores.length) return null;
  const ord = [...valores].sort((a, b) => a - b);
  return ord[Math.min(ord.length - 1, Math.floor((ord.length - 1) * p))];
}

export function estatisticasDoVideo(cameraId: number): EstatisticasDoVideo | null {
  const reg = REGISTRO[String(cameraId)];
  if (!reg) return null;
  const agora = performance.now();
  const recentes = reg.chegadas.filter((t) => agora - t <= 5000);
  const fps = recentes.length >= 2 ? (recentes.length - 1) / ((recentes[recentes.length - 1] - recentes[0]) / 1000) : 0;
  return {
    exibidos: reg.exibidos,
    fps: Number.isFinite(fps) ? fps : 0,
    idadeP50: percentil(reg.idades, 0.5),
    idadeP95: percentil(reg.idades, 0.95),
    ultimoQuadroEm: reg.ultimo,
    estado: reg.estado,
  };
}

// Cores do overlay: as MESMAS do anotador do servidor (app/vision/annotator.py,
// lá em BGR) — quem compara um snapshot com o vídeo vê a mesma linguagem.
const COR_PESSOA = "rgb(255,255,255)";
const COR_OK = "rgb(72,209,138)";
const COR_PERIGO = "rgb(255,158,94)";
const COR_APROXIMACAO = "rgb(255,214,10)";
const FUNDO_ROTULO = "rgba(18,19,22,0.75)";
const TEXTO_ROTULO = "rgb(245,245,247)";

const SEM_SINAL_MS = 3000;
function retangulo(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  const rr = Math.max(0, Math.min(r, w / 2, h / 2));
  ctx.beginPath();
  ctx.roundRect(x, y, w, h, rr);
}

// Área de detecção: contorno NEUTRO e tracejado — o laranja contínuo é da área de risco.
const COR_AREA_DETECCAO = "rgba(245,245,247,0.95)";
// Fora da área, o quadro fica com 35 % do brilho (o mesmo fator do servidor nas miniaturas e evidências).
const ESCURECER_FORA = "rgba(0,0,0,0.65)";
// Caixa de pessoa mantida, nítida: 10 % maior em cada lado (FOLGA_DA_CAIXA em area_de_deteccao.py).
const FOLGA_DA_CAIXA = 0.1;
const CAMADA = document.createElement("canvas");

function desenharAreaDeDeteccao(
  ctx: CanvasRenderingContext2D,
  ov: Overlay,
  dx: number,
  dy: number,
  escala: number,
  escurecer: boolean,
  rotulos: boolean,
) {
  const area = ov.area || [];
  if (area.length < 3) return;
  const pontos = area.map(([x, y]) => [dx + x * ov.w * escala, dy + y * ov.h * escala] as const);
  const contorno = () => pontos.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
  ctx.save();
  if (escurecer) {
    // Camada escura num canvas à parte, com o polígono E as pessoas mantidas recortados dela: quem tem os pés
    // na área fica nítido inteiro, mesmo com a cabeça para fora (a mesma regra das miniaturas e evidências).
    const larg = Math.max(1, Math.round(ov.w * escala));
    const alt = Math.max(1, Math.round(ov.h * escala));
    if (CAMADA.width !== larg || CAMADA.height !== alt) {
      CAMADA.width = larg;
      CAMADA.height = alt;
    }
    const c = CAMADA.getContext("2d");
    if (c) {
      c.globalCompositeOperation = "source-over";
      c.clearRect(0, 0, larg, alt);
      c.fillStyle = ESCURECER_FORA;
      c.fillRect(0, 0, larg, alt);
      c.globalCompositeOperation = "destination-out";
      c.beginPath();
      area.forEach(([x, y], i) => (i ? c.lineTo(x * larg, y * alt) : c.moveTo(x * larg, y * alt)));
      c.closePath();
      c.fill();
      for (const cx of ov.caixas) {
        if (cx.k !== "pessoa" && cx.k !== "queda") continue;
        const [x1, y1, x2, y2] = cx.b;
        const fx = (x2 - x1) * FOLGA_DA_CAIXA;
        const fy = (y2 - y1) * FOLGA_DA_CAIXA;
        c.fillRect((x1 - fx) * escala, (y1 - fy) * escala, (x2 - x1 + 2 * fx) * escala, (y2 - y1 + 2 * fy) * escala);
      }
      c.globalCompositeOperation = "source-over";
      ctx.drawImage(CAMADA, dx, dy);
    }
  }
  ctx.beginPath();
  contorno();
  ctx.closePath();
  // Halo contínuo escuro por baixo do tracejado claro: legível sobre palco iluminado e sobre fundo escuro.
  ctx.lineWidth = 4;
  ctx.strokeStyle = "rgba(0,0,0,0.55)";
  ctx.stroke();
  ctx.setLineDash([8, 6]);
  ctx.lineWidth = 2;
  ctx.strokeStyle = COR_AREA_DETECCAO;
  ctx.stroke();
  ctx.setLineDash([]);
  if (rotulos) {
    const [tx, ty] = pontos.reduce((a, b) => (b[1] < a[1] || (b[1] === a[1] && b[0] < a[0]) ? b : a));
    const texto = "Área de detecção";
    ctx.textBaseline = "middle";
    const largura = ctx.measureText(texto).width + 12;
    const altura = 22;
    const lx = Math.max(dx, Math.min(tx, dx + ov.w * escala - largura));
    const ly = ty - altura >= dy ? ty - altura : ty;
    ctx.fillStyle = FUNDO_ROTULO;
    retangulo(ctx, lx, ly, largura, altura, 9);
    ctx.fill();
    ctx.fillStyle = TEXTO_ROTULO;
    ctx.fillText(texto, lx + 6, ly + altura / 2);
  }
  ctx.restore();
}

export function desenharOverlay(
  ctx: CanvasRenderingContext2D,
  ov: Overlay,
  dx: number,
  dy: number,
  escala: number,
  /** O replay já grava o quadro escurecido (evidência): lá só o contorno. */
  { escurecerFora = true }: { escurecerFora?: boolean } = {},
) {
  const opc = ov.opcoes || {};
  const mostrarCaixas = opc.boxes !== false;
  const mostrarRotulos = opc.labels !== false;
  const mostrarConf = opc.confidence !== false;
  const px = (x: number) => dx + x * escala;
  const py = (y: number) => dy + y * escala;

  const fonte = Math.max(12, Math.round(13 * Math.min(1.6, Math.max(0.8, escala * 1.3))));
  ctx.font = `600 ${fonte}px "Geist Variable", system-ui, sans-serif`;
  desenharAreaDeDeteccao(ctx, ov, dx, dy, escala, escurecerFora, mostrarRotulos);

  if (ov.zona_ativa && opc.risk_area !== false && ov.zona.length >= 3) {
    ctx.beginPath();
    ov.zona.forEach(([x, y], i) => (i ? ctx.lineTo(px(x * ov.w), py(y * ov.h)) : ctx.moveTo(px(x * ov.w), py(y * ov.h))));
    ctx.closePath();
    ctx.fillStyle = "rgba(255,158,94,0.08)";
    ctx.fill();
    ctx.lineWidth = 2;
    ctx.strokeStyle = COR_PERIGO;
    ctx.stroke();
  }

  ctx.font = `600 ${fonte}px "Geist Variable", system-ui, sans-serif`;
  ctx.textBaseline = "middle";
  for (const cx of ov.caixas) {
    const [x1, y1, x2, y2] = cx.b;
    const pessoa = cx.k === "pessoa";
    const perigo = cx.r || cx.k === "queda";
    const aproximando = !perigo && cx.a != null;
    if (mostrarCaixas) {
      ctx.lineWidth = perigo || aproximando ? 3 : 2;
      ctx.strokeStyle = perigo ? COR_PERIGO : aproximando ? COR_APROXIMACAO : pessoa ? COR_PESSOA : COR_OK;
      ctx.globalAlpha = pessoa && !perigo ? 0.9 : 1;
      retangulo(ctx, px(x1), py(y1), (x2 - x1) * escala, (y2 - y1) * escala, 10);
      ctx.stroke();
      ctx.globalAlpha = 1;
    }
    if (mostrarRotulos) {
      let texto = pessoa ? (cx.t != null ? `Pessoa ${cx.t}` : "Pessoa") : cx.n || cx.l;
      if (mostrarConf) texto += ` ${decimal(cx.c, 2)}`;
      if (aproximando) texto += ` · entra na zona em ~${decimal(cx.a as number)} s`;
      const largura = ctx.measureText(texto).width + 12;
      const altura = fonte + 8;
      const lx = Math.max(dx, Math.min(px(x1), dx + ov.w * escala - largura));
      const ly = pessoa && py(y1) - altura >= dy ? py(y1) - altura : py(y1);
      ctx.fillStyle = FUNDO_ROTULO;
      retangulo(ctx, lx, ly, largura, altura, 9);
      ctx.fill();
      ctx.fillStyle = perigo ? COR_PERIGO : aproximando ? COR_APROXIMACAO : TEXTO_ROTULO;
      ctx.fillText(texto, lx + 6, ly + altura / 2);
    }
  }

  if (ov.poses.length) {
    ctx.fillStyle = COR_PESSOA;
    ctx.globalAlpha = 0.5;
    for (const pose of ov.poses) {
      for (const [x, y] of pose) {
        ctx.beginPath();
        ctx.arc(px(x * ov.w), py(y * ov.h), 2.5, 0, Math.PI * 2);
        ctx.fill();
      }
    }
    ctx.globalAlpha = 1;
  }
}

export function LiveVideo({
  cameraId,
  label,
  anotado = false,
  onEstado,
}: {
  cameraId: number;
  label: string;
  /** Pede o overlay desenhado no servidor (quem não quer depender do canvas). */
  anotado?: boolean;
  onEstado?: (estado: EstadoDoStream) => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [estado, setEstado] = useState<EstadoDoStream>("conectando");
  const onEstadoRef = useRef(onEstado);
  onEstadoRef.current = onEstado;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    const ctx = canvas.getContext("2d");
    if (!ctx) return undefined;
    const chave = String(cameraId);
    const reg: Registro = (REGISTRO[chave] = { chegadas: [], idades: [], exibidos: 0, descartadosNoCliente: 0, estado: "conectando", ultimo: 0 });
    let vivo = true;
    let controlador: AbortController | null = null;
    let overlay: Overlay | null = null;
    let pendente: { bmp: ImageBitmap; ov: Overlay | null; ts: number | null } | null = null;
    let raf = 0;
    let tentativa = 0;
    let estadoAtual: EstadoDoStream = "conectando";
    const historico = new HistoricoDePes();

    const mudarEstado = (novo: EstadoDoStream) => {
      if (novo === estadoAtual) return;
      estadoAtual = novo;
      reg.estado = novo;
      setEstado(novo);
      onEstadoRef.current?.(novo);
    };

    const desenhar = () => {
      raf = 0;
      const item = pendente;
      pendente = null;
      if (!item || !vivo) {
        item?.bmp.close();
        return;
      }
      const dpr = window.devicePixelRatio || 1;
      const largura = Math.max(1, Math.round(canvas.clientWidth * dpr));
      const altura = Math.max(1, Math.round(canvas.clientHeight * dpr));
      if (canvas.width !== largura || canvas.height !== altura) {
        canvas.width = largura;
        canvas.height = altura;
      }
      const escala = Math.min(largura / item.bmp.width, altura / item.bmp.height);
      const w = item.bmp.width * escala;
      const h = item.bmp.height * escala;
      const dx = (largura - w) / 2;
      const dy = (altura - h) / 2;
      ctx.clearRect(0, 0, largura, altura);
      ctx.drawImage(item.bmp, dx, dy, w, h);
      if (item.ov && item.ov.w) {
        // Desenhando a área de detecção desta câmera: só o rascunho do editor aparece, sem a área salva por cima.
        const ed = useAreaDeteccao.getState();
        const redesenhando = ed.editando && ed.tipo === "deteccao" && ed.camId === cameraId;
        desenharOverlay(ctx, redesenhando ? { ...item.ov, area: [] } : item.ov, dx, dy, w / item.ov.w);
        // Raio-X: o histórico dos pés anda sempre (as trilhas já existem ao ligar).
        historico.registrar(item.ov.v, item.ov.caixas, item.ov.w, item.ov.h);
        const raio = useDashboardStore.getState().raioX;
        if (raio && item.ov.raiox) desenharRaioX(ctx, item.ov.raiox, item.ov.caixas, item.ov.w, item.ov.h, dx, dy, w / item.ov.w, historico);
        canvas.dataset.raiox = raio && item.ov.raiox ? "1" : "0";
      }
      // Para o E2E e o editor: a área que está sendo aplicada neste quadro ("" = quadro inteiro).
      canvas.dataset.area = item.ov?.area && item.ov.area.length >= 3 ? JSON.stringify(item.ov.area) : "";
      canvas.dataset.w = String(item.bmp.width);
      canvas.dataset.h = String(item.bmp.height);
      item.bmp.close();
      const agora = performance.now();
      reg.exibidos += 1;
      reg.ultimo = agora;
      reg.chegadas.push(agora);
      if (reg.chegadas.length > 300) reg.chegadas.splice(0, reg.chegadas.length - 300);
      if (item.ts) {
        reg.idades.push(Date.now() - item.ts);
        if (reg.idades.length > 300) reg.idades.splice(0, reg.idades.length - 300);
      }
      canvas.dataset.frames = String(reg.exibidos);
      mudarEstado("ao_vivo");
    };

    const vigia = window.setInterval(() => {
      if (estadoAtual === "ao_vivo" && performance.now() - reg.ultimo > SEM_SINAL_MS) mudarEstado("sem_sinal");
    }, 1000);

    // Um decode por vez; o que chegar durante ele substitui o "próximo" (não
    // enfileira). O laço de leitura nunca espera o decode.
    let decodificando = false;
    let proximo: { corpo: Uint8Array; ov: Overlay | null; ts: number | null } | null = null;
    const decodificar = (item: { corpo: Uint8Array; ov: Overlay | null; ts: number | null }) => {
      if (decodificando) {
        if (proximo) reg.descartadosNoCliente += 1;
        proximo = item;
        return;
      }
      decodificando = true;
      createImageBitmap(new Blob([item.corpo as BlobPart], { type: "image/jpeg" }))
        .then((bmp) => {
          if (!vivo) {
            bmp.close();
            return;
          }
          // Último quadro vence também no desenho: o anterior não desenhado sai.
          pendente?.bmp.close();
          pendente = { bmp, ov: item.ov, ts: item.ts };
          if (!raf) raf = requestAnimationFrame(desenhar);
        })
        .catch(() => undefined)
        .finally(() => {
          decodificando = false;
          const seguinte = proximo;
          proximo = null;
          if (seguinte && vivo) decodificar(seguinte);
        });
    };

    const conectar = async () => {
      while (vivo) {
        controlador = new AbortController();
        try {
          const resp = await fetch(`/api/cameras/${cameraId}/video_feed?meta=1${anotado ? "&anotado=1" : ""}`, {
            signal: controlador.signal,
            credentials: "same-origin",
            cache: "no-store",
          });
          if (!resp.ok || !resp.body) throw new Error(`HTTP ${resp.status}`);
          tentativa = 0;
          const leitor = resp.body.getReader();
          const multipart = new LeitorMultipart();
          while (vivo) {
            const { value, done } = await leitor.read();
            if (done) break;
            multipart.empurrar(value);
            // Lê TUDO o que chegou e fica só com o quadro mais novo: decodificar
            // quadro velho só aumentaria a idade do que aparece na tela.
            let maisNovo: { corpo: Uint8Array; ov: Overlay | null; ts: number | null } | null = null;
            for (const parte of multipart.partes()) {
              if (/application\/json/i.test(parte.cabecalho)) {
                try {
                  overlay = JSON.parse(new TextDecoder().decode(parte.corpo)) as Overlay;
                } catch {
                  overlay = null;
                }
                continue;
              }
              const ts = /X-Capture-Ts:\s*([\d.]+)/i.exec(parte.cabecalho);
              // Quadro sem X-Frame-Id é o placeholder do servidor (câmera parada).
              const temQuadro = /X-Frame-Id:/i.test(parte.cabecalho);
              if (maisNovo) reg.descartadosNoCliente += 1;
              maisNovo = { corpo: parte.corpo, ov: temQuadro ? overlay : null, ts: ts ? parseFloat(ts[1]) : null };
            }
            if (maisNovo) decodificar(maisNovo);
          }
        } catch (err) {
          if ((err as Error)?.name === "AbortError" || !vivo) return;
        }
        if (!vivo) return;
        mudarEstado("reconectando");
        tentativa += 1;
        // Backoff exponencial com jitter: N abas reconectando juntas não batem
        // no servidor no mesmo instante.
        const espera = Math.min(8000, 500 * 2 ** Math.min(tentativa, 4)) * (0.75 + Math.random() * 0.5);
        await new Promise((r) => setTimeout(r, espera));
      }
    };
    conectar();

    return () => {
      vivo = false;
      controlador?.abort();
      window.clearInterval(vigia);
      if (raf) cancelAnimationFrame(raf);
      pendente?.bmp.close();
      pendente = null;
      delete REGISTRO[chave];
    };
  }, [cameraId, anotado]);

  return (
    <canvas
      ref={canvasRef}
      className="live-video"
      role="img"
      aria-label={label}
      data-estado={estado}
      data-camera={cameraId}
    />
  );
}
