"""Relatório mensal para a CIPA (M10, MISSÃO 4): os números do mês, sem nada individual.

Duas camadas, as duas sem Flask:

- `montar_relatorio_mensal` devolve o dicionário (o JSON de `GET /api/relatorio/mensal`);
- `renderizar_html` transforma esse dicionário na página A4 de `GET /relatorio/mensal`.

As rotas (e o escopo do Operador) ficam em `app/api/relatorio.py`, ao lado do
relatório de turno, de onde vem o mesmo estilo e o mesmo princípio: número
calculado do banco, nenhum texto de modelo de linguagem.

Regra de privacidade do relatório: só contagens, medianas e nomes de câmera,
zona e regra. Não entram rótulo de rastreio, nome, e-mail, "responsável" de
Permissão de Trabalho nem quem encerrou/reconheceu/iniciou — quem operou
aparece só como "N reconhecimentos". Nenhum campo individual chega ao
dicionário nem à página: só contagens, medianas e nomes de câmera, zona e regra.

Mês: limites em HORA LOCAL do servidor (dia 1 às 00:00 até o dia 1 do mês
seguinte), a mesma convenção da temporada da Liga e dos turnos.

Dependências opcionais, todas injetáveis para testar sem monitor, disco ou
cadeia reais: `andon` (contadores ao vivo), `pasta_evacuacoes` e `verificar_cadeia`.
A tabela `intervencoes` pode não existir (outro agente a cria): a seção diz
"sem registro disponível" em vez de quebrar.
"""

from __future__ import annotations

import html
import logging
import re
import statistics
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from sqlalchemy.exc import SQLAlchemyError

import app.models as modelos
from app.extensions import db
from app.models import (
    PERMISSAO_CANCELADA,
    PERMISSAO_ENCERRADA,
    Alert,
    Camera,
    Incidente,
    PermissaoDeTrabalho,
    PontoDaLiga,
    _aware,
)
from app.services.alertas_simulados import e_simulado
from app.services.evacuacao import AVISO_DUPLA_CONTAGEM, listar_relatorios
from app.services.incidentes import titulo_do_alerta
from app.services.liga import setor_da_camera
from app.utils.texto import pluralizar

logger = logging.getLogger(__name__)

MESES = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
         "novembro", "dezembro")
_UM_DIA = timedelta(days=1)
_MES_RE = re.compile(r"(\d{4})-(0[1-9]|1[0-2])")
SO_TECNICO = "Disponível para Técnico e Supervisor (cobre a planta inteira, não um setor)."
MAX_INTERVENCOES_NO_RELATORIO = 100

FONTES = {
    "indicadores": "contado pelo sistema: cada minuto com gente na câmera e todos com os EPIs exigidos vira um ponto "
                   "na Liga de Setores. O total de minutos com gente não é gravado por mês: só aparece o contador do "
                   "servidor desde que foi iniciado.",
    "alertas": "contado pelo sistema, a partir dos alertas gravados no banco do VisionEPI no período. Falsos positivos "
               "marcados como tal ficam de fora das divisões por tipo e por câmera.",
    "incidentes": "contado pelo sistema, a partir dos incidentes (alertas agrupados por tipo e zona) abertos no período.",
    "intervencoes": "contado pelo sistema, a partir das intervenções registradas no período.",
    "permissoes": "contado pelo sistema: emitidas pela data de emissão, encerradas e canceladas pela data de encerramento.",
    "evacuacoes": "contado pelo sistema, a partir dos relatórios de evacuação arquivados em disco. A contagem é por câmera.",
    "cadeia_de_custodia": "verificado pelo sistema no momento em que este relatório foi gerado (a cadeia inteira, não só o mês).",
}


class MesInvalido(ValueError):
    """`mes` fora do formato AAAA-MM (ou fora de 2000–2100)."""


# ------------------------------------------------------------------ tempo
def interpretar_mes(texto: str | None, agora: datetime) -> tuple[int, int]:
    """"2026-10" → (2026, 10). Vazio = o mês corrente na hora local."""
    if not texto or not texto.strip():
        local = agora.astimezone()
        return local.year, local.month
    achou = _MES_RE.fullmatch(texto.strip())
    if achou is None or not 2000 <= int(achou.group(1)) <= 2100:
        raise MesInvalido(texto)
    return int(achou.group(1)), int(achou.group(2))


