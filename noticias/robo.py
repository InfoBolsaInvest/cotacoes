"""Robo de noticias dos ativos dos clientes InfoBolsa.

Roda no GitHub Actions as 7h30 e as 19h (Brasilia).
1. Le os ativos de cada app de cliente (objeto DATA publicado no Netlify).
2. Junta os ativos de todos os clientes, sem repetir.
3. Fontes oficiais (sem IA na busca): Fundos.NET (FIIs e Fiagros) e CVM/RAD (acoes).
4. Portais de noticias (so no turno da manha): API da Anthropic com pesquisa na web.
5. Grava no Firestore, sem repetir o que ja foi publicado, e avisa no Telegram o que for importante.
6. Registra o custo de cada rodada e respeita um limite de gasto por execucao.

Segredos (GitHub > Settings > Secrets and variables > Actions):
  ANTHROPIC_API_KEY, FIREBASE_SA (JSON da conta de servico), TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
"""
import base64, datetime as dt, hashlib, html, json, os, re, sys, time, traceback
import urllib.parse, urllib.request

AQUI = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------- configuracao
CLIENTES = {
    "flavio": "https://carteiraflavio.netlify.app/",
}
MODELO = "claude-haiku-4-5-20251001"
PRECO_ENTRADA = 1.00 / 1e6      # US$ por token de entrada (Haiku 4.5)
PRECO_SAIDA = 5.00 / 1e6        # US$ por token de saida
PRECO_BUSCA = 10.00 / 1000      # US$ por pesquisa na web
LIMITE_USD = float(os.environ.get("LIMITE_USD") or "1.50")   # teto de gasto por rodada
JANELA_DIAS = int(os.environ.get("JANELA_DIAS") or "3")      # quantos dias para tras olhar
PDF_MAX_BYTES = 12 * 1024 * 1024
VARIACAO_RENDIMENTO = 0.15
IR_JCP = 0.175                  # IRRF sobre JCP para pessoa fisica desde 01/01/2026 (LC 224/2025)
try:
    _COT = json.load(open(os.path.join(AQUI, "..", "cotacoes.json"), encoding="utf-8")).get("ativos", {})
except Exception:
    _COT = {}

def preco_ref(ticker):
    q = _COT.get(ticker) or {}
    return q.get("preco") if (q.get("preco") or 0) > 0 else None

def completa_provento(ticker, p):
    """Padroniza um provento: valor liquido do JCP, DY do pagamento pelo preco do dia."""
    tipo = "JCP" if "jcp" in (p.get("tipo") or "").lower() or "juros" in (p.get("tipo") or "").lower() else (p.get("tipo") or "Dividendo")
    bruto = float(p.get("valor_bruto") or 0)
    liq = p.get("valor_liquido")
    liq = float(liq) if liq not in (None, "", 0) else (round(bruto * (1 - IR_JCP), 8) if tipo == "JCP" else bruto)
    out = {"tipo": tipo, "valor_bruto": bruto, "valor_liquido": liq,
           "liquido_estimado": tipo == "JCP" and not p.get("valor_liquido"),
           "data_com": (p.get("data_com") or "")[:10], "pagamento": (p.get("pagamento") or "")[:10]}
    pr = preco_ref(ticker)
    if pr and bruto > 0:
        out["preco_ref"] = pr
        out["dy"] = round(100 * bruto / pr, 2)
    return out      # 15% ou mais de diferenca no rendimento vira destaque
PORTAIS_CONFIAVEIS = ["infomoney.com.br", "valor.globo.com", "valorinveste.globo.com", "moneytimes.com.br",
    "exame.com", "einvestidor.estadao.com.br", "folha.uol.com.br", "g1.globo.com", "oglobo.globo.com",
    "cnnbrasil.com.br", "seudinheiro.com", "bloomberglinea.com.br", "br.reuters.com", "investnews.com.br",
    "braziljournal.com", "istoedinheiro.com.br", "poder360.com.br", "suno.com.br", "fiis.com.br", "neofeed.com.br",
    "agenciabrasil.ebc.com.br", "forbes.com.br", "veja.abril.com.br", "metropoles.com"]
DOMINIOS_BLOQUEADOS = ["statusinvest.com.br", "investidor10.com.br", "fundamentus.com.br",
                       "clubefii.com.br", "br.tradingview.com", "br.investing.com",
                       "fundsexplorer.com.br", "fiis.com.br"]
TZ_BR = dt.timezone(dt.timedelta(hours=-3))
AGORA = dt.datetime.now(TZ_BR)
TURNO = os.environ.get("TURNO") or ("manha" if AGORA.hour < 12 else "noite")
BUSCAR_PORTAIS = os.environ.get("PORTAIS", "auto")
BUSCAR_PORTAIS = (TURNO == "manha") if BUSCAR_PORTAIS == "auto" else BUSCAR_PORTAIS == "1"
TESTE = os.environ.get("TESTE") == "1"   # nao grava nada, so mostra
SO_RENDIMENTOS = os.environ.get("REPROCESSAR_RENDIMENTOS") == "1"   # refaz so os proventos
ALERTAS = []      # (chave, texto, imediato): problemas para avisar o Douglas no Telegram
INFORMES = []     # avisos sem problema (ex.: ativo novo cadastrado sozinho)
FALHAS_IA = []
CHECOU_FECHAMENTO = False

def alerta(chave, texto, imediato=False):
    """imediato=False: so avisa se o problema se repetir na rodada seguinte (evita aviso por instabilidade passageira)."""
    ALERTAS.append((re.sub(r"\d+", "#", chave)[:90], texto, imediato))

UA = {"User-Agent": "Mozilla/5.0 (compatible; InfoBolsa-noticias/1.0)"}

# ---------------------------------------------------------------- utilidades
def http(url, data=None, headers=None, timeout=60):
    h = dict(UA)
    h.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(), r.headers.get("content-type", "")

def log(*a):
    print(*a, flush=True)

def sem_travessao(t):
    t = (t or "").replace(" — ", ", ").replace(" – ", ", ").replace("—", ", ").replace("–", "-")
    return re.sub(r"\s+", " ", t).strip()

def br_num(v, casas=2):
    s = f"{v:,.{casas}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")

def br_valor_unit(v):
    """Valor por cota/acao: 2 casas, ou ate 4 quando for centavo quebrado."""
    for casas in (2, 3, 4):
        if abs(round(v, casas) - v) < 1e-9:
            return br_num(v, casas)
    return br_num(v, 4)

def data_br_para_iso(s):
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})(?:\s+(\d{2}):(\d{2}))?", s or "")
    if not m:
        return None
    d, mo, a, hh, mm = m.groups()
    return f"{a}-{mo}-{d}" + (f"T{hh}:{mm}" if hh else "")

