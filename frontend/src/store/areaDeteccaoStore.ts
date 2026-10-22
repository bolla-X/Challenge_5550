import { create } from "zustand";
import { getAreaDeteccao, removerAreaDeteccao, salvarAreaDeteccao } from "../api/endpoints";
import type { AreaDeteccaoEstado } from "../api/types";
import { mensagemDeErro } from "../utils/erros";
import { areaDoPoligono, type Ponto } from "../utils/poligono";

/**
 * Editor da área de detecção (MISSÃO 7). Fica fora do dashboardStore de propósito:
 * é estado de uma aba só (Áreas, na tela de foco), sem evento de socket, e o
 * dashboardStore já carrega a área de RISCO com a mesma câmera (`camId`).
 */
export type TipoDeArea = "deteccao" | "risco";
export type ModoDeDesenho = "retangulo" | "poligono";

type Estado = {
  /** Qual área o editor mexe agora. */
  tipo: TipoDeArea;
  modo: ModoDeDesenho;
  editando: boolean;
  camId: number | null;
  salva: AreaDeteccaoEstado | null;
  /** Rascunho: o que está desenhado e ainda não foi salvo. */
  pontos: Ponto[];
  pendente: boolean;
  erro: string | null;
  aviso: string | null;
  setTipo: (tipo: TipoDeArea) => void;
  setModo: (modo: ModoDeDesenho) => void;
  alternarEdicao: () => void;
  setPontos: (pontos: Ponto[]) => void;
  refazer: () => void;
  carregar: (camId: number) => Promise<void>;
  salvar: () => Promise<void>;
  remover: () => Promise<void>;
};

const doServidor = (estado: AreaDeteccaoEstado | null): Ponto[] => (estado?.polygon || []).map((p) => ({ x: p.x, y: p.y }));

export const useAreaDeteccao = create<Estado>((set, get) => ({
  tipo: "risco",
  modo: "retangulo",
  editando: false,
  camId: null,
  salva: null,
  pontos: [],
  pendente: false,
  erro: null,
  aviso: null,
  setTipo: (tipo) => set({ tipo, editando: false, aviso: null, erro: null }),
  setModo: (modo) => set({ modo, pontos: [], aviso: null }),
  alternarEdicao: () => set((s) => ({ editando: !s.editando, aviso: null })),
  setPontos: (pontos) => set({ pontos, aviso: null }),
  refazer: () => set({ pontos: [], editando: true, aviso: null, erro: null }),
  carregar: async (camId) => {
    set({ camId, erro: null, aviso: null, editando: false });
    try {
      const { area_deteccao } = await getAreaDeteccao(camId);
      if (get().camId !== camId) return; // trocou de câmera no meio
      set({ salva: area_deteccao, pontos: doServidor(area_deteccao) });
    } catch (e) {
      if (get().camId === camId) set({ salva: null, pontos: [], erro: mensagemDeErro(e, "Não foi possível carregar a área de detecção.") });
    }
  },
  salvar: async () => {
    const { camId, pontos } = get();
    if (camId == null) return;
    if (pontos.length < 3) {
      set({ aviso: "A área de detecção precisa de pelo menos 3 pontos." });
      return;
    }
    if (areaDoPoligono(pontos) < 0.01) {
      set({ aviso: "A área de detecção é pequena demais: desenhe ao menos 1 % do quadro." });
      return;
    }
    set({ pendente: true, erro: null, aviso: null });
    try {
      const { area_deteccao } = await salvarAreaDeteccao(camId, pontos);
      set({ salva: area_deteccao, pontos: doServidor(area_deteccao), editando: false });
    } catch (e) {
      set({ erro: mensagemDeErro(e, "Não foi possível salvar a área de detecção.") });
    } finally {
      set({ pendente: false });
    }
  },
  remover: async () => {
    const { camId } = get();
    if (camId == null) return;
    set({ pendente: true, erro: null, aviso: null });
    try {
      const { area_deteccao } = await removerAreaDeteccao(camId);
      set({ salva: area_deteccao, pontos: [], editando: false });
    } catch (e) {
      set({ erro: mensagemDeErro(e, "Não foi possível remover a área de detecção.") });
    } finally {
      set({ pendente: false });
    }
  },
}));
