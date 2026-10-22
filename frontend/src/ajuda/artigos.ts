import { normalizar, termosDa } from "../utils/busca";

/**
 * Artigos da central de ajuda (`/ajuda`). Um artigo por TAREFA, escrito a partir
 * do que cada tela faz de fato: nomes de botão, abas e mensagens são os que
 * aparecem na interface. Tom e termos do docs/NEXT2026/GLOSSARIO.md.
 *
 * Regras para editar:
 * - passo curto, no imperativo, um verbo por passo;
 * - só afirme o que o código faz (e, para norma, o que o gov.br diz);
 * - "não detectado" nunca vira "ausente", e ID de rastreio nunca vira identidade.
 */

export type TipoDeConta = "operator" | "technical" | "supervisor";

export const TIPOS_DE_CONTA: TipoDeConta[] = ["operator", "technical", "supervisor"];
/** Mesmos rótulos de `ROTULO_DO_PAPEL` (layout.tsx), repetidos aqui para este módulo não depender de tela. */
export const ROTULO_DO_TIPO: Record<TipoDeConta, string> = {
  operator: "Operador",
  technical: "Técnico",
  supervisor: "Supervisor",
};

export interface LinkDeTela {
  href: string;
  rotulo: string;
}

export interface Artigo {
  id: string;
  titulo: string;
  /** Uma frase: para que serve e o que muda quando se faz. */
  resumo: string;
  /** Tipos de conta que fazem a tarefa (o Supervisor faz tudo o que o Técnico faz). */
  paraQuem: TipoDeConta[];
  /** Título da lista numerada. Padrão: "Passo a passo". */
  tituloDosPassos?: string;
  passos: string[];
  /** Caminho até a tela, em palavras. */
  ondeFica: string;
  /** Alerta, limite ou exceção que a pessoa precisa saber antes de confiar na tela. */
  notas?: string[];
  tela?: LinkDeTela;
  /** Outras palavras que a pessoa usaria para procurar o artigo. */
  termos?: string[];
}

const TODOS: TipoDeConta[] = ["operator", "technical", "supervisor"];
const TECNICO_E_SUPERVISOR: TipoDeConta[] = ["technical", "supervisor"];

