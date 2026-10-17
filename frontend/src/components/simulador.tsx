import { mensagemDeErro } from "../utils/erros";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useDashboardStore } from "../store/dashboardStore";
import { EmptyState, Numero, PanelSkeleton } from "./common";
import { IlustracaoGrafico } from "./ilustracoes";
import { rotuloDoRecurso } from "../api/ppe";
import { horaCurta } from "../utils/datas";
import { decimal, inteiro, pluralizar } from "../utils/formato";

/**
 * Simulador "E se?" (X2, `/simulador`, técnico ou acima). Reprocessa as trilhas
 * gravadas com outra zona, outra histerese ou outro conjunto de EPIs, e compara
 * com o que disparou de fato. Nunca altera alerta real.
 */

type Linha = [number, number][];
type Resumo = { total: number; por_regra: Record<string, number>; incidentes?: number; linha: Linha; registros?: number; pessoas?: number };
type Resultado = {
  janela: [number, number];
  balde_s: number;
  registros: number;
  simulado: Resumo;
  com_regra_atual: Resumo;
  real: Resumo;
  custo_ms: number;
};
type Contexto = {
  atual: { epis: string[]; zona: [number, number][]; zona_nome: string | null; zona_ligada: boolean; criar_apos_s: number | null; criar_apos_quadros: number };
  trilha: { registros: number; primeiro: number | null; ultimo: number | null; bytes: number };
  epis_com_dado: string[];
  rotulos: Record<string, string>;
};

const JANELAS: [string, number][] = [
  ["15 min", 0.25],
  ["1 h", 1],
  ["4 h", 4],
  ["24 h", 24],
];

const ROTULO_REGRA = (regra: string, rotulos: Record<string, string>) => {
  if (regra === "risk_area_presence") return "Na zona de risco";
  const [tipo, ...resto] = regra.split("_");
  const chave = resto.join("_");
  return `${rotulos[chave] ?? rotuloDoRecurso(chave)}${tipo === "incorrect" ? " (uso incorreto)" : ""}`;
};

function hora(t: number) {
  return horaCurta(new Date(t * 1000));
}

/** Duas faixas de barras alinhadas no tempo, mesma escala (uma pergunta: "quando, e quanto?"). */
function LinhaLadoALado({ resultado }: { resultado: Resultado }) {
  const [foco, setFoco] = useState<number | null>(null);
  const faixas: { nome: string; classe: string; linha: Linha }[] = [
    { nome: "Com a regra proposta (simulado)", classe: "proposta", linha: resultado.simulado.linha },
    { nome: "Disparados de fato", classe: "real", linha: resultado.real.linha },
  ];
  const maximo = Math.max(1, ...faixas.flatMap((f) => f.linha.map(([, n]) => n)));
  const n = resultado.simulado.linha.length;
  const W = 720;
  const H = 72;
  const passo = W / n;
  const largura = Math.max(2, passo - 2);
  return (
    <div className="sim-linhas" data-testid="sim-linha">
      {faixas.map((f) => (
        <div key={f.classe} className="sim-faixa">
          <p className="sim-faixa-nome">
            <span className={`sim-amostra ${f.classe}`} aria-hidden="true" />
            {f.nome}
          </p>
          <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" aria-label={`${f.nome}: alertas por intervalo`}>
            <line x1="0" x2={W} y1={H - 0.5} y2={H - 0.5} className="sim-base" />
            {f.linha.map(([t, q], i) => {
              const h = q ? Math.max(3, (q / maximo) * (H - 6)) : 0;
              return (
                <g key={t} onMouseEnter={() => setFoco(i)} onMouseLeave={() => setFoco(null)}>
                  <rect x={i * passo} y={0} width={passo} height={H} className="sim-alvo" />
                  {q > 0 && <rect x={i * passo + 1} y={H - h} width={largura} height={h} rx={Math.min(4, largura / 2)} className={`sim-barra ${f.classe}`} />}
                </g>
              );
            })}
            {foco !== null && <rect x={foco * passo} y={0} width={passo} height={H} className="sim-foco" />}
          </svg>
        </div>
      ))}
      <div className="sim-eixo">
        <span>{hora(resultado.janela[0])}</span>
        <span className="t-data">
          {foco !== null
            ? `${hora(resultado.simulado.linha[foco][0])}: ${resultado.simulado.linha[foco][1]} simulado · ${resultado.real.linha[foco][1]} real`
            : `barras de ${Math.round(resultado.balde_s / 60) || 1} min`}
        </span>
        <span>{hora(resultado.janela[1])}</span>
      </div>
    </div>
  );
}

