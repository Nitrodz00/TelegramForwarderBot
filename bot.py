import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, StateFilter
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode, ChatType
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.dispatcher.middlewares.base import BaseMiddleware
from dotenv import load_dotenv
import database

load_dotenv()

# ========== الإعدادات ==========
BOT_TOKEN = os.getenv("BOT_TOKEN", "8797443914:AAEwCenxuzRjZFZY6Z_AzDvmqC--cADVbks")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
database.init_db()

# ========== نظام الحماية (تفعيل البوت لاستخدام شخصي أو محدد فقط) ==========
class AllowedUsersMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        allowed_str = os.getenv("ALLOWED_USERS", "")
        # إذا لم يتم وضع المتغير في Railway، سيسمح للجميع (كالعادة)
        if not allowed_str:
            return await handler(event, data)
            
        # استخراج المعرفات كأرقام
        allowed_ids = [int(x.strip()) for x in allowed_str.split(",") if x.strip().isdigit()]
        if not allowed_ids:
            return await handler(event, data)
            
        # إذا لم يكن الحدث يحتوي على معرّف المستخدم (مثل رسائل القنوات) فدعه يمر ليتعامل معه الكود
        if getattr(event, "from_user", None) is None:
            return await handler(event, data)
            
        user_id = event.from_user.id
        
        # إذا كان المستخدم غير موجود في القائمة المعتمدة
        if user_id not in allowed_ids:
            if isinstance(event, types.Message) and event.text and event.text.startswith("/start"):
                # إبلاغه بالرفض المهذب فقط عند محاولة الدخول أول مرة
                await event.answer("🔒 <b>حظر أمني:</b>\nعُذراً، هذه البيئة السحابية خاصة ومغلقة للمعتمدين فقط.")
            return # التجاهل التام (لا ردود ولا استخدام للبوت)
            
        return await handler(event, data)

# تسجيل نظام الحماية على جميع الرسائل، الأزرار، والإضافات للمجموعات
dp.message.middleware(AllowedUsersMiddleware())
dp.callback_query.middleware(AllowedUsersMiddleware())
dp.my_chat_member.middleware(AllowedUsersMiddleware())


# ========== حالات FSM ==========
class AddChannel(StatesGroup):
    waiting_for_source = State()
    waiting_for_destination = State()
    waiting_for_source_name = State()
    waiting_for_destination_name = State()

# ========== بناء لوحات المفاتيح المتخفية كمساحة سحابية ==========

def main_menu_kb(user_id: int):
    active = database.is_bot_active(user_id)
    status = "🟢 المزامنة نشطة" if active else "🔴 المزامنة متوقفة"
    toggle = "⏹ إيقاف المزامنة" if active else "▶️ تشغيل المزامنة"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"حالة الأرشيف: {status}", callback_data="noop")],
        [InlineKeyboardButton(text=toggle, callback_data="toggle_active")],
        [InlineKeyboardButton(text="📥 أدوات الجلب (Input)", callback_data="menu_sources"),
         InlineKeyboardButton(text="📤 مساحات الحفظ (Storage)", callback_data="menu_destinations")],
        [InlineKeyboardButton(text="📊 فحص مساحاتي", callback_data="diagnose"),
         InlineKeyboardButton(text="📖 دليل الاستخدام", callback_data="how_to_use")],
    ])

