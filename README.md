# Chat-BTH

Chat-BTH คือผู้ช่วย AI แบบใช้งานส่วนตัวบนเครื่อง ใช้ Ollama เป็นค่าเริ่มต้น มี Web UI สำหรับแชทและสร้างเว็บไซต์/แดชบอร์ด และมี Telegram bot สำหรับใช้งานจากมือถือ

เอกสารนี้อัปเดตจากโปรเจกต์จริงบน Dell ณ วันที่ 10 ตุลาคม 2026

## สถานะปัจจุบัน

- Hermes Agent Gateway ทำงานอยู่และเชื่อมต่อ Telegram ได้
- โมเดลหลักของ Hermes Agent คือ `gemma3:4b`
- ตั้ง `context_length` และ `ollama_num_ctx` ไว้ที่ 65,536 tokens
- Ollama พบโมเดลที่ติดตั้ง 11 รายการ
- Hermes Doctor ไม่พบ Security Advisory
- Regression tests ล่าสุด: 130 รายการ, ผ่าน 128 รายการ, ล้มเหลว 1 รายการ และ error 1 รายการ
- Python compile ผ่าน; การตรวจ JavaScript ยังรันไม่ได้เพราะเครื่อง Dell ไม่มี Node.js

หมายเหตุ: ผลทดสอบที่ไม่ผ่านทั้งสองรายการเกิดจากขั้นตอนตรวจ `node --check` แต่ไม่มีคำสั่ง `node` ในเครื่อง ไม่ใช่ปัญหาจาก Ollama หรือโมเดล

## ความสามารถปัจจุบัน

### Web UI

- **Chat** — สร้างโปรเจกต์และแชทหลายรายการ เปลี่ยนชื่อ ลบ เลือกโมเดล แนบไฟล์ข้อความ และค้นเว็บเมื่อเปิด “ค้นเว็บ”
- **Build** — เปิด/สร้างไฟล์ใน workspace, ให้ AI วิเคราะห์และแก้ไฟล์, รันคำสั่งที่อนุญาต, ตรวจ HTML/CSS/JavaScript และเปิด Live Preview
- **Build Assistant** — คุยเพื่อวางแผนหรือขอคำแนะนำก่อนให้ AI แก้ไฟล์จริง
- **Guided Build (BTH Create)** — ตอบคำถามทีละข้อ ตรวจ Project Spec, Freeze ข้อกำหนด, วิเคราะห์ส่วนที่ขาด, สร้างงานตามลำดับ และ Verification
- **Preview Editor** — เลือก Element ใน Preview แล้วแก้ข้อความ ลิงก์ รูปภาพ และ style ที่รองรับ โดยต้องอนุมัติ patch ก่อนใช้
- **ประวัติไฟล์** — revision, undo, redo, restore และ compare
- **ตรวจสอบ/ส่งออก** — diagnostics, security audit, audit log, metrics, รายงาน Build และ export เว็บไซต์เป็น ZIP
- **Notebook** — สร้าง ค้นหา แก้ไข ลบ และส่งออกเป็น .txt เก็บข้อมูลใน localStorage ของเบราว์เซอร์
- **Worker Compute** — ดูสถานะ Ollama, GPU, RAM และ system load; บันทึกรายชื่อเครื่องใน LAN และเพิ่ม provider แบบ OpenAI-compatible หรือ Google AI Studio
- **สร้างเสียง** — สร้าง MP3 จากคำตอบด้วย Piper และ FFmpeg บนเครื่อง (ไม่ส่งข้อความออกอินเทอร์เน็ต)
- **ธีม Web UI** — Windows XP, Light, Neon, macOS, Cyberpunk, Synthwave, Blueprint, Dracula, Matrix, Win98 และ E-Ink

### ประเภทงานที่ Guided Build รองรับ

