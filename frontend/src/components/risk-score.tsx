import NumberFlow from "@number-flow/react";
import { useDashboardStore } from "../store/dashboardStore";
import { Panel, Badge, EmptyState, PanelSkeleton } from "./common";
import type { RiskTrendBucket } from "../api/types";
import { paraDate } from "../utils/datas";

// Mesmos rótulos usados em feature_manager.py / compliance.tsx.
const FEATURE_LABELS: Record<string, string> = {
  helmet: "Capacete",
  vest: "Colete",
  gloves: "Luvas",
  falls: "Quedas",
  posture: "Postura",
  risk_area: "Área de risco",
};

// Cor é rara por design: baixo/moderado ficam neutros, só alto/crítico
// ganham o tingimento de perigo.
const LEVEL_TONE: Record<string, "neutral" | "error"> = {
  baixo: "neutral",
  moderado: "neutral",
  alto: "error",
  critico: "error",
};

const LEVEL_LABEL: Record<string, string> = {
  baixo: "Baixa",
  moderado: "Moderada",
  alto: "Alta",
  critico: "Crítica",
};

function formatBucketHour(iso: string): string {
  return paraDate(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

/** Sparkline SVG puro, só a linha, em currentColor: o container decide a cor
 * e ela acompanha o tema. `<title>` por ponto dá tooltip nativo. */
function Sparkline({ buckets, values, height = 40 }: { buckets: RiskTrendBucket[]; values: number[]; height?: number }) {
  if (values.length < 2) return null;
  const width = Math.max(values.length * 8, 60);
  const max = 100; // score é sempre 0-100, eixo fixo pra não distorcer picos pequenos
  const stepX = width / (values.length - 1);
  const points = values.map((v, i) => [i * stepX, height - (v / max) * height] as const);
  const linePath = points.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");

  return (
    <svg className="risk-sparkline" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" role="img" aria-label="Tendência de risco nas últimas horas">
      <path d={linePath} fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
      {points.map(([x, y], i) => (
        <circle key={buckets[i]?.bucket_start ?? i} cx={x} cy={y} r="7" fill="transparent">
          <title>{buckets[i] ? `${formatBucketHour(buckets[i].bucket_start)}, ${values[i]}/100` : `${values[i]}/100`}</title>
        </circle>
      ))}
    </svg>
  );
}

/** Mini variante inline pra caber num chip: responde "essa categoria está
 * subindo ou descendo", não valores exatos. */
function MiniSparkline({ values }: { values: number[] }) {
  if (values.length < 2 || values.every((v) => v === 0)) return null;
  const width = 40;
  const height = 12;
  const stepX = width / (values.length - 1);
  const path = values.map((v, i) => `${i === 0 ? "M" : "L"}${(i * stepX).toFixed(1)},${(height - (v / 100) * height).toFixed(1)}`).join(" ");
  return (
    <svg className="risk-mini-sparkline" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" aria-hidden="true">
      <path d={path} fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

/** Estatística honesta sobre janela deslizante: contagem de alertas
 * ponderada por severidade, não previsão. O rótulo e a descrição deixam
 * isso explícito. */
export function RiskScoreCard() {
  const riskScore = useDashboardStore((s) => s.riskScore);
  const riskTrend = useDashboardStore((s) => s.riskTrend);
  const bootstrapping = useDashboardStore((s) => s.bootstrapping);

  if (bootstrapping) {
    return (
      <Panel id="panel-risk-score" title="Tendência de risco" description="Frequência recente de alertas por categoria.">
        <PanelSkeleton lines={4} />
      </Panel>
    );
  }

  if (!riskScore) {
    return (
      <Panel id="panel-risk-score" title="Tendência de risco" description="Frequência recente de alertas por categoria.">
        <EmptyState>Aguardando a primeira leitura.</EmptyState>
      </Panel>
    );
  }

  const { overall, features, window_minutes } = riskScore;
  const tone = LEVEL_TONE[overall.level] ?? "neutral";
  const activeFeatures = Object.entries(features)
    .filter(([, item]) => item.alert_count > 0)
    .sort(([, a], [, b]) => b.score - a.score);

  return (
    <Panel
      id="panel-risk-score"
      title="Tendência de risco"
      description={`Frequência de alertas nos últimos ${window_minutes} min. Estatística sobre o histórico, não previsão.`}
      action={<Badge tone={tone}>{LEVEL_LABEL[overall.level] ?? overall.level}</Badge>}
    >
      <div className="content-enter">
        <div className="risk-headline">
          <span className="risk-value">
            <NumberFlow value={overall.score} respectMotionPreference />
          </span>
          <span className="risk-unit">/100</span>
        </div>
        {overall.driving_feature && (
          <p className="risk-driver">
            Categoria mais frequente: <strong>{FEATURE_LABELS[overall.driving_feature] ?? overall.driving_feature}</strong>
          </p>
        )}
        {riskTrend && riskTrend.buckets.length >= 2 && (
          <div className="risk-trend">
            <Sparkline buckets={riskTrend.buckets} values={riskTrend.buckets.map((b) => b.overall.score)} />
            <div className="risk-trend-axis">
              <span>{formatBucketHour(riskTrend.buckets[0].bucket_start)}</span>
              <span>últimas {riskTrend.hours}h</span>
              <span>{formatBucketHour(riskTrend.buckets[riskTrend.buckets.length - 1].bucket_end)}</span>
            </div>
          </div>
        )}
        <div className="class-list">
          {activeFeatures.length ? (
            activeFeatures.map(([key, item]) => (
              <span className="chip" key={key}>
                {FEATURE_LABELS[key] ?? key} · {item.alert_count} alerta{item.alert_count === 1 ? "" : "s"}
                {riskTrend && <MiniSparkline values={riskTrend.buckets.map((b) => b.features[key]?.score ?? 0)} />}
              </span>
            ))
          ) : (
            <span className="chip">Sem alertas na janela</span>
          )}
        </div>
      </div>
    </Panel>
  );
}
