import "../styles/onboarding.css";
import { useCallback, useEffect, useState } from "react";
import { ApiError, apiFetch } from "../api/client";
import type { AuthUser, UserRole } from "../api/types";
import { useDashboardStore } from "../store/dashboardStore";
import { mensagemDeErro } from "../utils/erros";
import { pluralizar } from "../utils/formato";
import { Badge, EmptyState, PanelSkeleton } from "./common";
import { IconeAviso, IconeOk } from "./icones";
import { ROTULO_DO_PAPEL, ScreenHead } from "./layout";

/**
 * Primeiro acesso do supervisor (MISSÃO 4, Fase 3): um assistente que leva às
 * ferramentas que já existem. O estado (marcado, pulado, detectado) vive no
 * servidor (app/services/onboarding.py), então fechar a aba e voltar retoma de
 * onde parou. O que o checklist "Pronto para operar" mostra é o que o servidor
 * DETECTOU, nunca o que foi só marcado à mão.
 */

export type PassoId = "camera" | "referencia" | "planta" | "zonas" | "epis" | "usuarios" | "pronto";
export type MarcaDoPasso = "pendente" | "feito" | "pulado";

export type PassoDoServidor = {
  passo: PassoId;
  /** O que vale: o detectado vence a marcação. */
  estado: MarcaDoPasso;
  marcado: MarcaDoPasso;
  detectado: boolean | null;
  detalhe: string | null;
};
export type ItemDoChecklist = { passo: PassoId; ok: boolean; detalhe: string };
export type EstadoDoOnboarding = {
  passos: PassoDoServidor[];
  ordem: PassoId[];
  proximo_passo: PassoId | null;
  progresso: { total: number; feitos: number; pulados: number; resolvidos: number };
  checklist: { itens: ItemDoChecklist[]; pendentes: number; pronto_para_operar: boolean };
  concluido: boolean;
  concluido_em: string | null;
  atualizado_em: string | null;
  atualizado_por: string | null;
};

const URL_BASE = "/api/onboarding";

type Destino = "grid" | "focus";

/**
 * Leva a uma tela da aplicação principal. `/primeiro-acesso` é uma rota própria
 * (como `/evacuacao`), fora da troca de telas do store: sem trocar o endereço, a
 * tela escolhida mudaria no store e o assistente continuaria à vista.
 */
function irPara(destino: Destino, cameraId?: number): void {
  const { setCamId, setScreen } = useDashboardStore.getState();
  if (cameraId !== undefined) setCamId(cameraId);
  window.history.replaceState(null, "", "/");
  setScreen(destino);
}

function irParaCamera(): void {
  const { cameras, camId } = useDashboardStore.getState();
  const alvo = cameras.find((c) => c.id === camId) ?? cameras[0];
  if (alvo) irPara("focus", alvo.id);
  else irPara("grid");
}

export type InfoDoPasso = { titulo: string; porque: string; dica?: string; acao?: { rotulo: string; ir: () => void } };

