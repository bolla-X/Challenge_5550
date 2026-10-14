import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import type { Alert, Incidente } from "../api/types";
import { detalheDoIncidente, reconhecerIncidente } from "../api/endpoints";
import { paraDate } from "../utils/datas";
import { pessoasDoIncidente, zonaDoIncidente } from "../utils/incidentes";
import { IncidentReplay } from "./replay";

/**
 * Detalhe do incidente: linha causal por ID (X4), evidências com replay e
 * verificação da cadeia de custódia (X3). Tudo do servidor; nada inferido aqui.
 */

type Passo = { t: number; texto: string; tipo: string; duracao: boolean; alert_id: number | null };
type LinhaCausal = { pessoas: string[]; linhas: Record<string, Passo[]> };
type Elo = { id: number; tipo: string; ref: string; situacao: string; arquivo?: string; descricao: string; elo_sha256: string };
type Verificacao = { integra: boolean; adulterada: boolean; ausentes: number; elos: Elo[]; quebrado: Elo | null; ultimo_elo: string };

const SITUACAO: Record<string, string> = {
  ok: "íntegro",
  conteudo_alterado: "conteúdo alterado",
  registro_alterado: "registro da cadeia alterado",
  cadeia_quebrada: "cadeia quebrada (elo removido ou fora de ordem)",
  ausente: "evidência ausente do disco",
};
const TIPO_ELO: Record<string, string> = { alerta: "Alerta", snapshot: "Quadro", clipe: "Replay", privacidade: "Privacidade", evento: "Evento" };