def limites_do_mes(ano: int, mes: int) -> tuple[datetime, datetime]:
    """[início, fim) do mês em hora local, devolvidos em UTC (com fuso)."""
    inicio = datetime(ano, mes, 1).astimezone()
    seguinte = datetime(ano + (mes == 12), mes % 12 + 1, 1).astimezone()
    return inicio.astimezone(timezone.utc), seguinte.astimezone(timezone.utc)


def _naive_utc(valor: datetime) -> datetime:
    return valor.astimezone(timezone.utc).replace(tzinfo=None)


def _no_periodo(coluna, inicio: datetime, fim: datetime):
    """Filtro [início, fim) como o resto do projeto: SQLite guarda UTC sem fuso."""
    return (coluna >= _naive_utc(inicio)) & (coluna < _naive_utc(fim))


def _dentro(iso: str | None, inicio: datetime, fim: datetime) -> bool:
    try:
        valor = _aware(datetime.fromisoformat(str(iso)))
    except ValueError:
        return False
    return inicio <= valor < fim


def _rotulo_do_mes(ano: int, mes: int) -> str:
    return f"{MESES[mes - 1]} de {ano}"


# ------------------------------------------------------------------ seções
def _por_camera(camera_ids, nomes: dict[int, str]) -> dict[str, int]:
    contagem = Counter(nomes.get(cid) or f"Câmera #{cid}" for cid in camera_ids)
    return dict(contagem.most_common())


def _mediana(valores: list[float]) -> float | None:
    return round(statistics.median(valores), 1) if valores else None


def _alertas(inicio, fim, camera_id, nomes) -> dict[str, Any]:
    consulta = Alert.query.filter(_no_periodo(Alert.created_at, inicio, fim))
    if camera_id is not None:
        consulta = consulta.filter(Alert.camera_id == camera_id)
    todos = consulta.all()
    validos = [a for a in todos if not (a.metadata_json or {}).get("false_positive")]
    return {
        "total": len(todos),
        # Quantos dos alertas do mês são histórico simulado da demonstração (já contados no total).
        "simulados": sum(1 for a in todos if e_simulado(a)),
        "validos": len(validos),
        "falsos_positivos": len(todos) - len(validos),
        "criticos": sum(1 for a in validos if a.severity == "critical"),
        # Marca de "Avisei o colaborador"; só a contagem, nunca quem avisou.
        "colaboradores_avisados": sum(1 for a in validos if (a.metadata_json or {}).get("acknowledged")),
        "por_regra": dict(Counter(titulo_do_alerta(a.message) for a in validos).most_common()),
        "por_camera": _por_camera((a.camera_id for a in validos), nomes),
    }


def _incidentes(inicio, fim, camera_id, nomes) -> dict[str, Any]:
    consulta = Incidente.query.filter(_no_periodo(Incidente.aberto_em, inicio, fim))
    if camera_id is not None:
        consulta = consulta.filter(Incidente.camera_id == camera_id)
    itens = consulta.all()
    reconhecidos = [i for i in itens if i.reconhecido_em is not None and i.aberto_em is not None]
    segundos = [(_aware(i.reconhecido_em) - _aware(i.aberto_em)).total_seconds() for i in reconhecidos]
    return {
        "total": len(itens),
        "criticos": sum(1 for i in itens if i.severity == "critical"),
        # Quem reconheceu (papel) existe na tabela, mas não sai daqui: "N reconhecimentos".
        "reconhecimentos": len(reconhecidos),
        "mediana_ate_reconhecer_s": _mediana(segundos),
        # `titulo` já é o texto da regra sem o rótulo de rastreio ("Sem capacete").
        "por_regra": dict(Counter(i.titulo for i in itens).most_common()),
        "por_zona": dict(Counter(i.zona for i in itens).most_common()),
        "por_camera": _por_camera((i.camera_id for i in itens), nomes),
    }


