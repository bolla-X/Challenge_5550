import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { CSS2DObject, CSS2DRenderer } from "three/examples/jsm/renderers/CSS2DRenderer.js";
import type { CameraDoGemeo, PeNaPlanta } from "./tipos";

/**
 * Cena do gêmeo digital (X1). Imperativa e isolada do React: o componente só
 * cria, passa os dados novos (`atualizar`) e destrói.
 *
 * Coordenadas: a planta é normalizada 0–1 (a mesma do G5) e vira um galpão de
 * LARGURA × PROFUNDIDADE metros. y é a altura.
 *
 * Custo: sem sombras dinâmicas, materiais sem luz física (Lambert/Basic),
 * geometrias compartilhadas por todos os avatares, e o laço de desenho para
 * quando a aba fica oculta (`document.hidden`).
 */

export const LARGURA = 40;
export const PROFUNDIDADE = 25;
const ALTURA_CAMERA = 4.2;
const ALTURA_ZONA = 2.4;

export type Cores = {
  canvas: string;
  surface: string;
  sunken: string;
  hairline: string;
  text: string;
  text2: string;
  text3: string;
  accent: string;
  ok: string;
  danger: string;
  stop: string;
};

export function lerCores(el: HTMLElement = document.documentElement): Cores {
  const css = getComputedStyle(el);
  const v = (nome: string, padrao: string) => css.getPropertyValue(nome).trim() || padrao;
  return {
    canvas: v("--canvas", "#F5F5F7"),
    surface: v("--surface", "#FFFFFF"),
    sunken: v("--sunken", "#EBEBEF"),
    hairline: v("--hairline", "#E5E5EA"),
    text: v("--text", "#1A1A1C"),
    text2: v("--text-2", "#5E5E64"),
    text3: v("--text-3", "#68686F"),
    accent: v("--accent", "#0A66C2"),
    ok: v("--ok", "#16794A"),
    danger: v("--danger", "#AF4606"),
    stop: v("--stop", "#C9241B"),
  };
}

export function paraMundo(x: number, y: number): THREE.Vector3 {
  return new THREE.Vector3((x - 0.5) * LARGURA, 0, (y - 0.5) * PROFUNDIDADE);
}

export function corDoEstado(estado: PeNaPlanta["estado"], cores: Cores): string {
  if (estado === "emergencia") return cores.stop;
  if (estado === "sem_epi" || estado === "zona") return cores.danger;
  return cores.ok;
}

type Avatar = {
  chave: string;
  grupo: THREE.Group;
  corpo: THREE.Mesh;
  anel: THREE.Mesh;
  alvo: THREE.Vector3;
  rotulo: CSS2DObject;
  visto: number;
  dados: PeNaPlanta & { camera_id: number; camera_nome: string };
};

export type Selecao =
  | { tipo: "pessoa"; camera_id: number; camera_nome: string; pe: PeNaPlanta }
  | { tipo: "zona"; camera_id: number; camera_nome: string; zona_nome: string | null }
  | null;

export type Metricas = { quadros: number; intervaloP95: number; desenhoP95: number; pausado: boolean; escala: number };

function p95(valores: number[]): number {
  if (!valores.length) return 0;
  const ordenados = [...valores].sort((a, b) => a - b);
  return ordenados[Math.min(ordenados.length - 1, Math.floor(ordenados.length * 0.95))];
}

function rotuloHtml(texto: string, classe: string): CSS2DObject {
  const div = document.createElement("div");
  div.className = classe;
  div.textContent = texto;
  return new CSS2DObject(div);
}

