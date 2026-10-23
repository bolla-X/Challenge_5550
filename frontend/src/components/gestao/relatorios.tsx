import { inteiro } from "../../utils/formato";
import { PanelSkeleton } from "../common";
import { IconeBaixar } from "../icones";
import type { Resumo } from "./tipos";
import { ErroComRetentativa } from "./ui";

/** Cartões do resumo: chave do servidor, rótulo e se um valor acima de zero é pendência (laranja de perigo). */
const CARTOES: { chave: keyof Omit<Resumo, "simulados">; rotulo: string; pendencia?: boolean }[] = [
  { chave: "colaboradores_ativos", rotulo: "Colaboradores ativos" },
  { chave: "epis_no_catalogo", rotulo: "EPIs no catálogo" },
  { chave: "entregas_vigentes", rotulo: "Entregas vigentes" },
  { chave: "trocas_vencidas", rotulo: "Trocas vencidas", pendencia: true },
  { chave: "cas_vencidos", rotulo: "CAs vencidos", pendencia: true },
  { chave: "cas_a_vencer", rotulo: "CAs a vencer em 30 dias", pendencia: true },
  { chave: "ocorrencias_abertas", rotulo: "Ocorrências abertas", pendencia: true },
  { chave: "ocorrencias_30d", rotulo: "Ocorrências em 30 dias" },
  { chave: "alertas_30d", rotulo: "Alertas das câmeras em 30 dias (contagem geral)" },
];

const EXPORTACOES: { recurso: string; rotulo: string; texto: string }[] = [
  { recurso: "colaboradores", rotulo: "Colaboradores", texto: "Matrícula, nome, setor, função e admissão." },
  { recurso: "epis", rotulo: "Catálogo de EPIs", texto: "Itens com CA, validade do CA e vida útil." },
  { recurso: "entregas", rotulo: "Entregas", texto: "Todas as entregas e devoluções, com a situação de cada uma." },
  { recurso: "ocorrencias", rotulo: "Ocorrências", texto: "Tipo, gravidade, status e ação corretiva." },
  { recurso: "alertas", rotulo: "Alertas", texto: "Histórico de alertas do monitoramento, sem vínculo com colaboradores. Na demonstração inclui alertas simulados." },
];

export function AbaRelatorios({ resumo, carregando, erro, aoTentar }: { resumo: Resumo | null; carregando: boolean; erro: string | null; aoTentar: () => void }) {
  return (
    <div className="gt-aba">
      <section className="card gt-painel" aria-label="Resumo">
        <h2>Resumo</h2>
        {erro ? (
          <ErroComRetentativa mensagem={erro} aoTentar={aoTentar} />
        ) : carregando || !resumo ? (
          <PanelSkeleton lines={4} />
        ) : (
          <dl className="gt-resumo" data-testid="gestao-resumo">
            {CARTOES.map(({ chave, rotulo, pendencia }) => (
              <div key={chave} className={pendencia && resumo[chave] > 0 ? "pendencia" : ""} data-testid={`gestao-resumo-${chave}`}>
                <dt>{rotulo}</dt>
                <dd>{inteiro(resumo[chave])}</dd>
              </div>
            ))}
          </dl>
        )}
      </section>

      <section className="card gt-painel" aria-label="Exportação">
        <h2>Exportar em CSV</h2>
        <p className="gt-ajuda">Planilhas com ponto e vírgula entre as colunas, em UTF-8. Cada arquivo leva a data do dia no nome.</p>
        <ul className="gt-exportar">
          {EXPORTACOES.map(({ recurso, rotulo, texto }) => (
            <li key={recurso}>
              <div>
                <strong>{rotulo}</strong>
                <span>{texto}</span>
              </div>
              <a className="button ghost" href={`/api/gestao/exportar/${recurso}.csv`} download data-testid={`gestao-exportar-${recurso}`}
                 aria-label={`Baixar CSV de ${rotulo.toLowerCase()}`}>
                <IconeBaixar /> Baixar CSV
              </a>
            </li>
          ))}
        </ul>
        <div className="gt-mensal">
          <span>O relatório mensal para a CIPA abre em outra aba.</span>
          <a className="button ghost" href="/relatorio/mensal" target="_blank" rel="noopener noreferrer" data-testid="gestao-relatorio-mensal">
            Abrir o relatório mensal
          </a>
        </div>
      </section>
    </div>
  );
}
