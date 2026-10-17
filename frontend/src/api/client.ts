// Same-origin in both dev (Vite proxy) and prod (Flask serves the build),
// so no base URL / CORS config is needed. See vite.config.ts for the proxy.
import { EVENTO_SESSAO_EXPIRADA } from "../utils/sessao";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public body: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

// 401 nestas rotas é a resposta normal de "credencial errada" ou "ninguém logado",
// não uma sessão que expirou.
const ROTAS_SEM_AVISO_DE_SESSAO = ["/api/auth/login", "/api/auth/me", "/api/auth/logout"];

/**
 * Uma chamada autenticada devolveu 401: avisa o app (que decide se havia alguém
 * logado). Exportada para o `fetch` direto que ainda existe em algumas telas.
 */
export function avisarSeSessaoExpirou(path: string, status: number): void {
  if (status !== 401 || typeof window === "undefined") return;
  const rota = path.split("?")[0];
  if (ROTAS_SEM_AVISO_DE_SESSAO.includes(rota)) return;
  window.dispatchEvent(new CustomEvent(EVENTO_SESSAO_EXPIRADA));
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  let corpoInterrompido = false;
  const body = await res.json().catch(() => {
    corpoInterrompido = true;
    return null;
  });
  // Resposta 2xx sem JSON legível: a leitura foi cortada (navegação, conexão
  // caiu). Trata como falha de rede, que quem chama já sabe repetir.
  if (res.ok && corpoInterrompido && res.status !== 204) throw new TypeError("Failed to fetch (corpo interrompido)");
  if (!res.ok) {
    avisarSeSessaoExpirou(path, res.status);
    const message = (body && typeof body === "object" && "error" in body && String((body as { error: unknown }).error)) || `Falha na comunicação com o servidor (código ${res.status}).`;
    throw new ApiError(message, res.status, body);
  }
  return body as T;
}
