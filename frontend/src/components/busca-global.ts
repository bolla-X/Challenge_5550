import { useEffect, useMemo, useRef, useState } from "react";
import { ApiError } from "../api/client";
import { listarPermissoesParaBusca, listarRegrasParaBusca, type PermissaoParaBusca, type RegraParaBusca } from "../api/busca";
import { listarIncidentes } from "../api/endpoints";
import type { CameraRecord, Incidente } from "../api/types";
import { buscarArtigos, enderecoDoArtigo } from "../ajuda/artigos";
import { ROLE_ACCESS, useDashboardStore, type CameraScreen, type ViewMode } from "../store/dashboardStore";
import { contemTodos, idDeRastreio, termosDa } from "../utils/busca";
import { eFalhaDeRede } from "../utils/erros";
import { idsDoIncidente, rotuloDoIncidente, zonaDoIncidente } from "../utils/incidentes";

/**
 * Busca global da paleta de comandos (Ctrl K): câmeras, incidentes ativos, IDs de
 * rastreio, regras, permissões, telas e artigos de ajuda. Só oferece o que o tipo
 * de conta pode abrir. Os dados do servidor chegam depois de 200 ms sem digitar e
 * ficam em cache por 15 s; falha de rede não faz barulho (a busca só fica sem
 * aquele grupo). O ID de rastreio é só o rótulo por posição, nunca identidade.
 */

export interface ItemDeBusca {
  id: string;
  rotulo: string;
  detalhe?: string;
  abrir: () => void;
}

export interface GrupoDeBusca {
  chave: string;
  titulo: string;
  itens: ItemDeBusca[];
  /** Frase no lugar dos itens (ex.: o ID de rastreio não está em nenhum incidente ativo). */
  nota?: string;
}

const ESPERA_MS = 200;
const VALIDADE_DO_CACHE_MS = 15_000;
const LIMITE_POR_GRUPO = 5;
const LIMITE_DE_TELAS = 6;
const NIVEL: Record<ViewMode, number> = { operator: 1, technical: 2, supervisor: 3 };

// ---- telas ---------------------------------------------------------------------

type Destino = { href: string; novaAba?: boolean } | { tela: CameraScreen };

interface TelaBuscavel {
  rotulo: string;
  detalhe: string;
  palavras: string[];
  /** Menor tipo de conta que abre a tela (o mesmo que o App.tsx e a API exigem). */
  minimo: ViewMode;
  destino: Destino;
}

