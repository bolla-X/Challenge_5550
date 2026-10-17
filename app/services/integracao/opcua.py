"""Servidor OPC UA somente leitura com o estado da planta (CLP/SCADA leem, não escrevem).

O app roda em threads (Flask-SocketIO `threading`), não em asyncio. O asyncua é
asyncio puro, então o servidor vive num thread PRÓPRIO com event loop PRÓPRIO, e
`publicar()` só agenda uma corrotina nesse loop (`run_coroutine_threadsafe`):
quem chama (o laço de captura) nunca espera a rede.

Endpoint: `opc.tcp://<host>:<porta>/visionepi/`. Espaço de endereços (namespace
`urn:visionepi`, índice devolvido pelo servidor, normalmente 2). NodeIds são do
tipo string, estáveis para o engenheiro de automação amarrar no CLP:

    ns=<i>;s=Planta                                   objeto
    ns=<i>;s=Planta.PlantaEmAlarme                    Boolean
    ns=<i>;s=Planta.Torre                             String  "verde"|"amarelo"|"vermelho"
    ns=<i>;s=Cameras                                  objeto
    ns=<i>;s=Cameras.Camera_<id>                      objeto, um por câmera
    ns=<i>;s=Cameras.Camera_<id>.Estado               String  "ok"|"atencao"|"alarme"|"offline"
    ns=<i>;s=Cameras.Camera_<id>.Conformidade         Double  0..1 (NaN = sem dado)
    ns=<i>;s=Cameras.Camera_<id>.UltimoAlerta         String  mensagem ("" = nenhum)
    ns=<i>;s=Cameras.Camera_<id>.IncidentesAtivos     objeto
    ns=<i>;s=Cameras.Camera_<id>.IncidentesAtivos.<regra>   Int32, criado sob demanda

Câmera que some do estado fica com `Estado = "offline"` (nunca "ok" velho). Nó
de regra que zera continua existindo com valor 0 (nó não é apagado até reiniciar).

LIMITAÇÕES (decisão consciente):

- SEM segurança: política `None`, sem certificado, sem usuário/senha. É para rede
  de chão de fábrica ISOLADA (VLAN/DMZ industrial), nunca exposta à internet nem
  à rede corporativa. Quem precisar de Basic256Sha256 + certificado precisa de
  configuração adicional (fora do escopo desta entrega).
- Somente leitura: `WriteRequest` e `CallRequest` são negados no servidor
  (regra de permissão) e os nós têm AccessLevel só de leitura. Cliente também não
  altera o espaço de endereços (AddNodes é de admin).
"""

from __future__ import annotations

import asyncio
import logging
import math
import threading
from typing import Any

from asyncua import Server, ua
from asyncua.crypto.permission_rules import SimpleRoleRuleset

from ._erros import descrever_falha_de_bind, sondar_porta

logger = logging.getLogger(__name__)
# O asyncua loga cada sessão/subscription em INFO; em produção isso é ruído.
logging.getLogger("asyncua").setLevel(logging.WARNING)

CAMINHO_ENDPOINT = "/visionepi/"
_TIPOS_PROIBIDOS = (ua.ObjectIds.WriteRequest_Encoding_DefaultBinary, ua.ObjectIds.CallRequest_Encoding_DefaultBinary)


class _PermissaoSomenteLeitura(SimpleRoleRuleset):
    """O ruleset padrão deixa o papel User escrever. Aqui ninguém escreve nem chama método."""

    def __init__(self) -> None:
        super().__init__()
        negados = {ua.NodeId(tipo) for tipo in _TIPOS_PROIBIDOS}
        for papel, permitidos in self._permission_dict.items():
            self._permission_dict[papel] = permitidos - negados


def _nome_seguro(valor: Any) -> str:
    """'.' e '/' separam caminhos (NodeId textual e BrowsePath); troca por '_'."""
    return str(valor).strip().replace(".", "_").replace("/", "_") or "_"


def _igual(a: Any, b: Any) -> bool:
    if isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b):
        return True
    return a == b


