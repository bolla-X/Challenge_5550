"""Relatório de turno (F9): números do turno, imprimíveis, sem depender de LLM.

`GET /api/relatorio/turno?horas=8[&camera_id=N]` — JSON agregado do banco.
`GET /relatorio/turno?horas=8` — a mesma coisa como página A4 para imprimir/PDF
(o navegador faz o PDF: Ctrl+P → Salvar como PDF; sem dependência nova).

Resumo em texto por LLM: OPCIONAL, assíncrono e rotulado. Só existe se a camada
LLM do projeto estiver ligada e com chave (no backend; nunca no navegador). O
texto vai marcado como "interpretação gerada" e o relatório não depende dele —
os números acima são os do banco.
"""

from __future__ import annotations

import re

import html
import threading
from collections import Counter, defaultdict
from datetime import timedelta
from typing import Any

from flask import Blueprint, Response, current_app, jsonify, request

from app.models import Alert, Camera, EventLog, utc_now
from app.services.nr6 import FONTE_NR6, mapear
from app.utils.auth import camera_scope, login_required

relatorio_bp = Blueprint("relatorio", __name__)

_resumos: dict[str, dict[str, Any]] = {}
_resumos_lock = threading.Lock()


def _naive(dt):
    return dt.replace(tzinfo=None) if dt is not None and dt.tzinfo is not None else dt


