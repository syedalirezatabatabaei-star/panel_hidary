import asyncio,json,logging,re,urllib.request
from decimal import Decimal,ROUND_HALF_UP
from fastapi import FastAPI,Depends,HTTPException,UploadFile,File,Request,Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel,Field
from sqlalchemy.orm import Session
from sqlalchemy import func,inspect,text
from .config import settings
from .database import Base,engine,SessionLocal,get_db
from .models import User,PagePermission,UserPagePermission,CoinTransaction,SystemSetting,WalletAccount,WalletRequest,WalletTransaction,SecurityEventLog
from .security import hash_password,verify_password,create_access_token,current_user
from datetime import datetime
app=FastAPI(title="Hidary Admin API",version="1.1.0",docs_url="/docs" if settings.api_docs_enabled else None,redoc_url="/redoc" if settings.api_docs_enabled else None,openapi_url="/openapi.json" if settings.api_docs_enabled else None)
app.add_middleware(CORSMiddleware,allow_origins=settings.allowed_origins,allow_credentials=True,allow_methods=["*"],allow_headers=["*"])
PAGES={"dashboard":"داشبورد","products":"محصولات","addProduct":"افزودن محصول","sites":"سایت‌های پایش‌شده","aiTokens":"توکن هوش مصنوعی","settings":"تنظیمات","systemSettings":"تنظیمات کلی سیستم","reports":"گزارش‌ها","users":"کاربران","permissions":"دسترسی‌ها","coins":"مدیریت توکن"}
DEFAULTS={"admin":{k:(True,True) for k in PAGES},"manager":{"dashboard":(True,False),"users":(True,True),"permissions":(False,False),"coins":(True,True),"reports":(True,False),"aiTokens":(True,False),"settings":(True,False)},"user":{"dashboard":(True,False),"aiTokens":(True,False)}}
def seed():
    Base.metadata.create_all(bind=engine); db=SessionLocal()
    try:
        # Create the bootstrap admin only when it does not exist.
        # Never overwrite an existing password hash on every container restart.
        if not db.query(User).filter_by(username=settings.admin_username).first():
            db.add(User(username=settings.admin_username,full_name=settings.admin_full_name,
                        password_hash=hash_password(settings.admin_password),role="admin"))
        for role,pages in DEFAULTS.items():
            for key,(view,edit) in pages.items():
                p=db.query(PagePermission).filter_by(role=role,page_key=key).first()
                if not p: db.add(PagePermission(role=role,page_key=key,can_view=view,can_edit=edit))
        db.flush()
        # Backfill individual permissions for existing accounts. Existing
        # per-user choices are never overwritten by role defaults.
        for account in db.query(User).filter(User.role!="admin").all():
            role_defaults=DEFAULTS.get(account.role,DEFAULTS["user"])
            for key in PAGES:
                own=db.query(UserPagePermission).filter_by(user_id=account.id,page_key=key).first()
                if not own:
                    view,edit=role_defaults.get(key,(False,False))
                    db.add(UserPagePermission(user_id=account.id,page_key=key,can_view=view,can_edit=edit))
        for key,value in {"fx_auto_enabled":"true","exchange_fee_percent":"0.5","fx_status":"waiting","fx_source":"TGJU","n8n_user_visible_limit":"10"}.items():
            if not db.get(SystemSetting,key): db.add(SystemSetting(key=key,value=value))
        db.commit()
    finally: db.close()

def ensure_wallet_request_columns():
    inspector=inspect(engine)
    if "wallet_requests" not in inspector.get_table_names(): return
    existing={column["name"] for column in inspector.get_columns("wallet_requests")}
    additions={"fee_percent":"DECIMAL(7,4) NOT NULL DEFAULT 0","fee_irr":"DECIMAL(18,2) NOT NULL DEFAULT 0","total_payable_irr":"DECIMAL(18,2) NOT NULL DEFAULT 0"}
    with engine.begin() as connection:
        for name,ddl in additions.items():
            if name not in existing:
                connection.execute(text("ALTER TABLE wallet_requests ADD COLUMN "+name+" "+ddl))

def ensure_user_session_version_column():
    inspector=inspect(engine)
    if "users" not in inspector.get_table_names(): return
    columns={c["name"] for c in inspector.get_columns("users")}
    if "session_version" not in columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE users ADD COLUMN session_version INT NOT NULL DEFAULT 0"))

