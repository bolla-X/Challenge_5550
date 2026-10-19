import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { listAlerts, listarIncidentes } from "../api/endpoints";
import { ROTULOS_DE_SEVERIDADE } from "../api/ppe";
import type { Alert, Incidente } from "../api/types";
import { socket } from "../socket/client";
import { useDashboardStore } from "../store/dashboardStore";
import { dataHoraCurta, paraDate } from "../utils/datas";
import { mensagemDeErro } from "../utils/erros";
import { pluralizar } from "../utils/formato";
import { Badge, EmptyState, PanelSkeleton } from "./common";
import { IlustracaoEscudo } from "./ilustracoes";
import { IconeSino } from "./icones";
import { IncidenteDetalhe } from "./incidente-detalhe";
import "../styles/notificacoes.css";

/**
 * Central de notificações: o histórico de alertas que a pessoa pode ver, com
 * contador de não lidas no sino da barra superior.
 *
 * - Fonte: `GET /alerts?limit=50` (o backend já aplica o escopo do Operador), o histórico
 *   que o store carrega no bootstrap e os eventos do socket (`alert_created`,
 *   `alert_updated`, `alert_resolved`, que chegam de TODAS as câmeras visíveis).
 * - "Lida" é só do navegador, por conta: localStorage com a chave do id do usuário.
 *   Não existe tabela nem rota para isso, de propósito.
 * - Cada item leva ao incidente (modal de detalhe) e/ou à câmera em foco.
 */

const MAX_ITENS = 100;
const MAX_LIDAS_GUARDADAS = 500;
const CHAVE_DE_LIDAS = "visionepi-notificacoes-lidas";

const SEVERIDADES = ["critical", "high", "medium", "low", "info"] as const;
const GRAVES = new Set(["critical", "high"]);

// ------------------------------------------------------------------ lidas ----
function chaveDeLidas(userId: number): string {
  return `${CHAVE_DE_LIDAS}:${userId}`;
}

/** Ids lidos deste usuário neste navegador. localStorage pode lançar (janela privada): vira "nada lido". */
export function lerLidas(userId: number): number[] {
  try {
    const bruto = localStorage.getItem(chaveDeLidas(userId));
    const valor: unknown = bruto ? JSON.parse(bruto) : [];
    return Array.isArray(valor) ? valor.filter((v): v is number => typeof v === "number") : [];
  } catch {
    return [];
  }
}

function gravarLidas(userId: number, ids: number[]): void {
  try {
    localStorage.setItem(chaveDeLidas(userId), JSON.stringify(ids.slice(-MAX_LIDAS_GUARDADAS)));
  } catch {
    // Sem localStorage só não persiste: a sessão atual continua certa na memória.
  }
}

function useLidas(userId: number) {
  const [lidas, setLidas] = useState<number[]>(() => lerLidas(userId));
  useEffect(() => {
    setLidas(lerLidas(userId));
    // Outra aba do mesmo navegador marcou algo: acompanha.
    const aoMudar = (e: StorageEvent) => {
      if (e.key === chaveDeLidas(userId)) setLidas(lerLidas(userId));
    };
    window.addEventListener("storage", aoMudar);
    return () => window.removeEventListener("storage", aoMudar);
  }, [userId]);

  const alterar = useCallback(
    (mudar: (atuais: Set<number>) => Set<number>) => {
      setLidas((anteriores) => {
        const proximas = [...mudar(new Set(anteriores))];
        gravarLidas(userId, proximas);
        return proximas;
      });
    },
    [userId],
  );
  const marcar = useCallback((ids: number[]) => alterar((s) => new Set([...s, ...ids])), [alterar]);
  const desmarcar = useCallback(
    (id: number) =>
      alterar((s) => {
        s.delete(id);
        return s;
      }),
    [alterar],
  );
  return { lidas: useMemo(() => new Set(lidas), [lidas]), marcar, desmarcar };
}

// -------------------------------------------------------------- histórico ----
function instante(alerta: Alert): number {
  return paraDate(alerta.created_at).getTime();
}

/** Junta as fontes por id (a última lista vence) e ordena do mais novo ao mais antigo. */
function mesclar(...listas: Alert[][]): Alert[] {
  const porId = new Map<number, Alert>();
  for (const lista of listas) for (const alerta of lista) porId.set(alerta.id, alerta);
  return [...porId.values()].sort((a, b) => instante(b) - instante(a)).slice(0, MAX_ITENS);
}

