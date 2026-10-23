import { useEffect, useId, useMemo, useState } from "react";
import type { FormEvent } from "react";
import { apiFetch } from "../../api/client";
import { useDashboardStore } from "../../store/dashboardStore";
import { mensagemDeErro } from "../../utils/erros";
import { pluralizar } from "../../utils/formato";
import { EmptyState, PanelSkeleton } from "../common";
import { IlustracaoEscudo } from "../ilustracoes";
import { agoraLocal, dataHora, instanteIso, montarUrl, ROTULO_GRAVIDADE, ROTULO_STATUS, ROTULO_TIPO } from "./tipos";
import type { ListaDeColaboradores, Ocorrencia } from "./tipos";
import { Campo, descrito, ErroComRetentativa, SeloDaGravidade, SeloDoStatus, usarFocoAoAbrir } from "./ui";
import { usarRecurso } from "./usar-recurso";

const opcoes = (mapa: Record<string, string>) =>
  Object.entries(mapa).map(([valor, nome]) => (
    <option key={valor} value={valor}>{nome}</option>
  ));

function FormularioDeOcorrencia({ setores, colaboradores, aoSalvar, aoCancelar }: { setores: string[]; colaboradores: ListaDeColaboradores | null; aoSalvar: () => void; aoCancelar: () => void }) {
  const base = useId();
  const ref = usarFocoAoAbrir();
  const [campos, setCampos] = useState({ tipo: "quase_acidente", gravidade: "media", setor: "", descricao: "", ocorrida_em: agoraLocal(), colaborador_id: "" });
  const [erros, setErros] = useState<Record<string, string>>({});
  const [ocupado, setOcupado] = useState(false);
  const mudar = (campo: keyof typeof campos) => (e: { target: { value: string } }) => setCampos((c) => ({ ...c, [campo]: e.target.value }));
  const id = (nome: string) => `${base}-${nome}`;

  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    const novos: Record<string, string> = {};
    if (!campos.setor.trim()) novos.setor = "Informe o setor.";
    if (!campos.descricao.trim()) novos.descricao = "Descreva o que aconteceu.";
    if (!campos.ocorrida_em) novos.ocorrida_em = "Informe a data e a hora.";
    setErros(novos);
    if (Object.keys(novos).length) return;
    setOcupado(true);
    try {
      await apiFetch<{ ocorrencia: Ocorrencia }>("/api/gestao/ocorrencias", {
        method: "POST",
        body: JSON.stringify({
          tipo: campos.tipo,
          gravidade: campos.gravidade,
          setor: campos.setor.trim(),
          descricao: campos.descricao.trim(),
          ocorrida_em: instanteIso(campos.ocorrida_em),
          colaborador_id: campos.colaborador_id ? Number(campos.colaborador_id) : null,
        }),
      });
      aoSalvar();
    } catch (err) {
      setErros({ geral: mensagemDeErro(err, "Não foi possível registrar a ocorrência.") });
    } finally {
      setOcupado(false);
    }
  };

  return (
    <form ref={ref} className="card gt-form" onSubmit={enviar} noValidate aria-label="Registrar ocorrência" data-testid="gestao-form-ocorrencia">
      <h2>Registrar ocorrência</h2>
      <div className="gt-form-grade">
        <Campo id={id("tipo")} rotulo="Tipo">
          <select id={id("tipo")} value={campos.tipo} onChange={mudar("tipo")}>{opcoes(ROTULO_TIPO)}</select>
        </Campo>
        <Campo id={id("gravidade")} rotulo="Gravidade">
          <select id={id("gravidade")} value={campos.gravidade} onChange={mudar("gravidade")}>{opcoes(ROTULO_GRAVIDADE)}</select>
        </Campo>
        <Campo id={id("setor")} rotulo="Setor" erro={erros.setor}>
          <input id={id("setor")} list={id("setores")} value={campos.setor} maxLength={80} onChange={mudar("setor")} aria-invalid={erros.setor ? true : undefined}
                 aria-describedby={descrito(id("setor"), undefined, erros.setor)} autoComplete="off" />
          <datalist id={id("setores")}>
            {setores.map((s) => (
              <option key={s} value={s} />
            ))}
          </datalist>
        </Campo>
        <Campo id={id("quando")} rotulo="Data e hora" erro={erros.ocorrida_em}>
          <input id={id("quando")} type="datetime-local" value={campos.ocorrida_em} onChange={mudar("ocorrida_em")} aria-invalid={erros.ocorrida_em ? true : undefined}
                 aria-describedby={descrito(id("quando"), undefined, erros.ocorrida_em)} />
        </Campo>
        <Campo id={id("colaborador")} rotulo="Colaborador (opcional)" ajuda="Só se a ocorrência envolveu uma pessoa conhecida. O vínculo é administrativo, não vem das câmeras.">
          <select id={id("colaborador")} value={campos.colaborador_id} onChange={mudar("colaborador_id")} aria-describedby={`${id("colaborador")}-ajuda`}>
            <option value="">Sem colaborador ligado</option>
            {colaboradores?.items.map((c) => (
              <option key={c.id} value={c.id}>{c.nome} ({c.matricula})</option>
            ))}
          </select>
        </Campo>
      </div>
      <Campo id={id("descricao")} rotulo="Descrição" erro={erros.descricao}>
        <textarea id={id("descricao")} value={campos.descricao} maxLength={2000} rows={3} onChange={mudar("descricao")} aria-invalid={erros.descricao ? true : undefined}
                  aria-describedby={descrito(id("descricao"), undefined, erros.descricao)} />
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
          {ocupado ? "Aguarde…" : "Registrar ocorrência"}
        </button>
      </div>
    </form>
  );
}