/** Todas as telas do App. Quem não pode abrir não vê na busca. */
const TELAS: TelaBuscavel[] = [
  { rotulo: "Câmeras", detalhe: "Grade de câmeras", palavras: ["grade", "monitoramento"], minimo: "technical", destino: { tela: "grid" } },
  { rotulo: "Início", detalhe: "A planta agora", palavras: ["home", "planta"], minimo: "supervisor", destino: { tela: "home" } },
  { rotulo: "Visão geral", detalhe: "Por setor", palavras: ["setores", "painel"], minimo: "supervisor", destino: { tela: "overview" } },
  { rotulo: "Contas", detalhe: "Acesso da equipe", palavras: ["usuários", "senha", "operador"], minimo: "supervisor", destino: { tela: "accounts" } },
  { rotulo: "Sobre", detalhe: "Créditos e licenças", palavras: ["licenças", "créditos"], minimo: "technical", destino: { tela: "sobre" } },
  { rotulo: "Modo TV", detalhe: "Segurança do turno por setor", palavras: ["tv", "andon", "parede"], minimo: "operator", destino: { href: "/tv" } },
  { rotulo: "Torre de luz", detalhe: "Verde, amarelo e vermelho", palavras: ["torre", "sirene", "opc ua", "mqtt", "clp"], minimo: "operator", destino: { href: "/torre" } },
  { rotulo: "Portal de Entrada", detalhe: "Check-in de EPIs", palavras: ["portal", "portaria", "check-in"], minimo: "operator", destino: { href: "/portal" } },
  { rotulo: "Gêmeo digital", detalhe: "A planta em 3D", palavras: ["gemeo", "3d", "planta"], minimo: "operator", destino: { href: "/gemeo" } },
  { rotulo: "Liga de Setores", detalhe: "Pontos e missões", palavras: ["liga", "missões", "nível"], minimo: "operator", destino: { href: "/liga" } },
  { rotulo: "Retrospectiva", detalhe: "O turno em cartões", palavras: ["stories", "turno"], minimo: "operator", destino: { href: "/retrospectiva" } },
  { rotulo: "Você vs. a IA", detalhe: "Desafio", palavras: ["desafio", "jogo"], minimo: "operator", destino: { href: "/desafio" } },
  { rotulo: "Permissão de trabalho", detalhe: "Emitir e acompanhar", palavras: ["permissões", "pt", "vigia", "nr-33", "nr-35"], minimo: "operator", destino: { href: "/permissoes" } },
  { rotulo: "Central de ajuda", detalhe: "Artigos por tarefa", palavras: ["ajuda", "tutorial", "como fazer"], minimo: "operator", destino: { href: "/ajuda" } },
  { rotulo: "Regras de alerta", detalhe: "Editor de regras", palavras: ["regras", "editor", "condição"], minimo: "technical", destino: { href: "/regras" } },
  { rotulo: "Auditoria das evidências", detalhe: "Cadeia de custódia", palavras: ["auditoria", "custódia", "integridade", "sha-256"], minimo: "technical", destino: { href: "/auditoria" } },
  { rotulo: "Simulador “E se?”", detalhe: "Testar uma regra no histórico", palavras: ["simulador", "e se", "histerese"], minimo: "technical", destino: { href: "/simulador" } },
  { rotulo: "Modo Evacuação", detalhe: "Contagem por câmera", palavras: ["evacuação", "emergência", "ponto de encontro"], minimo: "technical", destino: { href: "/evacuacao" } },
  { rotulo: "Rotular recortes", detalhe: "Aprendizado ativo", palavras: ["rotular", "rótulos", "yolo", "dataset"], minimo: "technical", destino: { href: "/rotular" } },
  { rotulo: "Apresentação", detalhe: "Roteiro da demonstração", palavras: ["palco", "demo", "slides"], minimo: "technical", destino: { href: "/palco" } },
  { rotulo: "Gestão de EPIs", detalhe: "Colaboradores, entregas e ocorrências", palavras: ["epi", "colaboradores", "catálogo", "certificado de aprovação", "entregas", "devolução", "ocorrências", "exportar", "csv", "ca vencido", "troca vencida", "pendência", "ficha de epi", "nr-6"], minimo: "technical", destino: { href: "/gestao" } },
  { rotulo: "Relatório do turno", detalhe: "Imprimir ou salvar em PDF", palavras: ["pdf", "imprimir", "turno", "nr-6"], minimo: "technical", destino: { href: "/relatorio/turno", novaAba: true } },
  { rotulo: "Primeiro acesso", detalhe: "Configurar a planta", palavras: ["onboarding", "assistente", "pronto para operar"], minimo: "supervisor", destino: { href: "/primeiro-acesso" } },
];

function abrirDestino(destino: Destino): void {
  if ("tela" in destino) {
    useDashboardStore.getState().setScreen(destino.tela);
  } else if (destino.novaAba) {
    window.open(destino.href, "_blank", "noopener,noreferrer");
  } else {
    window.location.assign(destino.href);
  }
}

function abrirCamera(id: number): void {
  const { setCamId, setScreen } = useDashboardStore.getState();
  setCamId(id);
  setScreen("focus");
}

// ---- dados do servidor -----------------------------------------------------------

interface DadosDoServidor {
  incidentes: Incidente[] | null;
  regras: RegraParaBusca[] | null;
  permissoes: PermissaoParaBusca[] | null;
}

const SEM_DADOS: DadosDoServidor = { incidentes: null, regras: null, permissoes: null };

/** Falha de rede e resposta de erro da API são esperadas numa busca: só bug de verdade vai ao console. */
function falhaInesperada(motivo: unknown): boolean {
  return !eFalhaDeRede(motivo) && !(motivo instanceof ApiError);
}

