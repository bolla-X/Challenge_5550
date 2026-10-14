import type { Alert } from "./api/types";

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
  if ("vibrate" in navigator) navigator.vibrate([200, 100, 200]);
  if (permissaoDeNotificacao() !== "granted") return false;
  const incidente = (alerta.metadata || {}).incidente_id;
  const titulo = `Alerta crítico${nomeDaCamera ? ` · ${nomeDaCamera}` : ""}`;
  const opcoes: NotificationOptions = {
    body: alerta.message.split(/ [·—] /)[0],
    tag: incidente ? `incidente-${incidente}` : `alerta-${alerta.id}`,
    icon: "/static/dist/icons/icone-192.png",
    badge: "/static/dist/icons/icone-192.png",
  };
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