def iso_para_br(s):
    return f"{s[8:10]}/{s[5:7]}/{s[0:4]}" if s and len(s) >= 10 else ""

def id_doc(prefixo, chave):
    return prefixo + "-" + hashlib.sha1(str(chave).encode()).hexdigest()[:20]

def normaliza_url(u):
    p = urllib.parse.urlsplit(u.strip())
    q = [(k, v) for k, v in urllib.parse.parse_qsl(p.query) if not k.lower().startswith("utm_")]
    return urllib.parse.urlunsplit((p.scheme.lower(), p.netloc.lower().removeprefix("www."),
                                    p.path.rstrip("/"), urllib.parse.urlencode(q), ""))

# ---------------------------------------------------------------- custo
class Custo:
    def __init__(self):
        self.entrada = self.saida = self.buscas = self.chamadas = 0
        self.parou_no_limite = False
    @property
    def usd(self):
        return self.entrada * PRECO_ENTRADA + self.saida * PRECO_SAIDA + self.buscas * PRECO_BUSCA
    def pode(self, estimativa):
        if self.usd + estimativa > LIMITE_USD:
            self.parou_no_limite = True
            return False
        return True
    def soma(self, usage):
        self.chamadas += 1
        self.entrada += (usage.input_tokens or 0) + (getattr(usage, "cache_creation_input_tokens", 0) or 0) \
            + (getattr(usage, "cache_read_input_tokens", 0) or 0)
        self.saida += usage.output_tokens or 0
        stu = getattr(usage, "server_tool_use", None)
        if stu is not None:
            self.buscas += getattr(stu, "web_search_requests", 0) or 0

CUSTO = Custo()
TESTE_SAIDA = []

# ---------------------------------------------------------------- IA
_cliente_ia = None
def ia():
    global _cliente_ia
    if _cliente_ia is None:
        import anthropic
        _cliente_ia = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _cliente_ia

REGRAS = """Regras de escrita (obrigatorias):
- Portugues do Brasil, linguagem simples, para um investidor comum.
- Resumo com 2 ou 3 frases curtas. Escreva com suas palavras, nunca copie frases do texto original.
- Tom neutro, apenas informativo. Proibido opinar, recomendar ou sugerir compra, venda ou manutencao.
- Nunca use travessao. Use virgula ou ponto.
- Numeros no padrao brasileiro (200.000,00; R$ 1,25) e percentuais com 2 casas decimais (10,50%).
- Nao fale de voce mesmo, nao cumprimente, nao use primeira pessoa.
Marque "importante": true SOMENTE nestes casos, e em "motivo" use exatamente um destes textos:
- "Corte de dividendo" ou "Aumento forte de dividendo": quando o proprio texto disser que o provento caiu ou subiu bastante em relacao ao anterior. Anuncio normal de dividendo NAO e importante.
- "OPA": oferta publica de aquisicao de acoes ou cotas.
- "Recuperação judicial": recuperacao judicial, extrajudicial ou falencia da empresa ou de devedor relevante do fundo.
- "Inadimplência": atraso ou calote de devedores relevantes de um fundo.
- "Emissão de cotas" ou "Emissão de ações": nova oferta de cotas ou de acoes. Emissao de divida (debentures, letras financeiras, CRI, CRA) NAO e importante.
- "Troca de gestor": troca da gestora ou da administradora de um FUNDO. Troca de diretor, vice-presidente ou conselheiro de empresa NAO e importante.
- "Incorporação ou fusão": incorporacao, fusao, cisao ou liquidacao do fundo ou da empresa.
Em qualquer outro caso: "importante": false e "motivo": ""."""

def _json_da_resposta(msg):
    txt = "".join(getattr(b, "text", "") for b in msg.content if getattr(b, "type", "") == "text")
    m = re.search(r"\{[\s\S]*\}", txt)
    if not m:
        raise ValueError("resposta sem JSON: " + txt[:200])
    return json.loads(m.group(0))

def resumir_documento(ticker, nome, categoria, assunto, pdf_bytes):
    if not CUSTO.pode(0.08):
        return None
    conteudo = []
    if pdf_bytes:
        conteudo.append({"type": "document", "source": {"type": "base64", "media_type": "application/pdf",
                                                         "data": base64.b64encode(pdf_bytes).decode()}})
    conteudo.append({"type": "text", "text": f"""Documento oficial de {nome} ({ticker}).
Categoria: {categoria}. Assunto informado: {assunto or 'nao informado'}.

{REGRAS}

Responda somente com JSON neste formato:
{{"titulo": "titulo curto e claro, ate 80 caracteres", "resumo": "2 ou 3 frases", "importante": false, "motivo": ""}}"""})
    msg = ia().messages.create(model=MODELO, max_tokens=500, messages=[{"role": "user", "content": conteudo}])
    CUSTO.soma(msg.usage)
    return _json_da_resposta(msg)

def extrair_proventos(ticker, nome, assunto, pdf_bytes):
    if not CUSTO.pode(0.05):
        return None
    classe = {"3": "ordinaria (ON)", "4": "preferencial (PN)", "5": "preferencial classe A (PNA)",
              "6": "preferencial classe B (PNB)", "11": "unit"}.get(re.sub(r"^[A-Z]+", "", ticker), "")
    conteudo = [{"type": "document", "source": {"type": "base64", "media_type": "application/pdf",
                                                 "data": base64.b64encode(pdf_bytes).decode()}},
                {"type": "text", "text": f"""Aviso de proventos de {nome}. Extraia os proventos da acao {ticker} ({classe}).
Se o documento tiver valores diferentes por especie de acao, use os da {classe}.
Para JCP, informe o valor bruto e, se o documento trouxer, o valor liquido para pessoa fisica (se nao trouxer, use null).
Datas no formato AAAA-MM-DD. "data_com" e o ultimo dia para ter a acao e receber (tambem chamada data-base ou "data com"); NUNCA use a data ex, que e o dia seguinte. Se o pagamento ainda nao tiver data, use null.
So liste proventos que ESTE documento esta anunciando ou aprovando, com valor por acao. Se o documento so traz orientacoes
(tributacao, investidor nao residente, cadastro, agenda) ou apenas lembra um provento ja anunciado em outro documento,
devolva "proventos": [] e use titulo e resumo que descrevam o que o documento realmente informa.

{REGRAS}

Responda somente com JSON neste formato:
{{"titulo": "titulo curto, ate 70 caracteres", "resumo": "1 frase curta dizendo o que foi aprovado (sem repetir valores e datas)", "importante": false, "motivo": "",
 "proventos": [{{"tipo": "Dividendo ou JCP", "valor_bruto": 0.0, "valor_liquido": null, "data_com": "AAAA-MM-DD", "pagamento": "AAAA-MM-DD"}}]}}"""}]
    msg = ia().messages.create(model=MODELO, max_tokens=600, temperature=0, messages=[{"role": "user", "content": conteudo}])
    CUSTO.soma(msg.usage)
    return _json_da_resposta(msg)

