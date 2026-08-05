import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev: Vite proxies everything to Flask on :5000 so the browser sees one
// origin and we never need CORS (per approved plan, question 3).
// Prod: Flask serves this build's output directly from app/static/dist
// (per approved plan, question 1) — outDir points straight there.
const FLASK_TARGET = "http://localhost:5000";

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
