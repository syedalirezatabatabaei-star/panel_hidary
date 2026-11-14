from datetime import datetime
from sqlalchemy import String,Integer,Boolean,DateTime,ForeignKey,UniqueConstraint,Numeric,LargeBinary,Text
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

class UserPagePermission(Base):
    __tablename__="user_page_permissions"
    __table_args__=(UniqueConstraint("user_id","page_key",name="uq_user_page"),)
    id:Mapped[int]=mapped_column(Integer,primary_key=True)
    user_id:Mapped[int]=mapped_column(ForeignKey("users.id",ondelete="CASCADE"),index=True)
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


class SystemSetting(Base):
    __tablename__="system_settings"
    key:Mapped[str]=mapped_column(String(80),primary_key=True)
    value:Mapped[str]=mapped_column(Text,default="")

class WalletAccount(Base):
    __tablename__="wallet_accounts"
    id:Mapped[int]=mapped_column(Integer,primary_key=True)
    user_id:Mapped[int]=mapped_column(ForeignKey("users.id"),unique=True,index=True)
    balance_irr:Mapped[float]=mapped_column(Numeric(18,2),default=0)
    updated_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow,onupdate=datetime.utcnow)

class WalletRequest(Base):
    __tablename__="wallet_requests"
    id:Mapped[int]=mapped_column(Integer,primary_key=True)
    user_id:Mapped[int]=mapped_column(ForeignKey("users.id"),index=True)
    entered_currency:Mapped[str]=mapped_column(String(3))
    entered_amount:Mapped[float]=mapped_column(Numeric(18,2))
    amount_irr:Mapped[float]=mapped_column(Numeric(18,2))
    amount_usd:Mapped[float]=mapped_column(Numeric(18,4))
    fx_rate:Mapped[float]=mapped_column(Numeric(18,4))
    fee_percent:Mapped[float]=mapped_column(Numeric(7,4),default=0)
    fee_irr:Mapped[float]=mapped_column(Numeric(18,2),default=0)
    total_payable_irr:Mapped[float]=mapped_column(Numeric(18,2),default=0)
    status:Mapped[str]=mapped_column(String(20),default="pending",index=True)
    proof_filename:Mapped[str|None]=mapped_column(String(255),nullable=True)
    proof_content_type:Mapped[str|None]=mapped_column(String(100),nullable=True)
    proof_data:Mapped[bytes|None]=mapped_column(LargeBinary,nullable=True)
    rejection_reason:Mapped[str|None]=mapped_column(String(500),nullable=True)
    reviewed_by:Mapped[int|None]=mapped_column(ForeignKey("users.id"),nullable=True)
    reviewed_at:Mapped[datetime|None]=mapped_column(DateTime,nullable=True)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
    user=relationship("User",foreign_keys=[user_id])

class WalletTransaction(Base):
    __tablename__="wallet_transactions"
    id:Mapped[int]=mapped_column(Integer,primary_key=True)
    user_id:Mapped[int]=mapped_column(ForeignKey("users.id"),index=True)
    actor_id:Mapped[int]=mapped_column(ForeignKey("users.id"))
    transaction_type:Mapped[str]=mapped_column(String(20),index=True)
    amount_irr:Mapped[float]=mapped_column(Numeric(18,2))
    balance_after_irr:Mapped[float]=mapped_column(Numeric(18,2))
    description:Mapped[str]=mapped_column(String(255))
    request_id:Mapped[int|None]=mapped_column(ForeignKey("wallet_requests.id"),nullable=True)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
    user=relationship("User",foreign_keys=[user_id])
