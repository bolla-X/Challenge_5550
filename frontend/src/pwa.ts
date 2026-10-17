import type { Alert } from "./api/types";
import type { EventoDeEscalonamento } from "./socket/events";

/**
 * PWA do supervisor (X10): service worker da casca offline e aviso local de
 * alerta crítico com o app ABERTO (notificação do sistema + vibração).
 *
 * Service worker e notificações só existem em contexto seguro (HTTPS ou
 * localhost) — MDN: https://developer.mozilla.org/en-US/docs/Web/API/Service_Worker_API
 * e https://developer.mozilla.org/en-US/docs/Web/API/Notifications_API. No
 * celular o `new Notification()` lança TypeError; por isso a notificação sai
 * pelo service worker (`registration.showNotification`).
 *
 * Push com o app FECHADO não entra: exigiria um serviço de push externo.
 */

let registro: ServiceWorkerRegistration | null = null;
let ultimaNotificacao = 0;

export function registrarServiceWorker(): void {
  if (!("serviceWorker" in navigator) || !window.isSecureContext) return;
  navigator.serviceWorker
    .register("/sw.js", { scope: "/" })
    .then((r) => {
      registro = r;
    })
    .catch((e) => console.warn("[pwa] service worker não registrado", e));
}

export function notificacoesSuportadas(): boolean {
  return "Notification" in window && window.isSecureContext;
}

export function permissaoDeNotificacao(): NotificationPermission | "indisponivel" {
  return notificacoesSuportadas() ? Notification.permission : "indisponivel";
}

/** Só a partir de um clique (a MDN pede gesto do usuário). */
export async function pedirPermissao(): Promise<NotificationPermission | "indisponivel"> {
  if (!notificacoesSuportadas()) return "indisponivel";
  return Notification.requestPermission();
}

/** Alerta crítico com o app aberto: vibra e mostra UMA notificação por incidente (troca, não empilha). */
export function avisarAlertaCritico(alerta: Alert, nomeDaCamera?: string): boolean {
  if (alerta.severity !== "critical") return false;
  const agora = Date.now();
  if (agora - ultimaNotificacao < 8000) return false;
  ultimaNotificacao = agora;
  // O Chromium bloqueia vibrate() sem um toque prévio do usuário na página
  // (ativação de usuário "pegajosa") e registra erro no console — visto no
  // crawler da MISSÃO 4. Ver CHANGELOG (MDN Navigator.vibrate).
  const tocou = (navigator as Navigator & { userActivation?: { hasBeenActive: boolean } }).userActivation?.hasBeenActive ?? true;
  if ("vibrate" in navigator && tocou) navigator.vibrate([200, 100, 200]);
  const incidente = (alerta.metadata || {}).incidente_id;
  const titulo = `Alerta crítico${nomeDaCamera ? ` · ${nomeDaCamera}` : ""}`;
  return mostrarNotificacao(titulo, {
    body: alerta.message.split(/ [·—] /)[0],
    tag: incidente ? `incidente-${incidente}` : `alerta-${alerta.id}`,
    icon: "/static/dist/icons/icone-192.png",
    badge: "/static/dist/icons/icone-192.png",
  });
}

/**
 * Escalonamento nível 1 (M7): o alerta crítico ficou sem reconhecimento além do prazo.
 * Mesma notificação local do alerta crítico, sem o limite de 8 s (é raro e é o que importa),
 * com tag própria por alerta: o aviso do escalonamento troca, não empilha.
 */
export function avisarEscalonamento(evento: EventoDeEscalonamento, nomeDaCamera?: string): boolean {
  if (evento.nivel !== 1) return false;
  const tocou = (navigator as Navigator & { userActivation?: { hasBeenActive: boolean } }).userActivation?.hasBeenActive ?? true;
  if ("vibrate" in navigator && tocou) navigator.vibrate([300, 100, 300, 100, 300]);
  const minutos = Math.max(1, Math.round(evento.segundos_sem_reconhecer / 60));
  return mostrarNotificacao(`Sem reconhecimento há ${minutos} min${nomeDaCamera ? ` · ${nomeDaCamera}` : ""}`, {
    body: (evento.mensagem ?? "Alerta crítico").split(/ [·—] /)[0],
    tag: `escalonamento-${evento.alerta_id}`,
    icon: "/static/dist/icons/icone-192.png",
    badge: "/static/dist/icons/icone-192.png",
  });
}

function mostrarNotificacao(titulo: string, opcoes: NotificationOptions): boolean {
  if (permissaoDeNotificacao() !== "granted") return false;
  // Contador lido pelo E2E (o headless não mostra a notificação na tela).
  const w = window as unknown as { __visionepiNotificacoes?: number };
  w.__visionepiNotificacoes = (w.__visionepiNotificacoes ?? 0) + 1;
  if (registro) {
    registro.showNotification(titulo, opcoes).catch(() => undefined);
  } else {
    try {
      new Notification(titulo, opcoes);
    } catch {
      return false;
    }
  }
  return true;
}