function useHistoricoDeAlertas() {
  const doStore = useDashboardStore((s) => s.alertHistory);
  const [buscados, setBuscados] = useState<Alert[]>([]);
  const [recebidos, setRecebidos] = useState<Alert[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);

  const recarregar = useCallback(() => {
    setErro(null);
    return listAlerts({ limit: 50 })
      .then((res) => setBuscados(res.items))
      .catch((e) => setErro(mensagemDeErro(e, "Não foi possível carregar as notificações.")))
      .finally(() => setCarregando(false));
  }, []);

  useEffect(() => {
    void recarregar();
  }, [recarregar]);

  // O store só assina a câmera em foco; o socket traz o alerta de qualquer câmera visível.
  useEffect(() => {
    const receber = (alerta: Alert) => setRecebidos((atuais) => [...atuais.filter((a) => a.id !== alerta.id), alerta].slice(-MAX_ITENS));
    // Mesmo molde de dashboardStore.subscribeToServerEvents: `ServerEvents` mapeia evento -> payload, e o
    // TypeScript não fecha essa assinatura com os overloads de `Socket#on`. Cada evento abaixo é concreto.
    type Assinar = (evento: "alert_created" | "alert_updated" | "alert_resolved", ouvinte: (alerta: Alert) => void) => void;
    const eventos = ["alert_created", "alert_updated", "alert_resolved"] as const;
    for (const evento of eventos) (socket.on as Assinar)(evento, receber);
    return () => {
      for (const evento of eventos) (socket.off as Assinar)(evento, receber);
    };
  }, []);

  const itens = useMemo(() => mesclar(doStore, buscados, recebidos), [doStore, buscados, recebidos]);
  return { itens, carregando, erro, recarregar };
}

/** alerta -> incidente a que pertence (para o link "Ver incidente"). Só lido com o painel aberto. */
function useIncidentesDosAlertas(aberto: boolean) {
  const [porAlerta, setPorAlerta] = useState<Map<number, Incidente>>(new Map());
  useEffect(() => {
    if (!aberto) return;
    let vivo = true;
    listarIncidentes({ limit: 200 })
      .then((res) => {
        if (!vivo) return;
        const mapa = new Map<number, Incidente>();
        for (const incidente of res.items) for (const id of incidente.alert_ids ?? []) mapa.set(id, incidente);
        setPorAlerta(mapa);
      })
      .catch(() => undefined); // sem o mapa, o item ainda abre a câmera
    return () => {
      vivo = false;
    };
  }, [aberto]);
  return porAlerta;
}

// ------------------------------------------------------------------- tela ----
function Item({
  alerta,
  nomeDaCamera,
  lida,
  incidente,
  podeAbrirCamera,
  aoAlternar,
  aoVerIncidente,
  aoAbrirCamera,
}: {
  alerta: Alert;
  nomeDaCamera: string | null;
  lida: boolean;
  incidente: Incidente | undefined;
  podeAbrirCamera: boolean;
  aoAlternar: () => void;
  aoVerIncidente: () => void;
  aoAbrirCamera: () => void;
}) {
  const grave = GRAVES.has(alerta.severity);
  const quando = dataHoraCurta(paraDate(alerta.last_seen_at ?? alerta.created_at));
  return (
    <li className={`notif-item ${lida ? "lida" : "nao-lida"}`.trim()} data-testid="notificacao-item" data-lida={lida ? "1" : "0"}>
      <div className="notif-item-topo">
        <Badge tone={grave ? "error" : "neutral"}>{ROTULOS_DE_SEVERIDADE[alerta.severity] ?? "Alerta"}</Badge>
        <span className="notif-item-quando">{quando}</span>
      </div>
      <p className="notif-item-titulo">
        {!lida && <span className="so-leitor">Não lida. </span>}
        {alerta.message}
      </p>
      <p className="notif-item-meta">
        {[nomeDaCamera, alerta.status === "resolved" ? "Resolvido" : "Ativo"].filter(Boolean).join(" · ")}
      </p>
      <div className="notif-item-acoes">
        {incidente && (
          <button type="button" className="small" onClick={aoVerIncidente}>
            Ver incidente
          </button>
        )}
        {podeAbrirCamera && (
          <button type="button" className="ghost small" onClick={aoAbrirCamera}>
            Abrir câmera
          </button>
        )}
        <button type="button" className="ghost small notif-alternar" onClick={aoAlternar}>
          {lida ? "Marcar como não lida" : "Marcar como lida"}
        </button>
      </div>
    </li>
  );
}

