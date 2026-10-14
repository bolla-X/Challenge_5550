import type { Incidente } from "../api/types";

/** IDs de rastreio do incidente (os ativos, quando o servidor manda). Nunca identidade. */
export function idsDoIncidente(inc: Incidente): (number | string)[] {
  return inc.pessoas_ativas ?? inc.pessoas ?? [];
}

/** "Pessoa 4" · "Pessoas 4, 7, 9" · "Pessoas 4, 7, 9 +3" · "" (sinal global, sem pessoa). */
export function pessoasDoIncidente(inc: Incidente, maximo = 4): string {
  const ids = idsDoIncidente(inc);
  if (!ids.length) return "";
  if (ids.length === 1) return `Pessoa ${ids[0]}`;
  const mostrados = ids.slice(0, maximo).join(", ");
  return `Pessoas ${mostrados}${ids.length > maximo ? ` +${ids.length - maximo}` : ""}`;
}

/** Zona só quando diz algo ("Toda a câmera" é o padrão sem zona desenhada). */
export function zonaDoIncidente(inc: Incidente): string | null {
  return inc.zona && inc.zona !== "Toda a câmera" ? inc.zona : null;
}

/** Uma frase: "Sem capacete na Zona A: Pessoas 4, 7, 9" (sem lista de pontos médios). */
export function rotuloDoIncidente(inc: Incidente): string {
  const zona = zonaDoIncidente(inc);
  const onde = !zona ? "" : zona === "Fora da zona" ? " fora da zona" : inc.rule === "risk_area_presence" ? ` (${zona})` : ` na ${zona}`;
  const pessoas = pessoasDoIncidente(inc);
  return `${inc.titulo}${onde}${pessoas ? `: ${pessoas}` : ""}`;
}
