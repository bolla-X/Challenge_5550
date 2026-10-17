import { mensagemDeErro } from "../utils/erros";
import { useCallback, useEffect, useState } from "react";
import { useDashboardStore } from "../store/dashboardStore";
import { Badge, EmptyState, Numero, PanelSkeleton } from "./common";
import { IlustracaoPlanta } from "./ilustracoes";
import { dataHoraCurta, paraDate } from "../utils/datas";
import { pluralizar } from "../utils/formato";

/**
 * Modo Evacuação (M3). Contagem por câmera, nunca por pessoa: track ID é rótulo
 * de rastreio, não identidade. O aviso de dupla contagem fica sempre visível.
 * Ao encerrar, o relatório entra na cadeia de custódia (X3) — app/services/evacuacao.py.
 */

export const AVISO_DUPLA_CONTAGEM = "Contagem por câmera — pode haver dupla contagem se as câmeras se sobrepõem.";

type CameraNaEvacuacao = {
  id: number;
  nome: string;
  online: boolean;
  pessoas: number;
  zonas: Record<string, number>;
  maximo: number;
  idade_analise_s: number | null;
  desatualizada: boolean;
};
type Posicao = { camera_id: number; track_id: number | string; x: number; y: number; visto_em: string; ha_s: number; visivel_agora: boolean };
type Resumo = {
  numero: number;
  inicio: string;
  fim: string;
  duracao_s: number;
  total_maximo_somado: number;
  chegadas_ponto_de_encontro: number | null;
  sha256: string;
};
type EstadoAtivo = {
  ativa: true;
  inicio: string;
  iniciada_por: string;
  segundos: number;
  ponto_de_encontro_camera_id: number | null;
  cameras: CameraNaEvacuacao[];
  total: number;
  aviso: string;
  ultimas_posicoes: Posicao[];
  chegadas_ponto_de_encontro: number | null;
};
type EstadoInativo = { ativa: false; ultima: Resumo | null; aviso?: string };
type EstadoDaEvacuacao = EstadoAtivo | EstadoInativo;

export function cronometro(segundos: number): string {
  const s = Math.max(0, Math.floor(segundos));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const r = s % 60;
  const dois = (n: number) => String(n).padStart(2, "0");
  return h ? `${h}:${dois(m)}:${dois(r)}` : `${dois(m)}:${dois(r)}`;
}

async function pedir<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, { credentials: "same-origin", headers: { "Content-Type": "application/json" }, ...init });
  const corpo = await r.json().catch(() => null);
  if (!r.ok) {
    const msg = corpo && typeof corpo === "object" && "error" in corpo ? String((corpo as { error: unknown }).error) : `Falha na comunicação com o servidor (código ${r.status}).`;
    throw Object.assign(new Error(msg), { status: r.status });
  }
  return corpo as T;
}

function useEvacuacao() {
  const [estado, setEstado] = useState<EstadoDaEvacuacao | null>(null);
  const [erro, setErro] = useState<{ msg: string; status?: number } | null>(null);
  const [n, setN] = useState(0);
  const ativa = estado?.ativa === true;
  useEffect(() => {
    let vivo = true;
    const tick = () =>
      pedir<EstadoDaEvacuacao>("/api/evacuacao")
        .then((d) => {
          if (!vivo) return;
          setEstado(d);
          setErro(null);
        })
        .catch((e: Error & { status?: number }) => vivo && setErro({ msg: mensagemDeErro(e, "Falha ao ler a evacuação."), status: e.status }));
    tick();
    const id = window.setInterval(tick, ativa ? 1000 : 5000);
    return () => {
      vivo = false;
      window.clearInterval(id);
    };
  }, [ativa, n]);
  return { estado, erro, recarregar: useCallback(() => setN((x) => x + 1), []) };
}

function MapaDePosicoes({ posicoes }: { posicoes: Posicao[] }) {
  if (!posicoes.length) {
    return <p className="evac-nota">Nenhuma posição na planta ainda. Só aparecem câmeras com a planta calibrada (G5).</p>;
  }
  return (
    <svg className="evac-mapa" viewBox="0 0 100 100" role="img" aria-label={`Última posição vista de ${posicoes.length} rótulos de rastreio na planta`}>
      <rect x="0.5" y="0.5" width="99" height="99" rx="2" className="evac-mapa-fundo" />
      {posicoes.map((p) => (
        <g key={`${p.camera_id}-${p.track_id}`} transform={`translate(${Math.min(99, Math.max(1, p.x * 100))} ${Math.min(99, Math.max(1, p.y * 100))})`}>
          <circle r="1.8" className={p.visivel_agora ? "evac-ponto agora" : "evac-ponto antes"} />
          <title>{`Rótulo ${p.track_id} · câmera ${p.camera_id} · visto há ${Math.round(p.ha_s)} s`}</title>
        </g>
      ))}
    </svg>
  );
}

