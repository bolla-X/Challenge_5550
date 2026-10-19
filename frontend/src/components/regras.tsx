import { avisarSeSessaoExpirou } from "../api/client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent as TeclaReact, ReactNode } from "react";
import { useDashboardStore } from "../store/dashboardStore";
import { Badge, EmptyState, PanelSkeleton } from "./common";
import { IconeFechar, IconeMais } from "./icones";
import { IlustracaoEscudo } from "./ilustracoes";
import { mensagemDeErro } from "../utils/erros";
import { dataHoraCurta, horaCurta } from "../utils/datas";
import { decimal, inteiro, pluralizar } from "../utils/formato";
import { useFecharComEsc } from "../utils/teclado";
import "../styles/regras.css";

/**
 * Editor de regras sem código (M4, `/regras`, técnico ou acima).
 * Contrato: app/api/regras.py e app/services/regras_editor.py. A regra é montada com blocos
 * (grupos E/OU aninháveis); o servidor valida e devolve o erro em pt-BR com o caminho do campo
 * ("condicao.itens[0].segundos: ..."), que esta tela mostra junto do controle certo.
 * "Testar no histórico" só lê a trilha gravada: nunca cria nem muda alerta real.
 */

// ------------------------------------------------------------------ tipos ---
type TipoBloco = "zona" | "epi" | "duracao" | "postura" | "aproximacao" | "horario" | "permissao_ativa";
type Operador = "E" | "OU";

type Bloco =
  | { k: string; tipo: "zona"; dentro: boolean }
  | { k: string; tipo: "epi"; epi: string; estado: string }
  | { k: string; tipo: "duracao"; segundos: number | null }
  | { k: string; tipo: "postura"; postura: string }
  | { k: string; tipo: "aproximacao" }
  | { k: string; tipo: "horario"; de: string; ate: string }
  | { k: string; tipo: "permissao_ativa"; ativa: boolean };
type Grupo = { k: string; op: Operador; itens: No[] };
type No = Bloco | Grupo;

export type Opcoes = { severidades: string[]; epis: Record<string, string>; estados_epi: string[]; posturas: string[] };
export type Limites = { profundidade: number; blocos: number };
export type RegraApi = {
  id: string;
  nome: string;
  ativa: boolean;
  origem: "pre_carregada" | "usuario";
  regra_id: string;
  camera_ids: number[] | null;
  condicao: unknown;
  acoes: {
    severidade: string;
    mensagem: string;
    fala: boolean;
    integracao: boolean;
    escalonamento: { supervisor_s: number | null; tv_s: number | null };
  };
  protegida: boolean;
};
export type Listagem = { regras: RegraApi[]; limites: Limites; opcoes: Opcoes };

type Rascunho = {
  id: string | null; // null = regra nova (o servidor gera o id)
  nome: string;
  ativa: boolean;
  protegida: boolean;
  camera_ids: number[] | null;
  condicao: Grupo;
  severidade: string;
  mensagem: string;
  fala: boolean;
  integracao: boolean;
  supervisor_s: number | null;
  tv_s: number | null;
};

type ErroDoServidor = { caminho: string; texto: string };
export type ResultadoTeste = {
  camera_id: number;
  janela: [number, number];
  registros?: number;
  simulavel: boolean;
  motivo: string | null;
  disparos: number;
  linha_do_tempo: [number, number][];
  pessoas: number;
  incidentes?: number;
  balde_s?: number;
};

// ----------------------------------------------------------------- rótulos ---
const ROTULO_TIPO: Record<TipoBloco, string> = {
  zona: "Zona",
  epi: "EPI",
  duracao: "Duração",
  postura: "Postura",
  aproximacao: "Aproximação",
  horario: "Horário",
  permissao_ativa: "Permissão ativa",
};
const TIPOS: TipoBloco[] = ["zona", "epi", "duracao", "postura", "aproximacao", "horario", "permissao_ativa"];
const ROTULO_SEVERIDADE: Record<string, string> = { critical: "Crítica", high: "Alta", medium: "Média", low: "Baixa" };
const ADJETIVO_SEVERIDADE: Record<string, string> = { critical: "crítico", high: "alto", medium: "médio", low: "baixo" };
const ROTULO_ESTADO_EPI: Record<string, string> = { ausente: "Ausente (sem o EPI)", presente: "Presente", incorreto: "Incorreto (mal usado)" };
const ROTULO_POSTURA: Record<string, string> = { caida: "Pessoa caída", suspeita: "Postura suspeita" };
const MSG_403 = "O editor de regras é para Técnico e Supervisor.";

// ------------------------------------------------------------------- rede ---
async function pedir<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, { credentials: "same-origin", headers: { "Content-Type": "application/json" }, ...init });
  avisarSeSessaoExpirou(url, r.status);
  const corpo = await r.json().catch(() => null);
  if (!r.ok) {
    const obj = corpo && typeof corpo === "object" ? (corpo as { error?: unknown; code?: unknown }) : {};
    const msg = obj.error ? String(obj.error) : `HTTP ${r.status}`;
    throw Object.assign(new Error(msg), { status: r.status, code: typeof obj.code === "string" ? obj.code : undefined });
  }
  return corpo as T;
}
type ErroDeRede = Error & { status?: number; code?: string };

/** "condicao.itens[0].segundos: precisa ser..." vira {caminho, texto}. Sem caminho, caminho vazio. */
function lerErro(mensagem: string): ErroDoServidor {
  const m = /^([A-Za-z_][\w.[\]]*): (.+)$/.exec(mensagem);
  return m ? { caminho: m[1], texto: m[2] } : { caminho: "", texto: mensagem };
}

// ---------------------------------------------------------- modelo de dados ---
let sequencia = 0;
const novaChave = () => `k${++sequencia}`;
const ehGrupo = (no: No): no is Grupo => "itens" in no;

function blocoPadrao(tipo: TipoBloco, opcoes: Opcoes): Bloco {
  const k = novaChave();
  switch (tipo) {
    case "zona":
      return { k, tipo, dentro: true };
    case "epi":
      return { k, tipo, epi: Object.keys(opcoes.epis)[0] ?? "", estado: "ausente" };
    case "duracao":
      return { k, tipo, segundos: 10 };
    case "postura":
      return { k, tipo, postura: opcoes.posturas[0] ?? "caida" };
    case "aproximacao":
      return { k, tipo };
    case "horario":
      return { k, tipo, de: "06:00", ate: "18:00" };
    default:
      return { k, tipo: "permissao_ativa", ativa: true };
  }
}

function daApi(bruto: unknown): No {
  const no = (bruto ?? {}) as Record<string, unknown>;
  if (Array.isArray(no.itens) || "op" in no) {
    return { k: novaChave(), op: no.op === "OU" ? "OU" : "E", itens: (Array.isArray(no.itens) ? no.itens : []).map(daApi) };
  }
  return { ...no, k: novaChave() } as unknown as Bloco;
}

function paraApi(no: No): unknown {
  if (ehGrupo(no)) return { op: no.op, itens: no.itens.map(paraApi) };
  const { k: _chave, ...resto } = no;
  return resto;
}

function rascunhoDaRegra(r: RegraApi): Rascunho {
  const condicao = daApi(r.condicao);
  return {
    id: r.id,
    nome: r.nome,
    ativa: r.ativa,
    protegida: r.protegida,
    camera_ids: r.camera_ids,
    condicao: ehGrupo(condicao) ? condicao : { k: novaChave(), op: "E", itens: [condicao] },
    severidade: r.acoes.severidade,
    mensagem: r.acoes.mensagem,
    fala: r.acoes.fala,
    integracao: r.acoes.integracao,
    supervisor_s: r.acoes.escalonamento?.supervisor_s ?? null,
    tv_s: r.acoes.escalonamento?.tv_s ?? null,
  };
}

