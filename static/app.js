"use strict";
const API=(p,o)=>{o=o||{};const h=Object.assign({},o.headers||{});if(TOKEN&&!h.Authorization)h.Authorization="Bearer "+TOKEN;o.headers=h;return fetch(p,o).then(r=>r.json());};
const PALETTE=["#4f46e5","#0ea5e9","#15a34a","#e08a00","#e0413e","#7c6cf0","#0d9488","#db2777","#64748b","#16a34a"];
const STATUS_CLASS={"正常":"g","考核期":"y","见习":"y","实习":"y","待复权":"y","停审":"r","降级":"r","已回收":"r","退出":"r","永封":"r"};
const LEVEL_CLASS={"待转正":"lv0","初审":"lv1","中审":"lv2","高审":"lv3"};
const DIR_LABEL={ge:"≥ 达标",le:"≤ 达标",count0:"计数(越小越好)"};
function svg(tag,a){const e=document.createElementNS("http://www.w3.org/2000/svg",tag);for(const k in a)e.setAttribute(k,a[k]);return e;}

// ---------- 自定义下拉选择 ----------
const SEL_WRAP=new Map();
function initCustomSelects(){
  document.querySelectorAll("select").forEach(sel=>{if(!SEL_WRAP.has(sel)) wrapSelect(sel);});
}
function wrapSelect(sel){
  if(SEL_WRAP.has(sel)) return SEL_WRAP.get(sel);
  const origParent=sel.parentNode;
  sel.classList.add("sel-native");
  const wrap=document.createElement("div"); wrap.className="sel-wrap";
  const trigger=document.createElement("button"); trigger.className="sel-trigger"; trigger.type="button";
  const drop=document.createElement("div"); drop.className="sel-drop";
  origParent.insertBefore(wrap, sel);
  wrap.appendChild(trigger); wrap.appendChild(drop); wrap.appendChild(sel);
  SEL_WRAP.set(sel, wrap);
  renderSelect(sel);
  sel.addEventListener("change", ()=>renderSelect(sel));
  trigger.addEventListener("click", e=>{e.stopPropagation(); toggleSelect(sel);});
  drop.addEventListener("click", e=>{
    const opt=e.target.closest(".sel-option");
    if(!opt || opt.classList.contains("disabled")) return;
    if(sel.disabled) return; // 跨权防卫：原生 select 被禁用时禁止程序化改值
    sel.value=opt.dataset.value;
    sel.dispatchEvent(new Event("change",{bubbles:true}));
    renderSelect(sel); closeAllSelects();
  });
  return wrap;
}
function renderSelect(sel){
  const wrap=SEL_WRAP.get(sel); if(!wrap) return;
  wrap.classList.toggle("disabled", !!sel.disabled);
  const trigger=wrap.querySelector(".sel-trigger");
  const drop=wrap.querySelector(".sel-drop");
  const opts=[...sel.options];
  const selected=opts.find(o=>o.selected)||opts[0];
  trigger.textContent=selected?selected.textContent:"";
  drop.innerHTML=opts.map(o=>`<div class="sel-option ${o.selected?'selected':''}${o.disabled?' disabled':''}" data-value="${o.value}">${o.textContent}</div>`).join("");
}
function refreshCustomSelect(el){
  const sel=typeof el==="string"?document.getElementById(el):el;
  if(!sel) return; wrapSelect(sel); renderSelect(sel);
}
function toggleSelect(sel){
  const wrap=SEL_WRAP.get(sel); if(!wrap || wrap.classList.contains("disabled") || sel.disabled) return;
  const wasOpen=wrap.classList.contains("open");
  closeAllSelects();
  if(!wasOpen){wrap.classList.add("open"); const opt=wrap.querySelector(".sel-option.selected"); if(opt) opt.scrollIntoView({block:"nearest"});}
}
function closeAllSelects(){SEL_WRAP.forEach((wrap)=>wrap.classList.remove("open"));}
document.addEventListener("click",()=>closeAllSelects());
window.addEventListener("keydown",e=>{if(e.key==="Escape")closeAllSelects();});

// 横向条形
function barChart(box,data){
  box.innerHTML=""; if(!data.length){box.innerHTML='<div class="empty">暂无数据</div>';return;}
  const W=box.clientWidth||560,rowH=26,pad=8,labelW=128,valW=44;
  const H=data.length*rowH+pad*2, max=Math.max.apply(null,data.map(d=>d.value))||1;
  const s=svg("svg",{viewBox:`0 0 ${W} ${H}`,width:"100%",height:H});
  data.forEach((d,i)=>{const y=pad+i*rowH,bw=Math.max(2,(W-labelW-valW-pad)*(d.value/max));
    const l=svg("text",{x:0,y:y+rowH/2+4,fill:"#1e2532","font-size":12});l.textContent=d.label.length>10?d.label.slice(0,10):d.label;s.appendChild(l);
    s.appendChild(svg("rect",{x:labelW,y:y+4,width:bw,height:rowH-10,rx:4,fill:d.color||"#4f46e5"}));
    const v=svg("text",{x:labelW+bw+6,y:y+rowH/2+4,fill:"#707a8a","font-size":12});v.textContent=d.value;if(d.suffix)v.textContent+=d.suffix;s.appendChild(v);});
  box.appendChild(s);
}
// 环形
function donutChart(box,data){
  box.innerHTML=""; if(!data.length){box.innerHTML='<div class="empty">暂无数据</div>';return;}
  const W=box.clientWidth||560,H=Math.max(200,W*0.5),cx=W/2,cy=H/2,r=Math.min(W,H)/2-22,ir=r*0.6;
  const total=data.reduce((s,d)=>s+d.value,0)||1;
  const s=svg("svg",{viewBox:`0 0 ${W} ${H}`,width:"100%",height:H});
  let a0=-Math.PI/2;
  data.forEach(d=>{const a1=a0+(d.value/total)*Math.PI*2,lg=a1-a0>Math.PI?1:0;
    const x0=cx+r*Math.cos(a0),y0=cy+r*Math.sin(a0),x1=cx+r*Math.cos(a1),y1=cy+r*Math.sin(a1);
    const xi1=cx+ir*Math.cos(a1),yi1=cy+ir*Math.sin(a1),xi0=cx+ir*Math.cos(a0),yi0=cy+ir*Math.sin(a0);
    s.appendChild(svg("path",{d:`M${x0} ${y0} A${r} ${r} 0 ${lg} 1 ${x1} ${y1} L${xi1} ${yi1} A${ir} ${ir} 0 ${lg} 0 ${xi0} ${yi0} Z`,fill:d.color||"#4f46e5"}));
    a0=a1;});
  const t1=svg("text",{x:cx,y:cy-4,fill:"#1e2532","font-size":22,"text-anchor":"middle","font-weight":800});t1.textContent=total;s.appendChild(t1);
  const t2=svg("text",{x:cx,y:cy+18,fill:"#707a8a","font-size":12,"text-anchor":"middle"});t2.textContent="记录数";s.appendChild(t2);
  box.appendChild(s);
  const lg=document.createElement("div");lg.className="legend";
  data.forEach(d=>{const sp=document.createElement("span");sp.innerHTML=`<i style="background:${d.color}"></i>${d.label} ${d.value}`;lg.appendChild(sp);});
  box.appendChild(lg);
}
// 折线（趋势）
function lineChart(box,data,opts){
  opts=opts||{}; box.innerHTML=""; if(!data.length){box.innerHTML='<div class="empty">暂无数据</div>';return;}
  const W=box.clientWidth||560,H=190,pad=28,m=Math.max.apply(null,data.map(d=>d.value))||100,M=Math.min.apply(null,data.map(d=>d.value));
  const lo=0,hi=Math.max(100,(Math.ceil((m*1.15)/10)*10));
  const s=svg("svg",{viewBox:`0 0 ${W} ${H}`,width:"100%",height:H});
  for(let g=0;g<=4;g++){const yy=pad+(H-pad*2)*g/4;const val=Math.round(hi-(hi-lo)*g/4);
    s.appendChild(svg("line",{x1:pad,y1:yy,x2:W-10,y2:yy,stroke:"#eef1f6"}));
    const t=svg("text",{x:4,y:yy+4,fill:"#aab","font-size":10});t.textContent=val;s.appendChild(t);}
  const X=i=>pad+(W-pad-10)*i/(data.length-1||1);
  const Y=v=>pad+(H-pad*2)*(1-(v-lo)/(hi-lo));
  const pts=data.map((d,i)=>`${X(i)},${Y(d.value)}`).join(" ");
  s.appendChild(svg("polyline",{points:pts,fill:"none",stroke:opts.color||"#4f46e5","stroke-width":2.5}));
  data.forEach((d,i)=>{s.appendChild(svg("circle",{cx:X(i),cy:Y(d.value),r:4,fill:"#fff",stroke:opts.color||"#4f46e5","stroke-width":2}));
    const t=svg("text",{x:X(i),y:Y(d.value)-10,fill:"#1e2532","font-size":11,"text-anchor":"middle","font-weight":700});t.textContent=d.value;s.appendChild(t);
    const xl=svg("text",{x:X(i),y:H-6,fill:"#707a8a","font-size":11,"text-anchor":"middle"});xl.textContent=d.label;s.appendChild(xl);});
  box.appendChild(s);
}
// 排名横向条（带通过/失败着色）
function hBar(box,data){
  box.innerHTML=""; if(!data.length){box.innerHTML='<div class="empty">暂无数据</div>';return;}
  const W=box.clientWidth||560,rowH=28,pad=8,labelW=130,valW=64;
  const H=data.length*rowH+pad*2,max=Math.max.apply(null,data.map(d=>d.value))||1;
  const s=svg("svg",{viewBox:`0 0 ${W} ${H}`,width:"100%",height:H});
  data.forEach((d,i)=>{const y=pad+i*rowH,bw=Math.max(2,(W-labelW-valW-pad)*(d.value/max));
    const l=svg("text",{x:0,y:y+rowH/2+4,fill:"#1e2532","font-size":12});l.textContent=(i+1)+". "+(d.label.length>9?d.label.slice(0,9):d.label);s.appendChild(l);
    s.appendChild(svg("rect",{x:labelW,y:y+5,width:bw,height:rowH-11,rx:4,fill:d.color||"#4f46e5"}));
    const v=svg("text",{x:labelW+bw+6,y:y+rowH/2+4,fill:"#707a8a","font-size":12});v.textContent=d.value;s.appendChild(v);});
  box.appendChild(s);
}

let DICT={};
function debounce(fn,ms){let t;return (...args)=>{clearTimeout(t);t=setTimeout(()=>fn(...args),ms);};}
async function loadDict(){
  DICT=await API("/api/dict");
  document.getElementById("sysver").textContent="制度版本 "+DICT.system_version;
  fill("f-domain",[...new Set(DICT.categories.map(c=>c.domain))].sort()); fill("f-category",[...new Set(DICT.categories.map(c=>c.category))].sort());
  fill("f-level",DICT.account_levels,[""]); fill("f-status",DICT.statuses,[""]);
  fill("e-status",DICT.statuses.filter(s=>s!=="降级"),[]);
  fill("a-level",DICT.account_levels,[]); fill("a-status",DICT.account_statuses,[]);
  document.getElementById("acct-list").innerHTML=DICT.accounts.map(a=>`<option value="${a.account_id}">`).join("");
  document.getElementById("cat-list").innerHTML=DICT.categories.map(c=>`<option value="${c.category}">`).join("");
  fill("f-group",[...new Set(DICT.categories.map(c=>c.group_name))]);
  loadCategories();
  // 申请管理：填充流程节点下拉
  const nodeOpts=EVAL_NODES.map(n=>`<option value="${n}">${n}</option>`).join("");
  const apn=document.getElementById("ap-node"); if(apn)apn.innerHTML='<option value="">全部节点</option>'+nodeOpts;
  const evn=document.getElementById("ev-node"); if(evn)evn.innerHTML='<option value="">（未指定）</option>'+nodeOpts;
  initCustomSelects();
}
function fill(id,vals,extra){const e=document.getElementById(id);const label=e.dataset.label;const emptyText=label?`全部${label}`:"全部";const h=(extra||[""]).map(v=>`<option value="${v}">${v||emptyText}</option>`).join("")+vals.map(v=>`<option value="${v}">${v}</option>`).join("");e.innerHTML=h;refreshCustomSelect(e);}

// ---------- 制度文档 ----------
async function loadSystem(){
  const ver=DICT.system_version||"V20260904B";
  const verEl=document.getElementById("sys-doc-ver");
  if(verEl) verEl.textContent=ver;
  const guest=!(ME&&ME.account_id);
  const guestHint=document.getElementById("sys-guest-hint");
  const docCard=document.getElementById("sys-doc-card");
  const flowCard=document.getElementById("sys-flow-card");
  if(guestHint) guestHint.style.display=guest?"block":"none";
  if(docCard) docCard.style.display=guest?"none":"block";
  if(flowCard) flowCard.style.display=guest?"none":"block";
  if(guest) return;
  const pdfBase="/api/system-docs/百科任务评审团特色初优方向评审申请与考核制度_V20260904B.pdf";
  const pdfUrl=TOKEN?pdfBase+"?token="+encodeURIComponent(TOKEN):pdfBase;
  const sysPdf=document.getElementById("sys-pdf");
  if(sysPdf && sysPdf.dataset.src){ sysPdf.src=pdfUrl; }
  const openBtn=document.getElementById("sys-open-pdf");
  if(openBtn){ openBtn.href=pdfUrl; }
  document.querySelectorAll(".sys-flow-item img").forEach(img=>{
    if(img.dataset.src){
      img.src=TOKEN?img.dataset.src+"?token="+encodeURIComponent(TOKEN):img.dataset.src;
    }
  });
}
// ---------- 账号登录情况（系统管理二级页，仅超级管理员） ----------
async function loadLoginLogs(){
  if(!(ME&&ME.is_super_admin)) return;
  const d=await API("/api/login-logs");
  const rows=(d&&d.rows)||[];
  const body=document.getElementById("sys-login-body");
  if(!body) return;
  body.innerHTML=rows.length?rows.map(r=>`<tr>
    <td>${escMsg(r.account_id)}</td><td>${escMsg(r.login_time||"")}</td>
    <td>${escMsg(r.ip_display||r.ip||"—")}</td><td>${escMsg(r.device_id||"—")}</td>
    <td class="wrap" style="max-width:320px">${escMsg(r.user_agent||"—")}</td></tr>`).join(""):'<tr><td colspan="5" class="empty">暂无登录记录</td></tr>';
}
function openFlowPreview(n){
  const map={"1":["图1_评审报名申请流程.png","图1 评审报名申请流程"],"2":["图2_升级与分类扩充流程.png","图2 升级与分类扩充流程"],"3":["图3_日常考核流程.png","图3 日常考核流程"],"4":["图4_违规惩处与申述流程.png","图4 违规惩处与申述流程"]};
  const [file,title]=map[n]||["",""];
  if(!file) return;
  document.getElementById("flow-title").textContent=title;
  document.getElementById("flow-img").src="/api/system-docs/"+file+(TOKEN?"?token="+encodeURIComponent(TOKEN):"");
  document.getElementById("modal-flow").classList.add("show");
}

// ---------- 总览 ----------
async function loadOverview(){
  const d=await API("/api/overview"); const s=d.snapshot;
  const kpis=[
    {l:"账号总数",v:s.total_acct},{l:"启用分类",v:s.total_cat},{l:"权限记录",v:s.total_perm},
    {l:"正常率",v:s.active_rate+"%",cls:"ok"},
    {l:"考核通过率",v:(d.assess?d.assess.pass_rate+"%":"—"),cls:"info"}
  ];
  document.getElementById("kpis").innerHTML=kpis.map(k=>`<div class="kpi"><div class="v ${k.cls||""}">${k.v}</div><div class="l">${k.l}</div></div>`).join("");
  barChart(document.getElementById("chart-domain"),d.domain_cov.map((x,i)=>({label:x.domain,value:x.persons,suffix:"人",color:PALETTE[i%PALETTE.length]})));
  const sd=d.status_dist.length?d.status_dist:[{status:"正常",c:s.total_acct}];
  donutChart(document.getElementById("chart-astatus"),sd.map((x,i)=>({label:x.status,value:x.c,color:PALETTE[i%PALETTE.length]})));
  if(d.assess){
    donutChart(document.getElementById("chart-pass"),[{label:"通过",value:d.assess.passed,color:"#15a34a"},{label:"不通过",value:d.assess.fail,color:"#e0413e"}]);
    const tr=await API("/api/assess/stats?period="+d.latest_period);
    lineChart(document.getElementById("chart-trend"),tr.trend.map(t=>({label:t.period,value:t.pass_rate})),{color:"#0ea5e9"});
  } else {document.getElementById("chart-pass").innerHTML='<div class="empty">暂无考核数据</div>';document.getElementById("chart-trend").innerHTML='<div class="empty">暂无考核数据</div>';}
  loadStats();
}

// ---------- 台账 ----------
let ledgerPage=1, ledgerView="matrix";
function lf(){return{domain:val("f-domain"),group_name:val("f-group"),category:val("f-category"),level:val("f-level"),status:val("f-status"),account_id:val("f-account"),only_active:document.getElementById("f-active").checked?"1":""};}
function toggleView(){
  ledgerView=ledgerView==="matrix"?"detail":"matrix";
  const btn=document.getElementById("btn-view");
  btn.textContent=ledgerView==="matrix"?"明细视图":"矩阵视图";
  document.getElementById("ledger-matrix").style.display=ledgerView==="matrix"?"block":"none";
  document.getElementById("ledger-detail").style.display=ledgerView==="detail"?"block":"none";
  ledgerPage=1; loadLedger();
}
async function loadLedger(){if(ledgerView==="matrix")return loadMatrix(); return loadDetail();}
async function loadMatrix(){
  const f=lf(); const qs=new URLSearchParams({...f,page:ledgerPage,size:20}).toString();
  const d=await API("/api/permissions/matrix?"+qs);
  const body=document.getElementById("matrix-body");
  if(!d.rows.length){body.innerHTML='<div class="empty" style="padding:30px 0">无数据</div>'; document.getElementById("matrix-pager").innerHTML=""; return;}
  body.innerHTML=d.rows.map(r=>{
    const domains=r.domains.map(dom=>{
      const tags=dom.items.map(it=>`<span class="tag" title="${it.group_name?it.group_name+' · ':''}${it.category} · ${it.status}">${it.category}</span>`).join(" ");
      return `<div class="matrix-domain"><span class="domain-name">${dom.domain}</span><div class="domain-tags">${tags}</div></div>`;
    }).join("");
    const name=r.display_name&&r.display_name!==r.account_id?`${r.account_id}<br><span class="muted">${r.display_name}</span>`:r.account_id;
    return `<div class="matrix-row" data-aid="${r.account_id}">
      <div class="matrix-cell name" data-label="账号 / 昵称">${name}</div>
      <div class="matrix-cell" data-label="账号等级"><span class="pill ${LEVEL_CLASS[r.acct_level]||'n'}">${r.acct_level}</span></div>
      <div class="matrix-cell" data-label="状态"><span class="pill ${STATUS_CLASS[r.acct_status]||'n'}">${r.acct_status}</span></div>
      <div class="matrix-cell perms" data-label="权限分布">${domains}</div>
      <div class="matrix-cell" data-label="操作">${ME?`<button class="linkbtn" data-edit-acct="${r.account_id}">编辑账号</button><br>`:''}<button class="linkbtn" data-expand="${r.account_id}">展开</button></div>
    </div>
    <div class="matrix-detail" id="md-${r.account_id}" style="display:none"></div>`;
  }).join("");
  // 分页（含跳转输入）
  const tp=Math.max(1,Math.ceil(d.total/d.size));
  document.getElementById("matrix-pager").innerHTML=`<button class="btn ghost" ${ledgerPage<=1?"disabled":""} data-pg="-1">上一页</button><span>第 <input id="matrix-jump" type="number" min="1" max="${tp}" value="${d.page}" style="width:54px;text-align:center"> / ${tp} 页 · 共 ${d.total} 人</span><button class="btn ghost" ${ledgerPage>=tp?"disabled":""} data-pg="1">下一页</button><button class="btn ghost" id="matrix-go">跳转</button>`;
  document.querySelectorAll("#matrix-pager [data-pg]").forEach(b=>b.onclick=()=>{ledgerPage+=+b.dataset.pg;loadMatrix();});
  const doJumpMatrix=()=>{const v=parseInt(document.getElementById("matrix-jump").value,10); if(v>=1&&v<=tp){ledgerPage=v;loadMatrix();}};
  document.getElementById("matrix-go").onclick=doJumpMatrix;
  document.getElementById("matrix-jump").onkeydown=e=>{if(e.key==="Enter")doJumpMatrix();};
  // 编辑账号
  document.querySelectorAll("#matrix-body [data-edit-acct]").forEach(b=>b.onclick=()=>openAcctByAid(b.dataset.editAcct));
  // 展开/折叠
  document.querySelectorAll("#matrix-body [data-expand]").forEach(b=>b.onclick=async()=>{
    const aid=b.dataset.expand, box=document.getElementById("md-"+aid);
    if(box.style.display==="block"){box.style.display="none"; b.textContent="展开"; return;}
    const pd=await API("/api/permissions?account_id="+encodeURIComponent(aid)+"&size=2000");
    box.innerHTML='<table class="mini"><thead><tr><th>分类</th><th>二级组</th><th>领域</th><th>状态</th><th>操作</th></tr></thead><tbody>'+
      pd.rows.map(p=>{
        const isRec=p.status==="已回收";
        const btn=ME?(isRec?`<button class="linkbtn" data-restore="${p.id}">恢复</button>`:`<button class="linkbtn del" data-del="${p.id}">回收</button>`):'';
        return `<tr><td>${p.category}</td><td>${p.group_name||""}</td><td>${p.domain||""}</td><td><span class="pill ${STATUS_CLASS[p.status]||'n'}">${p.status}</span></td><td>${ME?`<button class="linkbtn" data-edit="${p.id}">改</button>`:''}${btn}</td></tr>`;}).join("")+'</tbody></table>';
    box.style.display="block"; b.textContent="折叠";
    box.querySelectorAll("[data-edit]").forEach(b=>b.onclick=()=>openEdit(b.dataset.edit));
    box.querySelectorAll("[data-del]").forEach(b=>b.onclick=()=>recycle(b.dataset.del));
    box.querySelectorAll("[data-restore]").forEach(b=>b.onclick=()=>restore(b.dataset.restore));
  });
}
async function loadDetail(){
  const f=lf(); const qs=new URLSearchParams({...f,page:ledgerPage,size:50}).toString();
  const d=await API("/api/permissions?"+qs);
  document.getElementById("ledger-body").innerHTML=d.rows.length?d.rows.map(r=>{
    const isRec=r.status==="已回收";
    const btn=ME?(isRec?`<button class="linkbtn" data-restore="${r.id}">恢复</button>`:`<button class="linkbtn del" data-del="${r.id}">回收</button>`):'';
    return `<tr>
    <td>${r.account_id}${r.display_name&&r.display_name!==r.account_id?`<br><span class="muted">${r.display_name}</span>`:""}</td><td>${r.domain||""}</td><td>${r.group_name||""}</td><td class="wrap">${r.category}</td>
    <td><span class="pill ${STATUS_CLASS[r.status]||'n'}">${r.status}</span></td>
    <td>${r.effect_date||""}</td><td>${r.expire_date||""}</td><td class="wrap">${r.source}</td><td>${r.operator}</td>
    <td>${ME?`<button class="linkbtn" data-edit="${r.id}">改</button>`:''}${btn}</td></tr>`;}).join(""):'<tr><td colspan="10" class="empty">无数据</td></tr>';
  const tp=Math.max(1,Math.ceil(d.total/d.size));
  document.getElementById("ledger-pager").innerHTML=`<button class="btn ghost" ${ledgerPage<=1?"disabled":""} data-pg="-1">上一页</button><span>第 <input id="ledger-jump" type="number" min="1" max="${tp}" value="${d.page}" style="width:54px;text-align:center"> / ${tp} 页 · 共 ${d.total} 条</span><button class="btn ghost" ${ledgerPage>=tp?"disabled":""} data-pg="1">下一页</button><button class="btn ghost" id="ledger-go">跳转</button>`;
  document.querySelectorAll("#ledger-pager [data-pg]").forEach(b=>b.onclick=()=>{ledgerPage+=+b.dataset.pg;loadDetail();});
  const doJumpLedger=()=>{const v=parseInt(document.getElementById("ledger-jump").value,10); if(v>=1&&v<=tp){ledgerPage=v;loadDetail();}};
  document.getElementById("ledger-go").onclick=doJumpLedger;
  document.getElementById("ledger-jump").onkeydown=e=>{if(e.key==="Enter")doJumpLedger();};
  document.querySelectorAll("#ledger-body [data-edit]").forEach(b=>b.onclick=()=>openEdit(b.dataset.edit));
  document.querySelectorAll("#ledger-body [data-del]").forEach(b=>b.onclick=()=>recycle(b.dataset.del));
  document.querySelectorAll("#ledger-body [data-restore]").forEach(b=>b.onclick=()=>restore(b.dataset.restore));
}
function val(id){return document.getElementById(id).value;}
let editId=null;
function updateCatRequired(){const isChu=val("e-level")==="初审";const c=document.getElementById("e-category");if(c){if(isChu)c.value="";c.readOnly=isChu;c.placeholder=isChu?"初审无需分类":"";}}
function openEdit(id){editId=id||null;document.getElementById("edit-title").textContent=id?"修改权限":"单条录入";
  ["e-account","e-category","e-effect","e-expire","e-source","e-operator"].forEach(x=>document.getElementById(x).value="");
  document.getElementById("e-level").value="中审";document.getElementById("e-status").value="正常";
  if(id){fetch("/api/permissions?page=1&size=2000").then(r=>r.json()).then(d=>{const r=d.rows.find(x=>String(x.id)===String(id));if(r){document.getElementById("e-account").value=r.account_id;document.getElementById("e-category").value=r.category;document.getElementById("e-level").value=r.level;document.getElementById("e-status").value=r.status;document.getElementById("e-effect").value=r.effect_date||"";document.getElementById("e-expire").value=r.expire_date||"";document.getElementById("e-source").value=r.source;document.getElementById("e-operator").value=r.operator;updateCatRequired();refreshCustomSelect("e-level");refreshCustomSelect("e-status");}});}
  document.getElementById("modal-edit").classList.add("show");
}
async function saveEdit(){if(!requireAuth())return;
  const level=val("e-level");
  if(!val("e-account")){await UI.alert("账号为必填");return;}
  if(level!=="初审" && !val("e-category")){await UI.alert("分类为必填（初审除外）");return;}
  const b={account_id:val("e-account"),category:val("e-category"),level:level,status:val("e-status"),effect_date:val("e-effect"),source:val("e-source"),operator:val("e-operator")};
  const res=editId?await fetch("/api/permissions/"+editId,{method:"PUT",headers:j(),body:JSON.stringify(b)}).then(r=>r.json()):await fetch("/api/permissions",{method:"POST",headers:j(),body:JSON.stringify(b)}).then(r=>r.json());
  if(res.error){await UI.alert("保存失败："+res.error);return;}document.getElementById("modal-edit").classList.remove("show");loadLedger();loadOverview();loadLogs();}