class ServidorOPCUA:
    def __init__(
        self,
        porta: int = 4840,
        host: str = "127.0.0.1",
        namespace: str = "urn:visionepi",
        timeout_inicio_s: float = 45.0,
    ) -> None:
        self.porta = int(porta)
        self.host = host
        self.namespace = namespace
        self.timeout_inicio_s = timeout_inicio_s
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._pronto = threading.Event()
        self._erro: str | None = None
        self._no_ar = False
        # Tudo abaixo só é tocado dentro do loop do servidor.
        self._servidor: Server | None = None
        self._idx = 0
        self._tranca: asyncio.Lock | None = None
        self._pai_cameras: Any = None
        self._planta_em_alarme: Any = None
        self._torre: Any = None
        self._cameras: dict[str, dict[str, Any]] = {}
        self._ultimo: dict[Any, Any] = {}

    @property
    def endpoint(self) -> str:
        return f"opc.tcp://{self.host}:{self.porta}{CAMINHO_ENDPOINT}"

    @property
    def indice_namespace(self) -> int:
        """Índice do namespace `urn:visionepi` no servidor (vale após `iniciar()`)."""
        return self._idx

    def status(self) -> dict[str, Any]:
        return {"estado": "no_ar" if self._no_ar else "falhou", "endpoint": self.endpoint, "erro": self._erro}

    # -- ciclo de vida -------------------------------------------------------

    def iniciar(self) -> dict[str, Any]:
        """Sobe o servidor e devolve `status()`. Nunca lança: falha vira `erro` em pt-BR."""
        if self._thread is not None and self._thread.is_alive():
            return self.status()
        self._pronto.clear()
        self._erro = None
        self._thread = threading.Thread(target=self._executar, name="opcua-servidor", daemon=True)
        self._thread.start()
        if not self._pronto.wait(self.timeout_inicio_s) and self._erro is None:
            self._erro = f"O servidor OPC UA não respondeu em {self.timeout_inicio_s:g} s."
        if self._erro is not None:
            self.parar()
        return self.status()

    def parar(self) -> None:
        loop, thread = self._loop, self._thread
        if loop is not None and thread is not None and thread.is_alive():
            futuro = asyncio.run_coroutine_threadsafe(self._encerrar(), loop)
            try:
                futuro.result(timeout=5)
            except Exception:  # noqa: BLE001 - parar nunca lança; o thread sai mesmo assim
                logger.warning("opcua_parar_falhou", exc_info=True)
            loop.call_soon_threadsafe(loop.stop)
            thread.join(timeout=5)
        elif thread is not None:
            thread.join(timeout=5)
        self._no_ar = False
        self._thread = None
        self._loop = None

    def _executar(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        try:
            loop.run_until_complete(self._subir())
            self._no_ar = True
        except Exception as exc:  # noqa: BLE001 - qualquer falha de subida vira status
            self._erro = self._mensagem_de_erro(exc)
            logger.warning("opcua_nao_subiu", extra={"erro": str(exc)})
            self._loop = None
            self._pronto.set()
            loop.close()
            return
        self._pronto.set()
        try:
            loop.run_forever()
        finally:
            loop.close()

    def _mensagem_de_erro(self, exc: Exception) -> str:
        return descrever_falha_de_bind(exc, "OPC UA", self.host, self.porta)

    async def _subir(self) -> None:
        sondar_porta(self.host, self.porta)
        self._tranca = asyncio.Lock()
        servidor = Server()
        await servidor.init()
        servidor.set_endpoint(self.endpoint)
        servidor.set_server_name("VisionEPI")
        servidor.set_security_policy([ua.SecurityPolicyType.NoSecurity], permission_ruleset=_PermissaoSomenteLeitura())
        self._idx = await servidor.register_namespace(self.namespace)
        objetos = servidor.nodes.objects
        planta = await objetos.add_object(self._nodeid("Planta"), self._nome("Planta"))
        self._planta_em_alarme = await self._variavel(planta, "Planta", "PlantaEmAlarme", False, ua.VariantType.Boolean)
        self._torre = await self._variavel(planta, "Planta", "Torre", "verde", ua.VariantType.String)
        self._pai_cameras = await objetos.add_object(self._nodeid("Cameras"), self._nome("Cameras"))
        try:
            await servidor.start()
        except BaseException:
            # O InternalServer já subiu antes do bind falhar: desfaz para não vazar tarefa no loop.
            try:
                await servidor.stop()
            except Exception:  # noqa: BLE001
                logger.debug("opcua_stop_apos_falha", exc_info=True)
            raise
        self._servidor = servidor

    async def _encerrar(self) -> None:
        servidor, self._servidor = self._servidor, None
        if servidor is not None:
            await servidor.stop()

    # -- espaço de endereços -------------------------------------------------

    def _nodeid(self, caminho: str) -> ua.NodeId:
        return ua.NodeId(caminho, self._idx)

    def _nome(self, nome: str) -> ua.QualifiedName:
        return ua.QualifiedName(nome, self._idx)

    async def _variavel(self, pai: Any, prefixo: str, nome: str, inicial: Any, tipo: ua.VariantType) -> Any:
        no = await pai.add_variable(self._nodeid(f"{prefixo}.{nome}"), self._nome(nome), inicial, varianttype=tipo)
        await no.set_read_only()
        self._ultimo[no] = inicial
        return no

    async def _escrever(self, no: Any, valor: Any, tipo: ua.VariantType) -> None:
        # Só escreve se mudou: evita notificação de subscription à toa a cada publicação.
        if _igual(self._ultimo.get(no), valor):
            return
        await no.write_value(ua.Variant(valor, tipo))
        self._ultimo[no] = valor

    async def _camera(self, camera_id: str) -> dict[str, Any]:
        nos = self._cameras.get(camera_id)
        if nos is not None:
            return nos
        prefixo = f"Cameras.Camera_{camera_id}"
        objeto = await self._pai_cameras.add_object(self._nodeid(prefixo), self._nome(f"Camera_{camera_id}"))
        nos = {
            "Estado": await self._variavel(objeto, prefixo, "Estado", "offline", ua.VariantType.String),
            "Conformidade": await self._variavel(objeto, prefixo, "Conformidade", math.nan, ua.VariantType.Double),
            "UltimoAlerta": await self._variavel(objeto, prefixo, "UltimoAlerta", "", ua.VariantType.String),
            "incidentes_pai": await objeto.add_object(self._nodeid(f"{prefixo}.IncidentesAtivos"), self._nome("IncidentesAtivos")),
            "prefixo": prefixo,
            "regras": {},
        }
        self._cameras[camera_id] = nos
        return nos

    async def _regra(self, nos: dict[str, Any], regra: str) -> Any:
        no = nos["regras"].get(regra)
        if no is None:
            prefixo = f"{nos['prefixo']}.IncidentesAtivos"
            no = await self._variavel(nos["incidentes_pai"], prefixo, regra, 0, ua.VariantType.Int32)
            nos["regras"][regra] = no
        return no

    async def _aplicar(self, estado: dict[str, Any]) -> None:
        assert self._tranca is not None
        async with self._tranca:
            if self._servidor is None:
                return
            await self._escrever(self._planta_em_alarme, bool(estado.get("planta_em_alarme")), ua.VariantType.Boolean)
            await self._escrever(self._torre, str(estado.get("torre") or "verde"), ua.VariantType.String)
            vistas = set()
            for camera in estado.get("cameras") or []:
                camera_id = _nome_seguro(camera.get("id"))
                vistas.add(camera_id)
                nos = await self._camera(camera_id)
                await self._escrever(nos["Estado"], str(camera.get("estado") or "offline"), ua.VariantType.String)
                conformidade = camera.get("conformidade")
                valor = math.nan if conformidade is None else float(conformidade)
                await self._escrever(nos["Conformidade"], valor, ua.VariantType.Double)
                ultimo = camera.get("ultimo_alerta") or {}
                await self._escrever(nos["UltimoAlerta"], str(ultimo.get("mensagem") or ""), ua.VariantType.String)
                incidentes = {_nome_seguro(r): int(n) for r, n in (camera.get("incidentes_por_regra") or {}).items()}
                for regra in nos["regras"].keys() - incidentes.keys():
                    incidentes[regra] = 0
                for regra, quantidade in incidentes.items():
                    await self._escrever(await self._regra(nos, regra), quantidade, ua.VariantType.Int32)
            for camera_id, nos in self._cameras.items():
                if camera_id not in vistas:
                    await self._escrever(nos["Estado"], "offline", ua.VariantType.String)

    def publicar(self, estado_planta: dict[str, Any], aguardar_s: float | None = None) -> bool:
        """Agenda a publicação no loop do servidor; thread-safe e sem bloquear.

        Devolve False se o servidor não está no ar. Com `aguardar_s`, espera a
        aplicação terminar (útil em teste); falha na aplicação vira False + log.
        """
        loop = self._loop
        if loop is None or not self._no_ar:
            return False
        futuro = asyncio.run_coroutine_threadsafe(self._aplicar(estado_planta), loop)
        futuro.add_done_callback(self._registrar_falha)
        if aguardar_s is None:
            return True
        try:
            futuro.result(timeout=aguardar_s)
        except Exception:  # noqa: BLE001
            return False
        return True

    @staticmethod
    def _registrar_falha(futuro: Any) -> None:
        if not futuro.cancelled() and futuro.exception() is not None:
            logger.warning("opcua_publicar_falhou", extra={"erro": str(futuro.exception())})
