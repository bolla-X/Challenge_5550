import { useDashboardStore } from "../store/dashboardStore";
import { Panel } from "./common";
import type { FeatureFlag } from "../api/types";

const FEATURE_ORDER = ["ppe", "helmet", "vest", "gloves", "pose", "falls", "posture", "risk_area"];

const FEATURE_PROFILES: Record<string, Record<string, boolean>> = {
  basic: { ppe: false, helmet: false, vest: false, gloves: false, pose: true, falls: true, posture: true, risk_area: false },
  epi: { ppe: true, helmet: true, vest: true, gloves: true, pose: true, falls: false, posture: false, risk_area: false },
  risk: { ppe: false, helmet: false, vest: false, gloves: false, pose: true, falls: true, posture: true, risk_area: true },
  full: { ppe: true, helmet: true, vest: true, gloves: true, pose: true, falls: true, posture: true, risk_area: true },
};

const SHORT_DESCRIPTION: Record<string, string> = {
  ppe: "Grupo de EPI",
  helmet: "Proteção da cabeça",
  vest: "Proteção visual",
  gloves: "Proteção das mãos",
  pose: "Pontos corporais",
  falls: "Pessoa caída",
  posture: "Postura suspeita",
  risk_area: "Zona configurável",
};

const FEATURE_ICONS: Record<string, string> = {
  ppe: "M4 12a8 8 0 0 1 16 0v2h1v3H3v-3h1v-2Zm3 2h10v-2a5 5 0 0 0-10 0v2Z",
  helmet: "M5 13a7 7 0 0 1 14 0v1h2v3H3v-3h2v-1Zm3 1h8v-1a4 4 0 0 0-8 0v1Z",
  vest: "M8 3h3l1 3 1-3h3l4 5-2 3v10H6V11L4 8l4-5Zm1 8v7h2v-7H9Zm4 0v7h2v-7h-2Z",
  gloves: "M7 3a2 2 0 0 1 2 2v5h1V4a2 2 0 0 1 4 0v6h1V6a2 2 0 0 1 4 0v7c0 5-3 8-7 8s-7-3-7-8V5a2 2 0 0 1 2-2Z",
  pose: "M12 5a3 3 0 1 0 0-1 3 3 0 0 0 0 1Zm-5 6 4-2h2l4 2v3l-3-1v8h-4v-8l-3 1v-3Z",
  falls: "M7 6a3 3 0 1 1 6 0 3 3 0 0 1-6 0Zm1 8 4-4 3 3 5 1-1 3-5-1-4 4-6-1 1-3 3-2Z",
  posture: "M12 4a3 3 0 1 1 0 6 3 3 0 0 1 0-6Zm-2 8h4l3 8h-3l-2-5-2 5H7l3-8Z",
  risk_area: "M12 3 2 21h20L12 3Zm1 14h-2v2h2v-2Zm0-7h-2v5h2v-5Z",
};

const OVERLAY_LABELS: Record<string, string> = {
  boxes: "Bounding boxes",
  labels: "Labels",
  confidence: "Confiança",
  pose: "Pontos de pose",
  risk_area: "Zona de risco",
};

function supportMessage(key: string, model: ReturnType<typeof useDashboardStore.getState>["model"]): string {
  if (!model) return "Aguardando diagnóstico";
  const supported = model.supported_ppe || ({} as Record<string, boolean>);
  if (["helmet", "vest", "gloves"].includes(key) && !supported[key as keyof typeof supported]) {
    return "Indisponível no modelo YOLO atual";
  }
  if (key === "ppe" && !model.ppe_ready) return "Ativo, mas aguardando modelo PPE completo";
  if (["pose", "falls", "posture"].includes(key)) return "Disponível via MediaPipe";
  if (key === "risk_area") return "Disponível por zona configurável + YOLO pessoa";
  return "Disponível";
}

function FeatureCard({ feature }: { feature: FeatureFlag }) {
  const model = useDashboardStore((s) => s.model);
  const updateFeatures = useDashboardStore((s) => s.updateFeatures);
  const checked = feature.enabled;
  return (
    <label className={`feature-card ${checked ? "enabled" : "off"}`}>
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => updateFeatures({ [feature.key]: e.target.checked }).catch(console.error)}
        aria-label={feature.label}
      />
      <span className="feature-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24">
          <path d={FEATURE_ICONS[feature.key] || "M4 4h16v16H4z"} />
        </svg>
      </span>
      <span className="feature-copy">
        <strong>{feature.label}</strong>
        <small>{SHORT_DESCRIPTION[feature.key] || feature.description}</small>
        <em>{supportMessage(feature.key, model)}</em>
      </span>
      <span className="feature-state">{checked ? "Ativo" : "Inativo"}</span>
    </label>
  );
}

export function FeatureStrip() {
  const features = useDashboardStore((s) => s.features);
  const updateFeatures = useDashboardStore((s) => s.updateFeatures);
  const sorted = [...features].sort((a, b) => FEATURE_ORDER.indexOf(a.key) - FEATURE_ORDER.indexOf(b.key));
  return (
    <Panel
      title="Features analisadas"
      description="Ativa ou desativa o que o backend processa em tempo real."
      className="feature-strip-panel"
      action={
        <div className="profile-row">
          {(["basic", "epi", "risk", "full"] as const).map((profile) => (
            <button
              key={profile}
              className="profile-btn small"
              type="button"
              onClick={() => updateFeatures(FEATURE_PROFILES[profile]).catch(console.error)}
            >
              {{ basic: "Básico", epi: "EPI", risk: "Risco", full: "Completo" }[profile]}
            </button>
          ))}
        </div>
      }
    >
      <div className="features horizontal">
        {sorted.map((feature) => (
          <FeatureCard key={feature.key} feature={feature} />
        ))}
      </div>
    </Panel>
  );
}

export function OverlayControls() {
  const overlay = useDashboardStore((s) => s.overlay);
  const updateOverlay = useDashboardStore((s) => s.updateOverlay);
  if (!overlay) return null;
  return (
    <Panel title="Overlay do vídeo" description="Controle o que aparece dentro do frame sem misturar dados operacionais." className="technical-only">
      <div className="features compact">
        {Object.entries(OVERLAY_LABELS).map(([key, label]) => (
          <label className="feature-item" key={key}>
            <input
              type="checkbox"
              checked={overlay[key as keyof typeof overlay] !== false}
              onChange={(e) => updateOverlay({ [key]: e.target.checked }).catch(console.error)}
            />
            <span>
              <strong>{label}</strong>
              <small>Controle visual dentro do vídeo</small>
            </span>
          </label>
        ))}
      </div>
    </Panel>
  );
}
