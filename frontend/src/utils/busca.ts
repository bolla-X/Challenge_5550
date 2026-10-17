/**
 * Busca por texto do app (central de ajuda e paleta de comandos): sem acento e
 * sem diferenciar maiúsculas. "Câmera", "camera" e "CÂMERA" são a mesma palavra.
 */

/** Minúsculas e sem acento. */
export function normalizar(texto: string): string {
  return texto
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .trim();
}

/** Palavras da consulta, já normalizadas. Consulta vazia: nenhuma palavra. */
export function termosDa(consulta: string): string[] {
  return normalizar(consulta).split(/\s+/).filter(Boolean);
}

/** Todas as palavras aparecem no texto, em qualquer ordem. Sem palavras, casa com tudo. */
export function contemTodos(texto: string, termos: string[]): boolean {
  if (!termos.length) return true;
  const alvo = normalizar(texto);
  return termos.every((termo) => alvo.includes(termo));
}

/**
 * "pessoa 12", "Pessoa12", "id 12", "rastreio 12" ou "#12" → 12. Número solto
 * ("12") não conta: seria ambíguo com busca por qualquer outro texto.
 */
export function idDeRastreio(consulta: string): number | null {
  const m = /^(?:(?:pessoas?|id|rastreio)\s*#?\s*|#\s*)(\d{1,6})$/.exec(normalizar(consulta));
  return m ? Number(m[1]) : null;
}
