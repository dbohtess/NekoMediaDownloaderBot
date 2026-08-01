# Neko Media Downloader Bot 🐾

بوت تيليجرام خاص لتنزيل الفيديوهات من:

- Instagram
- TikTok
- X / Twitter

## التشغيل على الكمبيوتر

أنشئ ملف `.env` محليًا:

```env
BOT_TOKEN=ضع_توكن_البوت
ALLOWED_USERS=ضع_معرف_تيليجرام
```

ثم:

```bash
pip install -r requirements.txt
python bot.py
```

## التشغيل على Render

المشروع مجهز تلقائيًا كـ **Free Web Service** باستخدام:

- `render.yaml`
- `Dockerfile`
- Telegram Webhook

في Render أضف متغيري البيئة فقط:

- `BOT_TOKEN`
- `ALLOWED_USERS`

Render يضيف عنوان الخدمة تلقائيًا، والبوت يحوله إلى Telegram Webhook بدون تعديل يدوي.

## الخصوصية

يمكن إضافة أكثر من مستخدم مفصولين بفاصلة:

```env
ALLOWED_USERS=123456789,987654321
```

الملفات التي يتم تنزيلها مؤقتة وتحذف بعد إرسال الفيديو إلى تيليجرام.
