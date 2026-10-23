"""Dados SIMULADOS da Gestão de EPIs (Metaindústria), idempotentes e determinísticos (ES Sprint 4, F1.4 e F1.5).

Uso: `flask --app wsgi gestao semear` ou, automaticamente, `python run.py --demo`.

- tudo é fictício e MARCADO: `ficticio=True` nas quatro tabelas e `metadata_json = {"simulado": true, "seed_id": ...}`
  nos alertas. Nomes de pessoas são inventados e genéricos; fabricantes são "Fabricante Fictício A/B/C"; os CAs ficam na
  faixa 900000-999999 e não correspondem a CA real;
- idempotente pela chave natural (`matricula`, `ca`, `codigo`, `seed_id`): rodar de novo não duplica nada e não mexe no que já
  existe (nem no que a pessoa editou). Chave que já existe como registro REAL (`ficticio=False`) é ignorada, e nada do
  seed é pendurado nela;
- determinístico: `random.Random(5550)`, datas relativas a `hoje`. `montar_plano` é puro (sem banco): o teste confere as
  contagens sem gravar nada;
- NÃO toca o fluxo ao vivo: os alertas históricos nascem `resolved`, entre 2 e 30 dias atrás (nenhum nas últimas 24 h),
  inseridos direto na tabela (sem passar pelo estado de alertas, sem incidente, sem socket). O painel ao vivo não muda.
"""

# ruff: noqa: E501  (tabelas de dados: cada linha é um registro com texto corrido)
from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from app.extensions import db
from app.models import (
    OCORRENCIA_ABERTA,
    OCORRENCIA_EM_TRATAMENTO,
    OCORRENCIA_ENCERRADA,
    Alert,
    Camera,
    Colaborador,
    EntregaEpi,
    EpiCatalogo,
    Ocorrencia,
)
from app.services import gestao_epi as servico

SEMENTE = 5550
REGISTRADO_POR = "Dados simulados"

# setor -> funções (4 colaboradores por setor, 24 no total)
SETORES = {
    "Obra": ("Pedreiro", "Armador", "Servente", "Encarregado de obra"),
    "Expedição": ("Operador de empilhadeira", "Conferente", "Auxiliar de expedição", "Líder de expedição"),
    "Manutenção": ("Mecânico industrial", "Eletricista", "Soldador", "Técnico de manutenção"),
    "Portaria": ("Porteiro", "Controlador de acesso", "Vigia", "Auxiliar de portaria"),
    "Usinagem": ("Operador de CNC", "Torneiro mecânico", "Ajustador", "Fresador"),
    "Almoxarifado": ("Almoxarife", "Auxiliar de almoxarifado", "Conferente de estoque", "Controlador de materiais"),
}
NOMES = (
    "Ana", "Bruno", "Camila", "Diego", "Elaine", "Fábio", "Gabriela", "Henrique", "Isabela", "João", "Karina", "Leandro",
    "Marina", "Nelson", "Olívia", "Paulo", "Quitéria", "Rafael", "Simone", "Tiago", "Úrsula", "Vinícius", "Wanda", "Yuri",
    "Beatriz", "Caio", "Daniela", "Eduardo", "Fernanda", "Gustavo",
)
SOBRENOMES = (
    "Almeida", "Barros", "Cardoso", "Dias", "Esteves", "Farias", "Guedes", "Hoffmann", "Ibrahim", "Jesus", "Klein", "Lopes",
    "Moura", "Nogueira", "Oliveira", "Pacheco", "Queiroz", "Ramos", "Siqueira", "Teixeira", "Uchoa", "Vasconcelos", "Weber",
    "Xavier", "Azevedo", "Borges", "Campos", "Duarte", "Fontes", "Gomes",
)

