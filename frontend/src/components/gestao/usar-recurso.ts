import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "../../api/client";
import { mensagemDeErro } from "../../utils/erros";

/**
 * GET de um recurso da Gestão. Mantém o dado anterior enquanto a URL muda (filtro novo não pisca o skeleton) e
 * descarta a resposta de uma URL que já não é a atual. `recarregar` repete a chamada (botão "Tentar de novo").
 */
export function usarRecurso<T>(url: string, mensagemPadrao = "Não foi possível carregar os dados.") {
  const [dados, setDados] = useState<T | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [tentativa, setTentativa] = useState(0);

  useEffect(() => {
    let vivo = true;
    setErro(null);
    apiFetch<T>(url)
      .then((d) => vivo && setDados(d))
      .catch((e) => {
        if (!vivo) return;
        setDados(null);
        setErro(mensagemDeErro(e, mensagemPadrao));
      });
    return () => {
      vivo = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url, tentativa]);

  const recarregar = useCallback(() => setTentativa((t) => t + 1), []);
  return { dados, erro, carregando: dados === null && erro === null, recarregar };
}
