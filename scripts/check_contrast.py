import re, sys, pathlib
css = pathlib.Path("frontend/src/styles/tokens.css").read_text(encoding="utf-8")
def blocos(c):
    claro = dict(re.findall(r'--([\w-]+)\s*:\s*(#[0-9A-Fa-f]{6})', c.split('@media')[0]))
    escuro = dict(re.findall(r'--([\w-]+)\s*:\s*(#[0-9A-Fa-f]{6})', c.split(':root[data-theme="dark"]')[1]))
    return claro, escuro
def lin(v): v/=255; return v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4
def lum(h):
    h=h.lstrip('#'); r,g,b=(int(h[i:i+2],16) for i in (0,2,4))
    return .2126*lin(r)+.7152*lin(g)+.0722*lin(b)
def ratio(a,b):
    la,lb=lum(a),lum(b); hi,lo=max(la,lb),min(la,lb); return (hi+.05)/(lo+.05)
def blocos_rgba(c):
    padrao=r'--([\w-]+)\s*:\s*rgba\((\d+),\s*(\d+),\s*(\d+),\s*([.\d]+)\)'
    claro={n:(int(r),int(g),int(b),float(a)) for n,r,g,b,a in re.findall(padrao, c.split('@media')[0])}
    escuro={n:(int(r),int(g),int(b),float(a)) for n,r,g,b,a in re.findall(padrao, c.split(':root[data-theme="dark"]')[1])}
    return claro, escuro
def compor(rgba, fundo_hex):
    """Cor rgba assentada sobre um fundo opaco: a*fg + (1-a)*bg por canal."""
    r,g,b,a=rgba; f=fundo_hex.lstrip('#'); br,bg_,bb=(int(f[i:i+2],16) for i in (0,2,4))
    return '#%02X%02X%02X' % (round(a*r+(1-a)*br), round(a*g+(1-a)*bg_), round(a*b+(1-a)*bb))
# Fundos rgba e o texto que de fato assenta em cada um. Sobre a linha tingida
# fica --text (título), --text-2 (contexto e horário) e --danger (ponto, chip).
# O overlay flutua sobre vídeo, então também sobre preto e branco puros.
COMPOSTOS=[
    ("tint-danger", ["canvas","surface"], ["text","text-2","danger"]),
    ("overlay", ["canvas","surface","#000000","#FFFFFF"], ["on-overlay"]),
    ("scrim", ["canvas","surface"], ["text"]),
]
TEXTO=["text","text-2","text-3","accent","danger","stop","ok"]
falhas=0
claro_hex, escuro_hex = blocos(css)
claro_rgba, escuro_rgba = blocos_rgba(css)
for nome,p in zip(("CLARO","ESCURO"), (claro_hex, escuro_hex)):
    rgba = claro_rgba if nome=="CLARO" else {**claro_rgba, **escuro_rgba}
    hexs = {**claro_hex, **p}  # --overlay e --on-overlay só existem no bloco claro
    for fundo_rgba, bases, textos in COMPOSTOS:
        for base in bases:
            base_hex = base if base.startswith('#') else hexs[base]
            composto = compor(rgba[fundo_rgba], base_hex)
            for fg in textos:
                r=ratio(hexs[fg],composto); ok=r>=4.5; falhas+=0 if ok else 1
                print(f"{nome:6} {fg:>10} sobre {fundo_rgba}+{base:<8} ({composto}) {r:5.2f}:1 {'ok' if ok else 'FALHA'}")
for nome,p in zip(("CLARO","ESCURO"), (claro_hex, escuro_hex)):
    for fundo in ("canvas","surface","sunken"):
        for fg in TEXTO:
            r=ratio(p[fg],p[fundo]); ok=r>=4.5; falhas+=0 if ok else 1
            print(f"{nome:6} {fg:>8} sobre {fundo:<8} {r:5.2f}:1 {'ok' if ok else 'FALHA'}")
    r=ratio(p["control-line"],p["canvas"]); ok=r>=3.0; falhas+=0 if ok else 1
    print(f"{nome:6} control-line sobre canvas {r:5.2f}:1 {'ok' if ok else 'FALHA'} (alvo 3:1)")
    r=ratio(p["on-accent"],p["accent"]); ok=r>=4.5; falhas+=0 if ok else 1
    print(f"{nome:6} on-accent sobre accent    {r:5.2f}:1 {'ok' if ok else 'FALHA'}")
print("falhas:", falhas); sys.exit(1 if falhas else 0)
