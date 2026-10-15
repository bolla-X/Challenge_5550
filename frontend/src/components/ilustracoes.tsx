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
