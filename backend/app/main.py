from fastapi import FastAPI,Depends,HTTPException,UploadFile,File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel,Field
from sqlalchemy.orm import Session
from sqlalchemy import func
from .config import settings
from .database import Base,engine,SessionLocal,get_db
from .models import User,PagePermission,CoinTransaction,SystemSetting,WalletAccount,WalletRequest,WalletTransaction
from .security import hash_password,verify_password,create_access_token,current_user
from datetime import datetime
from decimal import Decimal
app=FastAPI(title="Hidary Admin API",version="1.0.0")
app.add_middleware(CORSMiddleware,allow_origins=settings.allowed_origins,allow_credentials=True,allow_methods=["*"],allow_headers=["*"])
PAGES={"dashboard":"داشبورد","users":"کاربران","permissions":"دسترسی‌ها","coins":"مدیریت توکن"}
DEFAULTS={"admin":{k:(True,True) for k in PAGES},"manager":{"dashboard":(True,False),"users":(True,True),"permissions":(False,False),"coins":(True,True)},"user":{"dashboard":(True,False),"users":(False,False),"permissions":(False,False),"coins":(True,False)}}
def seed():
    Base.metadata.create_all(bind=engine); db=SessionLocal()
    try:
        if not db.query(User).filter_by(username=settings.admin_username).first():
            db.add(User(username=settings.admin_username,full_name=settings.admin_full_name,password_hash=hash_password(settings.admin_password),role="admin"))
        for role,pages in DEFAULTS.items():
            for key,(view,edit) in pages.items():
                p=db.query(PagePermission).filter_by(role=role,page_key=key).first()
                if not p: db.add(PagePermission(role=role,page_key=key,can_view=view,can_edit=edit))
        db.commit()
    finally: db.close()
@app.on_event("startup")
def startup(): seed()
def require_page(page,edit=False):
    def check(user:User=Depends(current_user),db:Session=Depends(get_db)):
        if user.role=="admin": return user
        p=db.query(PagePermission).filter_by(role=user.role,page_key=page).first()
        if not p or not p.can_view or (edit and not p.can_edit): raise HTTPException(403,"دسترسی کافی ندارید")
        return user
    return check
class UserCreate(BaseModel):
    username:str=Field(min_length=3,max_length=80); password:str=Field(min_length=8,max_length=128)
    full_name:str=Field(min_length=2,max_length=160); role:str="user"
class UserUpdate(BaseModel):
    full_name:str|None=None; role:str|None=None; is_active:bool|None=None
    password:str|None=Field(default=None,min_length=8,max_length=128)
class PermissionUpdate(BaseModel):
    role:str; page_key:str; can_view:bool; can_edit:bool
class CoinChange(BaseModel):
    user_id:int; amount:int; reason:str=Field(min_length=2,max_length=255); reference:str|None=None
@app.get("/api/health")
def health(): return {"status":"ok"}
@app.post("/api/auth/login")
def login(form:OAuth2PasswordRequestForm=Depends(),db:Session=Depends(get_db)):
    u=db.query(User).filter_by(username=form.username).first()
    if not u or not verify_password(form.password,u.password_hash) or not u.is_active: raise HTTPException(401,"نام کاربری یا رمز عبور اشتباه است")
    return {"access_token":create_access_token(u.id),"token_type":"bearer"}
@app.get("/api/auth/me")
def me(user:User=Depends(current_user),db:Session=Depends(get_db)):
    ps=db.query(PagePermission).filter_by(role=user.role).all()
    return {"id":user.id,"username":user.username,"full_name":user.full_name,"role":user.role,"coin_balance":user.coin_balance,"permissions":{p.page_key:{"view":p.can_view,"edit":p.can_edit} for p in ps}}
@app.get("/api/dashboard")
def dashboard(user:User=Depends(require_page("dashboard")),db:Session=Depends(get_db)):
    recent=db.query(CoinTransaction).order_by(CoinTransaction.id.desc()).limit(8).all()
    return {"users_total":db.query(func.count(User.id)).scalar() or 0,"users_active":db.query(func.count(User.id)).filter(User.is_active.is_(True)).scalar() or 0,"coins_total":db.query(func.coalesce(func.sum(User.coin_balance),0)).scalar() or 0,"coins_used":db.query(func.coalesce(func.sum(-CoinTransaction.amount),0)).filter(CoinTransaction.amount<0).scalar() or 0,"recent_transactions":[{"id":t.id,"username":t.user.username,"amount":t.amount,"reason":t.reason,"created_at":t.created_at.isoformat()} for t in recent]}
@app.get("/api/users")
def users(user:User=Depends(require_page("users")),db:Session=Depends(get_db)):
    return [{"id":u.id,"username":u.username,"full_name":u.full_name,"role":u.role,"is_active":u.is_active,"coin_balance":u.coin_balance} for u in db.query(User).order_by(User.id.desc()).all()]
@app.post("/api/users",status_code=201)
def create_user(data:UserCreate,actor:User=Depends(require_page("users",True)),db:Session=Depends(get_db)):
    if data.role not in DEFAULTS: raise HTTPException(400,"نقش نامعتبر است")
    if db.query(User).filter_by(username=data.username).first(): raise HTTPException(409,"نام کاربری تکراری است")
    u=User(username=data.username,full_name=data.full_name,role=data.role,password_hash=hash_password(data.password)); db.add(u); db.commit(); db.refresh(u)
    return {"id":u.id,"username":u.username}
