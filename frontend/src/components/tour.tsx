import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { UserRole } from "../api/types";
import { useDashboardStore } from "../store/dashboardStore";
import { normalizar } from "../utils/busca";
import { useFecharComEsc } from "../utils/teclado";
import "../styles/tour.css";

/**
 * Tour guiado por tipo de conta: 3 a 5 passos curtos, cada um ancorado num
 * elemento que já existe na tela. Passo cujo alvo não está na tela é pulado, sem
 * quebrar. Pular ou concluir (e Esc) lembra que o tour já foi visto, por tipo de
 * conta, no localStorage. `reverTour()` apaga a marca e abre o tour de novo.
 *
 * Como ligar: `<TourGuiado />` uma vez, na casca da aplicação (ao lado de
 * `<CommandPalette />` em App.tsx): ele decide sozinho se mostra. E um botão
 * "Rever tour" que chama `reverTour()`.
 */

type Alvo = string | { seletor: string; texto: string };

export interface PassoDoTour {
  /** Seletores tentados em ordem; vale o primeiro elemento visível. `texto` filtra pelo texto do elemento. */
  alvos: Alvo[];
  titulo: string;
  texto: string;
}

export const PASSOS_DO_TOUR: Record<UserRole, PassoDoTour[]> = {
  operator: [
    {
      alvos: [".kiosk-banner"],
      titulo: "Como está a sua câmera",
      texto: "Este aviso diz se está tudo conforme. Quando há alerta, ele descreve o que o sistema viu.",
    },
    {
      alvos: [".kiosk-footer .actions"],
      titulo: "Os EPIs do setor",
      texto:
        "Cada EPI aparece conforme ou em falta. \"Indisponível\" quer dizer que o modelo atual não detecta aquele EPI. Não significa que está tudo certo.",
    },
    {
      alvos: [".kiosk-actions"],
      titulo: "O que fazer com um alerta",
      texto:
        "Avise a pessoa no local e toque em \"Avisei o colaborador\". Se o alerta foi engano, toque em \"Marcar falso positivo\".",
    },
    {
      alvos: ['.appbar button[aria-pressed][aria-label*="som de alertas"]'],
      titulo: "Som dos alertas",
      texto: "Silencie ou ative o som dos alertas. A escolha fica salva para o seu tipo de conta.",
    },
    {
      alvos: ['[aria-label="Ajuda sobre esta tela"]'],
      titulo: "Ajuda em cada tela",
      texto: "O botão ? abre, em outra aba, o artigo que explica a tela em que você está.",
    },
  ],
  technical: [
    {
      alvos: [{ seletor: ".appbar-secundarios button", texto: "Buscar" }],
      titulo: "Busca em qualquer tela",
      texto:
        "Ctrl K abre a busca: câmeras, incidentes, regras, permissões, telas e artigos de ajuda. Digite \"pessoa 12\" para achar a câmera onde esse ID de rastreio está num incidente ativo.",
    },
    {
      alvos: [".camera-grid"],
      titulo: "Suas câmeras",
      texto:
        "Cada cartão mostra a imagem, o estado e os incidentes ativos. Clique num cartão para abrir a câmera e configurá-la.",
    },
    {
      alvos: [".video-card"],
      titulo: "O vídeo e o Raio-X",
      texto:
        "A imagem ao vivo da câmera. Se o sistema perceber câmera tampada, movida ou sem foco, um selo aparece aqui com o botão Redefinir referência. A tecla X liga o Raio-X: o que o modelo viu e o que o sistema decidiu.",
    },
    {
      alvos: [".tabs-list"],
      titulo: "As abas da câmera",
      texto:
        "As mais usadas ficam à vista, como Alertas, Conformidade e Pessoas. O resto está em Mais: Zona, Planta, Portaria e a configuração da câmera.",
    },
    {
      alvos: ['.appbar-secundarios a[href="/relatorio/turno"]'],
      titulo: "Relatório do turno",
      texto: "Os números do turno, prontos para imprimir ou salvar em PDF. Abre em outra aba.",
    },
  ],
  supervisor: [
    {
      alvos: [".home-agora"],
      titulo: "A planta agora",
      texto: "Câmeras no ar, pessoas, incidentes ativos e o nível da planta. Tudo por setor, nunca por pessoa.",
    },
    {
      alvos: [".aviso-primeiro-acesso"],
      titulo: "Falta configurar a planta?",
      texto: "O assistente leva da primeira câmera ao \"pronto para operar\". Você pode pular e voltar depois.",
    },
    {
      alvos: [".home-tile-cameras"],
      titulo: "Câmeras",
      texto: "Abra a grade para ver os incidentes, as zonas e a portaria de cada câmera.",
    },
    {
      alvos: ['.home-bento a.home-tile[href="/auditoria"]'],
      titulo: "Cadeia de custódia",
      texto: "Confira se alguma evidência foi alterada depois de gravada.",
    },
    {
      alvos: [{ seletor: ".home-bento button.home-tile", texto: "Contas" }],
      titulo: "Contas da equipe",
      texto: "Crie as contas do Operador, do Técnico e de outros Supervisores. O Operador vê só a câmera do setor dele.",
    },
  ],
};

