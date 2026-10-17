/** Marca. Símbolo "Cúpula": capacete de segurança e câmera dome no mesmo
 * desenho (cúpula, aba solta, lente vazada). Uma cor só, `currentColor`, então
 * acompanha o tema pelo texto em volta. Fontes e regras em public/marca/ e
 * docs/NEXT2026/MARCA.md; o favicon.svg repete o símbolo com cor fixa porque
 * favicon não herda variável CSS. */

/** Geometria em grade de 32; mesma de public/marca/simbolo.svg. */
const SIMBOLO =
  "M5 19.5a11 11 0 0 1 22 0ZM3.5 21h25a1.5 1.5 0 0 1 0 3h-25a1.5 1.5 0 0 1 0-3ZM16 10.5a3.5 3.5 0 1 0 0 7a3.5 3.5 0 1 0 0-7Z";

/** Logotipo: "Vision" em Geist 640 e "EPI" em Geist 440, contornados
 * (public/marca/wordmark.svg). */
const LOGOTIPO =
  "M25.65 72.01L0 1.01L14.49 1.01L33.99 56.47L53.44 1.01L67.93 1.01L42.18 72.01ZM72.6 72.01L72.6 18.53L86.28 18.53L86.28 72.01ZM72.35 11.62L72.35 0L86.53 0L86.53 11.62ZM119.66 73.21Q111.3 73.21 105.87 70.89Q100.44 68.56 97.65 64.49Q94.85 60.42 94.45 55.17L108.39 54.62Q109.09 58.65 111.67 60.87Q114.24 63.1 119.7 63.1Q124 63.1 126.28 61.69Q128.56 60.27 128.56 57.33Q128.56 55.57 127.73 54.41Q126.9 53.25 124.5 52.37Q122.11 51.48 117.48 50.68Q109.26 49.23 104.61 47.18Q99.95 45.12 98.06 42Q96.17 38.88 96.17 34.3Q96.17 26.72 102.02 22.03Q107.87 17.33 119.29 17.33Q127.16 17.33 132.18 19.76Q137.21 22.18 139.8 26.3Q142.38 30.42 142.79 35.48L129 36.08Q128.89 33.58 127.81 31.62Q126.72 29.66 124.6 28.55Q122.48 27.44 119.09 27.44Q114.78 27.44 112.54 29.19Q110.3 30.93 110.3 33.8Q110.3 35.88 111.2 37.21Q112.11 38.55 114.35 39.39Q116.59 40.22 120.42 40.83Q128.75 42.03 133.63 44.13Q138.51 46.22 140.6 49.41Q142.68 52.6 142.68 57.14Q142.68 64.87 136.46 69.04Q130.23 73.21 119.66 73.21ZM150.96 72.01L150.96 18.53L164.64 18.53L164.64 72.01ZM150.71 11.62L150.71 0L164.89 0L164.89 11.62ZM199.46 73.21Q191.44 73.21 185.44 69.76Q179.44 66.32 176.12 60.02Q172.81 53.72 172.81 45.27Q172.81 36.77 176.12 30.52Q179.44 24.28 185.44 20.8Q191.44 17.33 199.46 17.33Q207.48 17.33 213.46 20.8Q219.44 24.28 222.75 30.52Q226.06 36.77 226.06 45.27Q226.06 53.72 222.75 60.02Q219.44 66.32 213.46 69.76Q207.48 73.21 199.46 73.21ZM199.46 62.38Q205.42 62.38 208.68 57.87Q211.94 53.37 211.94 45.27Q211.94 37.22 208.68 32.69Q205.42 28.16 199.46 28.16Q193.51 28.16 190.22 32.69Q186.94 37.22 186.94 45.27Q186.94 53.37 190.22 57.87Q193.51 62.38 199.46 62.38ZM234.24 72.01L234.24 18.53L246.59 18.53L247.13 33.81L245.46 33.24Q246.27 27.49 248.74 24.01Q251.22 20.52 254.87 18.93Q258.51 17.33 262.85 17.33Q268.71 17.33 272.76 19.89Q276.8 22.44 278.92 26.99Q281.04 31.54 281.04 37.62L281.04 72.01L267.36 72.01L267.36 42.09Q267.36 37.67 266.55 34.61Q265.73 31.54 263.78 29.94Q261.84 28.33 258.51 28.33Q253.56 28.33 250.74 31.87Q247.92 35.41 247.92 42.09L247.92 72.01ZM294.75 72.01L294.75 1.01L339.99 1.01L339.99 10L304.23 10L304.23 32.02L338.79 32.02L338.79 40.81L304.23 40.81L304.23 63.03L340.79 63.03L340.79 72.01ZM352.89 72.01L352.89 1.01L378.78 1.01Q390.8 1.01 397.49 6.78Q404.17 12.54 404.17 22.74Q404.17 29.58 401.14 34.57Q398.1 39.56 392.43 42.19Q386.76 44.82 378.78 44.82L362.37 44.82L362.37 72.01ZM362.37 35.84L378.66 35.84Q386.39 35.84 390.34 32.54Q394.29 29.24 394.29 22.74Q394.29 16.42 390.35 13.21Q386.4 10 378.66 10L362.37 10ZM414.68 72.01L414.68 1.01L424.16 1.01L424.16 72.01Z";
const LOGOTIPO_W = 424.16;
const LOGOTIPO_H = 73.21;

/** Símbolo decorativo: o nome sempre aparece escrito ao lado ou perto. */
export function Mark({ size = 28 }: { size?: number }) {
  return (
    <svg
      className="brand-mark"
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="currentColor"
      aria-hidden="true"
      focusable="false"
    >
      <path fillRule="evenodd" d={SIMBOLO} />
    </svg>
  );
}

/** Nome desenhado. Quando é o único nome visível (barra superior), vale como
 * imagem com rótulo; use `decorativo` se o nome já estiver escrito ao lado. */
export function Wordmark({ height = 14, decorativo = false }: { height?: number; decorativo?: boolean }) {
  const rotulo = decorativo ? { "aria-hidden": true } : { role: "img", "aria-label": "VisionEPI" };
  return (
    <svg
      className="brand-wordmark"
      width={Math.round((height * LOGOTIPO_W) / LOGOTIPO_H)}
      height={height}
      viewBox={`0 0 ${LOGOTIPO_W} ${LOGOTIPO_H}`}
      fill="currentColor"
      focusable="false"
      {...rotulo}
    >
      <path d={LOGOTIPO} />
    </svg>
  );
}
