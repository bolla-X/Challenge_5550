import { useId, useMemo, useState } from "react";
import type { FormEvent } from "react";
import { apiFetch } from "../../api/client";
import { useDashboardStore } from "../../store/dashboardStore";
import { mensagemDeErro } from "../../utils/erros";
import { pluralizar } from "../../utils/formato";
import { EmptyState, PanelSkeleton } from "../common";
import { IlustracaoEscudo } from "../ilustracoes";
import { CATEGORIAS, codigoDoErro, contagem, dataCurta, montarUrl, ROTULO_CATEGORIA, rotulo } from "./tipos";
import type { Epi } from "./tipos";
import { Campo, descrito, ErroComRetentativa, SeloDoCa, usarFocoAoAbrir } from "./ui";
import { usarRecurso } from "./usar-recurso";

const AJUDA_DA_VIDA_UTIL = "A troca prevista de cada entrega é a data de entrega mais a vida útil.";

/** Cadastro e edição de item do catálogo (só Supervisor). */
function FormularioDeEpi({ inicial, aoSalvar, aoCancelar }: { inicial?: Epi; aoSalvar: (e: Epi) => void; aoCancelar: () => void }) {
  const base = useId();
  const ref = usarFocoAoAbrir();
  const [campos, setCampos] = useState({
    nome: inicial?.nome ?? "",
    categoria: inicial?.categoria ?? "helmet",
    ca: inicial?.ca ?? "",
    validade_ca: inicial?.validade_ca?.slice(0, 10) ?? "",
    fabricante: inicial?.fabricante ?? "",
    vida_util_dias: inicial ? String(inicial.vida_util_dias) : "",
  });
  const [erros, setErros] = useState<Record<string, string>>({});
  const [ocupado, setOcupado] = useState(false);
  const mudar = (campo: keyof typeof campos) => (e: { target: { value: string } }) => setCampos((c) => ({ ...c, [campo]: e.target.value }));
  const id = (nome: string) => `${base}-${nome}`;

  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    const novos: Record<string, string> = {};
    const vida = Number(campos.vida_util_dias);
    if (!campos.nome.trim()) novos.nome = "Informe o nome do EPI.";
    if (!campos.ca.trim()) novos.ca = "Informe o número do CA.";
    if (!campos.validade_ca) novos.validade_ca = "Informe a validade do CA.";
    if (!campos.fabricante.trim()) novos.fabricante = "Informe o fabricante.";
    if (!Number.isInteger(vida) || vida < 1) novos.vida_util_dias = "Informe a vida útil em dias, um número inteiro maior que zero.";
    setErros(novos);
    if (Object.keys(novos).length) return;
    setOcupado(true);
    try {
      const res = await apiFetch<{ epi: Epi }>(inicial ? `/api/gestao/epis/${inicial.id}` : "/api/gestao/epis", {
        method: inicial ? "PUT" : "POST",
        body: JSON.stringify({ ...campos, nome: campos.nome.trim(), ca: campos.ca.trim(), fabricante: campos.fabricante.trim(), vida_util_dias: vida }),
      });
      aoSalvar(res.epi);
    } catch (err) {
      if (codigoDoErro(err) === "ca_duplicado") setErros({ ca: "Já existe um item no catálogo com este CA." });
      else setErros({ geral: mensagemDeErro(err, "Não foi possível salvar o item do catálogo.") });
    } finally {
      setOcupado(false);
    }
  };

  const rotuloDoForm = inicial ? "Editar item do catálogo" : "Novo item do catálogo";
  return (
    <form ref={ref} className="card gt-form" onSubmit={enviar} noValidate aria-label={rotuloDoForm} data-testid="gestao-form-epi">
      <h2>{rotuloDoForm}</h2>
      <div className="gt-form-grade">
        <Campo id={id("nome")} rotulo="Nome" erro={erros.nome}>
          <input id={id("nome")} value={campos.nome} maxLength={120} onChange={mudar("nome")} aria-invalid={erros.nome ? true : undefined}
                 aria-describedby={descrito(id("nome"), undefined, erros.nome)} autoComplete="off" />
        </Campo>
        <Campo id={id("categoria")} rotulo="Categoria">
          <select id={id("categoria")} value={campos.categoria} onChange={mudar("categoria")}>
            {CATEGORIAS.map((c) => (
              <option key={c} value={c}>{rotulo(ROTULO_CATEGORIA, c)}</option>
            ))}
          </select>
        </Campo>
        <Campo id={id("ca")} rotulo="Número do CA" erro={erros.ca}>
          <input id={id("ca")} value={campos.ca} maxLength={20} inputMode="numeric" onChange={mudar("ca")} aria-invalid={erros.ca ? true : undefined}
                 aria-describedby={descrito(id("ca"), undefined, erros.ca)} autoComplete="off" />
        </Campo>
        <Campo id={id("validade")} rotulo="Validade do CA" erro={erros.validade_ca}>
          <input id={id("validade")} type="date" value={campos.validade_ca} onChange={mudar("validade_ca")} aria-invalid={erros.validade_ca ? true : undefined}
                 aria-describedby={descrito(id("validade"), undefined, erros.validade_ca)} />
        </Campo>
        <Campo id={id("fabricante")} rotulo="Fabricante" erro={erros.fabricante}>
          <input id={id("fabricante")} value={campos.fabricante} maxLength={120} onChange={mudar("fabricante")} aria-invalid={erros.fabricante ? true : undefined}
                 aria-describedby={descrito(id("fabricante"), undefined, erros.fabricante)} autoComplete="off" />
        </Campo>
        <Campo id={id("vida")} rotulo="Vida útil (dias)" ajuda={AJUDA_DA_VIDA_UTIL} erro={erros.vida_util_dias}>
          <input id={id("vida")} inputMode="numeric" value={campos.vida_util_dias} onChange={mudar("vida_util_dias")} aria-invalid={erros.vida_util_dias ? true : undefined}
                 aria-describedby={descrito(id("vida"), AJUDA_DA_VIDA_UTIL, erros.vida_util_dias)} />
        </Campo>
      </div>
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
          {ocupado ? "Aguarde…" : "Salvar"}
        </button>
      </div>
    </form>
  );
}

