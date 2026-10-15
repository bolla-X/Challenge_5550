import type { Incidente } from "../../api/types";

/** Um pé projetado na planta (G5), com o estado que pinta o avatar (X1). */
export type PeNaPlanta = {
  track_id: number | string;
  x: number;
  y: number;
  dentro_da_calibracao: boolean;
  na_zona: boolean;
  estado: "conforme" | "sem_epi" | "zona" | "emergencia";
  faltando: string[];
  alert_id: number | null;
};

/** app/api/gemeo.py */
export type CameraDoGemeo = {
  id: number;
  nome: string;
  setor: string;
  calibrada: boolean;
  pontos_camera: [number, number][] | null;
  pontos_planta: [number, number][] | null;
  zona: [number, number][];
  zona_nome: string | null;
  pes: PeNaPlanta[];
  incidentes: Incidente[];
  rodando: boolean;
};

export type EstadoDoGemeo = { cameras: CameraDoGemeo[]; gerado_em: number };
