"""Permissão de Trabalho (PT) digital — MISSÃO 4, M5.

A câmera NÃO emite nem substitui a PT e NÃO substitui o vigia: ela confere, a
cada análise, três fatos que a PT promete e que o chão de fábrica esquece.

1. Entrou na zona controlada sem PT vigente (`sem_permissao_ativa`).
2. Há gente dentro e ninguém na área do vigia (`sem_vigia`).
3. Falta um EPI que a PT exige — SÓ dos EPIs que o modelo detecta; os demais
   aparecem no checklist como "verificação manual", nunca como checados.

Fonte da norma (lida em 17/10/2026, só o que está abaixo é afirmado):

- NR-33 (texto vigente, "nr-33-atualizada-2022-_retificada.pdf" no gov.br): vigia
  é o "trabalhador designado para permanecer fora do espaço confinado e que é
  responsável pelo acompanhamento, comunicação e ordem de abandono para os
  trabalhadores" (Glossário); 33.7.1 c) proíbe a entrada com "ausência de vigia
  durante a entrada, permanência e saída"; 33.3.4 c) o vigia permanece fora,
  junto à entrada; 33.3.4.1 a) o vigia pode ser "assistido por sistema de
  vigilância e comunicação eletrônicas"; 33.5.5 toda entrada é precedida de PET;
  33.5.12 a validade é limitada a uma jornada. EPI NÃO é campo mínimo da PET
  (só aparece no Anexo II, modelo informativo).
- NR-35 (altura, "nr-35-atualizada-2025-1.pdf"): 35.5.7 atividades não
  rotineiras são autorizadas por PT; 35.5.8.2 a validade é restrita ao
  turno/jornada.

O limite de 24 h por permissão é do SISTEMA (teto técnico), não uma citação da
norma; o aviso de "acima da jornada" usa `JORNADA_REFERENCIA_H`, ajustável.

Arquitetura (ciclo de vida da PT, "ler" ≠ "usar"):

- base única `query_permissoes`; invólucros `listar_gerenciamento_permissoes`
  (qualquer status — o histórico segue legível) e `listar_operacional_permissoes`
  (só o que pode ser USADO pelo avaliador: ativa e ainda não expirada);
- guarda de escrita `garantir_permissao_ativa`: encerrar/cancelar só vale para
  PT ativa (a API devolve 409 estável `permissao_nao_ativa`, mesmo se a tela falhar);
- `PermissaoDeTrabalho.vigente(agora)` é o ÚNICO predicado de "vale agora".
"""

from __future__ import annotations

import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from flask import current_app

from app.extensions import db
from app.models import (
    PERMISSAO_ATIVA,
    PERMISSAO_CANCELADA,
    PERMISSAO_ENCERRADA,
    PERMISSAO_TIPOS,
    Camera,
    PermissaoDeTrabalho,
    ZonaControlada,
    _aware,
    utc_now,
)
from app.repositories.event_repository import EventRepository
from app.services.aproximacao import ponto_no_poligono
from app.vision.person_compliance_matcher import PPE_KEYS, PPE_LABELS

# Todas as regras deste módulo usam a MESMA feature: não é uma chave do
# FeatureManager, então desligar "risk_area"/EPI na tela não resolve esses
# alertas por baixo dos panos, e o rótulo por pessoa no overlay não colide com
# o de `risk_area_presence`.
FEATURE = "permissao_trabalho"

DURACAO_MAX_H = 24
JORNADA_REFERENCIA_H = 8

URL_NR33 = (
    "https://www.gov.br/trabalho-e-emprego/pt-br/acesso-a-informacao/participacao-social/conselhos-e-orgaos-colegiados/"
    "comissao-tripartite-partitaria-permanente/arquivos/normas-regulamentadoras/nr-33-atualizada-2022-_retificada.pdf"
)
URL_NR35 = (
    "https://www.gov.br/trabalho-e-emprego/pt-br/acesso-a-informacao/participacao-social/conselhos-e-orgaos-colegiados/"
    "comissao-tripartite-partitaria-permanente/normas-regulamentadora/normas-regulamentadoras-vigentes/"
    "nr-35-atualizada-2025-1.pdf"
)

