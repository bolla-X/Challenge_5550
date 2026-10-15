/**
 * Modo Raio-X (X5): o que o modelo viu, separado do que o sistema decidiu.
 *
 * Desenha por cima do vídeo (mesmo canvas do overlay): esqueleto da pose,
 * barras de confiança por classe de EPI com o piso da classe, as detecções que
 * o filtro DESCARTOU (com o motivo), trilhas fantasma dos últimos 5 s e o
 * vetor de velocidade do F3. A decisão (alerta / confirmando / ok) aparece ao
 * lado da confiança bruta, nunca misturada com ela.
 */

/** Quantas pessoas ganham o painel "modelo x decisão" por quadro. */
const PAINEIS_MAX = 3;

export type RaioX = {
  esqueletos: { t: number | null; j: ([number, number, number] | null)[] }[];
  pessoas: { t: number | null; epis: Record<string, [number, string]>; decisao: Record<string, string>; vel: [number, number] | null }[];
  descartadas: { l: string; c: number; b: [number, number, number, number]; m: string }[];
  pisos: Record<string, number>;
  confianca_min: number;
};

type CaixaPessoa = { t: number | null; b: [number, number, number, number]; k: string };

// Mesmas juntas e ordem de camera_worker.JUNTAS.
const OSSOS: [number, number][] = [
  [1, 2], [1, 3], [3, 5], [2, 4], [4, 6], [1, 7], [2, 8], [7, 8], [7, 9], [9, 11], [8, 10], [10, 12],
];
const NOME_CURTO: Record<string, string> = {
  helmet: "Capacete", vest: "Colete", gloves: "Luvas", glasses: "Óculos", mask: "Máscara",
  safety_shoe: "Calçado", ear_protection: "Protetor", hardhat: "Capacete", safety_vest: "Colete", goggles: "Óculos",
};
const BRANCO = "rgba(245,245,247,0.95)";
const FANTASMA = "rgba(245,245,247,";
const OK = "rgb(72,209,138)";
const PERIGO = "rgb(255,158,94)";
const AMARELO = "rgb(255,214,10)";
const FUNDO = "rgba(18,19,22,0.82)";
const SEGUNDOS_DE_TRILHA = 5;

/** Histórico dos pés por ID (cliente), para as trilhas fantasma. */
export class HistoricoDePes {
  private porId = new Map<number, { x: number; y: number; t: number }[]>();
  private versao = -1;

  registrar(versao: number, caixas: CaixaPessoa[], w: number, h: number, agora = performance.now()): void {
    if (versao === this.versao) return;
    this.versao = versao;
    for (const c of caixas) {
      if (c.k !== "pessoa" || c.t == null) continue;
      const lista = this.porId.get(c.t) ?? [];
      lista.push({ x: (c.b[0] + c.b[2]) / 2 / w, y: c.b[3] / h, t: agora });
      this.porId.set(c.t, lista);
    }
    for (const [id, lista] of this.porId) {
      const recentes = lista.filter((p) => agora - p.t <= SEGUNDOS_DE_TRILHA * 1000);
      if (recentes.length) this.porId.set(id, recentes);
      else this.porId.delete(id);
    }
  }

  trilhas(): Map<number, { x: number; y: number; t: number }[]> {
    return this.porId;
  }
}

function rotuloCurto(chave: string): string {
  return NOME_CURTO[chave] ?? chave;
}

