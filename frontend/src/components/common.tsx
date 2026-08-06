import type { ReactNode } from "react";

export function Panel({
  id,
  title,
  description,
  action,
  className = "",
  children,
}: {
  id?: string;
  title: string;
  description?: string;
  action?: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  return (
    <section id={id} className={`card ${className}`.trim()}>
      <div className="card-head">
        <div>
          <h2>{title}</h2>
          {description && <p>{description}</p>}
        </div>
        {action}
      </div>
      <div className="card-body">{children}</div>
    </section>
  );
}

export function Badge({ tone = "neutral", children }: { tone?: "neutral" | "ok" | "warn" | "error" | "info"; children: ReactNode }) {
  const cls = tone === "neutral" ? "badge" : `badge ${tone}`;
  return <span className={cls}>{children}</span>;
}

export function EmptyState({ children }: { children: ReactNode }) {
  return <div className="empty-state">{children}</div>;
}

/** Placeholder desenhado pros primeiros segundos antes do bootstrap()
 * resolver — substitui o "pisca vazio->populado" por um estado que comunica
 * "carregando", não "sem dados". CSS puro (respeita prefers-reduced-motion
 * via a regra global que já zera todas as animation-duration). */
export function PanelSkeleton({ lines = 3 }: { lines?: number }) {
  return (
    <div className="panel-skeleton" aria-hidden="true">
      {Array.from({ length: lines }).map((_, i) => (
        <div className="skeleton-block skeleton-line" key={i} style={{ width: i === lines - 1 ? "55%" : "100%" }} />
      ))}
    </div>
  );
}
