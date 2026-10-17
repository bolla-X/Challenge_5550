import { Component, useEffect, useState } from "react";
import type { ErrorInfo, ReactNode } from "react";
import { ApiError } from "../api/client";
import type { UserRole } from "../api/types";
import { useDashboardStore } from "../store/dashboardStore";
import { ROTULO_DO_PAPEL } from "./layout";
import {
  IlustracaoCadeado,
  IlustracaoCaminhoPerdido,
  IlustracaoSemSinal,
  IlustracaoSessao,
  IlustracaoTelaComFalha,
} from "./ilustracoes";
import "../styles/excecoes.css";

/**
 * Páginas de exceção: cada uma com ilustração, um título, uma frase e UMA ação.
 * Tom e termos do docs/NEXT2026/GLOSSARIO.md.
 *
 * Como ligar no App.tsx: `ErroDoServidor` envolve o app inteiro (em main.tsx ou
 * no retorno de App), `SemConexao` entra uma vez em qualquer ponto sempre
 * montado, `PaginaNaoEncontrada` cobre o endereço que nenhuma tela conhece e
 * `AcessoNegado` entra no lugar da tela quando a API devolve 403.
 */

const ACAO_PRIMARIA = "button primary";
const ACAO_SECUNDARIA = "button ghost";

// ---- 404 -------------------------------------------------------------------

/** Endereço que nenhuma tela do app conhece. Mostra o que foi pedido. */
export function PaginaNaoEncontrada({ endereco }: { endereco?: string }) {
  const pedido = endereco ?? `${window.location.pathname}${window.location.search}`;
  return (
    <div className="excecao">
      <IlustracaoCaminhoPerdido />
      <h1>Esta página não existe</h1>
      <p>O endereço pode ter sido digitado errado, ou a tela mudou de lugar.</p>
      <code className="excecao-endereco">{pedido}</code>
      <div className="excecao-acoes">
        <a className={ACAO_PRIMARIA} href="/">
          Voltar ao início
        </a>
      </div>
    </div>
  );
}

// ---- erro de renderização --------------------------------------------------

function TelaDeFalha() {
  return (
    <main id="conteudo">
      <div className="excecao tela-cheia" role="alert">
        <IlustracaoTelaComFalha />
        <h1>Algo deu errado nesta tela</h1>
        <p>A tela não conseguiu ser desenhada. O que já foi registrado continua guardado. Recarregue para tentar de novo.</p>
        <div className="excecao-acoes">
          <button type="button" className="primary" onClick={() => window.location.reload()}>
            Recarregar
          </button>
          <a className={ACAO_SECUNDARIA} href="/">
            Voltar ao início
          </a>
        </div>
      </div>
    </main>
  );
}

/**
 * Captura erro de renderização da árvore abaixo e mostra a tela de falha no
 * lugar de uma página em branco. Registra no console uma única vez: é erro real
 * (também cobre o pacote de uma tela que não carregou depois de uma atualização).
 * Erro em evento ou em promessa não passa por aqui: esses o código trata.
 */
export class ErroDoServidor extends Component<{ children?: ReactNode }, { falhou: boolean }> {
  state = { falhou: false };
  private registrado = false;

  static getDerivedStateFromError() {
    return { falhou: true };
  }

  componentDidCatch(erro: Error, info: ErrorInfo) {
    if (this.registrado) return;
    this.registrado = true;
    console.error("[ErroDoServidor] erro ao desenhar a tela", erro, info.componentStack);
  }

  render() {
    return this.state.falhou ? <TelaDeFalha /> : this.props.children;
  }
}

// ---- sem conexão -----------------------------------------------------------

/** Socket caído por mais que isto vira aviso; menos que isso é só a reconexão normal. */
const ESPERA_DO_SOCKET_MS = 5000;

/**
 * Faixa discreta de "sem conexão". Aparece quando o navegador diz que está sem
 * rede OU quando o socket (só com alguém logado) fica desconectado por mais de
 * 5 s, e some sozinha ao voltar. A região `role="status"` fica sempre montada:
 * leitor de tela só anuncia mudança em região que já existia.
 */
