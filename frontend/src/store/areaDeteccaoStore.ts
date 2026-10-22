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
  carregando: boolean;
  /** A leitura falhou: não se sabe o que está salvo, então nada se grava por cima. */
  falhaCarga: boolean;
  pendente: "salvar" | "remover" | null;
  erro: string | null;
  aviso: string | null;
  sucesso: string | null;
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

/** O rascunho é diferente do que está salvo? */
export function temAlteracao(pontos: Ponto[], salva: AreaDeteccaoEstado | null): boolean {
  const s = salva?.polygon || [];
  return pontos.length !== s.length || pontos.some((p, i) => p.x !== s[i].x || p.y !== s[i].y);
}

const modoDaForma = (pontos: Ponto[]): ModoDeDesenho => (pontos.length && pontos.length !== 4 ? "poligono" : "retangulo");

export const useAreaDeteccao = create<Estado>((set, get) => ({
  // Primeiro passo da preparação de uma câmera (DEMO.md): o seletor abre na detecção.
  tipo: "deteccao",
  modo: "retangulo",
  editando: false,
  camId: null,
  salva: null,
  pontos: [],
  carregando: false,
  falhaCarga: false,
  pendente: null,
  erro: null,
  aviso: null,
  sucesso: null,
  // Trocar de tipo ou encerrar o desenho descarta o rascunho: nada fica escondido esperando um "Salvar".
  setTipo: (tipo) =>
    set((s) => ({ tipo, editando: false, pontos: doServidor(s.salva), aviso: null, erro: null, sucesso: null })),
  // Polígono aproveita a forma atual (um retângulo já é um polígono de 4 pontos arrastáveis); retângulo recomeça.
  setModo: (modo) => set((s) => ({ modo, pontos: modo === "poligono" ? s.pontos : [], aviso: null, sucesso: null })),
  alternarEdicao: () =>
    set((s) =>
      s.editando
        ? { editando: false, pontos: doServidor(s.salva), aviso: null }
        : { editando: true, aviso: null, sucesso: null },
    ),
  setPontos: (pontos) => set({ pontos, aviso: null, sucesso: null }),
  refazer: () => set({ pontos: [], editando: true, aviso: null, erro: null, sucesso: null }),
  carregar: async (camId) => {
    set({ camId, carregando: true, falhaCarga: false, erro: null, aviso: null, sucesso: null, editando: false });
    try {
      const { area_deteccao } = await getAreaDeteccao(camId);
      if (get().camId !== camId) return; // trocou de câmera no meio
      const pontos = doServidor(area_deteccao);
      set({ salva: area_deteccao, pontos, modo: modoDaForma(pontos), carregando: false });
    } catch (e) {
      if (get().camId === camId) {
        set({ salva: null, pontos: [], carregando: false, falhaCarga: true,
              erro: mensagemDeErro(e, "Não foi possível carregar a área de detecção.") });
      }
    }
  },
  salvar: async () => {
    const { camId, pontos, falhaCarga, carregando } = get();
    if (camId == null || falhaCarga || carregando) return;
    if (pontos.length < 3) {
      set({ aviso: "Desenhe a área no vídeo antes de salvar: ela precisa de pelo menos 3 pontos." });
      return;
    }
    if (areaDoPoligono(pontos) < 0.01) {
      set({ aviso: "A área de detecção ficou pequena demais (menos de 1 % da imagem) para caber uma pessoa. Desenhe uma área maior." });
      return;
    }
    set({ pendente: "salvar", erro: null, aviso: null, sucesso: null });
    try {
      const { area_deteccao } = await salvarAreaDeteccao(camId, pontos);
      set({ salva: area_deteccao, pontos: doServidor(area_deteccao), editando: false,
            sucesso: "Área de detecção salva. A próxima análise já usa a área nova." });
    } catch (e) {
      set({ erro: mensagemDeErro(e, "Não foi possível salvar a área de detecção.") });
    } finally {
      set({ pendente: null });
    }
  },
  remover: async () => {
    const { camId } = get();
    if (camId == null) return;
    set({ pendente: "remover", erro: null, aviso: null, sucesso: null });
    try {
      const { area_deteccao } = await removerAreaDeteccao(camId);
      set({ salva: area_deteccao, pontos: [], editando: false, modo: "retangulo",
            sucesso: "Área removida. A câmera volta a analisar o quadro inteiro." });
    } catch (e) {
      set({ erro: mensagemDeErro(e, "Não foi possível remover a área de detecção.") });
    } finally {
      set({ pendente: null });
    }
  },
}));
