import { useEffect, useId, useRef, useState } from "react";
import type { FormEvent, KeyboardEvent as TeclaReact } from "react";
import { createPortal } from "react-dom";
import { enviarFeedback, LIMITE_DE_TEXTO } from "../api/feedback";
import { useDashboardStore } from "../store/dashboardStore";
import { mensagemDeErro } from "../utils/erros";
import { inteiro } from "../utils/formato";
import { useFecharComEsc } from "../utils/teclado";
import "../styles/feedback.css";

/**
 * "Enviar feedback" (MISSÃO 4, Fase 3 item 11): diálogo curto aberto pelo menu da
 * barra superior. Grava só no servidor local (POST /api/feedback); o Supervisor lê
 * em /caixa-de-entrada. Esc fecha; o sucesso é anunciado numa região aria-live.
 */

/** Telas do espaço multi-câmera: o endereço é "/" para todas, então a tela vem do store. */
const ROTULO_DE_TELA: Record<string, string> = {
  "/grid": "Câmeras",
  "/focus": "Câmera em foco",
  "/kiosk": "Câmera do setor",
  "/overview": "Visão geral",
  "/home": "Início",
  "/accounts": "Contas",
  "/sobre": "Sobre",
  "/tv": "Modo TV",
  "/portal": "Portal de Entrada",
  "/desafio": "Você vs. a IA",
  "/gemeo": "Gêmeo digital",
  "/simulador": "Simulador",
  "/auditoria": "Auditoria",
  "/palco": "Apresentação",
  "/retrospectiva": "Retrospectiva",
  "/liga": "Liga de Setores",
  "/evacuacao": "Evacuação",
  "/torre": "Torre de luz",
  "/regras": "Editor de regras",
  "/permissoes": "Permissões de trabalho",
  "/primeiro-acesso": "Primeiro acesso",
  "/rotular": "Rotular recortes",
  "/caixa-de-entrada": "Caixa de entrada",
  "/produto": "Página do produto",
};

/** Onde a pessoa está agora, como caminho (o servidor guarda só isto, sem query). */
export function telaAtual(): string {
  const caminho = window.location.pathname.replace(/\/+$/, "") || "/";
  if (caminho !== "/" && caminho !== "/dashboard") return caminho;
  return `/${useDashboardStore.getState().screen}`;
}

/** Nome da tela para quem lê; caminho desconhecido volta como veio. */
export function rotuloDaTela(tela: string | null): string {
  if (!tela) return "Tela não informada";
  const base = "/" + (tela.split("/")[1] ?? "");
  return ROTULO_DE_TELA[tela] ?? ROTULO_DE_TELA[base] ?? tela;
}

export function FeedbackDialog({ aoFechar }: { aoFechar: () => void }) {
  const [texto, setTexto] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [enviado, setEnviado] = useState(false);
  const tela = useRef(telaAtual());
  const caixaRef = useRef<HTMLDivElement>(null);
  const fecharRef = useRef<HTMLButtonElement>(null);
  const titulo = useId();
  const ajuda = useId();

  useFecharComEsc(aoFechar);
  useEffect(() => {
    if (enviado) fecharRef.current?.focus();
  }, [enviado]);

  const vazio = !texto.trim();
  const enviar = (evento: FormEvent) => {
    evento.preventDefault();
    if (vazio || enviando) return;
    setEnviando(true);
    setErro(null);
    enviarFeedback(texto, tela.current)
      .then(() => setEnviado(true))
      .catch((e) => setErro(mensagemDeErro(e, "Falha ao enviar o feedback.")))
      .finally(() => setEnviando(false));
  };

  // O diálogo é modal: Tab e Shift+Tab ciclam dentro dele.
  const prenderFoco = (e: TeclaReact) => {
    if (e.key !== "Tab" || !caixaRef.current) return;
    const focaveis = [...caixaRef.current.querySelectorAll<HTMLElement>("textarea, button:not([disabled])")];
    if (!focaveis.length) return;
    const primeiro = focaveis[0];
    const ultimo = focaveis[focaveis.length - 1];
    if (e.shiftKey && document.activeElement === primeiro) {
      e.preventDefault();
      ultimo.focus();
    } else if (!e.shiftKey && document.activeElement === ultimo) {
      e.preventDefault();
      primeiro.focus();
    }
  };

  // Portal: a barra superior tem backdrop-filter, que prende elementos `position: fixed` à barra
  // em vez da janela. Sem o portal o fundo escurecido cobriria só a barra.
  return createPortal(
    <div className="modal-scrim" onClick={aoFechar}>
      <div
        ref={caixaRef}
        className="card modal feedback-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titulo}
        onClick={(e) => e.stopPropagation()}
        onKeyDown={prenderFoco}
        data-testid="feedback-dialogo"
      >
        <h2 id={titulo}>Enviar feedback</h2>
        {/* A região existe desde o início: leitor de tela só anuncia mudança numa região já presente. */}
        <div role="status" aria-live="polite" className="feedback-status" data-testid="feedback-status">
          {enviado && <p className="feedback-ok">Feedback enviado. Obrigado por ajudar a melhorar o VisionEPI.</p>}
        </div>

        {enviado ? (
          <div className="modal-acoes">
            <button type="button" className="primary" ref={fecharRef} onClick={aoFechar}>
              Fechar
            </button>
          </div>
        ) : (
          <form onSubmit={enviar} noValidate>
            <p id={ajuda} className="feedback-ajuda">
              Conte o que funcionou ou o que atrapalhou. A mensagem fica só neste servidor e é lida pelo Supervisor.
            </p>
            <label className="feedback-campo">
              <span>Sua mensagem</span>
              <textarea
                className="feedback-texto"
                value={texto}
                onChange={(e) => setTexto(e.target.value)}
                maxLength={LIMITE_DE_TEXTO}
                aria-describedby={ajuda}
                aria-invalid={erro ? true : undefined}
                autoFocus
                rows={6}
              />
            </label>
            <p className="feedback-contador">
              {inteiro(texto.length)} de {inteiro(LIMITE_DE_TEXTO)} caracteres
            </p>
            {erro && (
              <p className="feedback-erro" role="alert">
                {erro}
              </p>
            )}
            <div className="modal-acoes">
              <button type="button" className="ghost" onClick={aoFechar}>
                Cancelar
              </button>
              <button
                type="submit"
                className="primary"
                disabled={vazio || enviando}
                title={vazio ? "Escreva a mensagem para enviar" : undefined}
              >
                {enviando ? "Enviando…" : "Enviar"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>,
    document.body,
  );
}
