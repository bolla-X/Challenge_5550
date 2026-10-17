import { useEffect, useMemo, useRef, useState } from "react";
import { useDashboardStore } from "../store/dashboardStore";
import {
  ROTULO_DO_TIPO,
  TIPOS_DE_CONTA,
  artigoPorId,
  buscarArtigos,
  enderecoDoArtigo,
  type Artigo,
  type TipoDeConta,
} from "../ajuda/artigos";
import { pluralizar } from "../utils/formato";
import { EmptyState } from "./common";
import { IconeAjuda } from "./icones";
import "../styles/ajuda.css";

/**
 * Central de ajuda (`/ajuda`): artigos curtos por tarefa, com busca (sem acento
 * e sem diferenciar maiúsculas) e filtro por tipo de conta. `/ajuda?artigo=<id>`
 * abre direto no artigo. O conteúdo está em `ajuda/artigos.ts`.
 *
 * Como ligar: ver o comentário de `App.tsx` (rota `/ajuda`) e `BotaoDeAjuda` abaixo.
 */

/**
 * O "?" de cada tela: abre o artigo certo em outra aba, sem tirar a pessoa do que
 * está fazendo. O id vem de `ARTIGO_DA_TELA` (ajuda/artigos.ts).
 */
export function BotaoDeAjuda({ artigo }: { artigo: string }) {
  return (
    <a
      className="botao-de-ajuda"
      href={enderecoDoArtigo(artigo)}
      target="_blank"
      rel="noopener noreferrer"
      aria-label="Ajuda sobre esta tela"
      title="Ajuda sobre esta tela (abre em outra aba)"
      data-testid="botao-de-ajuda"
      data-artigo={artigo}
    >
      <IconeAjuda />
    </a>
  );
}

type Filtro = TipoDeConta | "todos";

function idDaUrl(): string | null {
  return new URLSearchParams(window.location.search).get("artigo");
}

function ArtigoAberto({ artigo, meuTipo, tituloRef }: { artigo: Artigo; meuTipo: TipoDeConta | null; tituloRef: React.RefObject<HTMLHeadingElement> }) {
  // Só oferece o link da tela a quem pode abri-la: o artigo diz para quem é.
  const podeAbrir = !meuTipo || artigo.paraQuem.includes(meuTipo);
  return (
    <article className="card ajuda-artigo" aria-labelledby="ajuda-artigo-titulo" data-testid="ajuda-artigo" data-artigo={artigo.id}>
      <header className="ajuda-artigo-cab">
        <ul className="ajuda-para" aria-label="Para quem">
          {artigo.paraQuem.map((tipo) => (
            <li key={tipo} className="chip">
              {ROTULO_DO_TIPO[tipo]}
            </li>
          ))}
        </ul>
        <h2 id="ajuda-artigo-titulo" ref={tituloRef} tabIndex={-1}>
          {artigo.titulo}
        </h2>
        <p className="ajuda-resumo">{artigo.resumo}</p>
      </header>

      <section aria-labelledby="ajuda-passos">
        <h3 id="ajuda-passos">{artigo.tituloDosPassos ?? "Passo a passo"}</h3>
        <ol className="ajuda-passos">
          {artigo.passos.map((passo) => (
            <li key={passo}>{passo}</li>
          ))}
        </ol>
      </section>

      {artigo.notas && artigo.notas.length > 0 && (
        <section aria-labelledby="ajuda-notas" className="ajuda-notas">
          <h3 id="ajuda-notas">Bom saber</h3>
          <ul>
            {artigo.notas.map((nota) => (
              <li key={nota}>{nota}</li>
            ))}
          </ul>
        </section>
      )}

      <section aria-labelledby="ajuda-onde">
        <h3 id="ajuda-onde">Onde fica</h3>
        <p>{artigo.ondeFica}</p>
        {artigo.tela && podeAbrir && (
          <a className="button ghost ajuda-tela" href={artigo.tela.href} data-testid="ajuda-abrir-tela">
            {artigo.tela.rotulo}
          </a>
        )}
      </section>
    </article>
  );
}

