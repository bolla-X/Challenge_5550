import { useEffect, useState } from "react";
import { ROLE_ACCESS, useDashboardStore } from "../store/dashboardStore";
import { createCamera, discoverCameras, getCameraStatus } from "../api/endpoints";
import type { CameraDiscoveryEntry, CameraFeatureSet, CameraRecord } from "../api/types";

const CAMERA_FEATURE_ORDER: (keyof CameraFeatureSet)[] = ["helmet", "vest", "gloves", "glasses", "pose", "falls", "posture", "risk_area"];
const CAMERA_FEATURE_LABELS: Record<keyof CameraFeatureSet, string> = {
  helmet: "Capacete",
  vest: "Colete",
  gloves: "Luvas",
  glasses: "Óculos",
  pose: "Pose",
  falls: "Quedas",
  posture: "Postura",
  risk_area: "Área de risco",
  ppe: "EPIs (grupo)", // toggle de grupo do backend — não tem chip próprio na UI (ver CAMERA_FEATURE_ORDER)
};

// Backend agora suporta multi-source de verdade (Fase A, Passo 4/5) — cada
// card consulta o status/feed da SUA PRÓPRIA câmera via /api/cameras/<id>,
// não mais o /video_feed legado (que só serve a câmera padrão e fazia
// todo card parecer "parado" mesmo com outra câmera rodando).
function useCameraRunning(cameraId: number): boolean {
  const [running, setRunning] = useState(false);
  useEffect(() => {
    let cancelled = false;
    const refresh = () => {
      getCameraStatus(cameraId)
        .then((status) => {
          if (!cancelled) setRunning(Boolean(status.running));
        })
        .catch(() => {
          if (!cancelled) setRunning(false);
        });
    };
    refresh();
    const interval = setInterval(refresh, 3000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [cameraId]);
  return running;
}

function CameraCard({
  camera,
  onConfigure,
  canConfigure,
}: {
  camera: CameraRecord;
  onConfigure: (id: number) => void;
  canConfigure: boolean;
}) {
  const running = useCameraRunning(camera.id);

  return (
    <div className="cam-card">
      {running ? (
        <div className="cam-frame">
          <span className="cam-live-tag">
            <span className="status-dot ok" /> recebendo
          </span>
          <img src={`/api/cameras/${camera.id}/video_feed`} alt={camera.name} />
        </div>
      ) : (
        <div className="cam-frame offline">
          <span>Monitoramento parado</span>
        </div>
      )}
      <div className="cam-body">
        <div className="cam-title-row">
          <h3>
            <span className={`status-dot ${running ? "ok" : "warn"}`} /> {camera.name}
          </h3>
        </div>
        <div className="cam-location">
          {camera.location || "Sem local definido"} · {camera.source_type} {camera.source}
        </div>
        <div className="cam-feature-chips">
          {CAMERA_FEATURE_ORDER.map((key) => (
            <span key={key} className={`cam-chip ${camera.features[key] ? "on" : ""}`.trim()}>
              {CAMERA_FEATURE_LABELS[key]}
            </span>
          ))}
        </div>
        <div className="cam-footer">
          <span className="cam-footer-stat" style={{ color: running ? "var(--ok, #22c55e)" : "var(--muted)" }}>
            {running ? "rodando" : "parada"}
          </span>
          <button type="button" className="cam-configure" onClick={() => onConfigure(camera.id)}>
            {canConfigure ? "Configurar" : "Ver"}
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round">
              <path d="M9 6l6 6-6 6" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}

/**
 * Formulário de cadastro de câmera nova — Fase A, Passo 6. Pra USB, testa
 * de verdade quais índices respondem AGORA (GET /api/cameras/discover) em
 * vez de pedir pra digitar um número no escuro; RTSP/Arquivo continuam
 * exigindo endereço manual (não tem como "descobrir" isso sozinho).
 */
function AddCameraModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [name, setName] = useState("");
  const [location, setLocation] = useState("");
  const [sourceType, setSourceType] = useState<"USB" | "RTSP" | "Arquivo">("USB");
  const [source, setSource] = useState("");
  const [fps, setFps] = useState(12);
  const [width, setWidth] = useState(960);
  const [height, setHeight] = useState(540);
  const [discovering, setDiscovering] = useState(false);
  const [discovered, setDiscovered] = useState<CameraDiscoveryEntry[] | null>(null);
  const [discoverError, setDiscoverError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const runDiscovery = () => {
    setDiscovering(true);
    setDiscoverError(null);
    discoverCameras(5)
      .then((res) => setDiscovered(res.items))
      .catch((err) => setDiscoverError(err instanceof Error ? err.message : "Falha ao detectar câmeras"))
      .finally(() => setDiscovering(false));
  };

  useEffect(() => {
    if (sourceType === "USB" && discovered === null) runDiscovery();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sourceType]);

  const handleSubmit = () => {
    if (!name.trim()) {
      setSubmitError("Dá um nome pra câmera.");
      return;
    }
    if (!source.trim()) {
      setSubmitError(sourceType === "USB" ? "Escolhe um índice detectado abaixo." : "Preenche o endereço da câmera.");
      return;
    }
    setSubmitting(true);
    setSubmitError(null);
    createCamera({ name: name.trim(), location: location.trim() || null, source_type: sourceType, source: source.trim(), fps, width, height })
      .then(() => onCreated())
      .catch((err) => setSubmitError(err instanceof Error ? err.message : "Falha ao cadastrar câmera"))
      .finally(() => setSubmitting(false));
  };

  return (
    <div
      style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,.6)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100 }}
      onClick={onClose}
    >
      <div
        className="card"
        style={{ width: 480, maxWidth: "92vw", maxHeight: "88vh", overflowY: "auto" }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="card-head">
          <div>
            <h2>Adicionar câmera</h2>
            <p>Cadastre uma fonte de vídeo real — sem câmeras de exemplo.</p>
          </div>
        </div>
        <div className="card-body">
          <div className="settings-grid">
            <label>
              Nome
              <input type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder="Ex.: Portaria" />
            </label>
            <label>
              Local (opcional)
              <input type="text" value={location} onChange={(e) => setLocation(e.target.value)} placeholder="Ex.: Entrada principal" />
            </label>
            <label>
              Tipo de fonte
              <select
                value={sourceType}
                onChange={(e) => {
                  const next = e.target.value as "USB" | "RTSP" | "Arquivo";
                  setSourceType(next);
                  setSource("");
                }}
              >
                <option value="USB">USB / webcam</option>
                <option value="RTSP">RTSP</option>
                <option value="Arquivo">Arquivo</option>
              </select>
            </label>
            <label>
              FPS alvo
              <input type="number" value={fps} min={1} max={60} onChange={(e) => setFps(Number(e.target.value) || 12)} />
            </label>
            <label>
              Largura (px)
              <input type="number" value={width} min={160} max={3840} onChange={(e) => setWidth(Number(e.target.value) || 960)} />
            </label>
            <label>
              Altura (px)
              <input type="number" value={height} min={120} max={2160} onChange={(e) => setHeight(Number(e.target.value) || 540)} />
            </label>
          </div>
          <p style={{ fontSize: 11, color: "var(--muted-2)", marginTop: -8, marginBottom: 8 }}>
            Escolher uma câmera USB detectada preenche a resolução nativa dela automaticamente — ajuste manual só se quiser forçar outra.
          </p>

          {sourceType === "USB" ? (
            <div style={{ marginTop: 4 }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
                <strong style={{ fontSize: 12.5 }}>Câmeras detectadas agora</strong>
                <button type="button" className="secondary small" onClick={runDiscovery} disabled={discovering}>
                  {discovering ? "Testando…" : "Testar de novo"}
                </button>
              </div>
              {discoverError && <p style={{ fontSize: 12, color: "var(--danger, #ef4444)" }}>{discoverError}</p>}
              {discovering && !discovered && <p style={{ fontSize: 12, color: "var(--muted)" }}>Testando índices 0 a 5…</p>}
              <div className="row-list">
                {discovered
                  ?.filter((d) => d.available)
                  .map((d) => (
                    <label
                      key={d.index}
                      className="row-item"
                      style={{ cursor: d.already_registered ? "not-allowed" : "pointer", opacity: d.already_registered ? 0.5 : 1 }}
                    >
                      <input
                        type="radio"
                        name="usb-source"
                        disabled={d.already_registered}
                        checked={source === d.source}
                        onChange={() => {
                          setSource(d.source);
                          // Preenche com a resolução NATIVA já detectada —
                          // é por isso que o discover() já traz width/height
                          // (ver conversa: "a Logitech é 1920x1080 também").
                          if (d.width && d.height) {
                            setWidth(d.width);
                            setHeight(d.height);
                          }
                        }}
                        style={{ marginTop: 4 }}
                      />
                      <div>
                        <strong>
                          Índice {d.index} {d.width ? `· ${d.width}×${d.height}` : ""}
                        </strong>
                        <span>{d.already_registered ? `Já cadastrada como "${d.registered_as}"` : "Disponível agora"}</span>
                      </div>
                    </label>
                  ))}
                {discovered && discovered.filter((d) => d.available).length === 0 && (
                  <p style={{ fontSize: 12, color: "var(--muted)" }}>Nenhuma câmera USB respondendo agora. Conecta e clica "Testar de novo".</p>
                )}
              </div>
            </div>
          ) : (
            <label style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 4 }}>
              {sourceType === "RTSP" ? "URL RTSP" : "Caminho do arquivo"}
              <input
                type="text"
                value={source}
                onChange={(e) => setSource(e.target.value)}
                placeholder={sourceType === "RTSP" ? "rtsp://192.168.0.10/stream1" : "/caminho/para/video.mp4"}
              />
            </label>
          )}

          {submitError && <p style={{ fontSize: 12, color: "var(--danger, #ef4444)", marginTop: 10 }}>{submitError}</p>}

          <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
            <button type="button" onClick={handleSubmit} disabled={submitting}>
              {submitting ? "Cadastrando…" : "Cadastrar câmera"}
            </button>
            <button type="button" className="secondary" onClick={onClose}>
              Cancelar
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

/**
 * Grid de câmeras — tela inicial de Técnico/Supervisor. Sem câmeras de
 * exemplo (Fase A, Passo 6): começa vazio até o usuário cadastrar a
 * primeira pelo modal acima. Operador nunca chega aqui (ver setMode no
 * store, que trava screen="kiosk" pro Operador).
 */
export function CameraGrid() {
  const cameras = useDashboardStore((s) => s.cameras);
  const mode = useDashboardStore((s) => s.mode);
  const setCamId = useDashboardStore((s) => s.setCamId);
  const setScreen = useDashboardStore((s) => s.setScreen);
  const loadCameras = useDashboardStore((s) => s.loadCameras);
  const access = ROLE_ACCESS[mode];
  const [showAddModal, setShowAddModal] = useState(false);

  const openFocus = (id: number) => {
    setCamId(id);
    setScreen("focus");
  };

  const handleCreated = () => {
    setShowAddModal(false);
    loadCameras().catch((err) => console.error(err));
  };

  if (cameras.length === 0) {
    return (
      <div style={{ padding: 40, textAlign: "center", maxWidth: 420, margin: "0 auto" }}>
        <p style={{ fontSize: 13, color: "var(--muted)", marginBottom: 16 }}>
          Nenhuma câmera cadastrada ainda. {access.canConfigure ? "Cadastre a primeira pra começar." : "Peça pro Técnico/Supervisor cadastrar uma."}
        </p>
        {access.canConfigure && (
          <button type="button" onClick={() => setShowAddModal(true)}>
            Adicionar câmera
          </button>
        )}
        {showAddModal && <AddCameraModal onClose={() => setShowAddModal(false)} onCreated={handleCreated} />}
      </div>
    );
  }

  return (
    <div className="camera-grid">
      {cameras.map((camera) => (
        <CameraCard key={camera.id} camera={camera} onConfigure={openFocus} canConfigure={access.canConfigure} />
      ))}
      {access.canConfigure && (
        <div className="cam-add-card" role="button" tabIndex={0} onClick={() => setShowAddModal(true)}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
            <path d="M12 5v14M5 12h14" />
          </svg>
          <span>Adicionar câmera</span>
        </div>
      )}
      {showAddModal && <AddCameraModal onClose={() => setShowAddModal(false)} onCreated={handleCreated} />}
    </div>
  );
}
