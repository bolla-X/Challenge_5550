import os

# Afinidade de CPU ANTES de qualquer import pesado (ver app/utils/limites_de_cpu.py).
# Medido: aplicada só dentro do create_app, ela se perdia assim que a primeira
# câmera rodava um `cv2.resize` (o OpenCV desta máquina usa o Concurrency
# Runtime do Windows, inicializado nos imports com a máscara antiga).
if os.getenv("VISIONEPI_CPUS", "").strip():
    import psutil

    psutil.Process().cpu_affinity([int(c) for c in os.environ["VISIONEPI_CPUS"].split(",") if c.strip().isdigit()])

from app import create_app

app = create_app()
