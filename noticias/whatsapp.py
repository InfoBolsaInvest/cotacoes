"""Noticia do dia pronta para o grupo do WhatsApp.

Roda as 10h e as 18h (Brasilia). Pega as noticias que o radar achou desde o ultimo envio,
a IA escolhe a mais relevante para quem investe, le a materia e escreve um resumo curto.
Manda no Telegram do Douglas em duas mensagens: um aviso e o texto pronto para copiar.
"""
import datetime as dt, html, json, os, re, sys, time, urllib.parse

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import robo
from robo import http, log, db, ia, MODELO, sem_travessao

TESTE = os.environ.get("TESTE") == "1"
TZ = robo.TZ_BR
AGORA = dt.datetime.now(TZ)
JANELA_MAX_H = 16

def candidatas():
    estado = {} if TESTE else (db().collection("radar_whats").document("estado").get().to_dict() or {})
    desde = estado.get("ultimo_ts")
    limite = (AGORA - dt.timedelta(hours=JANELA_MAX_H)).isoformat(timespec="seconds")
    if not desde or desde < limite:
        desde = limite
    usados = set(estado.get("usados", []))
    docs = db().collection("radar").where("ts", ">=", desde).stream()
    itens = []
    for d in docs:
        x = d.to_dict()
        if not x.get("relevante") or x.get("oficial") or d.id in usados or not x.get("link"):
            continue
        x["id"] = d.id
        itens.append(x)
    return itens, estado

def texto_da_materia(url):
    """Trecho da materia para a IA resumir melhor. Se o portal bloquear, segue so com o trecho do feed."""
    try:
        corpo, _ = http(url, timeout=20)
        s = corpo.decode("utf-8", "replace")
        s = re.sub(r"(?is)<(script|style|nav|header|footer|aside)[^>]*>.*?</\1>", " ", s)
        pars = [re.sub(r"<[^>]+>", " ", p) for p in re.findall(r"(?is)<p[^>]*>(.*?)</p>", s)]
        pars = [re.sub(r"\s+", " ", html.unescape(p)).strip() for p in pars]
        pars = [p for p in pars if len(p) > 60]
        return " ".join(pars)[:4000]
    except Exception as e:
        log("nao li a materia:", e)
        return ""

ESCOLHA = """Voce escolhe a noticia do momento para um grupo de WhatsApp de investidores pessoa fisica brasileiros (acoes, FIIs, renda fixa, economia).
Escolha UMA noticia: a mais relevante e interessante para esse publico. Prefira fato concreto e de impacto (dividendos, resultados, juros, inflacao, OPA, calote, emissao, mudanca de regra, movimento forte de mercado). Evite opiniao, recomendacao de compra, lista de "melhores acoes" e assunto repetido.
Responda somente com JSON: {"id": "..."}"""

RESUMO = """Escreva o texto de uma noticia para um grupo de WhatsApp de investidores.
Formato exato, sem nada antes ou depois:
📰 *TITULO*

RESUMO

Regras:
- TITULO: curto e claro, com suas palavras, no maximo 90 caracteres, sem ponto final.
- RESUMO: 2 ou 3 frases curtas dizendo o que aconteceu e o numero principal. Linguagem simples. Escreva com suas palavras, nunca copie frases do texto.
- Tom neutro e informativo. Proibido opinar, recomendar compra ou venda, fazer pergunta ou usar frase de efeito.
- Nunca use travessao. Numeros no padrao brasileiro (R$ 1.250,00) e percentuais com 2 casas decimais (10,50%).
- Use somente informacao que esta no texto abaixo. Se faltar o numero, nao invente."""

def chama(prompt, max_tokens):
    msg = ia().messages.create(model=MODELO, max_tokens=max_tokens, messages=[{"role": "user", "content": prompt}])
    return "".join(getattr(b, "text", "") for b in msg.content if getattr(b, "type", "") == "text").strip()

def telegram(texto, preview=False):
    tok, chat = os.environ.get("TELEGRAM_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if TESTE or not tok or not chat:
        log("[telegram]\n" + texto + "\n")
        return
    http(f"https://api.telegram.org/bot{tok}/sendMessage",
         data=urllib.parse.urlencode({"chat_id": chat, "text": texto[:3900],
                                      "disable_web_page_preview": "false" if preview else "true"}).encode())
    time.sleep(1)

def main():
    itens, estado = candidatas()
    ult = estado.get("ultimo_ts")
    if ult and AGORA - dt.datetime.fromisoformat(ult) < dt.timedelta(hours=3) and os.environ.get("FORCAR") != "1":
        log("ja mandou ha menos de 3 horas (rodada repetida pelo agendamento); nada a fazer")
        return
    log(f"{len(itens)} noticias candidatas")
    if not itens:
        robo.telegram("ℹ️ Notícia pro WhatsApp: não achei notícia nova desde o último envio. Se isso se repetir, mande para o Claude.")
        return
    itens.sort(key=lambda x: x.get("ts", ""), reverse=True)
    itens = itens[:120]
    lista = "\n".join(json.dumps({"id": x["id"], "fonte": x.get("fonte"), "titulo": x.get("titulo"),
                                  "resumo": x.get("resumo") or x.get("resumo_fonte", "")[:150]}, ensure_ascii=False)
                      for x in itens)
    resp = chama(ESCOLHA + "\n\nNoticias:\n" + lista, 100)
    m = re.search(r'"id"\s*:\s*"([^"]+)"', resp)
    por_id = {x["id"]: x for x in itens}
    escolhida = por_id.get(m.group(1)) if m else None
    if escolhida is None:
        escolhida = itens[0]
        log("IA nao escolheu um id valido, usando a mais recente")
    materia = texto_da_materia(escolhida["link"])
    base = (f"Titulo original: {escolhida.get('titulo')}\nFonte: {escolhida.get('fonte')}\n"
            f"Trecho do feed: {escolhida.get('resumo_fonte', '')}\nTexto da materia: {materia or '(nao disponivel)'}")
    corpo = sem_travessao_linhas(chama(RESUMO + "\n\n" + base, 400))
    if not corpo.startswith("📰"):
        corpo = "📰 " + corpo
    pronto = corpo + "\n\n" + escolhida["link"]
    hora = "manhã" if AGORA.hour < 14 else "tarde"
    telegram(f"📲 Notícia da {hora} pro WhatsApp. É só copiar a próxima mensagem e colar no grupo 👇")
    telegram(pronto, preview=True)
    if not TESTE:
        usados = (estado.get("usados", []) + [escolhida["id"]])[-50:]
        db().collection("radar_whats").document("estado").set(
            {"ultimo_ts": AGORA.isoformat(timespec="seconds"), "usados": usados})
    log("enviada:", escolhida.get("titulo"))

def sem_travessao_linhas(t):
    """Tira travessao sem juntar as linhas (o texto tem quebra entre titulo e resumo)."""
    return "\n".join(sem_travessao(l) if l.strip() else "" for l in t.splitlines()).strip()

if __name__ == "__main__":
    main()
