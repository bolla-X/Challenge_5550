import { useEffect, useState } from "react";
import { EmptyState, PanelSkeleton } from "./common";
import { IlustracaoCadeia } from "./ilustracoes";
import { VerificarIntegridade } from "./incidente-detalhe";

/**
 * Auditoria (X3, `/auditoria`): a cadeia de custódia inteira e a verificação
 * de integridade. É o argumento de LGPD e de prova: quem viu, o que foi
 * gravado e se alguma coisa mudou depois.
 */

type Elo = { id: number; tipo: string; ref: string; descricao: string; criado_em: string; elo_sha256: string; camera_id: number | null };

const TIPO: Record<string, string> = { alerta: "Alerta", snapshot: "Quadro", clipe: "Replay", privacidade: "Privacidade", evento: "Evento" };

export function AuditoriaScreen() {
  const [elos, setElos] = useState<Elo[] | null>(null);
  const [total, setTotal] = useState(0);
  const [erro, setErro] = useState<string | null>(null);

  const carregar = () => {
    setErro(null);
    fetch("/api/custodia?limit=100", { credentials: "same-origin" })
      .then(async (r) => {
        if (!r.ok) throw new Error(r.status === 403 ? "A auditoria é para o técnico ou o supervisor." : `HTTP ${r.status}`);
        return r.json();
      })
      .then((d) => {
        setElos(d.items);
        setTotal(d.total);
      })
      .catch((e) => setErro(e instanceof Error ? e.message : "falha"));
  };
  useEffect(carregar, []);

  return (
    <div className="screen auditoria" data-testid="auditoria">
      <div className="screen-head">
        <h1>Auditoria das evidências</h1>
        <span className="screen-sub">{elos ? `${total} elo${total === 1 ? "" : "s"} na cadeia de custódia` : <span className="skeleton-block skeleton-inline" />}</span>
        <div className="screen-actions">
          <a className="button ghost" href="/">
            Painel
          </a>
        </div>
      </div>
      <section className="card">
        <div className="card-body">
          <VerificarIntegridade />
        </div>
      </section>
      <section className="card">
        <div className="card-head">
          <div>
            <h2>Elos mais recentes</h2>
            <p>Alertas, quadros, replays e trocas de privacidade, na ordem em que entraram.</p>
          </div>
        </div>
        <div className="card-body">
          {erro ? (
            <div className="sim-erro" role="alert">
              {erro}
              <button type="button" className="ghost small" onClick={carregar}>
                Tentar de novo
              </button>
            </div>
          ) : !elos ? (
            <PanelSkeleton lines={5} />
          ) : elos.length === 0 ? (
            <EmptyState ilustracao={<IlustracaoCadeia />} titulo="A cadeia ainda está vazia">
              O primeiro alerta, quadro, replay ou troca de privacidade entra aqui com o seu SHA-256.
            </EmptyState>
          ) : (
            <table className="sim-tabela auditoria-tabela">
              <thead>
                <tr>
                  <th scope="col">#</th>
                  <th scope="col">Tipo</th>
                  <th scope="col">Evidência</th>
                  <th scope="col">Quando</th>
                  <th scope="col">SHA-256 do elo</th>
                </tr>
              </thead>
              <tbody>
                {elos.map((e) => (
                  <tr key={e.id}>
                    <td className="t-data">{e.id}</td>
                    <td>{TIPO[e.tipo] ?? e.tipo}</td>
                    <th scope="row">{e.descricao}</th>
                    <td className="t-data">{quando(e.criado_em)}</td>
                    <td className="t-data custodia-hash" title={e.elo_sha256}>
                      {e.elo_sha256.slice(0, 16)}…
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>
    </div>
  );
}

export default AuditoriaScreen;

/** "14/10 08:17:30": data curta e hora, sem a vírgula do toLocaleString. */
function quando(iso: string): string {
  const d = new Date(iso);
  const dois = (n: number) => String(n).padStart(2, "0");
  return `${dois(d.getDate())}/${dois(d.getMonth() + 1)} ${dois(d.getHours())}:${dois(d.getMinutes())}:${dois(d.getSeconds())}`;
}
