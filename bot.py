import os
import time
import requests
import telebot
import zipfile
import base64

# ⚠️ ضع التوكنز الخاصة بك هنا بدقة
TELEGRAM_TOKEN = "YOUR_TELEGRAM_TOKEN"
GH_TOKEN = "YOUR_GITHUB_TOKEN"
GH_REPO = "sameone29/apk-builder"

# إعداد جلسة Requests لتجنب مشاكل البروكسي
session = requests.Session()
session.trust_env = False

bot = telebot.TeleBot(TELEGRAM_TOKEN, session=session)
user_files = {}

def upload_to_github(path, content_bytes):
    url = f"https://api.github.com/repos/{GH_REPO}/contents/{path}"
    headers = {
        "Authorization": f"token {GH_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    # التحقق من وجود الملف مسبقاً لأخذ الـ SHA
    r = session.get(url, headers=headers)
    sha = ""
    if r.status_code == 200:
        sha = r.json().get("sha", "")
    
    content_encoded = base64.b64encode(content_bytes).decode()
    data = {
        "message": f"update {path}",
        "content": content_encoded
    }
    if sha:
        data["sha"] = sha
        
    res = session.put(url, headers=headers, json=data)
    return res.status_code in [200, 201]

def wait_for_apk():
    headers = {
        "Authorization": f"token {GH_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    for _ in range(20): # انتظر حتى 10 دقائق        time.sleep(30)
        r = session.get(f"https://api.github.com/repos/{GH_REPO}/actions/runs", headers=headers)
        
        if r.status_code != 200:
            continue
            
        runs = r.json().get("workflow_runs", [])
        if not runs:
            continue
            
        latest_run = runs[0]
        
        if latest_run["status"] == "completed":
            if latest_run["conclusion"] == "success":
                run_id = latest_run["id"]
                art = session.get(
                    f"https://api.github.com/repos/{GH_REPO}/actions/runs/{run_id}/artifacts",
                    headers=headers
                )
                
                if art.status_code == 200:
                    artifacts = art.json().get("artifacts", [])
                    if artifacts:
                        return artifacts[0]["archive_download_url"]
            else:
                print(f"البناء فشل: {latest_run['conclusion']}")
                return None
                
    return None

def download_apk(apk_url):
    headers = {
        "Authorization": f"token {GH_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    # تحميل الملف
    r = session.get(apk_url, headers=headers, allow_redirects=True, timeout=60)
    
    if r.status_code == 403:
        raise Exception("خطأ 403: توكن GitHub غير صالح أو لا يملك صلاحية الوصول.")
    elif r.status_code != 200:
        raise Exception(f"فشل التحميل. رمز الحالة: {r.status_code}")
        
    # التحقق من أن الرد ليس صفحة HTML خطأ
    if 'html' in r.headers.get('Content-Type', '').lower():
        raise Exception("الرابط يعيد صفحة خطأ HTML بدلاً من ملف ZIP.")

    file_path = "/tmp/app.zip"
    with open(file_path, "wb") as f:        f.write(r.content)
        
    # التحقق من حجم الملف
    if os.path.getsize(file_path) < 100:
        raise Exception("الملف المُحمل صغير جداً وتالف.")

    extract_path = "/tmp/apk"
    if os.path.exists(extract_path):
        import shutil
        shutil.rmtree(extract_path)
    os.makedirs(extract_path, exist_ok=True)
    
    try:
        with zipfile.ZipFile(file_path, "r") as z:
            z.extractall(extract_path)
    except zipfile.BadZipFile:
        raise Exception("الملف تالف وليس بصيغة ZIP صالحة.")
        
    # البحث عن ملف APK داخل المجلد المستخرج
    apk_file = None
    for root, dirs, files in os.walk(extract_path):
        for file in files:
            if file.endswith(".apk"):
                apk_file = os.path.join(root, file)
                break
        if apk_file:
            break
            
    if not apk_file:
        raise Exception("لم يتم العثور على ملف .apk داخل الأرشيف.")
        
    return apk_file

@bot.message_handler(commands=["start"])
def start(msg):
    bot.reply_to(msg,
    "👋 أهلاً! يمكنك:\n\n"
    "1️⃣ إرسال ملف MainActivity.kt مباشرة\n"
    "2️⃣ إرسال ملفات متعددة واحد واحد ثم /build\n"
    "3️⃣ إرسال ملف ZIP كامل فيه كل المشروع\n\n"
    "أرسل /build بعد رفع كل الملفات لبدء البناء"
    )

@bot.message_handler(commands=["build"])
def build(msg):
    uid = msg.chat.id
    if uid not in user_files or not user_files[uid]:
        bot.reply_to(msg, "❌ ما في ملفات! أرسل الملفات أولاً.")
        return
        try:
        bot.reply_to(msg, f"⏳ جاري رفع {len(user_files[uid])} ملف على GitHub...")
        
        for path, content in user_files[uid].items():
            upload_to_github(path, content)
            
        user_files[uid] = {}
        
        bot.reply_to(msg, "✅ تم الرفع! جاري البناء... (2-5 دقائق)")
        
        apk_url = wait_for_apk()
        
        if apk_url:
            bot.reply_to(msg, "⬇️ جاري تحميل APK...")
            apk_path = download_apk(apk_url)
            
            with open(apk_path, "rb") as f:
                bot.send_document(msg.chat.id, f, caption="✅ APK جاهز!")
        else:
            bot.reply_to(msg, "❌ فشل البناء أو انتهى الوقت.")
            
    except Exception as e:
        bot.reply_to(msg, f"❌ حدث خطأ: {str(e)}")

@bot.message_handler(content_types=["document"])
def handle_file(msg):
    uid = msg.chat.id
    if uid not in user_files:
        user_files[uid] = {}
        
    file_name = msg.document.file_name
    file_info = bot.get_file(msg.document.file_id)
    downloaded = bot.download_file(file_info.file_path)
    
    if file_name.endswith(".zip"):
        bot.reply_to(msg, "📦 جاري فك ضغط الـ ZIP...")
        temp_zip = "/tmp/upload.zip"
        with open(temp_zip, "wb") as f:
            f.write(downloaded)
            
        try:
            with zipfile.ZipFile(temp_zip, "r") as z:
                for name in z.namelist():
                    if name.endswith("/"):
                        continue
                        
                    with z.open(name) as zf:
                        content = zf.read()
                        
                        if name.endswith(".kt"):                            path = f"app/src/main/java/com/generated/app/{os.path.basename(name)}"
                        elif name.endswith(".xml") and "layout" in name:
                            path = f"app/src/main/res/layout/{os.path.basename(name)}"
                        elif name.endswith(".xml") and "values" in name:
                            path = f"app/src/main/res/values/{os.path.basename(name)}"
                        else:
                            path = f"app/src/main/{name}"
                            
                        user_files[uid][path] = content
                        
            bot.reply_to(msg, "✅ تم استخراج الملفات! أرسل /build لبدء البناء.")
        except Exception as e:
            bot.reply_to(msg, f"❌ فشل فك الضغط: {str(e)}")

    elif file_name.endswith(".kt"):
        path = f"app/src/main/java/com/generated/app/{file_name}"
        user_files[uid][path] = downloaded
        bot.reply_to(msg, f"✅ تم استلام {file_name}\nأرسل المزيد أو /build.")

    elif file_name.endswith(".xml"):
        if "layout" in file_name:
            path = f"app/src/main/res/layout/{file_name}"
        else:
            path = f"app/src/main/res/values/{file_name}"
        user_files[uid][path] = downloaded
        bot.reply_to(msg, f"✅ تم استلام {file_name}\nأرسل المزيد أو /build.")

    else:
        bot.reply_to(msg, "⚠️ صيغة غير مدعومة. أرسل .kt أو .xml أو .zip")

# ملاحظة: لا تشغل bot.polling() هنا إذا كنت تستخدم Always-on Task
