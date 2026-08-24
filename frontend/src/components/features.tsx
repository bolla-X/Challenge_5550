import { useDashboardStore } from "../store/dashboardStore";
import { FEATURE_ORDER, PPE_DESCRIPTIONS, PPE_KEYS, isPpeKey } from "../api/ppe";
import { Panel } from "./common";
import type { ComplianceState, FeatureFlag } from "../api/types";

// Perfis derivados das chaves canônicas — antes cada perfil listava as chaves
// de EPI à mão, então adicionar uma classe nova exigia editar os quatro.
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

// Only universally-recognizable icons are used (helmet/vest/gloves/warning
// triangle). Postura and Quedas have no obvious symbol, so they get a plain
// neutral dot instead of an invented icon — the label carries the meaning.
const FEATURE_ICONS: Record<string, string | null> = {
  ppe: "M4 12a8 8 0 0 1 16 0v2h1v3H3v-3h1v-2Zm3 2h10v-2a5 5 0 0 0-10 0v2Z",
  helmet: "M5 13a7 7 0 0 1 14 0v1h2v3H3v-3h2v-1Zm3 1h8v-1a4 4 0 0 0-8 0v1Z",
  vest: "M8 3h3l1 3 1-3h3l4 5-2 3v10H6V11L4 8l4-5Zm1 8v7h2v-7H9Zm4 0v7h2v-7h-2Z",
  gloves: "M7 3a2 2 0 0 1 2 2v5h1V4a2 2 0 0 1 4 0v6h1V6a2 2 0 0 1 4 0v7c0 5-3 8-7 8s-7-3-7-8V5a2 2 0 0 1 2-2Z",
  pose: null,
  falls: null,
  posture: null,
  risk_area: "M12 3 2 21h20L12 3Zm1 14h-2v2h2v-2Zm0-7h-2v5h2v-5Z",
};

const OVERLAY_LABELS: Record<string, string> = {
  boxes: "Bounding boxes",
  labels: "Labels",
  confidence: "Confiança",
  pose: "Pontos de pose",
  risk_area: "Zona de risco",
};

// ciano = dado vivo agora, não "feature ligada". Ligada-mas-parada é texto
// normal; só quando o item aparece no frame atual (ou dispara alerta, no
// caso de falls/posture que não têm detecção própria) é que acende.
// ponytail: falls/posture não têm payload de detecção dedicado, então a
// leitura é via o alerta ativo de pose — se o backend ganhar um campo
// próprio de detecção por sub-feature, trocar por isso.
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

function NavRow({ feature }: { feature: FeatureFlag }) {
  const model = useDashboardStore((s) => s.model);
  const compliance = useDashboardStore((s) => s.compliance);
  const updateFeatures = useDashboardStore((s) => s.updateFeatures);
  const checked = feature.enabled;
  const live = checked && isFeatureLive(feature.key, compliance);
  const iconPath = FEATURE_ICONS[feature.key];
  return (
    <button
      type="button"
      className={`nav-row ${checked ? "on" : ""} ${live ? "live" : ""}`.trim()}
      onClick={() => updateFeatures({ [feature.key]: !checked }).catch(console.error)}
    >
      <span className={`nav-row-icon ${iconPath ? "" : "dot"}`.trim()}>
        {iconPath && (
          <svg viewBox="0 0 24 24">
            <path d={iconPath} />
          </svg>
        )}
      </span>
      <span className="nav-row-body">
        <strong>{feature.label}</strong>
        <small>{SHORT_DESCRIPTION[feature.key] || feature.description} · {supportMessage(feature.key, model)}</small>
      </span>
      <span className="nav-row-state">
        <span className="nav-row-live-dot" />
        {checked ? "on" : "off"}
      </span>
    </button>
  );
}

/** Persistent, always-labeled sidebar. No icon-only affordance anywhere —
 * every row carries a visible label + short status text. */
export function Sidebar() {
  const features = useDashboardStore((s) => s.features);
  const updateFeatures = useDashboardStore((s) => s.updateFeatures);
  const sorted = [...features].sort((a, b) => FEATURE_ORDER.indexOf(a.key) - FEATURE_ORDER.indexOf(b.key));

  return (
    <nav className="sidebar" aria-label="Features e perfis">
      <div className="sidebar-group">
        <div className="sidebar-group-label">Perfis</div>
        <div className="profile-pills">
          {(["basic", "epi", "risk", "full"] as const).map((profile) => (
            <button
              key={profile}
              type="button"
              className="profile-pill"
              onClick={() => updateFeatures(FEATURE_PROFILES[profile]).catch(console.error)}
            >
              {PROFILE_TITLES[profile]}
            </button>
          ))}
        </div>
      </div>
      <div className="sidebar-group">
        <div className="sidebar-group-label">Features</div>
        <div className="nav-list">
          {sorted.map((feature) => (
            <NavRow key={feature.key} feature={feature} />
          ))}
        </div>
      </div>
    </nav>
  );
}

// CameraSidebar (mock por câmera) foi removida — substituída pela <Sidebar>
// real dentro de camera-focus.tsx desde a integração com o backend
// (Fase A, Passo 4/6). Ficava aqui sem uso nenhum.

export function OverlayControls() {
  const overlay = useDashboardStore((s) => s.overlay);
  const updateOverlay = useDashboardStore((s) => s.updateOverlay);
  if (!overlay) return null;
  return (
    <Panel id="panel-overlay" title="Overlay do vídeo" description="Controle o que aparece dentro do frame sem misturar dados operacionais.">
      <div className="features compact">
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