_fx_task=None
@app.on_event("startup")
async def startup():
    global _fx_task
    seed()
    ensure_wallet_request_columns()
    ensure_user_session_version_column()
    _fx_task=asyncio.create_task(tgju_rate_worker())

@app.on_event("shutdown")
async def shutdown():
    global _fx_task
    if _fx_task:
        _fx_task.cancel()
        try: await _fx_task
        except asyncio.CancelledError: pass
        _fx_task=None
def require_page(page,edit=False):
    def check(user:User=Depends(current_user),db:Session=Depends(get_db)):
        if user.role=="admin": return user
        # An explicit per-user permission takes precedence over the role template.
        p=db.query(UserPagePermission).filter_by(user_id=user.id,page_key=page).first()
        if not p:
            p=db.query(PagePermission).filter_by(role=user.role,page_key=page).first()
        if not p or not p.can_view or (edit and not p.can_edit):
            raise HTTPException(403,"دسترسی کافی ندارید")
        return user
    return check
def audit_event(db:Session,event_type:str,actor:User|None=None,target_user_id:int|None=None,request:Request|None=None,details:dict|None=None):
    ip=request.headers.get("x-real-ip") if request else None
    if not ip and request and request.client: ip=request.client.host
    agent=request.headers.get("user-agent","")[:500] if request else ""
    db.add(SecurityEventLog(event_type=event_type,actor_id=actor.id if actor else None,target_user_id=target_user_id,source_ip=(ip or "")[:64],user_agent=agent,details=json.dumps(details or {},ensure_ascii=False)[:4000]))

class UserCreate(BaseModel):
    username:str=Field(min_length=3,max_length=80); password:str=Field(min_length=8,max_length=128)
    full_name:str=Field(min_length=2,max_length=160); role:str="user"
class UserUpdate(BaseModel):
    full_name:str|None=None; role:str|None=None; is_active:bool|None=None
    password:str|None=Field(default=None,min_length=8,max_length=128)
class PermissionUpdate(BaseModel):
    user_id:int; page_key:str; can_view:bool; can_edit:bool
class CoinChange(BaseModel):
    user_id:int; amount:int; reason:str=Field(min_length=2,max_length=255); reference:str|None=None
@app.get("/api/health")
def health(): return {"status":"ok"}
_DUMMY_PASSWORD_HASH=hash_password("not-a-real-user-password-for-timing-equalization")
@app.post("/api/auth/login")
def login(request:Request,response:Response,form:OAuth2PasswordRequestForm=Depends(),db:Session=Depends(get_db)):
    u=db.query(User).filter_by(username=form.username).first()
    valid=verify_password(form.password,u.password_hash if u else _DUMMY_PASSWORD_HASH)
    if not u or not valid or not u.is_active:
        audit_event(db,"auth.login_failed",target_user_id=u.id if u else None,request=request,details={"username":form.username[:80]})
        db.commit()
        raise HTTPException(401,"نام کاربری یا رمز عبور اشتباه است")
    token=create_access_token(u.id,u.session_version or 0)
    response.set_cookie("hidary_session",token,max_age=settings.access_token_expire_minutes*60,httponly=True,secure=settings.cookie_secure,samesite="strict",path="/")
    audit_event(db,"auth.login_success",actor=u,target_user_id=u.id,request=request)
    db.commit()
    return {"success":True,"token_type":"cookie"}

@app.post("/api/auth/logout")
def logout(response:Response):
    response.delete_cookie("hidary_session",path="/",secure=settings.cookie_secure,httponly=True,samesite="strict")
    return {"success":True}
@app.get("/api/auth/me")
def me(user:User=Depends(current_user),db:Session=Depends(get_db)):
    if user.role=="admin":
        permissions={key:{"view":True,"edit":True} for key in PAGES}
    else:
        ps=db.query(UserPagePermission).filter_by(user_id=user.id).all()
        permissions={p.page_key:{"view":p.can_view,"edit":p.can_edit} for p in ps}
    return {"id":user.id,"username":user.username,"full_name":user.full_name,"role":user.role,"coin_balance":user.coin_balance,"permissions":permissions}