export class CenaGemeo {
  private renderer: THREE.WebGLRenderer;
  private rotulos: CSS2DRenderer;
  private cena = new THREE.Scene();
  private camera: THREE.PerspectiveCamera;
  private controles: OrbitControls;
  private relogio = new THREE.Clock();
  private raf = 0;
  private avatares = new Map<string, Avatar>();
  private camadaCameras = new THREE.Group();
  private camadaZonas = new THREE.Group();
  private zonasClicaveis: THREE.Mesh[] = [];
  private geoCorpo = new THREE.CapsuleGeometry(0.42, 1.1, 4, 12);
  private geoAnel = new THREE.RingGeometry(0.7, 0.86, 32);
  private assinaturaCameras = "";
  private intervalos: number[] = [];
  private custos: number[] = [];
  private ultimoQuadro = 0;
  private quadros = 0;
  // Regulador: sem GPU de verdade (SwiftShader, máquina fraca) o quadro passa
  // de 40 ms; a resolução interna cai em degraus até caber em 30 fps.
  private escala = Math.min(window.devicePixelRatio || 1, 1.75);
  private ultimaRegulagem = 0;
  private voo: { de: THREE.Vector3; para: THREE.Vector3; alvoDe: THREE.Vector3; alvoPara: THREE.Vector3; t: number } | null = null;
  private reduzirMovimento: boolean;
  private aoSelecionar: (s: Selecao) => void;
  private cores: Cores;
  private observador: ResizeObserver;
  private aoMudarVisibilidade = () => (document.hidden ? this.pausar() : this.retomar());

  constructor(private host: HTMLElement, opcoes: { aoSelecionar: (s: Selecao) => void; reduzirMovimento: boolean }) {
    this.aoSelecionar = opcoes.aoSelecionar;
    this.reduzirMovimento = opcoes.reduzirMovimento;
    this.cores = lerCores();
    // Lança se o WebGL não existir: quem chama cai para o 2D.
    this.renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
    this.renderer.setPixelRatio(this.escala);
    this.renderer.domElement.className = "gemeo-canvas";
    this.renderer.domElement.setAttribute("aria-label", "Gêmeo digital da planta em 3D");
    this.renderer.domElement.setAttribute("role", "img");
    host.appendChild(this.renderer.domElement);

    this.rotulos = new CSS2DRenderer();
    this.rotulos.domElement.className = "gemeo-rotulos";
    host.appendChild(this.rotulos.domElement);

    this.camera = new THREE.PerspectiveCamera(42, 1, 0.5, 400);
    this.camera.position.set(26, 30, 34);
    this.controles = new OrbitControls(this.camera, this.renderer.domElement);
    this.controles.target.set(0, 0, 0);
    this.controles.enableDamping = !this.reduzirMovimento;
    this.controles.dampingFactor = 0.08;
    this.controles.minDistance = 14;
    this.controles.maxDistance = 85;
    this.controles.minPolarAngle = 0.05;
    this.controles.maxPolarAngle = Math.PI / 2 - 0.12; // nunca por baixo do piso
    this.controles.screenSpacePanning = false;
    this.controles.addEventListener("change", () => this.limitarPan());

    this.montarGalpao();
    this.cena.add(this.camadaZonas, this.camadaCameras);

    this.renderer.domElement.addEventListener("pointerup", this.aoClicar);
    this.observador = new ResizeObserver(() => this.redimensionar());
    this.observador.observe(host);
    document.addEventListener("visibilitychange", this.aoMudarVisibilidade);
    this.redimensionar();
    this.retomar();
  }

