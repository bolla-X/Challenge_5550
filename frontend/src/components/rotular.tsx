import { mensagemDeErro } from "../utils/erros";
import { useCallback, useEffect, useState } from "react";
import { rotuloDaClasse } from "../api/ppe";
import { pluralizar } from "../utils/formato";

/**
 * Aprendizado ativo (G9), em `/rotular`: um recorte por vez, com a classe que
 * o modelo achou (em dúvida). → confirma, ← rejeita (ou os botões, no toque).
 * O zip exportado é um dataset YOLO só com os confirmados. Sem treino no app.
 */

type Item = { id: string; classe: string; confianca: number; camera_id: number | null };
type Contagem = { fila: number; confirmados: number; rejeitados: number };
type Resposta = { habilitado: boolean; item: Item | null; contagem: Contagem | null };

async function pedir<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, { credentials: "same-origin", headers: { "Content-Type": "application/json" }, ...init });
  if (!r.ok) throw new Error((await r.json().catch(() => ({})))?.error ?? "Não foi possível consultar os rótulos.");
  return r.json() as Promise<T>;
}

export function RotularScreen() {
  const [estado, setEstado] = useState<Resposta | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);

  const carregar = useCallback(() => {
    pedir<Resposta>("/api/rotulos/proximo")
      .then((r) => {
        setEstado(r);
        setErro(null);
      })
      .catch((e) => setErro(mensagemDeErro(e, "Não foi possível carregar os dados.")));
  }, []);

  useEffect(() => {
    carregar();
    const id = window.setInterval(() => {
      // Fila vazia: olha de novo de tempos em tempos (as câmeras vão enchendo).
      if (!document.hidden) carregar();
    }, 4000);
    return () => window.clearInterval(id);
  }, [carregar]);

  const decidir = useCallback(
    (decisao: "confirmar" | "rejeitar") => {
      const item = estado?.item;
      if (!item || ocupado) return;
      setOcupado(true);
      pedir<{ contagem: Contagem }>(`/api/rotulos/${item.id}`, { method: "POST", body: JSON.stringify({ decisao }) })
        .then(carregar)
        .catch((e) => setErro(mensagemDeErro(e, "Não foi possível carregar os dados.")))
        .finally(() => setOcupado(false));
    },
    [estado, ocupado, carregar],
  );

  useEffect(() => {
    const tecla = (e: KeyboardEvent) => {
      if (e.key === "ArrowRight") decidir("confirmar");
      else if (e.key === "ArrowLeft") decidir("rejeitar");
    };
    window.addEventListener("keydown", tecla);
    return () => window.removeEventListener("keydown", tecla);
  }, [decidir]);

  const item = estado?.item;
  const nome = item ? rotuloDaClasse(item.classe) : "";
  const c = estado?.contagem;

  return (
    <div className="rotular" data-testid="rotular">
      <header className="rotular-cabeca">
        <h1>Rotular recortes</h1>
        <span className="muted t-data" data-testid="rotular-contagem">
          {c ? `${c.fila} na fila · ${pluralizar(c.confirmados, "confirmado")} · ${pluralizar(c.rejeitados, "rejeitado")}` : ""}
        </span>
      </header>
      {erro && <p className="status-text error">{erro}</p>}
      {estado && !estado.habilitado ? (
        <p className="centered-empty">Aprendizado ativo desligado (APRENDIZADO_ATIVO=false).</p>
      ) : !item ? (
        <p className="centered-empty" data-testid="rotular-vazio">
          Nada para rotular agora. Os recortes chegam quando o modelo fica em dúvida sobre um EPI.
        </p>
      ) : (
        <section className="rotular-cartao card" data-testid="rotular-item" data-id={item.id}>
          <p className="rotular-pergunta">
            Isto é <strong>{nome}</strong>?
          </p>
          <img src={`/api/rotulos/${item.id}.jpg`} alt={`Recorte: possível ${nome}`} className="rotular-imagem" />
          <p className="muted t-data">confiança do modelo {Math.round(item.confianca * 100)}%</p>
          <div className="rotular-acoes">
            <button type="button" className="ghost" disabled={ocupado} onClick={() => decidir("rejeitar")}>
              ← Não é
            </button>
            <button type="button" className="primary" disabled={ocupado} onClick={() => decidir("confirmar")}>
              É {nome.toLowerCase()} →
            </button>
          </div>
        </section>
      )}
      <footer className="rotular-rodape">
        <a className="button ghost" href="/api/rotulos/dataset.zip" data-testid="rotular-exportar">
          Exportar conjunto de dados YOLO (.zip)
        </a>
        <span className="muted">Os recortes vêm do vídeo com rosto desfocado. Só os confirmados entram no zip.</span>
      </footer>
    </div>
  );
}
