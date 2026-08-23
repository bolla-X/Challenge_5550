import { io, type Socket } from "socket.io-client";
import type { ServerEvents } from "./events";

// Client -> server events: this app only ever emits via REST, never over the
// socket itself, so the emit side of the typed contract is empty.
type ClientEvents = Record<string, never>;

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
export const socket: Socket<ServerEvents, ClientEvents> = io({ autoConnect: true, transports: ["polling"] });
