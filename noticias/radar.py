"""Radar de noticias do mercado para o Telegram da InfoBolsa.

Roda no GitHub Actions a cada 30 minutos (07h as 22h de Brasilia).
1. Le feeds RSS de portais de investimentos e os documentos novos da CVM (fatos relevantes de todas as companhias).
2. Descarta o que ja foi enviado (Firestore, colecao "radar").
3. Haiku (barato) le so titulo e trecho: diz se e noticia de investimentos, quais ativos cita e se rende video.
4. Cruza os ativos com as carteiras dos clientes e manda cada noticia no Telegram, com destaque de quem tem o ativo.
5. Respeita teto de avisos e de gasto por dia e avisa se algo sair do esperado.

Segredos: ANTHROPIC_API_KEY, FIREBASE_SA, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID (os mesmos do robo de noticias).
"""
import datetime as dt, email.utils, html, json, os, re, sys, time, urllib.parse
import xml.etree.ElementTree as ET

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import robo
from robo import http, log, db, id_doc, sem_travessao, tickers_do_app, rad_documentos, ia, MODELO, \
    PRECO_ENTRADA, PRECO_SAIDA, RAD, data_br_para_iso, CLIENTES

TESTE = os.environ.get("TESTE") == "1"
MAX_DIA = int(os.environ.get("RADAR_MAX_DIA") or "50")
LIMITE_DIA_USD = float(os.environ.get("RADAR_LIMITE_USD") or "1.50")
JANELA_H = int(os.environ.get("RADAR_JANELA_H") or "20")
LOTE = 30
TZ = robo.TZ_BR
AGORA = dt.datetime.now(TZ)
HOJE = AGORA.strftime("%Y-%m-%d")

FEEDS = [
    ("InfoMoney", "https://www.infomoney.com.br/feed/"),
    ("InfoMoney Mercados", "https://www.infomoney.com.br/mercados/feed/"),
    ("InfoMoney FIIs", "https://www.infomoney.com.br/onde-investir/fundos-imobiliarios/feed/"),
    ("Money Times", "https://www.moneytimes.com.br/feed/"),
    ("Seu Dinheiro", "https://www.seudinheiro.com/feed/"),
    ("InvestNews", "https://investnews.com.br/feed/"),
    ("E-Investidor", "https://einvestidor.estadao.com.br/feed/"),
    ("Suno Notícias", "https://www.suno.com.br/noticias/feed/"),
    ("Brazil Journal", "https://braziljournal.com/feed/"),
    ("Exame Invest", "https://exame.com/invest/feed/"),
    ("Valor Investe", "https://valorinveste.globo.com/rss/valor-investe/"),
    ("InfoMoney Internacional", "https://www.infomoney.com.br/mercados/internacional/feed/"),
]

# ---------------------------------------------------------------- leitura dos feeds
def le_feed(nome, url):
    corpo, _ = http(url, timeout=30)
    raiz = ET.fromstring(corpo)
    itens = []
    for it in raiz.iter("item"):
        titulo = html.unescape((it.findtext("title") or "").strip())
        link = (it.findtext("link") or "").strip()
        desc = re.sub(r"<[^>]+>", " ", html.unescape(it.findtext("description") or ""))
        desc = re.sub(r"\s+", " ", desc).strip()[:300]
        quando = None
        pub = it.findtext("pubDate")
        if pub:
            try:
                quando = email.utils.parsedate_to_datetime(pub).astimezone(TZ)
            except Exception:
                quando = None
        if titulo and link:
            itens.append({"fonte": nome, "titulo": titulo, "link": link, "resumo_fonte": desc, "quando": quando})
    return itens

def coleta_feeds(falhas):
    todos = []
    for nome, url in FEEDS:
        try:
            itens = le_feed(nome, url)
            if not itens:
                raise ValueError("feed sem itens")
            todos += itens
        except Exception as e:
            falhas.append(f"{nome}: {str(e)[:80]}")
    return todos