export const ARTIGOS: Artigo[] = [
  {
    id: "reconhecer-alerta",
    titulo: "Reconhecer um alerta e avisar o colaborador",
    resumo: "Registre que o alerta foi visto e que a pessoa foi avisada. Isso não resolve nem apaga nada.",
    paraQuem: TODOS,
    passos: [
      "Operador: o aviso no topo da sua tela diz o que o sistema viu. Avise a pessoa no local.",
      "Operador: toque em \"Avisei o colaborador\". O botão vale para o alerta mais grave mostrado no aviso e confirma com \"Registrado: colaborador avisado.\"",
      "Técnico e Supervisor: abra a câmera e vá à aba Alertas. Em \"Incidentes ativos\", clique em \"Reconhecer\" no incidente. O tempo até a sua resposta fica registrado.",
      "Para registrar o aviso de todos os alertas ativos da câmera de uma vez, clique em \"Avisei todos\".",
      "O alerta sai da lista sozinho quando o sistema confirma que a condição voltou ao normal.",
    ],
    ondeFica:
      "Operador: tela inicial da sua câmera, botões embaixo do vídeo. Técnico e Supervisor: Câmeras, abrir a câmera, aba Alertas.",
    notas: [
      "Reconhecer não resolve o incidente. \"Resolver todos\" (Técnico e Supervisor) é outra ação: manda os alertas ativos para o histórico, sem apagar nada. Se a violação continuar, o mesmo alerta volta depois de 1 minuto.",
    ],
    tela: { href: "/", rotulo: "Abrir as câmeras" },
    termos: ["avisei", "incidente", "ciência", "responder", "alerta ativo"],
  },
  {
    id: "falso-positivo",
    titulo: "Marcar falso positivo",
    resumo: "Use quando o sistema alertou por engano. O alerta sai da lista e fica no histórico, com a marca.",
    paraQuem: TODOS,
    passos: [
      "Antes de marcar, confirme que foi engano. Técnico e Supervisor podem clicar em \"Ver replay\" para rever os quadros de antes e de depois do alerta.",
      "Operador: toque em \"Marcar falso positivo\" embaixo do vídeo.",
      "Técnico e Supervisor: abra a câmera, vá à aba Alertas e clique em \"Falso positivo\" na linha do alerta ativo.",
      "O sistema confirma com \"Alerta marcado como falso positivo.\" O alerta vai para o histórico com a marca \"Falso positivo\".",
    ],
    ondeFica:
      "Operador: tela inicial da sua câmera, botões embaixo do vídeo. Técnico e Supervisor: Câmeras, abrir a câmera, aba Alertas.",
    notas: [
      "No Relatório do turno, falso positivo não entra em \"Infrações × NR-6\" e aparece na contagem própria de falsos positivos.",
      "Na tela não há como desfazer a marca. Na dúvida, veja o replay antes.",
    ],
    tela: { href: "/", rotulo: "Abrir as câmeras" },
    termos: ["engano", "erro", "alarme falso", "descartar"],
  },
  {
    id: "ver-replay",
    titulo: "Ver o replay de um incidente",
    resumo: "Reveja os quadros reais de 5 s antes a 3 s depois do alerta, com as evidências que sustentaram a decisão.",
    paraQuem: TECNICO_E_SUPERVISOR,
    passos: [
      "Abra a câmera e vá à aba Alertas.",
      "Na linha do alerta, clique em \"Ver replay\". Pela \"Linha causal\" do incidente, use \"ver quadro\" em cada passo ou \"Ver replay\" em \"Evidências\".",
      "O replay toca no ritmo real da gravação. Use \"Pausar\" e a barra \"Posição no replay\" para parar num quadro. A marca \"momento do alerta\" mostra o instante exato.",
      "Leia \"Evidências que sustentaram o alerta\": quantas confirmações seguidas houve, o que o modelo viu na pessoa e quais EPIs ele sabe detectar.",
      "Feche com Esc ou com \"Fechar\".",
    ],
    ondeFica:
      "Câmeras, abrir a câmera, aba Alertas. No Gêmeo digital, selecione uma pessoa com alerta e use \"Ver replay do alerta\".",
    notas: [
      "O replay só fica pronto 3 s depois do alerta. Se aparecer \"Tente de novo em instantes\", espere um pouco.",
      "Com o modo privacidade ligado, os rostos aparecem desfocados. O número da pessoa é rastreio, não identidade.",
    ],
    tela: { href: "/", rotulo: "Abrir as câmeras" },
    termos: ["clipe", "vídeo do alerta", "quadros", "evidência", "linha causal"],
  },
  {
    id: "verificar-integridade",
    titulo: "Verificar a integridade de uma evidência",
    resumo: "Confira se alguma evidência foi alterada ou apagada depois de gravada.",
    paraQuem: TECNICO_E_SUPERVISOR,
    passos: [
      "Para um incidente: na aba Alertas da câmera, clique em \"Linha causal\" no incidente e role até \"Cadeia de custódia\".",
      "Clique em \"Verificar integridade\". Para a cadeia inteira, abra a Auditoria e use o mesmo botão.",
      "O resultado é \"Evidências íntegras\", \"Íntegras, com evidência ausente\" ou \"Adulteração detectada\". Quando há problema, a tela diz em qual elo e o que houve: conteúdo alterado, registro alterado, cadeia quebrada ou evidência ausente do disco.",
      "Anote o último elo mostrado no relatório do turno. Isso ancora a cadeia fora do sistema.",
    ],
    ondeFica:
      "Linha causal de um incidente, ou a tela Auditoria (Supervisor: Início, Cadeia de custódia; Técnico: Ctrl K e \"auditoria\").",
    notas: [
      "Cada evidência tem um SHA-256 encadeado ao anterior: mudar um byte quebra a cadeia daí em diante.",
      "A verificação mostra até 12 elos na tela. A tabela da Auditoria lista os 100 mais recentes.",
    ],
    tela: { href: "/auditoria", rotulo: "Abrir a Auditoria" },
    termos: ["custódia", "sha-256", "hash", "auditoria", "adulteração", "prova", "lgpd"],
  },
  {
    id: "criar-regra",
    titulo: "Criar uma regra e testar no histórico",
    resumo: "Monte uma regra com blocos, veja o que ela teria disparado nas últimas horas e só depois ative.",
    paraQuem: TECNICO_E_SUPERVISOR,
    passos: [
      "Abra Regras de alerta e clique em \"Criar regra\". Dê um nome à regra.",
      "Em \"Quando\", clique em \"Condição\" e escolha o tipo: Zona, EPI, Duração, Postura, Aproximação, Horário ou Permissão ativa. Combine com \"Todas as condições (E)\" ou \"Qualquer condição (OU)\". Confira a frase em \"Como a regra se lê\".",
      "Em \"Então\", escolha a severidade (Crítica, Alta, Média ou Baixa) e escreva a mensagem do alerta. Se quiser, marque \"Falar o alerta\", \"Enviar para a integração (OPC UA/MQTT)\" ou defina em quantos segundos escalar ao supervisor e à TV.",
      "Em \"Onde vale\", escolha todas as câmeras ou só algumas.",
      "Em \"Testar no histórico\", escolha a câmera e a janela (de 1 a 24 horas) e clique em \"Testar no histórico\". O resultado mostra disparos, pessoas vistas e incidentes numa linha do tempo.",
      "Clique em \"Criar regra\". A regra nasce desativada: abra-a e ligue \"Regra ativa\" quando estiver satisfeito.",
    ],
    ondeFica:
      "Tela Regras de alerta. Supervisor: Início, Visão geral, Editor de regras. Técnico: Ctrl K e \"regras\".",
    notas: [
      "O teste só lê a trilha gravada. Nunca cria nem muda um alerta real.",
      "As regras nativas já estão em execução e não se editam nem se excluem. Use \"Duplicar para editar\" e mude a cópia.",
      "Algumas regras não podem ser testadas no histórico. A tela avisa e você ainda pode salvar, mas só a verá em ação ao vivo.",
    ],
    tela: { href: "/regras", rotulo: "Abrir o editor de regras" },
    termos: ["editor", "condição", "histórico", "severidade", "simular", "blocos", "ativar"],
  },
  {
    id: "simulador-e-se",
    titulo: "Testar uma mudança no simulador \"E se?\"",
    resumo: "Veja quantos alertas teriam disparado com outra configuração, sem mexer em nenhum alerta real.",
    paraQuem: TECNICO_E_SUPERVISOR,
    passos: [
      "Abra o Simulador e escolha a câmera e a janela de tempo.",
      "Ajuste o que quer testar: os EPIs exigidos, a histerese para criar o alerta e a zona de risco (arraste os vértices).",
      "Clique em \"Reprocessar\".",
      "Compare \"Teriam disparado\" com \"Dispararam de fato\" e com \"Regra de hoje, simulada\". A última mostra o quanto o simulador reproduz o real.",
      "A tabela \"Por regra\" mostra a diferença regra a regra.",
    ],
    ondeFica: "Tela Simulador. Supervisor: Início, Simulador. Técnico: Ctrl K e \"simulador\".",
    notas: [
      "O simulador reprocessa o que o modelo viu na época: não roda o modelo de novo, e ignora a soneca do \"Resolver todos\" e as regras de emergência.",
      "Sem trilha gravada da câmera, \"Reprocessar\" fica desabilitado. Ligue a câmera e espere algumas análises.",
    ],
    tela: { href: "/simulador", rotulo: "Abrir o Simulador" },
    termos: ["e se", "histerese", "reprocessar", "zona", "comparar"],
  },
  {
    id: "emitir-permissao",
    titulo: "Emitir uma permissão de trabalho com vigia",
    resumo: "Registre quem trabalha na área de risco, por quanto tempo e com quais EPIs. A câmera confere; não emite nem substitui o vigia.",
    paraQuem: TECNICO_E_SUPERVISOR,
    passos: [
      "Abra Permissão de trabalho e clique em \"Emitir permissão\".",
      "Escolha a câmera e o tipo: Espaço confinado, Trabalho em altura ou Geral. Descreva o trabalho e informe o responsável. O responsável é texto livre e não é ligado às pessoas que a câmera detecta.",
      "Defina Início e Fim, em horário local. O limite do sistema é de 24 h. Acima de 8 h, o sistema emite e avisa que a norma limita a validade a uma jornada.",
      "Marque os EPIs exigidos. \"Fiscalizado pela câmera\" quer dizer que o modelo detecta aquele EPI. \"Verificação manual\" quer dizer que uma pessoa precisa conferir: a câmera não finge checar.",
      "Marque \"Exige vigia\" e clique no quadro da câmera para desenhar a área do vigia, com 3 pontos ou mais. Arraste um ponto para ajustar. Com o ponto em foco, Delete o remove.",
      "Clique em \"Emitir permissão\" e leia os \"Avisos da emissão\" antes de dispensar.",
      "Para a câmera cobrar permissão de quem entra na área de risco, ligue \"Zona exige permissão\" na câmera, em \"Zonas controladas\".",
      "Ao fim do trabalho, abra a permissão e clique em \"Encerrar permissão\". Para anular, use \"Cancelar permissão\".",
    ],
    ondeFica:
      "Tela Permissão de trabalho. Supervisor: Início, Visão geral, Permissões de trabalho. Técnico: Ctrl K e \"permissões\".",
    notas: [
      "A câmera confere só quem está dentro da área de risco desenhada. Sem permissão vigente numa zona que exige, entrar gera alerta. Com vigia exigido, pessoa na zona e ninguém na área do vigia gera alerta crítico. EPI exigido que o modelo detecta e falta gera alerta.",
      "Quem está com os pés na área do vigia conta como vigia, mesmo que as áreas se sobreponham.",
      "A câmera auxilia o vigia; não o substitui (NR-33, 33.3.4.1). O texto oficial da norma abre por link no detalhe da permissão.",
      "O Operador só lê as permissões da própria câmera.",
    ],
    tela: { href: "/permissoes", rotulo: "Abrir as permissões de trabalho" },
    termos: ["pt", "pet", "nr-33", "nr-35", "espaço confinado", "altura", "vigia", "zona controlada"],
  },
  {
    id: "acionar-evacuacao",
    titulo: "Acionar e encerrar uma evacuação",
    resumo: "Conte as pessoas detectadas por câmera durante a emergência e guarde o relatório na cadeia de custódia.",
    paraQuem: TECNICO_E_SUPERVISOR,
    passos: [
      "Abra Evacuação. Só o Supervisor aciona e encerra; o Técnico acompanha.",
      "Se quiser, em \"Ponto de encontro\", escolha a câmera que cobre esse ponto.",
      "Clique em \"Acionar evacuação\" e confirme em \"Acionar agora\". O cronômetro começa.",
      "Acompanhe a soma de pessoas detectadas agora, a contagem por câmera e por zona, os selos \"Sem sinal\" e \"Análise atrasada\" e, no ponto de encontro, o pico simultâneo desde o início.",
      "A planta mostra a última posição vista de cada ID de rastreio. Ponto cheio: visto agora. Ponto vazado: última posição antes de sumir.",
      "Ao terminar, clique em \"Encerrar evacuação\" e confirme em \"Encerrar e salvar relatório\".",
      "O relatório (número, duração e pico somado) entra na cadeia de custódia. Use \"Verificar integridade na auditoria\" para conferir.",
    ],
    ondeFica:
      "Tela Evacuação. Supervisor: Início, Visão geral, Evacuação. Técnico: Ctrl K e \"evacuação\".",
    notas: [
      "A contagem é por câmera e pode ter dupla contagem se as câmeras se sobrepõem. O aviso fica sempre visível na tela.",
      "O sistema conta pessoas detectadas. Quem a câmera não viu não entra na conta, e a contagem não confirma quem saiu.",
      "A posição na planta só aparece para câmeras com a planta calibrada.",
      "Uma evacuação encerrada não pode ser reaberta.",
    ],
    tela: { href: "/evacuacao", rotulo: "Abrir o Modo Evacuação" },
    termos: ["emergência", "ponto de encontro", "cronômetro", "contagem", "simulacro"],
  },
  {
    id: "redefinir-referencia",
    titulo: "Redefinir a referência de uma câmera tampada ou movida",
    resumo: "O sistema compara a imagem com uma referência para perceber câmera tampada, movida, escura, ofuscada ou sem foco. Redefina quando a mudança foi de propósito.",
    paraQuem: TECNICO_E_SUPERVISOR,
    passos: [
      "Com a câmera ligada, veja o selo de estado sobre o vídeo, na segunda linha à direita. Ele explica o problema, por exemplo \"A imagem ficou sem detalhe: algo pode estar tampando a lente.\"",
      "Se a lente está tampada, suja ou fora de foco, resolva o problema físico. O selo some sozinho quando a imagem volta ao normal.",
      "Se a mudança foi de propósito (câmera reposicionada, iluminação nova), confirme que a cena está em ordem e clique em \"Redefinir referência\".",
      "A mensagem \"Referência redefinida com a imagem atual.\" confirma. A partir daí o sistema compara com essa imagem.",
    ],
    ondeFica: "Câmeras, abrir a câmera, selo sobre o vídeo (aparece só quando o sistema percebe problema na imagem).",
    notas: [
      "A nova referência é a imagem de agora. Se a lente ainda estiver tampada, a referência fica errada: destampe antes.",
      "Se a câmera mudou de lugar, a calibração da planta e a zona de risco, desenhadas na imagem antiga, deixam de valer. Refaça as duas.",
    ],
    tela: { href: "/", rotulo: "Abrir as câmeras" },
    termos: ["sabotagem", "tampada", "obstruída", "movida", "escura", "ofuscada", "desfocada", "lente", "calibração"],
  },
  {
    id: "camera-do-celular",
    titulo: "Ligar a câmera do celular",
    resumo: "O celular vira uma câmera do sistema: o QR code leva ao endereço desta máquina na rede local.",
    paraQuem: TECNICO_E_SUPERVISOR,
    passos: [
      "Inicie o servidor em HTTPS (python run.py --https). Em HTTP, o celular não libera a câmera.",
      "Em Câmeras, clique em \"Adicionar câmera\", escolha o tipo \"Celular (via QR code)\", dê um nome e clique em \"Cadastrar câmera\".",
      "Abra a câmera e vá à aba \"Config. câmera\". O painel \"Celular como câmera\" mostra o QR code e o endereço.",
      "No celular, leia o QR code e toque em \"Iniciar câmera\".",
      "No painel, clique em \"Iniciar\" para começar a analisar a imagem.",
    ],
    ondeFica: "Câmeras, abrir a câmera, aba \"Config. câmera\" (só aparece o QR em câmera do tipo Celular).",
    notas: [
      "O link vale só para esta câmera. Quem tiver o link pode enviar imagem para ela, mas não ganha acesso ao painel.",
      "O QR leva ao endereço da rede local: celular e computador precisam estar na mesma rede.",
    ],
    tela: { href: "/", rotulo: "Abrir as câmeras" },
    termos: ["qr", "qr code", "https", "webcam", "celular como câmera", "pareamento"],
  },
  {
    id: "calibrar-planta",
    titulo: "Calibrar a planta",
    resumo: "Ligue a imagem da câmera à planta para ver onde cada ID de rastreio está. Oito cliques, na mesma ordem.",
    paraQuem: TECNICO_E_SUPERVISOR,
    passos: [
      "Abra a câmera e a aba \"Planta\" (dentro de \"Mais\").",
      "No quadro do vídeo, clique 4 pontos no chão. Escolha cantos de piso que você também reconhece na planta.",
      "Na planta ao lado, clique os mesmos 4 pontos, na mesma ordem. Cada ponto tem cor e número, de 1 a 4.",
      "Quando os dois contadores marcarem 4/4, clique em \"Salvar calibração\". \"Recomeçar\" limpa os pontos.",
      "Depois de salvar, a planta mostra os pés de cada ID de rastreio, a zona de risco e o mapa de calor. Ponto vazado: fora da área calibrada.",
      "Para refazer, use \"Recalibrar\". \"Apagar calibração\" remove a atual.",
    ],
    ondeFica: "Câmeras, abrir a câmera, aba \"Planta\" (em Mais).",
    notas: [
      "A planta é um modelo padrão com grade de 5 m, não o desenho do seu galpão. Use para ver posição relativa.",
      "O Gêmeo digital e o Modo Evacuação usam esta calibração. Sem ela, não há posição na planta.",
    ],
    tela: { href: "/", rotulo: "Abrir as câmeras" },
    termos: ["homografia", "calibração", "gêmeo", "posição", "chão", "mapa de calor"],
  },
  {
    id: "zona-de-risco",
    titulo: "Desenhar a zona de risco",
    resumo: "Desenhe sobre o vídeo o polígono onde a presença de uma pessoa gera alerta.",
    paraQuem: TECNICO_E_SUPERVISOR,
    passos: [
      "Abra a câmera, ligue o monitoramento com \"Iniciar\", vá à aba \"Áreas\" (em \"Mais\") e escolha \"Área de risco\".",
      "Clique em \"Editar no vídeo\". Clique no vídeo para criar cada ponto do polígono e arraste um ponto para movê-lo.",
      "\"Limpar pontos\" recomeça. \"Recarregar\" volta ao que está salvo.",
      "Com 3 pontos ou mais, clique em \"Salvar zona\". Com menos, o sistema avisa que a área precisa de pelo menos 3 pontos.",
      "Clique em \"Encerrar edição\" para sair do modo de desenho.",
    ],
    ondeFica: "Câmeras, abrir a câmera, aba \"Áreas\" (em Mais), \"Área de risco\". O vídeo precisa estar no ar.",
    notas: [
      "Se a câmera tiver área de detecção, desenhe a área de risco dentro dela: a parte que ficar fora não é vigiada, e o editor avisa.",
      "A zona é de cada câmera. Sem uma zona própria, a câmera usa a área padrão do sistema, que raramente coincide com o seu chão de fábrica.",
      "Para exigir permissão de trabalho de quem entra na zona, veja \"Emitir uma permissão de trabalho com vigia\".",
    ],
    tela: { href: "/", rotulo: "Abrir as câmeras" },
    termos: ["área de risco", "polígono", "zona", "desenhar", "perímetro"],
  },
  {
    id: "area-de-deteccao",
    titulo: "Limitar a área de detecção",
    resumo: "Diga onde a câmera procura pessoas: fora da área de detecção nada é detectado, rastreado ou alertado.",
    paraQuem: TECNICO_E_SUPERVISOR,
    passos: [
      "Abra a câmera, ligue o monitoramento com \"Iniciar\", vá à aba \"Áreas\" (em \"Mais\") e escolha \"Área de detecção\".",
      "Escolha \"Retângulo\" (aperte e arraste de um canto ao outro) ou \"Polígono\" (um clique por ponto) e clique em \"Desenhar no vídeo\".",
      "\"Refazer\" apaga o desenho e recomeça. Clique em \"Salvar área\": a próxima análise já usa a área nova.",
      "\"Remover área\" volta a analisar o quadro inteiro.",
    ],
    ondeFica: "Câmeras, abrir a câmera, aba \"Áreas\" (em Mais), \"Área de detecção\".",
    notas: [
      "Fora da área, o vídeo fica escurecido. Nas imagens de evidência e no replay, fica escurecido e desfocado.",
      "Vale o ponto dos pés: quem tem os pés dentro da área é analisado, mesmo com a cabeça para fora.",
      "A saúde da câmera (obstruída, movida, escura) continua olhando o quadro inteiro.",
      "Ordem para preparar uma câmera: área de detecção, depois área de risco, depois a calibração da planta.",
    ],
    tela: { href: "/", rotulo: "Abrir as câmeras" },
    termos: ["área de detecção", "recorte", "palco", "plateia", "quadro inteiro", "escurecido"],
  },
  {
    id: "relatorio-de-turno",
    titulo: "Exportar o relatório de turno",
    resumo: "Números do turno prontos para imprimir ou salvar em PDF, calculados do banco do sistema.",
    paraQuem: TECNICO_E_SUPERVISOR,
    passos: [
      "Na barra superior, clique em \"Relatório do turno\". Ele abre em outra aba, com as últimas 8 horas de todas as câmeras.",
      "Confira os totais (alertas, críticos, falsos positivos e duração mediana) e as tabelas por tipo, por câmera e por hora.",
      "Quando houve infração de EPI, \"Infrações × NR-6\" liga cada uma ao item da norma que o texto sustenta, com o link do texto no gov.br.",
      "Clique em \"Imprimir / salvar PDF\" e, no navegador, escolha salvar como PDF.",
      "Para outra janela ou uma câmera só, mude o endereço, por exemplo /relatorio/turno?horas=4&camera_id=1. As horas vão de 0,5 a 72.",
      "Para planilha, o Supervisor usa \"Exportar\" na barra superior (CSV do histórico de alertas carregado) ou a aba Exportação da câmera.",
    ],
    ondeFica: "Barra superior, \"Relatório do turno\" (Técnico e Supervisor). \"Exportar\": barra superior do Supervisor.",
    notas: [
      "Todos os números vêm do banco do sistema. Nenhum texto do relatório é gerado por modelo de linguagem.",
      "Os identificadores de pessoa são rastreios por posição, não identidades.",
      "A seção NR-6 indica o requisito relacionado e não é parecer jurídico. O PDF não substitui o texto publicado no DOU.",
    ],
    tela: { href: "/relatorio/turno", rotulo: "Abrir o relatório do turno" },
    termos: ["pdf", "csv", "exportar", "imprimir", "nr-6", "turno", "planilha", "cipa"],
  },
  {
    id: "integrar-clp-scada",
    titulo: "Integrar com CLP ou SCADA (OPC UA e MQTT)",
    resumo: "O sistema publica o estado da planta a cada segundo e cada alerta novo. Todos os canais vêm desligados.",
    paraQuem: TECNICO_E_SUPERVISOR,
    passos: [
      "Ligue o canal no servidor: OPCUA_ATIVO=true, MQTT_ATIVO=true ou WEBHOOK_URL=https://... No modo demo (python run.py --demo), OPC UA e MQTT já sobem ligados.",
      "Abra a Torre de luz e confira os selos \"OPC UA\", \"MQTT\" e \"Webhook\": no ar, desligado ou falhou. Passe o mouse num selo que falhou para ver o motivo.",
      "OPC UA: conecte em opc.tcp://<endereço do servidor>:4840/visionepi/ e leia o índice do namespace pelo URI urn:visionepi, sem fixar o número.",
      "Leia Planta.PlantaEmAlarme (verdadeiro quando a torre está vermelha) e Planta.Torre (verde, amarelo ou vermelho). Por câmera: Cameras.Camera_<id>.Estado, .Conformidade, .UltimoAlerta e .IncidentesAtivos.<regra>.",
      "MQTT: assine visionepi/#. O estado da planta vai em visionepi/planta/estado (retido) e cada alerta novo em visionepi/<id da câmera>/alerta.",
      "Webhook: cada alerta novo chega como POST em JSON na URL configurada.",
    ],
    ondeFica: "Torre de luz (/torre) e Modo TV mostram o mesmo estado que o CLP lê. Guia completo: docs/NEXT2026/INTEGRACAO.md, no repositório.",
    notas: [
      "Torre vermelha: alerta crítico ativo, ou câmera obstruída ou movida. Amarela: alerta não crítico, câmera sem sinal ou imagem escura, ofuscada ou desfocada. Verde: nenhum alerta e todas as câmeras com imagem. A sirene liga com crítico ainda não reconhecido.",
      "O OPC UA é somente leitura e sobe sem segurança. O broker MQTT embutido é anônimo e sem TLS. Use só em rede de chão de fábrica isolada. Em produção: certificado no OPC UA e TLS com credencial no MQTT.",
      "Porta ocupada, broker fora ou rede caída não derrubam o sistema: o canal aparece como falhou.",
      "Nada do que é publicado identifica pessoa.",
    ],
    tela: { href: "/torre", rotulo: "Abrir a Torre de luz" },
    termos: ["opc ua", "mqtt", "scada", "clp", "plc", "webhook", "torre", "sirene", "integração", "protocolo"],
  },
  {
    id: "cadastrar-camera",
    titulo: "Cadastrar uma câmera",
    resumo: "Registre a fonte de vídeo: webcam USB, câmera de rede (RTSP), arquivo de vídeo ou celular.",
    paraQuem: TECNICO_E_SUPERVISOR,
    passos: [
      "Em Câmeras, clique em \"Adicionar câmera\".",
      "Dê um nome e, se quiser, o local. Escolha o tipo de fonte: USB / webcam, RTSP, Arquivo ou Celular (via QR code).",
      "USB: o sistema testa os índices de 0 a 5 e lista as câmeras que respondem. Escolha uma e a resolução dela é preenchida. RTSP: informe a URL, como rtsp://192.168.0.10/stream1. Arquivo: informe o caminho do vídeo.",
      "Ajuste FPS alvo e resolução só se quiser forçar outros valores. Clique em \"Cadastrar câmera\".",
      "Abra a câmera e clique em \"Iniciar\" para começar o monitoramento.",
    ],
    ondeFica: "Câmeras (a grade): botão \"Adicionar câmera\".",
    notas: [
      "Um arquivo de vídeo serve para demonstração: a gravação faz o papel da câmera ao vivo.",
      "Depois do cadastro, siga com a referência, a planta, a zona de risco e os EPIs. O assistente do primeiro acesso leva por essa ordem.",
    ],
    tela: { href: "/", rotulo: "Abrir as câmeras" },
    termos: ["usb", "rtsp", "webcam", "arquivo", "nova câmera", "adicionar"],
  },
  {
    id: "portaria",
    titulo: "Ligar a Portaria e acompanhar o Portal de Entrada",
    resumo: "A Portaria libera ou nega a entrada pelos EPIs que você exigir para o setor.",
    paraQuem: TODOS,
    passos: [
      "Técnico e Supervisor: abra a câmera da entrada e vá à aba \"Portaria\" (em \"Mais\").",
      "Marque os EPIs obrigatórios. Um EPI cujo recurso está desligado na câmera aparece como \"Recurso desligado nesta câmera: sempre negaria\".",
      "Clique em \"Ligar portaria\" (ou \"Salvar exigências\"). A \"Prévia ao vivo\" mostra o veredito e os EPIs exigidos.",
      "Quem passa para diante da câmera no Portal de Entrada. Cada EPI exigido aparece como \"Confirmado\", \"Faltando\" ou \"Não verificável neste enquadramento\".",
      "O Operador de uma câmera com portaria vê a tela de portaria no lugar da tela comum.",
      "\"Desligar portaria\" volta ao funcionamento normal.",
    ],
    ondeFica: "Técnico e Supervisor: câmera, aba \"Portaria\" (em Mais). Portal de Entrada: /portal?camera=<número da câmera>.",
    notas: [
      "A Portaria só libera a entrada se todos os EPIs marcados estiverem visíveis. Na dúvida, nega.",
      "\"Não verificável\" não conta como confirmado nem como falta.",
      "Nenhuma foto é salva. O check-in conta para a meta do setor, nunca para uma pessoa.",
      "\"Tente enganar a IA\" liga o Raio-X no portal e explica por que o sistema decidiu cada item.",
    ],
    tela: { href: "/portal", rotulo: "Abrir o Portal de Entrada" },
    termos: ["portaria", "portal", "check-in", "entrada", "gate", "epi exigido", "enganar"],
  },
  {
    id: "primeiro-acesso",
    titulo: "Fazer o primeiro acesso da planta",
    resumo: "O assistente leva do zero ao \"pronto para operar\" e confere, com o que o sistema encontrou de verdade, o que já está feito.",
    paraQuem: ["supervisor"],
    passos: [
      "No Início, clique no aviso \"Configure a planta em poucos passos\" ou abra Primeiro acesso.",
      "Siga a ordem: cadastrar uma câmera, capturar a imagem de referência, calibrar a planta, desenhar a área de risco, definir os EPIs exigidos e criar as contas da equipe.",
      "Passos que o sistema encontra sozinho aparecem como \"Detectado\". Nos demais, faça na tela da câmera (o botão \"Abrir a câmera\" leva até lá) e volte para marcar como feito.",
      "Se não for o momento, clique em \"Pular por enquanto\". O progresso fica salvo e você retoma depois.",
      "No último passo, \"Pronto para operar\" confere tudo. Clique em \"Concluir o primeiro acesso\".",
      "Para refazer, use \"Refazer o primeiro acesso\".",
    ],
    ondeFica: "Tela Primeiro acesso. Início do Supervisor: aviso \"Configure a planta em poucos passos\" (some quando concluído).",
    notas: [
      "A referência é capturada sozinha na primeira imagem boa, com a câmera ligada e a cena em ordem.",
      "No modo demo, o primeiro acesso já vem concluído, e o Supervisor pode refazê-lo.",
      "Só contas do tipo Supervisor abrem esta tela.",
    ],
    tela: { href: "/primeiro-acesso", rotulo: "Abrir o primeiro acesso" },
    termos: ["onboarding", "assistente", "configurar", "começar", "pronto para operar", "checklist"],
  },
  {
    id: "criar-contas",
    titulo: "Criar e administrar contas da equipe",
    resumo: "Cada pessoa entra com a própria conta. O tipo de conta define o que ela vê e faz.",
    paraQuem: ["supervisor"],
    passos: [
      "No Início, abra \"Contas\" e clique em \"Nova conta\".",
      "Informe nome, e-mail (que será o login) e senha. Escolha o tipo: Operador (vê só a câmera do setor), Técnico (todas as câmeras e configuração) ou Supervisor (tudo, inclusive contas).",
      "Para Operador, escolha a câmera do setor. Sem ela, o Operador não vê câmera nenhuma e a barra superior avisa \"Sem setor atribuído\".",
      "Clique em \"Criar conta\" e passe os dados em mãos. Nada é enviado por e-mail.",
      "Na lista, \"Trocar senha\" encerra as sessões abertas da conta. \"Desativar\" e \"Reativar\" bloqueiam e liberam o acesso. \"Apagar\" remove a conta de vez, com confirmação.",
      "No primeiro acesso da planta, o assistente cria a conta com uma senha temporária que aparece uma única vez. Copie antes de fechar.",
    ],
    ondeFica: "Início do Supervisor, bloco \"Contas\".",
    notas: ["Você não vê as ações de senha, desativar e apagar na sua própria conta."],
    termos: ["usuário", "senha", "login", "operador", "técnico", "supervisor", "acesso", "permissão de acesso"],
  },
  {
    id: "tv-e-liga",
    titulo: "Ler o Modo TV e a Liga de Setores",
    resumo: "O Modo TV mostra a segurança do turno por setor, legível de longe. A Liga transforma metas em pontos do setor.",
    paraQuem: TECNICO_E_SUPERVISOR,
    passos: [
      "Abra o Modo TV numa tela da parede. Cada bloco é um setor.",
      "Leia \"EPIs exigidos em uso agora\" (a conformidade do momento) e os minutos seguidos com 100% dos EPIs.",
      "As barras mostram a meta de minutos conformes e de check-ins no portal. As conquistas do turno aparecem embaixo do setor.",
      "No topo, a torre de luz mostra o mesmo estado que o CLP lê: verde, amarelo ou vermelho.",
      "A Liga de Setores mostra pontos por setor, o nível da planta e as missões do turno. O Supervisor cria missões na tela Liga: check-ins no portal, incidentes reconhecidos em até 1 min, rótulos revisados ou minutos conformes.",
      "Nos últimos 10 minutos do turno, a TV abre a Retrospectiva uma vez.",
    ],
    ondeFica: "Modo TV (/tv) e Liga de Setores (/liga). Supervisor: Início, Modo TV e Liga de Setores.",
    notas: [
      "A pontuação é por setor, nunca por pessoa. Só entram indicadores positivos.",
      "Minutos sem ninguém na câmera não contam.",
    ],
    tela: { href: "/tv", rotulo: "Abrir o Modo TV" },
    termos: ["andon", "tv", "liga", "missão", "meta", "pontos", "retrospectiva", "setor", "parede"],
  },
  {
    id: "rotular-recortes",
    titulo: "Rotular recortes do modelo",
    resumo: "Confirme ou rejeite os recortes em que o modelo ficou em dúvida e exporte só os confirmados.",
    paraQuem: TECNICO_E_SUPERVISOR,
    passos: [
      "Abra Rotular recortes. A tela mostra um recorte por vez, com a classe de EPI que o modelo achou.",
      "Responda \"Isto é ...?\". Se for, use o botão \"É ...\" ou a seta para a direita. Se não for, use \"Não é\" ou a seta para a esquerda.",
      "Quando a fila esvazia, a tela avisa e confere de novo a cada poucos segundos. Os recortes chegam quando o modelo fica em dúvida sobre um EPI.",
      "\"Exportar conjunto de dados YOLO (.zip)\" baixa só os recortes confirmados.",
    ],
    ondeFica: "Tela Rotular recortes. Supervisor: Início, Visão geral, Rotular recortes. Técnico: Ctrl K e \"rotular\".",
    notas: [
      "Os recortes vêm do vídeo com rosto desfocado.",
      "O sistema não treina o modelo. O arquivo exportado serve para treinar fora dele.",
      "Se a tela disser que o aprendizado ativo está desligado, peça a quem cuida do servidor para ligá-lo.",
    ],
    tela: { href: "/rotular", rotulo: "Abrir Rotular recortes" },
    termos: ["aprendizado ativo", "yolo", "dataset", "recorte", "treino", "confirmar", "rejeitar"],
  },
  {
    id: "apresentacao",
    titulo: "Conduzir a apresentação",
    resumo: "O Modo Apresentação conta o produto em cenas, com controle pelo teclado ou pelo celular.",
    paraQuem: TECNICO_E_SUPERVISOR,
    passos: [
      "Abra Apresentação. A tela mostra uma cena por vez, com título e legenda embaixo.",
      "Avance com a seta para a direita, Espaço ou Page Down. Volte com a seta para a esquerda ou Page Up.",
      "A tecla Q mostra ou esconde o QR code do controle.",
      "Para controlar pelo celular, leia o QR code. Celular e computador precisam estar na mesma rede, com o servidor em HTTPS (python run.py --demo --https).",
      "Se o servidor sair do ar, o teclado ainda troca a cena nesta tela.",
    ],
    ondeFica: "Tela Apresentação. Supervisor: Início, Apresentação. Técnico: Ctrl K e \"apresentação\".",
    notas: ["Se o controle do celular mostrar \"Link expirado\", leia o QR code da tela de novo."],
    tela: { href: "/palco", rotulo: "Abrir a Apresentação" },
    termos: ["palco", "demo", "cenas", "controle", "slides", "apresentar"],
  },
  {
    id: "gemeo-digital",
    titulo: "Ler o Gêmeo digital da planta",
    resumo: "Cada pessoa é uma cápsula na cor do estado, na posição que a calibração dá ao pé dela. Nunca aparece foto.",
    paraQuem: TECNICO_E_SUPERVISOR,
    passos: [
      "Calibre a planta da câmera. Sem calibração não há posição na planta.",
      "Abra o Gêmeo digital. As cores são: Conforme, Sem EPI exigido, Na zona de risco e Possível queda.",
      "Clique numa pessoa para ver o ID de rastreio, o estado, os EPIs que faltam e a linha do tempo das últimas mudanças.",
      "Se a pessoa tem alerta, \"Ver replay do alerta\" abre o replay.",
      "Sem WebGL, o sistema mostra uma planta 2D. Para forçar a visão 2D, acrescente ?2d=1 ao endereço.",
    ],
    ondeFica: "Tela Gêmeo digital. Supervisor: Início, Gêmeo digital. Técnico: Ctrl K e \"gêmeo\".",
    notas: ["O número é de rastreio desta câmera e não identifica ninguém."],
    tela: { href: "/gemeo", rotulo: "Abrir o Gêmeo digital" },
    termos: ["3d", "planta", "cápsula", "gêmeo", "digital", "posição"],
  },
  {
    id: "limites-do-sistema",
    titulo: "O que o sistema não faz (limites honestos)",
    resumo: "Antes de confiar numa tela, saiba o que ela não consegue afirmar.",
    paraQuem: TODOS,
    tituloDosPassos: "O que lembrar",
    passos: [
      "Não detectado não é ausente. O sistema só diz o que a câmera viu. Se um EPI está fora do ângulo, longe, no escuro ou é de um tipo que o modelo não detecta, a tela mostra \"indisponível\", \"não verificável\" ou \"verificação manual\", nunca \"conforme\".",
      "O ID de rastreio não é identidade. \"Pessoa 12\" é um número dado pela posição na imagem, e pode haver troca de número durante o dia. Não há reconhecimento facial, nome ligado a ID nem ranking de pessoas: pontuação e metas são por setor.",
      "A câmera auxilia o vigia; não o substitui (NR-33, 33.3.4.1). Ela também não emite nem substitui a Permissão de Trabalho.",
      "A contagem de pessoas é por câmera. Na evacuação, câmeras que se sobrepõem podem contar a mesma pessoa duas vezes.",
      "Tendência de risco é estatística do que já aconteceu, não previsão. O pré-alerta de aproximação é uma projeção do movimento, não uma certeza.",
      "O relatório de turno e as indicações de norma ajudam a achar o requisito relacionado. Não são parecer jurídico.",
      "Rostos ficam desfocados enquanto o modo privacidade estiver ligado. Só o Supervisor o desliga, e a troca fica registrada com o usuário.",
    ],
    ondeFica: "Vale para todas as telas. Para tirar dúvida sobre uma tela específica, use o botão de ajuda (?) dela.",
    termos: ["limites", "identidade", "facial", "lgpd", "privacidade", "detectado", "ausente", "rastreio", "honesto", "não faz"],
  },
];

