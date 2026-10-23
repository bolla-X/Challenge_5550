import { useId, useState } from "react";
import type { FormEvent } from "react";
import { apiFetch } from "../../api/client";
import { mensagemDeErro } from "../../utils/erros";
import { Campo, descrito, usarFocoAoAbrir } from "./ui";
import { codigoDoErro } from "./tipos";
import type { Colaborador } from "./tipos";

/** Cadastro e edição de colaborador (só Supervisor). Sem CPF, sem foto: matrícula, nome, setor, função e admissão. */
export function FormularioDeColaborador({
  inicial,
  setores,
  aoSalvar,
  aoCancelar,
}: {
  inicial?: Colaborador;
  setores: string[];
  aoSalvar: (c: Colaborador) => void;
  aoCancelar: () => void;
}) {
  const base = useId();
  const ref = usarFocoAoAbrir();
  const [campos, setCampos] = useState({
    matricula: inicial?.matricula ?? "",
    nome: inicial?.nome ?? "",
    setor: inicial?.setor ?? "",
    funcao: inicial?.funcao ?? "",
    admissao: inicial?.admissao?.slice(0, 10) ?? "",
  });
  const [ativo, setAtivo] = useState(inicial?.ativo ?? true);
  const [erros, setErros] = useState<Record<string, string>>({});
  const [ocupado, setOcupado] = useState(false);
  const mudar = (campo: keyof typeof campos) => (e: { target: { value: string } }) => setCampos((c) => ({ ...c, [campo]: e.target.value }));
  const id = (nome: string) => `${base}-${nome}`;

  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    const novos: Record<string, string> = {};
    if (!campos.matricula.trim()) novos.matricula = "Informe a matrícula.";
    if (!campos.nome.trim()) novos.nome = "Informe o nome.";
    if (!campos.setor.trim()) novos.setor = "Informe o setor.";
    if (!campos.funcao.trim()) novos.funcao = "Informe a função.";
    if (!campos.admissao) novos.admissao = "Informe a data de admissão.";
    setErros(novos);
    if (Object.keys(novos).length) return;
    setOcupado(true);
    try {
      const corpo = { ...campos, matricula: campos.matricula.trim(), nome: campos.nome.trim(), setor: campos.setor.trim(), funcao: campos.funcao.trim(), ...(inicial ? { ativo } : {}) };
      const res = await apiFetch<{ colaborador: Colaborador }>(inicial ? `/api/gestao/colaboradores/${inicial.id}` : "/api/gestao/colaboradores", {
        method: inicial ? "PUT" : "POST",
        body: JSON.stringify(corpo),
      });
      aoSalvar(res.colaborador);
    } catch (err) {
      if (codigoDoErro(err) === "matricula_duplicada") setErros({ matricula: "Já existe um colaborador com esta matrícula." });
      else setErros({ geral: mensagemDeErro(err, "Não foi possível salvar o colaborador.") });
    } finally {
      setOcupado(false);
    }
  };

  const rotuloDoForm = inicial ? "Editar colaborador" : "Novo colaborador";
  return (
    <form ref={ref} className="card gt-form" onSubmit={enviar} noValidate aria-label={rotuloDoForm} data-testid="gestao-form-colaborador">
      <h2>{rotuloDoForm}</h2>
      <div className="gt-form-grade">
        <Campo id={id("matricula")} rotulo="Matrícula" erro={erros.matricula}>
          <input id={id("matricula")} value={campos.matricula} maxLength={32} onChange={mudar("matricula")} aria-invalid={erros.matricula ? true : undefined}
                 aria-describedby={descrito(id("matricula"), undefined, erros.matricula)} autoComplete="off" />
        </Campo>
        <Campo id={id("nome")} rotulo="Nome" erro={erros.nome}>
          <input id={id("nome")} value={campos.nome} maxLength={120} onChange={mudar("nome")} aria-invalid={erros.nome ? true : undefined}
                 aria-describedby={descrito(id("nome"), undefined, erros.nome)} autoComplete="off" />
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
        <Campo id={id("funcao")} rotulo="Função" erro={erros.funcao}>
          <input id={id("funcao")} value={campos.funcao} maxLength={80} onChange={mudar("funcao")} aria-invalid={erros.funcao ? true : undefined}
                 aria-describedby={descrito(id("funcao"), undefined, erros.funcao)} autoComplete="off" />
        </Campo>
        <Campo id={id("admissao")} rotulo="Data de admissão" erro={erros.admissao}>
          <input id={id("admissao")} type="date" value={campos.admissao} onChange={mudar("admissao")} aria-invalid={erros.admissao ? true : undefined}
                 aria-describedby={descrito(id("admissao"), undefined, erros.admissao)} />
        </Campo>
      </div>
      {inicial && (
        <label className="gt-check">
          <input type="checkbox" checked={ativo} onChange={(e) => setAtivo(e.target.checked)} /> Colaborador ativo
        </label>
      )}
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
