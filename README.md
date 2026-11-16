# 🎬 محمّل الفيديوهات — Video Downloader

تطبيق ويب بسيط كيخليك تيليشارجي أي فيديو من **YouTube، Facebook، Instagram، TikTok، X** وأكثر من 1000 منصة، وتختار واش بغيتي **فيديو (MP4)** ولا **صوت فقط (MP3 / M4A / WAV / OPUS)**.

مبني بـ Flask + [yt-dlp](https://github.com/yt-dlp/yt-dlp).

## التشغيل

خاصك **Python 3.10+** و **ffmpeg** يكونو مثبتين.

```bash
pip install -r requirements.txt
python app.py
```

ومن بعد حل المتصفح على http://localhost:5000

فـ Windows تقدر غير تكليكي جوج مرات على `start.bat`.

## ملاحظات

- الفيديوهات الخاصة ولا اللي خاصها تسجيل الدخول ما كتتيليشارجاش.
- إلى شي منصة وقفات، حدّث yt-dlp: `pip install -U yt-dlp`
- الملفات كتتمسح أوتوماتيكيا من الدوسي `downloads` من بعد ساعة.
- حمّل غير المحتوى اللي عندك الحق فيه.