OPINIAO = re.compile(r"pre[cç]o[- ]alvo|recomenda[cç][aã]o|potencial de (alta|valoriza)|carteira recomendada|rating de compra", re.I)

def limpa_opiniao():
    if TESTE:
        return 0
    n = 0
    for snap in db().collection("noticias").where("origem", "==", "portal").stream():
        d = snap.to_dict()
        if OPINIAO.search(d.get("titulo", "") + " " + d.get("resumo", "")):
            snap.reference.delete()
            n += 1
    return n

def buscar_portais(ticker, info, desde_iso, ja_publicados=()):
    if not CUSTO.pode(0.06):
        return []
    nome = info.get("nome", ticker)
    prompt = f"""Pesquise noticias publicadas em portais de noticias desde {iso_para_br(desde_iso)} sobre {nome}, codigo de negociacao {ticker} na B3.
Inclua SOMENTE noticias claramente sobre este ativo: o texto precisa citar o codigo {ticker} ou o nome exato "{nome}". Descarte qualquer coisa sobre outra empresa ou fundo com nome parecido, paginas de cotacao, foruns, listas genericas de "melhores ativos", conteudo patrocinado e materias anteriores a {iso_para_br(desde_iso)}.
Descarte tambem materias cujo assunto principal seja recomendacao de analistas (compra, venda, neutro), preco-alvo, potencial de valorizacao ou carteira recomendada.
Assuntos que JA foram publicados sobre este ativo (nao traga noticia sobre o mesmo fato, mesmo de outro portal):
{chr(10).join("- " + t for t in ja_publicados) or "- nenhum"}
Se nao houver nada novo, devolva a lista vazia. No maximo 3 itens.

{REGRAS}

Responda somente com JSON neste formato:
{{"itens": [{{"titulo": "titulo curto com suas palavras", "url": "link exato da materia", "fonte": "nome do portal", "data": "AAAA-MM-DD", "resumo": "2 ou 3 frases", "cita_ativo": "trecho curto da materia onde aparece {ticker} ou {nome}", "importante": false, "motivo": ""}}]}}"""
    tool = {"type": "web_search_20250305", "name": "web_search", "max_uses": 1,
            "allowed_domains": PORTAIS_CONFIAVEIS,
            "user_location": {"type": "approximate", "country": "BR", "timezone": "America/Sao_Paulo"}}
    msg = ia().messages.create(model=MODELO, max_tokens=1200, tools=[tool],
                               messages=[{"role": "user", "content": prompt}])
    CUSTO.soma(msg.usage)
    # links que vieram de fato da pesquisa (protege contra link inventado)
    reais = set()
    for b in msg.content:
        if getattr(b, "type", "") == "web_search_tool_result" and isinstance(getattr(b, "content", None), list):
            for r in b.content:
                u = getattr(r, "url", None)
                if u:
                    reais.add(normaliza_url(u))
    try:
        itens = _json_da_resposta(msg).get("itens", [])
    except Exception as e:
        log("  portais: JSON invalido", ticker, e)
        return []
    bons = []
    chaves = [ticker.lower(), nome.lower()] + [p.lower() for p in nome.split() if len(p) > 4 and p.lower() not in ("fundo", "fiagro", "capital", "banco")]
    for it in itens:
        url = (it.get("url") or "").strip()
        if not url.startswith("http") or normaliza_url(url) not in reais:
            continue
        host = urllib.parse.urlsplit(url).netloc.lower().removeprefix("www.")
        if not any(host == d or host.endswith("." + d) for d in PORTAIS_CONFIAVEIS):
            continue
        cita = (it.get("cita_ativo", "") + " " + it.get("titulo", "") + " " + it.get("resumo", "")).lower()
        if ticker.lower() not in cita and nome.lower() not in cita and not any(c in cita for c in chaves):
            continue
        data = (it.get("data") or "")[:10]
        if not re.match(r"\d{4}-\d{2}-\d{2}$", data) or data < desde_iso[:10]:
            continue
        if OPINIAO.search(it.get("titulo", "") + " " + it.get("resumo", "")):
            continue
        bons.append(it)
    return bons

# ---------------------------------------------------------------- Firestore
_db = None
def db():
    global _db
    if _db is None:
        import firebase_admin
        from firebase_admin import credentials, firestore
        cred = credentials.Certificate(json.loads(os.environ["FIREBASE_SA"]))
        firebase_admin.initialize_app(cred)
        _db = firestore.client()
    return _db

def ids_existentes(ids):
    if TESTE or not ids:
        return set()
    refs = [db().collection("noticias").document(i) for i in ids]
    out = set()
    for i in range(0, len(refs), 100):
        for snap in db().get_all(refs[i:i + 100]):
            if snap.exists:
                out.add(snap.id)
    return out

def grava_noticia(doc_id, item):
    item = dict(item)
    item["titulo"] = sem_travessao(item.get("titulo"))[:140]
    item["resumo"] = sem_travessao(item.get("resumo"))[:700]
    item["criado_em"] = AGORA.isoformat(timespec="seconds")
    if TESTE:
        TESTE_SAIDA.append(f"{item['ticker']} | {item['tipo']} | {item.get('data','')} | {item['titulo']} | {item['resumo'][:160]}"
                           + (" | " + json.dumps(item["proventos"], ensure_ascii=False) if item.get("proventos") else ""))
        return True
    from google.api_core.exceptions import AlreadyExists
    try:
        db().collection("noticias").document(doc_id).create(item)
        return True
    except AlreadyExists:
        return False

def estado_ativo(ticker):
    if TESTE:
        return {}
    s = db().collection("ativos").document(ticker).get()
    return s.to_dict() if s.exists else {}

def salva_estado_ativo(ticker, dados):
    if not TESTE:
        db().collection("ativos").document(ticker).set(dados, merge=True)

FEED_MAX = 600          # cerca de 4 meses de historico
FEED_MAX_BYTES = 900_000   # documento do Firestore aceita ate 1 MB
CAMPOS_FEED = ("ticker", "tipo", "data", "titulo", "resumo", "link", "fonte", "importante", "motivo", "variacao", "proventos")

def atualiza_feed(cli, tickers):
    itens = []
    for i in range(0, len(tickers), 30):
        q = db().collection("noticias").where("ticker", "in", tickers[i:i + 30])
        for snap in q.stream():
            d = snap.to_dict()
            itens.append({k: d[k] for k in CAMPOS_FEED if k in d})
    itens.sort(key=lambda x: (x.get("data") or ""), reverse=True)
    itens = itens[:FEED_MAX]
    while len(json.dumps(itens, ensure_ascii=False).encode()) > FEED_MAX_BYTES:
        itens = itens[:int(len(itens) * 0.9)]
    db().collection("feeds").document(cli).set({
        "atualizado": AGORA.isoformat(timespec="seconds"),
        "tickers": tickers,
        "itens_json": json.dumps(itens, ensure_ascii=False),
    })