NORMAS: dict[str, dict[str, Any]] = {
    "espaco_confinado": {
        "codigo": "NR-33",
        "url": URL_NR33,
        "itens": [
            {
                "item": "Glossário (vigia)",
                "texto": "Vigia: trabalhador designado para permanecer fora do espaço confinado e que é responsável pelo "
                "acompanhamento, comunicação e ordem de abandono para os trabalhadores.",
            },
            {"item": "33.3.4 c)", "texto": "O vigia permanece fora do espaço confinado, junto à entrada."},
            {
                "item": "33.3.4.1 a)",
                "texto": "O vigia pode ser assistido por sistema de vigilância e comunicação eletrônicas. "
                "A câmera auxilia o vigia; não o substitui.",
            },
            {"item": "33.5.5", "texto": "Toda entrada é precedida de PET."},
            {"item": "33.5.12", "texto": "A validade da permissão é limitada a uma jornada."},
            {
                "item": "33.7.1 c)",
                "texto": "É proibida a entrada com ausência de vigia durante a entrada, permanência e saída.",
            },
            {
                "item": "Anexo II",
                "texto": "Modelo informativo de PET. EPI não é campo mínimo da PET; só aparece neste modelo.",
            },
        ],
    },
    "altura": {
        "codigo": "NR-35",
        "url": URL_NR35,
        "itens": [
            {"item": "35.5.7", "texto": "Atividades não rotineiras são autorizadas por Permissão de Trabalho."},
            {"item": "35.5.8.2", "texto": "A validade da permissão é restrita ao turno/jornada."},
        ],
    },
}

# Item da norma que limita a validade à jornada, por tipo (só onde há citação verificada).
_ITEM_VALIDADE = {"espaco_confinado": "NR-33, 33.5.12", "altura": "NR-35, 35.5.8.2"}

TTL_CACHE_S = 5.0


