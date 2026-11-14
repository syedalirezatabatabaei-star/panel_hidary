from datetime import datetime,timedelta,timezone
from jose import jwt,JWTError
from passlib.context import CryptContext
from fastapi import Depends,HTTPException,status,Cookie
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from .config import settings
from .database import get_db
from .models import User
pwd_context=CryptContext(schemes=["bcrypt"],deprecated="auto")
oauth2_scheme=OAuth2PasswordBearer(tokenUrl="/api/auth/login",auto_error=False)
def hash_password(password:str)->str: return pwd_context.hash(password)
def verify_password(password:str,hashed:str)->bool:
    try: return pwd_context.verify(password,hashed)
    except (ValueError,TypeError): return False
def create_access_token(user_id:int,session_version:int=0)->str:
    exp=datetime.now(timezone.utc)+timedelta(minutes=settings.access_token_expire_minutes)
    return jwt.encode({"sub":str(user_id),"ver":int(session_version),"exp":exp},settings.secret_key,algorithm="HS256")
def current_user(token:str|None=Depends(oauth2_scheme),session_cookie:str|None=Cookie(default=None,alias="hidary_session"),db:Session=Depends(get_db))->User:
    credential=token or session_cookie
    error=HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,detail="اعتبار ورود نامعتبر است",headers={"WWW-Authenticate":"Bearer"})
    if not credential: raise error
    try:
        payload=jwt.decode(credential,settings.secret_key,algorithms=["HS256"])
        user_id=int(payload.get("sub","0")); version=int(payload.get("ver",0))
    except (JWTError,ValueError,TypeError): raise error
    user=db.get(User,user_id)
    if not user or not user.is_active or int(user.session_version or 0)!=version: raise error
    return user
