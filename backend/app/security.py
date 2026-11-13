from datetime import datetime,timedelta,timezone
from jose import jwt,JWTError
from passlib.context import CryptContext
from fastapi import Depends,HTTPException,status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from .config import settings
from .database import get_db
from .models import User
pwd_context=CryptContext(schemes=["bcrypt"],deprecated="auto")
oauth2_scheme=OAuth2PasswordBearer(tokenUrl="/api/auth/login")
def hash_password(password:str)->str: return pwd_context.hash(password)
def verify_password(password:str,hashed:str)->bool: return pwd_context.verify(password,hashed)
def create_access_token(user_id:int)->str:
    exp=datetime.now(timezone.utc)+timedelta(minutes=settings.access_token_expire_minutes)
    return jwt.encode({"sub":str(user_id),"exp":exp},settings.secret_key,algorithm="HS256")
def current_user(token:str=Depends(oauth2_scheme),db:Session=Depends(get_db))->User:
    error=HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,detail="اعتبار ورود نامعتبر است")
    try: user_id=int(jwt.decode(token,settings.secret_key,algorithms=["HS256"]).get("sub","0"))
    except (JWTError,ValueError): raise error
    user=db.get(User,user_id)
    if not user or not user.is_active: raise error
    return user
