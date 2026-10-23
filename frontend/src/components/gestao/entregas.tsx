import { useId, useMemo, useState } from "react";
import type { FormEvent } from "react";
import { apiFetch } from "../../api/client";
import { useDashboardStore } from "../../store/dashboardStore";
import { mensagemDeErro } from "../../utils/erros";
import { pluralizar } from "../../utils/formato";
import { EmptyState, PanelSkeleton } from "../common";
import { IlustracaoFila } from "../ilustracoes";
import { codigoDoErro, dataCurta, hojeIso, montarUrl, ROTULO_MOTIVO, ROTULO_SITUACAO_ENTREGA } from "./tipos";
import type { Entrega, Epi, ListaDeColaboradores } from "./tipos";
import { Campo, descrito, ErroComRetentativa, SeloDaEntrega, usarFocoAoAbrir } from "./ui";
import { usarRecurso } from "./usar-recurso";

/**
 * O texto do CA vencido, o mesmo no aviso ao escolher o EPI e no 409 `ca_vencido`: a regra é da empresa, não da NR-6
 * (a norma não proíbe expressamente). Sem a data (EPI que a tela não conhece), a frase perde só o "venceu em".
 */
const mensagemDeCaVencido = (validade?: string) =>
  `O CA deste EPI ${validade ? `venceu em ${dataCurta(validade)}` : "está vencido"} e a entrega está bloqueada pela política da empresa. Escolha outro item ou peça ao Supervisor para atualizar o CA no catálogo.`;

function FormularioDeEntrega({ aoSalvar, aoCancelar }: { aoSalvar: () => void; aoCancelar: () => void }) {
  const base = useId();
  const ref = usarFocoAoAbrir();
  const colaboradores = usarRecurso<ListaDeColaboradores>("/api/gestao/colaboradores?ativo=true", "Não foi possível carregar os colaboradores.");
  const epis = usarRecurso<{ items: Epi[] }>("/api/gestao/epis", "Não foi possível carregar o catálogo de EPIs.");
  const [campos, setCampos] = useState({ colaborador_id: "", epi_id: "", quantidade: "1", entregue_em: hojeIso(), motivo: "admissao", observacao: "" });
  const [erros, setErros] = useState<Record<string, string>>({});
  const [ocupado, setOcupado] = useState(false);
  const mudar = (campo: keyof typeof campos) => (e: { target: { value: string } }) => setCampos((c) => ({ ...c, [campo]: e.target.value }));
  const id = (nome: string) => `${base}-${nome}`;
  const escolhido = epis.dados?.items.find((i) => String(i.id) === campos.epi_id);
  // Aviso na hora da escolha; o 409 do servidor continua sendo a autoridade (a tela não bloqueia o envio).
  const avisoDoCa = escolhido?.situacao_ca === "vencido" ? mensagemDeCaVencido(escolhido.validade_ca) : undefined;
  const ajudaDoCa =
    escolhido?.situacao_ca === "a_vencer" && typeof escolhido.dias_para_vencer === "number" ? `O CA vence em ${pluralizar(escolhido.dias_para_vencer, "dia")}.` : undefined;

  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    const novos: Record<string, string> = {};
    const quantidade = Number(campos.quantidade);
    if (!campos.colaborador_id) novos.colaborador_id = "Escolha o colaborador.";
    if (!campos.epi_id) novos.epi_id = "Escolha o EPI.";
    if (!Number.isInteger(quantidade) || quantidade < 1) novos.quantidade = "Informe uma quantidade inteira, de 1 em diante.";
    if (!campos.entregue_em) novos.entregue_em = "Informe a data da entrega.";
    setErros(novos);
    if (Object.keys(novos).length) return;
    setOcupado(true);
    try {
      await apiFetch<{ entrega: Entrega }>("/api/gestao/entregas", {
        method: "POST",
        body: JSON.stringify({ ...campos, colaborador_id: Number(campos.colaborador_id), epi_id: Number(campos.epi_id), quantidade }),
      });
      aoSalvar();
    } catch (err) {
      if (codigoDoErro(err) === "ca_vencido") {
        setErros({ epi_id: mensagemDeCaVencido(escolhido?.validade_ca) });
      } else {
        setErros({ geral: mensagemDeErro(err, "Não foi possível registrar a entrega.") });
      }
    } finally {
      setOcupado(false);
    }
  };

  const falhaNaBase = colaboradores.erro ?? epis.erro;
  return (
    <form ref={ref} className="card gt-form" onSubmit={enviar} noValidate aria-label="Registrar entrega" data-testid="gestao-form-entrega">
      <h2>Registrar entrega</h2>
      {falhaNaBase && (
        <ErroComRetentativa mensagem={falhaNaBase} aoTentar={() => { colaboradores.recarregar(); epis.recarregar(); }} />
      )}
      <div className="gt-form-grade">
        <Campo id={id("colaborador")} rotulo="Colaborador" erro={erros.colaborador_id}>
          <select id={id("colaborador")} value={campos.colaborador_id} onChange={mudar("colaborador_id")} aria-invalid={erros.colaborador_id ? true : undefined}
                  aria-describedby={descrito(id("colaborador"), undefined, erros.colaborador_id)} data-testid="gestao-entrega-colaborador">
            <option value="">Escolha o colaborador</option>
            {colaboradores.dados?.items.map((c) => (
              <option key={c.id} value={c.id}>{c.nome} ({c.matricula})</option>
            ))}
          </select>
        </Campo>
        <Campo id={id("epi")} rotulo="EPI" ajuda={ajudaDoCa} erro={erros.epi_id || avisoDoCa}>
          <select id={id("epi")} value={campos.epi_id} onChange={(e) => { mudar("epi_id")(e); setErros((antes) => ({ ...antes, epi_id: "" })); }}
                  aria-invalid={erros.epi_id || avisoDoCa ? true : undefined} aria-describedby={descrito(id("epi"), ajudaDoCa, erros.epi_id || avisoDoCa)}
                  data-testid="gestao-entrega-epi">
            <option value="">Escolha o EPI</option>
            {epis.dados?.items.map((i) => (
              <option key={i.id} value={i.id}>{i.nome}, CA {i.ca}{i.situacao_ca === "vencido" ? " (CA vencido)" : ""}</option>
            ))}
          </select>
        </Campo>
        <Campo id={id("quantidade")} rotulo="Quantidade" erro={erros.quantidade}>
          <input id={id("quantidade")} type="number" min={1} step={1} inputMode="numeric" value={campos.quantidade} onChange={mudar("quantidade")}
                 aria-invalid={erros.quantidade ? true : undefined} aria-describedby={descrito(id("quantidade"), undefined, erros.quantidade)} />
        </Campo>
        <Campo id={id("data")} rotulo="Data da entrega" erro={erros.entregue_em}>
          <input id={id("data")} type="date" value={campos.entregue_em} onChange={mudar("entregue_em")} aria-invalid={erros.entregue_em ? true : undefined}
                 aria-describedby={descrito(id("data"), undefined, erros.entregue_em)} />
        </Campo>
        <Campo id={id("motivo")} rotulo="Motivo">
          <select id={id("motivo")} value={campos.motivo} onChange={mudar("motivo")}>
            {Object.entries(ROTULO_MOTIVO).map(([valor, nome]) => (
              <option key={valor} value={valor}>{nome}</option>
            ))}
          </select>
        </Campo>
      </div>
      <Campo id={id("obs")} rotulo="Observação (opcional)">
        <textarea id={id("obs")} value={campos.observacao} maxLength={500} rows={2} onChange={mudar("observacao")} />
      </Campo>
      {erros.geral && (
        <p className="gt-erro" role="alert">
          {erros.geral}
        </p>
      )}
      <div className="modal-acoes">
        <button type="button" className="ghost" onClick={aoCancelar} disabled={ocupado}>
          Cancelar
        </button>
        <button type="submit" className="primary" disabled={ocupado}>
          {ocupado ? "Aguarde…" : "Registrar entrega"}
        </button>
      </div>
    </form>
  );
}

