import os
import asyncio
import logging
import re
import sqlite3
import requests
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
except ImportError:  # Web UI can run without an optional .env loader.
    def load_dotenv(*_args, **_kwargs):
        return False

try:
    from ddgs import DDGS
except ImportError:  # Searching reports a clear status until the optional package is installed.
    DDGS = None

try:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
    from telegram.ext import (
        ApplicationBuilder,
        CallbackQueryHandler,
        CommandHandler,
        MessageHandler,
        ContextTypes,
        filters,
    )
except ImportError:  # Keep web_app importable when this host runs the web UI only.
    InlineKeyboardButton = InlineKeyboardMarkup = Update = Any
    ApplicationBuilder = CallbackQueryHandler = CommandHandler = MessageHandler = None
    filters = None

    class ContextTypes:
        DEFAULT_TYPE = Any

try:
    from youtube_transcript_api import YouTubeTranscriptApi
except ImportError:  # ฟีเจอร์ YouTube จะแจ้งวิธีติดตั้งเมื่อยังไม่มีแพ็กเกจ
    YouTubeTranscriptApi = None

load_dotenv()

# ==================== การตั้งค่า (แก้ไขได้ผ่านไฟล์ .env โดยไม่ต้องแก้โค้ด) ====================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
MY_USER_ID = int(os.getenv("MY_USER_ID", "0"))
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
MODEL_NAME = os.getenv("MODEL_NAME", "hermes-agent")  # ชื่อโมเดลที่สร้างจาก Modelfile (ดู README)

# พารามิเตอร์ที่จูนสำหรับ Acer Nitro 5: i5-8300H (4 core/8 thread) / GTX1050Ti 4GB / RAM 32GB
NUM_CTX = int(os.getenv("NUM_CTX", "4096"))     # context window — ลดลงถ้า RAM ตึง
NUM_THREAD = int(os.getenv("NUM_THREAD", "4"))  # ใช้ physical core (ไม่ใช่ thread) ของ CPU
NUM_GPU = int(os.getenv("NUM_GPU", "20"))       # จำนวน layer ที่ยัดใส่ GPU — ต้องทดสอบหาค่าที่พอดี VRAM
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.7"))
KEEP_ALIVE = os.getenv("KEEP_ALIVE", "30m")     # กันโมเดลถูก unload ทำให้ต้องโหลดใหม่ทุกครั้ง
SEARCH_MAX_RESULTS = int(os.getenv("SEARCH_MAX_RESULTS", "2"))
SEARCH_TIMEOUT = int(os.getenv("SEARCH_TIMEOUT", "25"))
MAX_OUTPUT_TOKENS = int(os.getenv("MAX_OUTPUT_TOKENS", "512"))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "300"))
SCRIPT_TIMEOUT = int(os.getenv("SCRIPT_TIMEOUT", "60"))
SCRIPT_OUTPUT_LIMIT = int(os.getenv("SCRIPT_OUTPUT_LIMIT", "6000"))
YOUTUBE_MAX_CHARS = int(os.getenv("YOUTUBE_MAX_CHARS", "12000"))

PROJECT_ROOT = Path(__file__).resolve().parent
EXPERIMENTS_DIR = PROJECT_ROOT / "experiments"
CONVERSATION_DB = Path(os.getenv("CONVERSATION_DB", str(PROJECT_ROOT / "conversations.db")))
MEMORY_HISTORY_MESSAGES = int(os.getenv("MEMORY_HISTORY_MESSAGES", "4"))
MEMORY_MESSAGE_MAX_CHARS = int(os.getenv("MEMORY_MESSAGE_MAX_CHARS", "300"))
PENDING_ACTIONS = {}

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def init_conversation_db() -> None:
    """Create a small durable, per-user conversation store."""
    with sqlite3.connect(CONVERSATION_DB) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS conversation_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_conversation_user_id "
            "ON conversation_history(user_id, id)"
        )


def save_conversation_message(user_id: int, role: str, content: str) -> None:
    cleaned = content.strip()
    if not cleaned:
        return
    with sqlite3.connect(CONVERSATION_DB) as conn:
        conn.execute(
            "INSERT INTO conversation_history(user_id, role, content) VALUES (?, ?, ?)",
            (user_id, role, cleaned),
        )


