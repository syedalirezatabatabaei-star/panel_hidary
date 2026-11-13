from fastapi import FastAPI,Depends,HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel,Field
from sqlalchemy.orm import Session
from sqlalchemy import func
from .config import settings
from .database import Base,engine,SessionLocal,get_db
from .models import User,PagePermission,CoinTransaction
from .security import hash_password,verify_password,create_access_token,current_user
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
