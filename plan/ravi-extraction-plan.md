# طرح اجرایی جامع استخراج ماژول/پروژه Ravi به مخزن مستقل Git و پاکسازی کامل از مخزن فعلی

نسخه سند: 1.2  
وضعیت: اجرایی و نهایی  
تاریخ تدوین: نوامبر ۲۰۲۶  

---

## ۱. مقدمه و هدف

هدف از این طرح اجرایی، جداسازی کامل و بی‌دغدغه زیرساخت هوش مصنوعی **Ravi** از مخزن مونوپورت فعلی (`soroush-zendedel.github.io`) و انتقال آن به یک مخزن مستقل و متن‌باز به نام `ravi` با مجوز MIT است؛ به‌گونه‌ای که هیچ‌گونه اثر، فایل، متغیر یا وابستگی سرگردانی از Ravi در مخزن میزبان باقی نماند و در عین حال، داده‌های پایدار (Persistent Volumes)، تنظیمات پرووایدرها، و پچ حیاتی Cloudflare بدون کوچک‌ترین آسیبی حفظ شوند.

---

## ۲. رویکرد ساخت شاخه جدید (Branch-First Extraction Strategy)

به منظور مدیریت دقیق روند جداسازی و حفظ تاریخچه پروژه‌های مرتبط، مراحل استخراج با ساختار شاخه‌ای به شرح زیر انجام می‌شود:

1. **ساخت شاخه `ravi`:**
   یک شاخه مستقل به نام `ravi` از وضعیت فعلی مخزن مونوپورت ساخته می‌شود.
2. **انتقال و سازماندهی در پوشه اختصاصی درون شاخه:**
   درون این شاخه، تمامی فایل‌های مرتبط با Ravi به یک پوشه مستقل منتقل و سازماندهی می‌شوند تا ساختار نهایی مخزن `ravi` شکل بگیرد.
3. **قطع اتصال از `main` (تبدیل به مخزن مستقل):**
   این شاخه به مخزن `main` ادغام (Merge) **نخواهد شد**؛ بلکه به عنوان پایه و مبنای یک مخزن Git جدید و مستقل (`ravi`) استفاده خواهد شد تا کاملاً از مخزن `soroush-zendedel.github.io` جدا شود.

---

## ۳. فهرست دارایی‌ها و فایل‌های مرتبط با Ravi در مخزن فعلی

پیش از شروع استخراج، دارایی‌های زیر که مربوط به Ravi و زیرساخت LiteLLM هستند شناسایی شده‌اند و باید با دقت مدیریت شوند:

1. **فایل‌های پیکربندی و محیطی:**
   - [`config.yaml`](config.yaml): حاوی تعریف مدل‌های Cloudflare Workers AI و Google Gemini.
   - `.env` و `.env.example`: حاوی کلیدهای امنیتی (`LITELLM_MASTER_KEY`، `CLOUDFLARE_API_TOKEN`، `POSTGRES_PASSWORD`).
   - [`docker-compose.yml`](docker-compose.yml): تعریف سرویس‌های `ravi-redis`، `ravi-postgres` و `ravi-proxy` (با نام‌گذاری‌های اختصاصی Ravi).

2. **پچ‌های اختصاصی کد:**
   - [`docker/litellm/transformation.py`](docker/litellm/transformation.py): پچ اختصاصی برای رفع مشکل قالب آرایه‌ای پیام‌های Cloudflare در LiteLLM (`v1.106.6`).

3. **اسکریپت‌های مدیریت محلی:**
   - `scripts/Start-Ravi.ps1`
   - `scripts/Stop-Ravi.ps1`

4. **اسناد پایه:**
   - [`ravi.main.md`](ravi.main.md): سند اصلی معماری و پروپوزال Ravi.

5. **داده‌های پایدار و پایگاه داده (Docker Volumes & Database Names):**
   - نام پایگاه داده PostgreSQL: `ravi` (به جای `litellm`)
   - نام Volumeهای پایدار داکر:
     - `ravi_redis_data`
     - `ravi_postgres_data`
   *(نکته حیاتی: اجرای دستورات مخرب مانند `docker compose down -v` ممنوع است مگر هنگام migration کامل با داشتن پشتیبان `pg_dump`.)*

---

## ۴. ساختار پیشنهادی مخزن مستقل `ravi`

مخزن جدید `ravi` با ساختار ماژولار زیر ایجاد خواهد شد:

```text
ravi/
├── README.md
├── LICENSE (MIT)
├── CONTRIBUTING.md
├── SECURITY.md
├── CHANGELOG.md
├── ROADMAP.md
├── .gitignore
├── .dockerignore
├── .env.example
├── config.yaml
├── docker-compose.yml
├── docker/
│   └── litellm/
│       └── transformation.py
├── docs/
│   ├── architecture/
│   ├── api/
│   └── deployment/
├── src/
│   ├── core/
│   ├── integrations/
│   └── routing/
├── tests/
│   ├── unit/
│   └── integration/
└── scripts/
    ├── Start-Ravi.ps1
    └── Stop-Ravi.ps1
```