function horaComSegundos(t: number) {
  return new Date(t * 1000).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function VerificarIntegridade({ incidenteId }: { incidenteId?: number }) {
  const [estado, setEstado] = useState<"parado" | "verificando" | "erro">("parado");
  const [resultado, setResultado] = useState<Verificacao | null>(null);
  const verificar = () => {
    setEstado("verificando");
    fetch(`/api/custodia/verificar${incidenteId != null ? `?incidente_id=${incidenteId}` : ""}`, { credentials: "same-origin" })
      .then(async (r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return (await r.json()) as Verificacao;
      })
      .then((v) => {
        setResultado(v);
        setEstado("parado");
      })
      .catch(() => setEstado("erro"));
  };
  const titulo = !resultado
    ? null
    : resultado.adulterada
      ? "Adulteração detectada"
      : resultado.integra
        ? "Evidências íntegras"
        : "Íntegras, com evidência ausente";
  return (
    <section className="custodia" data-testid="custodia">
      <div className="custodia-cab">
        <div>
          <h3>Cadeia de custódia</h3>
          <p className="t-secondary">Cada evidência tem um SHA-256 encadeado ao anterior: mudar um byte quebra a cadeia daí em diante.</p>
        </div>
        <button type="button" className="small" onClick={verificar} disabled={estado === "verificando"} data-testid="verificar-integridade">
          {estado === "verificando" ? "Verificando…" : "Verificar integridade"}
        </button>
      </div>
      {estado === "erro" && (
        <p className="status-text error" role="alert">
          Não foi possível verificar agora. <button type="button" className="link-button" onClick={verificar}>Tentar de novo</button>
        </p>
      )}
      {resultado && (
        <div className={`custodia-resultado ${resultado.adulterada ? "falha" : resultado.integra ? "ok" : "aviso"}`} data-testid="custodia-resultado" data-integra={resultado.integra ? "1" : "0"}>
          <p className="custodia-veredito">
            <span className="dot" />
            <strong>{titulo}</strong>
            {resultado.quebrado && (
              <span>
                {" "}· elo #{resultado.quebrado.id} ({TIPO_ELO[resultado.quebrado.tipo] ?? resultado.quebrado.tipo}): {SITUACAO[resultado.quebrado.situacao]}
                {resultado.quebrado.arquivo ? ` em ${resultado.quebrado.arquivo}` : ""}
              </span>
            )}
          </p>
          <ol className="custodia-elos">
            {resultado.elos.slice(0, 12).map((e) => (
              <li key={e.id} className={e.situacao}>
                <span className="t-data">#{e.id}</span>
                <span>{TIPO_ELO[e.tipo] ?? e.tipo}</span>
                <span className="custodia-hash t-data" title={e.elo_sha256}>
                  {e.elo_sha256.slice(0, 12)}…
                </span>
                <span>{SITUACAO[e.situacao] ?? e.situacao}</span>
              </li>
            ))}
          </ol>
          <p className="muted">
            Último elo da cadeia: <code className="t-data">{resultado.ultimo_elo.slice(0, 16)}…</code>. Anote no relatório do turno para ancorar a cadeia fora do sistema.
          </p>
        </div>
      )}
    </section>
  );
}

export function IncidenteDetalhe({
  incidente,
  nomeDaCamera,
  onClose,
  inline = false,
}: {
  incidente: Incidente;
  nomeDaCamera?: string;
  onClose: () => void;
  /** No palco (X6): o cartão direto na página, sem fundo escurecido nem portal. */
  inline?: boolean;
}) {
  const [linha, setLinha] = useState<LinhaCausal | null>(null);
  const [alertas, setAlertas] = useState<Alert[]>([]);
  const [pessoa, setPessoa] = useState<string | null>(null);
  const [replay, setReplay] = useState<{ alertId: number; ms?: number } | null>(null);

  useEffect(() => {
    let vivo = true;
    fetch(`/api/incidentes/${incidente.id}/linha-causal`, { credentials: "same-origin" })
      .then((r) => (r.ok ? r.json() : { pessoas: [], linhas: {} }))
      .then((d: LinhaCausal) => {
        if (!vivo) return;
        setLinha(d);
        setPessoa((p) => p ?? d.pessoas[0] ?? null);
      })
      .catch(() => vivo && setLinha({ pessoas: [], linhas: {} }));
    detalheDoIncidente(incidente.id)
      .then((d) => vivo && setAlertas(d.alertas))
      .catch(() => undefined);
    return () => {
      vivo = false;
    };
  }, [incidente.id]);

  useEffect(() => {
    if (inline) return undefined;
    const esc = (e: KeyboardEvent) => e.key === "Escape" && !replay && onClose();
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [onClose, replay, inline]);

  const [reconhecido, setReconhecido] = useState<number | null>(incidente.reconhecido_em_s);
  const reconhecer = () =>
    reconhecerIncidente(incidente.id)
      .then((r) => setReconhecido(r.incidente.reconhecido_em_s ?? 0))
      .catch(() => undefined);
  const passos = pessoa && linha ? linha.linhas[pessoa] ?? [] : [];
  const zona = zonaDoIncidente(incidente);

  const cartao = (
    <>
        <header className="replay-cab">
          <div>
            <h2 id="incidente-titulo">
              {incidente.titulo}
              {zona ? ` · ${zona}` : ""}
            </h2>
            <p className="t-secondary">
              {[nomeDaCamera, pessoasDoIncidente(incidente, 8), `aberto às ${paraDate(incidente.aberto_em).toLocaleTimeString("pt-BR")}`]
                .filter(Boolean)
                .join(" · ")}
            </p>
          </div>
          <div className="incidente-acoes">
            {reconhecido != null ? (
              <span className="chip ok" data-testid="incidente-reconhecido">
                Reconhecido em {Math.round(reconhecido)} s
              </span>
            ) : (
              <button type="button" className="small" onClick={reconhecer} data-testid="incidente-reconhecer">
                Reconhecer
              </button>
            )}
            <button type="button" className="ghost small incidente-fechar" onClick={onClose}>
              Fechar
            </button>
          </div>
        </header>

        <section className="causal" aria-label="Linha causal">
          <div className="causal-cab">
            <h3>Linha causal</h3>
            {linha && linha.pessoas.length > 1 && (
              <div className="segmented" role="tablist" aria-label="ID de rastreio">
                {linha.pessoas.slice(0, 8).map((p) => (
                  <button key={p} type="button" role="tab" aria-selected={pessoa === p} className={pessoa === p ? "active" : ""} onClick={() => setPessoa(p)}>
                    Pessoa {p}
                  </button>
                ))}
              </div>
            )}
          </div>
          {!linha ? (
            <p className="status-text">Montando a linha causal…</p>
          ) : passos.length === 0 ? (
            <p className="t-secondary">Sem eventos registrados para este ID no período.</p>
          ) : (
            <ol className="causal-passos" data-testid="linha-causal">
              {passos.map((p, i) => (
                <li key={`${p.t}-${i}`} className={`${p.tipo} ${p.duracao ? "duracao" : ""}`}>
                  {p.duracao ? <span className="causal-seta" aria-hidden="true">→</span> : <time className="t-data">{horaComSegundos(p.t)}</time>}
                  <span className="causal-texto">{p.texto}</span>
                  {p.alert_id != null && !p.duracao && (
                    <button type="button" className="link-button" onClick={() => setReplay({ alertId: p.alert_id as number, ms: p.t * 1000 })}>
                      ver quadro
                    </button>
                  )}
                </li>
              ))}
            </ol>
          )}
          <p className="muted">Montada só com o que foi registrado (aproximação, alertas, reconhecimento). Sem IA generativa.</p>
        </section>

        {alertas.length > 0 && (
          <section className="incidente-alertas">
            <h3>Evidências ({alertas.length})</h3>
            <ul>
              {alertas.slice(0, 10).map((a) => (
                <li key={a.id}>
                  <span>{a.message}</span>
                  <button type="button" className="ghost small" onClick={() => setReplay({ alertId: a.id })}>
                    Ver replay
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}

        <VerificarIntegridade incidenteId={incidente.id} />
    </>
  );
  const replayModal = replay && (
    <IncidentReplay alertId={replay.alertId} cameraName={nomeDaCamera} irParaMs={replay.ms} onClose={() => setReplay(null)} />
  );
  if (inline) {
    return (
      <div className="card incidente-modal incidente-inline" data-testid="incidente-detalhe">
        {cartao}
        {replayModal}
      </div>
    );
  }
  // Portal: o detalhe abre de dentro de um <summary>, e o clique no modal não
  // pode abrir/fechar o <details> por baixo.
  return createPortal(
    <>
      <div className="modal-scrim" onClick={onClose}>
        <div className="card modal incidente-modal" role="dialog" aria-labelledby="incidente-titulo" onClick={(e) => e.stopPropagation()} data-testid="incidente-detalhe">
          {cartao}
        </div>
      </div>
      {replayModal}
    </>,
    document.body,
  );
}