def get_conversation_context(user_id: int) -> str:
    with sqlite3.connect(CONVERSATION_DB) as conn:
        rows = conn.execute(
            """
            SELECT role, content
            FROM conversation_history
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (user_id, MEMORY_HISTORY_MESSAGES),
        ).fetchall()
    if not rows:
        return ""
    rows.reverse()
    lines = []
    for role, content in rows:
        speaker = "ผู้ใช้" if role == "user" else "ผู้ช่วย"
        compact = " ".join(content.split())[:MEMORY_MESSAGE_MAX_CHARS]
        lines.append(f"{speaker}: {compact}")
    return "\n".join(lines)


def clear_conversation(user_id: int) -> None:
    with sqlite3.connect(CONVERSATION_DB) as conn:
        conn.execute("DELETE FROM conversation_history WHERE user_id = ?", (user_id,))


def search_web(query: str) -> str:
    """ค้นหาข้อมูลบนอินเทอร์เน็ต (จำกัดผลลัพธ์น้อยๆ เพื่อลดข้อความที่โมเดลต้องอ่าน -> ตอบเร็วขึ้น)"""
    try:
        if DDGS is None:
            return "ยังไม่ได้ติดตั้ง ddgs จึงยังค้นเว็บจากเครื่องนี้ไม่ได้"
        results = list(DDGS().text(query, max_results=SEARCH_MAX_RESULTS))
        if not results:
            return "ไม่พบข้อมูลที่เกี่ยวข้องบนอินเทอร์เน็ต"
        sources = []
        for index, result in enumerate(results, 1):
            title = result.get("title", "ไม่ระบุชื่อแหล่งข้อมูล")
            url = result.get("href", "")
            body = result.get("body", "").strip()
            sources.append(f"[{index}] {title}\nURL: {url}\n{body}")
        return "\n\n".join(sources)
    except Exception as e:
        logger.warning(f"Web search error: {e}")
        return "ระบบค้นหาข้อมูลขัดข้องชั่วคราว"


CURRENT_INFO_TERMS = (
    "วันนี้", "ล่าสุด", "ปัจจุบัน", "ตอนนี้", "ข่าว", "ราคา", "อากาศ",
    "ตาราง", "เที่ยวบิน", "หุ้น", "ค่าเงิน", "อัตราแลกเปลี่ยน", "กฎหมาย",
    "ค้นหาข้อมูล",
    "อัปเดต", "update", "latest", "today", "current", "news", "price",
    "weather", "stock", "exchange rate",
)


def should_search_web(query: str) -> bool:
    """ค้นเว็บอัตโนมัติเฉพาะคำถามที่ข้อมูลมีโอกาสเปลี่ยนแปลงบ่อย"""
    normalized = re.sub(r"\s+", " ", query.lower()).strip()
    return any(term in normalized for term in CURRENT_INFO_TERMS)


YOUTUBE_URL_PATTERN = re.compile(
    r"https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/|youtube\.com/embed/)([A-Za-z0-9_-]{11})",
    re.IGNORECASE,
)


def extract_youtube_urls(text: str) -> list[str]:
    """ดึง URL YouTube จากข้อความ โดยรองรับ watch, youtu.be, shorts และ embed"""
    return [match.group(0) for match in YOUTUBE_URL_PATTERN.finditer(text)]


def extract_youtube_id(url: str) -> str | None:
    match = YOUTUBE_URL_PATTERN.search(url)
    return match.group(1) if match else None


def fetch_youtube_context(url: str) -> str:
    """ดึงชื่อวิดีโอและ transcript เพื่อให้ Hermes สรุป ไม่ดาวน์โหลดวิดีโอ"""
    video_id = extract_youtube_id(url)
    if not video_id:
        return "ลิงก์ YouTube ไม่ถูกต้องหรือไม่รองรับรูปแบบนี้"
    if YouTubeTranscriptApi is None:
        return (
            "ยังไม่ได้ติดตั้งตัวดึง transcript ของ YouTube "
            "จึงยังสรุปเนื้อหาจากวิดีโอนี้ไม่ได้"
        )

    title = ""
    try:
        metadata = requests.get(
            "https://www.youtube.com/oembed",
            params={"url": url, "format": "json"},
            timeout=10,
        )
        if metadata.ok:
            title = metadata.json().get("title", "")
    except requests.RequestException:
        pass

    try:
        api = YouTubeTranscriptApi()
        try:
            transcript = api.fetch(video_id, languages=["th", "en"])
        except AttributeError:  # รองรับ API รุ่นเก่า
            transcript = YouTubeTranscriptApi.get_transcript(
                video_id, languages=["th", "en"]
            )
        parts = []
        for item in transcript:
            text = getattr(item, "text", None)
            if text is None and isinstance(item, dict):
                text = item.get("text", "")
            if text:
                parts.append(text.strip())
        transcript_text = re.sub(r"\s+", " ", " ".join(parts)).strip()
        if not transcript_text:
            return "วิดีโอนี้มี transcript ว่าง จึงสรุปเนื้อหาไม่ได้"
        if len(transcript_text) > YOUTUBE_MAX_CHARS:
            transcript_text = transcript_text[:YOUTUBE_MAX_CHARS] + " ...[ตัดเนื้อหาส่วนเกิน]"
        header = f"ชื่อวิดีโอ: {title}\n" if title else ""
        return f"แหล่งข้อมูล YouTube: {url}\n{header}Transcript:\n{transcript_text}"
    except Exception as error:
        logger.warning("YouTube transcript error for %s: %s", video_id, error)
        return (
            f"ไม่สามารถดึง transcript ของวิดีโอได้ ({type(error).__name__}) "
            "วิดีโออาจปิด transcript, จำกัดภูมิภาค หรือไม่มีคำบรรยาย"
        )


async def get_external_context(query: str) -> str:
    """รวม transcript YouTube และผลค้นเว็บตามคำขอของผู้ใช้"""
    contexts = []
    youtube_urls = extract_youtube_urls(query)
    if youtube_urls:
        youtube_results = await asyncio.wait_for(
            asyncio.to_thread(
                lambda: "\n\n".join(fetch_youtube_context(url) for url in youtube_urls[:2])
            ),
            timeout=SEARCH_TIMEOUT,
        )
        contexts.append(youtube_results)

    if should_search_web(query) or not youtube_urls:
        web_query = YOUTUBE_URL_PATTERN.sub("", query).strip()
        if web_query:
            contexts.append(await get_web_context(web_query))
    return "\n\n".join(contexts)


async def get_web_context(query: str) -> str:
    """ค้นเว็บแบบไม่บล็อก event loop และยกเลิกการรอนานเกินไป"""
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(search_web, query), timeout=SEARCH_TIMEOUT
        )
    except asyncio.TimeoutError:
        logger.warning("Web search timeout for query: %s", query)
        return "ค้นเว็บไม่ทันเวลา ให้ตอบจากความรู้ของโมเดลและระบุว่าไม่ได้ยืนยันข้อมูลล่าสุด"


def is_within_experiments(path: Path) -> bool:
    """ตรวจว่าไฟล์อยู่ใต้ experiments จริง เพื่อกัน path traversal"""
    try:
        path.resolve().relative_to(EXPERIMENTS_DIR.resolve())
        return True
    except ValueError:
        return False


def resolve_experiment_script(script_name: str) -> Path:
    """อนุญาตเฉพาะ Python script ใน experiments/ และไม่อนุญาต shell command"""
    script_name = script_name.strip().replace("\\", "/")
    if script_name.startswith("experiments/"):
        script_name = script_name[len("experiments/"):]
    candidate = (EXPERIMENTS_DIR / script_name).resolve()
    if not is_within_experiments(candidate):
        raise ValueError("อนุญาตให้รันได้เฉพาะไฟล์ภายในโฟลเดอร์ experiments/")
    if candidate.suffix != ".py":
        raise ValueError("อนุญาตเฉพาะไฟล์ .py")
    if not candidate.is_file():
        raise FileNotFoundError(f"ไม่พบไฟล์ {script_name}")
    return candidate


def run_experiment_script(script_name: str) -> str:
    """รันสคริปต์แบบไม่ผ่าน shell พร้อม timeout และจำกัด output"""
    script_path = resolve_experiment_script(script_name)
    safe_env = {
        "PATH": os.getenv("PATH", "/usr/bin:/bin"),
        "LANG": os.getenv("LANG", "C.UTF-8"),
        "PYTHONUNBUFFERED": "1",
    }
    started = time.monotonic()
    try:
        completed = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(PROJECT_ROOT),
            env=safe_env,
            capture_output=True,
            text=True,
            timeout=SCRIPT_TIMEOUT,
            check=False,
        )
        output = (completed.stdout or "") + (completed.stderr or "")
        output = output[-SCRIPT_OUTPUT_LIMIT:]
        duration = time.monotonic() - started
        status = "สำเร็จ" if completed.returncode == 0 else f"ล้มเหลว (exit {completed.returncode})"
        return f"สถานะ: {status}\nเวลา: {duration:.1f} วินาที\n\n{output or '(ไม่มี output)'}"
    except subprocess.TimeoutExpired:
        return f"หยุดการทำงานเพราะใช้เวลาเกิน {SCRIPT_TIMEOUT} วินาที"


def approval_keyboard(action_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ อนุมัติ", callback_data=f"approve:{action_id}"),
            InlineKeyboardButton("❌ ปฏิเสธ", callback_data=f"reject:{action_id}"),
        ]
    ])


async def ask_for_approval(
    update: Update,
    action_type: str,
    description: str,
    payload: dict,
) -> None:
    action_id = uuid.uuid4().hex[:8]
    PENDING_ACTIONS[action_id] = {
        "user_id": update.effective_user.id,
        "type": action_type,
        "description": description,
        "payload": payload,
        "created_at": time.time(),
    }
    await update.message.reply_text(
        f"🔐 คำขอรออนุมัติ [{action_id}]\n\n{description}\n\n"
        "ระบบจะทำเฉพาะงานที่ระบุไว้เท่านั้น และยังไม่แก้ไขไฟล์โปรเจกต์อัตโนมัติ",
        reply_markup=approval_keyboard(action_id),
    )


async def run_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """สร้างคำขอรันสคริปต์ที่อยู่ใน experiments/ เท่านั้น"""
    if not is_authorized(update):
        await update.message.reply_text("⛔ คุณไม่มีสิทธิ์ใช้งาน Bot ตัวนี้")
        return
    script_name = " ".join(context.args).strip()
    if not script_name:
        await update.message.reply_text(
            "ใช้งาน: /run <ชื่อไฟล์.py>\nตัวอย่าง: /run experiments/health_check.py"
        )
        return
    try:
        script_path = resolve_experiment_script(script_name)
    except (ValueError, FileNotFoundError) as error:
        await update.message.reply_text(f"⛔ {error}")
        return
    await ask_for_approval(
        update,
        "run_script",
        f"จะรันสคริปต์ Python:\n`{script_path.relative_to(PROJECT_ROOT)}`\n"
        f"จำกัดเวลา {SCRIPT_TIMEOUT} วินาที",
        {"script_name": str(script_path.relative_to(EXPERIMENTS_DIR))},
    )


async def improve_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """สร้างข้อเสนอปรับปรุงจากคำขอของผู้ใช้ โดยยังไม่แก้ไฟล์จริง"""
    if not is_authorized(update):
        await update.message.reply_text("⛔ คุณไม่มีสิทธิ์ใช้งาน Bot ตัวนี้")
        return
    request = " ".join(context.args).strip()
    if not request:
        await update.message.reply_text(
            "ใช้งาน: /improve <สิ่งที่ต้องการเพิ่ม>\n"
            "ตัวอย่าง: /improve เพิ่มคำสั่งสรุปไฟล์ log"
        )
        return
    plan_prompt = (
        "วิเคราะห์คำขอพัฒนาบอทต่อไปนี้และเสนอแผนแบบสั้น กระชับ 3-6 ขั้นตอน "
        "ระบุไฟล์ที่คาดว่าจะต้องแก้ การทดสอบ และความเสี่ยง "
        "ห้ามเขียนคำสั่ง shell และห้ามอ้างว่าดำเนินการแล้ว\n\n"
        f"คำขอ: {request}"
    )
    try:
        plan = await asyncio.to_thread(call_ollama, plan_prompt)
    except Exception as error:
        await update.message.reply_text(f"ไม่สามารถสร้างข้อเสนอได้: {error}")
        return
    await ask_for_approval(
        update,
        "improvement_plan",
        f"ข้อเสนอการปรับปรุง:\n{plan.strip()}\n\n"
        "การอนุมัตินี้เป็นการยืนยันให้เก็บข้อเสนอไว้เท่านั้น "
        "ยังไม่มีการแก้ไขไฟล์หรือรีสตาร์ทบอท",
        {"request": request, "plan": plan.strip()},
    )


async def approval_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id != MY_USER_ID:
        await query.answer("ไม่มีสิทธิ์", show_alert=True)
        return
    await query.answer()
    action, action_id = query.data.split(":", 1)
    pending = PENDING_ACTIONS.pop(action_id, None)
    if not pending or pending["user_id"] != query.from_user.id:
        await query.edit_message_text("คำขอนี้หมดอายุหรือถูกดำเนินการไปแล้ว")
        return
    if action == "reject":
        await query.edit_message_text(f"❌ ปฏิเสธคำขอ [{action_id}] แล้ว")
        return
    if action != "approve":
        await query.edit_message_text("คำขอไม่ถูกต้อง")
        return
    if pending["type"] == "improvement_plan":
        await query.edit_message_text(
            f"✅ อนุมัติให้เก็บข้อเสนอ [{action_id}] แล้ว\n\n"
            "ยังไม่มีการแก้ไขไฟล์จริง หากต้องการให้สร้าง patch ต้องตรวจสอบและอนุมัติอีกขั้น"
        )
        return
    if pending["type"] == "run_script":
        await query.edit_message_text(f"⏳ กำลังรันงาน [{action_id}]...")
        result = await asyncio.to_thread(
            run_experiment_script, pending["payload"]["script_name"]
        )
        result_text = f"🧪 ผลการทดลอง [{action_id}]\n\n{result}"
        for start in range(0, len(result_text), 3900):
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=result_text[start:start + 3900],
            )


def is_authorized(update: Update) -> bool:
    return update.effective_user.id == MY_USER_ID


def call_ollama(prompt: str, model_name: str | None = None, options_override: dict | None = None) -> str:
    """เรียก Ollama API แบบ blocking — ฟังก์ชันนี้จะถูกรันใน thread แยกเสมอ
    เพื่อไม่ให้บอทค้างทั้งตัวระหว่างรอโมเดลประมวลผล"""
    options = {
        "num_ctx": NUM_CTX,
        "num_thread": NUM_THREAD,
        "num_gpu": NUM_GPU,
        "temperature": TEMPERATURE,
        "num_predict": MAX_OUTPUT_TOKENS,
        "repeat_penalty": 1.1,
    }
    if options_override:
        options.update({key: value for key, value in options_override.items() if not key.startswith("_")})
    payload = {
        "model": model_name or MODEL_NAME,
        "prompt": prompt,
        "stream": False,
        "keep_alive": KEEP_ALIVE,
        "options": options,
    }
    if options_override and options_override.get("_format"):
        payload["format"] = options_override["_format"]
        payload["think"] = False
    if options_override and "_think" in options_override:
        payload["think"] = options_override["_think"]
    response = requests.post(OLLAMA_URL, json=payload, timeout=(options_override or {}).get("_timeout", REQUEST_TIMEOUT))
    response.raise_for_status()
    return response.json().get("response", "เกิดข้อผิดพลาดในการประมวลผลจากฝั่ง AI")


SYSTEM_PERSONA = (
    "คุณคือ AI Supervisor ประสิทธิภาพสูง ทำงานด้วยแนวคิดแบบ first principles และวินัยเข้มข้น "
    "คุณไม่ได้อ้างว่าเป็น Elon Musk และไม่เลียนแบบตัวบุคคลจริง แต่ใช้หลักคิดเชิงวิศวกรรม ความเร็ว และความรับผิดชอบ "
    "เป้าหมายหลักคือช่วยผู้ใช้บรรลุเป้าหมายด้วยขั้นตอนที่สั้น ชัด และวัดผลได้ "
    "แตกปัญหาเป็นข้อเท็จจริงพื้นฐาน ตัดสมมติฐานที่ไม่จำเป็น และไม่ยอมรับคำตอบว่าเคยทำแบบนี้มาตลอด "
    "จัดลำดับความสำคัญอย่างเด็ดขาด ให้โฟกัสเฉพาะ critical path และเสนอให้ลบ มอบหมาย หรือทำอัตโนมัติงานที่ไม่เร่งเป้าหมาย "
    "แบ่งงานเป็น timebox สั้นๆ โดยใช้กฎ 5 นาที และผลักดันให้เริ่มทำทันที "
    "สื่อสารตรง กระชับ วิเคราะห์ได้ชัด เรียกการผัดวันหรือการทำให้ซับซ้อนเกินจำเป็นอย่างสุภาพแต่ตรงไปตรงมา "
    "ผลักดันให้ทำ prototype และทดสอบเร็ว ยอมรับความล้มเหลวที่แก้ไขได้ และวนรอบปรับปรุงจากข้อมูลจริง "
    "ทุกครั้งที่ผู้ใช้แจ้งเป้าหมายหรือสถานะ ให้ถาม deadline ที่แน่นอน เสนอให้ลดเวลาประเมินลงครึ่งหนึ่ง "
    "ขอขั้นตอนที่ทำให้เสร็จได้ภายใน 1 ชั่วโมง และถามว่า 'คอขวดที่ใหญ่ที่สุดตอนนี้คืออะไร และทำไมคุณยังไม่กำจัดมัน?' "
    "ถ้าคำถามมี deadline อยู่แล้ว ให้ยึด deadline นั้นและอย่าถามซ้ำโดยไม่จำเป็น "
    "ถ้าเป็นเรื่องเทคนิค ให้เริ่มจากคำสั่งหรือการทดลองที่ตรวจสอบได้ทันที พร้อมเกณฑ์สำเร็จและทางแก้ถัดไป "
    "ตอบภาษาเดียวกับผู้ใช้ สรุปคำตอบก่อน ไม่เกริ่นยาว ไม่ทวนคำถาม ไม่แต่งข้อมูล "
    "แยกข้อเท็จจริงออกจากการอนุมาน และหากไม่แน่ใจให้บอกตรงๆ "
    "รักษาความปลอดภัยและความเป็นส่วนตัว ห้ามเปิดเผย token รหัสผ่าน หรือข้อมูลลับ "
    "เมื่อมีข้อมูลจากเว็บหรือ transcript ให้ใช้เฉพาะข้อมูลที่เกี่ยวข้องและอ้างอิงไม่เกิน 3 รายการในรูปแบบ [1], [2], [3] "
)



def build_prompt(
    question: str, web_context: str = "", conversation_context: str = ""
) -> str:
    sections = [SYSTEM_PERSONA]
    if conversation_context:
        sections.append(
            "บริบทจากบทสนทนาก่อนหน้า ใช้เฉพาะเมื่อเกี่ยวข้อง และอย่าอ้างว่าเป็นข้อเท็จจริงใหม่:\n"
            + conversation_context
        )
    if web_context:
        sections.append(
            "ข้อมูลจากอินเทอร์เน็ตที่ใช้ประกอบคำตอบ (อาจไม่สมบูรณ์):\n"
            + web_context
        )
    sections.append(f"ข้อความล่าสุดจากผู้ใช้: {question}")
    return "\n\n".join(sections)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        await update.message.reply_text("⛔ คุณไม่มีสิทธิ์ใช้งาน Bot ตัวนี้")
        return
    await update.message.reply_text(
        "สวัสดีครับ! ระบบพร้อมรับคำสั่งเฉพาะคุณเรียบร้อยแล้ว\n\n"
        "💬 พิมพ์คำถามตรงๆ = ตอบจากความรู้ของโมเดลเลย (เร็ว)\n"
        "🔍 /search <คำถาม> = ค้นหาข้อมูลบนอินเทอร์เน็ตก่อนตอบ\n"
        "🧪 /run <ไฟล์.py> = ขออนุมัติรันสคริปต์ใน experiments/\n"
        "🛠️ /improve <คำขอ> = สร้างข้อเสนอปรับปรุงโดยยังไม่แก้ไฟล์จริง"
    )


def ensure_reply_ends_with_khrab(text: str) -> str:
    """Ensure final user-facing Thai replies end politely and consistently."""
    reply = text.rstrip()
    return reply if reply.endswith("ครับ") else f"{reply}\n\nครับ"


async def process_and_reply(update: Update, context: ContextTypes.DEFAULT_TYPE, prompt: str, thinking_text: str):
    """ฟังก์ชันกลาง: ส่ง prompt ให้ Ollama แล้วตอบกลับ ใช้ร่วมกันทั้งโหมดค้นหาและไม่ค้นหา"""
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    processing_msg = await update.message.reply_text(thinking_text)

    try:
        reply = await asyncio.to_thread(call_ollama, prompt)
    except requests.exceptions.Timeout:
        reply = "⏱️ โมเดลประมวลผลนานเกินไป ลองถามใหม่แบบสั้นลง หรือรอเครื่องว่างแล้วลองใหม่อีกครั้ง"
    except requests.exceptions.ConnectionError:
        reply = "❌ เชื่อมต่อ Ollama ไม่ได้ ตรวจสอบว่ารัน `ollama serve` อยู่หรือยัง"
    except Exception as e:
        reply = f"ไม่สามารถติดต่อ Ollama ได้: {e}"

    reply = ensure_reply_ends_with_khrab(reply)

    try:
        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=processing_msg.message_id)
    except Exception:
        pass  # ข้อความอาจถูกลบไปแล้ว ไม่เป็นไร

    # Telegram จำกัดข้อความไม่เกิน 4096 ตัวอักษร ต้องตัดแบ่งถ้ายาวเกิน
    for i in range(0, len(reply), 4000):
        await update.message.reply_text(reply[i:i + 4000])
    return reply


async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """สั่งค้นหาแบบชัดเจนด้วย /search <คำถาม> — จะค้นเว็บก่อนแล้วค่อยส่งให้ Hermes ตอบ"""
    if not is_authorized(update):
        await update.message.reply_text("⛔ คุณไม่มีสิทธิ์ใช้งาน Bot ตัวนี้")
        return

    query = " ".join(context.args).strip()
    if not query:
        await update.message.reply_text("พิมพ์คำถามต่อท้ายด้วยครับ เช่น: /search อากาศกรุงเทพวันนี้")
        return

    try:
        web_context = await get_external_context(query)
    except asyncio.TimeoutError:
        web_context = "ค้นข้อมูลไม่ทันเวลา ให้ตอบเท่าที่มีข้อมูลและระบุว่าไม่ได้ยืนยันข้อมูลล่าสุด"
    user_id = update.effective_user.id
    conversation_context = get_conversation_context(user_id)
    combined_prompt = build_prompt(query, web_context, conversation_context)
    reply = await process_and_reply(
        update, context, combined_prompt,
        "🔍 กำลังค้นหาข้อมูลและคิดคำตอบ (บนเครื่องนี้อาจใช้เวลาสักครู่)..."
    )
    save_conversation_message(user_id, "user", query)
    save_conversation_message(user_id, "assistant", reply)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ข้อความปกติ (ไม่ใช่ /search) — ตอบจากความรู้ของโมเดลตรงๆ โดยไม่ค้นเว็บ"""
    if not is_authorized(update):
        await update.message.reply_text("⛔ คุณไม่มีสิทธิ์ใช้งาน Bot ตัวนี้")
        return

    user_text = update.message.text.strip()
    has_external_request = should_search_web(user_text) or bool(extract_youtube_urls(user_text))
    try:
        web_context = await get_external_context(user_text) if has_external_request else ""
    except asyncio.TimeoutError:
        web_context = "ค้นข้อมูลไม่ทันเวลา ให้ตอบเท่าที่มีข้อมูลและระบุว่าไม่ได้ยืนยันข้อมูลล่าสุด"
    user_id = update.effective_user.id
    conversation_context = get_conversation_context(user_id)
    combined_prompt = build_prompt(user_text, web_context, conversation_context)
    thinking_text = (
        "🔎 กำลังค้นข้อมูลล่าสุดและสรุปคำตอบ..."
        if web_context else "🤔 กำลังสรุปคำตอบให้กระชับ..."
    )
    reply = await process_and_reply(
        update, context, combined_prompt,
        thinking_text
    )
    save_conversation_message(user_id, "user", user_text)
    save_conversation_message(user_id, "assistant", reply)


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clear only the requesting user's saved conversation context."""
    if not is_authorized(update):
        await update.message.reply_text("⛔ คุณไม่มีสิทธิ์ใช้งาน Bot ตัวนี้")
        return
    clear_conversation(update.effective_user.id)
    await update.message.reply_text("ล้างความจำบทสนทนาปัจจุบันแล้วครับ")


if __name__ == '__main__':
    if ApplicationBuilder is None:
        raise RuntimeError("กรุณาติดตั้ง python-telegram-bot ก่อนรัน Telegram bot")
    if not TELEGRAM_TOKEN or MY_USER_ID == 0:
        raise RuntimeError("กรุณาตั้งค่า TELEGRAM_TOKEN และ MY_USER_ID ในไฟล์ .env ก่อนรัน")

    init_conversation_db()
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset_command))
    app.add_handler(CommandHandler("search", search_command))
    app.add_handler(CommandHandler("run", run_command))
    app.add_handler(CommandHandler("improve", improve_command))
    app.add_handler(CallbackQueryHandler(approval_callback, pattern=r"^(approve|reject):"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("Private Agent Bot (Hermes + Web Search) กำลังทำงาน...")
    app.run_polling()
