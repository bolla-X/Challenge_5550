import { apiFetch } from "./client";

// Leituras da busca global (paleta de comandos). Só os campos que a busca usa.
// Incidentes: `listarIncidentes` (endpoints.ts).

/** app/api/regras.py: GET /api/regras (técnico ou acima). */
export interface RegraParaBusca {
  id: string;
  nome: string;
  ativa: boolean;
  /** "pre_carregada" para as nativas. */
  origem: string;
}
export const listarRegrasParaBusca = () => apiFetch<{ regras: RegraParaBusca[] }>("/api/regras");

/** app/api/permissoes.py: GET /api/permissoes (o Operador só vê as da própria câmera). */
export interface PermissaoParaBusca {
  id: number;
  numero: string;
  camera_id: number;
  tipo: string;
  descricao: string;
  status: string;
  exige_vigia: boolean;
}
export const listarPermissoesParaBusca = (limite = 200) =>
  apiFetch<{ items: PermissaoParaBusca[]; count: number }>(`/api/permissoes?limit=${limite}`);