@app.patch("/api/users/{uid}")
def update_user(uid:int,data:UserUpdate,actor:User=Depends(require_page("users",True)),db:Session=Depends(get_db)):
    u=db.get(User,uid)
    if not u: raise HTTPException(404,"کاربر پیدا نشد")
    if u.id==actor.id and data.is_active is False: raise HTTPException(400,"نمی‌توانید حساب خود را غیرفعال کنید")
    if data.role is not None:
        if data.role not in DEFAULTS: raise HTTPException(400,"نقش نامعتبر است")
        u.role=data.role
    if data.full_name is not None: u.full_name=data.full_name
    if data.is_active is not None: u.is_active=data.is_active
    if data.password: u.password_hash=hash_password(data.password)
    db.commit(); return {"success":True}
@app.get("/api/permissions")
def permissions(actor:User=Depends(require_page("permissions")),db:Session=Depends(get_db)):
    return {"pages":PAGES,"roles":{r:[{"page_key":p.page_key,"page_title":PAGES[p.page_key],"can_view":p.can_view,"can_edit":p.can_edit} for p in db.query(PagePermission).filter_by(role=r).all()] for r in DEFAULTS}}
@app.put("/api/permissions")
def set_permission(data:PermissionUpdate,actor:User=Depends(require_page("permissions",True)),db:Session=Depends(get_db)):
    if data.role not in DEFAULTS or data.role=="admin" or data.page_key not in PAGES: raise HTTPException(400,"نقش یا صفحه نامعتبر است")
    if data.can_edit and not data.can_view: raise HTTPException(400,"ویرایش بدون مشاهده مجاز نیست")
    p=db.query(PagePermission).filter_by(role=data.role,page_key=data.page_key).first()
    if not p: p=PagePermission(role=data.role,page_key=data.page_key); db.add(p)
    p.can_view=data.can_view; p.can_edit=data.can_edit; db.commit(); return {"success":True}
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
    usd_irr_rate:Decimal=Field(gt=0)
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

@app.get("/api/wallet")
def wallet_summary(user:User=Depends(current_user),db:Session=Depends(get_db)):
    w=wallet_for(db,user.id)
    db.commit()
    rate=Decimal(setting(db,"usd_irr_rate","600000"))
    return {"balance_irr":float(w.balance_irr),"balance_usd":float(w.balance_irr/rate),"usd_irr_rate":float(rate)}

@app.get("/api/wallet/requests")
def wallet_requests(user:User=Depends(current_user),db:Session=Depends(get_db)):
    q=db.query(WalletRequest).order_by(WalletRequest.id.desc())
    if user.role!="admin": q=q.filter(WalletRequest.user_id==user.id)
    return [{"id":x.id,"user_id":x.user_id,"username":x.user.username,"full_name":x.user.full_name,
      "currency":x.entered_currency,"entered_amount":float(x.entered_amount),"amount_irr":float(x.amount_irr),
      "amount_usd":float(x.amount_usd),"status":x.status,"proof_filename":x.proof_filename,
      "rejection_reason":x.rejection_reason,"created_at":x.created_at.isoformat(),"type":"deposit"} for x in q.all()]

@app.post("/api/wallet/deposit-requests",status_code=201)
def create_wallet_request(data:WalletRequestInput,user:User=Depends(current_user),db:Session=Depends(get_db)):
    currency=data.currency.upper()
    if currency not in ("IRR","USD"): raise HTTPException(400,"واحد پول نامعتبر است")
    rate=Decimal(setting(db,"usd_irr_rate","600000"))
    amount_irr=data.amount if currency=="IRR" else data.amount*rate
    amount_usd=data.amount if currency=="USD" else data.amount/rate
    row=WalletRequest(user_id=user.id,entered_currency=currency,entered_amount=data.amount,amount_irr=amount_irr,amount_usd=amount_usd,fx_rate=rate,status="awaiting_payment")
    db.add(row);db.commit();db.refresh(row)
    return {"id":row.id,"amount_irr":float(amount_irr),"amount_usd":float(amount_usd),"status":row.status}

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
    if Decimal(w.balance_irr)<amount: raise HTTPException(400,"موجودی کیف پول کافی نیست")
    row=WalletTransaction(user_id=user.id,actor_id=user.id,transaction_type="withdrawal_pending",amount_irr=-amount,balance_after_irr=w.balance_irr,description="درخواست برداشت: "+data.destination)
    db.add(row);db.commit();db.refresh(row)
    return {"id":row.id,"status":"pending"}

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
    return {"usd_irr_rate":setting(db,"usd_irr_rate","600000"),"bank_name":setting(db,"bank_name","بانک"),"card_holder":setting(db,"card_holder","نام صاحب کارت"),"card_number":setting(db,"card_number","0000-0000-0000-0000"),"iban":setting(db,"iban",""),"bank_description":setting(db,"bank_description","")}

@app.put("/api/wallet/config")
def update_wallet_config(data:WalletConfigInput,actor:User=Depends(wallet_admin),db:Session=Depends(get_db)):
    for k,v in data.model_dump().items(): set_setting(db,k,v)
    db.commit();return {"success":True}

@app.get("/api/system/config")
def get_system_config(user:User=Depends(current_user),db:Session=Depends(get_db)):
    return {"site_title":setting(db,"site_title","پنل مدیریت حیدری"),"support_email":setting(db,"support_email",""),"support_phone":setting(db,"support_phone",""),"default_currency":setting(db,"default_currency","IRR")}

@app.put("/api/system/config")
def update_system_config(data:SystemConfigInput,actor:User=Depends(wallet_admin),db:Session=Depends(get_db)):
    for k,v in data.model_dump().items(): set_setting(db,k,v)
    db.commit();return {"success":True}
