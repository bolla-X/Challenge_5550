"""Editor de regras sem código (MISSÃO 4, M4): formato, validação e avaliação.

Uma regra do editor é um JSON — condição (grupos E/OU aninháveis de blocos) e
ações — que o `RuleEngine` avalia DEPOIS das regras nativas, sobre os mesmos
fatos por pessoa que o matcher já produziu. Não existe segundo caminho de
execução: o avaliador devolve `RuleAlert`, e o AlertStateService (histerese,
incidente, escalonamento) trata o alerta como qualquer outro.

Formato (todas as chaves em pt-BR, como na API):

    {"id", "nome", "ativa", "origem": "pre_carregada"|"usuario",
     "regra_id", "camera_ids": [int] | null,
     "condicao": {"op": "E"|"OU", "itens": [bloco | grupo, ...]},
     "acoes": {"severidade", "mensagem", "fala", "integracao",
               "escalonamento": {"supervisor_s", "tv_s"}}}

Blocos: zona, epi, duracao, postura, aproximacao, horario, permissao_ativa.

Semântica de `duracao`: o bloco vale para o GRUPO que o contém — o resultado
dos demais itens do grupo (E ou OU) precisa ficar verdadeiro, sem interrupção,
por N segundos para a pessoa. Vários `duracao` no mesmo grupo: vale o maior.
Horário: janela [de, ate) em hora LOCAL do servidor; `de > ate` atravessa a
meia-noite.

Dois adaptadores montam os FATOS normalizados por pessoa: `fatos_ao_vivo`
(do que o RuleEngine tem) e `fatos_do_historico` (da trilha do simulador X2).
Bloco sem dado no histórico (postura, aproximação) torna a regra "não
simulável" em `testar_no_historico` — informado, nunca fingido.
"""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Callable, Iterable, Mapping

from app.services.risk_rules import PPE_INCORRECT_MESSAGES, PPE_RULES, RuleAlert
from app.services.simulador import Parametros, baldes, dentro, simular_com
from app.vision.person_compliance_matcher import PPE_KEYS

SEVERIDADES = ("critical", "high", "medium", "low")
ORIGENS = ("pre_carregada", "usuario")
OPERADORES = ("E", "OU")
EPI_ESTADOS = ("ausente", "presente", "incorreto")
POSTURAS = ("caida", "suspeita")
PROFUNDIDADE_MAXIMA = 3
BLOCOS_MAXIMOS = 20
DURACAO_MAXIMA_S = 3600

# Regras nativas que o editor sabe reescrever como definição, e a feature de
# cada uma (a mesma do RuleAlert nativo: o AlertStateService resolve o alerta
# quando a feature é desligada, e a chave do alerta inclui a feature).
REGRA_RISCO = "risk_area_presence"
REGRA_QUEDA = "fallen_person"
REGRA_POSTURA = "suspicious_posture"
FEATURE_DAS_NATIVAS: dict[str, str] = {
    **{f"missing_{chave}": chave for chave in PPE_RULES},
    **{f"incorrect_{chave}": chave for chave in PPE_RULES},
    REGRA_RISCO: "risk_area",
    REGRA_QUEDA: "falls",
    REGRA_POSTURA: "posture",
}
FEATURE_PADRAO = "regras"
SUFIXO_NEGATIVA = " (visto sem o EPI)"
SUJEITO_POSE_GLOBAL = "global_pose"

_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_HORA = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
_STATUS_DO_EPI = {"ok": "presente", "present": "presente", "detected": "presente", "missing": "ausente", "incorrect": "incorreto"}
_CODIGO_DA_TRILHA = {"m": "ausente", "i": "incorreto", "o": "presente"}

Fatos = dict[str, Any]


class RegraInvalida(ValueError):
    """Regra fora do formato. A mensagem já vem em pt-BR, com o caminho do campo."""


# --------------------------------------------------------------- formato ---
@dataclass(frozen=True)
class Bloco:
    tipo: str
    dados: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"tipo": self.tipo, **self.dados}


@dataclass(frozen=True)
class Grupo:
    op: str
    itens: tuple["Bloco | Grupo", ...]

    def to_dict(self) -> dict[str, Any]:
        return {"op": self.op, "itens": [item.to_dict() for item in self.itens]}


