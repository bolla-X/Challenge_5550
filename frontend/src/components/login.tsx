import { useState } from "react";
import { useDashboardStore } from "../store/dashboardStore";

/**
 * Tela de entrada. Só aparece quando `GET /api/auth/me` responde `user: null`.
 *
 * Não existe "criar conta": num sistema de segurança do trabalho quem cria
 * acesso é quem já tem acesso (supervisor pela tela de usuários, ou
 * `flask users create` na primeira instalação).
 */
export function LoginScreen() {
  const login = useDashboardStore((s) => s.login);
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  const enviar = (evento: React.FormEvent) => {
    evento.preventDefault();
    setErro(null);
    setEnviando(true);
    login(email, senha)
      .catch((err) => setErro(err instanceof Error ? err.message : "Não foi possível entrar."))
      .finally(() => setEnviando(false));
  };

  return (
    <div className="login-shell">
      <form className="login-card" onSubmit={enviar}>
        <h1>VisionEPI</h1>
        <p className="login-sub">Monitoramento de segurança industrial</p>

        <label>
          E-mail
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="username"
            autoFocus
            required
          />
        </label>

        <label>
          Senha
          <input
            type="password"
            value={senha}
            onChange={(e) => setSenha(e.target.value)}
            autoComplete="current-password"
            required
          />
        </label>

        {/* role="alert" para leitor de tela anunciar a falha sem precisar
            navegar até o texto. */}
        {erro && (
          <p className="login-erro" role="alert">
            {erro}
          </p>
        )}

        <button type="submit" disabled={enviando || !email || !senha}>
          {enviando ? "Entrando…" : "Entrar"}
        </button>

        <p className="login-ajuda">
          Sem acesso? Peça ao responsável pela segurança do trabalho — não há cadastro público.
        </p>
      </form>
    </div>
  );
}
