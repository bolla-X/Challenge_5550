import { ApiError, apiFetch } from "./client";

/**
 * Feedback dentro do app e contatos da página pública /produto.
 * Contrato: app/api/feedback.py. Tudo é gravado só no servidor local.
 */

export interface ItemDeFeedback {
  id: number;
  texto: string;
  /** Só o caminho da tela de onde veio (sem query), ou null. */
  tela: string | null;
  tipo_de_conta: string;
  user_id: number | null;
  /** Nome da conta que enviou, quando ela ainda existe. */
  autor: string | null;
  criado_em: string | null;
  lido: boolean;
}

export interface ItemDeContato {
  id: number;
  nome: string;
  empresa: string | null;
  email: string;
  mensagem: string;
  consentimento: boolean;
  criado_em: string | null;
  lido: boolean;
}

export interface Caixa<T> {
  items: T[];
  count: number;
  nao_lidos: number;
}

export interface NovoContato {
  nome: string;
  empresa: string;
  email: string;
  mensagem: string;
  consentimento: boolean;
}

/** Limite de caracteres do feedback e da mensagem de contato (o servidor recusa acima disto). */
export const LIMITE_DE_TEXTO = 2000;

export const enviarFeedback = (texto: string, tela: string) =>
  apiFetch<{ feedback: ItemDeFeedback }>("/api/feedback", { method: "POST", body: JSON.stringify({ texto, tela }) });

export const listarFeedback = () => apiFetch<Caixa<ItemDeFeedback>>("/api/feedback?limit=200");

export const marcarFeedbackLido = (id: number, lido = true) =>
  apiFetch<{ feedback: ItemDeFeedback }>(`/api/feedback/${id}/lido`, { method: "POST", body: JSON.stringify({ lido }) });

export const enviarContato = (contato: NovoContato) =>
  apiFetch<{ ok: true }>("/api/contatos", { method: "POST", body: JSON.stringify(contato) });

export const listarContatos = () => apiFetch<Caixa<ItemDeContato>>("/api/contatos?limit=200");

export const marcarContatoLido = (id: number, lido = true) =>
  apiFetch<{ contato: ItemDeContato }>(`/api/contatos/${id}/lido`, { method: "POST", body: JSON.stringify({ lido }) });

/** Campo que o servidor apontou num 400 de validação (`campo` no corpo), se houver. */
export function campoDoErro(err: unknown): string | null {
  if (!(err instanceof ApiError) || !err.body || typeof err.body !== "object") return null;
  const campo = (err.body as { campo?: unknown }).campo;
  return typeof campo === "string" ? campo : null;
}