# chave, nome, categoria, CA, fabricante, vida útil (dias), validade do CA em dias a partir de hoje
CATALOGO = (
    ("capacete", "Capacete de segurança com jugular", "helmet", "900101", "Fabricante Fictício A", 1095, 420),
    ("colete", "Colete refletivo", "vest", "900102", "Fabricante Fictício B", 365, 300),
    ("vaqueta", "Luva de vaqueta", "gloves", "900103", "Fabricante Fictício C", 90, -45),  # CA VENCIDO
    ("nitrilica", "Luva nitrílica", "gloves", "900104", "Fabricante Fictício A", 30, 210),
    ("oculos", "Óculos de proteção incolor", "glasses", "900105", "Fabricante Fictício B", 365, 25),  # a vencer
    ("pff2", "Respirador PFF2", "mask", "900106", "Fabricante Fictício C", 30, 12),  # a vencer
    ("calcado", "Calçado de segurança", "safety_shoe", "900107", "Fabricante Fictício A", 365, 365),
    ("plug", "Protetor auricular tipo plug", "ear_protection", "900108", "Fabricante Fictício B", 90, 150),
    ("concha", "Protetor auricular tipo concha", "ear_protection", "900109", "Fabricante Fictício C", 730, 600),
    ("cinto", "Cinto tipo paraquedista", "outro", "900110", "Fabricante Fictício A", 730, 480),
)

# (tipo, gravidade, setor, descrição, dias atrás, status, ação corretiva, liga a um colaborador do setor?)
OCORRENCIAS = (
    ("quase_acidente", "media", "Expedição", "Carga mal amarrada quase caiu da empilhadeira durante a movimentação no pátio.", 3, OCORRENCIA_ABERTA, "", False),
    ("condicao_insegura", "alta", "Obra", "Andaime sem guarda-corpo no segundo pavimento.", 2, OCORRENCIA_ABERTA, "", False),
    ("ato_inseguro", "media", "Usinagem", "Operação do torno sem óculos de proteção.", 5, OCORRENCIA_ABERTA, "", True),
    ("condicao_insegura", "baixa", "Almoxarifado", "Piso molhado na entrada do corredor B, sem sinalização.", 1, OCORRENCIA_ABERTA, "", False),
    ("acidente", "media", "Manutenção", "Corte superficial na mão durante a troca de uma peça; luva inadequada para a tarefa.", 9, OCORRENCIA_EM_TRATAMENTO, "Revisar o tipo de luva da tarefa e treinar a equipe.", True),
    ("quase_acidente", "alta", "Obra", "Queda de ferramenta de cerca de 3 metros de altura, sem ninguém embaixo.", 14, OCORRENCIA_EM_TRATAMENTO, "Instalar rodapé nos andaimes e revisar a amarração das ferramentas.", False),
    ("condicao_insegura", "media", "Usinagem", "Protetor da serra circular com folga no encaixe.", 20, OCORRENCIA_EM_TRATAMENTO, "Ajuste do protetor agendado com a manutenção.", False),
    ("acidente", "baixa", "Portaria", "Torção leve de tornozelo na rampa da portaria.", 27, OCORRENCIA_ENCERRADA, "Rampa nivelada e faixa antiderrapante instalada.", True),
    ("quase_acidente", "critica", "Expedição", "Empilhadeira passou perto de pedestre na faixa de travessia.", 33, OCORRENCIA_ENCERRADA, "Faixa repintada, espelho convexo instalado e conversa com os operadores.", False),
    ("ato_inseguro", "baixa", "Manutenção", "Uso de escada sem apoio de um colega.", 41, OCORRENCIA_ENCERRADA, "Reforço do procedimento de trabalho com escada.", True),
    ("condicao_insegura", "media", "Almoxarifado", "Prateleira com excesso de peso na parte superior.", 48, OCORRENCIA_ENCERRADA, "Carga redistribuída e limite de peso sinalizado.", False),
    ("acidente", "alta", "Obra", "Queda sem ferimento grave em escada provisória.", 55, OCORRENCIA_ENCERRADA, "Escada substituída e inspeção semanal incluída.", True),
    ("quase_acidente", "baixa", "Usinagem", "Cavaco quente projetado perto do rosto; o protetor facial estava em uso.", 63, OCORRENCIA_ENCERRADA, "Cortina de proteção instalada na máquina.", False),
    ("ato_inseguro", "media", "Expedição", "Operador sem capacete no pátio de carga.", 72, OCORRENCIA_ENCERRADA, "Orientação individual e reforço do uso de capacete no início do turno.", True),
    ("condicao_insegura", "alta", "Manutenção", "Cabo elétrico exposto no painel da bancada 2.", 84, OCORRENCIA_ENCERRADA, "Cabo substituído e painel inspecionado.", False),
)