function EditorDeZona({ cameraId, zona, onZona }: { cameraId: number; zona: [number, number][]; onZona: (z: [number, number][]) => void }) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [arrastando, setArrastando] = useState<number | null>(null);
  const [selecionado, setSelecionado] = useState<number | null>(null);
  const mover = (e: React.PointerEvent) => {
    if (arrastando === null || !svgRef.current) return;
    const r = svgRef.current.getBoundingClientRect();
    const x = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width));
    const y = Math.min(1, Math.max(0, (e.clientY - r.top) / r.height));
    onZona(zona.map((p, i) => (i === arrastando ? [Number(x.toFixed(4)), Number(y.toFixed(4))] : p)));
  };
  return (
    <div className="sim-zona">
      <img src={`/api/cameras/${cameraId}/frame.jpg`} alt="Quadro atual da câmera" />
      <svg
        ref={svgRef}
        viewBox="0 0 1 1"
        preserveAspectRatio="none"
        onPointerMove={mover}
        onPointerUp={() => setArrastando(null)}
        onPointerLeave={() => setArrastando(null)}
        data-testid="sim-zona"
      >
        {zona.length >= 3 && <polygon points={zona.map(([x, y]) => `${x},${y}`).join(" ")} className="sim-zona-poly" />}
      </svg>
      {zona.map(([x, y], i) => (
        <button
          key={i}
          type="button"
          className={`sim-vertice ${selecionado === i ? "selecionado" : ""}`.trim()}
          style={{ left: `${x * 100}%`, top: `${y * 100}%` }}
          aria-label={`Vértice ${i + 1} da zona: selecione e use as setas para mover`}
          aria-pressed={selecionado === i}
          data-testid="sim-vertice"
          onClick={() => setSelecionado(i)}
          onPointerDown={(e) => {
            e.preventDefault();
            setSelecionado(i);
            setArrastando(i);
          }}
          onKeyDown={(e) => {
            const d = e.shiftKey ? 0.05 : 0.01;
            const delta: Record<string, [number, number]> = { ArrowLeft: [-d, 0], ArrowRight: [d, 0], ArrowUp: [0, -d], ArrowDown: [0, d] };
            const m = delta[e.key];
            if (!m) return;
            e.preventDefault();
            onZona(zona.map((p, j) => (j === i ? [Math.min(1, Math.max(0, p[0] + m[0])), Math.min(1, Math.max(0, p[1] + m[1]))] : p)));
          }}
        />
      ))}
    </div>
  );
}

