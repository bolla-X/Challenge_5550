import { useEffect, useState } from "react";
import { getTv } from "../api/endpoints";
import type { TvSetor, TvEstado } from "../api/types";

/**
 * Modo TV / Andon (G8), em `/tv`: legível a 5 m. Um bloco por SETOR com a
 * conformidade de agora, a sequência de minutos com 100 % dos EPIs exigidos,
 * o progresso das metas e as conquistas do turno. Nada por pessoa: a
 * pontuação é do setor (princípios em app/services/andon.py).
 */

function pct(v: number | null): string {
  return v == null ? "—" : `${Math.round(v * 100)}%`;
}

function Progresso({ rotulo, valor, meta }: { rotulo: string; valor: number; meta: number | null }) {
  if (!meta) {
    return (
      <div className="tv-meta">
        <span>{rotulo}</span>
        <strong className="t-data">{valor}</strong>
      </div>
    );
  }
  const fracao = Math.min(1, valor / meta);
  return (
    <div className="tv-meta">
      <span>{rotulo}</span>
      <strong className="t-data">
        {valor} / {meta}
      </strong>
      <span className="tv-barra" aria-hidden="true">
        <span style={{ transform: `scaleX(${fracao})` }} />
      </span>
    </div>
  );
}

function Setor({ s }: { s: TvSetor }) {
  const noAr = s.cameras.filter((c) => c.running).length;
  return (
    <section className="tv-setor" data-testid={`tv-setor-${s.setor}`}>
      <header>
        <h2>{s.setor}</h2>
        <span className="tv-cameras">
          {s.cameras.map((c) => (
            <span key={c.camera_id} className={`dot ${c.running ? "ok" : "off"}`} title={c.nome} />
          ))}
          {noAr} de {s.cameras.length} no ar
        </span>
      </header>
      <div className="tv-numeros">
        <div>
          <strong className="tv-grande t-data" data-testid="tv-conformidade">
            {pct(s.conformidade_atual)}
          </strong>
          <span>EPIs exigidos em uso agora</span>
        </div>
        <div>
          <strong className="tv-grande t-data" data-testid="tv-sequencia">
            {s.sequencia_min} min
          </strong>
          <span>seguidos com 100% dos EPIs</span>
        </div>
      </div>
      <Progresso rotulo="Minutos conformes no turno" valor={s.minutos_conformes} meta={s.metas.minutos_conformes} />
      <Progresso rotulo="Check-ins no portal" valor={s.checkins_portal} meta={s.metas.checkins_portal} />
      {s.alertas_reconhecidos > 0 && (
        <div className="tv-meta">
          <span>Alertas críticos reconhecidos</span>
          <strong className="t-data">
            {s.alertas_reconhecidos} / {s.alertas_criticos}
          </strong>
        </div>
      )}
      {s.conquistas.length > 0 && (
        <ul className="tv-conquistas" aria-label="Conquistas do setor">
          {s.conquistas.map((c) => (
            <li key={c.id} data-testid={`tv-conquista-${c.id}`}>
              {c.texto}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function TvScreen({ embutido = false }: { embutido?: boolean }) {
  const [estado, setEstado] = useState<TvEstado | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [agora, setAgora] = useState(() => new Date());
  useEffect(() => {
    let vivo = true;
    const tick = () => {
      setAgora(new Date());
      getTv()
        .then((e) => {
          if (!vivo) return;
          setEstado(e);
          setErro(null);
        })
        .catch((e: Error) => vivo && setErro(e.message));
    };
    tick();
    const id = window.setInterval(tick, 5000);
    return () => {
      vivo = false;
      window.clearInterval(id);
    };
  }, []);

  return (
    <div className={`tv ${embutido ? "embutido" : ""}`.trim()} data-testid="tv">
      {!embutido && (
        <header className="tv-cabeca">
          <h1>Segurança do turno</h1>
          <span className="t-data">{agora.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>
        </header>
      )}
      {erro && <p className="status-text error">{erro}</p>}
      {!estado ? (
        <p className="centered-empty">Carregando…</p>
      ) : (
        <div className="tv-grade">
          {estado.setores.map((s) => (
            <Setor key={s.setor} s={s} />
          ))}
        </div>
      )}
      <footer className="tv-rodape muted">
        Pontuação por setor, nunca por pessoa. Minutos sem ninguém na câmera não contam. Últimas {estado?.janela_h ?? 8} h.
      </footer>
    </div>
  );
}
