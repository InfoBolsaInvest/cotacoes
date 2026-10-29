# REFERENCIA: codigo da aba "Noticias" do app do Flavio (CSS, HTML e JS). Para outro app, adaptar ao layout dele. Uso no app do Flavio: python3 noticias_aba.py src/base.html FEED_URL
import sys
arq, feed = sys.argv[1], sys.argv[2]
s = open(arq, encoding="utf-8").read()
if 'id="aba-noticias"' in s:
    import re
    s = re.sub(r"const FEED_URL = '[^']*';", "const FEED_URL = '" + feed + "';", s)
    open(arq, "w", encoding="utf-8").write(s)
    print("ja tinha a aba; FEED_URL atualizado")
    sys.exit()

def rep(old, new):
    global s
    assert s.count(old) == 1, old[:50]
    s = s.replace(old, new)

CSS = """
/* ---------- noticias ---------- */
.nt-topo{display:flex;justify-content:space-between;align-items:flex-end;gap:16px;flex-wrap:wrap;margin-bottom:18px}
.nt-atual{color:var(--ink-3);font-size:13px}
.nt-dest{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin-bottom:22px;align-items:start}
.nt-dest-tit{display:flex;align-items:center;gap:8px;font-size:13px;font-weight:700;letter-spacing:.5px;text-transform:uppercase;color:var(--accent);margin:0 0 10px}
.nt-dest-tit svg{width:16px;height:16px}
.nt-filtros{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin:0 0 16px}
.nt-sel{font-family:inherit;font-size:14px;padding:8px 12px;border-radius:999px;border:1px solid var(--border);background:var(--surface);color:var(--ink);font-weight:600}
.nt-sel option{color:#132526}
.nt-chips{display:flex;gap:8px;flex-wrap:wrap}
.nt-chips .chip.on{background:#FFB400;color:#162526;border-color:#FFB400}
.nt-cont{color:var(--ink-3);font-size:13px;margin-left:auto}
.nt-dia{font-size:13px;font-weight:700;color:var(--ink-2);text-transform:uppercase;letter-spacing:.5px;margin:18px 0 10px;padding-bottom:6px;border-bottom:1px solid var(--border)}
.nt-lista{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;align-items:start}
.nt-item{--tc:#5B6B78;background:var(--surface);-webkit-backdrop-filter:blur(6px);backdrop-filter:blur(6px);border:1px solid var(--border);border-left:3px solid var(--tc);border-radius:14px;padding:16px 18px;box-shadow:var(--shadow);display:grid;grid-template-columns:48px 1fr;gap:14px;align-items:start;min-width:0}
.nt-t-fato{--tc:#6D4AD6} .nt-t-com{--tc:#1F6FA8} .nt-t-rel{--tc:#0F8577} .nt-t-not{--tc:#5B6B78} .nt-rend{--tc:var(--accent)}
:root[data-theme="dark"] .nt-t-fato{--tc:#B39DFF} :root[data-theme="dark"] .nt-t-com{--tc:#6CB8F0}
:root[data-theme="dark"] .nt-t-rel{--tc:#4FD1C5} :root[data-theme="dark"] .nt-t-not{--tc:#A9B6C2}
.nt-imp{border-color:rgba(255,180,0,.55);border-left-color:var(--accent);background:var(--accent-soft)}
.nt-logo{position:relative;overflow:hidden;width:48px;height:48px;border-radius:12px;display:grid;place-items:center;font-weight:800;font-size:12.5px;letter-spacing:.3px}
.nt-logo img{position:absolute;inset:0;width:100%;height:100%;display:block}
.nt-meta{display:flex;gap:8px;align-items:center;flex-wrap:wrap;font-size:12.5px;color:var(--ink-3);margin-bottom:4px}
.nt-meta .tk{color:var(--ink);font-size:14px;font-weight:700}
.nt-tipo{display:inline-flex;align-items:center;gap:5px;padding:2px 9px 2px 7px;border-radius:999px;color:var(--tc);background:color-mix(in srgb,var(--tc) 14%,transparent);font-weight:700;font-size:11.5px}
.nt-tipo svg,.nt-flag svg{width:13px;height:13px;flex:none}
.nt-flag{display:inline-flex;align-items:center;gap:5px;padding:2px 9px 2px 7px;border-radius:999px;background:var(--accent);color:#162526;font-weight:700;font-size:11.5px}
.nt-fonte{font-weight:700;color:var(--ink-2)}
.nt-item h4{margin:2px 0 6px;font-size:15.5px;line-height:1.35}
.nt-t-not h4{font-size:16px}
.nt-item p{margin:0 0 8px;color:var(--ink-2);font-size:14px;line-height:1.5}
.nt-t-rel p{font-size:13.5px}
.nt-link{font-size:13px;font-weight:600;color:var(--accent);text-decoration:none}
.nt-link:hover{text-decoration:underline}
.nt-var{font-weight:700}
.nt-rv{display:flex;align-items:baseline;gap:6px 10px;flex-wrap:wrap;margin:6px 0 10px}
.nt-rv-num{font-size:25px;font-weight:800;letter-spacing:-.3px;color:var(--ink);line-height:1.1}
.nt-rv-un{color:var(--ink-3);font-size:13px;font-weight:600}
.nt-rv-bruto{color:var(--ink-3);font-size:12.5px}
.nt-pill{display:inline-block;padding:2px 8px;border-radius:999px;font-size:11.5px;font-weight:700;background:var(--surface-2);color:var(--ink-2)}
.nt-pill.pos{color:var(--pos);background:color-mix(in srgb,var(--pos) 14%,transparent)}
.nt-pill.neg{color:var(--neg);background:color-mix(in srgb,var(--neg) 14%,transparent)}
.nt-pill.acc{color:var(--accent);background:var(--accent-soft)}
.nt-rs{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-bottom:10px}
.nt-rs div{background:var(--surface-2);border-radius:10px;padding:8px 10px;min-width:0}
.nt-rs span{display:block;font-size:11px;color:var(--ink-3);font-weight:700;text-transform:uppercase;letter-spacing:.3px;margin-bottom:2px}
.nt-rs b{font-size:14.5px;white-space:nowrap}
.nt-rs i{font-style:normal}
.nt-voce{display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;border:1px solid color-mix(in srgb,var(--accent) 45%,transparent);background:var(--accent-soft);border-radius:10px;padding:9px 12px;margin-bottom:8px;font-size:13.5px;color:var(--ink-2)}
.nt-voce b{color:var(--ink)}
.nt-voce .v{font-size:18px;font-weight:800;color:var(--accent);white-space:nowrap}
.nt-nota{display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;font-size:12.5px;color:var(--ink-3)}
.nt-frase{font-size:13px !important;color:var(--ink-3) !important;margin:0 0 8px !important}
.nt-vazio{color:var(--ink-3);padding:24px 0}
.nt-mais{display:block;margin:18px auto 0}
.nt-rodape{color:var(--ink-3);font-size:12.5px;margin-top:22px}
@media (max-width:1100px){ .nt-dest{grid-template-columns:1fr 1fr} }
@media (max-width:820px){ .nt-lista,.nt-dest{grid-template-columns:1fr} .nt-cont{margin-left:0;width:100%} }
@media (max-width:560px){ .nt-item{grid-template-columns:40px 1fr;gap:10px;padding:14px} .nt-logo{width:40px;height:40px;font-size:11px} .nt-rs b{font-size:13.5px} .nt-rs div{padding:7px 8px} .nt-rs i{display:none} }
"""

