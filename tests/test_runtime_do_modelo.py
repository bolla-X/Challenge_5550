"""Escolha de runtime: só entra export aprovado, e sempre há volta ao PyTorch."""

from __future__ import annotations

import json

from app.vision.runtime_do_modelo import garantir_runtime, resolver_caminho


def _aprovar(raiz, modelo, chave, caminho_rel, concordancia=1.0):
    arquivo = raiz / "models" / "export" / "aprovados.json"
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    dados = json.loads(arquivo.read_text(encoding="utf-8")) if arquivo.exists() else {}
    dados.setdefault(modelo, {})[chave] = {"concordancia": concordancia, "caminho": caminho_rel}
    arquivo.write_text(json.dumps(dados), encoding="utf-8")
    alvo = raiz / caminho_rel
    alvo.parent.mkdir(parents=True, exist_ok=True)
    alvo.write_bytes(b"x")


def test_pytorch_pedido_e_o_pt(tmp_path):
    caminho, motivo = resolver_caminho(tmp_path, modelo="epi", peso_pt="models/x.pt", imgsz=640, pedido="pytorch", ordem="onnx")
    assert caminho == "models/x.pt"


def test_onnx_sem_aprovacao_cai_no_pt(tmp_path):
    caminho, motivo = resolver_caminho(tmp_path, modelo="epi", peso_pt="models/x.pt", imgsz=640, pedido="onnx", ordem="onnx")
    assert caminho == "models/x.pt"
    assert "nenhum" in motivo


def test_onnx_aprovado_e_existente_e_usado(tmp_path):
    _aprovar(tmp_path, "epi", "onnx-dyn:640", "models/export/a/a.onnx")
    caminho, motivo = resolver_caminho(tmp_path, modelo="epi", peso_pt="models/x.pt", imgsz=640, pedido="auto", ordem="onnx,pytorch")
    assert caminho.endswith("a.onnx")
    assert "aprovado" in motivo


def test_aprovacao_e_por_resolucao(tmp_path):
    """Aprovado a 640 não vale para 416: a concordância muda com a resolução."""
    _aprovar(tmp_path, "epi", "onnx-dyn:640", "models/export/a/a.onnx")
    caminho, _ = resolver_caminho(tmp_path, modelo="epi", peso_pt="models/x.pt", imgsz=416, pedido="onnx", ordem="onnx")
    assert caminho == "models/x.pt"


def test_auto_respeita_a_ordem(tmp_path):
    _aprovar(tmp_path, "epi", "onnx-dyn:640", "models/export/a/a.onnx")
    caminho, _ = resolver_caminho(tmp_path, modelo="epi", peso_pt="models/x.pt", imgsz=640, pedido="auto", ordem="pytorch,onnx")
    assert caminho == "models/x.pt"


class DetectorQueFalha:
    def __init__(self):
        self.model_path = "models/export/a/a.onnx"
        self.runtime = "onnx"
        self._last_diagnostics = None
        self._sessao_onnx_ajustada = True

    def detect_lote(self, frames):
        raise RuntimeError("onnxruntime.dll ausente")

    def diagnostics(self):
        return {}


def test_runtime_que_falha_no_teste_volta_ao_pt():
    det = DetectorQueFalha()
    ativo = garantir_runtime(det, "models/x.pt")
    assert ativo == "pytorch (fallback)"
    assert det.model_path == "models/x.pt"


def test_estatico_aprovado_vale_quando_nao_ha_dinamico(tmp_path):
    _aprovar(tmp_path, "pessoa", "onnx:640", "models/export/p/p.onnx", concordancia=0.98)
    caminho, motivo = resolver_caminho(tmp_path, modelo="pessoa", peso_pt="models/y.pt", imgsz=640, pedido="onnx", ordem="onnx")
    assert caminho.endswith("p.onnx")


def test_aquecer_modelos_infere_uma_vez_em_cada_e_tolera_falha():
    from app.vision.runtime_do_modelo import aquecer_modelos

    class Det:
        def __init__(self, caminho, falha=False):
            self.model_path, self.falha, self.chamadas = caminho, falha, 0

        def detect_lote(self, quadros):
            self.chamadas += 1
            assert quadros[0].shape == (540, 960, 3)
            if self.falha:
                raise RuntimeError("modelo ausente")
            return [[]]

    epi, pessoa, quebrado = Det("epi.onnx"), Det("pessoa.onnx"), Det("pose.pt", falha=True)
    tempos = aquecer_modelos([epi, pessoa, None, quebrado])

    assert (epi.chamadas, pessoa.chamadas, quebrado.chamadas) == (1, 1, 1)
    assert set(tempos) == {"epi.onnx", "pessoa.onnx"}, "falha não derruba o boot nem entra nos tempos"


