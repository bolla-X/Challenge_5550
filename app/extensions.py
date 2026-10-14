from flask_migrate import Migrate
from flask_socketio import SocketIO
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
migrate = Migrate()
socketio = SocketIO()


# SQLite com várias threads escrevendo (um worker por câmera, o gravador de
# evidências e as rotas HTTP): no modo de diário padrão um leitor bloqueia o
# escritor e qualquer espera passa dos 5 s do pysqlite — "database is locked"
# (visto no E2E da MISSÃO 2 com as 4 câmeras). WAL deixa leitura e escrita em
# paralelo; o busy_timeout dá folga para a escrita que espera a vez.
# Documentação: https://www.sqlite.org/wal.html e https://www.sqlite.org/pragma.html#pragma_busy_timeout
def _ajustar_sqlite(dbapi_connection, _connection_record) -> None:  # noqa: ANN001
    import sqlite3

    if not isinstance(dbapi_connection, sqlite3.Connection):
        return
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA busy_timeout=15000")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
    finally:
        cursor.close()


def _registrar_ajuste_do_sqlite() -> None:
    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    if not event.contains(Engine, "connect", _ajustar_sqlite):
        event.listen(Engine, "connect", _ajustar_sqlite)


_registrar_ajuste_do_sqlite()
