import { useId, useRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { ApiError } from "../api/client";
import { campoDoErro, enviarContato, LIMITE_DE_TEXTO } from "../api/feedback";
import { mensagemDeErro } from "../utils/erros";
import { inteiro } from "../utils/formato";
import { Mark, Wordmark } from "./brand";
import { ThemeToggle } from "./layout";
import "../styles/produto.css";

/**
 * Página pública /produto (MISSÃO 4, Fase 3 item 10). Sem login, sem dado da planta.
 *
 * Regra de conteúdo: só o que o sistema faz e que foi testado. Nada de cliente,
 * depoimento, métrica de mercado, preço ou número que o sistema não produziu. Os
 * números citados (8 s de replay, 5 s antes e 3 s depois, 7 EPIs) vêm de app/config.py
 * e de app/vision/person_compliance_matcher.py.
 *
 * O formulário grava LOCALMENTE (POST /api/contatos, app/api/feedback.py); o Supervisor
 * lê em /caixa-de-entrada.
 */

// Arquivos de public/ saem do build em /static/dist/ (vite `base`).
const GIF_DO_PALCO = `${import.meta.env.BASE_URL}produto/palco.gif`;
const QUADRO_DO_PALCO = `${import.meta.env.BASE_URL}produto/palco-quadro.webp`;
const EMAIL_VALIDO = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

function Secao({ id, titulo, introducao, children }: { id: string; titulo: string; introducao?: string; children: ReactNode }) {
  return (
    <section id={id} className="produto-secao" aria-labelledby={`${id}-titulo`}>
      <div className="produto-miolo">
        <h2 id={`${id}-titulo`}>{titulo}</h2>
        {introducao && <p className="produto-intro">{introducao}</p>}
        {children}
      </div>
    </section>
  );
}

function Cartao({ titulo, children }: { titulo: string; children: ReactNode }) {
  return (
    <li className="card produto-cartao">
      <h3>{titulo}</h3>
      <p>{children}</p>
    </li>
  );
}

/** O GIF anima sem parar: quem pede movimento reduzido já começa no quadro estático, e há botão para pausar. */
function MidiaDoPalco() {
  const [pausado, setPausado] = useState(() => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false);
  return (
    <figure className="produto-midia">
      <img
        src={pausado ? QUADRO_DO_PALCO : GIF_DO_PALCO}
        alt="Modo Apresentação percorrendo as cenas da demonstração: abertura com os números da planta e o Portal de Entrada."
        width={800}
        height={450}
        decoding="async"
      />
      <figcaption>
        <span>Modo Apresentação do VisionEPI, com dados de demonstração.</span>
        <button type="button" className="ghost small" aria-pressed={pausado} onClick={() => setPausado((p) => !p)}>
          {pausado ? "Reproduzir animação" : "Pausar animação"}
        </button>
      </figcaption>
    </figure>
  );
}

type Campo = "nome" | "email" | "mensagem" | "consentimento";
type Erros = Partial<Record<Campo, string>>;
const ORDEM_DOS_CAMPOS: Campo[] = ["nome", "email", "mensagem", "consentimento"];

function validar(v: { nome: string; email: string; mensagem: string; consentimento: boolean }): Erros {
  const erros: Erros = {};
  if (!v.nome.trim()) erros.nome = "Informe o seu nome.";
  if (!EMAIL_VALIDO.test(v.email.trim())) erros.email = "Informe um e-mail válido, como nome@empresa.com.br.";
  if (!v.mensagem.trim()) erros.mensagem = "Escreva a sua mensagem.";
  if (!v.consentimento) erros.consentimento = "Marque o consentimento para guardarmos seus dados.";
  return erros;
}

function FormularioDeContato() {
  const [nome, setNome] = useState("");
  const [empresa, setEmpresa] = useState("");
  const [email, setEmail] = useState("");
  const [mensagem, setMensagem] = useState("");
  const [consentimento, setConsentimento] = useState(false);
  const [erros, setErros] = useState<Erros>({});
  const [falha, setFalha] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [enviado, setEnviado] = useState(false);
  const id = useId();
  const refs = {
    nome: useRef<HTMLInputElement>(null),
    email: useRef<HTMLInputElement>(null),
    mensagem: useRef<HTMLTextAreaElement>(null),
    consentimento: useRef<HTMLInputElement>(null),
  };

  const focarNoPrimeiro = (e: Erros) => {
    const primeiro = ORDEM_DOS_CAMPOS.find((c) => e[c]);
    if (primeiro) refs[primeiro].current?.focus();
  };

  const enviar = (evento: FormEvent) => {
    evento.preventDefault();
    if (enviando) return;
    const encontrados = validar({ nome, email, mensagem, consentimento });
    setErros(encontrados);
    setFalha(null);
    if (Object.keys(encontrados).length) {
      focarNoPrimeiro(encontrados);
      return;
    }
    setEnviando(true);
    enviarContato({ nome: nome.trim(), empresa: empresa.trim(), email: email.trim(), mensagem: mensagem.trim(), consentimento })
      .then(() => {
        setEnviado(true);
        setNome("");
        setEmpresa("");
        setEmail("");
        setMensagem("");
        setConsentimento(false);
      })
      .catch((e: unknown) => {
        const campo = campoDoErro(e);
        if (campo && (ORDEM_DOS_CAMPOS as string[]).includes(campo) && e instanceof ApiError) {
          const apontado: Erros = { [campo as Campo]: e.message };
          setErros(apontado);
          focarNoPrimeiro(apontado);
        } else {
          setFalha(mensagemDeErro(e, "Falha ao enviar a mensagem."));
        }
      })
      .finally(() => setEnviando(false));
  };

  const campoErro = (c: Campo) => (erros[c] ? `${id}-${c}-erro` : undefined);
  const quantosErros = Object.keys(erros).length;

  return (
    <div className="produto-contato">
      {/* Região sempre presente: o leitor de tela só anuncia mudança numa região que já existia. */}
      <div role="status" aria-live="polite" className="produto-status" data-testid="contato-status">
        {enviado && <p className="produto-sucesso">Mensagem enviada. Obrigado pelo contato; vamos responder pelo e-mail informado.</p>}
      </div>

      <form onSubmit={enviar} noValidate aria-label="Fale com a equipe do VisionEPI">
        <div className="produto-linha">
          <div className="produto-campo">
            <label htmlFor={`${id}-nome`}>Nome</label>
            <input
              id={`${id}-nome`}
              ref={refs.nome}
              type="text"
              value={nome}
              onChange={(e) => setNome(e.target.value)}
              maxLength={120}
              autoComplete="name"
              required
              aria-required="true"
              aria-invalid={erros.nome ? true : undefined}
              aria-describedby={campoErro("nome")}
            />
            {erros.nome && (
              <span id={campoErro("nome")} className="produto-erro">
                {erros.nome}
              </span>
            )}
          </div>
          <div className="produto-campo">
            <label htmlFor={`${id}-empresa`}>
              Empresa <span className="produto-opcional">(opcional)</span>
            </label>
            <input
              id={`${id}-empresa`}
              type="text"
              value={empresa}
              onChange={(e) => setEmpresa(e.target.value)}
              maxLength={160}
              autoComplete="organization"
            />
          </div>
        </div>

        <div className="produto-campo">
          <label htmlFor={`${id}-email`}>E-mail</label>
          <input
            id={`${id}-email`}
            ref={refs.email}
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            maxLength={254}
            autoComplete="email"
            required
            aria-required="true"
            aria-invalid={erros.email ? true : undefined}
            aria-describedby={campoErro("email")}
          />
          {erros.email && (
            <span id={campoErro("email")} className="produto-erro">
              {erros.email}
            </span>
          )}
        </div>

        <div className="produto-campo">
          <label htmlFor={`${id}-mensagem`}>Mensagem</label>
          <textarea
            id={`${id}-mensagem`}
            ref={refs.mensagem}
            className="produto-texto"
            value={mensagem}
            onChange={(e) => setMensagem(e.target.value)}
            maxLength={LIMITE_DE_TEXTO}
            rows={5}
            required
            aria-required="true"
            aria-invalid={erros.mensagem ? true : undefined}
            aria-describedby={campoErro("mensagem")}
          />
          <span className="produto-contador">
            {inteiro(mensagem.length)} de {inteiro(LIMITE_DE_TEXTO)} caracteres
          </span>
          {erros.mensagem && (
            <span id={campoErro("mensagem")} className="produto-erro">
              {erros.mensagem}
            </span>
          )}
        </div>

        <div className="produto-campo">
          <label className="produto-consentimento" htmlFor={`${id}-consentimento`}>
            <input
              id={`${id}-consentimento`}
              ref={refs.consentimento}
              type="checkbox"
              checked={consentimento}
              onChange={(e) => setConsentimento(e.target.checked)}
              required
              aria-required="true"
              aria-invalid={erros.consentimento ? true : undefined}
              aria-describedby={`${id}-privacidade ${campoErro("consentimento") ?? ""}`.trim()}
            />
            <span>Aceito que o VisionEPI guarde meu nome, empresa, e-mail e mensagem para responder o meu contato.</span>
          </label>
          {erros.consentimento && (
            <span id={campoErro("consentimento")} className="produto-erro">
              {erros.consentimento}
            </span>
          )}
          <p id={`${id}-privacidade`} className="produto-privacidade">
            Os dados ficam só no servidor desta instalação do VisionEPI e não são enviados a terceiros. Você escolhe o que escrever: não
            peça nem informe dados de pessoas da sua planta.
          </p>
        </div>

        {quantosErros > 0 && (
          <p className="produto-resumo-erros" role="alert">
            {quantosErros === 1 ? "Corrija o campo indicado." : `Corrija os ${quantosErros} campos indicados.`}
          </p>
        )}
        {falha && (
          <p className="produto-resumo-erros" role="alert">
            {falha}
          </p>
        )}

        <button type="submit" className="primary grande" disabled={enviando}>
          {enviando ? "Enviando…" : "Enviar mensagem"}
        </button>
      </form>
    </div>
  );
}

export function ProdutoScreen() {
  return (
    <div className="produto" data-testid="produto">
      <header className="produto-topo">
        <div className="produto-miolo produto-topo-linha">
          <a className="produto-marca" href="/produto" aria-label="VisionEPI, início desta página">
            <Mark size={24} />
            <Wordmark decorativo />
          </a>
          <nav className="produto-nav" aria-label="Seções da página">
            <a href="#como-funciona">Como funciona</a>
            <a href="#diferenciais">Diferenciais</a>
            <a href="#privacidade">Privacidade</a>
            <a href="#integracoes">Integrações</a>
          </nav>
          <div className="produto-topo-acoes">
            <ThemeToggle />
            <a className="button ghost" href="/">
              Entrar
            </a>
            <a className="button primary produto-cta-topo" href="#contato">
              Falar com a equipe
            </a>
          </div>
        </div>
      </header>

      <section className="produto-hero" aria-labelledby="produto-titulo">
        <div className="produto-miolo produto-hero-grade">
          <div className="produto-hero-texto">
            <p className="produto-sobretitulo">VisionEPI</p>
            <h1 id="produto-titulo">Segurança do trabalho que enxerga a planta inteira.</h1>
            <p className="produto-lide">
              Câmeras comuns viram um sistema que vê EPI, queda e área de risco ao vivo, agrupa o que vê em incidentes e guarda cada
              evidência com prova de integridade. Por setor, nunca por pessoa. Roda inteiro num notebook, sem internet.
            </p>
            <div className="produto-hero-acoes">
              <a className="button primary grande" href="#contato">
                Falar com a equipe
              </a>
              <a className="button ghost grande" href="#como-funciona">
                Ver como funciona
              </a>
            </div>
          </div>
          <MidiaDoPalco />
        </div>
      </section>

      <Secao
        id="problema"
        titulo="O problema"
        introducao="As câmeras já estão na planta. O que falta é alguém olhando todas ao mesmo tempo, e um registro que sirva depois."
      >
        <ul className="produto-grade tres">
          <Cartao titulo="Ninguém olha tudo">
            Um colete esquecido, uma pessoa dentro da área de risco ou uma queda passam despercebidos até alguém rever a gravação.
          </Cartao>
          <Cartao titulo="Alerta demais vira ruído">
            Um alerta por pessoa e por EPI enche a tela. O que importa é o incidente: o que está errado, onde e desde quando.
          </Cartao>
          <Cartao titulo="Evidência sem prova">
            Depois do fato, é difícil mostrar o que a câmera viu e que a imagem não foi alterada no caminho.
          </Cartao>
        </ul>
      </Secao>

      <Secao
        id="como-funciona"
        titulo="Como funciona"
        introducao="Cinco passos, da imagem da câmera até a evidência guardada."
      >
        <ol className="produto-passos">
          <li>
            <span className="produto-passo-numero" aria-hidden="true">1</span>
            <div>
              <h3>Câmera</h3>
              <p>Câmera USB, RTSP ou vídeo gravado. O celular também serve como câmera, lendo um QR code.</p>
            </div>
          </li>
          <li>
            <span className="produto-passo-numero" aria-hidden="true">2</span>
            <div>
              <h3>Detecção</h3>
              <p>
                Um modelo de visão reconhece sete EPIs (capacete, colete, luvas, óculos, máscara, calçado e protetor auricular), pessoas e
                postura. Quando a parte do corpo não aparece no quadro, “não detectado” não vira “ausente”.
              </p>
            </div>
          </li>
          <li>
            <span className="produto-passo-numero" aria-hidden="true">3</span>
            <div>
              <h3>Regra</h3>
              <p>
                Regras prontas e regras que o próprio time monta no editor, sem código. A condição só vira alerta depois de confirmada por
                análises seguidas, para um quadro ruim não disparar nada.
              </p>
            </div>
          </li>
          <li>
            <span className="produto-passo-numero" aria-hidden="true">4</span>
            <div>
              <h3>Alerta</h3>
              <p>
                O alerta é por pessoa rastreada; o painel mostra incidentes, que agrupam por câmera, regra e zona. Quem supervisiona
                reconhece o incidente, e a torre de luz, a TV e o celular do supervisor acompanham.
              </p>
            </div>
          </li>
          <li>
            <span className="produto-passo-numero" aria-hidden="true">5</span>
            <div>
              <h3>Evidência na custódia</h3>
              <p>
                A imagem de evidência e o replay entram numa cadeia com SHA-256 encadeado. Mudar um byte depois faz a verificação apontar
                exatamente o elo que não fecha.
              </p>
            </div>
          </li>
        </ol>
      </Secao>

      <Secao
        id="diferenciais"
        titulo="Diferenciais"
        introducao="Só o que existe no sistema hoje e passou nos testes do projeto."
      >
        <ul className="produto-grade">
          <Cartao titulo="Replay com rosto desfocado">
            Os 8 segundos do incidente, 5 antes e 3 depois, gravados já com o rosto desfocado.
          </Cartao>
          <Cartao titulo="Cadeia de custódia SHA-256">
            Cada evidência é encadeada à anterior. Prova que nada mudou depois de entrar na cadeia; não é carimbo de tempo de autoridade
            certificadora.
          </Cartao>
          <Cartao titulo="Editor de regras sem código">
            Condições com E e OU sobre zona, EPI, duração, postura, aproximação e horário, testadas no histórico antes de ligar.
          </Cartao>
          <Cartao titulo="Permissão de trabalho com vigia">
            Zona confinada com janela de horário e responsável. Sem ninguém na área do vigia, o alerta é crítico. A câmera ajuda o vigia, não o
            substitui.
          </Cartao>
          <Cartao titulo="Integração OPC UA e MQTT">
            SCADA ou CLP lê o estado da planta por OPC UA (somente leitura) e os eventos saem por MQTT.
          </Cartao>
          <Cartao titulo="Torre de luz">
            Vermelho, amarelo e verde virtuais, iguais ao que o CLP lê. A sirene fica ligada até alguém reconhecer o incidente.
          </Cartao>
          <Cartao titulo="Modo Evacuação">
            Contagem de pessoas por câmera em tempo real e relatório que entra na custódia. Pode haver dupla contagem quando as câmeras se
            sobrepõem, e a tela avisa.
          </Cartao>
          <Cartao titulo="Saúde da câmera">
            Avisa quando a imagem é tapada, a câmera é movida, ou a imagem fica escura, ofuscada ou desfocada.
          </Cartao>
          <Cartao titulo="Roda offline">
            Modelo, banco de dados e interface rodam na própria máquina, sem internet. O que sai dela é só o que você ligar.
          </Cartao>
        </ul>
      </Secao>

      <Secao
        id="privacidade"
        titulo="Privacidade e LGPD"
        introducao="O sistema foi desenhado para medir a planta, não para vigiar pessoas."
      >
        <ul className="produto-grade">
          <Cartao titulo="Por setor, nunca por pessoa">
            Pontuação e metas são de setores e equipes. Não existe ranking de pessoas.
          </Cartao>
          <Cartao titulo="Sem reconhecimento facial">
            “Pessoa 7” é um número de rastreio por posição e muda quando a pessoa sai do quadro. Nenhum nome é ligado a ele.
          </Cartao>
          <Cartao titulo="Rosto desfocado">
            Vídeo, replay, imagem de evidência e recortes do aprendizado ativo saem do servidor com o rosto desfocado. Só o Supervisor desliga,
            e a troca fica registrada.
          </Cartao>
        </ul>
        <div className="card produto-guarda">
          <h3>O que é guardado e por quanto tempo</h3>
          <ul>
            <li>O vídeo ao vivo não é gravado: passa por uma memória temporária. Nada é gravado no Portal de Entrada.</li>
            <li>
              Quando um alerta nasce, ficam guardados a imagem de evidência, o replay de 8 segundos e o registro do alerta, com rótulo de
              rastreio e sem nome.
            </li>
            <li>
              O aprendizado ativo guarda recortes com o rosto desfocado numa fila de até 300. Só os que uma pessoa confirma são exportados.
            </li>
            <li>
              Não existe expiração automática. O prazo é definido por quem implanta: o Supervisor apaga os alertas já resolvidos por
              antiguidade, e as imagens de evidência deles saem junto. Os replays ficam na pasta de replays da instalação, que o responsável
              gerencia.
            </li>
            <li>
              A pasta de arquivos temporários é limpa a cada início do monitoramento, e a evidência ainda ligada a um alerta é preservada.
            </li>
          </ul>
          <p>
            A base legal e a transparência com os trabalhadores são de quem implanta, e fogem do escopo do software. Isto não é parecer
            jurídico.
          </p>
        </div>
      </Secao>

      <Secao
        id="integracoes"
        titulo="Integrações"
        introducao="Todas opcionais e desligadas por padrão. Nada publicado identifica uma pessoa."
      >
        <ul className="produto-grade">
          <Cartao titulo="OPC UA">
            Servidor somente leitura, com o estado da planta, a torre e o estado de cada câmera. Sobe sem criptografia por padrão: use em rede
            de chão de fábrica isolada.
          </Cartao>
          <Cartao titulo="MQTT">
            Publica o estado da planta (retido) e cada alerta novo, por câmera. Funciona com o broker da sua planta.
          </Cartao>
          <Cartao titulo="Webhook HTTP">
            Um POST em JSON a cada alerta novo. Destinos da rede interna ficam bloqueados, a menos que você os libere.
          </Cartao>
          <Cartao titulo="Celular do supervisor">
            Aplicativo instalável no celular, com notificação de alerta crítico no navegador.
          </Cartao>
        </ul>
      </Secao>

      <Secao
        id="contato"
        titulo="Fale com a equipe"
        introducao="Conte o que você quer ver rodando. A mensagem chega ao supervisor desta instalação."
      >
        <FormularioDeContato />
      </Secao>

      <footer className="produto-rodape">
        <div className="produto-miolo produto-rodape-linha">
          <span className="produto-marca">
            <Mark size={20} />
            <Wordmark decorativo height={12} />
          </span>
          <p>Feito para o FIAP NEXT 2026, Challenge Metaindústria, SPI Integração.</p>
          <a href="/">Entrar no sistema</a>
        </div>
      </footer>
    </div>
  );
}

export default ProdutoScreen;
