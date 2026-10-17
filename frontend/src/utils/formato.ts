const LOCALE = "pt-BR";

/** Número com vírgula decimal (pt-BR), com exatamente `casas` casas: 1234,5 → "1.234,5". */
export function decimal(valor: number, casas = 1): string {
  return valor.toLocaleString(LOCALE, { minimumFractionDigits: casas, maximumFractionDigits: casas });
}

/** Inteiro com separador de milhar (pt-BR). */
export function inteiro(valor: number): string {
  return valor.toLocaleString(LOCALE, { maximumFractionDigits: 0 });
}

/**
 * Contagem com o substantivo no número certo: "1 alerta", "3 alertas".
 * Para plurais irregulares passe o plural: pluralizar(2, "missão", "missões").
 */
export function pluralizar(n: number, singular: string, plural = `${singular}s`): string {
  return `${inteiro(n)} ${n === 1 ? singular : plural}`;
}
