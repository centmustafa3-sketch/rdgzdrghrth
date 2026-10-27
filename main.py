import sys
import logging
import asyncio
from config import Config
from userbot import TelegramAIResponder

# تهيئة نظام التسجيل (Logging)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)


def main():
    print("""
    ==================================================
        🚀 Telegram AI Auto-Responder (Userbot)
        مساعد الذكاء الاصطناعي لحساب تليجرام الشخصي
    ==================================================
    """)

    # فحص الإعدادات الأساسية
    errors = Config.validate()
    if errors:
        print("❌ تنبيه: هناك إعدادات مفقودة في ملف .env:\n")
        for err in errors:
            print(f"  • {err}")
        print("\n💡 يُرجى فتح ملف .env وإدخال بياناتك، أو تشغيل معالج الإعداد التفاعلي:")
        print("   python setup_and_login.py\n")
        sys.exit(1)

    responder = TelegramAIResponder()
    try:
        asyncio.run(responder.start())
    except KeyboardInterrupt:
        print("\n👋 تم إيقاف البوت بنجاح. مع السلامة!")
    except Exception as e:
        print(f"\n❌ حدث خطأ غير متوقع: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
