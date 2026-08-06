import { useEffect } from "react";
import { Command } from "cmdk";
import { useDashboardStore } from "../store/dashboardStore";

// Painéis técnicos só existem no DOM quando mode === "technical" (drawer
// desmontado em Operador) — pular pra eles precisa trocar de modo primeiro,
// senão o scroll mira um elemento que não existe ainda.
const TECHNICAL_ONLY_IDS = new Set(["panel-checklist", "panel-overlay", "panel-risk-area", "panel-settings", "panel-model", "panel-alert-history"]);

const JUMP_TARGETS: { id: string; label: string }[] = [
  { id: "panel-video", label: "Vídeo" },
  { id: "panel-risk-score", label: "Tendência de risco" },
  { id: "panel-alerts", label: "Alertas ativos" },
  { id: "panel-compliance", label: "Conformidade" },
  { id: "panel-people", label: "Pessoas e detecções" },
  { id: "panel-timeline", label: "Linha do tempo" },
  { id: "panel-checklist", label: "Checklist pré-start (Técnico)" },
  { id: "panel-overlay", label: "Overlay do vídeo (Técnico)" },
  { id: "panel-risk-area", label: "Editor de área de risco (Técnico)" },
  { id: "panel-settings", label: "Configurações rápidas (Técnico)" },
  { id: "panel-model", label: "Modelo YOLO (Técnico)" },
  { id: "panel-alert-history", label: "Histórico de alertas (Técnico)" },
];

function scrollToPanel(id: string) {
  const el = document.getElementById(id);
  if (!el) return;
  el.scrollIntoView({ behavior: "smooth", block: "start" });
  el.classList.add("panel-jump-highlight");
  window.setTimeout(() => el.classList.remove("panel-jump-highlight"), 900);
}

/** Cmd/Ctrl+K — sempre acessível (não só modo Técnico): navegação de
 * teclado beneficia o operador tanto quanto o técnico, e o padrão
 * Linear/Raycast já é reconhecível por qualquer avaliador. */
export function CommandPalette() {
  const open = useDashboardStore((s) => s.commandPaletteOpen);
  const setOpen = useDashboardStore((s) => s.setCommandPaletteOpen);
  const mode = useDashboardStore((s) => s.mode);
  const setMode = useDashboardStore((s) => s.setMode);
  const running = useDashboardStore((s) => s.running);
  const start = useDashboardStore((s) => s.start);
  const stop = useDashboardStore((s) => s.stop);
  const muted = useDashboardStore((s) => s.muted);
  const toggleMuted = useDashboardStore((s) => s.toggleMuted);

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen(!useDashboardStore.getState().commandPaletteOpen);
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, []);

  const runAndClose = (fn: () => void) => {
    fn();
    setOpen(false);
  };

  const jumpTo = (id: string) => {
    if (TECHNICAL_ONLY_IDS.has(id) && mode !== "technical") setMode("technical");
    setOpen(false);
    // setTimeout, não requestAnimationFrame: rAF fica pausado em aba em
    // segundo plano (e o usuário pode ter aberto a paleta e trocado de aba
    // durante a animação do drawer técnico) — setTimeout dispara de
    // qualquer jeito. Espera o drawer técnico (AnimatePresence) montar.
    setTimeout(() => scrollToPanel(id), 50);
  };

  return (
    <Command.Dialog
      open={open}
      onOpenChange={setOpen}
      label="Paleta de comandos"
      overlayClassName="command-palette-overlay"
      contentClassName="command-palette"
    >
      <Command.Input placeholder="Buscar uma ação…" autoFocus />
      <Command.List>
        <Command.Empty>Nenhum resultado.</Command.Empty>
        <Command.Group heading="Modo">
          <Command.Item onSelect={() => runAndClose(() => setMode(mode === "operator" ? "technical" : "operator"))}>
            Trocar para modo {mode === "operator" ? "Técnico" : "Operador"}
          </Command.Item>
        </Command.Group>
        <Command.Group heading="Monitoramento">
          <Command.Item onSelect={() => runAndClose(() => (running ? stop() : start()).catch(console.error))}>
            {running ? "Parar monitoramento" : "Iniciar monitoramento"}
          </Command.Item>
          <Command.Item onSelect={() => runAndClose(toggleMuted)}>{muted ? "Ativar som de alertas" : "Silenciar som de alertas"}</Command.Item>
        </Command.Group>
        <Command.Group heading="Ir para">
          {JUMP_TARGETS.map((target) => (
            <Command.Item key={target.id} onSelect={() => jumpTo(target.id)}>
              {target.label}
            </Command.Item>
          ))}
        </Command.Group>
      </Command.List>
    </Command.Dialog>
  );
}
