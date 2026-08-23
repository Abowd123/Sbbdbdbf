import os
import re
import time
import uuid
import threading
import urllib.parse

import requests
from flask import Flask, request, jsonify, send_from_directory

# ============================================================
# ⚙️ الإعدادات
# ============================================================
KUVU_MODEL = "Kuvu 1.0"
DEFAULT_RES = "1080p"
DEFAULT_ASPECT = "16:9"
DEFAULT_DURATION = 8

# مفتاح حماية بسيط. اضبطه كمتغير بيئة على Railway.
API_KEY = os.environ.get("API_KEY", "change-me-please")

# الواجهة تُقدَّم من مجلد static
app = Flask(__name__, static_folder="static", static_url_path="")

# تخزين حالة المهام في الذاكرة
tasks = {}


# ============================================================
# 📤 رفع الوسائط (خدمات متعددة)
# ============================================================
def upload_catbox(file_bytes, filename):
    try:
        files = {'fileToUpload': (filename, file_bytes)}
        data = {'reqtype': 'fileupload'}
        r = requests.post('https://catbox.moe/user/api.php', files=files, data=data, timeout=60)
        if r.status_code == 200 and r.text.strip():
            return r.text.strip()
    except Exception as e:
        print(f"catbox failed: {e}")
    return None


def upload_0x0(file_bytes, filename):
    try:
        files = {'file': (filename, file_bytes)}
        r = requests.post('https://0x0.st', files=files, timeout=60)
        if r.status_code == 200 and r.text.strip().startswith('http'):
            return r.text.strip()
    except Exception as e:
        print(f"0x0.st failed: {e}")
    return None


def upload_uguu(file_bytes, filename):
    try:
        files = {'files[]': (filename, file_bytes)}
        r = requests.post('https://uguu.se/upload', files=files, timeout=60)
        if r.status_code == 200:
            data = r.json()
            url = data.get('files', [{}])[0].get('url')
            if url:
                return url
    except Exception as e:
        print(f"uguu failed: {e}")
    return None


def upload_quax(file_bytes, filename):
    try:
        files = {'files[]': (filename, file_bytes)}
        r = requests.post('https://qu.ax/upload.php', files=files, timeout=60)
        if r.status_code == 200:
            data = r.json()
            url = data.get('files', [{}])[0].get('url')
            if url:
                return url
    except Exception as e:
        print(f"qu.ax failed: {e}")
    return None


def upload_to_host(file_bytes, filename):
    """محاولة الرفع إلى عدة خدمات حتى تنجح واحدة"""
    for host in (upload_catbox, upload_0x0, upload_uguu, upload_quax):
        url = host(file_bytes, filename)
        if url:
            return url
    return None


# ============================================================
# 🧠 مقدمة آمنة
# ============================================================
def safe_prompt(text):
    if text:
        return f"Create a visually artistic, non-violent, family-friendly interpretation of: {text}"
    return text


# ============================================================
# 🤖 دوال Kuvu AI
# ============================================================
def generate_temp_email():
    s = requests.Session()
    s.headers.update({
        'accept': 'application/json, text/plain, */*',
        'accept-language': 'en-US,en;q=0.9',
        'origin': 'https://www.emailnator.com',
        'referer': 'https://www.emailnator.com/',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'x-requested-with': 'XMLHttpRequest'
    })
    s.get('https://www.emailnator.com')
    xsrf = s.cookies.get('XSRF-TOKEN')
    if not xsrf:
        raise Exception("فشل الحصول على XSRF-TOKEN")
    s.headers.update({'x-xsrf-token': urllib.parse.unquote(xsrf)})
    r = s.post('https://www.emailnator.com/generate-email', json={'email': ['dotGmail']})
    email = r.json()['email'][0]
    return s, email


def get_magic_link(email_session, email):
    email_session.get('https://www.emailnator.com')
    xsrf = email_session.cookies.get('XSRF-TOKEN')
    if xsrf:
        email_session.headers.update({'x-xsrf-token': urllib.parse.unquote(xsrf)})

    r = email_session.post('https://www.emailnator.com/message-list', json={'email': email})
    old_ids = {m['messageID'] for m in r.json()['messageData']}

    while True:
        time.sleep(4)
        email_session.get('https://www.emailnator.com')
        xsrf = email_session.cookies.get('XSRF-TOKEN')
        if xsrf:
            email_session.headers.update({'x-xsrf-token': urllib.parse.unquote(xsrf)})

        r = email_session.post('https://www.emailnator.com/message-list', json={'email': email})
        try:
            messages = r.json()['messageData']
        except Exception:
            messages = []

        for msg in messages:
            if msg['messageID'] not in old_ids and msg.get('from') != 'AI TOOLS':
                email_session.get('https://www.emailnator.com')
                if xsrf:
                    email_session.headers.update({'x-xsrf-token': urllib.parse.unquote(xsrf)})
                msg_res = email_session.post(
                    'https://www.emailnator.com/message-list',
                    json={'email': email, 'messageID': msg['messageID']}
                )
                match = re.search(r'https://kuvu\.ai/api/auth/magic-link/verify\?token=[^\s"<]+', msg_res.text)
                if match:
                    return match.group(0)
        time.sleep(2)