function rascunhoNovo(opcoes: Opcoes): Rascunho {
  return {
    id: null,
    nome: "",
    ativa: false,
    protegida: false,
    camera_ids: null,
    condicao: { k: novaChave(), op: "E", itens: [blocoPadrao("zona", opcoes)] },
    severidade: opcoes.severidades.includes("high") ? "high" : (opcoes.severidades[0] ?? "high"),
    mensagem: "",
    fala: false,
    integracao: false,
    supervisor_s: null,
    tv_s: null,
  };
}

/** Cópia editável de uma regra (a nativa não se edita: duplica e edita a cópia). */
function duplicar(r: Rascunho): Rascunho {
  const recriar = (no: No): No => (ehGrupo(no) ? { ...no, k: novaChave(), itens: no.itens.map(recriar) } : { ...no, k: novaChave() });
  return { ...r, id: null, nome: `${r.nome} (cópia)`, ativa: false, protegida: false, condicao: recriar(r.condicao) as Grupo };
}

/** Corpo que a API recebe (POST/PUT) e que o teste usa; sem chaves de interface. */
function corpoDoRascunho(r: Rascunho) {
  return {
    ...(r.id ? { id: r.id } : {}),
    nome: r.nome,
    ativa: r.ativa,
    camera_ids: r.camera_ids,
    condicao: paraApi(r.condicao),
    acoes: {
      severidade: r.severidade,
      mensagem: r.mensagem,
      fala: r.fala,
      integracao: r.integracao,
      escalonamento: { supervisor_s: r.supervisor_s, tv_s: r.tv_s },
    },
  };
}

function alterar(grupo: Grupo, trilha: number[], fn: (no: No) => No | null): Grupo {
  if (trilha.length === 0) return (fn(grupo) as Grupo | null) ?? grupo;
  const [indice, ...resto] = trilha;
  const itens = grupo.itens.flatMap((item, i): No[] => {
    if (i !== indice) return [item];
    if (resto.length === 0) {
      const novo = fn(item);
      return novo ? [novo] : [];
    }
    return [alterar(item as Grupo, resto, fn)];
  });
  return { ...grupo, itens };
}

function contarBlocos(no: No): number {
  return ehGrupo(no) ? no.itens.reduce((soma, item) => soma + contarBlocos(item), 0) : 1;
}

// ------------------------------------------------------- leitura humana ---
function duracaoTexto(s: number): string {
  if (s < 60) return `${inteiro(s)} s`;
  const m = Math.floor(s / 60);
  const r = s % 60;
  return r ? `${inteiro(m)} min ${inteiro(r)} s` : `${inteiro(m)} min`;
}

function textoDoBloco(b: Bloco, opcoes: Opcoes): string {
  switch (b.tipo) {
    case "zona":
      return b.dentro ? "na zona de risco" : "fora da zona de risco";
    case "epi": {
      const nome = (opcoes.epis[b.epi] ?? b.epi ?? "EPI").toLowerCase();
      return b.estado === "presente" ? `com ${nome}` : b.estado === "incorreto" ? `com ${nome} usado de forma incorreta` : `sem ${nome}`;
    }
    case "postura":
      return b.postura === "suspeita" ? "em postura suspeita" : "caído";
    case "aproximacao":
      return "se aproximando da zona de risco";
    case "horario":
      return `entre ${b.de || "…"} e ${b.ate || "…"}`;
    case "permissao_ativa":
      return b.ativa ? "com permissão ativa" : "sem permissão ativa";
    default:
      return "";
  }
}

function textoDoGrupo(g: Grupo, opcoes: Opcoes, raiz: boolean): string {
  const partes: string[] = [];
  const horarios: string[] = [];
  const duracoes: number[] = [];
  for (const item of g.itens) {
    if (ehGrupo(item)) partes.push(`(${textoDoGrupo(item, opcoes, false)})`);
    else if (item.tipo === "duracao") duracoes.push(item.segundos ?? 0);
    else if (item.tipo === "horario" && g.op === "E" && raiz) horarios.push(textoDoBloco(item, opcoes));
    else partes.push(textoDoBloco(item, opcoes));
  }
  let texto = partes.join(g.op === "E" ? " E " : " OU ");
  const maior = Math.max(0, ...duracoes);
  if (maior > 0) texto = `${texto || "…"} por ${duracaoTexto(maior)}`;
  if (horarios.length) texto = partes.length || maior > 0 ? `${texto}, ${horarios.join(" e ")}` : horarios.join(" e ");
  return texto || "…";
}

function listaEmPortugues(itens: string[]): string {
  return itens.length < 2 ? (itens[0] ?? "") : `${itens.slice(0, -1).join(", ")} e ${itens[itens.length - 1]}`;
}

function fraseDaRegra(r: Rascunho, opcoes: Opcoes, nomesCameras: Map<number, string>): string {
  const adjetivo = ADJETIVO_SEVERIDADE[r.severidade] ?? r.severidade;
  const base = `Alerta ${adjetivo} quando alguém estiver ${textoDoGrupo(r.condicao, opcoes, true)}.`;
  if (r.camera_ids === null) return `${base} Vale em todas as câmeras.`;
  if (r.camera_ids.length === 0) return `${base} Escolha em quais câmeras ela vale.`;
  const nomes = r.camera_ids.map((id) => nomesCameras.get(id) ?? `câmera ${id}`);
  return `${base} Vale só em ${listaEmPortugues(nomes)}.`;
}

// ---------------------------------------------------------------- pequenos ---
function Confirmar({ titulo, texto, acao, tom, onSim, onNao, ocupado }: {
  titulo: string; texto: string; acao: string; tom: "danger" | "primary"; onSim: () => void; onNao: () => void; ocupado: boolean;
}) {
  useFecharComEsc(onNao);
  const caixa = useRef<HTMLDivElement>(null);
  const prender = (e: TeclaReact) => {
    if (e.key !== "Tab") return;
    const foco = caixa.current?.querySelectorAll<HTMLElement>("button:not(:disabled)");
    if (!foco || !foco.length) return;
    const primeiro = foco[0];
    const ultimo = foco[foco.length - 1];
    if (e.shiftKey && document.activeElement === primeiro) {
      e.preventDefault();
      ultimo.focus();
    } else if (!e.shiftKey && document.activeElement === ultimo) {
      e.preventDefault();
      primeiro.focus();
    }
  };
  return (
    <div className="modal-scrim" onClick={onNao}>
      <div
        ref={caixa}
        className="card modal regras-confirma"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="regras-confirma-titulo"
        aria-describedby="regras-confirma-texto"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={prender}
      >
        <h2 id="regras-confirma-titulo">{titulo}</h2>
        <p id="regras-confirma-texto">{texto}</p>
        <div className="modal-acoes">
          <button type="button" className="ghost" onClick={onNao} disabled={ocupado} autoFocus>Cancelar</button>
          <button type="button" className={tom} onClick={onSim} disabled={ocupado}>{ocupado ? "Aguarde…" : acao}</button>
        </div>
      </div>
    </div>
  );
}

function Interruptor({ ligado, nome, onAlternar, ocupado }: { ligado: boolean; nome: string; onAlternar: () => void; ocupado?: boolean }) {
  return (
    <button type="button" role="switch" aria-checked={ligado} aria-label={nome} className="regras-switch" disabled={ocupado} onClick={onAlternar}>
      <span className="regras-switch-pino" aria-hidden="true" />
    </button>
  );
}

