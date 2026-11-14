"use strict";
(function () {
  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
  const id = (s) => document.getElementById(s);
  let me = null, reportRows = [], walletConfig = null, activeDepositRequest = null, activeDepositData = null;
  const labels = {dashboard:"داشبورد",products:"لیست محصولات",addProduct:"افزودن محصول جدید",aiTokens:"توکن هوش مصنوعی",settings:"تنظیمات",systemSettings:"تنظیمات کلی سیستم",reports:"گزارش‌ها",sites:"سایت‌های پایش‌شده",users:"کاربران",permissions:"نقش‌ها و دسترسی‌ها",coins:"مدیریت توکن"};
  const loaders = {dashboard:loadDashboard,users:loadUsers,permissions:loadPermissions,coins:loadCoins,reports:loadReports,settings:loadSettings,systemSettings:loadSystemSettings,aiTokens:loadWallet};
  const roleName = (r) => ({admin:"مدیر کل",manager:"مدیر",user:"کاربر"})[r] || r || "کاربر";
  const allowed = (k) => !!me && (me.role === "admin" || !!(me.permissions && me.permissions[k] && me.permissions[k].view));
  const canEdit = (k) => !!me && (me.role === "admin" || !!(me.permissions && me.permissions[k] && me.permissions[k].edit));
  const setText = (key, value) => { const n=id(key); if(n) n.textContent = value == null ? "" : String(value); };
  const setHTML = (key, value) => { const n=id(key); if(n) n.innerHTML=value; };
  const dateText = (v, time) => { if(!v) return "—"; const d=new Date(v); return Number.isNaN(d.getTime())?"—":d.toLocaleString("fa-IR",time?{}:{dateStyle:"short"}); };
  function busy(button, state, label) {
    if(!button) return;
    if(state) { if(button.dataset.oldText===undefined) button.dataset.oldText=button.textContent; button.disabled=true; if(label) button.textContent=label; }
    else { button.disabled=false; if(button.dataset.oldText!==undefined) { button.textContent=button.dataset.oldText; delete button.dataset.oldText; } }
  }
  function submenu(force) {
    const box=id("settingsSubnav"), trigger=$('#sideNav a[data-page="settings"]');
    if(!box) return;
    const open=typeof force==="boolean"?force:box.classList.contains("hidden");
    box.classList.toggle("hidden",!open);
    if(trigger) { trigger.setAttribute("aria-expanded",String(open)); trigger.classList.toggle("submenu-open",open); }
  }
  function renderPermissions() {
    id("userSettingsLink")?.classList.toggle("hidden",!allowed("settings"));
    $("#sideNav a[data-page]").forEach(a=>{
      const visible=a.dataset.page==="settings"?allowed("settings"):allowed(a.dataset.page);
      a.classList.toggle("hidden",!visible);
      a.setAttribute("aria-hidden",String(!visible));
      if(visible) a.removeAttribute("tabindex"); else a.tabIndex=-1;
    });
    const box=id("settingsSubnav");
    if(box && !$$("a[data-page]",box).some(a=>!a.classList.contains("hidden"))) submenu(false);
  }
  function showPage(key, updateHash) {
    const target=labels[key] && id(key+"Page") ? key : "dashboard";
    if(target!=="dashboard" && !allowed(target)) { toast("برای مشاهده این بخش دسترسی ندارید."); return; }
    $$(".page-section").forEach(s=>s.classList.toggle("hidden",s.id!==target+"Page"));
    setText("pageTitle",labels[target]);
    $$("#sideNav a[data-page]").forEach(a=>a.classList.toggle("active",a.dataset.page===target || (["users","permissions","systemSettings"].includes(target)&&a.dataset.page==="settings")));
    if(["users","permissions","systemSettings"].includes(target)) submenu(true); else if(target!=="settings") submenu(false);
    if(updateHash!==false && location.hash!=="#"+target) history.replaceState(null,"","#"+target);
    if(loaders[target]) Promise.resolve(loaders[target]()).catch(e=>toast(e.message||"بارگذاری صفحه ناموفق بود."));
  }

  async function refreshFxRate() {
    try {
      const fx=await api.get("/api/fx/rate");
      const value=Number(fx.rate||0);
      if(value>0&&walletConfig&&walletConfig.fx_auto_enabled)walletConfig.usd_irr_rate=value;
      setText("fxRateValue",value>0?money(value):"نرخ در دسترس نیست");
      if(id("depositAmount")&&!activeDepositRequest)updateDepositConversion();
      const status=fx.status==="ok"?"به‌روز":fx.status==="stale"?"قدیمی":fx.status==="manual"?"دستی":fx.status==="error"?"خطا در دریافت":"در انتظار دریافت";
      setText("fxRateStatus",status+(fx.age_seconds!=null?" · "+num(fx.age_seconds)+" ثانیه قبل":""));
      setText("fxRateSource",fx.source||"TGJU");
      if(fx.last_error&&me?.role==="admin")setText("fxRateError",fx.last_error);else setText("fxRateError","");
    } catch(error) {
      setText("fxRateStatus","عدم دریافت وضعیت نرخ");
    }
  }
  async function loadDashboard() {
    setText("dashboardStatus","در حال دریافت اطلاعات...");
    try {
      const d=await api.get("/api/dashboard");
      setText("usersTotal",num(d.users_total)); setText("coinsTotal",num(d.coins_total)); setText("coinsUsed",num(d.coins_used));
      setText("productCount","—"); setText("sitesTotal","—");
      const rows=Array.isArray(d.recent_transactions)?d.recent_transactions:[];
      setHTML("recentTransactions",rows.length?rows.map(t=>"<tr><td>"+esc(t.username)+"</td><td>"+num(t.amount)+"</td><td>"+esc(t.reason)+"</td><td>"+dateText(t.created_at,false)+"</td></tr>").join(""):'<tr><td colspan="4" class="report-empty">هنوز تراکنشی ثبت نشده است.</td></tr>');
      setText("lastUpdated",new Date().toLocaleTimeString("fa-IR",{hour:"2-digit",minute:"2-digit"})); setText("dashboardStatus","اطلاعات با موفقیت به‌روزرسانی شد");
    } catch(e) { setText("dashboardStatus","دریافت اطلاعات ناموفق بود"); setHTML("recentTransactions",'<tr><td colspan="4" class="report-empty">دریافت اطلاعات ناموفق بود: '+esc(e.message)+'</td></tr>'); throw e; }
  }
  function renderReportRows(query) {
    const body=id("reportTransactions"); if(!body) return;
    const q=String(query||"").trim().toLocaleLowerCase("fa");
    const rows=reportRows.filter(t=>[t.username,t.reason,t.amount,t.balance_after].some(v=>String(v??"").toLocaleLowerCase("fa").includes(q)));
    body.innerHTML=rows.length?rows.map(t=>"<tr><td>"+esc(t.username)+"</td><td>"+num(t.amount)+"</td><td>"+num(t.balance_after)+"</td><td>"+esc(t.reason)+"</td><td>"+dateText(t.created_at,true)+"</td></tr>").join(""):'<tr><td colspan="5" class="report-empty">'+(reportRows.length?"موردی با این عبارت پیدا نشد.":"هنوز تراکنشی ثبت نشده است.")+'</td></tr>';
  }
  async function loadReports() {
    if(!allowed("coins")) throw new Error("برای مشاهده گزارش‌ها دسترسی مدیریت توکن لازم است.");
    setText("reportStatus","در حال دریافت...");
    try {
      const rows=await api.get("/api/coins/transactions"); reportRows=Array.isArray(rows)?rows:[];
      setText("reportCount",num(reportRows.length));
      setText("reportPositive",num(reportRows.filter(x=>Number(x.amount)>0).reduce((s,x)=>s+Number(x.amount),0)));
      setText("reportNegative",num(Math.abs(reportRows.filter(x=>Number(x.amount)<0).reduce((s,x)=>s+Number(x.amount),0))));
      setText("reportLatest",dateText(reportRows[0]?.created_at,false));
      renderReportRows(id("reportSearch")?.value||""); setText("reportStatus",reportRows.length+" رکورد دریافت شد");
    } catch(e) { setText("reportStatus","دریافت اطلاعات ناموفق بود"); setHTML("reportTransactions",'<tr><td colspan="5" class="report-empty">گزارش از سرور دریافت نشد: '+esc(e.message)+'</td></tr>'); throw e; }
  }
  async function loadUsers() {
    const rows=await api.get("/api/users"), list=Array.isArray(rows)?rows:[];
    id("addUserBtn")?.classList.toggle("hidden",!canEdit("users"));
    setHTML("usersTable",list.length?list.map(u=>"<tr><td>"+esc(u.full_name)+"</td><td>"+esc(u.username)+"</td><td>"+roleName(u.role)+"</td><td>"+(u.is_active?"فعال":"غیرفعال")+"</td><td>"+num(u.coin_balance)+"</td></tr>").join(""):'<tr><td colspan="5" class="report-empty">کاربری ثبت نشده است.</td></tr>');
    const select=id("coinUser");
    if(select) select.innerHTML='<option value="">انتخاب کاربر</option>'+list.map(u=>'<option value="'+Number(u.id)+'">'+esc(u.full_name)+' ('+esc(u.username)+')</option>').join("");
  }
  async function loadPermissions(userId) {
    const query=userId?"?user_id="+encodeURIComponent(userId):"";
    const data=await api.get("/api/permissions"+query), box=id("permissionsContent"); if(!box) return;
    const users=data.users||[], selected=String(data.selected_user_id||"");
    let selector=id("permissionUserSelect");
    if(selector){
      selector.innerHTML=users.map(u=>'<option value="'+Number(u.id)+'">'+esc(u.full_name||u.username)+' ('+esc(u.username)+')</option>').join("");
      selector.value=selected;
      selector.disabled=!canEdit("permissions")||!users.length;
    }
    if(!selected){box.innerHTML='<p class="report-empty">ابتدا یک کاربر ایجاد کنید تا دسترسی اختصاصی او را تنظیم کنید.</p>';return;}
    const perms=data.permissions||{};
    box.innerHTML=Object.entries(data.pages||{}).map(([key,title])=>{
      const p=perms[key]||{view:false,edit:false};
      return '<div class="permission-row"><span>'+esc(title)+'</span><label><input type="checkbox" data-page="'+esc(key)+'" data-kind="view" '+(p.view?"checked":"")+'> مشاهده</label><label><input type="checkbox" data-page="'+esc(key)+'" data-kind="edit" '+(p.edit?"checked":"")+'> ویرایش</label></div>';
    }).join("");
    $("input[type=checkbox]",box).forEach(input=>{
      input.disabled=!canEdit("permissions");
      input.addEventListener("change",async()=>{
        const selector='[data-page="'+CSS.escape(input.dataset.page)+'"]';
        const view=box.querySelector('input[data-kind="view"]'+selector), edit=box.querySelector('input[data-kind="edit"]'+selector);
        if(edit.checked)view.checked=true;
        if(input.dataset.kind==="view"&&!view.checked)edit.checked=false;
        try{
          await api.put("/api/permissions",{user_id:Number(selected),page_key:input.dataset.page,can_view:view.checked,can_edit:edit.checked});
          toast("دسترسی اختصاصی کاربر ذخیره شد.");
        }catch(e){toast(e.message);await loadPermissions(selected);}
      });
    });
  }
  async function loadCoins() {
    id("coinForm")?.classList.toggle("hidden",!canEdit("coins"));
    const rows=await api.get("/api/coins/transactions"), list=Array.isArray(rows)?rows:[];
    setHTML("coinsTable",list.length?list.map(t=>"<tr><td>"+esc(t.username)+"</td><td>"+num(t.amount)+"</td><td>"+num(t.balance_after)+"</td><td>"+esc(t.reason)+"</td><td>"+dateText(t.created_at,true)+"</td></tr>").join(""):'<tr><td colspan="5" class="report-empty">تراکنشی ثبت نشده است.</td></tr>');
  }
  async function loadSettings() {
    $$("[data-settings-target]").forEach(b=>{const visible=allowed(b.dataset.settingsTarget); b.classList.toggle("hidden",!visible); b.disabled=!visible; b.onclick=()=>showPage(b.dataset.settingsTarget);});
  }
  async function loadSystemSettings() {
    const d=await api.get("/api/system/config"), form=id("systemConfigForm"); if(!form) return;
    Object.keys(d||{}).forEach(k=>{if(form.elements[k]) form.elements[k].value=d[k];});
    form.querySelectorAll("input,select,button").forEach(el=>el.disabled=!canEdit("systemSettings"));
  }
  const money=(v,c)=>{const n=Number(v||0);return (Number.isFinite(n)?n:0).toLocaleString("en-US",{maximumFractionDigits:2})+(c==="USD"?" $":" ریال");};
  function showBankCard() {
    if(!walletConfig||!walletConfig.card_number) return;
    setText("paymentBankName",walletConfig.bank_name||"بانک"); setText("paymentCardNumber",walletConfig.card_number);
    setText("paymentCardHolder",walletConfig.card_holder||"صاحب کارت"); setText("paymentIban",walletConfig.iban?"شبا: "+walletConfig.iban:"");
    setText("paymentBankDescription",walletConfig.bank_description||"پس از کارت‌به‌کارت، فیش پرداخت را ارسال کنید.");
    const amount=Number(id("depositAmount")?.value||0), currency=id("depositCurrency")?.value||"IRR", rate=Number(walletConfig.usd_irr_rate||0);
    const base=Number(activeDepositData?.amount_irr??(currency==="USD"?amount*rate:amount));
    const fee=Number(activeDepositData?.fee_irr??(currency==="USD"?base*Number(walletConfig.exchange_fee_percent||0)/100:0));
    const total=Number(activeDepositData?.total_payable_irr??(base+fee));
    setText("paymentAmountDue","اصل مبلغ: "+money(base)+" | کارمزد صراف ("+Number(activeDepositData?.fee_percent??walletConfig.exchange_fee_percent??0.5)+"٪): "+money(fee)+" | مبلغ نهایی قابل پرداخت: "+money(total));
    id("bankPaymentPanel")?.classList.remove("hidden");
  }
  function updateDepositConversion() {
    const amount=Number(id("depositAmount")?.value||0), currency=id("depositCurrency")?.value||"IRR", rate=Number(walletConfig?.usd_irr_rate||0);
    if(id("depositConverted")) id("depositConverted").value=amount>0?(rate>0?money(currency==="IRR"?amount/rate:amount*rate,currency==="IRR"?"USD":"IRR"):"نرخ تبدیل توسط مدیر تنظیم نشده"):"";
    if(amount>0&&walletConfig?.card_number) { showBankCard(); id("paymentDoneBtn")?.classList.remove("hidden"); if(id("paymentDoneBtn")) id("paymentDoneBtn").disabled=!activeDepositRequest; }
    else if(!activeDepositRequest) id("bankPaymentPanel")?.classList.add("hidden");
  }
  const walletStatus=s=>({awaiting_payment:"در انتظار پرداخت",pending:"در انتظار تأیید",approved:"تأیید شد",rejected:"رد شد",withdrawal_pending:"در انتظار بررسی",withdrawal_approved:"برداشت تأیید شد",withdrawal_rejected:"برداشت رد شد"})[s]||s||"—";
  async function loadWalletTables() {
    const admin=me?.role==="admin";
    const results=await Promise.all([api.get("/api/wallet/requests"),admin?api.get("/api/wallet/withdrawals"):Promise.resolve([])]);
    const requests=Array.isArray(results[0])?results[0]:[], withdrawals=Array.isArray(results[1])?results[1]:[];
    id("withdrawalReviewPanel")?.classList.toggle("hidden",!admin);
    setHTML("withdrawalRequestsList",withdrawals.length?withdrawals.map(x=>'<article class="withdrawal-request-card"><div><b>'+esc(x.username)+'</b><small>'+dateText(x.created_at,true)+'</small></div><strong>'+money(x.amount_irr)+'</strong><p>'+esc(x.description)+'</p><span>'+walletStatus(x.status)+'</span>'+(x.status==="withdrawal_pending"?'<div class="withdrawal-request-actions"><button class="btn btn-primary withdrawal-approve" data-id="'+Number(x.id)+'" type="button">تأیید برداشت</button><button class="btn btn-soft withdrawal-reject" data-id="'+Number(x.id)+'" type="button">رد درخواست</button></div>':"")+'</article>').join(""):'<p class="report-empty">درخواست برداشتی برای بررسی وجود ندارد.</p>');
    setHTML("depositRequestsTable",requests.length?requests.map(x=>{
      const own=Number(x.user_id)===Number(me.id);
      const actions=admin&&x.status==="pending"?'<button class="btn btn-primary deposit-approve" data-id="'+Number(x.id)+'" type="button">تأیید</button> <button class="btn btn-soft deposit-reject" data-id="'+Number(x.id)+'" type="button">رد</button>':(x.status==="awaiting_payment"&&own?'<button class="btn btn-soft continue-deposit" data-id="'+Number(x.id)+'" type="button">ادامه پرداخت</button>':"—");
      return '<tr><td>'+esc(x.full_name||x.username)+'</td><td>'+money(x.entered_amount,x.currency)+'<small class="fee-breakdown">کارمزد: '+money(x.fee_irr||0)+'<br>پرداخت: '+money(x.total_payable_irr??x.amount_irr)+'</small></td><td>'+walletStatus(x.status)+'</td><td>'+(x.proof_filename?'<button class="btn btn-soft proof-view" data-id="'+Number(x.id)+'" type="button">مشاهده فیش</button>':"—")+'</td><td>'+dateText(x.created_at,false)+'</td><td>'+actions+'</td></tr>';
    }).join(""):'<tr><td colspan="6" class="report-empty">درخواستی ثبت نشده است.</td></tr>');
    $$(".continue-deposit").forEach(b=>b.addEventListener("click",()=>{
      const x=requests.find(r=>String(r.id)===b.dataset.id); if(!x) return;
      activeDepositRequest=x.id; activeDepositData={amount_irr:x.amount_irr,amount_usd:x.amount_usd,fee_percent:x.fee_percent,fee_irr:x.fee_irr,total_payable_irr:x.total_payable_irr};
      id("depositAmount").value=x.entered_amount; id("depositCurrency").value=x.currency;
      id("depositAmount").disabled=true; id("depositCurrency").disabled=true; showBankCard();
      id("paymentDoneBtn").classList.remove("hidden"); id("paymentDoneBtn").disabled=false; id("proofUploadForm").classList.add("hidden");
    }));
    $$(".deposit-approve").forEach(b=>b.addEventListener("click",()=>reviewDeposit(b.dataset.id,"approve")));
    $$(".deposit-reject").forEach(b=>b.addEventListener("click",()=>reviewDeposit(b.dataset.id,"reject")));
    $$(".withdrawal-approve").forEach(b=>b.addEventListener("click",()=>reviewWithdrawal(b.dataset.id,"approve")));
    $$(".withdrawal-reject").forEach(b=>b.addEventListener("click",()=>reviewWithdrawal(b.dataset.id,"reject")));
    $$(".proof-view").forEach(b=>b.addEventListener("click",async()=>{
      let popup=null;
      try {
        popup=window.open("about:blank","_blank"); if(!popup) throw new Error("مرورگر بازشدن پنجره جدید را مسدود کرد.");
        const response=await fetch(API_BASE+"/api/wallet/deposit-requests/"+b.dataset.id+"/proof",{headers:{Authorization:"Bearer "+localStorage.getItem("hidary_token")}});
        if(!response.ok) {popup.close(); throw new Error("دریافت فیش ناموفق بود.");}
        const url=URL.createObjectURL(await response.blob()); popup.location.href=url; setTimeout(()=>URL.revokeObjectURL(url),60000);
      } catch(e) { if(popup&&!popup.closed) popup.close(); toast(e.message); }
    }));
  }
  async function reviewDeposit(idValue,action) {
    let reason=""; if(action==="reject") {reason=prompt("علت رد درخواست را وارد کنید:")||""; if(!reason.trim()) return;}
    try {await api.post("/api/wallet/deposit-requests/"+encodeURIComponent(idValue)+"/review",{action,reason});toast("وضعیت درخواست ثبت شد.");await loadWallet();} catch(e){toast(e.message);}
  }
  async function reviewWithdrawal(idValue,action) {
    let reason=""; if(action==="reject") {reason=prompt("علت رد برداشت را وارد کنید:")||""; if(!reason.trim()) return;}
    try {await api.post("/api/wallet/withdrawals/"+encodeURIComponent(idValue)+"/review",{action,reason});toast("وضعیت برداشت ثبت شد.");await loadWallet();} catch(e){toast(e.message);}
  }
  async function loadWallet() {
    const result=await Promise.all([api.get("/api/wallet"),api.get("/api/wallet/config")]), w=result[0]; walletConfig=result[1]||{};
    setText("walletBalanceIrr",money(w.balance_irr)); setText("walletBalanceUsd",Number(w.usd_irr_rate)>0?money(w.balance_usd,"USD"):"نرخ تبدیل تنظیم نشده");
    id("walletConfigPanel")?.classList.toggle("hidden",me.role!=="admin");
    const form=id("walletConfigForm");
    if(form) {
      Object.keys(walletConfig).forEach(k=>{if(form.elements[k])form.elements[k].value=walletConfig[k];});
      form.querySelectorAll("input,select,button").forEach(el=>el.disabled=me.role!=="admin");
      const auto=form.elements.fx_auto_enabled,rateInput=form.elements.usd_irr_rate;
      if(auto)auto.disabled=me.role!=="admin";
      if(rateInput)rateInput.disabled=me.role!=="admin"||!!walletConfig.fx_auto_enabled;
      setText("fxConfigStatus",walletConfig.fx_auto_enabled?"نرخ خودکار از TGJU دریافت می‌شود.":"حالت دستی فعال است؛ نرخ را مدیر تعیین می‌کند.");
      setText("fxConfigLastUpdate",walletConfig.fx_updated_at?"آخرین دریافت: "+dateText(walletConfig.fx_updated_at,true):"هنوز نرخ خودکاری دریافت نشده است.");
    }
    if(!activeDepositRequest) {if(id("depositAmount"))id("depositAmount").disabled=false;if(id("depositCurrency"))id("depositCurrency").disabled=false;}
    updateDepositConversion(); await loadWalletTables();
  }
  function setTheme(dark) {
    document.body.classList.toggle("theme-dark",!!dark);
    const button=id("themeToggle");
    if(button){button.setAttribute("aria-pressed",String(!!dark));button.setAttribute("aria-label",dark?"فعال‌سازی حالت روشن":"فعال‌سازی حالت تیره");button.title=dark?"حالت روشن":"حالت تیره";}
    try{localStorage.setItem("hidary_theme",dark?"dark":"light");}catch(_){}
  }
  function closeUserMenu(){id("userMenu")?.classList.add("hidden");id("userMenuBtn")?.setAttribute("aria-expanded","false");}
  function bindEvents() {
    id("refreshDashboard")?.addEventListener("click",()=>loadDashboard().catch(e=>toast(e.message)));
    id("permissionUserSelect")?.addEventListener("change",e=>loadPermissions(e.target.value).catch(x=>toast(x.message)));
    id("sideNav")?.addEventListener("click",e=>{
      const a=e.target.closest("a[data-page]"); if(!a||!id("sideNav").contains(a))return; e.preventDefault();
      if(a.dataset.page==="settings"){submenu();showPage("settings");return;} showPage(a.dataset.page);
    });
    const search=id("menuSearch"), links=$$("#sideNav a[data-page]");
    const filter=value=>{
      const q=String(value||"").trim().toLocaleLowerCase("fa");
      links.forEach(a=>a.classList.toggle("search-hidden",!!q&&!a.textContent.toLocaleLowerCase("fa").includes(q)));
      if(q) submenu(true);
    };
    search?.addEventListener("input",e=>filter(e.target.value));
    search?.addEventListener("keydown",e=>{
      if(e.key==="Escape"){search.value="";filter("");search.blur();}
      if(e.key==="Enter"){const first=links.find(a=>!a.classList.contains("search-hidden")&&!a.classList.contains("hidden")&&a.dataset.page!=="settings");if(first){showPage(first.dataset.page);search.value="";filter("");search.blur();}}
    });
    id("trendProductNav")?.addEventListener("change",e=>{if(e.target.value==="all")showPage("products");});
    id("productKpiTile")?.addEventListener("click",e=>{e.preventDefault();showPage("products");});
    id("reportSearch")?.addEventListener("input",e=>renderReportRows(e.target.value));
    id("exportTransactions")?.addEventListener("click",()=>{
      if(!reportRows.length){toast("داده‌ای برای خروجی وجود ندارد.");return;}
      const quote=v=>'"'+String(v??"").replace(/"/g,'""')+'"';
      const rows=[["کاربر","مقدار تغییر","موجودی پس از تراکنش","شرح","تاریخ"],...reportRows.map(t=>[t.username,t.amount,t.balance_after,t.reason,dateText(t.created_at,true)])];
      const url=URL.createObjectURL(new Blob(["\uFEFF"+rows.map(r=>r.map(quote).join(",")).join("\r\n")],{type:"text/csv;charset=utf-8"}));
      const a=document.createElement("a");a.href=url;a.download="hidary-transactions.csv";document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
    });
    id("systemConfigForm")?.addEventListener("submit",async e=>{e.preventDefault();try{await api.put("/api/system/config",Object.fromEntries(new FormData(e.currentTarget)));toast("تنظیمات ذخیره شد.");}catch(x){toast(x.message);}});
    id("depositAmount")?.addEventListener("input",updateDepositConversion); id("depositCurrency")?.addEventListener("change",updateDepositConversion);
    id("depositRequestForm")?.addEventListener("submit",async e=>{
      e.preventDefault();const form=e.currentTarget,button=$('button[type="submit"]',form),amount=Number(id("depositAmount").value),currency=id("depositCurrency").value;
      if(!Number.isFinite(amount)||amount<=0){toast("مبلغ معتبر وارد کنید.");return;}
      busy(button,true,"در حال ثبت...");
      try{const d=await api.post("/api/wallet/deposit-requests",{amount,currency});activeDepositRequest=d.id;activeDepositData={...d,currency,entered_amount:amount};id("depositAmount").disabled=true;id("depositCurrency").disabled=true;showBankCard();id("paymentDoneBtn").classList.remove("hidden");id("paymentDoneBtn").disabled=false;id("proofUploadForm").classList.add("hidden");toast("درخواست ثبت شد؛ پس از پرداخت فیش را ارسال کنید.");await loadWalletTables();}
      catch(x){busy(button,false);toast(x.message);}
    });
    id("paymentDoneBtn")?.addEventListener("click",()=>{if(!activeDepositRequest){toast("ابتدا درخواست افزایش موجودی ثبت کنید.");return;}id("proofUploadForm")?.classList.remove("hidden");id("paymentProofFile")?.focus();});
    id("proofUploadForm")?.addEventListener("submit",async e=>{
      e.preventDefault();const form=e.currentTarget,file=id("paymentProofFile").files[0],button=$('button[type="submit"]',form);
      if(!file||!activeDepositRequest){toast("فایل فیش را انتخاب کنید.");return;}if(file.size>5*1024*1024){toast("حجم فایل نباید بیشتر از ۵ مگابایت باشد.");return;}
      const fd=new FormData();fd.append("file",file);busy(button,true,"در حال ارسال...");
      try{await api.post("/api/wallet/deposit-requests/"+activeDepositRequest+"/proof",fd);toast("فیش ارسال شد و برای تأیید مدیر در صف قرار گرفت.");form.reset();form.classList.add("hidden");id("paymentDoneBtn").classList.add("hidden");id("bankPaymentPanel").classList.add("hidden");activeDepositRequest=null;activeDepositData=null;id("depositAmount").disabled=false;id("depositCurrency").disabled=false;const submit=$('#depositRequestForm button[type="submit"]');if(submit)submit.disabled=false;await loadWalletTables();}
      catch(x){busy(button,false);toast(x.message);}
    });
    id("withdrawalForm")?.addEventListener("submit",async e=>{
      e.preventDefault();const form=e.currentTarget,button=$('button[type="submit"]',form),amount=Number(id("withdrawalAmount").value),destination=id("withdrawalDestination").value.trim();
      if(!Number.isFinite(amount)||amount<=0||destination.length<5){toast("مبلغ و شماره مقصد معتبر وارد کنید.");return;}
      busy(button,true,"در حال ثبت...");
      try{await api.post("/api/wallet/withdrawals",{amount_irr:amount,destination});toast("درخواست برداشت ثبت شد.");form.reset();await loadWallet();}
      catch(x){toast(x.message);}finally{busy(button,false);}
    });
    id("walletConfigForm")?.elements.fx_auto_enabled?.addEventListener("change",e=>{
      const rateInput=id("walletConfigForm")?.elements.usd_irr_rate;
      if(rateInput)rateInput.disabled=e.target.value==="true";
    });
    id("walletConfigForm")?.addEventListener("submit",async e=>{
      e.preventDefault();const form=e.currentTarget,button=$('button[type="submit"]',form);busy(button,true,"در حال ذخیره...");
      try{const payload=Object.fromEntries(new FormData(form));payload.fx_auto_enabled=payload.fx_auto_enabled==="true";if(!payload.usd_irr_rate)payload.usd_irr_rate=walletConfig.usd_irr_rate||0;await api.put("/api/wallet/config",payload);toast("تنظیمات نرخ و کارمزد ذخیره شد.");await loadWallet();}
      catch(x){toast(x.message);}finally{busy(button,false);}
    });
    id("logoutBtn")?.addEventListener("click",()=>{try{localStorage.removeItem("hidary_token");}catch(_){}location.replace("/login/");});
    id("userMenuBtn")?.addEventListener("click",()=>{const menu=id("userMenu"),open=menu.classList.toggle("hidden")===false;id("userMenuBtn").setAttribute("aria-expanded",String(open));});
    document.addEventListener("click",e=>{if(!e.target.closest(".profile-menu-wrap"))closeUserMenu();});
    document.addEventListener("keydown",e=>{if(e.key==="Escape"){closeUserMenu();submenu(false);}});
    id("userSettingsLink")?.addEventListener("click",e=>{e.preventDefault();closeUserMenu();showPage("settings");});
    id("themeToggle")?.addEventListener("click",()=>setTheme(!document.body.classList.contains("theme-dark")));
    id("addUserBtn")?.addEventListener("click",()=>id("userForm")?.classList.toggle("hidden"));
    id("userForm")?.addEventListener("submit",async e=>{
      e.preventDefault();const form=e.currentTarget,button=$('button[type="submit"]',form);busy(button,true,"در حال ثبت...");
      try{await api.post("/api/users",Object.fromEntries(new FormData(form)));form.reset();form.classList.add("hidden");toast("کاربر ایجاد شد.");await loadUsers();}
      catch(x){toast(x.message);}finally{busy(button,false);}
    });
    id("coinForm")?.addEventListener("submit",async e=>{
      e.preventDefault();const form=e.currentTarget,data=new FormData(form),button=$('button[type="submit"]',form),user_id=Number(data.get("user_id")),amount=Number(data.get("amount")),reason=String(data.get("reason")||"").trim();
      if(!user_id||!Number.isInteger(amount)||amount===0||reason.length<2){toast("کاربر، مقدار صحیح و علت تراکنش را وارد کنید.");return;}
      busy(button,true,"در حال ثبت...");
      try{await api.post("/api/coins/adjust",{user_id,amount,reason});form.reset();toast("تراکنش ثبت شد.");await Promise.all([loadCoins(),loadUsers(),loadDashboard()]);}
      catch(x){toast(x.message);}finally{busy(button,false);}
    });
  }
  async function init() {
    let storedToken=null;try{storedToken=localStorage.getItem("hidary_token");}catch(_){}
    if(!storedToken){location.replace("/login/");return;}
    bindEvents();let theme="light";try{theme=localStorage.getItem("hidary_theme")||"light";}catch(_){}setTheme(theme==="dark");
    try{
      me=await api.get("/api/auth/me");if(!me||!me.id)throw new Error("اطلاعات حساب کاربری از سرور دریافت نشد.");
      setText("userName",me.full_name||me.username);setText("userRole",roleName(me.role));setText("menuUserName",me.full_name||me.username);setText("menuUserRole",roleName(me.role));setText("todayLabel",new Date().toLocaleDateString("fa-IR"));
      renderPermissions();
      refreshFxRate();
      setInterval(refreshFxRate,25000);
      const requested=location.hash.replace(/^#/,""),initial=labels[requested]&&id(requested+"Page")?requested:"dashboard";
      if(initial==="settings")submenu(true);showPage(initial,false);
    }catch(e){
      // The API client redirects on HTTP 401. Keep valid tokens on network/5xx errors.
      const message=e&&e.message?e.message:"خطا در دریافت اطلاعات حساب کاربری";
      setText("pageTitle","خطا در اتصال به سامانه");
      toast(message);
    }
  }
  if(document.readyState==="loading") document.addEventListener("DOMContentLoaded",init,{once:true}); else init();
})();