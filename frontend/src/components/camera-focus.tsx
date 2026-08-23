import { useEffect, useState } from "react";
import { Sidebar, OverlayControls } from "./features";
// Sidebar de features por câmera do mock (Passo 2, CameraSidebar) foi
// substituída pela Sidebar real: o backend ainda é single-source, então
// ligar/desligar aqui precisa refletir no backend de verdade (mesmo
// raciocínio do Checklist/Zona/Overlay/Modelo/Gráficos acima) — senão o
// toggle parece funcionar mas não muda nada na detecção real.
import { Tabs, Panel, Badge, EmptyState, type TabItem } from "./common";
import { RiskAreaEditorPanel } from "./video";
import { ChecklistPanel, ModelStatusPanel, SettingsPanel } from "./diagnostics";
import { RiskScoreCard } from "./risk-score";
import { AlertPanel, AlertHistoryPanel } from "./alerts";
import { ComplianceCard, PersonCard } from "./compliance";
import { TimelineCard } from "./timeline";
import { ExportPanel } from "./export";
import { deleteCamera, discoverCameras, getCameraStatus, startCamera, stopCamera, updateCamera } from "../api/endpoints";
import type { MonitorStatus } from "../api/types";
import { useDashboardStore, type ViewMode } from "../store/dashboardStore";
import type { CameraRecord } from "../api/types";

// Tendência de risco (aba "Gráficos" do Supervisor) também já existia real
// — RiskScoreCard em risk-score.tsx, ligado ao /risk-score do backend.
// O painel próprio que eu tinha aqui usava um número fixo do mock (por
// isso não subia com detecções reais); reaproveitado abaixo sem versão
// mock própria, mesmo raciocínio do Checklist/Zona/Overlay/Modelo.

// Checklist (preflight real: backend/banco/vídeo/modelo/limpeza/snapshots)
// e Overlay já existiam como componentes reais (ChecklistPanel em
// diagnostics.tsx, OverlayControls em features.tsx) — reaproveitados
// direto abaixo, sem versão mock própria pra esta tela.

/**
 * Vídeo principal da tela de foco — por câmera de verdade. Substitui o
 * antigo <VideoCard /> (que sempre mostrava a câmera padrão/legada,
 * independente de qual câmera estava selecionada — bug reportado: "clico
 * em Configurar e todas mostram a Câmera 1"). Consulta status próprio,
 * mesmo padrão do CameraLiveControl/useCameraRunning usado no grid.
 */