export function SimuladorScreen() {
  const cameras = useDashboardStore((s) => s.cameras);
  const user = useDashboardStore((s) => s.user);
  const [camId, setCamId] = useState<number | null>(() => {
    const q = new URLSearchParams(window.location.search).get("camera");
    return q && /^\d+$/.test(q) ? Number(q) : null;
  });
  const [ctx, setCtx] = useState<Contexto | null>(null);
  const [horas, setHoras] = useState(1);
  const [epis, setEpis] = useState<string[]>([]);
  const [zona, setZona] = useState<[number, number][]>([]);
  const [usarZona, setUsarZona] = useState(true);
  const [histerese, setHisterese] = useState(2);
  const [resultado, setResultado] = useState<Resultado | null>(null);
  const [rodando, setRodando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    if (camId === null && cameras.length) setCamId(cameras[0].id);
  }, [cameras, camId]);

  const carregarContexto = useCallback(() => {
    if (camId === null) return;
    setCtx(null);
    setResultado(null);
    fetch(`/api/simulador/contexto?camera_id=${camId}`, { credentials: "same-origin" })
      .then(async (r) => {
        if (!r.ok) throw new Error(r.status === 403 ? "Só técnico ou supervisor usa o simulador." : "Falha ao carregar o simulador.");
        return (await r.json()) as Contexto;
      })
      .then((c) => {
        setCtx(c);
        setEpis(c.atual.epis.filter((e) => c.epis_com_dado.includes(e)));
        setZona(c.atual.zona.length >= 3 ? c.atual.zona : [[0.6, 0.5], [0.95, 0.5], [0.95, 0.95], [0.6, 0.95]]);
        setUsarZona(c.atual.zona_ligada && c.atual.zona.length >= 3);
        setHisterese(c.atual.criar_apos_s ?? 2);
        setErro(null);
      })
      .catch((e) => setErro(mensagemDeErro(e, "Falha ao carregar o simulador.")));
  }, [camId]);

  useEffect(carregarContexto, [carregarContexto]);

  const rodar = () => {
    if (camId === null) return;
    setRodando(true);
    setErro(null);
    fetch("/api/simulador", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ camera_id: camId, horas, epis, zona: usarZona ? zona : null, criar_apos_s: histerese }),
    })
      .then(async (r) => {
        const corpo = await r.json();
        if (!r.ok) throw new Error(corpo.error ?? "Falha ao reprocessar.");
        return corpo as Resultado;
      })
      .then(setResultado)
      .catch((e) => setErro(mensagemDeErro(e, "Falha ao reprocessar.")))
      .finally(() => setRodando(false));
  };

  const regras = useMemo(() => {
    if (!resultado) return [];
    const todas = new Set([...Object.keys(resultado.simulado.por_regra), ...Object.keys(resultado.real.por_regra), ...Object.keys(resultado.com_regra_atual.por_regra)]);
    return [...todas].sort();
  }, [resultado]);

  if (user && user.role === "operator") {
    return (
      <div className="screen">
        <p className="centered-empty">O simulador é para o técnico ou o supervisor.</p>
      </div>
    );
  }

  const diferenca = resultado ? resultado.simulado.total - resultado.real.total : 0;

  return (
    <div className="screen sim" data-testid="simulador">
      <div className="screen-head">
        <h1>Simulador “E se?”</h1>
        <span className="screen-sub">Reprocessa o que as câmeras viram com outra regra. Nunca altera alerta real.</span>
        <div className="screen-actions">
          <a className="button ghost" href="/">
            Painel
          </a>
        </div>
      </div>
      <div className="sim-grade">
        <section className="card sim-controles" aria-label="Regra proposta">
          <div className="card-body">
            <label className="sim-campo">
              <span>Câmera</span>
              <select value={camId ?? ""} onChange={(e) => setCamId(Number(e.target.value))}>
                {cameras.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </label>
            <fieldset className="sim-campo">
              <legend>Janela</legend>
              <div className="segmented" role="radiogroup">
                {JANELAS.map(([rotulo, h]) => (
                  <button key={rotulo} type="button" role="radio" aria-checked={horas === h} className={horas === h ? "active" : ""} onClick={() => setHoras(h)}>
                    {rotulo}
                  </button>
                ))}
              </div>
            </fieldset>
            {!ctx ? (
              <PanelSkeleton lines={4} />
            ) : (
              <>
                <fieldset className="sim-campo">
                  <legend>EPIs exigidos</legend>
                  <div className="sim-chips">
                    {Object.keys(ctx.rotulos).map((k) => {
                      const temDado = ctx.epis_com_dado.includes(k);
                      const ligado = epis.includes(k);
                      return (
                        <button
                          key={k}
                          type="button"
                          className={`chip-toggle ${ligado ? "on" : ""}`}
                          aria-pressed={ligado}
                          disabled={!temDado}
                          title={temDado ? undefined : "Sem dado gravado: estava desligado ou o modelo não detecta"}
                          onClick={() => setEpis((atual) => (ligado ? atual.filter((e) => e !== k) : [...atual, k]))}
                        >
                          {ctx.rotulos[k]}
                        </button>
                      );
                    })}
                  </div>
                </fieldset>
                <label className="sim-campo">
                  <span>
                    Histerese para criar: <strong className="t-data">{decimal(histerese)} s</strong>
                    <span className="muted"> (hoje {ctx.atual.criar_apos_s == null ? "sem dado" : decimal(ctx.atual.criar_apos_s, Number.isInteger(ctx.atual.criar_apos_s) ? 0 : 1)} s ou {pluralizar(ctx.atual.criar_apos_quadros, "análise")})</span>
                  </span>
                  <input type="range" min={0.5} max={10} step={0.5} value={histerese} onChange={(e) => setHisterese(Number(e.target.value))} data-testid="sim-histerese" />
                </label>
                <fieldset className="sim-campo">
                  <legend>
                    <label className="sim-check">
                      <input type="checkbox" checked={usarZona} onChange={(e) => setUsarZona(e.target.checked)} />
                      Zona de risco {ctx.atual.zona_nome ? `(${ctx.atual.zona_nome})` : ""}
                    </label>
                  </legend>
                  {usarZona && camId !== null && <EditorDeZona cameraId={camId} zona={zona} onZona={setZona} />}
                  {usarZona && (
                    <button
                      type="button"
                      className="ghost small"
                      disabled={JSON.stringify(zona) === JSON.stringify(ctx.atual.zona)}
                      title={JSON.stringify(zona) === JSON.stringify(ctx.atual.zona) ? "A zona editada já é igual à zona atual da câmera" : undefined}
                      onClick={() => setZona(ctx.atual.zona.length >= 3 ? ctx.atual.zona : zona)}
                    >
                      Voltar à zona atual
                    </button>
                  )}
                </fieldset>
                <button type="button" className="primary block" disabled={rodando || !ctx.trilha.registros} onClick={rodar} data-testid="sim-rodar">
                  {rodando ? "Reprocessando…" : "Reprocessar"}
                </button>
                <p className="muted">
                  {ctx.trilha.registros
                    ? `${pluralizar(ctx.trilha.registros, "análise gravada", "análises gravadas")} desde ${hora(ctx.trilha.primeiro ?? 0)} (${decimal(ctx.trilha.bytes / 1024 / 1024)} MB, sem imagem).`
                    : "Ainda não há trilha gravada desta câmera. Ligue a câmera e espere algumas análises."}
                </p>
              </>
            )}
          </div>
        </section>
        <section className="card sim-resultado" aria-live="polite">
          <div className="card-body">
            {erro && (
              <div className="sim-erro" role="alert">
                <strong>Não foi possível reprocessar.</strong> {erro}
                <button type="button" className="ghost small" onClick={carregarContexto}>
                  Tentar de novo
                </button>
              </div>
            )}
            {!resultado ? (
              <EmptyState ilustracao={<IlustracaoGrafico />} titulo="Mude a regra e reprocesse">
                Arraste os vértices da zona, mude a histerese ou desligue um EPI. O resultado aparece aqui, lado a lado com o que aconteceu de verdade.
              </EmptyState>
            ) : (
              <>
                <dl className="sim-numeros" data-testid="sim-numeros">
                  <div>
                    <dt>Teriam disparado</dt>
                    <dd className="t-data" data-testid="sim-total" data-valor={resultado.simulado.total}><Numero valor={resultado.simulado.total} /></dd>
                    <span className="muted">{pluralizar(resultado.simulado.incidentes ?? 0, "incidente")}</span>
                  </div>
                  <div>
                    <dt>Dispararam de fato</dt>
                    <dd className="t-data" data-testid="sim-real" data-valor={resultado.real.total}><Numero valor={resultado.real.total} /></dd>
                    <span className="muted">{diferenca === 0 ? "igual" : diferenca > 0 ? `${diferenca} a mais com a proposta` : `${-diferenca} a menos com a proposta`}</span>
                  </div>
                  <div>
                    <dt>Regra de hoje, simulada</dt>
                    <dd className="t-data"><Numero valor={resultado.com_regra_atual.total} /></dd>
                    <span className="muted">quanto o simulador reproduz o real</span>
                  </div>
                </dl>
                <LinhaLadoALado resultado={resultado} />
                <table className="sim-tabela">
                  <caption>Por regra</caption>
                  <thead>
                    <tr>
                      <th scope="col">Regra</th>
                      <th scope="col">Proposta</th>
                      <th scope="col">Hoje (simulado)</th>
                      <th scope="col">Real</th>
                    </tr>
                  </thead>
                  <tbody>
                    {regras.map((r) => (
                      <tr key={r}>
                        <th scope="row">{ROTULO_REGRA(r, ctx?.rotulos ?? {})}</th>
                        <td className="t-data">{resultado.simulado.por_regra[r] ?? 0}</td>
                        <td className="t-data">{resultado.com_regra_atual.por_regra[r] ?? 0}</td>
                        <td className="t-data">{resultado.real.por_regra[r] ?? 0}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="muted">
                  {pluralizar(resultado.registros, "análise reprocessada", "análises reprocessadas")} em {inteiro(resultado.custo_ms)} ms. O simulador usa o que o modelo viu na época
                  (não reroda o modelo) e ignora a “soneca” do “resolver todos” e as regras de emergência.
                </p>
              </>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}

export default SimuladorScreen;
