import { useEffect, useRef, useState } from "react";
import { PanelSkeleton } from "./common";
import { decimal, pluralizar } from "../utils/formato";

/**
 * “Você vs. a IA” (G2), em `/desafio`. Cada rodada toca ~1,6 s de vídeo
 * (rosto desfocado) e congela no quadro da pergunta; quem joga clica nas
 * pessoas com infração antes do tempo acabar. Depois o placar mostra, lado a
 * lado e com a MESMA regra, a pessoa e a IA contra o gabarito curado à mão
 * (docs/NEXT2026/GABARITO.md) — inclusive quando a IA erra. O placar é desta
 * sessão do navegador: apelido opcional, nada vai ao banco.
 */

type Rodada = { id: string; pergunta: string; quadros: number };
type Placar = { acertos: number; erros: number; perdidos: number; alvos: number; tempo_ms: number | null };
type Resultado = {
  gabarito: { caixa: [number, number, number, number]; sem_capacete: boolean | null }[];
  humano: Placar;
  ia: Placar & { caixas: [number, number, number, number][] };
};

const W = 960;
const H = 540;
const TEMPO_S = 12;

function lerPlacar(): { humano: number; ia: number; rodadas: number } {
  try {
    return JSON.parse(sessionStorage.getItem("visionepi-desafio") ?? "") as { humano: number; ia: number; rodadas: number };
  } catch {
    return { humano: 0, ia: 0, rodadas: 0 };
  }
}

function pontos(p: Placar): number {
  return Math.max(0, p.acertos - p.erros);
}