# ---------------------------------------------------------------- Telegram
def telegram(texto):
    tok, chat = os.environ.get("TELEGRAM_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if TESTE or not tok or not chat:
        log("  [telegram]", texto[:500])
        return
    try:
        http(f"https://api.telegram.org/bot{tok}/sendMessage",
             data=urllib.parse.urlencode({"chat_id": chat, "text": texto[:3900], "disable_web_page_preview": "true"}).encode())
    except Exception as e:
        log("  telegram falhou:", e)

def avisa_telegram(item):
    tok, chat = os.environ.get("TELEGRAM_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not tok or not chat:
        return
    texto = (f"\U0001F514 {item['ticker']} | {item['tipo']}\n{item['titulo']}\n\n{item['resumo']}\n\n"
             f"Motivo do destaque: {item.get('motivo') or 'assunto relevante'}\n{item['link']}")
    if TESTE:
        log("  [teste telegram]", texto[:200])
        return
    try:
        http(f"https://api.telegram.org/bot{tok}/sendMessage",
             data=urllib.parse.urlencode({"chat_id": chat, "text": texto, "disable_web_page_preview": "true"}).encode())
    except Exception as e:
        log("  telegram falhou:", e)

# ---------------------------------------------------------------- carteiras
def tickers_do_app(url):
    corpo, _ = http(url + ("&" if "?" in url else "?") + "t=" + str(int(time.time())))
    s = corpo.decode("utf-8", "replace")
    m = re.search(r"const DATA = (\{.*?\});\s*\n", s, re.S)
    if not m:
        raise ValueError("DATA nao encontrado em " + url)
    dados = json.loads(m.group(1))
    return sorted({a["ticker"] for a in dados["ativos"] if a.get("classe") in ("acoes", "fiis")})

# ---------------------------------------------------------------- Fundos.NET
FNET = "https://fnet.bmfbovespa.com.br/fnet/publico/"
CATEGORIAS_FII = {
    "Fato Relevante": "Fato relevante",
    "Comunicado ao Mercado": "Comunicado",
    "Aviso aos Cotistas": "Comunicado",
    "Aviso aos Cotistas - Estruturado": "Rendimento",
    "Relatórios": "Relatório gerencial",
    "Oferta Pública de Distribuição de Cotas": "Comunicado",
    "Assembleia": "Comunicado",
}

def fnet_lista(cnpj, n=30):
    url = (FNET + "pesquisarGerenciadorDocumentosDados?d=0&s=0&l=" + str(n) +
           "&o%5B0%5D%5BdataEntrega%5D=desc&cnpjFundo=" + cnpj)
    corpo, _ = http(url)
    return json.loads(corpo)["data"]

def fnet_rendimento(doc_id):
    corpo, _ = http(FNET + "exibirDocumento?id=" + str(doc_id))
    t = html.unescape(re.sub(r"<[^>]+>", " ", corpo.decode("utf-8", "replace")))
    t = re.sub(r"\s+", " ", t)
    base = re.search(r"Data-base[^0-9]*?(\d{2}/\d{2}/\d{4})", t)
    val = re.search(r"Valor do provento \(R\$/unidade\)\s*([\d.,]+)", t)
    pag = re.search(r"Data do pagamento\s*(\d{2}/\d{2}/\d{4})", t)
    if not val:
        return None
    return {"valor": float(val.group(1).replace(".", "").replace(",", ".")),
            "data_base": base.group(1) if base else "", "pagamento": pag.group(1) if pag else ""}

def fontes_fii(ticker, info, desde_iso, novos):
    todos = fnet_lista(info["cnpj"])
    # documento reapresentado fica inativo: some do app e nao entra em comparacao
    inativos = [id_doc("fnet", d["id"]) for d in todos if (d.get("situacaoDocumento") or "A") != "A"]
    if inativos and not TESTE:
        for nid in ids_existentes(inativos):
            db().collection("noticias").document(nid).delete()
    docs = [d for d in todos if (d.get("situacaoDocumento") or "A") == "A"]
    candidatos = []
    for d in docs:
        cat = (d.get("categoriaDocumento") or "").strip()
        tipo_doc = (d.get("tipoDocumento") or "").strip()
        quando = data_br_para_iso(d.get("dataEntrega"))
        if not quando or quando[:10] < desde_iso or cat not in CATEGORIAS_FII:
            continue
        if SO_RENDIMENTOS and cat != "Aviso aos Cotistas - Estruturado":
            continue
        if cat == "Relatórios" and "Gerencial" not in tipo_doc:
            continue
        if cat == "Oferta Pública de Distribuição de Cotas" and not re.search(r"Início|Fato|Encerramento|Comunicado", tipo_doc):
            continue
        if cat == "Assembleia" and "Edital" not in tipo_doc and "Resumo" not in tipo_doc and "Ata" not in tipo_doc:
            continue
        candidatos.append(d)
    ids = {id_doc("fnet", d["id"]): d for d in candidatos}
    ja = ids_existentes(list(ids))
    rendimentos = [d for d in docs if (d.get("categoriaDocumento") or "").strip() == "Aviso aos Cotistas - Estruturado"
                   and "Rendimento" in (d.get("tipoDocumento") or "")]
    for nid, d in ids.items():
        if nid in ja:
            continue
        cat = d["categoriaDocumento"].strip()
        tipo = CATEGORIAS_FII[cat]
        quando = data_br_para_iso(d["dataEntrega"])
        link = FNET + "exibirDocumento?id=" + str(d["id"])
        item = {"ticker": ticker, "tipo": tipo, "data": quando, "link": link, "fonte": "B3 Fundos.NET",
                "origem": "oficial", "importante": False, "motivo": ""}
        if tipo == "Rendimento":
            r = fnet_rendimento(d["id"])
            if not r:
                continue
            ant = None
            anteriores = [x for x in rendimentos if x["id"] < d["id"]]
            if anteriores:
                ant = fnet_rendimento(max(anteriores, key=lambda x: x["id"])["id"])
            comp = ""
            if ant and ant["valor"] > 0:
                var = r["valor"] / ant["valor"] - 1
                if abs(var) < 0.00005:
                    comp = " Mesmo valor do anúncio anterior."
                else:
                    comp = (f" No anúncio anterior foram R$ {br_valor_unit(ant['valor'])} por cota, "
                            f"{'alta' if var > 0 else 'queda'} de {br_num(abs(var) * 100)}%.")
                    if abs(var) >= VARIACAO_RENDIMENTO:
                        item["importante"] = True
                        item["motivo"] = ("Aumento forte do rendimento" if var > 0 else "Corte do rendimento")
                item["variacao"] = round(var * 100, 2)
            item["titulo"] = f"Rendimento de R$ {br_valor_unit(r['valor'])} por cota"
            item["resumo"] = (f"O fundo vai pagar R$ {br_valor_unit(r['valor'])} por cota em {r['pagamento']}, "
                              f"para quem tinha cotas no fim do dia {r['data_base']}." + comp)
            item["valor"] = r["valor"]
            item["proventos"] = [completa_provento(ticker, {"tipo": "Rendimento", "valor_bruto": r["valor"],
                                 "valor_liquido": r["valor"], "data_com": data_br_para_iso(r["data_base"]) or "",
                                 "pagamento": data_br_para_iso(r["pagamento"]) or ""})]
            item["resumo"] = "Rendimento mensal do fundo, isento de imposto de renda para pessoa física." + comp
        else:
            assunto = (d.get("tipoDocumento") or "").strip()
            pdf = None
            try:
                corpo, ct = http(FNET + "downloadDocumento?id=" + str(d["id"]))
                if corpo[:4] == b"%PDF" and len(corpo) <= PDF_MAX_BYTES:
                    pdf = corpo
            except Exception as e:
                log("  pdf fnet falhou", d["id"], e)
            res = None
            if pdf:
                try:
                    res = resumir_documento(ticker, info["nome"], cat, assunto, pdf)
                except Exception as e:
                    log("  IA falhou", ticker, d["id"], e)
                    FALHAS_IA.append(f"{ticker}: {e}")
            if not res:
                res = {"titulo": tipo if not assunto else assunto, "resumo":
                       f"{info['nome']} publicou um documento oficial ({cat.lower()}"
                       + (f", {assunto.lower()}" if assunto else "") + "). Veja o documento completo no link.",
                       "importante": bool(d.get("altaPrioridade")) and tipo == "Fato relevante", "motivo": ""}
            item.update({"titulo": res.get("titulo") or tipo, "resumo": res.get("resumo") or "",
                         "importante": bool(res.get("importante")), "motivo": res.get("motivo") or ""})
            if cat == "Oferta Pública de Distribuição de Cotas" and not item["importante"]:
                item["importante"], item["motivo"] = True, "Emissão de cotas"
        if grava_noticia(nid, item):
            novos.append(item)

# ---------------------------------------------------------------- CVM (RAD)
RAD = "https://www.rad.cvm.gov.br/ENET/"
CATEGORIAS_ACAO = {
    "Fato Relevante": "Fato relevante",
    "Comunicado ao Mercado": "Comunicado",
    "Aviso aos Acionistas": "Comunicado",
    "Dados Econômico-Financeiros": "Comunicado",
}
_rad_cache = None
def rad_documentos(desde_iso):
    global _rad_cache
    if _rad_cache is not None:
        return _rad_cache
    d0 = dt.date.fromisoformat(desde_iso)
    corpo = json.dumps({"dataDe": d0.strftime("%d/%m/%Y"), "dataAte": AGORA.strftime("%d/%m/%Y"),
                        "empresa": "", "setorAtividade": "-1", "categoriaEmissor": "-1", "situacaoEmissor": "-1",
                        "tipoParticipante": "-1", "dataReferencia": "", "categoria": "IPE_-1_-1_-1", "periodo": "2",
                        "horaIni": "", "horaFim": "", "palavraChave": "", "ultimaDtRef": "false", "tipoEmpresa": "0",
                        "token": "", "versaoCaptcha": ""}).encode()
    r, _ = http(RAD + "frmConsultaExternaCVM.aspx/ListarDocumentos", data=corpo,
                headers={"Content-Type": "application/json; charset=utf-8"}, timeout=120)
    dados = json.loads(r)["d"].get("dados") or ""
    docs = []
    for rec in dados.split("&*"):
        f = rec.split("$&")
        if len(f) < 11:
            continue
        cod = re.sub(r"\D", "", f[0])
        dl = re.search(r"OpenDownloadDocumentos\('(\d+)','(\d+)','(\d+)','IPE'\)", rec)
        if not cod or not dl:
            continue
        assunto = re.sub(r"</?spanOrder>", "", f[4]).strip(" -")
        docs.append({"cvm": int(cod), "empresa": f[1].strip(), "categoria": f[2].strip(),
                     "tipo": f[3].strip(), "assunto": html.unescape(assunto),
                     "entrega": data_br_para_iso(re.sub(r"<[^>]+>\d*</spanOrder>", "", f[6])),
                     "seq": dl.group(1), "versao": dl.group(2), "protocolo": dl.group(3)})
    _rad_cache = docs
    return docs

def fontes_acao(ticker, info, desde_iso, novos):
    docs = [d for d in rad_documentos(desde_iso) if d["cvm"] == info["cvm"] and d["categoria"] in CATEGORIAS_ACAO
            and d["entrega"] and d["entrega"][:10] >= desde_iso and doc_acao_relevante(d)]
    ids = {id_doc("cvm", d["protocolo"]): d for d in docs}
    ja = ids_existentes(list(ids))
    for nid, d in ids.items():
        if nid in ja:
            continue
        tipo = CATEGORIAS_ACAO[d["categoria"]]
        txt = (d["assunto"] + " " + d["tipo"]).lower()
        if d["categoria"] == "Aviso aos Acionistas" and re.search(r"dividend|juros sobre|jcp|provento|rendimento", txt):
            tipo = "Rendimento"
        if SO_RENDIMENTOS and tipo != "Rendimento":
            continue
        link = RAD + "frmExibirArquivoIPEExterno.aspx?NumeroProtocoloEntrega=" + d["protocolo"]
        pdf, falhou = None, False
        try:
            corpo, _ = http(RAD + "frmDownloadDocumento.aspx?Tela=ext&numSequencia=" + d["seq"] + "&numVersao=" +
                            d["versao"] + "&numProtocolo=" + d["protocolo"] + "&descTipo=IPE&CodigoInstituicao=1")
            if corpo[:4] == b"%PDF" and len(corpo) <= PDF_MAX_BYTES:
                pdf = corpo
        except Exception as e:
            log("  pdf cvm falhou", d["protocolo"], e)
            falhou = True
        res = None
        if pdf:
            try:
                if tipo == "Rendimento":
                    res = extrair_proventos(ticker, info["nome"], d["assunto"] or d["tipo"], pdf)
                else:
                    res = resumir_documento(ticker, info["nome"], d["categoria"], d["assunto"] or d["tipo"], pdf)
            except Exception as e:
                log("  IA falhou", ticker, d["protocolo"], e)
                FALHAS_IA.append(f"{ticker}: {e}")
                falhou = True
        if falhou or (pdf and not res):
            continue   # tenta de novo na proxima rodada
        if tipo == "Rendimento" and res and not res.get("proventos"):
            log("  sem valores de provento", ticker, d["protocolo"])
        if not res:
            res = {"titulo": d["assunto"] or d["categoria"], "resumo":
                   f"{info['nome']} publicou um documento oficial na CVM ({d['categoria'].lower()}). "
                   "Veja o documento completo no link.", "importante": False, "motivo": ""}
        item = {"ticker": ticker, "tipo": tipo, "data": d["entrega"], "link": link, "fonte": "CVM",
                "origem": "oficial", "titulo": res.get("titulo") or d["categoria"], "resumo": res.get("resumo") or "",
                "importante": bool(res.get("importante")), "motivo": res.get("motivo") or ""}
        provs = [completa_provento(ticker, p) for p in (res.get("proventos") or []) if p.get("valor_bruto")]
        if provs and any(p["data_com"] for p in provs):
            item["proventos"] = provs
        elif tipo == "Rendimento":
            item["tipo"] = "Comunicado"   # aviso sobre provento ja anunciado, sem valor novo
        if grava_noticia(nid, item):
            novos.append(item)

def doc_acao_relevante(d):
    a = (d["assunto"] + " " + d["tipo"]).lower()
    if re.search(r"apresenta[cç][aã]o|teleconfer|webcast|per[ií]odo de sil[eê]ncio", a):
        return False
    if re.search(r"ingl[eê]s|english", a):
        return False
    if d["categoria"] == "Dados Econômico-Financeiros":
        return bool(re.search(r"release|resultado", a)) and not re.search(r"apresenta", a)
    return True

# ---------------------------------------------------------------- portais
def titulos_recentes(ticker, dias=10):
    if TESTE:
        return []
    lim = (AGORA.date() - dt.timedelta(days=dias)).isoformat()
    out = []
    for snap in db().collection("noticias").where("ticker", "==", ticker).stream():
        d = snap.to_dict()
        if (d.get("data") or "") >= lim:
            out.append(d.get("titulo", ""))
    return out[:25]

def fontes_portais(ticker, info, desde_iso, novos):
    ja = titulos_recentes(ticker) + [n["titulo"] for n in novos if n["ticker"] == ticker]
    itens = buscar_portais(ticker, info, desde_iso, ja)
    ids = {id_doc("web", normaliza_url(it["url"])): it for it in itens}
    existentes = ids_existentes(list(ids))
    for nid, it in ids.items():
        if nid in existentes:
            continue
        item = {"ticker": ticker, "tipo": "Notícia", "data": it["data"], "link": it["url"],
                "fonte": (it.get("fonte") or urllib.parse.urlsplit(it["url"]).netloc.removeprefix("www."))[:60],
                "origem": "portal", "titulo": it.get("titulo") or "", "resumo": it.get("resumo") or "",
                "importante": bool(it.get("importante")), "motivo": it.get("motivo") or ""}
        if grava_noticia(nid, item):
            novos.append(item)

# ---------------------------------------------------------------- cadastro automatico de ativo novo
def _b3(url_base, params):
    q = base64.b64encode(json.dumps(params).encode()).decode()
    corpo, _ = http(url_base + q)
    return json.loads(corpo or b"{}")

def cadastra_acao(ticker):
    raiz = re.sub(r"\d+$", "", ticker)
    d = _b3("https://sistemaswebb3-listados.b3.com.br/listedCompaniesProxy/CompanyCall/GetInitialCompanies/",
            {"language": "pt-br", "pageNumber": 1, "pageSize": 20, "company": raiz})
    for r in d.get("results") or []:
        if (r.get("issuingCompany") or "").upper() == raiz and r.get("codeCVM") and not (r.get("typeBDR") or "").strip():
            nome = (r.get("tradingName") or r.get("companyName") or ticker).strip().title()
            return {"tipo": "acao", "cvm": int(r["codeCVM"]), "nome": nome, "busca": f"{nome} {ticker}"}
    return None

def cadastra_fundo(ticker):
    """Acha o CNPJ com uma pesquisa curta e so aceita se o Fundos.NET confirmar que o fundo e desse codigo."""
    if not CUSTO.pode(0.04):
        return None
    msg = ia().messages.create(model=MODELO, max_tokens=300, tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 2}],
        messages=[{"role": "user", "content": f"Qual e o CNPJ do fundo (FII, Fiagro ou ETF) negociado na B3 com o codigo {ticker}? "
                   'Responda somente com JSON: {"cnpj": "so numeros", "nome": "nome curto do fundo", "tipo": "FII, Fiagro ou ETF"}. '
                   'Se nao tiver certeza, use cnpj vazio.'}])
    CUSTO.soma(msg.usage)
    r = _json_da_resposta(msg)
    cnpj = re.sub(r"\D", "", r.get("cnpj") or "")
    if len(cnpj) != 14 or "etf" in (r.get("tipo") or "").lower():
        return None
    docs = fnet_lista(cnpj, 40)
    raiz = re.sub(r"\d+$", "", ticker)
    ok = any(re.search(r"\b" + raiz + r"\b", ((x.get("nomePregao") or "") + " " + (x.get("informacoesAdicionais") or "")).upper()) for x in docs)
    if not ok:
        for x in docs:
            if (x.get("categoriaDocumento") or "").strip() == "Aviso aos Cotistas - Estruturado":
                corpo, _ = http(FNET + "exibirDocumento?id=" + str(x["id"]))
                ok = ticker in corpo.decode("utf-8", "replace").upper()
                break
    if not ok:
        return None
    nome = (r.get("nome") or ticker).strip()
    return {"tipo": "fii", "cnpj": cnpj, "nome": nome, "busca": f"{ticker} {nome}"}

