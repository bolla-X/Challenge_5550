/**
 * Texto de erro que o usuário lê. O `fetch` do navegador rejeita com um
 * TypeError cuja mensagem nativa vem em inglês ("Failed to fetch"); aqui ela
 * vira português. Erro que já traz texto (do servidor ou escrito pela tela)
 * passa como veio.
 */
export function mensagemDeErro(err: unknown, padrao: string): string {
  if (err instanceof TypeError) return "Sem conexão com o servidor.";
  return err instanceof Error && err.message ? err.message : padrao;
}