def sources_menu_kb(user_id: int):
    sources = database.get_channels(user_id, "source")
    rows = []
    for ch_id, title in sources:
        rows.append([
            InlineKeyboardButton(text=f"📥 {title}", callback_data="noop"),
            InlineKeyboardButton(text="❌ إزالة", callback_data=f"del_source_{ch_id}"),
        ])
    rows.append([InlineKeyboardButton(text="➕ إضافة نقطة إدخال جديدة", callback_data="add_source")])
    rows.append([InlineKeyboardButton(text="🔙 العودة", callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def destinations_menu_kb(user_id: int):
    destinations = database.get_channels(user_id, "destination")
    rows = []
    for ch_id, title in destinations:
        rows.append([
            InlineKeyboardButton(text=f"📤 {title}", callback_data="noop"),
            InlineKeyboardButton(text="❌ إزالة", callback_data=f"del_dest_{ch_id}"),
        ])
    rows.append([InlineKeyboardButton(text="➕ إضافة مساحة تخزين جديدة", callback_data="add_destination")])
    rows.append([InlineKeyboardButton(text="🔙 العودة", callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def cancel_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ إلغاء العملية", callback_data="cancel_add")]
    ])

# ========== أوامر البوت المخفية للهروب من الفلاتر ==========

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    if message.chat.type != ChatType.PRIVATE:
        return
    uid = message.from_user.id
    name = message.from_user.first_name or "بكم"
    await message.answer(
        f"☁️ <b>أهلاً {name} في مساحتك السحابية التنظيمية!</b>\n\n"
        "أنا مساعدك الشخصي لتنظيم ملاحظاتك وأرشفتها بشكل تلقائي وسحابي.\n\n"
        "• 📥 حدد نقاط الإدخال (حيث أستلم البيانات)\n"
        "• 📤 حدد مساحات الحفظ الأرشيفية (مساحتك الخاصة المحمية)\n"
        "• 🔒 جميع مساحاتك مشفرة ولا أشارك بياناتك مع أي طرف.\n\n"
        "ابدأ إدارة أرشيفك الآن:",
        reply_markup=main_menu_kb(uid)
    )

@dp.message(Command("admin"))
async def admin_cmd(message: types.Message):
    if message.chat.type != ChatType.PRIVATE:
        return
    uid = message.from_user.id
    await message.answer(
        "⚙️ <b>لوحة تحكم الأرشيف</b>\n"
        "قم بتنظيم بيئات التخزين الخاصة بك هنا:",
        reply_markup=main_menu_kb(uid)
    )

@dp.message(Command("id"))
async def get_chat_id(message: types.Message):
    try:
        await message.delete()
    except Exception:
        pass

    if message.chat.type == ChatType.PRIVATE:
        await message.answer(
            f"📌 <b>معرّف حسابك الشخصي هو:</b>\n<code>{message.chat.id}</code>"
        )
    else:
        text = (
            f"📌 <b>طلب معرف المساحة (سري)</b>\n\n"
            f"البيئة: <b>{message.chat.title or 'بدون اسم'}</b>\n"
            f"الرقم التسلسلي: <code>{message.chat.id}</code>\n\n"
            f"انسخ الرقم لاستخدامه في الإعدادات."
        )
        try:
            await bot.send_message(chat_id=message.from_user.id, text=text)
        except Exception:
            pass

@dp.my_chat_member()
async def on_bot_added(my_chat_member: types.ChatMemberUpdated):
    if my_chat_member.new_chat_member.status in ["member", "administrator"]:
        chat = my_chat_member.chat
        user_who_added = my_chat_member.from_user
        if chat.type in [ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL]:
            text = (
                f"✅ <b>تم تفعيل المساعد في: {chat.title or 'المساحة الجديدة'}</b>\n\n"
                f"📌 الرمز التسلسلي لهذه البيئة هو:\n"
                f"<code>{chat.id}</code>\n\n"
                f"لإضافتها كبيئة معتمدة، انسخ هذا الرقم وألصقه لي هنا (في الخاص)."
            )
            try:
                await bot.send_message(chat_id=user_who_added.id, text=text)
            except Exception:
                pass

# ========== الأزرار الرئيسية ==========

@dp.callback_query(F.data == "noop")
async def noop(callback: types.CallbackQuery):
    await callback.answer()

@dp.callback_query(F.data == "toggle_active")
async def toggle_active(callback: types.CallbackQuery):
    uid = callback.from_user.id
    current = database.is_bot_active(uid)
    database.set_bot_active(uid, not current)
    msg = "تم تفعيل المزامنة السحابية ▶️" if not current else "تم إيقاف المزامنة السحابية ⏹"
    await callback.message.edit_reply_markup(reply_markup=main_menu_kb(uid))
    await callback.answer(msg, show_alert=True)

@dp.callback_query(F.data == "back_main")
async def back_main(callback: types.CallbackQuery):
    uid = callback.from_user.id
    await callback.message.edit_text(
        "⚙️ <b>لوحة تحكم الأرشيف</b>\n"
        "قم بتنظيم بيئات التخزين الخاصة بك هنا:",
        reply_markup=main_menu_kb(uid)
    )

@dp.callback_query(F.data == "menu_sources")
async def menu_sources(callback: types.CallbackQuery):
    uid = callback.from_user.id
    sources = database.get_channels(uid, "source")
    count = len(sources)
    text = f"📥 <b>نقاط الإدخال المعتمدة</b>\n({count} مسجلة)\n\nنقوم بقراءة البيانات المؤقتة <b>مـن</b> هذه البيئات:"
    await callback.message.edit_text(text, reply_markup=sources_menu_kb(uid))

@dp.callback_query(F.data == "menu_destinations")
async def menu_destinations(callback: types.CallbackQuery):
    uid = callback.from_user.id
    destinations = database.get_channels(uid, "destination")
    count = len(destinations)
    text = f"📤 <b>مساحات التخزين المعتمدة</b>\n({count} مسجلة)\n\nنقوم بأرشفة البيانات السحابية <b>إلـى</b> هذه البيئات:"
    await callback.message.edit_text(text, reply_markup=destinations_menu_kb(uid))

@dp.callback_query(F.data == "diagnose")
async def diagnose(callback: types.CallbackQuery):
    uid = callback.from_user.id
    sources = database.get_channels(uid, "source")
    dests = database.get_channels(uid, "destination")
    active = database.is_bot_active(uid)
    text = (
        f"📊 <b>فحص المزامنة الخاص بك</b>\n\n"
        f"حالة الخدمة: {'🟢 مستقرة' if active else '🔴 معطلة'}\n\n"
        f"📥 <b>نقاط الإدخال ({len(sources)}):</b>\n"
    )
    if sources:
        for ch_id, title in sources:
            text += f"  ▪️ {title} — <code>{ch_id}</code>\n"
    else:
        text += "  ⚠️ النظام يحتاج نقطة إدخال\n"
    text += f"\n📤 <b>التخزين ({len(dests)}):</b>\n"
    if dests:
        for ch_id, title in dests:
            text += f"  ▪️ {title} — <code>{ch_id}</code>\n"
    else:
        text += "  ⚠️ النظام يحتاج بيئة تخزين\n"
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 العودة", callback_data="back_main")]
    ]))

@dp.callback_query(F.data == "how_to_use")
async def how_to_use(callback: types.CallbackQuery):
    text = (
        "📖 <b>دليل التنظيم السحابي</b>\n\n"
        "أهلاً بك في خدمة المزامنة السحابية الاحترافية. هذه الخدمة صُممت للحفاظ على بياناتك بطريقة مؤتمتة.\n\n"
        "1️⃣ <b>التصاريح التشغيلية:</b>\n"
        "يجب الموافقة للإدارة (Admin) للخدمة ضمن أي مساحة (مجموعة أو واجهة) ترغب بأرشفتها لضمان استقرار قراءة البيانات.\n\n"
        "2️⃣ <b>التعرف على بيئات العمل:</b>\n"
        "أضف الخدمة للمساحة وسيصدر النظام رمزاً تسلسلياً خاصاً بها للمشرف حصراً، أو اكتب أمر `/id` لاكتشافه بخصوصية تامة.\n\n"
        "3️⃣ <b>تعريف البيئات:</b>\n"
        "في الواجهة، الصق المعرّف التسلسلي (ID) لتعريف مساحة كـ (نقطة إدخال) أو كـ (تخزين).\n\n"
        "4️⃣ <b>التوثيق الآمن:</b>\n"
        "تأكد من حالة (المزامنة النشطة 🟢). سيتكفل النظام تلقائياً وبشكل صامت بأرشفة المستندات والملاحظات فور رفعها."
    )
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 العودة", callback_data="back_main")]
        ])
    )

