# -*- coding: utf-8 -*-
"""Genera la version estatica del tablero para GitHub Pages (docs/).

Se ejecuta tras cada sincronizacion (sincronizar.bat / sincronizar_horaria.bat)
y al crear los PDFs (pdf_mensual.bat), y se sube con:
    python export_static.py  ->  crea docs/index.html + docs/pdf/*.pdf
La pagina queda publica en https://latinbienti-sys.github.io/embudoventas/

La pagina embebe todos los dias del cache (JSON) y el filtro Desde/Hasta se
aplica 100% en el navegador, sin servidor. (La version con botones +/- y
consulta viva sigue siendo el tablero local: http://127.0.0.1:8080)
"""
import json
import shutil
from datetime import date, datetime
from pathlib import Path

import dashboard_app
import store

BASE = Path(__file__).parent
SITE = BASE / "docs"
PDFS = SITE / "pdf"

MESES = {1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo", 6: "junio",
         7: "julio", 8: "agosto", 9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre"}

CSS = """
:root { --azul:#0f3b6e; --verde:#1e8e5a; --naranja:#e07b2a; --rojo:#8a1d1d; --gris:#eef1f5; --borde:#d3dae3; }
* { box-sizing: border-box; }
body { font-family: "Segoe UI", Arial, sans-serif; margin: 0; background: #f4f6f9; color: #1c2733; }
header { background: var(--azul); color: #fff; padding: 14px 22px; display:flex; align-items:center; gap:18px; flex-wrap:wrap; }
header h1 { font-size: 18px; margin: 0 0 2px; }
.sub { font-size: 12px; opacity: .85; }
main { padding: 20px; max-width: 1200px; margin: 0 auto; }
.barra { display:flex; gap:12px; align-items:center; flex-wrap:wrap; margin-bottom:16px; }
.barra input, .barra button, .barra select { font-size:14px; padding:7px 10px; border:1px solid var(--borde); border-radius:6px; }
.btn { background: var(--azul); color:#fff; border:none; cursor:pointer; }
.btn:hover { filter:brightness(1.1); }
.b { border-radius:6px; padding:2px 9px; font-size:13px; line-height:1.4; border:1px solid var(--borde); background:#fff; cursor:pointer; }
.tarjeta { background: #fff; border: 1px solid var(--borde); border-radius: 10px; padding: 16px; margin-bottom: 18px; }
.tarjeta h2 { margin: 0 0 12px; font-size: 15px; color: var(--azul); }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { border-bottom: 1px solid var(--gris); padding: 8px 10px; text-align: left; }
th { background: #f8fafc; color: #56657a; font-weight: 600; }
tr.total td { font-weight: 700; background: #f2f7ff; }
.num { text-align: center; font-variant-numeric: tabular-nums; }
.bar-fondo { background: var(--gris); border-radius: 8px; height: 16px; min-width: 80px; }
.bar-fondo > i { display:block; height: 16px; border-radius: 8px; background: var(--naranja); font-style: normal; color:#fff; font-size:10px; line-height:16px; padding-left:4px; }
a.pdf { display:inline-block; margin:0 6px 8px 0; padding:6px 12px; border:1px solid var(--borde); border-radius:6px; text-decoration:none; color:var(--azul); background:#fff; font-size:13px; }
.nota { font-size: 12px; color: #56657a; }
.aviso { color:var(--rojo); font-weight:600; }
.foot { color:#8a939c; font-size:12px; margin-top:10px; text-align:center; }
.pestanas { display:flex; flex-wrap:wrap; gap:6px; margin-bottom:14px; }
.pestanas button { border:1px solid var(--borde); background:#fff; border-radius:6px; padding:7px 13px; font-size:13px; cursor:pointer; color:#3a4a5c; }
.pestanas button.activa { background:var(--azul); color:#fff; border-color:var(--azul); font-weight:600; }
.graf-dia { display:flex; align-items:flex-end; gap:2px; height:120px; margin-top:8px; }
.graf-dia .col { flex:1; display:flex; flex-direction:column; align-items:center; gap:4px; min-width:0; }
.graf-dia .col i { display:block; width:100%; background:var(--naranja); border-radius:3px 3px 0 0; position:relative; }
.graf-dia .col span { font-size:10px; color:#56657a; }
.graf-dia .col b { font-size:10px; }
.legend span { display:inline-block; width:10px; height:10px; margin:0 4px 0 12px; vertical-align:middle; }
"""


def esc(t):
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


JS = r"""
var D = JSON.parse(document.getElementById('data').textContent);
var uids = D.execs.map(function(e){ return e.uid; });

function esc(s){ return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
function pad(n){ return (n<10?'0':'')+n; }
function dinero(n){ n = Math.round(Number(n)||0); return n.toLocaleString('en-US'); }
function cierreStage(){ var cs=null; (D.stages||[]).forEach(function(s){ if(s.toLowerCase().indexOf('cierre')>=0) cs=s; }); return cs; }
function diasInRange(a,b){ return (D.dias||[]).filter(function(d){ return d>=a && d<=b; }); }
function diasDelMes(ym){ return (D.dias||[]).filter(function(d){ return d.indexOf(ym)===0; }); }
function sumDia(daysArr,uid){ var o={c:0,t:0,s:0,a:0}; daysArr.forEach(function(ds){ var dd=(D.daily[ds]||{})[uid]; if(dd){ o.c+=dd.c; o.t+=dd.t; o.s+=dd.s; o.a+=dd.a; } }); return o; }
function sumMov(daysArr,uid,stage){ var n=0; daysArr.forEach(function(ds){ var mm=(D.moves[ds]||{})[uid]||{}; n += mm[stage]||0; }); return n; }
function sumVen(daysArr,uid){ var n=0; daysArr.forEach(function(ds){ var vv=(D.ventas[ds]||{})[uid]||0; n+=vv; }); return n; }
function logrado(uid,stage,daysArr){
  if(stage==='Contacto Tienda') return sumDia(daysArr,uid).s;
  if(stage==='Seguimiento whatsapp Corporativo') return sumDia(daysArr,uid).a;
  return sumMov(daysArr,uid,stage);
}

var estado = { desde:'', hasta:'' };

function renderDaily(){
  var days = diasInRange(estado.desde, estado.hasta);
  var filas = D.execs.map(function(e){
    var x = sumDia(days, e.uid), tot = x.c+x.t+x.s;
    return '<tr><td>'+esc(e.nombre)+'</td><td class="num">'+x.c+'</td><td class="num">'+x.t+'</td>'+
           '<td class="num">'+x.a+'</td><td class="num">'+x.s+'</td><td class="num">'+tot+'</td></tr>';
  }).join('');
  var tv={c:0,t:0,s:0,a:0};
  D.execs.forEach(function(e){ var x=sumDia(days,e.uid); tv.c+=x.c; tv.t+=x.t; tv.s+=x.s; tv.a+=x.a; });
  document.getElementById('tbody-daily').innerHTML = filas +
    '<tr class="total"><td>Total</td><td class="num">'+tv.c+'</td><td class="num">'+tv.t+'</td>'+
    '<td class="num">'+tv.a+'</td><td class="num">'+tv.s+'</td><td class="num">'+(tv.c+tv.t+tv.s)+'</td></tr>';
}

function renderFunnel(){
  var days = diasInRange(estado.desde, estado.hasta);
  document.getElementById('funnel-rango').innerHTML = estado.desde + ' a ' + estado.hasta;
  var stages = D.stages||[];
  var maxf = 1;
  var rows = D.execs.map(function(e){
    var row = {nombre:e.nombre};
    stages.forEach(function(st){ row[st] = logrado(e.uid,st,days)||0; });
    stages.forEach(function(st){ if(row[st]>maxf) maxf=row[st]; });
    return row;
  });
  var totals = {}; stages.forEach(function(st){ totals[st]=0; });
  rows.forEach(function(r){ stages.forEach(function(st){ totals[st]+=r[st]; }); });
  document.getElementById('thead-funnel').innerHTML = '<tr><th>Ejecutivo</th>'+
    stages.map(function(s){ return '<th>'+esc(s)+'</th>'; }).join('')+'</tr>';
  document.getElementById('tbody-funnel').innerHTML = rows.map(function(r){
    var celdas = stages.map(function(s){
      var v=r[s]||0, an=Math.round(v/maxf*100);
      return '<td class="num"><div class="bar-fondo"><i style="width:'+an+'%">&nbsp;'+v+'</i></div></td>';
    }).join('');
    return '<tr><td>'+esc(r.nombre)+'</td>'+celdas+'</tr>';
  }).join('') + '<tr class="total"><td>Total</td>'+
    stages.map(function(s){ return '<td class="num">'+totals[s]+'</td>'; }).join('')+'</tr>';
}

function renderGestion(){
  var days = diasInRange(estado.desde, estado.hasta), nd = days.length;
  var stages = D.stages||[];
  var meta = {}; stages.forEach(function(s){ meta[s]=Math.round((D.meta_diaria[s]||0)*nd); });
  var filas = D.execs.map(function(e){
    var celdas = stages.map(function(s){
      var lo = logrado(e.uid,s,days)||0, pe = Math.max(0, meta[s]-lo), ok = lo>=meta[s];
      var color = ok ? '#1e8e5a' : '#0f3b6e';
      return '<td class="num"><b style="color:'+color+'">'+lo+'</b><div class="nota" style="font-size:10px">pend '+pe+'</div></td>';
    }).join('');
    return '<tr><td>'+esc(e.nombre)+'</td>'+celdas+'</tr>';
  }).join('');
  var tot={meta:0,log:0};
  document.getElementById('thead-gestion').innerHTML =
    '<tr><th>Ejecutivo</th>'+stages.map(function(s){return '<th>'+esc(s)+'</th>';}).join('')+'</tr>'+
    '<tr class="total"><th>Meta del rango ('+nd+' d&iacute;as)</th>'+
    stages.map(function(s){ tot.meta += meta[s]; return '<th class="num">'+meta[s]+'</th>'; }).join('')+'</tr>';
  document.getElementById('tbody-gestion').innerHTML = filas;
  var totlog = stages.map(function(s){
    var t=0; D.execs.forEach(function(e){ t += logrado(e.uid,s,days)||0; }); return '<td class="num">'+t+'</td>';
  }).join('');
  document.getElementById('tfoot-gestion').innerHTML = '<tr class="total"><td>Total logrado</td>'+totlog+'</tr>';
  var ym = estado.hasta.slice(0,7), md = diasDelMes(ym);
  var fecha = new Date(estado.hasta.slice(0,4), +estado.hasta.slice(5,7)-1, 1).toLocaleDateString('es', {month:'long', year:'numeric'});
  var vLog=0; D.execs.forEach(function(e){ vLog += sumVen(md,e.uid); });
  var vMeta = Math.round(D.sales_meta||0), vPend = Math.max(0, vMeta-vLog);
  document.getElementById('gestion-venta').innerHTML =
    'Venta del mes (<b>'+fecha+'</b>): <b>US$'+dinero(vLog)+'</b> &middot; Meta: US$'+dinero(vMeta)+
    ' &middot; Pendiente: US$'+dinero(vPend);
}

function renderCierre(){
  var days = diasInRange(estado.desde, estado.hasta);
  var cs = cierreStage();
  var filas = D.execs.map(function(e){
    var x = sumDia(days,e.uid);
    var venta = sumVen(days,e.uid), cierres = cs ? (sumMov(days,e.uid,cs)||0) : 0;
    return '<tr><td>'+esc(e.nombre)+'</td><td class="num">'+x.c+'</td><td class="num">'+x.t+'</td>'+
           '<td class="num">'+x.s+'</td><td class="num"><b style="color:'+(cierres?'#1e8e5a':'#0f3b6e')+'">'+cierres+'</b></td>'+
           '<td class="num"><b>US$'+dinero(venta)+'</b></td></tr>';
  }).join('');
  var tv={p:0,a:0,s:0,ci:0,v:0};
  D.execs.forEach(function(e){ var x=sumDia(days,e.uid); tv.p+=x.c; tv.a+=x.t; tv.s+=x.s;
      var ci = cs ? (sumMov(days,e.uid,cs)||0) : 0; tv.ci+=ci; tv.v+=sumVen(days,e.uid); });
  document.getElementById('tbody-cierre').innerHTML = filas +
    '<tr class="total"><td>Total</td><td class="num">'+tv.p+'</td><td class="num">'+tv.a+'</td>'+
    '<td class="num">'+tv.s+'</td><td class="num">'+tv.ci+'</td><td class="num">US$'+dinero(tv.v)+'</td></tr>';
  document.getElementById('cierre-nota').innerHTML =
    'Resultado del <b>'+estado.desde+'</b> al <b>'+estado.hasta+'</b>: prospectaron <b>'+tv.p+'</b>, '+
    'atendieron <b>'+tv.a+'</b>, cerraron <b>'+tv.ci+'</b>.';
}

function histChart(ss){
  var n=ss.length; if(!n) return '<p class="nota">Sin datos en el rango.</p>';
  var W = Math.max(320, n*52+52), H = 205, padL=42, padB=24, padT=8;
  var IW = W-padL, IH = H-padB-padT;
  var maxB = 1; ss.forEach(function(x){ var s=x.p+x.a+x.c; if(s>maxB) maxB=s; });
  var maxV = 1; ss.forEach(function(x){ if(x.v>maxV) maxV=x.v; });
  var stepB = Math.ceil(maxB/4), stepV = Math.ceil(maxV/4);
  var bw = Math.min(34, Math.floor((IW-8)/n));
  var out = '<svg width="'+W+'" height="'+H+'" viewBox="0 0 '+W+' '+H+'" xmlns="http://www.w3.org/2000/svg">';
  for(var k=0;k<=4;k++){
    var y = padT+IH - IH*k/4;
    out += '<line x1="'+padL+'" y1="'+y+'" x2="'+W+'" y2="'+y+'" stroke="#eef1f5"/>';
    out += '<text x="'+(padL-6)+'" y="'+(y+4)+'" font-size="10" fill="#56657a" text-anchor="end">'+(k*stepB)+'</text>';
    out += '<text x="'+(W-2)+'" y="'+(y+4)+'" font-size="10" fill="#8a1d1d" text-anchor="end">'+(k*stepV)+'</text>';
  }
  var pit;
  ss.forEach(function(x,i){
    var cx = padL + (IW/n)*i + (IW/n)/2;
    var bwNow = bw;
    var yt = padT+IH - IH*(x.a+x.c)/maxB, yi = padT+IH - IH*x.c/maxB, yp = padT+IH - IH*(x.p+x.a+x.c)/maxB;
    out += '<rect x="'+(cx-bwNow/2)+'" y="'+yt+'" width="'+bwNow+'" height="'+Math.max(0,IH*(x.a+x.c)/maxB)+'" fill="#1e8e5a"/>';
    out += '<rect x="'+(cx-bwNow/2)+'" y="'+yi+'" width="'+bwNow+'" height="'+Math.max(0,IH*x.c/maxB)+'" fill="#e07b2a"/>';
    out += '<rect x="'+(cx-bwNow/2)+'" y="'+yp+'" width="'+bwNow+'" height="'+Math.max(0,IH*x.p/maxB)+'" fill="#2f7cc9"/>';
    var vy = padT+IH - IH*x.v/maxV;
    if(i===0){ pit = 'M'+cx+' '+vy; } else { pit += ' L'+cx+' '+vy; }
  });
  out += '<path d="'+pit+'" fill="none" stroke="#8a1d1d" stroke-width="2"/>';
  ss.forEach(function(x,i){
    var cx = padL + (IW/n)*i + (IW/n)/2;
    var vy = padT+IH - IH*x.v/maxV;
    out += '<circle cx="'+cx+'" cy="'+vy+'" r="2.5" fill="#8a1d1d"/>';
    var lab = x.ds.slice(5);
    if(n>14 && i%3!==0) return;
    out += '<text x="'+cx+'" y="'+(H-6)+'" font-size="9" fill="#56657a" text-anchor="middle">'+lab+'</text>';
  });
  out += '</svg>';
  return out;
}

function renderHistorico(nombre){
  var hd = document.getElementById('hist-desde').value || estado.desde;
  var hh = document.getElementById('hist-hasta').value || estado.hasta;
  var days = diasInRange(hd, hh);
  var uid = null;
  D.execs.forEach(function(e){ if(e.nombre===nombre) uid=e.uid; });
  var ss = days.map(function(ds){
    var p=0,a=0,ci=0,v=0;
    if(uid!==null){
      var x = sumDia([ds],uid);
      p=x.c; a=x.t; ci=cierreStage()?(sumMov([ds],uid,cierreStage())||0):0; v=sumVen([ds],uid);
    } else {
      D.execs.forEach(function(e){
        var x=sumDia([ds],e.uid);
        p+=x.c; a+=x.t; ci+=cierreStage()?(sumMov([ds],e.uid,cierreStage())||0):0; v+=sumVen([ds],e.uid);
      });
    }
    return {ds:ds, p:p, a:a, c:ci, v:v};
  });
  document.getElementById('hist-chart').innerHTML = histChart(ss);
  document.getElementById('tbody-historico').innerHTML = ss.map(function(x){
    return '<tr><td>'+x.ds+'</td><td class="num">'+x.p+'</td><td class="num">'+x.a+'</td>'+
           '<td class="num">'+x.c+'</td><td class="num">'+dinero(x.v)+'</td></tr>';
  }).join('');
  var tp=0,ta=0,tc=0,tv=0;
  ss.forEach(function(x){ tp+=x.p; ta+=x.a; tc+=x.c; tv+=x.v; });
  document.getElementById('tbody-historico').insertAdjacentHTML('beforeend',
    '<tr class="total"><td>Total</td><td class="num">'+tp+'</td><td class="num">'+ta+'</td>'+
    '<td class="num">'+tc+'</td><td class="num">'+dinero(tv)+'</td></tr>');
}

function renderVista(){
  var ym = estado.hasta.slice(0,7);
  var days = diasDelMes(ym);
  var stages = D.stages||[];
  function vrow(e){
    var funnel = {};
    stages.forEach(function(st){ funnel[st] = logrado(e.uid,st,days)||0; });
    var serie = days.map(function(ds){ var x=sumDia([ds],e.uid); return x.c+x.t+x.s; });
    return {nombre:e.nombre, funnel:funnel, serie:serie, venta:sumVen(days,e.uid)};
  }
  var rows = D.execs.map(vrow);
  var global = {nombre:'GLOBAL', funnel:{}, serie:[], venta:0};
  stages.forEach(function(st){ global.funnel[st]=0; rows.forEach(function(r){ global.funnel[st]+=r.funnel[st]; }); });
  for(var i=0;i<days.length;i++){ global.serie[i]=0; rows.forEach(function(r){ global.serie[i]+=r.serie[i]||0; }); }
  rows.forEach(function(r){ global.venta += r.venta; });
  var items = [global].concat(rows);
  var maxf=1, maxd=1;
  items.forEach(function(x){ stages.forEach(function(st){ if(x.funnel[st]>maxf) maxf=x.funnel[st]; }); x.serie.forEach(function(v){ if(v>maxd) maxd=v; }); });
  var fecha = new Date(estado.hasta.slice(0,4), +estado.hasta.slice(5,7)-1, 1).toLocaleDateString('es', {month:'long', year:'numeric'});
  var metaV = Math.round(D.sales_meta||0);
  var filasTodo = rows.map(function(r){
    var celdas = stages.map(function(st){ return '<td class="num">'+(r.funnel[st]||0)+'</td>'; }).join('');
    return '<tr><td>'+esc(r.nombre)+'</td>'+celdas+'<td class="num">US$'+dinero(r.venta)+'</td></tr>';
  }).join('');
  var totFilas = stages.map(function(st){
    var n=0; rows.forEach(function(r){ n += r.funnel[st]||0; }); return '<td class="num">'+n+'</td>';
  }).join('');
  var totVentas = 0; rows.forEach(function(r){ totVentas += r.venta; });
  var thTodo = stages.map(function(s){ return '<th class="num">'+esc(s)+'</th>'; }).join('')+'<th class="num">Venta mes</th>';
  var todosHtml = '<div style="overflow-x:auto"><table><thead><tr><th>Todos los ejecutivos</th>'+thTodo+'</tr></thead>'+
    '<tbody>'+filasTodo+'<tr class="total"><td>Total</td>'+totFilas+'<td class="num">US$'+dinero(totVentas)+'</td></tr></tbody></table></div>';
  document.getElementById('pestanas').innerHTML = items.map(function(x,i){
    return '<button data-i="'+i+'" class="'+(i?'':'activa')+'">'+esc(x.nombre)+'</button>';
  }).join('');
  document.getElementById('panel-vista').innerHTML = items.map(function(x,i){
    var celdas = stages.map(function(st){
      var v=x.funnel[st]||0, an=Math.round(v/maxf*100);
      return '<td class="num"><div class="bar-fondo"><i style="width:'+an+'%">&nbsp;'+v+'</i></div></td>';
    }).join('');
    var cols = x.serie.map(function(v,di){
      var hh=Math.max(3, Math.round(v/maxd*95));
      return '<div class="col"><b>'+v+'</b><i style="height:'+hh+'px"></i><span>'+(di+1)+'</span></div>';
    }).join('');
    var pend = Math.max(0, metaV-x.venta);
    return '<div class="vista-panel" data-i="'+i+'"'+(i?' hidden':'')+'>'+
      '<p class="nota"><b>Informe del mes '+esc(fecha)+'</b> &mdash; '+esc(x.nombre)+'</p>'+
      (i==='0' || i===0 ? todosHtml : '')+
      '<div style="overflow-x:auto"><table><thead><tr><th>Flujo (embudo del mes)</th>'+
      stages.map(function(s){ return '<th class="num">'+esc(s)+'</th>'; }).join('')+'</tr></thead>'+
      '<tbody><tr><td>'+esc(x.nombre)+'</td>'+celdas+'</tr></tbody></table></div>'+
      '<p class="nota">Venta mensual: <b>US$'+dinero(x.venta)+'</b> &middot; Meta: US$'+dinero(metaV)+
      ' &middot; Pendiente: US$'+dinero(pend)+'</p>'+
      '<p class="nota">Atenci&oacute;n diaria del mes (creados + atendidos + contacto tienda)</p>'+
      '<div class="graf-dia">'+cols+'</div></div>';
  }).join('');
  Array.prototype.forEach.call(document.querySelectorAll('#pestanas button'), function(b){ b.onclick = tabClick; });
}
function tabClick(){
  var bts = document.querySelectorAll('#pestanas button');
  bts.forEach(function(b){ b.classList.remove('activa'); });
  this.classList.add('activa');
  Array.prototype.forEach.call(document.querySelectorAll('#panel-vista .vista-panel'), function(p){
    p.hidden = String(p.getAttribute('data-i')) !== this.getAttribute('data-i');
  }, this);
}

function todo(){
  renderDaily();
  renderFunnel();
  renderGestion();
  renderCierre();
  renderHistorico(selHist.value);
  renderVista();
}

var selHist = null;
document.addEventListener('DOMContentLoaded', function(){
  var fd = document.getElementById('fecha-desde'), fh = document.getElementById('fecha-hasta');
  var ULT = D.dias[D.dias.length-1], PRI = D.dias[0];
  fd.min = fh.min = PRI; fd.max = fh.max = ULT;
  estado.desde = estado.hasta = ULT;
  fd.value = fh.value = ULT;
  document.getElementById('rango-datos').textContent = PRI + ' a ' + ULT;

  selHist = document.getElementById('sel-hist');
  selHist.innerHTML = '<option value="GLOBAL">GLOBAL</option>' +
    D.execs.map(function(e){ return '<option value="'+esc(e.nombre)+'">'+esc(e.nombre)+'</option>'; }).join('');
  selHist.onchange = function(){ renderHistorico(selHist.value); };

  var hds = document.getElementById('hist-desde'), hhs = document.getElementById('hist-hasta');
  hds.min = hhs.min = PRI; hds.max = hhs.max = ULT;
  hds.value = PRI; hhs.value = ULT;
  document.getElementById('btn-hist-filtrar').onclick = function(){ renderHistorico(selHist.value); };
  hds.onchange = function(){ renderHistorico(selHist.value); };
  hhs.onchange = function(){ renderHistorico(selHist.value); };

  document.getElementById('btn-ver').onclick = function(){
    if(fd.value>fh.value){ var t=fd.value; fd.value=fh.value; fh.value=t; }
    estado.desde = fd.value; estado.hasta = fh.value;
    todo();
  };
  fd.onchange = function(){ if(fd.value>fh.value) fh.value=fd.value; estado.desde=fd.value; todo(); };
  fh.onchange = function(){ if(fh.value<fd.value) fd.value=fh.value; estado.hasta=fh.value; todo(); };

  todo();
});
"""


def main():
    SITE.mkdir(exist_ok=True)
    PDFS.mkdir(exist_ok=True)

    last = store.last_snapshot_date(dashboard_app.cfg["sqlite_path"])
    if not last:
        raise SystemExit("Sin datos: primero ejecuta sincronizar.bat")
    dia = date.fromisoformat(last[:10])

    dias = store.get_dias_disponibles(dashboard_app.cfg["sqlite_path"])
    execs = dashboard_app._active_execs()

    # ---- datos diarios por dia (para filtrar en el navegador) ----
    daily, moves, ventas = {}, {}, {}
    for ds in dias:
        d = date.fromisoformat(ds)
        rows, _ = dashboard_app.build_daily_panel(d, d)
        daily[ds] = {str(r["uid"]): {"c": r["creados"], "t": r["atendidos"],
                                     "s": r["tienda"], "a": r["actividades"]} for r in rows}
        m = {}
        for r in store.get_stage_moves_range(dashboard_app.cfg["sqlite_path"], d, d):
            m.setdefault(str(r["odoo_uid"]), {})[r["stage"]] = r["count"]
        moves[ds] = m
        v = {}
        for r in store.get_ventas_daily_range(dashboard_app.cfg["sqlite_path"], d, d):
            v[str(r["odoo_uid"])] = r["amount"]
        ventas[ds] = v

    data_payload = {
        "dias": dias,
        "execs": [{"uid": str(e["odoo_uid"]), "nombre": e["name"]} for e in execs],
        "stages": dashboard_app.cfg.get("funnel_stages", []),
        "meta_diaria": dashboard_app.cfg.get("daily_meta", {}) or {},
        "sales_meta": dashboard_app.cfg.get("sales_meta", 0) or 0,
        "daily": daily, "moves": moves, "ventas": ventas,
    }

    last_sync = store.last_sync_ok(dashboard_app.cfg["sqlite_path"])
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M")

    # ---- PDFs al sitio ----
    src_pdf = Path(dashboard_app.cfg.get("pdf_output_dir", "pdf_reports"))
    for old in PDFS.glob("*.pdf"):
        old.unlink()
    if src_pdf.exists():
        for p in src_pdf.glob("*.pdf"):
            shutil.copy(p, PDFS / p.name)
    archivos_pdf = sorted(host.name for host in PDFS.glob("*.pdf"))
    pdf_html = "".join(
        f'<a class="pdf" href="pdf/{esc(a)}" target="_blank">&#128196; {esc(a)}</a>' for a in archivos_pdf
    ) if archivos_pdf else "<span class='nota'>Sin PDFs aun (usa pdf_mensual.bat).</span>"

    est = f"&uacute;ltima sincronizaci&oacute;n: {esc(last_sync['run_at'])}" if last_sync else "sin sincronizar"

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="3600">
<title>Embudo de Ventas - Latinbien</title>
<style>{CSS}</style>
</head>
<body>
<header>
  <h1>Embudo de Ventas &#8226; Latinbien</h1>
  <span class="sub">{est}</span> &nbsp;|&nbsp; <span class="sub">actualizado {ahora}</span>
</header>
<main>
  <div class="barra">
    <label>Desde: <input type="date" id="fecha-desde"></label>
    <label>Hasta: <input type="date" id="fecha-hasta"></label>
    <button id="btn-ver" class="btn">Ver rango</button>
    <span class="sub">Rango del filtro (datos: <b id="rango-datos"></b>). Se aplica a todas las tablas.</span>
  </div>

  <section class="tarjeta">
    <h2>Clientes atendidos por ejecutivo</h2>
    <p class="nota">Columnas del rango seleccionado: nuevos en CRM, atendidos, actividades de seguimiento, contacto tienda y total.</p>
    <div style="overflow-x:auto">
      <table>
        <thead><tr>
          <th>Ejecutivo</th><th class="num">Nuevos CRM</th><th class="num">Atendidos</th>
          <th class="num">Actividades</th><th class="num">Contacto Tienda</th><th class="num">Total</th>
        </tr></thead>
        <tbody id="tbody-daily"></tbody>
      </table>
    </div>
  </section>

  <section class="tarjeta">
    <h2>Embudo de ventas por flujo (rango) &#8212; <span id="funnel-rango"></span></h2>
    <p class="nota">Flujo en el rango Desde/Hasta: movimientos de etapa por ejecutivo. Contacto Tienda y Seguimiento whatsapp se suman del seguimiento/registro local.</p>
    <div style="overflow-x:auto">
      <table>
        <thead id="thead-funnel"></thead>
        <tbody id="tbody-funnel"></tbody>
      </table>
    </div>
  </section>

  <section class="tarjeta">
    <h2>Gesti&oacute;n (meta del rango vs logrado vs pendiente)</h2>
    <p class="nota" id="gestion-venta"></p>
    <div style="overflow-x:auto">
      <table>
        <thead id="thead-gestion"></thead>
        <tbody id="tbody-gestion"></tbody>
        <tfoot id="tfoot-gestion"></tfoot>
      </table>
    </div>
  </section>

  <section class="tarjeta">
    <h2>Hist&oacute;rico de gesti&oacute;n por ejecutivo</h2>
    <div class="barra">
      <label>Ejecutivo: <select id="sel-hist"></select></label>
      <label>Desde: <input type="date" id="hist-desde"></label>
      <label>Hasta: <input type="date" id="hist-hasta"></label>
      <button id="btn-hist-filtrar" class="b">Filtrar</button>
      <span class="sub">Rango propio del hist&oacute;rico (por defecto todo el historial). Barras = gesti&oacute;n del d&iacute;a (azul = prospectados, verde = atendidos, naranja = cierres). L&iacute;nea roja = venta del d&iacute;a.</span>
    </div>
    <div id="hist-chart" style="margin-bottom:10px"></div>
    <div style="overflow-x:auto">
      <table>
        <thead><tr>
          <th>D&iacute;a</th><th class="num">Prospectados</th><th class="num">Atendidos</th>
          <th class="num">Cierres</th><th class="num">Venta del d&iacute;a</th>
        </tr></thead>
        <tbody id="tbody-historico"></tbody>
      </table>
    </div>
  </section>

  <section class="tarjeta">
    <h2>Cierre por ejecutivo (rango)</h2>
    <p class="nota" id="cierre-nota"></p>
    <p class="nota">Prospectados = nuevos CRM del rango; Atendidos = clientes con actividad; Cierres = leads que pasaron a Cierre; Venta = monto de esos cierres.</p>
    <div style="overflow-x:auto">
      <table>
        <thead><tr>
          <th>Ejecutivo</th><th class="num">Prospectados</th><th class="num">Atendidos</th>
          <th class="num">Contacto Tienda</th><th class="num">Cierres</th><th class="num">Venta</th>
        </tr></thead>
        <tbody id="tbody-cierre"></tbody>
      </table>
    </div>
  </section>

  <section class="tarjeta">
    <h2>Vista por ejecutivo (como el PDF del mes)</h2>
    <p class="nota">La info del informe PDF de cada ejecutivo, directamente en pesta&ntilde;as (mes del d&iacute;a "Hasta").</p>
    <div class="pestanas" id="pestanas"></div>
    <div id="panel-vista"></div>
  </section>

  <section class="tarjeta">
    <h2>Informes PDF del mes</h2>
    <p class="nota">Gen&eacute;ralos con pdf_mensual.bat (crea GLOBAL + uno por ejecutivo) y quedan visibles y descargables aqui.</p>
    {pdf_html}
    <p class="nota" style="margin-top:10px">El tablero interactivo con botones +/− (Contacto Tienda) se abre localmente con dashboard.bat en http://127.0.0.1:8080.</p>
  </section>

  <div class="foot">Generado automaticamente desde el cache local (solo lectura, sin modificar Odoo).</div>
</main>
<script id="data" type="application/json">{json.dumps(data_payload, ensure_ascii=False)}</script>
<script>{JS}</script>
</body>
</html>
"""
    (SITE / "index.html").write_text(html, encoding="utf-8")
    print(f"Tablero estatico generado en docs/ ({len(dias)} dias, {len(execs)} ejecutivos, {len(archivos_pdf)} PDFs)")
    print("Publica con subir_web.bat (o desde sincronizar.bat / pdf_mensual.bat)")


if __name__ == "__main__":
    main()