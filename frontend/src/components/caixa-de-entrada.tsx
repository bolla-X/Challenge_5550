import { useCallback, useEffect, useState } from "react";
import { ApiError } from "../api/client";
import {
  excluirContato,
  listarContatos,
  listarFeedback,
  marcarContatoLido,
  marcarFeedbackLido,
  type Caixa,
  type ItemDeContato,
  type ItemDeFeedback,
} from "../api/feedback";
import { dataHoraCurta, paraDate } from "../utils/datas";
import { mensagemDeErro } from "../utils/erros";
import { pluralizar } from "../utils/formato";
import { Badge, EmptyState, PanelSkeleton, Tabs } from "./common";
import { rotuloDaTela } from "./feedback";
import { IlustracaoFila } from "./ilustracoes";
import { ROTULO_DO_PAPEL, ScreenHead } from "./layout";
import "../styles/feedback.css";

/**
 * Caixa de entrada do Supervisor (MISSÃO 4, Fase 3 itens 10 e 11): o que chegou por
 * "Enviar feedback" (contas do app) e pelo formulário da página pública /produto.
 * Tudo vem do servidor local (app/api/feedback.py); marcar como lido grava no banco.
 */

type Filtro = "todos" | "nao-lidos";

// Módulo, não componente: referência estável, para `useCaixa` não recarregar a cada render.
const marcarFeedback = (id: number, lido: boolean) => marcarFeedbackLido(id, lido).then((r) => r.feedback);
const marcarContato = (id: number, lido: boolean) => marcarContatoLido(id, lido).then((r) => r.contato);

/** Uma caixa (feedback ou contatos): lista, filtro e "marcar como lido". Nada de regra de negócio aqui. */
function useCaixa<T extends { id: number; lido: boolean }>(
  carregar: () => Promise<Caixa<T>>,
  marcar: (id: number, lido: boolean) => Promise<T>,
  excluir?: (id: number) => Promise<unknown>,
) {
  const [itens, setItens] = useState<T[] | null>(null);
  const [erro, setErro] = useState<{ mensagem: string; status?: number } | null>(null);
  const [ocupado, setOcupado] = useState<number | null>(null);

  const recarregar = useCallback(() => {
    setErro(null);
    return carregar()
      .then((c) => setItens(c.items))
      .catch((e: unknown) => setErro({ mensagem: mensagemDeErro(e, "Não foi possível ler a caixa de entrada."), status: e instanceof ApiError ? e.status : undefined }));
  }, [carregar]);

  useEffect(() => {
    void recarregar();
  }, [recarregar]);

  const alternar = (item: T) => {
    setOcupado(item.id);
    marcar(item.id, !item.lido)
      .then((novo) => setItens((atuais) => (atuais ?? []).map((i) => (i.id === novo.id ? novo : i))))
      .catch((e: unknown) => setErro({ mensagem: mensagemDeErro(e, "Não foi possível marcar como lido.") }))
      .finally(() => setOcupado(null));
  };
  const apagar = (item: T) => {
    if (!excluir) return;
    setOcupado(item.id);
    excluir(item.id)
      .then(() => setItens((atuais) => (atuais ?? []).filter((i) => i.id !== item.id)))
      .catch((e: unknown) => setErro({ mensagem: mensagemDeErro(e, "Não foi possível excluir o contato.") }))
      .finally(() => setOcupado(null));
  };
  return { itens, erro, ocupado, recarregar, alternar, apagar, naoLidos: (itens ?? []).filter((i) => !i.lido).length };
}

function Quando({ iso }: { iso: string | null }) {
  return <time dateTime={iso ?? undefined}>{dataHoraCurta(paraDate(iso))}</time>;
}

function BotaoLido({ lido, ocupado, aoAlternar }: { lido: boolean; ocupado: boolean; aoAlternar: () => void }) {
  return (
    <button type="button" className="ghost small" disabled={ocupado} onClick={aoAlternar}>
      {lido ? "Marcar como não lido" : "Marcar como lido"}
    </button>
  );
}

function Lista<T extends { id: number; lido: boolean }>({
  itens,
  filtro,
  vazio,
  desenhar,
}: {
  itens: T[];
  filtro: Filtro;
  vazio: string;
  desenhar: (item: T) => JSX.Element;
}) {
  const visiveis = filtro === "nao-lidos" ? itens.filter((i) => !i.lido) : itens;
  if (!visiveis.length) {
    return (
      <EmptyState ilustracao={<IlustracaoFila />} titulo={filtro === "nao-lidos" && itens.length ? "Tudo lido" : "Nenhuma mensagem ainda"}>
        {filtro === "nao-lidos" && itens.length ? "Não há itens não lidos. Mude o filtro para ver os anteriores." : vazio}
      </EmptyState>
    );
  }
  return (
    <ul className="caixa-lista">
      {visiveis.map((item) => (
        <li key={item.id} className={`card caixa-item ${item.lido ? "lido" : "novo"}`} data-lido={item.lido ? "1" : "0"}>
          {desenhar(item)}
        </li>
      ))}
    </ul>
  );
}

