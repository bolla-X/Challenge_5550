import type { CameraMock, FalsePositiveAuditItem } from "../api/types";

/**
 * Dados mock das câmeras — fase de interface, antes do backend suportar
 * multi-source de verdade (ver conversa: "interface primeiro, câmeras
 * múltiplas depois"). Porta 1:1 do protótipo HTML validado no chat.
 *
 * Quando o backend ganhar GET /cameras, este arquivo é substituído por uma
 * chamada real em api/endpoints.ts + populado no bootstrap() do store — o
 * shape de CameraMock em api/types.ts já foi desenhado pra isso.
 */
export const MOCK_CAMERAS: CameraMock[] = [
  {
    id: 1,
    name: "Câmera 1 — Portaria",
    location: "Entrada principal",
    source_type: "RTSP",
    source: "rtsp://192.168.0.21/stream1",
    status: "ok",
    fps: 12,
    features: { helmet: true, vest: true, gloves: false, pose: false, falls: false, posture: false, risk_area: false },
    alerts: [],
    risk_score: 12,
    driving_feature: "Capacete",
    connectivity: { latency_ms: 42, uptime_pct: 99.6, last_reconnect: "há 6 dias" },
    error_log: [],
  },
  {
    id: 2,
    name: "Câmera 2 — Linha de produção",
    location: "Setor B",
    source_type: "RTSP",
    source: "rtsp://192.168.0.22/stream1",
    status: "ok",
    fps: 10,
    features: { helmet: true, vest: true, gloves: true, pose: true, falls: true, posture: true, risk_area: true },
    alerts: [
      { id: "a1", sev: "critical", label: "Sem capacete", meta: "regra: helmet · pessoa #2", time: "há 2 min" },
      { id: "a2", sev: "high", label: "Sem colete de segurança", meta: "regra: vest · pessoa #1", time: "há 6 min" },
    ],
    risk_score: 78,
    driving_feature: "Capacete",
    connectivity: { latency_ms: 118, uptime_pct: 97.1, last_reconnect: "há 14h" },
    error_log: [
      { msg: "Frame indisponível por 3.2s", time: "hoje, 09:12" },
      { msg: "Reconexão automática bem-sucedida", time: "hoje, 09:12" },
    ],
  },
  {
    id: 3,
    name: "Câmera 3 — Estacionamento",
    location: "Área externa",
    source_type: "RTSP",
    source: "rtsp://192.168.0.23/stream1",
    status: "offline",
    fps: 0,
    features: { helmet: false, vest: false, gloves: false, pose: true, falls: false, posture: false, risk_area: false },
    alerts: [{ id: "a3", sev: "info", label: "Câmera reconectando", meta: "última leitura há 4 min", time: "agora" }],
    risk_score: 0,
    driving_feature: null,
    connectivity: { latency_ms: null, uptime_pct: 81.4, last_reconnect: "tentando…" },
    error_log: [
      { msg: "Não foi possível abrir a fonte de vídeo", time: "hoje, 10:04" },
      { msg: "Timeout de conexão RTSP", time: "hoje, 10:04" },
    ],
  },
  {
    id: 4,
    name: "Câmera 4 — Almoxarifado",
    location: "Depósito 2",
    source_type: "USB",
    source: "índice 0 (webcam local)",
    status: "ok",
    fps: 12,
    features: { helmet: false, vest: false, gloves: false, pose: true, falls: true, posture: false, risk_area: false },
    alerts: [],
    risk_score: 5,
    driving_feature: null,
    connectivity: { latency_ms: 8, uptime_pct: 99.9, last_reconnect: "há 21 dias" },
    error_log: [],
  },
];

export const MOCK_AUDIT_QUEUE: FalsePositiveAuditItem[] = [
  { id: 1, camera_id: 2, label: "Sem colete de segurança", reported_by: "Operador (Cam 2)", time: "há 40 min", status: "pending" },
  { id: 2, camera_id: 1, label: "Sem capacete (detecção antiga)", reported_by: "Operador (Cam 1)", time: "ontem", status: "pending" },
];