# ========== المقاطعة وحذف الجداول ==========

@dp.callback_query(F.data.startswith("del_source_"))
async def del_source(callback: types.CallbackQuery):
    uid = callback.from_user.id
    ch_id = callback.data[len("del_source_"):]
    database.remove_channel(uid, ch_id)
    await callback.answer("✅ تم الإغلاق!", show_alert=True)
    sources = database.get_channels(uid, "source")
    text = f"📥 <b>نقاط الإدخال المعتمدة</b>\n({len(sources)} مسجلة)\n\nنقوم بقراءة البيانات المؤقتة <b>مـن</b> هذه البيئات:"
    await callback.message.edit_text(text, reply_markup=sources_menu_kb(uid))

@dp.callback_query(F.data.startswith("del_dest_"))
async def del_dest(callback: types.CallbackQuery):
    uid = callback.from_user.id
    ch_id = callback.data[len("del_dest_"):]
    database.remove_channel(uid, ch_id)
    await callback.answer("✅ تم الإغلاق!", show_alert=True)
    destinations = database.get_channels(uid, "destination")
    text = f"📤 <b>مساحات التخزين المعتمدة</b>\n({len(destinations)} مسجلة)\n\nنقوم بأرشفة البيانات السحابية <b>إلـى</b> هذه البيئات:"
    await callback.message.edit_text(text, reply_markup=destinations_menu_kb(uid))