def test_openvino_gpu_aprovado_devolve_dispositivo_e_precisao(tmp_path, monkeypatch):
    import app.vision.runtime_do_modelo as rt
    from app.vision.runtime_do_modelo import resolver

    monkeypatch.setattr(rt, "gpu_disponivel", lambda: True)

    pasta = tmp_path / "models" / "export" / "vyra_ppe_640_dyn" / "vyra_ppe_640_dyn_openvino_model"
    pasta.mkdir(parents=True)
    (tmp_path / "models" / "export" / "aprovados.json").write_text(json.dumps({"epi": {
        "openvino-dyn@gpu-fp16:640": {"concordancia": 0.99, "caminho": "models/export/vyra_ppe_640_dyn/vyra_ppe_640_dyn_openvino_model"},
        "onnx-dyn:640": {"concordancia": 1.0, "caminho": "models/export/nao-existe.onnx"},
    }}), encoding="utf-8")

    escolha = resolver(tmp_path, modelo="epi", peso_pt="vyra.pt", imgsz=640, pedido="auto", ordem="openvino-gpu,onnx,pytorch")

    assert escolha["caminho"] == str(pasta)
    assert (escolha["dispositivo"], escolha["precisao"]) == ("GPU", "fp16")
    sem_gpu = resolver(tmp_path, modelo="epi", peso_pt="vyra.pt", imgsz=640, pedido="auto", ordem="onnx,pytorch")
    assert sem_gpu["caminho"] == "vyra.pt" and sem_gpu["dispositivo"] is None, "onnx aprovado mas ausente → .pt"


def test_gpu_que_nao_compila_cai_para_cpu(tmp_path, monkeypatch):
    """Fallback garantido: o detector compila na CPU e diz isso no diagnóstico."""
    import sys
    import types

    from app.vision.yolo_ppe_detector import YoloPPEDetector

    pasta = tmp_path / "x_openvino_model"
    pasta.mkdir()
    (pasta / "x.xml").write_text("<net/>", encoding="utf-8")
    compilados = []

    class Modelo:
        def get_parameters(self):
            return [type("P", (), {"get_layout": lambda self: type("L", (), {"empty": False})()})()]

    propriedades = {}

    class Core:
        def read_model(self, model, weights):
            return Modelo()

        def set_property(self, valores):
            propriedades.update(valores)

        def compile_model(self, modelo, device_name, config):
            if device_name == "GPU":
                raise RuntimeError("GPU indisponível")
            compilados.append((device_name, config))
            return "compilado-cpu"

    falso = types.ModuleType("openvino")
    falso.Core = Core
    falso.Layout = lambda s: s
    monkeypatch.setitem(sys.modules, "openvino", falso)
    monkeypatch.setenv("OV_CACHE_DIR", str(tmp_path / "cache"))
    detector = YoloPPEDetector(model_path=str(pasta))
    detector.dispositivo_openvino = "GPU"
    backend = type("B", (), {})()
    detector._recompilar_openvino(backend)

    assert backend.ov_compiled_model == "compilado-cpu"
    assert compilados[0][0] == "CPU"
    assert detector.dispositivo_ativo == "CPU (fallback da GPU)"
    # O cache do OpenVINO vale para o Core inteiro (GPU e CPU), em OV_CACHE_DIR.
    assert propriedades["CACHE_DIR"] == str(tmp_path / "cache")


def test_sem_gpu_o_auto_pula_o_openvino_gpu(tmp_path, monkeypatch):
    import app.vision.runtime_do_modelo as rt

    (tmp_path / "models" / "export" / "ov_model").mkdir(parents=True)
    (tmp_path / "x.onnx").write_text("", encoding="utf-8")
    (tmp_path / "models" / "export" / "aprovados.json").write_text(json.dumps({"epi": {
        "openvino-dyn@gpu-fp32:640": {"concordancia": 1.0, "caminho": "models/export/ov_model"},
        "onnx-dyn:640": {"concordancia": 1.0, "caminho": str(tmp_path / "x.onnx")},
    }}), encoding="utf-8")
    monkeypatch.setattr(rt, "gpu_disponivel", lambda: False)
    escolha = rt.resolver(tmp_path, modelo="epi", peso_pt="vyra.pt", imgsz=640, pedido="auto", ordem="openvino-gpu,onnx,pytorch")
    assert escolha["caminho"] == str(tmp_path / "x.onnx")
    assert escolha["dispositivo"] is None
