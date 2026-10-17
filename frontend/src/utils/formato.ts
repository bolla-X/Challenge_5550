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

/** Tamanho em bytes (base 1024) com vírgula decimal e unidade separada: 1536 → "1,5 KB", 5 GiB → "5,0 GB". */
export function bytesLegiveis(bytes: number): string {
  const unidades = ["B", "KB", "MB", "GB", "TB"];
  let valor = Math.max(0, bytes);
  let i = 0;
  while (valor >= 1024 && i < unidades.length - 1) {
    valor /= 1024;
    i += 1;
  }
  return `${i === 0 ? inteiro(valor) : decimal(valor, valor >= 100 ? 0 : 1)} ${unidades[i]}`;
}
