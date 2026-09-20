const TEM_FUSO = /Z$|[+-]\d\d:\d\d$/;

/**
 * Converte o ISO que o backend devolve em Date, no instante certo.
 *
 * O backend grava UTC (utc_now em app/models.py) mas o SQLite devolve o
 * datetime naive na leitura, e o isoformat() sai sem sufixo de fuso (ex.:
 * "2026-08-06T16:54:47.491761"). Sem acrescentar "Z", o Date() do JS lê
 * esse valor como horário LOCAL e desloca tudo pelo fuso da máquina.
 * Um valor que já traz fuso ("Z" ou "+00:00") passa intacto.
 *
 * Sem valor, devolve agora: é o que todos os pontos de chamada faziam.
 * Conferido em tests/test_serializer_datas_naive.py.
 */
export function paraDate(valor: string | null | undefined): Date {
  if (!valor) return new Date();
  return new Date(TEM_FUSO.test(valor) ? valor : `${valor}Z`);
}
