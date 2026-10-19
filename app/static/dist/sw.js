/*
 * Service worker do VisionEPI (X10): só a "casca" do app offline.
 *
 * - Navegação (HTML): rede primeiro; sem rede, a última casca guardada, para o
 *   app abrir e mostrar "sem conexão" em vez da página de erro do navegador.
 * - /static/dist/ (JS, CSS, fontes, ícones, nomes com hash): cache primeiro.
 * - /api/*, vídeo, socket e qualquer outra coisa: NUNCA em cache — dado de
 *   segurança velho é pior que dado nenhum.
 *
 * Offline (Missão 4, Fase 3 item 9): a navegação que falha sem rede recebe a
 * casca guardada para QUALQUER endereço de página (o app lê o caminho e monta a
 * tela certa) e o app mostra a faixa "sem conexão". Endereços de API, arquivos e
 * tempo real não recebem a casca: para eles o erro do navegador é a resposta
 * honesta. Só HTML vira a casca guardada (uma navegação para JSON não a sobrescreve).
 *
 * Push com o app fechado NÃO existe aqui: exigiria um serviço de push externo
 * (Web Push). Ver docs/NEXT2026/CHANGELOG.md (X10).
 *
 * Referência: MDN, Service Worker API (contexto seguro; `http://localhost` conta
 * como seguro): https://developer.mozilla.org/en-US/docs/Web/API/Service_Worker_API
 */
const VERSAO = "visionepi-casca-v2";

// Mesma lista de prefixos que o servidor não trata como "página" (app/api/status.py).
const SEM_CASCA = /^\/(api|static|socket\.io|snapshots|alerts|events|relatorio)(\/|$)/;

self.addEventListener("install", (evento) => {
  evento.waitUntil(caches.open(VERSAO).then((c) => c.addAll(["/"])).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (evento) => {
  evento.waitUntil(
    caches
      .keys()
      .then((nomes) => Promise.all(nomes.filter((n) => n !== VERSAO).map((n) => caches.delete(n))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (evento) => {
  const req = evento.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (req.mode === "navigate") {
    const ehPagina = !SEM_CASCA.test(url.pathname);
    evento.respondWith(
      fetch(req)
        .then((resp) => {
          const html = (resp.headers.get("content-type") || "").includes("text/html");
          if (resp.ok && html && ehPagina) {
            const copia = resp.clone();
            caches.open(VERSAO).then((c) => c.put("/", copia));
          }
          return resp;
        })
        .catch(() =>
          ehPagina
            ? caches.match("/").then((casca) => casca || Response.error())
            : Response.error(),
        ),
    );
    return;
  }
  if (url.pathname.startsWith("/static/dist/")) {
    evento.respondWith(
      caches.match(req).then(
        (guardado) =>
          guardado ||
          fetch(req).then((resp) => {
            if (resp.ok) {
              const copia = resp.clone();
              caches.open(VERSAO).then((c) => c.put(req, copia));
            }
            return resp;
          }),
      ),
    );
  }
});

// Clique na notificação de alerta crítico: traz o app para a frente.
self.addEventListener("notificationclick", (evento) => {
  evento.notification.close();
  evento.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((janelas) => {
      const aberta = janelas.find((j) => "focus" in j);
      return aberta ? aberta.focus() : self.clients.openWindow("/");
    }),
  );
});