def montar_relatorio(horas: float, camera_id: int | None) -> dict[str, Any]:
    fim = utc_now()
    inicio = fim - timedelta(hours=horas)
    consulta = Alert.query.filter(Alert.created_at >= _naive(inicio))
    if camera_id is not None:
        consulta = consulta.filter(Alert.camera_id == camera_id)
    alertas = consulta.all()
    cameras = {c.id: c.name for c in Camera.query.all()}

    por_regra = Counter(re.split(r" [·—] ", a.message)[0] if a.message else a.rule for a in alertas)
    por_camera = Counter(cameras.get(a.camera_id, f"#{a.camera_id}") for a in alertas)
    por_hora: dict[str, int] = defaultdict(int)
    duracoes = []
    for a in alertas:
        if a.created_at:
            por_hora[_naive(a.created_at).strftime("%H:00")] += 1
        if a.resolved_at and a.created_at:
            duracoes.append((_naive(a.resolved_at) - _naive(a.created_at)).total_seconds())
    eventos = EventLog.query.filter(EventLog.created_at >= _naive(inicio))
    if camera_id is not None:
        eventos = eventos.filter(EventLog.camera_id == camera_id)
    eventos = eventos.all()
    tipos = Counter(e.event_type for e in eventos)
    duracoes.sort()
    return {
        "janela": {"inicio": _naive(inicio).isoformat(), "fim": _naive(fim).isoformat(), "horas": horas},
        "camera_id": camera_id,
        "alertas": {
            "total": len(alertas),
            "criticos": sum(1 for a in alertas if a.severity == "critical"),
            "ativos_agora": sum(1 for a in alertas if a.status == "active"),
            # Marcas gravadas na metadata do alerta (ver Alert.to_dict).
            "falsos_positivos": sum(1 for a in alertas if (a.metadata_json or {}).get("false_positive")),
            "reconhecidos": sum(1 for a in alertas if (a.metadata_json or {}).get("acknowledged")),
            "por_regra": dict(por_regra.most_common()),
            "por_camera": dict(por_camera.most_common()),
            "por_hora": dict(sorted(por_hora.items())),
            "duracao_mediana_s": duracoes[len(duracoes) // 2] if duracoes else None,
        },
        # G10: cada infração de EPI ligada ao item da NR-6 que o texto sustenta.
        # Falso positivo não é infração: fica fora.
        "nr6": {"fonte": FONTE_NR6, "linhas": mapear(Counter(
            a.rule for a in alertas if not (a.metadata_json or {}).get("false_positive")))},
        "eventos": {
            "pre_alertas_de_aproximacao": tipos.get("approach_risk_area", 0),
            "quedas_de_sinal": tipos.get("camera_disconnected", 0),
            "privacidade_desligada": sum(1 for e in eventos if e.event_type == "privacy_toggled"
                                         and not (e.metadata_json or {}).get("ativa", True)),
        },
    }


def _parametros():
    try:
        horas = max(0.5, min(72.0, float(request.args.get("horas", 8))))
    except ValueError:
        horas = 8.0
    escopo = camera_scope()
    camera_id = escopo if escopo is not None else request.args.get("camera_id", type=int)
    return horas, camera_id


@relatorio_bp.get("/api/relatorio/turno")
@login_required
def relatorio_json():
    horas, camera_id = _parametros()
    return jsonify(montar_relatorio(horas, camera_id))


_NOMES_EPI = {"helmet": "Capacete", "vest": "Colete", "gloves": "Luvas", "glasses": "Óculos", "mask": "Máscara",
              "safety_shoe": "Calçado", "ear_protection": "Protetor auricular"}


def _secao_nr6(nr6: dict[str, Any]) -> str:
    if not nr6["linhas"]:
        return ""
    linhas = []
    for linha in nr6["linhas"]:
        nome = html.escape(_NOMES_EPI.get(linha["epi"], linha["epi"]))
        if linha["itens"]:
            itens = "<br>".join(f"<b>{html.escape(i['item'])}</b>: “{html.escape(i['texto'])}”" for i in linha["itens"])
        else:
            itens = f"<i>sem item sustentado pelo texto</i>: {html.escape(linha['sem_item'] or '')}"
        linhas.append(f"<tr><td>{nome}</td><td class=nr6>{itens}</td><td>{linha['alertas']}</td></tr>")
    return (f"<h2>Infrações × NR-6</h2><table>{''.join(linhas)}</table>"
            f"<p class=nota>Trechos literais da NR-6 (Portaria MTE nº 57/2025): "
            f"<a href=\"{html.escape(nr6['fonte'])}\">texto no gov.br</a>. O PDF não substitui o publicado no DOU. "
            f"Indicação do requisito relacionado, não parecer jurídico.</p>")


@relatorio_bp.get("/relatorio/turno")
@login_required
def relatorio_html():
    horas, camera_id = _parametros()
    r = montar_relatorio(horas, camera_id)
    a, e = r["alertas"], r["eventos"]

    def linhas(d: dict) -> str:
        return "".join(f"<tr><td>{html.escape(str(k))}</td><td>{v}</td></tr>" for k, v in d.items()) or \
            "<tr><td colspan=2>nenhum</td></tr>"

    mediana = f"{a['duracao_mediana_s'] / 60:.1f} min" if a["duracao_mediana_s"] is not None else "sem dado"
    inicio_txt = html.escape(r["janela"]["inicio"][:16].replace("T", " "))
    fim_txt = html.escape(r["janela"]["fim"][:16].replace("T", " "))
    escopo_txt = f"câmera #{camera_id}" if camera_id else "todas as câmeras"
    corpo = f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<title>VisionEPI — Relatório de turno</title>
<style>
 @page {{ size: A4; margin: 16mm; }}
 body {{ font: 14px/1.45 -apple-system, "Segoe UI", system-ui, sans-serif; color: #1A1A1C; max-width: 760px; margin: 24px auto; }}
 h1 {{ font-size: 24px; margin: 0 0 4px; }} h2 {{ font-size: 16px; margin: 28px 0 8px; }}
 .sub {{ color: #5E5E64; }} .kpis {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-top: 16px; }}
 .kpi {{ border: 1px solid #E5E5EA; border-radius: 12px; padding: 12px; }} .kpi b {{ display: block; font-size: 24px; }}
 table {{ width: 100%; border-collapse: collapse; }} td {{ padding: 6px 4px; border-bottom: 1px solid #E5E5EA; }}
 td:last-child {{ text-align: right; font-variant-numeric: tabular-nums; }}
 .nota {{ color: #5E5E64; font-size: 12px; margin-top: 24px; }}
 td.nr6 {{ text-align: left; font-size: 12px; color: #3A3A3F; }}
 @media print {{ .nao-imprimir {{ display: none; }} }}
</style></head><body>
<h1>Relatório de turno</h1>
<div class="sub">{inicio_txt} a {fim_txt} (UTC) · {escopo_txt}</div>
<p class="nao-imprimir"><button onclick="window.print()">Imprimir / salvar PDF</button></p>
<div class="kpis">
 <div class="kpi"><b>{a['total']}</b>alertas</div><div class="kpi"><b>{a['criticos']}</b>críticos</div>
 <div class="kpi"><b>{a['falsos_positivos']}</b>falsos positivos</div><div class="kpi"><b>{mediana}</b>duração mediana</div>
</div>
<h2>Por tipo</h2><table>{linhas(a['por_regra'])}</table>
<h2>Por câmera</h2><table>{linhas(a['por_camera'])}</table>
<h2>Por hora</h2><table>{linhas(a['por_hora'])}</table>
{_secao_nr6(r["nr6"])}
<h2>Eventos</h2><table>{linhas({'Pré-alertas de aproximação (projeção cinemática)': e['pre_alertas_de_aproximacao'],
                                 'Quedas de sinal de câmera': e['quedas_de_sinal'],
                                 'Vezes que a privacidade foi desligada': e['privacidade_desligada']})}</table>
<p class="nota">Números calculados do banco do VisionEPI. Identificadores de pessoa são rastreios por posição,
 não identidades. Nenhum texto deste relatório foi gerado por modelo de linguagem.</p>
</body></html>"""
    return Response(corpo, mimetype="text/html")


@relatorio_bp.post("/api/relatorio/turno/resumo")
@login_required
def pedir_resumo():
    """Resumo opcional por LLM — assíncrono; GET na mesma rota busca o resultado."""
    horas, camera_id = _parametros()
    if not current_app.config.get("LLM_ENABLED") or not current_app.config.get("GEMINI_API_KEY"):
        return jsonify({"estado": "indisponivel", "motivo": "camada LLM desligada (LLM_ENABLED=false ou sem chave)"}), 200
    chave = f"{horas}:{camera_id}"
    dados = montar_relatorio(horas, camera_id)
    app = current_app._get_current_object()

    def gerar():
        try:
            from app.llm import ProvedorGemini

            provedor = ProvedorGemini(api_key=app.config.get("GEMINI_API_KEY"), modelo=app.config.get("GEMINI_MODEL"),
                                      timeout_s=float(app.config.get("LLM_TIMEOUT_S", 30)))
            texto = provedor.resumir(
                "Resuma em até 5 frases, em português, para um supervisor de segurança do trabalho, os números "
                "abaixo de um turno. Não invente nada que não esteja nos números.\n" + str(dados)
            )
            resultado = {"estado": "pronto", "texto": texto, "rotulo": "Interpretação gerada por modelo de linguagem"}
        except Exception as exc:  # noqa: BLE001  (LLM fora do ar não quebra o relatório)
            from app.llm import redigir_segredos

            resultado = {"estado": "falhou", "motivo": redigir_segredos(str(exc))}
        with _resumos_lock:
            _resumos[chave] = resultado

    with _resumos_lock:
        _resumos[chave] = {"estado": "pendente"}
    threading.Thread(target=gerar, daemon=True).start()
    return jsonify({"estado": "pendente"}), 202


@relatorio_bp.get("/api/relatorio/turno/resumo")
@login_required
def ver_resumo():
    horas, camera_id = _parametros()
    with _resumos_lock:
        return jsonify(_resumos.get(f"{horas}:{camera_id}", {"estado": "nao_pedido"}))