// ---- "já viu" ----------------------------------------------------------------

/** Chave do localStorage de cada tipo de conta (exportada para testes e para quem precisa pular o tour). */
export const chaveDoTour = (papel: UserRole) => `visionepi-tour-visto-${papel}`;
/** Evento que `reverTour()` dispara e `TourGuiado` escuta. */
export const EVENTO_REVER_TOUR = "visionepi:rever-tour";

// Sem localStorage (janela privada, dados do site bloqueados) o tour ainda não
// volta durante esta visita: a marca fica na memória da página.
const vistosNestaPagina = new Set<UserRole>();

function jaViu(papel: UserRole): boolean {
  if (vistosNestaPagina.has(papel)) return true;
  try {
    return localStorage.getItem(chaveDoTour(papel)) === "1";
  } catch {
    return false;
  }
}

function marcarVisto(papel: UserRole): void {
  vistosNestaPagina.add(papel);
  try {
    localStorage.setItem(chaveDoTour(papel), "1");
  } catch {
    // Sem localStorage: vale só até recarregar a página.
  }
}

function esquecer(papel: UserRole): void {
  vistosNestaPagina.delete(papel);
  try {
    localStorage.removeItem(chaveDoTour(papel));
  } catch {
    // Nada a apagar.
  }
}

/** Botão "Rever tour": apaga a marca do tipo de conta atual e abre o tour de novo. */
export function reverTour(): void {
  const papel = useDashboardStore.getState().user?.role;
  if (papel) esquecer(papel);
  window.dispatchEvent(new CustomEvent(EVENTO_REVER_TOUR));
}

// ---- alvos -------------------------------------------------------------------

function visivel(el: Element): boolean {
  const r = el.getBoundingClientRect();
  return r.width > 0 && r.height > 0;
}

function acharAlvo(alvos: Alvo[]): HTMLElement | null {
  for (const alvo of alvos) {
    const seletor = typeof alvo === "string" ? alvo : alvo.seletor;
    const texto = typeof alvo === "string" ? null : normalizar(alvo.texto);
    let candidatos: NodeListOf<HTMLElement>;
    try {
      candidatos = document.querySelectorAll<HTMLElement>(seletor);
    } catch {
      continue;
    }
    for (const el of candidatos) {
      if (!visivel(el)) continue;
      if (texto && !normalizar(el.textContent ?? "").includes(texto)) continue;
      return el;
    }
  }
  return null;
}

/** Índice do primeiro passo, a partir de `desde`, cujo alvo está na tela agora; -1 se não há. */
function proximoDisponivel(passos: PassoDoTour[], desde: number): number {
  for (let i = desde; i < passos.length; i += 1) if (acharAlvo(passos[i].alvos)) return i;
  return -1;
}

function contarDisponiveis(passos: PassoDoTour[], desde: number): number {
  let n = 0;
  for (let i = desde; i < passos.length; i += 1) if (acharAlvo(passos[i].alvos)) n += 1;
  return n;
}