def cadastro_salvo():
    if TESTE:
        return {}
    return {s.id: s.to_dict() for s in db().collection("cadastro").stream()}

def cadastra_novos(sem_cadastro, cadastro):
    for t in sem_cadastro:
        info = None
        try:
            info = cadastra_acao(t)
            if not info:
                info = cadastra_fundo(t)
        except Exception as e:
            log("  cadastro automatico falhou", t, e)
            alerta("cadastro " + t, f"Não consegui cadastrar sozinho o ativo novo {t} (erro: {str(e)[:120]}). Vou tentar de novo na próxima rodada.")
            continue
        if info:
            cadastro[t] = info
            INFORMES.append(f"Ativo novo na carteira: {t} ({info['nome']}). Já cadastrei e vou acompanhar os documentos oficiais dele.")
        else:
            info = {"tipo": "sem_oficial", "nome": t, "busca": t}
            cadastro[t] = info
            INFORMES.append(f"Ativo novo na carteira: {t}. Não achei documentos oficiais para ele (pode ser ETF, BDR ou um fundo diferente), "
                            "então ele fica só com as notícias dos portais. Se ele for importante, fale com o Claude.")
        if not TESTE:
            db().collection("cadastro").document(t).set(dict(info, criado_em=AGORA.isoformat(timespec="seconds")))

