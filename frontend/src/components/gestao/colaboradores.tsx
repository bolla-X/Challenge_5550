import { useEffect, useMemo, useRef, useState } from "react";
import { useDashboardStore } from "../../store/dashboardStore";
import { pluralizar } from "../../utils/formato";
import { EmptyState, PanelSkeleton } from "../common";
import { IlustracaoFila } from "../ilustracoes";
import { FormularioDeColaborador } from "./form-colaborador";
import { contagem, dataCurta, dataHora, montarUrl, ROTULO_MOTIVO, ROTULO_TIPO, rotulo } from "./tipos";
import type { Colaborador, Entrega, ListaDeColaboradores, Ocorrencia } from "./tipos";
import { ErroComRetentativa, Selo, SeloDaEntrega, SeloDaGravidade, SeloDoStatus } from "./ui";
import { usarRecurso } from "./usar-recurso";

type SituacaoDaLista = "ativos" | "inativos" | "todos";
const ATIVO_DA_SITUACAO: Record<SituacaoDaLista, string> = { ativos: "true", inativos: "false", todos: "" };

// ------------------------------------------------------------------ detalhe ---
function DetalheDoColaborador({ id, ehSupervisor, setores, aoVoltar, aoMudar }: { id: number; ehSupervisor: boolean; setores: string[]; aoVoltar: () => void; aoMudar: () => void }) {
  const showMessage = useDashboardStore((s) => s.showMessage);
  const detalhe = usarRecurso<{ colaborador: Colaborador; entregas: Entrega[]; ocorrencias: Ocorrencia[] }>(`/api/gestao/colaboradores/${id}`, "Não foi possível carregar o colaborador.");
  const [editando, setEditando] = useState(false);
  const titulo = useRef<HTMLHeadingElement>(null);
  const carregado = Boolean(detalhe.dados);

  // O detalhe troca a lista inteira: o foco vai para o nome (ao abrir e ao sair da edição), para o leitor de tela anunciar onde está.
  useEffect(() => {
    if (!editando && carregado) titulo.current?.focus({ preventScroll: true });
  }, [editando, carregado]);

  const voltar = (
    <button type="button" className="ghost small" onClick={aoVoltar}>
      Voltar para a lista
    </button>
  );
  if (detalhe.erro) {
    return (
      <div className="gt-detalhe">
        {voltar}
        <ErroComRetentativa mensagem={detalhe.erro} aoTentar={detalhe.recarregar} />
      </div>
    );
  }
  if (!detalhe.dados) {
    return (
      <div className="gt-detalhe">
        {voltar}
        <PanelSkeleton lines={6} />
      </div>
    );
  }
  const { colaborador: c, entregas, ocorrencias } = detalhe.dados;

  return (
    <div className="gt-detalhe" data-testid="gestao-detalhe-colaborador">
      {voltar}
      {editando ? (
        <FormularioDeColaborador
          inicial={c}
          setores={setores}
          aoCancelar={() => setEditando(false)}
          aoSalvar={() => {
            setEditando(false);
            detalhe.recarregar();
            aoMudar();
            showMessage("Colaborador atualizado.", "ok");
          }}
        />
      ) : (
        <section className="card gt-painel" aria-label={`Colaborador ${c.nome}`}>
          <header className="gt-painel-topo">
            <div>
              <h2 ref={titulo} tabIndex={-1} className="gt-titulo-detalhe">{c.nome}</h2>
              <p className="gt-ajuda">
                Matrícula <span className="gt-num">{c.matricula}</span>
              </p>
            </div>
            <div className="gt-topo-acoes">
              {!c.ativo && <Selo tom="neutro">Inativo</Selo>}
              {ehSupervisor && (
                <button type="button" className="ghost small" onClick={() => setEditando(true)}>
                  Editar
                </button>
              )}
            </div>
          </header>
          <dl className="gt-ficha">
            <div><dt>Setor</dt><dd>{c.setor}</dd></div>
            <div><dt>Função</dt><dd>{c.funcao}</dd></div>
            <div><dt>Admissão</dt><dd>{dataCurta(c.admissao)}</dd></div>
            <div><dt>Entregas vigentes</dt><dd>{entregas.filter((e) => e.situacao === "vigente").length}</dd></div>
          </dl>
        </section>
      )}

      <section className="card gt-painel" aria-label="Histórico de EPIs">
        <h2>Histórico de EPIs</h2>
        <p className="gt-ajuda">Da entrega mais recente para a mais antiga.</p>
        {entregas.length === 0 ? (
          <EmptyState>Nenhuma entrega de EPI registrada para este colaborador.</EmptyState>
        ) : (
          <div className="tabela-rolavel">
            <table className="tabela" data-testid="gestao-historico">
              <thead>
                <tr>
                  <th>EPI</th>
                  <th className="num">Qtd.</th>
                  <th>Entregue em</th>
                  <th>Troca prevista</th>
                  <th>Devolvido em</th>
                  <th>Motivo</th>
                  <th>Situação</th>
                </tr>
              </thead>
              <tbody>
                {entregas.map((e) => (
                  <tr key={e.id}>
                    <td>
                      {e.epi.nome}
                      <span className="gt-sub">CA <span className="gt-num">{e.epi.ca}</span></span>
                    </td>
                    <td className="num">{e.quantidade}</td>
                    <td>{dataCurta(e.entregue_em)}</td>
                    <td>{dataCurta(e.troca_prevista_em)}</td>
                    <td>{dataCurta(e.devolvido_em)}</td>
                    <td>{rotulo(ROTULO_MOTIVO, e.motivo)}</td>
                    <td><SeloDaEntrega entrega={e} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="card gt-painel" aria-label="Ocorrências ligadas">
        <h2>Ocorrências ligadas</h2>
        {ocorrencias.length === 0 ? (
          <EmptyState>Nenhuma ocorrência ligada a este colaborador.</EmptyState>
        ) : (
          <div className="tabela-rolavel">
            <table className="tabela" data-testid="gestao-colaborador-ocorrencias">
              <thead>
                <tr>
                  <th>Código</th>
                  <th>Quando</th>
                  <th>Tipo</th>
                  <th>Gravidade</th>
                  <th>Descrição</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {ocorrencias.map((o) => (
                  <tr key={o.id}>
                    <td className="gt-num">{o.codigo}</td>
                    <td className="gt-nowrap">{dataHora(o.ocorrida_em)}</td>
                    <td>{rotulo(ROTULO_TIPO, o.tipo)}</td>
                    <td><SeloDaGravidade gravidade={o.gravidade} /></td>
                    <td className="gt-descricao">{o.descricao}</td>
                    <td><SeloDoStatus status={o.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

// -------------------------------------------------------------------- aba ---
export function AbaColaboradores({ ehSupervisor, aoMudar }: { ehSupervisor: boolean; aoMudar: () => void }) {
  const showMessage = useDashboardStore((s) => s.showMessage);
  const [busca, setBusca] = useState("");
  const [buscaAplicada, setBuscaAplicada] = useState("");
  const [setor, setSetor] = useState("");
  const [situacao, setSituacao] = useState<SituacaoDaLista>("ativos");
  const [criando, setCriando] = useState(false);
  const [selecionado, setSelecionado] = useState<number | null>(null);
  const [setores, setSetores] = useState<string[]>([]);
  const ultimoAberto = useRef<number | null>(null);

  // Ao voltar do detalhe, o foco volta ao nome que foi clicado (a lista continua montada por baixo).
  useEffect(() => {
    if (selecionado !== null || ultimoAberto.current === null) return;
    document.querySelector<HTMLElement>(`[data-testid="gestao-colaborador-${ultimoAberto.current}"]`)?.focus();
    ultimoAberto.current = null;
  }, [selecionado]);

  // Uma chamada por pausa na digitação, não por tecla.
  useEffect(() => {
    const t = window.setTimeout(() => setBuscaAplicada(busca.trim()), 250);
    return () => window.clearTimeout(t);
  }, [busca]);

  const url = useMemo(
    () => montarUrl("/api/gestao/colaboradores", { busca: buscaAplicada, setor, ativo: ATIVO_DA_SITUACAO[situacao] }),
    [buscaAplicada, setor, situacao],
  );
  const lista = usarRecurso<ListaDeColaboradores>(url, "Não foi possível carregar os colaboradores.");
  useEffect(() => {
    if (lista.dados?.setores?.length) setSetores((antes) => [...new Set([...antes, ...lista.dados!.setores])].sort((a, b) => a.localeCompare(b, "pt-BR")));
  }, [lista.dados]);

  const filtrando = Boolean(buscaAplicada || setor || situacao !== "ativos");
  const limparFiltros = () => {
    setBusca("");
    setBuscaAplicada("");
    setSetor("");
    setSituacao("ativos");
  };

  if (selecionado !== null) {
    return <DetalheDoColaborador id={selecionado} ehSupervisor={ehSupervisor} setores={setores} aoVoltar={() => setSelecionado(null)} aoMudar={() => { aoMudar(); lista.recarregar(); }} />;
  }

  const novo = ehSupervisor && (
    <button type="button" className="primary" aria-expanded={criando} onClick={() => setCriando((aberto) => !aberto)} data-testid="gestao-novo-colaborador">
      Novo colaborador
    </button>
  );
  const itens = lista.dados?.items;

  return (
    <div className="gt-aba">
      <div className="gt-barra">
        <div className="gt-filtros" role="search" aria-label="Filtrar colaboradores">
          <label className="field gt-campo gt-busca">
            <span className="gt-rotulo">Buscar por nome ou matrícula</span>
            <input type="search" value={busca} onChange={(e) => setBusca(e.target.value)} data-testid="gestao-busca-colaborador" autoComplete="off" />
          </label>
          <label className="field gt-campo">
            <span className="gt-rotulo">Setor</span>
            <select value={setor} onChange={(e) => setSetor(e.target.value)} data-testid="gestao-filtro-setor">
              <option value="">Todos os setores</option>
              {[...new Set([...setores, ...(setor ? [setor] : [])])].map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </label>
          <label className="field gt-campo">
            <span className="gt-rotulo">Situação</span>
            <select value={situacao} onChange={(e) => setSituacao(e.target.value as SituacaoDaLista)}>
              <option value="ativos">Ativos</option>
              <option value="inativos">Inativos</option>
              <option value="todos">Todos</option>
            </select>
          </label>
        </div>
        {novo}
      </div>

      {criando && (
        <FormularioDeColaborador
          setores={setores}
          aoCancelar={() => setCriando(false)}
          aoSalvar={(c) => {
            setCriando(false);
            lista.recarregar();
            aoMudar();
            showMessage(`Colaborador cadastrado: ${c.nome}.`, "ok");
          }}
        />
      )}

      {lista.erro ? (
        <ErroComRetentativa mensagem={lista.erro} aoTentar={lista.recarregar} />
      ) : lista.carregando || !itens ? (
        <PanelSkeleton lines={6} />
      ) : itens.length === 0 ? (
        filtrando ? (
          <EmptyState titulo="Nenhum colaborador encontrado" ilustracao={<IlustracaoFila />}
                      acao={<button type="button" className="small" onClick={limparFiltros}>Limpar filtros</button>}>
            Nenhum colaborador combina com a busca e os filtros escolhidos.
          </EmptyState>
        ) : (
          <EmptyState titulo="Nenhum colaborador cadastrado" ilustracao={<IlustracaoFila />}
                      acao={ehSupervisor && !criando ? <button type="button" className="primary" onClick={() => setCriando(true)}>Novo colaborador</button> : undefined}>
            {ehSupervisor ? "Cadastre o primeiro colaborador para registrar entregas de EPI." : "O Supervisor cadastra os colaboradores."}
          </EmptyState>
        )
      ) : (
        <section className="card gt-painel" aria-label="Colaboradores">
          <p className="gt-ajuda" role="status">{pluralizar(lista.dados?.count ?? itens.length, "colaborador", "colaboradores")}</p>
          <p className="gt-ajuda">Pendência: EPI em uso com a troca vencida ou com o CA vencido.</p>
          <div className="tabela-rolavel">
            <table className="tabela" data-testid="gestao-tabela-colaboradores">
              <thead>
                <tr>
                  <th>Matrícula</th>
                  <th>Nome</th>
                  <th>Setor</th>
                  <th>Função</th>
                  <th className="num">EPIs vigentes</th>
                  <th>Pendências</th>
                </tr>
              </thead>
              <tbody>
                {itens.map((c) => {
                  const pendencias = contagem(c.pendencias);
                  return (
                    <tr key={c.id}>
                      <td className="gt-num">{c.matricula}</td>
                      <td>
                        <button type="button" className="gt-link" onClick={() => { ultimoAberto.current = c.id; setSelecionado(c.id); }} data-testid={`gestao-colaborador-${c.id}`}>
                          {c.nome}
                        </button>
                        {!c.ativo && <Selo tom="neutro">Inativo</Selo>}
                      </td>
                      <td>{c.setor}</td>
                      <td>{c.funcao}</td>
                      <td className="num">{contagem(c.entregas_vigentes)}</td>
                      <td>{pendencias > 0 ? <Selo tom="perigo">{pluralizar(pendencias, "pendência")}</Selo> : <span className="gt-sub-inline">Nenhuma</span>}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