@app.get("/api/dashboard")
def dashboard(user:User=Depends(require_page("dashboard")),db:Session=Depends(get_db)):
    recent=db.query(CoinTransaction).order_by(CoinTransaction.id.desc()).limit(8).all()
    return {"users_total":db.query(func.count(User.id)).scalar() or 0,"users_active":db.query(func.count(User.id)).filter(User.is_active.is_(True)).scalar() or 0,"coins_total":db.query(func.coalesce(func.sum(User.coin_balance),0)).scalar() or 0,"coins_used":db.query(func.coalesce(func.sum(-CoinTransaction.amount),0)).filter(CoinTransaction.amount<0).scalar() or 0,"recent_transactions":[{"id":t.id,"username":t.user.username,"amount":t.amount,"reason":t.reason,"created_at":t.created_at.isoformat()} for t in recent]}
@app.get("/api/users")
def users(user:User=Depends(require_page("users")),db:Session=Depends(get_db)):
    return [{"id":u.id,"username":u.username,"full_name":u.full_name,"role":u.role,"is_active":u.is_active,"coin_balance":u.coin_balance} for u in db.query(User).order_by(User.id.desc()).all()]
@app.post("/api/users",status_code=201)
def create_user(data:UserCreate,request:Request,actor:User=Depends(require_page("users",True)),db:Session=Depends(get_db)):
    if data.role not in DEFAULTS: raise HTTPException(400,"نقش نامعتبر است")
    if data.role=="admin" and actor.role!="admin": raise HTTPException(403,"ایجاد مدیر کل فقط توسط مدیر کل مجاز است")
    if db.query(User).filter_by(username=data.username).first(): raise HTTPException(409,"نام کاربری تکراری است")
    u=User(username=data.username,full_name=data.full_name,role=data.role,password_hash=hash_password(data.password)); db.add(u); db.flush()
    role_defaults=DEFAULTS.get(data.role,DEFAULTS["user"])
    for key in PAGES:
        view,edit=role_defaults.get(key,(False,False))
        db.add(UserPagePermission(user_id=u.id,page_key=key,can_view=view,can_edit=edit))
    db.commit(); db.refresh(u)
    return {"id":u.id,"username":u.username}
@app.patch("/api/users/{uid}")
def update_user(uid:int,data:UserUpdate,request:Request,actor:User=Depends(require_page("users",True)),db:Session=Depends(get_db)):
    u=db.get(User,uid)
    if not u: raise HTTPException(404,"کاربر پیدا نشد")
    if u.role=="admin" and actor.role!="admin": raise HTTPException(403,"مدیر میانی اجازه تغییر حساب مدیر کل را ندارد")
    if data.role is not None:
        if data.role not in DEFAULTS: raise HTTPException(400,"نقش نامعتبر است")
        if data.role=="admin" and actor.role!="admin": raise HTTPException(403,"ارتقای حساب به مدیر کل فقط توسط مدیر کل مجاز است")
        if u.role=="admin" and data.role!="admin": raise HTTPException(403,"تغییر نقش مدیر کل از این مسیر مجاز نیست")
    if u.id==actor.id and data.is_active is False: raise HTTPException(400,"نمی‌توانید حساب خود را غیرفعال کنید")
    role_changed=data.role is not None and data.role!=u.role
    revoke=role_changed or bool(data.password) or (data.is_active is not None and data.is_active!=u.is_active)
    if role_changed:
        u.role=data.role
        db.query(UserPagePermission).filter_by(user_id=u.id).delete(synchronize_session=False)
        if u.role!="admin":
            defaults=DEFAULTS.get(u.role,DEFAULTS["user"])
            for key in PAGES:
                view,edit=defaults.get(key,(False,False))
                db.add(UserPagePermission(user_id=u.id,page_key=key,can_view=view,can_edit=edit))
    if data.full_name is not None: u.full_name=data.full_name
    if data.is_active is not None: u.is_active=data.is_active
    if data.password: u.password_hash=hash_password(data.password)
    if revoke: u.session_version=(u.session_version or 0)+1
    audit_event(db,"user.updated",actor=actor,target_user_id=u.id,request=request,details={"role":u.role,"role_changed":role_changed,"password_changed":bool(data.password),"active":u.is_active})
    db.commit()
    return {"success":True,"sessions_revoked":revoke}
