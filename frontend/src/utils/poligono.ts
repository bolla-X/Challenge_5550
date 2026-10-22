/**
 * Geometria de polígono normalizado (0–1), espelho de app/vision/area_de_deteccao.py.
 * O servidor é quem decide (valida e filtra); aqui é só o que o editor precisa para
 * avisar antes de salvar.
 */
export type Ponto = { x: number; y: number };

/** Raio horizontal (paridade de cruzamentos): vale para polígono côncavo. */
export function pontoNoPoligono(x: number, y: number, poligono: Ponto[]): boolean {
  let dentro = false;
  for (let i = 0, j = poligono.length - 1; i < poligono.length; j = i++) {
    const a = poligono[i];
    const b = poligono[j];
    if (a.y > y !== b.y > y && x < ((b.x - a.x) * (y - a.y)) / (b.y - a.y) + a.x) dentro = !dentro;
  }
  return dentro;
}

/** Área pela fórmula do laço, em fração do quadro. */
export function areaDoPoligono(poligono: Ponto[]): number {
  let soma = 0;
  poligono.forEach((p, i) => {
    const q = poligono[(i + 1) % poligono.length];
    soma += p.x * q.y - q.x * p.y;
  });
  return Math.abs(soma) / 2;
}

/** A área de risco tem parte fora da área de detecção? (vértices e pontos ao longo das arestas) */
export function riscoForaDaArea(risco: Ponto[], area: Ponto[], passos = 8): boolean {
  if (area.length < 3 || risco.length < 3) return false;
  for (let i = 0; i < risco.length; i++) {
    const a = risco[i];
    const b = risco[(i + 1) % risco.length];
    for (let k = 0; k < passos; k++) {
      const t = k / passos;
      if (!pontoNoPoligono(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t, area)) return true;
    }
  }
  return false;
}

/** Os 4 cantos do retângulo entre dois pontos, no sentido horário a partir do canto de cima à esquerda. */
export function retanguloEntre(a: Ponto, b: Ponto): Ponto[] {
  const x1 = Math.min(a.x, b.x);
  const x2 = Math.max(a.x, b.x);
  const y1 = Math.min(a.y, b.y);
  const y2 = Math.max(a.y, b.y);
  return [
    { x: x1, y: y1 },
    { x: x2, y: y1 },
    { x: x2, y: y2 },
    { x: x1, y: y2 },
  ];
}
