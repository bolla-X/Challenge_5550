import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "../api/client";
import { useDashboardStore } from "../store/dashboardStore";
import { dataHoraCurta, horaCurta, paraDate } from "../utils/datas";
import { mensagemDeErro } from "../utils/erros";
import { pluralizar } from "../utils/formato";
import { BadgeDeSaude, useCameraEstado } from "./camera-grid";
import { Badge, Numero, PanelSkeleton } from "./common";
import { AVISO_DUPLA_CONTAGEM, cronometro, useEvacuacao } from "./evacuacao";
import type { Resumo } from "./evacuacao";
import { EstadoDoPasso, INFO, useOnboarding } from "./onboarding";
import type { PassoId } from "./onboarding";
import { QuadroDaCena } from "./palco-video";
import { AVISO_VIGIA } from "./permissoes";
import { RegraEmBlocos, Resultado } from "./regras";
import type { Listagem, Opcoes, RegraDeExemplo, ResultadoTeste } from "./regras";
import { IntegracoesDaPlanta, motivoDaTorre, plantaEscalonada, textoDaTorre, Torre, useEstadoDaIntegracao } from "./torre";

export type { RegraDeExemplo } from "./regras";

/**
 * Cenas da MISSÃO 4 no palco (Fase 6): só o que já existe e passou no E2E, mostrado com dado real.
 * Nada aqui inventa número: o que o servidor não sabe vira a mensagem dele (ou um aviso honesto).
 * O preparo de cada cena (referência da câmera, permissão de demonstração) e a saída (encerrar a
 * evacuação e a permissão) são do servidor: `app/api/palco.py`.
 */

const SEM_CAMERA = <p className="palco-vazio">Câmera da cena não cadastrada.</p>;

// ------------------------------------------------------------ Tape a câmera ---
function TapeComCamera({ cameraId, aoVivo }: { cameraId: number; aoVivo: boolean }) {
  // 1 s (e não 3): quem tapa a lente espera ver o alerta aparecer e sumir.
  const estado = useCameraEstado(cameraId, 1000);
  const saude = estado.saude;
  const comProblema = saude !== undefined && saude.estado !== "ok";
  return (
    <div className="palco-tape" data-testid="palco-tape" data-saude={saude?.estado ?? "desconhecida"}>
      <div className="palco-tape-video">
        <QuadroDaCena cameraId={cameraId} estado={estado} />
        <span className="palco-tape-badge">
          {comProblema ? (
            <BadgeDeSaude saude={saude} />
          ) : (
            <span className="chip ok" data-testid="saude-ok" role="status">
              <span className="dot" />
              {saude ? "Imagem OK" : "Lendo a imagem…"}
            </span>
          )}
        </span>
      </div>
      <aside className="palco-tape-painel">
        <p className="palco-tape-instrucao">Tape a lente com a mão</p>
        {comProblema ? (
          <div className="palco-alerta" role="alert" data-testid="palco-tape-alerta">
            <strong>{saude.estado === "obstruida" ? "Câmera obstruída" : `Imagem com problema: ${saude.rotulo.toLowerCase()}`}</strong>
            <span>O sistema acusou o problema em vez de dizer “nenhuma violação”.</span>
          </div>
        ) : (
          <p className="palco-tape-calmo">A imagem está como a referência. Ao tapar a lente, o alerta aparece em poucos segundos e some ao destapar.</p>
        )}
        {!aoVivo && (
          <p className="palco-aviso" role="note" data-testid="palco-tape-sem-webcam">
            Esta câmera toca uma gravação: tapar a lente não muda nada. Ligue a webcam e reinicie a demonstração para esta cena reagir.
          </p>
        )}
      </aside>
    </div>
  );
}

export function CenaTapeACamera({ cameraId, aoVivo }: { cameraId: number | null; aoVivo: boolean }) {
  return cameraId == null ? SEM_CAMERA : <TapeComCamera cameraId={cameraId} aoVivo={aoVivo} />;
}