@app.get("/api/permissions")
def permissions(user_id:int|None=None,actor:User=Depends(current_user),db:Session=Depends(get_db)):
    if actor.role!="admin": raise HTTPException(403,"فقط مدیر کل می‌تواند دسترسی کاربران را مدیریت کند")
    accounts=db.query(User).filter(User.role!="admin").order_by(User.id.asc()).all()
    selected=db.get(User,user_id) if user_id else (accounts[0] if accounts else None)
    if selected and selected.role=="admin": raise HTTPException(400,"دسترسی مدیر کل قابل تغییر نیست")
    rows=db.query(UserPagePermission).filter_by(user_id=selected.id).all() if selected else []
    permissions={p.page_key:{"view":p.can_view,"edit":p.can_edit} for p in rows}
    return {"pages":PAGES,"users":[{"id":u.id,"username":u.username,"full_name":u.full_name,"role":u.role} for u in accounts],
            "selected_user_id":selected.id if selected else None,"permissions":permissions}
@app.put("/api/permissions")
def set_permission(data:PermissionUpdate,actor:User=Depends(current_user),db:Session=Depends(get_db)):
    if actor.role!="admin": raise HTTPException(403,"فقط مدیر کل می‌تواند دسترسی کاربران را مدیریت کند")
    if data.page_key not in PAGES: raise HTTPException(400,"صفحه نامعتبر است")
    target=db.get(User,data.user_id)
    if not target or target.role=="admin": raise HTTPException(404,"کاربر قابل ویرایش پیدا نشد")
    if data.can_edit and not data.can_view: raise HTTPException(400,"ویرایش بدون مشاهده مجاز نیست")
    p=db.query(UserPagePermission).filter_by(user_id=target.id,page_key=data.page_key).first()
    if not p:
        p=UserPagePermission(user_id=target.id,page_key=data.page_key);db.add(p)
    p.can_view=data.can_view;p.can_edit=data.can_edit;db.commit();return {"success":True}
@app.get("/api/coins/transactions")
def transactions(user_id:int|None=None,actor:User=Depends(require_page("coins")),db:Session=Depends(get_db)):
    q=db.query(CoinTransaction).order_by(CoinTransaction.id.desc())
    if user_id: q=q.filter(CoinTransaction.user_id==user_id)
    return [{"id":t.id,"user_id":t.user_id,"username":t.user.username,"amount":t.amount,"balance_after":t.balance_after,"reason":t.reason,"created_at":t.created_at.isoformat()} for t in q.limit(200).all()]
@app.post("/api/coins/adjust")
def adjust(data:CoinChange,actor:User=Depends(require_page("coins",True)),db:Session=Depends(get_db)):
    if data.amount==0: raise HTTPException(400,"مقدار نمی‌تواند صفر باشد")
    try:
        u=db.query(User).filter(User.id==data.user_id).with_for_update().one_or_none()
        if not u: raise HTTPException(404,"کاربر پیدا نشد")
        balance=u.coin_balance+data.amount
        if balance<0: raise HTTPException(400,"موجودی کافی نیست")
        u.coin_balance=balance
        db.add(CoinTransaction(user_id=u.id,actor_id=actor.id,amount=data.amount,balance_after=balance,reason=data.reason,reference=data.reference))
        db.commit(); return {"success":True,"balance":balance}
    except Exception: db.rollback(); raise


# Wallet and system configuration
def setting(db, key, default=""):
    row=db.get(SystemSetting,key)
    return row.value if row else default

def set_setting(db,key,value):
    row=db.get(SystemSetting,key)
    if not row: row=SystemSetting(key=key,value=str(value)); db.add(row)
    else: row.value=str(value)

def _digits_to_ascii(value):
    table=str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩","01234567890123456789")
    return str(value).translate(table)

def _parse_rate_value(value):
    cleaned=re.sub(r"[^0-9.]","",_digits_to_ascii(value or ""))
    rate=Decimal(cleaned) if cleaned else Decimal("0")
    if rate<100000 or rate>1000000000:
        raise ValueError("TGJU returned an implausible USD/IRR rate")
    return rate

