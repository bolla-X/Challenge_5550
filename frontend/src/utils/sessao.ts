/**
 * Endereço de retorno da sessão expirada: guardado quando o servidor responde
 * 401 com a pessoa logada, usado depois do login para voltar de onde parou.
 *
 * sessionStorage (e não localStorage): vale só para esta aba e some ao fechá-la,
 * então um terminal compartilhado não carrega o destino de uma pessoa para a
 * próxima. try/catch porque o armazenamento lança em janela privada.
 */
const CHAVE_DE_RETORNO = "visionepi-retorno";

/** Evento global disparado por `api/client.ts` quando uma chamada autenticada devolve 401. */
export const EVENTO_SESSAO_EXPIRADA = "visionepi:sessao-expirada";

/** Rota atual como o navegador a vê: caminho, busca e âncora. */
export function rotaAtual(): string {
  const { pathname, search, hash } = window.location;
  return `${pathname}${search}${hash}`;
}

/** Só caminho do próprio app: começa com uma barra e não vira outro site ("//x", "/\x"). */
function eRotaInterna(valor: string): boolean {
  return valor.startsWith("/") && !valor.startsWith("//") && !valor.startsWith("/\\");
}

/** Guarda a rota atual como destino de retorno (o último guardado vale). */
export function guardarRetorno(): void {
  try {
    sessionStorage.setItem(CHAVE_DE_RETORNO, rotaAtual());
  } catch {
    // sessionStorage indisponível: a pessoa volta pelo início, só isso.
  }
}

/** Devolve o destino guardado (e o apaga). `null` se não há, ou se não é um caminho interno. */
export function consumirRetorno(): string | null {
  try {
    const valor = sessionStorage.getItem(CHAVE_DE_RETORNO);
    sessionStorage.removeItem(CHAVE_DE_RETORNO);
    return valor && eRotaInterna(valor) ? valor : null;
  } catch {
    return null;
  }
}