@dataclass(frozen=True)
class Acoes:
    severidade: str
    mensagem: str
    fala: bool = False
    integracao: bool = False
    supervisor_s: int | None = None
    tv_s: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "severidade": self.severidade,
            "mensagem": self.mensagem,
            "fala": self.fala,
            "integracao": self.integracao,
            "escalonamento": {"supervisor_s": self.supervisor_s, "tv_s": self.tv_s},
        }


@dataclass(frozen=True)
class Regra:
    id: str
    nome: str
    ativa: bool
    origem: str
    regra_id: str
    camera_ids: tuple[int, ...] | None
    condicao: Grupo
    acoes: Acoes

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "nome": self.nome,
            "ativa": self.ativa,
            "origem": self.origem,
            "regra_id": self.regra_id,
            "camera_ids": list(self.camera_ids) if self.camera_ids is not None else None,
            "condicao": self.condicao.to_dict(),
            "acoes": self.acoes.to_dict(),
        }


# ------------------------------------------------------------- validação ---
def _erro(caminho: str, mensagem: str):
    raise RegraInvalida(f"{caminho}: {mensagem}" if caminho else mensagem)


def _inteiro(valor: Any, caminho: str, minimo: int, maximo: int) -> int:
    if isinstance(valor, bool) or not isinstance(valor, int):
        _erro(caminho, "precisa ser um número inteiro")
    if not minimo <= valor <= maximo:
        _erro(caminho, f"precisa estar entre {minimo} e {maximo}")
    return valor


def _booleano(valor: Any, caminho: str) -> bool:
    if not isinstance(valor, bool):
        _erro(caminho, "precisa ser verdadeiro ou falso")
    return valor


def _texto(valor: Any, caminho: str, maximo: int) -> str:
    if not isinstance(valor, str) or not valor.strip():
        _erro(caminho, "texto obrigatório")
    texto = valor.strip()
    if len(texto) > maximo:
        _erro(caminho, f"no máximo {maximo} caracteres")
    return texto


def _escolha(valor: Any, caminho: str, validos: tuple[str, ...]) -> str:
    if valor not in validos:
        _erro(caminho, f"valor inválido {valor!r}; use um de: {', '.join(validos)}")
    return valor


def _minutos(hora: str) -> int:
    return int(hora[:2]) * 60 + int(hora[3:])


def _bloco_zona(dado: dict, caminho: str) -> dict[str, Any]:
    return {"dentro": _booleano(dado.get("dentro"), f"{caminho}.dentro")}


def _bloco_epi(dado: dict, caminho: str) -> dict[str, Any]:
    return {"epi": _escolha(dado.get("epi"), f"{caminho}.epi", PPE_KEYS),
            "estado": _escolha(dado.get("estado"), f"{caminho}.estado", EPI_ESTADOS)}


def _bloco_duracao(dado: dict, caminho: str) -> dict[str, Any]:
    return {"segundos": _inteiro(dado.get("segundos"), f"{caminho}.segundos", 1, DURACAO_MAXIMA_S)}


def _bloco_postura(dado: dict, caminho: str) -> dict[str, Any]:
    return {"postura": _escolha(dado.get("postura"), f"{caminho}.postura", POSTURAS)}


def _bloco_aproximacao(dado: dict, caminho: str) -> dict[str, Any]:
    return {}


def _bloco_horario(dado: dict, caminho: str) -> dict[str, Any]:
    janela = {}
    for campo in ("de", "ate"):
        valor = dado.get(campo)
        if not isinstance(valor, str) or not _HORA.match(valor):
            _erro(f"{caminho}.{campo}", "use o formato HH:MM (00:00 a 23:59)")
        janela[campo] = valor
    if janela["de"] == janela["ate"]:
        _erro(caminho, "'de' e 'ate' não podem ser iguais (a janela ficaria vazia)")
    return janela


def _bloco_permissao(dado: dict, caminho: str) -> dict[str, Any]:
    return {"ativa": _booleano(dado.get("ativa"), f"{caminho}.ativa")}