- Internal Dashboard
- เว็บไซต์หลายหน้า: Corporate Website, Organization Portal, Retail & Product Catalog, Service Business, Knowledge & Document Hub
- เว็บไซต์มาตรฐาน: Landing Page, Company Website, Portfolio, Product Catalog, Content / Blog
- Catalog / Library: Digital Library, Document Center, Product & Service Catalog, Media Archive, Learning Library

เว็บไซต์กำหนดหน้าได้ เช่น หน้าหลัก เกี่ยวกับองค์กร นโยบาย กฎระเบียบ/เอกสาร คลังความรู้ สินค้า บริการ ข่าวสาร ติดต่อ และเนื้อหาทั่วไป ระบบจะสร้าง HTML, CSS, JavaScript และเมนูเชื่อมโยงให้

### Telegram bot

- ตอบคำถามจาก Ollama
- /search <คำถาม> ค้นเว็บก่อนตอบ
- สรุป YouTube จากชื่อและ transcript หากวิดีโอมีคำบรรยาย
- /run <ไฟล์.py> ขออนุมัติรันไฟล์ Python ภายใน experiments/
- /improve <คำขอ> สร้างแผนปรับปรุงโดยยังไม่แก้ไฟล์จริง
- จำกัดผู้ใช้ด้วย MY_USER_ID และต้องกดอนุมัติก่อนรันสคริปต์

## ติดตั้ง

ต้องมี Python 3.10 ขึ้นไป, Ollama ที่กำลังทำงาน และโมเดลอย่างน้อยหนึ่งตัว

    python -m venv venv
    ./venv/bin/pip install -r requirements.txt
    ollama pull gemma3:4b

สร้างไฟล์ .env ที่โฟลเดอร์หลัก:

    OLLAMA_URL=http://127.0.0.1:11434/api/generate
    MODEL_NAME=gemma3:4b
    WEB_HOST=127.0.0.1
    WEB_PORT=8080
    # ไฟล์โมเดล Piper ที่ดาวน์โหลด/เก็บไว้ในเครื่องแล้ว
    HERMES_PIPER_MODEL_TH=/absolute/path/to/th_TH-voice.onnx

### เตรียมเสียงแบบ local

ติดตั้ง dependency ตามปกติด้วย `./venv/bin/pip install -r requirements.txt` ซึ่งจะติดตั้งคำสั่ง `piper`; ต้องมี `ffmpeg` ใน `PATH` ด้วย สำหรับ Python 3.14 ให้ติดตั้ง TLTK แบบไม่ดึง dependency corpus ที่ยังไม่รองรับด้วย `./venv/bin/pip install --no-deps tltk==1.10` จากนั้นนำไฟล์โมเดล Piper ที่รองรับภาษาไทยมาเก็บไว้ในเครื่อง **พร้อมไฟล์ config ที่มีชื่อต่อท้าย `.onnx.json`** แล้วชี้ `HERMES_PIPER_MODEL_TH` ไปยังไฟล์ `.onnx` ดังตัวอย่างข้างต้น ระบบจะเรียก `python -m piper` จาก virtual environment เดียวกับ Web UI เพื่อให้ใช้งาน phonemizer ไทยได้ถูกต้อง

การดาวน์โหลดโมเดลอาจทำครั้งเดียวบนเครื่องที่เชื่อมต่ออินเทอร์เน็ต แล้วคัดลอกทั้งสองไฟล์มายังเครื่องใช้งานได้ หลังจากตั้งค่าแล้ว การกดสร้างเสียงใน Web UI และ `voice_agent.py` จะเรียกเฉพาะ Piper และ FFmpeg ในเครื่อง ไม่มีการส่งข้อความไปยังบริการ TTS ภายนอก

ถ้าจะใช้ Telegram ให้เพิ่ม TELEGRAM_TOKEN และ MY_USER_ID อย่า commit .env หรือ API key

## วิธีใช้งานแบบเร็ว

### เปิด Web UI

    ollama serve
    ./venv/bin/python web_app.py