# regra, recurso, mensagem, gravidade (as mesmas de app/services/risk_rules.py), peso no sorteio
REGRAS_DE_ALERTA = (
    ("missing_helmet", "helmet", "Sem capacete", "critical", 10),
    ("missing_vest", "vest", "Sem colete", "high", 9),
    ("missing_gloves", "gloves", "Sem luvas", "medium", 8),
    ("risk_area_presence", "risk_area", "Pessoa em área de risco", "high", 8),
    ("fall_detected", "falls", "Queda detectada", "critical", 2),
)
TOTAL_DE_ALERTAS = 40


@dataclass
class Plano:
    colaboradores: list[dict[str, Any]] = field(default_factory=list)
    epis: list[dict[str, Any]] = field(default_factory=list)
    entregas: list[dict[str, Any]] = field(default_factory=list)
    ocorrencias: list[dict[str, Any]] = field(default_factory=list)
    alertas: list[dict[str, Any]] = field(default_factory=list)


def _instante_local(dia: date, hora: int, minuto: int) -> datetime:
    return datetime.combine(dia, time(hora, minuto)).astimezone(timezone.utc)


MOTIVO_NA_OBSERVACAO = {"substituicao": "Troca por desgaste.", "dano": "Danificado em serviço.", "perda": "Extraviado."}
DIAS_DO_KIT_DE_ADMISSAO = 30  # `admissao` só vale para entrega até 30 dias depois da admissão