def fetch_tgju_rate():
    headers={"User-Agent":"Mozilla/5.0 (compatible; HidaryRateBot/1.0)","Accept":"application/json,text/html"}
    request=urllib.request.Request("https://call1.tgju.org/ajax.json",headers=headers)
    try:
        with urllib.request.urlopen(request,timeout=12) as response:
            payload=json.loads(response.read().decode("utf-8","replace"))
        raw=payload.get("current",{}).get("price_dollar_rl",{}).get("p")
        return _parse_rate_value(raw)
    except Exception as api_error:
        logging.warning("TGJU JSON feed failed: %s",api_error)
    request=urllib.request.Request("https://www.tgju.org/profile/price_dollar_rl",headers=headers)
    with urllib.request.urlopen(request,timeout=12) as response:
        html=response.read().decode("utf-8","replace")
    patterns=[
        r"""id=["']l-price_dollar_rl["'][^>]*>\s*([0-9۰-۹٠-٩,٬.]+)""",
        r'price_dollar_rl.{0,500}?([0-9۰-۹٠-٩][0-9۰-۹٠-٩,٬.]{5,})'
    ]
    for pattern in patterns:
        match=re.search(pattern,html,re.I|re.S)
        if match:
            try: return _parse_rate_value(match.group(1))
            except ValueError: pass
    raise ValueError("Could not extract price_dollar_rl from TGJU")

def update_tgju_rate_once():
    db=SessionLocal()
    try:
        if (setting(db,"fx_auto_enabled","true") or "true").lower() not in ("true","1","yes","on"):
            return None
        market_rate=fetch_tgju_rate()
        # TGJU supplies IRR; 1,000 toman markup equals 10,000 IRR.
        rate=market_rate+Decimal("10000")
        set_setting(db,"usd_irr_rate",str(rate))
        set_setting(db,"fx_market_rate_irr",str(market_rate))
        set_setting(db,"fx_markup_toman","1000")
        set_setting(db,"fx_updated_at",datetime.utcnow().isoformat())
        set_setting(db,"fx_status","ok")
        set_setting(db,"fx_source","TGJU")
        set_setting(db,"fx_last_error","")
        db.commit()
        return rate
    finally: db.close()

async def tgju_rate_worker():
    while True:
        try:
            await asyncio.to_thread(update_tgju_rate_once)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logging.exception("Automatic TGJU rate update failed")
            db=SessionLocal()
            try:
                set_setting(db,"fx_status","error")
                set_setting(db,"fx_last_error",str(error)[:500])
                db.commit()
            finally: db.close()
        await asyncio.sleep(25)

def wallet_for(db,user_id):
    row=db.query(WalletAccount).filter_by(user_id=user_id).with_for_update().one_or_none()
    if not row:
        row=WalletAccount(user_id=user_id,balance_irr=0); db.add(row); db.flush()
    return row

def wallet_admin(user:User=Depends(current_user)):
    if user.role!="admin": raise HTTPException(403,"فقط مدیر کل می‌تواند این عملیات را انجام دهد")
    return user

class WalletRequestInput(BaseModel):
    currency:str
    amount:Decimal=Field(gt=0)
class WalletWithdrawInput(BaseModel):
    amount_irr:Decimal=Field(gt=0)
    destination:str=Field(min_length=5,max_length=160)
class WalletReviewInput(BaseModel):
    action:str
    reason:str|None=None
class WalletConfigInput(BaseModel):
    usd_irr_rate:Decimal=Field(default=Decimal("0"),ge=0)
    fx_auto_enabled:bool=True
    exchange_fee_percent:Decimal=Field(default=Decimal("0.5"),ge=0,le=100)
    bank_name:str=Field(max_length=120)
    card_holder:str=Field(max_length=160)
    card_number:str=Field(max_length=40)
    iban:str=Field(default="",max_length=40)
    bank_description:str=Field(default="",max_length=500)
class SystemConfigInput(BaseModel):
    site_title:str=Field(min_length=2,max_length=160)
    support_email:str=""
    support_phone:str=""
    default_currency:str="IRR"
    withdrawal_fee_percent:Decimal=Field(default=Decimal("0"),ge=0,le=100)
    n8n_user_visible_limit:int=Field(default=10,ge=1,le=500)

@app.get("/api/wallet")
def wallet_summary(user:User=Depends(current_user),db:Session=Depends(get_db)):
    w=wallet_for(db,user.id)
    db.commit()
    rate=Decimal(setting(db,"usd_irr_rate","0") or "0")
    return {"balance_irr":float(w.balance_irr),"balance_usd":float(w.balance_irr/rate) if rate>0 else 0,"usd_irr_rate":float(rate)}

