import os
import telebot
import routeros_api
import random
import string
from telebot import types

BOT_TOKEN = os.environ.get('BOT_TOKEN')
MIKROTIK_IP = os.environ.get('MIKROTIK_IP')       
MIKROTIK_USER = os.environ.get('MIKROTIK_USER')   
MIKROTIK_PASS = os.environ.get('MIKROTIK_PASS')   
ADMIN_ID = int(os.environ.get('ADMIN_ID', 0)) 

bot = telebot.TeleBot(BOT_TOKEN)
allowed_users = {ADMIN_ID} 
user_states = {}

def get_mikrotik_connection():
    connection = routeros_api.RouterOsApiPool(
        MIKROTIK_IP, username=MIKROTIK_USER, password=MIKROTIK_PASS, plaintext_login=True
    )
    return connection.get_api()

def main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("📊 حالة الميكروتك"), types.KeyboardButton("📡 الصحون المتصلة"))
    markup.add(types.KeyboardButton("🔍 تفاصيل يوزر"), types.KeyboardButton("📉 استهلاك الشبكة الآن"))
    markup.add(types.KeyboardButton("🚫 طرد يوزر نشط"), types.KeyboardButton("🎫 إنشاء كرت سريع"))
    markup.add(types.KeyboardButton("⏱️ آخر خروج للمشتركين"))
    return markup

@bot.message_handler(func=lambda message: message.chat.id not in allowed_users)
def handle_unauthorized(message):
    chat_id = message.chat.id
    username = message.from_user.username or "بدون معرف"
    first_name = message.from_user.first_name
    if message.text == "/start":
        bot.reply_to(message, "⏳ أهلاً بك. تم إرسال طلب انضمام لمالك الشبكة، يرجى الانتظار لحين الموافقة...")
        admin_markup = types.InlineKeyboardMarkup()
        btn_accept = types.InlineKeyboardButton("✅ موافقة", callback_data=f"accept_{chat_id}")
        btn_reject = types.InlineKeyboardButton("❌ رفض", callback_data=f"reject_{chat_id}")
        admin_markup.add(btn_accept, btn_reject)
        bot.send_message(ADMIN_ID, f"🔔 **طلب انضمام جديد للبوت:**\n\n👤 الاسم: {first_name}\n🏷️ المعرف: @{username}\n🆔 الآيدي: `{chat_id}`", reply_markup=admin_markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith(('accept_', 'reject_')))
def handle_admin_decision(call):
    if call.from_user.id != ADMIN_ID: return
    action, target_id = call.data.split('_')
    target_id = int(target_id)
    if action == 'accept':
        allowed_users.add(target_id)
        bot.send_message(target_id, "🎉 تم قبول طلبك من قبل الأدمن! يمكنك الآن التحكم بالبوت واستخدام الأزرار.", reply_markup=main_keyboard())
        bot.edit_message_text(f"✅ تم قبول المستخدم بنجاح ({target_id}).", chat_id=ADMIN_ID, message_id=call.message.message_id)
    elif action == 'reject':
        bot.send_message(target_id, "❌ نعتذر منك، تم رفض طلب انضمامك للبوت البرمجي.")
        bot.edit_message_text(f"❌ تم رفض المستخدم ({target_id}).", chat_id=ADMIN_ID, message_id=call.message.message_id)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "⚙️ أهلاً بك مجدداً في لوحة تحكم الميكروتك الآمنة:", reply_markup=main_keyboard())

