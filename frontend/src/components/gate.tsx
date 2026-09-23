import { useEffect, useRef, useState } from "react";
import { useDashboardStore } from "../store/dashboardStore";
import { playGateApprovedChime, playGateDeniedChime } from "../audio/chime";
import { MuteToggle } from "./layout";
import { Panel } from "./common";
import { getGate, putGate, startCamera } from "../api/endpoints";
import type { CameraRecord, GateState } from "../api/types";
import { PPE_KEYS, PPE_LABELS } from "../api/ppe";

const TITULO: Record<string, string> = {
  approved: "ENTRADA LIBERADA",
  denied: "ENTRADA NEGADA",
  waiting: "AGUARDANDO",
  off: "PORTARIA DESLIGADA",
};

/**
 * Consulta o veredito a cada 700 ms: o veredito não pode andar atrás da câmera.
 *
 * `comSom` toca o alarme de aprovada/negada a cada TRANSIÇÃO de veredito — nunca
 * no primeiro carregamento (senão toda vez que se abre a tela ela apita) e nunca
 * enquanto o veredito se mantém (senão "negada" viraria sirene contínua). A
 * prévia de configuração (GateConfigPanel) passa `comSom=false`: quem está
 * ajustando os EPIs exigidos não precisa ouvir a portaria apitando a cada clique.
 */
function useGate(camId: number, comSom = false): GateState | null {
  const [gate, setGate] = useState<GateState | null>(null);
  const anterior = useRef<GateState["verdict"] | null>(null);
  useEffect(() => {
    setGate(null);
    anterior.current = null;
    let cancelled = false;
    const tick = () =>
      getGate(camId)
        .then((g) => {
          if (cancelled) return;
          setGate(g);
          if (comSom && anterior.current !== null && anterior.current !== g.verdict && !useDashboardStore.getState().muted) {
            if (g.verdict === "approved") playGateApprovedChime();
            else if (g.verdict === "denied") playGateDeniedChime();
          }
          anterior.current = g.verdict;
        })
        .catch(() => {
          if (!cancelled) setGate(null);
        });
    tick();
    const timer = setInterval(tick, 700);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [camId, comSom]);
  return gate;
}

function VeredictoGrande({ gate }: { gate: GateState | null }) {
  const veredito = gate?.verdict ?? "waiting";
  const faltando = (gate?.missing ?? []).map((k) => PPE_LABELS[k as keyof typeof PPE_LABELS] ?? k);
  return (
    <div className={`gate-verdict ${veredito}`} role="status" aria-live="assertive">
      <strong>{TITULO[veredito] ?? "AGUARDANDO"}</strong>
      {veredito === "denied" && faltando.length > 0 && <span>Falta: {faltando.join(", ")}</span>}
      {veredito === "approved" && <span>Todos os EPIs exigidos foram identificados.</span>}
      {veredito === "waiting" && <span>Posicione-se na frente da câmera.</span>}
    </div>
  );
}

function ChipsExigidos({ gate }: { gate: GateState | null }) {
  if (!gate) return null;
  return (
    <div className="actions">
      {gate.required.map((k) => {
        const falta = gate.missing.includes(k);
        const semPessoa = gate.verdict === "waiting";
        return (
          <span key={k} className={`chip ${semPessoa ? "" : falta ? "miss" : "ok"}`}>
            <span className="dot" />
            {PPE_LABELS[k as keyof typeof PPE_LABELS] ?? k}
          </span>
        );
      })}
    </div>
  );
}

/** Tela cheia da portaria: veredito enorme, vídeo e a lista do que é exigido. */
export function GateKiosk({ camId }: { camId: number }) {
  const camera = useDashboardStore((s) => s.cameras.find((c) => c.id === camId));
  const gate = useGate(camId, true);
  const [starting, setStarting] = useState(false);
  if (!camera) return null;

  return (
    <div className="kiosk-wrap">
      <VeredictoGrande gate={gate} />
      <div className={`card kiosk-video gate-video ${gate?.verdict ?? ""}`.trim()}>
        <div className="over-video">
          <span className="over-pill">{camera.name} · Portaria</span>
        </div>
        <img
          src={`/api/cameras/${camId}/video_feed`}
          alt={`Vídeo de ${camera.name}`}
        />
        <div className="kiosk-actions">
          <button
            type="button"
            className="ghost small"
            disabled={starting}
            onClick={() => {
              setStarting(true);
              startCamera(camId).finally(() => setStarting(false));
            }}
          >
            {starting ? "Iniciando…" : "Iniciar câmera"}
          </button>
        </div>
      </div>
      <div className="kiosk-footer">
        <ChipsExigidos gate={gate} />
        <MuteToggle />
      </div>
    </div>
  );
}

/** Aba de configuração (técnico/supervisor): quais EPIs a portaria exige + prévia ao vivo. */
export function GateConfigPanel({ camera }: { camera: CameraRecord }) {
  const loadCameras = useDashboardStore((s) => s.loadCameras);
  const showMessage = useDashboardStore((s) => s.showMessage);
  const gate = useGate(camera.id);
  const [exigidos, setExigidos] = useState<string[]>(camera.gate_required ?? ["helmet", "vest"]);
  const [salvando, setSalvando] = useState(false);
  const ligada = camera.gate_required != null;

  useEffect(() => {
    setExigidos(camera.gate_required ?? ["helmet", "vest"]);
  }, [camera.id, camera.gate_required]);

  const alternar = (chave: string) =>
    setExigidos((atual) => (atual.includes(chave) ? atual.filter((k) => k !== chave) : [...atual, chave]));

  const salvar = (required: string[] | null) => {
    setSalvando(true);
    putGate(camera.id, required)
      .then(() => {
        showMessage(required ? "Portaria ligada nesta câmera." : "Portaria desligada.", "ok");
        return loadCameras();
      })
      .catch((err) => showMessage(err instanceof Error ? err.message : "Falha ao salvar a portaria.", "error"))
      .finally(() => setSalvando(false));
  };

  return (
    <Panel
      id="panel-gate"
      title="Modo portaria"
      description="Só libera a entrada se todos os EPIs marcados estiverem visíveis. Na dúvida, nega. O operador desta câmera passa a ver a tela de portaria."
    >
      <div className="features">
        {PPE_KEYS.map((chave) => (
          <label className="feature-item" key={chave}>
            <span className="switch">
              <input type="checkbox" checked={exigidos.includes(chave)} onChange={() => alternar(chave)} />
              <span className="switch-track">
                <span className="switch-thumb" />
              </span>
            </span>
            <span>
              <strong>{PPE_LABELS[chave]}</strong>
              <small>{camera.features[chave] ? "Obrigatório para entrar" : "Feature desligada nesta câmera: sempre negaria"}</small>
            </span>
          </label>
        ))}
      </div>
      <div className="actions actions-top">
        <button type="button" className="primary" disabled={salvando || exigidos.length === 0} onClick={() => salvar(exigidos)}>
          {ligada ? "Salvar exigências" : "Ligar portaria"}
        </button>
        {ligada && (
          <button type="button" className="ghost" disabled={salvando} onClick={() => salvar(null)}>
            Desligar portaria
          </button>
        )}
      </div>
      {ligada && (
        <>
          <p className="status-text">Prévia ao vivo:</p>
          <VeredictoGrande gate={gate} />
          <ChipsExigidos gate={gate} />
        </>
      )}
    </Panel>
  );
}