export function CentralDeNotificacoes({ userId }: { userId: number }) {
  const mode = useDashboardStore((s) => s.mode);
  const cameras = useDashboardStore((s) => s.cameras);
  const setCamId = useDashboardStore((s) => s.setCamId);
  const setScreen = useDashboardStore((s) => s.setScreen);

  const [aberto, setAberto] = useState(false);
  const [severidade, setSeveridade] = useState("");
  const [cameraId, setCameraId] = useState("");
  const [incidenteAberto, setIncidenteAberto] = useState<{ incidente: Incidente; camera: string | undefined } | null>(null);

  const { itens, carregando, erro, recarregar } = useHistoricoDeAlertas();
  const { lidas, marcar, desmarcar } = useLidas(userId);
  const incidentes = useIncidentesDosAlertas(aberto);

  const raizRef = useRef<HTMLDivElement>(null);
  const sinoRef = useRef<HTMLButtonElement>(null);
  const painelRef = useRef<HTMLDivElement>(null);
  const painelId = useId();
  const tituloId = useId();

  const nomes = useMemo(() => new Map(cameras.map((c) => [c.id, c.name])), [cameras]);
  const naoLidas = itens.filter((a) => !lidas.has(a.id));
  const temGraveNaoLida = naoLidas.some((a) => GRAVES.has(a.severity));
  const visiveis = itens.filter(
    (a) => (!severidade || a.severity === severidade) && (!cameraId || String(a.camera_id) === cameraId),
  );
  const comFiltro = Boolean(severidade || cameraId);

  const fechar = useCallback((devolverFoco: boolean) => {
    setAberto(false);
    if (devolverFoco) sinoRef.current?.focus();
  }, []);

  // Ao abrir: atualiza a lista e põe o foco no painel (o leitor de tela anuncia o nome do diálogo).
  useEffect(() => {
    if (!aberto) return;
    void recarregar();
    painelRef.current?.focus();
  }, [aberto, recarregar]);

  // Esc fecha e devolve o foco ao sino; clique ou foco fora fecham sem roubar o foco.
  useEffect(() => {
    if (!aberto) return;
    const tecla = (e: KeyboardEvent) => {
      if (e.key === "Escape") fechar(true);
    };
    const clique = (e: MouseEvent) => {
      if (raizRef.current && !raizRef.current.contains(e.target as Node)) fechar(false);
    };
    const foco = (e: FocusEvent) => {
      if (raizRef.current && e.target instanceof Node && !raizRef.current.contains(e.target)) fechar(false);
    };
    document.addEventListener("keydown", tecla);
    document.addEventListener("mousedown", clique);
    document.addEventListener("focusin", foco);
    return () => {
      document.removeEventListener("keydown", tecla);
      document.removeEventListener("mousedown", clique);
      document.removeEventListener("focusin", foco);
    };
  }, [aberto, fechar]);

  const abrirIncidente = (alerta: Alert, incidente: Incidente) => {
    marcar([alerta.id]);
    setAberto(false);
    setIncidenteAberto({ incidente, camera: alerta.camera_id != null ? nomes.get(alerta.camera_id) : undefined });
  };
  const abrirCamera = (alerta: Alert) => {
    if (alerta.camera_id == null) return;
    marcar([alerta.id]);
    setCamId(alerta.camera_id);
    setScreen("focus");
    fechar(false);
  };

  const rotuloDoSino = naoLidas.length
    ? `Central de notificações, ${pluralizar(naoLidas.length, "não lida", "não lidas")}`
    : "Central de notificações";

  return (
    <div className="notif" ref={raizRef}>
      <button
        ref={sinoRef}
        type="button"
        className="icon notif-sino"
        aria-haspopup="dialog"
        aria-expanded={aberto}
        aria-controls={aberto ? painelId : undefined}
        aria-label={rotuloDoSino}
        title="Central de notificações"
        data-testid="central-notificacoes"
        onClick={() => setAberto((v) => !v)}
      >
        <IconeSino />
        {naoLidas.length > 0 && (
          <span className="notif-contador" data-grave={temGraveNaoLida ? "1" : "0"} data-testid="notificacoes-nao-lidas" aria-hidden="true">
            {naoLidas.length > 99 ? "99+" : naoLidas.length}
          </span>
        )}
      </button>

      {aberto && (
        <div
          ref={painelRef}
          id={painelId}
          className="notif-painel card"
          role="dialog"
          aria-labelledby={tituloId}
          tabIndex={-1}
          data-testid="central-notificacoes-painel"
        >
          <header className="notif-cabeca">
            <div>
              <h2 id={tituloId}>Notificações</h2>
              <p className="notif-resumo" role="status">
                {naoLidas.length ? pluralizar(naoLidas.length, "não lida", "não lidas") : "Tudo lido"}
              </p>
            </div>
            <button
              type="button"
              className="ghost small"
              disabled={!naoLidas.length}
              title="Marca como lidas todas as notificações da lista, mesmo as escondidas pelos filtros"
              onClick={() => marcar(itens.map((a) => a.id))}
            >
              Marcar todas como lidas
            </button>
          </header>

          <div className="notif-filtros">
            <label className="notif-filtro">
              <span>Severidade</span>
              <select value={severidade} onChange={(e) => setSeveridade(e.target.value)}>
                <option value="">Todas</option>
                {SEVERIDADES.map((s) => (
                  <option key={s} value={s}>
                    {ROTULOS_DE_SEVERIDADE[s]}
                  </option>
                ))}
              </select>
            </label>
            {cameras.length > 1 && (
              <label className="notif-filtro">
                <span>Câmera</span>
                <select value={cameraId} onChange={(e) => setCameraId(e.target.value)}>
                  <option value="">Todas</option>
                  {cameras.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </label>
            )}
          </div>

          <div className="notif-lista-area">
            {carregando && !itens.length ? (
              <div aria-busy="true" className="notif-estado">
                <PanelSkeleton lines={4} />
              </div>
            ) : erro && !itens.length ? (
              <div className="notif-estado" role="alert">
                <p>{erro}</p>
                <button type="button" className="small" onClick={() => void recarregar()}>
                  Tentar de novo
                </button>
              </div>
            ) : !itens.length ? (
              <EmptyState ilustracao={<IlustracaoEscudo />} titulo="Nenhuma notificação">
                Quando uma câmera detectar algo, o alerta aparece aqui, com o histórico das últimas ocorrências.
              </EmptyState>
            ) : !visiveis.length ? (
              <EmptyState
                titulo="Nenhum alerta com esses filtros"
                acao={
                  <button
                    type="button"
                    className="small"
                    onClick={() => {
                      setSeveridade("");
                      setCameraId("");
                    }}
                  >
                    Limpar filtros
                  </button>
                }
              >
                Mude a severidade ou a câmera para ver mais.
              </EmptyState>
            ) : (
              <ul className="notif-lista" aria-label={comFiltro ? "Alertas filtrados" : "Alertas recentes"}>
                {visiveis.map((alerta) => {
                  const lida = lidas.has(alerta.id);
                  const existe = alerta.camera_id != null && nomes.has(alerta.camera_id);
                  return (
                    <Item
                      key={alerta.id}
                      alerta={alerta}
                      nomeDaCamera={alerta.camera_id == null ? null : (nomes.get(alerta.camera_id) ?? "Câmera removida")}
                      lida={lida}
                      incidente={incidentes.get(alerta.id)}
                      podeAbrirCamera={existe && mode !== "operator"}
                      aoAlternar={() => (lida ? desmarcar(alerta.id) : marcar([alerta.id]))}
                      aoVerIncidente={() => {
                        const incidente = incidentes.get(alerta.id);
                        if (incidente) abrirIncidente(alerta, incidente);
                      }}
                      aoAbrirCamera={() => abrirCamera(alerta)}
                    />
                  );
                })}
              </ul>
            )}
          </div>
        </div>
      )}

      {incidenteAberto && (
        <IncidenteDetalhe
          incidente={incidenteAberto.incidente}
          nomeDaCamera={incidenteAberto.camera}
          onClose={() => {
            setIncidenteAberto(null);
            window.setTimeout(() => sinoRef.current?.focus(), 0);
          }}
        />
      )}
    </div>
  );
}
