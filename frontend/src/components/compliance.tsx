import { useDashboardStore } from "../store/dashboardStore";
import { PPE_KEYS, PPE_LABELS } from "../api/ppe";
import { Panel, Badge, EmptyState, PanelSkeleton } from "./common";

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
      action={<Badge tone="neutral">{`${personCount} pessoa${personCount === 1 ? "" : "s"}`}</Badge>}
    >
      <div className="row-list">
        {rows.length ? (
          rows.map((row) => (
            <div className="row-item" key={row.key}>
              <span className={`row-dot ${row.status}`} />
              <div>
                <strong>{row.label}</strong>
                <span>{row.message}</span>
              </div>
            </div>
          ))
        ) : (
          <EmptyState>Aguardando análise.</EmptyState>
        )}
      </div>
    </Panel>
  );
}

export function PersonCard() {
  const compliance = useDashboardStore((s) => s.compliance);
  const lastDetections = useDashboardStore((s) => s.lastDetections);
  const lastPose = useDashboardStore((s) => s.lastPose);
  const bootstrapping = useDashboardStore((s) => s.bootstrapping);
  const people = compliance?.people || [];
  const detectionCount = lastDetections.length;

  if (bootstrapping) {
    return (
      <Panel id="panel-people" title="Pessoas e detecções" description="Cards por pessoa quando o modelo PPE completo estiver disponível.">
        <PanelSkeleton lines={2} />
      </Panel>
    );
  }

  return (
    <Panel
      id="panel-people"
      title="Pessoas e detecções"
      description="Cards por pessoa quando o modelo PPE completo estiver disponível."
      action={<Badge tone="neutral">{`${detectionCount} ${detectionCount === 1 ? "detecção" : "detecções"}`}</Badge>}
    >
      <div className="row-list">
        {people.length > 0 ? (
          people.map((person) => (
            <div className="row-item" key={person.id}>
              <span className="row-dot ok" />
              <div>
                <strong>{person.label || person.id}</strong>
                <span>
                  Confiança {(person.confidence * 100).toFixed(1)}% · box {person.box.x1},{person.box.y1} → {person.box.x2},{person.box.y2}
                </span>
                <div className="metrics">
                  {PPE_KEYS.map((key) => {
                    const item = person.ppe[key];
                    return (
                      <span className={`metric ${item?.status || ""}`} key={key}>
                        {PPE_LABELS[key]}: {item?.message || item?.status || "-"}
                      </span>
                    );
                  })}
                  <span className="metric">Risco: {person.risk_area?.message || "não avaliado"}</span>
                </div>
              </div>
            </div>
          ))
        ) : (
          <FallbackPersonRows detections={lastDetections} pose={lastPose} hasCompliance={Boolean(compliance)} />
        )}
      </div>
    </Panel>
  );
}

/**
 * Ported from the vanilla app.js's renderDetections(): only reached when
 * compliance.people is empty. If MediaPipe found a pose but YOLO found no
 * "person" box, infer a single person from the pose alone. Otherwise falls
 * back to raw YOLO person boxes without full PPE matching.
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
          <span className="row-dot ok" />
          <div>
            <strong>Pessoa 1</strong>
            <span>Inferida por pose MediaPipe. Para múltiplas pessoas, use YOLO com classe person ativa.</span>
            <div className="metrics">
              <span className="metric">Pose: detectada</span>
            </div>
          </div>
        </div>
      )}
      {rawPeople.map((person, index) => (
        <div className="row-item" key={index}>
          <span className="row-dot ok" />
          <div>
            <strong>Pessoa {index + 1}</strong>
            <span>
              Confiança {(person.confidence * 100).toFixed(1)}% · box {person.box.x1},{person.box.y1} → {person.box.x2},{person.box.y2}
            </span>
            <div className="metrics">
              <span className="metric">Multi-pessoa via YOLO</span>
            </div>
          </div>
        </div>
      ))}
    </>
  );
}
