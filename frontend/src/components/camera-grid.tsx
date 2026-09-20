import { useEffect, useState } from "react";
import { ROLE_ACCESS, useDashboardStore } from "../store/dashboardStore";
import { createCamera, discoverCameras, getCameraStatus } from "../api/endpoints";
import type { Alert, CameraDiagnostico, CameraDiscoveryEntry, CameraRecord } from "../api/types";

// Cada cartão consulta o status/feed da SUA PRÓPRIA câmera via
// /api/cameras/<id>, não o /video_feed legado (que só serve a câmera padrão).
export type EstadoDaCamera = {
  running: boolean;
  /** De qual fonte está lendo. `undefined` num backend que não manda o campo. */
  modo?: "ao_vivo" | "reconectando" | "fixture";
  tentativas: number;
  /** FPS do loop de captura e resolução do frame que CHEGOU (ver types.ts). */
  diagnostico?: CameraDiagnostico;
  /** Alertas ativos desta câmera, do mesmo GET /status. */
  alertas: Alert[];
};

const PARADA: EstadoDaCamera = { running: false, tentativas: 0, alertas: [] };

/** Exportado para o painel de diagnóstico e a tela de foco reaproveitarem o
 *  MESMO polling de 3 s, em vez de abrir um segundo contra a mesma rota. */
export function useCameraEstado(cameraId: number): EstadoDaCamera {
  const [estado, setEstado] = useState<EstadoDaCamera>(PARADA);
  useEffect(() => {
    let cancelled = false;
    const refresh = () => {
      getCameraStatus(cameraId)
        .then((status) => {
          if (cancelled) return;
          setEstado({
            running: Boolean(status.running),
            modo: status.video?.modo,
            tentativas: status.video?.reconnect_attempts ?? 0,
            diagnostico: status.diagnostico,
            alertas: status.active_alerts ?? [],
          });
        })
        .catch(() => {
          if (!cancelled) setEstado(PARADA);
        });
    };
    refresh();
    const interval = setInterval(refresh, 3000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [cameraId]);
  return estado;
}

/** Estado crítico: alerta ativo `critical` ou `high` na câmera. */
export function temAlertaCritico(estado: EstadoDaCamera): Alert | undefined {
  return estado.alertas.find((a) => a.severity === "critical" || a.severity === "high");
}

/** Uma linha de estado, em caixa normal. `fixture` NÃO é falha: é fallback
 * deliberado, e a leitura tem que ser "fonte de demonstração". */
export function textoDeEstado(estado: EstadoDaCamera): string {
  if (!estado.running) return "Monitoramento parado";
  if (estado.modo === "fixture") return "Fonte de demonstração";
  if (estado.modo === "reconectando") return `Reconectando, tentativa ${estado.tentativas + 1}`;
  if (estado.diagnostico?.fonte_sem_imagem) return "Recebendo, sem imagem";
  return "Recebendo";
}

function ChevronIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M9 6l6 6-6 6" />
    </svg>
  );
}

/** Cartão de câmera: imagem no topo, nome do setor e uma linha de estado.
 * Sem cabeçalho, sem fps, sem chip em cima da imagem. Estado crítico coloca
 * um anel de 2 px no cartão (ver .cam-card.critical). */
function CameraCard({
  camera,
  onOpen,
  canConfigure,
  onEstado,
}: {
  camera: CameraRecord;
  onOpen: (id: number) => void;
  canConfigure: boolean;
  onEstado?: (id: number, estado: EstadoDaCamera) => void;
}) {
  const estado = useCameraEstado(camera.id);
  useEffect(() => {
    onEstado?.(camera.id, estado);
  }, [camera.id, estado, onEstado]);

  const critico = Boolean(temAlertaCritico(estado));
  const linha = [camera.location, textoDeEstado(estado)].filter(Boolean).join(" · ");

  return (
    <button
      type="button"
      className={`card cam-card ${critico ? "critical" : ""}`.trim()}
      onClick={() => onOpen(camera.id)}
      aria-label={`${canConfigure ? "Configurar" : "Ver"} ${camera.name}`}
    >
      {estado.running ? (
        <div className="cam-frame">
          <img src={`/api/cameras/${camera.id}/video_feed`} alt="" />
        </div>
      ) : (
        <div className="cam-frame offline">Monitoramento parado</div>
      )}
      <div className="cam-body">
        <span className="cam-text">
          <span className="cam-name">{camera.name}</span>
          <span className="cam-state">{linha}</span>
        </span>
        <ChevronIcon />
      </div>
    </button>
  );
}

