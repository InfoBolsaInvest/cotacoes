import json, urllib.request, urllib.parse, ssl
def get(url, data=None, headers=None):
    h = {'User-Agent': 'Mozilla/5.0 (compatible; InfoBolsa-noticias/1.0)'}
    h.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=h)
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.status, r.headers.get('content-type'), r.read()
tests = {
 'fnet_lista': ('https://fnet.bmfbovespa.com.br/fnet/publico/pesquisarGerenciadorDocumentosDados?d=0&s=0&l=5&o%5B0%5D%5BdataEntrega%5D=desc&cnpjFundo=97521225000125', None, None),
 'fnet_doc': ('https://fnet.bmfbovespa.com.br/fnet/publico/exibirDocumento?id=1335757', None, None),
 'fnet_pdf': ('https://fnet.bmfbovespa.com.br/fnet/publico/downloadDocumento?id=1339341', None, None),
 'cvm_rad': ('https://www.rad.cvm.gov.br/ENET/frmConsultaExternaCVM.aspx/ListarDocumentos', json.dumps({'dataDe':'27/10/2026','dataAte':'28/10/2026','empresa':'','setorAtividade':'-1','categoriaEmissor':'-1','situacaoEmissor':'-1','tipoParticipante':'-1','dataReferencia':'','categoria':'IPE_-1_-1_-1','periodo':'2','horaIni':'','horaFim':'','palavraChave':'','ultimaDtRef':'false','tipoEmpresa':'0','token':'','versaoCaptcha':''}).encode(), {'Content-Type':'application/json; charset=utf-8'}),
 'cvm_pdf': ('https://www.rad.cvm.gov.br/ENET/frmDownloadDocumento.aspx?Tela=ext&numSequencia=1103588&numVersao=1&numProtocolo=1578882&descTipo=IPE&CodigoInstituicao=1', None, None),
 'app_flavio': ('https://carteiraflavio.netlify.app/', None, None),
}
for k,(u,d,h) in tests.items():
    try:
        s,ct,b = get(u,d,h); print(k, s, ct, len(b), b[:100])
    except Exception as e:
        print(k, 'ERRO', repr(e)[:200])