function PainelDeDevolucao({ entrega, aoConcluir, aoCancelar }: { entrega: Entrega; aoConcluir: () => void; aoCancelar: () => void }) {
  const base = useId();
  const ref = usarFocoAoAbrir();
  const [data, setData] = useState(hojeIso());
  const [erro, setErro] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);

  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    if (!data) {
      setErro("Informe a data da devolução.");
      return;
    }
    setOcupado(true);
    setErro(null);
    try {
      await apiFetch<{ entrega: Entrega }>(`/api/gestao/entregas/${entrega.id}/devolucao`, { method: "POST", body: JSON.stringify({ devolvido_em: data }) });
      aoConcluir();
    } catch (err) {
      setErro(codigoDoErro(err) === "ja_devolvido" ? "Esta entrega já foi devolvida." : mensagemDeErro(err, "Não foi possível registrar a devolução."));
    } finally {
      setOcupado(false);
    }
  };

  return (
    <form ref={ref} className="card gt-form" onSubmit={enviar} noValidate aria-label="Registrar devolução" data-testid="gestao-form-devolucao">
      <h2>Registrar devolução</h2>
      <p className="gt-ajuda">
        {entrega.epi.nome}, entregue a {entrega.colaborador.nome} em {dataCurta(entrega.entregue_em)} (<span className="gt-num">{entrega.codigo}</span>).
      </p>
      <Campo id={`${base}-data`} rotulo="Data da devolução" erro={erro ?? undefined}>
        <input id={`${base}-data`} type="date" value={data} onChange={(e) => setData(e.target.value)} aria-invalid={erro ? true : undefined}
               aria-describedby={descrito(`${base}-data`, undefined, erro ?? undefined)} />
      </Campo>
      <div className="modal-acoes">
        <button type="button" className="ghost" onClick={aoCancelar} disabled={ocupado}>
          Cancelar
        </button>
        <button type="submit" className="primary" disabled={ocupado}>
          {ocupado ? "Aguarde…" : "Registrar devolução"}
        </button>
      </div>
    </form>
  );
}

