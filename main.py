"""
ChatTop Premium Flask Server v3
All endpoints + Admin routes + AI push + Broadcast-all support
"""
import os, json, time, logging, requests
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory, Response
from flask_cors import CORS

import firebase_admin
from firebase_admin import credentials, messaging

try:
    from langdetect import detect as lang_detect
    LANGDETECT_OK = True
except ImportError:
    LANGDETECT_OK = False

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
log = logging.getLogger(__name__)

app  = Flask(__name__, static_folder='static', static_url_path='/static')
CORS(app, resources={r'/api/*': {'origins': '*'}, r'/admin*': {'origins': '*'}})

BASE_DIR = Path(__file__).parent

# ── Firebase ──────────────────────────────────────────────────
_fb_ready = False
try:
    cred = credentials.Certificate(str(BASE_DIR / 'service-account.json'))
    firebase_admin.initialize_app(cred)
    _fb_ready = True
    log.info('Firebase Admin initialized')
except Exception as e:
    log.error(f'Firebase: {e}')

# ── Lang → Neural Voice ───────────────────────────────────────
LANG_VOICE = {
    'en':'en-US-AriaNeural','hi':'hi-IN-SwaraNeural','ta':'ta-IN-PallaviNeural',
    'te':'te-IN-ShrutiNeural','kn':'kn-IN-SapnaNeural','ml':'ml-IN-SobhanaNeural',
    'bn':'bn-IN-TanishaaNeural','mr':'mr-IN-AarohiNeural','gu':'gu-IN-DhwaniNeural',
    'pa':'pa-IN-OjasNeural','ur':'ur-PK-UzmaNeural','ar':'ar-AE-FatimaNeural',
    'fr':'fr-FR-DeniseNeural','de':'de-DE-KatjaNeural','es':'es-ES-ElviraNeural',
    'pt':'pt-BR-FranciscaNeural','ru':'ru-RU-SvetlanaNeural','zh':'zh-CN-XiaoxiaoNeural',
    'ja':'ja-JP-NanamiNeural','ko':'ko-KR-SunHiNeural','it':'it-IT-ElsaNeural',
    'tr':'tr-TR-EmelNeural','pl':'pl-PL-ZofiaNeural','nl':'nl-NL-ColetteNeural',
    'sv':'sv-SE-SofieNeural','no':'nb-NO-PernilleNeural','da':'da-DK-ChristelNeural',
    'fi':'fi-FI-NooraNeural','id':'id-ID-GadisNeural','ms':'ms-MY-YasminNeural',
    'vi':'vi-VN-HoaiMyNeural','th':'th-TH-PremwadeeNeural',
}
TTS_API  = 'https://ttsv2.fastdevelopers.workers.dev/tts'
IMG_API  = 'https://ayaanmods.site/aiimage.php'
IMG_KEY  = 'annonymousai'
TOKENS_FILE = BASE_DIR / 'fcm_tokens.json'


def _load_tokens() -> dict:
    if TOKENS_FILE.exists():
        try: return json.loads(TOKENS_FILE.read_text())
        except Exception: pass
    return {}

def _save_tokens(t: dict):
    TOKENS_FILE.write_text(json.dumps(t, indent=2))

def _get_all_tokens() -> list[str]:
    tokens = _load_tokens()
    result = []
    for v in tokens.values():
        t = v.get('token') if isinstance(v, dict) else v
        if t: result.append(t)
    return result

def _fcm_send(token:str, title:str, body:str, data:dict|None=None, ntype:str='message') -> str:
    data = data or {}
    data['type'] = ntype
    is_call = (ntype == 'call')
    webpush_actions = [
        messaging.WebpushNotificationAction(action='accept',  title='✅ Accept'),
        messaging.WebpushNotificationAction(action='decline', title='❌ Decline'),
    ] if is_call else []
    msg = messaging.Message(
        token=token,
        notification=messaging.Notification(title=title, body=body),
        android=messaging.AndroidConfig(
            priority='high',
            notification=messaging.AndroidNotification(
                title=title, body=body,
                sound='default', notification_count=1,
                visibility=messaging.AndroidNotification.VISIBILITY_PUBLIC,
                channel_id='calls' if is_call else 'messages',
                priority=messaging.AndroidNotification.PRIORITY_HIGH,
            ),
        ),
        webpush=messaging.WebpushConfig(
            headers={'Urgency':'high','TTL':'60'},
            notification=messaging.WebpushNotification(
                title=title, body=body,
                require_interaction=is_call,
                actions=webpush_actions,
                silent=False,
            ),
        ),
        data={str(k):str(v) for k,v in data.items()},
    )
    return messaging.send(msg)


