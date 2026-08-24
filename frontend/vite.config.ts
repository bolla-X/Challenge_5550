import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev: Vite proxies everything to Flask so the browser sees one origin and
// we never need CORS (per approved plan, question 3).
// Prod: Flask serves this build's output directly from app/static/dist
// (per approved plan, question 1) — outDir points straight there.
//
// A porta tem que bater com Config.PORT (app/config.py) / .env PORT — é a
// mesma que Dockerfile, docker-compose e README usam.
const FLASK_PORT = process.env.PORT ?? "5000";
const FLASK_TARGET = `http://localhost:${FLASK_PORT}`;

export default defineConfig({
  plugins: [react()],
  // Flask's default static_folder ("static") already serves anything under
  // app/static/, including app/static/dist/ once built — so base must match
  // where Flask will actually expose these assets. No Flask static_folder
  // change needed at all; only app/api/status.py's index() route changes,
  // to send this build's index.html instead of the old Jinja template.
  base: "/static/dist/",
  server: {
    port: 5173,
    proxy: {
      "/socket.io": { target: FLASK_TARGET, ws: true, changeOrigin: true },
      "/video_feed": { target: FLASK_TARGET, changeOrigin: true },
      // /api/cameras/*/video_feed também é stream MJPEG — changeOrigin
      // igual ao /video_feed acima, senão a imagem nunca chega a carregar.
      "/api": { target: FLASK_TARGET, changeOrigin: true },
      "/status": FLASK_TARGET,
      "/preflight": FLASK_TARGET,
      "/start": FLASK_TARGET,
      "/stop": FLASK_TARGET,
      "/features": FLASK_TARGET,
      "/alerts": FLASK_TARGET,
      "/model": FLASK_TARGET,
      "/settings": FLASK_TARGET,
      "/overlay": FLASK_TARGET,
      "/risk-area": FLASK_TARGET,
      "/risk-score": FLASK_TARGET,
      "/events": FLASK_TARGET,
      "/snapshots": FLASK_TARGET,
      "/analysis": FLASK_TARGET,
    },
  },
  build: {
    outDir: "../app/static/dist",
    emptyOutDir: true,
  },
});