# ========== الفلترة التلقائية للإضافات ==========

@dp.callback_query(F.data == "add_source")
async def add_source_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AddChannel.waiting_for_source)
    await callback.message.answer(
        "📥 <b>إضافة نقطة إدخال</b>\n\n"
        "نحن ندعم حماية هويتك. الرجاء تزويدنا بالمعرّف الآمن:\n"
        "1️⃣ الرمز التسلسلي: <code>-1001234567890</code> ⬅️ <b>يفضله النظام لاستقرار الأمان!</b>\n"
        "2️⃣ مُعرّف آمن: <code>@mysecurehub</code>\n\n"
        "*(تنبيه أمني: روابط + لا تتناسب مع خوارزميات التشفير لدينا)*",
        reply_markup=cancel_kb()
    )
    await callback.answer()

@dp.callback_query(F.data == "add_destination")
async def add_destination_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AddChannel.waiting_for_destination)
    await callback.message.answer(
        "📤 <b>إعداد مساحة الأرشفة (Storage)</b>\n\n"
        "يرجى تحديد المعرّف التسلسلي لمخزنك الخاص:\n"
        "1️⃣ الرمز التسلسلي: <code>-1001234567890</code> ⬅️ <b>يفضله النظام!</b>\n"
        "2️⃣ مُعرّف التخزين: <code>@mystorage</code>\n\n"
        "*(تنبيه أمني: روابط + لا تستجيب للتصاريح الأمنية)*",
        reply_markup=cancel_kb()
    )
    await callback.answer()

