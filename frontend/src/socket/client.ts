import { io, type Socket } from "socket.io-client";
import type { ServerEvents } from "./events";

// Client -> server: quase tudo vai por REST. A exceção é `revalidate`, que o
// cliente dispara periodicamente para o servidor reconferir a sessão daquele
// socket — sem isso, um socket aberto sobreviveria à revogação do acesso.
type ClientEvents = {
  revalidate: () => void;
  // Câmera aberta na tela: o servidor só manda a telemetria de alta
  // frequência (analysis, compliance_state) para quem a está vendo.
  focar: (payload: { camera_id: number }) => void;
};

// Same-origin socket: Vite proxies /socket.io to Flask in dev (vite.config.ts),
// Flask serves both in prod. No URL/CORS config needed either way.
//
// transports: ["polling"] is deliberate, not a default. Vite's dev-server
// websocket-upgrade proxy resets the connection against Flask's threading
// dev server (verified: direct-to-Flask polling delivers every event
// correctly, proxied websocket-upgrade tears the session down with
// ECONNRESET). Polling is plenty for this app's ~12 FPS analysis rate.
// Revisit if a real WSGI/ASGI server (gunicorn+eventlet, etc.) replaces the
// Werkzeug dev server in prod.
//
// autoConnect: false — quem conecta é subscribeToServerEvents, depois que a
// sessão é conhecida. Conectando no carregamento do módulo, a tela de login
// abria um socket que o servidor rejeitava (socket_rejected_unauthenticated,
// ~37 por rodada de E2E) e o poll seguinte daquele sid voltava 400 no console.
export const socket: Socket<ServerEvents, ClientEvents> = io({ autoConnect: false, transports: ["polling"] });