def logos_faltando(cadastro, ativos):
    pasta = os.path.join(AQUI, "..", "logos")
    falta = [t for t in ativos if (cadastro.get(t) or {}).get("tipo") == "acao" and not os.path.exists(os.path.join(pasta, t + ".svg"))]
    if falta and not TESTE:
        open(os.path.join(AQUI, "..", "logos_faltando.txt"), "w").write("\n".join(falta) + "\n")

# ---------------------------------------------------------------- verificacoes de saude
def confere_cotacoes():
    try:
        c = json.load(open(os.path.join(AQUI, "..", "cotacoes.json"), encoding="utf-8"))
    except Exception as e:
        alerta("cotacoes arquivo", f"Não consegui ler o arquivo de cotações automáticas ({e}).", True)
        return
    falhas = c.get("falhas") or []
    if falhas:
        mot = c.get("motivos") or {}
        alerta("cotacoes falhas " + ",".join(sorted(falhas)),
               "Cotações automáticas: não consegui o preço de " + ", ".join(falhas) + ". Motivo: "
               + "; ".join(f"{t}: {mot.get(t, '?')}" for t in falhas[:5]))
    global CHECOU_FECHAMENTO
    hoje = AGORA.date().isoformat()
    ult = c.get("atualizado") or ""
    CHECOU_FECHAMENTO = AGORA.weekday() < 5 and AGORA.hour >= 19
    if CHECOU_FECHAMENTO and (ult[:10] != hoje or ult[11:16] < "17:30"):
        quando = f"{ult[8:10]}/{ult[5:7]} às {ult[11:13]}h{ult[14:16]}" if ult else "nunca"
        alerta("cotacoes paradas", f"As cotações automáticas dos apps não atualizaram até o fechamento de hoje. "
               f"A última atualização foi em {quando}. (Se hoje foi feriado na B3, pode ignorar.)", True)

