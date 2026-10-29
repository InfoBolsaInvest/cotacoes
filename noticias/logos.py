"""Baixa o logo oficial das acoes para logos/TICKER.svg (fonte: icons.brapi.dev).

Uso:
  python3 noticias/logos.py ITUB3 TAEE11          baixa so esses
  python3 noticias/logos.py --arquivo lista.txt   um ticker por linha (o robo de noticias gera logos_faltando.txt)
  python3 noticias/logos.py --forcar ITUB3        baixa de novo mesmo se ja existir

Regra da InfoBolsa: logo nunca fica em quadrado branco. Quando o logo vem com fundo claro,
o fundo passa a ser a cor principal da marca e o desenho fica branco.
Para um logo feito a mao, salve o SVG em logos/manual/TICKER.svg: ele tem prioridade e nunca e sobrescrito.
"""
import os, re, shutil, sys, urllib.request
from collections import Counter

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
PASTA = os.path.join(RAIZ, "logos")
MANUAL = os.path.join(PASTA, "manual")
FONTE = "https://icons.brapi.dev/icons/{}.svg"


def claro(hexcor):
    c = hexcor.lstrip("#")
    if len(c) == 3:
        c = "".join(x * 2 for x in c)
    if len(c) != 6:
        return False
    r, g, b = (int(c[i:i + 2], 16) for i in (0, 2, 4))
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255 > 0.85


def corrige_fundo(svg):
    """Fundo claro vira a cor da marca; o resto do desenho fica branco."""
    fundo = re.search(r'<(path|rect)[^>]*fill="(#[0-9A-Fa-f]{3,6})"[^>]*(d="M0 0h56v56H0z"|width="56")[^>]*/?>', svg)
    if not fundo or not claro(fundo.group(2)):
        return svg, False
    cores = [c for c in re.findall(r'(?:fill|stop-color)="(#[0-9A-Fa-f]{3,6})"', svg) if not claro(c)]
    marca = Counter(c.upper() for c in cores).most_common(1)[0][0] if cores else "#2F6F66"
    tag_fundo = fundo.group(0)
    corpo = svg.replace(tag_fundo, "\0FUNDO\0", 1)
    corpo = re.sub(r'fill="(?!none)[^"]*"', 'fill="#FFFFFF"', corpo)
    corpo = re.sub(r'stop-color="[^"]*"', 'stop-color="#FFFFFF"', corpo)
    # formas sem fill (preto por padrao) tambem ficam brancas
    corpo = re.sub(r'<(path|circle|rect|ellipse|polygon)(?![^>]*\bfill=)', r'<\1 fill="#FFFFFF"', corpo)
    corpo = corpo.replace("\0FUNDO\0", re.sub(r'fill="[^"]*"', f'fill="{marca}"', tag_fundo, count=1))
    return corpo, True


def baixa(ticker, forcar=False):
    t = ticker.strip().upper()
    if not t:
        return None
    destino = os.path.join(PASTA, t + ".svg")
    manual = os.path.join(MANUAL, t + ".svg")
    if os.path.exists(manual):
        shutil.copyfile(manual, destino)
        print(f"::notice::{t}: logo manual")
        return "manual"
    if os.path.exists(destino) and not forcar:
        return "ja tinha"
    try:
        req = urllib.request.Request(FONTE.format(t), headers={"User-Agent": "Mozilla/5.0 (InfoBolsa logos)"})
        svg = urllib.request.urlopen(req, timeout=30).read().decode("utf-8")
    except Exception as e:
        print(f"::warning::{t}: sem logo na fonte ({e}); o app mostra o quadrado colorido")
        return None
    if "<svg" not in svg:
        print(f"::warning::{t}: a fonte nao devolveu um SVG")
        return None
    svg, mudou = corrige_fundo(svg)
    os.makedirs(PASTA, exist_ok=True)
    open(destino, "w", encoding="utf-8").write(svg)
    print(f"::notice::{t}: logo salvo" + (" (fundo claro trocado pela cor da marca)" if mudou else ""))
    return "baixado"


if __name__ == "__main__":
    args = sys.argv[1:]
    forcar = "--forcar" in args
    args = [a for a in args if a != "--forcar"]
    tickers = []
    if args[:1] == ["--arquivo"]:
        if len(args) > 1 and os.path.exists(args[1]):
            tickers = open(args[1]).read().split()
    else:
        tickers = [x for a in args for x in a.replace(",", " ").split()]
    for t in tickers:
        baixa(t, forcar)
