import { useState } from "react";
import { useDashboardStore } from "../store/dashboardStore";
import { Panel } from "./common";

// O antigo <VideoCard/> (vídeo da câmera padrão legada com o canvas do editor
// de zona por cima) não era montado por tela nenhuma desde a integração
// multi-câmera; saiu como código morto. O editor abaixo continua igual.

export function RiskAreaEditorPanel() {
  const { riskArea, riskEditorActive, riskEditorPoints, toggleRiskEditor, clearRiskEditorPoints, resetRiskEditorFromServer, updateRiskArea, showMessage } =
    useDashboardStore();
  const [saving, setSaving] = useState(false);

  const save = async () => {
    if (riskEditorPoints.length < 3) {
      showMessage("Área de risco precisa de pelo menos 3 pontos.", "warning");
      return;
    }
    setSaving(true);
    try {
      await updateRiskArea({ name: riskArea?.name || "Área de risco", polygon: riskEditorPoints });
    } catch {
      // mensagem já emitida pela ação do store
    } finally {
      setSaving(false);
    }
  };

  const statusText = riskArea
    ? `${riskArea.name}, ${riskEditorPoints.length} ponto(s), modo ${riskEditorActive ? "edição" : "visualização"}`
    : "Área atual não carregada.";

  return (
    <Panel id="panel-risk-area" title="Editor de área de risco" description="Clique no vídeo (com o monitoramento ativo) para criar pontos normalizados.">
      <div className="actions">
        <button className="small" type="button" onClick={toggleRiskEditor}>
          {riskEditorActive ? "Encerrar edição" : "Editar no vídeo"}
        </button>
        <button className="ghost small" type="button" onClick={clearRiskEditorPoints}>
          Limpar pontos
        </button>
        <button className="ghost small" type="button" onClick={resetRiskEditorFromServer}>
          Recarregar
        </button>
        <button className={`primary small ${saving ? "is-pending" : ""}`.trim()} type="button" disabled={saving} onClick={() => save().catch(console.error)}>
          {saving ? "Salvando…" : "Salvar zona"}
        </button>
      </div>
      <p className="status-text t-data">{statusText}</p>
    </Panel>
  );
}