เปิด [http://127.0.0.1:8080](http://127.0.0.1:8080) ในเบราว์เซอร์ ห้ามเปิด web/index.html ด้วย file:// เพราะหน้าเว็บต้องเรียก API จาก server

1. สร้างโปรเจกต์จากเมนูด้านซ้าย
2. ใช้ Chat เพื่อสนทนา หรือ Build เพื่อสร้างงาน
3. เลือกโมเดลและพิมพ์คำสั่งให้ชัดเจน
4. เปิด “ค้นเว็บ” เมื่ออยากได้ข้อมูลปัจจุบัน
5. สร้างเว็บไซต์ด้วย Build > Guided Build ตอบคำถาม ตรวจสรุป แล้วกด Freeze & Build
6. ตรวจ Preview และใช้ Files / History / Security Audit / Export ตามต้องการ

### สร้างเว็บไซต์

ไปที่ Build > Guided Build แล้วเลือก blueprint กรอกชื่อ โทนสี และหน้า/หมวดหมู่:

1. กด “ตรวจ Project Spec”
2. แก้ข้อมูลหากระบบแจ้งว่ายังไม่ครบ
3. กด “Freeze & Build”
4. ตรวจ Verification และเปิด Preview
5. แก้ไฟล์โดยตรง หรือเลือก Element ใน Preview ให้ Build Assistant เสนอ patch
6. กด “ส่งออก ZIP” เมื่อผ่านการตรวจสอบ

Catalog/Library รองรับค้นหา เรียงลำดับ หน้าต่างรายละเอียด และฟอร์มเพิ่มรายการพร้อมปก/PDF ข้อมูลรายการเก็บใน IndexedDB ของเบราว์เซอร์ จึงเหมาะกับต้นแบบหรือเครื่องเดียว

### เปิด Telegram bot

    ollama serve
    ./venv/bin/python bot.py

พิมพ์ /start เพื่อดูคำสั่ง ข้อความปกติจะตอบจากโมเดลโดยตรง ระบบจะค้นเว็บอัตโนมัติเมื่อข้อความสื่อว่าต้องการข้อมูลล่าสุด หรือมีลิงก์ YouTube

## โมเดลและ provider

### เหตุผลที่เลือก `gemma3:4b` บน VRAM 8 GB

Hermes Agent บังคับให้โมเดลมี Context Window อย่างน้อย 64K tokens หากใช้ `deepseek-r1:7b-40k` จะถูกปฏิเสธทันที เพราะโมเดลถูกประกาศไว้เพียง 40,960 tokens แม้จะตั้งค่า Ollama สูงกว่านั้นก็ตาม

จึงเลือก `gemma3:4b` เป็นจุดสมดุลสำหรับการ์ด VRAM 8 GB ด้วยเหตุผลดังนี้:

1. โมเดลขนาด 4B ใช้พื้นที่น้ำหนักโมเดลน้อยกว่า 7B ทำให้เหลือ VRAM สำหรับ KV cache ซึ่งเป็นส่วนสำคัญของ Context Window ขนาด 65K
2. ตั้งค่า `context_length: 65536` และ `ollama_num_ctx: 65536` ให้สอดคล้องกับข้อกำหนดขั้นต่ำของ Hermes Agent
3. ลดโอกาส Out Of Memory เมื่อเทียบกับการใช้โมเดล 7B ที่ Context เท่ากัน โดยยังคงความเร็วตอบสนองและความเสถียรไว้ได้ดีกว่าใน VRAM 8 GB
4. เหมาะกับงานสนทนา ภาษาไทย และงานสรุป/วิเคราะห์ที่ต้องอ่านบริบทยาวบนเครื่องภายใน

ค่า 65K เป็นเพดานบริบทที่ตั้งค่าไว้ ไม่ได้หมายความว่าทุกคำขอจะใช้ VRAM เต็มจำนวนเท่ากัน การใช้จริงขึ้นอยู่กับความยาว prompt, จำนวน token ที่ตอบกลับ, quantization และ KV cache ของ Ollama จึงควรตรวจ `ollama ps` และ `nvidia-smi` ควบคู่กัน หากพบ OOM ให้ลด `ollama_num_ctx` เป็น 49152 หรือ 32768

ข้อจำกัดที่ต้องทราบ: `gemma3:4b` ใน Ollama ปัจจุบันไม่รองรับ Tools ผ่าน custom OpenAI-compatible endpoint จึงตั้ง `platform_toolsets.telegram: []` ไว้ เพื่อให้ Telegram ตอบข้อความได้เสถียร หากต้องการใช้ Tools ให้เลือกโมเดลที่รองรับ Tools และมี Context อย่างน้อย 64K

โมเดลเริ่มต้นมาจาก MODEL_NAME และ Web UI อ่านรายชื่อโมเดลที่ติดตั้งใน Ollama สร้างโมเดลจาก Modelfile ได้ด้วย:

    ollama create hermes-agent -f Modelfile

เพิ่ม provider ได้จาก Worker Compute โดยต้องใช้ HTTPS API key จะอยู่ในหน่วยความจำของ Web server ไม่ส่งกลับ browser และหายเมื่อ restart server

    VISION_API_KEY=เก็บคีย์ไว้บน-server
    HERMES_PROVIDERS_JSON=[{"id":"vision","name":"Vision Worker","type":"openai-compatible","base_url":"https://provider.example/v1","api_key_env":"VISION_API_KEY","models":["vision-model"],"capabilities":["vision"]}]

Google AI Studio ใช้ native generateContent API โดยเลือกประเภท provider เป็น Google ในหน้าเว็บ

## ตัวแปรตั้งค่าที่ใช้บ่อย

| ตัวแปร | ค่าเริ่มต้น | หน้าที่ |
| --- | --- | --- |
| OLLAMA_URL | http://localhost:11434/api/generate | URL Ollama |
| MODEL_NAME | gemma3:4b | โมเดลหลักของ Chat-BTH |
| WEB_HOST / WEB_PORT | 127.0.0.1 / 8080 | ที่อยู่ Web server |
| HERMES_DB_PATH | data/chat_bth.db | ตำแหน่ง SQLite |
| HERMES_WORKSPACE_ROOT | data/workspaces | ตำแหน่งไฟล์ Build |
| HERMES_WEB_TOKEN | ไม่ตั้งค่า | token ป้องกัน Web API |
| HERMES_RUN_COMMANDS | python,python3,node,npm,pytest | allowlist คำสั่ง Build |
| NUM_CTX / NUM_THREAD / NUM_GPU | 40960 / 4 / 20 | ปรับทรัพยากร Ollama ของ Web UI เดิม; Hermes Agent ใช้ `ollama_num_ctx=65536` ใน `~/.hermes/config.yaml` |
| TEMPERATURE | 0.7 | ความสุ่มของคำตอบ |
| MAX_OUTPUT_TOKENS | 512 | ความยาวคำตอบทั่วไป |
| HERMES_PIPER_MODEL / HERMES_PIPER_MODEL_TH | ไม่ตั้งค่า | ไฟล์โมเดล `.onnx` ของ Piper สำหรับสร้างเสียง local (`_TH` มีผลกับคำขอภาษาไทย) |
| HERMES_PIPER_COMMAND / HERMES_FFMPEG_COMMAND | Python ปัจจุบัน `-m piper` / `ffmpeg` | ระบุ path ของ Piper หรือ FFmpeg เมื่อไม่ได้อยู่ในตำแหน่งปกติ |
| SEARCH_MAX_RESULTS / SEARCH_TIMEOUT | 2 / 25 | จำนวนผลค้นหา/เวลารอ |
| SCRIPT_TIMEOUT / SCRIPT_OUTPUT_LIMIT | 60 / 6000 | จำกัด Telegram experiment |

## ข้อจำกัดและความปลอดภัย

- ไฟล์แนบรวมกับข้อความไม่เกิน 12,000 ตัวอักษร แนบได้ 5 ไฟล์ ไฟล์ละไม่เกิน 500 KB รองรับ txt, md, csv, json, py, js, ts, html, css, log
- Build จำกัดไฟล์ประมาณ 1 MB, จำนวน 500 ไฟล์ และเวลารันคำสั่ง 1–60 วินาที
- Build ใช้ allowlist และไม่ผ่าน shell แต่ไม่ใช่ sandbox ระดับ container ควรรันเฉพาะโค้ดที่เชื่อถือได้
- Telegram /run อนุญาตเฉพาะ .py ใต้ experiments/ และต้องกดอนุมัติ แต่ไม่ใช่ sandbox ระดับระบบปฏิบัติการ
- Notebook และประวัติ Build Assistant เก็บใน browser ไม่ซิงก์ข้ามเครื่อง/พอร์ต ควร export ข้อมูลสำคัญ
- Project, chat และข้อความอยู่ใน SQLite; ไฟล์ Build แยกตาม project id และการลบโปรเจกต์จะลบ workspace ด้วย
- Preview ต้องมี entry เป็น index.html, dist/index.html, build/index.html หรือ public/index.html และควรใช้ asset แบบ relative path
- เปิด LAN ให้ตั้ง WEB_HOST=0.0.0.0 และ HERMES_WEB_TOKEN เป็น token สุ่มยาว ใช้ HTTPS ผ่าน reverse proxy และ firewall ไม่ควรเปิดสู่ Internet โดยตรง

## ตรวจสอบและทดสอบ

    node --check web/app.js
    ./venv/bin/python -m unittest discover -s tests -v
    ./venv/bin/python -m tests.preview_fixture

ผลตรวจสอบล่าสุดบน Dell (10 ตุลาคม 2026): Python compile ผ่าน, automated tests 130 รายการ โดยผ่าน 128 รายการ และไม่ผ่าน 2 รายการเนื่องจากไม่มี Node.js สำหรับ `node --check` ส่วน Hermes Doctor รายงานว่า Gateway, Python environment, configuration และ Ollama connectivity ใช้งานได้

## โครงสร้างโปรเจกต์

    web_app.py             FastAPI backend, Web UI และ API
    web/                   HTML, CSS, JavaScript และ assets
    bot.py                 Telegram bot, Ollama, web search และ YouTube
    voice_agent.py         Voice agent แบบ local Whisper + Piper + pygame
    web_store.py           SQLite persistence
    bth_create/            Blueprint, component, theme, guided build, verification
    data/workspaces/       ไฟล์ Build แยกตาม project id
    data/chat_bth.db       SQLite database เริ่มต้น
    data/audio/            MP3 จาก endpoint เสียง
    experiments/           สคริปต์ที่ Telegram /run อนุญาต
    tests/                 regression tests และ UI fixture
    Modelfile              สูตรสร้างโมเดล hermes-agent

voice_agent.py เป็นโปรแกรมแยกจาก Web UI ต้องติดตั้ง dependency เพิ่ม เช่น SpeechRecognition, faster-whisper และ pygame รวมถึงมีไมโครโฟน/อุปกรณ์เสียง จึงไม่ได้อยู่ในขั้นตอนเริ่มต้นของ Web UI

เมื่อเปิด Voice Agent ให้กด `5` และ `6` พร้อมกันเพื่อเริ่มบันทึกหนึ่งประโยค (Push-to-Talk) ปรับปุ่มได้ผ่าน `HERMES_PUSH_TO_TALK_KEYS` เช่น `F8` หรือ `ctrl+space` โดยการดักปุ่มระดับระบบต้องทำงานบน desktop session ที่อนุญาตให้โปรแกรมรับ global keyboard events.