@app.get("/api/wallet/requests")
def wallet_requests(user:User=Depends(current_user),db:Session=Depends(get_db)):
    q=db.query(WalletRequest).order_by(WalletRequest.id.desc())
    if user.role!="admin": q=q.filter(WalletRequest.user_id==user.id)
    return [{"id":x.id,"user_id":x.user_id,"username":x.user.username,"full_name":x.user.full_name,
      "currency":x.entered_currency,"entered_amount":float(x.entered_amount),"amount_irr":float(x.amount_irr),
      "amount_usd":float(x.amount_usd),"fee_percent":float(x.fee_percent or 0),"fee_irr":float(x.fee_irr or 0),
      "total_payable_irr":float(x.total_payable_irr or x.amount_irr),"status":x.status,"proof_filename":x.proof_filename,
      "rejection_reason":x.rejection_reason,"created_at":x.created_at.isoformat(),"type":"deposit"} for x in q.all()]

@app.post("/api/wallet/deposit-requests",status_code=201)
def create_wallet_request(data:WalletRequestInput,user:User=Depends(current_user),db:Session=Depends(get_db)):
    currency=data.currency.upper()
    if currency not in ("IRR","USD"): raise HTTPException(400,"واحد پول نامعتبر است")
    rate=Decimal(setting(db,"usd_irr_rate","0") or "0")
    if rate<=0: raise HTTPException(400,"مدیر هنوز نرخ تبدیل دلار را تنظیم نکرده است")
    if not setting(db,"card_number","").strip(): raise HTTPException(400,"اطلاعات کارت بانکی هنوز توسط مدیر ثبت نشده است")
    amount_irr=data.amount if currency=="IRR" else data.amount*rate
    amount_usd=data.amount if currency=="USD" else data.amount/rate
    fee_percent=Decimal(setting(db,"exchange_fee_percent","0.5") or "0.5")
    # Exchange commission is charged only when the customer converts USD to IRR.
    fee_irr=(amount_irr*fee_percent/Decimal("100")).quantize(Decimal("0.01"),rounding=ROUND_HALF_UP) if currency=="USD" else Decimal("0.00")
    total_payable_irr=amount_irr+fee_irr
    row=WalletRequest(user_id=user.id,entered_currency=currency,entered_amount=data.amount,amount_irr=amount_irr,
      amount_usd=amount_usd,fx_rate=rate,fee_percent=fee_percent,fee_irr=fee_irr,
      total_payable_irr=total_payable_irr,status="awaiting_payment")
    db.add(row);db.commit();db.refresh(row)
    return {"id":row.id,"amount_irr":float(amount_irr),"amount_usd":float(amount_usd),"fee_percent":float(fee_percent),"fee_irr":float(fee_irr),"total_payable_irr":float(total_payable_irr),"status":row.status}

@app.post("/api/wallet/deposit-requests/{request_id}/proof")
async def upload_wallet_proof(request_id:int,file:UploadFile=File(...),user:User=Depends(current_user),db:Session=Depends(get_db)):
    row=db.get(WalletRequest,request_id)
    if not row or (row.user_id!=user.id and user.role!="admin"): raise HTTPException(404,"درخواست پیدا نشد")
    if row.status not in ("awaiting_payment","pending"): raise HTTPException(400,"این درخواست در وضعیت قابل ارسال فیش نیست")
    if file.content_type not in ("image/jpeg","image/png","image/webp","application/pdf"): raise HTTPException(400,"فقط تصویر یا PDF مجاز است")
    data=await file.read()
    if len(data)>5*1024*1024: raise HTTPException(400,"حداکثر حجم فیش ۵ مگابایت است")
    row.proof_filename=file.filename[:255];row.proof_content_type=file.content_type;row.proof_data=data;row.status="pending"
    db.commit();return {"success":True,"status":"pending"}

@app.get("/api/wallet/deposit-requests/{request_id}/proof")
def get_wallet_proof(request_id:int,user:User=Depends(current_user),db:Session=Depends(get_db)):
    from fastapi.responses import Response
    row=db.get(WalletRequest,request_id)
    if not row or not row.proof_data or (row.user_id!=user.id and user.role!="admin"): raise HTTPException(404,"فیش پیدا نشد")
    return Response(content=row.proof_data,media_type=row.proof_content_type,headers={"Content-Disposition":'inline; filename="'+(row.proof_filename or "proof")+'"'})

