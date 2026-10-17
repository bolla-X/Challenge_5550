import novidades from "../novidades.json";
import { EmptyState } from "./common";
import "../styles/novidades.css";

/**
 * Novidades (`/novidades`): o que mudou no VisionEPI, na linguagem de quem usa.
 * Os textos vêm de `src/novidades.json`, gerado por `scripts/gerar_novidades.py`
 * a partir das seções "Novidades" do CHANGELOG (só título e frase, sem número de
 * medição nem nome de arquivo). A tela não tem estado de rede: o arquivo vai no build.
 */

type Item = { titulo: string; texto: string };
type Missao = { missao: string; titulo: string; data: string; itens: Item[] };

const MISSOES = (novidades as { missoes: Missao[] }).missoes;
const FORMATO_DA_DATA = new Intl.DateTimeFormat("pt-BR", { day: "numeric", month: "long", year: "numeric" });

/** "2026-10-17" → "17 de outubro de 2026". Meio-dia local: a data não pula de dia por fuso. */
function dataPorExtenso(iso: string): string {
  return FORMATO_DA_DATA.format(new Date(`${iso}T12:00:00`));
}

export default function NovidadesScreen() {
  return (
    <div className="screen novidades" data-testid="novidades">
      <header className="screen-head">
        <h1>Novidades</h1>
        <p className="screen-sub">O que mudou no VisionEPI, da mais recente para a mais antiga.</p>
        <div className="screen-actions">
          <a className="button ghost" href="/">
            Voltar ao painel
          </a>
        </div>
      </header>

      {MISSOES.length === 0 ? (
        <EmptyState titulo="Nenhuma novidade registrada">Quando uma versão nova sair, o que mudou aparece aqui.</EmptyState>
      ) : (
        MISSOES.map((m) => (
          <section className="card novidades-missao" key={`${m.missao}-${m.data}`} aria-labelledby={`nov-${m.data}-${m.missao.replace(/\s/g, "")}`}>
            <div className="novidades-topo">
              <p className="novidades-etapa">{m.missao}</p>
              <h2 id={`nov-${m.data}-${m.missao.replace(/\s/g, "")}`}>{m.titulo}</h2>
              <time dateTime={m.data}>{dataPorExtenso(m.data)}</time>
            </div>
            <ul className="novidades-itens">
              {m.itens.map((item) => (
                <li key={item.titulo}>
                  <strong>{item.titulo}</strong>
                  <span>{item.texto}</span>
                </li>
              ))}
            </ul>
          </section>
        ))
      )}
    </div>
  );
}