export function desenharRaioX(
  ctx: CanvasRenderingContext2D,
  dados: RaioX,
  caixas: CaixaPessoa[],
  w: number,
  h: number,
  dx: number,
  dy: number,
  escala: number,
  historico: HistoricoDePes,
  agora = performance.now(),
): void {
  const px = (x: number) => dx + x * escala;
  const py = (y: number) => dy + y * escala;
  const fonte = Math.max(11, Math.round(12 * Math.min(1.5, Math.max(0.85, escala * 1.3))));

  // Trilhas fantasma (5 s, desbotando).
  ctx.lineCap = "round";
  for (const pontos of historico.trilhas().values()) {
    for (let i = 1; i < pontos.length; i += 1) {
      const idade = (agora - pontos[i].t) / (SEGUNDOS_DE_TRILHA * 1000);
      ctx.strokeStyle = `${FANTASMA}${Math.max(0, 0.75 * (1 - idade)).toFixed(3)})`;
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.moveTo(px(pontos[i - 1].x * w), py(pontos[i - 1].y * h));
      ctx.lineTo(px(pontos[i].x * w), py(pontos[i].y * h));
      ctx.stroke();
    }
  }

  // Esqueletos.
  for (const esq of dados.esqueletos) {
    ctx.strokeStyle = BRANCO;
    ctx.lineWidth = 2;
    for (const [a, b] of OSSOS) {
      const ja = esq.j[a];
      const jb = esq.j[b];
      if (!ja || !jb || ja[2] < 0.3 || jb[2] < 0.3) continue;
      ctx.beginPath();
      ctx.moveTo(px(ja[0] * w), py(ja[1] * h));
      ctx.lineTo(px(jb[0] * w), py(jb[1] * h));
      ctx.stroke();
    }
    for (const j of esq.j) {
      if (!j || j[2] < 0.3) continue;
      ctx.fillStyle = BRANCO;
      ctx.beginPath();
      ctx.arc(px(j[0] * w), py(j[1] * h), 3, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  // Detecções descartadas pelo filtro: tracejadas, com o motivo.
  ctx.font = `600 ${fonte}px "Geist Variable", system-ui, sans-serif`;
  ctx.textBaseline = "middle";
  for (const d of dados.descartadas) {
    const [x1, y1, x2, y2] = d.b;
    ctx.setLineDash([5, 4]);
    ctx.strokeStyle = "rgba(245,245,247,0.6)";
    ctx.lineWidth = 1.5;
    ctx.strokeRect(px(x1), py(y1), (x2 - x1) * escala, (y2 - y1) * escala);
    ctx.setLineDash([]);
    const texto = `${rotuloCurto(d.l)} ${d.c.toFixed(2)} · descartado: ${d.m}`;
    const lw = ctx.measureText(texto).width + 10;
    ctx.fillStyle = FUNDO;
    ctx.fillRect(px(x1), py(y2) + 2, lw, fonte + 6);
    ctx.fillStyle = "rgba(245,245,247,0.85)";
    ctx.fillText(texto, px(x1) + 5, py(y2) + 2 + (fonte + 6) / 2);
  }

  // Por pessoa: vetor de velocidade e painel "modelo x decisão".
  const porId = new Map(dados.pessoas.map((p) => [p.t, p]));
  // Painel só para as pessoas maiores (mais perto da câmera) e sem sobrepor outro
  // painel: numa multidão, um painel por pessoa virava uma parede ilegível.
  const area = (c: (typeof caixas)[number]) => (c.b[2] - c.b[0]) * (c.b[3] - c.b[1]);
  const comPainel = new Set(
    caixas.filter((c) => c.k === "pessoa" && c.t != null).sort((a, b) => area(b) - area(a)).slice(0, PAINEIS_MAX).map((c) => c.t),
  );
  const ocupados: [number, number, number, number][] = [];
  for (const c of caixas) {
    if (c.k !== "pessoa" || c.t == null) continue;
    const p = porId.get(c.t);
    if (!p) continue;
    const [x1, y1, x2, y2] = c.b;
    if (p.vel) {
      // Para onde os pés vão em 1 s (F3), na escala do quadro.
      const fx = px((x1 + x2) / 2);
      const fy = py(y2);
      const tx = fx + p.vel[0] * w * escala;
      const ty = fy + p.vel[1] * h * escala;
      if (Math.hypot(tx - fx, ty - fy) > 4) {
        ctx.strokeStyle = AMARELO;
        ctx.fillStyle = AMARELO;
        ctx.lineWidth = 2.5;
        ctx.beginPath();
        ctx.moveTo(fx, fy);
        ctx.lineTo(tx, ty);
        ctx.stroke();
        const ang = Math.atan2(ty - fy, tx - fx);
        ctx.beginPath();
        ctx.moveTo(tx, ty);
        ctx.lineTo(tx - 9 * Math.cos(ang - 0.45), ty - 9 * Math.sin(ang - 0.45));
        ctx.lineTo(tx - 9 * Math.cos(ang + 0.45), ty - 9 * Math.sin(ang + 0.45));
        ctx.closePath();
        ctx.fill();
      }
    }
    const linhas = Object.entries(p.epis);
    if (!linhas.length || !comPainel.has(c.t)) continue;
    const linhaH = fonte + 8;
    const largura = Math.max(150, fonte * 13);
    const altura = linhas.length * linhaH + 10;
    let ox = px(x2) + 6;
    if (ox + largura > dx + w * escala) ox = Math.max(dx, px(x1) - largura - 6);
    const oy = Math.max(dy, Math.min(py(y1), dy + h * escala - altura));
    if (ocupados.some(([ax, ay, aw, ah]) => ox < ax + aw && ox + largura > ax && oy < ay + ah && oy + altura > ay)) continue;
    ocupados.push([ox, oy, largura, altura]);
    ctx.fillStyle = FUNDO;
    ctx.beginPath();
    ctx.roundRect(ox, oy, largura, altura, 8);
    ctx.fill();
    linhas.forEach(([chave, [conf, status]], i) => {
      const y = oy + 5 + i * linhaH;
      const decisao = p.decisao[chave];
      const corDecisao = status === "ok" ? OK : decisao === "alerta" ? PERIGO : status === "missing" || status === "incorrect" ? AMARELO : BRANCO;
      ctx.fillStyle = BRANCO;
      ctx.fillText(rotuloCurto(chave), ox + 8, y + linhaH / 2);
      // Barra: confiança bruta do modelo, com o piso da classe marcado.
      const bx = ox + largura * 0.42;
      const bw = largura * 0.3;
      ctx.fillStyle = "rgba(245,245,247,0.18)";
      ctx.fillRect(bx, y + linhaH / 2 - 3, bw, 6);
      ctx.fillStyle = BRANCO;
      ctx.fillRect(bx, y + linhaH / 2 - 3, bw * Math.max(0, Math.min(1, conf)), 6);
      const piso = dados.pisos[chave] ?? dados.confianca_min;
      ctx.fillStyle = AMARELO;
      ctx.fillRect(bx + bw * piso - 1, y + linhaH / 2 - 6, 2, 12);
      // Decisão do sistema, separada.
      ctx.fillStyle = corDecisao;
      const rotulo = status === "ok" ? "ok" : decisao === "alerta" ? "alerta" : decisao ? decisao.replace("confirmando", "conf.") : "falta";
      ctx.fillText(rotulo, bx + bw + 8, y + linhaH / 2);
    });
  }
}