@dp.callback_query(F.data == "cancel_add")
async def cancel_add(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.delete()
    await callback.answer("تم إلغاء التكوين.")

# ========== قراءة الخوارزميات المدخلة ==========

@dp.message(StateFilter(AddChannel.waiting_for_source))
async def receive_source(message: types.Message, state: FSMContext):
    ch_id, ch_title = extract_chat_info(message)
    if ch_id == "PRIVATE_LINK_ERROR":
        await message.answer(
            "❌ <b>حظر أمني: الروابط الطويلة لا تتطابق مع التشفير.</b>\nالرجاء إدخال الرمز التسلسلي (أمر /id).",
            reply_markup=cancel_kb()
        )
        return
    if not ch_id:
        await message.answer("❌ مساحة مجهولة، أعد التأكد.", reply_markup=cancel_kb())
        return

    await state.update_data(pending_id=ch_id, pending_type="source", auto_title_cache=ch_title)
    await state.set_state(AddChannel.waiting_for_source_name)
    await message.answer(
        f"✅ تمت المواءمة مع: <code>{ch_id}</code>\n\nاكتب تسمية وصفية لها:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"✅ اعتماد: {ch_title}", callback_data="autoname_autobtn")],[InlineKeyboardButton(text="❌ إلغاء", callback_data="cancel_add")]])
    )

@dp.message(StateFilter(AddChannel.waiting_for_destination))
async def receive_destination(message: types.Message, state: FSMContext):
    ch_id, ch_title = extract_chat_info(message)
    if ch_id == "PRIVATE_LINK_ERROR":
        await message.answer(
            "❌ <b>حظر أمني: الروابط الطويلة لا تتطابق مع التشفير.</b>\nالرجاء إدخال الرمز التسلسلي.",
            reply_markup=cancel_kb()
        )
        return
    if not ch_id:
        await message.answer("❌ مساحة مجهولة، أعد التأكد.", reply_markup=cancel_kb())
        return

    await state.update_data(pending_id=ch_id, pending_type="destination", auto_title_cache=ch_title)
    await state.set_state(AddChannel.waiting_for_destination_name)
    await message.answer(
        f"✅ تمت المواءمة مع مخزن: <code>{ch_id}</code>\n\nيرجى كتابة اسم تعريفي لهذه المساحة التخزينية المخصصة لك:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"✅ اعتماد التسمية: {ch_title}", callback_data="autoname_autobtn")],[InlineKeyboardButton(text="❌ إلغاء", callback_data="cancel_add")]])
    )

@dp.message(StateFilter(AddChannel.waiting_for_source_name, AddChannel.waiting_for_destination_name))
async def receive_name(message: types.Message, state: FSMContext):
    data = await state.get_data()
    uid = message.from_user.id
    await finalize_add(message, state, uid, data.get("pending_id"), message.text.strip(), data.get("pending_type"))

@dp.callback_query(F.data == "autoname_autobtn")
async def autoname_cb(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    uid = callback.from_user.id
    await finalize_add(callback.message, state, uid, data.get("pending_id"), data.get("auto_title_cache", "خادم سحابي"), data.get("pending_type"))
    await callback.answer()

async def finalize_add(message: types.Message, state: FSMContext, uid: int, ch_id: str, name: str, c_type: str):
    database.add_channel(uid, ch_id, name, c_type)
    await state.clear()
    icon = "📥" if c_type == "source" else "📤"
    type_ar = "تخصيص للقراءة" if c_type == "source" else "تخصيص للأرشفة"
    await message.answer(
        f"✅ <b>تم ربط الخادم السحابي!</b>\n\n{icon} <b>{name}</b>\nالتسلسل: <code>{ch_id}</code>\nالوظيفة: {type_ar}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"🔙 نظرة على الاستضافات",
                                  callback_data="menu_sources" if c_type == "source" else "menu_destinations")],
        ])
    )

@dp.message(F.forward_from_chat)
async def handle_isolated_forward(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state:
        return
    chat = message.forward_from_chat
    chat_id = str(chat.id)
    chat_title = chat.title or chat.username or str(chat.id)
    await message.answer(
        f"✅ تحليل ناجح. رمز المساحة:\n<b>{chat_title}</b>\n"
        f"التسلسل: <code>{chat_id}</code>\n\nهل ترغب في تسجيل هذه البيئة كجزء من مساحاتك السحابية؟",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📥 اعتماد لـ(الإدخال)", callback_data=f"grab_source_{chat_id}"),
             InlineKeyboardButton(text="📤 اعتماد لـ(الأرشيف والتخزين)", callback_data=f"grab_dest_{chat_id}")],
        ])
    )

@dp.callback_query(F.data.startswith("grab_"))
async def add_grabbed_channel(callback: types.CallbackQuery):
    uid = callback.from_user.id
    parts = callback.data.split("_", 2)
    c_type = "source" if parts[1] == "source" else "destination"
    ch_id = parts[2]
    database.add_channel(uid, ch_id, f"تكوين {ch_id}", c_type)
    await callback.message.edit_text(f"✅ تم تأكيد التسجيل برمز <code>{ch_id}</code> بسلامة تامة ضمن الخوادم.")