  // ------------------------------------------------------------ galpão
  private montarGalpao(): void {
    const c = this.cores;
    this.cena.background = new THREE.Color(c.canvas);
    this.cena.add(new THREE.HemisphereLight(0xffffff, new THREE.Color(c.sunken), 1.15));
    const sol = new THREE.DirectionalLight(0xffffff, 0.9);
    sol.position.set(-20, 40, 18);
    this.cena.add(sol);

    const piso = new THREE.Mesh(
      new THREE.PlaneGeometry(LARGURA, PROFUNDIDADE),
      new THREE.MeshLambertMaterial({ color: new THREE.Color(c.surface) }),
    );
    piso.rotation.x = -Math.PI / 2;
    this.cena.add(piso);

    const grade = new THREE.GridHelper(LARGURA, 20, new THREE.Color(c.hairline), new THREE.Color(c.hairline));
    grade.scale.set(1, 1, PROFUNDIDADE / LARGURA);
    grade.position.y = 0.01;
    this.cena.add(grade);

    // Paredes baixas: dão volume sem esconder nada de nenhum ângulo.
    const parede = new THREE.MeshLambertMaterial({ color: new THREE.Color(c.sunken) });
    const altura = 1.2;
    const espessura = 0.25;
    const lados: [number, number, number, number][] = [
      [0, -PROFUNDIDADE / 2, LARGURA, espessura],
      [0, PROFUNDIDADE / 2, LARGURA, espessura],
      [-LARGURA / 2, 0, espessura, PROFUNDIDADE],
      [LARGURA / 2, 0, espessura, PROFUNDIDADE],
    ];
    for (const [x, z, w, d] of lados) {
      const m = new THREE.Mesh(new THREE.BoxGeometry(w, altura, d), parede);
      m.position.set(x, altura / 2, z);
      this.cena.add(m);
    }
  }

  // ------------------------------------------------------------ dados
  atualizar(cameras: CameraDoGemeo[]): void {
    const assinatura = JSON.stringify(cameras.map((cam) => [cam.id, cam.pontos_planta, cam.pontos_camera, cam.zona, cam.zona_nome, cam.setor]));
    if (assinatura !== this.assinaturaCameras) {
      this.assinaturaCameras = assinatura;
      this.montarCamerasEZonas(cameras);
    }
    const agora = performance.now();
    for (const cam of cameras) {
      if (!cam.calibrada) continue;
      for (const pe of cam.pes) {
        const chave = `${cam.id}:${pe.track_id}`;
        let avatar = this.avatares.get(chave);
        const alvo = paraMundo(pe.x, pe.y);
        if (!avatar) {
          avatar = this.criarAvatar(chave, alvo);
          this.avatares.set(chave, avatar);
        }
        avatar.alvo.copy(alvo);
        avatar.visto = agora;
        avatar.dados = { ...pe, camera_id: cam.id, camera_nome: cam.nome };
        const cor = new THREE.Color(corDoEstado(pe.estado, this.cores));
        (avatar.corpo.material as THREE.MeshLambertMaterial).color.copy(cor);
        (avatar.anel.material as THREE.MeshBasicMaterial).color.copy(cor);
        avatar.anel.visible = pe.estado !== "conforme";
        (avatar.corpo.material as THREE.MeshLambertMaterial).opacity = pe.dentro_da_calibracao ? 1 : 0.45;
        avatar.rotulo.element.textContent = String(pe.track_id);
      }
    }
    // Quem sumiu há mais de 1,5 s sai da cena.
    for (const [chave, avatar] of this.avatares) {
      if (agora - avatar.visto > 1500) {
        this.cena.remove(avatar.grupo);
        avatar.grupo.remove(avatar.rotulo);
        avatar.rotulo.element.remove();
        (avatar.corpo.material as THREE.Material).dispose();
        (avatar.anel.material as THREE.Material).dispose();
        this.avatares.delete(chave);
      }
    }
  }

  get pessoasEmCena(): number {
    return this.avatares.size;
  }

  private criarAvatar(chave: string, posicao: THREE.Vector3): Avatar {
    const grupo = new THREE.Group();
    const corpo = new THREE.Mesh(this.geoCorpo, new THREE.MeshLambertMaterial({ color: this.cores.ok, transparent: true }));
    corpo.position.y = 0.97;
    corpo.userData.chave = chave;
    const anel = new THREE.Mesh(this.geoAnel, new THREE.MeshBasicMaterial({ color: this.cores.danger, side: THREE.DoubleSide }));
    anel.rotation.x = -Math.PI / 2;
    anel.position.y = 0.03;
    const rotulo = rotuloHtml("", "gemeo-id");
    rotulo.position.set(0, 2.25, 0);
    grupo.add(corpo, anel, rotulo);
    grupo.position.copy(posicao);
    this.cena.add(grupo);
    return { chave, grupo, corpo, anel, alvo: posicao.clone(), rotulo, visto: performance.now(), dados: {} as Avatar["dados"] };
  }

