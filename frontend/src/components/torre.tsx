import { avisarSeSessaoExpirou } from "../api/client";
import { mensagemDeErro } from "../utils/erros";
import { useEffect, useState } from "react";

/**
 * Torre de luz virtual (M2): verde/amarelo/vermelho + sirene visual, refletindo
 * EXATAMENTE o estado que vai para o OPC UA e o MQTT (`/api/integracao/estado`,
 * calculado por app/services/integracao/estado.py). Aparece em `/torre` e no Modo TV.
 */

export type CorDaTorre = "verde" | "amarelo" | "vermelho";
type CameraDaPlanta = {
  id: number;
  nome: string;
  estado: string;
  saude_visual?: string;
  critico_nao_reconhecido?: boolean;
  /** Crítico sem reconhecimento além do prazo da TV (M7): a torre e a TV piscam mais rápido. */
  escalonado?: boolean;
};
type Integracao = { ativo?: boolean; estado?: string; endpoint?: string | null; erro?: string | null };
export type EstadoDaIntegracao = {
  planta: { planta_em_alarme: boolean; torre: CorDaTorre; sirene: boolean; cameras: CameraDaPlanta[]; ts: string };
  integracoes: Record<string, Integracao>;
};

const TEXTO: Record<CorDaTorre, string> = {
  verde: "Tudo em ordem",
  amarelo: "Atenção",
  vermelho: "Alarme",
};
const NOME_DA_INTEGRACAO: Record<string, string> = { opcua: "OPC UA", mqtt: "MQTT", broker: "Broker MQTT embutido", webhook: "Webhook" };
const ESTADO_DA_INTEGRACAO: Record<string, string> = {
  no_ar: "no ar",
  conectado: "conectado",
  desligado: "desligado",
  falhou: "falhou",
  desconectado: "desconectado",
  reconectando: "reconectando",
};

export function useEstadoDaIntegracao(intervaloMs = 2000) {
  const [estado, setEstado] = useState<EstadoDaIntegracao | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  useEffect(() => {
    let vivo = true;
    const tick = () =>
      fetch("/api/integracao/estado", { credentials: "same-origin" })
        .then(async (r) => {
          avisarSeSessaoExpirou("/api/integracao/estado", r.status);
          if (!r.ok) throw new Error(r.status === 401 ? "Sessão encerrada. Entre de novo." : `Falha ao ler o estado da planta (código ${r.status}).`);
          return (await r.json()) as EstadoDaIntegracao;
        })
        .then((d) => {
          if (!vivo) return;
          setEstado(d);
          setErro(null);
        })
        .catch((e) => vivo && setErro(mensagemDeErro(e, "Falha ao ler o estado da planta.")));
    tick();
    const id = window.setInterval(tick, intervaloMs);
    return () => {
      vivo = false;
      window.clearInterval(id);
    };
  }, [intervaloMs]);
  return { estado, erro };
}

/** Alguma câmera com crítico sem reconhecimento além do prazo da TV (escalonamento nível 2, M7). */
export function plantaEscalonada(planta: EstadoDaIntegracao["planta"]): boolean {
  return planta.cameras.some((c) => c.escalonado === true);
}

export function Torre({ cor, sirene, escalonado = false, compacta = false }: { cor: CorDaTorre; sirene: boolean; escalonado?: boolean; compacta?: boolean }) {
  const sufixo = escalonado ? ", escalonado: sem reconhecimento além do prazo" : "";
  if (compacta) {
    return (
      <span className="torre-mini" data-testid="torre-mini" data-cor={cor} aria-label={`Torre de luz: ${TEXTO[cor]}${sufixo}`}>
        <span className={`torre-lampada ${cor} acesa`} aria-hidden="true" />
        {TEXTO[cor]}
      </span>
    );
  }
  return (
    <div className={`torre ${sirene ? "sirene" : ""} ${escalonado ? "escalonado" : ""}`.trim()} data-testid="torre" data-cor={cor}
         data-sirene={sirene ? "1" : "0"} data-escalonado={escalonado ? "1" : "0"}
         role="img" aria-label={`Torre de luz: ${TEXTO[cor]}${sirene ? ", sirene ligada" : ""}${sufixo}`}>
      <div className="torre-corpo">
        {(["vermelho", "amarelo", "verde"] as CorDaTorre[]).map((c) => (
          <span key={c} className={`torre-lampada ${c} ${c === cor ? "acesa" : ""}`} />
        ))}
      </div>
      <div className="torre-base" />
    </div>
  );
}

/** Por que a torre está assim: as câmeras fora de "ok", ou a frase de tudo em ordem. */
export function motivoDaTorre(estado: EstadoDaIntegracao["planta"]): string {
  const problemas = estado.cameras.filter((c) => c.estado !== "ok");
  if (!problemas.length) return "Nenhum incidente ativo e todas as câmeras com imagem.";
  return problemas
    .slice(0, 4)
    .map((c) => `${c.nome}: ${c.saude_visual && c.saude_visual !== "ok" ? `câmera ${c.saude_visual}` : c.estado === "offline" ? "sem sinal" : c.estado === "alarme" ? "alarme" : "atenção"}`)
    .join(" · ");
}

/** O que a torre diz em palavras: "Tudo em ordem", "Alarme — alerta crítico sem reconhecimento"... */
export function textoDaTorre(planta: EstadoDaIntegracao["planta"]): string {
  const escalonado = plantaEscalonada(planta);
  return `${TEXTO[planta.torre]}${planta.sirene ? " — alerta crítico sem reconhecimento" : ""}${escalonado ? " há muito tempo: supervisão avisada" : ""}`;
}

/** Uma pílula por integração (OPC UA, MQTT, broker, webhook), com o estado que o servidor informa. */
export function IntegracoesDaPlanta({ integracoes }: { integracoes: EstadoDaIntegracao["integracoes"] }) {
  return (
    <div className="torre-integracoes" aria-label="Integrações industriais">
      {Object.entries(integracoes).map(([nome, i]) => (
        <span key={nome} className={`chip ${i.estado === "falhou" ? "miss" : i.estado === "no_ar" || i.estado === "conectado" ? "ok" : ""}`}
              title={i.erro || i.endpoint || undefined} data-integracao={nome} data-estado={i.estado ?? "desligado"}>
          {(i.estado === "no_ar" || i.estado === "conectado") && <span className="dot" />}
          {NOME_DA_INTEGRACAO[nome] ?? nome}: {ESTADO_DA_INTEGRACAO[i.estado ?? "desligado"] ?? i.estado}
        </span>
      ))}
    </div>
  );
}

export function TorreScreen() {
  const { estado, erro } = useEstadoDaIntegracao();
  const escalonado = estado ? plantaEscalonada(estado.planta) : false;
  return (
    <div className="torre-tela" data-testid="torre-tela">
      {estado ? (
        <>
          <Torre cor={estado.planta.torre} sirene={estado.planta.sirene} escalonado={escalonado} />
          <div>
            <p className="torre-estado" aria-live="polite">
              {textoDaTorre(estado.planta)}
            </p>
            <p className="torre-detalhe">{motivoDaTorre(estado.planta)}</p>
          </div>
          <IntegracoesDaPlanta integracoes={estado.integracoes} />
        </>
      ) : (
        <p role={erro ? "alert" : "status"}>{erro ?? "Lendo o estado da planta…"}</p>
      )}
    </div>
  );
}

export default TorreScreen;
