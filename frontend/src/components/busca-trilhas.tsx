import { useCallback, useRef, useState } from "react";
import type { FormEvent } from "react";
import { avisarSeSessaoExpirou } from "../api/client";
import { PPE_KEYS, PPE_LABELS, ROTULOS_DE_CLASSE, type PpeKey } from "../api/ppe";
import { useDashboardStore } from "../store/dashboardStore";
import { horaCompleta } from "../utils/datas";
import { mensagemDeErro } from "../utils/erros";
import { decimal, pluralizar } from "../utils/formato";
import { EmptyState, PanelSkeleton } from "./common";
import { IlustracaoCamera, IlustracaoEscudo, IlustracaoGrafico } from "./ilustracoes";
import { IncidentReplay } from "./replay";
import "../styles/busca-trilhas.css";

/**
 * Busca nas trilhas (M6, técnico ou acima). Contrato: app/api/busca.py e app/services/busca_trilhas.py.
 * Sem LLM: o servidor filtra a trilha gravada da câmera por zona, horário, permanência, EPI ausente e
 * velocidade, e devolve trechos contínuos de um rótulo de rastreio ("Pessoa N", nunca identidade).
 * Cada trecho mostra a trilha desenhada (na planta calibrada ou sobre o quadro da câmera) e, quando o
 * servidor achou um replay gravado no período, abre o replay do incidente.
 */

// ------------------------------------------------------------------ tipos ---
type Ponto = [number, number, number]; // x, y (0 a 1) e instante (s desde 1970)
type Trecho = {
  camera_id: number;
  rotulo: string;
  rastreio: number | string;
  inicio: number;
  fim: number;
  duracao_s: number;
  epis_ausentes: string[];
  velocidade_media: number | null;
  total_pontos: number;
  pontos: Ponto[];
  pontos_planta?: Ponto[];
  alerta_id: number | null;
  incidente_id: number | null;
  clipe_da_mesma_pessoa: boolean | null;
};
type Poligono = [number, number][];
type Resposta = {
  camera: { id: number; nome: string; planta_calibrada: boolean; zona: Poligono; zona_planta: Poligono };
  registros_lidos: number;
  total: number;
  limite: number;
  items: Trecho[];
};
export type Filtros = {
  camera: string;
  de: string;
  ate: string;
  zona: boolean;
  permanencia: string;
  epis: PpeKey[];
  velMin: string;
  velMax: string;
};
type Estado =
  | { fase: "ocioso" }
  | { fase: "carregando" }
  | { fase: "erro"; msg: string; status?: number }
  | { fase: "pronto"; dados: Resposta };

const FILTROS_VAZIOS: Filtros = { camera: "", de: "", ate: "", zona: false, permanencia: "", epis: [], velMin: "", velMax: "" };
const LARGURA_QUADRO = 960;
const ALTURA_QUADRO = 540;

// ------------------------------------------------------------------ rede ---
async function pedir<T>(url: string): Promise<T> {
  const r = await fetch(url, { credentials: "same-origin" });
  avisarSeSessaoExpirou(url, r.status);
  const corpo = await r.json().catch(() => null);
  if (!r.ok) {
    const msg = corpo && typeof corpo === "object" && "error" in corpo ? String((corpo as { error: unknown }).error) : "Falha ao buscar nas trilhas.";
    throw Object.assign(new Error(msg), { status: r.status });
  }
  return corpo as T;
}

// -------------------------------------------------------------- formatação ---
function semEpi(chave: string): string {
  const rotulo = PPE_LABELS[chave as PpeKey];
  return ROTULOS_DE_CLASSE[`no_${chave}`] ?? (rotulo ? `Sem ${rotulo.toLowerCase()}` : chave);
}

function instante(segundos: number): string {
  const d = new Date(segundos * 1000);
  return `${d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" })} ${horaCompleta(d)}`;
}