@bot.message_handler(func=lambda message: message.chat.id in allowed_users)
def handle_commands(message):
    chat_id = message.chat.id
    if chat_id in user_states:
        state = user_states[chat_id]
        if state == 'waiting_search': search_username(message)
        elif state == 'waiting_kick': kick_username(message)
        return
    try:
        api = get_mikrotik_connection()
        if message.text == "📊 حالة الميكروتك":
            res = api.get_resource('/system/resource').get()
            bot.reply_to(message, f"📈 استهلاك المعالج: {res['cpu-load']}%\n⏱️ وقت التشغيل المتواصل: {res['uptime']}")
        elif message.text == "📡 الصحون المتصلة":
            neighbors = api.get_resource('/ip/neighbor').get()
            text = "📡 **الأجهزة والصحون المكتشفة (Neighbors):**\n\n"
            for n in neighbors[:10]:
                text += f"🖥️ الجهاز: {n.get('identity','-')}\n🔌 البورت: {n.get('interface','-')}\n🌐 IP: {n.get('address','-')}\n-------------------------\n"
            bot.reply_to(message, text)
        elif message.text == "🔍 تفاصيل يوزر":
            user_states[chat_id] = 'waiting_search'
            bot.reply_to(message, "📝 أرسل اسم يوزر الهوتسبوت لفحصه وعرض الـ Remote IP:")
        elif message.text == "🚫 طرد يوزر نشط":
            user_states[chat_id] = 'waiting_kick'
            bot.reply_to(message, "📝 أرسل اسم اليوزر المتصل حالياً لإخراجه وفصله فوراً:")
        elif message.text == "📉 استهلاك الشبكة الآن":
            interfaces = api.get_resource('/interface').get()
            wan = interfaces['name']
            traffic = api.get_resource('/interface').call('monitor-traffic', {'interface': wan, 'once': True})
            rx = round(int(traffic['rx-bits-per-second']) / 1024 / 1024, 2)
            tx = round(int(traffic['tx-bits-per-second']) / 1024 / 1024, 2)
            bot.reply_to(message, f"📉 **الاستهلاك الفوري على كرت ({wan}):**\n\n📥 Download: {rx} Mbps\n📤 Upload: {tx} Mbps")
        elif message.text == "🎫 إنشاء كرت سريع":
            card_name = ''.join(random.choices(string.ascii_lowercase + string.digits, k=5))
            api.get_resource('/ip/hotspot/user').add(name=card_name, password=card_name, profile="default")
            bot.reply_to(message, f"🎫 **تم إنشاء كرت هوتسبوت جديد بنجاح:**\n\n👤 اسم المستخدم: `{card_name}`\n🔑 كلمة المرور: `{card_name}`\n📋 البروفايل: Default", parse_mode="Markdown")
        elif message.text == "⏱️ آخر خروج للمشتركين":
            user_list = api.get_resource('/ip/hotspot/user').get()
            text = "⏱️ **آخر الحسابات المتوقفة وخروجها:**\n\n"
            count = 0
            for u in user_list:
                if u.get('last-logged-out') and u['last-logged-out'] != "never":
                    text += f"👤 يوزر: {u['name']}\n🕒 خروج: {u['last-logged-out']}\n-------------------------\n"
                    count += 1
                    if count >= 8: break
            bot.reply_to(message, text if count > 0 else "📭 لا توجد سجلات خروج.")
    except Exception as e: bot.reply_to(message, f"❌ حدث خطأ أثناء الاتصال.\nالخطأ: {str(e)}")

def search_username(message):
    chat_id = message.chat.id
    username = message.text.strip()
    del user_states[chat_id]
    try:
        api = get_mikrotik_connection()
        active = api.get_resource('/ip/hotspot/active').get()
        user_info = next((u for u in active if u['user'] == username), None)
        if user_info:
            bot.reply_to(message, f"🟢 **اليوزر متصل حالياً!**\n\n🌐 Remote IP: {user_info.get('address','-')}\n📟 MAC: {user_info.get('mac-address','-')}\n⏱️ مدة الاتصال: {user_info.get('uptime','-')}")
        else:
            bot.reply_to(message, f"🔴 اليوزر غير متصل بالشبكة حالياً.")
    except Exception as e: bot.reply_to(message, f"❌ خطأ: {e}")

def kick_username(message):
    chat_id = message.chat.id
    username = message.text.strip()
    del user_states[chat_id]
    try:
        api = get_mikrotik_connection()
        active = api.get_resource('/ip/hotspot/active').get()
        user_info = next((u for u in active if u['user'] == username), None)
        if user_info:
            api.get_resource('/ip/hotspot/active').remove(id=user_info['.id'])
            bot.reply_to(message, f"💥 تم فصل وطرد المستخدم ({username}) من الشبكة بنجاح.")
        else:
            bot.reply_to(message, f"❌ المستخدم غير نشط أو غير متصل بالأساس ليتم فصله.")
    except Exception as e: bot.reply_to(message, f"❌ خطأ: {e}")

if __name__ == "__main__":
    bot.infinity_polling()
