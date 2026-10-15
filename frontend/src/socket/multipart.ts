/**
 * Leitor de `multipart/x-mixed-replace` (o MJPEG do servidor) sem cópia
 * quadrática.
 *
 * A primeira versão do player concatenava o buffer inteiro a cada pedaço que
 * chegava (`new Uint8Array(buf.length + chunk.length)`). Bastava o leitor ficar
 * um pouco para trás para o buffer crescer, cada cópia ficar mais cara e ele
 * ficar AINDA mais para trás — atraso que se realimenta: medido no bench, idade
 * do quadro p95 de 2 a 7 s com o servidor publicando em ~3 ms.
 *
 * Aqui o buffer cresce por dobra e o que já foi lido é só um deslocamento
 * (`ini`); a compactação copia apenas o que falta ler. Cada parte sai com o
 * corpo copiado (o buffer é reaproveitado), e o chamador decide o que fazer
 * com ela — o player fica só com a mais nova.
 */
export type Parte = { cabecalho: string; corpo: Uint8Array };

const decodificador = new TextDecoder();

export class LeitorMultipart {
  private buf = new Uint8Array(1 << 20);
  private ini = 0;
  private fim = 0;

  empurrar(pedaco: Uint8Array): void {
    if (pedaco.length > this.buf.length - this.fim) {
      const usado = this.fim - this.ini;
      if (usado + pedaco.length <= this.buf.length) {
        this.buf.copyWithin(0, this.ini, this.fim);
      } else {
        const novo = new Uint8Array(Math.max(this.buf.length * 2, (usado + pedaco.length) * 2));
        novo.set(this.buf.subarray(this.ini, this.fim));
        this.buf = novo;
      }
      this.ini = 0;
      this.fim = usado;
    }
    this.buf.set(pedaco, this.fim);
    this.fim += pedaco.length;
  }

  /** Todas as partes COMPLETAS disponíveis agora, em ordem. */
  partes(): Parte[] {
    const saida: Parte[] = [];
    for (;;) {
      const fimCab = this.acharSeparador();
      if (fimCab < 0) return saida;
      const cabecalho = decodificador.decode(this.buf.subarray(this.ini, fimCab));
      const m = /Content-Length:\s*(\d+)/i.exec(cabecalho);
      if (!m) {
        this.ini = fimCab + 4;
        continue;
      }
      const inicioCorpo = fimCab + 4;
      const fimCorpo = inicioCorpo + parseInt(m[1], 10);
      if (this.fim < fimCorpo) return saida;
      saida.push({ cabecalho, corpo: this.buf.slice(inicioCorpo, fimCorpo) });
      this.ini = fimCorpo;
    }
  }

  private acharSeparador(): number {
    const b = this.buf;
    for (let i = this.ini; i + 3 < this.fim; i++) {
      if (b[i] === 13 && b[i + 1] === 10 && b[i + 2] === 13 && b[i + 3] === 10) return i;
    }
    return -1;
  }
}
