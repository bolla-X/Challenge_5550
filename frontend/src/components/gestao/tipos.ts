import { ApiError } from "../../api/client";
import { PPE_KEYS, PPE_LABELS } from "../../api/ppe";
import { horaCurta, paraDate } from "../../utils/datas";

/**
 * Tipos, rótulos e formatadores da Gestão de EPIs. Contrato: docs/specs/es-sprint4-contrato-gestao.md.
 * Situações (CA, entrega) vêm calculadas do servidor; a tela só as nomeia.
 */

export type SituacaoCa = "valido" | "a_vencer" | "vencido";
export type SituacaoEntrega = "vigente" | "troca_vencida" | "devolvido";
export type StatusOcorrencia = "aberta" | "em_tratamento" | "encerrada";

export interface Resumo {
  colaboradores_ativos: number;
  epis_no_catalogo: number;
  entregas_vigentes: number;
  trocas_vencidas: number;
  cas_vencidos: number;
  cas_a_vencer: number;
  ocorrencias_abertas: number;
  ocorrencias_30d: number;
  alertas_30d: number;
  simulados: boolean;
}

export interface Colaborador {
  id: number;
  matricula: string;
  nome: string;
  setor: string;
  funcao: string;
  admissao: string | null;
  ativo: boolean;
  ficticio?: boolean;
  entregas_vigentes?: number;
  /** O contrato não diz se é contagem ou lista: a tela aceita os dois (ver `contagem`). */
  pendencias?: number | unknown[];
}

export interface Epi {
  id: number;
  nome: string;
  categoria: string;
  ca: string;
  validade_ca: string;
  fabricante: string;
  vida_util_dias: number;
  ficticio?: boolean;
  situacao_ca?: SituacaoCa;
  dias_para_vencer?: number | null;
  entregas_vigentes?: number;
}

export interface Entrega {
  id: number;
  codigo: string;
  colaborador: { id: number; matricula: string; nome: string; setor: string };
  /** `situacao_ca` é opcional: o servidor passa a mandar, mas a tela não depende dele para existir. */
  epi: { id: number; nome: string; categoria: string; ca: string; situacao_ca?: SituacaoCa };
  quantidade: number;
  entregue_em: string;
  troca_prevista_em: string;
  devolvido_em: string | null;
  motivo: string;
  observacao: string;
  registrado_por: string;
  situacao: SituacaoEntrega;
  ficticio?: boolean;
}

export interface Ocorrencia {
  id: number;
  codigo: string;
  tipo: string;
  gravidade: string;
  setor: string;
  descricao: string;
  ocorrida_em: string;
  status: StatusOcorrencia;
  acao_corretiva: string | null;
  colaborador: { id: number; nome: string; matricula: string } | null;
  alerta_id?: number | null;
  encerrada_em?: string | null;
  ficticio?: boolean;
}

export interface ListaDeColaboradores {
  items: Colaborador[];
  count: number;
  setores: string[];
}

// ------------------------------------------------------------------ rótulos ---
export const ROTULO_CATEGORIA: Record<string, string> = { ...PPE_LABELS, outro: "Outro" };
export const CATEGORIAS = [...PPE_KEYS, "outro"] as const;

export const ROTULO_MOTIVO: Record<string, string> = { admissao: "Admissão", substituicao: "Substituição", perda: "Perda", dano: "Dano" };
export const ROTULO_TIPO: Record<string, string> = {
  acidente: "Acidente",
  quase_acidente: "Quase acidente",
  condicao_insegura: "Condição insegura",
  ato_inseguro: "Ato inseguro",
};
export const ROTULO_GRAVIDADE: Record<string, string> = { baixa: "Baixa", media: "Média", alta: "Alta", critica: "Crítica" };
export const ROTULO_STATUS: Record<string, string> = { aberta: "Aberta", em_tratamento: "Em tratamento", encerrada: "Encerrada" };
export const ROTULO_SITUACAO_ENTREGA: Record<SituacaoEntrega, string> = { vigente: "Vigente", troca_vencida: "Troca vencida", devolvido: "Devolvida" };

/** Rótulo de uma chave conhecida; chave desconhecida passa como veio (a tela nunca esconde o dado). */
export const rotulo = (mapa: Record<string, string>, chave: string): string => mapa[chave] ?? chave;

// ---------------------------------------------------------------- formatação ---
/** "2026-10-10" → "10/10/2026", sem passar por Date (que deslocaria o dia pelo fuso). */
export function dataCurta(iso: string | null | undefined): string {
  if (!iso) return "–";
  const [a, m, d] = iso.slice(0, 10).split("-");
  return a && m && d ? `${d}/${m}/${a}` : iso;
}

/** "14/10/2026 14:05" para um instante ISO do servidor (com ano: o histórico passa de um ano). */
export function dataHora(iso: string): string {
  const data = paraDate(iso);
  return `${data.toLocaleDateString("pt-BR")} ${horaCurta(data)}`;
}

/** Hoje como "AAAA-MM-DD" na data local, o formato do `<input type="date">`. */
export function hojeIso(): string {
  const d = new Date();
  const dois = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${dois(d.getMonth() + 1)}-${dois(d.getDate())}`;
}

/** Agora como "AAAA-MM-DDTHH:MM" local, o formato do `<input type="datetime-local">`. */
export const agoraLocal = (): string => {
  const d = new Date();
  return `${hojeIso()}T${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
};

/** Valor do `datetime-local` (hora da máquina) → instante ISO 8601 em UTC, como o contrato pede. */
export const instanteIso = (local: string): string => new Date(local).toISOString().replace(/\.\d{3}Z$/, "+00:00");

/** Contagem de algo que o servidor pode mandar como número ou como lista. */
export const contagem = (v: number | unknown[] | undefined): number => (Array.isArray(v) ? v.length : Number(v ?? 0));

/** `?a=1&b=2` só com os valores preenchidos. */
export function montarUrl(base: string, params: Record<string, string>): string {
  const q = new URLSearchParams();
  for (const [chave, valor] of Object.entries(params)) if (valor) q.set(chave, valor);
  const texto = q.toString();
  return texto ? `${base}?${texto}` : base;
}

/** `code` estável que o servidor manda nos 400/404/409 (ex.: `ca_vencido`), ou null. */
export function codigoDoErro(err: unknown): string | null {
  if (!(err instanceof ApiError) || !err.body || typeof err.body !== "object") return null;
  const codigo = (err.body as { code?: unknown }).code;
  return typeof codigo === "string" ? codigo : null;
}
