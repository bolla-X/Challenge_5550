import { useDashboardStore } from "../store/dashboardStore";
import { FEATURE_ORDER, PPE_DESCRIPTIONS, PPE_KEYS, isPpeKey } from "../api/ppe";
import { Panel } from "./common";
import type { ComplianceState, FeatureFlag } from "../api/types";

// Perfis derivados das chaves canônicas.
const ppeAll = (value: boolean) => Object.fromEntries(PPE_KEYS.map((key) => [key, value]));
const FEATURE_PROFILES: Record<string, Record<string, boolean>> = {
  basic: { ppe: false, ...ppeAll(false), pose: true, falls: true, posture: true, risk_area: false },
  epi: { ppe: true, ...ppeAll(true), pose: true, falls: false, posture: false, risk_area: false },
  risk: { ppe: false, ...ppeAll(false), pose: true, falls: true, posture: true, risk_area: true },
  full: { ppe: true, ...ppeAll(true), pose: true, falls: true, posture: true, risk_area: true },
};
const PROFILE_TITLES: Record<string, string> = { basic: "Básico", epi: "EPI", risk: "Risco", full: "Completo" };

const SHORT_DESCRIPTION: Record<string, string> = {
  ppe: "Grupo de EPI",
  ...PPE_DESCRIPTIONS,
  pose: "Pontos corporais",
  falls: "Pessoa caída",
  posture: "Postura suspeita",
  risk_area: "Zona configurável",
};

const OVERLAY_LABELS: Record<string, string> = {
  boxes: "Bounding boxes",
  labels: "Labels",
  confidence: "Confiança",
  pose: "Pontos de pose",
  risk_area: "Zona de risco",
};

// "Vivo" = aparece no frame atual (ou dispara alerta, no caso de falls/
// posture, que não têm detecção própria). Ligado-mas-parado é texto normal.
// ponytail: falls/posture não têm payload de detecção dedicado, então a
// leitura é via o alerta ativo de pose. Se o backend ganhar um campo próprio
// de detecção por sub-feature, trocar por isso.
function isFeatureLive(key: string, compliance: ComplianceState | null): boolean {
  if (!compliance) return false;
  switch (key) {
    case "helmet":
    case "vest":
    case "gloves":
      return (compliance.ppe[key]?.detections.length ?? 0) > 0;
    case "ppe":
      return PPE_KEYS.some((k) => (compliance.ppe[k]?.detections.length ?? 0) > 0);
    case "pose":
      return compliance.pose ? !["disabled", "waiting"].includes(compliance.pose.status) : false;
    case "falls":
    case "posture":
      return compliance.pose?.active_alert?.feature === key;
    case "risk_area":
      return Boolean(compliance.risk_area && !["disabled"].includes(compliance.risk_area.status) && compliance.risk_area.active_alert);
    default:
      return false;
  }
}

function supportMessage(key: string, model: ReturnType<typeof useDashboardStore.getState>["model"]): string {
  if (!model) return "aguardando diagnóstico";
  const supported = model.supported_ppe || ({} as Record<string, boolean>);
  if (isPpeKey(key) && !supported[key]) return "indisponível no modelo atual";
  if (key === "ppe" && !model.ppe_ready) return "aguardando modelo PPE completo";
  if (["pose", "falls", "posture"].includes(key)) return "via MediaPipe";
  if (key === "risk_area") return "zona + YOLO pessoa";
  return "disponível";
}

/** Um recurso na sidebar: nome, descrição curta e o estado em texto. O ponto
 * só acende quando o item está aparecendo no frame agora. */
function FeatureRow({ feature }: { feature: FeatureFlag }) {
  const model = useDashboardStore((s) => s.model);
  const compliance = useDashboardStore((s) => s.compliance);
  const updateFeatures = useDashboardStore((s) => s.updateFeatures);
  const checked = feature.enabled;
  const live = checked && isFeatureLive(feature.key, compliance);
  return (
    <button
      type="button"
      className={`side-item ${checked ? "current" : ""} ${live ? "live" : ""}`.trim()}
      aria-pressed={checked}
      onClick={() => updateFeatures({ [feature.key]: !checked }).catch(console.error)}
    >
      <span className="dot" />
      <span className="side-item-body">
        {feature.label}
        <small>
          {SHORT_DESCRIPTION[feature.key] || feature.description} · {supportMessage(feature.key, model)}
        </small>
      </span>
      <span className="side-item-state">{checked ? "Ligado" : "Desligado"}</span>
    </button>
  );
}

/** Grupos de perfis e recursos da sidebar. Sempre com rótulo visível. */
export function FeatureGroups() {
  const features = useDashboardStore((s) => s.features);
  const updateFeatures = useDashboardStore((s) => s.updateFeatures);
  const sorted = [...features].sort((a, b) => FEATURE_ORDER.indexOf(a.key) - FEATURE_ORDER.indexOf(b.key));

  return (
    <>
      <div className="sidebar-group">
        <h2>Perfis</h2>
        <div className="side-profiles">
          {(["basic", "epi", "risk", "full"] as const).map((profile) => (
            <button key={profile} type="button" className="small" onClick={() => updateFeatures(FEATURE_PROFILES[profile]).catch(console.error)}>
              {PROFILE_TITLES[profile]}
            </button>
          ))}
        </div>
      </div>
      <div className="sidebar-group">
        <h2>Recursos</h2>
        {sorted.map((feature) => (
          <FeatureRow key={feature.key} feature={feature} />
        ))}
      </div>
    </>
  );
}

export function OverlayControls() {
  const overlay = useDashboardStore((s) => s.overlay);
  const updateOverlay = useDashboardStore((s) => s.updateOverlay);
  if (!overlay) return null;
  return (
    <Panel id="panel-overlay" title="Overlay do vídeo" description="Controle o que aparece dentro do frame sem misturar dados operacionais.">
      <div className="features">
        {Object.entries(OVERLAY_LABELS).map(([key, label]) => (
          <label className="feature-item" key={key}>
            <span className="switch">
              <input
                type="checkbox"
                checked={overlay[key as keyof typeof overlay] !== false}
                onChange={(e) => updateOverlay({ [key]: e.target.checked }).catch(console.error)}
              />
              <span className="switch-track">
                <span className="switch-thumb" />
              </span>
            </span>
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