export function AbaEntregas({ aoMudar }: { aoMudar: () => void }) {
  const showMessage = useDashboardStore((s) => s.showMessage);
  const [situacao, setSituacao] = useState("");
  const [criando, setCriando] = useState(false);
  const [devolvendo, setDevolvendo] = useState<Entrega | null>(null);
  const url = useMemo(() => montarUrl("/api/gestao/entregas", { situacao }), [situacao]);
  const lista = usarRecurso<{ items: Entrega[]; count: number }>(url, "Não foi possível carregar as entregas.");
  const itens = lista.dados?.items;

  return (
    <div className="gt-aba">
      <div className="gt-barra">
        <div className="gt-filtros" role="search" aria-label="Filtrar entregas">
          <label className="field gt-campo">
            <span className="gt-rotulo">Situação</span>
            <select value={situacao} onChange={(e) => setSituacao(e.target.value)} data-testid="gestao-filtro-situacao">
              <option value="">Todas</option>
              {Object.entries(ROTULO_SITUACAO_ENTREGA).map(([valor, nome]) => (
                <option key={valor} value={valor}>{nome}</option>
              ))}
            </select>
          </label>
        </div>
        <button type="button" className="primary" aria-expanded={criando} onClick={() => { setDevolvendo(null); setCriando((aberto) => !aberto); }} data-testid="gestao-nova-entrega">
          Registrar entrega
        </button>
      </div>

      {criando && (
        <FormularioDeEntrega
          aoCancelar={() => setCriando(false)}
          aoSalvar={() => {
            setCriando(false);
            lista.recarregar();
            aoMudar();
            showMessage("Entrega registrada.", "ok");
          }}
        />
      )}
      {devolvendo && (
        <PainelDeDevolucao
          key={devolvendo.id}
          entrega={devolvendo}
          aoCancelar={() => setDevolvendo(null)}
          aoConcluir={() => {
            setDevolvendo(null);
            lista.recarregar();
            aoMudar();
            showMessage("Devolução registrada.", "ok");
          }}
        />
      )}

      {lista.erro ? (
        <ErroComRetentativa mensagem={lista.erro} aoTentar={lista.recarregar} />
      ) : lista.carregando || !itens ? (
        <PanelSkeleton lines={6} />
      ) : itens.length === 0 ? (
        <EmptyState titulo="Nenhuma entrega encontrada" ilustracao={<IlustracaoFila />}
                    acao={!criando ? <button type="button" className="primary" onClick={() => setCriando(true)}>Registrar entrega</button> : undefined}>
          {situacao ? "Nenhuma entrega está nesta situação." : "Registre a primeira entrega de EPI a um colaborador."}
        </EmptyState>
      ) : (
        <section className="card gt-painel" aria-label="Entregas de EPI">
          <p className="gt-ajuda" role="status">{pluralizar(lista.dados?.count ?? itens.length, "entrega")}</p>
          <div className="tabela-rolavel">
            <table className="tabela" data-testid="gestao-tabela-entregas">
              <thead>
                <tr>
                  <th>Código</th>
                  <th>Colaborador</th>
                  <th>EPI</th>
                  <th className="num">Qtd.</th>
                  <th>Entregue em</th>
                  <th>Troca prevista</th>
                  <th>Devolvido em</th>
                  <th>Situação</th>
                  <th><span className="gt-so-leitor">Ações</span></th>
                </tr>
              </thead>
              <tbody>
                {itens.map((e) => (
                  <tr key={e.id} data-testid={`gestao-entrega-${e.id}`}>
                    <td className="gt-num">{e.codigo}</td>
                    <td>
                      {e.colaborador.nome}
                      <span className="gt-sub">Matrícula <span className="gt-num">{e.colaborador.matricula}</span></span>
                    </td>
                    <td>
                      {e.epi.nome}
                      <span className="gt-sub">CA <span className="gt-num">{e.epi.ca}</span></span>
                    </td>
                    <td className="num">{e.quantidade}</td>
                    <td>{dataCurta(e.entregue_em)}</td>
                    <td>{dataCurta(e.troca_prevista_em)}</td>
                    <td>{dataCurta(e.devolvido_em)}</td>
                    <td><SeloDaEntrega entrega={e} /></td>
                    <td>
                      {e.situacao !== "devolvido" && (
                        <button type="button" className="ghost small gt-nowrap" onClick={() => { setCriando(false); setDevolvendo(e); }}
                                aria-label={`Registrar devolução de ${e.epi.nome} de ${e.colaborador.nome}`}>
                          Registrar devolução
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
      <p className="gt-ajuda gt-norma">NR-6, item 6.5.1 d): registrar o fornecimento de EPI ao empregado (livros, fichas ou sistema eletrônico).</p>
    </div>
  );
}