def coleta_cvm(falhas):
    """Fatos relevantes e comunicados de todas as companhias abertas (sem IA na busca)."""
    itens = []
    try:
        desde = (AGORA - dt.timedelta(days=1)).strftime("%Y-%m-%d")
        for d in rad_documentos(desde):
            if d["categoria"] != "Fato Relevante":
                continue
            titulo = f"{d['empresa']}: fato relevante" + (f", {d['assunto']}" if d["assunto"] else "")
            quando = None
            try:
                quando = dt.datetime.fromisoformat(d["entrega"]).replace(tzinfo=TZ) if d["entrega"] else None
            except Exception:
                pass
            itens.append({"fonte": "CVM", "titulo": titulo[:250],
                          "link": RAD + "frmExibirArquivoIPEExterno.aspx?NumeroProtocoloEntrega=" + d["protocolo"],
                          "resumo_fonte": "", "quando": quando, "oficial": True})
    except Exception as e:
        falhas.append(f"CVM: {str(e)[:80]}")
    return itens

# ---------------------------------------------------------------- carteiras
def mapa_clientes(falhas):
    por_ativo = {}
    for cli, url in CLIENTES.items():
        try:
            for t in tickers_do_app(url):
                por_ativo.setdefault(t, set()).add(cli)
        except Exception as e:
            falhas.append(f"carteira {cli}: {str(e)[:80]}")
    return por_ativo

def nomes_dos_ativos():
    try:
        cad = json.load(open(os.path.join(AQUI, "ativos.json"), encoding="utf-8"))
    except Exception:
        return {}
    return {t: v.get("nome", "") for t, v in cad.items() if not t.startswith("_") and isinstance(v, dict)}

# ---------------------------------------------------------------- estado (Firestore)
def ja_vistos(ids):
    if TESTE or not ids:
        return set()
    refs = [db().collection("radar").document(i) for i in ids]
    out = set()
    for i in range(0, len(refs), 100):
        for snap in db().get_all(refs[i:i + 100]):
            if snap.exists:
                out.add(snap.id)
    return out

def marca_visto(doc_id, dados):
    if not TESTE:
        db().collection("radar").document(doc_id).set(dados)

def meta_dia():
    if TESTE:
        return {"enviados": 0, "usd": 0.0}
    snap = db().collection("radar_dia").document(HOJE).get()
    return snap.to_dict() if snap.exists else {"enviados": 0, "usd": 0.0}

def salva_meta(m):
    if not TESTE:
        db().collection("radar_dia").document(HOJE).set(m)

# ---------------------------------------------------------------- triagem com IA
PROMPT = """Voce faz a triagem de noticias para um educador financeiro brasileiro (canal de YouTube e Instagram sobre investimentos).
Para cada item (id, fonte, titulo, trecho), responda:
- "relevante": true se for noticia de investimentos ou que mexe com investimentos (acoes, FIIs, Fiagros, renda fixa, Selic, inflacao, cambio, bolsa, economia que afeta o mercado, BDRs, bolsas e empresas do exterior, ETFs, cripto). false para esporte, celebridade, politica sem efeito no mercado, publicidade, dica de produto, "melhores acoes para comprar" generico e conteudo repetido de recomendacao.
- "tickers": codigos de negociacao da B3 citados ou claramente identificados (ex.: ["MXRF11","PETR4"]); empresa do exterior: o ticker la fora (ex.: "NVDA"). Se o titulo so cita o nome da empresa e voce tem certeza do codigo, inclua. Lista vazia se nao houver.
- "categoria": uma entre "Ações", "FIIs e Fiagros", "Renda fixa", "Macro e juros", "Câmbio", "Exterior", "Cripto", "Outros".
- "video": true se rende pauta de video: historia pouco conhecida, empresa ou fundo pouco falado com fato forte, corte ou salto de dividendo, OPA, calote, recuperacao judicial, polemica, mudanca de regra, numero chamativo. false para noticia de rotina.
- "motivo": se video for true, em ate 12 palavras por que rende video. Senao "".
- "resumo": uma frase curta em portugues simples dizendo o que aconteceu, com suas palavras, neutra, sem opiniao.
Escrita: nunca use travessao; percentuais com 2 casas e virgula decimal.
Responda somente com JSON: {"itens": [{"id": "...", "relevante": true, "tickers": [], "categoria": "...", "video": false, "motivo": "", "resumo": "..."}]}"""

