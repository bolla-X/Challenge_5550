import { apiFetch } from "./client";

// Contrato de GET /api/status (app/services/status_do_sistema.py). Técnico ou acima.
// Distinto de getStatus() de endpoints.ts, que lê o `/status` legado do monitor.

export type EstadoDoComponente = "ok" | "atencao" | "falha" | "desligado";

type Item = { estado: EstadoDoComponente; resumo: string };

export type ModeloDoStatus = {
  nome: string;
  arquivo: string | null;
  runtime: string | null;
  runtime_pedido: string | null;
  runtime_validado: string | null;
  dispositivo: string | null;
  carga_ms: number | null;
  aquecimento_ms: number | null;
  aquecido: boolean;
};
export type CameraDoStatus = {
  id: number;
  nome: string;
  situacao: "no_ar" | "sem_sinal" | "parada" | "apresentacao";
  estado: EstadoDoComponente;
  saude_visual: { estado: string; rotulo: string };
  fps: number | null;
  privacidade_ativa: boolean | null;
  tentativas_de_reconexao: number | null;
};
export type IntegracaoDoStatus = Item & {
  endpoint?: string | null;
  erro?: string | null;
  como_ligar: string;
  estatisticas?: { enviados: number; falhas: number; descartados: number; pendentes: number };
};
export type VolumeDoStatus = {
  estado: EstadoDoComponente;
  resumo?: string;
  total_bytes?: number;
  usado_bytes?: number;
  livre_bytes?: number;
  livre_fracao?: number;
};
export type PastaDoStatus = { existe: boolean; bytes: number; arquivos: number; parcial: boolean };

export type StatusDoSistema = {
  gerado_em: string;
  versao: { construido_em: string | null };
  componentes: {
    modelos: Item & { modelos?: ModeloDoStatus[]; degradado?: boolean; motivo_da_degradacao?: string | null };
    cameras: Item & { cameras?: CameraDoStatus[] };
    banco: Item & { motor?: string; consulta_ms?: number; arquivo?: string; bytes?: number };
    opcua: IntegracaoDoStatus;
    mqtt: IntegracaoDoStatus;
    broker: IntegracaoDoStatus;
    webhook: IntegracaoDoStatus;
    llm: Item & {
      ligado?: boolean;
      tem_chave?: boolean;
      /** "demonstracao": resposta fixa, sem GEMINI_API_KEY. Ausente em servidores que não mandam o campo. */
      modo?: "real" | "demonstracao";
      versao_do_prompt?: string;
      intervalo_minimo_s?: number | null;
      limite_de_espera_s?: number | null;
      como_ligar?: string;
    };
    disco: Item & {
      volumes?: Record<"evidencias" | "instancia", VolumeDoStatus>;
      pastas?: Record<"imagens" | "clipes" | "trilhas", PastaDoStatus>;
    };
  };
  politicas: {
    privacidade: { padrao_ligada: boolean; cameras: { id: number; nome: string; ativa: boolean | null }[] };
    retencao: {
      expira_sozinha: boolean;
      imagem_de_evidencia: boolean;
      replay: boolean;
      replay_antes_s: number | null;
      replay_depois_s: number | null;
      trilhas_teto_mb: number;
      trilhas_mb_por_arquivo: number;
      trilhas_arquivos: number;
      cadeia_de_custodia: boolean;
      limpa_ao_ligar_a_camera: boolean;
    };
  };
};

/** Com prazo: servidor travado não pode deixar a página em "carregando" para sempre. */
export const getStatusDoSistema = () =>
  apiFetch<StatusDoSistema>("/api/status", typeof AbortSignal.timeout === "function" ? { signal: AbortSignal.timeout(15_000) } : undefined);
