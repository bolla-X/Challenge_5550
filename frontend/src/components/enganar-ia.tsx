import { useEffect, useRef, useState } from "react";
import type { PortalItem, PortalState } from "../api/types";
import { PPE_LABELS } from "../api/ppe";

/**
 * "Tente enganar a IA" (X9): modo desafio do Portal. O visitante diz o que vai
 * tentar (boné no lugar do capacete etc.), tem alguns segundos diante da
 * câmera e o sistema mostra o que detectou e por quê. O placar é anônimo e
 * só desta sessão do navegador — e mostra com honestidade quando a IA é
 * enganada (e quando ela erra com o EPI de verdade).
 */

type Tentativa = { chave: string; rotulo: string; falsa: boolean };
const TENTATIVAS: Tentativa[] = [
  { chave: "bone", rotulo: "Boné no lugar do capacete", falsa: true },
  { chave: "colete", rotulo: "Peça colorida no lugar do colete", falsa: true },
  { chave: "nada", rotulo: "Sem nenhum EPI", falsa: true },
  { chave: "real", rotulo: "Com os EPIs de verdade (prova)", falsa: false },
];
const DURACAO_S = 8;
type Placar = { tentativas: number; enganaram: number; pegas: number; erros_com_epi_real: number };
const PLACAR_VAZIO: Placar = { tentativas: 0, enganaram: 0, pegas: 0, erros_com_epi_real: 0 };
const CHAVE = "visionepi-placar-enganar";

function lerPlacar(): Placar {
  try {
    return { ...PLACAR_VAZIO, ...JSON.parse(sessionStorage.getItem(CHAVE) || "{}") };
  } catch {
    return PLACAR_VAZIO;
  }
}

function salvarPlacar(p: Placar) {
  try {
    sessionStorage.setItem(CHAVE, JSON.stringify(p));
  } catch {
    // sem sessionStorage: o placar vale só enquanto a tela estiver aberta
  }
}

type Resultado = { tentativa: Tentativa; liberado: boolean; itens: PortalItem[] };

function nome(item: PortalItem) {
  return PPE_LABELS[item.key as keyof typeof PPE_LABELS] ?? item.key;
}

function veredito(r: Resultado): { titulo: string; classe: string; texto: string } {
  const confirmados = r.itens.filter((i) => i.estado === "confirmado");
  const faltando = r.itens.filter((i) => i.estado === "faltando");
  if (r.tentativa.falsa && r.liberado) {
    const enganado = confirmados[0];
    return {
      titulo: "Você enganou a IA",
      classe: "enganou",
      texto: enganado
        ? `O sistema confirmou “${nome(enganado)}”: ${enganado.explicacao ?? "detectado"}. É exatamente o tipo de caso que vai para a fila de rótulos e melhora o modelo.`
        : "O sistema liberou. Registramos a falha com honestidade.",
    };
  }
  if (r.tentativa.falsa) {
    const pego = faltando[0];
    return {
      titulo: "A IA pegou",
      classe: "pegou",
      texto: pego ? `Faltou “${nome(pego)}”: ${pego.explicacao ?? "não detectado"}.` : "O sistema não liberou a entrada.",
    };
  }
  if (r.liberado) return { titulo: "Liberado corretamente", classe: "pegou", texto: "Todos os EPIs exigidos foram confirmados." };
  const falha = faltando[0];
  return {
    titulo: "A IA errou com o EPI de verdade",
    classe: "enganou",
    texto: falha ? `Não confirmou “${nome(falha)}”: ${falha.explicacao ?? "não detectado"}. Falso negativo — fica registrado.` : "Não liberou mesmo com os EPIs.",
  };
}

export function EnganarIA({ portal }: { portal: PortalState | null }) {
  const [escolha, setEscolha] = useState<Tentativa>(TENTATIVAS[0]);
  const [restante, setRestante] = useState<number | null>(null);
  const [resultado, setResultado] = useState<Resultado | null>(null);
  const [placar, setPlacar] = useState<Placar>(lerPlacar);
  const liberouRef = useRef(false);
  const itensRef = useRef<PortalItem[]>([]);

  // Durante a tentativa, guarda se o portal chegou a liberar e os itens do último estado.
  useEffect(() => {
    if (restante === null || !portal) return;
    if (portal.verdict === "approved") liberouRef.current = true;
    if (portal.itens.length) itensRef.current = portal.itens;
  }, [portal, restante]);

  useEffect(() => {
    if (restante === null) return undefined;
    if (restante <= 0) {
      const r: Resultado = { tentativa: escolha, liberado: liberouRef.current, itens: itensRef.current };
      setResultado(r);
      setRestante(null);
      const novo = { ...placar, tentativas: placar.tentativas + 1 };
      if (escolha.falsa && r.liberado) novo.enganaram += 1;
      else if (escolha.falsa) novo.pegas += 1;
      else if (!r.liberado) novo.erros_com_epi_real += 1;
      setPlacar(novo);
      salvarPlacar(novo);
      return undefined;
    }
    const id = window.setTimeout(() => setRestante((s) => (s === null ? null : s - 1)), 1000);
    return () => window.clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [restante]);

  const comecar = () => {
    liberouRef.current = false;
    itensRef.current = [];
    setResultado(null);
    setRestante(DURACAO_S);
  };
  const v = resultado ? veredito(resultado) : null;

  return (
    <section className="enganar card" aria-label="Tente enganar a IA" data-testid="enganar">
      <header>
        <h2>Tente enganar a IA</h2>
        <p className="muted">Escolha o que vai tentar, fique diante da câmera e veja o que o sistema viu — com o Raio-X ligado.</p>
      </header>
      <div className="enganar-opcoes" role="radiogroup" aria-label="O que você vai tentar">
        {TENTATIVAS.map((t) => (
          <button
            key={t.chave}
            type="button"
            role="radio"
            aria-checked={escolha.chave === t.chave}
            className={`chip-toggle ${escolha.chave === t.chave ? "on" : ""}`}
            disabled={restante !== null}
            onClick={() => setEscolha(t)}
            data-testid={`enganar-${t.chave}`}
          >
            {t.rotulo}
          </button>
        ))}
      </div>
      {restante !== null ? (
        <p className="enganar-contagem t-data" role="status" data-testid="enganar-contagem">
          Valendo… {restante} s
        </p>
      ) : (
        <button type="button" className="primary" onClick={comecar} data-testid="enganar-comecar">
          Valendo! ({DURACAO_S} s)
        </button>
      )}
      {v && (
        <div className={`enganar-resultado ${v.classe}`} role="status" data-testid="enganar-resultado" data-resultado={v.classe}>
          <strong>{v.titulo}</strong>
          <p>{v.texto}</p>
        </div>
      )}
      <dl className="enganar-placar" data-testid="enganar-placar">
        <div>
          <dt>Tentativas</dt>
          <dd className="t-data">{placar.tentativas}</dd>
        </div>
        <div>
          <dt>Enganaram a IA</dt>
          <dd className="t-data">{placar.enganaram}</dd>
        </div>
        <div>
          <dt>Pegas</dt>
          <dd className="t-data">{placar.pegas}</dd>
        </div>
        <div>
          <dt>Erros com EPI real</dt>
          <dd className="t-data">{placar.erros_com_epi_real}</dd>
        </div>
      </dl>
      <p className="muted">Placar anônimo, só desta sessão. Nenhuma foto é salva.</p>
    </section>
  );
}
