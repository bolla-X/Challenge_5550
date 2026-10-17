import { useCallback, useEffect, useId, useMemo, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { apiFetch } from "../api/client";
import { rotuloDaRegra } from "../api/ppe";
import { useDashboardStore } from "../store/dashboardStore";
import { decimal, inteiro, pluralizar } from "../utils/formato";
import { mensagemDeErro } from "../utils/erros";
import { EmptyState, PanelSkeleton } from "./common";
import { IlustracaoGrafico } from "./ilustracoes";
import "../styles/intervencoes.css";

/**
 * Antes e depois de uma intervenção, e a conta do retorno (M8). Contrato: app/api/intervencoes.py e
 * app/services/intervencoes.py.
 *
 * Três regras da tela, as mesmas do servidor: (1) o aviso "correlação não é causa" nunca some; (2) o tamanho da
 * amostra vem junto de qualquer número; (3) o retorno é só aritmética sobre números que a pessoa digita, e o texto
 * diz "estimativa com as suas premissas": nenhum custo ou estatística oficial é embutido aqui.
 */

interface Intervencao {
  id: number;
  camera_id: number | null;
  setor: string | null;
  titulo: string;
  descricao: string;
  data_da_intervencao: string;
  criada_por: string;
  criada_em: string | null;
}
interface Lado {
  completa: boolean;
  dias_na_janela: number;
  dias_decorridos: number;
  alertas: { total: number; por_regra: Record<string, number> };
  incidentes: { total: number };
  amostra: { dias_com_dados: number; dias_decorridos: number; minutos_conformes_registrados: number; minutos_observados: number | null };
}
interface Comparacao {
  janela_dias: number;
  antes: Lado;
  depois: Lado;
  por_regra: { regra: string; antes: number; depois: number }[];
  variacao: { alertas_pct: number | null; incidentes_pct: number | null } | null;
  exposicao: { disponivel: boolean; motivo: string };
  observacoes: string[];
  aviso_da_janela: string | null;
  aviso: string;
}
interface ResultadoRoi {
  resultado: { custo_por_incidente: number; economia: number; ganho_liquido: number; roi_pct: number | null; payback_dias: number | null };
  formula: string;
  aviso: string;
}

export const AVISO_DE_CORRELACAO = "Correlação não é causa: outras mudanças no período também contam.";
const JANELAS = [7, 14, 30];

// ------------------------------------------------------------- formatação ---
const dinheiro = (v: number) => v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

/** "2026-10-10" → "10/10/2026", sem passar por Date (que deslocaria o dia pelo fuso). */
function dataCurta(iso: string): string {
  const [a, m, d] = iso.split("-");
  return a && m && d ? `${d}/${m}/${a}` : iso;
}

function percentual(valor: number | null): string {
  if (valor === null) return "sem base para o percentual (o antes foi zero)";
  const sinal = valor > 0 ? "+" : valor < 0 ? "−" : "";
  return `${sinal}${decimal(Math.abs(valor))}%`;
}

/** Número digitado em pt-BR: "1.500,50", "1500,5" ou "1500.5". Vazio ou ilegível vira null. */
function lerNumero(texto: string): number | null {
  const limpo = texto.trim().replace(/\s/g, "");
  if (!limpo) return null;
  const normal = limpo.includes(",") ? limpo.replace(/\./g, "").replace(",", ".") : limpo;
  const n = Number(normal);
  return Number.isFinite(n) ? n : null;
}

function escopoDe(i: Intervencao, nomeDaCamera: (id: number) => string): string {
  if (i.camera_id !== null) return `Câmera: ${nomeDaCamera(i.camera_id)}`;
  return `Setor: ${i.setor ?? ""}`;
}

function Campo({ id, rotulo, ajuda, erro, children }: { id: string; rotulo: string; ajuda?: string; erro?: string; children: ReactNode }) {
  return (
    <div className="field iv-campo">
      <label htmlFor={id} className="iv-rotulo">
        {rotulo}
      </label>
      {children}
      {ajuda && (
        <p className="iv-ajuda" id={`${id}-ajuda`}>
          {ajuda}
        </p>
      )}
      {erro && (
        <p className="iv-erro" id={`${id}-erro`} role="alert">
          {erro}
        </p>
      )}
    </div>
  );
}
const descrito = (id: string, ajuda?: string, erro?: string) => [ajuda ? `${id}-ajuda` : null, erro ? `${id}-erro` : null].filter(Boolean).join(" ") || undefined;

// ------------------------------------------------------------------ criar ---
function FormularioDeIntervencao({ aoCriar, aoCancelar }: { aoCriar: (i: Intervencao) => void; aoCancelar: () => void }) {
  const base = useId();
  const cameras = useDashboardStore((s) => s.cameras);
  const setores = useMemo(() => [...new Set(cameras.map((c) => (c.location ?? "").trim() || c.name))].sort((a, b) => a.localeCompare(b, "pt-BR")), [cameras]);
  const [titulo, setTitulo] = useState("");
  const [descricao, setDescricao] = useState("");
  const [data, setData] = useState("");
  const [tipo, setTipo] = useState<"camera" | "setor">("camera");
  const [cameraId, setCameraId] = useState("");
  const [setor, setSetor] = useState("");
  const [erros, setErros] = useState<Record<string, string>>({});
  const [ocupado, setOcupado] = useState(false);

  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    const novos: Record<string, string> = {};
    if (!titulo.trim()) novos.titulo = "Informe o título.";
    if (!data) novos.data = "Informe a data da intervenção.";
    if (tipo === "camera" && !cameraId) novos.escopo = "Escolha a câmera.";
    if (tipo === "setor" && !setor) novos.escopo = "Escolha o setor.";
    setErros(novos);
    if (Object.keys(novos).length) return;
    setOcupado(true);
    try {
      const res = await apiFetch<{ intervencao: Intervencao }>("/api/intervencoes", {
        method: "POST",
        body: JSON.stringify({
          titulo,
          descricao,
          data_da_intervencao: data,
          camera_id: tipo === "camera" ? Number(cameraId) : null,
          setor: tipo === "setor" ? setor : null,
        }),
      });
      aoCriar(res.intervencao);
    } catch (err) {
      setErros({ geral: mensagemDeErro(err, "Falha ao registrar a intervenção.") });
    } finally {
      setOcupado(false);
    }
  };

  return (
    <form className="card iv-form" onSubmit={enviar} noValidate aria-label="Registrar intervenção" data-testid="intervencao-form">
      <h3>Registrar intervenção</h3>
      <Campo id={`${base}-titulo`} rotulo="Título" erro={erros.titulo}>
        <input id={`${base}-titulo`} value={titulo} maxLength={160} onChange={(e) => setTitulo(e.target.value)} aria-invalid={erros.titulo ? true : undefined}
               aria-describedby={descrito(`${base}-titulo`, undefined, erros.titulo)} placeholder="Ex.: Nova sinalização no piso" />
      </Campo>
      <Campo id={`${base}-desc`} rotulo="O que foi feito (opcional)">
        <textarea id={`${base}-desc`} value={descricao} maxLength={2000} rows={3} onChange={(e) => setDescricao(e.target.value)} />
      </Campo>
      <Campo id={`${base}-data`} rotulo="Data da intervenção" erro={erros.data}>
        <input id={`${base}-data`} type="date" value={data} onChange={(e) => setData(e.target.value)} aria-invalid={erros.data ? true : undefined}
               aria-describedby={descrito(`${base}-data`, undefined, erros.data)} />
      </Campo>
      <fieldset className="iv-escopo">
        <legend className="iv-rotulo">Onde</legend>
        <label className="iv-radio">
          <input type="radio" name={`${base}-tipo`} checked={tipo === "camera"} onChange={() => setTipo("camera")} /> Uma câmera
        </label>
        <label className="iv-radio">
          <input type="radio" name={`${base}-tipo`} checked={tipo === "setor"} onChange={() => setTipo("setor")} /> Um setor
        </label>
        {tipo === "camera" ? (
          <select aria-label="Câmera" value={cameraId} onChange={(e) => setCameraId(e.target.value)}>
            <option value="">Escolha a câmera</option>
            {cameras.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        ) : (
          <select aria-label="Setor" value={setor} onChange={(e) => setSetor(e.target.value)}>
            <option value="">Escolha o setor</option>
            {setores.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        )}
        {erros.escopo && (
          <p className="iv-erro" role="alert">
            {erros.escopo}
          </p>
        )}
      </fieldset>
      {erros.geral && (
        <p className="iv-erro" role="alert">
          {erros.geral}
        </p>
      )}
      <div className="modal-acoes">
        <button type="button" className="ghost" onClick={aoCancelar} disabled={ocupado}>
          Voltar
        </button>
        <button type="submit" className="primary" disabled={ocupado}>
          {ocupado ? "Aguarde…" : "Registrar"}
        </button>
      </div>
    </form>
  );
}

// -------------------------------------------------------------- comparação ---
function Barras({ rotulo, antes, depois, maximo }: { rotulo: string; antes: number; depois: number; maximo: number }) {
  const largura = (v: number) => `${maximo > 0 ? Math.max(v > 0 ? 3 : 0, (v / maximo) * 100) : 0}%`;
  return (
    <div className="iv-linha" role="img" aria-label={`${rotulo}: antes ${antes}, depois ${depois}`}>
      <span className="iv-linha-rotulo">{rotulo}</span>
      <div className="iv-trilho">
        <span className="iv-barra antes" style={{ width: largura(antes) }} />
        <span className="iv-valor t-data">{inteiro(antes)}</span>
        <span className="iv-legenda">antes</span>
      </div>
      <div className="iv-trilho">
        <span className="iv-barra depois" style={{ width: largura(depois) }} />
        <span className="iv-valor t-data">{inteiro(depois)}</span>
        <span className="iv-legenda">depois</span>
      </div>
    </div>
  );
}

function AmostraDoLado({ titulo, lado }: { titulo: string; lado: Lado }) {
  const a = lado.amostra;
  const decorridos = lado.completa ? lado.dias_na_janela : lado.dias_decorridos;
  return (
    <div className="iv-amostra-lado">
      <strong>{titulo}</strong>
      <span>
        {pluralizar(a.dias_com_dados, "dia")} com dados em {decorridos} ({lado.completa ? "janela completa" : `de ${lado.dias_na_janela} da janela`})
      </span>
      <span>{pluralizar(a.minutos_conformes_registrados, "minuto conforme", "minutos conformes")} registrados</span>
    </div>
  );
}

function PainelDaComparacao({ dados }: { dados: Comparacao }) {
  const maximo = Math.max(1, dados.antes.alertas.total, dados.depois.alertas.total, dados.antes.incidentes.total, dados.depois.incidentes.total,
                          ...dados.por_regra.flatMap((r) => [r.antes, r.depois]));
  return (
    <div className="iv-comparacao" data-testid="intervencao-comparacao">
      {dados.aviso_da_janela && (
        <p className="iv-aviso-janela" role="status" data-testid="intervencao-aviso-janela">
          {dados.aviso_da_janela}
        </p>
      )}
      <div className="iv-barras">
        <Barras rotulo="Alertas" antes={dados.antes.alertas.total} depois={dados.depois.alertas.total} maximo={maximo} />
        <Barras rotulo="Incidentes" antes={dados.antes.incidentes.total} depois={dados.depois.incidentes.total} maximo={maximo} />
        {dados.por_regra.map((r) => (
          <Barras key={r.regra} rotulo={rotuloDaRegra(r.regra)} antes={r.antes} depois={r.depois} maximo={maximo} />
        ))}
      </div>
      {dados.variacao && (
        <p className="iv-variacao">
          Variação com a janela completa: alertas {percentual(dados.variacao.alertas_pct)}; incidentes {percentual(dados.variacao.incidentes_pct)}.
        </p>
      )}
      <div className="iv-amostra" aria-label="Tamanho da amostra">
        <h4>Tamanho da amostra</h4>
        <AmostraDoLado titulo="Antes" lado={dados.antes} />
        <AmostraDoLado titulo="Depois" lado={dados.depois} />
        {!dados.exposicao.disponivel && <p className="iv-ajuda">{dados.exposicao.motivo}</p>}
        {dados.observacoes.map((o) => (
          <p className="iv-ajuda" key={o}>
            {o}
          </p>
        ))}
      </div>
    </div>
  );
}

// --------------------------------------------------------------------- ROI ---
function FormularioDeRoi({ intervencaoId, comparacao }: { intervencaoId: number; comparacao: Comparacao | null }) {
  const base = useId();
  const [campos, setCampos] = useState({ custo: "", evitados: "", medio: "", periodo: "", horas: "", valorHora: "" });
  const [resultado, setResultado] = useState<ResultadoRoi | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const mudar = (campo: keyof typeof campos) => (e: { target: { value: string } }) => setCampos((c) => ({ ...c, [campo]: e.target.value }));
  const podeUsarObservado = comparacao !== null && comparacao.depois.completa;

  const usarObservado = () => {
    if (!comparacao) return;
    const diferenca = Math.max(0, comparacao.antes.incidentes.total - comparacao.depois.incidentes.total);
    setCampos((c) => ({ ...c, evitados: String(diferenca), periodo: String(comparacao.janela_dias) }));
  };

  const calcular = async (e: FormEvent) => {
    e.preventDefault();
    const numeros = {
      custo_da_intervencao: lerNumero(campos.custo),
      incidentes_evitados: lerNumero(campos.evitados),
      custo_medio_por_incidente: lerNumero(campos.medio),
      periodo_dias: lerNumero(campos.periodo),
      horas_perdidas_por_incidente: campos.horas.trim() ? lerNumero(campos.horas) : 0,
      custo_da_hora: campos.valorHora.trim() ? lerNumero(campos.valorHora) : 0,
    };
    if (Object.values(numeros).some((v) => v === null)) {
      setResultado(null);
      setErro("Preencha os números obrigatórios, só com dígitos (vírgula nos centavos).");
      return;
    }
    setOcupado(true);
    setErro(null);
    try {
      setResultado(await apiFetch<ResultadoRoi>(`/api/intervencoes/${intervencaoId}/roi`, { method: "POST", body: JSON.stringify(numeros) }));
    } catch (err) {
      setResultado(null);
      setErro(mensagemDeErro(err, "Falha ao calcular o retorno."));
    } finally {
      setOcupado(false);
    }
  };

  return (
    <section className="card iv-roi" aria-label="Retorno do investimento" data-testid="intervencao-roi">
      <h3>Retorno do investimento</h3>
      <p className="iv-ajuda">
        Estimativa com as suas premissas. Digite os seus números: o sistema não traz custo, média de mercado nem estatística oficial.
      </p>
      <form onSubmit={calcular} noValidate className="iv-roi-form">
        <Campo id={`${base}-custo`} rotulo="Custo da intervenção (R$)">
          <input id={`${base}-custo`} inputMode="decimal" value={campos.custo} onChange={mudar("custo")} />
        </Campo>
        <Campo id={`${base}-evitados`} rotulo="Incidentes evitados no período" ajuda="O que você estima ter evitado. O botão abaixo sugere a diferença observada.">
          <input id={`${base}-evitados`} inputMode="decimal" value={campos.evitados} onChange={mudar("evitados")} aria-describedby={`${base}-evitados-ajuda`} />
        </Campo>
        <Campo id={`${base}-periodo`} rotulo="Período dos incidentes evitados (dias)">
          <input id={`${base}-periodo`} inputMode="numeric" value={campos.periodo} onChange={mudar("periodo")} />
        </Campo>
        <Campo id={`${base}-medio`} rotulo="Custo médio estimado de um incidente (R$)">
          <input id={`${base}-medio`} inputMode="decimal" value={campos.medio} onChange={mudar("medio")} />
        </Campo>
        <Campo id={`${base}-horas`} rotulo="Horas perdidas por incidente (opcional)">
          <input id={`${base}-horas`} inputMode="decimal" value={campos.horas} onChange={mudar("horas")} />
        </Campo>
        <Campo id={`${base}-hora`} rotulo="Custo de uma hora (R$, opcional)">
          <input id={`${base}-hora`} inputMode="decimal" value={campos.valorHora} onChange={mudar("valorHora")} />
        </Campo>
        <div className="modal-acoes iv-roi-acoes">
          <button type="button" className="ghost" onClick={usarObservado} disabled={!podeUsarObservado}
                  title={podeUsarObservado ? undefined : "Disponível quando a janela do depois estiver completa."}>
            Usar a diferença observada
          </button>
          <button type="submit" className="primary" disabled={ocupado}>
            {ocupado ? "Aguarde…" : "Calcular"}
          </button>
        </div>
      </form>
      {erro && (
        <p className="iv-erro" role="alert">
          {erro}
        </p>
      )}
      {resultado && (
        <div className="iv-roi-resultado" data-testid="roi-resultado" role="status">
          <h4>Estimativa com as suas premissas</h4>
          <dl>
            <div><dt>Economia estimada no período</dt><dd className="t-data">{dinheiro(resultado.resultado.economia)}</dd></div>
            <div><dt>Ganho líquido</dt><dd className="t-data">{dinheiro(resultado.resultado.ganho_liquido)}</dd></div>
            <div>
              <dt>Retorno sobre o custo</dt>
              <dd className="t-data">{resultado.resultado.roi_pct === null ? "não calculado" : `${decimal(resultado.resultado.roi_pct)}%`}</dd>
            </div>
            <div>
              <dt>Retorno do investimento em</dt>
              <dd className="t-data">{resultado.resultado.payback_dias === null ? "não calculado" : `${decimal(resultado.resultado.payback_dias)} dias`}</dd>
            </div>
          </dl>
          <pre className="iv-formula" aria-label="Fórmula usada">{resultado.formula}</pre>
          <p className="iv-ajuda">{resultado.aviso}</p>
        </div>
      )}
    </section>
  );
}

// ------------------------------------------------------------------ detalhe ---
function DetalheDaIntervencao({ item, podeApagar, aoApagar }: { item: Intervencao; podeApagar: boolean; aoApagar: () => void }) {
  const [janela, setJanela] = useState(7);
  const [dados, setDados] = useState<Comparacao | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [tentativa, setTentativa] = useState(0);
  const [confirmando, setConfirmando] = useState(false);
  const [apagando, setApagando] = useState(false);

  useEffect(() => {
    let vivo = true;
    setCarregando(true);
    setErro(null);
    apiFetch<Comparacao>(`/api/intervencoes/${item.id}/comparacao?janela_dias=${janela}`)
      .then((d) => vivo && setDados(d))
      .catch((e) => {
        if (!vivo) return;
        setDados(null);
        setErro(mensagemDeErro(e, "Falha ao carregar a comparação."));
      })
      .finally(() => vivo && setCarregando(false));
    return () => {
      vivo = false;
    };
  }, [item.id, janela, tentativa]);

  const apagar = async () => {
    setApagando(true);
    try {
      await apiFetch(`/api/intervencoes/${item.id}`, { method: "DELETE" });
      aoApagar();
    } catch (e) {
      setErro(mensagemDeErro(e, "Falha ao apagar a intervenção."));
      setConfirmando(false);
    } finally {
      setApagando(false);
    }
  };

  return (
    <div className="iv-detalhe">
      <section className="card iv-painel" aria-label={`Comparação: ${item.titulo}`}>
        <header className="iv-painel-topo">
          <div>
            <h3>{item.titulo}</h3>
            <p className="iv-ajuda">Intervenção em {dataCurta(item.data_da_intervencao)}. {item.descricao}</p>
          </div>
          <label className="iv-janela">
            <span className="iv-rotulo">Janela</span>
            <select value={janela} onChange={(e) => setJanela(Number(e.target.value))}>
              {JANELAS.map((j) => (
                <option key={j} value={j}>
                  {pluralizar(j, "dia")} antes e depois
                </option>
              ))}
            </select>
          </label>
        </header>
        <p className="iv-aviso" role="note" data-testid="intervencao-aviso">
          {dados?.aviso ?? AVISO_DE_CORRELACAO}
        </p>
        {carregando && !dados ? (
          <PanelSkeleton lines={5} />
        ) : erro ? (
          <div role="alert" className="iv-erro-bloco">
            <p className="iv-erro">{erro}</p>
            <button type="button" className="small" onClick={() => setTentativa((t) => t + 1)}>
              Tentar de novo
            </button>
          </div>
        ) : dados ? (
          <PainelDaComparacao dados={dados} />
        ) : null}
        {podeApagar && (
          <div className="iv-apagar">
            {confirmando ? (
              <>
                <span>Apagar esta intervenção? Os alertas e incidentes continuam no histórico.</span>
                <button type="button" className="ghost small" onClick={() => setConfirmando(false)} disabled={apagando}>
                  Voltar
                </button>
                <button type="button" className="danger small" onClick={apagar} disabled={apagando}>
                  {apagando ? "Aguarde…" : "Apagar"}
                </button>
              </>
            ) : (
              <button type="button" className="ghost small" onClick={() => setConfirmando(true)}>
                Apagar intervenção
              </button>
            )}
          </div>
        )}
      </section>
      <FormularioDeRoi key={item.id} intervencaoId={item.id} comparacao={dados} />
    </div>
  );
}

// -------------------------------------------------------------------- tela ---
export default function Intervencoes() {
  const cameras = useDashboardStore((s) => s.cameras);
  const papel = useDashboardStore((s) => s.user?.role);
  const podeRegistrar = papel === undefined || papel === "supervisor"; // sem conta (autenticação desligada) o servidor também libera
  const [itens, setItens] = useState<Intervencao[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [selecionada, setSelecionada] = useState<number | null>(null);
  const [criando, setCriando] = useState(false);

  const carregar = useCallback(() => {
    setErro(null);
    return apiFetch<{ items: Intervencao[] }>("/api/intervencoes")
      .then((res) => setItens(res.items))
      .catch((e) => setErro(mensagemDeErro(e, "Falha ao carregar as intervenções.")));
  }, []);
  useEffect(() => {
    void carregar();
  }, [carregar]);

  const nomeDaCamera = (id: number) => cameras.find((c) => c.id === id)?.name ?? `câmera ${id}`;
  const atual = itens?.find((i) => i.id === selecionada) ?? null;

  return (
    <div className="iv-tela" data-testid="intervencoes">
      <header className="iv-cabeca">
        <div>
          <h1>Antes e depois</h1>
          <p className="iv-ajuda">Compare janelas iguais de dias antes e depois de uma mudança na planta, e estime o retorno com os seus números.</p>
        </div>
        {podeRegistrar && !criando && (
          <button type="button" className="primary" onClick={() => setCriando(true)}>
            Registrar intervenção
          </button>
        )}
      </header>

      {criando && (
        <FormularioDeIntervencao
          aoCancelar={() => setCriando(false)}
          aoCriar={(nova) => {
            setCriando(false);
            setItens((atuais) => [nova, ...(atuais ?? [])]);
            setSelecionada(nova.id);
          }}
        />
      )}

      {erro ? (
        <div role="alert" className="iv-erro-bloco">
          <p className="iv-erro">{erro}</p>
          <button type="button" className="small" onClick={() => void carregar()}>
            Tentar de novo
          </button>
        </div>
      ) : itens === null ? (
        <PanelSkeleton lines={4} />
      ) : itens.length === 0 ? (
        <EmptyState
          titulo="Nenhuma intervenção registrada"
          ilustracao={<IlustracaoGrafico />}
          acao={
            podeRegistrar && !criando ? (
              <button type="button" className="primary" onClick={() => setCriando(true)}>
                Registrar intervenção
              </button>
            ) : undefined
          }
        >
          {podeRegistrar ? "Registre uma mudança feita na planta para ver o antes e o depois." : "O Supervisor registra as mudanças feitas na planta."}
        </EmptyState>
      ) : (
        <div className="iv-grade">
          <ul className="iv-lista card" aria-label="Intervenções registradas">
            {itens.map((i) => (
              <li key={i.id}>
                <button type="button" className={`iv-item ${i.id === selecionada ? "ativa" : ""}`.trim()} aria-pressed={i.id === selecionada}
                        onClick={() => setSelecionada(i.id === selecionada ? null : i.id)}>
                  <strong>{i.titulo}</strong>
                  <span>{dataCurta(i.data_da_intervencao)} · {escopoDe(i, nomeDaCamera)}</span>
                </button>
              </li>
            ))}
          </ul>
          {atual ? (
            <DetalheDaIntervencao
              key={atual.id}
              item={atual}
              podeApagar={podeRegistrar}
              aoApagar={() => {
                setItens((atuais) => (atuais ?? []).filter((i) => i.id !== atual.id));
                setSelecionada(null);
              }}
            />
          ) : (
            <p className="iv-ajuda iv-escolha">Escolha uma intervenção para abrir a comparação.</p>
          )}
        </div>
      )}
    </div>
  );
}
