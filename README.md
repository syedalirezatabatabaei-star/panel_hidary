# پنل شرکت خاقانی نوین سپاهان
پنل مدیریتی فارسی با فرانت‌اند HTML/CSS/JavaScript و API مبتنی بر FastAPI و MySQL.

## راه‌اندازی بک‌اند
1. دیتابیس MySQL با نام `panel_hidary` و charset برابر `utf8mb4` بسازید.
2. وارد پوشه `backend` شوید و `python -m venv .venv` اجرا کنید.
3. محیط مجازی را فعال و `pip install -r requirements.txt` را اجرا کنید.
4. `.env.example` را به `.env` کپی کنید و مقادیر دیتابیس، SECRET_KEY و ADMIN_PASSWORD را حتماً تغییر دهید.
5. از پوشه backend اجرا کنید: `uvicorn app.main:app --reload`

در اولین اجرا جدول‌ها و مدیر اولیه ایجاد می‌شوند. هیچ رمز پیش‌فرض امنی وجود ندارد؛ قبل از اجرا ADMIN_PASSWORD را تنظیم کنید.

## فرانت‌اند
از ریشه مخزن `python -m http.server 5500` را اجرا کنید و `http://127.0.0.1:5500/login/` را باز کنید. آدرس API پیش‌فرض `http://127.0.0.1:8000` است.

## نقش‌ها و سکه
نقش‌های پایه admin، manager و user هستند. دسترسی صفحه‌ای در بک‌اند هم بررسی می‌شود. سکه فعلاً اعتبار داخلی است و نرخ تبدیل AI در این نسخه تعریف نشده است.

## پیش از انتشار
HTTPS، SECRET_KEY تصادفی و محرمانه، رمز قوی مدیر، محدودسازی CORS، rate limit ورود، مدیریت انقضای نشست و پشتیبان‌گیری دیتابیس را پیکربندی کنید. این نسخه اسکلت اولیه است و پیش از production باید تست امنیتی و عملکردی شود.

## Running databases with Docker Compose

Copy `.env.example` to `.env` in the repository root and replace all placeholder passwords with strong random values:

```bash
cp .env.example .env
nano .env
```

The external Docker network `shared_network` must exist. Create it if needed:

```bash
docker network create --driver bridge shared_network
```

Start the databases:

```bash
docker compose up -d
docker compose ps
```

- MySQL: `panel-hidary-mysql:3306`, database `panel_hidary`
- PostgreSQL: `panel-hidary-postgres:5432`, database `panel_hidary_analytics`
- MySQL data volume: `panel_hidary_mysql_data`
- PostgreSQL data volume: `panel_hidary_postgres_data`

Database ports are not published on the host. Containers attached to `shared_network` connect using the service container names. Never commit `.env`.

The backend environment file `backend/.env` is separate. If the backend runs inside Docker on `shared_network`, its MySQL `DATABASE_URL` hostname must be `panel-hidary-mysql`, not `127.0.0.1`.