# ══════════════════════════════════════════════════════════════
#  PAGES
# ══════════════════════════════════════════════════════════════

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/admin')
@app.route('/admin/')
def admin_panel():
    return send_from_directory('static', 'admin.html')

@app.route('/<path:fn>')
def static_files(fn):
    return send_from_directory('static', fn)


# ══════════════════════════════════════════════════════════════
#  AI IMAGE GENERATION
# ══════════════════════════════════════════════════════════════

@app.route('/api/generate-image', methods=['POST','GET'])
def generate_image():
    if request.method == 'POST':
        b = request.get_json(silent=True) or {}
        prompt = b.get('prompt','').strip()
    else:
        prompt = request.args.get('prompt','').strip()
    if not prompt:
        return jsonify({'success':False,'error':'prompt required'}), 400
    log.info(f'[IMG] "{prompt[:60]}"')
    last_err = None
    for attempt in range(1,4):
        try:
            r = requests.get(IMG_API, params={'key':IMG_KEY,'prompt':prompt},
                             timeout=35, headers={'Accept':'application/json'})
            r.raise_for_status()
            data = r.json()
            if data.get('success') and data.get('images'):
                log.info(f'[IMG] Got {len(data["images"])} images')
                return jsonify({'success':True,'images':data['images'],
                                'prompt':prompt,'settings':data.get('settings',{})})
            last_err = data.get('error','No images')
        except requests.Timeout: last_err='timeout'
        except Exception as e: last_err=str(e)
        if attempt<3: time.sleep(attempt)
    log.error(f'[IMG] Failed: {last_err}')
    return jsonify({'success':False,'error':last_err}), 502


# ══════════════════════════════════════════════════════════════
#  TTS
# ══════════════════════════════════════════════════════════════

@app.route('/api/tts', methods=['POST'])
def tts():
    b = request.get_json(silent=True) or {}
    text  = b.get('text','').strip()
    voice = b.get('voice','').strip()
    lang  = b.get('lang','').strip().lower()
    if not text:
        return jsonify({'success':False,'error':'text required'}), 400
    if not voice:
        if not lang and LANGDETECT_OK:
            try: lang=lang_detect(text)
            except Exception: lang='en'
        voice = LANG_VOICE.get(lang, LANG_VOICE['en'])
    log.info(f'[TTS] voice={voice} len={len(text)}')
    try:
        r = requests.post(TTS_API, json={'text':text,'voice':voice}, timeout=22)
        r.raise_for_status()
        return Response(r.content, status=200,
                        mimetype=r.headers.get('Content-Type','audio/mpeg'),
                        headers={'Cache-Control':'no-store','Access-Control-Allow-Origin':'*'})
    except requests.Timeout: return jsonify({'success':False,'error':'TTS timeout'}), 504
    except Exception as e: return jsonify({'success':False,'error':str(e)}), 502

@app.route('/api/tts/voices')
def tts_voices():
    names={'en':'English','hi':'Hindi','ta':'Tamil','te':'Telugu','kn':'Kannada',
           'ml':'Malayalam','bn':'Bengali','ar':'Arabic','fr':'French','de':'German',
           'es':'Spanish','pt':'Portuguese','ru':'Russian','zh':'Chinese',
           'ja':'Japanese','ko':'Korean','it':'Italian','tr':'Turkish','pl':'Polish',
           'nl':'Dutch','id':'Indonesian','ms':'Malay','vi':'Vietnamese','th':'Thai'}
    return jsonify({'voices':[{'code':c,'name':names.get(c,c.upper()),'voice':v}
                               for c,v in LANG_VOICE.items()]})


# ══════════════════════════════════════════════════════════════
#  FCM PUSH
# ══════════════════════════════════════════════════════════════

@app.route('/api/send-notification', methods=['POST'])
def send_notification():
    b = request.get_json(silent=True) or {}
    token = b.get('token','').strip()
    title = b.get('title','New Notification')
    body  = b.get('body','')
    ntype = b.get('type','message')
    extra = b.get('data',{})
    if not token: return jsonify({'success':False,'error':'token required'}), 400
    if not _fb_ready: return jsonify({'success':False,'error':'Firebase not ready'}), 503
    try:
        mid = _fcm_send(token, title, body, extra, ntype)
        log.info(f'[FCM] {ntype} → {token[:16]}...')
        return jsonify({'success':True,'messageId':mid})
    except Exception as e:
        log.error(f'[FCM] {e}')
        return jsonify({'success':False,'error':str(e)}), 502


