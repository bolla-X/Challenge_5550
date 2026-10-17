import { useEffect } from "react";

/** Fecha um diálogo com Esc. Todo modal do sistema usa isto (padrão de diálogo da WAI-ARIA). */
export function useFecharComEsc(aoFechar: () => void, ativo = true): void {
  useEffect(() => {
    if (!ativo) return;
    const tecla = (e: KeyboardEvent) => {
      if (e.key === "Escape") aoFechar();
    };
    window.addEventListener("keydown", tecla);
    return () => window.removeEventListener("keydown", tecla);
  }, [aoFechar, ativo]);
}