_BLOCOS = {
    "zona": _bloco_zona,
    "epi": _bloco_epi,
    "duracao": _bloco_duracao,
    "postura": _bloco_postura,
    "aproximacao": _bloco_aproximacao,
    "horario": _bloco_horario,
    "permissao_ativa": _bloco_permissao,
}


def _validar_grupo(dado: Any, caminho: str, profundidade: int, blocos: list[int]) -> Grupo:
    if not isinstance(dado, dict):
        _erro(caminho, "o grupo precisa ser um objeto com 'op' e 'itens'")
    if profundidade > PROFUNDIDADE_MAXIMA:
        _erro(caminho, f"grupos aninhados em até {PROFUNDIDADE_MAXIMA} níveis")
    op = _escolha(dado.get("op"), f"{caminho}.op", OPERADORES)
    itens_brutos = dado.get("itens")
    if not isinstance(itens_brutos, list) or not itens_brutos:
        _erro(f"{caminho}.itens", "o grupo precisa de pelo menos um item")
    itens: list[Bloco | Grupo] = []
    for indice, item in enumerate(itens_brutos):
        sub = f"{caminho}.itens[{indice}]"
        if not isinstance(item, dict):
            _erro(sub, "o item precisa ser um bloco ou um grupo")
        if "itens" in item or "op" in item:
            itens.append(_validar_grupo(item, sub, profundidade + 1, blocos))
            continue
        tipo = item.get("tipo")
        if tipo not in _BLOCOS:
            _erro(f"{sub}.tipo", f"bloco desconhecido {tipo!r}; use um de: {', '.join(_BLOCOS)}")
        blocos[0] += 1
        if blocos[0] > BLOCOS_MAXIMOS:
            _erro(sub, f"a regra aceita no máximo {BLOCOS_MAXIMOS} blocos")
        itens.append(Bloco(tipo, _BLOCOS[tipo](item, sub)))
    if all(isinstance(i, Bloco) and i.tipo == "duracao" for i in itens):
        _erro(f"{caminho}.itens", "o grupo só tem blocos de duração; adicione a condição que precisa durar")
    return Grupo(op, tuple(itens))


def validar(regra: Any) -> Regra:
    """Valida e normaliza uma regra (dict). Levanta `RegraInvalida` em pt-BR."""
    if not isinstance(regra, dict):
        _erro("", "a regra precisa ser um objeto JSON")
    id_ = regra.get("id")
    if not isinstance(id_, str) or not _ID.match(id_):
        _erro("id", "use de 1 a 64 caracteres: letras, números, '_' ou '-'")
    origem = _escolha(regra.get("origem", "usuario"), "origem", ORIGENS)
    if origem == "pre_carregada":
        regra_id = _escolha(regra.get("regra_id"), "regra_id", tuple(FEATURE_DAS_NATIVAS))
    else:
        regra_id = f"regra:{id_}"  # nunca colide com o nome de uma regra nativa
    camera_ids = regra.get("camera_ids")
    if camera_ids is not None:
        if not isinstance(camera_ids, list):
            _erro("camera_ids", "use uma lista de ids de câmera ou null (todas)")
        camera_ids = tuple(_inteiro(c, f"camera_ids[{i}]", 1, 2**31 - 1) for i, c in enumerate(camera_ids))
    acoes = regra.get("acoes")
    if not isinstance(acoes, dict):
        _erro("acoes", "obrigatório")
    escalonamento = acoes.get("escalonamento") or {}
    if not isinstance(escalonamento, dict):
        _erro("acoes.escalonamento", "precisa ser um objeto com 'supervisor_s' e 'tv_s'")
    segundos = {
        campo: None if escalonamento.get(campo) is None
        else _inteiro(escalonamento[campo], f"acoes.escalonamento.{campo}", 1, 86400)
        for campo in ("supervisor_s", "tv_s")
    }
    return Regra(
        id=id_,
        nome=_texto(regra.get("nome"), "nome", 120),
        ativa=_booleano(regra.get("ativa", False), "ativa"),
        origem=origem,
        regra_id=regra_id,
        camera_ids=camera_ids,
        condicao=_validar_grupo(regra.get("condicao"), "condicao", 1, [0]),
        acoes=Acoes(
            severidade=_escolha(acoes.get("severidade"), "acoes.severidade", SEVERIDADES),
            mensagem=_texto(acoes.get("mensagem"), "acoes.mensagem", 200),
            fala=_booleano(acoes.get("fala", False), "acoes.fala"),
            integracao=_booleano(acoes.get("integracao", False), "acoes.integracao"),
            supervisor_s=segundos["supervisor_s"],
            tv_s=segundos["tv_s"],
        ),
    )


