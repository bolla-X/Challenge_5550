/**
 * Alerta falado em pt-BR (G6), com a voz do próprio navegador.
 *
 * Web Speech API (MDN, lida em 13/10/2026):
 * - https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesis —
 *   `speak()` enfileira, `cancel()` esvazia a fila, `getVoices()` pode vir
 *   vazio até o evento `voiceschanged`;
 * - https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesisVoice/localService —
 *   `localService: true` = sintetizador local (funciona sem internet).
 *
 * Regras:
 * - só alerta crítico, e só se o som não estiver mudo (o mesmo `muted` do bipe);
 * - sem voz pt-BR na máquina, devolve `false` e quem chamou toca o bipe;
 * - nunca fala por cima: no máximo UMA frase esperando (a mais recente
 *   substitui a anterior), um intervalo mínimo entre frases e a mesma frase
 *   não se repete dentro de `REPETICAO_MS`.
 */

export const INTERVALO_MIN_MS = 4000;
export const REPETICAO_MS = 30_000;

type AlertaFalavel = { message: string; severity: string; camera_id?: number | null };

/** "Sem capacete — Pessoa 3" na câmera "Doca 2" → "Atenção: sem capacete, pessoa 3, na câmera Doca 2." */
export function montarFrase(alerta: AlertaFalavel, nomeDaCamera?: string | null): string {
  const partes = alerta.message.split(" — ").map((p) => p.trim()).filter(Boolean);
  const oque = (partes[0] ?? "alerta").replace(/^./, (c) => c.toLowerCase());
  const quem = partes[1] ? `, ${partes[1].replace(/^Pessoa/, "pessoa")}` : "";
  const onde = nomeDaCamera ? `, na câmera ${nomeDaCamera}` : "";
  return `Atenção: ${oque}${quem}${onde}.`;
}

function sintetizador(): SpeechSynthesis | null {
  return typeof window !== "undefined" && "speechSynthesis" in window ? window.speechSynthesis : null;
}

/** A voz pt-BR a usar: local primeiro (funciona offline), depois qualquer pt-BR. */
export function vozPtBr(): SpeechSynthesisVoice | null {
  const s = sintetizador();
  if (!s) return null;
  const vozes = s.getVoices().filter((v) => v.lang.replace("_", "-").toLowerCase().startsWith("pt-br"));
  return vozes.find((v) => v.localService) ?? vozes[0] ?? null;
}

let falandoAte = 0;
let pendente: string | null = null;
let timer: number | null = null;
const faladas = new Map<string, number>();

function falarAgora(frase: string, voz: SpeechSynthesisVoice) {
  const s = sintetizador();
  if (!s) return;
  const u = new SpeechSynthesisUtterance(frase);
  u.voice = voz;
  u.lang = voz.lang;
  u.rate = 1.05;
  faladas.set(frase, Date.now());
  falandoAte = Date.now() + INTERVALO_MIN_MS;
  // O intervalo mínimo conta do INÍCIO da frase; terminar antes não o encurta.
  u.onend = () => agendar();
  s.speak(u);
}

function agendar() {
  if (timer != null || pendente == null) return;
  const espera = Math.max(0, falandoAte - Date.now());
  timer = window.setTimeout(() => {
    timer = null;
    const s = sintetizador();
    const voz = vozPtBr();
    if (!s || !voz || pendente == null) return;
    if (s.speaking) {
      falandoAte = Date.now() + 500;
      agendar();
      return;
    }
    const frase = pendente;
    pendente = null;
    falarAgora(frase, voz);
  }, espera);
}

/**
 * Fala o alerta (ou o coloca na vez). `false` = não há voz pt-BR: toque o bipe.
 * Alerta não crítico devolve `true` sem falar — o bipe dele segue a regra de sempre.
 */
export function falarAlerta(alerta: AlertaFalavel, nomeDaCamera?: string | null): boolean {
  if (alerta.severity !== "critical") return true;
  const voz = vozPtBr();
  if (!voz) return false;
  const frase = montarFrase(alerta, nomeDaCamera);
  const ultima = faladas.get(frase);
  if (ultima != null && Date.now() - ultima < REPETICAO_MS) return true;
  for (const [f, t] of faladas) if (Date.now() - t > REPETICAO_MS) faladas.delete(f);
  pendente = frase; // a mais recente substitui a que esperava
  agendar();
  return true;
}

/** Mudo no meio da fala: para já e esquece o que esperava. */
export function calarFala() {
  pendente = null;
  if (timer != null) {
    window.clearTimeout(timer);
    timer = null;
  }
  sintetizador()?.cancel();
}

// A lista de vozes chega assíncrona em alguns navegadores (MDN: `voiceschanged`).
sintetizador()?.addEventListener?.("voiceschanged", () => void 0);