function duracao(segundos: number): string {
  if (segundos < 60) return `${decimal(segundos)} s`;
  return `${Math.floor(segundos / 60)} min ${Math.round(segundos % 60)} s`;
}

/** Valida o formulário e monta a consulta. O servidor valida de novo; aqui o erro aparece antes de ir à rede. */
export function montarConsulta(f: Filtros): { consulta: string } | { erro: string } {
  if (!f.camera) return { erro: "Escolha a câmera da busca." };
  const consulta = new URLSearchParams({ camera_id: f.camera });
  const instantes: Record<string, number> = {};
  for (const [campo, valor, rotulo] of [["de", f.de, "o horário inicial"], ["ate", f.ate, "o horário final"]] as const) {
    if (!valor) continue;
    const d = new Date(valor);
    if (Number.isNaN(d.getTime())) return { erro: `Informe ${rotulo} com data e hora completas.` };
    instantes[campo] = d.getTime();
    consulta.set(campo, d.toISOString());
  }
  if (instantes.de !== undefined && instantes.ate !== undefined && instantes.de >= instantes.ate) {
    return { erro: "O horário final precisa ser depois do inicial." };
  }
  const numeros: [string, string, string][] = [
    ["permanencia_min_s", f.permanencia, "a permanência mínima"],
    ["vel_min", f.velMin, "a velocidade mínima"],
    ["vel_max", f.velMax, "a velocidade máxima"],
  ];
  const lidos: Record<string, number> = {};
  for (const [campo, valor, rotulo] of numeros) {
    if (valor.trim() === "") continue;
    const n = Number(valor.replace(",", "."));
    if (!Number.isFinite(n) || n < 0) return { erro: `Informe ${rotulo} como um número, de 0 em diante.` };
    lidos[campo] = n;
    consulta.set(campo, String(n));
  }
  if (lidos.vel_min !== undefined && lidos.vel_max !== undefined && lidos.vel_min > lidos.vel_max) {
    return { erro: "A velocidade máxima precisa ser maior ou igual à mínima." };
  }
  if (f.zona) consulta.set("zona", "1");
  if (f.epis.length) consulta.set("epi_ausente", f.epis.join(","));
  return { consulta: consulta.toString() };
}

// ---------------------------------------------------------------- desenho ---
function TrilhaDesenhada({ trecho, camera }: { trecho: Trecho; camera: Resposta["camera"] }) {
  const naPlanta = camera.planta_calibrada && !!trecho.pontos_planta?.length;
  const pontos = naPlanta ? (trecho.pontos_planta as Ponto[]) : trecho.pontos;
  const zona = naPlanta ? camera.zona_planta : camera.zona;
  // Planta: quadrado 100x100 (pé fora do chão calibrado é extrapolação e fica preso à borda).
  // Câmera: o mesmo espaço 960x540 do quadro, com a imagem atual ao fundo.
  const [largura, altura] = naPlanta ? [100, 100] : [LARGURA_QUADRO, ALTURA_QUADRO];
  const limitar = (v: number, max: number) => Math.min(max, Math.max(0, v));
  const mapear = (x: number, y: number): [number, number] => [limitar(x * largura, largura), limitar(y * altura, altura)];
  const linha = pontos.map(([x, y]) => mapear(x, y).join(",")).join(" ");
  const [x0, y0] = mapear(pontos[0][0], pontos[0][1]);
  const [x1, y1] = mapear(pontos[pontos.length - 1][0], pontos[pontos.length - 1][1]);
  const raio = largura / 55;
  const poligono = zona.map(([x, y]) => mapear(x, y).join(",")).join(" ");
  return (
    <figure className="busca-trilha" data-testid="busca-trilha" data-plano={naPlanta ? "planta" : "camera"}>
      <svg
        className="busca-svg"
        viewBox={`0 0 ${largura} ${altura}`}
        role="img"
        aria-label={`Trilha de ${trecho.rotulo} de ${instante(trecho.inicio)} a ${horaCompleta(new Date(trecho.fim * 1000))}, ${pluralizar(pontos.length, "ponto", "pontos")}, ${naPlanta ? "na planta" : "sobre o quadro da câmera"}`}
      >
        {naPlanta ? (
          <rect className="busca-fundo" x="0.5" y="0.5" width={largura - 1} height={altura - 1} rx="2" />
        ) : (
          <image href={`/api/cameras/${camera.id}/frame.jpg`} x="0" y="0" width={largura} height={altura} preserveAspectRatio="none" />
        )}
        {zona.length >= 3 && <polygon className="busca-zona" points={poligono} />}
        {pontos.length > 1 && <polyline className="busca-linha" points={linha} />}
        <circle className="busca-inicio" cx={x0} cy={y0} r={raio}>
          <title>Início</title>
        </circle>
        <circle className="busca-fim" cx={x1} cy={y1} r={raio}>
          <title>Fim</title>
        </circle>
      </svg>
      <figcaption className="busca-legenda">
        Círculo vazado: início. Círculo cheio: fim. {zona.length >= 3 ? "Tracejado: área de risco. " : ""}
        {naPlanta ? "Posição dos pés na planta calibrada." : "Posição dos pés sobre o quadro atual da câmera: esta câmera não tem planta calibrada."}
      </figcaption>
    </figure>
  );
}

