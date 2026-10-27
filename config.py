import os
import json
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
SETTINGS_PATH = BASE_DIR / "settings.json"

# تحميل ملف .env إن وجد
load_dotenv(dotenv_path=ENV_PATH)

DEFAULT_SETTINGS = {
    "is_away": True,
    "owner_name": os.getenv("OWNER_NAME", "صاحب الحساب"),
    "disclose_ai": os.getenv("DISCLOSE_AI", "true").strip().lower() in ("true", "1", "yes"),
    "ignored_users": [],
    "custom_system_prompt": "",
    "cooldown_seconds": 3,
    "max_history_turns": 10
}


def load_settings() -> dict:
    """تحميل الإعدادات المحفوظة من ملف JSON، أو إنشاء إعدادات افتراضية."""
    if not SETTINGS_PATH.exists():
        save_settings(DEFAULT_SETTINGS)
        return DEFAULT_SETTINGS.copy()
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            # دمج مع الإعدادات الافتراضية لأي حقول جديدة
            for k, v in DEFAULT_SETTINGS.items():
                if k not in data:
                    data[k] = v
            return data
    except Exception as e:
        print(f"[تحذير] خطأ في قراءة ملف الإعدادات: {e}. استخدام الإعدادات الافتراضية.")
        return DEFAULT_SETTINGS.copy()


def save_settings(settings: dict) -> None:
    """حفظ الإعدادات في ملف JSON."""
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[خطأ] تعذر حفظ ملف الإعدادات: {e}")


class Config:
    TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID", "").strip()
    TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "").strip()
    TELEGRAM_PHONE = os.getenv("TELEGRAM_PHONE", "").strip()
    TELEGRAM_STRING_SESSION = os.getenv("TELEGRAM_STRING_SESSION", "").strip()
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
    PORT = int(os.getenv("PORT", "8080")) if os.getenv("PORT") else None
    SESSION_NAME = str(BASE_DIR / "userbot_session")

    @classmethod
    def validate(cls) -> list[str]:
        """فحص وجود المتغيرات الأساسية وإرجاع الأخطاء إن وجدت."""
        errors = []
        if not cls.TELEGRAM_API_ID:
            errors.append("TELEGRAM_API_ID مفقود في ملف .env")
        else:
            try:
                int(cls.TELEGRAM_API_ID)
            except ValueError:
                errors.append("TELEGRAM_API_ID يجب أن يكون أرقاماً فقط.")
        if not cls.TELEGRAM_API_HASH:
            errors.append("TELEGRAM_API_HASH مفقود في ملف .env")
        if not cls.GEMINI_API_KEY:
            errors.append("GEMINI_API_KEY مفقود في ملف .env")
        return errors
