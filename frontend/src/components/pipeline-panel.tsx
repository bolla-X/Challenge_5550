import { mensagemDeErro } from "../utils/erros";
import { useEffect, useState } from "react";
import { Panel, PanelSkeleton } from "./common";
import { estatisticasDoVideo } from "./live-video";
import { decimal, pluralizar } from "../utils/formato";

/**
 * Painel de diagnóstico de engenharia (F5): de onde vem cada milissegundo.
 *
 * Tudo aqui é MEDIDO, não estimado: percentis do próprio loop
 * (`GET /api/diagnostics/pipeline`, app/services/pipeline_stats.py) e, do lado
 * do navegador, o que o player em canvas de fato exibiu. Atualiza a 1 Hz —
 * é diagnóstico, não vídeo.
 */
type Etapa = { n: number; p50: number | null; p95: number | null; p99: number | null };
type CameraDiag = {
  running: boolean;
  fonte_fps: number | null;
  alvo_fps: number;
  detectar_a_cada_n: number;
  espectadores: number;
  stats: { etapas: Record<string, Etapa>; taxas_por_s: Record<string, number> };
};
type Diag = {
  cameras: Record<string, CameraDiag>;
  modelos: Record<
    string,
    { caminho: string | null; imgsz: number | null; runtime: string | null; carga_ms: number | null; dispositivo?: string | null }
  >;
  agendador: { modo: string; inferencias: number; ultimo_erro: string | null } | null;
  adaptativo: { nivel: number; nivel_max: number; degradado: boolean; reducoes: string[]; motivo: string | null } | null;
};

// Ordem do caminho de um quadro: captura → análise (no agendador) → publicação → saída.
const GRUPOS: { titulo: string; etapas: [string, string][] }[] = [
  { titulo: "Captura e preparo", etapas: [["preprocessamento", "Redução / rotação"]] },
  {
    titulo: "Análise (agendador de inferência)",
    etapas: [
      ["inferencia_epi", "Modelo de EPI"],
      ["inferencia_pessoa", "Modelo de pessoa"],
      ["inferencia_pose", "Pose (várias pessoas)"],
      ["tracking", "Rastreamento"],
      ["filtro_epi", "EPI ↔ pessoa"],
      ["pose", "Esqueleto por pessoa"],
    ],
  },
  {
    titulo: "Publicação (loop da câmera)",
    etapas: [
      ["regras", "Regras"],
      ["alertas", "Histerese / alertas"],
      ["conformidade", "Conformidade"],
      ["replay", "Memória do replay"],
      ["emissao", "Envio em tempo real"],
    ],
  },
  {
    titulo: "Saída (só quando alguém assiste)",
    etapas: [
      ["privacidade", "Desfoque de rosto"],
      ["encode", "JPEG"],
      ["anotacao", "Anotação no pixel"],
    ],
  },
];

function ms(v: number | null | undefined): string {
  if (v == null) return "sem dado";
  return v >= 100 ? `${Math.round(v)} ms` : `${decimal(v)} ms`;
}

