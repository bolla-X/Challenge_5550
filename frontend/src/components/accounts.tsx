import { useOnboarding } from "./onboarding";
import { mensagemDeErro } from "../utils/erros";
import { useEffect, useState } from "react";
import { useDashboardStore } from "../store/dashboardStore";
import { Numero, Panel } from "./common";
import { Miniatura } from "./camera-grid";
import { useLiga } from "./liga";
import { CartaoGestaoInicio } from "./gestao/cartao-inicio";
import {
  IconeApresentacao,
  IconeContas,
  IconeCubo,
  IconeEscudo,
  IconeFrasco,
  IconeStories,
  IconeTrofeu,
  IconeTv,
} from "./icones";
import { ROTULO_DO_PAPEL as PAPEL, ScreenHead } from "./layout";
import { apiFetch } from "../api/client";
import type { AuthUser, UserRole } from "../api/types";
import { pluralizar } from "../utils/formato";

const listUsers = () => apiFetch<{ items: AuthUser[] }>("/api/users");
const createUser = (body: { email: string; name: string; password: string; role: string; camera_id: number | null }) =>
  apiFetch<{ user: AuthUser }>("/api/users", { method: "POST", body: JSON.stringify(body) });
const patchUser = (id: number, body: Record<string, unknown>) =>
  apiFetch<{ user: AuthUser }>(`/api/users/${id}`, { method: "PATCH", body: JSON.stringify(body) });
const deleteUser = (id: number) => apiFetch<{ deleted: boolean }>(`/api/users/${id}`, { method: "DELETE" });

type Agora = { noAr: number; total: number; pessoas: number; incidentes: number };

/** O que está acontecendo na planta agora, do mesmo `/api/gemeo` do palco. */
function useAgora(): Agora | null {
  const [agora, setAgora] = useState<Agora | null>(null);
  useEffect(() => {
    let vivo = true;
    const tick = () =>
      apiFetch<{ cameras: { rodando: boolean; pes: unknown[]; incidentes: unknown[] }[] }>("/api/gemeo")
        .then((d) => {
          if (!vivo) return;
          setAgora({
            noAr: d.cameras.filter((c) => c.rodando).length,
            total: d.cameras.length,
            pessoas: d.cameras.reduce((n, c) => n + c.pes.length, 0),
            incidentes: d.cameras.reduce((n, c) => n + c.incidentes.length, 0),
          });
        })
        .catch(() => vivo && setAgora(null));
    tick();
    const id = window.setInterval(tick, 5000);
    return () => {
      vivo = false;
      window.clearInterval(id);
    };
  }, []);
  return agora;
}

function saudacao(): string {
  const h = new Date().getHours();
  return h < 12 ? "Bom dia" : h < 18 ? "Boa tarde" : "Boa noite";
}

const ATALHOS: { href: string; titulo: string; texto: string; Icone: (p: { size?: number }) => JSX.Element }[] = [
  { href: "/palco", titulo: "Apresentação", texto: "O roteiro da demo, com controle pelo celular.", Icone: IconeApresentacao },
  { href: "/gemeo", titulo: "Gêmeo digital", texto: "A planta em 3D, cada pessoa na cor do estado.", Icone: IconeCubo },
  { href: "/liga", titulo: "Liga de Setores", texto: "Pontos da equipe e missões do turno.", Icone: IconeTrofeu },
  { href: "/auditoria", titulo: "Cadeia de custódia", texto: "Verificar a integridade das evidências.", Icone: IconeEscudo },
  { href: "/simulador", titulo: "Simulador", texto: "Testar uma regra nas últimas horas.", Icone: IconeFrasco },
  { href: "/retrospectiva", titulo: "Retrospectiva", texto: "O turno em cartões, com dados reais.", Icone: IconeStories },
  { href: "/tv", titulo: "Modo TV", texto: "Setores e metas para a parede.", Icone: IconeTv },
];

/** Início do supervisor: a planta agora, as câmeras ao vivo e as portas de entrada. */
/** Enquanto o primeiro acesso não foi concluído, o Início lembra (e leva ao assistente). */
function AvisoDePrimeiroAcesso() {
  const { dados } = useOnboarding();
  if (!dados || dados.concluido) return null;
  return (
    <a className="card aviso-primeiro-acesso" href="/primeiro-acesso" data-testid="aviso-primeiro-acesso">
      <strong>Configure a planta em poucos passos</strong>
      <span>
        {dados.checklist.pendentes} {dados.checklist.pendentes === 1 ? "item pendente" : "itens pendentes"} para ficar pronto para operar.
        Continuar o primeiro acesso →
      </span>
    </a>
  );
}