@app.post("/api/wallet/withdrawals",status_code=201)
def create_withdrawal(data:WalletWithdrawInput,user:User=Depends(current_user),db:Session=Depends(get_db)):
    w=wallet_for(db,user.id)
    amount=Decimal(data.amount_irr)
    fee_rate=Decimal(setting(db,"withdrawal_fee_percent","0") or "0")
    if fee_rate<0 or fee_rate>100: raise HTTPException(500,"نرخ کارمزد برداشت در تنظیمات نامعتبر است")
    pending=db.query(func.coalesce(func.sum(-WalletTransaction.amount_irr),0)).filter(WalletTransaction.user_id==user.id,WalletTransaction.transaction_type=="withdrawal_pending").scalar() or Decimal("0")
    available=Decimal(w.balance_irr)-Decimal(pending)
    if available<amount: raise HTTPException(400,"موجودی قابل برداشت پس از کسر درخواست‌های در انتظار کافی نیست")
    fee=(amount*fee_rate/Decimal("100")).quantize(Decimal("0.01"))
    payout=amount-fee
    description="درخواست برداشت: "+data.destination+" | کارمزد: "+str(fee)+" ریال ("+str(fee_rate)+"٪) | مبلغ خالص: "+str(payout)+" ریال"
    row=WalletTransaction(user_id=user.id,actor_id=user.id,transaction_type="withdrawal_pending",amount_irr=-amount,balance_after_irr=w.balance_irr,description=description)
    db.add(row);db.commit();db.refresh(row)
    return {"id":row.id,"status":"pending","amount_irr":float(amount),"fee_irr":float(fee),"payout_irr":float(payout),"fee_percent":float(fee_rate)}

@app.get("/api/wallet/withdrawals")
def list_withdrawals(user:User=Depends(current_user),db:Session=Depends(get_db)):
    q=db.query(WalletTransaction).filter(WalletTransaction.transaction_type.in_(["withdrawal_pending","withdrawal_approved","withdrawal_rejected"])).order_by(WalletTransaction.id.desc())
    if user.role!="admin": q=q.filter(WalletTransaction.user_id==user.id)
    return [{"id":x.id,"user_id":x.user_id,"username":x.user.username,"amount_irr":float(abs(x.amount_irr)),"status":x.transaction_type,"description":x.description,"created_at":x.created_at.isoformat()} for x in q.all()]

@app.post("/api/wallet/deposit-requests/{request_id}/review")
def review_wallet_request(request_id:int,data:WalletReviewInput,actor:User=Depends(wallet_admin),db:Session=Depends(get_db)):
    row=db.get(WalletRequest,request_id)
    if not row: raise HTTPException(404,"درخواست پیدا نشد")
    if row.status!="pending": raise HTTPException(400,"این درخواست قبلاً بررسی شده یا فیش ندارد")
    if data.action not in ("approve","reject"): raise HTTPException(400,"عملیات نامعتبر است")
    row.status="approved" if data.action=="approve" else "rejected"
    row.rejection_reason=(data.reason or "")[:500] if data.action=="reject" else None
    row.reviewed_by=actor.id;row.reviewed_at=datetime.utcnow()
    if data.action=="approve":
        w=wallet_for(db,row.user_id);w.balance_irr=Decimal(w.balance_irr)+Decimal(row.amount_irr)
        db.add(WalletTransaction(user_id=row.user_id,actor_id=actor.id,transaction_type="deposit",amount_irr=row.amount_irr,balance_after_irr=w.balance_irr,description="تأیید افزایش موجودی #"+str(row.id),request_id=row.id))
    db.commit();return {"success":True,"status":row.status}