  private montarCamerasEZonas(cameras: CameraDoGemeo[]): void {
    for (const camada of [this.camadaCameras, this.camadaZonas]) {
      for (const filho of [...camada.children]) {
        camada.remove(filho);
        filho.traverse((o) => {
          if (o instanceof CSS2DObject) o.element.remove();
          if (o instanceof THREE.Mesh || o instanceof THREE.LineSegments || o instanceof THREE.Line) {
            o.geometry.dispose();
            (o.material as THREE.Material).dispose();
          }
        });
      }
    }
    this.zonasClicaveis = [];
    const c = this.cores;
    for (const cam of cameras) {
      if (!cam.calibrada || !cam.pontos_planta || cam.pontos_planta.length !== 4) continue;
      const quad = cam.pontos_planta.map(([x, y]) => paraMundo(x, y));

      // Setor: o chão que a câmera enxerga, levemente afundado na cor do sistema.
      const forma = new THREE.Shape(quad.map((p) => new THREE.Vector2(p.x, -p.z)));
      const setor = new THREE.Mesh(
        new THREE.ShapeGeometry(forma),
        new THREE.MeshBasicMaterial({ color: new THREE.Color(c.sunken), transparent: true, opacity: 0.55, depthWrite: false }),
      );
      setor.rotation.x = -Math.PI / 2;
      setor.position.y = 0.02;
      this.camadaCameras.add(setor);
      const centro = quad.reduce((a, p) => a.add(p), new THREE.Vector3()).multiplyScalar(0.25);
      const nomeSetor = rotuloHtml(`${cam.setor} · ${cam.nome}`, "gemeo-setor");
      nomeSetor.position.set(centro.x, 0.1, centro.z);
      this.camadaCameras.add(nomeSetor);

      // Cone de visão: a câmera fica atrás da borda "de perto" (a que na
      // imagem tem o maior y), no alto, olhando para o chão que ela vê.
      const pc = cam.pontos_camera ?? cam.pontos_planta;
      const indices = [0, 1, 2, 3].sort((a, b) => pc[b][1] - pc[a][1]);
      const perto = quad[indices[0]].clone().add(quad[indices[1]]).multiplyScalar(0.5);
      const longe = quad[indices[2]].clone().add(quad[indices[3]]).multiplyScalar(0.5);
      const recuo = perto.clone().sub(longe).normalize().multiplyScalar(3.5);
      const apice = perto.clone().add(recuo).setY(ALTURA_CAMERA);
      const linhas: number[] = [];
      for (const p of quad) linhas.push(apice.x, apice.y, apice.z, p.x, 0.04, p.z);
      for (let i = 0; i < 4; i += 1) {
        const a = quad[i];
        const b = quad[(i + 1) % 4];
        linhas.push(a.x, 0.04, a.z, b.x, 0.04, b.z);
      }
      const geo = new THREE.BufferGeometry();
      geo.setAttribute("position", new THREE.Float32BufferAttribute(linhas, 3));
      this.camadaCameras.add(
        new THREE.LineSegments(geo, new THREE.LineBasicMaterial({ color: new THREE.Color(c.text3), transparent: true, opacity: 0.5 })),
      );
      const corpoCam = new THREE.Mesh(
        new THREE.BoxGeometry(0.9, 0.55, 0.55),
        new THREE.MeshLambertMaterial({ color: new THREE.Color(c.text2) }),
      );
      corpoCam.position.copy(apice);
      corpoCam.lookAt(centro);
      this.camadaCameras.add(corpoCam);

      // Zona de risco: volume translúcido na cor de perigo.
      if (cam.zona.length >= 3) {
        const formaZona = new THREE.Shape(cam.zona.map(([x, y]) => {
          const p = paraMundo(x, y);
          return new THREE.Vector2(p.x, -p.z);
        }));
        const volume = new THREE.Mesh(
          new THREE.ExtrudeGeometry(formaZona, { depth: ALTURA_ZONA, bevelEnabled: false }),
          new THREE.MeshBasicMaterial({ color: new THREE.Color(c.danger), transparent: true, opacity: 0.14, depthWrite: false }),
        );
        volume.rotation.x = -Math.PI / 2;
        volume.userData = { tipo: "zona", camera_id: cam.id, camera_nome: cam.nome, zona_nome: cam.zona_nome };
        this.camadaZonas.add(volume);
        this.zonasClicaveis.push(volume);
        const bordas = new THREE.LineSegments(
          new THREE.EdgesGeometry(volume.geometry),
          new THREE.LineBasicMaterial({ color: new THREE.Color(c.danger), transparent: true, opacity: 0.7 }),
        );
        bordas.rotation.x = -Math.PI / 2;
        this.camadaZonas.add(bordas);
        const zc = cam.zona.reduce((a, [x, y]) => a.add(paraMundo(x, y)), new THREE.Vector3()).multiplyScalar(1 / cam.zona.length);
        const nome = rotuloHtml(cam.zona_nome ?? "Zona de risco", "gemeo-zona");
        nome.position.set(zc.x, ALTURA_ZONA + 0.4, zc.z);
        this.camadaZonas.add(nome);
      }
    }
  }