function reduzirMovimento(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

// ---- posição -----------------------------------------------------------------

const MARGEM = 12;
const FOLGA = 6; // o anel fica um pouco maior que o alvo
const LARGURA_PADRAO = 320;
const ALTURA_PADRAO = 200;

interface Caixa {
  anel: { top: number; left: number; width: number; height: number };
  cartao: { top: number; left: number };
}

function calcular(alvo: DOMRect, largura: number, altura: number): Caixa {
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const cabeAbaixo = alvo.bottom + FOLGA + MARGEM + altura <= vh - MARGEM;
  const cabeAcima = alvo.top - FOLGA - MARGEM - altura >= MARGEM;
  // Alvo grande (a grade inteira): sem espaço fora dele, o cartão fica no pé da janela.
  const topo = cabeAbaixo
    ? alvo.bottom + FOLGA + MARGEM
    : cabeAcima
      ? alvo.top - FOLGA - MARGEM - altura
      : Math.max(MARGEM, vh - altura - MARGEM);
  const esquerda = Math.min(Math.max(MARGEM, alvo.left), Math.max(MARGEM, vw - largura - MARGEM));
  return {
    anel: {
      top: Math.round(alvo.top - FOLGA),
      left: Math.round(alvo.left - FOLGA),
      width: Math.round(alvo.width + FOLGA * 2),
      height: Math.round(alvo.height + FOLGA * 2),
    },
    cartao: { top: Math.round(topo), left: Math.round(esquerda) },
  };
}

function mesmaCaixa(a: Caixa | null, b: Caixa): boolean {
  return (
    a !== null &&
    a.anel.top === b.anel.top &&
    a.anel.left === b.anel.left &&
    a.anel.width === b.anel.width &&
    a.anel.height === b.anel.height &&
    a.cartao.top === b.cartao.top &&
    a.cartao.left === b.cartao.left
  );
}

// ---- um passo na tela --------------------------------------------------------

function PassoNaTela({
  passo,
  posicao,
  total,
  ultimo,
  aoAvancar,
  aoPular,
  aoSumirOAlvo,
}: {
  passo: PassoDoTour;
  posicao: number;
  total: number;
  ultimo: boolean;
  aoAvancar: () => void;
  aoPular: () => void;
  aoSumirOAlvo: () => void;
}) {
  const id = useId();
  const cartaoRef = useRef<HTMLDivElement>(null);
  const avancarRef = useRef<HTMLButtonElement>(null);
  const [caixa, setCaixa] = useState<Caixa | null>(null);
  const sumiu = useRef(false);

  const medir = useCallback(() => {
    const alvo = acharAlvo(passo.alvos);
    if (!alvo) {
      if (!sumiu.current) {
        sumiu.current = true;
        aoSumirOAlvo();
      }
      return;
    }
    const cartao = cartaoRef.current;
    const nova = calcular(alvo.getBoundingClientRect(), cartao?.offsetWidth ?? LARGURA_PADRAO, cartao?.offsetHeight ?? ALTURA_PADRAO);
    setCaixa((atual) => (mesmaCaixa(atual, nova) ? atual : nova));
  }, [passo, aoSumirOAlvo]);

  // Traz o alvo para a janela (só se ele está fora dela) e mede antes de pintar.
  useLayoutEffect(() => {
    sumiu.current = false;
    const alvo = acharAlvo(passo.alvos);
    if (alvo) {
      const r = alvo.getBoundingClientRect();
      if (r.bottom <= 0 || r.top >= window.innerHeight) {
        alvo.scrollIntoView({ block: "center", inline: "nearest", behavior: reduzirMovimento() ? "auto" : "smooth" });
      }
    }
    medir();
  }, [passo, medir]);

  // Acompanha rolagem, redimensionamento e mudança de layout (o alvo pode se mexer).
  useEffect(() => {
    let quadro = 0;
    const agendar = () => {
      cancelAnimationFrame(quadro);
      quadro = requestAnimationFrame(medir);
    };
    window.addEventListener("resize", agendar);
    window.addEventListener("scroll", agendar, true);
    const intervalo = window.setInterval(medir, 400);
    return () => {
      cancelAnimationFrame(quadro);
      window.removeEventListener("resize", agendar);
      window.removeEventListener("scroll", agendar, true);
      window.clearInterval(intervalo);
    };
  }, [medir]);

  // O foco entra no cartão ao abrir. Nos passos seguintes ele já está no botão.
  useEffect(() => {
    avancarRef.current?.focus();
  }, []);

  // Tab fica dentro do cartão.
  const aoTeclar = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== "Tab") return;
    const botoes = Array.from(cartaoRef.current?.querySelectorAll<HTMLElement>("button:not(:disabled)") ?? []);
    if (!botoes.length) return;
    const primeiro = botoes[0];
    const ultimoBotao = botoes[botoes.length - 1];
    if (e.shiftKey && document.activeElement === primeiro) {
      e.preventDefault();
      ultimoBotao.focus();
    } else if (!e.shiftKey && document.activeElement === ultimoBotao) {
      e.preventDefault();
      primeiro.focus();
    }
  };

  return createPortal(
    <div className="tour" data-testid="tour">
      {caixa && (
        <div
          className="tour-anel"
          aria-hidden="true"
          style={{ top: caixa.anel.top, left: caixa.anel.left, width: caixa.anel.width, height: caixa.anel.height }}
        />
      )}
      <div
        ref={cartaoRef}
        className="tour-cartao"
        role="dialog"
        aria-modal="true"
        aria-labelledby={`${id}-titulo`}
        aria-describedby={`${id}-texto`}
        onKeyDown={aoTeclar}
        style={caixa ? { top: caixa.cartao.top, left: caixa.cartao.left } : { visibility: "hidden" }}
      >
        <div className="tour-topo">
          <p className="tour-passo" data-testid="tour-passo">
            Passo {posicao} de {total}
          </p>
          <p className="tour-esc">
            <kbd>Esc</kbd> fecha
          </p>
        </div>
        <h2 id={`${id}-titulo`}>{passo.titulo}</h2>
        <p id={`${id}-texto`}>{passo.texto}</p>
        <div className="tour-acoes">
          <button type="button" className="ghost small" onClick={aoPular} data-testid="tour-pular">
            Pular tour
          </button>
          <button type="button" className="primary small" onClick={aoAvancar} ref={avancarRef} data-testid="tour-proximo">
            {ultimo ? "Concluir" : "Próximo"}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}