@app.post("/api/wallet/withdrawals/{transaction_id}/review")
def review_withdrawal(transaction_id:int,data:WalletReviewInput,actor:User=Depends(wallet_admin),db:Session=Depends(get_db)):
    row=db.get(WalletTransaction,transaction_id)
    if not row or row.transaction_type!="withdrawal_pending": raise HTTPException(404,"درخواست برداشت پیدا نشد")
    if data.action not in ("approve","reject"): raise HTTPException(400,"عملیات نامعتبر است")
    w=wallet_for(db,row.user_id)
    if data.action=="approve":
        amount=abs(Decimal(row.amount_irr))
        if Decimal(w.balance_irr)<amount: raise HTTPException(400,"موجودی کیف پول دیگر کافی نیست")
        w.balance_irr=Decimal(w.balance_irr)-amount
        row.transaction_type="withdrawal_approved";row.balance_after_irr=w.balance_irr
    else:
        row.transaction_type="withdrawal_rejected";row.description += " | رد: "+(data.reason or "")[:300]
    db.commit();return {"success":True}

@app.get("/api/wallet/config")
def get_wallet_config(user:User=Depends(current_user),db:Session=Depends(get_db)):
    return {"usd_irr_rate":setting(db,"usd_irr_rate","0"),"fx_auto_enabled":(setting(db,"fx_auto_enabled","true").lower() in ("true","1","yes","on")),
      "fx_updated_at":setting(db,"fx_updated_at",""),"fx_status":setting(db,"fx_status","waiting"),"fx_source":setting(db,"fx_source","TGJU"),
      "fx_last_error":setting(db,"fx_last_error","") if user.role=="admin" else "","exchange_fee_percent":setting(db,"exchange_fee_percent","0.5"),
      "bank_name":setting(db,"bank_name",""),"card_holder":setting(db,"card_holder",""),"card_number":setting(db,"card_number",""),"iban":setting(db,"iban",""),"bank_description":setting(db,"bank_description","")}

@app.put("/api/wallet/config")
def update_wallet_config(data:WalletConfigInput,actor:User=Depends(wallet_admin),db:Session=Depends(get_db)):
    values=data.model_dump()
    if not values["fx_auto_enabled"] and values["usd_irr_rate"]<=0:
        raise HTTPException(400,"در حالت دستی باید نرخ دلار بزرگ‌تر از صفر باشد")
    for k,v in values.items():
        if k=="usd_irr_rate" and values["fx_auto_enabled"] and v<=0:
            continue
        set_setting(db,k,("true" if v else "false") if isinstance(v,bool) else v)
    set_setting(db,"fx_status","manual" if not values["fx_auto_enabled"] else "waiting")
    db.commit();return {"success":True}

@app.get("/api/fx/rate")
def get_fx_rate(user:User=Depends(current_user),db:Session=Depends(get_db)):
    rate=Decimal(setting(db,"usd_irr_rate","0") or "0")
    updated=setting(db,"fx_updated_at","")
    status=setting(db,"fx_status","waiting")
    age=None
    if updated:
        try: age=max(0,int((datetime.utcnow()-datetime.fromisoformat(updated)).total_seconds()))
        except Exception: age=None
    stale=bool(age is not None and age>90 and setting(db,"fx_auto_enabled","true").lower() in ("true","1","yes","on"))
    if stale and status=="ok": status="stale"
    return {"rate":float(rate),"unit":"IRR","source":setting(db,"fx_source","TGJU"),
      "updated_at":updated,"age_seconds":age,"status":status,"stale":stale,
      "auto_enabled":setting(db,"fx_auto_enabled","true").lower() in ("true","1","yes","on"),
      "exchange_fee_percent":float(Decimal(setting(db,"exchange_fee_percent","0.5") or "0.5")),
      "last_error":setting(db,"fx_last_error","") if user.role=="admin" else ""}

@app.get("/api/system/config")
def get_system_config(user:User=Depends(current_user),db:Session=Depends(get_db)):
    result={"site_title":setting(db,"site_title","پنل مدیریت"),"support_email":setting(db,"support_email",""),"support_phone":setting(db,"support_phone",""),"default_currency":setting(db,"default_currency","IRR"),"withdrawal_fee_percent":setting(db,"withdrawal_fee_percent","0")}
    if user.role=="admin":
        result["n8n_user_visible_limit"]=int(setting(db,"n8n_user_visible_limit","10") or "10")
    return result

@app.put("/api/system/config")
def update_system_config(data:SystemConfigInput,actor:User=Depends(wallet_admin),db:Session=Depends(get_db)):
    for k,v in data.model_dump().items(): set_setting(db,k,v)
    db.commit();return {"success":True}