def montar_plano(dia: date, camera_ids: list[int | None]) -> Plano:
    """Tudo o que o seed cria, em dicionários, sem tocar no banco. Mesma entrada, mesma saída."""
    rng = random.Random(SEMENTE)
    plano = Plano()

    nomes = rng.sample(NOMES, 24)
    sobrenomes = rng.sample(SOBRENOMES, 24)
    recentes = set(rng.sample(range(24), 8))  # admitidos há menos de ~1 ano: o kit de admissão cai na janela de 12 meses
    admissoes: dict[str, date] = {}
    numero = 0
    for setor, funcoes in SETORES.items():
        for funcao in funcoes:
            matricula = f"MI-{numero + 1:04d}"
            admissoes[matricula] = dia - timedelta(days=rng.randint(60, 350) if numero in recentes else rng.randint(400, 3000))
            plano.colaboradores.append({
                "matricula": matricula, "nome": f"{nomes[numero]} {sobrenomes[numero]}", "setor": setor, "funcao": funcao,
                "admissao": admissoes[matricula],
            })
            numero += 1
    matriculas = list(admissoes)
    veteranos = [m for i, m in enumerate(matriculas) if i not in recentes]

    vida = {}
    for chave, nome, categoria, ca, fabricante, vida_util, validade in CATALOGO:
        vida[chave] = (ca, vida_util)
        plano.epis.append({"nome": nome, "categoria": categoria, "ca": ca, "fabricante": fabricante,
                           "vida_util_dias": vida_util, "validade_ca": dia + timedelta(days=validade)})

    def entrega(matricula: str, chave: str, dias_atras: int, motivo: str) -> dict[str, Any]:
        """Ninguém recebe EPI antes de ser admitido, e `admissao` só vale até 30 dias depois da admissão."""
        admissao = admissoes[matricula]
        entregue = max(dia - timedelta(days=dias_atras), admissao)
        if entregue == admissao:
            motivo = "admissao"
        elif motivo == "admissao" and (entregue - admissao).days > DIAS_DO_KIT_DE_ADMISSAO:
            motivo = rng.choice(("substituicao", "perda", "dano"))
        ca, vida_util = vida[chave]
        item = {
            "codigo": f"SEED-ENT-{len(plano.entregas) + 1:04d}", "matricula": matricula, "ca": ca,
            "quantidade": 2 if chave in ("vaqueta", "nitrilica") else 1, "entregue_em": entregue,
            "troca_prevista_em": entregue + timedelta(days=vida_util), "devolvido_em": None, "motivo": motivo,
            "observacao": MOTIVO_NA_OBSERVACAO.get(motivo, ""),
        }
        plano.entregas.append(item)
        return item

    # A: o EPI "de cabeça ou de pé" de cada colaborador (24). Quem entrou há menos de 1 ano recebeu o kit na admissão;
    # os veteranos receberam o kit antes da janela, então o que aparece aqui é uma reposição.
    kit = []
    for i, matricula in enumerate(matriculas):
        chave = rng.choice(("capacete", "calcado"))
        if i in recentes:
            kit.append(entrega(matricula, chave, (dia - admissoes[matricula]).days - rng.randint(0, 7), "admissao"))
        else:
            kit.append(entrega(matricula, chave, rng.randint(150, 360), "substituicao"))
    # B: um segundo EPI de longa vida para 12 colaboradores
    for matricula in rng.sample(matriculas, 12):
        entrega(matricula, rng.choice(("colete", "oculos", "concha")), rng.randint(100, 340), "admissao")
    # C: 6 substituições. A entrega antiga é devolvida e a nova nasce no dia da devolução.
    for antiga in rng.sample(kit, 6):
        antiga["devolvido_em"] = antiga["entregue_em"] + timedelta(days=rng.randint(40, 110))
        chave = "capacete" if antiga["ca"] == vida["capacete"][0] else "calcado"
        nova = entrega(antiga["matricula"], chave, (dia - antiga["devolvido_em"]).days, rng.choice(("substituicao", "dano", "perda")))
        nova["quantidade"] = antiga["quantidade"]
    # D: EPIs de vida curta (18): (chave, quantos, quantos já com a troca vencida). Só veteranos: as datas ficam depois da
    # admissão sem ajuste, e a contagem de trocas vencidas (8) não depende do sorteio.
    for chave, quantos, vencidos in (("vaqueta", 9, 5), ("nitrilica", 5, 2), ("pff2", 2, 1), ("plug", 2, 0)):
        vida_util = vida[chave][1]
        for i, matricula in enumerate(rng.sample(veteranos, quantos)):
            dias = vida_util + rng.randint(10, 60) if i < vencidos else rng.randint(2, vida_util - 5)
            entrega(matricula, chave, dias, "substituicao")

    por_setor: dict[str, list[str]] = {}
    for colaborador in plano.colaboradores:
        por_setor.setdefault(colaborador["setor"], []).append(colaborador["matricula"])
    for i, (tipo, gravidade, setor, descricao, dias_atras, status, acao, liga) in enumerate(OCORRENCIAS, start=1):
        ocorrida = _instante_local(dia - timedelta(days=dias_atras), rng.randint(7, 16), rng.randint(0, 59))
        plano.ocorrencias.append({
            "codigo": f"SEED-OCO-{i:04d}", "tipo": tipo, "gravidade": gravidade, "setor": setor, "descricao": descricao,
            "ocorrida_em": ocorrida, "status": status, "acao_corretiva": acao,
            "matricula": rng.choice(por_setor[setor]) if liga else None,
            "encerrada_em": ocorrida + timedelta(days=rng.randint(1, 8)) if status == OCORRENCIA_ENCERRADA else None,
        })

    pesos = [r[4] for r in REGRAS_DE_ALERTA]
    for i in range(1, TOTAL_DE_ALERTAS + 1):
        regra, recurso, texto, gravidade, _ = rng.choices(REGRAS_DE_ALERTA, weights=pesos)[0]
        criado = _instante_local(dia - timedelta(days=rng.randint(2, 30)), rng.randint(6, 17), rng.randint(0, 59))
        plano.alertas.append({
            "seed_id": f"SEED-ALR-{i:04d}", "camera_id": rng.choice(camera_ids) if camera_ids else None, "rule": regra,
            "severity": gravidade, "feature": recurso, "message": f"{texto} · Pessoa {rng.randint(1, 9)}",
            "criado_em": criado, "resolvido_em": criado + timedelta(minutes=rng.randint(2, 90)),
            "occurrences": rng.randint(1, 5),
        })
    return plano


def _resultado(total: int, criados: int, ignorados: int = 0) -> dict[str, int]:
    """`ignorados`: o seed não tocou porque a chave natural já existe como registro REAL (não fictício)."""
    return {"criados": criados, "existentes": total - criados - ignorados, "ignorados": ignorados}


