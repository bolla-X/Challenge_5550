"""O serializer do backend devolve ISO sem fuso quando o banco é SQLite.

E por isso que frontend/src/utils/datas.ts (paraDate) acrescenta "Z" antes
do Date(): sem isso o navegador le o valor como horario local. Nao ha runner
de testes no frontend (package.json sem script de teste, sem vitest ou
jest), entao a premissa e conferida aqui, do lado que produz a string.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from app.extensions import db
from app.models import Alert
from app.repositories.alert_repository import AlertRepository

SEM_FUSO = re.compile(r"Z$|[+-]\d\d:\d\d$")


def test_alerta_lido_do_sqlite_sai_sem_fuso_e_e_utc(app):
    with app.app_context():
        alert = AlertRepository().create(rule="missing_helmet", severity="high", message="Sem capacete", feature="helmet", metadata={})
        alert_id = alert.id
        db.session.expunge_all()
        lido = db.session.get(Alert, alert_id).to_dict()

    for campo in ("created_at", "first_seen_at", "last_seen_at"):
        iso = lido[campo]
        # Naive: e exatamente o caso que paraDate cobre acrescentando "Z".
        assert not SEM_FUSO.search(iso), (campo, iso)
        # E o instante gravado e UTC: reler como UTC cai em "agora".
        reparsado = datetime.fromisoformat(iso).replace(tzinfo=timezone.utc)
        assert abs(reparsado - datetime.now(timezone.utc)) < timedelta(minutes=1), (campo, iso)
