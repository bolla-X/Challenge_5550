import { inteiro } from "../../utils/formato";
import { IconeGestao } from "../icones";
import type { Resumo } from "./tipos";
import { usarRecurso } from "./usar-recurso";
import "../../styles/gestao.css";

/** Entrada da Gestão de EPIs no Início do Supervisor, com o resumo que o servidor já calcula. Carrega só o necessário: fica fora do chunk da tela. */
export function CartaoGestaoInicio() {
  const { dados } = usarRecurso<Resumo>("/api/gestao/resumo");
  const pendencias = dados ? dados.trocas_vencidas + dados.cas_vencidos : 0;
  return (
    <a className="home-tile gt-tile" href="/gestao" data-testid="home-gestao">
      <IconeGestao size={22} />
      <span className="gt-tile-texto">
        <strong>Gestão de EPIs{dados?.simulados ? " (dados simulados)" : ""}</strong>
        <span>Colaboradores com histórico de EPIs, catálogo com CA, entregas, ocorrências e exportação.</span>
      </span>
      {dados && (
        <dl className="gt-tile-numeros" aria-label={`Resumo da gestão de EPIs${dados.simulados ? " (dados simulados)" : ""}`}>
          <div><dt>colaboradores ativos</dt><dd>{inteiro(dados.colaboradores_ativos)}</dd></div>
          <div><dt>entregas vigentes</dt><dd>{inteiro(dados.entregas_vigentes)}</dd></div>
          <div className={pendencias > 0 ? "pendencia" : ""}><dt>trocas e CAs vencidos</dt><dd>{inteiro(pendencias)}</dd></div>
          <div className={dados.ocorrencias_abertas > 0 ? "pendencia" : ""}><dt>ocorrências abertas</dt><dd>{inteiro(dados.ocorrencias_abertas)}</dd></div>
        </dl>
      )}
    </a>
  );
}
