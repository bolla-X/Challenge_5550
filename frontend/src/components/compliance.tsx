import { useEffect, useState } from "react";
import { useDashboardStore } from "../store/dashboardStore";
import { PPE_KEYS, PPE_LABELS } from "../api/ppe";
import { Panel, Badge, EmptyState, PanelSkeleton } from "./common";

/** Chip de EPI: pílula com ponto e rótulo. Conforme em --ok, ausente com o
 * tingimento de perigo, não avaliado neutro. */
function PpeChip({ label, status }: { label: string; status?: string }) {
  const cls = status === "ok" ? "chip ok" : status === "missing" || status === "incorrect" ? "chip miss" : "chip";
  return (
    <span className={cls}>
      <span className="dot" />
      {label}
    </span>
  );
}

export function ComplianceCard() {
  const compliance = useDashboardStore((s) => s.compliance);
  const bootstrapping = useDashboardStore((s) => s.bootstrapping);
  const personCount = compliance?.person_count ?? 0;

  if (bootstrapping) {
    return (
      <Panel id="panel-compliance" title="Conformidade" description="Estado atual por item, fora do vídeo.">
        <PanelSkeleton lines={3} />
      </Panel>
    );
  }

  const rows: { key: string; label: string; status: string; message: string }[] = [];
  if (compliance) {
    PPE_KEYS.forEach((key) => {
      const item = compliance.ppe[key];
      if (!item) return;
      rows.push({ key, label: item.label, status: item.status, message: item.supported === false ? "Modelo incompatível" : item.message });
    });
    if (compliance.pose) rows.push({ key: "pose", label: "Pose", status: compliance.pose.status, message: compliance.pose.message });
    if (compliance.risk_area)
      rows.push({ key: "risk_area", label: "Área de risco", status: compliance.risk_area.status, message: compliance.risk_area.message });
  }

  return (
    <Panel
      id="panel-compliance"
      title="Conformidade"
      description="Estado atual por item, fora do vídeo."
      action={<Badge>{`${personCount} pessoa${personCount === 1 ? "" : "s"}`}</Badge>}
    >
      <div className="row-list">
        {rows.length ? (
          rows.map((row) => (
            <div className="row-item" key={row.key}>
              <span className={`dot ${row.status}`} />
              <div className="row-detail">
                <strong>{row.label}</strong>
                <span>{row.message}</span>
              </div>
            </div>
          ))
        ) : (
          <EmptyState>Aguardando a primeira análise desta câmera.</EmptyState>
        )}
      </div>
    </Panel>
  );
}

type EventoDaLinha = { ts: number; ppe: Record<string, string>; queda: boolean; zona?: string | null };