function PainelDeFeedback({ caixa, filtro }: { caixa: ReturnType<typeof useCaixa<ItemDeFeedback>>; filtro: Filtro }) {
  if (!caixa.itens) return null;
  return (
    <Lista
      itens={caixa.itens}
      filtro={filtro}
      vazio="Quando alguém usar “Enviar feedback” no menu da barra superior, a mensagem aparece aqui."
      desenhar={(f) => (
        <>
          <header className="caixa-topo">
            <div className="caixa-quem">
              <strong>{f.autor ?? "Conta removida"}</strong>
              <Badge>{ROTULO_DO_PAPEL[f.tipo_de_conta] ?? f.tipo_de_conta}</Badge>
              {!f.lido && <Badge tone="info">Não lido</Badge>}
            </div>
            <span className="caixa-quando">
              {rotuloDaTela(f.tela)} · <Quando iso={f.criado_em} />
            </span>
          </header>
          <p className="caixa-texto">{f.texto}</p>
          <div className="caixa-acoes">
            <BotaoLido lido={f.lido} ocupado={caixa.ocupado === f.id} aoAlternar={() => caixa.alternar(f)} />
          </div>
        </>
      )}
    />
  );
}

function PainelDeContatos({ caixa, filtro }: { caixa: ReturnType<typeof useCaixa<ItemDeContato>>; filtro: Filtro }) {
  if (!caixa.itens) return null;
  return (
    <Lista
      itens={caixa.itens}
      filtro={filtro}
      vazio="Quando alguém preencher o formulário da página do produto, o contato aparece aqui."
      desenhar={(c) => (
        <>
          <header className="caixa-topo">
            <div className="caixa-quem">
              <strong>{c.nome}</strong>
              {c.empresa && <span className="caixa-empresa">{c.empresa}</span>}
              {!c.lido && <Badge tone="info">Não lido</Badge>}
            </div>
            <span className="caixa-quando">
              <Quando iso={c.criado_em} />
            </span>
          </header>
          <p className="caixa-contato">
            <a href={`mailto:${c.email}`}>{c.email}</a>
          </p>
          <p className="caixa-texto">{c.mensagem}</p>
          <div className="caixa-acoes">
            <span className="caixa-consentimento">Aceitou guardarmos os dados para responder o contato.</span>
            <BotaoLido lido={c.lido} ocupado={caixa.ocupado === c.id} aoAlternar={() => caixa.alternar(c)} />
            <button
              type="button"
              className="ghost small"
              disabled={caixa.ocupado === c.id}
              onClick={() => {
                if (window.confirm(`Excluir o contato de ${c.nome}? Nome, e-mail e mensagem somem do sistema e não dá para desfazer.`)) caixa.apagar(c);
              }}
            >
              Excluir
            </button>
          </div>
        </>
      )}
    />
  );
}

export function CaixaDeEntradaScreen() {
  const feedback = useCaixa<ItemDeFeedback>(listarFeedback, marcarFeedback);
  const contatos = useCaixa<ItemDeContato>(listarContatos, marcarContato, excluirContato);
  const [aba, setAba] = useState("feedback");
  const [filtro, setFiltro] = useState<Filtro>("todos");

  const negado = feedback.erro?.status === 403 || contatos.erro?.status === 403;
  if (negado) {
    return (
      <div className="screen">
        <EmptyState titulo="Acesso restrito" acao={<a className="button ghost" href="/">Voltar ao painel</a>}>
          A caixa de entrada é do Supervisor. Peça a quem tem esse tipo de conta.
        </EmptyState>
      </div>
    );
  }

  const falha = feedback.erro ?? contatos.erro;
  const carregando = !feedback.itens && !contatos.itens && !falha;
  const rotulo = (nome: string, n: number) => (n ? `${nome} (${pluralizar(n, "não lido", "não lidos")})` : nome);

  return (
    <div className="screen caixa" data-testid="caixa-de-entrada">
      <ScreenHead
        title="Caixa de entrada"
        sub="Feedback do app e contatos da página do produto"
        actions={
          <>
            <label className="caixa-filtro">
              <span>Mostrar</span>
              <select value={filtro} onChange={(e) => setFiltro(e.target.value as Filtro)}>
                <option value="todos">Todos</option>
                <option value="nao-lidos">Só não lidos</option>
              </select>
            </label>
            <a className="button ghost" href="/">
              Voltar ao painel
            </a>
          </>
        }
      />

      {falha && (
        <div className="caixa-falha" role="alert">
          <p>{falha.mensagem}</p>
          <button
            type="button"
            className="small"
            onClick={() => {
              void feedback.recarregar();
              void contatos.recarregar();
            }}
          >
            Tentar de novo
          </button>
        </div>
      )}

      {carregando ? (
        <div aria-busy="true">
          <PanelSkeleton lines={6} />
        </div>
      ) : (
        <Tabs
          idPrefix="caixa"
          active={aba}
          onChange={setAba}
          tabs={[
            { key: "feedback", label: rotulo("Feedback", feedback.naoLidos), content: <PainelDeFeedback caixa={feedback} filtro={filtro} /> },
            { key: "contatos", label: rotulo("Contatos", contatos.naoLidos), content: <PainelDeContatos caixa={contatos} filtro={filtro} /> },
          ]}
        />
      )}
    </div>
  );
}

export default CaixaDeEntradaScreen;
