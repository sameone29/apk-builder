import os
import time
import requests
import telebot
import zipfile
import base64

TELEGRAM_TOKEN = "YOUR_TELEGRAM_TOKEN"
GH_TOKEN = "YOUR_GITHUB_TOKEN"
GH_REPO = "sameone29/apk-builder"

bot = telebot.TeleBot(TELEGRAM_TOKEN)
user_files = {}


def upload_to_github(path, content_bytes):
    url = f"https://api.github.com/repos/{GH_REPO}/contents/{path}"
    headers = {"Authorization": f"token {GH_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    r = requests.get(url, headers=headers)
    sha = r.json().get("sha", "") if r.status_code == 200 else ""
    content = base64.b64encode(content_bytes).decode()
    data = {"message": f"update {path}", "content": content}
    if sha:
        data["sha"] = sha
    res = requests.put(url, headers=headers, json=data)
    return res.status_code in [200, 201]


def wait_for_apk():
    headers = {"Authorization": f"token {GH_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    for _ in range(20):
        time.sleep(30)
        r = requests.get(f"https://api.github.com/repos/{GH_REPO}/actions/runs", headers=headers)
        runs = r.json().get("workflow_runs", [])
        if runs and runs[0]["status"] == "completed":
            if runs[0]["conclusion"] == "success":
                run_id = runs[0]["id"]
                art = requests.get(
                    f"https://api.github.com/repos/{GH_REPO}/actions/runs/{run_id}/artifacts",
                    headers=headers
                ).json()
                artifacts = art.get("artifacts", [])
                if artifacts:
                    return artifacts[0]["archive_download_url"]
            return None
    return None


def download_apk(apk_url):
    headers = {"Authorization": f"token {GH_TOKEN}"}
    r = requests.get(apk_url, headers=headers, allow_redirects=True)
    with open("/tmp/app.zip", "wb") as f:
        f.write(r.content)
    with zipfile.ZipFile("/tmp/app.zip", "r") as z:
        z.extractall("/tmp/apk")
    return "/tmp/apk/app-debug.apk"


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
    bot.reply_to(msg, f"⏳ جاري رفع {len(user_files[uid])} ملف على GitHub...")
    for path, content in user_files[uid].items():
        upload_to_github(path, content)
    user_files[uid] = {}
    bot.reply_to(msg, "✅ تم الرفع! جاري البناء... (2-3 دقائق)")
    apk_url = wait_for_apk()
    if apk_url:
        apk_path = download_apk(apk_url)
        with open(apk_path, "rb") as f:
            bot.send_document(msg.chat.id, f, caption="✅ APK جاهز!")
    else:
        bot.reply_to(msg, "❌ فشل البناء، تحقق من الكود وحاول مرة ثانية.")


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
        with open("/tmp/upload.zip", "wb") as f:
            f.write(downloaded)
        with zipfile.ZipFile("/tmp/upload.zip", "r") as z:
            for name in z.namelist():
                if not name.endswith("/"):
                    with z.open(name) as zf:
                        if name.endswith(".kt"):
                            path = f"app/src/main/java/com/generated/app/{os.path.basename(name)}"
                        elif name.endswith(".xml") and "layout" in name:
                            path = f"app/src/main/res/layout/{os.path.basename(name)}"
                        elif name.endswith(".xml") and "values" in name:
                            path = f"app/src/main/res/values/{os.path.basename(name)}"
                        else:
                            path = f"app/src/main/{name}"
                        user_files[uid][path] = zf.read()
        bot.reply_to(msg, "✅ تم استخراج الملفات! أرسل /build لبدء البناء.")

    elif file_name.endswith(".kt"):
        path = f"app/src/main/java/com/generated/app/{file_name}"
        user_files[uid][path] = downloaded
        bot.reply_to(msg, f"✅ تم استلام {file_name}\nأرسل المزيد من الملفات أو /build للبناء.")

    elif file_name.endswith(".xml"):
        if "layout" in file_name:
            path = f"app/src/main/res/layout/{file_name}"
        else:
            path = f"app/src/main/res/values/{file_name}"
        user_files[uid][path] = downloaded
        bot.reply_to(msg, f"✅ تم استلام {file_name}\nأرسل المزيد من الملفات أو /build للبناء.")

    else:
        bot.reply_to(msg, "⚠️ صيغة غير مدعومة. أرسل .kt أو .xml أو .zip")


bot.polling()
