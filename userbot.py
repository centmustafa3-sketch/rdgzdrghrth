import asyncio
import logging
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from config import Config, load_settings, save_settings
from ai_engine import AIEngine

logger = logging.getLogger("Userbot")


class TelegramAIResponder:
    def __init__(self):
        self.settings = load_settings()
        self.ai = AIEngine()
        
        session = StringSession(Config.TELEGRAM_STRING_SESSION) if Config.TELEGRAM_STRING_SESSION else Config.SESSION_NAME
        self.client = TelegramClient(
            session,
            int(Config.TELEGRAM_API_ID),
            Config.TELEGRAM_API_HASH
        )
        self.me = None
        
        # بافر لتجميع الرسائل المتتالية من نفس الشخص
        self.message_buffers: dict[int, list[str]] = {}
        self.debounce_tasks: dict[int, asyncio.Task] = {}

    def is_away(self) -> bool:
        self.settings = load_settings()
        return self.settings.get("is_away", True)

    def set_away(self, status: bool) -> None:
        self.settings = load_settings()
        self.settings["is_away"] = status
        save_settings(self.settings)

    async def start(self):
        """بدء تشغيل عميل تليجرام وتسجيل معالجات الأحداث."""
        await self.client.start(phone=Config.TELEGRAM_PHONE if Config.TELEGRAM_PHONE else None)
        self.me = await self.client.get_me()
        logger.info(f"تم تسجيل الدخول بنجاح بحساب: {self.me.first_name} (@{self.me.username or 'بدون معرف'}) [ID: {self.me.id}]")

        # تسجيل معالج الرسائل الواردة
        self.client.add_event_handler(self.handle_incoming, events.NewMessage(incoming=True))
        # تسجيل معالج أوامر التحكم في الرسائل المحفوظة (Saved Messages)
        self.client.add_event_handler(self.handle_control_commands, events.NewMessage(outgoing=True))

        # تشغيل سيرفر خفيف لفحص الحالة على السيرفرات السحابية (Render / Koyeb) إن وجد منفذ PORT
        if Config.PORT:
            asyncio.create_task(self._start_healthcheck_server(Config.PORT))

        print("\n" + "=" * 55)
        print("🤖 بوت المساعد الذكي لتليجرام يعمل الآن بنجاح!")
        print(f"👤 الحساب: {self.me.first_name} (ID: {self.me.id})")
        print(f"🛌 وضع الغياب (Auto-Reply): {'مُفعّل (ON)' if self.is_away() else 'مُعطّل (OFF)'}")
        print("💡 للتحكم بالبوت: افتح 'الرسائل المحفوظة' (Saved Messages) في تليجرام واكتب .help")
        print("=" * 55 + "\n")

        await self.client.run_until_disconnected()

    async def _start_healthcheck_server(self, port: int):
        """سيرفر HTTP فائق الخفة لإبقاء الخدمة حية على الاستضافات السحابية المجانية."""
        async def handle_client(reader, writer):
            try:
                await reader.read(1024)
                resp = b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 2\r\n\r\nOK"
                writer.write(resp)
                await writer.drain()
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

        try:
            server = await asyncio.start_server(handle_client, "0.0.0.0", port)
            logger.info(f"سيرفر فحص الاتصال السحابي (Healthcheck) يعمل على المنفذ: {port}")
        except Exception as e:
            logger.warning(f"تعذر تشغيل سيرفر Healthcheck: {e}")

    async def handle_incoming(self, event: events.NewMessage.Event):
        """معالجة الرسائل الواردة في المحادثات الخاصة."""
        # نتجاهل المجموعات والقنوات، نهتم فقط بالخاص
        if not event.is_private:
            return

        sender = await event.get_sender()
        if not sender:
            return

        # تجاهل البوتات وحسابات تليجرام الرسمية ورسائل النفس
        if sender.bot or sender.id == 777000 or sender.id == self.me.id:
            return

        # إذا كان وضع الغياب متوقفاً، لا نرد تلقائياً
        if not self.is_away():
            return

        # التحقق من قائمة التجاهل (Blacklist)
        ignored = self.settings.get("ignored_users", [])
        sender_username = (sender.username or "").lower()
        if sender.id in ignored or f"@{sender_username}" in ignored:
            logger.info(f"تجاهل رسالة من مستخدم محظور: {sender.id} (@{sender_username})")
            return

        incoming_text = event.raw_text.strip()
        if not incoming_text:
            return

        chat_id = event.chat_id
        sender_name = sender.first_name or "صديقي"

        # تجميع الرسائل المتتالية (Debounce)
        if chat_id not in self.message_buffers:
            self.message_buffers[chat_id] = []
        self.message_buffers[chat_id].append(incoming_text)

        # إلغاء المؤقت السابق إن وُجد وبدء مؤقت جديد
        if chat_id in self.debounce_tasks and not self.debounce_tasks[chat_id].done():
            self.debounce_tasks[chat_id].cancel()

        self.debounce_tasks[chat_id] = asyncio.create_task(
            self._delayed_reply(chat_id, sender_name)
        )

    async def _delayed_reply(self, chat_id: int, sender_name: str):
        """الانتظار قليلاً ثم الرد على مجموع الرسائل دفعة واحدة ليبدو الرد واقعياً."""
        try:
            # انتظار ثانيتين لجمع أي رسائل متتالية أخرى
            await asyncio.sleep(2.5)

            buffered = self.message_buffers.pop(chat_id, [])
            if not buffered:
                return

            full_text = "\n".join(buffered)
            logger.info(f"معالجة رسالة من {sender_name} [{chat_id}]: {full_text}")

            # محاكاة علامة القراءة (Seen)
            try:
                await self.client.send_read_acknowledge(chat_id)
            except Exception:
                pass

            # إظهار حالة "يكتب الآن... / typing" لمدة قصيرة تعكس التفكير البشري
            async with self.client.action(chat_id, "typing"):
                # استدعاء الذكاء الاصطناعي في خيط منفصل لعدم تجميد الأحداث
                reply = await asyncio.to_thread(
                    self.ai.generate_reply, chat_id, sender_name, full_text
                )
                # انتظار ثانية إضافية لإعطاء شعور الكتابة الواقعية
                await asyncio.sleep(1.5)

            # إرسال الرد
            await self.client.send_message(chat_id, reply)
            logger.info(f"تم إرسال الرد إلى {sender_name}: {reply}")

        except asyncio.CancelledError:
            # تم إلغاؤه لأن هناك رسالة جديدة وصلت في فترة التجميع
            pass
        except Exception as e:
            logger.error(f"خطأ أثناء معالجة الرد التلقائي: {e}")

    async def handle_control_commands(self, event: events.NewMessage.Event):
        """معالجة أوامر التحكم الصادرة من المستخدم في محادثة 'الرسائل المحفوظة'."""
        # نتحقق من أن الرسالة في الرسائل المحفوظة الخاصة بالحساب (Saved Messages)
        if event.chat_id != self.me.id:
            return

        text = event.raw_text.strip()
        if not text.startswith("."):
            return

        parts = text.split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1].strip() if len(parts) > 1 else ""

        if cmd in (".help", ".مساعدة", ".اوامر"):
            help_text = (
                "🤖 **لوحة تحكم المساعد الذكي لتليجرام**\n\n"
                "• `.away on` : تفعيل الرد التلقائي (أنا نائم / غير متفرغ).\n"
                "• `.away off` : إيقاف الرد التلقائي (أنا متاح الآن).\n"
                "• `.status` : عرض الحالة الحالية والإحصائيات.\n"
                "• `.setname [الاسم]` : تغيير اسم صاحب الحساب لدى الـ AI.\n"
                "• `.disclose on` : الـ AI يوضح للناس بلطف أنه مساعدك الذكي.\n"
                "• `.disclose off` : الـ AI يتحدث بأسلوبك كأنه أنت تماماً.\n"
                "• `.prompt [نص التعليمات]` : تخصيص شخصية أو تعليمات الـ AI.\n"
                "• `.resetprompt` : استعادة التعليمات الافتراضية الذكية.\n"
                "• `.ignore [id أو @username]` : تجاهل شخص وعدم الرد عليه.\n"
                "• `.unignore [id أو @username]` : إزالة شخص من قائمة التجاهل.\n"
                "• `.clear` : مسح ذاكرة وسياق المحادثات السابقة.\n"
            )
            await event.reply(help_text)

        elif cmd == ".away":
            arg = args.lower()
            if arg in ("on", "1", "تفعيل", "شغال"):
                self.set_away(True)
                await event.reply("✅ **تم تفعيل وضع الغياب!**\nسيرد الذكاء الاصطناعي الآن تلقائياً وبشكل طبيعي على أي رسالة خاصة تصلك.")
            elif arg in ("off", "0", "ايقاف", "تعطيل"):
                self.set_away(False)
                await event.reply("⏸️ **تم إيقاف وضع الغياب!**\nلن يرد الـ AI تلقائياً الآن، ويمكنك التحدث بنفسك بحرية.")
            else:
                current = "مُفعّل (ON) 🟢" if self.is_away() else "مُعطّل (OFF) 🔴"
                await event.reply(f"حالة وضع الغياب حالياً: {current}\nللتغيير اكتب:\n`.away on` أو `.away off`")

        elif cmd == ".status":
            self.settings = load_settings()
            away_str = "مُفعّل 🟢 (يرد على الرسائل)" if self.settings.get("is_away", True) else "مُعطّل 🔴 (صامت)"
            disclose_str = "نعم (يوضح أنه مساعد AI)" if self.settings.get("disclose_ai", True) else "لا (يتكلم باسمك مباشرة)"
            owner = self.settings.get("owner_name", "غير محدد")
            ignored_count = len(self.settings.get("ignored_users", []))
            active_chats = len(self.ai.conversations)

            status_text = (
                "📊 **حالة البوت الحالية:**\n\n"
                f"• **وضع الغياب:** {away_str}\n"
                f"• **اسم صاحب الحساب:** {owner}\n"
                f"• **موديل الذكاء الاصطناعي:** `{Config.GEMINI_MODEL}`\n"
                f"• **توضيح الهوية:** {disclose_str}\n"
                f"• **المحادثات النشطة في الذاكرة:** {active_chats}\n"
                f"• **عدد المستبعدين:** {ignored_count}\n"
            )
            await event.reply(status_text)

        elif cmd == ".setname":
            if not args:
                await event.reply("⚠️ يرجى كتابة الاسم بعد الأمر، مثال: `.setname أحمد`")
                return
            self.settings = load_settings()
            self.settings["owner_name"] = args
            save_settings(self.settings)
            self.ai.refresh_settings()
            await event.reply(f"✅ تم تحديث اسم صاحب الحساب إلى: **{args}**")

        elif cmd == ".disclose":
            arg = args.lower()
            self.settings = load_settings()
            if arg in ("on", "1", "نعم"):
                self.settings["disclose_ai"] = True
                save_settings(self.settings)
                self.ai.refresh_settings()
                await event.reply("✅ تم تفعيل توضيح الهوية: الـ AI سيوضح للطرف الآخر أنه مساعدك الذكي.")
            elif arg in ("off", "0", "لا"):
                self.settings["disclose_ai"] = False
                save_settings(self.settings)
                self.ai.refresh_settings()
                await event.reply("✅ تم إيقاف توضيح الهوية: الـ AI سيتحدث بأسلوبك كأنك أنت تماماً.")
            else:
                await event.reply("⚠️ استخدم `.disclose on` أو `.disclose off`")

        elif cmd == ".prompt":
            if not args:
                await event.reply("⚠️ يرجى كتابة التعليمات المراد توجيه الـ AI بها، مثال:\n`.prompt تصرف كخبير تقني مرح وأجب باختصار`")
                return
            self.settings = load_settings()
            self.settings["custom_system_prompt"] = args
            save_settings(self.settings)
            self.ai.refresh_settings()
            await event.reply(f"✅ **تم تحديث برومبت الذكاء الاصطناعي:**\n\n_{args}_")

        elif cmd == ".resetprompt":
            self.settings = load_settings()
            self.settings["custom_system_prompt"] = ""
            save_settings(self.settings)
            self.ai.refresh_settings()
            await event.reply("✅ تم استعادة البرومبت الافتراضي الذكي بنجاح.")

        elif cmd == ".ignore":
            if not args:
                await event.reply("⚠️ اكتب المعرف أو الرقم بعد الأمر، مثال: `.ignore @username`")
                return
            target = int(args) if args.lstrip("-").isdigit() else args.lower()
            self.settings = load_settings()
            ignored = self.settings.get("ignored_users", [])
            if target not in ignored:
                ignored.append(target)
                self.settings["ignored_users"] = ignored
                save_settings(self.settings)
                await event.reply(f"🚫 تم إضافة `{target}` إلى قائمة التجاهل (لن يتم الرد عليه).")
            else:
                await event.reply(f"ℹ️ `{target}` موجود بالفعل في قائمة التجاهل.")

        elif cmd == ".unignore":
            if not args:
                await event.reply("⚠️ اكتب المعرف أو الرقم بعد الأمر، مثال: `.unignore @username`")
                return
            target = int(args) if args.lstrip("-").isdigit() else args.lower()
            self.settings = load_settings()
            ignored = self.settings.get("ignored_users", [])
            if target in ignored:
                ignored.remove(target)
                self.settings["ignored_users"] = ignored
                save_settings(self.settings)
                await event.reply(f"✅ تم إزالة `{target}` من قائمة التجاهل.")
            else:
                await event.reply(f"ℹ️ `{target}` غير موجود في قائمة التجاهل.")

        elif cmd == ".clear":
            self.ai.clear_history()
            await event.reply("🧹 تم مسح ذاكرة وسياق كل المحادثات السابقة بنجاح.")