@app.route('/api/send-broadcast', methods=['POST'])
def send_broadcast():
    b = request.get_json(silent=True) or {}
    tokens  = b.get('tokens', [])
    title   = b.get('title','📢 Admin')
    body    = b.get('body','')
    extra   = {str(k):str(v) for k,v in (b.get('data') or {}).items()}
    extra['type'] = 'broadcast'
    broadcast_all = b.get('broadcast_all', False)

    # If broadcast_all=True, load all stored tokens
    if broadcast_all:
        tokens = _get_all_tokens()

    if not tokens: return jsonify({'success':False,'error':'no tokens','sent':0}), 400
    if not _fb_ready: return jsonify({'success':False,'error':'Firebase not ready'}), 503

    sent=failed=0
    for i in range(0,len(tokens),500):
        chunk=tokens[i:i+500]
        mm=messaging.MulticastMessage(
            tokens=chunk,
            notification=messaging.Notification(title=title,body=body),
            android=messaging.AndroidConfig(
                priority='high',
                notification=messaging.AndroidNotification(
                    title=title,body=body,sound='default',
                    visibility=messaging.AndroidNotification.VISIBILITY_PUBLIC,
                ),
            ),
            webpush=messaging.WebpushConfig(
                headers={'Urgency':'high'},
                notification=messaging.WebpushNotification(title=title,body=body),
            ),
            data=extra,
        )
        resp=messaging.send_each_for_multicast(mm)
        sent+=resp.success_count; failed+=resp.failure_count
    log.info(f'[FCM-BC] sent={sent} failed={failed}')
    return jsonify({'success':True,'sent':sent,'failed':failed})


@app.route('/api/send-call-notification', methods=['POST'])
def send_call_notification():
    b=request.get_json(silent=True) or {}
    token=b.get('token','').strip()
    caller=b.get('callerName','Unknown')
    cid=b.get('callerId','')
    video=b.get('isVideo',False)
    avatar=b.get('callerAvatar','')
    if not token: return jsonify({'success':False,'error':'token required'}), 400
    if not _fb_ready: return jsonify({'success':False,'error':'Firebase not ready'}), 503
    data={'callerName':caller,'callerId':cid,'isVideo':str(video).lower(),
          'senderAvatar':avatar,'chatId':cid}
    try:
        mid=_fcm_send(token,f'📞 {caller}',f'Incoming {"Video" if video else "Voice"} Call',data,'call')
        return jsonify({'success':True,'messageId':mid})
    except Exception as e:
        return jsonify({'success':False,'error':str(e)}), 502


@app.route('/api/send-ai-reply', methods=['POST'])
def send_ai_reply():
    b=request.get_json(silent=True) or {}
    uid=b.get('uid','').strip()
    preview=b.get('preview','AURA AI replied').strip()
    if not uid: return jsonify({'success':False,'error':'uid required'}), 400
    tokens=_load_tokens()
    entry=tokens.get(uid)
    token=(entry.get('token') if isinstance(entry,dict) else entry) if entry else None
    if not token: return jsonify({'success':False,'error':'token not found'}), 404
    if not _fb_ready: return jsonify({'success':False,'error':'Firebase not ready'}), 503
    try:
        mid=_fcm_send(token,'AURA AI',preview,
                      {'type':'ai_reply','aiName':'AURA AI','body':preview},'ai_reply')
        return jsonify({'success':True,'messageId':mid})
    except Exception as e:
        return jsonify({'success':False,'error':str(e)}), 502


@app.route('/api/save-token', methods=['POST'])
def save_token():
    b=request.get_json(silent=True) or {}
    uid=b.get('uid','').strip()
    token=b.get('token','').strip()
    platform=b.get('platform','web')
    if not uid or not token: return jsonify({'success':False,'error':'uid+token required'}), 400
    tokens=_load_tokens()
    tokens[uid]={'token':token,'platform':platform,'ts':int(time.time())}
    _save_tokens(tokens)
    log.info(f'[TOKEN] Saved uid={uid[:12]}...')
    return jsonify({'success':True})


@app.route('/api/get-token')
def get_token():
    uid=request.args.get('uid','').strip()
    if not uid: return jsonify({'success':False,'error':'uid required'}), 400
    tokens=_load_tokens()
    entry=tokens.get(uid)
    if entry:
        t=entry.get('token') if isinstance(entry,dict) else entry
        if t: return jsonify({'success':True,'token':t})
    return jsonify({'success':False,'error':'not found'}), 404


@app.route('/api/test-notification')
def test_notification():
    tokens=_load_tokens()
    return jsonify({
        'success':True,'server':'ChatTop v3',
        'firebase':'ready' if _fb_ready else 'error',
        'langdetect':LANGDETECT_OK,'tts_api':TTS_API,'image_api':IMG_API,
        'saved_tokens':len(tokens),
    })


if __name__ == '__main__':
    port=int(os.environ.get('PORT',5000))
    log.info(f'ChatTop v3 starting on port {port}')
    app.run(host='0.0.0.0', port=port, debug=False)