def _minutos_conformes(inicio, fim, camera_id) -> int:
    consulta = PontoDaLiga.query.filter(PontoDaLiga.tipo == "minuto_conforme", _no_periodo(PontoDaLiga.criado_em, inicio, fim))
    if camera_id is not None:
        consulta = consulta.filter(PontoDaLiga.camera_id == camera_id)
    return consulta.count()


def _contador_do_servidor(andon: Callable[[], list[dict[str, Any]]] | None, camera_id: int | None) -> dict[str, Any] | None:
    """Minutos com gente e conformes desde que o servidor subiu (memória dos workers, não é do mês)."""
    if andon is None:
        return None
    try:
        resumos = [r for r in andon() if camera_id is None or r.get("camera_id") == camera_id]
    except Exception:  # noqa: BLE001  (monitor de teste ou worker caído não derruba o relatório)
        logger.warning("relatorio_mensal_andon_falhou", exc_info=True)
        return None
    com_gente = sum(int(r.get("minutos_com_pessoas") or 0) for r in resumos)
    conformes = sum(int(r.get("minutos_conformes") or 0) for r in resumos)
    return {
        "minutos_com_gente": com_gente,
        "minutos_conformes": conformes,
        "conformidade_pct": round(100 * conformes / com_gente, 1) if com_gente else None,
        "nota": "contador do servidor desde que foi iniciado; reiniciar o servidor zera",
    }


def _indicadores(inicio, fim, camera_id, agora, andon) -> dict[str, Any]:
    no_mes_corrente = inicio <= agora < fim
    return {
        "minutos_conformes": _minutos_conformes(inicio, fim, camera_id),
        "minutos_com_gente": None,  # não é gravado por mês (ver FONTES["indicadores"])
        "conformidade_pct": None,
        "desde_que_o_servidor_subiu": _contador_do_servidor(andon, camera_id) if no_mes_corrente else None,
    }


def _humanizar(texto: Any) -> str:
    return str(texto or "sem tipo").replace("_", " ").strip().capitalize()


def _intervencoes(inicio, fim, camera_id, nomes) -> dict[str, Any]:
    """Defensivo: se o modelo ou a tabela `intervencoes` não existirem neste banco, a seção diz que não há registro."""
    indisponivel = {"disponivel": False, "total": None, "itens": []}
    modelo = getattr(modelos, "Intervencao", None)
    if modelo is None:
        return indisponivel
    # `data_da_intervencao` é um dia na hora local do servidor.
    primeiro, seguinte = inicio.astimezone().date(), fim.astimezone().date()
    try:
        consulta = modelo.query.filter(modelo.data_da_intervencao >= primeiro, modelo.data_da_intervencao < seguinte)
        if camera_id is not None:
            # Vale para a câmera ou para o setor dela (a intervenção é de UM dos dois).
            setor = setor_da_camera(db.session.get(Camera, camera_id))
            consulta = consulta.filter((modelo.camera_id == camera_id) | (modelo.setor == setor))
        itens = consulta.order_by(modelo.data_da_intervencao, modelo.id).all()
    except SQLAlchemyError:  # tabela ainda não criada neste banco
        db.session.rollback()
        return indisponivel
    return {
        "disponivel": True,
        "total": len(itens),
        # `titulo` é texto livre de quem registrou; `criada_por` e `descricao` ficam de fora.
        "itens": [{"data": i.data_da_intervencao.isoformat(),
                   "titulo": i.titulo,
                   "escopo": i.setor if i.setor else (nomes.get(i.camera_id) or f"Câmera #{i.camera_id}")}
                  for i in itens[:MAX_INTERVENCOES_NO_RELATORIO]],
    }


def _permissoes(inicio, fim, camera_id) -> dict[str, Any]:
    """Só contagens: `responsavel`, `criada_por` e `encerrada_por` não são lidos."""
    def consultar(coluna_de_data, *colunas, extra=()):
        consulta = db.session.query(*colunas).filter(_no_periodo(coluna_de_data, inicio, fim), *extra)
        if camera_id is not None:
            consulta = consulta.filter(PermissaoDeTrabalho.camera_id == camera_id)
        return consulta

    emitidas = consultar(PermissaoDeTrabalho.criada_em, PermissaoDeTrabalho.tipo).all()
    return {
        "emitidas": len(emitidas),
        "por_tipo": dict(Counter(tipo for (tipo,) in emitidas).most_common()),
        "encerradas": consultar(PermissaoDeTrabalho.encerrada_em, PermissaoDeTrabalho.id,
                                extra=(PermissaoDeTrabalho.status == PERMISSAO_ENCERRADA,)).count(),
        "canceladas": consultar(PermissaoDeTrabalho.encerrada_em, PermissaoDeTrabalho.id,
                                extra=(PermissaoDeTrabalho.status == PERMISSAO_CANCELADA,)).count(),
    }