class Gasto:
    usd = 0.0

GASTO = Gasto()

def triagem(itens):
    """Devolve {id: resposta}. Um item que a IA nao respondeu fica de fora."""
    out = {}
    for i in range(0, len(itens), LOTE):
        lote = itens[i:i + LOTE]
        linhas = "\n".join(json.dumps({"id": it["id"], "fonte": it["fonte"], "titulo": it["titulo"],
                                       "trecho": it["resumo_fonte"][:200]}, ensure_ascii=False) for it in lote)
        msg = ia().messages.create(model=MODELO, max_tokens=6000,
                                   messages=[{"role": "user", "content": PROMPT + "\n\nItens:\n" + linhas}])
        GASTO.usd += (msg.usage.input_tokens or 0) * PRECO_ENTRADA + (msg.usage.output_tokens or 0) * PRECO_SAIDA
        for r in robo._json_da_resposta(msg).get("itens", []):
            if r.get("id"):
                out[r["id"]] = r
    return out

# ---------------------------------------------------------------- Telegram
def esc(t):
    return html.escape(t or "", quote=False)

def envia(texto):
    tok, chat = os.environ.get("TELEGRAM_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if TESTE or not tok or not chat:
        log("[telegram]\n" + re.sub(r"<[^>]+>", "", texto) + "\n")
        return True
    for tentativa in range(3):
        try:
            http(f"https://api.telegram.org/bot{tok}/sendMessage",
                 data=urllib.parse.urlencode({"chat_id": chat, "text": texto[:3900], "parse_mode": "HTML",
                                              "disable_web_page_preview": "true"}).encode())
            time.sleep(1.2)
            return True
        except Exception as e:
            log("telegram falhou:", e)
            time.sleep(3 * (tentativa + 1))
    return False

def monta_mensagem(it, r, clientes_do_ativo):
    cab = f"📰 <b>{esc(r.get('categoria') or 'Mercado')}</b> | {esc(it['fonte'])}"
    if r.get("tickers"):
        cab += " | " + esc(" ".join(r["tickers"][:4]))
    partes = [cab, f"<b>{esc(sem_travessao(it['titulo']))}</b>"]
    if r.get("resumo"):
        partes.append(esc(sem_travessao(r["resumo"])))
    if clientes_do_ativo:
        linhas = []
        for tk, cs in clientes_do_ativo.items():
            linhas.append(f"{esc(tk)}: " + ", ".join(sorted(c.capitalize() for c in cs)))
        partes.append("👥 <b>Clientes com esse ativo</b>\n" + "\n".join(linhas))
    if r.get("video"):
        partes.append("🎬 <b>Dá vídeo:</b> " + esc(sem_travessao(r.get("motivo") or "assunto chamativo")))
    partes.append(it["link"])
    return "\n\n".join(partes)

# ---------------------------------------------------------------- principal
def main():
    falhas = []
    bruto = coleta_feeds(falhas) + coleta_cvm(falhas)
    if len(bruto) < 5:
        robo.telegram("⚠️ Radar de notícias: quase nenhuma notícia veio das fontes nesta rodada. Mande esta mensagem para o Claude.\n" + "; ".join(falhas)[:600])
        raise SystemExit("poucas noticias coletadas")
    limite = AGORA - dt.timedelta(hours=JANELA_H)
    vistos_link = set()
    itens = []
    for it in bruto:
        if it["quando"] and it["quando"] < limite:
            continue
        chave = robo.normaliza_url(it["link"])
        if chave in vistos_link:
            continue
        vistos_link.add(chave)
        it["id"] = id_doc("r", chave)
        itens.append(it)
    ja = ja_vistos([i["id"] for i in itens])
    novos = [i for i in itens if i["id"] not in ja]
    log(f"{len(bruto)} lidos, {len(itens)} na janela, {len(novos)} novos, falhas de fonte: {len(falhas)}")

    meta = meta_dia()
    if meta["usd"] >= LIMITE_DIA_USD:
        log("limite de gasto do dia atingido")
        if not meta.get("avisou_limite"):
            robo.telegram(f"ℹ️ Radar de notícias: atingi o limite de gasto do dia (US$ {LIMITE_DIA_USD:.2f}). Só volta amanhã.")
            meta["avisou_limite"] = True
            salva_meta(meta)
        return
    if not novos:
        verifica_saude(falhas, meta)
        return

    por_ativo = mapa_clientes(falhas)
    nomes = nomes_dos_ativos()
    resp = triagem(novos)
    meta["usd"] = round(meta.get("usd", 0) + GASTO.usd, 4)

    fila = []
    for it in novos:
        r = resp.get(it["id"])
        if r is None:
            continue    # a IA nao respondeu: tenta de novo na proxima rodada
        if not r.get("relevante"):
            marca_visto(it["id"], {"titulo": it["titulo"][:200], "dia": HOJE, "enviado": False})
            continue
        texto = (it["titulo"] + " " + it["resumo_fonte"]).lower()
        tks = {t.upper() for t in (r.get("tickers") or [])}
        tks |= {t for t in re.findall(r"\b[A-Z]{4}\d{1,2}\b", it["titulo"] + " " + it["resumo_fonte"])}
        tks |= {t for t, n in nomes.items() if len(n) >= 5 and n.lower() in texto}
        dos_clientes = {t: por_ativo[t] for t in sorted(tks) if t in por_ativo}
        prioridade = (0 if dos_clientes else 1, 0 if r.get("video") else 1, 0 if it.get("oficial") else 1)
        fila.append((prioridade, it, r, dos_clientes))
    fila.sort(key=lambda x: x[0])

    enviados = 0
    for prioridade, it, r, dos_clientes in fila:
        if meta["enviados"] >= MAX_DIA:
            marca_visto(it["id"], {"titulo": it["titulo"][:200], "dia": HOJE, "enviado": False, "motivo": "teto do dia"})
            continue
        if envia(monta_mensagem(it, r, dos_clientes)):
            marca_visto(it["id"], {"titulo": it["titulo"][:200], "dia": HOJE, "enviado": True,
                                   "video": bool(r.get("video")), "clientes": sorted({c for cs in dos_clientes.values() for c in cs})})
            meta["enviados"] += 1
            enviados += 1
    if enviados == 0 and fila == [] and novos and not resp:
        falhas.append("IA nao devolveu triagem")
    if meta["enviados"] >= MAX_DIA and not meta.get("avisou_teto"):
        robo.telegram(f"ℹ️ Radar de notícias: cheguei em {MAX_DIA} avisos hoje. O resto só amanhã (sobe ou desce o limite quando quiser).")
        meta["avisou_teto"] = True
    salva_meta(meta)
    log(f"enviados: {enviados} (hoje: {meta['enviados']}), gasto da rodada US$ {GASTO.usd:.4f}, do dia US$ {meta['usd']:.4f}")
    verifica_saude(falhas, meta)

def verifica_saude(falhas, meta):
    """Avisa uma vez por dia se alguma fonte ficou fora do ar."""
    if not falhas or TESTE:
        if falhas:
            log("falhas:", falhas)
        return
    if meta.get("avisou_falha") == HOJE:
        return
    robo.telegram("ℹ️ Radar de notícias: algumas fontes falharam nesta rodada (o resto segue normal):\n" +
                  "\n".join("• " + f for f in falhas[:8]))
    meta["avisou_falha"] = HOJE
    salva_meta(meta)

if __name__ == "__main__":
    main()
