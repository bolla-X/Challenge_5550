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

/** Uma linha: "Sem capacete · Zona A · Pessoas 4, 7, 9". */
export function rotuloDoIncidente(inc: Incidente): string {
  return [inc.titulo, zonaDoIncidente(inc), pessoasDoIncidente(inc)].filter(Boolean).join(" · ");
}
