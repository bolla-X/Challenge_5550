import { useCallback, useEffect, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { changeOwnPassword } from "../api/endpoints";
import type { UserRole } from "../api/types";
import { getStatusDoSistema } from "../api/status-do-sistema";
import type { EstadoDoComponente, StatusDoSistema } from "../api/status-do-sistema";
import { useDashboardStore } from "../store/dashboardStore";
import { mensagemDeErro } from "../utils/erros";
import { dataHoraCurta, paraDate } from "../utils/datas";
import { decimal, pluralizar } from "../utils/formato";
import { EmptyState, PanelSkeleton } from "./common";
import { ROTULO_DO_PAPEL } from "./layout";
import { SeloDeEstado } from "./pagina-status";
import { useEstadoDaIntegracao } from "./torre";
import "../styles/configuracoes.css";

/**
 * Configurações (`/configuracoes`): um lugar só, em seções na barra lateral.
 *
 * Esta tela NÃO tem formulário de câmera, de regra, de zona nem de conta: cada seção
 * leva à tela que já faz isso (câmera: aba "Config. câmera" da própria câmera; regras:
 * `/regras`; contas: a tela de Contas). A única coisa nova aqui é a troca da própria
 * senha, porque a API existia (`POST /api/auth/password`) e nenhuma tela a usava.
 *
 * Seção que o tipo de conta não pode usar continua na lista, esmaecida, e ao abri-la a
 * tela diz o que é e quem pode: o servidor valida de novo em cada rota.
 */

type IdDaSecao = "conta" | "planta" | "cameras" | "regras" | "integracoes" | "privacidade" | "usuarios";

const NIVEL: Record<UserRole, number> = { operator: 1, technical: 2, supervisor: 3 };

type Secao = {
  id: IdDaSecao;
  titulo: string;
  descricao: string;
  minimo: UserRole;
  /** Quem pode: aparece na barra lateral quando a seção está fora do alcance. */
  quem: string;
  explicacao: string;
};

const SECOES: Secao[] = [
  {
    id: "conta",
    titulo: "Conta",
    descricao: "Seus dados e a troca da senha.",
    minimo: "operator",
    quem: "Todos",
    explicacao: "",
  },
  {
    id: "planta",
    titulo: "Planta",
    descricao: "Planta baixa e calibração de cada câmera.",
    minimo: "technical",
    quem: "Técnico ou Supervisor",
    explicacao: "A calibração da planta é do Técnico para cima.",
  },
  {
    id: "cameras",
    titulo: "Câmeras",
    descricao: "Fonte, imagem, área de risco e portaria de cada câmera.",
    minimo: "technical",
    quem: "Técnico ou Supervisor",
    explicacao: "A configuração das câmeras é do Técnico para cima. Você acompanha a câmera do seu setor na tela inicial.",
  },
  {
    id: "regras",
    titulo: "Regras",
    descricao: "Quando um alerta nasce, sem escrever código.",
    minimo: "technical",
    quem: "Técnico ou Supervisor",
    explicacao: "O editor de regras é do Técnico para cima.",
  },
  {
    id: "integracoes",
    titulo: "Integrações",
    descricao: "OPC UA, MQTT e webhook para outros sistemas.",
    minimo: "technical",
    quem: "Técnico ou Supervisor",
    explicacao: "O estado das integrações é do Técnico para cima.",
  },
  {
    id: "privacidade",
    titulo: "Privacidade",
    descricao: "Desfoque de rosto e o que fica guardado.",
    minimo: "technical",
    quem: "Técnico ou Supervisor",
    explicacao: "A política de privacidade e de retenção é do Técnico para cima.",
  },
  {
    id: "usuarios",
    titulo: "Usuários",
    descricao: "Contas, tipos de conta e setores.",
    minimo: "supervisor",
    quem: "Só o Supervisor",
    explicacao: "Só o Supervisor cria contas e muda tipo de conta ou setor.",
  },
];

// ---------------------------------------------------------------- navegação --

/** Abre a câmera (tela de foco) na aba pedida. O estado da câmera mora no store, então é navegação interna, sem recarregar. */
function abrirCamera(cameraId: number, aba?: string): void {
  const { setCamId, setScreen } = useDashboardStore.getState();
  window.history.pushState(null, "", aba ? `/?aba=${aba}` : "/");
  setCamId(cameraId);
  setScreen("focus");
}

function abrirContas(): void {
  window.history.pushState(null, "", "/");
  useDashboardStore.getState().setScreen("accounts");
}

function secaoDaUrl(): IdDaSecao {
  const id = window.location.hash.replace("#", "");
  return SECOES.some((s) => s.id === id) ? (id as IdDaSecao) : "conta";
}

// ---------------------------------------------------------------- utilidades --

function Campo({ rotulo, children }: { rotulo: string; children: ReactNode }) {
  return (
    <div className="status-row">
      <span className="status-row-label">{rotulo}</span>
      <span className="status-row-value">{children}</span>
    </div>
  );
}

function Bloco({ titulo, children }: { titulo: string; children: ReactNode }) {
  return (
    <section className="config-bloco">
      <h3>{titulo}</h3>
      {children}
    </section>
  );
}

function ListaDeCameras({ aba, rotulo }: { aba: string; rotulo: string }) {
  const cameras = useDashboardStore((s) => s.cameras);
  if (!cameras.length) {
    return <EmptyState>Nenhuma câmera cadastrada ainda. Adicione a primeira na tela de câmeras.</EmptyState>;
  }
  return (
    <ul className="config-lista">
      {cameras.map((c) => (
        <li key={c.id}>
          <span className="config-lista-nome">
            <strong>{c.name}</strong>
            {c.location && <small>{c.location}</small>}
          </span>
          <button type="button" className="ghost small" onClick={() => abrirCamera(c.id, aba)} aria-label={`${rotulo}: ${c.name}`}>
            {rotulo}
          </button>
        </li>
      ))}
    </ul>
  );
}

// -------------------------------------------------------------------- conta --
function SecaoConta() {
  const user = useDashboardStore((s) => s.user);
  const cameras = useDashboardStore((s) => s.cameras);
  const logout = useDashboardStore((s) => s.logout);
  const [atual, setAtual] = useState("");
  const [nova, setNova] = useState("");
  const [confirmacao, setConfirmacao] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [trocou, setTrocou] = useState(false);

  if (!user) return null;
  const setor = user.role === "operator" ? (cameras.find((c) => c.id === user.camera_id)?.name ?? "sem setor atribuído") : null;

  const enviar = (e: FormEvent) => {
    e.preventDefault();
    if (nova.length < 10) {
      setErro("A nova senha precisa de pelo menos 10 caracteres.");
      return;
    }
    if (nova !== confirmacao) {
      setErro("A confirmação não é igual à nova senha.");
      return;
    }
    setErro(null);
    setSalvando(true);
    changeOwnPassword(atual, nova)
      .then(() => setTrocou(true))
      .catch((err) => setErro(mensagemDeErro(err, "Não foi possível trocar a senha.")))
      .finally(() => setSalvando(false));
  };

  return (
    <>
      <Bloco titulo="Seus dados">
        <div className="status-list">
          <Campo rotulo="Nome">{user.name}</Campo>
          <Campo rotulo="E-mail">{user.email}</Campo>
          <Campo rotulo="Tipo de conta">{ROTULO_DO_PAPEL[user.role] ?? user.role}</Campo>
          {setor && <Campo rotulo="Setor">{setor}</Campo>}
          {user.last_login_at && <Campo rotulo="Último acesso">{dataHoraCurta(paraDate(user.last_login_at))}</Campo>}
        </div>
        <p className="config-dica">Nome, e-mail e tipo de conta são mudados pelo Supervisor.</p>
      </Bloco>

      <Bloco titulo="Trocar a senha">
        {trocou ? (
          <div className="config-aviso" role="status">
            <p>Senha alterada. Por segurança, as sessões abertas desta conta foram encerradas, inclusive esta.</p>
            <button type="button" className="primary" onClick={() => void logout()}>
              Entrar de novo
            </button>
          </div>
        ) : (
          <form className="config-form" onSubmit={enviar} data-testid="config-trocar-senha">
            <label>
              <span>Senha atual</span>
              <input type="password" autoComplete="current-password" required value={atual} onChange={(e) => setAtual(e.target.value)} />
            </label>
            <label>
              <span>Nova senha</span>
              <input type="password" autoComplete="new-password" required minLength={10} value={nova} onChange={(e) => setNova(e.target.value)} />
            </label>
            <label>
              <span>Repita a nova senha</span>
              <input type="password" autoComplete="new-password" required value={confirmacao} onChange={(e) => setConfirmacao(e.target.value)} />
            </label>
            <p className="config-dica">Pelo menos 10 caracteres. Ao trocar, todas as sessões desta conta são encerradas.</p>
            {erro && (
              <p className="config-erro" role="alert">
                {erro}
              </p>
            )}
            <div>
              <button type="submit" className="primary" disabled={salvando || !atual || !nova || !confirmacao}>
                {salvando ? "Trocando…" : "Trocar senha"}
              </button>
            </div>
          </form>
        )}
      </Bloco>
    </>
  );
}

// ------------------------------------------------------------------- planta --
function SecaoPlanta() {
  return (
    <>
      <Bloco titulo="Calibrar a planta baixa">
        <p className="config-texto">
          A calibração liga quatro pontos do chão da imagem aos mesmos pontos da planta. É ela que põe cada pessoa no lugar certo da planta e do gêmeo
          digital. Escolha a câmera:
        </p>
        <ListaDeCameras aba="planta" rotulo="Calibrar" />
      </Bloco>
      <Bloco titulo="Ver o resultado">
        <p className="config-texto">O gêmeo digital mostra todas as câmeras calibradas numa planta só.</p>
        <a className="button" href="/gemeo">
          Abrir o gêmeo digital
        </a>
      </Bloco>
    </>
  );
}

// ----------------------------------------------------------------- câmeras --
function SecaoCameras() {
  return (
    <Bloco titulo="Configuração de cada câmera">
      <p className="config-texto">Fonte de vídeo, tamanho da imagem, rotação, Celular por QR code e remoção ficam na aba "Config. câmera" de cada uma.</p>
      <ListaDeCameras aba="camconfig" rotulo="Configurar" />
      <p className="config-dica">Para adicionar uma câmera nova, use a tela de câmeras.</p>
    </Bloco>
  );
}

// ------------------------------------------------------------------- regras --
function SecaoRegras() {
  return (
    <Bloco titulo="Editor de regras">
      <p className="config-texto">
        Monte a regra com blocos de condição e de ação, teste no histórico e só depois ative. As regras que já vêm com o sistema aparecem pré-carregadas.
      </p>
      <a className="button primary" href="/regras">
        Abrir o editor de regras
      </a>
    </Bloco>
  );
}

// -------------------------------------------------------------- integrações --
const NOME_DA_INTEGRACAO: Record<string, string> = { opcua: "OPC UA", mqtt: "MQTT", broker: "Broker MQTT embutido", webhook: "Webhook" };
const COMO_LIGAR: [string, string][] = [
  ["OPC UA", "OPCUA_ATIVO=true"],
  ["MQTT", "MQTT_ATIVO=true (broker em MQTT_HOST e MQTT_PORTA)"],
  ["Broker MQTT embutido, para demonstração sem rede", "MQTT_BROKER_EMBUTIDO=true"],
  ["Webhook", "WEBHOOK_URL=https://seu-endereco"],
];

function estadoDaIntegracao(estado?: string, ativo?: boolean): EstadoDoComponente {
  if (estado === "no_ar" || estado === "conectado") return "ok";
  if (estado === "falhou") return "falha";
  if (estado === "desligado" || ativo === false) return "desligado";
  return "atencao";
}

function SecaoIntegracoes() {
  const { estado, erro } = useEstadoDaIntegracao(5000);
  return (
    <>
      <Bloco titulo="Estado agora">
        {estado ? (
          <div className="status-list">
            {Object.entries(estado.integracoes).map(([chave, i]) => (
              <div className="config-integracao" key={chave}>
                <div className="status-row">
                  <span className="status-row-label">{NOME_DA_INTEGRACAO[chave] ?? chave}</span>
                  <SeloDeEstado estado={estadoDaIntegracao(i.estado, i.ativo)} />
                </div>
                {i.endpoint && <small className="config-detalhe">{i.endpoint}</small>}
                {i.erro && <small className="config-detalhe">{i.erro}</small>}
              </div>
            ))}
          </div>
        ) : erro ? (
          <p className="config-erro" role="alert">
            {erro}
          </p>
        ) : (
          <PanelSkeleton lines={3} />
        )}
      </Bloco>
      <Bloco titulo="Como ligar">
        <p className="config-texto">As integrações vêm desligadas. Para ligar, defina as variáveis no arquivo .env e reinicie o servidor:</p>
        <dl className="config-variaveis">
          {COMO_LIGAR.map(([nome, variavel]) => (
            <div key={nome}>
              <dt>{nome}</dt>
              <dd>
                <code>{variavel}</code>
              </dd>
            </div>
          ))}
        </dl>
        <p className="config-dica">O guia para quem vai ler os dados (nós OPC UA, tópicos MQTT, exemplo) é o arquivo docs/NEXT2026/INTEGRACAO.md.</p>
        <div className="config-acoes">
          <a className="button ghost" href="/torre">
            Ver a torre de luz
          </a>
          <a className="button ghost" href="/status">
            Ver a saúde do sistema
          </a>
        </div>
      </Bloco>
    </>
  );
}

// -------------------------------------------------------------- privacidade --
function SecaoPrivacidade() {
  const [dados, setDados] = useState<StatusDoSistema["politicas"] | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  const carregar = useCallback(() => {
    setErro(null);
    getStatusDoSistema()
      .then((r) => setDados(r.politicas))
      .catch((err) => setErro(mensagemDeErro(err, "Não foi possível ler a política de privacidade.")));
  }, []);
  useEffect(carregar, [carregar]);

  if (erro) {
    return (
      <div className="config-erro" role="alert">
        <p>{erro}</p>
        <button type="button" onClick={carregar}>
          Tentar de novo
        </button>
      </div>
    );
  }
  if (!dados) return <PanelSkeleton lines={5} />;

  const { privacidade, retencao } = dados;
  const antes = retencao.replay_antes_s;
  const depois = retencao.replay_depois_s;
  return (
    <>
      <Bloco titulo="Desfoque de rosto por câmera">
        <p className="config-texto">
          Ao ligar o sistema, o desfoque começa {privacidade.padrao_ligada ? "ligado" : "desligado"} em toda câmera. Só o Supervisor liga ou desliga, na tela da câmera, e
          cada troca fica registrada com o nome de quem fez.
        </p>
        {privacidade.cameras.length === 0 ? (
          <EmptyState>Nenhuma câmera cadastrada ainda.</EmptyState>
        ) : (
          <ul className="config-lista">
            {privacidade.cameras.map((c) => (
              <li key={c.id}>
                <span className="config-lista-nome">
                  <strong>{c.nome}</strong>
                </span>
                <span className={`chip ${c.ativa ? "ok" : ""}`}>
                  {c.ativa && <span className="dot" aria-hidden="true" />}
                  {c.ativa === null ? "Sem informação" : c.ativa ? "Desfoque ligado" : "Desfoque desligado"}
                </span>
                <button type="button" className="ghost small" onClick={() => abrirCamera(c.id)} aria-label={`Abrir a câmera ${c.nome}`}>
                  Abrir câmera
                </button>
              </li>
            ))}
          </ul>
        )}
      </Bloco>

      <Bloco titulo="O que fica guardado">
        <div className="status-list">
          <Campo rotulo="Imagem de evidência">{retencao.imagem_de_evidencia ? "gravada quando o alerta nasce" : "não gravada"}</Campo>
          <Campo rotulo="Replay">
            {retencao.replay && antes !== null && depois !== null
              ? `${decimal(antes)} s antes e ${decimal(depois)} s depois do alerta`
              : "desligado"}
          </Campo>
          <Campo rotulo="Trilhas do simulador">
            sem imagem, até {decimal(retencao.trilhas_teto_mb, 0)} MB por câmera ({pluralizar(retencao.trilhas_arquivos, "arquivo")} de {decimal(retencao.trilhas_mb_por_arquivo, 0)} MB; o
            mais antigo é substituído)
          </Campo>
          <Campo rotulo="Cadeia de custódia">{retencao.cadeia_de_custodia ? "ligada" : "desligada"}</Campo>
          <Campo rotulo="Validade">{retencao.expira_sozinha ? "expira sozinha" : "nada expira sozinho"}</Campo>
        </div>
        <p className="config-dica">
          {retencao.expira_sozinha
            ? ""
            : "Evidência e replay ficam até alguém apagar. Apagar é uma ação manual, com confirmação. O tamanho de cada pasta está na página de status."}
        </p>
        <div className="config-acoes">
          <a className="button ghost" href="/status">
            Ver o espaço em disco
          </a>
        </div>
      </Bloco>
    </>
  );
}

// ----------------------------------------------------------------- usuários --
function SecaoUsuarios() {
  return (
    <Bloco titulo="Contas">
      <p className="config-texto">
        Crie contas, troque o tipo de conta (Operador, Técnico ou Supervisor), atribua o setor do Operador, desative ou apague. Trocar a senha de alguém encerra as sessões
        abertas dessa conta.
      </p>
      <button type="button" className="primary" onClick={abrirContas}>
        Abrir a gestão de contas
      </button>
    </Bloco>
  );
}

const CONTEUDO: Record<IdDaSecao, () => ReactNode> = {
  conta: () => <SecaoConta />,
  planta: () => <SecaoPlanta />,
  cameras: () => <SecaoCameras />,
  regras: () => <SecaoRegras />,
  integracoes: () => <SecaoIntegracoes />,
  privacidade: () => <SecaoPrivacidade />,
  usuarios: () => <SecaoUsuarios />,
};

// ------------------------------------------------------------------- tela --
export default function ConfiguracoesScreen() {
  const user = useDashboardStore((s) => s.user);
  const [ativa, setAtiva] = useState<IdDaSecao>(secaoDaUrl);

  useEffect(() => {
    const aoMudarOHash = () => setAtiva(secaoDaUrl());
    window.addEventListener("hashchange", aoMudarOHash);
    return () => window.removeEventListener("hashchange", aoMudarOHash);
  }, []);

  if (!user) return null;
  const nivel = NIVEL[user.role] ?? 0;
  const secao = SECOES.find((s) => s.id === ativa) ?? SECOES[0];
  const liberada = nivel >= NIVEL[secao.minimo];

  const escolher = (id: IdDaSecao) => {
    setAtiva(id);
    window.history.replaceState(null, "", `#${id}`);
  };

  return (
    <div className="screen config" data-testid="configuracoes">
      <header className="screen-head">
        <h1>Configurações</h1>
        <p className="screen-sub">Tudo o que se ajusta no VisionEPI, em um lugar só.</p>
        <div className="screen-actions">
          <a className="button ghost" href="/">
            Voltar ao painel
          </a>
        </div>
      </header>

      <div className="config-layout">
        <nav className="config-nav" aria-label="Seções das configurações">
          {SECOES.map((s) => {
            const podeUsar = nivel >= NIVEL[s.minimo];
            return (
              <button
                key={s.id}
                type="button"
                className={`config-nav-item ${s.id === ativa ? "ativa" : ""}`.trim()}
                aria-current={s.id === ativa ? "page" : undefined}
                aria-disabled={!podeUsar || undefined}
                title={!podeUsar ? `${s.quem}: ${s.explicacao}` : undefined}
                data-secao={s.id}
                onClick={() => escolher(s.id)}
              >
                <span>{s.titulo}</span>
                {!podeUsar && <small>{s.quem}</small>}
              </button>
            );
          })}
        </nav>

        <section className="card config-painel" aria-labelledby="config-titulo" data-testid={`config-${secao.id}`}>
          <div className="config-painel-topo">
            <h2 id="config-titulo">{secao.titulo}</h2>
            <p>{secao.descricao}</p>
          </div>
          {liberada ? (
            CONTEUDO[secao.id]()
          ) : (
            <div className="config-bloqueada" data-testid="config-bloqueada">
              <EmptyState titulo="Esta seção não está disponível para o seu tipo de conta">
                {secao.explicacao} Seu tipo de conta é {ROTULO_DO_PAPEL[user.role] ?? user.role}. Peça a quem tem acesso ({secao.quem}).
              </EmptyState>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