export const INFO: Record<PassoId, InfoDoPasso> = {
  camera: {
    titulo: "Cadastrar uma câmera",
    porque: "Sem câmera cadastrada não há imagem para analisar. Comece pela que cobre a área mais crítica.",
    dica: "Na grade, use Adicionar câmera e escolha USB, RTSP, arquivo ou celular.",
    acao: { rotulo: "Abrir as câmeras", ir: () => irPara("grid") },
  },
  referencia: {
    titulo: "Capturar a imagem de referência",
    porque: "É com ela que o sistema percebe câmera tampada, movida ou sem foco.",
    dica:
      "Ligue a câmera com a cena em ordem: a referência é capturada sozinha na primeira imagem boa. Se a câmera for reposicionada depois, use Redefinir referência, que aparece sobre o vídeo quando o sistema acusa problema na imagem.",
    acao: { rotulo: "Abrir a câmera", ir: irParaCamera },
  },
  planta: {
    titulo: "Calibrar a planta",
    porque: "Com a planta calibrada, o gêmeo digital e o Modo Evacuação mostram onde cada pessoa está.",
    dica: "Na tela da câmera, abra a aba Planta (em Mais): clique 4 pontos no chão do vídeo e os mesmos 4 na planta, na mesma ordem.",
    acao: { rotulo: "Abrir a câmera", ir: irParaCamera },
  },
  zonas: {
    titulo: "Desenhar a área de risco",
    porque: "Sem uma área própria, a câmera usa a área padrão do sistema, que raramente coincide com o seu chão de fábrica.",
    dica: "Na tela da câmera, abra a aba Zona (em Mais), desenhe o polígono sobre o vídeo e salve.",
    acao: { rotulo: "Abrir a câmera", ir: irParaCamera },
  },
  epis: {
    titulo: "Definir os EPIs exigidos",
    porque: "A Portaria libera ou nega a entrada pelos EPIs que você exigir. Sem isso, nada é cobrado na entrada.",
    dica: "Na tela da câmera, abra a aba Portaria (em Mais) e escolha os EPIs obrigatórios daquele setor.",
    acao: { rotulo: "Abrir a câmera", ir: irParaCamera },
  },
  usuarios: {
    titulo: "Criar as contas da equipe",
    porque: "Cada pessoa entra com a própria conta: o Operador vê só a câmera do setor, o Técnico configura.",
  },
  pronto: {
    titulo: "Pronto para operar",
    porque: "Esta é a conferência final, feita com o que o sistema encontrou de verdade.",
  },
};

// ----------------------------------------------------------------- dados --
export function useOnboarding() {
  const [dados, setDados] = useState<EstadoDoOnboarding | null>(null);
  const [erro, setErro] = useState<{ msg: string; status?: number } | null>(null);
  const [falha, setFalha] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [n, setN] = useState(0);

  useEffect(() => {
    let vivo = true;
    apiFetch<EstadoDoOnboarding>(URL_BASE)
      .then((d) => {
        if (!vivo) return;
        setDados(d);
        setErro(null);
      })
      .catch((e: unknown) => {
        if (vivo) setErro({ msg: mensagemDeErro(e, "Não foi possível ler o primeiro acesso."), status: e instanceof ApiError ? e.status : undefined });
      });
    return () => {
      vivo = false;
    };
  }, [n]);

  // Quem volta de outra aba (depois de cadastrar a câmera, por exemplo) vê a detecção atual.
  useEffect(() => {
    const aoVoltar = () => {
      if (document.visibilityState === "visible") setN((x) => x + 1);
    };
    document.addEventListener("visibilitychange", aoVoltar);
    return () => document.removeEventListener("visibilitychange", aoVoltar);
  }, []);

  const escrever = useCallback(async (caminho: string, metodo: "PUT" | "POST", corpo: object): Promise<boolean> => {
    setOcupado(true);
    setFalha(null);
    try {
      setDados(await apiFetch<EstadoDoOnboarding>(caminho, { method: metodo, body: JSON.stringify(corpo) }));
      return true;
    } catch (e) {
      setFalha(mensagemDeErro(e, "Não foi possível salvar o passo."));
      return false;
    } finally {
      setOcupado(false);
    }
  }, []);

  return {
    dados,
    erro,
    falha,
    ocupado,
    recarregar: useCallback(() => setN((x) => x + 1), []),
    marcar: useCallback((passo: PassoId, estado: MarcaDoPasso) => escrever(`${URL_BASE}/${passo}`, "PUT", { estado }), [escrever]),
    refazer: useCallback(() => escrever(`${URL_BASE}/refazer`, "POST", {}), [escrever]),
    concluir: useCallback(() => escrever(`${URL_BASE}/concluir`, "POST", {}), [escrever]),
  };
}

// --------------------------------------------------------- peças da tela --
export function EstadoDoPasso({ passo }: { passo: PassoDoServidor }) {
  if (passo.estado === "feito") return <Badge tone="ok">{passo.detectado ? "Detectado" : "Feito"}</Badge>;
  if (passo.estado === "pulado") return <Badge>Pulado</Badge>;
  return <Badge>Pendente</Badge>;
}