function Confirmar({ titulo, texto, acao, onSim, onNao, ocupado }: {
  titulo: string; texto: string; acao: string; onSim: () => void; onNao: () => void; ocupado: boolean;
}) {
  useEffect(() => {
    const esc = (e: KeyboardEvent) => e.key === "Escape" && onNao();
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [onNao]);
  return (
    <div className="modal-scrim" onClick={onNao}>
      <div className="card modal" role="alertdialog" aria-modal="true" aria-labelledby="evac-confirma-titulo" onClick={(e) => e.stopPropagation()}>
        <h2 id="evac-confirma-titulo">{titulo}</h2>
        <p>{texto}</p>
        <div className="modal-acoes">
          <button type="button" className="ghost" onClick={onNao} disabled={ocupado}>Cancelar</button>
          <button type="button" className="danger" onClick={onSim} disabled={ocupado} autoFocus>
            {ocupado ? "Aguarde…" : acao}
          </button>
        </div>
      </div>
    </div>
  );
}

export function EvacuacaoScreen() {
  const user = useDashboardStore((s) => s.user);
  const cameras = useDashboardStore((s) => s.cameras);
  const { estado, erro, recarregar } = useEvacuacao();
  const [ponto, setPonto] = useState<string>("");
  const [confirmando, setConfirmando] = useState<"iniciar" | "encerrar" | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [falha, setFalha] = useState<string | null>(null);
  const [relatorio, setRelatorio] = useState<{ arquivo: string; custodia_registrada: boolean; relatorio: Resumo } | null>(null);
  const podeAcionar = user?.role === "supervisor";

  const executar = async (acao: "iniciar" | "encerrar") => {
    setOcupado(true);
    setFalha(null);
    try {
      if (acao === "iniciar") {
        await pedir("/api/evacuacao/iniciar", {
          method: "POST",
          body: JSON.stringify(ponto ? { ponto_de_encontro_camera_id: Number(ponto) } : {}),
        });
        setRelatorio(null);
      } else {
        setRelatorio(await pedir("/api/evacuacao/encerrar", { method: "POST", body: "{}" }));
      }
      setConfirmando(null);
      recarregar();
    } catch (e) {
      setFalha(mensagemDeErro(e, "Não foi possível concluir."));
    } finally {
      setOcupado(false);
    }
  };

  if (erro?.status === 403) {
    return (
      <div className="screen">
        <EmptyState titulo="Acesso restrito">
          O Modo Evacuação é visto por Técnico e Supervisor, e acionado pelo Supervisor. Peça a quem tem esse perfil.
        </EmptyState>
      </div>
    );
  }
  if (!estado) {
    return <div className="screen" aria-busy="true">{erro ? <p role="alert">{erro.msg}</p> : <PanelSkeleton lines={6} />}</div>;
  }

  const aviso = estado.aviso || AVISO_DUPLA_CONTAGEM;
  return (
    <div className={`screen evac ${estado.ativa ? "evac-ativa" : ""}`} data-testid="evacuacao" data-ativa={estado.ativa ? "1" : "0"}>
      <header className="evac-topo">
        <div>
          <p className="evac-sobretitulo">{estado.ativa ? "Evacuação em andamento" : "Modo Evacuação"}</p>
          <h1 className="evac-titulo">
            {estado.ativa ? (
              <span className="evac-cronometro" data-testid="evac-cronometro" aria-live="off">{cronometro(estado.segundos)}</span>
            ) : (
              "Pronto para acionar"
            )}
          </h1>
        </div>
        <div className="evac-acoes">
          {!estado.ativa && podeAcionar && (
            <>
              <label className="evac-ponto">
                <span>Ponto de encontro</span>
                <select value={ponto} onChange={(e) => setPonto(e.target.value)} aria-label="Câmera do ponto de encontro">
                  <option value="">Sem câmera no ponto</option>
                  {cameras.map((c) => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
              </label>
              <button type="button" className="danger grande" onClick={() => setConfirmando("iniciar")}>Acionar evacuação</button>
            </>
          )}
          {estado.ativa && podeAcionar && (
            <button type="button" className="grande" onClick={() => setConfirmando("encerrar")}>Encerrar evacuação</button>
          )}
          {!podeAcionar && <p className="evac-nota">Só o Supervisor aciona e encerra.</p>}
        </div>
      </header>

      <p className="evac-aviso" role="note" data-testid="evac-aviso">{aviso}</p>
      {falha && <p className="evac-falha" role="alert">{falha}</p>}

      {estado.ativa ? (
        <>
          <section className="evac-numeros" aria-label="Contagem agora">
            <div className="evac-numero">
              <span className="evac-numero-valor" data-testid="evac-total"><Numero valor={estado.total} /></span>
              <span className="evac-numero-rotulo">{pluralizar(estado.total, "pessoa detectada", "pessoas detectadas")} agora (soma das câmeras)</span>
            </div>
            <div className="evac-numero">
              <span className="evac-numero-valor">
                {estado.chegadas_ponto_de_encontro == null ? "—" : <Numero valor={estado.chegadas_ponto_de_encontro} />}
              </span>
              <span className="evac-numero-rotulo">
                {estado.chegadas_ponto_de_encontro == null
                  ? "Sem câmera no ponto de encontro"
                  : "No ponto de encontro (pico simultâneo desde o início)"}
              </span>
            </div>
          </section>
          <section className="evac-grade" aria-label="Por câmera">
            {estado.cameras.map((c) => (
              <article key={c.id} className="card evac-camera" data-online={c.online ? "1" : "0"}>
                <header>
                  <h2>{c.nome}</h2>
                  {!c.online ? (
                    <Badge tone="error">Sem sinal</Badge>
                  ) : c.desatualizada ? (
                    <Badge tone="warn">Análise atrasada</Badge>
                  ) : c.id === estado.ponto_de_encontro_camera_id ? (
                    <Badge tone="info">Ponto de encontro</Badge>
                  ) : null}
                </header>
                <p className="evac-camera-valor"><Numero valor={c.pessoas} /></p>
                <p className="evac-camera-rotulo">{pluralizar(c.pessoas, "pessoa agora", "pessoas agora")} · pico {c.maximo}</p>
                {Object.entries(c.zonas).map(([zona, n]) => (
                  <p key={zona} className="evac-zona">{zona}: {n} na zona</p>
                ))}
              </article>
            ))}
          </section>
          <section className="card evac-planta">
            <h2>Última posição vista na planta</h2>
            <MapaDePosicoes posicoes={estado.ultimas_posicoes} />
            <p className="evac-nota">Pontos cheios: vistos agora. Vazados: última posição antes de sumir. Cada ponto é um rótulo de rastreio, não uma pessoa identificada.</p>
          </section>
        </>
      ) : (
        <section className="card evac-ultima">
          {relatorio ? (
            <>
              <h2>Relatório nº {relatorio.relatorio.numero} encerrado</h2>
              <p>
                Duração {cronometro(relatorio.relatorio.duracao_s)} · pico somado {relatorio.relatorio.total_maximo_somado}
                {relatorio.relatorio.chegadas_ponto_de_encontro != null && ` · ponto de encontro ${relatorio.relatorio.chegadas_ponto_de_encontro}`}
              </p>
              <p data-testid="evac-custodia">
                {relatorio.custodia_registrada
                  ? "Registrado na cadeia de custódia."
                  : "A cadeia de custódia está desligada neste ambiente: o relatório foi salvo, mas sem elo de integridade."}
              </p>
              <a className="button ghost" href="/auditoria">Verificar integridade na auditoria</a>
            </>
          ) : estado.ultima ? (
            <>
              <h2>Última evacuação: nº {estado.ultima.numero}</h2>
              <p>
                {dataHoraCurta(paraDate(estado.ultima.inicio))} · duração {cronometro(estado.ultima.duracao_s)} · pico somado{" "}
                {estado.ultima.total_maximo_somado}
              </p>
              <a className="button ghost" href="/auditoria">Ver na auditoria</a>
            </>
          ) : (
            <EmptyState ilustracao={<IlustracaoPlanta />} titulo="Nenhuma evacuação registrada">
              Ao acionar, o painel mostra quantas pessoas cada câmera vê agora, a última posição na planta e quantas chegaram ao ponto
              de encontro.
            </EmptyState>
          )}
        </section>
      )}

      {confirmando && (
        <Confirmar
          titulo={confirmando === "iniciar" ? "Acionar a evacuação?" : "Encerrar a evacuação?"}
          texto={
            confirmando === "iniciar"
              ? "O cronômetro começa agora e a contagem por câmera passa a ser registrada."
              : "O relatório é salvo e entra na cadeia de custódia. Não dá para reabrir esta evacuação."
          }
          acao={confirmando === "iniciar" ? "Acionar agora" : "Encerrar e salvar relatório"}
          ocupado={ocupado}
          onNao={() => setConfirmando(null)}
          onSim={() => executar(confirmando)}
        />
      )}
    </div>
  );
}

export default EvacuacaoScreen;
