/** Marca. O logotipo é a palavra bem composta; o símbolo aparece pouco
 * (ícone da aba, tela de login). Cores vêm dos tokens, então acompanham o
 * tema; o favicon.svg em public/ repete o desenho com cores fixas porque
 * favicon não herda variável CSS. */

export function Mark({ size = 28 }: { size?: number }) {
  return (
    <svg className="brand-mark" width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="9" fill="var(--text)" />
      <rect x="9" y="10.5" width="14" height="11" rx="3" fill="none" stroke="var(--surface)" strokeWidth="1.8" />
      <circle cx="9" cy="10.5" r="2.6" fill="var(--danger)" />
    </svg>
  );
}

export function Wordmark() {
  return <span className="brand-wordmark">VisionEPI</span>;
}