function Checklist({ itens, pendentes, pronto_para_operar: pronto }: EstadoDoOnboarding["checklist"]) {
  return (
    <div className="onb-pronto" data-testid="onb-pronto" data-pronto={pronto ? "1" : "0"}>
      <p className={`onb-pronto-titulo ${pronto ? "ok" : ""}`}>
        {pronto
          ? "Tudo certo: o sistema encontrou cada item abaixo."
          : `${pendentes === 1 ? "Falta" : "Faltam"} ${pluralizar(pendentes, "item", "itens")} para operar com segurança.`}
      </p>
      <ul className="onb-itens">
        {itens.map((i) => (
          <li key={i.passo} data-passo={i.passo} data-ok={i.ok ? "1" : "0"}>
            <span className={`onb-marca ${i.ok ? "ok" : "pendente"}`} aria-hidden="true">
              {i.ok ? <IconeOk size={16} /> : <IconeAviso size={16} />}
            </span>
            <span className="onb-item-texto">
              <strong>{INFO[i.passo].titulo}</strong>
              <span>{i.detalhe}</span>
            </span>
            <span className="onb-item-estado">{i.ok ? "Feito" : "Pendente"}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

type ContaCriada = { email: string; nome: string; papel: UserRole; senha: string };

/** Criar conta com senha temporária: o servidor gera, devolve UMA vez, e a tela some com ela ao fechar. */
function FormularioDeConta({ aoCriar }: { aoCriar: () => void }) {
  const cameras = useDashboardStore((s) => s.cameras);
  const [nome, setNome] = useState("");
  const [email, setEmail] = useState("");
  const [papel, setPapel] = useState<UserRole>("operator");
  const [cameraId, setCameraId] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [criada, setCriada] = useState<ContaCriada | null>(null);
  const [copiada, setCopiada] = useState<"sim" | "nao" | null>(null);
  const precisaCamera = papel === "operator";

  const criar = (e: React.FormEvent) => {
    e.preventDefault();
    if (precisaCamera && !cameraId) {
      setErro("Escolha a câmera do setor deste Operador.");
      return;
    }
    setSalvando(true);
    setErro(null);
    apiFetch<{ user: AuthUser; senha_temporaria: string }>("/api/users", {
      method: "POST",
      body: JSON.stringify({ name: nome, email, role: papel, camera_id: precisaCamera ? Number(cameraId) : null, senha_temporaria: true }),
    })
      .then((r) => {
        setCriada({ email: r.user.email, nome: r.user.name, papel: r.user.role, senha: r.senha_temporaria });
        setCopiada(null);
        setNome("");
        setEmail("");
        setCameraId("");
        aoCriar();
      })
      .catch((err: unknown) => setErro(mensagemDeErro(err, "Não foi possível criar a conta.")))
      .finally(() => setSalvando(false));
  };

  const copiar = async () => {
    if (!criada) return;
    try {
      await navigator.clipboard.writeText(criada.senha);
      setCopiada("sim");
    } catch {
      setCopiada("nao");
    }
  };

  return (
    <div className="onb-conta">
      {criada && (
        <div className="onb-senha" data-testid="onb-senha" role="status">
          <p className="onb-senha-titulo">
            Conta criada para {criada.nome} ({ROTULO_DO_PAPEL[criada.papel] ?? criada.papel})
          </p>
          <p className="onb-senha-ajuda">Senha temporária de {criada.email}:</p>
          <div className="onb-senha-linha">
            <code className="onb-senha-valor" data-testid="onb-senha-valor">
              {criada.senha}
            </code>
            <button type="button" className="small" onClick={copiar}>
              Copiar
            </button>
          </div>
          <p className="onb-senha-aviso">
            <strong>Esta senha não aparece de novo.</strong> Entregue em mãos e peça para a pessoa trocá-la depois do primeiro acesso. Nada é enviado por e-mail.
          </p>
          {copiada === "sim" && <p className="onb-senha-ajuda">Senha copiada.</p>}
          {copiada === "nao" && <p className="onb-senha-ajuda">Não foi possível copiar. Selecione a senha e copie à mão.</p>}
          <button type="button" className="ghost small" onClick={() => setCriada(null)}>
            Já anotei a senha
          </button>
        </div>
      )}

      <form onSubmit={criar} className="onb-form" aria-label="Nova conta">
        <label className="field">
          <span>Nome</span>
          <input value={nome} onChange={(e) => setNome(e.target.value)} required maxLength={120} autoComplete="off" />
        </label>
        <label className="field">
          <span>E-mail (login)</span>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="off" />
        </label>
        <label className="field">
          <span>Tipo de conta</span>
          <select value={papel} onChange={(e) => setPapel(e.target.value as UserRole)}>
            <option value="operator">Operador (vê só a câmera do setor)</option>
            <option value="technical">Técnico (todas as câmeras e configuração)</option>
            <option value="supervisor">Supervisor (tudo, inclusive contas)</option>
          </select>
        </label>
        {precisaCamera && (
          <label className="field">
            <span>Câmera do setor</span>
            <select value={cameraId} onChange={(e) => setCameraId(e.target.value)} required disabled={cameras.length === 0}>
              <option value="">{cameras.length ? "Escolha uma câmera cadastrada" : "Nenhuma câmera cadastrada"}</option>
              {cameras.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
            {cameras.length === 0 && <small>Cadastre a câmera primeiro, no passo anterior, para vincular o Operador.</small>}
          </label>
        )}
        {erro && (
          <p className="onb-falha" role="alert">
            {erro}
          </p>
        )}
        <div className="onb-form-acoes">
          <button type="submit" className="primary" disabled={salvando}>
            {salvando ? "Criando…" : "Criar conta com senha temporária"}
          </button>
        </div>
      </form>
    </div>
  );
}

function posicaoInicial(d: EstadoDoOnboarding): number {
  const alvo = d.proximo_passo ?? d.ordem[d.ordem.length - 1];
  return Math.max(0, d.ordem.indexOf(alvo));
}

// ------------------------------------------------------------------ tela --
export function OnboardingScreen() {
  const { dados, erro, falha, ocupado, recarregar, marcar, refazer, concluir } = useOnboarding();
  const [indice, setIndice] = useState<number | null>(null);

  useEffect(() => {
    if (dados && indice === null) setIndice(posicaoInicial(dados));
  }, [dados, indice]);

  if (!dados) {
    if (erro?.status === 403) {
      return (
        <div className="screen">
          <EmptyState titulo="Acesso restrito">O primeiro acesso é do Supervisor. Peça a quem tem esse tipo de conta.</EmptyState>
        </div>
      );
    }
    return (
      <div className="screen" aria-busy={erro ? undefined : "true"}>
        {erro ? (
          <div className="onb-erro" role="alert">
            <p>{erro.msg}</p>
            <button type="button" onClick={recarregar}>
              Tentar de novo
            </button>
          </div>
        ) : (
          <PanelSkeleton lines={6} />
        )}
      </div>
    );
  }

  const { progresso, checklist } = dados;
  const total = progresso.total;
  const atual = Math.min(Math.max(indice ?? posicaoInicial(dados), 0), total - 1);
  const passo = dados.passos[atual];
  const info = INFO[passo.passo];
  const ehFinal = atual === total - 1;
  const porcentagem = Math.round((progresso.resolvidos / total) * 100);

  const resolver = async (estado: "feito" | "pulado") => {
    const ok = await marcar(passo.passo, estado);
    if (ok && !ehFinal) setIndice(atual + 1);
  };

  const topo = (
    <>
      <ScreenHead title="Primeiro acesso" sub="Do zero até a planta pronta para operar, no seu ritmo." />
      <div className="onb-progresso-bloco">
        <div
          className="onb-progresso"
          data-testid="onb-progresso"
          role="progressbar"
          aria-label="Progresso do primeiro acesso"
          aria-valuemin={0}
          aria-valuemax={total}
          aria-valuenow={progresso.resolvidos}
          aria-valuetext={`${progresso.resolvidos} de ${total} passos`}
        >
          <div className="onb-progresso-preenchido" style={{ width: `${porcentagem}%` }} />
        </div>
        <p className="onb-progresso-texto">
          {progresso.resolvidos} de {total} passos
          {progresso.pulados > 0 && `, ${pluralizar(progresso.pulados, "pulado")}`}
        </p>
      </div>
    </>
  );

  if (dados.concluido) {
    return (
      <div className="screen onb" data-testid="onboarding" data-concluido="1">
        {topo}
        <section className="card onb-concluido" data-testid="onb-concluido">
          <h2>Primeiro acesso concluído</h2>
          <p>
            {checklist.pronto_para_operar
              ? "A planta está pronta para operar. Cada item abaixo foi encontrado pelo sistema."
              : `Concluído, mas ${pluralizar(checklist.pendentes, "item segue pendente", "itens seguem pendentes")}. Você pode voltar a eles quando quiser.`}
          </p>
          <Checklist {...checklist} />
          {falha && (
            <p className="onb-falha" role="alert">
              {falha}
            </p>
          )}
          <div className="onb-acoes">
            <button
              type="button"
              className="ghost"
              onClick={async () => {
                if (await refazer()) setIndice(0);
              }}
              disabled={ocupado}
              data-testid="onb-refazer"
            >
              Refazer o primeiro acesso
            </button>
          </div>
        </section>
      </div>
    );
  }

  return (
    <div className="screen onb" data-testid="onboarding" data-concluido="0">
      {topo}
      <div className="onb-corpo">
        <nav className="onb-trilha" aria-label="Passos do primeiro acesso">
          <ol>
            {dados.passos.map((p, i) => (
              <li key={p.passo}>
                <button
                  type="button"
                  className={`onb-trilha-item ${i === atual ? "atual" : ""}`}
                  aria-current={i === atual ? "step" : undefined}
                  onClick={() => setIndice(i)}
                  data-passo={p.passo}
                  data-estado={p.estado}
                >
                  <span className="onb-trilha-numero">{i + 1}</span>
                  <span className="onb-trilha-texto">
                    <strong>{INFO[p.passo].titulo}</strong>
                    <EstadoDoPasso passo={p} />
                  </span>
                </button>
              </li>
            ))}
          </ol>
        </nav>

        <section className="card onb-passo" data-testid="onb-passo" data-passo={passo.passo} data-estado={passo.estado}>
          <p className="onb-sobretitulo">
            Passo {atual + 1} de {total}
          </p>
          <h2>{info.titulo}</h2>
          <p className="onb-porque">{info.porque}</p>

          {passo.detalhe && (
            <p className={`onb-detectado ${passo.detectado ? "ok" : ""}`} data-testid="onb-detectado">
              <span className="onb-marca" aria-hidden="true">
                {passo.detectado ? <IconeOk size={16} /> : <IconeAviso size={16} />}
              </span>
              {passo.detectado ? "Encontrado: " : "Ainda não: "}
              {passo.detalhe}
            </p>
          )}

          {info.acao && (
            <div className="onb-acao">
              <button type="button" className="primary" onClick={info.acao.ir}>
                {info.acao.rotulo}
              </button>
              {info.dica && <p className="onb-dica">{info.dica}</p>}
            </div>
          )}

          {passo.passo === "usuarios" && <FormularioDeConta aoCriar={recarregar} />}

          {passo.passo === "pronto" && (
            <>
              <Checklist {...checklist} />
              {!checklist.pronto_para_operar && (
                <p className="onb-dica">Você pode concluir mesmo assim e voltar aos itens pendentes depois. O checklist continua mostrando o que falta.</p>
              )}
            </>
          )}

          {falha && (
            <p className="onb-falha" role="alert">
              {falha}
            </p>
          )}

          <div className="onb-acoes">
            <button type="button" className="ghost" onClick={() => setIndice(atual - 1)} disabled={atual === 0 || ocupado} data-testid="onb-voltar">
              Voltar
            </button>
            {!ehFinal && (
              <button type="button" className="ghost" onClick={() => resolver("pulado")} disabled={ocupado} data-testid="onb-pular">
                Pular por enquanto
              </button>
            )}
            {ehFinal ? (
              <button type="button" className="primary" onClick={() => concluir()} disabled={ocupado} data-testid="onb-feito">
                {ocupado ? "Salvando…" : "Concluir o primeiro acesso"}
              </button>
            ) : (
              <button type="button" className="primary" onClick={() => resolver("feito")} disabled={ocupado} data-testid="onb-feito">
                {passo.detectado ? "Continuar" : "Marcar como feito"}
              </button>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}

export default OnboardingScreen;