/** Linha do tempo de conformidade de UM ID de rastreio (F2): só as mudanças. */
function LinhaDoTempo({ cameraId, pessoaId }: { cameraId: number; pessoaId: string }) {
  const [eventos, setEventos] = useState<EventoDaLinha[] | null>(null);
  useEffect(() => {
    let vivo = true;
    const carregar = () =>
      fetch(`/api/cameras/${cameraId}/conformidade-por-id/${encodeURIComponent(pessoaId)}`, { credentials: "same-origin" })
        .then((r) => (r.ok ? r.json() : null))
        .then((d) => vivo && setEventos(d ? (d.eventos as EventoDaLinha[]) : []))
        .catch(() => vivo && setEventos([]));
    carregar();
    const t = window.setInterval(carregar, 3000);
    return () => {
      vivo = false;
      window.clearInterval(t);
    };
  }, [cameraId, pessoaId]);
  if (eventos === null) return <span className="muted">Carregando…</span>;
  return (
    <div className="linha-do-tempo" data-testid="linha-do-tempo">
      <span className="muted">ID de rastreio — some quando a pessoa sai de cena; não identifica ninguém.</span>
      {eventos.length === 0 ? (
        <span className="muted">Sem mudanças registradas ainda.</span>
      ) : (
        <ol>
          {[...eventos].reverse().map((e) => (
            <li key={e.ts}>
              <time>{new Date(e.ts * 1000).toLocaleTimeString("pt-BR")}</time>
              <span className="chip-row">
                {e.queda && (
                  <span className="chip miss">
                    <span className="dot" />
                    Queda
                  </span>
                )}
                {PPE_KEYS.filter((k) => e.ppe[k]).map((k) => (
                  <PpeChip key={k} label={PPE_LABELS[k]} status={e.ppe[k]} />
                ))}
                {e.zona === "inside" && (
                  <span className="chip miss">
                    <span className="dot" />
                    Na área de risco
                  </span>
                )}
              </span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

export function PersonCard() {
  const compliance = useDashboardStore((s) => s.compliance);
  const lastDetections = useDashboardStore((s) => s.lastDetections);
  const lastPose = useDashboardStore((s) => s.lastPose);
  const bootstrapping = useDashboardStore((s) => s.bootstrapping);
  const people = compliance?.people || [];
  const detectionCount = lastDetections.length;
  const camId = useDashboardStore((s) => s.camId);
  const [aberto, setAberto] = useState<string | null>(null);

  if (bootstrapping) {
    return (
      <Panel id="panel-people" title="Pessoas e detecções" description="Uma ficha por pessoa rastreada. O número é do rastreio, não uma identidade.">
        <PanelSkeleton lines={2} />
      </Panel>
    );
  }

  return (
    <Panel
      id="panel-people"
      title="Pessoas e detecções"
      description="Uma ficha por pessoa rastreada. O número é do rastreio, não uma identidade."
      action={<Badge>{`${detectionCount} ${detectionCount === 1 ? "detecção" : "detecções"}`}</Badge>}
    >
      <div className="row-list">
        {people.length > 0 ? (
          people.map((person) => {
            const naArea = person.risk_area?.status === "inside";
            return (
              <div className="row-item" key={person.id}>
                <span className={`dot ${naArea ? "risk" : "ok"}`} />
                <div className="row-detail">
                  <strong>{person.label || person.id}</strong>
                  <span>
                    Confiança {(person.confidence * 100).toFixed(1)}%, caixa {person.box.x1},{person.box.y1} a {person.box.x2},{person.box.y2}
                  </span>
                  {camId != null && (
                    <button
                      type="button"
                      className="link-button"
                      aria-expanded={aberto === person.id}
                      onClick={() => setAberto(aberto === person.id ? null : person.id)}
                    >
                      {aberto === person.id ? "Fechar linha do tempo" : "Linha do tempo"}
                    </button>
                  )}
                  {camId != null && aberto === person.id && <LinhaDoTempo cameraId={camId} pessoaId={person.id} />}
                  <div className="chip-row">
                    {PPE_KEYS.map((key) => {
                      const item = person.ppe[key];
                      return <PpeChip key={key} label={PPE_LABELS[key]} status={item?.status} />;
                    })}
                    <span className={`chip ${naArea ? "miss" : ""}`.trim()}>
                      <span className="dot" />
                      {person.risk_area?.message || "Área não avaliada"}
                    </span>
                  </div>
                </div>
              </div>
            );
          })
        ) : (
          <FallbackPersonRows detections={lastDetections} pose={lastPose} hasCompliance={Boolean(compliance)} />
        )}
      </div>
    </Panel>
  );
}

/**
 * Só alcançado quando compliance.people está vazio. Se o MediaPipe achou uma
 * pose mas o YOLO não achou caixa de "person", infere uma pessoa a partir
 * da pose. Senão, cai nas caixas cruas de pessoa do YOLO, sem EPI casado.
 */
function FallbackPersonRows({
  detections,
  pose,
  hasCompliance,
}: {
  detections: import("../api/types").Detection[];
  pose: import("../api/types").PoseResult | null;
  hasCompliance: boolean;
}) {
  const rawPeople = detections.filter((item) => item.label === "person" || item.category === "person");
  const posePerson = Boolean(pose?.found) && rawPeople.length === 0;

  if (!rawPeople.length && !posePerson) {
    return <EmptyState>{hasCompliance ? "Nenhuma pessoa detectada pelo YOLO no frame atual." : "Nenhuma detecção recebida no frame atual."}</EmptyState>;
  }

  return (
    <>
      {posePerson && (
        <div className="row-item">
          <span className="dot ok" />
          <div className="row-detail">
            <strong>Pessoa 1</strong>
            <span>Inferida por pose MediaPipe. Para múltiplas pessoas, use YOLO com a classe person ativa.</span>
            <div className="chip-row">
              <span className="chip">Pose detectada</span>
            </div>
          </div>
        </div>
      )}
      {rawPeople.map((person, index) => (
        <div className="row-item" key={index}>
          <span className="dot ok" />
          <div className="row-detail">
            <strong>Pessoa {index + 1}</strong>
            <span>
              Confiança {(person.confidence * 100).toFixed(1)}%, caixa {person.box.x1},{person.box.y1} a {person.box.x2},{person.box.y2}
            </span>
            <div className="chip-row">
              <span className="chip">Multi-pessoa via YOLO</span>
            </div>
          </div>
        </div>
      ))}
    </>
  );
}