def confere_intervalo():
    if TESTE:
        return
    s = db().collection("config").document("ultima_execucao").get()
    if not s.exists:
        return
    ant = (s.to_dict() or {}).get("inicio") or ""
    try:
        horas = (AGORA - dt.datetime.fromisoformat(ant)).total_seconds() / 3600
    except Exception:
        return
    if horas > 14:
        alerta("intervalo", f"O robô de notícias ficou {br_num(horas, 0)} horas sem rodar (a última rodada antes desta foi em "
               f"{ant[8:10]}/{ant[5:7]} às {ant[11:13]}h{ant[14:16]}). Ele deveria rodar às 7h30 e às 19h.", True)

ERRO_GRAVE = re.compile(r"credit|billing|balance|authentication|unauthorized|permission|invalid x-api-key|401|403", re.I)

def envia_alertas():
    if INFORMES:
        telegram("ℹ️ Robô de notícias\n\n" + "\n\n".join("• " + i for i in INFORMES))
    if TESTE:
        for a in ALERTAS:
            log("  [alerta]", a)
        return
    ref = db().collection("config").document("alertas")
    snap = ref.get()
    st = snap.to_dict() if snap.exists else {}
    cont_ant, enviados = st.get("contagem") or {}, st.get("enviados") or {}
    cont, msgs = {}, []
    for chave, texto, imediato in ALERTAS:
        n = cont_ant.get(chave, 0) + 1
        cont[chave] = n
        if not imediato and n < 2:
            continue
        ult = (enviados.get(chave) or {}).get("em", "")
        if ult and (AGORA - dt.datetime.fromisoformat(ult)).total_seconds() < 20 * 3600:
            continue
        msgs.append(texto)
        enviados[chave] = {"em": AGORA.isoformat(timespec="seconds"), "texto": texto[:200]}
    resolvidos = [k for k in list(enviados) if k not in cont and (k != "cotacoes paradas" or CHECOU_FECHAMENTO)]
    for k in resolvidos:
        msgs.append("✅ Normalizou: " + enviados.pop(k)["texto"])
    if msgs:
        probs = [m for m in msgs if not m.startswith("✅")]
        cab = "⚠️ Robô de notícias: algo fora do esperado" if probs else "✅ Robô de notícias"
        rod = "\n\nMande esta mensagem para o Claude (no chat da carteira do Flávio) que ele resolve." if probs else ""
        telegram(cab + "\n\n" + "\n\n".join("• " + m for m in msgs) + rod)
    ref.set({"contagem": cont, "enviados": enviados, "atualizado": AGORA.isoformat(timespec="seconds")})

# ---------------------------------------------------------------- principal
def recomeca_do_zero():
    for col in ("noticias", "feeds"):
        while True:
            docs = list(db().collection(col).limit(400).stream())
            if not docs:
                break
            lote = db().batch()
            for d in docs:
                lote.delete(d.reference)
            lote.commit()
    for snap in db().collection("ativos").stream():
        snap.reference.update({"portais_em": ""})

def ja_rodou_hoje():
    """O horario automatico do GitHub atrasa muito: se o despertador ja rodou este turno hoje, a rodada atrasada nao repete."""
    if TESTE or os.environ.get("GITHUB_EVENT_NAME") != "schedule":
        return False
    s = db().collection("config").document("ultima_execucao").get()
    d = s.to_dict() if s.exists else {}
    feitos = d.get("turnos_do_dia") or {}
    return feitos.get(TURNO) == AGORA.date().isoformat()

