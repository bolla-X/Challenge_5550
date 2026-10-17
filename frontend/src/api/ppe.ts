import type { CameraFeatureSet } from "./types";

/**
 * Fonte ÚNICA das chaves e rótulos de EPI no frontend (e, mais abaixo, dos
 * rótulos pt-BR de classe do modelo, recurso, severidade e situação: a tela
 * nunca escreve uma chave crua da API).
 *
 * Espelha `PPE_KEYS`/`PPE_LABELS` de app/vision/person_compliance_matcher.py.
 * Antes esta lista aparecia copiada em quatro arquivos (compliance, features,
 * camera-grid, operator-kiosk) — habilitar óculos/máscara/calçado exigia achar
 * as quatro cópias, e esquecer uma deixava a tela mentindo em silêncio.
 */
export const PPE_KEYS = ["helmet", "vest", "gloves", "glasses", "mask", "safety_shoe", "ear_protection"] as const;
export type PpeKey = (typeof PPE_KEYS)[number];

export const PPE_LABELS: Record<PpeKey, string> = {
  helmet: "Capacete",
  vest: "Colete",
  gloves: "Luvas",
  glasses: "Óculos",
  mask: "Máscara",
  safety_shoe: "Calçado",
  ear_protection: "Protetor auricular",
};

/**
 * Rótulo pt-BR de QUALQUER classe que o modelo devolve: EPI, ausência de EPI
 * ("no_helmet"...), queda, pessoa. A tela nunca escreve a chave crua: chave
 * desconhecida só passa por `rotuloDaClasse`, que a devolve como veio.
 */
export const ROTULOS_DE_CLASSE: Record<string, string> = {
  ...PPE_LABELS,
  hardhat: PPE_LABELS.helmet,
  safety_vest: PPE_LABELS.vest,
  goggles: PPE_LABELS.glasses,
  no_helmet: "Sem capacete",
  no_vest: "Sem colete",
  no_gloves: "Sem luvas",
  no_glasses: "Sem óculos",
  no_mask: "Sem máscara",
  no_safety_shoe: "Sem calçado",
  fall_detected: "Queda",
  person: "Pessoa",
  safety_cone: "Cone",
};

export function rotuloDaClasse(chave: string): string {
  return ROTULOS_DE_CLASSE[chave] ?? chave;
}

/**
 * Rótulo pt-BR de cada recurso (feature) que gera alerta: os EPIs e os demais
 * sinais. Espelha os rótulos de app/services/feature_manager.py, em forma curta.
 */
export const ROTULOS_DE_RECURSO: Record<string, string> = {
  ...PPE_LABELS,
  ppe: "EPIs",
  pose: "Pose",
  falls: "Quedas",
  posture: "Postura",
  risk_area: "Área de risco",
  sos: "SOS por gesto",
  ergonomia: "Ergonomia",
  imobilidade: "Pessoa imóvel",
};

export function rotuloDoRecurso(chave: string): string {
  return ROTULOS_DE_RECURSO[chave] ?? chave;
}

/**
 * Rótulo pt-BR da REGRA que gerou o alerta (a chave `rule` da API, ex.: "missing_helmet"): as de EPI
 * saem de `PPE_LABELS`; as demais nativas ficam no mapa; regra do editor ("regra:<id>") mostra o id que a pessoa escolheu.
 */
export const ROTULOS_DE_REGRA: Record<string, string> = {
  risk_area_presence: "Pessoa em área de risco",
  fallen_person: "Pessoa caída",
  suspicious_posture: "Postura suspeita",
};

export function rotuloDaRegra(regra: string): string {
  const epi = /^(missing|incorrect)_(\w+)$/.exec(regra);
  if (epi && epi[2] in PPE_LABELS) {
    const nome = PPE_LABELS[epi[2] as PpeKey];
    return epi[1] === "missing" ? `Sem ${nome.toLowerCase()}` : `${nome} incorreto`;
  }
  if (regra.startsWith("regra:")) return `Regra do editor (${regra.slice("regra:".length)})`;
  return ROTULOS_DE_REGRA[regra] ?? regra;
}

/** Severidade e situação do alerta, como a tela e o CSV as escrevem. */
export const ROTULOS_DE_SEVERIDADE: Record<string, string> = {
  critical: "Crítico",
  high: "Alto",
  medium: "Médio",
  low: "Baixo",
  info: "Informativo",
};

export const ROTULOS_DE_SITUACAO: Record<string, string> = { active: "Ativo", resolved: "Resolvido" };

/** Descrição curta usada na sidebar de features. */
export const PPE_DESCRIPTIONS: Record<PpeKey, string> = {
  helmet: "Proteção da cabeça",
  vest: "Alta visibilidade",
  gloves: "Proteção das mãos",
  glasses: "Proteção ocular",
  mask: "Proteção respiratória",
  safety_shoe: "Proteção dos pés",
  ear_protection: "Proteção auricular",
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
