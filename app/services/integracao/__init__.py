"""Integração industrial do VisionEPI: OPC UA, MQTT, webhook e broker embutido.

Pacote isolado: nada aqui importa `MonitorService` nem o Flask. O monitor monta o
resumo por câmera, chama `estado_da_planta()` e entrega ao `GerenteDeIntegracao`,
que sobe só o que a configuração liga e nunca derruba o laço de captura.
"""