export function SemConexao() {
  const conectado = useDashboardStore((s) => s.connected);
  const logado = useDashboardStore((s) => s.user !== null);
  const [online, setOnline] = useState(() => typeof navigator === "undefined" || navigator.onLine !== false);
  const [socketCaiu, setSocketCaiu] = useState(false);

  useEffect(() => {
    const aoMudar = () => setOnline(navigator.onLine !== false);
    window.addEventListener("online", aoMudar);
    window.addEventListener("offline", aoMudar);
    aoMudar();
    return () => {
      window.removeEventListener("online", aoMudar);
      window.removeEventListener("offline", aoMudar);
    };
  }, []);

  useEffect(() => {
    if (!logado || conectado) {
      setSocketCaiu(false);
      return undefined;
    }
    const espera = window.setTimeout(() => setSocketCaiu(true), ESPERA_DO_SOCKET_MS);
    return () => window.clearTimeout(espera);
  }, [logado, conectado]);

  const mensagem = !online
    ? "Este aparelho está sem rede. Tentando reconectar…"
    : socketCaiu
      ? "Sem conexão com o servidor. Tentando reconectar…"
      : null;

  return (
    <div className="sem-conexao" role="status" aria-live="polite" data-testid="sem-conexao">
      {mensagem && (
        <div className="sem-conexao-faixa">
          <IlustracaoSemSinal />
          <span>{mensagem}</span>
        </div>
      )}
    </div>
  );
}

// ---- sessão expirada -------------------------------------------------------

/** Aviso da tela de login quando a sessão acabou no meio do uso. */
export function SessaoExpirada() {
  return (
    <p className="sessao-expirada" role="status" data-testid="sessao-expirada">
      <IlustracaoSessao />
      <span>Sua sessão expirou. Entre de novo para continuar de onde parou.</span>
    </p>
  );
}

// ---- acesso negado ---------------------------------------------------------

/** Papel mínimo que a API exigiu (`required_role` do 403), ou `undefined` se o erro não for esse. */
export function papelExigidoDe(erro: unknown): UserRole | undefined {
  if (!(erro instanceof ApiError) || erro.status !== 403) return undefined;
  const corpo = erro.body;
  if (!corpo || typeof corpo !== "object" || !("required_role" in corpo)) return undefined;
  const papel = String((corpo as { required_role: unknown }).required_role);
  return rotuloDoPapel(papel) ? (papel as UserRole) : undefined;
}

/** Rótulo em português do tipo de conta; `undefined` para chave que não é um papel. */
function rotuloDoPapel(papel: string | undefined): string | undefined {
  return papel && Object.prototype.hasOwnProperty.call(ROTULO_DO_PAPEL, papel) ? ROTULO_DO_PAPEL[papel] : undefined;
}

/**
 * Tela que a conta atual não pode abrir. `papelExigido` é o MÍNIMO (os papéis
 * são hierárquicos: Supervisor abre o que o Técnico abre); `recurso` é o nome da
 * tela, em português ("o Editor de regras").
 */
export function AcessoNegado({ papelExigido, recurso }: { papelExigido?: string; recurso?: string }) {
  const user = useDashboardStore((s) => s.user);
  const exigido = rotuloDoPapel(papelExigido);
  const alvo = recurso ?? "esta tela";
  const quem =
    papelExigido === "supervisor"
      ? `Só contas do tipo Supervisor abrem ${alvo}.`
      : exigido
        ? `Contas do tipo ${exigido} e Supervisor abrem ${alvo}.`
        : `O tipo da sua conta não abre ${alvo}.`;
  const seu = user ? ` Sua conta é do tipo ${rotuloDoPapel(user.role) ?? user.role}.` : "";
  return (
    <div className="excecao" role="alert">
      <IlustracaoCadeado />
      <h1>{exigido ? `Esta tela é para ${exigido}` : "Esta tela é para outro tipo de conta"}</h1>
      <p>
        {quem}
        {seu} Se você precisa dela, peça a quem administra as contas.
      </p>
      <div className="excecao-acoes">
        <a className={ACAO_PRIMARIA} href="/">
          Voltar ao início
        </a>
      </div>
    </div>
  );
}