def login_kuvu(verify_link):
    headers = {
        'accept': '*/*',
        'accept-language': 'en-US,en;q=0.9',
        'cache-control': 'no-cache',
        'content-type': 'application/json',
        'origin': 'https://kuvu.ai',
        'pragma': 'no-cache',
        'sec-ch-ua': '"Chromium";v="139", "Not;A=Brand";v="99"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    session = requests.Session()
    session.get(verify_link, headers={**headers, 'referer': 'https://kuvu.ai/'}, allow_redirects=True)
    cookie = session.cookies.get('__Secure-better-auth.session_token')
    if not cookie:
        raise Exception("فشل الحصول على كوكيز الجلسة")
    return session, cookie


def generate_video_task(session, cookie, payload):
    headers = {
        'accept': '*/*',
        'accept-language': 'en-US,en;q=0.9',
        'cache-control': 'no-cache',
        'content-type': 'application/json',
        'origin': 'https://kuvu.ai',
        'pragma': 'no-cache',
        'referer': 'https://kuvu.ai/home',
        'sec-ch-ua': '"Chromium";v="139", "Not;A=Brand";v="99"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'cookie': f"__Secure-better-auth.session_token={cookie}"
    }

    if payload["type"] == "text_to_video":
        url = 'https://kuvu.ai/api/ai-video/text-to-video/gen'
    elif payload["type"] == "image_to_video":
        url = 'https://kuvu.ai/api/ai-video/image-to-video/gen'
    elif payload["type"] == "video_edit":
        url = 'https://kuvu.ai/api/ai-video/video-edit/gen'
    else:
        raise Exception("نوع غير معروف")

    safe_text = safe_prompt(payload.get("prompt", ""))

    kuvu_payload = {
        "prompt": safe_text,
        "model": KUVU_MODEL,
        "resolution": payload.get("resolution", DEFAULT_RES),
        "aspect_ratio": payload.get("aspect_ratio", DEFAULT_ASPECT),
        "duration": payload.get("duration", DEFAULT_DURATION),
        "return_last_frame": False,
        "generationType": "",
        "enableFallback": False,
        "enableTranslation": False,
        "input": {
            "images": payload.get("images", []),
            "videos": payload.get("videos", []),
            "audios": payload.get("audios", [])
        },
        "videoPrompt": safe_text,
        "videoModel": KUVU_MODEL,
        "quality": payload.get("resolution", DEFAULT_RES),
        "aspectRatio": payload.get("aspect_ratio", DEFAULT_ASPECT)
    }

    r = session.post(url, headers=headers, json=kuvu_payload)
    if r.status_code != 200:
        try:
            err_data = r.json()
            if err_data.get("isSafe") is False:
                raise Exception("⚠️ النص غير آمن حسب فلتر Kuvu. يرجى إعادة صياغة الوصف بطريقة غير عنيفة.")
            raise Exception(f"فشل إنشاء المهمة: {r.text[:300]}")
        except ValueError:
            raise Exception(f"فشل إنشاء المهمة: {r.text[:300]}")
    data = r.json()
    if 'taskId' not in data or 'request' not in data:
        raise Exception(f"استجابة غير متوقعة: {r.text[:300]}")
    return data['taskId'], data['request']


def poll_video(session, cookie, task_id, req):
    headers = {
        'accept': '*/*',
        'accept-language': 'en-US,en;q=0.9',
        'cache-control': 'no-cache',
        'content-type': 'application/json',
        'origin': 'https://kuvu.ai',
        'pragma': 'no-cache',
        'referer': 'https://kuvu.ai/home',
        'user-agent': 'Mozilla/5.0',
        'cookie': f"__Secure-better-auth.session_token={cookie}"
    }
    payload = {
        'taskId': task_id,
        'taskIds': [task_id],
        'request': req,
        'finalize': True
    }
    while True:
        time.sleep(5)
        r = session.post('https://kuvu.ai/api/ai-video/text-to-video/get', headers=headers, json=payload)
        if r.status_code != 200:
            raise Exception(f"خطأ في الاستعلام: {r.text[:300]}")
        data = r.json()
        if 'status' not in data:
            raise Exception(f"استجابة غير متوقعة: {r.text[:300]}")
        if data['status'] == 'SUCCESS':
            return data.get('videoUrl', '')
        elif data['status'] == 'RUNNING':
            continue
        else:
            raise Exception(f"انتهت المهمة بحالة: {data['status']}")


# ============================================================
# 🔧 معالجة المهمة في خيط منفصل
# ============================================================
def run_generation(task_id, payload):
    def update(status, message, extra=None):
        tasks[task_id].update({"status": status, "message": message})
        if extra:
            tasks[task_id].update(extra)

    try:
        update("running", "جاري تجهيز البريد المؤقت...")
        email_session, email = generate_temp_email()
        update("running", f"البريد المؤقت: {email} — في انتظار رابط التحقق...")

        kuvu_headers = {
            'accept': '*/*',
            'accept-language': 'en-US,en;q=0.9',
            'cache-control': 'no-cache',
            'content-type': 'application/json',
            'origin': 'https://kuvu.ai',
            'pragma': 'no-cache',
            'referer': 'https://kuvu.ai/signin?from=%2Fhome',
            'sec-ch-ua': '"Chromium";v="139", "Not;A=Brand";v="99"',
            'user-agent': 'Mozilla/5.0'
        }
        requests.post('https://kuvu.ai/api/auth/sign-in/magic-link', headers=kuvu_headers,
                      json={'email': email, 'callbackURL': 'https://kuvu.ai/home'})

        verify_link = get_magic_link(email_session, email)
        update("running", "تم استلام رابط التحقق. جاري تسجيل الدخول...")

        session_kuvu, cookie = login_kuvu(verify_link)
        update("running", "تم تسجيل الدخول. جاري إنشاء المهمة...")

        kuvu_task_id, req = generate_video_task(session_kuvu, cookie, payload)
        update("running", "بدأ التوليد. قد يستغرق عدة دقائق...")

        video_url = poll_video(session_kuvu, cookie, kuvu_task_id, req)
        update("done", "اكتمل التوليد.", {"videoUrl": video_url})
    except Exception as e:
        update("error", str(e))


# ============================================================
# 🌐 نقاط الـ API
# ============================================================
def check_auth():
    key = request.headers.get("X-API-Key")
    return key == API_KEY


@app.route("/api/upload", methods=["POST"])
def api_upload():
    if not check_auth():
        return jsonify({"error": "غير مصرح"}), 401
    if 'file' not in request.files:
        return jsonify({"error": "لا يوجد ملف"}), 400
    f = request.files['file']
    url = upload_to_host(f.read(), f.filename or "file")
    if not url:
        return jsonify({"error": "فشل رفع الوسائط"}), 500
    return jsonify({"url": url})


@app.route("/api/generate", methods=["POST"])
def api_generate():
    if not check_auth():
        return jsonify({"error": "غير مصرح"}), 401
    body = request.get_json(force=True) or {}
    mode = body.get("type", "text_to_video")
    prompt = body.get("prompt", "")
    images = body.get("images", [])
    videos = body.get("videos", [])

    if mode == "text_to_video" and not prompt:
        return jsonify({"error": "أرسل نصًا أولاً."}), 400
    if mode == "image_to_video" and not images:
        return jsonify({"error": "أرسل صورة واحدة على الأقل."}), 400
    if mode == "video_edit" and not videos:
        return jsonify({"error": "أرسل فيديو واحدًا على الأقل."}), 400

    payload = {
        "type": mode,
        "prompt": prompt,
        "images": images,
        "videos": videos,
        "audios": body.get("audios", []),
        "resolution": body.get("resolution", DEFAULT_RES),
        "aspect_ratio": body.get("aspect_ratio", DEFAULT_ASPECT),
        "duration": body.get("duration", DEFAULT_DURATION)
    }

    task_id = uuid.uuid4().hex
    tasks[task_id] = {"status": "running", "message": "بدأت المهمة...", "videoUrl": None}
    threading.Thread(target=run_generation, args=(task_id, payload), daemon=True).start()
    return jsonify({"taskId": task_id})


@app.route("/api/status/<task_id>", methods=["GET"])
def api_status(task_id):
    if not check_auth():
        return jsonify({"error": "غير مصرح"}), 401
    task = tasks.get(task_id)
    if not task:
        return jsonify({"error": "المهمة غير موجودة"}), 404
    return jsonify(task)


# ============================================================
# 🖥️ تقديم الواجهة
# ============================================================
@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "Kuvu AI"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)