async function recycle(id){if(!await UI.confirm("确认回收该权限？将记录操作人与时间。"))return;await fetch("/api/permissions/"+id,{method:"DELETE"});loadLedger();loadOverview();loadLogs();}
async function restore(id){if(!await UI.confirm("确认恢复该权限？将重新设为正常。"))return;await fetch("/api/permissions/"+id+"/restore",{method:"POST",headers:j(),body:JSON.stringify({})});loadLedger();loadOverview();loadLogs();}
function parseCSV(t){return t.trim().split(/\r?\n/).filter(l=>l.trim()).map(l=>{const p=l.split(",").map(s=>s.trim());if(p[0]==="账号"&&p[1]==="分类")return null;return{account_id:p[0],category:p[1],level:p[2]||"",status:p[3]||"正常",effect_date:p[4]||"",expire_date:p[5]||"",source:p[6]||"批量导入",operator:p[7]||"批量导入"};}).filter(Boolean);}
async function doImport(){const rows=parseCSV(document.getElementById("imp-text").value);if(!rows.length){await UI.alert("没有可导入的数据");return;}
  const res=await API("/api/permissions/import",{method:"POST",headers:j(),body:JSON.stringify({rows,mode:val("imp-mode")})});
  document.getElementById("imp-result").textContent=`成功 ${res.added} 条，跳过 ${res.skipped} 条。\n`+(res.errors&&res.errors.length?("错误(前10)：\n"+res.errors.slice(0,10).join("\n")):"");
  loadLedger();loadOverview();loadDict();loadLogs();}

// ---------- 统计分析 ----------
async function loadStats(){const dim=val("s-dim");const d=await API("/api/stats?dim="+encodeURIComponent(dim));
  const total=d.rows.reduce((s,r)=>s+r.perm_cnt,0)||1;
  document.getElementById("stats-dim-h").textContent={domain:"领域(部门)",group_name:"二级组",category:"分类",level:"等级",status:"状态",system_version:"制度版本",effect_month:"生效月份",operator:"操作人"}[dim]||"维度";
  document.getElementById("stats-body").innerHTML=d.rows.length?d.rows.map(r=>`<tr><td>${r.dim}</td><td>${r.perm_cnt}</td><td>${r.person_cnt}</td><td>${r.cat_cnt}</td><td>${(r.perm_cnt/total*100).toFixed(1)}%</td></tr>`).join(""):'<tr><td colspan="5" class="empty">无数据</td></tr>';
  barChart(document.getElementById("chart-stats"),d.rows.map((r,i)=>({label:r.dim,value:r.perm_cnt,color:PALETTE[i%PALETTE.length]})));}

// ---------- 考核管理 ----------
function currentScope(){const b=document.querySelector("#page-assess .subtab.active");return b?b.dataset.sub:null;}
function scopePeriod(scope){const map={edit:"e-period",review:"v-period",official:"o-period",summary:"s-period"};const id=map[scope]||"s-period";return val(id)||document.querySelector("#"+id+" option")?.value;}
function showSub(sub){document.querySelectorAll("#page-assess .subtab").forEach(b=>b.classList.toggle("active",b.dataset.sub===sub));
  ["edit","review","official","summary","config"].forEach(s=>{const el=document.getElementById("sub-"+s);if(el)el.style.display=s===sub?"block":"none";});
  if(sub==="config")loadCfg();else if(sub==="edit")loadScope("edit");else if(sub==="review")loadScope("review");else if(sub==="official")loadScope("official");else if(sub==="summary")loadSummary();}
// 指标配置
async function loadCfg(){const d=await API("/api/assess/config");
  document.getElementById("cfg-body").innerHTML=d.rows.map(c=>`<tr data-name="${c.name}" data-id="${c.id}">
    <td><b>${c.name}</b></td>
    <td><input class="cw" type="number" step="1" value="${c.weight}" style="width:70px"></td>
    <td><input class="cp" type="number" step="0.1" value="${c.pass_line}" style="width:70px"></td>
    <td><select class="cd">${["ge","le","count0"].map(o=>`<option value="${o}" ${c.direction===o?"selected":""}>${DIR_LABEL[o]}</option>`).join("")}</select></td>
    <td><select class="ct">${["percent","count"].map(o=>`<option value="${o}" ${c.input_type===o?"selected":""}>${o==="percent"?"百分比":"计数"}</option>`).join("")}</select></td>
    <td><input class="cn" value="${c.note||""}" style="width:160px"></td>
    <td><button class="linkbtn del" data-cfgd="${c.id}" data-auth="write">删除</button></td></tr>`).join("");
  initCustomSelects();
  document.querySelectorAll("#cfg-body [data-cfgd]").forEach(b=>b.onclick=()=>delCfg(b.dataset.cfgd));}
async function delCfg(id){if(!await UI.confirm("确认删除该指标？删除后权重合计将变化，建议同步调整其余指标。"))return;
  const res=await fetch("/api/assess/config/"+id,{method:"DELETE"}).then(r=>r.json());
  if(res.error){await UI.alert("删除失败："+res.error);return;}loadCfg();loadLogs();}
async function saveCfg(){if(!requireAuth())return;const items=[...document.querySelectorAll("#cfg-body tr")].map(tr=>({name:tr.dataset.name,weight:+tr.querySelector(".cw").value,pass_line:+tr.querySelector(".cp").value,direction:tr.querySelector(".cd").value,input_type:tr.querySelector(".ct").value,note:tr.querySelector(".cn").value}));
  const sum=items.reduce((s,i)=>s+i.weight,0);
  if(Math.abs(sum-100)>0.01&&!await UI.confirm("权重合计为 "+sum+"，不等于100，仍要保存？"))return;
  const res=await API("/api/assess/config",{method:"PUT",headers:j(),body:JSON.stringify({items})});
  if(res.error){await UI.alert("保存失败："+res.error);return;}await UI.alert("指标配置已保存");loadCfg();}
async function addCfg(){const b={name:val("c-name"),weight:+val("c-weight"),pass_line:+val("c-pass"),direction:val("c-dir"),input_type:val("c-type"),note:val("c-note")};
  if(!b.name){await UI.alert("指标名称为必填");return;}const res=await API("/api/assess/config",{method:"POST",headers:j(),body:JSON.stringify(b)});
  if(res.error){await UI.alert("添加失败："+res.error);return;}document.getElementById("modal-cfg").classList.remove("show");loadCfg();}
// 周期
async function loadPeriods(){const d=await API("/api/assess/periods");const opts=d.periods.map(p=>`<option value="${p}">${p}</option>`).join("");
  ["e-period","v-period","o-period","s-period"].forEach(id=>{const el=document.getElementById(id);if(el){el.innerHTML=opts;refreshCustomSelect(id);}});
  return d.periods;}
// 评分录入/修改
let recId=null, recPeriod=null;
// 各页签（scope）对应的评分字段；编辑考核不应出现「主分类版本数」等评审口径字段（制度 5.4）
const REC_SCOPE_FIELDS={edit:["r2-task","r2-fe"],review:["r2-judg","r2-mv","r2-fe"],official:["r2-off","r2-ov"],summary:["r2-judg","r2-task","r2-off","r2-fb","r2-ov","r2-mv","r2-fe"]};
function toggleRecFields(scope){const show=new Set(REC_SCOPE_FIELDS[scope]||REC_SCOPE_FIELDS.summary);
  ["r2-judg","r2-task","r2-off","r2-fb","r2-ov","r2-mv","r2-fe"].forEach(id=>{const el=document.getElementById(id);if(!el)return;const lab=el.closest("label");if(lab)lab.style.display=show.has(id)?"":"none";});}
function openRec(id,scope){recId=id||null;scope=scope||currentScope();recPeriod=scopePeriod(scope)||scopePeriod("summary");toggleRecFields(scope);
  document.getElementById("rec-title").textContent=id?"修改评分":"录入评分";
  ["r2-account","r2-period","r2-judg","r2-task","r2-off","r2-fb","r2-ov","r2-mv","r2-fe","r2-op","r2-vreason","r2-note"].forEach(x=>document.getElementById(x).value="");
  document.getElementById("r2-veto").checked=false;document.getElementById("r2-period").value=recPeriod||"";
  if(id){fetch("/api/assess/records?period="+encodeURIComponent(recPeriod||"")).then(r=>r.json()).then(d=>{const r=d.rows.find(x=>String(x.id)===String(id));if(r)setRec(r);});}
  document.getElementById("modal-rec").classList.add("show");}
function setRec(r){document.getElementById("r2-account").value=r.account_id;document.getElementById("r2-period").value=r.period;document.getElementById("r2-judg").value=r.v_judgment;document.getElementById("r2-task").value=r.v_task;document.getElementById("r2-off").value=r.v_official_err;document.getElementById("r2-fb").value=r.v_feedback;document.getElementById("r2-ov").value=r.official_versions;document.getElementById("r2-mv").value=r.main_cat_versions;document.getElementById("r2-fe").value=r.feature_edits;document.getElementById("r2-veto").checked=!!r.veto;document.getElementById("r2-vreason").value=r.veto_reason||"";document.getElementById("r2-note").value=r.note||"";document.getElementById("r2-op").value=r.operator||"";}
async function saveRec(){if(!requireAuth())return;const b={account_id:val("r2-account"),period:val("r2-period")||recPeriod,v_judgment:+val("r2-judg"),v_task:+val("r2-task"),v_official_err:+val("r2-off"),v_feedback:+val("r2-fb"),official_versions:+val("r2-ov"),main_cat_versions:+val("r2-mv"),feature_edits:+val("r2-fe"),veto:document.getElementById("r2-veto").checked,veto_reason:val("r2-vreason"),note:val("r2-note"),operator:val("r2-op")};
  if(!b.account_id||!b.period){await UI.alert("账号与周期为必填");return;}
  if(b.veto&&!b.veto_reason){await UI.alert("已勾选一票否决，须选择具体否决项（制度 5.5 共 8 项）");return;}
  const res=recId?await fetch("/api/assess/records/"+recId,{method:"PUT",headers:j(),body:JSON.stringify(b)}).then(r=>r.json()):await API("/api/assess/records",{method:"POST",headers:j(),body:JSON.stringify(b)});
  if(res.error){await UI.alert("保存失败："+res.error);return;}document.getElementById("modal-rec").classList.remove("show");const s=currentScope();if(s==="edit"||s==="review"||s==="official")loadScope(s);if(s==="summary")loadSummary();loadOverview();loadLogs();}

// 申请管理（新评审报名申请流程）
const EVAL_NODES=["资格待核查","待授权","已授权","待转正评估","评估完成"];
const EVAL_RESULTS=["待评估","不通过","通过转正","实习"];
const REG_CONDITIONS=[
  "近6个月累计编辑通过版本≥500个",
  "进阶难度任务累计达标≥100个",
];
async function loadApplys(){const d=await API("/api/registrations");
  const node=val("ap-node"), result=val("ap-result"), kw=(val("ap-keyword")||"").trim().toLowerCase();
  const rows=d.rows.filter(r=>{
    if(node && (r.eval_node||"")!==node) return false;
    if(result && (r.eval_result||"")!==result) return false;
    if(kw){const hay=((r.apply_id||"")+(r.category||"")+(r.referrer||"")).toLowerCase(); if(!hay.includes(kw)) return false;}
    return true;
  });
  document.getElementById("ap-body").innerHTML=rows.length?rows.map(r=>{
    const resultClass={"通过转正":"g","实习":"g","不通过":"r","待评估":"y"}[r.eval_result]||"n";
    const isAdmin=!!(ME&&ME.is_admin);
    const isApplicant=!!(ME&&ME.account_id===r.apply_id);
    let acts="";
    if(isAdmin){acts+=`<button class="linkbtn" data-rge="${r.id}">评</button><button class="linkbtn del" data-rgd="${r.id}">删</button>`;}
    else if(isApplicant){acts+=`<button class="linkbtn" data-rg="${r.id}">改</button><button class="linkbtn del" data-rgd="${r.id}">删</button>`;}
    return `<tr>
    <td>${r.apply_time||""}</td><td>${r.apply_id||""}</td><td>${r.qq||""}</td><td>${r.referrer||""}</td>
    <td>${r.category||""}</td><td>${r.condition_type||""}</td><td>${r.eval_node||"—"}</td><td>${r.eval_node_time||""}</td>
    <td><span class="pill ${resultClass}">${r.eval_result||"—"}</span></td>
    <td>${r.evaluator||""}</td><td class="wrap">${r.note||""}</td>
    <td>${acts||'<span class="muted">—</span>'}</td></tr>`;}).join(""):'<tr><td colspan="12" class="empty">暂无申请记录</td></tr>';
  document.querySelectorAll("#ap-body [data-rg]").forEach(b=>b.onclick=()=>openApply(b.dataset.rg));
  document.querySelectorAll("#ap-body [data-rge]").forEach(b=>b.onclick=()=>openEval(b.dataset.rge));
  document.querySelectorAll("#ap-body [data-rgd]").forEach(b=>b.onclick=async()=>{if(!requireAuth())return;if(await UI.confirm("确认删除该申请？")){const res=await fetch("/api/registrations/"+b.dataset.rgd,{method:"DELETE",headers:j()}).then(r=>r.json());if(res.error){await UI.alert("删除失败："+res.error);return;}loadApplys();}});}
