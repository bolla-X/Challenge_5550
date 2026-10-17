/**
 * Ilustrações originais dos estados vazios (desenho do projeto, traço fino na
 * cor terciária do texto, um único detalhe na cor de interação). Sem foto, sem
 * pessoa realista: o assunto é a planta, a câmera, a evidência.
 */
type Props = { className?: string };

const COMUM = {
  viewBox: "0 0 160 112",
  fill: "none",
  role: "presentation" as const,
  "aria-hidden": true,
  className: "ilustracao",
};

/** Câmera sem imagem ainda: aguardando a primeira análise. */
export function IlustracaoCamera({ className }: Props) {
  return (
    <svg {...COMUM} className={`ilustracao ${className ?? ""}`}>
      <rect x="34" y="30" width="72" height="50" rx="12" className="tr" />
      <path d="M106 46l20-11v42l-20-11" className="tr" />
      <circle cx="70" cy="55" r="13" className="tr" />
      <circle cx="70" cy="55" r="4" className="destaque" />
      <path d="M22 92h116" className="tr fino" />
    </svg>
  );
}

/** Planta vista de cima, sem ninguém nela. */
export function IlustracaoPlanta({ className }: Props) {
  return (
    <svg {...COMUM} className={`ilustracao ${className ?? ""}`}>
      <rect x="18" y="18" width="124" height="76" rx="8" className="tr" />
      <path d="M62 18v40M62 76v18M100 58h42M18 58h26" className="tr fino" />
      <rect x="104" y="24" width="32" height="26" rx="4" className="zona" />
      <circle cx="44" cy="40" r="3" className="destaque" />
    </svg>
  );
}

/** Lista vazia de incidentes: escudo com o traço de "tudo certo". */
export function IlustracaoEscudo({ className }: Props) {
  return (
    <svg {...COMUM} className={`ilustracao ${className ?? ""}`}>
      <path d="M80 14l34 12v26c0 22-14 38-34 46-20-8-34-24-34-46V26z" className="tr" />
      <path d="M66 56l10 10 20-22" className="destaque-traco" />
    </svg>
  );
}

/** Cadeia de custódia ainda sem elo: três elos encadeados, o último em aberto. */
export function IlustracaoCadeia({ className }: Props) {
  return (
    <svg {...COMUM} className={`ilustracao ${className ?? ""}`}>
      <rect x="18" y="44" width="40" height="24" rx="12" className="tr" />
      <rect x="60" y="44" width="40" height="24" rx="12" className="tr" />
      <rect x="102" y="44" width="40" height="24" rx="12" className="tr tracejado" />
      <path d="M50 56h18M92 56h18" className="destaque-traco" />
    </svg>
  );
}

/** Gráfico sem dado: eixos e uma linha de base. */
export function IlustracaoGrafico({ className }: Props) {
  return (
    <svg {...COMUM} className={`ilustracao ${className ?? ""}`}>
      <path d="M26 18v72h112" className="tr" />
      <path d="M38 78h14v-18H38zM62 78h14V48H62zM86 78h14V64H86z" className="tr fino" />
      <path d="M110 78h14V36h-14z" className="zona" />
      <path d="M30 90h104" className="tr fino" />
    </svg>
  );
}

/** Página que não existe: a planta com um caminho tracejado que termina em lugar nenhum. */
export function IlustracaoCaminhoPerdido({ className }: Props) {
  return (
    <svg {...COMUM} className={`ilustracao ${className ?? ""}`}>
      <rect x="18" y="18" width="124" height="76" rx="8" className="tr fino" />
      <path d="M36 74c14 0 18-22 32-22s14 14 28 14" className="tr tracejado" />
      <circle cx="36" cy="74" r="3.5" className="tr" />
      <circle cx="112" cy="62" r="11" className="tr tracejado" />
      <circle cx="112" cy="62" r="3" className="destaque" />
    </svg>
  );
}

/** Tela que falhou ao desenhar: o painel rachado por um traço de interrupção. */
export function IlustracaoTelaComFalha({ className }: Props) {
  return (
    <svg {...COMUM} className={`ilustracao ${className ?? ""}`}>
      <rect x="30" y="20" width="100" height="64" rx="10" className="tr" />
      <path d="M62 94h36M80 84v10" className="tr fino" />
      <path d="M86 20l-10 18 14 8-10 22" className="destaque-traco" />
    </svg>
  );
}

/** Sem rede: três arcos de sinal e o corte na diagonal. */
export function IlustracaoSemSinal({ className }: Props) {
  return (
    <svg {...COMUM} className={`ilustracao ${className ?? ""}`}>
      <path d="M40 54a56 56 0 0 1 80 0" className="tr fino" />
      <path d="M54 68a36 36 0 0 1 52 0" className="tr" />
      <path d="M68 82a16 16 0 0 1 24 0" className="tr" />
      <circle cx="80" cy="94" r="3" className="destaque" />
      <path d="M46 24l68 76" className="destaque-traco" />
    </svg>
  );
}

/** Sessão que acabou: relógio com o ponteiro parado perto do fim. */
export function IlustracaoSessao({ className }: Props) {
  return (
    <svg {...COMUM} className={`ilustracao ${className ?? ""}`}>
      <circle cx="80" cy="56" r="34" className="tr" />
      <path d="M80 30v4M80 78v4M54 56h4M102 56h4" className="tr fino" />
      <path d="M80 56V38" className="tr" />
      <path d="M80 56l14 8" className="destaque-traco" />
      <circle cx="80" cy="56" r="3" className="destaque" />
    </svg>
  );
}

/** Acesso negado: cadeado fechado, com a chave de outro tipo de conta. */
export function IlustracaoCadeado({ className }: Props) {
  return (
    <svg {...COMUM} className={`ilustracao ${className ?? ""}`}>
      <rect x="52" y="48" width="56" height="42" rx="9" className="tr" />
      <path d="M64 48V38a16 16 0 0 1 32 0v10" className="tr" />
      <circle cx="80" cy="66" r="4" className="destaque" />
      <path d="M80 70v8" className="destaque-traco" />
    </svg>
  );
}

/** Fila de recortes vazia: cartões empilhados. */
export function IlustracaoFila({ className }: Props) {
  return (
    <svg {...COMUM} className={`ilustracao ${className ?? ""}`}>
      <rect x="44" y="20" width="72" height="54" rx="8" className="tr fino" />
      <rect x="36" y="30" width="72" height="54" rx="8" className="tr" />
      <path d="M52 64l14-14 10 10 8-8 12 12" className="destaque-traco" />
    </svg>
  );
}