function ErroInline({ id, texto }: { id: string; texto: string | null }) {
  return texto ? <span id={id} className="regras-erro-campo">{texto}</span> : null;
}

const idSeguro = (caminho: string) => `regras-${caminho.replace(/[^\w]/g, "-")}`;

// --------------------------------------------------------------- blocos ---
function MenuCondicao({ onEscolher, desabilitado, titulo }: { onEscolher: (tipo: TipoBloco) => void; desabilitado: boolean; titulo?: string }) {
  const [aberto, setAberto] = useState(false);
  const raiz = useRef<HTMLDivElement>(null);
  const gatilho = useRef<HTMLButtonElement>(null);
  const fechar = useCallback(() => {
    setAberto(false);
    gatilho.current?.focus();
  }, []);
  useFecharComEsc(fechar, aberto);
  useEffect(() => {
    if (!aberto) return undefined;
    raiz.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus();
    const fora = (e: MouseEvent) => {
      if (raiz.current && !raiz.current.contains(e.target as Node)) setAberto(false);
    };
    document.addEventListener("mousedown", fora);
    return () => document.removeEventListener("mousedown", fora);
  }, [aberto]);
  const navegar = (e: TeclaReact) => {
    const itens = Array.from(raiz.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? []);
    const atual = itens.indexOf(document.activeElement as HTMLElement);
    if (e.key === "ArrowDown") itens[(atual + 1) % itens.length]?.focus();
    else if (e.key === "ArrowUp") itens[(atual - 1 + itens.length) % itens.length]?.focus();
    else if (e.key === "Home") itens[0]?.focus();
    else if (e.key === "End") itens[itens.length - 1]?.focus();
    else return;
    e.preventDefault();
  };
  return (
    <div className="regras-menu-raiz" ref={raiz}>
      <button
        ref={gatilho}
        type="button"
        className="small"
        aria-haspopup="menu"
        aria-expanded={aberto}
        disabled={desabilitado}
        title={titulo}
        onClick={() => setAberto((v) => !v)}
      >
        <IconeMais aria-hidden="true" /> Condição
      </button>
      {aberto && (
        <div className="regras-menu" role="menu" aria-label="Tipo de condição" onKeyDown={navegar}>
          {TIPOS.map((tipo) => (
            <button
              key={tipo}
              type="button"
              role="menuitem"
              onClick={() => {
                setAberto(false);
                onEscolher(tipo);
              }}
            >
              {ROTULO_TIPO[tipo]}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

type ContextoDoEditor = {
  opcoes: Opcoes;
  limites: Limites;
  totalBlocos: number;
  erro: ErroDoServidor | null;
  aoEditar: (trilha: number[], fn: (no: No) => No | null) => void;
};

function Campo({ rotulo, children }: { rotulo: string; children: ReactNode }) {
  return (
    <label className="field">
      <span>{rotulo}</span>
      {children}
    </label>
  );
}

function ControlesDoBloco({ bloco, ctx, mudar, invalido, descricao }: {
  bloco: Bloco; ctx: ContextoDoEditor; mudar: (p: Record<string, unknown>) => void; invalido: boolean; descricao?: string;
}) {
  const a11y = { "aria-invalid": invalido || undefined, "aria-describedby": descricao };
  const numero = (valor: string) => (valor === "" ? null : Number(valor));
  switch (bloco.tipo) {
    case "zona":
      return (
        <Campo rotulo="A pessoa está">
          <select value={bloco.dentro ? "dentro" : "fora"} onChange={(e) => mudar({ dentro: e.target.value === "dentro" })} {...a11y}>
            <option value="dentro">Dentro da zona de risco</option>
            <option value="fora">Fora da zona de risco</option>
          </select>
        </Campo>
      );
    case "epi":
      return (
        <div className="regras-campos">
          <Campo rotulo="EPI">
            <select value={bloco.epi} onChange={(e) => mudar({ epi: e.target.value })} {...a11y}>
              {Object.entries(ctx.opcoes.epis).map(([chave, nome]) => (
                <option key={chave} value={chave}>{nome}</option>
              ))}
            </select>
          </Campo>
          <Campo rotulo="Estado">
            <select value={bloco.estado} onChange={(e) => mudar({ estado: e.target.value })} {...a11y}>
              {ctx.opcoes.estados_epi.map((estado) => (
                <option key={estado} value={estado}>{ROTULO_ESTADO_EPI[estado] ?? estado}</option>
              ))}
            </select>
          </Campo>
        </div>
      );
    case "duracao":
      return (
        <>
          <Campo rotulo="Por quanto tempo (segundos)">
            <input type="number" inputMode="numeric" min={1} step={1} value={bloco.segundos ?? ""} onChange={(e) => mudar({ segundos: numero(e.target.value) })} {...a11y} />
          </Campo>
          <p className="regras-dica">O resto das condições deste grupo precisa se manter, sem interrupção, por esse tempo.</p>
        </>
      );
    case "postura":
      return (
        <Campo rotulo="Postura">
          <select value={bloco.postura} onChange={(e) => mudar({ postura: e.target.value })} {...a11y}>
            {ctx.opcoes.posturas.map((p) => (
              <option key={p} value={p}>{ROTULO_POSTURA[p] ?? p}</option>
            ))}
          </select>
        </Campo>
      );
    case "aproximacao":
      return <p className="regras-dica">A pessoa se aproxima da zona de risco (pré-alerta de aproximação). Não tem ajuste.</p>;
    case "horario":
      return (
        <>
          <div className="regras-campos">
            <Campo rotulo="De">
              <input type="time" value={bloco.de} onChange={(e) => mudar({ de: e.target.value })} {...a11y} />
            </Campo>
            <Campo rotulo="Até">
              <input type="time" value={bloco.ate} onChange={(e) => mudar({ ate: e.target.value })} {...a11y} />
            </Campo>
          </div>
          <p className="regras-dica">Hora local do servidor. Se "De" for depois de "Até", a janela atravessa a meia-noite.</p>
        </>
      );
    default:
      return (
        <Campo rotulo="Permissão de trabalho">
          <select value={bloco.ativa ? "sim" : "nao"} onChange={(e) => mudar({ ativa: e.target.value === "sim" })} {...a11y}>
            <option value="sim">Há permissão ativa</option>
            <option value="nao">Não há permissão ativa</option>
          </select>
        </Campo>
      );
  }
}

function BlocoEditor({ bloco, caminho, trilha, ctx }: { bloco: Bloco; caminho: string; trilha: number[]; ctx: ContextoDoEditor }) {
  const erro = ctx.erro && (ctx.erro.caminho === caminho || ctx.erro.caminho.startsWith(`${caminho}.`)) ? ctx.erro.texto : null;
  const idErro = `${idSeguro(caminho)}-erro`;
  return (
    <li className="regras-bloco" data-tipo={bloco.tipo} data-invalido={erro ? "1" : undefined}>
      <div className="regras-bloco-topo">
        <span className="regras-bloco-tipo">{ROTULO_TIPO[bloco.tipo]}</span>
        <button type="button" className="ghost small icon" aria-label={`Remover condição ${ROTULO_TIPO[bloco.tipo]}`} title="Remover condição" onClick={() => ctx.aoEditar(trilha, () => null)}>
          <IconeFechar aria-hidden="true" />
        </button>
      </div>
      <ControlesDoBloco
        bloco={bloco}
        ctx={ctx}
        invalido={Boolean(erro)}
        descricao={erro ? idErro : undefined}
        mudar={(patch) => ctx.aoEditar(trilha, (no) => ({ ...no, ...patch }) as No)}
      />
      <ErroInline id={idErro} texto={erro} />
    </li>
  );
}

function GrupoEditor({ grupo, caminho, trilha, profundidade, ctx }: { grupo: Grupo; caminho: string; trilha: number[]; profundidade: number; ctx: ContextoDoEditor }) {
  const raiz = trilha.length === 0;
  const erro = ctx.erro && [caminho, `${caminho}.op`, `${caminho}.itens`].includes(ctx.erro.caminho) ? ctx.erro.texto : null;
  const idErro = `${idSeguro(caminho)}-erro`;
  const semBlocos = ctx.totalBlocos >= ctx.limites.blocos;
  const semNivel = profundidade >= ctx.limites.profundidade;
  const motivoBloco = semBlocos ? `Limite de ${pluralizar(ctx.limites.blocos, "bloco")} por regra atingido.` : undefined;
  const motivoGrupo = semBlocos
    ? motivoBloco
    : semNivel
      ? `Limite de ${pluralizar(ctx.limites.profundidade, "nível", "níveis")} de grupo atingido.`
      : undefined;
  const nome = raiz ? "Condições da regra" : `Grupo ${trilha.map((i) => i + 1).join(".")}`;
  return (
    <div className={`regras-grupo${raiz ? " raiz" : ""}`} role="group" aria-label={nome} data-invalido={erro ? "1" : undefined}>
      <div className="regras-grupo-topo">
        <label className="regras-op">
          <span>{raiz ? "Combinar" : `Combinar no grupo ${trilha.map((i) => i + 1).join(".")}`}</span>
          <select
            value={grupo.op}
            aria-invalid={erro ? true : undefined}
            aria-describedby={erro ? idErro : undefined}
            onChange={(e) => ctx.aoEditar(trilha, (no) => ({ ...(no as Grupo), op: e.target.value as Operador }))}
          >
            <option value="E">Todas as condições (E)</option>
            <option value="OU">Qualquer condição (OU)</option>
          </select>
        </label>
        {!raiz && (
          <button type="button" className="ghost small" aria-label={`Remover ${nome}`} onClick={() => ctx.aoEditar(trilha, () => null)}>
            Remover grupo
          </button>
        )}
      </div>
      {grupo.itens.length === 0 && <p className="regras-dica">Este grupo está vazio. Adicione uma condição.</p>}
      <ul className="regras-itens">
        {grupo.itens.map((item, i) => {
          const sub = `${caminho}.itens[${i}]`;
          return ehGrupo(item) ? (
            <li key={item.k} className="regras-item-grupo">
              <GrupoEditor grupo={item} caminho={sub} trilha={[...trilha, i]} profundidade={profundidade + 1} ctx={ctx} />
            </li>
          ) : (
            <BlocoEditor key={item.k} bloco={item} caminho={sub} trilha={[...trilha, i]} ctx={ctx} />
          );
        })}
      </ul>
      <ErroInline id={idErro} texto={erro} />
      <div className="regras-grupo-acoes">
        <MenuCondicao
          desabilitado={semBlocos}
          titulo={motivoBloco}
          onEscolher={(tipo) => ctx.aoEditar(trilha, (no) => ({ ...(no as Grupo), itens: [...(no as Grupo).itens, blocoPadrao(tipo, ctx.opcoes)] }))}
        />
        <button
          type="button"
          className="small"
          disabled={semBlocos || semNivel}
          title={motivoGrupo}
          onClick={() =>
            ctx.aoEditar(trilha, (no) => ({
              ...(no as Grupo),
              itens: [...(no as Grupo).itens, { k: novaChave(), op: "E", itens: [blocoPadrao("zona", ctx.opcoes)] } as Grupo],
            }))
          }
        >
          <IconeMais aria-hidden="true" /> Grupo
        </button>
      </div>
      {(semBlocos || semNivel) && <p className="regras-dica regras-limite">{motivoGrupo}</p>}
    </div>
  );
}

// ------------------------------------------------------------- resultado ---
function rotuloDeBalde(segundos: number): string {
  const minutos = segundos / 60;
  if (minutos < 1) return `${inteiro(Math.round(segundos))} s`;
  return `${Number.isInteger(minutos) ? inteiro(minutos) : decimal(minutos, 1)} min`;
}

function LinhaDoTempo({ resultado }: { resultado: ResultadoTeste }) {
  const linha = resultado.linha_do_tempo;
  const [inicio, fim] = resultado.janela;
  const mesmoDia = new Date(inicio * 1000).toDateString() === new Date(fim * 1000).toDateString();
  const rotulo = (t: number) => (mesmoDia ? horaCurta(new Date(t * 1000)) : dataHoraCurta(new Date(t * 1000)));
  const maximo = Math.max(1, ...linha.map(([, n]) => n));
  const pico = linha.reduce<[number, number] | null>((melhor, atual) => (atual[1] > (melhor?.[1] ?? 0) ? atual : melhor), null);
  if (!linha.length) return null;
  return (
    <div className="regras-linha" data-testid="regras-linha-do-tempo">
      <div
        className="regras-barras"
        role="img"
        aria-label={`Linha do tempo: ${pluralizar(resultado.disparos, "disparo")} em ${pluralizar(linha.length, "intervalo")}${pico ? `; maior concentração às ${horaCurta(new Date(pico[0] * 1000))}` : ""}`}
      >
        {linha.map(([t, n]) => (
          <span key={t} className="regras-barra-coluna" title={`${rotulo(t)}: ${pluralizar(n, "disparo")}`}>
            {n > 0 && <span className="regras-barra" style={{ height: `${Math.max(6, (n / maximo) * 100)}%` }} />}
          </span>
        ))}
      </div>
      <div className="regras-eixo" aria-hidden="true">
        <span>{rotulo(inicio)}</span>
        <span>{rotulo(inicio + (fim - inicio) / 2)}</span>
        <span>{rotulo(fim)}</span>
      </div>
      <p className="regras-dica">
        {resultado.balde_s ? `Cada barra soma ${rotuloDeBalde(resultado.balde_s)}. ` : ""}
        {pico ? `Maior concentração: ${pluralizar(pico[1], "disparo")} às ${horaCurta(new Date(pico[0] * 1000))}.` : "Nenhum disparo na janela."}
      </p>
    </div>
  );
}

/** O resultado de "Testar no histórico", igual ao do editor: números reais, ou o motivo real de não poder testar. */
export function Resultado({ resultado, obsoleto }: { resultado: ResultadoTeste; obsoleto: boolean }) {
  const [inicio, fim] = resultado.janela;
  const janela = `${dataHoraCurta(new Date(inicio * 1000))} a ${dataHoraCurta(new Date(fim * 1000))}`;
  return (
    <div className="regras-resultado-corpo">
      {obsoleto && <p className="regras-aviso" role="note">A regra mudou depois deste teste. Teste de novo para ver o efeito das mudanças.</p>}
      {!resultado.simulavel ? (
        <div className="regras-nao-simulavel" data-testid="regras-nao-simulavel">
          <h4>Esta regra não pode ser testada no histórico</h4>
          <p>{resultado.motivo}</p>
          <p className="regras-dica">Nenhum resultado foi calculado. Você ainda pode salvar a regra, mas ela só será vista em ação ao vivo.</p>
        </div>
      ) : (
        <>
          <dl className="regras-numeros">
            <div>
              <dt>Disparos</dt>
              <dd data-testid="regras-disparos">{inteiro(resultado.disparos)}</dd>
            </div>
            <div>
              <dt>Pessoas vistas</dt>
              <dd>{inteiro(resultado.pessoas)}</dd>
            </div>
            <div>
              <dt>Incidentes</dt>
              <dd>{resultado.incidentes == null ? "sem dado" : inteiro(resultado.incidentes)}</dd>
            </div>
          </dl>
          <p className="regras-dica">
            {resultado.registros === 0
              ? "A câmera não tem análise gravada nessa janela: o zero acima não quer dizer que a regra está calma."
              : `Janela ${janela}${resultado.registros != null ? `, ${pluralizar(resultado.registros, "análise gravada", "análises gravadas")}` : ""}. Um disparo é um alerta que seria criado depois da confirmação do sistema, um por pessoa.`}
          </p>
          <LinhaDoTempo resultado={resultado} />
        </>
      )}
    </div>
  );
}

// ------------------------------------------------------- modo leitura ---
/** A regra no formato do editor, sem o que o servidor acrescenta (id, origem...). Vem do roteiro do palco. */
export type RegraDeExemplo = Pick<RegraApi, "nome" | "camera_ids" | "condicao" | "acoes">;

function leituraDoBloco(b: Bloco, opcoes: Opcoes): string {
  const texto = b.tipo === "duracao" ? `por ${duracaoTexto(b.segundos ?? 0)}` : textoDoBloco(b, opcoes);
  return texto.charAt(0).toUpperCase() + texto.slice(1);
}

function NoEmLeitura({ no, opcoes, raiz }: { no: Grupo; opcoes: Opcoes; raiz: boolean }) {
  return (
    <div className={`regras-grupo${raiz ? " raiz" : ""}`} role="group" aria-label={raiz ? "Condições da regra" : "Grupo de condições"}>
      <p className="regras-op-leitura">{no.op === "E" ? "Todas as condições (E)" : "Qualquer condição (OU)"}</p>
      <ul className="regras-itens">
        {no.itens.map((item) =>
          ehGrupo(item) ? (
            <li key={item.k} className="regras-item-grupo">
              <NoEmLeitura no={item} opcoes={opcoes} raiz={false} />
            </li>
          ) : (
            <li key={item.k} className="regras-bloco" data-tipo={item.tipo}>
              <div className="regras-bloco-topo">
                <span className="regras-bloco-tipo">{ROTULO_TIPO[item.tipo]}</span>
              </div>
              <p className="regras-bloco-leitura">{leituraDoBloco(item, opcoes)}</p>
            </li>
          ),
        )}
      </ul>
    </div>
  );
}

/**
 * A regra montada em blocos, só para ler (o palco mostra; quem edita é `/regras`). Usa os mesmos
 * rótulos, a mesma frase ("Como a regra se lê") e o mesmo estilo dos blocos do editor.
 */
export function RegraEmBlocos({ regra, opcoes, nomesCameras }: { regra: RegraDeExemplo; opcoes: Opcoes; nomesCameras?: Map<number, string> }) {
  const rascunho = rascunhoDaRegra({ ...regra, id: "exemplo", ativa: false, origem: "usuario", regra_id: "regra:exemplo", protegida: false });
  return (
    <div className="regras-leitura" data-testid="regra-em-blocos">
      <div className="regras-frase-caixa">
        <p className="regras-frase-rotulo">Como a regra se lê</p>
        <p className="regras-frase" data-testid="regras-frase">{fraseDaRegra(rascunho, opcoes, nomesCameras ?? new Map())}</p>
      </div>
      <NoEmLeitura no={rascunho.condicao} opcoes={opcoes} raiz />
    </div>
  );
}

// ------------------------------------------------------------------ tela ---
export default function RegrasScreen() {
  const cameras = useDashboardStore((s) => s.cameras);
  const [dados, setDados] = useState<Listagem | null>(null);
  const [erroCarga, setErroCarga] = useState<{ msg: string; status?: number } | null>(null);
  const [rascunho, setRascunho] = useState<Rascunho | null>(null);
  const [base, setBase] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [erroSalvar, setErroSalvar] = useState<ErroDoServidor | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [falha, setFalha] = useState<string | null>(null);
  const [ocupadas, setOcupadas] = useState<Set<string>>(new Set());
  const [excluindo, setExcluindo] = useState<RegraApi | null>(null);
  const [excluindoAgora, setExcluindoAgora] = useState(false);
  const [descartar, setDescartar] = useState<{ acao: () => void } | null>(null);
  const [nativasAbertas, setNativasAbertas] = useState<boolean | null>(null);

  const [cameraTeste, setCameraTeste] = useState("");
  const [horas, setHoras] = useState("1");
  const [testando, setTestando] = useState(false);
  const [resultado, setResultado] = useState<{ dados: ResultadoTeste; chave: string } | null>(null);
  const [erroTeste, setErroTeste] = useState<string | null>(null);

  const carregar = useCallback(async () => {
    try {
      const d = await pedir<Listagem>("/api/regras");
      setDados(d);
      setErroCarga(null);
    } catch (e) {
      const erro = e as ErroDeRede;
      setErroCarga({ msg: mensagemDeErro(erro, "Não foi possível carregar as regras."), status: erro.status });
    }
  }, []);
  useEffect(() => {
    void carregar();
  }, [carregar]);

  const nomesCameras = useMemo(() => new Map(cameras.map((c) => [c.id, c.name])), [cameras]);
  const corpo = useMemo(() => (rascunho ? JSON.stringify(corpoDoRascunho(rascunho)) : ""), [rascunho]);
  const sujo = Boolean(rascunho && !rascunho.protegida && corpo !== base);

  const abrir = useCallback((r: Rascunho) => {
    setRascunho(r);
    setBase(JSON.stringify(corpoDoRascunho(r)));
    setErroSalvar(null);
    setAviso(null);
    setFalha(null);
    setResultado(null);
    setErroTeste(null);
  }, []);

  /** Antes de trocar de regra com alterações não salvas, pergunta. */
  const comConfirmacao = (acao: () => void) => (sujo ? setDescartar({ acao }) : acao());

  const mudar = (patch: Partial<Rascunho>) => {
    setErroSalvar(null);
    setRascunho((r) => (r ? { ...r, ...patch } : r));
  };
  const editarCondicao = useCallback((trilha: number[], fn: (no: No) => No | null) => {
    setErroSalvar(null);
    setRascunho((r) => (r ? { ...r, condicao: alterar(r.condicao, trilha, fn) } : r));
  }, []);

  const marcarOcupada = (id: string, ligada: boolean) =>
    setOcupadas((atual) => {
      const novo = new Set(atual);
      if (ligada) novo.add(id);
      else novo.delete(id);
      return novo;
    });

  const alternar = async (regra: { id: string; nome: string }, ligar: boolean) => {
    marcarOcupada(regra.id, true);
    setFalha(null);
    try {
      const { regra: nova } = await pedir<{ regra: RegraApi }>(`/api/regras/${regra.id}/${ligar ? "ativar" : "desativar"}`, { method: "POST", body: "{}" });
      setDados((d) => (d ? { ...d, regras: d.regras.map((r) => (r.id === nova.id ? nova : r)) } : d));
      setRascunho((r) => (r && r.id === nova.id ? { ...r, ativa: nova.ativa } : r));
      setBase((b) => {
        try {
          const o = JSON.parse(b) as { id?: string; ativa?: boolean };
          return o.id === nova.id ? JSON.stringify({ ...o, ativa: nova.ativa }) : b;
        } catch {
          return b;
        }
      });
    } catch (e) {
      const erro = e as ErroDeRede;
      setFalha(erro.status === 403 ? MSG_403 : mensagemDeErro(erro, `Não foi possível ${ligar ? "ativar" : "desativar"} a regra.`));
    } finally {
      marcarOcupada(regra.id, false);
    }
  };

  const salvar = async () => {
    if (!rascunho || rascunho.protegida) return;
    if (rascunho.camera_ids !== null && rascunho.camera_ids.length === 0) {
      setErroSalvar({ caminho: "camera_ids", texto: "escolha pelo menos uma câmera ou use Todas as câmeras" });
      return;
    }
    setSalvando(true);
    setErroSalvar(null);
    setAviso(null);
    try {
      const novo = rascunho.id === null;
      const { regra } = await pedir<{ regra: RegraApi }>(novo ? "/api/regras" : `/api/regras/${rascunho.id}`, {
        method: novo ? "POST" : "PUT",
        body: JSON.stringify(corpoDoRascunho(rascunho)),
      });
      setDados((d) => (d ? { ...d, regras: novo ? [...d.regras, regra] : d.regras.map((r) => (r.id === regra.id ? regra : r)) } : d));
      const salvo = rascunhoDaRegra(regra);
      setRascunho(salvo);
      setBase(JSON.stringify(corpoDoRascunho(salvo)));
      setAviso(novo ? "Regra criada, ainda desativada. Teste no histórico e ative quando fizer sentido." : "Alterações salvas.");
    } catch (e) {
      const erro = e as ErroDeRede;
      if (erro.status === 400) setErroSalvar(lerErro(erro.message));
      else if (erro.code === "regra_protegida")
        setErroSalvar({ caminho: "", texto: "Esta é uma regra nativa: ela já roda no sistema e não pode ser editada nem excluída. Duplique e edite a cópia." });
      else if (erro.status === 404) {
        setErroSalvar({ caminho: "", texto: "Esta regra não existe mais. A lista foi atualizada." });
        void carregar();
      } else setErroSalvar({ caminho: "", texto: erro.status === 403 ? MSG_403 : mensagemDeErro(erro, "Não foi possível salvar a regra.") });
    } finally {
      setSalvando(false);
    }
  };

  const excluir = async () => {
    if (!excluindo) return;
    setExcluindoAgora(true);
    try {
      await pedir(`/api/regras/${excluindo.id}`, { method: "DELETE" });
      setDados((d) => (d ? { ...d, regras: d.regras.filter((r) => r.id !== excluindo.id) } : d));
      if (rascunho?.id === excluindo.id) {
        setRascunho(null);
        setBase("");
        setResultado(null);
      }
      setFalha(null);
      setAviso(`Regra "${excluindo.nome}" excluída.`);
    } catch (e) {
      const erro = e as ErroDeRede;
      setFalha(
        erro.code === "regra_protegida"
          ? "Regra nativa não pode ser excluída: ela já roda no sistema."
          : erro.status === 403 ? MSG_403 : mensagemDeErro(erro, "Não foi possível excluir a regra."),
      );
    } finally {
      setExcluindo(null);
      setExcluindoAgora(false);
    }
  };

  const cameraEscolhida = cameraTeste || String(cameras[0]?.id ?? "");
  const testar = async () => {
    if (!rascunho) return;
    const h = Number(horas);
    if (!Number.isInteger(h) || h < 1 || h > 24) {
      setErroTeste("Informe a janela em horas inteiras, de 1 a 24.");
      return;
    }
    if (rascunho.camera_ids !== null && rascunho.camera_ids.length === 0) {
      setErroTeste("Escolha pelo menos uma câmera onde a regra vale, ou use Todas as câmeras.");
      return;
    }
    setTestando(true);
    setErroTeste(null);
    const enviado = corpoDoRascunho(rascunho);
    const { id: _id, ...regra } = enviado as typeof enviado & { id?: string };
    try {
      const r = await pedir<ResultadoTeste>("/api/regras/testar", {
        method: "POST",
        body: JSON.stringify({ regra: rascunho.nome.trim() ? regra : { ...regra, nome: undefined }, camera_id: Number(cameraEscolhida), horas: h }),
      });
      setResultado({ dados: r, chave: corpo });
    } catch (e) {
      const erro = e as ErroDeRede;
      setResultado(null);
      setErroTeste(erro.status === 403 ? MSG_403 : mensagemDeErro(erro, "Não foi possível testar a regra."));
    } finally {
      setTestando(false);
    }
  };

  // ---- estados da tela inteira ----
  if (erroCarga?.status === 403) {
    return (
      <div className="screen regras">
        <EmptyState ilustracao={<IlustracaoEscudo />} titulo="Acesso restrito">{MSG_403} Peça a quem tem esse perfil.</EmptyState>
      </div>
    );
  }
  if (!dados) {
    return (
      <div className="screen regras" aria-busy={!erroCarga}>
        <header className="screen-head"><h1>Regras de alerta</h1></header>
        {erroCarga ? (
          <div className="regras-erro-tela" role="alert">
            <p>{erroCarga.msg}</p>
            <button type="button" onClick={() => void carregar()}>Tentar de novo</button>
          </div>
        ) : (
          <div className="regras-grade" data-testid="regras-carregando">
            <div className="card regras-painel"><PanelSkeleton lines={7} /></div>
            <div className="card regras-painel"><PanelSkeleton lines={9} /></div>
          </div>
        )}
      </div>
    );
  }

  const { opcoes, limites } = dados;
  const usuario = dados.regras.filter((r) => r.origem === "usuario");
  const nativas = dados.regras.filter((r) => r.origem === "pre_carregada");
  const nativasVisiveis = nativasAbertas ?? usuario.length === 0;
  const totalBlocos = rascunho ? contarBlocos(rascunho.condicao) : 0;
  const frase = rascunho ? fraseDaRegra(rascunho, opcoes, nomesCameras) : "";
  const ctx: ContextoDoEditor | null = rascunho
    ? { opcoes, limites, totalBlocos, erro: erroSalvar, aoEditar: editarCondicao }
    : null;
  const erroEm = (caminho: string) => (erroSalvar && (erroSalvar.caminho === caminho || erroSalvar.caminho.startsWith(`${caminho}.`)) ? erroSalvar.texto : null);
  const desabilitado = rascunho?.protegida ?? false;
  const novaRegra = () => comConfirmacao(() => abrir(rascunhoNovo(opcoes)));

  return (
    <div className="screen regras" data-testid="regras">
      <header className="screen-head">
        <h1>Regras de alerta</h1>
        <p className="screen-sub">Monte a regra com blocos, teste no histórico e só depois ative.</p>
        <div className="screen-actions">
          <button type="button" className="primary" onClick={novaRegra}><IconeMais aria-hidden="true" /> Criar regra</button>
        </div>
      </header>

      {falha && <p className="regras-erro-tela" role="alert">{falha}</p>}
      {aviso && !sujo && <p className="regras-sucesso" role="status">{aviso}</p>}

      <div className="regras-grade">
        {/* ---------------------------------------------------------- lista ---- */}
        <aside className="card regras-painel regras-lista" data-testid="regras-lista" aria-label="Lista de regras">
          <h2 className="regras-titulo-secao">Minhas regras</h2>
          {usuario.length === 0 ? (
            <p className="regras-dica">Você ainda não criou nenhuma regra.</p>
          ) : (
            <ul className="regras-linhas">
              {usuario.map((r) => {
                const ocupada = ocupadas.has(r.id);
                const selecionada = rascunho?.id === r.id;
                return (
                  <li key={r.id} className={`regras-linha-item${selecionada ? " sel" : ""}`} data-ativa={r.ativa ? "1" : "0"}>
                    <div className="regras-linha-topo">
                      <button type="button" className="regras-corpo" aria-current={selecionada ? "true" : undefined} onClick={() => comConfirmacao(() => abrir(rascunhoDaRegra(r)))}>
                        <span className="regras-nome">{r.nome}</span>
                        <span className="regras-meta">Severidade {(ROTULO_SEVERIDADE[r.acoes.severidade] ?? r.acoes.severidade).toLowerCase()} · {r.ativa ? "ativa" : "desativada"}</span>
                      </button>
                      <Interruptor ligado={r.ativa} ocupado={ocupada} nome={`Regra ${r.nome} ativa`} onAlternar={() => void alternar(r, !r.ativa)} />
                    </div>
                    <div className="regras-linha-acoes">
                      <button type="button" className="ghost small" onClick={() => comConfirmacao(() => abrir(rascunhoDaRegra(r)))} aria-label={`Editar regra ${r.nome}`}>Editar</button>
                      <button type="button" className="ghost small regras-excluir" onClick={() => setExcluindo(r)} aria-label={`Excluir regra ${r.nome}`}>Excluir</button>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}

          <details className="regras-nativas" open={nativasVisiveis} onToggle={(e) => setNativasAbertas((e.currentTarget as HTMLDetailsElement).open)}>
            <summary>Regras nativas ({nativas.length})</summary>
            {nativas.length === 0 ? (
              <p className="regras-dica">Nenhuma regra nativa listada.</p>
            ) : (
              <ul className="regras-linhas">
                {nativas.map((r) => {
                  const selecionada = rascunho?.id === r.id;
                  return (
                    <li key={r.id} className={`regras-linha-item${selecionada ? " sel" : ""}`}>
                      <button type="button" className="regras-corpo" aria-current={selecionada ? "true" : undefined} onClick={() => comConfirmacao(() => abrir(rascunhoDaRegra(r)))}>
                        <span className="regras-nome">{r.nome}</span>
                        <span className="regras-meta">Nativa, já em execução</span>
                      </button>
                      <div className="regras-linha-acoes">
                        <button type="button" className="ghost small" aria-label={`Duplicar para editar a regra ${r.nome}`} onClick={() => comConfirmacao(() => abrir(duplicar(rascunhoDaRegra(r))))}>
                          Duplicar para editar
                        </button>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </details>
        </aside>

        {/* --------------------------------------------------------- editor ---- */}
        <section className="regras-direita" aria-label="Editor da regra">
          {!rascunho || !ctx ? (
            <div className="card regras-painel" data-testid="regras-editor" data-vazio="1">
              <EmptyState
                ilustracao={<IlustracaoEscudo />}
                titulo={usuario.length === 0 ? "Você ainda não criou regras" : "Nenhuma regra aberta"}
                acao={<button type="button" className="primary" onClick={novaRegra}>Criar regra</button>}
              >
                {usuario.length === 0
                  ? "Crie uma regra com blocos de condição, veja quantas vezes ela teria disparado no histórico e ative quando fizer sentido."
                  : "Escolha uma regra na lista para editar, ou crie uma nova."}
              </EmptyState>
            </div>
          ) : (
            <div className="card regras-painel regras-editor" data-testid="regras-editor" data-protegida={rascunho.protegida ? "1" : "0"}>
              <div className="regras-editor-topo">
                <div>
                  <h2>{rascunho.id === null ? "Nova regra" : rascunho.nome || "Regra sem nome"}</h2>
                  {rascunho.protegida && <Badge>Nativa, já em execução</Badge>}
                  {!rascunho.protegida && rascunho.id !== null && <Badge tone={rascunho.ativa ? "ok" : "neutral"}>{rascunho.ativa ? "Ativa" : "Desativada"}</Badge>}
                  {rascunho.id === null && <Badge>Ainda não salva</Badge>}
                </div>
                {!rascunho.protegida && rascunho.id !== null && (
                  <label className="regras-liga">
                    <span>Regra ativa</span>
                    <Interruptor
                      ligado={rascunho.ativa}
                      ocupado={ocupadas.has(rascunho.id)}
                      nome={`Regra ${rascunho.nome || "sem nome"} ativa`}
                      onAlternar={() => void alternar({ id: rascunho.id as string, nome: rascunho.nome }, !rascunho.ativa)}
                    />
                  </label>
                )}
              </div>

              <div className="regras-frase-caixa">
                <p className="regras-frase-rotulo">Como a regra se lê</p>
                <p className="regras-frase" data-testid="regras-frase">{frase}</p>
              </div>

              {rascunho.protegida && (
                <div className="regras-nativa-nota" role="note">
                  <p>Esta regra nativa já está em execução e não pode ser editada nem excluída. Para mudar o comportamento, duplique e edite a cópia.</p>
                  <button type="button" className="primary small" onClick={() => comConfirmacao(() => abrir(duplicar(rascunho)))}>Duplicar para editar</button>
                </div>
              )}

              {erroSalvar && (
                <p className="regras-erro-tela" role="alert">
                  {erroSalvar.caminho ? `Não foi possível salvar: ${erroSalvar.texto}.` : erroSalvar.texto}
                </p>
              )}

              <fieldset className="regras-conjunto" disabled={desabilitado}>
                <legend className="regras-visualmente-oculto">Definição da regra</legend>

                <div className="regras-secao">
                  <Campo rotulo="Nome da regra">
                    <input
                      type="text"
                      value={rascunho.nome}
                      placeholder="Ex.: Sem capacete na zona de risco"
                      aria-invalid={erroEm("nome") ? true : undefined}
                      aria-describedby={erroEm("nome") ? "regras-nome-erro" : undefined}
                      onChange={(e) => mudar({ nome: e.target.value })}
                    />
                  </Campo>
                  <ErroInline id="regras-nome-erro" texto={erroEm("nome")} />
                </div>

                <div className="regras-secao" role="group" aria-labelledby="regras-sec-quando">
                  <h3 id="regras-sec-quando">Quando</h3>
                  <GrupoEditor grupo={rascunho.condicao} caminho="condicao" trilha={[]} profundidade={1} ctx={ctx} />
                  <p className="regras-dica">Blocos usados: {inteiro(totalBlocos)} de {inteiro(limites.blocos)}.</p>
                </div>

                <div className="regras-secao" role="group" aria-labelledby="regras-sec-entao">
                  <h3 id="regras-sec-entao">Então</h3>
                  <div className="regras-campos">
                    <Campo rotulo="Severidade">
                      <select
                        value={rascunho.severidade}
                        aria-invalid={erroEm("acoes.severidade") ? true : undefined}
                        onChange={(e) => mudar({ severidade: e.target.value })}
                      >
                        {opcoes.severidades.map((s) => (
                          <option key={s} value={s}>{ROTULO_SEVERIDADE[s] ?? s}</option>
                        ))}
                      </select>
                    </Campo>
                    <div>
                      <Campo rotulo="Mensagem do alerta">
                        <input
                          type="text"
                          value={rascunho.mensagem}
                          placeholder="Ex.: Pessoa sem capacete na zona"
                          aria-invalid={erroEm("acoes.mensagem") ? true : undefined}
                          aria-describedby={erroEm("acoes.mensagem") ? "regras-mensagem-erro" : undefined}
                          onChange={(e) => mudar({ mensagem: e.target.value })}
                        />
                      </Campo>
                      <ErroInline id="regras-mensagem-erro" texto={erroEm("acoes.mensagem")} />
                    </div>
                  </div>
                  <div className="regras-checks">
                    <label className="regras-check">
                      <input type="checkbox" checked={rascunho.fala} onChange={(e) => mudar({ fala: e.target.checked })} />
                      <span>Falar o alerta</span>
                    </label>
                    <label className="regras-check">
                      <input type="checkbox" checked={rascunho.integracao} onChange={(e) => mudar({ integracao: e.target.checked })} />
                      <span>Enviar para a integração (OPC UA/MQTT)</span>
                    </label>
                  </div>
                  <div className="regras-campos">
                    <div>
                      <Campo rotulo="Escalar ao supervisor após (segundos)">
                        <input
                          type="number"
                          inputMode="numeric"
                          min={1}
                          step={1}
                          value={rascunho.supervisor_s ?? ""}
                          aria-invalid={erroEm("acoes.escalonamento.supervisor_s") ? true : undefined}
                          aria-describedby={erroEm("acoes.escalonamento.supervisor_s") ? "regras-sup-erro" : undefined}
                          onChange={(e) => mudar({ supervisor_s: e.target.value === "" ? null : Number(e.target.value) })}
                        />
                      </Campo>
                      <ErroInline id="regras-sup-erro" texto={erroEm("acoes.escalonamento.supervisor_s")} />
                    </div>
                    <div>
                      <Campo rotulo="Escalar à TV e à torre após (segundos)">
                        <input
                          type="number"
                          inputMode="numeric"
                          min={1}
                          step={1}
                          value={rascunho.tv_s ?? ""}
                          aria-invalid={erroEm("acoes.escalonamento.tv_s") ? true : undefined}
                          aria-describedby={erroEm("acoes.escalonamento.tv_s") ? "regras-tv-erro" : undefined}
                          onChange={(e) => mudar({ tv_s: e.target.value === "" ? null : Number(e.target.value) })}
                        />
                      </Campo>
                      <ErroInline id="regras-tv-erro" texto={erroEm("acoes.escalonamento.tv_s")} />
                    </div>
                  </div>
                  <p className="regras-dica">Deixe vazio para não escalonar.</p>
                </div>

                <div className="regras-secao" role="group" aria-labelledby="regras-sec-onde">
                  <h3 id="regras-sec-onde">Onde vale</h3>
                  <div className="regras-checks">
                    <label className="regras-check">
                      <input type="radio" name="regras-escopo" checked={rascunho.camera_ids === null} onChange={() => mudar({ camera_ids: null })} />
                      <span>Todas as câmeras</span>
                    </label>
                    <label className="regras-check">
                      <input type="radio" name="regras-escopo" checked={rascunho.camera_ids !== null} onChange={() => mudar({ camera_ids: rascunho.camera_ids ?? [] })} />
                      <span>Só algumas câmeras</span>
                    </label>
                  </div>
                  {rascunho.camera_ids !== null && (
                    <div className="regras-cameras" role="group" aria-label="Câmeras onde a regra vale">
                      {cameras.length === 0 ? (
                        <p className="regras-dica">Nenhuma câmera cadastrada.</p>
                      ) : (
                        cameras.map((c) => (
                          <label key={c.id} className="regras-check">
                            <input
                              type="checkbox"
                              checked={rascunho.camera_ids?.includes(c.id) ?? false}
                              onChange={(e) =>
                                mudar({
                                  camera_ids: e.target.checked
                                    ? [...(rascunho.camera_ids ?? []), c.id]
                                    : (rascunho.camera_ids ?? []).filter((id) => id !== c.id),
                                })
                              }
                            />
                            <span>{c.name}</span>
                          </label>
                        ))
                      )}
                    </div>
                  )}
                  <ErroInline id="regras-camera-erro" texto={erroEm("camera_ids")} />
                </div>
              </fieldset>

              {/* ---- testar no histórico (também vale para a regra nativa) ---- */}
              <div className="regras-secao regras-teste" role="group" aria-labelledby="regras-sec-teste">
                <h3 id="regras-sec-teste">Testar no histórico</h3>
                <p className="regras-dica">Reprocessa a trilha gravada da câmera com esta regra. Não cria nem muda nenhum alerta real.</p>
                <div className="regras-campos regras-teste-campos">
                  <Campo rotulo="Câmera">
                    <select value={cameraEscolhida} onChange={(e) => setCameraTeste(e.target.value)} disabled={cameras.length === 0}>
                      {cameras.map((c) => (
                        <option key={c.id} value={c.id}>{c.name}</option>
                      ))}
                    </select>
                  </Campo>
                  <Campo rotulo="Janela (horas, de 1 a 24)">
                    <input type="number" inputMode="numeric" min={1} max={24} step={1} value={horas} onChange={(e) => setHoras(e.target.value)} />
                  </Campo>
                  <button type="button" className="primary regras-botao-teste" data-testid="regras-testar" onClick={() => void testar()} disabled={testando || cameras.length === 0}>
                    {testando ? "Testando…" : "Testar no histórico"}
                  </button>
                </div>
                {cameras.length === 0 && <p className="regras-dica">Cadastre uma câmera para poder testar.</p>}
                <div
                  className="regras-resultado"
                  data-testid="regras-resultado"
                  data-estado={testando ? "carregando" : erroTeste ? "erro" : resultado ? (resultado.dados.simulavel ? "pronto" : "nao-simulavel") : "vazio"}
                  aria-live="polite"
                  aria-busy={testando}
                >
                  {testando ? (
                    <p className="regras-dica">Lendo a trilha gravada…</p>
                  ) : erroTeste ? (
                    <div className="regras-erro-tela" role="alert">
                      <p>{erroTeste}</p>
                      <button type="button" className="small" onClick={() => void testar()}>Tentar de novo</button>
                    </div>
                  ) : resultado ? (
                    <Resultado resultado={resultado.dados} obsoleto={resultado.chave !== corpo} />
                  ) : null}
                </div>
              </div>

              {!rascunho.protegida && (
                <div className="regras-barra">
                  <button type="button" className="ghost" onClick={() => comConfirmacao(() => setRascunho(null))} disabled={salvando}>Fechar</button>
                  <button type="button" className="primary" data-testid="regras-salvar" onClick={() => void salvar()} disabled={salvando || (rascunho.id !== null && !sujo)}>
                    {salvando ? "Salvando…" : rascunho.id === null ? "Criar regra" : "Salvar alterações"}
                  </button>
                </div>
              )}
            </div>
          )}
        </section>
      </div>

      {excluindo && (
        <Confirmar
          titulo="Excluir a regra?"
          texto={`A regra "${excluindo.nome}" deixa de valer agora e não pode ser recuperada.`}
          acao="Excluir regra"
          tom="danger"
          ocupado={excluindoAgora}
          onNao={() => setExcluindo(null)}
          onSim={() => void excluir()}
        />
      )}
      {descartar && (
        <Confirmar
          titulo="Descartar as alterações?"
          texto="Há alterações não salvas nesta regra. Se continuar, elas se perdem."
          acao="Descartar alterações"
          tom="danger"
          ocupado={false}
          onNao={() => setDescartar(null)}
          onSim={() => {
            const { acao } = descartar;
            setDescartar(null);
            acao();
          }}
        />
      )}
    </div>
  );
}

export { RegrasScreen };
