import { useDashboardStore } from "../store/dashboardStore";
import { Panel, Badge, EmptyState } from "./common";

const PPE_LABELS: Record<"helmet" | "vest" | "gloves", string> = { helmet: "Capacete", vest: "Colete", gloves: "Luvas" };

export function ComplianceMatrix() {
  const compliance = useDashboardStore((s) => s.compliance);
  const personCount = compliance?.person_count ?? 0;

  const cards: { key: string; label: string; status: string; message: string }[] = [];
  if (compliance) {
    (["helmet", "vest", "gloves"] as const).forEach((key) => {
      const item = compliance.ppe[key];
      if (!item) return;
      cards.push({
        key,
        label: item.label,
        status: item.status,
        message: item.supported === false ? "Modelo incompatível" : item.message,
      });
    });
    if (compliance.pose) cards.push({ key: "pose", label: "Pose", status: compliance.pose.status, message: compliance.pose.message });
    if (compliance.risk_area)
      cards.push({ key: "risk_area", label: "Área de risco", status: compliance.risk_area.status, message: compliance.risk_area.message });
  }

  return (
    <Panel
      title="Conformidade atual"
      description="Dados operacionais ficam fora do vídeo para reduzir poluição visual."
      action={<Badge tone="neutral">{`${personCount} pessoa${personCount === 1 ? "" : "s"}`}</Badge>}
    >
      <div className="compliance matrix">
        {cards.length ? (
          cards.map((card) => (
            <div className={`compliance-card ${card.status}`} key={card.key}>
              <strong>{card.label}</strong>
              <span>{card.message}</span>
            </div>
          ))
        ) : (
          <EmptyState>Aguardando análise.</EmptyState>
        )}
      </div>
    </Panel>
  );
}

export function PersonCards() {
  const compliance = useDashboardStore((s) => s.compliance);
  const lastDetections = useDashboardStore((s) => s.lastDetections);
  const lastPose = useDashboardStore((s) => s.lastPose);
  const people = compliance?.people || [];
  // Badge mirrors the original renderDetections(): total raw YOLO detections
  // in the latest frame, not just matched people.
  const detectionCount = lastDetections.length;

  return (
    <Panel
      title="Pessoas e detecções"
      description="Resumo externo ao frame. Cards por pessoa serão enriquecidos quando o modelo PPE chegar."
      action={<Badge tone="neutral">{`${detectionCount} ${detectionCount === 1 ? "detecção" : "detecções"}`}</Badge>}
    >
      <div className="person-cards">
        {people.length > 0 ? (
          people.map((person) => (
            <article className="person-card" key={person.id}>
              <strong>{person.label || person.id}</strong>
              <span>
                Confiança {(person.confidence * 100).toFixed(1)}% · box {person.box.x1},{person.box.y1} → {person.box.x2},{person.box.y2}
              </span>
              <div className="metrics">
                {(["helmet", "vest", "gloves"] as const).map((key) => {
                  const item = person.ppe[key];
                  return (
                    <span className={`metric ${item?.status || ""}`} key={key}>
                      {PPE_LABELS[key]}: {item?.message || item?.status || "-"}
                    </span>
                  );
                })}
                <span className="metric">Risco: {person.risk_area?.message || "não avaliado"}</span>
              </div>
            </article>
          ))
        ) : (
          <FallbackPersonCards detections={lastDetections} pose={lastPose} hasCompliance={Boolean(compliance)} />
        )}
      </div>
    </Panel>
  );
}

/**
 * Ported from the vanilla app.js's renderDetections(): only reached when
 * compliance.people is empty. If MediaPipe found a pose but YOLO found no
 * "person" box, infer a single person from the pose alone (single-person
 * MediaPipe can't be multi-person — that needs YOLO with the person class
 * enabled). Otherwise falls back to raw YOLO person boxes without full PPE
 * matching (that matching only happens server-side via compliance.people).
 */
function FallbackPersonCards({
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
    return (
      <EmptyState>
        {hasCompliance ? "Nenhuma pessoa detectada pelo YOLO no frame atual." : "Nenhuma detecção recebida no frame atual."}
      </EmptyState>
    );
  }

  return (
    <>
      {posePerson && (
        <article className="person-card">
          <strong>Pessoa 1</strong>
          <span>Inferida por pose MediaPipe. Para múltiplas pessoas, use YOLO com classe person ativa.</span>
          <div className="metrics">
            <span className="metric">Pose: detectada</span>
          </div>
        </article>
      )}
      {rawPeople.map((person, index) => (
        <article className="person-card" key={index}>
          <strong>Pessoa {index + 1}</strong>
          <span>
            Confiança {(person.confidence * 100).toFixed(1)}% · box {person.box.x1},{person.box.y1} → {person.box.x2},{person.box.y2}
          </span>
          <div className="metrics">
            <span className="metric">Multi-pessoa via YOLO</span>
          </div>
        </article>
      ))}
    </>
  );
}