function useDadosDoServidor(consultaFirme: string, ativa: boolean, mode: ViewMode): DadosDoServidor {
  const [dados, setDados] = useState<DadosDoServidor>(SEM_DADOS);
  const emVoo = useRef(false);
  const carregadoEm = useRef<number | null>(null);
  const montado = useRef(true);

  useEffect(() => {
    montado.current = true;
    return () => {
      montado.current = false;
    };
  }, []);

  // Paleta fechada: esquece o que tinha (incidente ativo envelhece rápido).
  useEffect(() => {
    if (!ativa) {
      setDados(SEM_DADOS);
      carregadoEm.current = null;
    }
  }, [ativa]);

  useEffect(() => {
    if (!ativa || consultaFirme.length < 2 || emVoo.current) return;
    if (carregadoEm.current !== null && Date.now() - carregadoEm.current < VALIDADE_DO_CACHE_MS) return;
    emVoo.current = true;
    Promise.allSettled([
      mode !== "operator" ? listarIncidentes({ status: "active", limit: 200 }) : Promise.resolve(null),
      ROLE_ACCESS[mode].canConfigure ? listarRegrasParaBusca() : Promise.resolve(null),
      listarPermissoesParaBusca(),
    ]).then(([incidentes, regras, permissoes]) => {
      emVoo.current = false;
      carregadoEm.current = Date.now();
      if (!montado.current) return;
      for (const r of [incidentes, regras, permissoes]) {
        if (r.status === "rejected" && falhaInesperada(r.reason)) console.error("[busca] falha ao consultar o servidor", r.reason);
      }
      setDados((anterior) => ({
        incidentes: incidentes.status === "fulfilled" ? (incidentes.value?.items ?? null) : anterior.incidentes,
        regras: regras.status === "fulfilled" ? (regras.value?.regras ?? null) : anterior.regras,
        permissoes: permissoes.status === "fulfilled" ? (permissoes.value?.items ?? null) : anterior.permissoes,
      }));
    });
  }, [consultaFirme, ativa, mode]);

  return dados;
}

// ---- montagem dos grupos -----------------------------------------------------------

const ROTULO_DO_TIPO_DE_PERMISSAO: Record<string, string> = {
  espaco_confinado: "Espaço confinado",
  altura: "Trabalho em altura",
  geral: "Geral",
};

function resumir(texto: string, maximo = 70): string {
  return texto.length > maximo ? `${texto.slice(0, maximo - 1).trimEnd()}…` : texto;
}