def semear(*, dia: date | None = None) -> dict[str, dict[str, int]]:
    """Cria o que falta e devolve `{categoria: {"criados": n, "existentes": m, "ignorados": k}}`.

    Rodar de novo não duplica nada. Matrícula, CA ou código que já existe como registro REAL (`ficticio=False`) fica
    como está e nada do seed é pendurado nele (entrega, ocorrência): conta como `ignorados`.
    """
    dia = dia or servico.hoje()
    camera_ids = [c.id for c in Camera.query.order_by(Camera.id.asc()).all()]
    plano = montar_plano(dia, camera_ids)
    resultado: dict[str, dict[str, int]] = {}

    colaboradores: dict[str, Colaborador] = {}
    reais_c: set[str] = set()
    for c in Colaborador.query.filter(Colaborador.matricula.in_([p["matricula"] for p in plano.colaboradores])):
        if c.ficticio:
            colaboradores[c.matricula] = c
        else:
            reais_c.add(c.matricula)
    criados = 0
    for p in plano.colaboradores:
        if p["matricula"] not in colaboradores and p["matricula"] not in reais_c:
            colaboradores[p["matricula"]] = Colaborador(**p, ativo=True, ficticio=True)
            db.session.add(colaboradores[p["matricula"]])
            criados += 1
    resultado["colaboradores"] = _resultado(len(plano.colaboradores), criados, len(reais_c))

    epis: dict[str, EpiCatalogo] = {}
    reais_e: set[str] = set()
    for e in EpiCatalogo.query.filter(EpiCatalogo.ca.in_([p["ca"] for p in plano.epis])):
        if e.ficticio:
            epis[e.ca] = e
        else:
            reais_e.add(e.ca)
    criados = 0
    for p in plano.epis:
        if p["ca"] not in epis and p["ca"] not in reais_e:
            epis[p["ca"]] = EpiCatalogo(**p, ficticio=True)
            db.session.add(epis[p["ca"]])
            criados += 1
    resultado["epis"] = _resultado(len(plano.epis), criados, len(reais_e))

    codigos = dict(db.session.query(EntregaEpi.codigo, EntregaEpi.ficticio).filter(
        EntregaEpi.codigo.in_([p["codigo"] for p in plano.entregas])).all())
    criados = ignorados = 0
    for p in plano.entregas:
        if p["codigo"] in codigos:
            ignorados += 0 if codigos[p["codigo"]] else 1
        elif p["matricula"] in reais_c or p["ca"] in reais_e:
            ignorados += 1
        else:
            dados = {k: v for k, v in p.items() if k not in ("matricula", "ca")}
            db.session.add(EntregaEpi(
                **dados, colaborador=colaboradores[p["matricula"]], epi=epis[p["ca"]], ca_na_entrega=p["ca"],
                epi_nome_na_entrega=epis[p["ca"]].nome, registrado_por=REGISTRADO_POR, ficticio=True))
            criados += 1
    resultado["entregas"] = _resultado(len(plano.entregas), criados, ignorados)

    codigos = dict(db.session.query(Ocorrencia.codigo, Ocorrencia.ficticio).filter(
        Ocorrencia.codigo.in_([p["codigo"] for p in plano.ocorrencias])).all())
    criados = ignorados = 0
    for p in plano.ocorrencias:
        if p["codigo"] in codigos:
            ignorados += 0 if codigos[p["codigo"]] else 1
            continue
        dados = {k: v for k, v in p.items() if k != "matricula"}
        # colaborador REAL com a mesma matrícula: a ocorrência simulada nasce sem vínculo
        colaborador = colaboradores.get(p["matricula"]) if p["matricula"] else None
        db.session.add(Ocorrencia(**dados, colaborador=colaborador, registrada_por=REGISTRADO_POR, ficticio=True))
        criados += 1
    resultado["ocorrencias"] = _resultado(len(plano.ocorrencias), criados, ignorados)

    chave = Alert.metadata_json["seed_id"].as_string()
    existentes = {s for (s,) in db.session.query(chave).filter(chave.in_([p["seed_id"] for p in plano.alertas]))}
    for p in plano.alertas:
        if p["seed_id"] not in existentes:
            db.session.add(Alert(
                camera_id=p["camera_id"], rule=p["rule"], severity=p["severity"], message=p["message"], feature=p["feature"],
                status="resolved", metadata_json={"simulado": True, "seed_id": p["seed_id"]}, occurrences=p["occurrences"],
                created_at=p["criado_em"], first_seen_at=p["criado_em"], last_seen_at=p["resolvido_em"],
                resolved_at=p["resolvido_em"],
            ))
    resultado["alertas"] = _resultado(len(plano.alertas), len(plano.alertas) - len(existentes))

    db.session.commit()
    return resultado
