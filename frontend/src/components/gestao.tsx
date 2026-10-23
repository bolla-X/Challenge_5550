import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { useDashboardStore } from "../store/dashboardStore";
import { ThemeToggle } from "./layout";
import { AbaCatalogo } from "./gestao/catalogo";
import { AbaColaboradores } from "./gestao/colaboradores";
import { AbaEntregas } from "./gestao/entregas";
import { AbaOcorrencias } from "./gestao/ocorrencias";
import { AbaRelatorios } from "./gestao/relatorios";
import type { Resumo } from "./gestao/tipos";
import { usarRecurso } from "./gestao/usar-recurso";
import "../styles/gestao.css";

/**
 * Gestão de EPIs (`/gestao`): colaboradores com histórico de EPIs, catálogo com CA, entregas, ocorrências e
 * exportação. Cadastro administrativo: nada aqui é ligado às câmeras nem a imagens. Contrato da API:
 * docs/specs/es-sprint4-contrato-gestao.md. Cada aba busca os próprios dados; o resumo do topo é recarregado
 * quando uma aba grava algo (`aoMudar`).
 */

const ABAS = [
  { chave: "colaboradores", rotulo: "Colaboradores" },
  { chave: "catalogo", rotulo: "Catálogo de EPIs" },
  { chave: "entregas", rotulo: "Entregas" },
  { chave: "ocorrencias", rotulo: "Ocorrências" },
  { chave: "relatorios", rotulo: "Relatórios e exportação" },
] as const;
type Aba = (typeof ABAS)[number]["chave"];

/** `/gestao?aba=entregas` abre direto na aba; valor desconhecido cai na primeira. */
function abaInicial(): Aba {
  const pedida = new URLSearchParams(window.location.search).get("aba");
  return ABAS.find((a) => a.chave === pedida)?.chave ?? "colaboradores";
}

export default function GestaoScreen() {
  const papel = useDashboardStore((s) => s.user?.role);
  const ehSupervisor = papel === "supervisor"; // sem papel conhecido, a tela não oferece o que só o Supervisor faz (o servidor decide)
  const [aba, setAba] = useState<Aba>(abaInicial);
  const resumo = usarRecurso<Resumo>("/api/gestao/resumo", "Não foi possível carregar o resumo.");
  const listaRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const url = new URL(window.location.href);
    url.searchParams.set("aba", aba);
    window.history.replaceState(null, "", url);
  }, [aba]);

  const teclado = (e: KeyboardEvent) => {
    const atual = ABAS.findIndex((a) => a.chave === aba);
    let proxima = atual;
    if (e.key === "ArrowRight") proxima = (atual + 1) % ABAS.length;
    else if (e.key === "ArrowLeft") proxima = (atual - 1 + ABAS.length) % ABAS.length;
    else if (e.key === "Home") proxima = 0;
    else if (e.key === "End") proxima = ABAS.length - 1;
    else return;
    e.preventDefault();
    setAba(ABAS[proxima].chave);
    listaRef.current?.querySelectorAll<HTMLButtonElement>('[role="tab"]')[proxima]?.focus();
  };

  return (
    <div className="gt-tela" data-testid="gestao">
      <header className="gt-cabeca">
        <div>
          <h1>Gestão de EPIs</h1>
          <p className="gt-ajuda">Colaboradores, catálogo com CA, entregas e ocorrências de segurança, em um lugar só.</p>
          <p className="gt-ajuda gt-privacidade" data-testid="gestao-privacidade">
            Cadastro administrativo: nenhum colaborador é ligado a câmeras, imagens ou números de rastreio.
          </p>
          {resumo.dados?.simulados && (
            <p className="gt-ajuda gt-simulados">
              <span className="chip gt-simulado" data-testid="gestao-simulados">
                Dados simulados
              </span>
              <span>Dados simulados: nomes, fabricantes e CAs fictícios, criados para a demonstração.</span>
            </p>
          )}
        </div>
        <div className="gt-cabeca-acoes">
          <ThemeToggle />
          <a className="button ghost" href="/">
            Voltar ao painel
          </a>
        </div>
      </header>

      <div className="gt-abas" role="tablist" aria-label="Seções da Gestão de EPIs" ref={listaRef} onKeyDown={teclado}>
        {ABAS.map((a) => (
          <button
            key={a.chave}
            type="button"
            role="tab"
            id={`gestao-tab-${a.chave}`}
            aria-selected={a.chave === aba}
            aria-controls={`gestao-painel-${a.chave}`}
            tabIndex={a.chave === aba ? 0 : -1}
            className={`gt-aba-botao ${a.chave === aba ? "ativa" : ""}`.trim()}
            data-testid={`gestao-aba-${a.chave}`}
            onClick={() => setAba(a.chave)}
          >
            {a.rotulo}
          </button>
        ))}
      </div>

      <div role="tabpanel" id={`gestao-painel-${aba}`} aria-labelledby={`gestao-tab-${aba}`} className="gt-painel-da-aba">
        {aba === "colaboradores" && <AbaColaboradores ehSupervisor={ehSupervisor} aoMudar={resumo.recarregar} />}
        {aba === "catalogo" && <AbaCatalogo ehSupervisor={ehSupervisor} aoMudar={resumo.recarregar} />}
        {aba === "entregas" && <AbaEntregas aoMudar={resumo.recarregar} />}
        {aba === "ocorrencias" && <AbaOcorrencias aoMudar={resumo.recarregar} />}
        {aba === "relatorios" && <AbaRelatorios resumo={resumo.dados} carregando={resumo.carregando} erro={resumo.erro} aoTentar={resumo.recarregar} />}
      </div>
    </div>
  );
}