---

## ۵. مراحل گام‌به‌گام اجرایی

### گام اول: ایجاد شاخه مستقل `ravi` در مخزن فعلی
1. ساخت و انتقال به شاخه جدید:
   ```powershell
   git checkout -b ravi
   ```
2. سازماندهی و انتقال فایل‌های مربوط به زیرساخت هوش مصنوعی به ساختار استاندارد مخزن `ravi`.

### گام دوم: آماده‌سازی و پشتیبان‌گیری از داده‌ها و تنظیمات موجود
1. تهیه پشتیبان کامل (`pg_dump`) از پایگاه داده فعلی و فایل‌های [`config.yaml`](config.yaml)، [`docker-compose.yml`](docker-compose.yml)، `.env` و [`docker/litellm/transformation.py`](docker/litellm/transformation.py).
2. مستندسازی و نام‌گذاری جدید Volumeها و پایگاه داده با پیشوند رسمی `ravi`.
3. اطمینان از سلامت کانتینرها و ثبت تست‌های موفقیت‌آمیز API پیش از جابجایی.

### گام سوم: تنظیم و تست استقرار مستقل Ravi با نام‌گذاری‌های جدید (`ravi`)
1. به‌روزرسانی `docker-compose.yml` در مخزن مستقل Ravi با اعمال تغییرات زیر:
   - تغییر نام پایگاه داده به `ravi` (`POSTGRES_DB: ravi`).
   - تغییر نام Volumeهای داکر به `ravi_redis_data` و `ravi_postgres_data`.
   - تغییر نام کانتینرها به `ravi-redis`، `ravi-postgres` و `ravi-proxy` جهت تفکیک کامل از نام‌های قبلی `litellm-...`.
2. تنظیم فایل `.env` نمونه (`.env.example`) بدون قرار دادن کلیدهای واقعی و با متغیرهای اختصاصی `RAVI_MASTER_KEY` / `LITELLM_MASTER_KEY`.
3. راه‌اندازی محیط مستقل با دستور:
   ```powershell
   docker compose up -d --build
   ```
4. تست Health Check و ارسال درخواست‌های تستی (متنی و آرایه‌ای) به آدرس `http://127.0.0.1:4000/chat/completions` جهت اطمینان از صحت عملکرد پچ Cloudflare در مخزن جدید.

### گام چهارم: پاکسازی کامل آثار Ravi از شاخه و مخزن مونوپورت اصلی (`main` در `soroush-zendedel.github.io`)
پس از جدا شدن کامل شاخه `ravi` و تبدیل آن به ریپازیتوری مستقل:
1. بازگشت به شاخه `main` در مخزن مونوپورت.
2. حذف فایل [`docker/litellm/transformation.py`](docker/litellm/transformation.py).
3. حذف اسکریپت‌های مرتبط با LiteLLM.
4. حذف `config.yaml`، `docker-compose.yml` و فایل‌های وابسته به LiteLLM از ریشه مخزن فعلی.
5. پاکسازی متغیرهای محیطی مرتبط با Ravi از فایل‌های `.env` و `.env.example` در مخزن مونوپورت.
6. به‌روزرسانی [`README.md`](README.md) و مستندات پروژه مونوپورت (DevOS) به منظور اشاره به مخزن مستقل Ravi به عنوان سرویس خارجی (External AI Infrastructure).

### گام پنجم: بازبینی نهایی و انتشار
1. اجرای اعتبارسنجی نهایی روی هر دو پروژه (مخزن مستقل Ravi و مخزن پاکسازی‌شده DevOS).
2. ثبت تگ نسخه اولیه `v0.1.0` روی مخزن Ravi.
3. انتشار مستندات نحوه اتصال پروژه‌های مصرف‌کننده (مانند DevOS) به API مستقل Ravi.

---

## ۶. نکات ایمنی و مدیریتی مهم
- **حفظ Volumeها و نام‌گذاری جدید:** Volumeهای جدید با نام‌های `ravi_redis_data` و `ravi_postgres_data` و دیتابیس `ravi` ایجاد می‌شوند. در صورت نیاز به انتقال داده‌های قبلی، باید اطلاعات با دستور `pg_dump` استخراج شده و پس از بالا آمدن دیتابیس جدید `ravi`, به آن Import شود.
- **امنیت کلیدها:** به هیچ عنوان `CLOUDFLARE_API_TOKEN` یا کلیدهای امنیتی در هیچ‌یک از commitهای گیت قرار نگیرند.
- **استقلال کامل:** پروژه DevOS پس از این تغییرات نباید هیچ‌گونه وابستگی کدی یا داکری مستقیم به فایل‌های داخلی Ravi داشته باشد و صرفاً از طریق آدرس شبکه و API Key با آن ارتباط برقرار کند.
