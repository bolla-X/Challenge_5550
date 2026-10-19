from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

# Token do celular-câmera e do controle do palco: `?t=<token>` na query e `/api/celular/<token>/quadro` no caminho.
_TOKEN_NA_QUERY = re.compile(r'([?&]t=)[^&\s"]+')
_TOKEN_NO_CAMINHO = re.compile(r'(/api/celular/)[^/\s"]+')


class FiltroDeTokensNoAcesso(logging.Filter):
    """Troca o token por `***` na linha de acesso do werkzeug (que loga a URL inteira em INFO).

    Nunca descarta a linha: só reescreve a mensagem já formatada.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        mensagem = record.getMessage()
        limpa = _TOKEN_NO_CAMINHO.sub(r"\g<1>***", _TOKEN_NA_QUERY.sub(r"\g<1>***", mensagem))
        if limpa != mensagem:
            record.msg, record.args = limpa, None
        return True


class JsonFormatter(logging.Formatter):
    RESERVED = {
        "name", "msg", "args", "levelname", "levelno", "pathname", "filename", "module",
        "exc_info", "exc_text", "stack_info", "lineno", "funcName", "created", "msecs",
        "relativeCreated", "thread", "threadName", "processName", "process", "message",
    }

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in self.RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: int = logging.INFO) -> None:
    acesso = logging.getLogger("werkzeug")
    if not any(isinstance(f, FiltroDeTokensNoAcesso) for f in acesso.filters):
        acesso.addFilter(FiltroDeTokensNoAcesso())
    root = logging.getLogger()
    if root.handlers:
        for handler in root.handlers:
            handler.setFormatter(JsonFormatter())
        root.setLevel(level)
        return

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(level)