class PermissaoInvalida(ValueError):
    """Violação de regra de negócio com `code` estável (a API devolve 400/409 com ele)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# ============================================================ validação ====
def _instante(valor: Any, campo: str) -> datetime:
    if isinstance(valor, datetime):
        resultado = valor
    elif isinstance(valor, str) and valor.strip():
        try:
            resultado = datetime.fromisoformat(valor.strip())
        except ValueError as exc:
            raise PermissaoInvalida("campo_invalido", f"'{campo}' deve ser uma data/hora ISO-8601.") from exc
    else:
        raise PermissaoInvalida("campo_invalido", f"'{campo}' é obrigatório (data/hora ISO-8601).")
    # Sem fuso = UTC, como o resto do sistema grava.
    return resultado.astimezone(timezone.utc) if resultado.tzinfo else resultado.replace(tzinfo=timezone.utc)


def normalizar_poligono(raw: Any, campo: str) -> list[list[float]]:
    """Lista de [x, y] ou {x, y} (≥ 3 pontos) → [[x, y], ...] limitado a 0–1."""
    if not isinstance(raw, list) or len(raw) < 3:
        raise PermissaoInvalida("campo_invalido", f"'{campo}' deve conter pelo menos 3 pontos.")
    pontos: list[list[float]] = []
    for ponto in raw:
        if isinstance(ponto, dict):
            x, y = ponto.get("x"), ponto.get("y")
        elif isinstance(ponto, (list, tuple)) and len(ponto) >= 2:
            x, y = ponto[0], ponto[1]
        else:
            raise PermissaoInvalida("campo_invalido", f"cada ponto de '{campo}' deve conter x e y.")
        try:
            xf, yf = float(x), float(y)
        except (TypeError, ValueError) as exc:
            raise PermissaoInvalida("campo_invalido", f"cada ponto de '{campo}' deve conter x e y numéricos.") from exc
        pontos.append([round(max(0.0, min(1.0, xf)), 4), round(max(0.0, min(1.0, yf)), 4)])
    return pontos


def _texto(dados: dict, campo: str, limite: int) -> str:
    valor = str(dados.get(campo) or "").strip()
    if not valor:
        raise PermissaoInvalida("campo_invalido", f"'{campo}' é obrigatório.")
    return valor[:limite]


def validar_dados(dados: Any, agora: datetime) -> tuple[dict[str, Any], list[str]]:
    """Valida o corpo de uma emissão. Devolve (campos normalizados, avisos).

    Erro bloqueante levanta `PermissaoInvalida`; aviso não bloqueia (a PT
    acima da jornada pode ser legítima em obra, mas a norma limita a validade).
    """
    if not isinstance(dados, dict):
        raise PermissaoInvalida("payload_invalido", "Payload inválido: esperado um objeto JSON.")
    avisos: list[str] = []

    tipo = str(dados.get("tipo") or "").strip()
    if tipo not in PERMISSAO_TIPOS:
        raise PermissaoInvalida("campo_invalido", f"'tipo' deve ser um de {list(PERMISSAO_TIPOS)}.")
    try:
        camera_id = int(dados.get("camera_id"))
    except (TypeError, ValueError) as exc:
        raise PermissaoInvalida("campo_invalido", "'camera_id' deve ser um número inteiro.") from exc

    inicio = _instante(dados.get("inicio"), "inicio")
    fim = _instante(dados.get("fim"), "fim")
    if fim <= inicio:
        raise PermissaoInvalida("janela_invalida", "'fim' deve ser posterior a 'inicio'.")
    duracao = fim - inicio
    if duracao > timedelta(hours=DURACAO_MAX_H):
        raise PermissaoInvalida("duracao_excedida", f"A permissão não pode durar mais de {DURACAO_MAX_H} h (limite do sistema).")
    if fim <= agora:
        raise PermissaoInvalida("janela_invalida", "'fim' já passou: não se emite permissão já expirada.")
    if duracao > timedelta(hours=JORNADA_REFERENCIA_H):
        onde = _ITEM_VALIDADE.get(tipo)
        base = f" ({onde})" if onde else ""
        avisos.append(
            f"Validade de {duracao.total_seconds() / 3600:.1f} h acima da jornada de referência de {JORNADA_REFERENCIA_H} h: "
            f"a norma limita a validade da permissão a uma jornada{base}."
        )

    epis_brutos = dados.get("epis_exigidos", [])
    if not isinstance(epis_brutos, list) or any(not isinstance(e, str) for e in epis_brutos):
        raise PermissaoInvalida("campo_invalido", "'epis_exigidos' deve ser uma lista de chaves de EPI.")
    desconhecidos = sorted({e for e in epis_brutos if e not in PPE_KEYS})
    if desconhecidos:
        raise PermissaoInvalida("campo_invalido", f"EPIs desconhecidos: {desconhecidos}. Válidos: {list(PPE_KEYS)}.")
    epis = list(dict.fromkeys(epis_brutos))

    exige_vigia = dados.get("exige_vigia", False)
    if not isinstance(exige_vigia, bool):
        raise PermissaoInvalida("campo_invalido", "'exige_vigia' deve ser true ou false.")
    area_vigia = None
    if exige_vigia:
        if dados.get("area_vigia") in (None, []):
            raise PermissaoInvalida("area_vigia_obrigatoria", "'area_vigia' é obrigatória quando 'exige_vigia' é verdadeiro.")
        area_vigia = normalizar_poligono(dados.get("area_vigia"), "area_vigia")
    else:
        if dados.get("area_vigia") not in (None, []):
            avisos.append("'area_vigia' foi ignorada porque 'exige_vigia' é falso.")
        if tipo == "espaco_confinado":
            avisos.append(
                "Espaço confinado sem 'exige_vigia': a câmera não conferirá a presença do vigia "
                "(NR-33, 33.7.1 c: é proibida a entrada com ausência de vigia)."
            )

    campos = {
        "camera_id": camera_id,
        "tipo": tipo,
        "descricao": _texto(dados, "descricao", 500),
        "responsavel": _texto(dados, "responsavel", 120),
        "inicio": inicio,
        "fim": fim,
        "epis_exigidos": epis,
        "exige_vigia": exige_vigia,
        "area_vigia": area_vigia,
    }
    return campos, avisos


# ============================================================ consultas ====
def query_permissoes(*, camera_id: int | None = None, status: str | None = None, fim_apos: datetime | None = None):
    """Base única de consulta (filtros comuns + ordem). Não decide o que pode ser USADO: ver invólucros."""
    consulta = PermissaoDeTrabalho.query
    if camera_id is not None:
        consulta = consulta.filter(PermissaoDeTrabalho.camera_id == camera_id)
    if status is not None:
        consulta = consulta.filter(PermissaoDeTrabalho.status == status)
    if fim_apos is not None:
        consulta = consulta.filter(PermissaoDeTrabalho.fim > fim_apos)
    return consulta.order_by(PermissaoDeTrabalho.inicio.desc(), PermissaoDeTrabalho.id.desc())


def listar_gerenciamento_permissoes(*, camera_id: int | None = None, status: str | None = None, limite: int = 200):
    """Tela de gestão e histórico: qualquer status, inclusive encerradas/canceladas/expiradas."""
    return query_permissoes(camera_id=camera_id, status=status).limit(limite).all()


def listar_operacional_permissoes(camera_id: int, agora: datetime):
    """O que o avaliador pode USAR: ativas que ainda não expiraram (a janela fina é `vigente`)."""
    return query_permissoes(camera_id=camera_id, status=PERMISSAO_ATIVA, fim_apos=agora).all()


def garantir_permissao_ativa(permissao: PermissaoDeTrabalho) -> None:
    """Guarda de escrita: só PT ativa pode ser encerrada/cancelada (ler ≠ usar)."""
    if permissao.status != PERMISSAO_ATIVA:
        raise PermissaoInvalida("permissao_nao_ativa", f"A permissão {permissao.numero} já está {permissao.status}.")


# ======================================================= cache em memória ===
def _destacar(permissao: PermissaoDeTrabalho) -> PermissaoDeTrabalho:
    """Cópia TRANSIENTE (fora de qualquer sessão): segura para ler em outra thread sem expirar no commit."""
    colunas = {c.key: getattr(permissao, c.key) for c in PermissaoDeTrabalho.__table__.columns}
    colunas["inicio"], colunas["fim"] = _aware(colunas["inicio"]), _aware(colunas["fim"])
    return PermissaoDeTrabalho(**colunas)


class _CacheDePermissoes:
    """Cache curto por câmera: o loop de captura não consulta o banco por quadro.

    Guarda as PT candidatas (ativas, não expiradas na carga) e a marca da zona.
    A janela de horário é aplicada em memória a cada chamada, então a virada de
    "ainda não começou" para "vigente" e a expiração não dependem do TTL. O que
    o TTL cobre é escrita feita por OUTRO processo; no mesmo processo, criar,
    encerrar, cancelar e marcar a zona chamam `invalidar`. Thread-safe: o lock
    serializa leitura, carga e invalidação (a carga é uma consulta indexada).
    """

    def __init__(self, ttl_s: float = TTL_CACHE_S, relogio: Callable[[], float] = time.monotonic) -> None:
        self.ttl_s = ttl_s
        self.relogio = relogio
        self._lock = threading.Lock()
        self._permissoes: dict[int, tuple[float, datetime, list[PermissaoDeTrabalho]]] = {}
        self._zonas: dict[int, tuple[float, bool]] = {}

    def permissoes(self, camera_id: int, agora: datetime) -> list[PermissaoDeTrabalho]:
        with self._lock:
            entrada = self._permissoes.get(camera_id)
            # Relógio de consulta que VOLTOU (teste, replay) invalida: a carga só
            # trouxe PT com fim > agora da carga.
            if entrada is None or self.relogio() - entrada[0] > self.ttl_s or agora < entrada[1]:
                lista = [_destacar(p) for p in listar_operacional_permissoes(camera_id, agora)]
                entrada = (self.relogio(), agora, lista)
                self._permissoes[camera_id] = entrada
            return entrada[2]

    def zona_exige(self, camera_id: int) -> bool:
        with self._lock:
            entrada = self._zonas.get(camera_id)
            if entrada is None or self.relogio() - entrada[0] > self.ttl_s:
                zona = db.session.get(ZonaControlada, camera_id)
                entrada = (self.relogio(), bool(zona and zona.exige_permissao))
                self._zonas[camera_id] = entrada
            return entrada[1]

    def invalidar(self, camera_id: int | None = None) -> None:
        with self._lock:
            if camera_id is None:
                self._permissoes.clear()
                self._zonas.clear()
            else:
                self._permissoes.pop(camera_id, None)
                self._zonas.pop(camera_id, None)


_EXTENSAO = "permissoes_cache"
_CRIACAO = threading.Lock()


def _cache() -> _CacheDePermissoes:
    """Um cache por app Flask (a suíte cria vários apps no mesmo processo)."""
    extensoes = current_app.extensions
    cache = extensoes.get(_EXTENSAO)
    if cache is None:
        with _CRIACAO:
            cache = extensoes.setdefault(_EXTENSAO, _CacheDePermissoes())
    return cache


def invalidar_cache(camera_id: int | None = None) -> None:
    _cache().invalidar(camera_id)


def permissao_ativa(camera_id: int, agora: datetime) -> PermissaoDeTrabalho | None:
    """A PT que vale para a câmera em `agora`, ou None. Cópia desanexada (somente leitura).

    Com mais de uma vigente (sobreposição), vale a que começou por último.
    """
    agora = _aware(agora)
    vigentes = [p for p in _cache().permissoes(camera_id, agora) if p.vigente(agora)]
    return max(vigentes, key=lambda p: (_aware(p.inicio), p.id or 0), default=None)


def zona_exige_permissao(camera_id: int) -> bool:
    return _cache().zona_exige(camera_id)


# ============================================================== escritas ====
def _registrar_evento(tipo: str, mensagem: str, permissao: PermissaoDeTrabalho, por: str, extra: dict | None = None) -> None:
    EventRepository().create(
        event_type=tipo,
        message=mensagem,
        severity="info",
        subject=f"permissao:{permissao.numero}"[:120],
        camera_id=permissao.camera_id,
        metadata={"permissao_id": permissao.id, "numero": permissao.numero, "tipo": permissao.tipo, "por": por, **(extra or {})},
    )


def emitir_permissao(dados: Any, *, criada_por: str, agora: datetime | None = None) -> tuple[PermissaoDeTrabalho, list[str]]:
    """Valida, grava, registra o evento e invalida o cache. Levanta PermissaoInvalida / LookupError (câmera)."""
    agora = _aware(agora or utc_now())
    campos, avisos = validar_dados(dados, agora)
    if db.session.get(Camera, campos["camera_id"]) is None:
        raise LookupError("câmera não encontrada")
    permissao = PermissaoDeTrabalho(numero=f"tmp-{uuid.uuid4().hex}", criada_por=criada_por, criada_em=agora, **campos)
    db.session.add(permissao)
    db.session.flush()  # precisa do id para o número legível; commit é um só
    permissao.numero = f"PT-{agora.year}-{permissao.id:04d}"
    db.session.commit()
    invalidar_cache(permissao.camera_id)
    _registrar_evento(
        "permissao_emitida",
        f"Permissão de trabalho {permissao.numero} emitida ({permissao.tipo}): {permissao.descricao[:120]}",
        permissao,
        criada_por,
        {"inicio": campos["inicio"].isoformat(), "fim": campos["fim"].isoformat(), "responsavel": permissao.responsavel},
    )
    return permissao, avisos


def _finalizar(permissao_id: int, novo_status: str, *, por: str, agora: datetime | None) -> PermissaoDeTrabalho:
    permissao = db.session.get(PermissaoDeTrabalho, permissao_id)
    if permissao is None:
        raise LookupError("permissão não encontrada")
    garantir_permissao_ativa(permissao)
    permissao.status = novo_status
    permissao.encerrada_em = _aware(agora or utc_now())
    permissao.encerrada_por = por
    db.session.commit()
    invalidar_cache(permissao.camera_id)
    rotulo = "encerrada" if novo_status == PERMISSAO_ENCERRADA else "cancelada"
    _registrar_evento(f"permissao_{rotulo}", f"Permissão de trabalho {permissao.numero} {rotulo}", permissao, por)
    return permissao


def encerrar_permissao(permissao_id: int, *, por: str, agora: datetime | None = None) -> PermissaoDeTrabalho:
    return _finalizar(permissao_id, PERMISSAO_ENCERRADA, por=por, agora=agora)


def cancelar_permissao(permissao_id: int, *, por: str, agora: datetime | None = None) -> PermissaoDeTrabalho:
    return _finalizar(permissao_id, PERMISSAO_CANCELADA, por=por, agora=agora)


def obter_zona_controlada(camera_id: int) -> dict[str, Any]:
    """Estado da marca; câmera sem registro = não exige permissão (comportamento de sempre)."""
    zona = db.session.get(ZonaControlada, camera_id)
    return zona.to_dict() if zona is not None else {"camera_id": camera_id, "exige_permissao": False, "atualizada_em": None}


def definir_zona_controlada(camera_id: int, exige_permissao: bool, *, por: str, agora: datetime | None = None) -> dict[str, Any]:
    if db.session.get(Camera, camera_id) is None:
        raise LookupError("câmera não encontrada")
    zona = db.session.get(ZonaControlada, camera_id)
    if zona is None:
        zona = ZonaControlada(camera_id=camera_id)
        db.session.add(zona)
    zona.exige_permissao = bool(exige_permissao)
    zona.atualizada_em = _aware(agora or utc_now())
    db.session.commit()
    invalidar_cache(camera_id)
    EventRepository().create(
        event_type="zona_controlada_atualizada",
        message="Zona controlada ligada: exige permissão de trabalho" if zona.exige_permissao else "Zona controlada desligada",
        severity="info",
        subject=f"zona_controlada:{camera_id}",
        camera_id=camera_id,
        metadata={"exige_permissao": zona.exige_permissao, "por": por},
    )
    return zona.to_dict()


# ============================================================= detalhe =====
def checklist(permissao: PermissaoDeTrabalho, supported_ppe: set[str]) -> list[dict[str, str]]:
    """EPI a EPI: o que o modelo detecta é "automatica"; o resto é "manual" (nunca fingimos checagem)."""
    return [
        {
            "epi": epi,
            "rotulo": PPE_LABELS.get(epi, epi),
            "verificacao": "automatica" if epi in supported_ppe else "manual",
        }
        for epi in (permissao.epis_exigidos or [])
    ]


def norma_da_permissao(tipo: str) -> dict[str, Any] | None:
    """Citação da norma do tipo (NR-33 espaço confinado, NR-35 altura); `geral` não tem citação sustentada."""
    return NORMAS.get(tipo)


def detalhar_permissao(permissao: PermissaoDeTrabalho, supported_ppe: set[str], agora: datetime) -> dict[str, Any]:
    return permissao.to_dict(_aware(agora)) | {
        "checklist": checklist(permissao, supported_ppe),
        "norma": norma_da_permissao(permissao.tipo),
    }


# ============================================================ avaliador ====
def pe_normalizado(box: dict[str, Any], frame_shape: tuple[int, ...]) -> tuple[float, float]:
    """Centro da BASE da caixa (onde a pessoa pisa), normalizado 0–1 pelo tamanho do quadro."""
    altura, largura = frame_shape[:2]
    return ((box["x1"] + box["x2"]) / 2 / max(1, largura), box["y2"] / max(1, altura))


class AvaliadorDePermissao:
    """Confere a PT contra o que a câmera vê. Sem estado temporal.

    Devolve dicts `{rule, severity, message, feature, metadata}` prontos para
    `RuleAlert(**d)`. NÃO guarda histórico nem faz debounce: a confirmação
    (`create_after_frames`) e a histerese de resolução são do AlertStateService,
    que já recebe estes alertas como qualquer outro. As dependências são
    injetáveis (`buscar_permissao`, `zona_exige`) para testar sem banco.

    Regras (só avaliadas quando há alguém `risk_area.status == "inside"`):

    - sem PT vigente e a zona exige permissão → `sem_permissao_ativa` (high), por pessoa;
    - com PT vigente (a marca da zona não é exigida para isto — a PT existe para
      esta câmera): quem tem os pés na `area_vigia` é VIGIA e não conta como
      entrante, mesmo que as áreas se sobreponham; se há entrantes e ninguém na
      área do vigia → `sem_vigia` (critical), uma por PT (sujeito `permissao_<id>`);
    - com PT vigente: EPI exigido, detectável pelo modelo, `missing`/`incorrect`
      num entrante → `permissao_<epi>` (high). EPI não detectável não alerta
      (aparece como "manual" no checklist).

    Limites conhecidos: com PT sobreposta vale a que começou por último; quem
    está ao mesmo tempo na zona e na área do vigia é tratado como vigia.
    """

    def __init__(
        self,
        buscar_permissao: Callable[[int, datetime], PermissaoDeTrabalho | None] = permissao_ativa,
        zona_exige: Callable[[int], bool] = zona_exige_permissao,
    ) -> None:
        self._buscar_permissao = buscar_permissao
        self._zona_exige = zona_exige

    def avaliar(
        self,
        camera_id: int,
        people: list[dict[str, Any]],
        frame_shape: tuple[int, ...],
        agora: datetime,
        supported_ppe: set[str],
    ) -> list[dict[str, Any]]:
        dentro = [p for p in people if (p.get("risk_area") or {}).get("status") == "inside"]
        if not dentro:  # caminho quente: ninguém na zona, nem cache nem banco
            return []

        permissao = self._buscar_permissao(camera_id, agora)
        if permissao is None:
            if not self._zona_exige(camera_id):
                return []
            return [self._sem_permissao(pessoa) for pessoa in dentro]

        alertas: list[dict[str, Any]] = []
        entrantes = dentro
        if permissao.exige_vigia:
            vigias = [p for p in people if self._na_area_do_vigia(p, permissao, frame_shape)]
            ids_vigias = {p["id"] for p in vigias}
            entrantes = [p for p in dentro if p["id"] not in ids_vigias]
            if entrantes and not vigias:
                alertas.append(self._sem_vigia(permissao, entrantes))

        for pessoa in entrantes:
            alertas.extend(self._epis_faltando(permissao, pessoa, supported_ppe))
        return alertas

    @staticmethod
    def _na_area_do_vigia(pessoa: dict[str, Any], permissao: PermissaoDeTrabalho, frame_shape: tuple[int, ...]) -> bool:
        area = [(float(x), float(y)) for x, y in (permissao.area_vigia or [])]
        if len(area) < 3:
            return False
        return ponto_no_poligono(pe_normalizado(pessoa["box"], frame_shape), area)

    @staticmethod
    def _meta_da_pessoa(pessoa: dict[str, Any], permissao: PermissaoDeTrabalho | None = None) -> dict[str, Any]:
        meta = {"person_id": pessoa["id"], "person_label": pessoa["label"], "person_box": pessoa["box"]}
        if permissao is not None:
            meta |= {"permissao_id": permissao.id, "permissao_numero": permissao.numero}
        return meta

    def _sem_permissao(self, pessoa: dict[str, Any]) -> dict[str, Any]:
        return {
            "rule": "sem_permissao_ativa",
            "severity": "high",
            "message": f"Entrada na zona sem permissão ativa · {pessoa['label']}",
            "feature": FEATURE,
            "metadata": self._meta_da_pessoa(pessoa) | {"na_zona": True},
        }

    @staticmethod
    def _sem_vigia(permissao: PermissaoDeTrabalho, entrantes: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "rule": "sem_vigia",
            "severity": "critical",
            "message": "Pessoa no espaço confinado sem vigia na área de vigia",
            "feature": FEATURE,
            "metadata": {
                "subject": f"permissao_{permissao.id}",
                "permissao_id": permissao.id,
                "permissao_numero": permissao.numero,
                "pessoas_na_zona": [p["id"] for p in entrantes],
                "area_vigia": permissao.area_vigia,
            },
        }

    def _epis_faltando(self, permissao: PermissaoDeTrabalho, pessoa: dict[str, Any], supported_ppe: set[str]) -> list[dict[str, Any]]:
        alertas = []
        for epi in permissao.epis_exigidos or []:
            if epi not in supported_ppe:  # manual: nunca fingir checagem
                continue
            status = ((pessoa.get("ppe") or {}).get(epi) or {}).get("status")
            if status not in ("missing", "incorrect"):
                continue
            alertas.append(
                {
                    "rule": f"permissao_{epi}",
                    "severity": "high",
                    "message": f"Sem {PPE_LABELS.get(epi, epi)} exigido pela permissão nº {permissao.numero} · {pessoa['label']}",
                    "feature": FEATURE,
                    "metadata": self._meta_da_pessoa(pessoa, permissao) | {"epi": epi, "status": status},
                }
            )
        return alertas