/**
 * Artigo certo para cada tela. A chave é o endereço (começa com "/"), o nome da
 * tela do store (`screen`) ou `focus:<aba>` para uma aba da câmera em foco
 * (as chaves das abas são as de `TABS_BY_MODE`, em camera-focus.tsx).
 * `BotaoDeAjuda` recebe o valor, não a chave.
 */
export const ARTIGO_DA_TELA: Record<string, string> = {
  // endereços
  "/auditoria": "verificar-integridade",
  "/simulador": "simulador-e-se",
  "/regras": "criar-regra",
  "/permissoes": "emitir-permissao",
  "/evacuacao": "acionar-evacuacao",
  "/torre": "integrar-clp-scada",
  "/tv": "tv-e-liga",
  "/liga": "tv-e-liga",
  "/portal": "portaria",
  "/palco": "apresentacao",
  "/gemeo": "gemeo-digital",
  "/rotular": "rotular-recortes",
  "/primeiro-acesso": "primeiro-acesso",
  "/relatorio/turno": "relatorio-de-turno",
  // telas do store
  kiosk: "reconhecer-alerta",
  grid: "cadastrar-camera",
  focus: "reconhecer-alerta",
  overview: "tv-e-liga",
  accounts: "criar-contas",
  sobre: "limites-do-sistema",
  // abas da câmera em foco
  "focus:alerts": "reconhecer-alerta",
  "focus:zone": "area-de-deteccao",
  "focus:gate": "portaria",
  "focus:camconfig": "camera-do-celular",
  "focus:planta": "calibrar-planta",
  "focus:export": "relatorio-de-turno",
};