# ------------------------------------------------------------ compilação ---
# Cada nó vira uma função (fatos, agora, estado) -> bool. `estado` é o dicionário
# de duração da (câmera, regra, pessoa): caminho do grupo -> desde quando o
# resultado dele está verdadeiro.
_No = Callable[[Fatos, float, dict[str, float]], bool]


def _na_janela(hora: str | None, de: str, ate: str) -> bool:
    if not hora or not _HORA.match(hora):
        return False
    h, inicio, fim = _minutos(hora), _minutos(de), _minutos(ate)
    return inicio <= h < fim if inicio < fim else (h >= inicio or h < fim)


def _compilar_bloco(bloco: Bloco) -> _No:
    d = bloco.dados
    if bloco.tipo == "zona":
        dentro_ = d["dentro"]
        return lambda f, a, e: bool(f.get("na_zona")) is dentro_
    if bloco.tipo == "epi":
        chave, estado = d["epi"], d["estado"]
        return lambda f, a, e: (f.get("epi") or {}).get(chave) == estado
    if bloco.tipo == "postura":
        postura = d["postura"]
        return lambda f, a, e: postura in (f.get("posturas") or ())
    if bloco.tipo == "aproximacao":
        return lambda f, a, e: bool(f.get("aproximando"))
    if bloco.tipo == "horario":
        de, ate = d["de"], d["ate"]
        return lambda f, a, e: _na_janela(f.get("hora"), de, ate)
    ativa = d["ativa"]  # permissao_ativa
    return lambda f, a, e: bool(f.get("permissao_ativa")) is ativa


def _compilar_grupo(grupo: Grupo, caminho: str) -> _No:
    filhos: list[_No] = []
    duracoes = [item.dados["segundos"] for item in grupo.itens if isinstance(item, Bloco) and item.tipo == "duracao"]
    for indice, item in enumerate(grupo.itens):
        if isinstance(item, Grupo):
            filhos.append(_compilar_grupo(item, f"{caminho}.{indice}"))
        elif item.tipo != "duracao":
            filhos.append(_compilar_bloco(item))
    juntar = all if grupo.op == "E" else any
    segundos = max(duracoes) if duracoes else None

    def avaliar(fatos: Fatos, agora: float, estado: dict[str, float]) -> bool:
        # Sem curto-circuito: o estado de duração dos subgrupos precisa avançar
        # (ou zerar) a cada avaliação, mesmo quando o resultado já está decidido.
        bruto = juntar([filho(fatos, agora, estado) for filho in filhos])
        if segundos is None:
            return bruto
        if not bruto:
            estado.pop(caminho, None)
            return False
        desde = estado.setdefault(caminho, agora)
        return agora - desde >= segundos

    return avaliar


def _blocos_da_regra(grupo: Grupo) -> list[Bloco]:
    saida: list[Bloco] = []
    for item in grupo.itens:
        saida.extend(_blocos_da_regra(item) if isinstance(item, Grupo) else [item])
    return saida


@dataclass(frozen=True)
class RegraCompilada:
    regra: Regra
    condicao: _No = field(repr=False, compare=False)
    tipos: frozenset[str]
    epis_violados: frozenset[str]  # EPIs citados como ausente/incorreto: base do sufixo "(visto sem o EPI)"
    epis: frozenset[str]
    feature: str

    def vale_para(self, camera_id: int | None) -> bool:
        return self.regra.camera_ids is None or camera_id in self.regra.camera_ids


