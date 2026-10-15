import { useEffect, useState } from "react";
import { Panel } from "./common";
import { getCameraStatus } from "../api/endpoints";
import { PPE_LABELS } from "../api/ppe";

interface AnaliseLlm {
  nivel_risco: "baixo" | "medio" | "alto" | "critico";
  epis_ausentes: string[];
  justificativa: string;
  confianca: number;
  acao_recomendada: string;
}

interface EstadoLlm {
  habilitado: boolean;
  motivo?: string;
  versao_prompt?: string;
  aceitos?: number;
  descartados_em_voo?: number;
  descartados_debounce?: number;
  invalidos?: number;
  em_voo?: number[];
  ultima?: AnaliseLlm | null;
}

const NIVEL: Record<string, string> = { baixo: "Baixo", medio: "Médio", alto: "Alto", critico: "Crítico" };

/**
 * Segunda opinião do LLM multimodal (Sprint 3). Só INFORMA: nunca cria, resolve
 * nem apaga alerta. Quem decide é o operador; o texto vem de um modelo de
 * linguagem e pode errar.
 */
export function LlmPanel({ camId }: { camId: number }) {
  const [llm, setLlm] = useState<EstadoLlm | null>(null);

  useEffect(() => {
    let cancelado = false;
    const tick = () =>
      getCameraStatus(camId)
        .then((s) => {
          if (!cancelado) setLlm(((s as unknown as { llm?: EstadoLlm }).llm ?? null) as EstadoLlm | null);
        })
        .catch(() => undefined);
    tick();
    const timer = setInterval(tick, 3000);
    return () => {
      cancelado = true;
      clearInterval(timer);
    };
  }, [camId]);

  const ultima = llm?.ultima ?? null;

  return (
    <Panel
      id="panel-llm"
      title="Segunda opinião (LLM multimodal)"
      description="Um modelo de linguagem com visão revisa o quadro quando um alerta nasce. Ele informa, não decide: nunca cria nem apaga alertas."
    >
      {!llm?.habilitado ? (
        <p className="empty-state">
          Camada desligada. {llm?.motivo ? `Motivo: ${llm.motivo}.` : ""} Ligue com LLM_ENABLED=true e GEMINI_API_KEY no arquivo .env.
        </p>
      ) : (
        <>
          <div className="actions">
            <span className="chip ok">
              <span className="dot" />
              Ligada · prompt {llm.versao_prompt}
            </span>
            <span className="chip">{llm.aceitos ?? 0} análise(s)</span>
            {(llm.em_voo?.length ?? 0) > 0 && <span className="chip">analisando…</span>}
            {(llm.invalidos ?? 0) > 0 && <span className="chip miss">{llm.invalidos} resposta(s) inválida(s) descartada(s)</span>}
          </div>
          {ultima ? (
            <div className="alert-list">
              <div className={`alert-row ${ultima.nivel_risco === "critico" || ultima.nivel_risco === "alto" ? "critical" : "medium"}`}>
                <span className="dot" />
                <div className="alert-row-body">
                  <strong>
                    Risco {NIVEL[ultima.nivel_risco] ?? ultima.nivel_risco} · confiança {Math.round(ultima.confianca * 100)}%
                  </strong>
                  <div className="alert-row-meta">{ultima.justificativa}</div>
                  <div className="alert-row-meta">
                    EPIs ausentes segundo o LLM:{" "}
                    {ultima.epis_ausentes.length
                      ? ultima.epis_ausentes.map((k) => PPE_LABELS[k as keyof typeof PPE_LABELS] ?? k).join(", ")
                      : "nenhum confirmado"}
                  </div>
                  <div className="alert-row-meta">
                    <b>Ação sugerida:</b> {ultima.acao_recomendada}
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <p className="empty-state">Nenhuma análise ainda. Ela acontece quando um alerta novo é criado nesta câmera.</p>
          )}
        </>
      )}
    </Panel>
  );
}
