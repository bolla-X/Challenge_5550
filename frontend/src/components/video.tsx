import { useEffect, useRef, useState } from "react";
import { useDashboardStore } from "../store/dashboardStore";
import { useAreaDeteccao, type ModoDeDesenho, type TipoDeArea } from "../store/areaDeteccaoStore";
import { Panel } from "./common";
import { pluralizar } from "../utils/formato";
import { retanguloEntre, riscoForaDaArea, type Ponto } from "../utils/poligono";

const COR_RISCO = "#f59e0b";
// Área de detecção: neutra (branco gelo, tracejado), nunca a cor de perigo.
const COR_DETECCAO = "rgba(245,245,247,0.95)";

/**
 * Camada do editor de áreas: desenha o polígono em edição e captura os cliques.
 * Fica por cima do vídeo, dentro de um contêiner `position: relative` (o
 * `.video-frame`). Edita a área de RISCO (cliques de polígono) ou a área de
 * DETECÇÃO (retângulo arrastado ou cliques de polígono), conforme o seletor do
 * painel "Áreas".
 *
 * As coordenadas são normalizadas em relação ao VÍDEO, não ao contêiner: o vídeo
 * usa `object-fit: contain`, então quando a fonte não é 16:9 (ex.: câmera girada
 * em pé) sobram faixas pretas, e normalizar pelo contêiner deslocaria a área.
 */
