import { useEffect, useId, useMemo, useRef, useState } from "react";
import type { FormEvent, KeyboardEvent as TeclaReact, PointerEvent as PonteiroReact, ReactNode } from "react";
import { ApiError, apiFetch } from "../api/client";
import { PPE_KEYS, PPE_LABELS } from "../api/ppe";
import type { PpeKey } from "../api/ppe";
import type { CameraRecord } from "../api/types";
import { useDashboardStore } from "../store/dashboardStore";
import { dataHoraCurta, horaCurta, paraDate } from "../utils/datas";
import { mensagemDeErro } from "../utils/erros";
import { useFecharComEsc } from "../utils/teclado";
import { Badge, EmptyState, PanelSkeleton } from "./common";
import { IlustracaoPlanta } from "./ilustracoes";
import "../styles/permissoes.css";

/**
 * Permissão de Trabalho digital (M5). Contrato: app/api/permissoes.py e
 * app/services/permissoes.py. A câmera auxilia o vigia; não o substitui, e só
 * fiscaliza os EPIs que o modelo detecta (o resto é "verificação manual").
 * O responsável é texto livre: não é vinculado às pessoas detectadas.
 *
 * `AreaDoVigia` é uma versão própria e pequena do editor de polígono do
 * simulador (`EditorDeZona`, que não é exportado e não adiciona pontos).
 * Unificar depois num componente só.
 */

type TipoPt = "espaco_confinado" | "altura" | "geral";
type StatusPt = "ativa" | "encerrada" | "cancelada";
type Ponto = [number, number];

interface Permissao {
  id: number;
  numero: string;
  camera_id: number;
  tipo: TipoPt;
  descricao: string;
  responsavel: string;
  inicio: string;
  fim: string;
  epis_exigidos: string[];
  exige_vigia: boolean;
  area_vigia: Ponto[] | null;
  status: StatusPt;
  vigente: boolean | null;
  criada_por: string;
  criada_em: string | null;
  encerrada_em: string | null;
  encerrada_por: string | null;
}
interface ItemDeChecklist {
  epi: string;
  rotulo: string;
  verificacao: "automatica" | "manual";
}
interface Norma {
  codigo: string;
  url: string;
  itens: { item: string; texto: string }[];
}
interface PermissaoDetalhe extends Permissao {
  checklist: ItemDeChecklist[];
  norma: Norma | null;
}
interface PermissaoEmitida extends PermissaoDetalhe {
  avisos: string[];
}

const TIPOS: Record<TipoPt, string> = {
  espaco_confinado: "Espaço confinado",
  altura: "Trabalho em altura",
  geral: "Geral",
};
const ORDEM_DE_TIPOS: TipoPt[] = ["espaco_confinado", "altura", "geral"];
const FILTROS_DE_STATUS: { valor: StatusPt | "todas"; rotulo: string }[] = [
  { valor: "ativa", rotulo: "Ativas" },
  { valor: "encerrada", rotulo: "Encerradas" },
  { valor: "cancelada", rotulo: "Canceladas" },
  { valor: "todas", rotulo: "Todas" },
];

export const AVISO_VIGIA = "A câmera auxilia o vigia; não o substitui (NR-33, 33.3.4.1).";
const EXPLICA_ZONA = "Com isto ligado, quem entrar na área de risco desta câmera sem permissão vigente gera alerta.";
const AJUDA_RESPONSAVEL = "Nome de quem responde pela permissão. Não é vinculado às pessoas detectadas.";
const AJUDA_FIM = "Horário local. Permissões muito longas geram um aviso na emissão, e há um limite máximo de duração.";
const MIN_PONTOS = 3;

// ------------------------------------------------------------------ datas ---
const dois = (n: number) => String(n).padStart(2, "0");

/** Valor de um <input type="datetime-local"> (hora local) para um Date. */
function paraCampoLocal(d: Date): string {
  return `${d.getFullYear()}-${dois(d.getMonth() + 1)}-${dois(d.getDate())}T${dois(d.getHours())}:${dois(d.getMinutes())}`;
}

/** Hora local do campo → ISO-8601 com o fuso explícito (ex.: 2026-10-17T08:00:00-03:00). */
function paraIsoComFuso(valor: string): string | null {
  const d = new Date(valor);
  if (!valor || Number.isNaN(d.getTime())) return null;
  const minutos = -d.getTimezoneOffset();
  const sinal = minutos >= 0 ? "+" : "-";
  const abs = Math.abs(minutos);
  const base = valor.length === 16 ? `${valor}:00` : valor;
  return `${base}${sinal}${dois(Math.floor(abs / 60))}:${dois(abs % 60)}`;
}

function janela(inicio: string, fim: string): string {
  const a = paraDate(inicio);
  const b = paraDate(fim);
  const mesmoDia = a.toDateString() === b.toDateString();
  return `${dataHoraCurta(a)} até ${mesmoDia ? horaCurta(b) : dataHoraCurta(b)}`;
}

/** Estado exibido: "vigente" é derivado pela API (inicio <= agora < fim e status ativa). */
function situacao(p: Permissao): { rotulo: string; tom: "ok" | "neutral" } {
  if (p.status === "encerrada") return { rotulo: "Encerrada", tom: "neutral" };
  if (p.status === "cancelada") return { rotulo: "Cancelada", tom: "neutral" };
  if (p.vigente) return { rotulo: "Vigente", tom: "ok" };
  return Date.now() < paraDate(p.inicio).getTime() ? { rotulo: "Agendada", tom: "neutral" } : { rotulo: "Passou do prazo", tom: "neutral" };
}

