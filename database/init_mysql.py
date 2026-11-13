#!/usr/bin/env python3
"""
Create missing MySQL tables for Panel Hidary.

Uses backend/.env DATABASE_URL and the PyMySQL driver already required by
the backend. It creates absent tables only and never alters or deletes data.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

import pymysql
from sqlalchemy.engine import make_url


ROOT_DIR = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT_DIR / "backend" / ".env"


def load_env_file(path: Path) -> None:
    """Load KEY=VALUE entries without overriding process environment values."""
    if not path.is_file():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]

        if key:
            os.environ.setdefault(key, value)


def connect() -> pymysql.connections.Connection:
    load_env_file(ENV_FILE)
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            f"DATABASE_URL is not set. Add it to {ENV_FILE} or the process environment."
        )

    url = make_url(database_url)
    if url.get_backend_name() != "mysql":
        raise RuntimeError("DATABASE_URL must point to MySQL.")
    if not url.database:
        raise RuntimeError("DATABASE_URL must include a database name.")

    query: dict[str, Any] = dict(url.query)
    connect_args: dict[str, Any] = {
        "host": url.host or "127.0.0.1",
        "port": url.port or 3306,
        "user": url.username,
        "password": url.password or "",
        "database": url.database,
        "charset": query.get("charset", "utf8mb4"),
        "connect_timeout": 10,
        "read_timeout": 30,
        "write_timeout": 30,
        "autocommit": True,
        "cursorclass": pymysql.cursors.DictCursor,
    }
    if query.get("unix_socket"):
        connect_args["unix_socket"] = query["unix_socket"]

    return pymysql.connect(**connect_args)


TABLES: dict[str, str] = {
    # Existing application schema: create only on a fresh database.
    "users": """
        CREATE TABLE users (
            id INT NOT NULL AUTO_INCREMENT,
            username VARCHAR(80) NOT NULL,
            full_name VARCHAR(160) NOT NULL DEFAULT '',
            password_hash VARCHAR(255) NOT NULL,
            role VARCHAR(30) NOT NULL DEFAULT 'user',
            is_active TINYINT(1) NOT NULL DEFAULT 1,
            coin_balance INT NOT NULL DEFAULT 0,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            UNIQUE KEY uq_users_username (username)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    "page_permissions": """
        CREATE TABLE page_permissions (
            id INT NOT NULL AUTO_INCREMENT,
            role VARCHAR(30) NOT NULL,
            page_key VARCHAR(60) NOT NULL,
            can_view TINYINT(1) NOT NULL DEFAULT 0,
            can_edit TINYINT(1) NOT NULL DEFAULT 0,
            PRIMARY KEY (id),
            UNIQUE KEY uq_role_page (role, page_key),
            KEY ix_page_permissions_role (role)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    "coin_transactions": """
        CREATE TABLE coin_transactions (
            id INT NOT NULL AUTO_INCREMENT,
            user_id INT NOT NULL,
            actor_id INT NOT NULL,
            amount INT NOT NULL,
            balance_after INT NOT NULL,
            reason VARCHAR(255) NOT NULL,
            reference VARCHAR(100) NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            KEY ix_coin_transactions_user_id (user_id),
            KEY ix_coin_transactions_actor_id (actor_id),
            CONSTRAINT fk_coin_tx_user FOREIGN KEY (user_id) REFERENCES users(id),
            CONSTRAINT fk_coin_tx_actor FOREIGN KEY (actor_id) REFERENCES users(id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    "system_settings": """
        CREATE TABLE system_settings (
            \`key\` VARCHAR(80) NOT NULL,
            \`value\` TEXT NOT NULL,
            PRIMARY KEY (\`key\`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    "wallet_accounts": """
        CREATE TABLE wallet_accounts (
            id INT NOT NULL AUTO_INCREMENT,
            user_id INT NOT NULL,
            balance_irr DECIMAL(18,2) NOT NULL DEFAULT 0,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            UNIQUE KEY uq_wallet_accounts_user (user_id),
            CONSTRAINT fk_wallet_accounts_user FOREIGN KEY (user_id) REFERENCES users(id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    "wallet_requests": """
        CREATE TABLE wallet_requests (
            id INT NOT NULL AUTO_INCREMENT,
            user_id INT NOT NULL,
            entered_currency VARCHAR(3) NOT NULL,
            entered_amount DECIMAL(18,2) NOT NULL,
            amount_irr DECIMAL(18,2) NOT NULL,
            amount_usd DECIMAL(18,4) NOT NULL,
            fx_rate DECIMAL(18,4) NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            proof_filename VARCHAR(255) NULL,
            proof_content_type VARCHAR(100) NULL,
            proof_data LONGBLOB NULL,
            rejection_reason VARCHAR(500) NULL,
            reviewed_by INT NULL,
            reviewed_at DATETIME NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            KEY ix_wallet_requests_user_id (user_id),
            KEY ix_wallet_requests_status (status),
            CONSTRAINT fk_wallet_requests_user FOREIGN KEY (user_id) REFERENCES users(id),
            CONSTRAINT fk_wallet_requests_reviewer FOREIGN KEY (reviewed_by)
                REFERENCES users(id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    "wallet_transactions": """
        CREATE TABLE wallet_transactions (
            id INT NOT NULL AUTO_INCREMENT,
            user_id INT NOT NULL,
            actor_id INT NOT NULL,
            transaction_type VARCHAR(20) NOT NULL,
            amount_irr DECIMAL(18,2) NOT NULL,
            balance_after_irr DECIMAL(18,2) NOT NULL,
            description VARCHAR(255) NOT NULL,
            request_id INT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            KEY ix_wallet_transactions_user_id (user_id),
            KEY ix_wallet_transactions_type (transaction_type),
            KEY ix_wallet_transactions_actor_id (actor_id),
            KEY ix_wallet_transactions_request_id (request_id),
            CONSTRAINT fk_wallet_tx_user FOREIGN KEY (user_id) REFERENCES users(id),
            CONSTRAINT fk_wallet_tx_actor FOREIGN KEY (actor_id) REFERENCES users(id),
            CONSTRAINT fk_wallet_tx_request FOREIGN KEY (request_id)
                REFERENCES wallet_requests(id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,

    # Role-based and user-specific permission model.
    "roles": """
        CREATE TABLE roles (
            id INT NOT NULL AUTO_INCREMENT,
            code VARCHAR(60) NOT NULL,
            title VARCHAR(120) NOT NULL,
            description VARCHAR(500) NULL,
            is_system TINYINT(1) NOT NULL DEFAULT 0,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            UNIQUE KEY uq_roles_code (code)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    "permissions": """
        CREATE TABLE permissions (
            id INT NOT NULL AUTO_INCREMENT,
            code VARCHAR(160) NOT NULL,
            page_key VARCHAR(80) NOT NULL,
            action_key VARCHAR(80) NOT NULL,
            title VARCHAR(190) NOT NULL,
            description VARCHAR(500) NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            UNIQUE KEY uq_permissions_code (code),
            UNIQUE KEY uq_permissions_page_action (page_key, action_key),
            KEY ix_permissions_page (page_key)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    "role_permissions": """
        CREATE TABLE role_permissions (
            role_id INT NOT NULL,
            permission_id INT NOT NULL,
            is_allowed TINYINT(1) NOT NULL DEFAULT 1,
            assigned_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (role_id, permission_id),
            KEY ix_role_permissions_permission (permission_id),
            CONSTRAINT fk_role_permissions_role FOREIGN KEY (role_id)
                REFERENCES roles(id) ON DELETE CASCADE,
            CONSTRAINT fk_role_permissions_permission FOREIGN KEY (permission_id)
                REFERENCES permissions(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    "user_roles": """
        CREATE TABLE user_roles (
            user_id INT NOT NULL,
            role_id INT NOT NULL,
            assigned_by INT NULL,
            assigned_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, role_id),
            KEY ix_user_roles_role (role_id),
            CONSTRAINT fk_user_roles_user FOREIGN KEY (user_id)
                REFERENCES users(id) ON DELETE CASCADE,
            CONSTRAINT fk_user_roles_role FOREIGN KEY (role_id)
                REFERENCES roles(id) ON DELETE CASCADE,
            CONSTRAINT fk_user_roles_assigner FOREIGN KEY (assigned_by)
                REFERENCES users(id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    "user_permission_overrides": """
        CREATE TABLE user_permission_overrides (
            user_id INT NOT NULL,
            permission_id INT NOT NULL,
            effect ENUM('allow','deny') NOT NULL,
            assigned_by INT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, permission_id),
            KEY ix_user_permission_overrides_permission (permission_id),
            CONSTRAINT fk_user_permission_overrides_user FOREIGN KEY (user_id)
                REFERENCES users(id) ON DELETE CASCADE,
            CONSTRAINT fk_user_permission_overrides_permission FOREIGN KEY (permission_id)
                REFERENCES permissions(id) ON DELETE CASCADE,
            CONSTRAINT fk_user_permission_overrides_assigner FOREIGN KEY (assigned_by)
                REFERENCES users(id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,

    # Authentication and security records.
    "user_sessions": """
        CREATE TABLE user_sessions (
            id BIGINT NOT NULL AUTO_INCREMENT,
            user_id INT NOT NULL,
            token_hash CHAR(64) NOT NULL,
            ip_address VARCHAR(45) NULL,
            user_agent VARCHAR(500) NULL,
            expires_at DATETIME NOT NULL,
            revoked_at DATETIME NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            UNIQUE KEY uq_user_sessions_token_hash (token_hash),
            KEY ix_user_sessions_user (user_id, revoked_at),
            KEY ix_user_sessions_expiry (expires_at),
            CONSTRAINT fk_user_sessions_user FOREIGN KEY (user_id)
                REFERENCES users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    "user_login_logs": """
        CREATE TABLE user_login_logs (
            id BIGINT NOT NULL AUTO_INCREMENT,
            user_id INT NULL,
            login_identifier VARCHAR(190) NULL,
            ip_address VARCHAR(45) NULL,
            user_agent VARCHAR(500) NULL,
            success TINYINT(1) NOT NULL DEFAULT 0,
            failure_reason VARCHAR(255) NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            KEY ix_user_login_logs_user_date (user_id, created_at),
            KEY ix_user_login_logs_ip_date (ip_address, created_at),
            CONSTRAINT fk_user_login_logs_user FOREIGN KEY (user_id)
                REFERENCES users(id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    "login_attempt_limits": """
        CREATE TABLE login_attempt_limits (
            identifier_hash CHAR(64) NOT NULL,
            attempts INT UNSIGNED NOT NULL DEFAULT 0,
            first_attempt_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            locked_until DATETIME NULL,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (identifier_hash),
            KEY ix_login_attempts_locked_until (locked_until)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    "password_reset_tokens": """
        CREATE TABLE password_reset_tokens (
            id BIGINT NOT NULL AUTO_INCREMENT,
            user_id INT NOT NULL,
            token_hash CHAR(64) NOT NULL,
            expires_at DATETIME NOT NULL,
            used_at DATETIME NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            UNIQUE KEY uq_password_reset_token (token_hash),
            KEY ix_password_reset_user_expiry (user_id, expires_at),
            CONSTRAINT fk_password_reset_user FOREIGN KEY (user_id)
                REFERENCES users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    "password_history": """
        CREATE TABLE password_history (
            id BIGINT NOT NULL AUTO_INCREMENT,
            user_id INT NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            KEY ix_password_history_user_date (user_id, created_at),
            CONSTRAINT fk_password_history_user FOREIGN KEY (user_id)
                REFERENCES users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,

    # Central AI credentials and per-user usage accounting.
    "ai_providers": """
        CREATE TABLE ai_providers (
            id INT NOT NULL AUTO_INCREMENT,
            code VARCHAR(80) NOT NULL,
            title VARCHAR(120) NOT NULL,
            base_url VARCHAR(500) NULL,
            is_active TINYINT(1) NOT NULL DEFAULT 1,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            UNIQUE KEY uq_ai_providers_code (code)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    "ai_tokens": """
        CREATE TABLE ai_tokens (
            id BIGINT NOT NULL AUTO_INCREMENT,
            provider_id INT NOT NULL,
            label VARCHAR(150) NOT NULL,
            token_ciphertext LONGBLOB NOT NULL,
            encryption_key_version VARCHAR(60) NOT NULL,
            token_last4 VARCHAR(4) NULL,
            status ENUM('active','inactive','revoked') NOT NULL DEFAULT 'active',
            priority INT NOT NULL DEFAULT 100,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            KEY ix_ai_tokens_provider_status (provider_id, status),
            KEY ix_ai_tokens_priority (status, priority),
            CONSTRAINT fk_ai_tokens_provider FOREIGN KEY (provider_id)
                REFERENCES ai_providers(id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    "ai_models": """
        CREATE TABLE ai_models (
            id INT NOT NULL AUTO_INCREMENT,
            provider_id INT NOT NULL,
            model_code VARCHAR(150) NOT NULL,
            title VARCHAR(190) NOT NULL,
            input_price_per_million DECIMAL(20,10) NULL,
            output_price_per_million DECIMAL(20,10) NULL,
            is_active TINYINT(1) NOT NULL DEFAULT 1,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            UNIQUE KEY uq_ai_models_provider_code (provider_id, model_code),
            CONSTRAINT fk_ai_models_provider FOREIGN KEY (provider_id)
                REFERENCES ai_providers(id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    "ai_user_limits": """
        CREATE TABLE ai_user_limits (
            id BIGINT NOT NULL AUTO_INCREMENT,
            user_id INT NOT NULL,
            daily_token_limit BIGINT UNSIGNED NULL,
            monthly_token_limit BIGINT UNSIGNED NULL,
            daily_cost_limit DECIMAL(20,8) NULL,
            monthly_cost_limit DECIMAL(20,8) NULL,
            is_enabled TINYINT(1) NOT NULL DEFAULT 1,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            UNIQUE KEY uq_ai_user_limits_user (user_id),
            CONSTRAINT fk_ai_user_limits_user FOREIGN KEY (user_id)
                REFERENCES users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    "ai_usage_logs": """
        CREATE TABLE ai_usage_logs (
            id BIGINT NOT NULL AUTO_INCREMENT,
            user_id INT NULL,
            provider_id INT NULL,
            token_id BIGINT NULL,
            model_id INT NULL,
            request_id VARCHAR(150) NULL,
            input_tokens BIGINT UNSIGNED NOT NULL DEFAULT 0,
            output_tokens BIGINT UNSIGNED NOT NULL DEFAULT 0,
            total_tokens BIGINT UNSIGNED NOT NULL DEFAULT 0,
            estimated_cost DECIMAL(20,10) NOT NULL DEFAULT 0,
            status ENUM('success','failed') NOT NULL,
            error_message TEXT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            UNIQUE KEY uq_ai_usage_request (request_id),
            KEY ix_ai_usage_user_date (user_id, created_at),
            KEY ix_ai_usage_provider_date (provider_id, created_at),
            KEY ix_ai_usage_model_date (model_id, created_at),
            CONSTRAINT fk_ai_usage_user FOREIGN KEY (user_id)
                REFERENCES users(id) ON DELETE SET NULL,
            CONSTRAINT fk_ai_usage_provider FOREIGN KEY (provider_id)
                REFERENCES ai_providers(id) ON DELETE SET NULL,
            CONSTRAINT fk_ai_usage_token FOREIGN KEY (token_id)
                REFERENCES ai_tokens(id) ON DELETE SET NULL,
            CONSTRAINT fk_ai_usage_model FOREIGN KEY (model_id)
                REFERENCES ai_models(id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,

    # Wallet policy, feature flags, API keys and operational logs.
    # Existing balances and payment history stay in wallet_* tables above.
    "wallet_settings": """
        CREATE TABLE wallet_settings (
            currency CHAR(3) NOT NULL,
            withdrawal_fee_type ENUM('fixed','percentage') NOT NULL DEFAULT 'percentage',
            withdrawal_fee_value DECIMAL(20,4) NOT NULL DEFAULT 0,
            minimum_withdrawal DECIMAL(20,4) NOT NULL DEFAULT 0,
            maximum_withdrawal DECIMAL(20,4) NULL,
            is_deposit_enabled TINYINT(1) NOT NULL DEFAULT 1,
            is_withdrawal_enabled TINYINT(1) NOT NULL DEFAULT 1,
            updated_by INT NULL,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (currency),
            CONSTRAINT fk_wallet_settings_updater FOREIGN KEY (updated_by)
                REFERENCES users(id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    "system_modules": """
        CREATE TABLE system_modules (
            id INT NOT NULL AUTO_INCREMENT,
            module_key VARCHAR(100) NOT NULL,
            title VARCHAR(150) NOT NULL,
            is_enabled TINYINT(1) NOT NULL DEFAULT 1,
            config JSON NULL,
            updated_by INT NULL,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            UNIQUE KEY uq_system_modules_key (module_key),
            CONSTRAINT fk_system_modules_updater FOREIGN KEY (updated_by)
                REFERENCES users(id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    "admin_audit_logs": """
        CREATE TABLE admin_audit_logs (
            id BIGINT NOT NULL AUTO_INCREMENT,
            actor_user_id INT NULL,
            action VARCHAR(150) NOT NULL,
            target_type VARCHAR(100) NULL,
            target_id BIGINT NULL,
            old_values JSON NULL,
            new_values JSON NULL,
            ip_address VARCHAR(45) NULL,
            user_agent VARCHAR(500) NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            KEY ix_audit_actor_date (actor_user_id, created_at),
            KEY ix_audit_target (target_type, target_id),
            CONSTRAINT fk_admin_audit_actor FOREIGN KEY (actor_user_id)
                REFERENCES users(id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    "system_logs": """
        CREATE TABLE system_logs (
            id BIGINT NOT NULL AUTO_INCREMENT,
            level ENUM('debug','info','warning','error','critical') NOT NULL,
            source VARCHAR(150) NULL,
            message TEXT NOT NULL,
            context JSON NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            KEY ix_system_logs_level_date (level, created_at),
            KEY ix_system_logs_source_date (source, created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    "api_keys": """
        CREATE TABLE api_keys (
            id BIGINT NOT NULL AUTO_INCREMENT,
            name VARCHAR(150) NOT NULL,
            key_hash CHAR(64) NOT NULL,
            scopes JSON NULL,
            expires_at DATETIME NULL,
            last_used_at DATETIME NULL,
            revoked_at DATETIME NULL,
            created_by INT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            UNIQUE KEY uq_api_keys_hash (key_hash),
            KEY ix_api_keys_expiry (expires_at),
            CONSTRAINT fk_api_keys_creator FOREIGN KEY (created_by)
                REFERENCES users(id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
}


PAGE_ACTIONS: dict[str, tuple[str, dict[str, str]]] = {
    "dashboard": ("داشبورد", {
        "view": "مشاهده",
        "edit": "مدیریت صفحه",
    }),
    "products": ("محصولات", {
        "view": "مشاهده محصولات",
        "edit": "مدیریت محصولات",
        "create": "ایجاد محصول",
        "delete": "حذف محصول",
        "import": "ورود گروهی محصولات",
        "export": "خروجی محصولات",
    }),
    "addProduct": ("افزودن محصول", {
        "view": "مشاهده صفحه افزودن محصول",
        "edit": "مدیریت فرم افزودن محصول",
        "create": "ثبت محصول جدید",
    }),
    "sites": ("سایت‌های پایش‌شده", {
        "view": "مشاهده سایت‌ها",
        "edit": "مدیریت سایت‌ها",
        "create": "افزودن سایت",
        "delete": "حذف سایت",
    }),
    "aiTokens": ("توکن هوش مصنوعی و کیف پول", {
        "view": "مشاهده کیف پول و توکن",
        "edit": "مدیریت این بخش",
        "manage": "مدیریت توکن مرکزی هوش مصنوعی",
        "usage.view": "مشاهده مصرف هوش مصنوعی",
        "deposit.create": "ثبت درخواست افزایش موجودی",
        "withdrawal.create": "ثبت درخواست برداشت",
        "deposit.review": "بررسی درخواست افزایش موجودی",
        "withdrawal.review": "بررسی درخواست برداشت",
        "wallet.config": "مدیریت تنظیمات کیف پول",
    }),
    "settings": ("تنظیمات", {
        "view": "مشاهده منوی تنظیمات",
        "edit": "مدیریت منوی تنظیمات",
    }),
    "systemSettings": ("تنظیمات کلی سیستم", {
        "view": "مشاهده تنظیمات سیستم",
        "edit": "تغییر تنظیمات سیستم",
    }),
    "reports": ("گزارش‌ها", {
        "view": "مشاهده گزارش‌ها",
        "edit": "مدیریت گزارش‌ها",
        "export": "خروجی گرفتن از گزارش‌ها",
    }),
    "users": ("کاربران", {
        "view": "مشاهده کاربران",
        "edit": "ویرایش کاربران",
        "create": "ایجاد کاربر",
        "deactivate": "فعال یا غیرفعال کردن کاربر",
        "password.reset": "بازنشانی رمز عبور کاربر",
    }),
    "permissions": ("سطح دسترسی", {
        "view": "مشاهده سطح دسترسی",
        "edit": "مدیریت سطح دسترسی",
        "roles.manage": "مدیریت نقش‌ها و مجوزهای نقش",
        "user_overrides.manage": "مدیریت مجوز اختصاصی کاربران",
    }),
    "coins": ("مدیریت توکن", {
        "view": "مشاهده تراکنش‌ها و موجودی توکن",
        "edit": "مدیریت بخش توکن",
        "adjust": "افزایش یا کاهش اعتبار کاربر",
        "transactions.view": "مشاهده تاریخچه تراکنش‌ها",
    }),
}


DEFAULT_ROLE_PAGE_ACCESS = {
    "admin": {page: (True, True) for page in PAGE_ACTIONS},
    "manager": {
        "dashboard": (True, False),
        "users": (True, True),
        "permissions": (False, False),
        "coins": (True, True),
        "reports": (True, False),
        "aiTokens": (True, False),
        "settings": (True, False),
    },
    "user": {
        "dashboard": (True, False),
        "aiTokens": (True, False),
    },
}

EXTRA_ROLE_GRANTS = {
    "manager": {
        "users.create",
        "coins.adjust",
        "aiTokens.deposit.create",
        "aiTokens.withdrawal.create",
    },
    "user": {
        "aiTokens.deposit.create",
        "aiTokens.withdrawal.create",
    },
}


def table_names(cursor: pymysql.cursors.DictCursor) -> set[str]:
    cursor.execute(
        """
        SELECT TABLE_NAME
        FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = DATABASE()
        """
    )
    return {row["TABLE_NAME"] for row in cursor.fetchall()}


def create_missing_tables(
    cursor: pymysql.cursors.DictCursor,
    dry_run: bool = False,
) -> tuple[list[str], list[str]]:
    existing = table_names(cursor)
    created: list[str] = []
    skipped: list[str] = []

    for table_name, ddl in TABLES.items():
        if table_name in existing:
            print(f"SKIP    {table_name} (already exists; left unchanged)")
            skipped.append(table_name)
            continue

        if dry_run:
            print(f"WOULD CREATE {table_name}")
            created.append(table_name)
            continue

        try:
            cursor.execute(ddl)
        except pymysql.err.OperationalError as exc:
            if exc.args and exc.args[0] == 1050:
                print(f"SKIP    {table_name} (created concurrently)")
                skipped.append(table_name)
                continue
            raise

        print(f"CREATED {table_name}")
        created.append(table_name)

    return created, skipped


def seed_base_permissions(cursor: pymysql.cursors.DictCursor) -> None:
    cursor.executemany(
        """
        INSERT IGNORE INTO roles (code, title, description, is_system)
        VALUES (%s, %s, %s, 1)
        """,
        [
            ("admin", "مدیر کل", "دسترسی کامل سامانه"),
            ("manager", "مدیر", "دسترسی مدیریتی محدود و قابل تنظیم"),
            ("user", "کاربر", "دسترسی پایه کاربر"),
        ],
    )

    # Preserve any legacy role strings already assigned to users.
    cursor.execute(
        """
        INSERT IGNORE INTO roles (code, title, description, is_system)
        SELECT DISTINCT role, CONCAT('نقش قدیمی: ', role),
               'مهاجرت‌شده از ستون users.role', 0
        FROM users
        WHERE role IS NOT NULL AND TRIM(role) <> ''
        """
    )

    permission_rows: list[tuple[str, str, str, str, str]] = []
    for page_key, (page_title, actions) in PAGE_ACTIONS.items():
        for action_key, action_title in actions.items():
            code = f"{page_key}.{action_key}"
            permission_rows.append((
                code,
                page_key,
                action_key,
                f"{page_title} - {action_title}",
                f"مجوز {action_title} در صفحه {page_title}",
            ))

    cursor.executemany(
        """
        INSERT IGNORE INTO permissions
            (code, page_key, action_key, title, description)
        VALUES (%s, %s, %s, %s, %s)
        """,
        permission_rows,
    )

    # Retain legacy page_permissions while the existing API still reads it.
    legacy_rows: list[tuple[str, str, int, int]] = []
    for role, pages in DEFAULT_ROLE_PAGE_ACCESS.items():
        for page_key in PAGE_ACTIONS:
            can_view, can_edit = pages.get(page_key, (False, False))
            legacy_rows.append((role, page_key, int(can_view), int(can_edit)))

    cursor.executemany(
        """
        INSERT IGNORE INTO page_permissions
            (role, page_key, can_view, can_edit)
        VALUES (%s, %s, %s, %s)
        """,
        legacy_rows,
    )

    # Link current users to the normalized roles table.
    cursor.execute(
        """
        INSERT IGNORE INTO user_roles (user_id, role_id)
        SELECT u.id, r.id
        FROM users AS u
        INNER JOIN roles AS r ON r.code = u.role
        """
    )

    grants: dict[str, set[str]] = {
        "admin": {
            f"{page_key}.{action_key}"
            for page_key, (_, actions) in PAGE_ACTIONS.items()
            for action_key in actions
        },
        "manager": set(),
        "user": set(),
    }

    for role, pages in DEFAULT_ROLE_PAGE_ACCESS.items():
        if role == "admin":
            continue
        for page_key in PAGE_ACTIONS:
            can_view, can_edit = pages.get(page_key, (False, False))
            if can_view:
                grants[role].add(f"{page_key}.view")
            if can_edit:
                grants[role].add(f"{page_key}.edit")
        grants[role].update(EXTRA_ROLE_GRANTS.get(role, set()))

    # Carry over legacy role-level view/edit settings without overwriting
    # any existing granular permission assignment.
    cursor.execute(
        "SELECT role, page_key, can_view, can_edit FROM page_permissions"
    )
    for row in cursor.fetchall():
        role = row["role"]
        page_key = row["page_key"]
        if page_key not in PAGE_ACTIONS:
            continue
        if row["can_view"]:
            grants.setdefault(role, set()).add(f"{page_key}.view")
        if row["can_edit"]:
            grants.setdefault(role, set()).add(f"{page_key}.edit")

    permission_ids: dict[str, int] = {}
    cursor.execute("SELECT id, code FROM permissions")
    for row in cursor.fetchall():
        permission_ids[row["code"]] = row["id"]

    role_ids: dict[str, int] = {}
    cursor.execute("SELECT id, code FROM roles")
    for row in cursor.fetchall():
        role_ids[row["code"]] = row["id"]

    role_permission_rows: list[tuple[int, int, int]] = []
    for role_code, codes in grants.items():
        role_id = role_ids.get(role_code)
        if role_id is None:
            continue
        for code in codes:
            permission_id = permission_ids.get(code)
            if permission_id is not None:
                role_permission_rows.append((role_id, permission_id, 1))

    if role_permission_rows:
        cursor.executemany(
            """
            INSERT IGNORE INTO role_permissions
                (role_id, permission_id, is_allowed)
            VALUES (%s, %s, %s)
            """,
            role_permission_rows,
        )


def seed_modules(cursor: pymysql.cursors.DictCursor) -> None:
    modules = [
        ("users", "مدیریت کاربران"),
        ("permissions", "نقش‌ها و سطح دسترسی"),
        ("ai", "هوش مصنوعی"),
        ("wallet", "کیف پول و اعتبار"),
        ("system_settings", "تنظیمات سیستم"),
        ("products", "محصولات"),
        ("reports", "گزارش‌ها"),
    ]
    cursor.executemany(
        """
        INSERT IGNORE INTO system_modules (module_key, title, is_enabled)
        VALUES (%s, %s, 1)
        """,
        modules,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create missing Panel Hidary MySQL tables safely."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show which tables would be created without changing the database.",
    )
    args = parser.parse_args()

    connection = None
    try:
        connection = connect()
        with connection.cursor() as cursor:
            cursor.execute("SELECT DATABASE() AS db_name")
            db_name = cursor.fetchone()["db_name"]
            print(f"Connected to MySQL database: {db_name}")

            created, skipped = create_missing_tables(cursor, dry_run=args.dry_run)

            if not args.dry_run:
                seed_base_permissions(cursor)
                seed_modules(cursor)
                print("SEEDED  roles, page permissions, role grants and modules")

            print(
                f"Finished: {len(created)} table(s) created"
                f"{' (planned)' if args.dry_run else ''}, "
                f"{len(skipped)} existing table(s) skipped."
            )
        return 0

    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        if connection is not None:
            connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
