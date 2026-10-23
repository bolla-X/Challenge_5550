import { useCallback, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { ApiError } from "../api/client";
import { getStatusDoSistema } from "../api/status-do-sistema";
import type {
  CameraDoStatus,
  EstadoDoComponente,
  IntegracaoDoStatus,
  ModeloDoStatus,
  PastaDoStatus,
  StatusDoSistema,
  VolumeDoStatus,
} from "../api/status-do-sistema";
import { mensagemDeErro } from "../utils/erros";
import { dataHoraCurta, paraDate } from "../utils/datas";
import { bytesLegiveis, decimal, inteiro, pluralizar } from "../utils/formato";
import { EmptyState, PanelSkeleton } from "./common";
import { IlustracaoEscudo } from "./ilustracoes";
import "../styles/status.css";

/**
 * Saúde do sistema (`/status`, técnico ou acima): um cartão por componente.
 * Contrato: GET /api/status (app/services/status_do_sistema.py). A cor aparece só
 * no selo de estado (ponto + palavra); o resto do cartão é neutro.
 *
 * Atualiza sozinha a cada 10 s enquanto a aba está visível. Se uma atualização
 * falha, a tela mantém o último retrato (com a idade dele) e avisa, em vez de apagar tudo.
 */

const INTERVALO_MS = 10_000;

const ROTULO_DO_ESTADO: Record<EstadoDoComponente, string> = {
  ok: "OK",
  atencao: "Atenção",
  falha: "Falha",
  desligado: "Desligado",
};
const ROTULO_DA_SITUACAO: Record<CameraDoStatus["situacao"], string> = {
  no_ar: "No ar",
  sem_sinal: "Sem sinal",
  parada: "Parada",
  apresentacao: "Em apresentação",
};
const ROTULO_DO_MODELO: Record<string, string> = { epi: "EPI", pessoa: "Pessoa", pose: "Pose" };
const ROTULO_DO_RUNTIME: Record<string, string> = {
  openvino: "OpenVINO",
  onnx: "ONNX",
  pytorch: "PyTorch",
  "pytorch (fallback)": "PyTorch (reserva)",
};
const ROTULO_DO_MOTOR: Record<string, string> = { sqlite: "SQLite", postgresql: "PostgreSQL", mysql: "MySQL" };

function textoDoErro(err: unknown): string {
  // O prazo da chamada estourou: o navegador entrega um DOMException em inglês.
  if (err instanceof DOMException && (err.name === "TimeoutError" || err.name === "AbortError")) return "O servidor demorou demais para responder.";
  return mensagemDeErro(err, "Não foi possível ler o status do sistema.");
}

/** Ponto + palavra. Só o ponto e o selo carregam a cor do estado. */
export function SeloDeEstado({ estado, rotulo, neutro = false }: { estado: EstadoDoComponente; rotulo?: string; neutro?: boolean }) {
  // `neutro`: o componente responde, mas não é "ligado de verdade" (ex.: LLM em modo demonstração), então sem verde.
  const classe = neutro ? "chip" : estado === "ok" ? "chip ok" : estado === "falha" ? "chip miss" : "chip";
  return (
    <span className={`${classe} status-selo`} data-estado={estado}>
      {estado === "ok" && !neutro && <span className="dot" aria-hidden="true" />}
      {estado === "atencao" && <span className="status-anel" aria-hidden="true" />}
      {rotulo ?? ROTULO_DO_ESTADO[estado]}
    </span>
  );
}

/** `texto`: o valor é frase, não número nem código (sai na fonte do texto, não na monoespaçada). */
function Linha({ rotulo, children, texto = false }: { rotulo: string; children: ReactNode; texto?: boolean }) {
  return (
    <div className="status-row">
      <span className="status-row-label">{rotulo}</span>
      <span className={texto ? "status-row-value texto" : "status-row-value"}>{children}</span>
    </div>
  );
}

function Cartao({
  id,
  titulo,
  estado,
  resumo,
  largo = false,
  rotuloDoSelo,
  seloNeutro = false,
  children,
}: {
  id: string;
  titulo: string;
  estado: EstadoDoComponente;
  resumo?: string;
  largo?: boolean;
  rotuloDoSelo?: string;
  seloNeutro?: boolean;
  children?: ReactNode;
}) {
  return (
    <section className={`card status-cartao ${largo ? "largo" : ""}`.trim()} data-testid={`status-${id}`} data-estado={estado} aria-labelledby={`status-${id}-t`}>
      <div className="status-cartao-topo">
        <h2 id={`status-${id}-t`}>{titulo}</h2>
        <SeloDeEstado estado={estado} rotulo={rotuloDoSelo} neutro={seloNeutro} />
      </div>
      {resumo && <p className="status-resumo-do-cartao">{resumo}</p>}
      {children && <div className="status-list">{children}</div>}
    </section>
  );
}

function segundos(ms: number | null | undefined): string | null {
  return typeof ms === "number" ? `${decimal(ms / 1000, ms >= 10_000 ? 0 : 1)} s` : null;
}

// ------------------------------------------------------------------ modelos --
function CartaoDeModelos({ dados }: { dados: StatusDoSistema["componentes"]["modelos"] }) {
  const modelos: ModeloDoStatus[] = dados.modelos ?? [];
  return (
    <Cartao id="modelos" titulo="Modelos de visão" estado={dados.estado} resumo={dados.resumo} largo>
      {modelos.length > 0 && (
        <div className="tabela-rolavel">
        <table className="tabela status-tabela">
          <thead>
            <tr>
              <th scope="col">Modelo</th>
              <th scope="col">Runtime</th>
              <th scope="col">Dispositivo</th>
              <th scope="col" className="num">Carga</th>
              <th scope="col" className="num">Aquecimento</th>
            </tr>
          </thead>
          <tbody>
            {modelos.map((m) => {
              const runtime = m.runtime_validado ?? m.runtime;
              const pedido = m.runtime_pedido;
              const pediuOutro = pedido && runtime && !runtime.startsWith(pedido) && pedido !== "auto";
              return (
                <tr key={m.nome}>
                  <th scope="row">{ROTULO_DO_MODELO[m.nome] ?? m.nome}</th>
                  <td>
                    {runtime ? (ROTULO_DO_RUNTIME[runtime] ?? runtime) : "ainda não carregou"}
                    {pediuOutro ? <small> (pedido: {ROTULO_DO_RUNTIME[pedido] ?? pedido})</small> : null}
                  </td>
                  <td>{m.dispositivo ?? "-"}</td>
                  <td className="num">{segundos(m.carga_ms) ?? "-"}</td>
                  <td className="num">{m.aquecido ? segundos(m.aquecimento_ms) : "sem aquecer"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        </div>
      )}
      {dados.degradado && <Linha rotulo="Desempenho" texto>reduzindo a carga para acompanhar</Linha>}
    </Cartao>
  );
}

// ------------------------------------------------------------------ câmeras --
function CartaoDeCameras({ dados }: { dados: StatusDoSistema["componentes"]["cameras"] }) {
  const cameras: CameraDoStatus[] = dados.cameras ?? [];
  return (
    <Cartao id="cameras" titulo="Câmeras" estado={dados.estado} resumo={dados.resumo} largo>
      {cameras.length > 0 && (
        <ul className="status-cameras">
          {cameras.map((c) => (
            <li key={c.id} data-testid={`status-camera-${c.id}`}>
              <span className="status-camera-nome">{c.nome}</span>
              <span className="status-camera-detalhe">
                {c.situacao !== "parada" && typeof c.fps === "number" ? `${decimal(c.fps)} fps` : null}
                {c.situacao === "sem_sinal" && c.tentativas_de_reconexao ? `${pluralizar(c.tentativas_de_reconexao, "tentativa")} de reconexão` : null}
              </span>
              <span className="status-camera-imagem">Imagem: {c.saude_visual.rotulo === "OK" ? "OK" : c.saude_visual.rotulo.toLowerCase()}</span>
              <SeloDeEstado estado={c.estado} rotulo={ROTULO_DA_SITUACAO[c.situacao]} />
            </li>
          ))}
        </ul>
      )}
    </Cartao>
  );
}

// -------------------------------------------------------------------- banco --
function CartaoDoBanco({ dados }: { dados: StatusDoSistema["componentes"]["banco"] }) {
  return (
    <Cartao id="banco" titulo="Banco de dados" estado={dados.estado} resumo={dados.resumo}>
      {dados.motor && <Linha rotulo="Motor">{ROTULO_DO_MOTOR[dados.motor] ?? dados.motor}</Linha>}
      {typeof dados.consulta_ms === "number" && <Linha rotulo="Consulta simples">{decimal(dados.consulta_ms)} ms</Linha>}
      {dados.arquivo && (
        <Linha rotulo="Arquivo">
          {dados.arquivo}
          {typeof dados.bytes === "number" ? `, ${bytesLegiveis(dados.bytes)}` : ""}
        </Linha>
      )}
    </Cartao>
  );
}

// ------------------------------------------------------------- integrações --
function CartaoDeIntegracao({ id, titulo, dados }: { id: string; titulo: string; dados: IntegracaoDoStatus }) {
  return (
    <Cartao id={id} titulo={titulo} estado={dados.estado} resumo={dados.resumo}>
      {dados.endpoint && <Linha rotulo="Endereço">{dados.endpoint}</Linha>}
      {dados.erro && <Linha rotulo="Motivo" texto>{dados.erro}</Linha>}
      {dados.estatisticas && (
        <Linha rotulo="Envios">
          {inteiro(dados.estatisticas.enviados)} enviados, {pluralizar(dados.estatisticas.falhas, "falha")}, {inteiro(dados.estatisticas.pendentes)} na fila
        </Linha>
      )}
      {dados.estado === "desligado" && <Linha rotulo="Para ligar" texto>defina <code>{dados.como_ligar}</code> no arquivo <code>.env</code></Linha>}
    </Cartao>
  );
}

// ---------------------------------------------------------------------- LLM --
function CartaoDoLlm({ dados }: { dados: StatusDoSistema["componentes"]["llm"] }) {
  const demonstracao = dados.modo === "demonstracao";
  const rotulo = demonstracao
    ? "Demonstração"
    : dados.estado === "ok" ? "Ligada" : dados.estado === "desligado" ? "Desligada" : dados.tem_chave === false ? "Sem chave" : undefined;
  return (
    <Cartao id="llm" titulo="Segunda opinião (LLM)" estado={dados.estado} resumo={dados.resumo} rotuloDoSelo={rotulo} seloNeutro={demonstracao}>
      <Linha rotulo="Chave de acesso" texto>{dados.tem_chave ? "configurada" : "não configurada"}</Linha>
      {dados.versao_do_prompt && <Linha rotulo="Versão do prompt">{dados.versao_do_prompt}</Linha>}
      {typeof dados.intervalo_minimo_s === "number" && <Linha rotulo="Intervalo mínimo por câmera">{decimal(dados.intervalo_minimo_s, 0)} s</Linha>}
      {typeof dados.limite_de_espera_s === "number" && <Linha rotulo="Limite de espera">{decimal(dados.limite_de_espera_s, 0)} s</Linha>}
      {(dados.estado !== "ok" || demonstracao) && dados.como_ligar && (
        <Linha rotulo="Para ligar" texto>
          defina <code>{dados.como_ligar}</code> no ambiente do terminal antes de subir o servidor (no modo demonstração o arquivo <code>.env</code> não é lido)
        </Linha>
      )}
    </Cartao>
  );
}

// -------------------------------------------------------------------- disco --
function Volume({ rotulo, volume }: { rotulo: string; volume: VolumeDoStatus }) {
  if (typeof volume.total_bytes !== "number" || typeof volume.usado_bytes !== "number") {
    return <Linha rotulo={rotulo}>{volume.resumo ?? "não medido"}</Linha>;
  }
  const usadoPct = volume.total_bytes ? Math.min(100, Math.round((volume.usado_bytes / volume.total_bytes) * 100)) : 0;
  return (
    <div className="status-volume">
      <div className="status-row">
        <span className="status-row-label">{rotulo}</span>
        <span className="status-row-value">
          {bytesLegiveis(volume.livre_bytes ?? 0)} livres de {bytesLegiveis(volume.total_bytes)}
        </span>
      </div>
      <div className="status-barra" role="img" aria-label={`${usadoPct}% do disco em uso`}>
        <span style={{ width: `${usadoPct}%` }} />
      </div>
    </div>
  );
}

function tamanhoDaPasta(p: PastaDoStatus): string {
  if (!p.existe) return "ainda não existe";
  return `${p.parcial ? "pelo menos " : ""}${bytesLegiveis(p.bytes)}, ${pluralizar(p.arquivos, "arquivo")}`;
}

function CartaoDeDisco({ dados }: { dados: StatusDoSistema["componentes"]["disco"] }) {
  return (
    <Cartao id="disco" titulo="Espaço em disco" estado={dados.estado} resumo={dados.resumo} largo>
      {dados.volumes && (
        <>
          <Volume rotulo="Pasta de evidências" volume={dados.volumes.evidencias} />
          <Volume rotulo="Pasta da instância (banco)" volume={dados.volumes.instancia} />
        </>
      )}
      {dados.pastas && (
        <>
          <Linha rotulo="Imagens de evidência">{tamanhoDaPasta(dados.pastas.imagens)}</Linha>
          <Linha rotulo="Clipes de replay">{tamanhoDaPasta(dados.pastas.clipes)}</Linha>
          <Linha rotulo="Trilhas do simulador">{tamanhoDaPasta(dados.pastas.trilhas)}</Linha>
        </>
      )}
    </Cartao>
  );
}

// ------------------------------------------------------------------ painel --
function resumoGeral(dados: StatusDoSistema): { estado: EstadoDoComponente; texto: string } {
  const itens = Object.values(dados.componentes);
  const falhas = itens.filter((i) => i.estado === "falha").length;
  const atencoes = itens.filter((i) => i.estado === "atencao").length;
  if (falhas) return { estado: "falha", texto: `${pluralizar(falhas, "componente com falha", "componentes com falha")}` };
  if (atencoes) return { estado: "atencao", texto: `${pluralizar(atencoes, "componente pede atenção", "componentes pedem atenção")}` };
  return { estado: "ok", texto: "Tudo em ordem" };
}

function idade(desde: number | null, agora: number): string {
  if (desde === null) return "";
  const s = Math.max(0, Math.round((agora - desde) / 1000));
  return s < 2 ? "agora" : `há ${s} s`;
}

export default function PaginaStatus() {
  const [dados, setDados] = useState<StatusDoSistema | null>(null);
  const [recebidoEm, setRecebidoEm] = useState<number | null>(null);
  const [erro, setErro] = useState<{ msg: string; status?: number } | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [agora, setAgora] = useState(() => Date.now());
  const emVoo = useRef(false);

  const carregar = useCallback(async () => {
    if (emVoo.current) return;
    emVoo.current = true;
    setCarregando(true);
    try {
      const resposta = await getStatusDoSistema();
      setDados(resposta);
      setRecebidoEm(Date.now());
      setErro(null);
    } catch (err) {
      setErro({ msg: textoDoErro(err), status: err instanceof ApiError ? err.status : undefined });
    } finally {
      emVoo.current = false;
      setCarregando(false);
    }
  }, []);

  useEffect(() => {
    void carregar();
    const atualiza = window.setInterval(() => {
      if (document.visibilityState === "visible") void carregar();
    }, INTERVALO_MS);
    const relogio = window.setInterval(() => setAgora(Date.now()), 1000);
    return () => {
      window.clearInterval(atualiza);
      window.clearInterval(relogio);
    };
  }, [carregar]);

  if (erro?.status === 403) {
    return (
      <div className="screen pagina-status">
        <EmptyState ilustracao={<IlustracaoEscudo />} titulo="Acesso restrito">
          O status do sistema é do Técnico para cima. Peça a quem tem esse tipo de conta.
        </EmptyState>
      </div>
    );
  }

  const geral = dados ? resumoGeral(dados) : null;
  const c = dados?.componentes;

  return (
    <div className="screen pagina-status" data-testid="pagina-status" aria-busy={carregando && !dados}>
      <header className="screen-head">
        <h1>Status do sistema</h1>
        {recebidoEm !== null && (
          <p className="screen-sub" data-testid="status-idade">
            Atualizado {idade(recebidoEm, agora)}
          </p>
        )}
        <div className="screen-actions">
          <button type="button" className="ghost" disabled={carregando} title={carregando ? "Lendo o estado agora; aguarde" : undefined} onClick={() => void carregar()}>
            {carregando && dados ? "Atualizando…" : "Atualizar"}
          </button>
          <a className="button ghost" href="/">
            Voltar ao painel
          </a>
        </div>
      </header>

      {erro && (
        <div className="status-erro" role="alert">
          <p>
            {erro.msg}
            {dados && recebidoEm !== null ? ` Mostrando o retrato de ${idade(recebidoEm, agora)}.` : ""}
          </p>
          <button type="button" onClick={() => void carregar()} disabled={carregando}>
            Tentar de novo
          </button>
        </div>
      )}

      {geral && (
        <p className="status-geral" data-estado={geral.estado} data-testid="status-geral">
          <SeloDeEstado estado={geral.estado} rotulo={geral.estado === "ok" ? "OK" : undefined} />
          <span>{geral.texto}</span>
        </p>
      )}

      {!dados && !erro && (
        <div className="status-grade" data-testid="status-carregando">
          {Array.from({ length: 6 }).map((_, i) => (
            <div className="card status-cartao" key={i}>
              <PanelSkeleton lines={3} />
            </div>
          ))}
        </div>
      )}

      {c && (
        <div className="status-grade">
          <CartaoDeModelos dados={c.modelos} />
          <CartaoDeCameras dados={c.cameras} />
          <CartaoDoBanco dados={c.banco} />
          <CartaoDeIntegracao id="opcua" titulo="OPC UA" dados={c.opcua} />
          <CartaoDeIntegracao id="mqtt" titulo="MQTT" dados={c.mqtt} />
          <CartaoDeIntegracao id="broker" titulo="Broker MQTT embutido" dados={c.broker} />
          <CartaoDeIntegracao id="webhook" titulo="Webhook" dados={c.webhook} />
          <CartaoDoLlm dados={c.llm} />
          <CartaoDeDisco dados={c.disco} />
          <section className="card status-cartao" data-testid="status-versao" aria-labelledby="status-versao-t">
            <div className="status-cartao-topo">
              <h2 id="status-versao-t">Versão do painel</h2>
            </div>
            <div className="status-list">
              <Linha rotulo="Compilado em">{dados?.versao.construido_em ? dataHoraCurta(paraDate(dados.versao.construido_em)) : "não informado"}</Linha>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