export function SupervisorHome() {
  const setScreen = useDashboardStore((s) => s.setScreen);
  const cameras = useDashboardStore((s) => s.cameras);
  const user = useDashboardStore((s) => s.user);
  const agora = useAgora();
  const { liga } = useLiga(15000);
  const primeiroNome = (user?.name ?? "").split(" ")[0];
  return (
    <div className="screen home">
      <ScreenHead title={`${saudacao()}${primeiroNome ? `, ${primeiroNome}` : ""}`} sub="A planta agora, nesta máquina." />
      <AvisoDePrimeiroAcesso />
      <dl className="home-agora" aria-label="Agora na planta">
        <div>
          <dt>câmeras no ar</dt>
          <dd>{agora ? `${agora.noAr}/${agora.total}` : "–"}</dd>
        </div>
        <div>
          <dt>pessoas na planta</dt>
          <dd>{agora ? <Numero valor={agora.pessoas} /> : "–"}</dd>
        </div>
        <div className={agora && agora.incidentes > 0 ? "alerta" : ""}>
          <dt>incidentes ativos</dt>
          <dd>{agora ? <Numero valor={agora.incidentes} /> : "–"}</dd>
        </div>
        <div>
          <dt>nível da planta</dt>
          <dd>{liga ? <Numero valor={liga.planta.nivel} /> : "–"}</dd>
        </div>
      </dl>
      <div className="home-bento">
        <button type="button" className="home-tile home-tile-cameras" onClick={() => setScreen("grid")}>
          <span className="home-miniaturas" aria-hidden="true">
            {cameras.slice(0, 4).map((c) => (
              <span key={c.id} className="home-miniatura">
                <Miniatura cameraId={c.id} />
                <small>{c.name}</small>
              </span>
            ))}
          </span>
          <span className="home-tile-texto">
            <strong>Câmeras</strong>
            <span>
              {pluralizar(cameras.length, "câmera")}: monitoramento, incidentes, zonas e portaria.
            </span>
          </span>
        </button>
        {ATALHOS.map(({ href, titulo, texto, Icone }) => (
          <a key={href} className="home-tile" href={href}>
            <Icone size={22} />
            <strong>{titulo}</strong>
            <span>{texto}</span>
          </a>
        ))}
        <button type="button" className="home-tile" onClick={() => setScreen("accounts")}>
          <IconeContas size={22} />
          <strong>Contas</strong>
          <span>Acesso de operadores e técnicos.</span>
        </button>
        <CartaoGestaoInicio />
      </div>
    </div>
  );
}