def compilar(regra: Regra) -> RegraCompilada:
    blocos = _blocos_da_regra(regra.condicao)
    epis = frozenset(b.dados["epi"] for b in blocos if b.tipo == "epi")
    violados = frozenset(b.dados["epi"] for b in blocos if b.tipo == "epi" and b.dados["estado"] != "presente")
    if regra.origem == "pre_carregada":
        feature = FEATURE_DAS_NATIVAS[regra.regra_id]
    else:
        feature = next(iter(epis)) if len(epis) == 1 else FEATURE_PADRAO
    return RegraCompilada(
        regra=regra,
        condicao=_compilar_grupo(regra.condicao, "0"),
        tipos=frozenset(b.tipo for b in blocos),
        epis_violados=violados,
        epis=epis,
        feature=feature,
    )


# ------------------------------------------------------------- avaliação ---
class AvaliadorDeRegras:
    """Avalia as regras ativas sobre os fatos de cada pessoa, com estado de duração.

    `relogio` só é usado quando `avaliar` não recebe `agora` — em produção o
    RuleEngine passa o relógio dele; nos testes, um relógio falso.
    """

    def __init__(self, regras: Iterable[RegraCompilada], relogio: Callable[[], float] = time.monotonic) -> None:
        self.regras = tuple(regras)
        self.relogio = relogio
        self._estado: dict[tuple[int | None, str, Any], dict[str, float]] = {}
        self._lock = threading.Lock()

    def avaliar(
        self,
        fatos_por_pessoa: Iterable[Fatos] | Mapping[Any, Fatos],
        agora: float | None = None,
        camera_id: int | None = None,
    ) -> list[RuleAlert]:
        agora = self.relogio() if agora is None else agora
        fatos = list(fatos_por_pessoa.values() if isinstance(fatos_por_pessoa, Mapping) else fatos_por_pessoa)
        alertas: list[RuleAlert] = []
        vistos: set[tuple[int | None, str, Any]] = set()
        with self._lock:
            for compilada in self.regras:
                regra = compilada.regra
                if not regra.ativa or not compilada.vale_para(camera_id):
                    continue
                for fato in fatos:
                    chave = (camera_id, regra.id, fato.get("pessoa_id"))
                    vistos.add(chave)
                    if compilada.condicao(fato, agora, self._estado.setdefault(chave, {})):
                        alertas.append(self._alerta(compilada, fato))
            # Pessoa que saiu de cena (ou regra desligada) perde o relógio de duração.
            for chave in [k for k in self._estado if k[0] == camera_id and k not in vistos]:
                del self._estado[chave]
        return alertas

    @staticmethod
    def _alerta(compilada: RegraCompilada, fato: Fatos) -> RuleAlert:
        regra = compilada.regra
        rotulo = fato.get("rotulo") or ""
        evidencia = fato.get("evidencia") or {}
        sufixo = SUFIXO_NEGATIVA if any(evidencia.get(e) == "negativa_detectada" for e in compilada.epis_violados) else ""
        mensagem = f"{regra.acoes.mensagem}{' · ' + rotulo if rotulo else ''}{sufixo}"
        if fato.get("global"):
            sujeito = {"subject": SUJEITO_POSE_GLOBAL}
        else:
            sujeito = {"person_id": fato.get("pessoa_id"), "person_label": rotulo}
        return RuleAlert(
            rule=regra.regra_id,
            severity=regra.acoes.severidade,
            message=mensagem,
            feature=compilada.feature,
            metadata={
                **sujeito,
                "person_box": fato.get("box"),
                "na_zona": bool(fato.get("na_zona")),
                "regra_editor_id": regra.id,
                "acoes": regra.acoes.to_dict(),
            },
        )


# ---------------------------------------------------------------- fatos ---
def _estado_do_epi(status: str | None) -> str:
    return _STATUS_DO_EPI.get(str(status or ""), "nao_verificado")