function ItemDoResultado({ trecho, camera, onReplay }: { trecho: Trecho; camera: Resposta["camera"]; onReplay: (t: Trecho) => void }) {
  const [aberta, setAberta] = useState(false);
  return (
    <li className="card busca-item" data-testid="busca-resultado" data-rotulo={trecho.rotulo}>
      <div className="busca-item-topo">
        <h3>{trecho.rotulo}</h3>
        <span className="busca-quando">
          {instante(trecho.inicio)} a {horaCompleta(new Date(trecho.fim * 1000))} · {duracao(trecho.duracao_s)}
        </span>
      </div>
      <div className="busca-detalhes">
        <span>{pluralizar(trecho.total_pontos, "ponto gravado", "pontos gravados")}</span>
        {trecho.velocidade_media != null && (
          <span title="Fração do quadro percorrida por segundo, pelos pés">velocidade média {decimal(trecho.velocidade_media, 2)} quadro/s</span>
        )}
      </div>
      {trecho.epis_ausentes.length > 0 && (
        <div className="busca-chips">
          {trecho.epis_ausentes.map((chave) => (
            <span key={chave} className="chip miss">{semEpi(chave)}</span>
          ))}
        </div>
      )}
      <div className="busca-acoes">
        <button type="button" className="small" aria-expanded={aberta} onClick={() => setAberta((v) => !v)}>
          {aberta ? "Esconder trilha" : "Ver trilha"}
        </button>
        {trecho.alerta_id != null && (
          <>
            <button type="button" className="small primary" data-testid="busca-replay" onClick={() => onReplay(trecho)}>
              Abrir replay
            </button>
            {trecho.clipe_da_mesma_pessoa === false && (
              <span className="busca-nota-replay">Replay de outro rótulo de rastreio no mesmo período.</span>
            )}
          </>
        )}
      </div>
      {aberta && <TrilhaDesenhada trecho={trecho} camera={camera} />}
    </li>
  );
}