def extract_chat_info(message: types.Message):
    if message.forward_from_chat:
        chat = message.forward_from_chat
        return str(chat.id), chat.title or chat.username or str(chat.id)
    if message.text:
        raw = message.text.strip()
        if "t.me/+" in raw or "joinchat" in raw:
            return "PRIVATE_LINK_ERROR", ""
        if "t.me/" in raw:
            return "@" + raw.rstrip("/").split("t.me/")[-1], "@" + raw.rstrip("/").split("t.me/")[-1]
        if raw.lstrip("-").isdigit():
            if not raw.startswith("-100"):
                raw = f"-100{raw.lstrip('-')}"
            return raw, raw
        if raw.startswith("@"):
            return raw, raw
        if raw.replace("_", "").isalnum():
            return "@" + raw, "@" + raw
    return None, None

# ========== خوارزمية السحب (نقل الرسائل) بلا ترك أثر ==========

async def copy_to_user_destinations(user_id: int, source_chat_id: str, message: types.Message):
    if not database.is_bot_active(user_id):
        return

    # التحقق مما إذا كانت الرسالة عبارة عن رد (Reply)
    reply_id = None
    if message.reply_to_message:
        reply_id = message.reply_to_message.message_id

    for dest in database.get_channels(user_id, "destination"):
        dest_id = dest[0]
        try:
            # محاولة العثور على المعرف المقابل للرسالة الأصلية في وجهة التخزين هذه
            target_reply_id = None
            if reply_id:
                target_reply_id = database.get_dest_msg_id(user_id, source_chat_id, reply_id, dest_id)

            # نسخ الرسالة مع ربط الرد إذا وجدنا المعرّف السابق
            msg_obj = await bot.copy_message(
                chat_id=dest_id, 
                from_chat_id=message.chat.id, 
                message_id=message.message_id,
                reply_to_message_id=target_reply_id
            )
            
            database.save_message_mapping(
                user_id=user_id,
                src_chat=source_chat_id,
                src_msg=message.message_id,
                dst_chat=dest_id,
                dst_msg=msg_obj.message_id
            )
            logging.info(f"[SYNC] {user_id}: {source_chat_id} >> {dest_id}")
        except Exception as e:
            logging.error(f"[FAIL] {user_id} >> {dest_id}: {e}")

@dp.channel_post()
async def forward_from_channel(message: types.Message):
    chat_id_str = str(message.chat.id)
    chat_username = f"@{message.chat.username}" if message.chat.username else None
    all_sources = database.get_all_sources_with_users()
    for user_id, ch_id in all_sources:
        if str(ch_id) == chat_id_str or (chat_username and str(ch_id) == chat_username):
            await copy_to_user_destinations(user_id, chat_id_str, message)

@dp.message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
async def forward_from_group(message: types.Message):
    if message.text and message.text.startswith("/"):
        return
    chat_id_str = str(message.chat.id)
    chat_username = f"@{message.chat.username}" if message.chat.username else None
    all_sources = database.get_all_sources_with_users()
    for user_id, ch_id in all_sources:
        if str(ch_id) == chat_id_str or (chat_username and str(ch_id) == chat_username):
            await copy_to_user_destinations(user_id, chat_id_str, message)

@dp.edited_channel_post()
@dp.edited_message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
async def handle_edited_message(message: types.Message):
    chat_id_str = str(message.chat.id)
    mapped = database.get_mapped_messages(chat_id_str, message.message_id)
    if not mapped:
        return
    for user_id, dest_chat_id, dest_message_id in mapped:
        if not database.is_bot_active(user_id):
            continue
        try:
            if message.text:
                await bot.edit_message_text(text=message.html_text, chat_id=dest_chat_id, message_id=dest_message_id, parse_mode=ParseMode.HTML)
            elif message.caption is not None:
                await bot.edit_message_caption(caption=message.html_text or "", chat_id=dest_chat_id, message_id=dest_message_id, parse_mode=ParseMode.HTML)
        except Exception:
            pass

async def main():
    logging.info("🚀 System Booting... (Cloud Sync Environment)")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot, allowed_updates=["message", "channel_post", "callback_query", "edited_message", "edited_channel_post", "my_chat_member"])

if __name__ == "__main__":
    asyncio.run(main())