def fatos_ao_vivo(
    people: list[dict[str, Any]],
    poses_por_pessoa: Mapping[str, Iterable[str]] | None,
    pre_alertas: list[dict[str, Any]] | None,
    agora_local: datetime,
    permissao_ativa: bool,
) -> list[Fatos]:
    """Fatos por pessoa a partir do estado que o RuleEngine já tem.

    `poses_por_pessoa`: id da pessoa -> {"caida", "suspeita"} (a chave
    "global_pose" é a pose sem caixa de pessoa). `pre_alertas`: avisos do
    EstimadorDeAproximacao (`track_id`). `agora_local`: hora do servidor.
    """
    hora = agora_local.strftime("%H:%M")
    poses = poses_por_pessoa or {}
    aproximando = {aviso.get("track_id") for aviso in pre_alertas or []}
    fatos: list[Fatos] = []
    for pessoa in people:
        ppe = pessoa.get("ppe") or {}
        fatos.append({
            "pessoa_id": pessoa["id"],
            "rotulo": pessoa["label"],
            "epi": {chave: _estado_do_epi((ppe.get(chave) or {}).get("status")) for chave in PPE_KEYS},
            "evidencia": {chave: (ppe.get(chave) or {}).get("evidence", "nao_detectado") for chave in PPE_KEYS},
            "na_zona": (pessoa.get("risk_area") or {}).get("status") == "inside",
            "posturas": set(poses.get(pessoa["id"], ())),
            "aproximando": pessoa.get("track_id") is not None and pessoa["track_id"] in aproximando,
            "hora": hora,
            "permissao_ativa": bool(permissao_ativa),
            "box": pessoa.get("box"),
        })
    if SUJEITO_POSE_GLOBAL in poses:
        # Sem caixa de pessoa a pose é uma só por quadro e não tem rótulo
        # (comportamento nativo: "Pessoa caída detectada", sem " · Pessoa N").
        fatos.append({
            "pessoa_id": SUJEITO_POSE_GLOBAL, "rotulo": "", "global": True, "epi": {}, "evidencia": {}, "na_zona": False,
            "posturas": set(poses[SUJEITO_POSE_GLOBAL]), "aproximando": False, "hora": hora,
            "permissao_ativa": bool(permissao_ativa), "box": None,
        })
    return fatos


def fatos_do_historico(
    registro: dict[str, Any], zona: Iterable[tuple[float, float]] | None = None, permissao_ativa: bool | None = None
) -> list[Fatos]:
    """Fatos por pessoa a partir de um registro de trilha (app/services/trilhas.py).

    A trilha guarda EPI, posição e instante — só. `zona`: polígono normalizado
    (sem ele `na_zona` não é conhecido); `permissao_ativa`: o chamador informa.
    Postura e aproximação não existem aqui: ver `motivo_nao_simulavel`.
    """
    poligono = tuple(tuple(p) for p in zona) if zona else None
    hora = datetime.fromtimestamp(float(registro["t"])).strftime("%H:%M")
    fatos: list[Fatos] = []
    for pessoa in registro.get("p") or []:
        pid, _pe_x, _pe_y, cx, cy, epis = pessoa
        fatos.append({
            "pessoa_id": pid,
            "rotulo": f"Pessoa {pid}",
            "epi": {chave: _CODIGO_DA_TRILHA.get(epis.get(chave), "nao_verificado") for chave in PPE_KEYS} if epis else {},
            "evidencia": {},
            "na_zona": bool(poligono) and dentro((cx, cy), poligono),  # type: ignore[arg-type]
            "posturas": set(),
            "aproximando": False,
            "hora": hora,
            "permissao_ativa": bool(permissao_ativa),
            "box": None,
        })
    return fatos


# ------------------------------------------------------- pré-carregadas ---
def _definicao_nativa(regra_id: str, nome: str, bloco: dict[str, Any], severidade: str) -> Regra:
    return validar({
        "id": f"pre_{regra_id}", "nome": nome, "ativa": False, "origem": "pre_carregada", "regra_id": regra_id,
        "camera_ids": None, "condicao": {"op": "E", "itens": [bloco]},
        "acoes": {"severidade": severidade, "mensagem": nome, "fala": False, "integracao": False,
                  "escalonamento": {"supervisor_s": None, "tv_s": None}},
    })