  // ------------------------------------------------------------ interação
  private aoClicar = (ev: PointerEvent) => {
    const r = this.renderer.domElement.getBoundingClientRect();
    const ponteiro = new THREE.Vector2(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1);
    const raio = new THREE.Raycaster();
    raio.setFromCamera(ponteiro, this.camera);
    const corpos = [...this.avatares.values()].map((a) => a.corpo);
    const acertoPessoa = raio.intersectObjects(corpos, false)[0];
    if (acertoPessoa) {
      const avatar = this.avatares.get(acertoPessoa.object.userData.chave as string);
      if (avatar) {
        const { camera_id, camera_nome, ...pe } = avatar.dados;
        this.aoSelecionar({ tipo: "pessoa", camera_id, camera_nome, pe });
        return;
      }
    }
    const acertoZona = raio.intersectObjects(this.zonasClicaveis, false)[0];
    if (acertoZona) {
      const u = acertoZona.object.userData;
      this.aoSelecionar({ tipo: "zona", camera_id: u.camera_id, camera_nome: u.camera_nome, zona_nome: u.zona_nome });
    }
  };

  /** Seleção pelo teclado/lista (acessibilidade): devolve a pessoa pela chave "câmera:id". */
  selecionarPessoa(chave: string): void {
    const avatar = this.avatares.get(chave);
    if (!avatar) return;
    const { camera_id, camera_nome, ...pe } = avatar.dados;
    this.aoSelecionar({ tipo: "pessoa", camera_id, camera_nome, pe });
  }

  /** Alterna entre a vista isométrica e a "visão de drone" (de cima). */
  visaoDeDrone(ligar: boolean): void {
    const para = ligar ? new THREE.Vector3(0, 52, 0.01) : new THREE.Vector3(26, 30, 34);
    const alvoPara = new THREE.Vector3(0, 0, 0);
    if (this.reduzirMovimento) {
      this.camera.position.copy(para);
      this.controles.target.copy(alvoPara);
      this.controles.update();
      return;
    }
    this.voo = { de: this.camera.position.clone(), para, alvoDe: this.controles.target.clone(), alvoPara, t: 0 };
  }