/**
 * Formulário de cadastro de câmera nova. Pra USB, testa de verdade quais
 * índices respondem AGORA (GET /api/cameras/discover) em vez de pedir pra
 * digitar um número no escuro; RTSP/Arquivo continuam exigindo endereço.
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
      setSubmitError("Dê um nome à câmera.");
      return;
    }
    if (!source.trim()) {
      setSubmitError(sourceType === "USB" ? "Escolha um índice detectado abaixo." : "Preencha o endereço da câmera.");
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
    <div className="modal-scrim" onClick={onClose}>
      <div className="card modal" role="dialog" aria-labelledby="add-camera-title" onClick={(e) => e.stopPropagation()}>
        <div className="card-head">
          <div>
            <h2 id="add-camera-title">Adicionar câmera</h2>
            <p>Cadastre uma fonte de vídeo real, sem câmeras de exemplo.</p>
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
          <p className="hint">
            Escolher uma câmera USB detectada preenche a resolução nativa dela automaticamente. Ajuste manual só se quiser forçar outra.
          </p>

          {sourceType === "USB" ? (
            <div>
              <div className="card-head-inline">
                <strong>Câmeras detectadas agora</strong>
                <button type="button" className="ghost small" onClick={runDiscovery} disabled={discovering}>
                  {discovering ? "Testando…" : "Testar de novo"}
                </button>
              </div>
              {discoverError && <p className="status-text error">{discoverError}</p>}
              {discovering && !discovered && <p className="status-text">Testando índices 0 a 5…</p>}
              <div className="row-list">
                {discovered
                  ?.filter((d) => d.available)
                  .map((d) => (
                    <label key={d.index} className={`row-item selectable ${d.already_registered ? "disabled" : ""}`.trim()}>
                      <input
                        type="radio"
                        name="usb-source"
                        disabled={d.already_registered}
                        checked={source === d.source}
                        onChange={() => {
                          setSource(d.source);
                          // Preenche com a resolução NATIVA já detectada.
                          if (d.width && d.height) {
                            setWidth(d.width);
                            setHeight(d.height);
                          }
                        }}
                      />
                      <div className="row-detail">
                        <strong>
                          Índice {d.index} {d.width ? `· ${d.width}×${d.height}` : ""}
                        </strong>
                        <span>{d.already_registered ? `Já cadastrada como "${d.registered_as}"` : "Disponível agora"}</span>
                      </div>
                    </label>
                  ))}
                {discovered && discovered.filter((d) => d.available).length === 0 && (
                  <p className="status-text">Nenhuma câmera USB respondendo agora. Conecte uma e clique em "Testar de novo".</p>
                )}
              </div>
            </div>
          ) : (
            <label className="field">
              <span>{sourceType === "RTSP" ? "URL RTSP" : "Caminho do arquivo"}</span>
              <input
                type="text"
                value={source}
                onChange={(e) => setSource(e.target.value)}
                placeholder={sourceType === "RTSP" ? "rtsp://192.168.0.10/stream1" : "/caminho/para/video.mp4"}
              />
            </label>
          )}

          {submitError && <p className="status-text error">{submitError}</p>}

          <div className="actions actions-top">
            <button type="button" className="primary" onClick={handleSubmit} disabled={submitting}>
              {submitting ? "Cadastrando…" : "Cadastrar câmera"}
            </button>
            <button type="button" onClick={onClose}>
              Cancelar
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

/**
 * Grade de câmeras, tela inicial de Técnico/Supervisor. Começa vazia até o
 * usuário cadastrar a primeira. Operador nunca chega aqui (ver setMode no
 * store, que trava screen="kiosk" pro Operador).
 */
export function CameraGrid({ onEstado }: { onEstado?: (id: number, estado: EstadoDaCamera) => void }) {
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
      <div className="centered-empty">
        <p>
          Nenhuma câmera cadastrada ainda.{" "}
          {access.canConfigure ? "Cadastre a primeira para começar." : "Peça ao Técnico ou ao Supervisor para cadastrar uma."}
        </p>
        {access.canConfigure && (
          <button type="button" className="primary" onClick={() => setShowAddModal(true)}>
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
        <CameraCard key={camera.id} camera={camera} onOpen={openFocus} canConfigure={access.canConfigure} onEstado={onEstado} />
      ))}
      {access.canConfigure && (
        <button type="button" className="cam-add" onClick={() => setShowAddModal(true)}>
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M12 5v14M5 12h14" />
          </svg>
          <span>Adicionar câmera</span>
        </button>
      )}
      {showAddModal && <AddCameraModal onClose={() => setShowAddModal(false)} onCreated={handleCreated} />}
    </div>
  );
}