// ------------------------------------------------------------ diálogo base ---
const FOCAVEL = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/** Diálogo: Esc fecha, foco entra e fica preso, volta para quem abriu ao fechar. */
function Dialogo({
  titulo,
  aoFechar,
  escAtivo = true,
  fecharNoScrim = true,
  role = "dialog",
  classe = "",
  testid,
  children,
}: {
  titulo: string;
  aoFechar: () => void;
  escAtivo?: boolean;
  fecharNoScrim?: boolean;
  role?: "dialog" | "alertdialog";
  classe?: string;
  testid?: string;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const idTitulo = useId();
  // Capturado na renderização: no efeito, um autoFocus dos filhos já teria trocado o foco.
  const anterior = useRef<HTMLElement | null>(document.activeElement as HTMLElement | null);
  useFecharComEsc(aoFechar, escAtivo);
  useEffect(() => {
    const el = ref.current;
    if (el && !el.contains(document.activeElement)) el.focus();
    return () => anterior.current?.focus?.();
  }, []);
  const prender = (e: TeclaReact) => {
    if (e.key !== "Tab" || !ref.current) return;
    const itens = Array.from(ref.current.querySelectorAll<HTMLElement>(FOCAVEL));
    if (!itens.length) {
      e.preventDefault();
      return;
    }
    const primeiro = itens[0];
    const ultimo = itens[itens.length - 1];
    const ativo = document.activeElement;
    if (e.shiftKey && (ativo === primeiro || ativo === ref.current)) {
      e.preventDefault();
      ultimo.focus();
    } else if (!e.shiftKey && ativo === ultimo) {
      e.preventDefault();
      primeiro.focus();
    }
  };
  return (
    <div className="modal-scrim" onClick={fecharNoScrim ? aoFechar : undefined}>
      <div
        ref={ref}
        className={`card modal pt-modal ${classe}`.trim()}
        role={role}
        aria-modal="true"
        aria-labelledby={idTitulo}
        tabIndex={-1}
        data-testid={testid}
        onClick={(e) => e.stopPropagation()}
        onKeyDown={prender}
      >
        <header className="pt-modal-topo">
          <h2 id={idTitulo}>{titulo}</h2>
          <button type="button" className="ghost small" onClick={aoFechar}>
            Fechar
          </button>
        </header>
        {children}
      </div>
    </div>
  );
}

function Confirmar({ titulo, texto, acao, ocupado, onSim, onNao }: { titulo: string; texto: string; acao: string; ocupado: boolean; onSim: () => void; onNao: () => void }) {
  return (
    <Dialogo titulo={titulo} aoFechar={onNao} role="alertdialog" classe="pt-confirma">
      <p className="pt-confirma-texto">{texto}</p>
      <div className="modal-acoes">
        <button type="button" className="ghost" onClick={onNao} disabled={ocupado} autoFocus>
          Voltar
        </button>
        <button type="button" className="danger" onClick={onSim} disabled={ocupado}>
          {ocupado ? "Aguarde…" : acao}
        </button>
      </div>
    </Dialogo>
  );
}

// ----------------------------------------------------------- área do vigia ---
const limitar = (v: number) => Math.min(1, Math.max(0, Number(v.toFixed(4))));
/** Pontos de partida de quem adiciona pelo teclado: um triângulo no meio do quadro, depois o meio da última aresta. */
const SEMENTES: Ponto[] = [[0.35, 0.35], [0.65, 0.35], [0.5, 0.65]];

function AreaDoVigia({
  cameraId,
  pontos,
  onChange,
  somenteLeitura = false,
  invalido = false,
}: {
  cameraId: number;
  pontos: Ponto[];
  onChange?: (p: Ponto[]) => void;
  somenteLeitura?: boolean;
  invalido?: boolean;
}) {
  const quadroRef = useRef<HTMLDivElement>(null);
  const focar = useRef<number | null>(null);
  const [arrastando, setArrastando] = useState<number | null>(null);
  const [versao, setVersao] = useState(0);
  const [carregada, setCarregada] = useState(false);
  const [semQuadro, setSemQuadro] = useState(false);
  const mudar = onChange ?? (() => undefined);

  useEffect(() => {
    if (focar.current === null) return;
    quadroRef.current?.querySelectorAll<HTMLButtonElement>(".pt-vertice")[focar.current]?.focus();
    focar.current = null;
  });

  const posicao = (e: { clientX: number; clientY: number }): Ponto | null => {
    const r = quadroRef.current?.getBoundingClientRect();
    if (!r || !r.width || !r.height) return null;
    return [limitar((e.clientX - r.left) / r.width), limitar((e.clientY - r.top) / r.height)];
  };
  const adicionar = (p: Ponto) => {
    focar.current = pontos.length;
    mudar([...pontos, p]);
  };
  const adicionarPeloTeclado = () => {
    if (pontos.length < SEMENTES.length) return adicionar(SEMENTES[pontos.length]);
    const a = pontos[pontos.length - 1];
    const b = pontos[0];
    adicionar([limitar((a[0] + b[0]) / 2), limitar((a[1] + b[1]) / 2 + 0.05)]);
  };
  const moverPara = (i: number, p: Ponto) => mudar(pontos.map((q, j) => (j === i ? p : q)));
  const teclaNoVertice = (e: TeclaReact, i: number) => {
    if (e.key === "Delete" || e.key === "Backspace") {
      e.preventDefault();
      const restantes = pontos.filter((_, j) => j !== i);
      focar.current = restantes.length ? Math.max(0, i - 1) : null;
      mudar(restantes);
      return;
    }
    const d = e.shiftKey ? 0.05 : 0.01;
    const delta: Record<string, Ponto> = { ArrowLeft: [-d, 0], ArrowRight: [d, 0], ArrowUp: [0, -d], ArrowDown: [0, d] };
    const m = delta[e.key];
    if (!m) return;
    e.preventDefault();
    moverPara(i, [limitar(pontos[i][0] + m[0]), limitar(pontos[i][1] + m[1])]);
  };
  const moverArrastando = (e: PonteiroReact, i: number) => {
    if (arrastando !== i) return;
    const p = posicao(e);
    if (p) moverPara(i, p);
  };
  const lista = pontos.map(([x, y]) => `${x},${y}`).join(" ");
  const faltam = Math.max(0, MIN_PONTOS - pontos.length);

  return (
    <div className="pt-area" data-testid="pt-area-vigia">
      {!somenteLeitura && (
        <p className="pt-ajuda" id="pt-area-instrucao">
          Clique no quadro para marcar os pontos da área onde o vigia fica. Arraste um ponto para ajustar. Com o ponto em foco, as setas o movem (Shift move mais) e Delete o remove.
        </p>
      )}
      <div className={`pt-quadro ${carregada ? "carregada" : ""}`.trim()} ref={quadroRef}>
        <img
          key={versao}
          src={`/api/cameras/${cameraId}/frame.jpg?v=${versao}`}
          alt="Quadro atual da câmera"
          onLoad={() => {
            setCarregada(true);
            setSemQuadro(false);
          }}
          onError={() => setSemQuadro(true)}
        />
        <svg
          viewBox="0 0 1 1"
          preserveAspectRatio="none"
          role="img"
          aria-label={pontos.length >= MIN_PONTOS ? `Área do vigia com ${pontos.length} pontos` : "Área do vigia ainda não desenhada"}
          className={somenteLeitura ? "" : "editavel"}
          onPointerDown={somenteLeitura ? undefined : (e) => {
            const p = posicao(e);
            if (p) adicionar(p);
          }}
        >
          {pontos.length >= MIN_PONTOS && <polygon points={lista} className="pt-vigia-poly" />}
          {pontos.length > 0 && pontos.length < MIN_PONTOS && <polyline points={lista} className="pt-vigia-linha" />}
        </svg>
        {!somenteLeitura &&
          pontos.map(([x, y], i) => (
            <button
              key={i}
              type="button"
              className="pt-vertice"
              style={{ left: `${x * 100}%`, top: `${y * 100}%` }}
              aria-label={`Ponto ${i + 1} da área do vigia`}
              aria-describedby="pt-area-instrucao"
              onPointerDown={(e) => {
                e.preventDefault();
                e.stopPropagation();
                e.currentTarget.setPointerCapture(e.pointerId);
                setArrastando(i);
              }}
              onPointerMove={(e) => moverArrastando(e, i)}
              onPointerUp={() => setArrastando(null)}
              onPointerCancel={() => setArrastando(null)}
              onKeyDown={(e) => teclaNoVertice(e, i)}
            />
          ))}
      </div>
      {semQuadro && <p className="pt-ajuda">Sem quadro da câmera agora. O desenho continua valendo, mas fica sem imagem de referência.</p>}
      {!somenteLeitura && (
        <div className="pt-area-barra">
          <span className="pt-ajuda" data-invalido={invalido ? "true" : undefined} tabIndex={invalido ? -1 : undefined}>
            {faltam > 0 ? `Marque pelo menos ${MIN_PONTOS} pontos (${pontos.length} de ${MIN_PONTOS}).` : `${pontos.length} pontos marcados.`}
          </span>
          <span className="pt-area-botoes">
            <button type="button" className="small" onClick={adicionarPeloTeclado}>
              Adicionar ponto
            </button>
            <button type="button" className="ghost small" onClick={() => mudar(pontos.slice(0, -1))} disabled={!pontos.length}>
              Desfazer último
            </button>
            <button type="button" className="ghost small" onClick={() => mudar([])} disabled={!pontos.length}>
              Limpar
            </button>
            <button
              type="button"
              className="ghost small"
              onClick={() => {
                setCarregada(false);
                setVersao((v) => v + 1);
              }}
            >
              Atualizar quadro
            </button>
          </span>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- formulário ---
interface Formulario {
  camera: string;
  tipo: TipoPt;
  descricao: string;
  responsavel: string;
  inicio: string;
  fim: string;
  epis: PpeKey[];
  exigeVigia: boolean;
  area: Ponto[];
}
type Erros = Partial<Record<string, string>>;
type Suporte = { estado: "sem-camera" } | { estado: "carregando" } | { estado: "indisponivel" } | { estado: "ok"; epis: Record<string, boolean> };

const CHAVE_DO_ERRO: Record<keyof Formulario, string> = {
  camera: "camera_id",
  tipo: "tipo",
  descricao: "descricao",
  responsavel: "responsavel",
  inicio: "inicio",
  fim: "fim",
  epis: "epis_exigidos",
  exigeVigia: "exige_vigia",
  area: "area_vigia",
};
const CAMPOS_DA_API = Object.values(CHAVE_DO_ERRO);

/** Em que campo mostrar o 400 da API (o texto do erro cita o campo entre aspas simples). */
function campoDoErro(code: string | undefined, mensagem: string): string {
  if (code === "area_vigia_obrigatoria") return "area_vigia";
  if (code === "janela_invalida" || code === "duracao_excedida") return /'inicio'/.test(mensagem) && !/'fim'/.test(mensagem) ? "inicio" : "fim";
  if (/EPIs desconhecidos/.test(mensagem)) return "epis_exigidos";
  const citado = /'(\w+)'/.exec(mensagem)?.[1];
  return citado && CAMPOS_DA_API.includes(citado) ? citado : "geral";
}

function validar(f: Formulario): Erros {
  const e: Erros = {};
  if (!f.camera) e.camera_id = "Escolha a câmera.";
  if (!f.descricao.trim()) e.descricao = "Descreva o trabalho.";
  if (!f.responsavel.trim()) e.responsavel = "Informe o nome de quem responde pela permissão.";
  const inicio = paraIsoComFuso(f.inicio);
  const fim = paraIsoComFuso(f.fim);
  if (!inicio) e.inicio = "Informe o início.";
  if (!fim) e.fim = "Informe o fim.";
  if (inicio && fim && new Date(fim).getTime() <= new Date(inicio).getTime()) e.fim = "O fim deve ser depois do início.";
  if (f.exigeVigia && f.area.length < MIN_PONTOS) e.area_vigia = `Marque pelo menos ${MIN_PONTOS} pontos para a área do vigia.`;
  return e;
}

function Campo({ id, rotulo, ajuda, erro, children }: { id: string; rotulo: string; ajuda?: string; erro?: string; children: ReactNode }) {
  return (
    <div className="field pt-campo">
      <label htmlFor={id} className="pt-rotulo">
        {rotulo}
      </label>
      {children}
      {ajuda && (
        <p className="pt-ajuda" id={`${id}-ajuda`}>
          {ajuda}
        </p>
      )}
      {erro && (
        <p className="pt-erro" id={`${id}-erro`} role="alert">
          {erro}
        </p>
      )}
    </div>
  );
}
const descrito = (id: string, ajuda?: string, erro?: string) => [ajuda ? `${id}-ajuda` : null, erro ? `${id}-erro` : null].filter(Boolean).join(" ") || undefined;

function FormularioDeEmissao({
  cameras,
  cameraInicial,
  aoFechar,
  aoEmitir,
}: {
  cameras: CameraRecord[];
  cameraInicial: string;
  aoFechar: () => void;
  aoEmitir: (p: PermissaoEmitida) => void;
}) {
  const base = useId();
  const formRef = useRef<HTMLFormElement>(null);
  const [form, setForm] = useState<Formulario>(() => {
    const agora = new Date();
    agora.setSeconds(0, 0);
    return {
      camera: cameraInicial || (cameras.length === 1 ? String(cameras[0].id) : ""),
      tipo: "geral",
      descricao: "",
      responsavel: "",
      inicio: paraCampoLocal(agora),
      fim: paraCampoLocal(new Date(agora.getTime() + 8 * 3600_000)),
      epis: [],
      exigeVigia: false,
      area: [],
    };
  });
  const [erros, setErros] = useState<Erros>({});
  const [tentativa, setTentativa] = useState(0);
  const [enviando, setEnviando] = useState(false);
  const [suporte, setSuporte] = useState<Suporte>({ estado: "sem-camera" });

  const atualizar = <K extends keyof Formulario>(chave: K, valor: Formulario[K]) => {
    setForm((f) => ({ ...f, [chave]: valor }));
    setErros((e) => {
      const proximo = { ...e };
      delete proximo[CHAVE_DO_ERRO[chave]];
      return proximo;
    });
  };

  // O que o modelo desta câmera detecta (o detalhe da permissão confirma depois de emitida).
  useEffect(() => {
    if (!form.camera) {
      setSuporte({ estado: "sem-camera" });
      return undefined;
    }
    let vivo = true;
    setSuporte({ estado: "carregando" });
    apiFetch<{ model?: { supported_ppe?: Record<string, boolean> } }>(`/api/cameras/${form.camera}/status`)
      .then((d) => vivo && setSuporte({ estado: "ok", epis: d.model?.supported_ppe ?? {} }))
      .catch(() => vivo && setSuporte({ estado: "indisponivel" }));
    return () => {
      vivo = false;
    };
  }, [form.camera]);

  useEffect(() => {
    if (!tentativa) return;
    formRef.current?.querySelector<HTMLElement>('[aria-invalid="true"], [data-invalido="true"]')?.focus();
  }, [tentativa]);

  const dicaDoEpi = (epi: PpeKey): ReactNode => {
    if (suporte.estado === "sem-camera") return <span className="pt-dica">Escolha a câmera para ver</span>;
    if (suporte.estado === "carregando") return <span className="pt-dica">Consultando a câmera…</span>;
    if (suporte.estado === "indisponivel") return <Badge>Verificação manual (câmera sem análise agora)</Badge>;
    return suporte.epis[epi] ? <Badge tone="ok">Fiscalizado pela câmera</Badge> : <Badge>Verificação manual</Badge>;
  };

  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    const invalidos = validar(form);
    if (Object.keys(invalidos).length) {
      setErros(invalidos);
      setTentativa((n) => n + 1);
      return;
    }
    setEnviando(true);
    setErros({});
    try {
      const resposta = await apiFetch<PermissaoEmitida>("/api/permissoes", {
        method: "POST",
        body: JSON.stringify({
          camera_id: Number(form.camera),
          tipo: form.tipo,
          descricao: form.descricao.trim(),
          responsavel: form.responsavel.trim(),
          inicio: paraIsoComFuso(form.inicio),
          fim: paraIsoComFuso(form.fim),
          epis_exigidos: form.epis,
          exige_vigia: form.exigeVigia,
          area_vigia: form.exigeVigia ? form.area : null,
        }),
      });
      aoEmitir(resposta);
    } catch (err) {
      const mensagem = mensagemDeErro(err, "Não foi possível emitir a permissão.");
      if (err instanceof ApiError && err.status === 400) {
        const code = err.body && typeof err.body === "object" && "code" in err.body ? String((err.body as { code: unknown }).code) : undefined;
        setErros({ [campoDoErro(code, mensagem)]: mensagem });
      } else if (err instanceof ApiError && err.status === 404) {
        setErros({ camera_id: "Câmera não encontrada. Escolha outra." });
      } else {
        setErros({ geral: mensagem });
      }
      setTentativa((n) => n + 1);
    } finally {
      setEnviando(false);
    }
  };

  const idc = (nome: string) => `${base}-${nome}`;
  const cameraNumero = Number(form.camera);

  return (
    <Dialogo titulo="Emitir permissão de trabalho" aoFechar={aoFechar} fecharNoScrim={false} classe="pt-modal-largo">
      <form ref={formRef} className="pt-form" onSubmit={enviar} noValidate data-testid="pt-form">
        <p className="pt-ajuda">Todos os campos são obrigatórios, exceto os EPIs e o vigia.</p>
        {erros.geral && (
          <p className="pt-falha" role="alert">
            {erros.geral}
          </p>
        )}

        <div className="pt-linha">
          <Campo id={idc("camera")} rotulo="Câmera" erro={erros.camera_id}>
            <select
              id={idc("camera")}
              value={form.camera}
              required
              aria-invalid={erros.camera_id ? true : undefined}
              aria-describedby={descrito(idc("camera"), undefined, erros.camera_id)}
              onChange={(e) => atualizar("camera", e.target.value)}
            >
              <option value="">Escolha a câmera</option>
              {cameras.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </Campo>
          <Campo id={idc("tipo")} rotulo="Tipo de trabalho" erro={erros.tipo}>
            <select
              id={idc("tipo")}
              value={form.tipo}
              aria-invalid={erros.tipo ? true : undefined}
              aria-describedby={descrito(idc("tipo"), undefined, erros.tipo)}
              onChange={(e) => atualizar("tipo", e.target.value as TipoPt)}
            >
              {ORDEM_DE_TIPOS.map((t) => (
                <option key={t} value={t}>
                  {TIPOS[t]}
                </option>
              ))}
            </select>
          </Campo>
        </div>
        {form.tipo === "espaco_confinado" && (
          <p className="pt-aviso" role="note">
            {AVISO_VIGIA}
          </p>
        )}

        <Campo id={idc("descricao")} rotulo="Descrição do trabalho" erro={erros.descricao}>
          <textarea
            id={idc("descricao")}
            value={form.descricao}
            maxLength={500}
            required
            rows={3}
            aria-invalid={erros.descricao ? true : undefined}
            aria-describedby={descrito(idc("descricao"), undefined, erros.descricao)}
            onChange={(e) => atualizar("descricao", e.target.value)}
          />
        </Campo>
        <Campo id={idc("responsavel")} rotulo="Responsável" ajuda={AJUDA_RESPONSAVEL} erro={erros.responsavel}>
          <input
            id={idc("responsavel")}
            type="text"
            value={form.responsavel}
            maxLength={120}
            required
            autoComplete="off"
            aria-invalid={erros.responsavel ? true : undefined}
            aria-describedby={descrito(idc("responsavel"), AJUDA_RESPONSAVEL, erros.responsavel)}
            onChange={(e) => atualizar("responsavel", e.target.value)}
          />
        </Campo>

        <div className="pt-linha">
          <Campo id={idc("inicio")} rotulo="Início" erro={erros.inicio}>
            <input
              id={idc("inicio")}
              type="datetime-local"
              value={form.inicio}
              required
              aria-invalid={erros.inicio ? true : undefined}
              aria-describedby={descrito(idc("inicio"), undefined, erros.inicio)}
              onChange={(e) => atualizar("inicio", e.target.value)}
            />
          </Campo>
          <Campo id={idc("fim")} rotulo="Fim" ajuda={AJUDA_FIM} erro={erros.fim}>
            <input
              id={idc("fim")}
              type="datetime-local"
              value={form.fim}
              required
              aria-invalid={erros.fim ? true : undefined}
              aria-describedby={descrito(idc("fim"), AJUDA_FIM, erros.fim)}
              onChange={(e) => atualizar("fim", e.target.value)}
            />
          </Campo>
        </div>

        <fieldset className="pt-grupo">
          <legend className="pt-rotulo">EPIs exigidos</legend>
          <p className="pt-ajuda">A câmera só alerta os EPIs que ela fiscaliza. Os demais ficam no checklist como verificação manual.</p>
          <div className="pt-epis">
            {PPE_KEYS.map((epi) => (
              <label key={epi} className="pt-epi">
                <input
                  type="checkbox"
                  checked={form.epis.includes(epi)}
                  onChange={(e) => atualizar("epis", e.target.checked ? [...form.epis, epi] : form.epis.filter((x) => x !== epi))}
                />
                <span className="pt-epi-nome">{PPE_LABELS[epi]}</span>
                {dicaDoEpi(epi)}
              </label>
            ))}
          </div>
          {erros.epis_exigidos && (
            <p className="pt-erro" role="alert">
              {erros.epis_exigidos}
            </p>
          )}
        </fieldset>

        <div className="pt-grupo">
          <label className="pt-epi">
            <input type="checkbox" checked={form.exigeVigia} onChange={(e) => atualizar("exigeVigia", e.target.checked)} />
            <span className="pt-epi-nome">Exige vigia</span>
          </label>
          <p className="pt-ajuda">Com vigia, a câmera avisa quando há gente na zona e ninguém na área do vigia.</p>
          {erros.exige_vigia && (
            <p className="pt-erro" role="alert">
              {erros.exige_vigia}
            </p>
          )}
          {form.exigeVigia && (
            <>
              {Number.isFinite(cameraNumero) && form.camera ? (
                <AreaDoVigia cameraId={cameraNumero} pontos={form.area} onChange={(p) => atualizar("area", p)} invalido={Boolean(erros.area_vigia)} />
              ) : (
                <p className="pt-ajuda">Escolha a câmera para desenhar a área do vigia sobre o quadro dela.</p>
              )}
              {erros.area_vigia && (
                <p className="pt-erro" role="alert">
                  {erros.area_vigia}
                </p>
              )}
            </>
          )}
        </div>

        <div className="modal-acoes">
          <button type="button" className="ghost" onClick={aoFechar} disabled={enviando}>
            Voltar
          </button>
          <button type="submit" className={`primary ${enviando ? "is-pending" : ""}`.trim()} disabled={enviando} data-testid="pt-salvar">
            {enviando ? "Emitindo…" : "Emitir permissão"}
          </button>
        </div>
      </form>
    </Dialogo>
  );
}

// ------------------------------------------------------------------ detalhe ---
function Linha({ rotulo, children }: { rotulo: string; children: ReactNode }) {
  return (
    <>
      <dt>{rotulo}</dt>
      <dd>{children}</dd>
    </>
  );
}

function DetalheDaPermissao({
  id,
  nomeDaCamera,
  podeEditar,
  aoFechar,
  aoMudar,
}: {
  id: number;
  nomeDaCamera: (id: number) => string;
  podeEditar: boolean;
  aoFechar: () => void;
  aoMudar: (texto: string) => void;
}) {
  const [d, setD] = useState<PermissaoDetalhe | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [n, setN] = useState(0);
  const [confirmando, setConfirmando] = useState<"encerrar" | "cancelar" | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [falha, setFalha] = useState<string | null>(null);

  useEffect(() => {
    let vivo = true;
    apiFetch<PermissaoDetalhe>(`/api/permissoes/${id}`)
      .then((x) => {
        if (!vivo) return;
        setD(x);
        setErro(null);
      })
      .catch((e) => vivo && setErro(mensagemDeErro(e, "Não foi possível abrir a permissão.")));
    return () => {
      vivo = false;
    };
  }, [id, n]);

  const executar = async (acao: "encerrar" | "cancelar") => {
    setOcupado(true);
    setFalha(null);
    try {
      const novo = await apiFetch<PermissaoDetalhe>(`/api/permissoes/${id}/${acao}`, { method: "POST", body: "{}" });
      setD(novo);
      aoMudar(acao === "encerrar" ? `Permissão ${novo.numero} encerrada.` : `Permissão ${novo.numero} cancelada.`);
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        setFalha("Esta permissão já foi encerrada ou cancelada, talvez por outra pessoa. Os dados abaixo foram atualizados.");
        setN((x) => x + 1);
      } else {
        setFalha(mensagemDeErro(e, "Não foi possível concluir."));
      }
    } finally {
      setConfirmando(null);
      setOcupado(false);
    }
  };

  const sit = d ? situacao(d) : null;
  return (
    <>
      <Dialogo titulo={d ? d.numero : "Permissão de trabalho"} aoFechar={aoFechar} escAtivo={!confirmando} classe="pt-modal-largo" testid="pt-detalhe">
        {erro && !d ? (
          <div className="pt-estado">
            <p role="alert">{erro}</p>
            <button type="button" onClick={() => setN((x) => x + 1)}>
              Tentar de novo
            </button>
          </div>
        ) : !d || !sit ? (
          <div aria-busy="true">
            <PanelSkeleton lines={5} />
          </div>
        ) : (
          <div className="pt-detalhe">
            <div className="pt-detalhe-chips">
              <Badge tone={sit.tom}>{sit.rotulo}</Badge>
              <Badge>{TIPOS[d.tipo] ?? d.tipo}</Badge>
              {d.exige_vigia && <Badge>Exige vigia</Badge>}
            </div>
            {falha && (
              <p className="pt-falha" role="alert">
                {falha}
              </p>
            )}
            {d.tipo === "espaco_confinado" && (
              <p className="pt-aviso" role="note" data-testid="pt-aviso-vigia">
                {AVISO_VIGIA}
              </p>
            )}
            <dl className="pt-dl">
              <Linha rotulo="Câmera">{nomeDaCamera(d.camera_id)}</Linha>
              <Linha rotulo="Janela">{janela(d.inicio, d.fim)}</Linha>
              <Linha rotulo="Responsável">{d.responsavel}</Linha>
              <Linha rotulo="Descrição">{d.descricao}</Linha>
              <Linha rotulo="Emitida por">
                {d.criada_por}
                {d.criada_em && `, em ${dataHoraCurta(paraDate(d.criada_em))}`}
              </Linha>
              {d.encerrada_em && (
                <Linha rotulo={d.status === "cancelada" ? "Cancelada por" : "Encerrada por"}>
                  {d.encerrada_por ?? "sem registro"}, em {dataHoraCurta(paraDate(d.encerrada_em))}
                </Linha>
              )}
            </dl>

            <section aria-labelledby={`pt-checklist-${d.id}`}>
              <h3 id={`pt-checklist-${d.id}`}>Checklist de EPIs</h3>
              {d.checklist.length ? (
                <>
                  <ul className="pt-checklist">
                    {d.checklist.map((item) => (
                      <li key={item.epi}>
                        <span className="pt-epi-nome">{item.rotulo}</span>
                        {item.verificacao === "automatica" ? (
                          <Badge tone="ok">Fiscalizado pela câmera</Badge>
                        ) : (
                          <Badge>Verificação manual: a câmera não detecta este EPI</Badge>
                        )}
                      </li>
                    ))}
                  </ul>
                  <p className="pt-ajuda">A câmera só alerta os EPIs fiscalizados. Os de verificação manual são conferidos por pessoas.</p>
                </>
              ) : (
                <p className="pt-ajuda">Esta permissão não exige EPIs específicos.</p>
              )}
            </section>

            {d.exige_vigia && d.area_vigia && d.area_vigia.length >= MIN_PONTOS && (
              <section aria-labelledby={`pt-vigia-${d.id}`}>
                <h3 id={`pt-vigia-${d.id}`}>Área do vigia</h3>
                <AreaDoVigia cameraId={d.camera_id} pontos={d.area_vigia} somenteLeitura />
              </section>
            )}

            <section aria-labelledby={`pt-norma-${d.id}`}>
              <h3 id={`pt-norma-${d.id}`}>Norma</h3>
              {d.norma ? (
                <>
                  <p className="pt-ajuda">Itens da {d.norma.codigo} citados por esta permissão.</p>
                  <ul className="pt-norma">
                    {d.norma.itens.map((it) => (
                      <li key={it.item}>
                        <strong>{it.item}</strong> {it.texto}
                      </li>
                    ))}
                  </ul>
                  <a href={d.norma.url} target="_blank" rel="noopener noreferrer">
                    Abrir o texto oficial da {d.norma.codigo} (gov.br, abre em nova aba)
                  </a>
                </>
              ) : (
                <p className="pt-ajuda">O tipo Geral não tem norma citada pelo sistema.</p>
              )}
            </section>

            {podeEditar && d.status === "ativa" && (
              <div className="modal-acoes">
                <button type="button" onClick={() => setConfirmando("cancelar")}>
                  Cancelar permissão
                </button>
                <button type="button" className="primary" onClick={() => setConfirmando("encerrar")}>
                  Encerrar permissão
                </button>
              </div>
            )}
          </div>
        )}
      </Dialogo>
      {confirmando && d && (
        <Confirmar
          titulo={confirmando === "encerrar" ? `Encerrar a permissão ${d.numero}?` : `Cancelar a permissão ${d.numero}?`}
          texto={
            confirmando === "encerrar"
              ? "A permissão deixa de valer agora e a câmera volta a tratar a área como sem permissão. O registro fica no histórico e não dá para reabrir."
              : "Use quando a permissão não vai mais ser usada. Ela deixa de valer agora e o registro fica no histórico. Não dá para reabrir."
          }
          acao={confirmando === "encerrar" ? "Encerrar agora" : "Cancelar agora"}
          ocupado={ocupado}
          onNao={() => setConfirmando(null)}
          onSim={() => executar(confirmando)}
        />
      )}
    </>
  );
}

// --------------------------------------------------------------------- tela ---
type Retorno = { texto: string; avisos: string[]; abrirId?: number };

export function PermissoesScreen() {
  const user = useDashboardStore((s) => s.user);
  const cameras = useDashboardStore((s) => s.cameras);
  const podeEditar = user?.role === "technical" || user?.role === "supervisor";
  const idExplicaZona = useId();

  const [filtroStatus, setFiltroStatus] = useState<StatusPt | "todas">("ativa");
  const [filtroCamera, setFiltroCamera] = useState("");
  const [lista, setLista] = useState<Permissao[] | null>(null);
  const [erroLista, setErroLista] = useState<string | null>(null);
  const [recarga, setRecarga] = useState(0);
  const [abertaId, setAbertaId] = useState<number | null>(null);
  const [formAberto, setFormAberto] = useState(false);
  const [retorno, setRetorno] = useState<Retorno | null>(null);
  const [falha, setFalha] = useState<string | null>(null);
  const [zonas, setZonas] = useState<Record<number, boolean | null>>({});
  const [zonaOcupada, setZonaOcupada] = useState<number | null>(null);

  const nomes = useMemo(() => new Map(cameras.map((c) => [c.id, c.name])), [cameras]);
  const nomeDaCamera = (id: number) => nomes.get(id) ?? `Câmera nº ${id}`;
  const idsDasCameras = cameras.map((c) => c.id).join(",");

  useEffect(() => {
    let vivo = true;
    const consulta = new URLSearchParams();
    if (filtroStatus !== "todas") consulta.set("status", filtroStatus);
    if (filtroCamera) consulta.set("camera_id", filtroCamera);
    const buscar = () =>
      apiFetch<{ items: Permissao[] }>(`/api/permissoes?${consulta.toString()}`)
        .then((r) => {
          if (!vivo) return;
          setLista(r.items);
          setErroLista(null);
        })
        .catch((e) => vivo && setErroLista(mensagemDeErro(e, "Não foi possível carregar as permissões.")));
    buscar();
    const id = window.setInterval(buscar, 30_000);
    return () => {
      vivo = false;
      window.clearInterval(id);
    };
  }, [filtroStatus, filtroCamera, recarga]);

  useEffect(() => {
    let vivo = true;
    cameras.forEach((c) => {
      apiFetch<{ exige_permissao: boolean }>(`/api/cameras/${c.id}/zona-controlada`)
        .then((z) => vivo && setZonas((p) => ({ ...p, [c.id]: z.exige_permissao })))
        .catch(() => vivo && setZonas((p) => ({ ...p, [c.id]: null })));
    });
    return () => {
      vivo = false;
    };
  }, [idsDasCameras]);

  const alternarZona = async (cam: CameraRecord, valor: boolean) => {
    setZonaOcupada(cam.id);
    setFalha(null);
    try {
      const z = await apiFetch<{ exige_permissao: boolean }>(`/api/cameras/${cam.id}/zona-controlada`, {
        method: "PUT",
        body: JSON.stringify({ exige_permissao: valor }),
      });
      setZonas((p) => ({ ...p, [cam.id]: z.exige_permissao }));
      setRetorno({ texto: z.exige_permissao ? `${cam.name}: a zona agora exige permissão.` : `${cam.name}: a zona deixou de exigir permissão.`, avisos: [] });
    } catch (e) {
      setFalha(mensagemDeErro(e, "Não foi possível alterar a zona."));
    } finally {
      setZonaOcupada(null);
    }
  };

  const recarregar = () => setRecarga((x) => x + 1);
  const tentarDeNovo = () => {
    setErroLista(null);
    setLista(null);
    recarregar();
  };

  const emitida = (p: PermissaoEmitida) => {
    setFormAberto(false);
    setFalha(null);
    setRetorno({ texto: `Permissão ${p.numero} emitida.`, avisos: p.avisos ?? [], abrirId: p.id });
    recarregar();
  };


  return (
    <div className="screen pt" data-testid="permissoes">
      <header className="pt-cabeca">
        <div>
          <h1>Permissão de trabalho</h1>
          <p className="pt-sub">
            Registra quem pode trabalhar na área de risco, por quanto tempo e com quais EPIs. A câmera confere a permissão; não a emite nem substitui o vigia.
          </p>
          {!podeEditar && <p className="pt-sub">Somente leitura: você vê as permissões da sua câmera.</p>}
        </div>
        {podeEditar && (
          <button type="button" className="primary" onClick={() => setFormAberto(true)} data-testid="pt-emitir">
            Emitir permissão
          </button>
        )}
      </header>

      <div className="pt-vivo" role="status" aria-live="polite">
        {retorno && (
          <div className="pt-retorno">
            <p className="pt-retorno-texto">
              <span className="chip ok">
                <span className="dot" />
                {retorno.texto}
              </span>
            </p>
            {retorno.avisos.length > 0 && (
              <div className="pt-avisos">
                <p className="pt-avisos-titulo">Avisos da emissão</p>
                <ul>
                  {retorno.avisos.map((a) => (
                    <li key={a}>{a}</li>
                  ))}
                </ul>
              </div>
            )}
            <div className="pt-retorno-acoes">
              {retorno.abrirId !== undefined && (
                <button type="button" className="small" onClick={() => setAbertaId(retorno.abrirId ?? null)}>
                  Abrir detalhe
                </button>
              )}
              <button type="button" className="ghost small" onClick={() => setRetorno(null)}>
                Dispensar
              </button>
            </div>
          </div>
        )}
      </div>
      {falha && (
        <p className="pt-falha" role="alert">
          {falha}
        </p>
      )}

      {cameras.length > 0 && (
        <section className="card pt-zonas" aria-labelledby={`${idExplicaZona}-titulo`}>
          <div className="card-head">
            <div>
              <h2 id={`${idExplicaZona}-titulo`}>Zonas controladas</h2>
              <p id={idExplicaZona}>{EXPLICA_ZONA}</p>
            </div>
          </div>
          <div className="card-body">
            <ul className="pt-zonas-lista">
              {cameras.map((c) => {
                const estado = zonas[c.id];
                return (
                  <li key={c.id} className="pt-zona">
                    <span className="pt-zona-nome">{c.name}</span>
                    {podeEditar ? (
                      <label className="pt-zona-controle">
                        <span className="switch">
                          <input
                            type="checkbox"
                            role="switch"
                            checked={estado === true}
                            disabled={estado === undefined || estado === null || zonaOcupada === c.id}
                            aria-label={`Zona exige permissão: ${c.name}`}
                            aria-describedby={idExplicaZona}
                            data-testid="pt-zona-switch"
                            data-camera-id={c.id}
                            onChange={(e) => alternarZona(c, e.target.checked)}
                          />
                          <span className="switch-track" aria-hidden="true">
                            <span className="switch-thumb" />
                          </span>
                        </span>
                        <span>{estado === null ? "Estado indisponível" : estado === undefined ? "Consultando…" : "Zona exige permissão"}</span>
                      </label>
                    ) : estado === undefined ? (
                      <span className="pt-dica">Consultando…</span>
                    ) : estado === null ? (
                      <span className="pt-dica">Estado indisponível</span>
                    ) : (
                      <Badge tone={estado ? "ok" : "neutral"}>{estado ? "Zona exige permissão" : "Zona não exige permissão"}</Badge>
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        </section>
      )}

      <section className="card pt-lista-card" aria-labelledby="pt-lista-titulo">
        <div className="card-head">
          <div>
            <h2 id="pt-lista-titulo">Permissões</h2>
            <p>Ativas são as que ainda não foram encerradas nem canceladas. O chip mostra se valem agora.</p>
          </div>
        </div>
        <div className="card-body">
          <div className="pt-filtros">
            <div className="field">
              <label htmlFor="pt-filtro-status">Situação</label>
              <select id="pt-filtro-status" value={filtroStatus} onChange={(e) => setFiltroStatus(e.target.value as StatusPt | "todas")}>
                {FILTROS_DE_STATUS.map((f) => (
                  <option key={f.valor} value={f.valor}>
                    {f.rotulo}
                  </option>
                ))}
              </select>
            </div>
            {cameras.length > 1 && (
              <div className="field">
                <label htmlFor="pt-filtro-camera">Câmera</label>
                <select id="pt-filtro-camera" value={filtroCamera} onChange={(e) => setFiltroCamera(e.target.value)}>
                  <option value="">Todas as câmeras</option>
                  {cameras.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>

          {erroLista && lista === null ? (
            <div className="pt-estado">
              <p role="alert">{erroLista}</p>
              <button type="button" onClick={tentarDeNovo}>
                Tentar de novo
              </button>
            </div>
          ) : lista === null ? (
            <div aria-busy="true">
              <PanelSkeleton lines={5} />
            </div>
          ) : (
            <>
              {erroLista && (
                <p className="pt-falha" role="alert">
                  {erroLista} Os dados abaixo podem estar desatualizados.{" "}
                  <button type="button" className="small" onClick={recarregar}>
                    Tentar de novo
                  </button>
                </p>
              )}
              {lista.length === 0 ? (
                <EmptyState
                  ilustracao={<IlustracaoPlanta />}
                  titulo={filtroStatus === "ativa" ? "Nenhuma permissão ativa" : "Nenhuma permissão neste filtro"}
                  acao={
                    podeEditar ? (
                      <button type="button" className="primary" onClick={() => setFormAberto(true)}>
                        Emitir permissão
                      </button>
                    ) : undefined
                  }
                >
                  {podeEditar
                    ? "Emita uma permissão para registrar quem pode trabalhar na área de risco e por quanto tempo."
                    : "Quando houver permissões para a sua câmera, elas aparecem aqui."}
                </EmptyState>
              ) : (
                <ul className="pt-lista" data-testid="pt-lista">
                  {lista.map((p) => {
                    const sit = situacao(p);
                    return (
                      <li key={p.id}>
                        <button type="button" className="pt-item" aria-haspopup="dialog" onClick={() => setAbertaId(p.id)}>
                          <span className="pt-item-id">
                            <span className="pt-numero">{p.numero}</span>
                            <span className="pt-tipo">{TIPOS[p.tipo] ?? p.tipo}</span>
                          </span>
                          <span className="pt-item-meio">
                            <span className="pt-camera">{nomeDaCamera(p.camera_id)}</span>
                            <span className="pt-janela">{janela(p.inicio, p.fim)}</span>
                          </span>
                          <span className="pt-item-resp">
                            <span className="pt-rotulo-mini">Responsável</span>
                            <span>{p.responsavel}</span>
                          </span>
                          <span className="pt-item-chips">
                            <Badge tone={sit.tom}>{sit.rotulo}</Badge>
                            {p.exige_vigia && <Badge>Exige vigia</Badge>}
                          </span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
            </>
          )}
        </div>
      </section>

      {formAberto && (
        <FormularioDeEmissao cameras={cameras} cameraInicial={filtroCamera} aoFechar={() => setFormAberto(false)} aoEmitir={emitida} />
      )}
      {abertaId !== null && (
        <DetalheDaPermissao
          key={abertaId}
          id={abertaId}
          nomeDaCamera={nomeDaCamera}
          podeEditar={podeEditar}
          aoFechar={() => setAbertaId(null)}
          aoMudar={(texto) => {
            setRetorno({ texto, avisos: [] });
            recarregar();
          }}
        />
      )}
    </div>
  );
}

export default PermissoesScreen;