SECAO = """
<!-- ===================== NOTICIAS ===================== -->
<section class="aba" id="aba-noticias">
  <div class="nt-topo">
    <div>
      <h2 class="titulo">Notícias dos seus ativos</h2>
      <p class="sub" style="margin:0">Comunicados oficiais e notícias sobre os ativos da sua carteira, atualizados todos os dias às 7h30 e às 19h.</p>
    </div>
    <div class="nt-atual" id="ntAtual"></div>
  </div>
  <div id="ntDestWrap" style="display:none"><p class="nt-dest-tit"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.7 21a2 2 0 0 1-3.4 0"/></svg>Destaques importantes</p><div class="nt-dest" id="ntDest"></div></div>
  <div class="nt-filtros">
    <select class="nt-sel" id="ntAtivo" aria-label="Filtrar por ativo"></select>
    <div class="nt-chips" id="ntTipos"></div>
    <span class="nt-cont" id="ntCont"></span>
  </div>
  <div id="ntLista"></div>
  <button class="chip nt-mais" id="ntMais" type="button" style="display:none">Mostrar mais</button>
  <p class="nt-rodape">Fontes oficiais: CVM e B3 (Fundos.NET), além de portais de notícias. Resumos preparados pela InfoBolsa Investimentos, com o link para o documento original em cada item. Conteúdo informativo, sem recomendação de compra ou venda.</p>
</section>
"""

