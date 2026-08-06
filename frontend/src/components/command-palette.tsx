import { useEffect } from "react";
import { Command } from "cmdk";
import { useDashboardStore, type ViewMode } from "../store/dashboardStore";
import { MODES } from "./layout";

// Alvo é o id do WRAPPER da aba (gerado por Tabs em common.tsx como
// `${idPrefix}-panel-${tabKey}`), não o id do Panel interno — o Panel só
// existe no DOM quando a aba dele está ativa (Fase 1: abas desmontam
// conteúdo inativo), então pular pra ele exige trocar de perfil E de aba
// antes de rolar, senão o alvo não existe ainda (bug corrigido na Fase 4:
// antes só trocava de modo, nunca de aba, e o getElementById voltava null
// sempre que a aba-alvo não era a ativa no momento).
type JumpTarget = { id: string; label: string; profile?: ViewMode; tabKey?: string };

const JUMP_TARGETS: JumpTarget[] = [
  { id: "panel-video", label: "Vídeo" },
  { id: "operator-panel-risk", label: "Tendência de risco", profile: "operator", tabKey: "risk" },
  { id: "operator-panel-alerts", label: "Alertas ativos", profile: "operator", tabKey: "alerts" },
  { id: "operator-panel-compliance", label: "Conformidade", profile: "operator", tabKey: "compliance" },
  { id: "operator-panel-people", label: "Pessoas e detecções", profile: "operator", tabKey: "people" },
  { id: "operator-panel-timeline", label: "Linha do tempo", profile: "operator", tabKey: "timeline" },
  { id: "technical-panel-checklist", label: "Checklist pré-start (Técnico)", profile: "technical", tabKey: "checklist" },
  { id: "technical-panel-overlay", label: "Overlay do vídeo (Técnico)", profile: "technical", tabKey: "overlay" },
  { id: "technical-panel-zone", label: "Editor de área de risco (Técnico)", profile: "technical", tabKey: "zone" },
  { id: "technical-panel-settings", label: "Configurações rápidas (Técnico)", profile: "technical", tabKey: "settings" },
  { id: "technical-panel-model", label: "Modelo YOLO (Técnico)", profile: "technical", tabKey: "model" },
  { id: "technical-panel-history", label: "Histórico de alertas (Técnico)", profile: "technical", tabKey: "history" },
  { id: "supervisor-panel-trend", label: "Tendência de risco (Supervisor)", profile: "supervisor", tabKey: "trend" },
  { id: "supervisor-panel-history", label: "Histórico de alertas (Supervisor)", profile: "supervisor", tabKey: "history" },
  { id: "supervisor-panel-export", label: "Exportação (Supervisor)", profile: "supervisor", tabKey: "export" },
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
  const setActiveTab = useDashboardStore((s) => s.setActiveTab);
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

  const jumpTo = (target: JumpTarget) => {
    if (target.profile && mode !== target.profile) setMode(target.profile);
    if (target.profile && target.tabKey) setActiveTab(target.profile, target.tabKey);
    setOpen(false);
    // setTimeout, não requestAnimationFrame: rAF fica pausado em aba em
    // segundo plano (e o usuário pode ter aberto a paleta e trocado de aba
    // durante a animação de fade da aba) — setTimeout dispara de qualquer
    // jeito. Espera o React montar a aba-alvo antes de tentar rolar até ela.
    setTimeout(() => scrollToPanel(target.id), 50);
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
        <Command.Group heading="Perfil">
          {MODES.filter((m) => m.key !== mode).map((m) => (
            <Command.Item key={m.key} onSelect={() => runAndClose(() => setMode(m.key))}>
              Mudar para perfil {m.label}
            </Command.Item>
          ))}
        </Command.Group>
        <Command.Group heading="Monitoramento">
          <Command.Item onSelect={() => runAndClose(() => (running ? stop() : start()).catch(console.error))}>
            {running ? "Parar monitoramento" : "Iniciar monitoramento"}
          </Command.Item>
          <Command.Item onSelect={() => runAndClose(toggleMuted)}>{muted ? "Ativar som de alertas" : "Silenciar som de alertas"}</Command.Item>
        </Command.Group>
        <Command.Group heading="Ir para">
          {JUMP_TARGETS.map((target) => (
            <Command.Item key={target.id} onSelect={() => jumpTo(target)}>
              {target.label}
            </Command.Item>
          ))}
        </Command.Group>
      </Command.List>
    </Command.Dialog>
  );
}