function PainelDeAtualizacao({ ocorrencia, aoConcluir, aoCancelar }: { ocorrencia: Ocorrencia; aoConcluir: () => void; aoCancelar: () => void }) {
  const base = useId();
  const ref = usarFocoAoAbrir();
  const [status, setStatus] = useState(ocorrencia.status as string);
  const [acao, setAcao] = useState(ocorrencia.acao_corretiva ?? "");
  const [erro, setErro] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);

  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    setOcupado(true);
    setErro(null);
    try {
      await apiFetch<{ ocorrencia: Ocorrencia }>(`/api/gestao/ocorrencias/${ocorrencia.id}`, { method: "PUT", body: JSON.stringify({ status, acao_corretiva: acao.trim() }) });
      aoConcluir();
    } catch (err) {
      setErro(mensagemDeErro(err, "Não foi possível atualizar a ocorrência."));
    } finally {
      setOcupado(false);
    }
  };

  return (
    <form ref={ref} className="card gt-form" onSubmit={enviar} noValidate aria-label="Atualizar ocorrência" data-testid="gestao-form-atualizar-ocorrencia">
      <h2>Atualizar ocorrência</h2>
      <p className="gt-ajuda"><span className="gt-num">{ocorrencia.codigo}</span>: {ocorrencia.descricao}</p>
      <Campo id={`${base}-status`} rotulo="Status">
        <select id={`${base}-status`} value={status} onChange={(e) => setStatus(e.target.value)} data-testid="gestao-ocorrencia-status">{opcoes(ROTULO_STATUS)}</select>
      </Campo>
      <Campo id={`${base}-acao`} rotulo="Ação corretiva" ajuda="O que foi ou será feito para evitar que aconteça de novo.">
        <textarea id={`${base}-acao`} value={acao} maxLength={2000} rows={3} onChange={(e) => setAcao(e.target.value)} aria-describedby={`${base}-acao-ajuda`} data-testid="gestao-ocorrencia-acao" />
      </Campo>
      {erro && (
        <p className="gt-erro" role="alert">
          {erro}
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

export function AbaOcorrencias({ aoMudar }: { aoMudar: () => void }) {
  const showMessage = useDashboardStore((s) => s.showMessage);
  const [status, setStatus] = useState("");
  const [tipo, setTipo] = useState("");
  const [setor, setSetor] = useState("");
  const [criando, setCriando] = useState(false);
  const [atualizando, setAtualizando] = useState<Ocorrencia | null>(null);
  const [setores, setSetores] = useState<string[]>([]);
  const base = usarRecurso<ListaDeColaboradores>("/api/gestao/colaboradores?ativo=true", "Não foi possível carregar os colaboradores.");
  const url = useMemo(() => montarUrl("/api/gestao/ocorrencias", { status, tipo, setor }), [status, tipo, setor]);
  const lista = usarRecurso<{ items: Ocorrencia[]; count: number }>(url, "Não foi possível carregar as ocorrências.");
  const itens = lista.dados?.items;

  // Setores para o filtro e o formulário: os dos colaboradores e os das ocorrências já vistas.
  useEffect(() => {
    const vistos = [...(base.dados?.setores ?? []), ...(itens?.map((o) => o.setor) ?? [])];
    if (vistos.length) setSetores((antes) => [...new Set([...antes, ...vistos])].sort((a, b) => a.localeCompare(b, "pt-BR")));
  }, [base.dados, itens]);

  return (
    <div className="gt-aba">
      <div className="gt-barra">
        <div className="gt-filtros" role="search" aria-label="Filtrar ocorrências">
          <label className="field gt-campo">
            <span className="gt-rotulo">Status</span>
            <select value={status} onChange={(e) => setStatus(e.target.value)} data-testid="gestao-filtro-status">
              <option value="">Todos</option>
              {opcoes(ROTULO_STATUS)}
            </select>
          </label>
          <label className="field gt-campo">
            <span className="gt-rotulo">Tipo</span>
            <select value={tipo} onChange={(e) => setTipo(e.target.value)}>
              <option value="">Todos</option>
              {opcoes(ROTULO_TIPO)}
            </select>
          </label>
          <label className="field gt-campo">
            <span className="gt-rotulo">Setor</span>
            <select value={setor} onChange={(e) => setSetor(e.target.value)}>
              <option value="">Todos os setores</option>
              {[...new Set([...setores, ...(setor ? [setor] : [])])].map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </label>
        </div>
        <button type="button" className="primary" aria-expanded={criando} onClick={() => { setAtualizando(null); setCriando((aberto) => !aberto); }} data-testid="gestao-nova-ocorrencia">
          Registrar ocorrência
        </button>
      </div>

      {criando && (
        <FormularioDeOcorrencia
          setores={setores}
          colaboradores={base.dados}
          aoCancelar={() => setCriando(false)}
          aoSalvar={() => {
            setCriando(false);
            lista.recarregar();
            aoMudar();
            showMessage("Ocorrência registrada.", "ok");
          }}
        />
      )}
      {atualizando && (
        <PainelDeAtualizacao
          key={atualizando.id}
          ocorrencia={atualizando}
          aoCancelar={() => setAtualizando(null)}
          aoConcluir={() => {
            setAtualizando(null);
            lista.recarregar();
            aoMudar();
            showMessage("Ocorrência atualizada.", "ok");
          }}
        />
      )}

      {lista.erro ? (
        <ErroComRetentativa mensagem={lista.erro} aoTentar={lista.recarregar} />
      ) : lista.carregando || !itens ? (
        <PanelSkeleton lines={6} />
      ) : itens.length === 0 ? (
        <EmptyState titulo="Nenhuma ocorrência encontrada" ilustracao={<IlustracaoEscudo />}
                    acao={!criando ? <button type="button" className="primary" onClick={() => setCriando(true)}>Registrar ocorrência</button> : undefined}>
          {status || tipo || setor ? "Nenhuma ocorrência combina com os filtros escolhidos." : "Registre acidentes, quase acidentes e condições inseguras para acompanhar a ação corretiva."}
        </EmptyState>
      ) : (
        <section className="card gt-painel" aria-label="Ocorrências de segurança">
          <p className="gt-ajuda" role="status">{pluralizar(lista.dados?.count ?? itens.length, "ocorrência")}</p>
          <div className="tabela-rolavel">
            <table className="tabela" data-testid="gestao-tabela-ocorrencias">
              <thead>
                <tr>
                  <th>Código</th>
                  <th>Quando</th>
                  <th>Tipo</th>
                  <th>Gravidade</th>
                  <th>Setor</th>
                  <th>Descrição</th>
                  <th>Colaborador</th>
                  <th>Status</th>
                  <th><span className="gt-so-leitor">Ações</span></th>
                </tr>
              </thead>
              <tbody>
                {itens.map((o) => (
                  <tr key={o.id} data-testid={`gestao-ocorrencia-${o.id}`}>
                    <td className="gt-num">{o.codigo}</td>
                    <td className="gt-nowrap">{dataHora(o.ocorrida_em)}</td>
                    <td>{ROTULO_TIPO[o.tipo] ?? o.tipo}</td>
                    <td><SeloDaGravidade gravidade={o.gravidade} /></td>
                    <td>{o.setor}</td>
                    <td className="gt-descricao">
                      {o.descricao}
                      {o.acao_corretiva && <span className="gt-sub">Ação corretiva: {o.acao_corretiva}</span>}
                    </td>
                    <td>{o.colaborador ? o.colaborador.nome : <span className="gt-sub-inline">Sem colaborador ligado</span>}</td>
                    <td><SeloDoStatus status={o.status} /></td>
                    <td>
                      <button type="button" className="ghost small gt-nowrap" onClick={() => { setCriando(false); setAtualizando(o); }}
                              aria-label={`Atualizar a ocorrência ${o.codigo}`}>
                        Atualizar
                      </button>
                    </td>
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
