import { useEffect, useState } from "react";
import { decimal } from "../utils/formato";

/**
 * Prova de escala (F10): N câmeras virtuais lendo uma fixture, workers de
 * verdade, e o que acontece com o FPS e a idade da análise por câmera.
 * O número é o desta máquina, agora — não uma projeção.
 */
type Linha = { camera_id: number; fps_publicado: number; fps_analisado: number; idade_analise_p95_ms: number | null };
type Estado = { n: number; cameras: Linha[]; adaptativo: { degradado: boolean; reducoes: string[] } | null };

async function chamar(metodo: string, corpo?: unknown): Promise<Estado | null> {
  const r = await fetch("/api/escala", {
    method: metodo,
    credentials: "same-origin",
    headers: corpo ? { "Content-Type": "application/json" } : undefined,
    body: corpo ? JSON.stringify(corpo) : undefined,
  });
  if (!r.ok) throw new Error((await r.json().catch(() => ({})))?.error ?? "Falha na prova de escala.");
  return metodo === "GET" ? ((await r.json()) as Estado) : null;
}

export function ScaleProof({ onClose }: { onClose: () => void }) {
  const [n, setN] = useState(4);
  const [estado, setEstado] = useState<Estado | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);

  useEffect(() => {
    let vivo = true;
    const atualizar = () =>
      chamar("GET")
        .then((e) => vivo && setEstado(e))
        .catch((e: Error) => vivo && setErro(e.message));
    atualizar();
    const id = window.setInterval(atualizar, 1500);
    return () => {
      vivo = false;
      window.clearInterval(id);
    };
  }, []);

  const executar = async (metodo: "POST" | "DELETE") => {
    setOcupado(true);
    setErro(null);
    try {
      await chamar(metodo, metodo === "POST" ? { n } : undefined);
    } catch (e) {
      setErro((e as Error).message);
    } finally {
      setOcupado(false);
    }
  };

  const linhas = estado?.cameras ?? [];
  const media = (k: keyof Linha) => (linhas.length ? linhas.reduce((a, l) => a + Number(l[k] ?? 0), 0) / linhas.length : 0);

  return (
    <div className="modal-scrim" onClick={onClose}>
      <div className="card modal escala-modal" role="dialog" aria-labelledby="escala-titulo" onClick={(e) => e.stopPropagation()}>
        <header className="replay-cab">
          <div>
            <h2 id="escala-titulo">Prova de escala</h2>
            <p className="t-secondary">Câmeras virtuais com processamento real lendo a mesma gravação. Os números são desta máquina, agora.</p>
          </div>
          <button type="button" className="ghost small" onClick={onClose}>
            Fechar
          </button>
        </header>
        <div className="actions">
          <label className="escala-n">
            Câmeras
            <input type="number" min={1} max={12} value={n} onChange={(e) => setN(Math.max(1, Math.min(12, Number(e.target.value) || 1)))} />
          </label>
          <button type="button" className="primary" disabled={ocupado} onClick={() => executar("POST")}>
            {estado?.n ? "Aplicar" : "Iniciar"}
          </button>
          <button type="button" className="ghost" disabled={ocupado || !estado?.n} onClick={() => executar("DELETE")}>
            Encerrar e remover
          </button>
        </div>
        {erro && <p className="status-text error">{erro}</p>}
        {estado?.adaptativo?.degradado && (
          <p className="status-text" role="status">
            Degradado: {estado.adaptativo.reducoes.join(" · ")}
          </p>
        )}
        {linhas.length > 0 && (
          <table className="escala-tabela">
            <thead>
              <tr>
                <th>Câmera</th>
                <th>Vídeo (fps)</th>
                <th>Análise (fps)</th>
                <th>Idade da análise p95</th>
              </tr>
            </thead>
            <tbody>
              {linhas.map((l) => (
                <tr key={l.camera_id}>
                  <td>#{l.camera_id}</td>
                  <td className="t-data">{decimal(l.fps_publicado)}</td>
                  <td className="t-data">{decimal(l.fps_analisado, 2)}</td>
                  <td className="t-data">{l.idade_analise_p95_ms == null ? "sem dado" : `${Math.round(l.idade_analise_p95_ms)} ms`}</td>
                </tr>
              ))}
              <tr className="escala-media">
                <td>Média ({linhas.length})</td>
                <td className="t-data">{decimal(media("fps_publicado"))}</td>
                <td className="t-data">{decimal(media("fps_analisado"), 2)}</td>
                <td className="t-data">{Math.round(media("idade_analise_p95_ms"))} ms</td>
              </tr>
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