def regras_pre_carregadas() -> list[Regra]:
    """As regras nativas reescritas como definições do editor (mensagem e severidade idênticas).

    Nascem `ativa=False`: a nativa já roda; ativar a cópia do editor ao lado
    dela duplicaria o alerta. O uso esperado é DUPLICAR e editar.
    """
    regras: list[Regra] = []
    for chave, (mensagem, severidade) in PPE_RULES.items():
        regras.append(_definicao_nativa(f"missing_{chave}", mensagem, {"tipo": "epi", "epi": chave, "estado": "ausente"}, severidade))
        regras.append(_definicao_nativa(f"incorrect_{chave}", PPE_INCORRECT_MESSAGES[chave],
                                        {"tipo": "epi", "epi": chave, "estado": "incorreto"}, severidade))
    regras.append(_definicao_nativa(REGRA_RISCO, "Pessoa em área de risco", {"tipo": "zona", "dentro": True}, "high"))
    regras.append(_definicao_nativa(REGRA_QUEDA, "Pessoa caída detectada", {"tipo": "postura", "postura": "caida"}, "critical"))
    regras.append(_definicao_nativa(REGRA_POSTURA, "Postura suspeita detectada", {"tipo": "postura", "postura": "suspeita"}, "medium"))
    return regras


# ------------------------------------------------- testar no histórico ---
def motivo_nao_simulavel(
    compilada: RegraCompilada,
    registros: list[dict[str, Any]],
    zona: Iterable[tuple[float, float]] | None,
    permissao_ativa: bool | None,
) -> str | None:
    """Por que a regra não pode ser simulada com a trilha, ou None se pode."""
    faltando = []
    if "postura" in compilada.tipos:
        faltando.append("postura (a trilha não guarda pose)")
    if "aproximacao" in compilada.tipos:
        faltando.append("aproximação (a trilha não guarda a velocidade)")
    if "zona" in compilada.tipos and not zona:
        faltando.append("zona (a câmera não tem área de risco configurada)")
    if "permissao_ativa" in compilada.tipos and permissao_ativa is None:
        faltando.append("permissão ativa (a trilha não guarda o histórico de permissões)")
    if faltando:
        return "Sem dado no histórico para: " + "; ".join(faltando) + "."
    gravados = {chave for r in registros for pessoa in (r.get("p") or []) for chave in (pessoa[5] or {})}
    sem_dado = sorted(compilada.epis - gravados)
    if registros and sem_dado:
        return "Sem dado no histórico para o(s) EPI(s): " + ", ".join(sem_dado) + " (estavam desligados na gravação)."
    return None


def testar_no_historico(
    regra: Regra | dict[str, Any],
    registros: Iterable[dict[str, Any]],
    inicio: float,
    fim: float,
    *,
    zona: Iterable[tuple[float, float]] | None = None,
    permissao_ativa: bool | None = None,
    parametros: Parametros | None = None,
    balde_s: float | None = None,
) -> dict[str, Any]:
    """Quantas vezes a regra teria disparado sobre as trilhas gravadas.

    "Disparo" = alerta CRIADO depois da histerese do AlertStateService (a
    mesma de `simular`), um por pessoa e regra — o número comparável com os
    alertas reais da câmera. Ignora `ativa` e `camera_ids` da regra (o teste é
    da regra como está no editor, na câmera escolhida).
    """
    regra = validar(regra) if isinstance(regra, dict) else regra
    registros = list(registros)
    compilada = compilar(replace(regra, ativa=True, camera_ids=None))
    motivo = motivo_nao_simulavel(compilada, registros, zona, permissao_ativa)
    if motivo is not None:
        return {"simulavel": False, "motivo": motivo, "disparos": 0, "linha_do_tempo": [], "pessoas": 0}
    avaliador = AvaliadorDeRegras([compilada])

    def violacoes_do_registro(registro: dict[str, Any]) -> dict[tuple[str, str, Any], bool]:
        alertas = avaliador.avaliar(fatos_do_historico(registro, zona, permissao_ativa), float(registro["t"]), None)
        return {(a.rule, a.feature, a.metadata["person_id"]): bool(a.metadata["na_zona"]) for a in alertas}

    resultado = simular_com(registros, violacoes_do_registro, parametros or Parametros(epis=frozenset(), zona=None))
    balde = balde_s if balde_s is not None else max(10.0, (fim - inicio) / 60)
    return {
        "simulavel": True,
        "motivo": None,
        "disparos": len(resultado.alertas),
        "linha_do_tempo": baldes([a["t"] for a in resultado.alertas], inicio, fim, balde),
        "pessoas": resultado.pessoas,
        "incidentes": resultado.incidentes,
        "registros": resultado.registros,
        "balde_s": balde,
    }
