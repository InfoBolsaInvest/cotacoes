import json, os, time, urllib.request, urllib.parse, datetime

UA = {'User-Agent': 'Mozilla/5.0 (cotacoes InfoBolsa)'}
B3 = 'https://cotacao.b3.com.br/mds/api/v1/instrumentQuotation/{}'
BRAPI = 'https://brapi.dev/api/quote/{}?token={}'
TOKEN = os.environ.get('BRAPI_TOKEN', '').strip()

def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode('utf-8'))

def acha(obj, chave):
    if isinstance(obj, dict):
        if chave in obj:
            return obj[chave]
        for v in obj.values():
            x = acha(v, chave)
            if x is not None:
                return x
    elif isinstance(obj, list):
        for v in obj:
            x = acha(v, chave)
            if x is not None:
                return x
    return None

def da_b3(t):
    d = get(B3.format(t))
    preco = acha(d, 'curPrc')
    if preco in (None, 0):
        return None
    var = acha(d, 'prcFlcn')
    hora = acha(d, 'dtTm')
    return {'preco': round(float(preco), 2),
            'var_dia': round(float(var), 2) if var is not None else None,
            'hora_fonte': hora, 'fonte': 'B3'}

def da_brapi(t):
    if not TOKEN:
        return None
    d = get(BRAPI.format(t, TOKEN))
    r = (d.get('results') or [{}])[0]
    preco = r.get('regularMarketPrice')
    if not preco:
        return None
    var = r.get('regularMarketChangePercent')
    return {'preco': round(float(preco), 2),
            'var_dia': round(float(var), 2) if var is not None else None,
            'hora_fonte': r.get('regularMarketTime'), 'fonte': 'brapi'}

tickers = []
for linha in open('tickers.txt', encoding='utf-8'):
    linha = linha.split('#')[0].strip().upper()
    if linha and linha not in tickers:
        tickers.append(linha)

try:
    antigo = json.load(open('cotacoes.json', encoding='utf-8'))
except Exception:
    antigo = {'ativos': {}}

ativos = {}
falhas = []
motivos = {}
for t in tickers:
    q = None
    for tentativa in range(3):
        for fonte in (da_b3, da_brapi):
            try:
                q = fonte(t)
                if not q:
                    motivos[t] = fonte.__name__ + ': sem preco'
            except Exception as e:
                q = None
                motivos[t] = fonte.__name__ + ': ' + str(e)[:120]
            if q:
                break
        if q:
            motivos.pop(t, None)
            break
        time.sleep(3)
    if q:
        q['atualizado'] = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-3))).strftime('%Y-%m-%dT%H:%M')
        ativos[t] = q
    else:
        falhas.append(t)
        if t in antigo.get('ativos', {}):
            ativos[t] = antigo['ativos'][t]
    time.sleep(0.4)

agora = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-3))).strftime('%Y-%m-%dT%H:%M')
# ativo sem cotacao por mais de 1 hora: costuma ser troca de codigo, grupamento ou saida da bolsa
falha_desde = {t: antigo.get('falha_desde', {}).get(t, agora) for t in falhas}
avisados = [t for t in antigo.get('avisados', []) if t in falhas]
novos_aviso = [t for t in falhas if t not in avisados and len(falhas) < len(tickers)
               and (datetime.datetime.fromisoformat(agora) - datetime.datetime.fromisoformat(falha_desde[t])).total_seconds() >= 3600]
if novos_aviso:
    tok, chat = os.environ.get('TELEGRAM_TOKEN'), os.environ.get('TELEGRAM_CHAT_ID')
    if tok and chat:
        texto = ('\u26a0\ufe0f Robô de cotações: ' + ', '.join(novos_aviso) + ' sem cotação há mais de 1 hora. '
                 'Pode ser troca de código, grupamento ou saída da bolsa. '
                 'Mande esta mensagem para o Claude (no chat da carteira do Flávio) que ele confere.')
        try:
            urllib.request.urlopen('https://api.telegram.org/bot' + tok + '/sendMessage',
                                   data=urllib.parse.urlencode({'chat_id': chat, 'text': texto}).encode(), timeout=20)
            avisados += novos_aviso
        except Exception as e:
            print('telegram falhou:', e)
saida = {'atualizado': agora, 'ativos': ativos, 'falhas': falhas, 'motivos': motivos,
         'falha_desde': falha_desde, 'avisados': avisados}
json.dump(saida, open('cotacoes.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1, sort_keys=True)
print('ok', len(tickers) - len(falhas), 'atualizados; falhas:', motivos)
if len(falhas) == len(tickers):
    raise SystemExit('nenhuma cotacao obtida')
