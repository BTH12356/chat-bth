"""Run the real library experiment and retain it in the workspace database."""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from web_app import BuildAgentRequest, apply_build_agent
from web_store import create_project, create_conversation, add_message, get_project

async def main():
    project = get_project(sys.argv[1]) if len(sys.argv) > 1 else create_project("ห้องสมุด • DeepSeek R1 7B — การทดลองจริง")
    if not project:
        raise SystemExit("Project not found")
    conversation = create_conversation(project["id"], "ผลการทดลองสร้างเว็บไซต์ห้องสมุด", "deepseek-r1:7b")
    instruction = (
        "สร้างเว็บไซต์ห้องสมุดภาษาไทยชื่อ 'ห้องสมุดแสงอักษร' ให้ดูเป็นมืออาชีพ "
        "ใช้พื้นสีครีม สีเขียวเข้มและสีทอง typography ชัดเจน responsive "
        "มี header, hero, รายการหนังสือตัวอย่างอย่างน้อย 8 เล่ม แสดงชื่อ ผู้แต่ง หมวดหมู่ "
        "ค้นหาชื่อหรือผู้แต่งและกรองหมวดหมู่ได้จริง ปุ่มดูรายละเอียดเปิด dialog ปิดด้วย Escape ได้ "
        "มีรายการโปรดบันทึกใน localStorage ปุ่มสลับดูรายการโปรด และ empty state "
        "มีเวลาเปิดบริการและ footer ระบุชัดว่าเป็นเว็บไซต์สาธิต ไม่มีการยืมจริง "
        "สร้าง index.html styles.css app.js ไม่ใช้ CDN หรือรูปภายนอก ใช้ปกหนังสือจาก CSS "
        "โค้ดกระชับสมบูรณ์พร้อมใช้งาน ไม่สร้างระบบล็อกอิน ไม่ติดตั้ง dependency"
    )
    add_message(conversation["id"], "user", instruction, "deepseek-r1:7b", False)
    print(json.dumps({"project_id": project["id"], "name": project["name"]}, ensure_ascii=False), flush=True)
    result = await apply_build_agent(project["id"], BuildAgentRequest(instruction=instruction, model="deepseek-r1:7b", run_command=False))
    add_message(conversation["id"], "assistant", json.dumps(result, ensure_ascii=False, indent=2), "deepseek-r1:7b", False)
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)

if __name__ == "__main__":
    asyncio.run(main())