const SITUACOES_DO_CA = [
  ["valido", "Válido"],
  ["a_vencer", "A vencer"],
  ["vencido", "Vencido"],
] as const;

export function AbaCatalogo({ ehSupervisor, aoMudar }: { ehSupervisor: boolean; aoMudar: () => void }) {
  const showMessage = useDashboardStore((s) => s.showMessage);
  const [categoria, setCategoria] = useState("");
  const [situacao, setSituacao] = useState("");
  const [formulario, setFormulario] = useState<{ epi?: Epi } | null>(null);
  const url = useMemo(() => montarUrl("/api/gestao/epis", { categoria, situacao }), [categoria, situacao]);
  const lista = usarRecurso<{ items: Epi[]; count: number }>(url, "Não foi possível carregar o catálogo de EPIs.");
  const itens = lista.dados?.items;

  return (
    <div className="gt-aba">
      <div className="gt-barra">
        <div className="gt-filtros" role="search" aria-label="Filtrar o catálogo">
          <label className="field gt-campo">
            <span className="gt-rotulo">Categoria</span>
            <select value={categoria} onChange={(e) => setCategoria(e.target.value)}>
              <option value="">Todas as categorias</option>
              {CATEGORIAS.map((c) => (
                <option key={c} value={c}>{rotulo(ROTULO_CATEGORIA, c)}</option>
              ))}
            </select>
          </label>
          <label className="field gt-campo">
            <span className="gt-rotulo">Situação do CA</span>
            <select value={situacao} onChange={(e) => setSituacao(e.target.value)}>
              <option value="">Todas</option>
              {SITUACOES_DO_CA.map(([valor, nome]) => (
                <option key={valor} value={valor}>{nome}</option>
              ))}
            </select>
          </label>
        </div>
        {ehSupervisor && (
          <button type="button" className="primary" aria-expanded={formulario !== null && !formulario.epi} onClick={() => setFormulario(formulario && !formulario.epi ? null : {})}
                  data-testid="gestao-novo-epi">
            Novo item
          </button>
        )}
      </div>

      {formulario && (
        <FormularioDeEpi
          key={formulario.epi?.id ?? "novo"}
          inicial={formulario.epi}
          aoCancelar={() => setFormulario(null)}
          aoSalvar={(epi) => {
            setFormulario(null);
            lista.recarregar();
            aoMudar();
            showMessage(`Item salvo no catálogo: ${epi.nome}.`, "ok");
          }}
        />
      )}

      {lista.erro ? (
        <ErroComRetentativa mensagem={lista.erro} aoTentar={lista.recarregar} />
      ) : lista.carregando || !itens ? (
        <PanelSkeleton lines={6} />
      ) : itens.length === 0 ? (
        <EmptyState titulo="Nenhum item no catálogo" ilustracao={<IlustracaoEscudo />}
                    acao={ehSupervisor && !formulario ? <button type="button" className="primary" onClick={() => setFormulario({})}>Novo item</button> : undefined}>
          {categoria || situacao ? "Nenhum item combina com os filtros escolhidos." : ehSupervisor ? "Cadastre os EPIs com o número do CA e a validade." : "O Supervisor cadastra os itens do catálogo."}
        </EmptyState>
      ) : (
        <section className="card gt-painel" aria-label="Catálogo de EPIs">
          <p className="gt-ajuda" role="status">
            {pluralizar(lista.dados?.count ?? itens.length, "item", "itens")}
            {itens.some((i) => i.ficticio) && ". Os CAs desta demonstração são fictícios (faixa 9xxxxx) e não têm validade legal."}
          </p>
          <div className="tabela-rolavel">
            <table className="tabela" data-testid="gestao-tabela-epis">
              <thead>
                <tr>
                  <th>EPI</th>
                  <th>Categoria</th>
                  <th>CA</th>
                  <th>Validade do CA</th>
                  <th className="num">Vida útil</th>
                  <th className="num">Entregas vigentes</th>
                  {ehSupervisor && <th><span className="gt-so-leitor">Ações</span></th>}
                </tr>
              </thead>
              <tbody>
                {itens.map((e) => (
                  <tr key={e.id} data-testid={`gestao-epi-${e.id}`}>
                    <td>
                      {e.nome}
                      <span className="gt-sub">{e.fabricante}</span>
                    </td>
                    <td>{rotulo(ROTULO_CATEGORIA, e.categoria)}</td>
                    <td className="gt-num">{e.ca}</td>
                    <td>
                      <span className="gt-nowrap">{dataCurta(e.validade_ca)}</span>
                      <SeloDoCa epi={e} />
                    </td>
                    <td className="num">{pluralizar(e.vida_util_dias, "dia")}</td>
                    <td className="num">{contagem(e.entregas_vigentes)}</td>
                    {ehSupervisor && (
                      <td>
                        <button type="button" className="ghost small" onClick={() => setFormulario({ epi: e })} aria-label={`Editar ${e.nome}`}>
                          Editar
                        </button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
