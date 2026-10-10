"""Phase 2 deterministic Guided Conversation over the existing form schemas."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .form_engine import FormDefinition, FormStore, RuleEngine


GUIDED_CONVERSATION_SCHEMA = "hermes.guided-conversation/v1"


class ConversationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


class GuidedQuestion(ConversationModel):
    id: str
    field_id: str
    topic: str
    prompt: str
    reason: str
    kind: Literal["text", "select", "multi_select", "boolean"]
    options: list[str] = Field(default_factory=list)
    suggested: Any = None
    required: bool = False
    clarification: bool = False


class GuidedSummaryItem(ConversationModel):
    field_id: str
    label: str
    value: Any = None
    editable: bool = True


class GuidedConversation(ConversationModel):
    schema_name: Literal[GUIDED_CONVERSATION_SCHEMA] = Field(alias="schema")
    session_id: str = Field(min_length=8, max_length=120)
    form_id: str
    status: Literal["collecting", "review", "confirmed"] = "collecting"
    values: dict[str, Any] = Field(default_factory=dict)
    asked: list[str] = Field(default_factory=list)
    question: GuidedQuestion | None = None
    summary: list[GuidedSummaryItem] = Field(default_factory=list)
    clarification: str | None = None


class GuidedAnswer(ConversationModel):
    field_id: str
    value: Any = None


_TOPICS = {
    "project_name": ("ตัวตนของเว็บไซต์", "เพื่อกำหนดชื่อที่ใช้ในหน้าเว็บและไฟล์โปรเจกต์"),
    "project_type": ("รูปแบบโปรเจกต์", "เพื่อเลือกโครงสร้างหลักที่รองรับงานนี้"),
    "blueprint_id": ("เป้าหมายของเว็บไซต์", "เพื่อเลือก Blueprint และชุดความสามารถที่เหมาะสม"),
    "modules": ("ความสามารถหลัก", "เพื่อสร้างเฉพาะส่วนที่ผู้ใช้ต้องการและลดงานส่วนเกิน"),
    "tabs": ("โครงสร้างเนื้อหา", "เพื่อวางหน้า/หมวดหมู่ที่ผู้เข้าชมจะใช้งาน"),
    "page_types": ("โครงสร้างเนื้อหา", "เพื่อเลือก block ที่เหมาะกับแต่ละหน้า"),
    "color_tone": ("ภาพลักษณ์", "เพื่อกำหนดทิศทางสีเริ่มต้นของ Theme"),
    "network_scope": ("การเข้าถึง", "เพื่อกำหนดข้อกำหนดด้านความปลอดภัยและการเผยแพร่"),
    "auth_enabled": ("การเข้าถึง", "เพื่อป้องกันเว็บไซต์เมื่อมีการเปิดใช้งานบนเครือข่าย"),
    "https_required": ("ความปลอดภัย", "เพื่อยืนยันการใช้ HTTPS ก่อนเปิดให้เข้าถึงจากภายนอก"),
    "allowed_origins": ("ความปลอดภัย", "เพื่อจำกัดแหล่งที่มาที่อนุญาตให้เรียกใช้ระบบ"),
    "ai_assistant": ("ผู้ช่วย AI", "เพื่อกำหนดว่าเว็บไซต์ต้องมีความสามารถ AI หรือไม่"),
    "ai_capabilities": ("ผู้ช่วย AI", "เพื่อให้ Hermes รู้ขอบเขตความสามารถที่อนุญาต"),
    "ai_autonomy": ("ผู้ช่วย AI", "เพื่อกำหนดระดับการอนุมัติของ AI"),
    "theme": ("ภาพลักษณ์", "เพื่อเลือก Theme ที่ใช้เป็นฐาน"),
    "density": ("ประสบการณ์ใช้งาน", "เพื่อเลือกความหนาแน่นของ layout"),
    "language": ("ภาษา", "เพื่อเตรียมเนื้อหาและ metadata ให้เหมาะกับผู้ใช้"),
    "content_needed": ("เนื้อหาเว็บไซต์", "เพื่อให้ Hermes เตรียมข้อความจริงแทนข้อความตัวอย่างในเว็บไซต์"),
    "content_about": ("เนื้อหาเว็บไซต์", "เพื่อเขียนข้อความแนะนำองค์กรหรือธุรกิจให้ตรงกับความจริง"),
    "content_offer": ("เนื้อหาเว็บไซต์", "เพื่อเขียนข้อความเกี่ยวกับสินค้า บริการ หรือสิ่งที่อยากนำเสนอ"),
    "content_audience": ("เนื้อหาเว็บไซต์", "เพื่อปรับน้ำเสียงและสารให้เหมาะกับกลุ่มผู้เข้าชม"),
    "content_contact": ("เนื้อหาเว็บไซต์", "เพื่อใส่ข้อมูลช่องทางติดต่อในหน้าเว็บไซต์"),
}


class GuidedConversationEngine:
    """Ask one schema field at a time and never mutate files or call a model."""

    def __init__(self, forms: FormStore | None = None, rules: RuleEngine | None = None):
        self.forms = forms or FormStore()
        self.rules = rules or RuleEngine()

    def start(self, form_id: str, session_id: str, initial_values: dict[str, Any] | None = None) -> GuidedConversation:
        definition = self.forms.get(form_id)
        values = dict(initial_values or {})
        self.rules.evaluate(definition, values)
        state = GuidedConversation(schema=GUIDED_CONVERSATION_SCHEMA, session_id=session_id, form_id=form_id, values=values)
        return self._advance(definition, state)

    def answer(self, state: GuidedConversation, answer: GuidedAnswer) -> GuidedConversation:
        definition = self.forms.get(state.form_id)
        if state.status != "collecting" or state.question is None:
            raise ValueError("guided conversation is not waiting for an answer")
        if answer.field_id != state.question.field_id:
            raise ValueError(f"answer must target the current guided field: {state.question.field_id}")
        field = next((field for field in definition.fields if field.id == answer.field_id), None)
        if field is None:
            raise ValueError(f"unknown guided field: {answer.field_id}")
        value = self._normalize(field, answer.value)
        if value is _AMBIGUOUS:
            question = self._question(definition, field, state.values, clarification=True)
            return state.model_copy(update={"question": question, "clarification": f"ยังไม่ชัดเจนสำหรับ {field.label} กรุณาเลือกจากตัวเลือกที่กำหนด"})
        values = {**state.values, field.id: value}
        asked = list(dict.fromkeys([*state.asked, field.id]))
        updated = state.model_copy(update={"values": values, "asked": asked, "clarification": None})
        return self._advance(definition, updated)

    def edit(self, state: GuidedConversation, values: dict[str, Any]) -> GuidedConversation:
        definition = self.forms.get(state.form_id)
        self.rules.evaluate(definition, values)
        updated = state.model_copy(update={"values": dict(values), "status": "review", "question": None, "clarification": None})
        return self._summary(definition, updated)

    def revise(self, state: GuidedConversation, field_id: str) -> GuidedConversation:
        """Return one reviewed answer to the collecting state for correction."""
        definition = self.forms.get(state.form_id)
        view = self.rules.evaluate(definition, state.values)
        field = next((item for item in definition.fields if item.id == field_id and item.id in view.visible_fields), None)
        if field is None:
            raise ValueError(f"guided field is not editable: {field_id}")
        question = self._question(definition, field, state.values, clarification=True)
        asked = [item for item in state.asked if item != field_id]
        return state.model_copy(update={"status": "collecting", "asked": asked, "question": question, "clarification": f"กรุณาแก้ไข {field.label} แล้วตอบอีกครั้ง"})

    def answer_text(self, state: GuidedConversation, text: str) -> GuidedConversation:
        """Turn a natural chat reply into the typed value expected by the current question."""
        if state.question is None:
            raise ValueError("guided conversation is not waiting for an answer")
        definition = self.forms.get(state.form_id)
        field = next(item for item in definition.fields if item.id == state.question.field_id)
        value = self._value_from_text(field, state.question, text)
        return self.answer(state, GuidedAnswer(field_id=field.id, value=value))

    def confirm(self, state: GuidedConversation) -> GuidedConversation:
        definition = self.forms.get(state.form_id)
        view = self.rules.evaluate(definition, state.values)
        if state.status != "review" or state.question is not None:
            raise ValueError("guided conversation must reach review before confirmation")
        unanswered = [field for field in view.visible_fields if field not in state.asked]
        if unanswered:
            raise ValueError(f"guided fields are unanswered: {unanswered}")
        missing = [field for field in view.required_fields if view.values.get(field) in (None, "", [])]
        if missing:
            raise ValueError(f"required guided fields are missing: {missing}")
        problem = self._validation_problem(definition, state.values)
        if problem:
            raise ValueError(problem[1])
        return state.model_copy(update={"status": "confirmed", "question": None, "summary": self._summary_items(definition, view.values)})

    def _advance(self, definition: FormDefinition, state: GuidedConversation) -> GuidedConversation:
        view = self.rules.evaluate(definition, state.values)
        if definition.id == "website_standard.v1" and "page_types" not in state.asked:
            state = state.model_copy(update={
                "values": {**state.values, "page_types": []},
                "asked": [*state.asked, "page_types"],
            })
            view = self.rules.evaluate(definition, state.values)
        for field in definition.fields:
            if field.id not in view.visible_fields or field.id in state.asked:
                continue
            question = self._question(definition, field, view.values)
            return state.model_copy(update={"question": question, "status": "collecting"})
        problem = self._validation_problem(definition, state.values)
        if problem:
            field_id, message = problem
            field = next(field for field in definition.fields if field.id == field_id)
            question = self._question(definition, field, state.values, clarification=True)
            asked = [item for item in state.asked if item != field_id]
            return state.model_copy(update={"question": question, "asked": asked, "status": "collecting", "clarification": message})
        return self._summary(definition, state.model_copy(update={"status": "review", "question": None}))

    @staticmethod
    def _validation_problem(definition: FormDefinition, values: dict[str, Any]) -> tuple[str, str] | None:
        """Validate relationships that a single field cannot express alone."""
        if definition.id != "website_standard.v1":
            return None
        tabs = values.get("tabs", [])
        page_types = values.get("page_types", [])
        language = values.get("language", [])
        if not isinstance(tabs, list) or not tabs:
            return "tabs", "ต้องระบุอย่างน้อย 1 หน้า/หมวดหมู่"
        if len(tabs) > 12:
            return "tabs", "ระบุหน้า/หมวดหมู่ได้ไม่เกิน 12 รายการ"
        if len({item.casefold() for item in tabs if isinstance(item, str)}) != len(tabs):
            return "tabs", "ชื่อหน้า/หมวดหมู่ต้องไม่ซ้ำกัน"
        if page_types and len(page_types) != len(tabs):
            return "page_types", "หากเลือกประเภทหน้า ต้องเลือกให้ครบและมีจำนวนเท่ากับหน้า/หมวดหมู่"
        if not isinstance(language, list) or not language:
            return "language", "กรุณาเลือกภาษาที่รองรับอย่างน้อย 1 ภาษา"
        if values.get("network_scope") in {"internet", "both"} and values.get("auth_enabled") is not True:
            return "auth_enabled", "เว็บไซต์ที่เข้าถึงจากอินเทอร์เน็ตต้องเปิด Authentication"
        return None

    def _summary(self, definition: FormDefinition, state: GuidedConversation) -> GuidedConversation:
        return state.model_copy(update={"summary": self._summary_items(definition, state.values)})

    @staticmethod
    def _summary_items(definition: FormDefinition, values: dict[str, Any]) -> list[GuidedSummaryItem]:
        return [GuidedSummaryItem(field_id=field.id, label=field.label, value=values.get(field.id)) for field in definition.fields if values.get(field.id) not in (None, "", [])]

    def _question(self, definition: FormDefinition, field, values: dict[str, Any], clarification: bool = False) -> GuidedQuestion:
        topic, reason = _TOPICS.get(field.id, ("รายละเอียดโปรเจกต์", "เพื่อให้ข้อมูลใน Project Schema ครบถ้วน"))
        label = self._thai_label(field.label)
        prompt = self._thai_prompt(field.id, label)
        if field.default not in (None, "", []):
            prompt = f"{prompt} หากยังไม่แน่ใจ พิมพ์ “ตามที่แนะนำ” เพื่อใช้ค่า {self._display(field.default)} ได้ครับ"
        if clarification:
            prompt = f"กรุณาเลือกหรือระบุ {label} ให้ชัดเจนครับ"
        kind = "boolean" if field.kind == "checkbox" else ("select" if field.kind == "radio" else field.kind)
        current = values.get(field.id)
        suggested = field.default if current in (None, "", []) else current
        return GuidedQuestion(id=f"ask-{field.id}", field_id=field.id, topic=topic, prompt=prompt, reason=reason, kind=kind, options=list(field.options), suggested=suggested, required=field.id in self.rules.evaluate(definition, values).required_fields, clarification=clarification)

    @staticmethod
    def _thai_label(label: str) -> str:
        return {
            "Project name": "ชื่อเว็บไซต์", "Website Blueprint": "เป้าหมายของเว็บไซต์", "Navigation tabs": "หน้า/หมวดหมู่ที่ต้องการ",
            "Page types": "รูปแบบของแต่ละหน้า", "Color tone": "โทนสี", "Network scope": "ขอบเขตการเข้าถึง",
            "Authentication": "การเข้าสู่ระบบ", "Density": "ความหนาแน่นของหน้าเว็บ", "Language": "ภาษา", "Features": "ความสามารถที่ต้องการ",
            "Add website content": "การใส่เนื้อหาเว็บไซต์", "Business or organization overview": "ข้อมูลธุรกิจหรือองค์กร",
            "Key products or services": "สินค้า/บริการหลัก", "Target audience": "กลุ่มเป้าหมาย", "Contact details": "ข้อมูลติดต่อ",
        }.get(label, label)

    @staticmethod
    def _thai_prompt(field_id: str, label: str) -> str:
        prompts = {
            "project_name": "อยากตั้งชื่อเว็บไซต์ว่าอะไรครับ?",
            "blueprint_id": "เว็บไซต์นี้ทำขึ้นเพื่ออะไรครับ? เช่น แนะนำบริษัท ขายสินค้า โชว์ผลงาน หรือเผยแพร่บทความ",
            "tabs": "อยากให้เว็บไซต์มีหน้า/เมนูอะไรบ้างครับ?",
            "color_tone": "อยากได้อารมณ์หรือโทนสีแบบไหนครับ? เช่น น่าเชื่อถือ อบอุ่น ธรรมชาติ หรือทันสมัย",
            "network_scope": "เว็บไซต์นี้ใช้ภายในองค์กร หรือให้คนทั่วไปเข้าถึงผ่านอินเทอร์เน็ตครับ?",
            "auth_enabled": "ต้องการให้ผู้ใช้เข้าสู่ระบบก่อนใช้งานหรือไม่ครับ?",
            "density": "ต้องการหน้าตาแบบกะทัดรัด หรือโปร่งอ่านง่ายครับ?",
            "language": "ต้องการให้เว็บไซต์รองรับภาษาไทย ภาษาอังกฤษ หรือทั้งสองภาษาครับ?",
            "content_needed": "ต้องการให้ Hermes ช่วยเขียนข้อความจริงลงในเว็บไซต์แทนข้อความตัวอย่างหรือไม่ครับ?",
            "content_about": "ช่วยเล่าภาพรวมของธุรกิจหรือองค์กรแบบสั้น ๆ ได้ไหมครับ? Hermes จะเรียบเรียงเป็นข้อความแนะนำให้",
            "content_offer": "มีสินค้า บริการ หรือจุดเด่นอะไรที่อยากให้หน้าเว็บสื่อสารบ้างครับ?",
            "content_audience": "เว็บไซต์นี้ต้องการสื่อสารกับใครเป็นหลักครับ? หากไม่มี พิมพ์ “ไม่มี” ได้",
            "content_contact": "ต้องการใส่ช่องทางติดต่ออะไรบ้างครับ? เช่น โทรศัพท์ อีเมล หรือที่อยู่ หากยังไม่มี พิมพ์ “ไม่มี” ได้",
        }
        return prompts.get(field_id, f"{label}คืออะไรครับ?")

    @staticmethod
    def _display(value: Any) -> str:
        return ", ".join(map(str, value)) if isinstance(value, list) else str(value)

    @staticmethod
    def _normalize(field, value: Any) -> Any:
        if field.kind == "checkbox":
            return value if isinstance(value, bool) else _AMBIGUOUS
        if field.kind in ("select", "radio"):
            return value if value in field.options else _AMBIGUOUS
        if field.kind == "multi_select":
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                return _AMBIGUOUS
            normalized = [item.strip() for item in value if item.strip()]
            if len(normalized) != len(value) or len(normalized) != len(set(normalized)):
                return _AMBIGUOUS
            if field.options and not all(item in field.options for item in normalized):
                return _AMBIGUOUS
            if field.required and not normalized:
                return _AMBIGUOUS
            if field.id == "tabs" and (not normalized or len(normalized) > 12):
                return _AMBIGUOUS
            return normalized
        if field.kind == "text":
            return value.strip() if isinstance(value, str) and value.strip() else _AMBIGUOUS
        return _AMBIGUOUS

    @staticmethod
    def _value_from_text(field, question: GuidedQuestion, text: str) -> Any:
        value = text.strip()
        lowered = value.casefold()
        if field.kind == "text":
            return value
        if lowered in {"ตามที่แนะนำ", "แนะนำเลย", "เหมาะสม", "ค่าเริ่มต้น", "default"}:
            return question.suggested
        if field.kind == "checkbox":
            if lowered in {"ใช่", "yes", "y", "true", "เปิด", "เปิดใช้", "ต้องการ", "เอา", "ครับ", "ค่ะ"}:
                return True
            if lowered in {"ไม่", "ไม่ใช่", "no", "n", "false", "ปิด", "ไม่ต้องการ", "ไม่เอา"}:
                return False
            return _AMBIGUOUS
        if field.kind in {"select", "radio"}:
            inferred = GuidedConversationEngine._infer_thai_option(field.id, lowered)
            if inferred is not None:
                return inferred
            return GuidedConversationEngine._match_option(value, field.options)
        if field.kind == "multi_select":
            if lowered in {"ใช้ค่าเดิม", "ค่าเดิม", "default"} and isinstance(question.suggested, list):
                return question.suggested
            if lowered in {"ไม่เลือก", "ไม่มี", "none", "ไม่ต้องการ"}:
                return []
            parts = [part.strip() for part in re.split(r"[,;\n]+", value) if part.strip()]
            if not field.options:
                return parts
            inferred = GuidedConversationEngine._infer_thai_multi_option(field.id, lowered)
            if inferred is not None:
                return inferred
            if lowered in {"ทั้งหมด", "all"}:
                return list(field.options)
            selected = []
            for part in parts:
                option = GuidedConversationEngine._match_option(part, field.options)
                if option is _AMBIGUOUS:
                    return _AMBIGUOUS
                selected.append(option)
            return selected
        return _AMBIGUOUS

    @staticmethod
    def _match_option(value: str, options: list[str]) -> str | object:
        candidate = value.strip().casefold()
        aliases = {"ไทย": "th", "ภาษาไทย": "th", "english": "en", "อังกฤษ": "en", "ภาษาอังกฤษ": "en"}
        candidate = aliases.get(candidate, candidate)
        exact = [option for option in options if option.casefold() == candidate]
        if len(exact) == 1:
            return exact[0]
        partial = [option for option in options if candidate and (option.casefold().endswith(candidate) or candidate in option.casefold())]
        return partial[0] if len(partial) == 1 else _AMBIGUOUS

    @staticmethod
    def _infer_thai_option(field_id: str, text: str) -> str | None:
        if field_id == "blueprint_id":
            mappings = (
                (("ขาย", "ร้าน", "สินค้า", "e-commerce", "อีคอมเมิร์ซ"), "website.retail.v1"),
                (("ผลงาน", "พอร์ต", "portfolio"), "website.portfolio.v1"),
                (("บริษัท", "องค์กร", "ธุรกิจ", "แนะนำเรา"), "website.company.v1"),
                (("บริการ", "service"), "website.services.v1"),
                (("บทความ", "ข่าว", "บล็อก", "content"), "website.content.v1"),
                (("ห้องสมุด", "library", "หนังสือ"), "catalog.library.v1"),
                (("เอกสาร", "document"), "catalog.documents.v1"),
                (("ความรู้", "คู่มือ", "knowledge"), "website.knowledge.v1"),
                (("เรียน", "คอร์ส", "อบรม", "learning"), "catalog.learning.v1"),
                (("สื่อ", "วิดีโอ", "media"), "catalog.media.v1"),
            )
            for keywords, option in mappings:
                if any(keyword in text for keyword in keywords):
                    return option
        if field_id == "color_tone":
            mappings = (( ("อบอุ่น", "ส้ม"), "orange"), (("ธรรมชาติ", "เขียว"), "green"), (("หรู", "ม่วง"), "purple"), (("เรียบ", "กลาง", "neutral"), "neutral"), (("น่าเชื่อถือ", "น้ำเงิน", "ฟ้า"), "blue"))
            for keywords, option in mappings:
                if any(keyword in text for keyword in keywords):
                    return option
        if field_id == "network_scope":
            if any(word in text for word in ("ภายใน", "องค์กร", "local")):
                return "local"
            if any(word in text for word in ("ทั้ง", "สองแบบ", "both")):
                return "both"
            if any(word in text for word in ("ทั่วไป", "สาธารณะ", "อินเทอร์เน็ต", "ออนไลน์", "internet")):
                return "internet"
        if field_id == "density":
            if any(word in text for word in ("กะทัดรัด", "แน่น", "compact")):
                return "compact"
            if any(word in text for word in ("โปร่ง", "อ่านง่าย", "comfortable")):
                return "comfortable"
        return None

    @staticmethod
    def _infer_thai_multi_option(field_id: str, text: str) -> list[str] | None:
        if field_id == "language":
            thai = any(word in text for word in ("ไทย", "th"))
            english = any(word in text for word in ("อังกฤษ", "english", "en"))
            if thai or english:
                return (["th"] if thai else []) + (["en"] if english else [])
        return None


_AMBIGUOUS = object()