def main():
    inicio = time.time()
    if ja_rodou_hoje():
        log(f"turno {TURNO} ja rodou hoje; rodada agendada atrasada ignorada")
        return
    if os.environ.get("REPROCESSAR_RENDIMENTOS") == "1" and not TESTE:
        for snap in db().collection("noticias").where("tipo", "==", "Rendimento").stream():
            snap.reference.delete()
        log("rendimentos apagados para reprocessar")
    if os.environ.get("RESET") == "1" and not TESTE:
        recomeca_do_zero()
        log("base de noticias zerada")
    erros, novos = [], []
    cadastro = {k: v for k, v in json.load(open(os.path.join(AQUI, "ativos.json"), encoding="utf-8")).items()
                if not k.startswith("_")}
    por_ativo = {}
    for cli, url in CLIENTES.items():
        try:
            for t in tickers_do_app(url):
                por_ativo.setdefault(t, []).append(cli)
        except Exception as e:
            erros.append(f"carteira {cli}: {e}")
    ativos = sorted(por_ativo)
    for cli in CLIENTES:
        n = sum(1 for cs in por_ativo.values() if cli in cs)
        if n < 3:
            alerta("carteira vazia " + cli, f"Só achei {n} ativos no app do cliente {cli}. O app pode ter mudado de formato ou estar fora do ar.", True)
    try:
        cadastro.update({k: v for k, v in cadastro_salvo().items() if k not in cadastro})
    except Exception as e:
        erros.append(f"cadastro salvo: {e}")
    sem_cadastro = [t for t in ativos if t not in cadastro]
    if TESTE and os.environ.get("CADASTRO_TESTE"):
        teste_cad = {}
        cadastra_novos([x.strip().upper() for x in os.environ["CADASTRO_TESTE"].split(",") if x.strip()], teste_cad)
        print("::notice::CADASTRO " + json.dumps(teste_cad, ensure_ascii=False))
        print("::notice::INFORMES " + " | ".join(INFORMES))
        return
    if sem_cadastro:
        cadastra_novos(sem_cadastro, cadastro)
    logos_faltando(cadastro, ativos)
    confere_cotacoes()
    try:
        confere_intervalo()
    except Exception as e:
        erros.append(f"intervalo: {e}")
    desde = (AGORA.date() - dt.timedelta(days=JANELA_DIAS)).isoformat()
    log(f"turno {TURNO} | portais {BUSCAR_PORTAIS} | {len(ativos)} ativos | desde {desde} | limite US$ {LIMITE_USD}")

    # 1) fontes oficiais
    for t in ativos:
        info = cadastro.get(t)
        if not info or info.get("tipo") not in ("fii", "acao"):
            continue
        try:
            antes = len(novos)
            if info["tipo"] == "fii":
                fontes_fii(t, info, desde, novos)
            else:
                fontes_acao(t, info, desde, novos)
            log(f"{t}: oficiais +{len(novos) - antes}")
        except Exception as e:
            erros.append(f"{t} oficial: {e}")
            traceback.print_exc()

    # 2) portais (comeca pelos ativos buscados ha mais tempo, para revezar se o limite cortar)
    if BUSCAR_PORTAIS and not SO_RENDIMENTOS:
        estados = {t: estado_ativo(t) for t in ativos}
        limite_portais = (AGORA - dt.timedelta(hours=18)).isoformat(timespec="seconds")
        ordem = sorted((t for t in ativos if estados[t].get("portais_em", "") < limite_portais),
                       key=lambda t: estados[t].get("portais_em", ""))
        desde_portais = (AGORA.date() - dt.timedelta(days=2)).isoformat()
        for t in ordem:
            info = cadastro.get(t) or {"nome": t}
            if CUSTO.parou_no_limite:
                break
            try:
                antes = len(novos)
                fontes_portais(t, info, desde_portais, novos)
                if not CUSTO.parou_no_limite:
                    salva_estado_ativo(t, {"portais_em": AGORA.isoformat(timespec="seconds")})
                log(f"{t}: portais +{len(novos) - antes} | gasto ate agora US$ {CUSTO.usd:.4f}")
            except Exception as e:
                erros.append(f"{t} portais: {e}")
                traceback.print_exc()

    try:
        removidas = limpa_opiniao()
        if removidas:
            log(f"removidas {removidas} materias de recomendacao de analistas")
    except Exception as e:
        erros.append(f"limpeza: {e}")

    # 3) feed de cada cliente (um documento por cliente, lido pelo app)
    if not TESTE:
        for cli in CLIENTES:
            try:
                atualiza_feed(cli, sorted(t for t, cs in por_ativo.items() if cli in cs))
            except Exception as e:
                erros.append(f"feed {cli}: {e}")
                traceback.print_exc()

    # 4) avisos e registro
    importantes = [n for n in novos if n.get("importante")]
    if os.environ.get("SEM_AVISO") != "1":
        for n in importantes:
            avisa_telegram(n)
    if CUSTO.parou_no_limite:
        erros.append(f"limite de US$ {br_num(LIMITE_USD)} atingido; os ativos restantes ficam para a proxima rodada")
        alerta("limite", f"O limite de gasto por rodada (US$ {br_num(LIMITE_USD)}) foi atingido de novo e alguns ativos ficaram para depois. "
               "Talvez seja hora de aumentar o limite.")
    for e in erros:
        if not e.startswith("limite de US$"):
            alerta("erro " + e[:70], "Erro: " + e[:300], bool(ERRO_GRAVE.search(e)))
    if FALHAS_IA:
        grave = any(ERRO_GRAVE.search(f) for f in FALHAS_IA)
        alerta("ia", f"A IA falhou em {len(FALHAS_IA)} resumo(s) nesta rodada. Exemplo: {FALHAS_IA[0][:200]}"
               + (" Parece ser problema de crédito ou da chave da API." if grave else ""), grave)
    reg = {"inicio": AGORA.isoformat(timespec="seconds"), "turno": TURNO, "portais": BUSCAR_PORTAIS,
           "ativos": len(ativos), "clientes": list(CLIENTES), "novas": len(novos), "importantes": len(importantes),
           "chamadas_ia": CUSTO.chamadas, "tokens_entrada": CUSTO.entrada, "tokens_saida": CUSTO.saida,
           "pesquisas_web": CUSTO.buscas, "custo_usd": round(CUSTO.usd, 4), "limite_usd": LIMITE_USD,
           "parou_no_limite": CUSTO.parou_no_limite, "duracao_s": round(time.time() - inicio, 1),
           "erros": erros[:30]}
    log(json.dumps(reg, ensure_ascii=False, indent=1))
    if not TESTE:
        db().collection("execucoes").document(AGORA.strftime("%Y-%m-%d_%H%M")).set(reg)
        try:
            s_ant = db().collection("config").document("ultima_execucao").get()
            turnos = dict((s_ant.to_dict() or {}).get("turnos_do_dia") or {}) if s_ant.exists else {}
        except Exception:
            turnos = {}
        if not SO_RENDIMENTOS:
            turnos[TURNO] = AGORA.date().isoformat()
        db().collection("config").document("ultima_execucao").set(dict(reg, turnos_do_dia=turnos))
    try:
        envia_alertas()
    except Exception as e:
        log("falha ao enviar alertas:", e)
        telegram("⚠️ Robô de notícias: não consegui processar os avisos desta rodada (" + str(e)[:200] + "). Mande para o Claude.")
    print(f"::notice::{len(novos)} novas, {len(importantes)} importantes, custo US$ {CUSTO.usd:.4f}, "
          f"{CUSTO.chamadas} chamadas, {CUSTO.buscas} pesquisas, erros: {len(erros)}")
    for e in erros[:10]:
        print("::warning::" + e[:300])
    if TESTE and TESTE_SAIDA:
        print("::notice::ITENS%0A" + "%0A".join(x.replace("%", "%25") for x in TESTE_SAIDA[:120]))

if __name__ == "__main__":
    main()