// ------------------------------------------------------------------- tela ---
export default function BuscaTrilhasScreen() {
  const cameras = useDashboardStore((s) => s.cameras);
  const [filtros, setFiltros] = useState<Filtros>(FILTROS_VAZIOS);
  const [estado, setEstado] = useState<Estado>({ fase: "ocioso" });
  const [erroDoForm, setErroDoForm] = useState<string | null>(null);
  const [replay, setReplay] = useState<{ alertaId: number; camera: string } | null>(null);
  const pedido = useRef(0);

  const cameraEscolhida = filtros.camera || (cameras[0] ? String(cameras[0].id) : "");
  const mudar = (parcial: Partial<Filtros>) => setFiltros((f) => ({ ...f, ...parcial }));

  const buscar = useCallback(async (f: Filtros) => {
    const montada = montarConsulta(f);
    if ("erro" in montada) {
      setErroDoForm(montada.erro);
      return;
    }
    setErroDoForm(null);
    const meu = ++pedido.current;
    setEstado({ fase: "carregando" });
    try {
      const dados = await pedir<Resposta>(`/api/busca/trilhas?${montada.consulta}`);
      if (meu === pedido.current) setEstado({ fase: "pronto", dados });
    } catch (e) {
      if (meu === pedido.current) {
        setEstado({ fase: "erro", msg: mensagemDeErro(e, "Falha ao buscar nas trilhas."), status: (e as { status?: number }).status });
      }
    }
  }, []);

  const enviar = (e: FormEvent) => {
    e.preventDefault();
    void buscar({ ...filtros, camera: cameraEscolhida });
  };

  if (estado.fase === "erro" && estado.status === 403) {
    return (
      <div className="screen busca" data-testid="busca-trilhas">
        <EmptyState ilustracao={<IlustracaoEscudo />} titulo="Acesso restrito">
          A busca nas trilhas é para Técnico e Supervisor. Peça a quem tem esse tipo de conta.
        </EmptyState>
      </div>
    );
  }

  return (
    <div className="screen busca" data-testid="busca-trilhas">
      <header className="screen-head">
        <h1>Busca nas trilhas</h1>
        <p className="screen-sub">Ache quem ficou na área de risco, sem EPI ou parado, a partir da trilha gravada. Nenhuma IA: só filtros.</p>
      </header>

      {cameras.length === 0 ? (
        <EmptyState ilustracao={<IlustracaoCamera />} titulo="Nenhuma câmera cadastrada">
          Cadastre uma câmera e deixe-a ligada por alguns minutos: a busca lê a trilha que ela grava.
        </EmptyState>
      ) : (
        <>
          <form className="card busca-form" onSubmit={enviar} aria-label="Filtros da busca" noValidate>
            <div className="busca-campos">
              <label className="field">
                <span>Câmera</span>
                <select value={cameraEscolhida} onChange={(e) => mudar({ camera: e.target.value })}>
                  {cameras.map((c) => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>De (início da janela)</span>
                <input type="datetime-local" value={filtros.de} onChange={(e) => mudar({ de: e.target.value })} />
              </label>
              <label className="field">
                <span>Até (fim da janela)</span>
                <input type="datetime-local" value={filtros.ate} onChange={(e) => mudar({ ate: e.target.value })} />
              </label>
              <label className="field">
                <span>Permanência mínima (s)</span>
                <input type="number" inputMode="decimal" min={0} step="any" value={filtros.permanencia} onChange={(e) => mudar({ permanencia: e.target.value })} />
              </label>
              <label className="field">
                <span>Velocidade mínima (quadro/s)</span>
                <input type="number" inputMode="decimal" min={0} step="any" value={filtros.velMin} onChange={(e) => mudar({ velMin: e.target.value })} />
              </label>
              <label className="field">
                <span>Velocidade máxima (quadro/s)</span>
                <input type="number" inputMode="decimal" min={0} step="any" value={filtros.velMax} onChange={(e) => mudar({ velMax: e.target.value })} />
              </label>
            </div>
            <p className="busca-dica">Sem horário, a busca olha toda a trilha gravada. Velocidade é a fração do quadro que os pés percorrem por segundo: 0,1 atravessa o quadro em 10 s.</p>

            <div className="busca-campos busca-campos-epis">
              <fieldset>
                <legend>Sem pelo menos um destes EPIs</legend>
                <div className="busca-epis">
                  {PPE_KEYS.map((chave) => (
                    <label key={chave} className="busca-check">
                      <input
                        type="checkbox"
                        checked={filtros.epis.includes(chave)}
                        onChange={(e) => mudar({ epis: e.target.checked ? [...filtros.epis, chave] : filtros.epis.filter((k) => k !== chave) })}
                      />
                      {PPE_LABELS[chave]}
                    </label>
                  ))}
                </div>
              </fieldset>
              <label className="busca-check">
                <input type="checkbox" checked={filtros.zona} onChange={(e) => mudar({ zona: e.target.checked })} />
                Só dentro da área de risco
              </label>
            </div>

            {erroDoForm && (
              <p className="busca-erro busca-erro-form" role="alert">{erroDoForm}</p>
            )}
            <div className="busca-barra">
              <button type="submit" className="primary" data-testid="busca-filtrar" disabled={estado.fase === "carregando"}>
                {estado.fase === "carregando" ? "Buscando…" : "Buscar"}
              </button>
              <button type="button" className="ghost" onClick={() => { setFiltros(FILTROS_VAZIOS); setErroDoForm(null); setEstado({ fase: "ocioso" }); }}>
                Limpar filtros
              </button>
            </div>
          </form>

          <section aria-live="polite" aria-busy={estado.fase === "carregando"} data-testid="busca-estado" data-estado={estado.fase}>
            {estado.fase === "ocioso" && (
              <EmptyState ilustracao={<IlustracaoGrafico />} titulo="Escolha os filtros e toque em Buscar">
                Cada resultado é um trecho contínuo de um rótulo de rastreio, com a trilha desenhada e o replay quando houver.
              </EmptyState>
            )}
            {estado.fase === "carregando" && (
              <div className="card busca-form" aria-hidden="true"><PanelSkeleton lines={5} /></div>
            )}
            {estado.fase === "erro" && (
              <div className="busca-erro" role="alert">
                <p>{estado.msg}</p>
                <button type="button" className="small" onClick={() => void buscar({ ...filtros, camera: cameraEscolhida })}>Tentar de novo</button>
              </div>
            )}
            {estado.fase === "pronto" && (
              estado.dados.items.length === 0 ? (
                <EmptyState ilustracao={<IlustracaoGrafico />} titulo="Nenhum trecho atende aos filtros">
                  {estado.dados.registros_lidos === 0
                    ? "A câmera não tem trilha gravada nessa janela. Ligue a câmera e espere algumas análises, ou amplie o horário."
                    : "Afrouxe um filtro: reduza a permanência mínima, tire um EPI ou amplie a janela."}
                </EmptyState>
              ) : (
                <>
                  <p className="busca-resumo">
                    {estado.dados.total > estado.dados.items.length
                      ? `Mostrando ${pluralizar(estado.dados.items.length, "trecho", "trechos")} de ${estado.dados.total}, do mais recente para o mais antigo.`
                      : `${pluralizar(estado.dados.total, "trecho", "trechos")}, do mais recente para o mais antigo.`}{" "}
                    Câmera {estado.dados.camera.nome}.
                  </p>
                  <ul className="busca-lista">
                    {estado.dados.items.map((t) => (
                      <ItemDoResultado
                        key={`${t.rastreio}-${t.inicio}`}
                        trecho={t}
                        camera={estado.dados.camera}
                        onReplay={(x) => x.alerta_id != null && setReplay({ alertaId: x.alerta_id, camera: estado.dados.camera.nome })}
                      />
                    ))}
                  </ul>
                  <p className="busca-dica busca-rodape">O número é um rótulo de rastreio por posição, não identifica ninguém. Rostos desfocados pelo modo privacidade.</p>
                </>
              )
            )}
          </section>
        </>
      )}

      {replay && <IncidentReplay alertId={replay.alertaId} cameraName={replay.camera} onClose={() => setReplay(null)} />}
    </div>
  );
}
