import type { CameraFeatureSet } from "./types";

/**
 * Fonte ÚNICA das chaves e rótulos de EPI no frontend.
 *
 * Espelha `PPE_KEYS`/`PPE_LABELS` de app/vision/person_compliance_matcher.py.
 * Antes esta lista aparecia copiada em quatro arquivos (compliance, features,
 * camera-grid, operator-kiosk) — habilitar óculos/máscara/calçado exigia achar
 * as quatro cópias, e esquecer uma deixava a tela mentindo em silêncio.
 */
export const PPE_KEYS = ["helmet", "vest", "gloves", "glasses", "mask", "safety_shoe"] as const;
export type PpeKey = (typeof PPE_KEYS)[number];

export const PPE_LABELS: Record<PpeKey, string> = {
  helmet: "Capacete",
  vest: "Colete",
  gloves: "Luvas",
  glasses: "Óculos",
  mask: "Máscara",
  safety_shoe: "Calçado",
};

/** Descrição curta usada na sidebar de features. */
export const PPE_DESCRIPTIONS: Record<PpeKey, string> = {
  helmet: "Proteção da cabeça",
  vest: "Alta visibilidade",
  gloves: "Proteção das mãos",
  glasses: "Proteção ocular",
  mask: "Proteção respiratória",
  safety_shoe: "Proteção dos pés",
};

/** Chaves de detecção que NÃO são EPI, na ordem em que a UI as apresenta. */
export const NON_PPE_FEATURE_KEYS = ["pose", "falls", "posture", "risk_area"] as const;

/** Ordem canônica das features numa lista/sidebar (o grupo "ppe" vem primeiro). */
export const FEATURE_ORDER: string[] = ["ppe", ...PPE_KEYS, ...NON_PPE_FEATURE_KEYS];

/** Chaves que aparecem como chip por câmera (sem o toggle de grupo "ppe"). */
export const CAMERA_FEATURE_ORDER: (keyof CameraFeatureSet)[] = [...PPE_KEYS, ...NON_PPE_FEATURE_KEYS];

export function isPpeKey(key: string): key is PpeKey {
  return (PPE_KEYS as readonly string[]).includes(key);
}