/** Criar e administrar contas. Só o supervisor chega aqui. */
export function AccountsScreen() {
  const setScreen = useDashboardStore((s) => s.setScreen);
  const cameras = useDashboardStore((s) => s.cameras);
  const showMessage = useDashboardStore((s) => s.showMessage);
  const eu = useDashboardStore((s) => s.user);

  const [usuarios, setUsuarios] = useState<AuthUser[]>([]);
  const [nome, setNome] = useState("");
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [mostrar, setMostrar] = useState(false);
  const [papel, setPapel] = useState<UserRole>("operator");
  const [cameraId, setCameraId] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [aba, setAba] = useState<"nova" | "gerenciar">("gerenciar");

  const carregar = () =>
    listUsers()
      .then((r) => setUsuarios(r.items))
      .catch((err) => showMessage(mensagemDeErro(err, "Não foi possível listar as contas."), "error"));

  useEffect(() => {
    carregar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const nomeDaCamera = (id: number | null) => (id == null ? "sem setor" : cameras.find((c) => c.id === id)?.name ?? `câmera ${id}`);
  const precisaCamera = papel === "operator";

  const criar = (e: React.FormEvent) => {
    e.preventDefault();
    if (precisaCamera && !cameraId) {
      showMessage("Escolha a câmera do setor deste operador.", "warning");
      return;
    }
    setSalvando(true);
    createUser({ email, name: nome, password: senha, role: papel, camera_id: precisaCamera ? Number(cameraId) : null })
      .then((r) => {
        showMessage(`Conta criada: ${r.user.email} (${PAPEL[r.user.role] ?? r.user.role}).`, "ok");
        setNome("");
        setEmail("");
        setSenha("");
        setCameraId("");
        return carregar();
      })
      .catch((err) => showMessage(mensagemDeErro(err, "Não foi possível criar a conta."), "error"))
      .finally(() => setSalvando(false));
  };

  const acao = (promessa: Promise<unknown>, ok: string) =>
    promessa
      .then(() => {
        showMessage(ok, "ok");
        return carregar();
      })
      .catch((err) => showMessage(mensagemDeErro(err, "Falha na operação."), "error"));

  const trocarSenha = (u: AuthUser) => {
    const nova = window.prompt(`Nova senha para ${u.email}:`);
    if (nova) acao(patchUser(u.id, { password: nova }), "Senha alterada. As sessões abertas dessa conta foram encerradas.");
  };

  return (
    <div className="screen">
      <ScreenHead
        title="Contas"
        sub={aba === "nova" ? "Nova conta" : pluralizar(usuarios.length, "conta")}
        actions={
          aba === "nova" ? (
            <button type="button" className="ghost" onClick={() => setAba("gerenciar")}>
              Voltar
            </button>
          ) : (
            <>
              <button type="button" className="ghost" onClick={() => setScreen("home")}>
                Início
              </button>
              <button type="button" className="primary" onClick={() => setAba("nova")}>
                Nova conta
              </button>
            </>
          )
        }
      />

      {aba === "nova" && (
      <Panel id="panel-new-account" title="Nova conta" description="Você define o e-mail e a senha. Passe os dados ao operador em mãos.">
        <form onSubmit={criar} className="account-form">
          <label>
            Nome
            <input value={nome} onChange={(e) => setNome(e.target.value)} required maxLength={120} autoComplete="off" />
          </label>
          <label>
            E-mail (login)
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="off" />
          </label>
          <label>
            Senha
            <span className="account-pass">
              <input
                type={mostrar ? "text" : "password"}
                value={senha}
                onChange={(e) => setSenha(e.target.value)}
                required
                autoComplete="new-password"
              />
              <button type="button" className="ghost small" onClick={() => setMostrar((v) => !v)}>
                {mostrar ? "Ocultar" : "Mostrar"}
              </button>
            </span>
          </label>
          <label>
            Tipo de conta
            <select value={papel} onChange={(e) => setPapel(e.target.value as UserRole)}>
              <option value="operator">Operador (vê só a câmera do setor)</option>
              <option value="technical">Técnico (todas as câmeras e configuração)</option>
              <option value="supervisor">Supervisor (tudo, inclusive contas)</option>
            </select>
          </label>
          {precisaCamera && (
            <label>
              Câmera do setor
              <select value={cameraId} onChange={(e) => setCameraId(e.target.value)} required disabled={cameras.length === 0}>
                <option value="">{cameras.length ? "Escolha uma câmera cadastrada…" : "Nenhuma câmera cadastrada"}</option>
                {cameras.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                    {c.gate_required ? " (portaria)" : ""}
                  </option>
                ))}
              </select>
              {cameras.length === 0 && <small>Cadastre a câmera primeiro, em Câmeras, para poder vincular o operador.</small>}
            </label>
          )}
          <div className="actions">
            <button type="submit" className="primary" disabled={salvando}>
              {salvando ? "Criando…" : "Criar conta"}
            </button>
          </div>
        </form>
      </Panel>
      )}

      {aba === "gerenciar" && (
      <Panel id="panel-accounts" title="Contas existentes" description={pluralizar(usuarios.length, "conta")}>
        <div className="account-list">
          {usuarios.map((u) => (
            <div key={u.id} className={`account-row${u.active ? "" : " inactive"}`}>
              <div>
                <strong>{u.name}</strong>
                <div className="t-secondary">
                  {u.email} · {PAPEL[u.role] ?? u.role}
                  {u.role === "operator" ? ` · ${nomeDaCamera(u.camera_id)}` : ""}
                  {u.active ? "" : " · desativada"}
                </div>
              </div>
              {u.id !== eu?.id && (
                <div className="actions">
                  <button type="button" className="ghost small" onClick={() => trocarSenha(u)}>
                    Trocar senha
                  </button>
                  <button
                    type="button"
                    className="ghost small"
                    onClick={() => acao(patchUser(u.id, { active: !u.active }), u.active ? "Conta desativada." : "Conta reativada.")}
                  >
                    {u.active ? "Desativar" : "Reativar"}
                  </button>
                  <button
                    type="button"
                    className="ghost small"
                    onClick={() => {
                      if (window.confirm(`Apagar definitivamente a conta de ${u.email}?`)) acao(deleteUser(u.id), "Conta apagada.");
                    }}
                  >
                    Apagar
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      </Panel>
      )}
    </div>
  );
}