export function DesafioScreen() {
  const [rodadas, setRodadas] = useState<Rodada[]>([]);
  const [indice, setIndice] = useState(0);
  const [quadro, setQuadro] = useState(0);
  const [fase, setFase] = useState<"inicio" | "video" | "clicar" | "resultado">("inicio");
  const [cliques, setCliques] = useState<[number, number][]>([]);
  const [restante, setRestante] = useState(TEMPO_S);
  const [resultado, setResultado] = useState<Resultado | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [apelido, setApelido] = useState("");
  const [placar, setPlacar] = useState(lerPlacar);
  const inicioRef = useRef(0);
  const cliquesRef = useRef<[number, number][]>([]);
  const respondidoRef = useRef(false);

  useEffect(() => {
    fetch("/api/desafio/rodadas", { credentials: "same-origin" })
      .then(async (r) => (r.ok ? r.json() : Promise.reject(new Error((await r.json().catch(() => ({})))?.error ?? "Falha ao carregar o desafio."))))
      .then((d: { rodadas: Rodada[] }) => setRodadas(d.rodadas))
      .catch((e: Error) => setErro(e.message));
  }, []);

  const rodada = rodadas[indice];

  // Pré-carrega os quadros e toca o clipe a 10 quadros/s.
  useEffect(() => {
    if (fase !== "video" || !rodada) return undefined;
    for (let k = 0; k < rodada.quadros; k += 1) new Image().src = `/api/desafio/${rodada.id}/quadro/${k}.jpg`;
    setQuadro(0);
    let k = 0;
    const id = window.setInterval(() => {
      k += 1;
      if (k >= rodada.quadros) {
        window.clearInterval(id);
        inicioRef.current = performance.now();
        setFase("clicar");
        return;
      }
      setQuadro(k);
    }, 100);
    return () => window.clearInterval(id);
  }, [fase, rodada]);

  const responder = (lista: [number, number][]) => {
    if (!rodada || respondidoRef.current) return;
    respondidoRef.current = true;
    const tempo = Math.round(performance.now() - inicioRef.current);
    fetch(`/api/desafio/${rodada.id}/resposta`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cliques: lista, tempo_ms: tempo }),
    })
      .then((r) => r.json())
      .then((res: Resultado) => {
        setResultado(res);
        setFase("resultado");
        const novo = { humano: placar.humano + pontos(res.humano), ia: placar.ia + pontos(res.ia), rodadas: placar.rodadas + 1 };
        setPlacar(novo);
        try {
          sessionStorage.setItem("visionepi-desafio", JSON.stringify(novo));
        } catch {
          /* janela privada: o placar fica só na memória */
        }
      })
      .catch((e: Error) => setErro(e.message));
  };

  // Relógio da fase de clique.
  useEffect(() => {
    if (fase !== "clicar") return undefined;
    setRestante(TEMPO_S);
    const id = window.setInterval(() => {
      const passou = (performance.now() - inicioRef.current) / 1000;
      const falta = Math.max(0, Math.ceil(TEMPO_S - passou));
      setRestante(falta);
      if (falta <= 0) {
        window.clearInterval(id);
        responder(cliquesRef.current);
      }
    }, 200);
    return () => window.clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fase]);

  const clicar = (e: React.MouseEvent<SVGSVGElement>) => {
    if (fase !== "clicar") return;
    const r = e.currentTarget.getBoundingClientRect();
    const novo: [number, number] = [((e.clientX - r.left) / r.width) * W, ((e.clientY - r.top) / r.height) * H];
    cliquesRef.current = [...cliquesRef.current, novo];
    setCliques(cliquesRef.current);
  };

  const proxima = () => {
    setResultado(null);
    setCliques([]);
    cliquesRef.current = [];
    respondidoRef.current = false;
    setIndice((i) => (i + 1) % Math.max(1, rodadas.length));
    setFase("video");
  };

  if (erro) return <p className="centered-empty">{erro}</p>;
  if (!rodada)
    return (
      <div className="desafio" aria-busy="true">
        <div className="skeleton-block desafio-esqueleto" />
        <PanelSkeleton lines={2} />
      </div>
    );

  return (
    <div className="desafio" data-testid="desafio" data-fase={fase}>
      <header className="desafio-cabeca">
        <h1>Você vs. a IA</h1>
        <span className="t-data" data-testid="desafio-placar">
          {apelido || "Você"} {placar.humano} × {placar.ia} IA · {pluralizar(placar.rodadas, "rodada")}
        </span>
      </header>
      {fase === "inicio" ? (
        <section className="desafio-inicio card">
          <p>
            {pluralizar(rodadas.length, "rodada")}. Cada uma mostra um trecho curto e congela: clique nas pessoas com infração em até {TEMPO_S} s.
            Depois você vê o gabarito e a resposta da IA, com a mesma regra para os dois.
          </p>
          <label>
            Apelido (opcional, não é salvo)
            <input value={apelido} maxLength={20} onChange={(e) => setApelido(e.target.value)} />
          </label>
          <button
            type="button"
            className="primary"
            onClick={() => {
              respondidoRef.current = false;
              setFase("video");
            }}
            data-testid="desafio-comecar"
          >
            Começar
          </button>
        </section>
      ) : (
        <>
          <p className="desafio-pergunta">
            {rodada.pergunta}
            {fase === "clicar" && (
              <span className="t-data" data-testid="desafio-relogio">
                {" "}
                {restante} s
              </span>
            )}
          </p>
          <svg viewBox={`0 0 ${W} ${H}`} className="desafio-quadro" onClick={clicar} data-testid="desafio-quadro">
            <image href={`/api/desafio/${rodada.id}/quadro/${fase === "video" ? quadro : rodada.quadros - 1}.jpg`} width={W} height={H} />
            {fase === "resultado" &&
              resultado?.gabarito.map((g, i) =>
                g.sem_capacete === null ? null : (
                  <rect
                    key={`g${i}`}
                    x={g.caixa[0]}
                    y={g.caixa[1]}
                    width={g.caixa[2] - g.caixa[0]}
                    height={g.caixa[3] - g.caixa[1]}
                    fill="none"
                    stroke={g.sem_capacete ? "var(--danger)" : "var(--ok)"}
                    strokeWidth="4"
                  />
                ),
              )}
            {fase === "resultado" &&
              resultado?.ia.caixas.map((c, i) => (
                <rect key={`ia${i}`} x={c[0]} y={c[1]} width={c[2] - c[0]} height={c[3] - c[1]} fill="none" stroke="white" strokeDasharray="10 6" strokeWidth="3" />
              ))}
            {cliques.map(([x, y], i) => (
              <circle key={`c${i}`} cx={x} cy={y} r="14" fill="var(--accent)" stroke="white" strokeWidth="3" />
            ))}
          </svg>
          {fase === "clicar" && (
            <button type="button" className="primary" onClick={() => responder(cliques)} data-testid="desafio-responder">
              Responder ({pluralizar(cliques.length, "clique")})
            </button>
          )}
          {fase === "resultado" && resultado && (
            <section className="desafio-resultado" data-testid="desafio-resultado">
              <table>
                <thead>
                  <tr>
                    <th />
                    <th>Acertos</th>
                    <th>Erros</th>
                    <th>Perdidos</th>
                    <th>Tempo</th>
                  </tr>
                </thead>
                <tbody>
                  {(["humano", "ia"] as const).map((quem) => (
                    <tr key={quem} data-testid={`desafio-linha-${quem}`}>
                      <th>{quem === "humano" ? apelido || "Você" : "IA"}</th>
                      <td className="t-data">
                        {resultado[quem].acertos} / {resultado[quem].alvos}
                      </td>
                      <td className="t-data">{resultado[quem].erros}</td>
                      <td className="t-data">{resultado[quem].perdidos}</td>
                      <td className="t-data">{resultado[quem].tempo_ms == null ? "sem dado" : `${decimal(resultado[quem].tempo_ms! / 1000)} s`}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="muted">
                Contorno vermelho: sem capacete no gabarito · verde: com capacete · tracejado: o que a IA apontou. Gabarito marcado à mão
                (docs/NEXT2026/GABARITO.md); pessoa cortada pela borda não conta. O tempo da IA é o da inferência neste computador.
              </p>
              <button type="button" className="primary" onClick={proxima} data-testid="desafio-proxima">
                Próxima rodada
              </button>
            </section>
          )}
        </>
      )}
    </div>
  );
}
