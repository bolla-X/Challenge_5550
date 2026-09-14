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
TEXTO=["text","text-2","text-3","accent","danger","stop","ok"]
falhas=0
for nome,p in zip(("CLARO","ESCURO"), blocos(css)):
    for fundo in ("canvas","surface","sunken"):
        for fg in TEXTO:
            r=ratio(p[fg],p[fundo]); ok=r>=4.5; falhas+=0 if ok else 1
            print(f"{nome:6} {fg:>8} sobre {fundo:<8} {r:5.2f}:1 {'ok' if ok else 'FALHA'}")
    r=ratio(p["control-line"],p["canvas"]); ok=r>=3.0; falhas+=0 if ok else 1
    print(f"{nome:6} control-line sobre canvas {r:5.2f}:1 {'ok' if ok else 'FALHA'} (alvo 3:1)")
    r=ratio(p["on-accent"],p["accent"]); ok=r>=4.5; falhas+=0 if ok else 1
    print(f"{nome:6} on-accent sobre accent    {r:5.2f}:1 {'ok' if ok else 'FALHA'}")
print("falhas:", falhas); sys.exit(1 if falhas else 0)