export function PipelinePanel({ cameraId }: { cameraId: number }) {
  const [diag, setDiag] = useState<Diag | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [video, setVideo] = useState(() => estatisticasDoVideo(cameraId));

  useEffect(() => {
    let vivo = true;
    const atualizar = () => {
      fetch("/api/diagnostics/pipeline?janela_s=10", { credentials: "same-origin" })
        .then((r) => (r.ok ? r.json() : Promise.reject(new Error("Falha ao carregar o diagnóstico."))))
        .then((d: Diag) => vivo && (setDiag(d), setErro(null)))
        .catch((e) => vivo && setErro(mensagemDeErro(e, "Falha ao carregar os dados.")));
      setVideo(estatisticasDoVideo(cameraId));
    };
    atualizar();
    const id = window.setInterval(atualizar, 1000);
    return () => {
      vivo = false;
      window.clearInterval(id);
    };
  }, [cameraId]);

  const cam = diag?.cameras[String(cameraId)];
  const etapas = cam?.stats.etapas ?? {};
  const taxas = cam?.stats.taxas_por_s ?? {};
  const maior = Math.max(1, ...Object.values(etapas).map((e) => e.p95 ?? 0).filter((v) => v < 60_000));

  return (
    <Panel id="panel-pipeline" title="Diagnóstico do processamento" description="Medido no próprio loop, janela de 10 s. p50 na barra cheia, p95 no traço.">
      {erro && <p className="status-text error">{erro}</p>}
      {!cam ? (
        diag ? <p className="status-text">Câmera parada ou sem dados ainda.</p> : <PanelSkeleton lines={3} />
      ) : (
        <div className="pipe">
          <div className="pipe-kpis">
            <Kpi rotulo="FPS lido da fonte" valor={taxas.frames_lidos} />
            <Kpi rotulo="FPS analisado" valor={taxas.inferencias} />
            <Kpi rotulo="FPS publicado" valor={taxas.frames_publicados} />
            <Kpi rotulo="FPS exibido nesta tela" valor={video?.fps} />
          </div>
          <div className="pipe-kpis">
            <Kpi rotulo="Idade ao publicar (p95)" texto={ms(etapas.idade_publicacao?.p95)} />
            <Kpi rotulo="Idade da análise (p95)" texto={ms(etapas.idade_na_inferencia?.p95)} />
            <Kpi rotulo="Idade na tela (p95)" texto={ms(video?.idadeP95)} />
            <Kpi rotulo="Quadros descartados/s" valor={(taxas.frames_descartados ?? 0) + (taxas.frames_acima_do_alvo ?? 0)} />
          </div>
          {GRUPOS.map((grupo) => (
            <section key={grupo.titulo} className="pipe-grupo">
              <h4>{grupo.titulo}</h4>
              {grupo.etapas
                .filter(([chave]) => etapas[chave])
                .map(([chave, rotulo]) => {
                  const e = etapas[chave];
                  return (
                    <div key={chave} className="pipe-linha" data-etapa={chave}>
                      <span className="pipe-rotulo">{rotulo}</span>
                      <span className="pipe-barra" aria-hidden="true">
                        <span className="pipe-p50" style={{ width: `${Math.min(100, ((e.p50 ?? 0) / maior) * 100)}%` }} />
                        <span className="pipe-p95" style={{ left: `${Math.min(100, ((e.p95 ?? 0) / maior) * 100)}%` }} />
                      </span>
                      <span className="pipe-num t-data">
                        {ms(e.p50)} · p95 {ms(e.p95)}
                      </span>
                    </div>
                  );
                })}
            </section>
          ))}
          <section className="pipe-grupo">
            <h4>Modelos e controle</h4>
            {Object.entries(diag?.modelos ?? {}).map(([nome, m]) => (
              <div key={nome} className="pipe-linha" data-testid={`runtime-${nome}`}>
                <span className="pipe-rotulo">{nome === "epi" ? "EPI" : nome === "pessoa" ? "Pessoa" : "Pose"}</span>
                <span className="pipe-num t-data">
                  {(m.runtime ?? "?").toUpperCase()}
                  {m.dispositivo ? ` em ${m.dispositivo}` : ""} · imagem {m.imgsz ?? "?"} px ·{m.caminho?.split(/[\\/]/).pop()}
                </span>
              </div>
            ))}
            <div className="pipe-linha">
              <span className="pipe-rotulo">Modo adaptativo</span>
              <span className="pipe-num t-data">
                {diag?.adaptativo?.degradado
                  ? `nível ${diag.adaptativo.nivel}/${diag.adaptativo.nivel_max}: ${diag.adaptativo.reducoes.join("; ")}`
                  : "normal (nada reduzido)"}
              </span>
            </div>
            <div className="pipe-linha">
              <span className="pipe-rotulo">Câmera</span>
              <span className="pipe-num t-data">
                fonte {cam.fonte_fps ? `${decimal(cam.fonte_fps)} fps` : "?"} · alvo {cam.alvo_fps} fps · detectar a cada {cam.detectar_a_cada_n} ·{" "}
                {pluralizar(cam.espectadores, "espectador", "espectadores")} · agendador {diag?.agendador?.modo ?? "síncrono"}
              </span>
            </div>
          </section>
        </div>
      )}
    </Panel>
  );
}

function Kpi({ rotulo, valor, texto }: { rotulo: string; valor?: number | null; texto?: string }) {
  return (
    <div className="pipe-kpi">
      <span className="pipe-kpi-valor t-data">{texto ?? (valor == null ? "sem dado" : decimal(valor))}</span>
      <span className="pipe-kpi-rotulo">{rotulo}</span>
    </div>
  );
}