JS = """
/* ---------- noticias dos ativos ---------- */
const FEED_URL = '__FEED__';
const NT_CORES = {
  ITSA4:['#00205B','#fff'], PETR4:['#008542','#FFD100'], BBSE3:['#FCF800','#465EFF'], BBAS3:['#FCF800','#465EFF'],
  SAPR4:['#0072BC','#fff'], SBSP3:['#005CA9','#fff'], BMGB4:['#FF6A13','#fff'], CPLE3:['#0D3B66','#fff'],
  WEGE3:['#00579D','#fff'], CXSE3:['#005CA9','#F39200'], BRAP3:['#CC092F','#fff'], KLBN3:['#00863C','#fff'],
  CMIG4:['#00A65D','#fff'], GOAU4:['#003DA5','#FFD200'], HGLG11:['#0B2341','#fff'], JPPA11:['#1C2D4A','#fff'],
  RZAK11:['#111111','#fff'], MXRF11:['#000000','#FFC709'], KNCR11:['#003865','#fff'], VGIR11:['#0E2F4D','#fff'],
  VGIP11:['#0E2F4D','#fff'], VGIA11:['#0E2F4D','#fff'], MCRE11:['#00467F','#fff'], VISC11:['#00314D','#fff'],
  BTCI11:['#0D2240','#fff'], FGAA11:['#003B4A','#fff'], XPCA11:['#000000','#FFC709'], OIAG11:['#8A6A12','#fff'],
  RURA11:['#EC7000','#fff']
};
const NT_TIPOS = [['Todos','Todos'],['Fato relevante','Fato relevante'],['Comunicado','Comunicado'],['Rendimento','Proventos'],['Relatório gerencial','Relatório gerencial'],['Notícia','Notícia']];
const NT_LOGO_URL = 'https://cdn.jsdelivr.net/gh/InfoBolsaInvest/cotacoes@main/logos/';
const NT_QTD = {};
(DATA.ativos||[]).forEach(a=>{ if (a.qtd && (a.classe==='acoes' || a.classe==='fiis')) NT_QTD[a.ticker] = (NT_QTD[a.ticker]||0) + Number(a.qtd); });
const NT_SVG = p => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${p}</svg>`;
const NT_ICO = {
  'Fato relevante': NT_SVG('<path d="M13 2 4 14h7l-1 8 9-12h-7z"/>'),
  'Comunicado': NT_SVG('<path d="M3 10v4h4l6 4V6L7 10z"/><path d="M16.5 8.5a5 5 0 0 1 0 7"/>'),
  'Rendimento': NT_SVG('<circle cx="12" cy="12" r="9"/><path d="M14.8 9.2c-.5-.9-1.5-1.4-2.8-1.4-1.6 0-2.7.8-2.7 2s1.1 1.7 2.7 2 2.8.8 2.8 2.1-1.2 2.1-2.8 2.1c-1.4 0-2.4-.6-2.9-1.5M12 6.3v1.5M12 16.2v1.5"/>'),
  'Relatório gerencial': NT_SVG('<path d="M14 3H6.5A1.5 1.5 0 0 0 5 4.5v15A1.5 1.5 0 0 0 6.5 21h11a1.5 1.5 0 0 0 1.5-1.5V8z"/><path d="M14 3v5h5M9 13h6M9 17h6"/>'),
  'Notícia': NT_SVG('<path d="M4 5h13v14H5.5A1.5 1.5 0 0 1 4 17.5z"/><path d="M17 9h3v8.5a1.5 1.5 0 0 1-1.5 1.5H17M7.5 9h6M7.5 12.5h6M7.5 16h3.5"/>'),
  sino: NT_SVG('<path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.7 21a2 2 0 0 1-3.4 0"/>')
};
const NT_CLS = {'Fato relevante':'nt-t-fato','Comunicado':'nt-t-com','Relatório gerencial':'nt-t-rel','Notícia':'nt-t-not','Rendimento':'nt-rend'};
let ntItens = [], ntAtivoSel = 'todos', ntTipoSel = 'Todos', ntQtd = 30;
const ntIso = d => d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');
const ntHoje = () => ntIso(new Date());
const ntDiaLabel = iso => { const on = ntIso(new Date(Date.now()-864e5)); return iso === ntHoje() ? 'Hoje' : iso === on ? 'Ontem' : iso.slice(8,10)+'/'+iso.slice(5,7)+'/'+iso.slice(0,4); };
const ntData = d => d ? d.slice(8,10)+'/'+d.slice(5,7)+'/'+d.slice(0,4) + (d.length > 10 ? ' às '+d.slice(11,13)+'h'+d.slice(14,16) : '') : '';
const ntCurta = d => d ? d.slice(8,10)+'/'+d.slice(5,7)+'/'+d.slice(0,4) : 'A definir';
const ntCasas = v => { for (const c of [2,3,4]) if (Math.abs(Math.round(v*10**c)/10**c - v) < 1e-9) return c; return 4; };
const ntRS = v => 'R$ ' + fNum(v, ntCasas(v));
const ntFii = t => /11$/.test(t);
function ntLogo(t){
  const c = NT_CORES[t] || ['#2F6F66','#fff'];
  const img = ntFii(t) ? '' : `<img src="${NT_LOGO_URL}${encodeURIComponent(t)}.svg" alt="" loading="lazy" onerror="this.remove()">`;
  return `<div class="nt-logo" style="background:${c[0]};color:${c[1]}">${esc(t.replace(/\\d+$/,''))}${img}</div>`;
}
function ntTag(n, rotulo){ return `<span class="nt-tipo">${NT_ICO[n.tipo]||''}${esc(rotulo||n.tipo)}</span>`; }
function ntFlag(n){ return n.importante ? `<span class="nt-flag">${NT_ICO.sino}${esc(n.motivo||'Destaque')}</span>` : ''; }
function ntStatus(ps){
  const h = ntHoje(), p = ps[0];
  if (p.pagamento && p.pagamento <= h) return '<span class="nt-pill pos">Pago</span>';
  if (p.data_com && p.data_com < h) return '<span class="nt-pill acc">A receber</span>';
  if (p.data_com === h) return '<span class="nt-pill acc">Data com hoje</span>';
  if (p.data_com){ const dias = Math.round((new Date(p.data_com+'T12:00') - new Date(h+'T12:00'))/864e5);
    return `<span class="nt-pill">Data com em ${dias} ${dias===1?'dia':'dias'}</span>`; }
  return '';
}
function ntRendCard(n){
  const ps = n.proventos, fii = ntFii(n.ticker), un = fii ? ['cota','cotas'] : ['ação','ações'];
  const tipos = [...new Set(ps.map(p=>p.tipo))], jcp = ps.some(p=>p.tipo==='JCP');
  let corpo = '';
  ps.forEach(p=>{
    const liq = p.tipo==='JCP' ? p.valor_liquido : p.valor_bruto;
    const ehJ = p.tipo==='JCP';
    let comp = '';
    if (typeof n.variacao === 'number' && ps.length === 1)
      comp = n.variacao === 0 ? '<span class="nt-pill">Igual ao anterior</span>'
           : `<span class="nt-pill ${n.variacao>0?'pos':'neg'}">${fSig(n.variacao)} vs anterior</span>`;
    corpo += `<div class="nt-rv"><span class="nt-rv-num">${ntRS(liq)}</span><span class="nt-rv-un">por ${un[0]}${ehJ?' (líquido)':''}${ps.length>1?' em '+esc(p.tipo):''}</span>${ehJ?`<span class="nt-rv-bruto">bruto ${ntRS(p.valor_bruto)}</span>`:''}${comp}</div>
      <div class="nt-rs"><div><span>Data com</span><b>${ntCurta(p.data_com)}</b></div><div><span>Pagamento</span><b>${ntCurta(p.pagamento)}</b></div>
      <div${p.preco_ref?` title="Calculado pelo preço de ${ntRS(p.preco_ref)}"`:''}><span>DY<i> do pagamento</i></span><b>${typeof p.dy==='number'?fPct(p.dy):'A definir'}</b></div></div>`;
  });
  const q = NT_QTD[n.ticker];
  if (q){
    const tot = ps.reduce((s,p)=>s + (p.tipo==='JCP' ? p.valor_liquido : p.valor_bruto) * q, 0);
    corpo += `<div class="nt-voce"><span>Com as suas <b>${fNum(q,0)} ${q===1?un[0]:un[1]}</b></span><span class="v">${fBRL(tot)}</span></div>`;
  }
  const nota = fii ? 'Isento de IR para pessoa física' : jcp ? 'JCP já com desconto de 17,5% de IR' + (ps.some(p=>p.liquido_estimado)?' (estimado)':'') : 'Dividendo isento de IR';
  const frase = !fii && n.resumo ? `<p class="nt-frase">${esc(n.resumo)}</p>` : '';
  return `<article class="nt-item nt-rend${n.importante?' nt-imp':''}">${ntLogo(n.ticker)}<div style="min-width:0">
    <div class="nt-meta"><span class="tk">${esc(n.ticker)}</span>${ntTag(n, tipos.join(' e '))}${ntStatus(ps)}${ntFlag(n)}</div>
    ${corpo}${frase}<div class="nt-nota"><span>${nota} · anunciado em ${ntData((n.data||'').slice(0,10))}</span>
    <a class="nt-link" href="${encodeURI(n.link)}" target="_blank" rel="noopener">Ver aviso oficial</a></div></div></article>`;
}
function ntCard(n){
  if (n.tipo === 'Rendimento' && Array.isArray(n.proventos) && n.proventos.length) return ntRendCard(n);
  const v = (typeof n.variacao === 'number' && n.variacao !== 0) ? ` <span class="nt-var ${n.variacao>0?'pos':'neg'}">${fSig(n.variacao)}</span>` : '';
  const noticia = n.tipo === 'Notícia';
  const rot = noticia ? 'Ler a notícia completa' : n.tipo === 'Relatório gerencial' ? 'Abrir o relatório' : 'Ver documento oficial';
  const fonte = noticia ? `<span class="nt-fonte">${esc(n.fonte||'')}</span>` : `<span>${esc(n.fonte||'')}</span>`;
  return `<article class="nt-item ${NT_CLS[n.tipo]||''}${n.importante?' nt-imp':''}">${ntLogo(n.ticker)}<div style="min-width:0">
    <div class="nt-meta"><span class="tk">${esc(n.ticker)}</span>${ntTag(n)}${ntFlag(n)}<span>${ntData(n.data)}</span></div>
    <h4>${esc(n.titulo)}${v}</h4><p>${esc(n.resumo)}</p>
    <div class="nt-nota">${fonte}<a class="nt-link" href="${encodeURI(n.link)}" target="_blank" rel="noopener">${rot}</a></div></div></article>`;
}
function ntRender(){
  const lim = new Date(Date.now()-30*864e5).toISOString().slice(0,10);
  const dest = ntItens.filter(n=>n.importante && (n.data||'') >= lim).slice(0,6);
  $('ntDestWrap').style.display = dest.length ? '' : 'none';
  $('ntDest').innerHTML = dest.map(ntCard).join('');
  const lista = ntItens.filter(n => (ntAtivoSel==='todos' || n.ticker===ntAtivoSel) && (ntTipoSel==='Todos' || n.tipo===ntTipoSel));
  $('ntCont').textContent = lista.length + (lista.length===1 ? ' item' : ' itens');
  if (!lista.length){ $('ntLista').innerHTML = '<p class="nt-vazio">Nenhuma novidade encontrada com esse filtro.</p>'; $('ntMais').style.display='none'; return; }
  let html = '', dia = null, aberto = false;
  lista.slice(0, ntQtd).forEach(n=>{ const d = (n.data||'').slice(0,10);
    if (d !== dia){ if (aberto) html += '</div>'; html += `<div class="nt-dia">${ntDiaLabel(d)}</div><div class="nt-lista">`; dia = d; aberto = true; }
    html += ntCard(n); });
  if (aberto) html += '</div>';
  $('ntLista').innerHTML = html;
  $('ntMais').style.display = lista.length > ntQtd ? '' : 'none';
}
function ntChips(el, opts, get, set){
  $(el).innerHTML = opts.map(o=>`<button type="button" class="chip ${get()===o[0]?'on':''}" data-v="${o[0]}">${o[1]}</button>`).join('');
  $(el).querySelectorAll('.chip').forEach(c=>c.addEventListener('click',()=>{ set(c.dataset.v); ntChips(el, opts, get, set); }));
}
function ntFiltros(){
  const tks = [...new Set(ntItens.map(n=>n.ticker))].sort();
  $('ntAtivo').innerHTML = '<option value="todos">Todos os ativos</option>' + tks.map(t=>`<option value="${t}">${t}</option>`).join('');
  $('ntAtivo').value = tks.includes(ntAtivoSel) ? ntAtivoSel : 'todos';
  ntChips('ntTipos', NT_TIPOS, ()=>ntTipoSel, v=>{ ntTipoSel = v; ntQtd = 30; ntRender(); });
}
$('ntAtivo').addEventListener('change', e=>{ ntAtivoSel = e.target.value; ntQtd = 30; ntRender(); });
$('ntMais').addEventListener('click', ()=>{ ntQtd += 30; ntRender(); });
function ntAplica(feed){
  ntItens = feed.itens || [];
  $('ntAtual').textContent = feed.atualizado ? 'Atualizado em ' + ntData(feed.atualizado.slice(0,16)) : '';
  ntFiltros(); ntRender();
}
async function ntCarrega(){
  try{ const c = JSON.parse(localStorage.getItem('noticias_feed')||'null'); if (c) ntAplica(c); }catch(e){}
  if (!FEED_URL){ if (!ntItens.length){ $('ntLista').innerHTML = '<p class="nt-vazio">As notícias dos seus ativos aparecem aqui em breve.</p>'; ntChips('ntTipos', NT_TIPOS, ()=>ntTipoSel, ()=>{}); $('ntAtivo').innerHTML='<option>Todos os ativos</option>'; } return; }
  try{
    const r = await fetch(FEED_URL + (FEED_URL.includes('?')?'&':'?') + 't=' + Date.now(), {cache:'no-store'});
    if (!r.ok) throw new Error(r.status);
    const j = await r.json(), f = j.fields || {};
    const feed = {atualizado: (f.atualizado||{}).stringValue || '', itens: JSON.parse((f.itens_json||{}).stringValue || '[]')};
    try{ localStorage.setItem('noticias_feed', JSON.stringify(feed)); }catch(e){}
    ntAplica(feed);
  }catch(e){ if (!ntItens.length) $('ntLista').innerHTML = '<p class="nt-vazio">Não foi possível carregar as notícias agora. Tente novamente em alguns minutos.</p>'; }
}
ntCarrega();
setInterval(ntCarrega, 60*60*1000);
"""

rep('    <button type="button" data-aba="estado" class="ativa">Carteira</button>\n',
    '    <button type="button" data-aba="estado" class="ativa">Carteira</button>\n    <button type="button" data-aba="noticias">Notícias</button>\n')
rep("@media print{", CSS + "@media print{")
rep("</main>", SECAO + "</main>")
rep("</script>\n</body>", JS.replace("__FEED__", feed) + "</script>\n</body>")
open(arq, "w", encoding="utf-8").write(s)
print("aba criada")
