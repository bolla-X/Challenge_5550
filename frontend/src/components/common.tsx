import { useRef } from "react";
import type { ReactNode } from "react";
import { motion, useReducedMotion } from "motion/react";

// Mesma curva de tokens.css (--ease-out).
const EASE = [0.23, 1, 0.32, 1] as const;

export interface TabItem {
  key: string;
  label: string;
  content: ReactNode;
}

/** Faixa de abas em pílula + painéis. Troca por seta e Home/End no teclado. */
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
                  transition={{ duration: shouldReduceMotion ? 0 : 0.16, ease: EASE }}
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
          {/* Troca instantânea de posição, só a entrada anima: o painel
              antigo já some no mesmo commit, então abas de altura diferente
              não pulam de layout durante a sobreposição. */}
          {tab.key === active && (
            <motion.div
              key={tab.key}
              initial={shouldReduceMotion ? false : { opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: shouldReduceMotion ? 0 : 0.16, ease: EASE }}
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

/** Chip de estado. Conforme usa --ok no ponto e no texto; falha usa o
 * tingimento de perigo; o resto fica neutro. */
export function Badge({ tone = "neutral", children }: { tone?: "neutral" | "ok" | "warn" | "error" | "info"; children: ReactNode }) {
  const cls = tone === "ok" ? "chip ok" : tone === "error" ? "chip miss" : "chip";
  return (
    <span className={cls}>
      {tone === "ok" && <span className="dot" />}
      {children}
    </span>
  );
}

export function EmptyState({ children }: { children: ReactNode }) {
  return <div className="empty-state">{children}</div>;
}

/** Placeholder dos primeiros segundos antes do bootstrap() resolver:
 * comunica "carregando", não "sem dados". Estático, sem brilho. */
export function PanelSkeleton({ lines = 3 }: { lines?: number }) {
  return (
    <div className="panel-skeleton" aria-hidden="true">
      {Array.from({ length: lines }).map((_, i) => (
        <div className={`skeleton-block skeleton-line ${i === lines - 1 ? "short" : ""}`.trim()} key={i} />
      ))}
    </div>
  );
}