function MainCameraVideo({ camera }: { camera: CameraRecord }) {
  const [running, setRunning] = useState<boolean | null>(null);
  const [starting, setStarting] = useState(false);

  useEffect(() => {
    setRunning(null);
    let cancelled = false;
    const refresh = () => {
      getCameraStatus(camera.id)
        .then((s) => {
          if (!cancelled) setRunning(Boolean(s.running));
        })
        .catch(() => {
          if (!cancelled) setRunning(false);
        });
    };
    refresh();
    const interval = setInterval(refresh, 2000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [camera.id]);

  const handleStart = () => {
    setStarting(true);
    startCamera(camera.id)
      .then(() => setRunning(true))
      .catch((err) => console.error(err))
      .finally(() => setStarting(false));
  };

  return (
    <section className="card video-card">
      <div className="video-frame">
        {running ? (
          <>
            <span className="video-live-dot">
              <span className="status-dot ok" /> recebendo
            </span>
            <img src={`/api/cameras/${camera.id}/video_feed`} alt={`Feed de vídeo — ${camera.name}`} />
          </>
        ) : (
          <div className="video-empty">
            <h3>Aguardando conexão de vídeo</h3>
            <p>{running === null ? "Carregando…" : `Inicie o monitoramento de "${camera.name}" para começar a receber o feed.`}</p>
            {running === false && (
              <button type="button" id="startBtn" disabled={starting} onClick={handleStart}>
                {starting ? "Iniciando…" : "Iniciar"}
              </button>
            )}
          </div>
        )}
      </div>
    </section>
  );
}

function CameraLiveControl({ camera }: { camera: CameraRecord }) {
  const [status, setStatus] = useState<MonitorStatus | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = () => {
    getCameraStatus(camera.id)
      .then(setStatus)
      .catch((err) => setError(err instanceof Error ? err.message : "Falha ao consultar status"));
  };

  // Consulta ao trocar de câmera e a cada 3s enquanto essa aba estiver
  // aberta — não usa socket ainda (o WS legado só fala da câmera padrão,
  // ver limitação documentada em MonitorService); polling simples resolve
  // pra esta fase de teste.
  useEffect(() => {
    setStatus(null);
    setError(null);
    refresh();
    const interval = setInterval(refresh, 3000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [camera.id]);

  const running = Boolean(status?.running);

  const handleStart = () => {
    setPending(true);
    setError(null);
    startCamera(camera.id)
      .then(setStatus)
      .catch((err) => setError(err instanceof Error ? err.message : "Falha ao iniciar câmera"))
      .finally(() => setPending(false));
  };

  const handleStop = () => {
    setPending(true);
    setError(null);
    stopCamera(camera.id)
      .then(setStatus)
      .catch((err) => setError(err instanceof Error ? err.message : "Falha ao parar câmera"))
      .finally(() => setPending(false));
  };

  return (
    <Panel
      title="Vídeo desta câmera"
      description="Inicia/para só esta câmera — independente da câmera padrão do topo da tela."
      action={<Badge tone={running ? "ok" : "neutral"}>{running ? "rodando" : "parada"}</Badge>}
    >
      {error && (
        <p style={{ fontSize: 12, color: "var(--danger, #ef4444)", marginBottom: 10 }}>{error}</p>
      )}
      <div className="video-frame" style={{ marginBottom: 12 }}>
        {running ? (
          // cache-buster simples via camera.id só troca a fonte quando muda
          // de câmera; o navegador mantém o stream MJPEG aberto sozinho.
          <img src={`/api/cameras/${camera.id}/video_feed`} alt={`Feed da câmera ${camera.id}`} />
        ) : (
          <div className="video-empty">
            <p>Câmera parada. Clique em Iniciar pra ver o feed.</p>
          </div>
        )}
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        <button type="button" disabled={pending || running} onClick={handleStart}>
          {pending && !running ? "Iniciando…" : "Iniciar esta câmera"}
        </button>
        <button type="button" className="secondary" disabled={pending || !running} onClick={handleStop}>
          {pending && running ? "Parando…" : "Parar esta câmera"}
        </button>
      </div>
    </Panel>
  );
}

function CameraConfigPanel({ camera }: { camera: CameraRecord }) {
  const setScreen = useDashboardStore((s) => s.setScreen);
  const loadCameras = useDashboardStore((s) => s.loadCameras);
  const [name, setName] = useState(camera.name);
  const [location, setLocation] = useState(camera.location ?? "");
  const [sourceType, setSourceType] = useState(camera.source_type);
  const [source, setSource] = useState(camera.source);
  const [fps, setFps] = useState(camera.fps);
  const [width, setWidth] = useState(camera.width);
  const [height, setHeight] = useState(camera.height);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [testing, setTesting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  // Se o usuário trocar de câmera (outro pill no topo), os campos precisam
  // refletir a câmera nova, não continuar mostrando o rascunho da anterior.
  useEffect(() => {
    setName(camera.name);
    setLocation(camera.location ?? "");
    setSourceType(camera.source_type);
    setSource(camera.source);
    setFps(camera.fps);
    setWidth(camera.width);
    setHeight(camera.height);
    setMessage(null);
  }, [camera.id]);

  const handleSave = () => {
    setSaving(true);
    setMessage(null);
    updateCamera(camera.id, { name, location: location || null, source_type: sourceType, source, fps, width, height })
      .then(() => {
        setMessage("Câmera salva — se estava rodando, já reiniciou sozinha com a config nova.");
        return loadCameras();
      })
      .catch((err) => setMessage(err instanceof Error ? err.message : "Falha ao salvar câmera"))
      .finally(() => setSaving(false));
  };

  const handleDelete = () => {
    if (!confirm("Remover esta câmera do sistema? Isso para o monitoramento dela e apaga o cadastro.")) return;
    setDeleting(true);
    deleteCamera(camera.id)
      .then(() => {
        setScreen("grid");
        return loadCameras();
      })
      .catch((err) => setMessage(err instanceof Error ? err.message : "Falha ao remover câmera"))
      .finally(() => setDeleting(false));
  };

  const handleTest = () => {
    if (sourceType !== "USB") {
      setMessage("Teste automático só cobre fontes USB por enquanto — RTSP/Arquivo exigem verificação manual.");
      return;
    }
    setTesting(true);
    setMessage(null);
    discoverCameras(5)
      .then((res) => {
        const match = res.items.find((d) => d.source === source);
        setMessage(match?.available ? `Índice ${source}: respondendo agora.` : `Índice ${source}: não respondeu ao teste.`);
      })
      .catch((err) => setMessage(err instanceof Error ? err.message : "Falha ao testar conexão"))
      .finally(() => setTesting(false));
  };

  return (
    <>
      <CameraLiveControl camera={camera} />
      <div style={{ height: 16 }} />
      <Panel title="Configuração da câmera" description="Fonte de vídeo e identificação — específico desta câmera.">
        <div className="settings-grid">
          <label>
            Nome
            <input type="text" value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          <label>
            Local
            <input type="text" value={location} onChange={(e) => setLocation(e.target.value)} />
          </label>
          <label>
            Tipo de fonte
            <select value={sourceType} onChange={(e) => setSourceType(e.target.value as CameraRecord["source_type"])}>
              <option value="USB">USB</option>
              <option value="RTSP">RTSP</option>
              <option value="Arquivo">Arquivo</option>
            </select>
          </label>
          <label>
            Endereço / índice
            <input type="text" value={source} onChange={(e) => setSource(e.target.value)} />
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
        {message && <p style={{ fontSize: 12, color: "var(--muted)", marginTop: 8 }}>{message}</p>}
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 14 }}>
          <button type="button" className="secondary small" disabled={testing} onClick={handleTest}>
            {testing ? "Testando…" : "Testar conexão"}
          </button>
        </div>
        <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
          <button type="button" disabled={saving} onClick={handleSave}>
            {saving ? "Salvando…" : "Salvar câmera"}
          </button>
          <button
            type="button"
            className="secondary small"
            disabled={deleting}
            style={{ color: "var(--danger)", borderColor: "rgba(239,68,68,.4)" }}
            onClick={handleDelete}
          >
            {deleting ? "Removendo…" : "Remover câmera"}
          </button>
        </div>
      </Panel>
    </>
  );
}

// Parâmetros e Modelo também já existiam reais (SettingsPanel e
// ModelStatusPanel em diagnostics.tsx) — é o ModelStatusPanel que mostra o
// aviso "modelo YOLO carregado não possui classes de EPI" quando aplicável;
// a versão mock que eu tinha colocado aqui escondia esse aviso, por isso
// sumiu da tela até essa correção.

function LogsPanel() {
  return (
    <Panel title="Log de erros" description="Exceções e eventos técnicos desta câmera.">
      <EmptyState>
        Ainda não existe um log persistente por câmera no backend — o erro mais recente aparece no Checklist (linha "Vídeo") e no badge de status do card no grid.
      </EmptyState>
    </Panel>
  );
}

// Histórico de alertas, Pessoas (com status de risco por pessoa) e Timeline
// também já existiam reais: AlertHistoryPanel/AlertPanel em alerts.tsx,
// PersonCard em compliance.tsx, TimelineCard em timeline.tsx. Mesmo
// raciocínio dos outros — reaproveitados direto no TABS_BY_MODE abaixo.

const TABS_BY_MODE: Record<Exclude<ViewMode, "operator">, TabItem[]> = {
  technical: [
    { key: "checklist", label: "Checklist", content: <ChecklistPanel /> },
    { key: "alerts", label: "Alertas", content: <AlertPanel /> },
    { key: "compliance", label: "Conformidade", content: <ComplianceCard /> },
    { key: "people", label: "Pessoas", content: <PersonCard /> },
    { key: "timeline", label: "Timeline", content: <TimelineCard /> },
    { key: "overlay", label: "Overlay", content: <OverlayControls /> },
    { key: "zone", label: "Zona", content: <RiskAreaEditorPanel /> },
    { key: "camconfig", label: "Config. câmera", content: <></> },
    { key: "settings", label: "Parâmetros", content: <SettingsPanel /> },
    { key: "model", label: "Modelo", content: <ModelStatusPanel /> },
    { key: "logs", label: "Logs", content: <></> },
    { key: "history", label: "Histórico", content: <AlertHistoryPanel /> },
  ],
  supervisor: [
    { key: "trend", label: "Gráficos", content: <RiskScoreCard /> },
    { key: "checklist", label: "Checklist", content: <ChecklistPanel /> },
    { key: "alerts", label: "Alertas", content: <AlertPanel /> },
    { key: "compliance", label: "Conformidade", content: <ComplianceCard /> },
    { key: "people", label: "Pessoas", content: <PersonCard /> },
    { key: "timeline", label: "Timeline", content: <TimelineCard /> },
    { key: "overlay", label: "Overlay", content: <OverlayControls /> },
    { key: "zone", label: "Zona", content: <RiskAreaEditorPanel /> },
    { key: "camconfig", label: "Config. câmera", content: <></> },
    { key: "settings", label: "Parâmetros", content: <SettingsPanel /> },
    { key: "model", label: "Modelo", content: <ModelStatusPanel /> },
    { key: "logs", label: "Logs", content: <></> },
    { key: "history", label: "Histórico", content: <AlertHistoryPanel /> },
    { key: "export", label: "Exportação", content: <ExportPanel /> },
  ],
};

/**
 * Foco individual de uma câmera — Técnico/Supervisor (mock). Reaproveita
 * <Sidebar> real (backend single-source) pra features + os mesmos componentes de card
 * (Panel/Badge/Tabs) já usados no resto do app. Operador nunca chega aqui.
 */
export function CameraFocus() {
  const camId = useDashboardStore((s) => s.camId);
  const cameras = useDashboardStore((s) => s.cameras);
  const setCamId = useDashboardStore((s) => s.setCamId);
  const setScreen = useDashboardStore((s) => s.setScreen);
  const mode = useDashboardStore((s) => s.mode);
  const camera = cameras.find((c) => c.id === camId);
  const [activeTab, setActiveTab] = useState<string>(mode === "supervisor" ? "trend" : "checklist");

  if (!camera || mode === "operator") return null;

  // Preenche o conteúdo real das abas que dependem da câmera selecionada
  // (as outras já vêm prontas no TABS_BY_MODE acima, incluindo os
  // painéis reais conectados ao backend — checklist/overlay/zona/
  // parâmetros/modelo não mudam por câmera porque o backend ainda é
  // single-source; só camconfig/logs/trend usam dado do mock por câmera).
  const tabs = TABS_BY_MODE[mode].map((tab) => {
    if (tab.key === "camconfig") return { ...tab, content: <CameraConfigPanel camera={camera} /> };
    if (tab.key === "logs") return { ...tab, content: <LogsPanel /> };
    return tab;
  });

  return (
    <>
      <div className="focus-topstrip">
        <button type="button" className="secondary small" onClick={() => setScreen("grid")}>
          ← Voltar pra grade
        </button>
        <div className="focus-cam-select">
          {cameras.map((c) => (
            <button
              key={c.id}
              type="button"
              className={`focus-cam-pill ${c.id === camId ? "active" : ""}`.trim()}
              onClick={() => setCamId(c.id)}
            >
              Cam {c.id}
            </button>
          ))}
        </div>
        <div className="focus-title">
          câmera: <b>{camera.name}</b>
        </div>
      </div>
      <div className="shell-body">
        <Sidebar />
        <main className="main">
          <div>
            <MainCameraVideo camera={camera} />
          </div>
          <div className="side-column">
            <Tabs tabs={tabs} active={activeTab} onChange={setActiveTab} idPrefix={`focus-${camId}`} />
          </div>
        </main>
      </div>
    </>
  );
}