_ROTULO_DA_PERMISSAO = {"espaco_confinado": "Espaço confinado", "altura": "Trabalho em altura", "geral": "Geral"}


def _evacuacoes(inicio, fim, pasta: Path | None) -> dict[str, Any]:
    itens = []
    for r in listar_relatorios(pasta) if pasta is not None else []:
        if _dentro(r.get("inicio"), inicio, fim):
            # Sem iniciada_por / encerrada_por: quem operou não entra no relatório.
            itens.append({k: r.get(k) for k in ("numero", "inicio", "duracao_s", "total_maximo_somado",
                                                 "chegadas_ponto_de_encontro")})
    return {"disponivel": True, "total": len(itens), "itens": sorted(itens, key=lambda i: i["inicio"] or ""),
            "aviso": AVISO_DUPLA_CONTAGEM}


def _cadeia(verificar_cadeia: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        resultado = verificar_cadeia()
    except Exception:  # noqa: BLE001  (a verificação nunca derruba o relatório; diz que não conseguiu)
        logger.warning("relatorio_mensal_cadeia_falhou", exc_info=True)
        db.session.rollback()
        return {"disponivel": False, "integra": None}
    return {"disponivel": True, "integra": bool(resultado.get("integra"))}


def _verificar_cadeia_padrao() -> dict[str, Any]:
    from app.services import custodia

    return custodia.verificar()


# ------------------------------------------------------------------ montagem
def montar_relatorio_mensal(
    ano: int,
    mes: int,
    *,
    camera_id: int | None = None,
    visao_da_planta: bool = True,
    agora: datetime | None = None,
    pasta_evacuacoes: Path | None = None,
    andon: Callable[[], list[dict[str, Any]]] | None = None,
    verificar_cadeia: Callable[[], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Números do mês. `camera_id` restringe alertas, incidentes, minutos, permissões e intervenções.

    `visao_da_planta=False` (Operador): evacuações e cadeia de custódia não são
    do setor dele, então saem marcadas como indisponíveis — as rotas de
    evacuação já respondem 403 ao Operador.
    """
    agora = _aware(agora) if agora is not None else datetime.now(timezone.utc)
    inicio, fim = limites_do_mes(ano, mes)
    nomes = {c.id: c.name for c in Camera.query.all()}
    alertas = _alertas(inicio, fim, camera_id, nomes)
    incidentes = _incidentes(inicio, fim, camera_id, nomes)
    indicadores = _indicadores(inicio, fim, camera_id, agora, andon)
    intervencoes = _intervencoes(inicio, fim, camera_id, nomes)
    permissoes = _permissoes(inicio, fim, camera_id)
    permissoes["por_tipo"] = {_ROTULO_DA_PERMISSAO.get(k, _humanizar(k)): v for k, v in permissoes["por_tipo"].items()}
    if visao_da_planta:
        evacuacoes = _evacuacoes(inicio, fim, pasta_evacuacoes)
        cadeia = _cadeia(verificar_cadeia or _verificar_cadeia_padrao)
    else:
        evacuacoes = {"disponivel": False, "total": None, "itens": [], "aviso": AVISO_DUPLA_CONTAGEM, "motivo": SO_TECNICO}
        cadeia = {"disponivel": False, "integra": None, "motivo": SO_TECNICO}
    return {
        "mes": f"{ano:04d}-{mes:02d}",
        "rotulo": _rotulo_do_mes(ano, mes),
        "periodo": {"inicio": inicio.astimezone().date().isoformat(),
                    "fim": (fim.astimezone().date() - _UM_DIA).isoformat()},
        "gerado_em": agora.isoformat(),
        "camera_id": camera_id,
        "indicadores": indicadores,
        "alertas": alertas,
        "alertas_simulados": alertas["simulados"],
        "incidentes": incidentes,
        "intervencoes": intervencoes,
        "permissoes": permissoes,
        "evacuacoes": evacuacoes,
        "cadeia_de_custodia": cadeia,
        "fontes": dict(FONTES),
        "sem_dados": not any((
            alertas["total"], incidentes["total"], indicadores["minutos_conformes"], permissoes["emitidas"],
            permissoes["encerradas"], permissoes["canceladas"], evacuacoes["total"], intervencoes["total"],
        )),
    }


# ------------------------------------------------------------------ HTML
def _e(valor: Any) -> str:
    return html.escape(str(valor))


def _tabela(dados: dict[str, Any], vazio: str = "nenhum") -> str:
    linhas = "".join(f"<tr><td>{_e(k)}</td><td>{_e(v)}</td></tr>" for k, v in dados.items())
    return f"<table>{linhas or f'<tr><td colspan=2>{_e(vazio)}</td></tr>'}</table>"


def _duracao(segundos: float | None) -> str:
    if segundos is None:
        return "sem dado"
    if segundos < 90:
        return f"{segundos:.0f} s".replace(".", ",")
    return f"{segundos / 60:.1f} min".replace(".", ",")


def _numero(n: int | None) -> str:
    return "sem dado" if n is None else f"{n:,}".replace(",", ".")


def _secao_indicadores(r: dict[str, Any]) -> str:
    ind = r["indicadores"]
    ao_vivo = ind["desde_que_o_servidor_subiu"]
    linhas = {"Minutos conformes no mês (gravados)": _numero(ind["minutos_conformes"])}
    if ao_vivo is not None:
        pct = f"{ao_vivo['conformidade_pct']:.1f}%".replace(".", ",") if ao_vivo["conformidade_pct"] is not None else "sem dado"
        linhas["Minutos com gente, desde que o servidor subiu"] = _numero(ao_vivo["minutos_com_gente"])
        linhas["Minutos conformes, desde que o servidor subiu"] = _numero(ao_vivo["minutos_conformes"])
        linhas["Conformidade nesse período"] = pct
    nota = ("O total mensal de minutos com gente não é gravado: por isso não há percentual de conformidade do mês, "
            "só o contador do servidor." if ind["minutos_com_gente"] is None else "")
    return f"<h2>Indicadores do mês</h2>{_tabela(linhas)}<p class=nota>{_e(nota)}</p>"


def _secao_intervencoes(r: dict[str, Any]) -> str:
    i = r["intervencoes"]
    if not i["disponivel"]:
        return "<h2>Intervenções</h2><p class=nota>Sem registro de intervenções disponível neste banco.</p>"
    linhas = "".join(f"<tr><td>{_e(datetime.fromisoformat(x['data']).strftime('%d/%m/%Y'))}</td><td>{_e(x['titulo'])}</td>"
                     f"<td>{_e(x['escopo'])}</td></tr>" for x in i["itens"])
    tabela = f"<table class=evac>{linhas}</table>" if linhas else ""
    return (f"<h2>Intervenções</h2><p>{_e(pluralizar(i['total'], 'intervenção', 'intervenções'))} no mês.</p>{tabela}"
            "<p class=nota>Os títulos são o texto que quem registrou digitou.</p>")


def _secao_permissoes(r: dict[str, Any]) -> str:
    p = r["permissoes"]
    resumo = {"Emitidas": p["emitidas"], "Encerradas": p["encerradas"], "Canceladas": p["canceladas"]}
    return f"<h2>Permissões de Trabalho</h2>{_tabela(resumo)}<h3>Emitidas por tipo</h3>{_tabela(p['por_tipo'])}"


def _secao_evacuacoes(r: dict[str, Any]) -> str:
    e = r["evacuacoes"]
    if not e["disponivel"]:
        return f"<h2>Evacuações</h2><p class=nota>{_e(e.get('motivo', ''))}</p>"
    if not e["itens"]:
        corpo = "<p>Nenhuma evacuação registrada no mês.</p>"
    else:
        def no_ponto(i: dict[str, Any]) -> str:
            chegadas = i["chegadas_ponto_de_encontro"]
            return "sem ponto de encontro" if chegadas is None else str(chegadas)

        linhas = "".join(
            f"<tr><td>nº {_e(i['numero'])}</td><td>{_e(_data_hora(i['inicio']))}</td><td>{_e(_duracao(i['duracao_s']))}</td>"
            f"<td>{_e(i['total_maximo_somado'])} somadas</td><td>{_e(no_ponto(i))}</td></tr>"
            for i in e["itens"])
        corpo = ("<table class=evac><tr><th>Evacuação</th><th>Início</th><th>Duração</th><th>Máx. somado</th>"
                 f"<th>Máx. no ponto de encontro</th></tr>{linhas}</table>")
    return f"<h2>Evacuações</h2>{corpo}<p class=nota>Atenção: {_e(e['aviso'])}.</p>"


def _data_hora(iso: str | None) -> str:
    try:
        return _aware(datetime.fromisoformat(str(iso))).astimezone().strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return "sem dado"


def _secao_cadeia(r: dict[str, Any]) -> str:
    c = r["cadeia_de_custodia"]
    if not c["disponivel"] and c.get("motivo"):
        texto = c["motivo"]
    elif not c["disponivel"]:
        texto = "A verificação não pôde ser feita agora."
    elif c["integra"]:
        texto = "Íntegra: nenhuma evidência alterada ou ausente na verificação feita ao gerar este relatório."
    else:
        texto = "NÃO íntegra: a verificação encontrou evidência alterada ou ausente. Peça a um Técnico para conferir a cadeia."
    return f"<h2>Cadeia de custódia</h2><p>{_e(texto)}</p>"


_CSS = """
 @font-face { font-family: "Geist"; src: url(/static/dist/fonts/geist-latin-wght-normal.woff2) format("woff2-variations");
   font-weight: 100 900; font-display: swap; }
 @page { size: A4; margin: 16mm; }
 body { font: 14px/1.5 "Geist", system-ui, sans-serif; color: #1A1A1C; background: #FFFFFF;
   max-width: 760px; margin: 32px auto; padding: 0 16px; }
 h1 { font-size: 28px; letter-spacing: -.02em; margin: 0 0 4px; }
 h2 { font-size: 17px; letter-spacing: -.01em; margin: 28px 0 8px; break-after: avoid; }
 h3 { font-size: 14px; margin: 16px 0 4px; break-after: avoid; }
 button { font: 500 14px "Geist", system-ui, sans-serif; height: 36px; padding: 0 16px; border-radius: 10px; border: 0;
   background: #0A66C2; color: #FFFFFF; cursor: pointer; }
 .sub { color: #5E5E64; } .kpis { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-top: 16px; }
 .kpi { border: 1px solid #E5E5EA; border-radius: 12px; padding: 12px; } .kpi b { display: block; font-size: 24px; }
 table { width: 100%; border-collapse: collapse; } td, th { padding: 6px 4px; border-bottom: 1px solid #E5E5EA; }
 th { text-align: left; font-weight: 600; font-size: 12px; color: #3A3A3F; }
 td:last-child { text-align: right; font-variant-numeric: tabular-nums; }
 table.evac td { text-align: left; font-size: 12px; }
 .nota { color: #5E5E64; font-size: 12px; margin-top: 8px; }
 .vazio { border: 1px dashed #C8C8CE; border-radius: 12px; padding: 12px; margin-top: 16px; color: #3A3A3F; }
 .fontes { margin-top: 32px; border-top: 2px solid #1A1A1C; padding-top: 8px; }
 .fontes li { margin-bottom: 4px; font-size: 12px; color: #3A3A3F; }
 @media print {
   .nao-imprimir { display: none; }
   body { margin: 0; max-width: none; padding: 0; font-size: 12px; }
   table, .kpi { break-inside: avoid; }
 }
"""


def renderizar_html(r: dict[str, Any]) -> str:
    """Página A4 imprimível. Tudo que vem de dado passa por `html.escape`."""
    a, i = r["alertas"], r["incidentes"]
    escopo = f"câmera #{r['camera_id']}" if r["camera_id"] is not None else "todas as câmeras"
    inicio = datetime.fromisoformat(r["periodo"]["inicio"]).strftime("%d/%m/%Y")
    fim = datetime.fromisoformat(r["periodo"]["fim"]).strftime("%d/%m/%Y")
    vazio = ("<p class=vazio>Nenhum dado registrado neste mês para este escopo. Se o sistema esteve desligado, "
             "o mês fica em branco: o relatório só conta o que foi gravado.</p>") if r["sem_dados"] else ""
    fontes = "".join(f"<li><b>{_e(nome)}</b>: {_e(texto)}</li>" for nome, texto in (
        ("Indicadores", r["fontes"]["indicadores"]), ("Alertas", r["fontes"]["alertas"]),
        ("Incidentes", r["fontes"]["incidentes"]), ("Intervenções", r["fontes"]["intervencoes"]),
        ("Permissões de Trabalho", r["fontes"]["permissoes"]), ("Evacuações", r["fontes"]["evacuacoes"]),
        ("Cadeia de custódia", r["fontes"]["cadeia_de_custodia"])))
    gerado = _e(_data_hora(r["gerado_em"]))
    simulados = (
        f'<p class="vazio">Este relatório inclui {_e(pluralizar(r["alertas_simulados"], "alerta simulado", "alertas simulados"))} '
        "(histórico de demonstração, sem vídeo).</p>"
    ) if r["alertas_simulados"] else ""
    avisados = pluralizar(a["colaboradores_avisados"], "colaborador avisado", "colaboradores avisados")
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<title>Relatório mensal para a CIPA · VisionEPI</title>
<style>{_CSS}</style></head><body>
<h1>Relatório mensal para a CIPA</h1>
<div class="sub">{_e(r['rotulo'].capitalize())} ({inicio} a {fim}), {_e(escopo)}</div>
<p class="nao-imprimir"><button onclick="window.print()">Imprimir / salvar PDF</button></p>
{vazio}{simulados}
<div class="kpis">
 <div class="kpi"><b>{_numero(a['validos'])}</b>alertas</div>
 <div class="kpi"><b>{_numero(i['total'])}</b>incidentes</div>
 <div class="kpi"><b>{_numero(r['indicadores']['minutos_conformes'])}</b>minutos conformes</div>
 <div class="kpi"><b>{_e(_duracao(i['mediana_ate_reconhecer_s']))}</b>até reconhecer (mediana)</div>
</div>
{_secao_indicadores(r)}
<h2>Alertas</h2>
<p>{_e(pluralizar(a['total'], 'alerta'))} no mês, dos quais {_e(pluralizar(a['falsos_positivos'], 'falso positivo', 'falsos positivos'))}
 e {_e(pluralizar(a['criticos'], 'crítico', 'críticos'))}; {_e(avisados)}.</p>
<h3>Por tipo</h3>{_tabela(a['por_regra'])}
<h3>Por câmera</h3>{_tabela(a['por_camera'])}
<h2>Incidentes</h2>
<p>{_e(pluralizar(i['total'], 'incidente'))} no mês, {_e(pluralizar(i['criticos'], 'crítico', 'críticos'))};
 {_e(pluralizar(i['reconhecimentos'], 'reconhecimento'))}, com mediana de {_e(_duracao(i['mediana_ate_reconhecer_s']))} até reconhecer.</p>
<h3>Por tipo</h3>{_tabela(i['por_regra'])}
<h3>Por zona</h3>{_tabela(i['por_zona'])}
<h3>Por câmera</h3>{_tabela(i['por_camera'])}
{_secao_intervencoes(r)}
{_secao_permissoes(r)}
{_secao_evacuacoes(r)}
{_secao_cadeia(r)}
<div class="fontes"><h2>Fonte de cada número</h2><ul>{fontes}</ul>
<p class="nota">Período: {inicio} a {fim}, hora do servidor. Gerado em {gerado}. Este relatório traz só totais por
 tipo, zona e câmera: não há nome, rótulo de rastreio nem identificação de quem operou o sistema. Nenhum texto foi gerado
 por modelo de linguagem.</p></div>
</body></html>"""
