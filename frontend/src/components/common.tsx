import { useRef } from "react";
import type { ReactNode } from "react";
import { motion, useReducedMotion } from "motion/react";

const EASE = [0.16, 1, 0.3, 1] as const; // matches tokens.css --ease

export interface TabItem {
  key: string;
  label: string;
  content: ReactNode;
}

/** Tab strip + panels, same active-pill pattern as Topbar's .mode-toggle
 * (layoutId slides instead of an abrupt color swap in two places at once).
 * Panels are full existing card components (Panel-wrapped) — Fase 1 swaps
 * which one is visible, it doesn't restructure their internals. */
export function Tabs({ tabs, active, onChange, idPrefix }: { tabs: TabItem[]; active: string; onChange: (key: string) => void; idPrefix: string }) {
  const listRef = useRef<HTMLDivElement>(null);
  const shouldReduceMotion = useReducedMotion();
  const activeIndex = Math.max(0, tabs.findIndex((t) => t.key === active));

  const onKeyDown = (event: React.KeyboardEvent) => {
    let nextIndex = activeIndex;
    if (event.key === "ArrowRight") nextIndex = (activeIndex + 1) % tabs.length;
    else if (event.key === "ArrowLeft") nextIndex = (activeIndex - 1 + tabs.length) % tabs.length;
    else if (event.key === "Home") nextIndex = 0;
    else if (event.key === "End") nextIndex = tabs.length - 1;
    else return;
    event.preventDefault();
    onChange(tabs[nextIndex].key);
    listRef.current?.querySelectorAll<HTMLButtonElement>('[role="tab"]')[nextIndex]?.focus();
  };

  return (
    <div className="tabs">
      <div className="tabs-list" role="tablist" ref={listRef} onKeyDown={onKeyDown}>
        {tabs.map((tab) => {
          const selected = tab.key === active;
          return (
            <button
              key={tab.key}
              type="button"
              role="tab"
              id={`${idPrefix}-tab-${tab.key}`}
              aria-selected={selected}
              aria-controls={`${idPrefix}-panel-${tab.key}`}
              tabIndex={selected ? 0 : -1}
              className={`tab ${selected ? "active" : ""}`.trim()}
              onClick={() => onChange(tab.key)}
            >
              {selected && (
                <motion.span
                  className="tab-pill"
                  layoutId={`${idPrefix}-tab-pill`}
                  transition={{ duration: shouldReduceMotion ? 0 : 0.2, ease: EASE }}
                />
              )}
              <span className="tab-label">{tab.label}</span>
            </button>
          );
        })}
      </div>
      {tabs.map((tab) => (
        <div
          key={tab.key}
          className="tabs-panel"
          role="tabpanel"
          id={`${idPrefix}-panel-${tab.key}`}
          aria-labelledby={`${idPrefix}-tab-${tab.key}`}
          hidden={tab.key !== active}
        >
          {/* Troca de posição instantânea, não crossfade: o painel antigo já
              some no mesmo commit (React desmonta, não há AnimatePresence),
              então as duas abas nunca ocupam espaço ao mesmo tempo — sem
              isso, abas de altura bem diferente (Checklist vs Modelo)
              pulariam de layout durante a sobreposição. Só a entrada anima. */}
          {tab.key === active && (
            <motion.div
              key={tab.key}
              initial={shouldReduceMotion ? false : { opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: shouldReduceMotion ? 0.001 : 0.15, ease: EASE }}
            >
              {tab.content}
            </motion.div>
          )}
        </div>
      ))}
    </div>
  );
}

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