function montarGrupos(consulta: string, mode: ViewMode, cameras: CameraRecord[], dados: DadosDoServidor): GrupoDeBusca[] {
  const termos = termosDa(consulta);
  if (!termos.length) return [];
  const grupos: GrupoDeBusca[] = [];
  const nomeDaCamera = (id: number | null) => (id == null ? undefined : cameras.find((c) => c.id === id)?.name);
  // O Operador fica na câmera do setor dele: não há câmera nem incidente para "abrir".
  const navegaPelasCameras = mode !== "operator";
  const idPedido = idDeRastreio(consulta);

  if (navegaPelasCameras) {
    const itens = cameras
      .filter((c) => contemTodos(`${c.name} ${c.location ?? ""} ${c.source_type} câmera`, termos))
      .slice(0, LIMITE_POR_GRUPO)
      .map((c) => ({ id: `camera-${c.id}`, rotulo: c.name, detalhe: c.location ?? undefined, abrir: () => abrirCamera(c.id) }));
    if (itens.length) grupos.push({ chave: "cameras", titulo: "Câmeras", itens });
  }

  if (navegaPelasCameras && dados.incidentes && idPedido === null) {
    const itens = dados.incidentes
      .filter((inc) => inc.camera_id != null && nomeDaCamera(inc.camera_id) !== undefined)
      .filter((inc) => contemTodos(`${rotuloDoIncidente(inc)} ${nomeDaCamera(inc.camera_id) ?? ""}`, termos))
      .slice(0, LIMITE_POR_GRUPO)
      .map((inc) => ({
        id: `incidente-${inc.id}`,
        rotulo: rotuloDoIncidente(inc),
        detalhe: nomeDaCamera(inc.camera_id),
        abrir: () => abrirCamera(inc.camera_id as number),
      }));
    if (itens.length) grupos.push({ chave: "incidentes", titulo: "Incidentes", itens });
  }

  if (navegaPelasCameras && dados.incidentes && idPedido !== null) {
    const termina = new RegExp(`(?:^|\\D)${idPedido}$`);
    const achados = dados.incidentes.filter(
      (inc) => inc.camera_id != null && nomeDaCamera(inc.camera_id) !== undefined && idsDoIncidente(inc).some((x) => termina.test(String(x).trim())),
    );
    if (achados.length) {
      grupos.push({
        chave: "rastreio",
        titulo: "IDs de rastreio",
        itens: achados.slice(0, LIMITE_POR_GRUPO).map((inc) => {
          const zona = zonaDoIncidente(inc);
          return {
            id: `rastreio-${idPedido}-${inc.id}`,
            rotulo: `Pessoa ${idPedido} em ${nomeDaCamera(inc.camera_id)}`,
            detalhe: `${inc.titulo}${zona ? `, ${zona}` : ""}`,
            abrir: () => abrirCamera(inc.camera_id as number),
          };
        }),
      });
    } else {
      grupos.push({
        chave: "rastreio",
        titulo: "IDs de rastreio",
        itens: [],
        nota: `Nenhum incidente ativo inclui a Pessoa ${idPedido} agora. Isso não quer dizer que ela não esteja na câmera: o ID é um rastreio por posição e não identifica ninguém.`,
      });
    }
  }

  if (dados.regras) {
    const itens = dados.regras
      .filter((r) => contemTodos(`${r.nome} regra`, termos))
      .slice(0, LIMITE_POR_GRUPO)
      .map((r) => ({
        id: `regra-${r.id}`,
        rotulo: r.nome,
        detalhe: r.origem === "pre_carregada" ? "Nativa" : r.ativa ? "Ativa" : "Desativada",
        abrir: () => abrirDestino({ href: "/regras" }),
      }));
    if (itens.length) grupos.push({ chave: "regras", titulo: "Regras", itens });
  }

  if (dados.permissoes) {
    // O responsável (texto livre com nome de pessoa) fica de fora: a busca acha por número, tipo, descrição e câmera.
    const itens = dados.permissoes
      .filter((p) =>
        contemTodos(`${p.numero} ${ROTULO_DO_TIPO_DE_PERMISSAO[p.tipo] ?? p.tipo} ${p.descricao} ${nomeDaCamera(p.camera_id) ?? ""} permissão`, termos),
      )
      .slice(0, LIMITE_POR_GRUPO)
      .map((p) => ({
        id: `permissao-${p.id}`,
        rotulo: `${p.numero}: ${resumir(p.descricao)}`,
        detalhe: `${ROTULO_DO_TIPO_DE_PERMISSAO[p.tipo] ?? p.tipo}, ${p.status}`,
        abrir: () => abrirDestino({ href: "/permissoes" }),
      }));
    if (itens.length) grupos.push({ chave: "permissoes", titulo: "Permissões", itens });
  }

  const telas = TELAS.filter((t) => NIVEL[mode] >= NIVEL[t.minimo])
    .filter((t) => contemTodos(`${t.rotulo} ${t.detalhe} ${t.palavras.join(" ")}`, termos))
    .slice(0, LIMITE_DE_TELAS)
    .map((t) => ({ id: `tela-${t.rotulo}`, rotulo: t.rotulo, detalhe: t.detalhe, abrir: () => abrirDestino(t.destino) }));
  if (telas.length) grupos.push({ chave: "telas", titulo: "Telas", itens: telas });

  const ajuda = buscarArtigos(consulta, mode)
    .slice(0, LIMITE_POR_GRUPO)
    .map((a) => ({ id: `ajuda-${a.id}`, rotulo: a.titulo, abrir: () => abrirDestino({ href: enderecoDoArtigo(a.id) }) }));
  if (ajuda.length) grupos.push({ chave: "ajuda", titulo: "Ajuda", itens: ajuda });

  return grupos;
}

/**
 * Grupos de resultado para o que a pessoa digitou. Consulta vazia: nenhum grupo
 * (a paleta mostra só os comandos de sempre). Câmeras, telas e ajuda respondem na
 * hora; incidentes, IDs de rastreio, regras e permissões chegam do servidor.
 */
export function useBuscaGlobal(consulta: string, ativa: boolean): GrupoDeBusca[] {
  const mode = useDashboardStore((s) => s.mode);
  const cameras = useDashboardStore((s) => s.cameras);
  const [firme, setFirme] = useState("");

  useEffect(() => {
    const texto = consulta.trim();
    if (!texto) {
      setFirme("");
      return undefined;
    }
    const temporizador = window.setTimeout(() => setFirme(texto), ESPERA_MS);
    return () => window.clearTimeout(temporizador);
  }, [consulta]);

  const dados = useDadosDoServidor(firme, ativa, mode);
  return useMemo(() => montarGrupos(consulta, mode, cameras, dados), [consulta, mode, cameras, dados]);
}
