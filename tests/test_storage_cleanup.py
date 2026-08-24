"""A limpeza de startup não pode destruir evidência ainda referenciada.

`CLEANUP_ON_MONITOR_START=true` apagava `runtime/snapshots` inteiro a cada
start — inclusive os arquivos que alertas antigos apontam via `frame_ref`,
deixando `GET /alerts/<id>/evidence` com 404 permanente.
"""
from __future__ import annotations

import pytest
from app.services.storage_cleanup_service import StorageCleanupService


@pytest.fixture()
def workspace(tmp_path):
    snapshots = tmp_path / "runtime" / "snapshots"
    snapshots.mkdir(parents=True)
    (snapshots / "alert_1_evidencia.jpg").write_bytes(b"evidencia")
    (snapshots / "temporario.jpg").write_bytes(b"lixo")
    (snapshots / "subdir").mkdir()
    (snapshots / "subdir" / "outro.jpg").write_bytes(b"lixo")
    return tmp_path, snapshots


def _service(base, **kwargs):
    return StorageCleanupService(base_dir=base, directories=["runtime/snapshots"], **kwargs)


def test_preserva_snapshot_referenciado_por_alerta(workspace):
    base, snapshots = workspace
    service = _service(base, protected_files=lambda: {"alert_1_evidencia.jpg"})

    result = service.cleanup_startup_artifacts()

    assert (snapshots / "alert_1_evidencia.jpg").exists()
    assert not (snapshots / "temporario.jpg").exists()
    assert result["preserved_files"] == 1
    assert result["removed_files"] == 2  # temporario.jpg + subdir/outro.jpg


def test_sem_lista_de_protegidos_limpa_tudo(workspace):
    """Comportamento antigo preservado para quem não passa `protected_files`."""
    base, snapshots = workspace
    result = _service(base).cleanup_startup_artifacts()

    assert list(snapshots.iterdir()) == []
    assert result["removed_files"] == 3


def test_desabilitado_nao_apaga_nada(workspace):
    base, snapshots = workspace
    result = _service(base, enabled=False).cleanup_startup_artifacts()

    assert result["enabled"] is False
    assert len(list(snapshots.iterdir())) == 3


def test_falha_ao_consultar_protegidos_pula_a_limpeza(workspace):
    """Na dúvida, preserva: apagar é irreversível, deixar lixo não é."""
    base, snapshots = workspace

    def explode():
        raise RuntimeError("banco indisponível")

    result = _service(base, protected_files=explode).cleanup_startup_artifacts()

    assert result["skipped"] is True
    assert result["removed_files"] == 0
    assert len(list(snapshots.iterdir())) == 3


def test_nao_sai_do_base_dir(tmp_path):
    """Guarda contra `CLEANUP_DIRECTORIES=../..` no .env."""
    fora = tmp_path.parent / "nao-mexer"
    fora.mkdir(exist_ok=True)
    alvo = fora / "importante.txt"
    alvo.write_text("nao apague")

    base = tmp_path / "projeto"
    base.mkdir()
    service = StorageCleanupService(base_dir=base, directories=["../nao-mexer"])
    service.cleanup_startup_artifacts()

    assert alvo.exists()
