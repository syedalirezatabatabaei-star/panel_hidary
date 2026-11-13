from datetime import datetime
from sqlalchemy import String,Integer,Boolean,DateTime,ForeignKey,UniqueConstraint
from sqlalchemy.orm import Mapped,mapped_column,relationship
from .database import Base
class User(Base):
    __tablename__="users"
    id:Mapped[int]=mapped_column(Integer,primary_key=True)
    username:Mapped[str]=mapped_column(String(80),unique=True,index=True)
    full_name:Mapped[str]=mapped_column(String(160),default="")
    password_hash:Mapped[str]=mapped_column(String(255))
    role:Mapped[str]=mapped_column(String(30),default="user")
    is_active:Mapped[bool]=mapped_column(Boolean,default=True)
    coin_balance:Mapped[int]=mapped_column(Integer,default=0)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
    transactions=relationship("CoinTransaction",back_populates="user",foreign_keys="CoinTransaction.user_id")
class PagePermission(Base):
    __tablename__="page_permissions"
    __table_args__=(UniqueConstraint("role","page_key",name="uq_role_page"),)
    id:Mapped[int]=mapped_column(Integer,primary_key=True)
    role:Mapped[str]=mapped_column(String(30),index=True)
    page_key:Mapped[str]=mapped_column(String(60))
    can_view:Mapped[bool]=mapped_column(Boolean,default=False)
    can_edit:Mapped[bool]=mapped_column(Boolean,default=False)
class CoinTransaction(Base):
    __tablename__="coin_transactions"
    id:Mapped[int]=mapped_column(Integer,primary_key=True)
    user_id:Mapped[int]=mapped_column(ForeignKey("users.id"),index=True)
    actor_id:Mapped[int]=mapped_column(ForeignKey("users.id"))
    amount:Mapped[int]=mapped_column(Integer)
    balance_after:Mapped[int]=mapped_column(Integer)
    reason:Mapped[str]=mapped_column(String(255))
    reference:Mapped[str|None]=mapped_column(String(100),nullable=True)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
    user=relationship("User",foreign_keys=[user_id],back_populates="transactions")