// -------------------------------------------------------- Fábrica conectada ---
export function CenaFabricaConectada() {
  const { estado, erro } = useEstadoDaIntegracao(1000);
  if (!estado) return <p className="palco-vazio" role={erro ? "alert" : "status"}>{erro ?? "Lendo o estado da planta…"}</p>;
  const { planta } = estado;
  return (
    <div className="palco-fabrica" data-testid="palco-fabrica" data-torre={planta.torre}>
      <Torre cor={planta.torre} sirene={planta.sirene} escalonado={plantaEscalonada(planta)} />
      <div className="palco-fabrica-texto">
        <p className="torre-estado" aria-live="polite">{textoDaTorre(planta)}</p>
        <p className="torre-detalhe">{motivoDaTorre(planta)}</p>
        <IntegracoesDaPlanta integracoes={estado.integracoes} />
        <p className="palco-clp" data-testid="palco-clp">
          O mesmo estado que um CLP lê em <code>Planta.PlantaEmAlarme</code>: <strong>{planta.planta_em_alarme ? "verdadeiro" : "falso"}</strong>
        </p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- Evacuação ---
/** A chave do palco (a mesma do QR): aciona e encerra a evacuação sem depender de quem está logado. */
function useTokenDoPalco(): string | null | undefined {
  const [token, setToken] = useState<string | null | undefined>(undefined); // undefined = lendo; null = não deu
  useEffect(() => {
    let vivo = true;
    apiFetch<{ caminho: string }>("/api/palco/controle")
      .then((d) => vivo && setToken(new URL(d.caminho, window.location.origin).searchParams.get("t")))
      .catch(() => vivo && setToken(null));
    return () => {
      vivo = false;
    };
  }, []);
  return token;
}

type RelatorioEncerrado = { relatorio: Resumo; custodia_registrada: boolean };

export function CenaEvacuacao() {
  const token = useTokenDoPalco();
  const { estado, erro, recarregar } = useEvacuacao();
  const [ocupado, setOcupado] = useState(false);
  const [falha, setFalha] = useState<string | null>(null);
  const [encerrada, setEncerrada] = useState<RelatorioEncerrado | null>(null);

  const comandar = async (acao: "iniciar" | "encerrar") => {
    setOcupado(true);
    setFalha(null);
    try {
      const r = await apiFetch<RelatorioEncerrado>(`/api/evacuacao/${acao}`, { method: "POST", body: JSON.stringify({ t: token }) });
      setEncerrada(acao === "encerrar" ? r : null);
      recarregar();
    } catch (e) {
      setFalha(mensagemDeErro(e, "Não foi possível concluir."));
    } finally {
      setOcupado(false);
    }
  };

  if (!estado) return <div aria-busy={!erro}>{erro ? <p className="palco-vazio" role="alert">{erro.msg}</p> : <PanelSkeleton lines={5} />}</div>;
  const ativa = estado.ativa;
  const semChave = token === null;
  return (
    <div className={`palco-evac${ativa ? " evac-ativa" : ""}`} data-testid="palco-evacuacao" data-ativa={ativa ? "1" : "0"}>
      <header className="evac-topo">
        <div>
          <p className="evac-sobretitulo">{ativa ? "Evacuação em andamento" : "Modo Evacuação"}</p>
          {ativa ? (
            <p className="evac-cronometro" data-testid="evac-cronometro" aria-live="off">{cronometro(estado.segundos)}</p>
          ) : (
            <p className="evac-titulo" data-testid="evac-pronto">Pronto para acionar</p>
          )}
        </div>
        <div className="palco-evac-acoes">
          {ativa ? (
            <button type="button" className="grande palco-evac-botao" data-testid="evac-encerrar" onClick={() => void comandar("encerrar")} disabled={ocupado || semChave}>
              {ocupado ? "Aguarde…" : "Encerrar e gravar relatório"}
            </button>
          ) : (
            <button type="button" className="danger grande palco-evac-botao" data-testid="evac-acionar" onClick={() => void comandar("iniciar")} disabled={ocupado || token === undefined || semChave}>
              {ocupado ? "Aguarde…" : "Acionar evacuação"}
            </button>
          )}
          <p className="evac-nota">Ao seguir para a próxima cena, a evacuação em andamento é encerrada e registrada.</p>
        </div>
      </header>

      <p className="evac-aviso" role="note" data-testid="evac-aviso">{estado.aviso || AVISO_DUPLA_CONTAGEM}</p>
      {semChave && <p className="evac-falha" role="alert">Sem a chave do palco (entre como Técnico ou Supervisor): o botão fica desligado.</p>}
      {falha && <p className="evac-falha" role="alert">{falha}</p>}

      {ativa ? (
        <>
          <section className="evac-numeros" aria-label="Contagem agora">
            <div className="evac-numero">
              <span className="evac-numero-valor" data-testid="evac-total"><Numero valor={estado.total} /></span>
              <span className="evac-numero-rotulo">{pluralizar(estado.total, "pessoa detectada", "pessoas detectadas")} agora (soma das câmeras)</span>
            </div>
          </section>
          <section className="evac-grade" aria-label="Por câmera">
            {estado.cameras.map((c) => (
              <article key={c.id} className="card evac-camera" data-online={c.online ? "1" : "0"}>
                <header>
                  <h2>{c.nome}</h2>
                  {!c.online ? <Badge tone="error">Sem sinal</Badge> : c.desatualizada ? <Badge tone="warn">Análise atrasada</Badge> : null}
                </header>
                <p className="evac-camera-valor"><Numero valor={c.pessoas} /></p>
                <p className="evac-camera-rotulo">{pluralizar(c.pessoas, "pessoa agora", "pessoas agora")} · pico {c.maximo}</p>
              </article>
            ))}
          </section>
        </>
      ) : (
        <section className="card evac-ultima" data-testid="evac-ultima">
          {encerrada ? (
            <>
              <h2>Relatório nº {encerrada.relatorio.numero} encerrado</h2>
              <p>Duração {cronometro(encerrada.relatorio.duracao_s)} · pico somado {encerrada.relatorio.total_maximo_somado}</p>
              <p data-testid="evac-custodia">
                {encerrada.custodia_registrada
                  ? "Registrado na cadeia de custódia (SHA-256 encadeado)."
                  : "A cadeia de custódia está desligada neste ambiente: o relatório foi salvo, mas sem elo de integridade."}
              </p>
            </>
          ) : estado.ultima ? (
            <>
              <h2>Última evacuação: nº {estado.ultima.numero}</h2>
              <p>{dataHoraCurta(paraDate(estado.ultima.inicio))} · duração {cronometro(estado.ultima.duracao_s)} · pico somado {estado.ultima.total_maximo_somado}</p>
            </>
          ) : (
            <p>Nenhuma evacuação registrada. Ao acionar, cada câmera mostra quantas pessoas vê agora.</p>
          )}
        </section>
      )}
    </div>
  );
}

// --------------------------------------------------------- Regra sem código ---
const JANELA_DO_TESTE_H = 24;

export function CenaRegraSemCodigo({ regra, cameraId }: { regra: RegraDeExemplo | null; cameraId: number | null }) {
  const cameras = useDashboardStore((s) => s.cameras);
  const [opcoes, setOpcoes] = useState<Opcoes | null>(null);
  const [resultado, setResultado] = useState<ResultadoTeste | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [testando, setTestando] = useState(false);

  useEffect(() => {
    let vivo = true;
    apiFetch<Listagem>("/api/regras")
      .then((d) => vivo && setOpcoes(d.opcoes))
      .catch((e: unknown) => vivo && setErro(mensagemDeErro(e, "Não foi possível carregar o editor de regras.")));
    return () => {
      vivo = false;
    };
  }, []);

  const testar = useCallback(async () => {
    if (!regra || cameraId == null) return;
    setTestando(true);
    setErro(null);
    try {
      setResultado(await apiFetch<ResultadoTeste>("/api/regras/testar", { method: "POST", body: JSON.stringify({ regra, camera_id: cameraId, horas: JANELA_DO_TESTE_H }) }));
    } catch (e) {
      setResultado(null);
      setErro(mensagemDeErro(e, "Não foi possível testar a regra."));
    } finally {
      setTestando(false);
    }
  }, [regra, cameraId]);
  useEffect(() => {
    void testar();
  }, [testar]);

  if (!regra) return <p className="palco-vazio">Esta cena não trouxe a regra de exemplo.</p>;
  const nomeDaCamera = cameras.find((c) => c.id === cameraId)?.name;
  return (
    <div className="palco-regra" data-testid="palco-regra">
      <section className="card palco-regra-blocos" aria-label="A regra em blocos">
        <h2>{regra.nome}</h2>
        {opcoes ? <RegraEmBlocos regra={regra} opcoes={opcoes} nomesCameras={new Map(cameras.map((c) => [c.id, c.name]))} /> : <PanelSkeleton lines={5} />}
      </section>
      <section className="card palco-regra-teste" aria-label="Testar no histórico">
        <h2>Testar no histórico</h2>
        <p className="regras-dica">
          {cameraId == null
            ? "A câmera da cena não está cadastrada: não há trilha para testar."
            : `Reprocessa a trilha gravada da câmera ${nomeDaCamera ?? cameraId} (até ${JANELA_DO_TESTE_H} h). Não cria nem muda alerta real.`}
        </p>
        <div className="regras-resultado" data-testid="regras-resultado" data-estado={testando ? "carregando" : erro ? "erro" : resultado ? (resultado.simulavel ? "pronto" : "nao-simulavel") : "vazio"} aria-live="polite" aria-busy={testando}>
          {testando ? (
            <p className="regras-dica">Lendo a trilha gravada…</p>
          ) : erro ? (
            <p className="regras-erro-tela" role="alert" data-testid="regras-erro">{erro}</p>
          ) : resultado ? (
            <Resultado resultado={resultado} obsoleto={false} />
          ) : null}
        </div>
        <button type="button" className="small" onClick={() => void testar()} disabled={testando || cameraId == null}>
          Testar de novo
        </button>
      </section>
    </div>
  );
}

// ------------------------------------------------------ Permissão com vigia ---
type PermissaoDaCena = { id: number; numero: string; responsavel: string; inicio: string; fim: string; exige_vigia: boolean };
/** Mesmo texto que `app/services/palco_preparos.py` grava como responsável da permissão de demonstração. */
const RESPONSAVEL_DA_DEMO = "Equipe de demonstração";

function usePermissaoDaCena(cameraId: number): PermissaoDaCena | null {
  const [permissao, setPermissao] = useState<PermissaoDaCena | null>(null);
  useEffect(() => {
    let vivo = true;
    const buscar = () =>
      apiFetch<{ items: PermissaoDaCena[] }>(`/api/permissoes?camera_id=${cameraId}&status=ativa`)
        .then((d) => vivo && setPermissao(d.items.find((p) => p.responsavel === RESPONSAVEL_DA_DEMO) ?? null))
        .catch(() => vivo && setPermissao(null));
    void buscar();
    // Até a permissão aparecer: o servidor a emite em thread, ao entrar na cena.
    const id = window.setInterval(buscar, 2000);
    return () => {
      vivo = false;
      window.clearInterval(id);
    };
  }, [cameraId]);
  return permissao;
}

function PermissaoComCamera({ cameraId }: { cameraId: number }) {
  const estado = useCameraEstado(cameraId, 1000);
  const permissao = usePermissaoDaCena(cameraId);
  const semVigia = estado.alertas.find((a) => a.rule === "sem_vigia");
  return (
    <div className="palco-tape palco-permissao" data-testid="palco-permissao" data-sem-vigia={semVigia ? "1" : "0"}>
      <div className="palco-tape-video">
        <QuadroDaCena cameraId={cameraId} estado={estado} />
      </div>
      <aside className="palco-tape-painel">
        <p className="palco-aviso palco-aviso-norma" role="note" data-testid="palco-aviso-vigia">{AVISO_VIGIA}</p>
        {permissao ? (
          <dl className="palco-pt" data-testid="palco-pt">
            <div><dt>Permissão</dt><dd>{permissao.numero} · espaço confinado</dd></div>
            <div><dt>Responsável</dt><dd>{permissao.responsavel}</dd></div>
            <div><dt>Válida até</dt><dd>{horaCurta(paraDate(permissao.fim))}</dd></div>
            <div><dt>Área do vigia</dt><dd>{permissao.exige_vigia ? "canto inferior esquerdo da imagem" : "não exigida"}</dd></div>
          </dl>
        ) : (
          <p className="palco-tape-calmo" role="status">Emitindo a permissão de demonstração…</p>
        )}
        {semVigia ? (
          <div className="palco-alerta" role="alert" data-testid="palco-sem-vigia">
            <strong>Sem vigia</strong>
            <span>{semVigia.message}</span>
          </div>
        ) : (
          <p className="palco-tape-calmo">Sem alerta de vigia agora: ninguém entrou na zona, ou há alguém na área do vigia.</p>
        )}
      </aside>
    </div>
  );
}

export function CenaPermissaoComVigia({ cameraId }: { cameraId: number | null }) {
  return cameraId == null ? SEM_CAMERA : <PermissaoComCamera cameraId={cameraId} />;
}

// -------------------------------------------------- Primeiro acesso em 30 s ---
const PASSOS: PassoId[] = ["camera", "referencia", "planta", "zonas", "epis", "usuarios", "pronto"];

export function CenaPrimeiroAcesso() {
  const { dados, erro } = useOnboarding();
  // Sem sessão de Supervisor o servidor recusa (403): a trilha vai estática, sem fingir o que foi detectado.
  const estatica = !dados && erro !== null;
  const ordem = dados?.ordem ?? PASSOS;
  return (
    <div className="palco-primeiro" data-testid="palco-primeiro-acesso" data-detectado={dados ? "1" : "0"}>
      <p className="palco-primeiro-frase" data-testid="palco-primeiro-frase">
        {dados
          ? "Cada passo abaixo foi detectado agora pelo sistema, nesta máquina."
          : estatica
            ? "No produto, cada passo detecta sozinho o que já está pronto."
            : "Lendo o que o sistema já detectou…"}
      </p>
      <ol className="palco-passos" aria-label="Passos do primeiro acesso">
        {ordem.map((id, i) => {
          const passo = dados?.passos.find((p) => p.passo === id);
          return (
            <li key={id} className="palco-passo" data-passo={id} data-estado={passo?.estado ?? "estatico"}>
              <span className="palco-passo-numero" aria-hidden="true">{i + 1}</span>
              <div className="palco-passo-texto">
                <strong>{INFO[id].titulo}</strong>
                <span>{INFO[id].porque}</span>
                {passo?.detalhe && (
                  <small className={passo.detectado ? "ok" : ""}>
                    {passo.detectado ? "Encontrado: " : "Ainda não: "}
                    {passo.detalhe}
                  </small>
                )}
              </div>
              {passo && <EstadoDoPasso passo={passo} />}
            </li>
          );
        })}
      </ol>
      {estatica && erro && erro.status !== 403 && <p className="evac-nota" role="status">{erro.msg}</p>}
    </div>
  );
}
