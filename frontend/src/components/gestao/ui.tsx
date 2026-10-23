import { useEffect, useRef } from "react";
import type { ReactNode } from "react";
import { pluralizar } from "../../utils/formato";
import { Badge } from "../common";
import { ROTULO_GRAVIDADE, ROTULO_SITUACAO_ENTREGA, ROTULO_STATUS, rotulo } from "./tipos";
import type { Entrega, Epi, SituacaoEntrega } from "./tipos";

/** Peças de tela comuns às abas da Gestão. Classes `gt-*` em styles/gestao.css. */

/**
 * Formulário que abre no meio da tela: ao montar, rola até ele (só o necessário), leva o foco ao primeiro campo e,
 * ao desmontar, devolve o foco a quem estava focado antes (o botão que o abriu). Ponha o `ref` no `<form>`.
 */
export function usarFocoAoAbrir() {
  const ref = useRef<HTMLFormElement>(null);
  useEffect(() => {
    const origem = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const form = ref.current;
    form?.scrollIntoView?.({ block: "nearest" });
    form?.querySelector<HTMLElement>("input:not([type=hidden]), select, textarea")?.focus({ preventScroll: true });
    return () => {
      if (origem && origem !== document.body && origem.isConnected) origem.focus({ preventScroll: true });
    };
  }, []);
  return ref;
}

/** Campo com rótulo ACIMA do controle, ajuda opcional e erro inline logo abaixo (role=alert). */
export function Campo({ id, rotulo: texto, ajuda, erro, children }: { id: string; rotulo: string; ajuda?: string; erro?: string; children: ReactNode }) {
  return (
    <div className="field gt-campo">
      <label htmlFor={id} className="gt-rotulo">
        {texto}
      </label>
      {children}
      {ajuda && (
        <p className="gt-ajuda" id={`${id}-ajuda`}>
          {ajuda}
        </p>
      )}
      {erro && (
        <p className="gt-erro" id={`${id}-erro`} role="alert">
          {erro}
        </p>
      )}
    </div>
  );
}

/** `aria-describedby` do controle de um `Campo`. */
export const descrito = (id: string, ajuda?: string, erro?: string) =>
  [ajuda ? `${id}-ajuda` : null, erro ? `${id}-erro` : null].filter(Boolean).join(" ") || undefined;

export function ErroComRetentativa({ mensagem, aoTentar }: { mensagem: string; aoTentar: () => void }) {
  return (
    <div role="alert" className="gt-erro-bloco">
      <p className="gt-erro">{mensagem}</p>
      <button type="button" className="small" onClick={aoTentar}>
        Tentar de novo
      </button>
    </div>
  );
}

export type Tom = "ok" | "alerta" | "perigo" | "neutro";

/** Selo de situação: o texto sempre acompanha a cor (ok = verde, perigo = laranja cheio, alerta = laranja vazado). */
export function Selo({ tom, children }: { tom: Tom; children: ReactNode }) {
  if (tom === "ok") return <Badge tone="ok">{children}</Badge>;
  if (tom === "perigo") return <Badge tone="error">{children}</Badge>;
  if (tom === "alerta") {
    return (
      <span className="chip gt-alerta">
        <span className="dot" />
        {children}
      </span>
    );
  }
  return <Badge>{children}</Badge>;
}

/** Validade do CA: válido, a vencer em N dias ou vencido. */
export function SeloDoCa({ epi }: { epi: Pick<Epi, "situacao_ca" | "dias_para_vencer"> }) {
  const dias = epi.dias_para_vencer;
  if (epi.situacao_ca === "vencido") {
    return <Selo tom="perigo">{typeof dias === "number" && dias < 0 ? `Vencido há ${pluralizar(-dias, "dia")}` : "Vencido"}</Selo>;
  }
  if (epi.situacao_ca === "a_vencer") {
    return <Selo tom="alerta">{typeof dias === "number" ? `A vencer em ${pluralizar(dias, "dia")}` : "A vencer"}</Selo>;
  }
  return <Selo tom="ok">Válido</Selo>;
}

const TOM_DA_ENTREGA: Record<SituacaoEntrega, Tom> = { vigente: "ok", troca_vencida: "perigo", devolvido: "neutro" };

/** Situação da entrega; EPI ainda em uso com o CA vencido ganha um segundo selo ("CA vencido"). */
export function SeloDaEntrega({ entrega }: { entrega: Pick<Entrega, "situacao" | "epi"> }) {
  const { situacao } = entrega;
  return (
    <>
      <Selo tom={TOM_DA_ENTREGA[situacao] ?? "neutro"}>{rotulo(ROTULO_SITUACAO_ENTREGA, situacao)}</Selo>
      {situacao !== "devolvido" && entrega.epi.situacao_ca === "vencido" && <Selo tom="perigo">CA vencido</Selo>}
    </>
  );
}

const TOM_DA_GRAVIDADE: Record<string, Tom> = { critica: "perigo", alta: "perigo", media: "alerta", baixa: "neutro" };

export const SeloDaGravidade = ({ gravidade }: { gravidade: string }) => (
  <Selo tom={TOM_DA_GRAVIDADE[gravidade] ?? "neutro"}>{rotulo(ROTULO_GRAVIDADE, gravidade)}</Selo>
);

const TOM_DO_STATUS: Record<string, Tom> = { aberta: "alerta", em_tratamento: "neutro", encerrada: "ok" };

export const SeloDoStatus = ({ status }: { status: string }) => <Selo tom={TOM_DO_STATUS[status] ?? "neutro"}>{rotulo(ROTULO_STATUS, status)}</Selo>;
