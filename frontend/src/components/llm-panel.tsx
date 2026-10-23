import { useEffect, useState } from "react";
import { Panel } from "./common";
import { getCameraStatus } from "../api/endpoints";
import { PPE_LABELS } from "../api/ppe";
import { pluralizar } from "../utils/formato";

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
  /** "demonstracao": resposta fixa do modo demonstração, sem GEMINI_API_KEY (app/llm). */
  modo?: "real" | "demonstracao";
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
  const demonstracao = llm?.modo === "demonstracao";

  return (
    <Panel
      id="panel-llm"
      title="Segunda opinião (LLM multimodal)"
      description="Um modelo de linguagem com visão revisa o quadro quando um alerta nasce. Ele informa, não decide: nunca cria nem apaga alertas."
    >
      {!llm?.habilitado ? (
        <p className="empty-state">
          Segunda opinião desligada. Quem administra o sistema pode ligá-la (a página Status do sistema explica como).
        </p>
      ) : (
        <>
          <div className="actions">
            {llm.modo === "demonstracao" ? (
              <span className="chip" data-testid="llm-modo-demonstracao">
                Modo demonstração · resposta fixa, sem chave do Gemini
              </span>
            ) : (
              <span className="chip ok">
                <span className="dot" />
                Ligada · instruções {llm.versao_prompt}
              </span>
            )}
            <span className="chip">{demonstracao ? pluralizar(llm.aceitos ?? 0, "resposta fixa", "respostas fixas") : pluralizar(llm.aceitos ?? 0, "análise")}</span>
            {(llm.em_voo?.length ?? 0) > 0 && <span className="chip">analisando…</span>}
            {(llm.invalidos ?? 0) > 0 && (
              <span className="chip miss">
                {pluralizar(llm.invalidos ?? 0, "resposta inválida", "respostas inválidas")} {llm.invalidos === 1 ? "descartada" : "descartadas"}
              </span>
            )}
          </div>
          {ultima && demonstracao ? (
            // Resposta fixa: nada de risco nem confiança, que pareceriam uma análise da imagem que não aconteceu.
            <p className="empty-state" data-testid="llm-exemplo-fixo">
              Exemplo de resposta (fixa). A imagem não foi analisada por um LLM. Com GEMINI_API_KEY no terminal antes de <code>run.py --demo</code>, aqui aparece a análise real.
            </p>
          ) : ultima ? (
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
