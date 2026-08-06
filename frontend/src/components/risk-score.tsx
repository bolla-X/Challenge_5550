import { useEffect, useRef, useState, useId } from "react";
import { motion, useReducedMotion } from "motion/react";
import NumberFlow from "@number-flow/react";
import { useDashboardStore } from "../store/dashboardStore";
import { Panel, Badge, PanelSkeleton } from "./common";
import type { RiskTrendBucket } from "../api/types";

// Mesmos rótulos usados em feature_manager.py / compliance.tsx — mantém a
// nomenclatura consistente em todo o dashboard.
const FEATURE_LABELS: Record<string, string> = {
  helmet: "Capacete",
  vest: "Colete",
  gloves: "Luvas",
  falls: "Quedas",
  posture: "Postura",
  risk_area: "Área de risco",
};

// Cor é rara por design ("Autoridade Discreta"): baixo/moderado ficam
// neutros, só alto/crítico ganham destaque.
const LEVEL_TONE: Record<string, "neutral" | "warn" | "error"> = {
  baixo: "neutral",
  moderado: "neutral",
  alto: "warn",
  critico: "error",
};

const LEVEL_LABEL: Record<string, string> = {
  baixo: "Baixa",
  moderado: "Moderada",
  alto: "Alta",
  critico: "Crítica",
};

function formatBucketHour(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

/** Sparkline SVG puro — sem lib, os buckets já vêm prontos do backend (até
 * ~24 pontos). Prova visual de tendência, não só o número isolado do
 * headline: é o item central pedido nesta rodada. `<title>` por ponto dá
 * tooltip nativo (hora + score) sem JS de hover extra. */
function Sparkline({ buckets, values, height = 34 }: { buckets: RiskTrendBucket[]; values: number[]; height?: number }) {
  const gradientId = useId();
  if (values.length < 2) return null;
  const width = Math.max(values.length * 8, 60);
  const max = 100; // score é sempre 0-100, eixo fixo pra não distorcer picos pequenos como se fossem grandes
  const stepX = width / (values.length - 1);
  const points = values.map((v, i) => [i * stepX, height - (v / max) * height] as const);
  const linePath = points.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const areaPath = `${linePath} L${width},${height} L0,${height} Z`;

  return (
    <svg className="risk-sparkline" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" role="img" aria-label="Tendência de risco nas últimas horas">
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--accent)" stopOpacity=".28" />
          <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={areaPath} fill={`url(#${gradientId})`} stroke="none" />
      <path d={linePath} fill="none" stroke="var(--accent)" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      {points.map(([x, y], i) => (
        <circle key={buckets[i]?.bucket_start ?? i} cx={x} cy={y} r="7" fill="transparent">
          <title>
            {buckets[i] ? `${formatBucketHour(buckets[i].bucket_start)} · ${values[i]}/100` : `${values[i]}/100`}
          </title>
        </circle>
      ))}
    </svg>
  );
}

/** Mini variante inline pra caber num chip de feature — sem eixo, sem
 * gradiente, só a linha. Existe pra responder "essa categoria está subindo
 * ou descendo", não pra ler valores exatos (isso é o hover do sparkline
 * grande). */
function MiniSparkline({ values }: { values: number[] }) {
  if (values.length < 2 || values.every((v) => v === 0)) return null;
  const width = 40;
  const height = 12;
  const stepX = width / (values.length - 1);
  const path = values.map((v, i) => `${i === 0 ? "M" : "L"}${(i * stepX).toFixed(1)},${(height - (v / 100) * height).toFixed(1)}`).join(" ");
  return (
    <svg className="risk-mini-sparkline" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" aria-hidden="true">
      <path d={path} fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** Estatística honesta sobre janela deslizante — contagem de alertas
 * ponderada por severidade, não previsão por IA/ML. O rótulo e a descrição
 * abaixo existem pra deixar isso explícito, não só pra soar bonito. */
export function RiskScoreCard() {
  const riskScore = useDashboardStore((s) => s.riskScore);
  const riskTrend = useDashboardStore((s) => s.riskTrend);
  const bootstrapping = useDashboardStore((s) => s.bootstrapping);
  const shouldReduceMotion = useReducedMotion();

  // Comunica "a categoria de risco em si mudou de faixa" (ex: moderado ->
  // alto), não cada tick de score dentro da mesma faixa — só dispara em
  // transição de nível, não a cada atualização de 30s.
  const previousLevel = useRef<string | null>(null);
  const [justChangedLevel, setJustChangedLevel] = useState(false);
  useEffect(() => {
    const level = riskScore?.overall.level ?? null;
    if (level && previousLevel.current && level !== previousLevel.current) {
      setJustChangedLevel(true);
      const timer = setTimeout(() => setJustChangedLevel(false), 900);
      previousLevel.current = level;
      return () => clearTimeout(timer);
    }
    previousLevel.current = level;
    return undefined;
  }, [riskScore?.overall.level]);

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
        <div className="risk-editor-status">Aguardando primeira leitura.</div>
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
      description={`Frequência de alertas nos últimos ${window_minutes} min — estatística sobre o histórico, não previsão.`}
      action={
        <motion.div
          animate={
            justChangedLevel && !shouldReduceMotion
              ? { scale: [1, 1.12, 1] }
              : { scale: 1 }
          }
          transition={{ duration: 0.4, ease: "easeOut" }}
        >
          <Badge tone={tone}>{LEVEL_LABEL[overall.level] ?? overall.level}</Badge>
        </motion.div>
      }
    >
      <div className="content-enter">
      <div className="risk-score-headline">
        <span className="risk-score-value">
          <NumberFlow value={overall.score} respectMotionPreference />
        </span>
        <span className="risk-score-unit">/100</span>
      </div>
      {overall.driving_feature && (
        <p className="risk-score-driver">
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
            <span className="class-chip" key={key}>
              {FEATURE_LABELS[key] ?? key} · {item.alert_count} alerta{item.alert_count === 1 ? "" : "s"}
              {riskTrend && (
                <MiniSparkline values={riskTrend.buckets.map((b) => b.features[key]?.score ?? 0)} />
              )}
            </span>
          ))
        ) : (
          <span className="class-chip">Sem alertas na janela</span>
        )}
      </div>
      </div>
    </Panel>
  );
}