  private limitarPan(): void {
    const t = this.controles.target;
    const x = THREE.MathUtils.clamp(t.x, -LARGURA / 2, LARGURA / 2);
    const z = THREE.MathUtils.clamp(t.z, -PROFUNDIDADE / 2, PROFUNDIDADE / 2);
    if (x !== t.x || z !== t.z || t.y !== 0) {
      const delta = new THREE.Vector3(x - t.x, -t.y, z - t.z);
      t.add(delta);
      this.camera.position.add(delta);
    }
  }

  // ------------------------------------------------------------ laço
  private redimensionar(): void {
    const largura = Math.max(1, this.host.clientWidth);
    const altura = Math.max(1, this.host.clientHeight);
    this.renderer.setSize(largura, altura, false);
    this.rotulos.setSize(largura, altura);
    this.camera.aspect = largura / altura;
    this.camera.updateProjectionMatrix();
  }

  private quadro = (t: number) => {
    this.raf = requestAnimationFrame(this.quadro);
    if (this.ultimoQuadro) {
      this.intervalos.push(t - this.ultimoQuadro);
      if (this.intervalos.length > 240) this.intervalos.shift();
    }
    this.ultimoQuadro = t;
    const inicio = performance.now();
    const dt = Math.min(0.1, this.relogio.getDelta());
    // Interpolação suave entre análises (a posição chega ~2–4 vezes por segundo).
    const fator = this.reduzirMovimento ? 1 : 1 - Math.exp(-dt * 7);
    for (const avatar of this.avatares.values()) avatar.grupo.position.lerp(avatar.alvo, fator);
    if (this.voo) {
      this.voo.t = Math.min(1, this.voo.t + dt / 0.9);
      const k = 1 - Math.pow(1 - this.voo.t, 3);
      this.camera.position.lerpVectors(this.voo.de, this.voo.para, k);
      this.controles.target.lerpVectors(this.voo.alvoDe, this.voo.alvoPara, k);
      if (this.voo.t >= 1) this.voo = null;
    }
    this.controles.update();
    this.renderer.render(this.cena, this.camera);
    this.rotulos.render(this.cena, this.camera);
    this.custos.push(performance.now() - inicio);
    if (this.custos.length > 240) this.custos.shift();
    this.quadros += 1;
    this.regular(t);
  };

  private regular(t: number): void {
    if (t - this.ultimaRegulagem < 2000 || this.intervalos.length < 60) return;
    this.ultimaRegulagem = t;
    const recente = p95(this.intervalos.slice(-60));
    if (recente > 40 && this.escala > 0.5) {
      this.escala = Math.max(0.5, this.escala * 0.75);
      this.renderer.setPixelRatio(this.escala);
      this.redimensionar();
      this.intervalos = [];
    }
  }

  pausar(): void {
    if (this.raf) cancelAnimationFrame(this.raf);
    this.raf = 0;
    this.ultimoQuadro = 0;
  }

  retomar(): void {
    if (this.raf || document.hidden) return;
    this.relogio.getDelta();
    this.raf = requestAnimationFrame(this.quadro);
  }

  metricas(): Metricas {
    return {
      quadros: this.quadros,
      intervaloP95: p95(this.intervalos),
      desenhoP95: p95(this.custos),
      pausado: this.raf === 0,
      escala: this.escala,
    };
  }

  destruir(): void {
    this.pausar();
    document.removeEventListener("visibilitychange", this.aoMudarVisibilidade);
    this.observador.disconnect();
    this.renderer.domElement.removeEventListener("pointerup", this.aoClicar);
    this.controles.dispose();
    this.cena.traverse((o) => {
      if (o instanceof THREE.Mesh || o instanceof THREE.LineSegments) {
        o.geometry.dispose();
        const m = o.material as THREE.Material | THREE.Material[];
        (Array.isArray(m) ? m : [m]).forEach((x) => x.dispose());
      }
    });
    this.renderer.dispose();
    this.renderer.domElement.remove();
    this.rotulos.domElement.remove();
  }
}