export function AjudaScreen() {
  const user = useDashboardStore((s) => s.user);
  const meuTipo: TipoDeConta | null = user?.role ?? null;
  const [idPedido] = useState(idDaUrl);
  const [abertoId, setAbertoId] = useState<string | null>(() => (artigoPorId(idPedido) ? idPedido : null));
  const [consulta, setConsulta] = useState("");
  const [filtro, setFiltro] = useState<Filtro>(() => {
    // Começa pelos artigos do seu tipo de conta, salvo se o link pediu um artigo de outro tipo.
    const pedido = artigoPorId(idPedido);
    if (!meuTipo || (pedido && !pedido.paraQuem.includes(meuTipo))) return "todos";
    return meuTipo;
  });
  const tituloRef = useRef<HTMLHeadingElement>(null);
  const moverFoco = useRef(false);

  const lista = useMemo(() => buscarArtigos(consulta, filtro === "todos" ? null : filtro), [consulta, filtro]);
  const aberto = artigoPorId(abertoId);
  const linkInvalido = idPedido !== null && !artigoPorId(idPedido);

  const abrir = (id: string) => {
    moverFoco.current = true;
    setAbertoId(id);
    try {
      window.history.replaceState(null, "", enderecoDoArtigo(id));
    } catch {
      // Sem History API: o artigo abre, só o endereço não acompanha.
    }
  };

  // Depois de escolher um artigo, o foco vai para o título dele (no celular a lista fica acima do texto).
  useEffect(() => {
    if (!moverFoco.current || !abertoId) return;
    moverFoco.current = false;
    tituloRef.current?.focus();
    tituloRef.current?.scrollIntoView?.({ block: "start" });
  }, [abertoId]);

  const limpar = () => {
    setConsulta("");
    setFiltro("todos");
  };

  return (
    <div className="screen ajuda" data-testid="ajuda">
      <div className="screen-head">
        <h1>Central de ajuda</h1>
        <span className="screen-sub">Passo a passo por tarefa, só com o que o sistema faz.</span>
        <div className="screen-actions">
          <a className="button ghost" href="/">
            Painel
          </a>
        </div>
      </div>

      <div className="ajuda-grade">
        <aside className="card ajuda-busca" aria-label="Buscar artigos">
          <div className="ajuda-busca-corpo">
            <input
              type="search"
              value={consulta}
              onChange={(e) => setConsulta(e.target.value)}
              aria-label="Buscar na ajuda"
              placeholder="Ex.: replay, vigia, referência"
              data-testid="ajuda-busca"
            />
            <div className="segmented ajuda-filtro" role="radiogroup" aria-label="Tipo de conta">
              {(["todos", ...TIPOS_DE_CONTA] as Filtro[]).map((valor) => (
                <button
                  key={valor}
                  type="button"
                  role="radio"
                  aria-checked={filtro === valor}
                  className={filtro === valor ? "active" : ""}
                  onClick={() => setFiltro(valor)}
                >
                  {valor === "todos" ? "Todos" : ROTULO_DO_TIPO[valor]}
                </button>
              ))}
            </div>
            <p className="ajuda-contagem" role="status" aria-live="polite" data-testid="ajuda-contagem">
              {pluralizar(lista.length, "artigo")}
            </p>
          </div>

          {lista.length === 0 ? (
            <div className="ajuda-vazio">
              <EmptyState titulo="Nenhum artigo encontrado">
                Tente outra palavra, como o nome do botão ou da tela, ou veja os artigos de todos os tipos de conta.
              </EmptyState>
              <button type="button" className="small" onClick={limpar}>
                Limpar busca
              </button>
            </div>
          ) : (
            <nav aria-label="Artigos da ajuda">
              <ul className="ajuda-lista">
                {lista.map((artigo) => (
                  <li key={artigo.id}>
                    <a
                      href={enderecoDoArtigo(artigo.id)}
                      aria-current={artigo.id === abertoId ? "true" : undefined}
                      data-artigo={artigo.id}
                      onClick={(e) => {
                        // Clique simples abre aqui; Ctrl ou botão do meio seguem o link normal.
                        if (e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
                        e.preventDefault();
                        abrir(artigo.id);
                      }}
                    >
                      <span className="ajuda-lista-titulo">{artigo.titulo}</span>
                      <span className="ajuda-lista-resumo">{artigo.resumo}</span>
                    </a>
                  </li>
                ))}
              </ul>
            </nav>
          )}
        </aside>

        <div className="ajuda-conteudo">
          {linkInvalido && !aberto && (
            <p className="status-text error" role="alert">
              Esse artigo não existe ou mudou de lugar. Escolha um da lista ou busque pelo que você quer fazer.
            </p>
          )}
          {aberto ? (
            <ArtigoAberto artigo={aberto} meuTipo={meuTipo} tituloRef={tituloRef} />
          ) : (
            <div className="card ajuda-boas-vindas">
              <h2>Escolha o que você quer fazer</h2>
              <p>
                Cada artigo explica uma tarefa, com os nomes de botão que aparecem na tela. Use a busca ou o botão de ajuda (
                <span className="ajuda-icone-inline" aria-hidden="true">
                  <IconeAjuda size={16} />
                </span>
                ) de cada tela.
              </p>
              <button type="button" className="small" onClick={() => abrir("limites-do-sistema")}>
                Ler o que o sistema não faz
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default AjudaScreen;