let regId=null, regScreenshotPath="", regEvalNode="";
// 把库内存储路径（data/screenshots/<sub>/<file>）转换为可访问的接口 URL（/api/screenshots/<sub>/<file>）
function shotUrl(p){
  if(!p) return "";
  let u=p.replace(/^data\/screenshots\//, "/api/screenshots/");
  if(TOKEN) u+=(u.indexOf("?")>=0?"&":"?")+"token="+encodeURIComponent(TOKEN);
  return u;
}
function resetApplyForm(){
  regEvalNode="";
  ["rg-applyid","rg-qq","rg-category","rg-note"].forEach(x=>{const el=document.getElementById(x);if(el){el.value="";el.readOnly=false;}});
  document.getElementById("rg-referrer").value=(ME&&ME.account_id)||"";
  document.getElementById("rg-level").value="初审";
  document.getElementById("rg-applytime").value="";
  document.querySelectorAll('input[name="rg-condition"]').forEach(el=>el.checked=false);
  const file=document.getElementById("rg-screenshot"); file.value="";
  document.getElementById("rg-screenshot-name").textContent="点击选择图片，或拖拽文件到此处";
  document.getElementById("rg-screenshot-preview").style.display="none";
  document.getElementById("rg-screenshot-preview").innerHTML="";
  regScreenshotPath="";
}
function setApplyPreview(path){
  const wrap=document.getElementById("rg-screenshot-preview");
  if(!wrap)return;
  if(!path){wrap.style.display="none";wrap.innerHTML="";return;}
  wrap.style.display="block";
  wrap.innerHTML=`<a href="${shotUrl(path)}" target="_blank"><img src="${shotUrl(path)}" alt="报名条件截图" title="点击查看原图"></a>`;
}
async function uploadRegScreenshot(input){
  if(!input.files[0])return;
  const fd=new FormData();fd.append("file",input.files[0]);
  const up=await fetch("/api/upload/screenshot",{method:"POST",headers:{Authorization:"Bearer "+TOKEN},body:fd}).then(r=>r.json());
  if(up.error){await UI.alert("截图上传失败："+up.error);return;}
  regScreenshotPath=up.path;setApplyPreview(regScreenshotPath);
}
function openApply(id){regId=id||null;resetApplyForm();document.getElementById("ap-title").textContent=id?"修改申请":"新增申请";
  if(id){fetch("/api/registrations").then(r=>r.json()).then(d=>{const r=d.rows.find(x=>String(x.id)===String(id));if(r){
    document.getElementById("rg-level").value=r.apply_level||"初审";
    document.getElementById("rg-applytime").value=r.apply_time||"";
    document.getElementById("rg-applyid").value=r.apply_id||"";
    document.getElementById("rg-qq").value=r.qq||"";
    document.getElementById("rg-referrer").value=r.referrer||"";
    document.getElementById("rg-category").value=r.category||"";
    if(r.condition_type){const cb=document.querySelector('input[name="rg-condition"][value="'+r.condition_type.replace(/"/g,'&quot;')+'"]');if(cb)cb.checked=true;}
    regScreenshotPath=r.screenshot_path||"";
    setApplyPreview(regScreenshotPath);
    regEvalNode=r.eval_node||"";
    lockApplyForm();
  }});}
  else{regEvalNode="";lockApplyForm();}
  document.getElementById("modal-apply").classList.add("show");}
function lockApplyForm(){
  const node=regEvalNode||"";
  const locked=!!node&&node!=="资格待核查";
  ["rg-applyid","rg-qq","rg-category","rg-note"].forEach(x=>{const el=document.getElementById(x);if(el)el.readOnly=locked;});
  document.querySelectorAll('input[name="rg-condition"]').forEach(el=>el.disabled=locked);
  const file=document.getElementById("rg-screenshot");
  if(file)file.disabled=locked;
  const label=document.getElementById("rg-screenshot-label");
  if(label){label.style.pointerEvents=locked?"none":"auto";label.style.opacity=locked?".6":"1";}
  const save=document.getElementById("rg-save");
  const submitEval=document.getElementById("rg-submit-eval");
  const hint=document.getElementById("rg-lockhint");
  if(locked){
    if(save)save.style.display="none";
    if(hint){hint.style.display="";hint.textContent="当前流程节点为「"+node+"」，资格审查后申请内容已锁定，不可修改。"+(node==="已授权"?"（已授权，可在下方提交评估申请）":"");}
    if(submitEval)submitEval.style.display=(node==="已授权")?"":"none";
  }else{
    if(save)save.style.display="";
    if(hint)hint.style.display="none";
    if(submitEval)submitEval.style.display="none";
  }
}
async function saveApply(){if(!requireAuth())return;
  if(regEvalNode&&regEvalNode!=="资格待核查"){await UI.alert("资格审查后申请内容已锁定，不可修改（当前节点："+regEvalNode+"）");return;}
  const applyId=val("rg-applyid").trim();
  if(!applyId){await UI.alert("百科ID 为必填");return;}
  const category=val("rg-category").trim();
  if(!category){await UI.alert("报名分类为必填");return;}
  const conditionEl=document.querySelector('input[name="rg-condition"]:checked');
  if(!conditionEl){await UI.alert("请选择报名条件选项");return;}
  const fileInput=document.getElementById("rg-screenshot");
  if(!regId && !regScreenshotPath){await UI.alert("请上传报名条件截图");return;}
  const screenshotPath=regScreenshotPath;
  const b={apply_id:applyId,qq:val("rg-qq"),referrer:val("rg-referrer"),category:category,condition_type:conditionEl.value,screenshot_path:screenshotPath,note:val("rg-note")};
  const res=regId?await fetch("/api/registrations/"+regId,{method:"PUT",headers:j(),body:JSON.stringify(b)}).then(r=>r.json()):await API("/api/registrations",{method:"POST",headers:j(),body:JSON.stringify(b)});
  if(res.error){await UI.alert("保存失败："+res.error);return;}document.getElementById("modal-apply").classList.remove("show");loadApplys();}
async function submitEvalApply(){if(!requireAuth())return;
  const res=await fetch("/api/registrations/"+regId,{method:"PUT",headers:j(),body:JSON.stringify({action:"submit_eval_apply"})});
  const d=await res.json();
  if(d.error){await UI.alert("提交失败："+d.error);return;}
  document.getElementById("modal-apply").classList.remove("show");loadApplys();}

let evalId=null;
function openEval(id){if(!requireAuth())return;evalId=id||null;document.getElementById("ev-title").textContent="评估报名";
  ["ev-level","ev-applytime","ev-applyid","ev-qq","ev-referrer","ev-category","ev-condition","ev-note","ev-nodetime","ev-evaluator","ev-resulttime"].forEach(x=>document.getElementById(x).value="");
  document.getElementById("ev-node").value="";document.getElementById("ev-result").value="";
  document.getElementById("ev-screenshot-wrap").innerHTML="";
  fetch("/api/registrations").then(r=>r.json()).then(d=>{const r=d.rows.find(x=>String(x.id)===String(id));if(r){
    document.getElementById("ev-level").value=r.apply_level||"";
    document.getElementById("ev-applytime").value=r.apply_time||"";
    document.getElementById("ev-applyid").value=r.apply_id||"";
    document.getElementById("ev-qq").value=r.qq||"";
    document.getElementById("ev-referrer").value=r.referrer||"";
    document.getElementById("ev-category").value=r.category||"";
    document.getElementById("ev-condition").value=r.condition_type||"";
    document.getElementById("ev-note").value=r.note||"";
    document.getElementById("ev-node").value=r.eval_node||"";
    document.getElementById("ev-nodetime").value=r.eval_node_time||"";
    document.getElementById("ev-result").value=r.eval_result||"";
    document.getElementById("ev-evaluator").value=r.evaluator||"";
    document.getElementById("ev-resulttime").value=r.eval_result_time||"";
    document.getElementById("ev-decision").value="";
    refreshCustomSelect("ev-result");refreshCustomSelect("ev-decision");
    const decWrap=document.getElementById("ev-decision-wrap");if(decWrap)decWrap.style.display=(r.eval_node||"")==="资格待核查"?"":"none";
    const adm=!!(ME&&ME.is_admin);
    const authBtn=document.getElementById("ev-authorize");if(authBtn)authBtn.style.display=(r.eval_node==="待授权"&&adm)?"":"none";
    const sp=r.screenshot_path||"";
    document.getElementById("ev-screenshot-wrap").innerHTML=sp?`<a href="${shotUrl(sp)}" target="_blank"><img src="${shotUrl(sp)}" alt="报名条件截图" title="点击查看原图"></a>`:'<span class="muted">未上传</span>';
    // 跨权防卫：节点顺序除超级管理员外不可回转；评估结果须流程进入「待转正评估」后方可填改，且非「待评估」后仅超级管理员可修改
    const sa=!!(ME&&ME.is_super_admin);
    const curIdx=EVAL_NODES.indexOf(r.eval_node||"");
    document.querySelectorAll("#ev-node option").forEach(o=>{const i=EVAL_NODES.indexOf(o.value);o.disabled=!sa&&i>=0&&curIdx>=0&&i<curIdx;});
    const resSel=document.getElementById("ev-result");
    const canEditResult = (r.eval_node==="待转正评估") && (sa || !r.eval_result || r.eval_result==="待评估");
    resSel.disabled=!canEditResult;
    const resWrap=SEL_WRAP.get(resSel);
    if(resWrap) resWrap.classList.toggle("disabled", !canEditResult);
    const resHint=document.getElementById("ev-result-hint");
    if(resHint) resHint.style.display = r.eval_node==="待转正评估" ? "none" : "";
    refreshCustomSelect(document.getElementById("ev-result"));
  }});
  document.getElementById("modal-eval").classList.add("show");}
async function saveEval(){if(!requireAuth())return;
  const node=val("ev-node");
  if(!node){await UI.alert("请选择当前流程节点");return;}
  const b={action:"eval",eval_node:node,eval_result:val("ev-result")||""};
  const dec=val("ev-decision");
  if(dec)b.decision=dec;
  if(node==="待转正评估"&&(b.eval_result==="通过转正"||b.eval_result==="实习")) b.eval_node="评估完成";
  const res=await fetch("/api/registrations/"+evalId,{method:"PUT",headers:j(),body:JSON.stringify(b)}).then(r=>r.json());
  if(res.error){await UI.alert("保存失败："+res.error);return;}document.getElementById("modal-eval").classList.remove("show");loadApplys();}
async function submitAuthorize(){if(!requireAuth())return;
  const res=await fetch("/api/registrations/"+evalId,{method:"PUT",headers:j(),body:JSON.stringify({action:"authorize"})});
  const d=await res.json();
  if(d.error){await UI.alert("授权失败："+d.error);return;}
  document.getElementById("modal-eval").classList.remove("show");loadApplys();}

// 升级申请 / 分类扩充（已并入「申请管理」） / 官方名单
const UP_SCHEMA={
  "apply":{api:"upgrade-applies",title:"升级申请",addBtn:"btn-up-apply-add",body:"up-apply-body",
    fields:[
      {k:"apply_id",l:"百科ID",type:"text",req:true,list:"acct-list"},
      {k:"qq",l:"QQ",type:"text"},
      {k:"referrer",l:"推荐人百科ID",type:"readonly"},
      {k:"category",l:"申请分类",type:"text",req:true,list:"cat-list"},
      {k:"screenshot_path",l:"报名条件截图",type:"file"},
      {k:"apply_time",l:"申请时间",type:"readonly",placeholder:"提交后自动生成"},
      {k:"note",l:"备注",type:"textarea"},
    ]},
  "expand":{api:"category-expands",title:"分类扩充申请",addBtn:"btn-up-expand-add",body:"up-expand-body",
    fields:[
      {k:"apply_id",l:"申请人账号（百科ID）",type:"readonly",lock:true,defaultMe:true},
      {k:"category",l:"申请扩充分类",type:"text",req:true,list:"cat-list"},
      {k:"apply_time",l:"申请时间",type:"readonly",placeholder:"提交后自动生成"},
      {k:"note",l:"备注",type:"textarea"},
    ]},
};
function showApplySub(sub){document.querySelectorAll("#page-apply .subtab").forEach(b=>b.classList.toggle("active",b.dataset.apply===sub));
  ["newapply","upgrade","expand","quota","official"].forEach(s=>{const el=document.getElementById("ap-"+s);if(el)el.style.display=s===sub?"block":"none";});
  if(sub==="newapply")loadApplys();else if(sub==="upgrade")loadUpgrade("apply");else if(sub==="expand")loadUpgrade("expand");else if(sub==="quota")loadQuota();else if(sub==="official")loadOfficialPackages();}
function upNodePill(n){if(n==="评估完成")return"g";if(n==="待授权"||n==="已授权"||n==="待转正评估"||n==="已公示")return"b";return"n";}
async function acceptUpgrade(id,decision,kind){
  upAccKind=kind||"upgrade";upDecKind=kind||"upgrade";
  if(!requireAuth())return;
  if(decision==="decline")openUpDecline(id);
  else openUpAccept(id);
}
// 升级中审 · 受理 / 不受理（弹窗：只读申请表单 + 操作表单）
let upAccId=null, upDecId=null, upAccKind="upgrade", upDecKind="upgrade";
function upApiBase(kind){return (kind==="expand")?"/api/category-expands":"/api/upgrade-applies";}
function buildFeatReadonlyHTML(feats){
  const arr=feats||[];if(!arr.length)return "";
  let h=`<label class="full">特色词条编辑达标记录</label><div class="feat-list" style="grid-column:1/-1">`;
  h+=arr.map(f=>{
    const link=(f.entry_link||"").trim();const safeLink=link.replace(/"/g,'&quot;');
    const linkCell=link?`<a class="fr-link-a" href="${safeLink}" target="_blank" rel="noopener" title="点击跳转">${link}</a>`:`<span class="fr-link-a empty">（无链接）</span>`;
    return `<div class="feat-row" style="background:#fafbff">`
      +`<input class="fr-entry" readonly value="${(f.entry_name||"").replace(/"/g,'&quot;')}">`
      +linkCell
      +`<input class="fr-ctime" readonly value="${(f.compliant_time||"").replace(/"/g,'&quot;')}">`
      +`<input class="fr-note" readonly value="${(f.note||"").replace(/"/g,'&quot;')}">`
      +`<button type="button" class="linkbtn fr-open" data-link="${safeLink}">打开</button>`
      +`</div>`;
  }).join("");
  h+=`</div>`;
  return h;
}
function buildUpReadonlyHTML(r,shotId){
  let h=[
    ["百科ID",r.apply_id],["QQ",r.qq],["推荐人百科ID",r.referrer],["申请分类",r.category],
    ["当前节点",r.eval_node],["申请时间",r.apply_time],["备注",r.note]
  ].map(([k,v])=>`<label>${k}<input readonly value="${(v||"").replace(/"/g,'&quot;')}"></label>`).join("")
  + `<label class="full">报名条件截图<div id="${shotId}" class="screenshot-preview" style="display:none"></div></label>`
  + buildFeatReadonlyHTML(r.features);
  return h;
}
function setShot(id,p){const el=document.getElementById(id);if(!el)return;
  if(p){el.style.display="";el.innerHTML=`<a href="${shotUrl(p)}" target="_blank"><img src="${shotUrl(p)}" alt="截图预览"></a>`;}
  else{el.style.display="none";el.innerHTML="";}}
async function openUpAccept(id){
  if(!requireAuth())return;upAccId=id;
  const d=await API(upApiBase(upAccKind));
  const r=(d.rows||[]).find(x=>String(x.id)===String(id));
  const box=document.getElementById("upacc-apply");
  if(r){box.innerHTML=buildUpReadonlyHTML(r,"upacc-shot");setShot("upacc-shot",r.screenshot_path);}
  else box.innerHTML='<span class="muted">未找到该申请</span>';
  document.getElementById("upacc-remark").value="";
  document.getElementById("modal-up-accept").classList.add("show");
}
async function openUpDecline(id){
  if(!requireAuth())return;upDecId=id;
  const d=await API(upApiBase(upDecKind));
  const r=(d.rows||[]).find(x=>String(x.id)===String(id));
  const box=document.getElementById("updec-apply");
  if(r){box.innerHTML=buildUpReadonlyHTML(r,"updec-shot");setShot("updec-shot",r.screenshot_path);}
  else box.innerHTML='<span class="muted">未找到该申请</span>';
  document.getElementById("updec-reason").value="";
  document.getElementById("modal-up-decline").classList.add("show");
}
async function submitUpAccept(){
  if(!requireAuth()||!upAccId)return;
  const remark=document.getElementById("upacc-remark").value.trim();
  const res=await fetch(upApiBase(upAccKind)+"/"+upAccId,{method:"PUT",headers:j(),body:JSON.stringify({action:"accept",op_remark:remark})}).then(r=>r.json());
  if(res.error){await UI.alert("受理失败："+res.error);return;}
  document.getElementById("modal-up-accept").classList.remove("show");loadUpgrade(upAccKind);
}
async function submitUpDecline(){
  if(!requireAuth()||!upDecId)return;
  const reason=document.getElementById("updec-reason").value.trim();
  if(!reason){await UI.alert("不受理理由为必填");return;}
  const res=await fetch(upApiBase(upDecKind)+"/"+upDecId,{method:"PUT",headers:j(),body:JSON.stringify({action:"decline",op_remark:reason})}).then(r=>r.json());
  if(res.error){await UI.alert("不受理失败："+res.error);return;}
  document.getElementById("modal-up-decline").classList.remove("show");loadUpgrade(upDecKind);
}
async function loadUpgrade(sub){const sc=UP_SCHEMA[sub];if(!sc)return;
  const url="/api/"+sc.api;
  const isApply = sub==="apply" || sub==="expand";
  const sourceType = sub==="apply" ? "upgrade" : (sub==="expand" ? "expand" : null);
  const kind = isApply ? (sub==="expand" ? "expand" : "upgrade") : null;
  const [d, sd] = await Promise.all([
    API(url),
    isApply ? API("/api/status-strip-applies?source_type="+sourceType) : Promise.resolve({rows:[]})
  ]);
  const stripMap={}; (sd.rows||[]).forEach(s=>{ if(s.source_id) stripMap[s.source_id]=s; });
  const body=document.getElementById(sc.body);
  if(sub==="apply"||sub==="expand"){
    const rows=d.rows||[];
    body.innerHTML=rows.length?rows.map(r=>{
      const strip=stripMap[r.id];
      const resCls=({"通过转正":"g","实习":"y","不通过":"r"})[r.eval_result]||"n";
      const tds=`<td>${r.apply_time||""}</td><td>${r.apply_id||""}</td><td>${r.qq||""}</td><td>${r.category||""}</td>`
        +`<td><span class="pill ${upNodePill(r.eval_node)}">${r.eval_node||""}</span></td>`
        +`<td>${r.eval_node_time||""}</td><td><span class="pill ${resCls}">${r.eval_result||"待评估"}</span></td><td>${r.evaluator||""}</td><td>${r.note||""}</td>`
        +renderStripStatusCell(strip);
      const isOp=!!(ME&&ME.account_id===r.apply_id);
      const isAdm=!!(ME&&ME.is_admin), isRev=!!(ME&&ME.is_reviewer);
      const isSuper=!!(ME&&ME.is_super_admin);
      const evalRoles=ME&&ME.eval_roles?ME.eval_roles:[];
      const isReviewLeader=isAdm||isRev;   // 受理/推进代理
      const isPublishLeader=evalRoles.includes("评审相关负责人")||isSuper;
      const hasEvalRole=evalRoles.length>0||isSuper;
      const node=r.eval_node||"资格待核查";
      let acts="";
      if(ME){
        if(isOp||isAdm) acts+=`<button class="linkbtn" data-up="${r.id}">改</button>`;
        if(isReviewLeader&&node==="资格待核查"){
          acts+=`<button class="linkbtn" data-accept="${r.id}">受理</button>`;
          acts+=`<button class="linkbtn del" data-decline="${r.id}">不受理</button>`;
        }else if(isReviewLeader&&(node==="待授权"||node==="已授权")){
          acts+=`<button class="linkbtn" data-accept="${r.id}">受理</button>`;
        }
        // 待转正评估/已公示：已绑定评审角色可评；超级管理员可修正
        if((node==="待转正评估"||node==="已公示")&&hasEvalRole) acts+=`<button class="linkbtn" data-eval="${r.id}">评</button>`;
        // 已公示/评估完成：评估留痕对公众（登录用户）只读可见
        if(node==="已公示"||node==="评估完成") acts+=`<button class="linkbtn" data-trace="${r.id}">留痕</button>`;
        // 已公示：仅「评审相关负责人」（含超级管理员）可确认发布
        if(node==="已公示"&&isPublishLeader) acts+=`<button class="linkbtn primary" data-publish="${r.id}">确认发布</button>`;
        // 删除：仅本人、管理员或超级管理员
        if(isOp||isAdm||isSuper) acts+=`<button class="linkbtn del" data-upd="${r.id}">删</button>`;
      }
      if(!acts) acts='<span class="muted">—</span>';
      return `<tr>${tds}<td>${acts}</td></tr>`;
    }).join(""):`<tr><td colspan="11" class="empty">暂无升级申请</td></tr>`;
    body.querySelectorAll("[data-up]").forEach(b=>b.onclick=()=>openUp(sub,b.dataset.up));
    body.querySelectorAll("[data-upd]").forEach(b=>b.onclick=async()=>{if(!requireAuth())return;if(await UI.confirm("确认删除？")){const res=await fetch("/api/"+sc.api+"/"+b.dataset.upd,{method:"DELETE",headers:j()}).then(r=>r.json());if(res.error){await UI.alert("删除失败："+res.error);return;}loadUpgrade(sub);}});
    body.querySelectorAll("[data-accept]").forEach(b=>b.onclick=()=>acceptUpgrade(b.dataset.accept,"accept",kind));
    body.querySelectorAll("[data-decline]").forEach(b=>b.onclick=()=>acceptUpgrade(b.dataset.decline,"decline",kind));
    body.querySelectorAll("[data-eval]").forEach(b=>b.onclick=()=>openUpEval(b.dataset.eval,kind));
    body.querySelectorAll("[data-trace]").forEach(b=>b.onclick=()=>openUpEval(b.dataset.trace,kind));
    body.querySelectorAll("[data-publish]").forEach(b=>b.onclick=()=>{upEvalId=b.dataset.publish;openUpEval(upEvalId,kind);});
    bindStripActions(sc.body, sub);
    return;
  }
  const cols=sc.fields;
  body.innerHTML=d.rows.length?d.rows.map(r=>{
    const strip = stripMap[r.id];
    const tds=cols.map(f=>{const v=r[f.k]||"";
      if(f.k==="status")return `<td><span class="pill ${v==="已通过"||v==="在任"?"g":(v==="已驳回"||v==="离任"?"r":"n")}">${v}</span></td>`;
      if(f.k==="account_id")return `<td>${v}${r.display_name&&r.display_name!==v?`<br><span class="muted">${r.display_name}</span>`:""}</td>`;
      return `<td>${v}</td>`;}).join("") + renderStripStatusCell(strip);
    const isOp = !!(ME && ME.account_id === r.account_id);
    const canEdit = !!(ME && (isOp || ME.is_admin));
    const canDel = sub==="apply" ? isOp : !!(ME && ME.is_admin);
    let acts="";
    if(ME){
      if(canEdit) acts += `<button class="linkbtn" data-up="${r.id}">改</button>`;
      if(canDel) acts += `<button class="linkbtn del" data-upd="${r.id}">删</button>`;
      acts += renderStripActions(r, sub, strip);
    }
    if(!acts) acts = '<span class="muted">—</span>';
    return `<tr>${tds}<td>${acts}</td></tr>`;}).join(""):`<tr><td colspan="${cols.length+2}" class="empty">暂无记录</td></tr>`;
  body.querySelectorAll("[data-up]").forEach(b=>b.onclick=()=>openUp(sub,b.dataset.up));
  body.querySelectorAll("[data-upd]").forEach(b=>b.onclick=async()=>{if(!requireAuth())return;if(await UI.confirm("确认删除？")){const res=await fetch("/api/"+sc.api+"/"+b.dataset.upd,{method:"DELETE",headers:j()}).then(r=>r.json());if(res.error){await UI.alert("删除失败："+res.error);return;}loadUpgrade(sub);}});
  bindStripActions(sc.body, sub);
}
// 官方任务包（名单管理）
async function loadOfficialPackages(){const kw=(document.getElementById("official-kw")?.value||"").trim();
  const url="/api/official-task-packages"+(kw?"?kw="+encodeURIComponent(kw):"");
  const d=await API(url);
  document.getElementById("up-official-body").innerHTML=d.rows.length?d.rows.map(r=>`<tr>
    <td>${r.task_id||"—"}</td><td><b>${r.task_name||"—"}</b></td><td>${r.creator||"—"}</td>
    <td>${r.member_count||0}</td><td>${r.owner||"—"}</td><td>${r.updated_at||r.created_at||"—"}</td>
    <td>${ME?`<button class="linkbtn" data-official-id="${r.id}">编辑</button><button class="linkbtn" data-official-view="${r.id}">展开</button><button class="linkbtn del" data-official-del="${r.id}">删除</button>`:'<span class="muted">—</span>'}</td></tr>`).join(""):'<tr><td colspan="7" class="empty">暂无官方任务包</td></tr>';
  document.querySelectorAll("#up-official-body [data-official-id]").forEach(b=>b.onclick=()=>openOfficialPackage(b.dataset.officialId));
  document.querySelectorAll("#up-official-body [data-official-view]").forEach(b=>b.onclick=()=>toggleOfficialMembers(b.dataset.officialView,b.closest("tr")));
  document.querySelectorAll("#up-official-body [data-official-del]").forEach(b=>b.onclick=async()=>{if(!requireAuth())return;if(await UI.confirm("确认删除该任务包？")){const res=await fetch("/api/official-task-packages/"+b.dataset.officialDel,{method:"DELETE",headers:j()}).then(r=>r.json());if(res.error){await UI.alert("删除失败："+res.error);return;}loadOfficialPackages();}});}
async function toggleOfficialMembers(pid,tr){
  const next=tr.nextElementSibling;
  if(next&&next.classList.contains("official-members-row")){next.remove();return;}
  const d=await API("/api/official-task-packages/"+pid);
  if(!d||d.error)return;
  const list=(d.members||[]).map(m=>`<span class="pill b">${m.account_id}${m.display_name&&m.display_name!==m.account_id?"("+m.display_name+")":""}</span>`).join(" ")||'<span class="muted">暂无参与人员</span>';
  const row=document.createElement("tr");row.className="official-members-row";
  row.innerHTML=`<td colspan="7" style="background:#fafbff;padding:12px 14px"><div style="margin-bottom:6px;font-weight:600;color:var(--sub)">参与人员：</div>${list}</td>`;
  tr.parentNode.insertBefore(row,tr.nextSibling);}
let officialId=null;
function openOfficialPackage(id){if(!requireAuth())return;officialId=id||null;
  document.getElementById("official-title").textContent=id?"编辑官方任务包":"新增官方任务包";
  ["off-name","off-task-id","off-creator","off-owner","off-members","off-note"].forEach(x=>document.getElementById(x).value="");
  document.getElementById("off-level").value="";
  refreshCustomSelect(document.getElementById("off-level"));
  if(id){fetch("/api/official-task-packages/"+id).then(r=>r.json()).then(d=>{
    if(d.error)return;
    document.getElementById("off-name").value=d.task_name||"";
    document.getElementById("off-task-id").value=d.task_id||"";
    document.getElementById("off-creator").value=d.creator||"";
    document.getElementById("off-owner").value=d.owner||"";
    document.getElementById("off-level").value=d.members&&d.members[0]?d.members[0].required_level||"":"";
    refreshCustomSelect(document.getElementById("off-level"));
    document.getElementById("off-members").value=(d.members||[]).map(m=>m.account_id).join("\n");
    document.getElementById("off-note").value=d.note||"";
  });}
  document.getElementById("modal-official").classList.add("show");}
async function saveOfficialPackage(){if(!requireAuth())return;
  const b={task_name:val("off-name"),task_id:val("off-task-id"),creator:val("off-creator"),owner:val("off-owner"),required_level:val("off-level"),members:val("off-members"),note:val("off-note"),operator:(ME&&ME.account_id)||""};
  if(!b.task_name||!b.task_id||!b.creator){await UI.alert("任务名称、任务ID、任务创建者为必填");return;}
  const url="/api/official-task-packages"+(officialId?"/"+officialId:"");
  const res=await fetch(url,{method:officialId?"PUT":"POST",headers:j(),body:JSON.stringify(b)}).then(r=>r.json());
  if(res.error){await UI.alert("保存失败："+res.error);return;}
  document.getElementById("modal-official").classList.remove("show");loadOfficialPackages();}
async function loadQuota(){const d=await API("/api/upgrade/quota");
  document.getElementById("up-quota-body").innerHTML=d.rows.length?d.rows.map(r=>`<tr>
    <td>${r.account_id}${r.display_name&&r.display_name!==r.account_id?`<br><span class="muted">${r.display_name}</span>`:""}</td>
    <td>${r.month}</td><td>${r.count}</td><td>${r.limit}</td>
    <td><span class="pill ${r.over?"r":"g"}">${r.over?"超额":"未超额"}</span></td></tr>`).join(""):'<tr><td colspan="5" class="empty">暂无分类扩充申请</td></tr>';}
let upSub=null, upId=null, upScreenshotPath="";
function openUp(sub,id){if(!requireAuth())return;upSub=sub;upId=id||null;const sc=UP_SCHEMA[sub];
  document.getElementById("up-title").textContent=(id?"修改":"新增")+sc.title;
  const box=document.getElementById("up-form");
  upScreenshotPath="";
  // 主字段（排除 file 类型与 备注：file 单独渲染、备注置末尾）
  const mainFields=sc.fields.filter(f=>f.type!=="file"&&f.k!=="note"&&!f.hide);
  let html=mainFields.map(f=>{
    if(f.type==="readonly")return `<label>${f.l}<input data-k="${f.k}"${f.lock?' data-lock="1"':''} readonly placeholder="${f.placeholder||''}"></label>`;
    if(f.type==="select"){const opts=(f.opts||[]).map(o=>`<option value="${o}">${o}</option>`).join("");return `<label>${f.l}${f.req?"*":""}<select data-k="${f.k}">${opts}</select></label>`;}
    if(f.type==="textarea")return `<label class="full">${f.l}<textarea data-k="${f.k}"></textarea></label>`;
    const list=f.list?` list="${f.list}"`:"";return `<label>${f.l}${f.req?"*":""}<input data-k="${f.k}"${list}></label>`;
  }).join("");
  // 截图上传（file 类型）
  const fileField=sc.fields.find(f=>f.type==="file");
  if(fileField){html+=`<label class="full">${fileField.l}<span class="req-star">*</span>
    <div class="file-upload full">
      <input type="file" id="up-screenshot" accept="image/*" hidden>
      <label for="up-screenshot" class="file-label" id="up-screenshot-label">
        <svg class="file-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
        <span class="file-text" id="up-screenshot-name">点击选择图片，或拖拽文件到此处</span>
        <span class="file-btn">选择文件</span>
      </label>
    </div>
    <div id="up-shot-preview" class="screenshot-preview" style="display:none"></div>
  </label>`;}
  // 特色词条编辑达标记录（apply / expand：置于 备注 之前）
  if(sub==="apply"||sub==="expand"){html+='<div class="feat-block"><div class="feat-head"><span>特色词条编辑达标记录<span class="req-star">*</span></span><button type="button" class="btn ghost sm" id="up-feat-add">+ 添加一条</button></div><div class="feat-list" id="up-feat-list"></div><div class="feat-tip">单条单登记：每条记录对应一个特色词条；点击「+ 添加一条」可补充多条。</div></div>';}
  // 备注（末尾）
  const noteField=sc.fields.find(f=>f.k==="note");
  if(noteField) html+=`<label class="full">${noteField.l}<textarea data-k="note"></textarea></label>`;
  box.innerHTML=html;
  initCustomSelects();
  if(ME){
    const ref=box.querySelector('[data-k="referrer"]');if(ref&&!ref.value)ref.value=ME.account_id||"";
    sc.fields.forEach(f=>{if(f.defaultMe){const el=box.querySelector('[data-k="'+f.k+'"]');if(el)el.value=ME.account_id||"";}});
  }
  if(sub==="apply"||sub==="expand"){document.getElementById("up-feat-add").onclick=()=>addFeatRow();}
  const sf=document.getElementById("up-screenshot");
  const sfLabel=document.getElementById("up-screenshot-label");
  const sfName=document.getElementById("up-screenshot-name");
  if(sf)sf.onchange=async()=>{const f=sf.files[0];if(sfName)sfName.textContent=f?f.name:"点击选择图片，或拖拽文件到此处";if(sfLabel)sfLabel.classList.toggle("has-file",!!f);await uploadUpScreenshot(sf);};
  if(sfLabel&&sf){
    ["dragenter","dragover"].forEach(ev=>sfLabel.addEventListener(ev,e=>{e.preventDefault();e.stopPropagation();sfLabel.classList.add("dragover");}));
    ["dragleave","drop"].forEach(ev=>sfLabel.addEventListener(ev,e=>{e.preventDefault();e.stopPropagation();sfLabel.classList.remove("dragover");}));
    sfLabel.addEventListener("drop",e=>{const f=e.dataTransfer.files&&e.dataTransfer.files[0];if(f){sf.files=e.dataTransfer.files;sf.dispatchEvent(new Event("change"));}});
  }
  if(id){fetch("/api/"+sc.api).then(r=>r.json()).then(d=>{const r=d.rows.find(x=>String(x.id)===String(id));if(r){
    sc.fields.forEach(f=>{const el=box.querySelector('[data-k="'+f.k+'"]');if(el){el.value=r[f.k]||"";if(el.tagName==="SELECT")refreshCustomSelect(el);}});
    if(sub==="apply"||sub==="expand"){renderFeatRows(r.features||[]);}
    if(sub==="apply"){upScreenshotPath=r.screenshot_path||"";setUpShotPreview(upScreenshotPath);}
    if((sub==="apply"||sub==="expand") && (r.eval_node||"")!=="资格待核查"){lockUpgradeForm(true, r.eval_node);}
  }});}
  else if(sub==="apply"||sub==="expand"){for(let i=0;i<10;i++)addFeatRow(null,true);}  // 新增默认 10 行（前 10 条必填不可删）
  if(sub==="apply"||sub==="expand")lockUpgradeForm(false);
  document.getElementById("modal-up").classList.add("show");}
function lockUpgradeForm(locked,node){
  document.querySelectorAll("#up-form [data-k]").forEach(el=>{ if(el.type!=="hidden"){ el.readOnly=(el.dataset.lock==="1")?true:locked; } });
  const sf=document.getElementById("up-screenshot"); if(sf)sf.disabled=locked;
  const sfLabel=document.getElementById("up-screenshot-label"); if(sfLabel){sfLabel.style.pointerEvents=locked?"none":"auto";sfLabel.style.opacity=locked?".6":"1";}
  document.querySelectorAll("#up-feat-list .feat-row input").forEach(el=>el.readOnly=locked);
  const addBtn=document.getElementById("up-feat-add"); if(addBtn)addBtn.style.display=locked?"none":"";
  document.querySelectorAll("#up-feat-list .fr-del").forEach(b=>b.style.display=locked?"none":"");
  const save=document.getElementById("up-save"); if(save)save.style.display=locked?"none":"";
  const hint=document.getElementById("up-lockhint"); if(hint){hint.style.display=locked?"":"none"; if(locked)hint.textContent="当前流程节点为「"+(node||"")+"」，资格审查后申请内容已锁定，不可修改。";}
}
function addFeatRow(data,locked){data=data||{};const list=document.getElementById("up-feat-list");if(!list)return;
  const row=document.createElement("div");row.className="feat-row"+(locked?" feat-locked":"");
  row.innerHTML='<input class="fr-entry" placeholder="词条名'+(locked?"（必填）":"")+'">'
    +'<input class="fr-link" placeholder="词条链接">'
    +'<input class="fr-ctime" placeholder="达标时间">'
    +'<input class="fr-note" placeholder="备注">'
    +(locked?'':'<span class="fr-acts"><button type="button" class="linkbtn fr-open" title="打开链接">打开</button><button type="button" class="linkbtn del fr-del">删</button></span>');
  row.querySelector(".fr-entry").value=data.entry_name||"";
  row.querySelector(".fr-link").value=data.entry_link||"";
  row.querySelector(".fr-ctime").value=data.compliant_time||"";
  row.querySelector(".fr-note").value=data.note||"";
  if(!locked){const del=row.querySelector(".fr-del");if(del)del.onclick=()=>row.remove();}
  list.appendChild(row);}
function renderFeatRows(arr){const list=document.getElementById("up-feat-list");if(!list)return;list.innerHTML="";(arr||[]).forEach(addFeatRow);}
function collectFeatRows(){return [...document.querySelectorAll("#up-feat-list .feat-row")].map(row=>({entry_name:(row.querySelector(".fr-entry").value||"").trim(),entry_link:(row.querySelector(".fr-link").value||"").trim(),compliant_time:(row.querySelector(".fr-ctime").value||"").trim(),note:(row.querySelector(".fr-note").value||"").trim()}));}
async function uploadUpScreenshot(input){if(!input.files[0])return;const fd=new FormData();fd.append("file",input.files[0]);
  const up=await fetch("/api/upload/screenshot",{method:"POST",headers:{Authorization:"Bearer "+TOKEN},body:fd}).then(r=>r.json());
  if(up.error){await UI.alert("截图上传失败："+up.error);return;}
  upScreenshotPath=up.path;setUpShotPreview(upScreenshotPath);}
function setUpShotPreview(p){const el=document.getElementById("up-shot-preview");if(!el)return;
  if(p){el.style.display="";el.innerHTML=`<a href="${shotUrl(p)}" target="_blank"><img src="${shotUrl(p)}" alt="截图预览" title="点击查看原图"></a>`;}
  else{el.style.display="none";el.innerHTML="";}}
async function saveUp(){if(!requireAuth())return;const sc=UP_SCHEMA[upSub];const b={};
  document.querySelectorAll("#up-form [data-k]").forEach(el=>{b[el.dataset.k]=el.value;});
  if(upSub==="apply"||upSub==="expand"){
    const feats=collectFeatRows();
    const lockedRows=[...document.querySelectorAll("#up-feat-list .feat-row.feat-locked")];
    const missing=lockedRows.filter(r=>!(r.querySelector(".fr-entry").value||"").trim());
    if(missing.length){await UI.alert("前 10 条「特色词条编辑达标记录」为必填项，请补全所有必填词条名");return;}
    if(!feats.length){await UI.alert((upSub==="expand"?"分类扩充申请":"升级申请")+"须至少登记一条「特色词条编辑达标记录」");return;}
    b.features=feats;
    b.screenshot_path=upScreenshotPath;
  }
  const res=upId?await fetch("/api/"+sc.api+"/"+upId,{method:"PUT",headers:j(),body:JSON.stringify(b)}).then(r=>r.json()):await API("/api/"+sc.api,{method:"POST",headers:j(),body:JSON.stringify(b)});
  if(res.error){await UI.alert("保存失败："+res.error);return;}document.getElementById("modal-up").classList.remove("show");loadUpgrade(upSub);}
// 升级中审 · 多人评估
let upEvalId=null, upEvalRole=null, upEvalKind="upgrade";
function currentEvalRole(my_roles){
  if(!my_roles||!my_roles.length) return null;
  if(my_roles.includes("评审相关负责人")) return "评审相关负责人";
  if(my_roles.includes("所属大团队质量组长")) return "所属大团队质量组长";
  if(my_roles.includes("分类小组长")) return "分类小组长";
  return null;
}
async function openUpEval(id, k){
  if(!requireAuth())return;
  upEvalId=id; upEvalKind=k||"upgrade";
  const base=upApiBase(upEvalKind);
  const [app, ev] = await Promise.all([API(base), API(base+"/"+id+"/evals")]);
  if(ev.error){await UI.alert("加载失败："+ev.error);return;}
  // 已绑定评审角色者可评估（严格限本人绑定角色）；其余登录用户只读查看留痕（公示后对公众可见）
  upEvalRole=currentEvalRole(ev.my_roles||[]);
  if(!upEvalRole&&ME.is_super_admin) upEvalRole="评审相关负责人";
  const r=(app.rows||[]).find(x=>String(x.id)===String(id));
  const applyBox=document.getElementById("upe-apply");
  if(r){
    applyBox.innerHTML=[
      ["百科ID",r.apply_id],["QQ",r.qq],["推荐人百科ID",r.referrer],["申请分类",r.category],
      ["当前节点",r.eval_node],["节点操作时间",r.eval_node_time||""],["申请时间",r.apply_time],
      ["评估结果",r.eval_result||"待评估"],["备注",r.note||""]
    ].map(([k,v])=>`<label>${k}<input readonly value="${(v||"").replace(/"/g,'&quot;')}"></label>`).join("")
    + `<label class="full">报名条件截图<div id="upe-shot" class="screenshot-preview" style="display:none"></div></label>`
    + buildFeatReadonlyHTML(r.features);
    const sp=r.screenshot_path||"";
    const shot=document.getElementById("upe-shot");
    if(sp){shot.style.display="";shot.innerHTML=`<a href="${shotUrl(sp)}" target="_blank"><img src="${shotUrl(sp)}" alt="截图预览"></a>`;}else{shot.style.display="none";shot.innerHTML="";}
  } else {applyBox.innerHTML='<span class="muted">未找到该申请</span>';}
  const evals=ev.rows||[];
  const node=ev.node||"资格待核查";
  const publicNode=!!ev.public;
  const submittedCount=evals.length;
  document.getElementById("upe-progress-text").textContent=submittedCount+" / 3 已提交";
  document.getElementById("upe-progress-node").textContent=node;
  document.getElementById("upe-progress-result").textContent=ev.eval_result||"待评估";
  document.querySelectorAll(".eval-role").forEach(sec=>{
    const role=sec.dataset.role;
    const agreeSel=sec.querySelector(".upe-agree");
    const reasonTa=sec.querySelector(".upe-reason");
    const ex=evals.find(e=>e.evaluator_role===role);
    const isMine = role===upEvalRole;
    sec.classList.toggle("mine",isMine);
    sec.classList.toggle("done",!!ex);
    const statusSpan=sec.querySelector(".er-status");
    if(statusSpan){statusSpan.textContent=ex?"已提交":"待提交";statusSpan.className="er-status "+(ex?"":"pending");}
    // 待转正评估阶段本人可编辑；已公示阶段仅超级管理员可修正
    const editable = isMine && (node==="待转正评估" || (node==="已公示" && ME.is_super_admin));
    agreeSel.disabled=!editable; reasonTa.disabled=!editable;
    renderSelect(agreeSel); // 同步自定义下拉的禁用态（禁用时不允许点选改值）
    if(ex){
      agreeSel.value=ex.agree||""; 
      reasonTa.value=ex.reason||"";
      reasonTa.classList.toggle("masked",!!ex.reason_masked);
    } else {agreeSel.value=""; reasonTa.value=""; reasonTa.classList.remove("masked");}
    const wbtn=sec.querySelector(".upe-withdraw");
    if(wbtn){
      wbtn.style.display = (isMine && ex && node==="待转正评估") ? "" : "none";
      if(!wbtn._bound){wbtn._bound=true; wbtn.onclick=()=>withdrawUpEval(role);}
    }
  });
  const hasMine = evals.some(e=>e.evaluator_role===upEvalRole);
  const withdrawBtn=document.getElementById("upe-withdraw");
  withdrawBtn.style.display = (hasMine && node==="待转正评估") ? "" : "none";
  // 保存按钮：仅本人绑定角色可编辑时显示；纯查看（无角色/已完结）隐藏
  const mineEditable = !!upEvalRole && (node==="待转正评估" || (node==="已公示" && ME.is_super_admin));
  document.getElementById("upe-save").style.display = mineEditable ? "" : "none";
  const publishWrap=document.getElementById("upe-publish-wrap");
  const publishBtn=document.getElementById("upe-publish");
  const canPublish = upEvalRole==="评审相关负责人" && node==="已公示";
  publishWrap.style.display = canPublish ? "" : "none";
  publishBtn.style.display = canPublish ? "" : "none";
  document.getElementById("modal-up-eval").classList.add("show");
}
async function saveUpEval(){
  if(!requireAuth())return;
  if(!upEvalId||!upEvalRole){await UI.alert("未获取到您的评审角色");return;}
  const sec=document.querySelector('.eval-role[data-role="'+upEvalRole+'"]');
  if(!sec){return;}
  const agree=sec.querySelector(".upe-agree").value;
  const reason=sec.querySelector(".upe-reason").value.trim();
  if(!agree){await UI.alert("请选择是否同意授予");return;}
  if(!reason){await UI.alert("评估理由为必填");return;}
  const b={evaluator_role:upEvalRole, agree, reason};
  const base=upApiBase(upEvalKind);
  const res=await fetch(base+"/"+upEvalId+"/evals",{method:"POST",headers:j(),body:JSON.stringify(b)}).then(r=>r.json());
  if(res.error){await UI.alert("提交失败："+res.error);return;}
  document.getElementById("modal-up-eval").classList.remove("show");loadUpgrade(upEvalKind);
}
async function withdrawUpEval(role){
  if(!requireAuth())return;
  if(!await UI.confirm("确认撤回该角色评估？撤回后需重新提交。"))return;
  const base=upApiBase(upEvalKind);
  const res=await fetch(base+"/"+upEvalId+"/evals",{method:"DELETE",headers:j()}).then(r=>r.json());
  if(res.error){await UI.alert("撤回失败："+res.error);return;}
  openUpEval(upEvalId, upEvalKind);
}
async function publishUpEval(){
  if(!requireAuth())return;
  if(upEvalRole!=="评审相关负责人"){await UI.alert("无权限：仅「评审相关负责人」可确认发布");return;}
  const result=document.getElementById("upe-publish-result").value;
  if(!result){await UI.alert("请选择最终评估结果");return;}
  if(!await UI.confirm("确认发布？发布后将进入「评估完成」并公示评估结果。"))return;
  const base=upApiBase(upEvalKind);
  const res=await fetch(base+"/"+upEvalId,{method:"PUT",headers:j(),body:JSON.stringify({action:"publish",eval_result:result})}).then(r=>r.json());
  if(res.error){await UI.alert("发布失败："+res.error);return;}
  document.getElementById("modal-up-eval").classList.remove("show");loadUpgrade(upEvalKind);
}
// 编辑/评审/官方任务 三页
const SCOPE_META={
  edit:{metric:"特色编辑达标数",col:"feature_edits",count:"feature_edits",body:"edit-body",kpis:"edit-kpis",countLabel:"特色达标数",minOk:1},
  review:{metric:"版本判定准确率",col:"v_judgment",count:"main_cat_versions",body:"review-body",kpis:"review-kpis",countLabel:"主分类评审版本数",extra:"review-progress"},
  official:{metric:"官方任务专项错误率",col:"v_official_err",count:"official_versions",body:"official-body",kpis:"official-kpis",countLabel:"官方任务版本数"}};
async function loadScope(scope){const m=SCOPE_META[scope];if(!m)return;const period=scopePeriod(scope);
  const cols=scope==="review"?9:(scope==="edit"?5:6);
  if(!period){document.getElementById(m.body).innerHTML=`<tr><td colspan="${cols}" class="empty">请先导入该周期考核数据</td></tr>`;document.getElementById(m.kpis).innerHTML="";return;}
  const [d,prog]=await Promise.all([
    API("/api/assess/records?period="+encodeURIComponent(period)),
    scope==="review"?API("/api/assess/review-progress?period="+encodeURIComponent(period)):Promise.resolve({rows:[]})]);
  const progMap={};prog.rows.forEach(x=>progMap[x.account_id]=x);
  let passN=0;const rows=d.rows.map(r=>{
    let ok=false;
    if(scope==="edit"){ok=(r.feature_edits||0)>=1;}
    else{const mt=r.metrics.find(x=>x.name===m.metric);ok=mt?mt.passed:false;}
    if(ok)passN++;return {r,ok};});
  const total=rows.length||1;
  const rate=Math.round(passN/total*100)+"%";
  const kpiItems=[{l:"参评人数",v:d.rows.length},{l:"本项达标",v:passN,cls:"ok"},{l:"本项达标率",v:rate,cls:"info"}];
  document.getElementById(m.kpis).innerHTML=kpiItems.map(k=>`<div class="kpi"><div class="v ${k.cls||""}">${k.v}</div><div class="l">${k.l}</div></div>`).join("");
  document.getElementById(m.kpis).style.gridTemplateColumns="repeat(3,1fr)";
  if(scope==="review"){
    document.getElementById(m.body).innerHTML=d.rows.length?rows.map(({r,ok})=>{
      const p=progMap[r.account_id]||{};
      const subNeedRaw=(p.sub_needs||[]).map(s=>`${s[0]}:${s[1]}`).join(" / ")||"—";
      const subNeed=subNeedRaw.replace(/"/g,'&quot;');
      return `<tr>
    <td>${r.account_id}${r.display_name&&r.display_name!==r.account_id?`<br><span class="muted">${r.display_name}</span>`:""}</td><td>${r.period}</td>
    <td><b>${r.v_judgment!=null?r.v_judgment:"-"}</b>%</td><td>${p.main_cat||"—"} / ${p.sub_count||0}副</td>
    <td>${p.main_actual||0}/${p.main_need||30}</td><td class="sub-needs" title="${subNeed}">${subNeedRaw}</td>
    <td>${p.effective||0}<span class="muted">(${p.main_actual||0}+${p.substitution||0}代)</span></td>
    <td><span class="pill ${p.passed?"g":"r"}">${p.passed?"达标":"未达标"}</span></td>
    <td>${ME?`<button class="linkbtn" data-re="${r.id}" data-auth="write">改</button>`:''}</td></tr>`;}).join(""):'<tr><td colspan="9" class="empty">无数据</td></tr>';
  }else if(scope==="edit"){
    document.getElementById(m.body).innerHTML=d.rows.length?rows.map(({r,ok})=>`<tr>
    <td>${r.account_id}${r.display_name&&r.display_name!==r.account_id?`<br><span class="muted">${r.display_name}</span>`:""}</td><td>${r.period}</td>
    <td>${r.feature_edits||0}</td>
    <td><span class="pill ${ok?"g":"r"}">${ok?"达标":"未达标"}</span></td>
    <td>${ME?`<button class="linkbtn" data-re="${r.id}" data-auth="write">改</button>`:''}</td></tr>`).join(""):'<tr><td colspan="5" class="empty">无数据</td></tr>';
  }else{
    document.getElementById(m.body).innerHTML=d.rows.length?rows.map(({r,ok})=>`<tr>
    <td>${r.account_id}${r.display_name&&r.display_name!==r.account_id?`<br><span class="muted">${r.display_name}</span>`:""}</td><td>${r.period}</td>
    <td><b>${r.v_official_err!=null?r.v_official_err:"-"}</b>%</td><td>${r.official_versions||0}</td>
    <td><span class="pill ${ok?"g":"r"}">${ok?"达标":"未达标"}</span></td>
    <td>${ME?`<button class="linkbtn" data-re="${r.id}" data-auth="write">改</button>`:''}</td></tr>`).join(""):'<tr><td colspan="6" class="empty">无数据</td></tr>';
  }
  document.querySelectorAll("#"+m.body+" [data-re]").forEach(b=>b.onclick=()=>openRec(b.dataset.re,scope));}
// 综合
async function loadSummary(){const period=scopePeriod("summary");if(!period)return;
  const d=await API("/api/assess/stats?period="+encodeURIComponent(period));
  document.getElementById("assess-kpis").innerHTML=[{l:"参评人数",v:d.total},{l:"通过",v:d.passed,cls:"ok"},{l:"不通过",v:d.fail,cls:"bad"},{l:"免考核",v:d.exempt,cls:"info"},{l:"通过率",v:d.pass_rate+"%",cls:"info"},{l:"平均综合分",v:d.avg_score}].map(k=>`<div class="kpi"><div class="v ${k.cls||""}">${k.v}</div><div class="l">${k.l}</div></div>`).join("");
  donutChart(document.getElementById("chart-pass2"),[{label:"通过",value:d.passed,color:"#15a34a"},{label:"不通过",value:d.fail,color:"#e0413e"},{label:"免考核",value:d.exempt,color:"#94a3b8"}]);
  barChart(document.getElementById("chart-metric"),d.metric_avg.map((m,i)=>({label:m.name,value:m.pass_rate,suffix:"%",color:PALETTE[i%PALETTE.length]})));
  hBar(document.getElementById("chart-rank"),d.ranking.map(r=>({label:r.account_id,value:r.composite,color:r.passed?"#15a34a":(r.exempt?"#94a3b8":"#e0413e")})));
  lineChart(document.getElementById("chart-trend2"),d.trend.map(t=>({label:t.period,value:t.pass_rate})),{color:"#0ea5e9"});
  document.getElementById("result-body").innerHTML=d.table.map((r,i)=>`<tr>
    <td>${i+1}</td><td>${r.account_id}${r.display_name&&r.display_name!==r.account_id?`<br><span class="muted">${r.display_name}</span>`:""}</td><td><b>${r.composite}</b></td><td>${r.v_judgment}</td><td>${r.v_task}</td><td>${r.v_official_err}</td><td>${r.v_feedback}</td><td>${r.veto?"是":"否"}</td><td>${r.exempt_tag?`<span class="pill n">${r.exempt_tag}</span>`:"—"}</td><td><span class="pill ${r.exempt?"n":(r.passed?"g":"r")}">${r.exempt?"免考核":(r.passed?"通过":"不通过")}</span></td></tr>`).join("");
  loadExempt(period);}
async function loadExempt(period){const d=await API("/api/assess/exemptions?period="+encodeURIComponent(period||""));
  document.getElementById("exempt-body").innerHTML=d.rows.length?d.rows.map(r=>`<tr>
    <td>${r.account_id}${r.display_name&&r.display_name!==r.account_id?`<br><span class="muted">${r.display_name}</span>`:""}</td><td>${r.period}</td><td>${r.kind}</td><td>${r.mode}</td><td>${r.days||0}</td><td>${r.reduce_ratio||0}%</td><td>${r.category||"—"}</td><td>${r.reason||""}</td>
    <td>${ME?`<button class="linkbtn del" data-ed="${r.id}" data-auth="write">删</button>`:'<span class="muted">—</span>'}</td></tr>`).join(""):'<tr><td colspan="9" class="empty">暂无免减报备（请假 / 特殊分类报备）</td></tr>';
  document.querySelectorAll("#exempt-body [data-ed]").forEach(b=>b.onclick=async()=>{if(!requireAuth())return;if(await UI.confirm("确认删除该免减报备？")){await fetch("/api/assess/exemptions/"+b.dataset.ed,{method:"DELETE"});loadExempt(scopePeriod("summary"));loadSummary();}});}
function openExemptModal(){const p=scopePeriod("summary")||"";["ex-account","ex-category","ex-reason"].forEach(x=>document.getElementById(x).value="");document.getElementById("ex-period").value=p;document.getElementById("ex-days").value=0;document.getElementById("ex-ratio").value=0;document.getElementById("modal-exempt").classList.add("show");}
async function saveExempt(){if(!requireAuth())return;const b={account_id:val("ex-account"),period:val("ex-period"),kind:val("ex-kind"),mode:val("ex-mode"),days:+val("ex-days"),reduce_ratio:+val("ex-ratio"),category:val("ex-category"),reason:val("ex-reason")};
  if(!b.account_id||!b.period){await UI.alert("账号与周期为必填");return;}
  const res=await API("/api/assess/exemptions",{method:"POST",headers:j(),body:JSON.stringify(b)});
  if(res.error){await UI.alert("保存失败："+res.error);return;}document.getElementById("modal-exempt").classList.remove("show");loadExempt(b.period);loadSummary();}

// ---------- 数据质量检查（冲突与冗余） ----------
let auditData = {conflicts: [], redundancy: []};
const SEV_CLS = {高: "bad", 中: "warn", 低: "n"};
function renderAudit(){
  const f = (document.querySelector("#audit-filter .segbtn.active") || {}).dataset?.f || "all";
  const q = (document.getElementById("audit-search").value || "").trim().toLowerCase();
  const m = r => !q || (r.account || "").toLowerCase().includes(q);
  const draw = (rows, bodyId) => {
    const list = rows.filter(m);
    document.getElementById(bodyId).innerHTML = list.length ? list.map(r => `
      <tr>
        <td><span class="pill ${SEV_CLS[r.severity] || "n"}">${r.severity || "—"}</span></td>
        <td>${r.kind}</td><td>${r.account}</td><td>${r.category}</td>
        <td class="wrap">${r.detail}</td><td class="wrap">${r.suggestion || "—"}</td>
      </tr>`).join("") : `<tr><td colspan="6" class="empty">无记录</td></tr>`;
  };
  const showC = (f === "all" || f === "conflict"), showR = (f === "all" || f === "redundancy");
  document.getElementById("card-conflict").style.display = showC ? "" : "none";
  document.getElementById("card-redun").style.display = showR ? "" : "none";
  draw(auditData.conflicts, "conflict-body");
  draw(auditData.redundancy, "redun-body");
}
async function loadAudit(){
  auditData.conflicts = (await API("/api/conflicts")).rows || [];
  auditData.redundancy = (await API("/api/redundancy")).rows || [];
  document.getElementById("conflict-n").textContent = auditData.conflicts.length;
  document.getElementById("redun-n").textContent = auditData.redundancy.length;
  document.getElementById("audit-total").textContent = auditData.conflicts.length + auditData.redundancy.length;
  document.getElementById("audit-conflict").textContent = auditData.conflicts.length;
  document.getElementById("audit-redun").textContent = auditData.redundancy.length;
  renderAudit();
}

// ---------- 纪律与转正管理 ----------
function showDiscSub(sub){document.querySelectorAll("#page-discipline .subtab").forEach(b=>b.classList.toggle("active",b.dataset.disc===sub));
  ["violation","appeal","promote","liability","stats","spot","reinstate","under","dormant","internship","retrain","identity"].forEach(s=>{const el=document.getElementById("disc-"+s);if(el)el.style.display=s===sub?"block":"none";});
  if(sub==="violation")loadViolations();else if(sub==="appeal")loadAppeals();else if(sub==="promote")loadPromote();else if(sub==="liability")loadLiabilities();else if(sub==="stats")loadViolationStats();else if(sub==="spot")loadSpotChecks();else if(sub==="reinstate")loadReinstate();else if(sub==="under")loadUnderperform();else if(sub==="dormant")loadDormant();else if(sub==="internship")loadInternship();else if(sub==="retrain")loadRetrain();else if(sub==="identity")loadIdentity();}
async function loadLiabilities(){const d=await API("/api/referrer-liabilities");const st=val("liab-status");
  const rows=st?d.rows.filter(r=>(r.status||"待处理")===st):d.rows;
  document.getElementById("liab-body").innerHTML=rows.length?rows.map(r=>`<tr>
    <td>${r.violation_id||""}</td><td>${r.violator_account||""}</td><td>${r.referrer_account||""}</td>
    <td>${r.category||'<span class="muted">—</span>'}</td><td>${r.level||""}</td><td>${r.penalty||'<span class="muted">—</span>'}</td>
    <td><span class="pill ${r.status==="已处理"?"g":(r.status==="已免除"?"y":"r")}">${r.status||"待处理"}</span></td>
    <td>${r.handled_by||""}</td><td>${r.handled_time||""}</td><td>${(r.note||"")}</td>
    <td>${r.status!=="已免除" && ME ?`<button class="linkbtn" data-liab="${r.id}" data-auth="write">标记处理</button>`:'<span class="muted">—</span>'}</td></tr>`).join(""):'<tr><td colspan="11" class="empty">暂无推荐人连带责任记录</td></tr>';
  document.querySelectorAll("#liab-body [data-liab]").forEach(b=>b.onclick=async()=>{if(!requireAuth())return;const ok=await UI.confirm("将该连带责任标记为「已处理」？");if(!ok)return;const res=await fetch("/api/referrer-liabilities/"+b.dataset.liab,{method:"PUT",headers:j(),body:JSON.stringify({status:"已处理",handled_by:(ME&&ME.account_id)||"管理",handled_time:new Date().toISOString().slice(0,10)})}).then(x=>x.json());if(res.error){await UI.alert("操作失败："+res.error);return;}loadLiabilities();});}
function loadViolationStats(dim){
  dim=dim||(document.querySelector('#disc-stats [data-vstat].active')||{}).dataset&&document.querySelector('#disc-stats [data-vstat].active').dataset.vstat||'account';
  API('/api/violation-stats').then(d=>{
    const s=d.summary||{}; const lvl=['轻微问题','一般违规','严重违规','重大违规'];
    document.getElementById('vstat-summary').innerHTML='总违规 <b>'+(s.total||0)+'</b> · 生效中 <b class="r">'+(s.active||0)+'</b> · 已撤销 <b>'+(s.revoked||0)+'</b>　|　'+lvl.map(x=>x+'：'+(s.by_level&&s.by_level[x]||0)).join('　');
    let head,rows;
    if(dim==='account'){head=['账号','违规次数','生效中','最近违规'];rows=(d.by_account||[]).map(r=>[r.account_id,r.cnt,r.active_cnt,r.last_time||'-']);}
    else if(dim==='category'){head=['分类','违规次数'];rows=(d.by_category||[]).map(r=>[r.category,r.cnt]);}
    else {head=['月份','违规次数'];rows=(d.by_month||[]).map(r=>[r.ym,r.cnt]);}
    document.getElementById('vstat-head').innerHTML=head.map(h=>'<th>'+h+'</th>').join('');
    document.getElementById('vstat-body').innerHTML=rows.length?rows.map(r=>'<tr>'+r.map(c=>'<td>'+c+'</td>').join('')+'</tr>').join(''):'<tr><td colspan="'+(head.length)+'" class="empty">暂无违规记录</td></tr>';
  }).catch(e=>{document.getElementById('vstat-body').innerHTML='<tr><td colspan="4" class="empty">加载失败：'+e+'</td></tr>';});}
/* ---------- 抽查记录（制度 7.1） ---------- */
async function loadSpotChecks(){
  const p=val("spot-period"),a=val("spot-account");
  const qs=[]; if(p)qs.push("period="+encodeURIComponent(p)); if(a)qs.push("account_id="+encodeURIComponent(a));
  const d=await API("/api/spot-checks"+(qs.length?"?"+qs.join("&"):""));
  const s=d.summary||{};
  document.getElementById("spot-summary").innerHTML=
    '记录 <b>'+(s.count||0)+'</b> 条 · 应抽 <b>'+(s.sample_need||0)+'</b> · 实抽 <b>'+(s.sampled||0)+'</b> · 完成率 <b>'+(s.finish_rate||0)+'%</b> · 问题版本 <b class="r">'+(s.problem||0)+'</b> · 问题率 <b class="r">'+(s.problem_rate||0)+'%</b>';
  const rows=d.rows||[];
  document.getElementById("spot-body").innerHTML=rows.length?rows.map(r=>`<tr>
    <td>${r.period||""}</td><td>${r.account_id||""}</td><td>${r.category||'<span class="muted">—</span>'}</td>
    <td>${r.total_versions||0}</td><td><b>${r.sample_need||0}</b></td><td>${r.main_need||0}</td><td>${r.sub_need||0}</td>
    <td>${r.sampled||0}</td><td>${r.problem_versions||0}</td>
    <td>${r.level?`<span class="pill ${r.level==="重大违规"||r.level==="严重违规"?"r":"y"}">${r.level}</span>`:'<span class="muted">—</span>'}</td>
    <td>${r.handling||'<span class="muted">—</span>'}</td>
    <td>${r.is_official?'<span class="pill r">官方任务</span>':'<span class="muted">—</span>'}</td>
    <td>${r.checker||""}</td>
    <td>${r.status==="已处理" || !ME?'<span class="muted">—</span>':`<button class="linkbtn" data-spot-done="${r.id}" data-auth="write">标记完成</button>`}</td></tr>`).join("")
    :'<tr><td colspan="14" class="empty">暂无抽查记录</td></tr>';
  document.querySelectorAll("#spot-body [data-spot-done]").forEach(b=>b.onclick=async()=>{
    const lvl=await UI.prompt("抽查结果违规等级（留空表示无问题）：\n轻微问题 / 一般违规 / 严重违规 / 重大违规","");
    if(lvl===null)return;
    const res=await fetch("/api/spot-checks/"+b.dataset.spotDone,{method:"PUT",headers:j(),
      body:JSON.stringify({level:lvl.trim(),handling:lvl.trim()?"按 7.2 分级处理":"抽查无问题"})}).then(x=>x.json());
    if(res.error){await UI.alert("操作失败："+res.error);return;} loadSpotChecks();});
}
/* ---------- 再训与复权（制度 6.4） ---------- */
async function loadReinstate(){
  const st=val("rein-status");
  const d=await API("/api/reinstate"+(st?"?status="+encodeURIComponent(st):""));
  const rows=st?(d.rows||[]):(d.rows||[]);
  document.getElementById("rein-body").innerHTML=rows.length?rows.map(r=>{
    const g=k=>r[k]?'<span class="pill g">达标</span>':'<span class="pill r">未达标</span>';
    const done=r.status==="已复权";
    return `<tr>
    <td>${r.account_id||""}</td><td>${r.category||'<span class="muted">全部</span>'}</td>
    <td>${r.target_level||""}</td>
    <td><span class="pill ${r.status==="已复权"?"g":(r.status==="已失败"?"r":"y")}">${r.status||"待审核"}</span></td>
    <td>${r.official_versions||0}</td><td>${r.main_cat_versions||0}</td><td>${r.accuracy||0}%</td>
    <td>${done?'<span class="muted">已完成</span>':`版本${g("ver_ok")} 正确率${g("acc_ok")}${(r.rule&&r.rule.main_min)?' 主分类'+g("main_ok"):""}`}</td>
    <td>${r.extend_count||0}</td><td>${r.block_until?`<span class="pill r">${r.block_until}</span>`:'<span class="muted">—</span>'}</td>
    <td>${r.apply_time||""}${r.result_time?"<br><span class='muted'>结果 "+r.result_time.slice(0,10)+"</span>":""}</td>
    <td>${done || !ME?'<span class="muted">—</span>':`<button class="linkbtn" data-rein-ok="${r.id}" data-auth="write">判定复权</button> <button class="linkbtn" data-rein-no="${r.id}" data-auth="write">判定失败</button>`}</td></tr>`;}).join("")
    :'<tr><td colspan="12" class="empty">暂无复权申请</td></tr>';
  document.querySelectorAll("#rein-body [data-rein-ok]").forEach(b=>b.onclick=async()=>{
    const res=await fetch("/api/reinstate/"+b.dataset.reinOk,{method:"PUT",headers:j(),body:JSON.stringify({status:"已复权"})}).then(x=>x.json());
    if(res.error){await UI.alert("不可判定为已复权：\n"+res.error);return;} loadReinstate();});
  document.querySelectorAll("#rein-body [data-rein-no]").forEach(b=>b.onclick=async()=>{
    if(!await UI.confirm("判定该复权申请失败？首次将延长 1 个月，再次失败则半年内不受理。"))return;
    const res=await fetch("/api/reinstate/"+b.dataset.reinNo,{method:"PUT",headers:j(),body:JSON.stringify({status:"已失败"})}).then(x=>x.json());
    if(res.error){await UI.alert("操作失败："+res.error);return;} loadReinstate();});
}
/* ---------- 连续未达标预警（制度 6.1） ---------- */
async function loadUnderperform(){
  const m=val("under-months")||6;
  const d=await API("/api/underperform?months="+m);
  const rows=d.rows||[];
  document.getElementById("under-body").innerHTML=rows.length?rows.map(r=>`<tr>
    <td>${r.account_id}</td>
    <td><b class="${r.streak>=2?"r":""}">${r.streak}</b> 期</td>
    <td><span class="pill ${r.streak>=2?"r":"y"}">${r.action}</span>${r.actionable?' <span class="pill r">可处置</span>':""}</td>
    <td>${(r.seq||[]).map(s=>s.period+' <span class="pill '+(s.status==="达标"?"g":(s.status==="免考核"||s.status==="无记录"?"n":"r"))+'">'+s.status+'</span>').join(" · ")}</td>
    <td>${r.actionable && ME?`<button class="linkbtn danger" data-ue="${r.account_id}" data-streak="${r.streak}" data-act="${r.suggested_action||'降级'}" data-auth="write">执行降级</button>`:'<span class="muted">—</span>'}</td></tr>`).join("")
    :'<tr><td colspan="5" class="empty">暂无连续未达标账号</td></tr>';
  document.querySelectorAll("#under-body [data-ue]").forEach(b=>b.onclick=()=>openUnderExec(b.dataset.ue,b.dataset.streak,b.dataset.act));
}
async function loadDormant(){const d=await API("/api/dormant");const rows=d.rows||[];
  document.getElementById("dormant-body").innerHTML=rows.length?rows.map(r=>`<tr>
    <td>${r.id}</td><td>${r.account_id}</td><td>${r.category}</td><td>${r.level}</td>
    <td><span class="pill n">${r.status}</span></td>
    <td><span class="muted">${r.reason||""}</span></td>
    <td>${ME?`<button class="linkbtn" data-dom="${r.id}" data-auth="write">标记休眠</button>`:'<span class="muted">—</span>'}</td></tr>`).join("")
    :'<tr><td colspan="7" class="empty">暂无休眠候选（所有有效权限近 2 月均有评审量或已请假）</td></tr>';
  document.querySelectorAll("#dormant-body [data-dom]").forEach(b=>b.onclick=async()=>{if(!requireAuth())return;if(!await UI.confirm("确认将该权限标记为「休眠」（制度 3.8）？恢复须走 6.4 再训流程。"))return;
    const res=await fetch("/api/dormant/"+b.dataset.dom,{method:"PUT",headers:j(),body:JSON.stringify({operator:(ME&&ME.account_id)||"管理"})}).then(x=>x.json());
    if(res.error){await UI.alert("操作失败："+res.error);return;}loadDormant();});}
async function loadInternship(){const d=await API("/api/internship");const rows=d.rows||[];
  document.getElementById("intern-body").innerHTML=rows.length?rows.map(r=>`<tr>
    <td>${r.id}</td><td>${r.account_id}</td><td>${r.category}</td><td>${r.level}</td>
    <td>${r.internship_start||"—"}</td><td>${r.expire_date||"—"}</td>
    <td>${r.expired?'<span class="pill r">已期满</span>':'<span class="pill n">实习中</span>'}</td>
    <td>${r.suggest_promote?'<span class="pill g">建议转正</span>':'<span class="muted">—</span>'}</td>
    <td>${ME?`<button class="linkbtn" data-int="${r.id}" data-st="${r.suggest_promote?'正常':'取消权限'}" data-auth="write">${r.suggest_promote?'转正':'取消'}</button>`:'<span class="muted">—</span>'}</td></tr>`).join("")
    :'<tr><td colspan="9" class="empty">暂无实习状态权限</td></tr>';
  document.querySelectorAll("#intern-body [data-int]").forEach(b=>b.onclick=async()=>{if(!requireAuth())return;const st=b.dataset.st;if(!await UI.confirm("确认将该实习权限变更为「"+st+"」？"))return;
    const res=await fetch("/api/internship/"+b.dataset.int,{method:"PUT",headers:j(),body:JSON.stringify({status:st,operator:(ME&&ME.account_id)||"管理"})}).then(x=>x.json());
    if(res.error){await UI.alert("操作失败："+res.error);return;}loadInternship();});}

/* ---------- 指南复训（制度 6.6） ---------- */
let rtEditId=null;
async function loadRetrain(){
  const st=val("retrain-status");
  const qs=st?("?status="+encodeURIComponent(st)):"";
  const d=await API("/api/retrains"+qs);
  const rows=d.rows||[];
  document.getElementById("retrain-body").innerHTML=rows.length?rows.map(r=>`<tr>
    <td>${r.id}</td><td>${r.guide_version||""}</td><td>${r.title||'<span class="muted">—</span>'}</td>
    <td>${(r.participants||"").replace(/;/g,", ")}</td>
    <td>${r.start_date||'<span class="muted">—</span>'}</td><td>${r.end_date||'<span class="muted">—</span>'}</td>
    <td><span class="pill ${(r.status==="已完成")?"g":(r.status==="未通过"?"r":"y")}">${r.status}</span></td>
    <td>${r.pass_count||0}/${r.total_count||0}</td>
    <td>${ME?`<button class="linkbtn" data-rt="${r.id}" data-auth="write">编辑</button> <button class="linkbtn danger" data-rt-del="${r.id}" data-auth="write">删除</button>`:'<span class="muted">—</span>'}</td></tr>`).join("")
    :'<tr><td colspan="9" class="empty">暂无复训记录</td></tr>';
  document.querySelectorAll("#retrain-body [data-rt]").forEach(b=>b.onclick=()=>openRetrain(b.dataset.rt));
  document.querySelectorAll("#retrain-body [data-rt-del]").forEach(b=>b.onclick=async()=>{if(!requireAuth())return;if(!await UI.confirm("确认删除该复训记录？"))return;
    const res=await fetch("/api/retrains/"+b.dataset.rtDel,{method:"DELETE",headers:j()}).then(x=>x.json());
    if(res.error){await UI.alert("操作失败："+res.error);return;}loadRetrain();});
}
function openRetrain(id){
  rtEditId=id||null;
  document.getElementById("retrain-title").textContent=id?"编辑复训记录":"登记指南复训";
  if(id){
    API("/api/retrains").then(d=>{
      const r=(d.rows||[]).find(x=>String(x.id)===String(id));
      if(r){document.getElementById("rt-guide").value=r.guide_version||"";document.getElementById("rt-title").value=r.title||"";
        document.getElementById("rt-start").value=r.start_date||"";document.getElementById("rt-end").value=r.end_date||"";
        document.getElementById("rt-status").value=r.status||"待开展";document.getElementById("rt-pass").value=r.pass_count||0;
        document.getElementById("rt-total").value=r.total_count||0;document.getElementById("rt-participants").value=r.participants||"";
        document.getElementById("rt-note").value=r.note||"";refreshCustomSelect("rt-status");}
      document.getElementById("modal-retrain").classList.add("show");
    });
  }else{
    ["rt-guide","rt-title","rt-start","rt-end","rt-participants","rt-note"].forEach(id=>document.getElementById(id).value="");
    document.getElementById("rt-status").value="待开展";document.getElementById("rt-pass").value=0;document.getElementById("rt-total").value=0;
    document.getElementById("modal-retrain").classList.add("show");
  }
}
async function saveRetrain(){if(!requireAuth())return;
  const body={guide_version:val("rt-guide"),title:val("rt-title"),start_date:val("rt-start"),end_date:val("rt-end"),
    status:val("rt-status"),pass_count:(+val("rt-pass")||0),total_count:(+val("rt-total")||0),
    participants:val("rt-participants"),note:val("rt-note"),operator:(ME&&ME.account_id)||"管理"};
  const res=rtEditId?await fetch("/api/retrains/"+rtEditId,{method:"PUT",headers:j(),body:JSON.stringify(body)}).then(x=>x.json())
                    :await fetch("/api/retrains",{method:"POST",headers:j(),body:JSON.stringify(body)}).then(x=>x.json());
  if(res.error){await UI.alert("保存失败："+res.error);return;}
  document.getElementById("modal-retrain").classList.remove("show");loadRetrain();
}

/* ---------- 身份与再训（制度 4.4 / 5.6） ---------- */
async function loadIdentity(){
  const tp=await API("/api/tadpole");
  const rows=tp.rows||[];
  document.getElementById("tadpole-body").innerHTML=rows.length?rows.map(r=>`<tr>
    <td>${r.account_id}</td><td><span class="pill y">${r.tadpole_status}</span></td>
    <td>${r.tadpole_until||'<span class="muted">—</span>'}</td>
    <td>${(r.permissions||[]).map(p=>p.category+' <span class="pill n">'+p.status+'</span>').join("，")}</td></tr>`).join("")
    :'<tr><td colspan="4" class="empty">当前无蝌蚪身份成员（无实习/见习权限）</td></tr>';
  const nr=await API("/api/need-retrain");
  const nrows=nr.rows||[];
  document.getElementById("needretrain-body").innerHTML=nrows.length?nrows.map(r=>`<tr><td>${r.account_id}</td><td>${r.reason||'<span class="muted">—</span>'}</td></tr>`).join("")
    :'<tr><td colspan="2" class="empty">暂无再训要求（所有处置账号均已完成复训）</td></tr>';
}

/* ---------- 连续未达标确认式降级（制度 6.1） ---------- */
function openUnderExec(account,streak,act){
  document.getElementById("ue-account").value=account;
  document.getElementById("ue-streak").value=streak+" 期";
  document.getElementById("ue-action").value=act||"降级";
  document.getElementById("modal-underexec").classList.add("show");
}
async function execUnder(){
  const account=val("ue-account"),action=val("ue-action"),note=val("ue-note");
  if(!await UI.confirm("确认对账号「"+account+"」执行「"+action+"」？此操作将变更其权限状态并写入变更日志。"))return;
  const res=await fetch("/api/underperform/execute",{method:"POST",headers:j(),body:JSON.stringify({account_id:account,action:action,note:note,operator:(ME&&ME.account_id)||"管理"})}).then(x=>x.json());
  if(res.error){await UI.alert("执行失败："+res.error);return;}
  document.getElementById("modal-underexec").classList.remove("show");loadUnderperform();
}
function penaltyTermText(r){
  if(!r.penalty)return '<span class="muted">—</span>';
  const t=+r.penalty_term||0;
  if((r.penalty==="停审"||r.penalty==="降级")&&t>0){
    let s=t+"天";
    if(r.penalty_due)s+=" / 到期 "+r.penalty_due;
    if(r.restored_at)s+=' <span class="pill g">已期满恢复</span>';
    return s;
  }
  return '<span class="muted">终态/无期限</span>';
}
async function loadViolations(){const d=await API("/api/violations");
  document.getElementById("vio-body").innerHTML=d.rows.length?d.rows.map(r=>`<tr>
    <td>${r.account_id}${r.display_name&&r.display_name!==r.account_id?`<br><span class="muted">${r.display_name}</span>`:""}</td>
    <td>${r.category||'<span class="muted">—</span>'}</td>
    <td><span class="pill ${r.level==="重大违规"||r.level==="严重违规"?"r":"y"}">${r.level}</span></td>
    <td><span class="pill ${r.status==="已撤销"?"g":"r"}">${r.status||"生效"}</span>${r.perm_id?" <span class=\"pill y\">已挂起权限</span>":""}</td>
    <td>${r.reason||""}</td><td>${r.penalty||'<span class="muted">—</span>'}</td><td>${penaltyTermText(r)}</td><td>${r.penalty_time||""}</td><td>${r.referrer||""}</td><td>${r.operator||""}</td>
    <td>${ME&&ME.is_admin?`<button class="linkbtn" data-vio="${r.id}" data-auth="write">改</button><button class="linkbtn del" data-viod="${r.id}" data-auth="write">删</button>`:'<span class="muted">—</span>'}</td></tr>`).join(""):'<tr><td colspan="11" class="empty">暂无违规记录</td></tr>';
  document.querySelectorAll("#vio-body [data-vio]").forEach(b=>b.onclick=()=>openVio(b.dataset.vio));
  document.querySelectorAll("#vio-body [data-viod]").forEach(b=>b.onclick=async()=>{if(!requireAuth())return;if(await UI.confirm("确认删除该违规记录？")){await fetch("/api/violations/"+b.dataset.viod,{method:"DELETE"});loadViolations();}});}
function toggleVioTerm(){const p=val("vio-penalty");const show=(p==="停审"||p==="降级");const w=document.getElementById("vio-term-wrap");if(w)w.style.display=show?"":"none";}
function openVio(id){vioId=id||null;["vio-account","vio-category","vio-penalty-time","vio-penalty","vio-penalty-term","vio-referrer","vio-operator","vio-reason","vio-note"].forEach(x=>document.getElementById(x).value="");
  document.getElementById("vio-level").value="一般违规";document.getElementById("vio-status").value="生效";document.getElementById("vio-penalty-term").value="0";
  if(id){fetch("/api/violations").then(r=>r.json()).then(d=>{const r=d.rows.find(x=>String(x.id)===String(id));if(r){document.getElementById("vio-account").value=r.account_id;document.getElementById("vio-category").value=r.category||"";document.getElementById("vio-level").value=r.level;document.getElementById("vio-status").value=r.status||"生效";document.getElementById("vio-penalty-time").value=r.penalty_time||"";document.getElementById("vio-penalty").value=r.penalty||"";document.getElementById("vio-penalty-term").value=r.penalty_term||0;document.getElementById("vio-referrer").value=r.referrer||"";document.getElementById("vio-operator").value=r.operator||"";document.getElementById("vio-reason").value=r.reason||"";document.getElementById("vio-note").value=r.note||"";refreshCustomSelect("vio-level");refreshCustomSelect("vio-status");}});}
  toggleVioTerm();document.getElementById("modal-vio").classList.add("show");}
async function saveVio(){if(!requireAuth())return;const b={account_id:val("vio-account"),category:val("vio-category"),level:val("vio-level"),status:val("vio-status"),reason:val("vio-reason"),penalty:val("vio-penalty"),penalty_term:+(val("vio-penalty-term")||0),penalty_time:val("vio-penalty-time"),referrer:val("vio-referrer"),operator:val("vio-operator"),note:val("vio-note")};
  if(!b.account_id){await UI.alert("被处罚账号为必填");return;}
  if((b.level==="严重违规"||b.level==="重大违规")&&!b.category){await UI.alert("严重/重大违规必须填写“违规分类”，系统将据此挂起该分类权限");return;}
  const res=vioId?await fetch("/api/violations/"+vioId,{method:"PUT",headers:j(),body:JSON.stringify(b)}).then(r=>r.json()):await API("/api/violations",{method:"POST",headers:j(),body:JSON.stringify(b)});
  if(res.error){await UI.alert("保存失败："+res.error);return;}document.getElementById("modal-vio").classList.remove("show");loadViolations();}

// ---------- 评审状态处置状态展示 ----------
function renderStripStatusCell(strip){
  if(!strip) return '<td><span class="muted">—</span></td>';
  const node=(who)=>who?`<span class="pill g">${who}</span>`:'<span class="pill n">待审</span>';
  const st=strip.status==='已通过'?'<span class="pill g">已通过</span>':(strip.status==='已驳回'?'<span class="pill r">已驳回</span>':'<span class="pill y">待审核</span>');
  return `<td>${st}<div class="muted sm">分类组长:${node(strip.cat_lead_approver)} 质量组长:${node(strip.quality_lead_approver)} 评审负责人:${node(strip.review_lead_approver)}</div></td>`;
}
function renderStripActions(row, sub, strip){
  if(!ME) return "";
  let html="";
  if(strip && strip.status==="待审核"){
    if(strip.can_cat_lead && !strip.cat_lead_approver) html+=`<button class="linkbtn" data-strip-approve="${strip.id}" data-kind="cat_lead" data-sub="${sub}">分类组长审批</button>`;
    if(strip.can_quality_lead && !strip.quality_lead_approver) html+=`<button class="linkbtn" data-strip-approve="${strip.id}" data-kind="quality_lead" data-sub="${sub}">质量组长审批</button>`;
    if(strip.can_review_lead && !strip.review_lead_approver) html+=`<button class="linkbtn" data-strip-approve="${strip.id}" data-kind="review_lead" data-sub="${sub}">评审负责人审批</button>`;
    if(strip.can_delete) html+=`<button class="linkbtn del" data-strip-del="${strip.id}" data-sub="${sub}">删</button>`;
  }
  return html;
}
function bindStripActions(bodyId, sub){
  const body = document.getElementById(bodyId);
  if(!body) return;
  body.querySelectorAll("[data-strip-approve]").forEach(b=>b.onclick=async()=>{
    if(!requireAuth())return;
    const kind=b.dataset.kind;
    const label={cat_lead:"分类组长（按分类）",quality_lead:"质量组长（按部门）",review_lead:"评审负责人（Adzwlqxm）"}[kind]||kind;
    if(!await UI.confirm("确认以「"+label+"」身份审批通过该节点？"))return;
    const res=await fetch("/api/status-strip-applies/"+b.dataset.stripApprove+"/approve",{method:"PUT",headers:j(),body:JSON.stringify({kind:kind})}).then(x=>x.json());
    if(res.error){await UI.alert("审批失败："+res.error);return;}
    await UI.alert(res.ok?(res.status==="已通过"?"三节点已通过，已回收该分类审核权限":"审批成功"):"审批成功");
    loadUpgrade(sub);
  });
  body.querySelectorAll("[data-strip-del]").forEach(b=>b.onclick=async()=>{
    if(!requireAuth())return;
    if(!await UI.confirm("确认删除该申请？"))return;
    const res=await fetch("/api/status-strip-applies/"+b.dataset.stripDel,{method:"DELETE"}).then(x=>x.json());
    if(res.error){await UI.alert("删除失败："+res.error);return;}
    loadUpgrade(b.dataset.sub);
  });
}

// ---------- 管理员管理（仅超级管理员可操作；含评审角色绑定，原独立页签已并入） ----------
let AM_META={scoped:{},domains:[],groups:[]}, AM_ROWS=[];
function amScopeOptions(role){
  if(role==="特色小组长"){
    return AM_META.groups.map(g=>'<option value="'+escMsg(g.group_name)+'">'+escMsg(g.group_name)+"（"+escMsg(g.domain)+"）</option>").join("");
  }
  return AM_META.domains.map(d=>'<option value="'+escMsg(d)+'">'+escMsg(d)+"</option>").join("");
}
function updateAmScope(){
  const role=val("am-role");const lab=document.getElementById("am-scope-label");
  if(!lab)return;
  if(AM_META.scoped[role]){lab.style.display="";document.getElementById("am-scope").innerHTML=amScopeOptions(role);refreshCustomSelect("am-scope");}
  else lab.style.display="none";
}
let amPending=null; // {target, role}
function openAmScope(target,role){
  amPending={target,role};
  const kind=AM_META.scoped[role]||"范围";
  document.getElementById("am-scope-title").textContent="设置「"+role+"」管辖"+kind;
  document.getElementById("am-scope-hint").textContent="「"+role+"」须绑定"+kind+"："+target;
  document.getElementById("am-scope-pick").innerHTML=amScopeOptions(role);
  refreshCustomSelect("am-scope-pick");
  document.getElementById("modal-am-scope").classList.add("show");
}
async function amGrant(target,role,scope){
  const res=await fetch("/api/admin/grant",{method:"POST",headers:j(),body:JSON.stringify({account_id:target,role:role,scope:scope||""})}).then(x=>x.json());
  if(res.error){await UI.alert("操作失败："+res.error);return;}
  showToast("已设置："+target+" / "+role+(scope?("·"+scope):""),"ok");
  loadAdminMgmt();
}
async function amRevoke(target,role){
  const res=await fetch("/api/admin/revoke",{method:"POST",headers:j(),body:JSON.stringify({account_id:target,role:role})}).then(x=>x.json());
  if(res.error){await UI.alert("操作失败："+res.error);return;}
  showToast("已取消："+target+" / "+role,"ok");
  loadAdminMgmt();
}
async function loadAdminMgmt(){
  const d=await API("/api/admin/accounts");
  if(d.error){await UI.alert("加载失败："+d.error);return;}
  AM_META={scoped:d.scoped_roles||{},domains:d.domains||[],groups:d.groups||[]};
  const roles=d.admin_roles||[]; // 已按期望顺序返回
  // 填充筛选下拉
  const frole=document.getElementById("am-filter-role");
  if(frole){frole.innerHTML='<option value="">全部角色</option><option value="_none_">无管理角色</option>'+roles.map(r=>'<option value="'+r+'">'+r+'</option>').join("");refreshCustomSelect("am-filter-role");}
  document.getElementById("am-acct-list").innerHTML=(d.rows||[]).map(r=>'<option value="'+r.account_id+'"></option>').join("");
  let rows=d.rows||[];
  // 筛选
  const kw=(val("am-filter-kw")||"").trim().toLowerCase();
  const fRole=val("am-filter-role");
  const fOff=val("am-filter-official");
  if(kw) rows=rows.filter(r=>r.account_id.toLowerCase().includes(kw)||(r.display_name||"").toLowerCase().includes(kw));
  if(fOff!=="") rows=rows.filter(r=>!!r.is_official==(fOff==="1"));
  if(fRole){
    rows=rows.filter(r=>{
      const held=(r.roles||[]).filter(x=>x.status==='在任'&&roles.includes(x.role)).map(x=>x.role);
      if(fRole==="_none_") return held.length===0;
      return held.includes(fRole);
    });
  }
  AM_ROWS=rows; // 缓存当前显示行，便于后续操作
  document.getElementById("am-body").innerHTML=rows.length?rows.map(r=>{
    const isAdm=!!r.is_admin, isSA=!!r.is_super_admin, isOff=!!r.is_official;
    const myRoles=(r.roles||[]).filter(x=>x.status==='在任'&&(roles.includes(x.role))).map(x=>x.role+(x.scope?'<span class="muted">·'+escMsg(x.scope)+'</span>':''));
    let acts="";
    if(ME&&ME.is_super_admin){
      roles.forEach(role=>{
        const held=(r.roles||[]).some(x=>x.role===role&&x.status==='在任');
        acts+=`<button class="linkbtn ${held?'del':''}" data-am-toggle="${r.account_id}" data-role="${role}" data-grant="${held?0:1}">${held?'取消':'设为'}${role}</button> `;
      });
    }
    if(!acts) acts='<span class="muted">—</span>';
    // 官方账号身份标签显示为「官方」
    const levelCell=isOff?'<span class="pill" style="background:#1d4ed8;color:#fff">官方</span>':`<span class="pill ${LEVEL_CLASS[r.level]||'n'}">${r.level||""}</span>`;
    return `<tr>
      <td>${r.account_id}${r.display_name&&r.display_name!==r.account_id?'<br><span class="muted">'+r.display_name+'</span>':''}</td>
      <td>${levelCell}</td>
      <td><span class="pill ${STATUS_CLASS[r.status]||'n'}">${r.status||""}</span></td>
      <td>${isAdm?'<span class="pill g">是</span>':'<span class="muted">否</span>'}</td>
      <td>${isSA?'<span class="pill" style="background:#7c2d12;color:#fff">是</span>':'<span class="muted">否</span>'}</td>
      <td>${isOff?'<span class="pill" style="background:#1d4ed8;color:#fff">是</span>':'<span class="muted">否</span>'}</td>
      <td>${myRoles.length?myRoles.map(x=>'<span class="tag">'+x+'</span>').join(" "):'<span class="muted">—</span>'}</td>
      <td>${acts}</td></tr>`;
  }).join(""):'<tr><td colspan="8" class="empty">暂无账号</td></tr>';
  document.querySelectorAll("#am-body [data-am-toggle]").forEach(b=>b.onclick=async()=>{
    if(!requireAuth())return;
    const target=b.dataset.amToggle, role=b.dataset.role, grant=b.dataset.grant==="1";
    if(grant&&AM_META.scoped[role]){openAmScope(target,role);return;}
    if(!await UI.confirm("确认"+(grant?"设为":"取消")+"「"+role+"」："+target+"？"))return;
    if(grant)await amGrant(target,role,"");
    else await amRevoke(target,role);
  });
  loadEvalRoleAssigns();
}
async function adminSet(grant){
  if(!requireAuth())return;
  const target=val("am-account").trim();
  const role=val("am-role");
  if(!target){await UI.alert("请填写目标账号");return;}
  let scope="";
  if(grant&&AM_META.scoped[role]){
    scope=val("am-scope");
    if(!scope){await UI.alert("「"+role+"」须选择"+(AM_META.scoped[role]||"管辖范围"));return;}
  }
  const res=await fetch(grant?"/api/admin/grant":"/api/admin/revoke",{method:"POST",headers:j(),body:JSON.stringify({account_id:target,role:role,scope:scope})}).then(x=>x.json());
  if(res.error){await UI.alert("操作失败："+res.error);return;}
  document.getElementById("am-tip").textContent=(grant?"已设为":"已取消")+"管理员："+target+" / "+role+(scope?("·"+scope):"");
  loadAdminMgmt();
}
async function createAccount(){
  if(!requireAuth())return;
  const account_id=val("na-account").trim();
  if(!account_id){await UI.alert("请填写账号");return;}
  const body={
    account_id,
    display_name:val("na-name").trim(),
    password:val("na-pw").trim(),
    level:val("na-level"),
    is_official:document.getElementById("na-official").checked,
    is_admin:document.getElementById("na-admin").checked
  };
  const res=await fetch("/api/accounts",{method:"POST",headers:j(),body:JSON.stringify(body)}).then(x=>x.json());
  if(res.error){await UI.alert("创建失败："+res.error);return;}
  document.getElementById("modal-new-account").classList.remove("show");
  await UI.alert("已创建账号："+account_id+(body.is_official?"（官方账号·管理员级别）":(body.is_admin?"（管理员级别）":"")));
  loadAdminMgmt();
}

async function loadAppeals(){const d=await API("/api/appeals");
  document.getElementById("appeal-body").innerHTML=d.rows.length?d.rows.map(r=>`<tr>
    <td>${r.ref_type||""}</td><td>${r.ref_id||""}</td>
    <td>${r.account_id}${r.display_name&&r.display_name!==r.account_id?`<br><span class="muted">${r.display_name}</span>`:""}</td>
    <td>${r.appeal_time||""}</td><td>${r.conclusion||""}</td><td>${r.suspended?"<span class=\"pill y\">暂停</span>":"<span class=\"pill g\">否</span>"}</td><td>${r.note||""}</td>
    <td>${ME?`<button class="linkbtn" data-ap="${r.id}" data-auth="write">改</button><button class="linkbtn del" data-apd="${r.id}" data-auth="write">删</button>`:'<span class="muted">—</span>'}</td></tr>`).join(""):'<tr><td colspan="8" class="empty">暂无申诉记录</td></tr>';
  document.querySelectorAll("#appeal-body [data-ap]").forEach(b=>b.onclick=()=>openAppeal(b.dataset.ap));
  document.querySelectorAll("#appeal-body [data-apd]").forEach(b=>b.onclick=async()=>{if(!requireAuth())return;if(await UI.confirm("确认删除该申诉？")){await fetch("/api/appeals/"+b.dataset.apd,{method:"DELETE"});loadAppeals();}});}
function openAppeal(id){apId=id||null;["ap-ref-type","ap-ref-id","ap-account","ap-appeal-time","ap-handler","ap-conclusion","ap-note","ap-recuser","ap-recuse-reason"].forEach(x=>document.getElementById(x).value="");document.getElementById("ap-suspended").value="1";document.getElementById("ap-recused").checked=false;document.getElementById("ap-recuse-hint").style.display="none";
  if(id){fetch("/api/appeals").then(r=>r.json()).then(d=>{const r=d.rows.find(x=>String(x.id)===String(id));if(r){document.getElementById("ap-ref-type").value=r.ref_type||"";document.getElementById("ap-ref-id").value=r.ref_id||"";document.getElementById("ap-account").value=r.account_id;document.getElementById("ap-appeal-time").value=r.appeal_time||"";document.getElementById("ap-handler").value=r.handler||"";document.getElementById("ap-suspended").value=r.suspended?"1":"0";document.getElementById("ap-conclusion").value=r.conclusion||"";document.getElementById("ap-note").value=r.note||"";document.getElementById("ap-recused").checked=!!r.recused;document.getElementById("ap-recuser").value=r.recuser||"";document.getElementById("ap-recuse-reason").value=r.recuse_reason||"";}});}
  document.getElementById("ap-account").onchange=()=>refreshRecuseHint("ap-account","ap-handler","ap-recuse-hint");document.getElementById("ap-handler").onchange=()=>refreshRecuseHint("ap-account","ap-handler","ap-recuse-hint");
  document.getElementById("modal-appeal").classList.add("show");}
async function refreshRecuseHint(acctField,handlerField,hintId){const acct=val(acctField);const handler=val(handlerField);const hint=document.getElementById(hintId);
  if(!acct||!handler){hint.style.display="none";return;}
  const d=await API("/api/recuse-hint?account_id="+encodeURIComponent(acct)+"&handler="+encodeURIComponent(handler));
  if(d.hint){hint.textContent="⚠️ "+d.hint;hint.style.display="block";hint.style.color="var(--bad)";}else{hint.style.display="none";}}
async function saveAppeal(){if(!requireAuth())return;const b={ref_type:val("ap-ref-type"),ref_id:+val("ap-ref-id")||0,account_id:val("ap-account"),appeal_time:val("ap-appeal-time"),handler:val("ap-handler"),conclusion:val("ap-conclusion"),suspended:document.getElementById("ap-suspended").value==="1",note:val("ap-note"),
    recused:document.getElementById("ap-recused").checked,recuser:val("ap-recuser"),recuse_reason:val("ap-recuse-reason")};
  if(!b.account_id){await UI.alert("申诉账号为必填");return;}
  const res=apId?await fetch("/api/appeals/"+apId,{method:"PUT",headers:j(),body:JSON.stringify(b)}).then(r=>r.json()):await API("/api/appeals",{method:"POST",headers:j(),body:JSON.stringify(b)});
  if(res.error){await UI.alert("提交失败："+res.error);return;}document.getElementById("modal-appeal").classList.remove("show");loadAppeals();}
async function loadPromote(){const d=await API("/api/permissions?status=见习&size=2000");
  document.getElementById("promote-body").innerHTML=d.rows.length?d.rows.map(r=>`<tr>
    <td>${r.account_id}${r.display_name&&r.display_name!==r.account_id?`<br><span class="muted">${r.display_name}</span>`:""}</td>
    <td>${r.category}</td><td>${r.probation_until||"—"}</td>
    <td>${ME?`<button class="linkbtn" data-pro="${r.id}" data-auth="write">转正</button>`:'<span class="muted">—</span>'}</td></tr>`).join(""):'<tr><td colspan="4" class="empty">暂无见习状态的权限记录</td></tr>';
  document.querySelectorAll("#promote-body [data-pro]").forEach(b=>b.onclick=async()=>{
    if(!await UI.confirm("确认将该权限由见习转为正常？系统将校验见习期与违规/申诉状态。"))return;
    const res=await fetch("/api/permissions/promote",{method:"PUT",headers:j(),body:JSON.stringify({id:+b.dataset.pro})}).then(r=>r.json());
    if(res.error){await UI.alert("转正失败："+res.error);return;}
    await UI.alert("转正成功");loadPromote();});}
let vioId=null, apId=null;

// ---------- 日志 ----------
async function loadLogs(){const d=await API("/api/logs");
  document.getElementById("log-body").innerHTML=d.rows.length?d.rows.map(r=>`<tr><td>${r.id}</td><td>${r.permission_id}</td><td>${r.account_id||"—"}</td><td>${r.action}</td><td>${r.operator}</td><td>${r.change_time}</td><td class="wrap">${r.detail}</td></tr>`).join(""):'<tr><td colspan="7" class="empty">无记录</td></tr>';}

// ---------- 我的权限（个人账号主页） ----------
async function loadMyPerms(){
  const d=await fetch("/api/my-capabilities",{headers:{"Authorization":"Bearer "+loadToken()}}).then(r=>r.json());
  if(d.account_id===null||d.account_id===undefined){showLogin();return;}
  const tier=d.tier||"无评审权限";
  const tierColor=tier==='超级管理员'?'#7c2d12':tier==='管理员'?'#b6602a':tier==='高审'?'var(--lv3,#c2410c)':tier==='中审'?'var(--lv2,#6d28d9)':'var(--lv1,#0369a1)';
  document.getElementById("myperm-head").innerHTML=`<div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap">
    <div style="font-size:18px;font-weight:800">${d.account_id}</div>
    <span class="pill">${d.level||""}</span>
    <span class="pill ${d.status==='正常'?'g':'y'}">${d.status||""}</span>
    ${tier!=="无评审权限"?`<span class="pill lv3" style="background:${tierColor};color:#fff">层级：${tier}</span>`:`<span class="pill lv3">无评审权限</span>`}
  </div>`;
  const caps=d.capabilities||[];
  const tierColorMap={'初审':'var(--lv1,#0369a1)','中审':'var(--lv2,#6d28d9)','高审':'var(--lv3,#c2410c)','管理员':'#b6602a','超级管理员':'#7c2d12'};
  document.getElementById("myperm-caps").innerHTML=caps.length?caps.map(c=>`
    <div class="capitem ${c.has?'on':'off'}">
      <div class="capname"><span class="led"></span>${c.name}<span class="tier-tag" style="background:${tierColorMap[c.tier]||'var(--primary)'};color:#fff;border-color:transparent">${c.tier||""}</span></div>
      <div class="capdesc">${c.desc||""}</div>
      <div class="caprow"><span class="capstate">${c.has?'● 拥有':'○ 无'}${c.override===1?'（单独开通）':c.override===0?'（单独撤销）':''}</span></div>
    </div>`).join(""):'<div class="muted">暂无权限数据</div>';
  const cats=d.categories||[];
  document.getElementById("myperm-cats").innerHTML=cats.length?cats.map(c=>`<span class="tag">${c.category} · ${c.level||""} · ${c.status||""}</span>`).join(""):'<span class="tag muted">暂无审核分类权限</span>';
  const adminBox=document.getElementById("myperm-admin");
  if(ME&&ME.is_super_admin){ adminBox.style.display="block"; bindCapAdminOnce(); }
  else adminBox.style.display="none";
}
let capAdminBound=false;
function bindCapAdminOnce(){
  if(capAdminBound) return; capAdminBound=true;
  const capInput=document.getElementById("cap-account");
  const loadBtn=document.getElementById("btn-cap-load");
  const doLoad=()=>{ const t=val("cap-account").trim(); if(!t){UI.alert("请填写目标账号");return;} loadCapMatrix(t); };
  if(loadBtn) loadBtn.onclick=doLoad;
  if(capInput) capInput.addEventListener("keydown",e=>{ if(e.key==="Enter"){ e.preventDefault(); doLoad(); } });
  const bulk=document.getElementById("cap-bulk");
  if(bulk) bulk.querySelectorAll("button[data-tier]").forEach(b=>b.onclick=async()=>{
    const t=val("cap-account").trim(); if(!t){UI.alert("请先载入目标账号");return;}
    if(!await UI.confirm("确认"+(b.dataset.act==='grant'?'开通':'撤销')+b.dataset.tier+"全套权限："+t+"？"))return;
    const res=await fetch("/api/admin/capability-bulk",{method:"POST",headers:j(),body:JSON.stringify({account_id:t,tier:b.dataset.tier,action:b.dataset.act})}).then(x=>x.json());
    if(res.error){await UI.alert("操作失败："+res.error);return;}
    loadCapMatrix(t);
  });
}
async function loadCapMatrix(t){
  const d=await API("/api/admin/account-capabilities?account_id="+encodeURIComponent(t));
  if(d.error){document.getElementById("cap-tip").textContent=d.error;return;}
  document.getElementById("cap-tip").textContent="已载入："+t+"（层级 "+d.tier+"）";
  document.getElementById("cap-bulk").style.display="flex";
  const caps=d.capabilities||[];
  const box=document.getElementById("cap-matrix"); box.style.display="grid";
  box.innerHTML=caps.length?caps.map(c=>`
    <div class="capitem ${c.has?'on':'off'}">
      <div class="capname"><span class="led"></span>${c.name}<span class="tier-tag">${c.tier}</span></div>
      <div class="capdesc">${c.desc||""}</div>
      <div class="caprow">
        <span class="capstate">${c.has?'● 拥有':'○ 无'}${c.override===1?'（单独开通）':c.override===0?'（单独撤销）':''}</span>
        <span class="capact">
          <button class="btn ghost sm" data-cap="${c.key}" data-grant="1">开通</button>
          <button class="btn ghost sm" data-cap="${c.key}" data-grant="0">撤销</button>
        </span>
      </div>
    </div>`).join(""):'<div class="muted">暂无权限数据</div>';
  box.querySelectorAll("[data-cap]").forEach(b=>b.onclick=async()=>{
    const grant=b.dataset.grant==="1";
    const name=(caps.find(x=>x.key===b.dataset.cap)||{}).name||b.dataset.cap;
    if(!await UI.confirm("确认"+(grant?"开通":"撤销")+"「"+name+"」："+t+"？"))return;
    const res=await fetch(grant?"/api/admin/capability-grant":"/api/admin/capability-revoke",{method:"POST",headers:j(),body:JSON.stringify({account_id:t,capability:b.dataset.cap})}).then(x=>x.json());
    if(res.error){await UI.alert("操作失败："+res.error);return;}
    loadCapMatrix(t);
  });
}

// ---------- 权限梳理（按层级展示 + 统计） ----------
async function loadPermSort(){
  const d=await API("/api/capabilities");
  const caps=d.caps||[], tiers=d.tiers||[], stats=d.stats||{};
  const grid=document.getElementById("permsort-grid");
  grid.innerHTML=tiers.map((tier,idx)=>{
    const items=caps.filter(c=>c.tier===tier);
    return `<div class="tier-col lev-${idx}"><h4>${tier}</h4><ul>${items.map(c=>`<li>${c.name}<span class="d">${c.desc||""}</span></li>`).join("")}</ul></div>`;
  }).join("");
  const tb=document.getElementById("permsort-stats-body");
  tb.innerHTML=caps.length?caps.map(c=>`<tr><td>${c.name}</td><td><span class="tag">${c.tier}</span></td><td>${stats[c.key]!=null?stats[c.key]:0}</td></tr>`).join(""):'<tr><td colspan="3">暂无数据</td></tr>';
}

// ---------- 基础数据 ----------
function renderAcctRow(r){
  const isOff=!!r.is_official;
  const usage = isOff?'<span class="pill" style="background:#1d4ed8;color:#fff">官方</span>':`<span class="pill ${r.is_test?'y':'g'}">${r.is_test?'测试':'实际'}</span>`;
  const usageBtn = (ME && ME.is_super_admin && !isOff) ? ` <button class="linkbtn" data-acct-test="${r.id}" data-current="${r.is_test?1:0}" title="切换用途">标记为${r.is_test?'实际':'测试'}</button>` : '';
  const ops = [];
  if(ME) ops.push(`<button class="linkbtn" data-aid="${r.id}" data-auth="write">编辑</button>`);
  if(ME && ME.is_super_admin) ops.push(`<button class="linkbtn del" data-acct-del="${r.id}" title="彻底删除">删除</button>`);
  const levelCell=isOff?'<span class="pill" style="background:#1d4ed8;color:#fff">官方</span>':`<span class="pill ${LEVEL_CLASS[r.level]||'n'}">${r.level}</span>`;
  return `<tr>
    <td>${r.account_id}</td><td>${levelCell}</td><td><span class="pill ${STATUS_CLASS[r.status]||'n'}">${r.status}</span></td>
    <td>${usage}${usageBtn}</td>
    <td>${r.join_date||""}</td><td>${r.last_login_ip_display?escMsg(r.last_login_ip_display):'<span class="muted">—</span>'}</td><td>${r.last_login_device?escMsg(r.last_login_device):'<span class="muted">—</span>'}</td><td>${r.note||""}</td>
    <td>${ops.length?ops.join(' '):'<span class="muted">—</span>'}</td></tr>`;
}
async function loadAccts(){const d=await API("/api/accounts");
  const official=d.rows.filter(r=>r.is_official), real=d.rows.filter(r=>!r.is_official&&!r.is_test), test=d.rows.filter(r=>!r.is_official&&r.is_test);
  document.getElementById("acct-body").innerHTML=real.length?real.map(renderAcctRow).join(""):'<tr><td colspan="9" class="empty">暂无实际账号</td></tr>';
  document.getElementById("acct-official-body").innerHTML=official.length?official.map(renderAcctRow).join(""):'<tr><td colspan="9" class="empty">暂无官方账号</td></tr>';
  document.getElementById("acct-test-body").innerHTML=test.length?test.map(renderAcctRow).join(""):'<tr><td colspan="9" class="empty">暂无测试账号</td></tr>';
  document.querySelectorAll("#acct-body [data-aid], #acct-official-body [data-aid], #acct-test-body [data-aid]").forEach(b=>b.onclick=()=>openAcct(b.dataset.aid));
  document.querySelectorAll("#acct-body [data-acct-del], #acct-official-body [data-acct-del], #acct-test-body [data-acct-del]").forEach(b=>b.onclick=async()=>{
    if(!requireAuth())return;
    const id=b.dataset.acctDel;
    const row=d.rows.find(x=>String(x.id)===String(id));
    if(!row)return;
    if(!await UI.confirm(`确认彻底删除账号「${row.account_id}」？\n将同步删除其权限、日志、申请、管理员角色等全部关联数据，不可恢复。`))return;
    const res=await fetch("/api/accounts/"+id,{method:"DELETE",headers:j()}).then(r=>r.json());
    if(res.error){await UI.alert("删除失败："+res.error);return;}
    await UI.alert("账号已彻底删除");
    loadAccts();loadOverview();loadLogs();
  });
  document.querySelectorAll("#acct-body [data-acct-test], #acct-test-body [data-acct-test]").forEach(b=>b.onclick=async()=>{
    if(!requireAuth())return;
    const id=b.dataset.acctTest;
    const cur=parseInt(b.dataset.current||"0",10);
    const row=d.rows.find(x=>String(x.id)===String(id));
    if(!row)return;
    const next=!cur;
    const label=next?'测试账号':'实际账号';
    if(!await UI.confirm(`确认将「${row.account_id}」标记为 ${label}？`))return;
    const res=await fetch("/api/accounts/"+id+"/test",{method:"PUT",headers:j(),body:JSON.stringify({is_test:next?1:0})}).then(r=>r.json());
    if(res.error){await UI.alert("操作失败："+res.error);return;}
    showToast(`${row.account_id} 已标记为 ${label}`,"ok");
    loadAccts();loadOverview();loadLogs();
  });
  loadPwdRequests();}
async function loadPwdRequests(){
  if(!(ME&&ME.is_super_admin))return;
  const card=document.getElementById("pwdreq-card");if(!card)return;
  const d=await API("/api/password-reset-requests?status=待处理");
  if(d.error){card.style.display="none";return;}
  const rows=d.rows||[];
  card.style.display=rows.length?"block":"none";
  document.getElementById("pwdreq-count").textContent=rows.length?("（"+rows.length+" 条）"):"";
  document.getElementById("pwdreq-body").innerHTML=rows.length?rows.map(r=>`<tr>
    <td>${escMsg(r.account_id)}</td><td>${r.contact?escMsg(r.contact):'<span class="muted">—</span>'}</td><td>${escMsg(r.created_at||"")}</td>
    <td><button class="linkbtn" data-pwdrst="${escMsg(r.account_id)}">重置密码</button></td></tr>`).join(""):"";
  document.querySelectorAll("#pwdreq-body [data-pwdrst]").forEach(b=>b.onclick=async()=>{
    if(!requireAuth())return;
    await resetAccountPassword(b.dataset.pwdrst, ()=>loadPwdRequests());
  });
}
async function resetAccountPassword(accountId, after){
  if(!(ME&&ME.is_super_admin)){await UI.alert("无权限：仅超级管理员可重置密码");return;}
  if(!await UI.confirm("确认为账号「"+accountId+"」重置 12 位随机密码？原密码将立即失效。"))return;
  const res=await fetch("/api/accounts/reset-password",{method:"POST",headers:j(),body:JSON.stringify({account_id:accountId})}).then(r=>r.json());
  if(res.error){await UI.alert("重置失败："+res.error);return;}
  await UI.alert("已重置成功。\n账号："+accountId+"\n新密码："+res.new_password+"\n（明文仅此一次展示，请立即复制并告知对方，提示对方登录后自行修改）");
  if(after)after();
}
function setAcctModal(r){
  document.getElementById("a-account").value=r.account_id;document.getElementById("a-level").value=r.level;document.getElementById("a-status").value=r.status;document.getElementById("a-join").value=r.join_date||"";document.getElementById("a-note").value=r.note||"";
  refreshCustomSelect("a-level");refreshCustomSelect("a-status");
  const rst=document.getElementById("acct-resetpw"), hint=document.getElementById("a-reset-hint");
  const show=rst&&ME&&ME.is_super_admin;
  if(rst)rst.style.display=show?"":"none";
  if(hint)hint.style.display=show?"block":"none";
  if(rst)rst.onclick=async()=>{if(!requireAuth())return;await resetAccountPassword(r.account_id);};
  document.getElementById("modal-acct").classList.add("show");}
function openAcct(id){fetch("/api/accounts").then(r=>r.json()).then(d=>{const r=d.rows.find(x=>String(x.id)===String(id));if(r)setAcctModal(r);});}
function openAcctByAid(aid){fetch("/api/accounts").then(r=>r.json()).then(d=>{const r=d.rows.find(x=>x.account_id===aid);if(r)setAcctModal(r);});}
async function saveAcct(){if(!requireAuth())return;
  const aid=document.getElementById("a-account").value;const b={level:val("a-level"),status:val("a-status"),join_date:val("a-join"),note:val("a-note")};
  const acctId=await findAcctId(aid);if(!acctId){await UI.alert("未找到该账号的ID");return;}
  const res=await fetch("/api/accounts/"+acctId,{method:"PUT",headers:j(),body:JSON.stringify(b)}).then(r=>r.json());
  if(res.error){await UI.alert("保存失败："+res.error);return;}document.getElementById("modal-acct").classList.remove("show");loadAccts();loadDict();loadOverview();loadLedger();loadLogs();}
async function findAcctId(aid){const d=await API("/api/accounts");const r=d.rows.find(x=>x.account_id===aid);return r?r.id:null;}
async function loadCategories(){
  const d=await API("/api/categories");
  const rows=d.rows||[];
  document.getElementById("dict-cats-body").innerHTML=rows.length?rows.map(c=>`<tr data-cat-id="${c.id}">
    <td>${escMsg(c.domain)}</td><td>${escMsg(c.group_name)}</td><td>${escMsg(c.category)}</td>
    <td>${ME&&ME.is_super_admin?`<button class="linkbtn" data-cat-edit="${c.id}">编辑</button> <button class="linkbtn del" data-cat-del="${c.id}">删除</button>`:'<span class="muted">—</span>'}</td>
  </tr>`).join(""):'<tr><td colspan="4" class="empty">暂无分类</td></tr>';
  document.querySelectorAll("#dict-cats-body [data-cat-edit]").forEach(b=>b.onclick=()=>openCatModal(parseInt(b.dataset.catEdit)));
  document.querySelectorAll("#dict-cats-body [data-cat-del]").forEach(b=>b.onclick=async()=>{
    if(!requireAuth())return;
    const id=parseInt(b.dataset.catDel);
    const row=rows.find(x=>x.id===id); if(!row)return;
    if(!await UI.confirm(`确认删除分类「${row.category}」？\n若该分类已被权限记录引用，系统将拒绝删除。`))return;
    const res=await fetch("/api/categories/"+id,{method:"DELETE",headers:j()}).then(r=>r.json());
    if(res.error){await UI.alert("删除失败："+res.error);return;}
    loadCategories();loadDict();
  });
}
function openCatModal(id){
  const isEdit=!!id;
  document.getElementById("cat-id").value=id||"";
  document.getElementById("cat-title").textContent=isEdit?"编辑分类":"新增分类";
  if(isEdit){
    const row=[...document.querySelectorAll("#dict-cats-body tr")].find(tr=>parseInt(tr.dataset.catId)===id);
    if(row){
      const tds=row.querySelectorAll("td");
      document.getElementById("cat-domain").value=tds[0].textContent;
      document.getElementById("cat-group").value=tds[1].textContent;
      document.getElementById("cat-name").value=tds[2].textContent;
    }
  }else{
    document.getElementById("cat-domain").value="";
    document.getElementById("cat-group").value="";
    document.getElementById("cat-name").value="";
  }
  document.getElementById("modal-cat").classList.add("show");
}
async function saveCat(){
  if(!requireAuth())return;
  const id=document.getElementById("cat-id").value;
  const body={domain:val("cat-domain"),group_name:val("cat-group"),category:val("cat-name")};
  const url=id?"/api/categories/"+id:"/api/categories";
  const method=id?"PUT":"POST";
  const res=await fetch(url,{method,headers:j(),body:JSON.stringify(body)}).then(r=>r.json());
  if(res.error){await UI.alert("保存失败："+res.error);return;}
  document.getElementById("modal-cat").classList.remove("show");
  loadCategories();loadDict();
}

// ---------- 考核 CSV 导入 ----------
function openRImport(scope){
  document.getElementById("ri-result").style.display="none";
  if(scope)document.getElementById("ri-scope").value=scope;
  document.getElementById("modal-rimport").classList.add("show");
  _resetFileInput();
}
function readFileAsText(file){
  return new Promise((res,rej)=>{
    const r=new FileReader();
    r.onload=()=>{
      const buf=r.result;
      const encoders=["utf-8","gb18030","gbk"];
      for(const enc of encoders){
        try{
          const txt=new TextDecoder(enc,{fatal:true}).decode(buf);
          // 简单启发：若 UTF-8 解码后出现大量替换了 U+FFFD，则换下一个
          if(enc==="utf-8" && txt.indexOf("\uFFFD")!==-1) continue;
          return res(txt);
        }catch(e){}
      }
      // 兜底：非致命解码
      res(new TextDecoder("utf-8").decode(buf));
    };
    r.onerror=()=>rej(r.error);
    r.readAsArrayBuffer(file);
  });
}
function _resetFileInput(){
  const label=document.getElementById("ri-file-label");
  const txt=document.getElementById("ri-filename");
  if(label){label.classList.remove("has-file");}
  if(txt){txt.classList.add("placeholder"); txt.textContent="点击选择 CSV 文件，或拖拽文件到此处";}
}
function _setFileName(name){
  const label=document.getElementById("ri-file-label");
  const txt=document.getElementById("ri-filename");
  if(label){label.classList.add("has-file");}
  if(txt){txt.classList.remove("placeholder"); txt.textContent=name||"已选择文件";}
}
async function importAssessCSV(preview){
  const file=document.getElementById("ri-file").files[0];
  const text=document.getElementById("ri-text").value.trim();
  let csv="";
  if(file){csv=await readFileAsText(file);}
  else if(text){csv=text;}
  else{await UI.alert("请选择文件或粘贴 CSV 内容");return;}
  const res=await fetch("/api/assess/import",{method:"POST",headers:j(),body:JSON.stringify({csv,period:val("ri-period"),operator:val("ri-op"),scope:val("ri-scope"),preview:!!preview})}).then(r=>r.json());
  const box=document.getElementById("ri-result"); box.style.display="block";
  if(res.error){box.innerHTML="<span style='color:var(--bad)'>导入失败："+res.error+"</span>"; return;}
  const scopeLabel={edit:"编辑任务",review:"评审任务",official:"官方任务",all:"全部"}[res.scope]||res.scope;
  const sum=`周期 <b>${res.period}</b> · 导入类型 <b>${scopeLabel}</b> · 有效记录 <b>${res.total_rows}</b> 条${res.skipped_rows?`（跳过 ${res.skipped_rows} 条）`:``} · 生成 <b>${res.records.length}</b> 人评分`;
  const table=`<table class="mini"><thead><tr><th>账号</th><th>版本判定%</th><th>任务达标%</th><th>官方错误%</th><th>反馈违规</th><th>综合分</th><th>判定</th><th>样本数</th></tr></thead><tbody>`+
    res.records.map(r=>`<tr><td>${r.account_id}</td><td>${r.v_judgment}</td><td>${r.v_task}</td><td>${r.v_official_err}</td><td>${r.v_feedback}</td><td><b>${r.composite}</b></td><td><span class="pill ${r.passed?'g':'r'}">${r.passed?'通过':'不通过'}</span></td><td>${r.rows}</td></tr>`).join("")+`</tbody></table>`;
  box.innerHTML=`<div style="margin-bottom:10px">${sum}</div>`+table;
  if(!preview){document.getElementById("ri-text").value=""; document.getElementById("ri-file").value=""; _resetFileInput(); loadPeriods(); const s=currentScope(); if(s==="edit"||s==="review"||s==="official")loadScope(s); if(s==="summary")loadSummary(); loadOverview(); loadLogs();}
}

// ---------- 全局必填星标统一：任何文本中的 * / ＊ / ✱ 统一渲染为红色半角 * ----------
// 运行时替换而非改源码，静态 HTML 与 JS 动态生成的表单（UP_SCHEMA 等）一并覆盖。
function unifyReqStars(root){
  root=root||document.body;
  const SKIP={SELECT:1,OPTION:1,TEXTAREA:1,SCRIPT:1,STYLE:1,INPUT:1};
  const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT,{acceptNode:function(n){
    const v=n.nodeValue;
    if(!v||(v.indexOf("*")<0&&v.indexOf("＊")<0&&v.indexOf("✱")<0))return NodeFilter.FILTER_REJECT;
    let p=n.parentElement;
    while(p){
      if(SKIP[p.tagName])return NodeFilter.FILTER_REJECT;
      if(p.classList&&p.classList.contains("req-star"))return NodeFilter.FILTER_REJECT; // 防自身递归
      p=p.parentElement;
    }
    return NodeFilter.FILTER_ACCEPT;
  }});
  const hits=[]; while(walker.nextNode())hits.push(walker.currentNode);
  hits.forEach(function(n){
    const parts=n.nodeValue.replace(/[＊✱]/g,"*").split("*");
    const frag=document.createDocumentFragment();
    parts.forEach(function(t,i){
      if(t)frag.appendChild(document.createTextNode(t));
      if(i<parts.length-1){const s=document.createElement("span");s.className="req-star";s.textContent="*";frag.appendChild(s);}
    });
    n.parentNode.replaceChild(frag,n);
  });
}
let _reqStarsLock=false;
const _reqStarsMO=new MutationObserver(function(){
  if(_reqStarsLock)return; _reqStarsLock=true;
  setTimeout(function(){ try{unifyReqStars();}finally{_reqStarsLock=false;} },60);
});
function startReqStarsWatcher(){
  unifyReqStars();
  _reqStarsMO.observe(document.body,{childList:true,subtree:true});
}

// ---------- 站内信箱（内部消息系统） ----------
const MSG_TYPE_LABEL={"system":"系统消息","push":"单独推送"};
const MSG_SCOPE_LABEL={"all":"全体成员","user":"指定账号","group":"用户组/群体"};
const MSG_SOURCE_LABEL={"manual":"手动发布","auto":"自动触发"};
const MSG_RULE_LABEL={"assess_result":"考核成绩公布","assess_notice":"月度考核通知"};
let ibSub="inbox", ibPage=1, mgPage=1;
function escMsg(s){return String(s==null?"":s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));}
function msgTime(t){return t?String(t).slice(0,19):"";}

function showInboxSub(sub){
  if(sub==="manage" && !(ME&&ME.is_super_admin)){UI.alert("无权限：消息管理仅超级管理员可访问"); sub="inbox";}
  ibSub=sub;
  document.querySelectorAll("#page-inbox .subtab").forEach(b=>b.classList.toggle("active",b.dataset.ib===sub));
  document.getElementById("ib-inbox").style.display=sub==="inbox"?"block":"none";
  const mg=document.getElementById("ib-manage"); if(mg) mg.style.display=sub==="manage"?"block":"none";
  if(sub==="inbox") loadInbox(); else loadMsgManage();
}
// ---- 我的收件箱 ----
async function loadInbox(){
  if(!ME||!ME.account_id) return;
  const kw=(val("ib-keyword")||"").trim();
  const q=new URLSearchParams({page:ibPage,size:20});
  if(kw) q.set("kw",kw);
  if(document.getElementById("ib-unread").checked) q.set("only_unread","1");
  const d=await API("/api/inbox?"+q.toString());
  const rows=d.rows||[];
  document.getElementById("ib-body").innerHTML=rows.length?rows.map(r=>`<tr class="${r.is_read?"":"ib-unread"}">
    <td>${r.is_read?'<span class="pill g">已读</span>':'<span class="pill r">未读</span>'}</td>
    <td>${MSG_TYPE_LABEL[r.msg_type]||r.msg_type}</td>
    <td class="wrap ${r.is_read?"":"msg-unread"}"><span class="msg-title-link" data-mv="${r.id}">${escMsg(r.title)}</span></td>
    <td>${MSG_SCOPE_LABEL[r.scope_type]||r.scope_type}</td>
    <td>${escMsg(r.sender||"系统")}</td>
    <td>${msgTime(r.send_time)}</td>
    <td>${msgTime(r.read_time)}</td>
    <td><button class="linkbtn" data-mv="${r.id}">查看详情</button>${r.is_read?"":`<button class="linkbtn" data-mrd="${r.id}">标记已读</button>`}</td>
  </tr>`).join(""):'<tr><td colspan="8" class="empty">暂无消息</td></tr>';
  document.querySelectorAll("#ib-body [data-mv]").forEach(b=>b.onclick=()=>openMsgView(b.dataset.mv));
  document.querySelectorAll("#ib-body [data-mrd]").forEach(b=>b.onclick=()=>markRead(b.dataset.mrd));
  const total=d.total||0,size=d.size||20,pages=Math.max(1,Math.ceil(total/size));
  document.getElementById("ib-total").textContent="共 "+total+" 条";
  document.getElementById("ib-page").textContent=ibPage+" / "+pages;
  loadInboxUnread();
}
async function markRead(id,silent){
  const res=await fetch("/api/inbox/"+id+"/read",{method:"POST",headers:j()}).then(r=>r.json());
  if(res.error){await UI.alert("标记失败："+res.error); return;}
  updateUnreadBadge(res.unread||0);
  if(!silent) showToast("已标记为已读","ok");
  if(document.getElementById("page-inbox").classList.contains("active")) loadInbox();
}
async function markAllRead(){
  if(!requireAuth()) return;
  const d=await API("/api/inbox?"+new URLSearchParams({only_unread:"1",size:500}).toString());
  const rows=d.rows||[];
  if(!rows.length){showToast("没有未读消息","info"); return;}
  if(!(await UI.confirm("确认将全部 "+rows.length+" 条未读消息标记为已读？"))) return;
  let last=0;
  for(const r of rows){
    const res=await fetch("/api/inbox/"+r.id+"/read",{method:"POST",headers:j()}).then(x=>x.json());
    if(!res.error) last=res.unread||0;
  }
  updateUnreadBadge(last); showToast("已全部标记为已读","ok"); loadInbox();
}
async function openMsgView(id){
  const d=await API("/api/inbox/"+id);
  if(d.error){await UI.alert(d.error); return;}
  document.getElementById("mv-title").textContent=d.title||"";
  const readTag=d.is_read?'<span class="pill g">已读</span>':'<span class="pill r">未读</span>';
  document.getElementById("mv-meta").innerHTML=
    `类型：<b>${MSG_TYPE_LABEL[d.msg_type]||d.msg_type}</b>　发布范围：<b>${MSG_SCOPE_LABEL[d.scope_type]||d.scope_type}</b>　发送人：<b>${escMsg(d.sender||"系统")}</b><br>`+
    `发送时间：<b>${msgTime(d.send_time)}</b>　来源：<b>${MSG_SOURCE_LABEL[d.source]||d.source}</b>${d.auto_rule?"（规则："+(MSG_RULE_LABEL[d.auto_rule]||d.auto_rule)+"）":""}<br>`+
    `状态：${readTag}　已读时间：<b>${msgTime(d.read_time)||"-"}</b>`;
  document.getElementById("mv-body").textContent=d.body||"（无正文）";
  document.getElementById("modal-msg-view").classList.add("show");
  if(!d.is_read) await markRead(id,true);
}
async function loadInboxUnread(){
  if(!ME||!ME.account_id){updateUnreadBadge(0); return;}
  const d=await API("/api/inbox/unread-count").catch(()=>({unread:0}));
  updateUnreadBadge(d.unread||0);
}
function updateUnreadBadge(n){
  const b=document.getElementById("inbox-badge"); if(b){
    b.style.display=n>0?"inline-flex":"none";
    b.textContent=n>99?"99+":String(n);
  }
  const tip=document.getElementById("ib-unread-tip");
  if(tip) tip.innerHTML=n>0?`您有 <b style="color:var(--bad)">${n}</b> 条未读消息`:"暂无未读消息";
}
// ---- 消息管理（仅超级管理员）----
async function loadMsgManage(){
  if(!(ME&&ME.is_super_admin)) return;
  const kw=(val("mg-keyword")||"").trim();
  const q=new URLSearchParams({page:mgPage,size:20});
  if(kw) q.set("kw",kw);
  const mt=val("mg-type"); if(mt) q.set("msg_type",mt);
  const ms=val("mg-scope"); if(ms) q.set("scope_type",ms);
  const d=await API("/api/messages?"+q.toString());
  const rows=d.rows||[];
  document.getElementById("mg-body").innerHTML=rows.length?rows.map(r=>`<tr>
    <td>${r.id}</td>
    <td>${MSG_TYPE_LABEL[r.msg_type]||r.msg_type}</td>
    <td class="wrap">${escMsg(r.title)}</td>
    <td>${MSG_SCOPE_LABEL[r.scope_type]||r.scope_type}</td>
    <td class="wrap">${r.scope_type==="all"?"全部成员":escMsg(r.scope_target||"-")}</td>
    <td>${MSG_SOURCE_LABEL[r.source]||r.source}${r.auto_rule?`<br><span class="muted">${MSG_RULE_LABEL[r.auto_rule]||r.auto_rule}</span>`:""}</td>
    <td>${r.recipient_count} / <b>${r.read_count}</b></td>
    <td>${msgTime(r.send_time)}</td>
    <td><button class="linkbtn" data-mgd="${r.id}">详情</button><button class="linkbtn del" data-mgdel="${r.id}">删除</button></td>
  </tr>`).join(""):'<tr><td colspan="9" class="empty">暂无消息</td></tr>';
  document.querySelectorAll("#mg-body [data-mgd]").forEach(b=>b.onclick=()=>openMsgDetail(b.dataset.mgd));
  document.querySelectorAll("#mg-body [data-mgdel]").forEach(b=>b.onclick=async()=>{
    if(!(await UI.confirm("确认删除该站内信？删除后所有接收人的记录一并清除。"))) return;
    const res=await fetch("/api/messages/"+b.dataset.mgdel,{method:"DELETE",headers:j()}).then(x=>x.json());
    if(res.error){await UI.alert("删除失败："+res.error); return;}
    showToast("已删除","ok"); loadMsgManage();
  });
  const total=d.total||0,size=d.size||20,pages=Math.max(1,Math.ceil(total/size));
  document.getElementById("mg-total").textContent="共 "+total+" 条";
  document.getElementById("mg-page").textContent=mgPage+" / "+pages;
}
async function openMsgDetail(id){
  const d=await API("/api/messages/"+id);
  if(d.error){await UI.alert(d.error); return;}
  const recs=d.recipients||[];
  const unreadN=recs.filter(r=>!r.is_read).length;
  document.getElementById("mv-title").textContent=d.title||"";
  document.getElementById("mv-meta").innerHTML=
    `类型：<b>${MSG_TYPE_LABEL[d.msg_type]||d.msg_type}</b>　范围：<b>${MSG_SCOPE_LABEL[d.scope_type]||d.scope_type}</b>　对象：<b>${d.scope_type==="all"?"全体成员":escMsg(d.scope_target||"-")}</b><br>`+
    `发送人：<b>${escMsg(d.sender||"")}</b>　发送时间：<b>${msgTime(d.send_time)}</b>　来源：<b>${MSG_SOURCE_LABEL[d.source]||d.source}</b>${d.auto_rule?"（"+(MSG_RULE_LABEL[d.auto_rule]||d.auto_rule)+"）":""}<br>`+
    `接收 <b>${recs.length}</b> 人，已读 <b>${recs.length-unreadN}</b> 人，未读 <b>${unreadN}</b> 人`;
  const list=recs.length?recs.map(r=>`<span class="tag ${r.is_read?"muted":""}">${escMsg(r.account_id)}${r.display_name&&r.display_name!==r.account_id?"("+escMsg(r.display_name)+")":""} ${r.is_read?"已读":"未读"}</span>`).join(""):'<span class="muted">无接收人</span>';
  document.getElementById("mv-body").innerHTML=`<div>${escMsg(d.body||"（无正文）")}</div><div class="taglist" style="margin-top:14px">${list}</div>`;
  document.getElementById("modal-msg-view").classList.add("show");
}
function syncMsgScope(){
  const s=val("ms-scope");
  document.getElementById("ms-wrap-user").style.display=s==="user"?"flex":"none";
  document.getElementById("ms-wrap-group").style.display=s==="group"?"block":"none";
}
// 群体搜索：按名称关键词过滤候选标签（不影响已勾选状态）
function filterMsgGroups(){
  const kw=(val("ms-group-search")||"").trim().toLowerCase();
  const tags=[...document.querySelectorAll("#ms-groups .tag.chk")];
  let shown=0;
  tags.forEach(t=>{
    const hit=!kw||t.textContent.toLowerCase().indexOf(kw)>=0;
    t.style.display=hit?"":"none";
    if(hit)shown++;
  });
  const cnt=document.getElementById("ms-group-count");
  if(cnt)cnt.textContent=kw?`匹配 ${shown} / ${tags.length} 个群体`:"";
}
async function openMsgSend(){
  if(!requireAuth()) return;
  if(!(ME&&ME.is_super_admin)){await UI.alert("无权限：仅超级管理员可发布站内信"); return;}
  ["ms-title","ms-body","ms-users"].forEach(id=>document.getElementById(id).value="");
  document.getElementById("ms-result").textContent="";
  document.getElementById("ms-scope").value="all";
  document.getElementById("ms-group-search").value="";
  const d=await API("/api/messages/groups");
  const groups=d.rows||[];
  document.getElementById("ms-groups").innerHTML=groups.length?groups.map(g=>
    `<label class="tag chk" data-key="${g.key}"><input type="checkbox" value="${g.key}">${escMsg(g.name)}（${g.count}人）</label>`).join("")
    :'<span class="muted">暂无可用群体</span>';
  document.querySelectorAll("#ms-groups .tag.chk input").forEach(cb=>{
    cb.checked=false;
    cb.onchange=()=>{const el=cb.closest(".tag"); if(el) el.classList.toggle("on",cb.checked);};
  });
  syncMsgScope();
  filterMsgGroups();
  refreshCustomSelect("ms-type"); refreshCustomSelect("ms-scope");
  document.getElementById("modal-msg-send").classList.add("show");
}
async function saveMsg(){
  if(!(ME&&ME.is_super_admin)){await UI.alert("无权限：仅超级管理员可发布站内信"); return;}
  const title=(val("ms-title")||"").trim();
  if(!title){await UI.alert("消息标题不能为空"); return;}
  const scope=val("ms-scope"); let target="";
  if(scope==="user"){
    target=(val("ms-users")||"").trim();
    if(!target){await UI.alert("请填写接收账号"); return;}
  } else if(scope==="group"){
    const sel=[...document.querySelectorAll("#ms-groups input:checked")].map(c=>c.value);
    if(!sel.length){await UI.alert("请至少选择一个用户组 / 群体"); return;}
    target=sel.join(",");
  }
  const res=await fetch("/api/messages",{method:"POST",headers:j(),
    body:JSON.stringify({msg_type:val("ms-type"),title:title,body:val("ms-body"),scope_type:scope,scope_target:target})}).then(r=>r.json());
  if(res.error){await UI.alert("发布失败："+res.error); return;}
  document.getElementById("ms-result").textContent="发布成功：消息 #"+res.id+"，共下发 "+res.count+" 人。";
  showToast("发布成功，已下发 "+res.count+" 人","ok");
  loadMsgManage();
}
function bindInbox(){
  document.querySelectorAll("#page-inbox .subtab").forEach(b=>b.onclick=()=>showInboxSub(b.dataset.ib));
  document.getElementById("btn-ib-query").onclick=()=>{ibPage=1;loadInbox();};
  document.getElementById("ib-keyword").addEventListener("keydown",e=>{if(e.key==="Enter"){e.preventDefault();ibPage=1;loadInbox();}});
  document.getElementById("ib-unread").onchange=()=>{ibPage=1;loadInbox();};
  document.getElementById("ib-prev").onclick=()=>{if(ibPage>1){ibPage--;loadInbox();}};
  document.getElementById("ib-next").onclick=()=>{ibPage++;loadInbox();};
  document.getElementById("btn-ib-readall").onclick=markAllRead;
  document.getElementById("btn-mg-query").onclick=()=>{mgPage=1;loadMsgManage();};
  document.getElementById("mg-prev").onclick=()=>{if(mgPage>1){mgPage--;loadMsgManage();}};
  document.getElementById("mg-next").onclick=()=>{mgPage++;loadMsgManage();};
  document.getElementById("btn-mg-send").onclick=openMsgSend;
  document.getElementById("ms-cancel").onclick=()=>document.getElementById("modal-msg-send").classList.remove("show");
  document.getElementById("ms-save").onclick=saveMsg;
  document.getElementById("ms-scope").onchange=syncMsgScope;
  document.getElementById("ms-group-search").oninput=filterMsgGroups;
  document.getElementById("mv-close").onclick=()=>document.getElementById("modal-msg-view").classList.remove("show");
  refreshCustomSelect("ms-type"); refreshCustomSelect("ms-scope");
  refreshCustomSelect("mg-type"); refreshCustomSelect("mg-scope");
  // 未读提醒：每分钟轮询一次，保持顶栏角标及时
  setInterval(()=>{if(ME&&ME.account_id) loadInboxUnread();}, 60000);
}

// ---------- 登录 / 会话 ----------
let TOKEN=null, ME=null;
function setToken(t){TOKEN=t; try{ if(t) localStorage.setItem("pcs_token",t); else localStorage.removeItem("pcs_token"); }catch(e){}}
function loadToken(){ try{ return localStorage.getItem("pcs_token"); }catch(e){ return null; } }
async function loadMe(){
  const t=loadToken(); if(!t){ME=null; renderUser(); return;}
  const d=await fetch("/api/me",{headers:{"Authorization":"Bearer "+t}}).then(r=>r.json()).catch(()=>({account_id:null}));
  if(d.account_id){TOKEN=t; ME={account_id:d.account_id,level:d.level,status:d.status,is_reviewer:d.is_reviewer,is_admin:d.is_admin,is_senior:!!d.is_senior,is_super_admin:!!d.is_super_admin,eval_roles:d.eval_roles||[]};} else {setToken(null); ME=null;}
  renderUser();
}
function renderUser(){
  const box=document.getElementById("userbox");
  document.body.classList.toggle("guest", !(ME&&ME.account_id));
  document.body.classList.remove("auth-pending");
  updateAdminNav();
  if(ME&&ME.account_id){
    box.style.display="inline-flex";
    const rolePill=ME.is_super_admin?'<span class="pill lv3" style="background:#7c2d12;color:#fff">超级管理员</span>':ME.is_admin?'<span class="pill lv3" style="background:var(--bad-soft);color:var(--bad)">管理员</span>':ME.is_senior?'<span class="pill lv3">高审</span>':ME.is_reviewer?'<span class="pill lv3">中审</span>':'';
    box.innerHTML=`<button class="btn ghost sm inbox-btn" id="btn-inbox" title="站内信箱"><svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>站内信<span class="inbox-badge" id="inbox-badge" style="display:none">0</span></button><span class="uinfo">${ME.account_id} · <b>${ME.level||""}</b>${rolePill}</span><button class="btn ghost sm" id="btn-chpw">修改密码</button><button class="btn ghost sm" id="btn-logout">退出</button>`;
    document.getElementById("btn-logout").onclick=doLogout;
    document.getElementById("btn-chpw").onclick=openChangePw;
    document.getElementById("btn-inbox").onclick=()=>showPage("inbox");
    loadInboxUnread();
  } else {
    box.style.display="inline-flex";
    box.innerHTML=`<button class="btn primary sm" id="btn-login">登录</button>`;
    document.getElementById("btn-login").onclick=()=>document.getElementById("modal-login").classList.add("show");
  }
}
function showLogin(){document.getElementById("lg-account").value="";document.getElementById("lg-pwd").value="";clearMsg("lg-msg");document.getElementById("modal-login").classList.add("show");document.getElementById("lg-account").focus();}
function getDeviceId(){
  let d=null;try{d=localStorage.getItem("pcs_device_id");}catch(e){}
  if(!d){d=(crypto.randomUUID?crypto.randomUUID():("dev-"+Date.now()+"-"+Math.random().toString(36).slice(2,10)));try{localStorage.setItem("pcs_device_id",d);}catch(e){}}
  return d;
}
async function doLogin(){const acc=document.getElementById("lg-account").value.trim(),pwd=document.getElementById("lg-pwd").value;
  const msg=document.getElementById("lg-msg"); msg.style.display="block";
  const res=await fetch("/api/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({account_id:acc,password:pwd,device_id:getDeviceId()})}).then(r=>r.json()).catch(e=>({error:e.message}));
  if(res.error){msg.textContent="登录失败："+res.error; msg.style.color="var(--bad)"; return;}
  if(!res.token){msg.textContent="登录失败：账号或密码错误"; msg.style.color="var(--bad)"; return;}
  setToken(res.token); ME={account_id:res.account_id,level:res.level,status:res.status,is_reviewer:res.is_reviewer,is_admin:res.is_admin,is_senior:!!res.is_senior,is_super_admin:!!res.is_super_admin,eval_roles:res.eval_roles||[]};
  document.getElementById("modal-login").classList.remove("show"); renderUser();
  // 刷新依赖权限的视图；若当前在制度页则只重载该页资源，否则整页刷新使受保护资源可见
  if(document.getElementById("page-system").classList.contains("active")){ loadSystem(); showToast("登录成功："+res.account_id+(res.is_reviewer?"（审核员）":""),"ok"); }
  else { showToast("登录成功，正在刷新页面…","ok"); location.reload(); }
}
function doLogout(){setToken(null); ME=null; renderUser(); if(["page-dict","page-logs","page-audit","page-logins"].some(id=>document.getElementById(id)?.classList.contains("active"))) showPage("overview"); showToast("已退出登录","info");}
function openChangePw(){
  if(!ME||!ME.account_id){showToast("请先登录后再修改密码","warn"); return;}
  document.getElementById("modal-login").classList.remove("show");
  document.getElementById("cp-account").value=ME.account_id;
  ["cp-old","cp-new","cp-confirm"].forEach(id=>document.getElementById(id).value="");
  document.getElementById("cp-msg").style.display="none";
  document.getElementById("cp-strength").textContent="";
  document.getElementById("modal-chpw").classList.add("show");
  document.getElementById("cp-old").focus();
}
function closeChangePw(){document.getElementById("modal-chpw").classList.remove("show");}
async function doChangePassword(){
  const acc=document.getElementById("cp-account").value.trim();
  const oldPwd=document.getElementById("cp-old").value;
  const newPwd=document.getElementById("cp-new").value;
  const confirm=document.getElementById("cp-confirm").value;
  const msg=document.getElementById("cp-msg"); msg.style.display="block";
  if(!acc){msg.textContent="请输入账号"; msg.style.color="var(--bad)"; return;}
  if(!oldPwd){msg.textContent="请输入原密码"; msg.style.color="var(--bad)"; return;}
  if(newPwd.length<6){msg.textContent="新密码长度至少 6 位"; msg.style.color="var(--bad)"; return;}
  if(newPwd!==confirm){msg.textContent="两次输入的新密码不一致"; msg.style.color="var(--bad)"; return;}
  const res=await fetch("/api/change-password",{method:"POST",headers:j(),body:JSON.stringify({account_id:acc,old_password:oldPwd,new_password:newPwd})}).then(r=>r.json()).catch(e=>({error:e.message}));
  if(res.error){msg.textContent="修改失败："+res.error; msg.style.color="var(--bad)"; return;}
  if(!res.ok){msg.textContent="修改失败："+(res.detail||"未知错误"); msg.style.color="var(--bad)"; return;}
  msg.textContent="密码修改成功，请使用新密码重新登录"; msg.style.color="var(--ok)";
  setTimeout(()=>{closeChangePw(); doLogout(); showLogin();},1200);
}
// ---------- 轻提示 ----------
let TOAST_TIMER=null;
function showToast(text,type){
  const box=document.getElementById("toast"), txt=document.getElementById("toast-text");
  if(!box||!txt) return;
  txt.textContent=text; box.className="toast show "+(type||"");
  box.style.display="flex";
  clearTimeout(TOAST_TIMER);
  TOAST_TIMER=setTimeout(()=>{box.classList.remove("show"); setTimeout(()=>box.style.display="none",200);},3000);
}
function clearMsg(id){const el=document.getElementById(id); if(el){el.style.display="none"; el.textContent="";}}
// ---------- 统一弹窗（替代浏览器原生 alert/confirm/prompt） ----------
const UI={
  _setup(id, title, text, okText, cancelText){
    document.getElementById(id+"-title").textContent=title;
    document.getElementById(id+"-text").textContent=text;
    const ok=document.getElementById(id+"-ok"); if(okText) ok.textContent=okText;
    const cancel=document.getElementById(id+"-cancel"); if(cancel&&cancelText) cancel.textContent=cancelText;
  },
  alert(text, title="提示"){
    return new Promise(resolve=>{
      this._setup("msg", title, text, "知道了", null);
      const modal=document.getElementById("modal-msg"); modal.classList.add("show");
      const ok=document.getElementById("msg-ok"), close=()=>{modal.classList.remove("show"); ok.onclick=null; resolve();};
      ok.onclick=close;
    });
  },
  confirm(text, title="确认"){
    return new Promise(resolve=>{
      this._setup("cf", title, text, "确认", "取消");
      const modal=document.getElementById("modal-confirm"); modal.classList.add("show");
      const ok=document.getElementById("cf-ok"), cancel=document.getElementById("cf-cancel");
      const cleanup=()=>{modal.classList.remove("show"); ok.onclick=null; cancel.onclick=null;};
      ok.onclick=()=>{cleanup(); resolve(true);};
      cancel.onclick=()=>{cleanup(); resolve(false);};
    });
  },
  prompt(text, def="", title="请输入"){
    return new Promise(resolve=>{
      this._setup("pm", title, text, "确认", "取消");
      const input=document.getElementById("pm-input"); input.value=def; input.focus(); input.select();
      const modal=document.getElementById("modal-prompt"); modal.classList.add("show");
      const ok=document.getElementById("pm-ok"), cancel=document.getElementById("pm-cancel");
      const cleanup=()=>{modal.classList.remove("show"); ok.onclick=null; cancel.onclick=null; input.onkeydown=null;};
      const submit=()=>{cleanup(); resolve(input.value);};
      ok.onclick=submit;
      cancel.onclick=()=>{cleanup(); resolve(null);};
      input.onkeydown=(e)=>{if(e.key==="Enter")submit(); if(e.key==="Escape"){cleanup(); resolve(null);}};
    });
  }
};
function requireAuth(msg="请先登录后再进行此操作"){if(!ME||!ME.account_id){UI.alert(msg); return false;} return true;}
function requireAdmin(){if(!requireAuth("请先登录"))return false; if(!ME.is_admin){UI.alert("无权限：系统管理仅对管理员开放"); return false;} return true;}
function updateAdminNav(){
  const show = !!(ME && ME.account_id && ME.is_admin);
  document.querySelectorAll("[data-admin='1']").forEach(el=>{
    if(el.classList.contains("navbtn")){el.style.display = show ? "" : "none";}
    else {el.style.display = show ? "flex" : "none";}
  });
  // 仅高审可见：违规登记入口等
  const seniorShow = !!(ME && ME.account_id && ME.level==='高审');
  document.querySelectorAll("[data-senior='1']").forEach(el=>{ el.style.display = seniorShow ? "" : "none"; });
  // 仅超级管理员可见：管理员管理等
  const saShow = !!(ME && ME.account_id && ME.is_super_admin);
  document.querySelectorAll("[data-superadmin='1']").forEach(el=>{ el.style.display = saShow ? "" : "none"; });
  // 官方任务名单已并入「申请/名单管理」，无需单独菜单开关
}
const EYE_OPEN='<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>';
const EYE_CLOSED='<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.96 9.96 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.82 3.32M4 4l16 16"/><circle cx="12" cy="12" r="3"/></svg>';
function toggleEye(btnId,inputId){
  const btn=document.getElementById(btnId), input=document.getElementById(inputId);
  if(!btn||!input) return;
  btn.addEventListener("click",()=>{
    const isPwd=input.type==="password";
    input.type=isPwd?"text":"password";
    btn.innerHTML=isPwd?EYE_CLOSED:EYE_OPEN;
    btn.classList.toggle("open",isPwd);
  });
}
function checkPwStrength(){
  const val=document.getElementById("cp-new").value;
  const box=document.getElementById("cp-strength");
  if(!val){box.textContent=""; return;}
  let score=0;
  if(val.length>=8) score++;
  if(/[A-Za-z]/.test(val)&&/\d/.test(val)) score++;
  if(/[^A-Za-z0-9]/.test(val)) score++;
  const levels=["弱：建议混合字母、数字与符号","中：可再加强复杂度","强"];
  const colors=["var(--bad)","var(--warn)","var(--ok)"];
  box.textContent="密码强度："+levels[Math.min(score,2)];
  box.style.color=colors[Math.min(score,2)];
}
// ---------- 工具 ----------
function j(){const h={"Content-Type":"application/json"}; if(TOKEN) h["Authorization"]="Bearer "+TOKEN; return h;}
function showPage(p){
  const groupOf=(page)=>{if(["ledger"].includes(page))return "perm"; if(["overview","dict","logs","audit","permsort","logins"].includes(page))return "sys"; return null;};
  const primary=(page)=>groupOf(page)||page;
  const pri=primary(p);
  document.querySelectorAll(".navbtn").forEach(b=>b.classList.toggle("active",b.dataset.page===pri));
  document.querySelectorAll(".subnav").forEach(n=>n.style.display="none");
  if(pri==="sys"){
    if(!requireAdmin())return;
    document.getElementById("subnav-sys").style.display="flex";
  }
  document.querySelectorAll(".subbtn").forEach(b=>b.classList.toggle("active",b.dataset.page===p));
  document.querySelectorAll(".page").forEach(s=>s.classList.toggle("active",s.id==="page-"+p));
  const _map={overview:loadOverview,ledger:loadLedger,assess:()=>showSub("edit"),apply:()=>showApplySub("newapply"),discipline:()=>showDiscSub("violation"),audit:loadAudit,logs:loadLogs,dict:()=>showDictSub("accts"),myperms:loadMyPerms,permsort:loadPermSort,inbox:()=>showInboxSub("inbox"),system:loadSystem,logins:loadLoginLogs};if(_map[p])_map[p]();
}
function showDictSub(sub){document.querySelectorAll("#page-dict .subtab").forEach(b=>b.classList.toggle("active",b.dataset.dict===sub));
  document.getElementById("dict-accts").style.display=sub==="accts"?"block":"none";document.getElementById("dict-cats").style.display=sub==="cats"?"block":"none";document.getElementById("dict-admin").style.display=sub==="admin"?"block":"none";
  if(sub==="accts")loadAccts();else if(sub==="admin")loadAdminMgmt();}
async function loadEvalRoleAssigns(){
  if(!(ME&&ME.is_super_admin))return;
  const tb=document.getElementById("er-body");if(!tb)return;
  const d=await API("/api/eval-role-assigns");
  const rows=(d&&d.rows)||[];
  if(!rows.length){tb.innerHTML='<tr><td colspan="6" class="empty">暂无角色绑定</td></tr>';return;}
  tb.innerHTML=rows.map(r=>`<tr>
    <td>${escMsg(r.role)}</td>
    <td>${escMsg(r.account_id)}</td>
    <td>${escMsg(r.display_name||"")}</td>
    <td>${r.category?escMsg(r.category):'<span class="muted">全部分类</span>'}</td>
    <td>${escMsg(r.created_at||"")}</td>
    <td><button class="linkbtn del" data-er="${r.id}">解除</button></td>
  </tr>`).join("");
}
function bind(){
  // ESC 关闭弹窗：优先关闭自定义下拉，再关闭最上层弹窗；UI.alert/confirm/prompt 按取消处理
  document.addEventListener("keydown",e=>{
    if(e.key!=="Escape") return;
    const openSel=document.querySelector(".sel-wrap.open");
    if(openSel){openSel.classList.remove("open"); e.stopPropagation(); return;}
    const modals=[...document.querySelectorAll(".modal.show")];
    if(!modals.length) return;
    const top=modals[modals.length-1];
    const id=top.id;
    if(id==="modal-confirm"){const c=document.getElementById("cf-cancel"); if(c) c.click();}
    else if(id==="modal-prompt"){const c=document.getElementById("pm-cancel"); if(c) c.click();}
    else if(id==="modal-msg"){const c=document.getElementById("msg-ok"); if(c) c.click();}
    else{top.classList.remove("show");}
    e.stopPropagation();
  });
  document.querySelectorAll(".navbtn").forEach(b=>b.onclick=()=>{
    const p=b.dataset.page;
    if(p==="perm")showPage("ledger");
    else if(p==="sys")showPage("dict");
    else showPage(p);
  });
  document.querySelectorAll(".subbtn").forEach(b=>b.onclick=()=>showPage(b.dataset.page));
  document.querySelectorAll("#page-assess .subtab").forEach(b=>b.onclick=()=>showSub(b.dataset.sub));
  document.querySelectorAll("#page-dict .subtab").forEach(b=>b.onclick=()=>showDictSub(b.dataset.dict));
  // 账号列表快捷筛选
  document.querySelectorAll(".acct-filter [data-acct-filter]").forEach(b=>b.onclick=()=>{
    const f=b.dataset.acctFilter;
    document.querySelectorAll(".acct-filter [data-acct-filter]").forEach(x=>x.classList.toggle("active",x===b));
    const real=document.getElementById("acct-real-card"), official=document.getElementById("acct-official-card"), test=document.getElementById("acct-test-card");
    if(real)real.style.display=(f==="real"||f==="all")?"block":"none";
    if(official)official.style.display=(f==="official"||f==="all")?"block":"none";
    if(test)test.style.display=(f==="test"||f==="all")?"block":"none";
  });
  document.getElementById("btn-query").onclick=()=>{ledgerPage=1;loadLedger();};
  document.getElementById("f-account").addEventListener("keydown",e=>{if(e.key==="Enter"){e.preventDefault();ledgerPage=1;loadLedger();}});
  document.getElementById("btn-reset").onclick=()=>{["f-domain","f-group","f-category","f-level","f-status","f-account"].forEach(id=>document.getElementById(id).value="");document.getElementById("f-active").checked=false;ledgerPage=1;loadLedger();};
  document.getElementById("btn-view").onclick=toggleView;
  document.getElementById("btn-add").onclick=()=>openEdit(null);
  document.getElementById("btn-import").onclick=()=>{document.getElementById("imp-text").value="";document.getElementById("imp-result").textContent="";document.getElementById("modal-import").classList.add("show");};
  document.getElementById("btn-export").onclick=()=>window.location.href="/api/export?"+new URLSearchParams(lf()).toString();
  const loginRefresh=document.getElementById("btn-loginlog-refresh"); if(loginRefresh) loginRefresh.onclick=()=>loadLoginLogs();
  document.getElementById("btn-stats-export").onclick=()=>window.location.href="/api/export?"+new URLSearchParams({dim:val("s-dim")}).toString();
  document.getElementById("s-dim").onchange=loadStats;
  document.getElementById("edit-cancel").onclick=()=>document.getElementById("modal-edit").classList.remove("show");
  document.getElementById("edit-save").onclick=saveEdit;
  document.getElementById("e-level").onchange=updateCatRequired;
  document.getElementById("imp-cancel").onclick=()=>document.getElementById("modal-import").classList.remove("show");
  document.getElementById("imp-save").onclick=doImport;
  document.getElementById("btn-cfg-save").onclick=saveCfg;document.getElementById("btn-cfg-add").onclick=()=>{["c-name","c-weight","c-pass","c-note"].forEach(x=>document.getElementById(x).value="");document.getElementById("c-weight").value=10;document.getElementById("c-pass").value=0;document.getElementById("modal-cfg").classList.add("show");};
  document.getElementById("cfg-cancel").onclick=()=>document.getElementById("modal-cfg").classList.remove("show");document.getElementById("cfg-save").onclick=addCfg;
  document.getElementById("btn-e-import").onclick=()=>openRImport("edit");
  document.getElementById("sysver").onclick=()=>showPage("system");
  const sysLoginBtn=document.getElementById("sys-login-btn");
  if(sysLoginBtn) sysLoginBtn.onclick=()=>document.getElementById("modal-login").classList.add("show");
  bindInbox();
  document.getElementById("btn-e-add").onclick=()=>openRec(null,"edit");
  document.getElementById("btn-v-import").onclick=()=>openRImport("review");
  document.getElementById("btn-v-add").onclick=()=>openRec(null,"review");
  document.getElementById("btn-o-import").onclick=()=>openRImport("official");
  document.getElementById("btn-o-add").onclick=()=>openRec(null,"official");
  document.getElementById("rec-cancel").onclick=()=>document.getElementById("modal-rec").classList.remove("show");document.getElementById("rec-save").onclick=saveRec;
  document.getElementById("ri-cancel").onclick=()=>document.getElementById("modal-rimport").classList.remove("show");
  document.getElementById("ri-preview").onclick=()=>importAssessCSV(true);
  document.getElementById("ri-save").onclick=()=>importAssessCSV(false);
  const riFile=document.getElementById("ri-file");
  const riLabel=document.getElementById("ri-file-label");
  if(riFile)riFile.onchange=()=>{if(riFile.files&&riFile.files[0])_setFileName(riFile.files[0].name);};
  if(riLabel){
    ["dragenter","dragover"].forEach(ev=>riLabel.addEventListener(ev,e=>{e.preventDefault();e.stopPropagation();riLabel.classList.add("dragover");}));
    ["dragleave","drop"].forEach(ev=>riLabel.addEventListener(ev,e=>{e.preventDefault();e.stopPropagation();riLabel.classList.remove("dragover");}));
    riLabel.addEventListener("drop",e=>{const f=e.dataTransfer.files&&e.dataTransfer.files[0]; if(f){riFile.files=e.dataTransfer.files; _setFileName(f.name);}});
  }
  document.getElementById("acct-cancel").onclick=()=>document.getElementById("modal-acct").classList.remove("show");document.getElementById("acct-save").onclick=saveAcct;
  document.getElementById("cat-cancel").onclick=()=>document.getElementById("modal-cat").classList.remove("show");document.getElementById("cat-save").onclick=saveCat;
  document.getElementById("btn-cat-add").onclick=()=>openCatModal(null);
  document.getElementById("btn-exempt-add").onclick=openExemptModal;
  document.getElementById("ex-cancel").onclick=()=>document.getElementById("modal-exempt").classList.remove("show");document.getElementById("ex-save").onclick=saveExempt;
  document.getElementById("btn-s-export").onclick=()=>window.location.href="/api/export?period="+encodeURIComponent(val("s-period"));
  // 申请管理
  document.getElementById("btn-ap-add").onclick=()=>openApply(null);
  document.getElementById("btn-ap-query").onclick=loadApplys;
  document.getElementById("ap-keyword").oninput=debounce(loadApplys,300);
  document.getElementById("ap-node").onchange=loadApplys;
  document.getElementById("ap-result").onchange=loadApplys;
  document.getElementById("rg-cancel").onclick=()=>document.getElementById("modal-apply").classList.remove("show");document.getElementById("rg-save").onclick=saveApply;
  document.getElementById("rg-submit-eval").onclick=submitEvalApply;
  // 特色词条链接：只读视图与编辑视图统一「打开」（事件委托，兼容动态生成）
  document.addEventListener("click",e=>{
    const openBtn=e.target.closest(".fr-open");
    if(openBtn){
      const row=openBtn.closest(".feat-row");
      let link="";
      if(row){
        const inp=row.querySelector(".fr-link");
        if(inp){link=inp.value.trim();}
        else{const a=row.querySelector(".fr-link-a"); if(a){link=(a.getAttribute("href")||"").trim();}}
      }
      if(!link) link=(openBtn.getAttribute("data-link")||"").trim();
      if(!link){showToast("链接为空，无法打开","warn");return;}
      window.open(link,"_blank","noopener");return;
    }
  });
  document.getElementById("ev-cancel").onclick=()=>document.getElementById("modal-eval").classList.remove("show");document.getElementById("ev-save").onclick=saveEval;
  document.getElementById("ev-authorize").onclick=submitAuthorize;
  document.getElementById("btn-ap-export").onclick=()=>window.location.href="/api/export-reg";
  const rgFile=document.getElementById("rg-screenshot");
  const rgLabel=document.getElementById("rg-screenshot-label");
  if(rgFile){
    rgFile.onchange=async()=>{const f=rgFile.files[0];const nm=document.getElementById("rg-screenshot-name");if(nm)nm.textContent=f?f.name:"点击选择图片，或拖拽文件到此处";if(rgLabel)rgLabel.classList.toggle("has-file",!!f);if(f)await uploadRegScreenshot(rgFile);};
  }
  if(rgLabel&&rgFile){
    ["dragenter","dragover"].forEach(ev=>rgLabel.addEventListener(ev,e=>{e.preventDefault();e.stopPropagation();rgLabel.classList.add("dragover");}));
    ["dragleave","drop"].forEach(ev=>rgLabel.addEventListener(ev,e=>{e.preventDefault();e.stopPropagation();rgLabel.classList.remove("dragover");}));
    rgLabel.addEventListener("drop",e=>{const f=e.dataTransfer.files&&e.dataTransfer.files[0];if(f){rgFile.files=e.dataTransfer.files;rgFile.dispatchEvent(new Event("change"));}});
  }
  // 申请管理（合并所有申请流）
  document.querySelectorAll("#page-apply .subtab").forEach(b=>b.onclick=()=>showApplySub(b.dataset.apply));
  // 制度文档流程图预览
  document.querySelectorAll(".sys-flow-item").forEach(b=>b.onclick=()=>openFlowPreview(b.dataset.flow));
  document.getElementById("flow-close").onclick=()=>document.getElementById("modal-flow").classList.remove("show");
  // 申请/名单管理
  document.getElementById("btn-up-apply-add").onclick=()=>openUp("apply",null);
  document.getElementById("btn-up-expand-add").onclick=()=>openUp("expand",null);
  document.getElementById("btn-up-official-add").onclick=()=>openOfficialPackage(null);
  document.getElementById("official-kw").oninput=debounce(loadOfficialPackages,300);
  document.getElementById("off-cancel").onclick=()=>document.getElementById("modal-official").classList.remove("show");
  document.getElementById("off-save").onclick=saveOfficialPackage;
  document.getElementById("up-cancel").onclick=()=>document.getElementById("modal-up").classList.remove("show");document.getElementById("up-save").onclick=saveUp;
  document.getElementById("upe-cancel").onclick=()=>document.getElementById("modal-up-eval").classList.remove("show");document.getElementById("upe-save").onclick=saveUpEval;
  document.getElementById("upe-withdraw").onclick=()=>withdrawUpEval(upEvalRole);document.getElementById("upe-publish").onclick=publishUpEval;
  document.getElementById("upacc-cancel").onclick=()=>document.getElementById("modal-up-accept").classList.remove("show");document.getElementById("upacc-save").onclick=submitUpAccept;
  document.getElementById("updec-cancel").onclick=()=>document.getElementById("modal-up-decline").classList.remove("show");document.getElementById("updec-save").onclick=submitUpDecline;
  // 纪律与转正
  document.querySelectorAll("#page-discipline .subtab").forEach(b=>b.onclick=()=>showDiscSub(b.dataset.disc));
  document.getElementById("btn-vio-add").onclick=()=>openVio(null);
  document.getElementById("vio-cancel").onclick=()=>document.getElementById("modal-vio").classList.remove("show");
  document.getElementById("vio-save").onclick=saveVio;
  // 管理员管理筛选（仅超级管理员）
  const amFilter=document.getElementById("btn-am-filter");
  if(amFilter)amFilter.onclick=loadAdminMgmt;
  const amReset=document.getElementById("btn-am-reset");
  if(amReset)amReset.onclick=()=>{document.getElementById("am-filter-kw").value="";document.getElementById("am-filter-role").value="";document.getElementById("am-filter-official").value="";refreshCustomSelect("am-filter-role");refreshCustomSelect("am-filter-official");loadAdminMgmt();};
  // 新建账号（仅超级管理员）
  const naBtn=document.getElementById("btn-new-account");
  if(naBtn)naBtn.onclick=()=>{
    ["na-account","na-name","na-pw"].forEach(id=>document.getElementById(id).value="");
    document.getElementById("na-level").value="中审";
    document.getElementById("na-official").checked=false;
    document.getElementById("na-admin").checked=true;
    document.getElementById("modal-new-account").classList.add("show");
  };
  const naOfficial=document.getElementById("na-official");
  if(naOfficial)naOfficial.onchange=()=>{ if(naOfficial.checked) document.getElementById("na-admin").checked=true; };
  const naCancel=document.getElementById("na-cancel");
  if(naCancel)naCancel.onclick=()=>document.getElementById("modal-new-account").classList.remove("show");
  const naSave=document.getElementById("na-save");
  if(naSave)naSave.onclick=createAccount;
  document.getElementById("am-scope-cancel").onclick=()=>{amPending=null;document.getElementById("modal-am-scope").classList.remove("show");};
  document.getElementById("am-scope-ok").onclick=async()=>{
    if(!amPending)return;
    const scope=val("am-scope-pick");
    if(!scope){await UI.alert("请选择管辖范围");return;}
    const p=amPending;amPending=null;
    document.getElementById("modal-am-scope").classList.remove("show");
    await amGrant(p.target,p.role,scope);
  };
  // 评审角色绑定（仅超级管理员）
  const erAdd=document.getElementById("btn-er-add");
  if(erAdd)erAdd.onclick=async()=>{
    const role=val("er-role");const account=val("er-account").trim();const category=val("er-category").trim();
    if(!account){await UI.alert("请填写人员账号");return;}
    const res=await API("/api/eval-role-assigns",{method:"POST",headers:j(),body:JSON.stringify({role,account_id:account,category})});
    if(res.error){await UI.alert("添加失败："+res.error);return;}
    document.getElementById("er-account").value="";loadEvalRoleAssigns();showToast("已添加角色绑定","ok");
  };
  const erBody=document.getElementById("er-body");
  if(erBody)erBody.addEventListener("click",async e=>{
    const btn=e.target.closest("[data-er]");if(!btn)return;
    const id=btn.getAttribute("data-er");
    const res=await API("/api/eval-role-assigns/"+id,{method:"DELETE",headers:j()});
    if(res.error){await UI.alert("解除失败："+res.error);return;}
    loadEvalRoleAssigns();showToast("已解除绑定","ok");
  });
  document.getElementById("vio-penalty").onchange=toggleVioTerm;
  document.getElementById("btn-appeal-add").onclick=()=>openAppeal(null);
  document.getElementById("ap-cancel").onclick=()=>document.getElementById("modal-appeal").classList.remove("show");
  document.getElementById("ap-save").onclick=saveAppeal;
  document.getElementById("liab-status").onchange=loadLiabilities;
  document.querySelectorAll('#disc-stats [data-vstat]').forEach(b=>b.onclick=()=>{document.querySelectorAll('#disc-stats [data-vstat]').forEach(x=>x.classList.remove('active'));b.classList.add('active');loadViolationStats(b.dataset.vstat);});
  document.getElementById("spot-add").onclick=()=>{["sp-period","sp-account","sp-category","sp-total","sp-sampled","sp-problem","sp-checker","sp-handling","sp-note","sp-recuser","sp-recuse-reason"].forEach(x=>document.getElementById(x).value="");document.getElementById("sp-official").checked=false;document.getElementById("sp-recused").checked=false;document.getElementById("sp-level").value="";document.getElementById("sp-recuse-hint").style.display="none";document.getElementById("sp-period").value=new Date().toISOString().slice(0,7);document.getElementById("modal-spot").classList.add("show");};
  document.getElementById("sp-cancel").onclick=()=>document.getElementById("modal-spot").classList.remove("show");
  document.getElementById("sp-account").onchange=()=>refreshRecuseHint("sp-account","sp-checker","sp-recuse-hint");
  document.getElementById("sp-checker").onchange=()=>refreshRecuseHint("sp-account","sp-checker","sp-recuse-hint");
  document.getElementById("sp-save").onclick=async()=>{
    if(!val("sp-period")||!val("sp-account")){await UI.alert("期间与被抽查账号必填");return;}
    const body={period:val("sp-period"),account_id:val("sp-account"),category:val("sp-category"),
      total_versions:+val("sp-total"),sampled:+val("sp-sampled"),problem_versions:+val("sp-problem"),
      level:val("sp-level"),checker:val("sp-checker"),handling:val("sp-handling"),
      is_official:document.getElementById("sp-official").checked,
      recused:document.getElementById("sp-recused").checked,recuser:val("sp-recuser"),recuse_reason:val("sp-recuse-reason"),
      note:val("sp-note"),
      operator:(ME&&ME.account_id)||"系统"};
    const res=await fetch("/api/spot-checks",{method:"POST",headers:j(),body:JSON.stringify(body)}).then(x=>x.json());
    if(res.error){await UI.alert("保存失败："+res.error);return;}
    document.getElementById("modal-spot").classList.remove("show");loadSpotChecks();};
  document.getElementById("spot-period").onchange=loadSpotChecks;
  document.getElementById("spot-account").onchange=loadSpotChecks;
  document.getElementById("rein-add").onclick=()=>{["rn-account","rn-category","rn-ov","rn-mv","rn-acc","rn-owner","rn-note"].forEach(x=>document.getElementById(x).value="");document.getElementById("rn-level").value="初审";document.getElementById("modal-rein").classList.add("show");};
  document.getElementById("rn-cancel").onclick=()=>document.getElementById("modal-rein").classList.remove("show");
  document.getElementById("rn-save").onclick=async()=>{
    if(!val("rn-account")){await UI.alert("申请人账号必填");return;}
    const res=await fetch("/api/reinstate",{method:"POST",headers:j(),body:JSON.stringify({
      account_id:val("rn-account"),category:val("rn-category"),target_level:val("rn-level"),
      official_versions:+val("rn-ov"),main_cat_versions:+val("rn-mv"),accuracy:+val("rn-acc"),
      owner:val("rn-owner"),note:val("rn-note"),operator:(ME&&ME.account_id)||"系统"})}).then(x=>x.json());
    if(res.error){await UI.alert("提交失败："+res.error);return;}
    document.getElementById("modal-rein").classList.remove("show");loadReinstate();};
  document.getElementById("rein-status").onchange=loadReinstate;
  document.getElementById("under-months").onchange=loadUnderperform;
  // 指南复训（制度 6.6）
  document.getElementById("retrain-add").onclick=()=>openRetrain(null);
  document.getElementById("retrain-status").onchange=loadRetrain;
  document.getElementById("rt-cancel").onclick=()=>document.getElementById("modal-retrain").classList.remove("show");
  document.getElementById("rt-save").onclick=saveRetrain;
  // 连续未达标确认式降级（制度 6.1）
  document.getElementById("ue-cancel").onclick=()=>document.getElementById("modal-underexec").classList.remove("show");
  document.getElementById("ue-save").onclick=execUnder;
  // 登录
  document.getElementById("lg-submit").onclick=doLogin;document.getElementById("lg-cancel").onclick=()=>document.getElementById("modal-login").classList.remove("show");
  const lgForgot=document.getElementById("lg-forgot");
  if(lgForgot)lgForgot.onclick=()=>{
    document.getElementById("modal-login").classList.remove("show");
    document.getElementById("pr-account").value="";document.getElementById("pr-contact").value="";
    const m=document.getElementById("pr-msg");m.style.display="none";
    document.getElementById("modal-pwdreset").classList.add("show");
    document.getElementById("pr-account").focus();
  };
  const prCancel=document.getElementById("pr-cancel");
  if(prCancel)prCancel.onclick=()=>document.getElementById("modal-pwdreset").classList.remove("show");
  const prSubmit=document.getElementById("pr-submit");
  if(prSubmit)prSubmit.onclick=async()=>{
    const acc=document.getElementById("pr-account").value.trim();
    const contact=document.getElementById("pr-contact").value.trim();
    const m=document.getElementById("pr-msg");m.style.display="block";
    if(!acc){m.textContent="请填写账号（百科ID）";m.style.color="var(--bad)";return;}
    const res=await fetch("/api/password-reset-request",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({account_id:acc,contact})}).then(r=>r.json()).catch(e=>({error:e.message}));
    if(res.error){m.textContent="提交失败："+res.error;m.style.color="var(--bad)";return;}
    m.textContent=res.message||"申请已提交，请等待管理员处理";m.style.color="var(--ok)";
    setTimeout(()=>{document.getElementById("modal-pwdreset").classList.remove("show");},2500);
  };
  document.getElementById("lg-pwd").addEventListener("keydown",e=>{if(e.key==="Enter")doLogin();});
  document.getElementById("lg-account").addEventListener("keydown",e=>{if(e.key==="Enter")document.getElementById("lg-pwd").focus();});
  ["lg-account","lg-pwd"].forEach(id=>document.getElementById(id).addEventListener("input",()=>clearMsg("lg-msg")));
  ["cp-account","cp-old","cp-new","cp-confirm"].forEach(id=>document.getElementById(id).addEventListener("input",()=>clearMsg("cp-msg")));
  ["lg-eye:lg-pwd","cp-eye-old:cp-old","cp-eye-new:cp-new","cp-eye-confirm:cp-confirm"].forEach(s=>{const[p,i]=s.split(":"); toggleEye(p,i);});
  document.getElementById("cp-submit").onclick=doChangePassword;
  document.getElementById("cp-cancel").onclick=closeChangePw;
  document.getElementById("cp-new").addEventListener("input",checkPwStrength);
  document.getElementById("cp-confirm").addEventListener("keydown",e=>{if(e.key==="Enter")doChangePassword();});
  // 数据质量检查（冲突与冗余）筛选与搜索
  document.querySelectorAll("#audit-filter .segbtn").forEach(b=>b.onclick=()=>{
    document.querySelectorAll("#audit-filter .segbtn").forEach(x=>x.classList.remove("active"));
    b.classList.add("active");renderAudit();
  });
  document.getElementById("audit-search").oninput=renderAudit;
}

(async function(){await loadDict();await loadPeriods();bind();await loadMe();showPage("ledger");startReqStarsWatcher();window.addEventListener("resize",()=>{const p=document.querySelector(".navbtn.active")?.dataset.page;if(p==="overview")loadOverview();if(p==="assess"&&document.getElementById("sub-summary").style.display!=="none")loadSummary();});})();