// ---- o tour ------------------------------------------------------------------

export function TourGuiado() {
  const papel = useDashboardStore((s) => s.user?.role ?? null);
  const showMessage = useDashboardStore((s) => s.showMessage);
  const [passos, setPassos] = useState<PassoDoTour[] | null>(null);
  const [indice, setIndice] = useState(0);
  const [vistos, setVistos] = useState(1);
  const focoAnterior = useRef<Element | null>(null);

  /** Abre o tour do tipo de conta pelo primeiro passo que tem alvo na tela. `false` se nenhum tem. */
  const abrir = useCallback((doPapel: UserRole): boolean => {
    const lista = PASSOS_DO_TOUR[doPapel];
    const primeiro = proximoDisponivel(lista, 0);
    if (primeiro < 0) return false;
    focoAnterior.current = document.activeElement;
    setPassos(lista);
    setIndice(primeiro);
    setVistos(1);
    return true;
  }, []);

  const fechar = useCallback(() => {
    if (papel) marcarVisto(papel);
    setPassos(null);
    const voltar = focoAnterior.current;
    focoAnterior.current = null;
    if (voltar instanceof HTMLElement && document.contains(voltar)) voltar.focus();
  }, [papel]);

  // Primeira visita: espera a tela montar e abre quando houver alvo (a tela carrega dados antes de desenhar).
  useEffect(() => {
    if (!papel) {
      setPassos(null);
      return undefined;
    }
    if (jaViu(papel)) return undefined;
    let tentativas = 0;
    let temporizador = window.setTimeout(function tentar() {
      if (abrir(papel)) return;
      tentativas += 1;
      if (tentativas < 20) temporizador = window.setTimeout(tentar, 500);
    }, 800);
    return () => window.clearTimeout(temporizador);
  }, [papel, abrir]);

  // "Rever tour".
  useEffect(() => {
    const aoPedir = () => {
      const atual = useDashboardStore.getState().user?.role;
      if (!atual) return;
      if (!abrir(atual)) {
        showMessage("Não há o que mostrar nesta tela. Volte ao Início ou às câmeras e peça o tour de novo.", "warning");
      }
    };
    window.addEventListener(EVENTO_REVER_TOUR, aoPedir);
    return () => window.removeEventListener(EVENTO_REVER_TOUR, aoPedir);
  }, [abrir, showMessage]);

  useFecharComEsc(fechar, passos !== null);

  const avancar = useCallback(() => {
    if (!passos) return;
    const proximo = proximoDisponivel(passos, indice + 1);
    if (proximo < 0) {
      fechar();
      return;
    }
    setIndice(proximo);
    setVistos((n) => n + 1);
  }, [passos, indice, fechar]);

  if (!passos) return null;
  const restantes = contarDisponiveis(passos, indice + 1);
  return (
    <PassoNaTela
      passo={passos[indice]}
      posicao={vistos}
      total={vistos + restantes}
      ultimo={restantes === 0}
      aoAvancar={avancar}
      aoPular={fechar}
      aoSumirOAlvo={avancar}
    />
  );
}

export default TourGuiado;