/** Id do artigo da tela, ou `undefined` se a tela não tem um (então não ponha o botão). */
export function artigoDaTela(chave: string): string | undefined {
  return Object.prototype.hasOwnProperty.call(ARTIGO_DA_TELA, chave) ? ARTIGO_DA_TELA[chave] : undefined;
}

export function artigoPorId(id: string | null | undefined): Artigo | undefined {
  return id ? ARTIGOS.find((a) => a.id === id) : undefined;
}

/** Endereço do artigo (o mesmo que `BotaoDeAjuda` abre). */
export function enderecoDoArtigo(id: string): string {
  return `/ajuda?artigo=${encodeURIComponent(id)}`;
}

// ---- busca -------------------------------------------------------------------

const INDICE = ARTIGOS.map((artigo) => ({
  artigo,
  titulo: normalizar(artigo.titulo),
  corpo: normalizar(
    [artigo.resumo, ...artigo.passos, artigo.ondeFica, ...(artigo.notas ?? []), ...(artigo.termos ?? [])].join(" "),
  ),
}));

/**
 * Artigos que casam com a consulta (sem acento, sem diferenciar maiúsculas; todas
 * as palavras precisam aparecer, em qualquer ordem), do mais para o menos
 * relevante: palavra no título vale mais que palavra no corpo. Consulta vazia:
 * todos, na ordem do arquivo. `tipo` filtra pelos artigos desse tipo de conta.
 */
export function buscarArtigos(consulta: string, tipo?: TipoDeConta | null): Artigo[] {
  const termos = termosDa(consulta);
  const doTipo = INDICE.filter((i) => !tipo || i.artigo.paraQuem.includes(tipo));
  if (!termos.length) return doTipo.map((i) => i.artigo);
  const pontuados: { artigo: Artigo; pontos: number; ordem: number }[] = [];
  doTipo.forEach((i, ordem) => {
    let pontos = 0;
    for (const termo of termos) {
      if (i.titulo.includes(termo)) pontos += 3;
      else if (i.corpo.includes(termo)) pontos += 1;
      else return;
    }
    pontuados.push({ artigo: i.artigo, pontos, ordem });
  });
  return pontuados.sort((a, b) => b.pontos - a.pontos || a.ordem - b.ordem).map((p) => p.artigo);
}
