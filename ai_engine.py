import time
import logging
from collections import deque
from google import genai
from google.genai import types
from config import Config, load_settings

logger = logging.getLogger("AIEngine")


class AIEngine:
    def __init__(self):
        self.settings = load_settings()
        self.api_key = Config.GEMINI_API_KEY
        self.model_name = Config.GEMINI_MODEL
        self.client = None
        
        # تخزين سجل المحادثة لكل مستخدم: {chat_id: deque([types.Content, ...])}
        self.conversations: dict[int, deque] = {}
        # وقت آخر رسالة لكل محادثة لتنظيف المحادثات القديمة
        self.last_active: dict[int, float] = {}

        if self.api_key:
            try:
                self.client = genai.Client(api_key=self.api_key)
                logger.info(f"تم تهيئة Google Gemini API بنجاح بموديل: {self.model_name}")
            except Exception as e:
                logger.error(f"خطأ في تهيئة Google Gemini: {e}")

    def refresh_settings(self):
        """تحديث الإعدادات من ملف settings.json"""
        self.settings = load_settings()

    def _build_system_instruction(self, user_name: str) -> str:
        """بناء التعليمات التوجيهية للذكاء الاصطناعي مع مراعاة تخصيص المستخدم."""
        self.refresh_settings()
        owner_name = self.settings.get("owner_name", "صاحب الحساب")
        disclose_ai = self.settings.get("disclose_ai", True)
        custom_prompt = self.settings.get("custom_system_prompt", "").strip()

        if custom_prompt:
            # إذا وضع المستخدم برومبت مخصص بنفسه
            return f"{custom_prompt}\nاسم صاحب الحساب: {owner_name}\nاسم الشخص الذي يراسلك الآن: {user_name}"

        if disclose_ai:
            return (
                f"أنت المساعد الذكي الخاص بـ '{owner_name}' على تليجرام.\n"
                f"صاحب الحساب ({owner_name}) غير متواجد حالياً (قد يكون نائماً، منشغلاً في اجتماع، أو بعيداً عن جهازه).\n"
                f"الشخص الذي يراسلك اسمه: '{user_name}'.\n\n"
                "تعليماتك وأسلوب حديثك:\n"
                "1. كن طبيعياً وودوداً وذكياً جداً. تحدث بأسلوب حواري عفوي وسلس يشبه المحادثات اليومية في تليجرام.\n"
                "2. إذا كانت هذه أول رسالة، وضح بلطف واختصار أنك مساعد الذكاء الاصطناعي لـ "
                f"{owner_name} لأن صاحب الحساب غير متفرغ الآن، وأنك مستعد للنقاش معه أو أخذ أي رسالة مهمة منه.\n"
                "3. ناقش أي موضوع يطرحه السائل: سواء سؤال تقني، عملي، استفسار، دردشة عادية، أو نقاش عام.\n"
                "4. تكيف مع لغة ولهجة السائل (إن تحدث بالسعودي، المصري، العراقي، الشامي، أو الفصحى، جارِه بلهجته بطريقة طبيعية دون تصنع).\n"
                "5. إذا سأل عن أمور شخصية أو خاصة بـ "
                f"{owner_name} لا تعرفها، أخبره بابتسامة ولباقة أنك ستسجل له الرسالة وسيراه {owner_name} بنفسه فور عودته.\n"
                "6. لا تجعل رسائلك طويلة جداً أو مبالغاً في رسميتها، اجعلها قصيرة ومناسبة لتليجرام.\n"
            )
        else:
            return (
                f"أنت تتحدث نيابة عن '{owner_name}' في تليجرام.\n"
                f"أنت ({owner_name}) حالياً شبه نائم أو منشغل جداً.\n"
                f"الشخص الذي يراسلك هو: '{user_name}'.\n\n"
                "تعليمات أسلوب المحادثة:\n"
                "1. تحدث كإنسان حقيقي 100% بأسلوب عفوي وشخصي ومريح تماماً بدون أي ملامح للروبوتات.\n"
                "2. لا تذكر أنك ذكاء اصطناعي، وتصرف كأنك صاحب الحساب وترد على السريع من الهاتف.\n"
                "3. جارِ الشخص في لهجته وأسلوبه، وناقشه في أسئلته ومواضيعه بذكاء وود.\n"
                "4. إذا طُلب منك شيء يتطلب قراراً حاسماً أو موعداً في الواقع، قل: 'أنا شوي منشغل/نعسان الآن، بس أصحى/أفضى برجع أكلمك وأرتب معك بالتفصيل!'.\n"
                "5. اجعل الردود خفيفة وطبيعية كأي محادثة تليجرام شخصية."
            )

    def generate_reply(self, chat_id: int, user_name: str, incoming_text: str) -> str:
        """توليد رد ذكي مع الحفاظ على سياق المحادثة لكل مستخدم."""
        if not self.client:
            return "عذراً، لم يتم ضبط مفتاح Gemini API بشكل صحيح. يرجى مراجعة إعدادات البوت."

        self.refresh_settings()
        max_turns = self.settings.get("max_history_turns", 10)

        # تهيئة سجل المحادثة إن لم يكن موجوداً
        now = time.time()
        # إذا مر أكثر من ساعتين على آخر رسالة، نبدأ سياق جديد لتجنب الخلط
        if chat_id in self.last_active and (now - self.last_active[chat_id] > 7200):
            self.conversations[chat_id] = deque(maxlen=max_turns * 2)
        
        if chat_id not in self.conversations:
            self.conversations[chat_id] = deque(maxlen=max_turns * 2)

        history = self.conversations[chat_id]
        self.last_active[chat_id] = now

        # إضافة رسالة المستخدم الجديدة إلى التاريخ
        user_content = types.Content(
            role="user",
            parts=[types.Part.from_text(text=incoming_text)]
        )
        history.append(user_content)

        # إعداد نظام التعليمات
        system_instruction = self._build_system_instruction(user_name)

        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.8,
            max_output_tokens=600,
        )

        try:
            # إرسال التاريخ بالكامل للحفاظ على الحوار المتصل
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=list(history),
                config=config,
            )

            reply_text = response.text.strip() if response.text else "تم استقبال رسالتك وسأرد عليك قريباً!"

            # إضافة رد الموديل إلى التاريخ
            model_content = types.Content(
                role="model",
                parts=[types.Part.from_text(text=reply_text)]
            )
            history.append(model_content)

            return reply_text

        except Exception as e:
            logger.error(f"خطأ أثناء توليد الرد من Gemini: {e}")
            return "أهلاً بك! صاحب الحساب غير متاح حالياً، وسيقرأ رسالتك ويرد عليك فور استيقاظه أو فراغه."

    def clear_history(self, chat_id: int | None = None):
        """مسح ذاكرة المحادثة لمستخدم معين أو للجميع."""
        if chat_id is not None:
            if chat_id in self.conversations:
                del self.conversations[chat_id]
        else:
            self.conversations.clear()
            self.last_active.clear()
