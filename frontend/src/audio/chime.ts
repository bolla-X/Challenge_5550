/**
 * Sintetizado via Web Audio API — sem lib, sem samples. Dois sons só:
 * alerta crítico entrando (interrompe, curto) e "voltou tudo certo"
 * (resolutivo, um pouco mais longo). Qualquer outro evento (alert_updated,
 * settings salvas, etc.) não passa por aqui de propósito — som em toda
 * ação viraria ruído numa sala cheia.
 */
let ctx: AudioContext | null = null;

function getCtx(): AudioContext | null {
  if (typeof window === "undefined") return null;
  const Ctor = window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!Ctor) return null;
  if (!ctx) ctx = new Ctor();
  if (ctx.state === "suspended") ctx.resume().catch(() => {});
  return ctx;
}

function tone(freq: number, startOffset: number, duration: number, peakGain: number) {
  const audioCtx = getCtx();
  if (!audioCtx) return;
  const osc = audioCtx.createOscillator();
  const gain = audioCtx.createGain();
  osc.type = "sine";
  osc.frequency.value = freq;
  const start = audioCtx.currentTime + startOffset;
  const end = start + duration;
  gain.gain.setValueAtTime(0, start);
  gain.gain.linearRampToValueAtTime(peakGain, start + 0.015);
  gain.gain.exponentialRampToValueAtTime(0.0001, end);
  osc.connect(gain);
  gain.connect(audioCtx.destination);
  osc.start(start);
  osc.stop(end + 0.02);
}

/** Alerta crítico/alto criado: um bipe curto e seco, dois tons descendo. */
export function playAlertChime() {
  tone(880, 0, 0.09, 0.09);
  tone(660, 0.09, 0.11, 0.08);
}

/** Voltou a "tudo certo" depois de ter tido alerta ativo: tom subindo, mais suave. */
export function playAllClearChime() {
  tone(523, 0, 0.12, 0.05);
  tone(784, 0.1, 0.18, 0.06);
}