export function RiskEditorCanvas({ wrapRef }: { wrapRef: React.RefObject<HTMLDivElement | null> }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const riskEditorActive = useDashboardStore((s) => s.riskEditorActive);
  const riskEditorPoints = useDashboardStore((s) => s.riskEditorPoints);
  const addRiskEditorPoint = useDashboardStore((s) => s.addRiskEditorPoint);
  const moveRiskEditorPoint = useDashboardStore((s) => s.moveRiskEditorPoint);
  const tipo = useAreaDeteccao((s) => s.tipo);
  const modo = useAreaDeteccao((s) => s.modo);
  const editandoDeteccao = useAreaDeteccao((s) => s.editando);
  const pontosDeteccao = useAreaDeteccao((s) => s.pontos);
  const setPontos = useAreaDeteccao((s) => s.setPontos);
  const arrastando = useRef<number | null>(null);
  const cantoInicial = useRef<Ponto | null>(null);

  const deteccao = tipo === "deteccao";
  const ativo = deteccao ? editandoDeteccao : riskEditorActive;
  const pontos = deteccao ? pontosDeteccao : riskEditorPoints;

  // Retângulo (em px do contêiner) que o vídeo realmente ocupa.
  const areaDoVideo = () => {
    const wrap = wrapRef.current;
    if (!wrap) return null;
    const box = wrap.getBoundingClientRect();
    // O vídeo agora é o <canvas class="live-video">, que publica o tamanho do
    // quadro em data-w/data-h; <img> fica como fallback.
    const live = wrap.querySelector<HTMLCanvasElement>("canvas.live-video");
    const img = wrap.querySelector("img");
    const nw = Number(live?.dataset.w) || img?.naturalWidth || 0;
    const nh = Number(live?.dataset.h) || img?.naturalHeight || 0;
    if (!nw || !nh) return { x: 0, y: 0, w: box.width, h: box.height, box };
    const scale = Math.min(box.width / nw, box.height / nh);
    const w = nw * scale;
    const h = nh * scale;
    return { x: (box.width - w) / 2, y: (box.height - h) / 2, w, h, box };
  };

  const draw = () => {
    const canvas = canvasRef.current;
    const area = areaDoVideo();
    if (!canvas || !area) return;
    const { box } = area;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.max(1, Math.floor(box.width * dpr));
    canvas.height = Math.max(1, Math.floor(box.height * dpr));
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, box.width, box.height);
    if (!pontos.length) return;
    const cor = deteccao ? COR_DETECCAO : COR_RISCO;
    const px = (p: { x: number; y: number }) => [area.x + p.x * area.w, area.y + p.y * area.h] as const;
    ctx.lineWidth = 2;
    ctx.strokeStyle = cor;
    ctx.fillStyle = deteccao ? "rgba(245,245,247,.10)" : "rgba(245, 158, 11, .12)";
    ctx.setLineDash(deteccao ? [8, 6] : []);
    ctx.shadowColor = deteccao ? "rgba(0,0,0,.6)" : "transparent";
    ctx.shadowBlur = deteccao ? 3 : 0;
    ctx.beginPath();
    pontos.forEach((p, i) => {
      const [x, y] = px(p);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    if (pontos.length >= 3) ctx.closePath();
    ctx.stroke();
    ctx.setLineDash([]);
    if (pontos.length >= 3) ctx.fill();
    pontos.forEach((p, i) => {
      const [x, y] = px(p);
      ctx.beginPath();
      ctx.arc(x, y, 5, 0, Math.PI * 2);
      ctx.fillStyle = cor;
      ctx.fill();
      ctx.fillStyle = "#f8fafc";
      ctx.font = "bold 11px system-ui";
      ctx.fillText(String(i + 1), x + 8, y - 8);
    });
  };

  useEffect(() => {
    draw();
    const img = wrapRef.current?.querySelector("img");
    window.addEventListener("resize", draw);
    img?.addEventListener("load", draw);
    return () => {
      window.removeEventListener("resize", draw);
      img?.removeEventListener("load", draw);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pontos, ativo, deteccao]);

  // Posição do ponteiro em coordenadas do vídeo (0..1) e em px do canvas.
  const posicao = (event: React.PointerEvent<HTMLCanvasElement>) => {
    const area = areaDoVideo();
    if (!area || !area.w || !area.h) return null;
    const box = event.currentTarget.getBoundingClientRect();
    const px = event.clientX - box.left;
    const py = event.clientY - box.top;
    return { area, px, py, x: (px - area.x) / area.w, y: (py - area.y) / area.h };
  };

  // Ponto já existente sob o ponteiro (raio de 12 px), ou -1.
  const pontoPerto = (pos: NonNullable<ReturnType<typeof posicao>>) => {
    let melhor = -1;
    let menor = 12;
    pontos.forEach((p, i) => {
      const d = Math.hypot(pos.area.x + p.x * pos.area.w - pos.px, pos.area.y + p.y * pos.area.h - pos.py);
      if (d <= menor) {
        menor = d;
        melhor = i;
      }
    });
    return melhor;
  };

  const arredondar = (v: number) => Math.round(Math.max(0, Math.min(1, v)) * 10000) / 10000;
  const noVideo = (pos: { x: number; y: number }) => ({ x: arredondar(pos.x), y: arredondar(pos.y) });
  const adicionar = (p: Ponto) => (deteccao ? setPontos([...pontosDeteccao, p]) : addRiskEditorPoint(p));
  const mover = (i: number, p: Ponto) =>
    deteccao ? setPontos(pontosDeteccao.map((q, k) => (k === i ? p : q))) : moveRiskEditorPoint(i, p);

  // Polígono: apertar EM CIMA de um ponto e arrastar o move; apertar em espaço
  // vazio cria um ponto novo. Retângulo (só na área de detecção): apertar e
  // arrastar desenha de um canto ao outro.
  const handlePointerDown = (event: React.PointerEvent<HTMLCanvasElement>) => {
    if (!ativo) return;
    const pos = posicao(event);
    if (!pos) return;
    if (deteccao && modo === "retangulo") {
      if (pos.x < 0 || pos.x > 1 || pos.y < 0 || pos.y > 1) return; // faixa preta
      cantoInicial.current = noVideo(pos);
      setPontos([]);
      event.currentTarget.setPointerCapture(event.pointerId);
      return;
    }
    const perto = pontoPerto(pos);
    if (perto >= 0) {
      arrastando.current = perto;
      event.currentTarget.setPointerCapture(event.pointerId);
      return;
    }
    if (pos.x < 0 || pos.x > 1 || pos.y < 0 || pos.y > 1) return; // faixa preta
    adicionar(noVideo(pos));
  };

  const handlePointerMove = (event: React.PointerEvent<HTMLCanvasElement>) => {
    if (!ativo) return;
    const pos = posicao(event);
    if (!pos) return;
    if (cantoInicial.current) {
      setPontos(retanguloEntre(cantoInicial.current, noVideo(pos)));
      return;
    }
    if (arrastando.current !== null) {
      mover(arrastando.current, noVideo(pos));
      return;
    }
    event.currentTarget.style.cursor = deteccao && modo === "retangulo" ? "crosshair" : pontoPerto(pos) >= 0 ? "grab" : "crosshair";
  };

  const handlePointerUp = (event: React.PointerEvent<HTMLCanvasElement>) => {
    if (cantoInicial.current) {
      const pos = posicao(event);
      if (pos) setPontos(retanguloEntre(cantoInicial.current, noVideo(pos)));
      cantoInicial.current = null;
      event.currentTarget.releasePointerCapture(event.pointerId);
      return;
    }
    if (arrastando.current === null) return;
    arrastando.current = null;
    event.currentTarget.releasePointerCapture(event.pointerId);
  };

  return (
    <canvas
      ref={canvasRef}
      className={`risk-editor-canvas ${ativo ? "" : "hidden"}`.trim()}
      aria-label={deteccao ? "Editor visual da área de detecção" : "Editor visual de área de risco"}
      data-testid="editor-de-area"
      data-tipo={tipo}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onPointerCancel={handlePointerUp}
    />
  );
}

// O antigo <VideoCard/> (câmera padrão legada) saiu como código morto no rebrand.

const TIPOS: { valor: TipoDeArea; rotulo: string }[] = [
  { valor: "deteccao", rotulo: "Área de detecção" },
  { valor: "risco", rotulo: "Área de risco" },
];
const MODOS: { valor: ModoDeDesenho; rotulo: string }[] = [
  { valor: "retangulo", rotulo: "Retângulo" },
  { valor: "poligono", rotulo: "Polígono" },
];

/**
 * Aba "Áreas" da tela de foco: um seletor entre a área de detecção (onde a
 * câmera procura pessoas) e a área de risco (onde a presença vira alerta).
 */
export function RiskAreaEditorPanel() {
  const camId = useDashboardStore((s) => s.camId);
  const riskArea = useDashboardStore((s) => s.riskArea);
  const riskEditorActive = useDashboardStore((s) => s.riskEditorActive);
  const riskEditorPoints = useDashboardStore((s) => s.riskEditorPoints);
  const toggleRiskEditor = useDashboardStore((s) => s.toggleRiskEditor);
  const tipo = useAreaDeteccao((s) => s.tipo);
  const setTipo = useAreaDeteccao((s) => s.setTipo);
  const carregar = useAreaDeteccao((s) => s.carregar);
  const salva = useAreaDeteccao((s) => s.salva);
  const pontosDeteccao = useAreaDeteccao((s) => s.pontos);
  const editandoDeteccao = useAreaDeteccao((s) => s.editando);

  useEffect(() => {
    if (camId != null) carregar(camId).catch(console.error);
  }, [camId, carregar]);

  // Sair da aba encerra o desenho: o canvas não pode ficar capturando cliques no vídeo.
  useEffect(() => () => useAreaDeteccao.setState({ editando: false }), []);

  const trocarTipo = (novo: TipoDeArea) => {
    if (novo === tipo) return;
    if (novo === "deteccao" && riskEditorActive) toggleRiskEditor();
    setTipo(novo);
  };

  // Aviso: com o desenho em curso vale o rascunho; fora dele, o que está salvo.
  const areaVigente = editandoDeteccao && pontosDeteccao.length >= 3 ? pontosDeteccao : salva?.polygon || [];
  const riscoVigente = riskEditorActive && riskEditorPoints.length >= 3 ? riskEditorPoints : riskArea?.polygon || [];
  const riscoFora = riskArea?.enabled !== false && riscoForaDaArea(riscoVigente, areaVigente);

  return (
    <Panel
      id="panel-risk-area"
      title="Editor de áreas"
      description={
        tipo === "deteccao"
          ? "Onde a câmera procura pessoas. Fora da área de detecção nada é detectado, rastreado ou alertado; sem área, vale o quadro inteiro."
          : "Onde a presença de pessoas gera alerta. Clique no vídeo para criar um ponto; arraste um ponto existente para movê-lo."
      }
    >
      <div className="segmented areas-tipo" role="radiogroup" aria-label="Tipo de área">
        {TIPOS.map((t) => (
          <button
            key={t.valor}
            type="button"
            role="radio"
            aria-checked={tipo === t.valor}
            className={tipo === t.valor ? "active" : ""}
            onClick={() => trocarTipo(t.valor)}
            data-testid={`areas-tipo-${t.valor}`}
          >
            {t.rotulo}
          </button>
        ))}
      </div>
      {tipo === "deteccao" ? <EditorDaAreaDeDeteccao /> : <EditorDaAreaDeRisco />}
      {riscoFora && (
        <p className="aviso-area" role="status" data-testid="aviso-risco-fora">
          Parte desta área de risco está fora da área de detecção e não será vigiada.
        </p>
      )}
    </Panel>
  );
}

function EditorDaAreaDeRisco() {
  const riskArea = useDashboardStore((s) => s.riskArea);
  const riskEditorActive = useDashboardStore((s) => s.riskEditorActive);
  const riskEditorPoints = useDashboardStore((s) => s.riskEditorPoints);
  const toggleRiskEditor = useDashboardStore((s) => s.toggleRiskEditor);
  const clearRiskEditorPoints = useDashboardStore((s) => s.clearRiskEditorPoints);
  const resetRiskEditorFromServer = useDashboardStore((s) => s.resetRiskEditorFromServer);
  const updateRiskArea = useDashboardStore((s) => s.updateRiskArea);
  const showMessage = useDashboardStore((s) => s.showMessage);
  const [saving, setSaving] = useState(false);

  const save = async () => {
    if (riskEditorPoints.length < 3) {
      showMessage("Área de risco precisa de pelo menos 3 pontos.", "warning");
      return;
    }
    setSaving(true);
    try {
      await updateRiskArea({ name: riskArea?.name || "Área de risco", polygon: riskEditorPoints });
    } catch {
      // mensagem já emitida pela ação do store
    } finally {
      setSaving(false);
    }
  };

  const statusText = riskArea
    ? `${riskArea.name}, ${pluralizar(riskEditorPoints.length, "ponto")}, modo ${riskEditorActive ? "edição" : "visualização"}`
    : "Área atual não carregada.";

  return (
    <>
      <div className="actions">
        <button className="small" type="button" onClick={toggleRiskEditor}>
          {riskEditorActive ? "Encerrar edição" : "Editar no vídeo"}
        </button>
        <button className="ghost small" type="button" onClick={clearRiskEditorPoints}>
          Limpar pontos
        </button>
        <button className="ghost small" type="button" onClick={resetRiskEditorFromServer}>
          Recarregar
        </button>
        <button className={`primary small ${saving ? "is-pending" : ""}`.trim()} type="button" disabled={saving} onClick={() => save().catch(console.error)}>
          {saving ? "Salvando…" : "Salvar zona"}
        </button>
      </div>
      <p className="status-text t-data">{statusText}</p>
    </>
  );
}

function EditorDaAreaDeDeteccao() {
  const salva = useAreaDeteccao((s) => s.salva);
  const pontos = useAreaDeteccao((s) => s.pontos);
  const modo = useAreaDeteccao((s) => s.modo);
  const editando = useAreaDeteccao((s) => s.editando);
  const pendente = useAreaDeteccao((s) => s.pendente);
  const erro = useAreaDeteccao((s) => s.erro);
  const aviso = useAreaDeteccao((s) => s.aviso);
  const setModo = useAreaDeteccao((s) => s.setModo);
  const alternarEdicao = useAreaDeteccao((s) => s.alternarEdicao);
  const refazer = useAreaDeteccao((s) => s.refazer);
  const salvar = useAreaDeteccao((s) => s.salvar);
  const remover = useAreaDeteccao((s) => s.remover);

  const status = salva?.ativa
    ? `Área de detecção salva, ${pluralizar(salva.polygon.length, "ponto")}.`
    : "Sem área de detecção: a câmera analisa o quadro inteiro.";
  const instrucao =
    modo === "retangulo"
      ? "Aperte e arraste no vídeo, de um canto ao outro."
      : "Clique no vídeo para criar cada ponto; arraste um ponto para movê-lo.";

  return (
    <>
      <div className="segmented areas-modo" role="radiogroup" aria-label="Forma de desenhar">
        {MODOS.map((m) => (
          <button
            key={m.valor}
            type="button"
            role="radio"
            aria-checked={modo === m.valor}
            className={modo === m.valor ? "active" : ""}
            onClick={() => setModo(m.valor)}
            data-testid={`areas-modo-${m.valor}`}
          >
            {m.rotulo}
          </button>
        ))}
      </div>
      <div className="actions">
        <button className="small" type="button" onClick={alternarEdicao} data-testid="deteccao-desenhar">
          {editando ? "Encerrar desenho" : "Desenhar no vídeo"}
        </button>
        <button className="ghost small" type="button" onClick={refazer} data-testid="deteccao-refazer">
          Refazer
        </button>
        <button
          className="ghost small"
          type="button"
          onClick={() => remover().catch(console.error)}
          disabled={pendente || !salva?.ativa}
          title={salva?.ativa ? "Volta a analisar o quadro inteiro" : "Não há área salva: a câmera já analisa o quadro inteiro"}
          data-testid="deteccao-remover"
        >
          Remover área
        </button>
        <button
          className={`primary small ${pendente ? "is-pending" : ""}`.trim()}
          type="button"
          disabled={pendente}
          onClick={() => salvar().catch(console.error)}
          data-testid="deteccao-salvar"
        >
          {pendente ? "Salvando…" : "Salvar área"}
        </button>
      </div>
      <p className="status-text t-data" data-testid="deteccao-status">
        {editando ? `${instrucao} ${pluralizar(pontos.length, "ponto")} no desenho.` : status}
      </p>
      {aviso && (
        <p className="aviso-area" role="status">
          {aviso}
        </p>
      )}
      {erro && (
        <p className="erro-area" role="alert">
          {erro}
        </p>
      )}
    </>
  );
}
