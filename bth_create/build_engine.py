"""Frozen-spec-only Build Engine for BTH Create v0.1."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from .blueprint import BlueprintStore
from .component import ComponentRegistry
from .gap_analysis import GapAnalysisReport, GapItem
from .page_recipe import PageRecipeStore
from .project_spec import project_spec_hash
from .spec_lifecycle import FrozenProjectSpec
from .source_model import stable_node_id
from .task_dag import TaskDAG
from .theme import ThemeStore


class BuildModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class BuildTaskResult(BuildModel):
    task_id: str
    status: Literal["passed", "blocked"]
    details: list[str] = Field(default_factory=list)


class BuildFailure(BuildModel):
    status: Literal["blocked"] = "blocked"
    task: str
    reason: str
    attempted: list[str] = Field(default_factory=list)
    needs_human: bool
    suggested_actions: list[str] = Field(default_factory=list)


class BuildBlocked(RuntimeError):
    def __init__(self, failure: BuildFailure):
        super().__init__(failure.reason)
        self.failure = failure


class BuildResult(BuildModel):
    status: Literal["built"] = "built"
    frozen_spec_id: str
    spec_hash: str
    workspace: str
    artifacts: list[str]
    generated_components: list[str]
    task_results: list[BuildTaskResult]


class MissingPartGenerator(Protocol):
    """Scoped extension point. It receives one MISSING item, never the conversation."""

    def generate(self, item: GapItem, workspace: Path) -> list[Path]: ...


class BuildEngine:
    def __init__(
        self,
        blueprints: BlueprintStore | None = None,
        themes: ThemeStore | None = None,
        components: ComponentRegistry | None = None,
        page_recipes: PageRecipeStore | None = None,
        template_root: Path | None = None,
    ):
        self.blueprints = blueprints or BlueprintStore()
        self.themes = themes or ThemeStore()
        self.components = components or ComponentRegistry()
        self.page_recipes = page_recipes or PageRecipeStore()
        self.template_root = template_root or Path(__file__).parent / "templates"

    def build(
        self,
        frozen: FrozenProjectSpec,
        report: GapAnalysisReport,
        dag: TaskDAG,
        workspace_root: Path,
        missing_generator: MissingPartGenerator | None = None,
        resume: bool = False,
    ) -> BuildResult:
        self._validate_inputs(frozen, report, dag)
        workspace = workspace_root / frozen.frozen_id
        if workspace.exists() and not resume:
            raise FileExistsError(f"build workspace already exists: {workspace}")
        workspace.mkdir(parents=True, exist_ok=resume)

        blueprint = self.blueprints.get(frozen.project_spec.blueprint.id)
        theme = self.themes.get(frozen.project_spec.theme.id)
        task_results: list[BuildTaskResult] = []
        generated: list[str] = []
        artifacts: list[Path] = []

        for task_id in dag.topological_order():
            if task_id == "validate_spec":
                task_results.append(BuildTaskResult(task_id=task_id, status="passed", details=["Frozen Project Spec hash matched."]))
            elif task_id == "load_blueprint":
                task_results.append(BuildTaskResult(task_id=task_id, status="passed", details=[f"Loaded {blueprint.id}@{blueprint.version}."]))
            elif task_id == "resolve_components":
                for component_id, version in frozen.component_versions.items():
                    if self.components.get(component_id).version != version:
                        self._block(task_id, f"Frozen component version is unavailable: {component_id}@{version}", ["load component metadata"])
                task_results.append(BuildTaskResult(task_id=task_id, status="passed", details=["Frozen component versions resolved."]))
            elif task_id == "configure_components":
                config_path = workspace / "project-config.json"
                config_path.write_text(self._project_config(frozen), encoding="utf-8")
                artifacts.append(config_path)
                task_results.append(BuildTaskResult(task_id=task_id, status="passed", details=[config_path.name]))
            elif task_id == "compose_layout":
                composed = self._compose_workspace(frozen, blueprint.default_component_mapping, theme, workspace)
                artifacts.extend(composed)
                task_results.append(BuildTaskResult(task_id=task_id, status="passed", details=[path.name for path in composed]))
            elif task_id.startswith("generate_missing_"):
                index = int(task_id.rsplit("_", 1)[1]) - 1
                item = report.missing[index]
                if missing_generator is None:
                    self._block(
                        task_id,
                        f"Missing requirement has no scoped generator: {item.requirement_id}",
                        ["classify requirement", "look up component registry"],
                    )
                generated_paths = missing_generator.generate(item, workspace)
                for path in generated_paths:
                    resolved = path.resolve()
                    if workspace.resolve() not in resolved.parents or not path.is_file():
                        self._block(task_id, "Generator returned an invalid or out-of-workspace artifact.", ["validate generated artifact paths"])
                artifacts.extend(generated_paths)
                generated.append(item.component_id or item.requirement_id)
                task_results.append(BuildTaskResult(task_id=task_id, status="passed", details=[path.name for path in generated_paths]))
            elif task_id == "run_tests":
                required = {"index.html", "styles.css", "app.js", "project-config.json"}
                missing_files = required - {path.name for path in artifacts}
                if missing_files:
                    self._block(task_id, f"Required build files are missing: {sorted(missing_files)}", ["basic artifact check"])
                task_results.append(BuildTaskResult(task_id=task_id, status="passed", details=["Basic artifact checks passed; full tests are Phase 10."]))
            elif task_id == "integration_test":
                task_results.append(BuildTaskResult(task_id=task_id, status="passed", details=["Build inputs are internally consistent; full integration verification is Phase 10."]))
            elif task_id == "build_product":
                task_results.append(BuildTaskResult(task_id=task_id, status="passed", details=["Static application workspace assembled."]))
            else:
                self._block(task_id, f"Unsupported task type in Build Engine: {task_id}", ["dispatch task"])

        relative_artifacts = sorted(str(path.relative_to(workspace)) for path in artifacts)
        return BuildResult(
            frozen_spec_id=frozen.frozen_id,
            spec_hash=frozen.spec_hash,
            workspace=str(workspace),
            artifacts=relative_artifacts,
            generated_components=generated,
            task_results=task_results,
        )

    def _validate_inputs(self, frozen: FrozenProjectSpec, report: GapAnalysisReport, dag: TaskDAG) -> None:
        if project_spec_hash(frozen.project_spec) != frozen.spec_hash:
            raise ValueError("frozen Project Spec hash mismatch")
        if report.frozen_spec_id != frozen.frozen_id or dag.frozen_spec_id != frozen.frozen_id:
            raise ValueError("build inputs reference different frozen specs")
        if report.spec_hash != frozen.spec_hash or dag.spec_hash != frozen.spec_hash:
            raise ValueError("build inputs have inconsistent spec hashes")

    def _project_config(self, frozen: FrozenProjectSpec) -> str:
        payload = {
            "frozen_spec_id": frozen.frozen_id,
            "spec_hash": frozen.spec_hash,
            "project": frozen.project_spec.model_dump(mode="json", by_alias=True),
            "versions": {
                "blueprint": frozen.blueprint_version,
                "theme": frozen.theme_version,
                "components": frozen.component_versions,
                "page_recipes": frozen.page_recipe_versions,
            },
        }
        return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

    def _compose_workspace(self, frozen: FrozenProjectSpec, mapping: dict, theme, workspace: Path) -> list[Path]:
        if frozen.project_spec.blueprint.id.startswith("catalog."):
            return self._compose_catalog(frozen, theme, workspace)
        if frozen.project_spec.project.type == "website":
            return self._compose_website(frozen, theme, workspace)
        project_name = html.escape(frozen.project_spec.project.name)
        project_node_key = frozen.project_spec.project.name.casefold().strip()
        module_cards = []
        for module in frozen.project_spec.modules:
            component_id = mapping[module].id
            title = html.escape(module.replace("_", " ").title())
            module_cards.append(f'<section class="module-card" data-node-id="{html.escape(stable_node_id(project_node_key, "dashboard", f"module/{module}"), quote=True)}" data-module="{html.escape(module)}" data-component="{html.escape(component_id)}"><h2>{title}</h2><p>Status: Ready</p></section>')
        templates = self.template_root / "internal_dashboard"
        index_template = (templates / "index.html.tpl").read_text(encoding="utf-8")
        css_template = (templates / "styles.css.tpl").read_text(encoding="utf-8")
        app_source = (templates / "app.js").read_text(encoding="utf-8")
        index_source = index_template.replace("{{PROJECT_NAME}}", project_name).replace("{{MODULE_CARDS}}", "\n".join(module_cards))
        colors = theme.colors
        typography = theme.typography
        css_source = (
            css_template.replace("{{FONT_FAMILY}}", typography["font_family"])
            .replace("{{FONT_SIZE}}", typography["font_size"])
            .replace("{{DESKTOP_COLOR}}", colors["desktop"])
            .replace("{{SURFACE_COLOR}}", colors["surface"])
            .replace("{{TEXT_COLOR}}", colors["text"])
            .replace("{{ACCENT_COLOR}}", colors["accent"])
            .replace("{{ACCENT_DARK}}", colors["accent_dark"])
        )
        paths = [workspace / "index.html", workspace / "styles.css", workspace / "app.js"]
        paths[0].write_text(index_source, encoding="utf-8")
        paths[1].write_text(css_source, encoding="utf-8")
        paths[2].write_text(app_source, encoding="utf-8")
        return paths

    def _compose_website(self, frozen: FrozenProjectSpec, theme, workspace: Path) -> list[Path]:
        templates = self.template_root / "website_standard"
        project_name = html.escape(frozen.project_spec.project.name)
        pages = frozen.project_spec.navigation.tabs
        filenames = ["index.html" if index == 0 else f"{page.slug or page.id}.html" for index, page in enumerate(pages)]
        template = (templates / "index.html.tpl").read_text(encoding="utf-8")
        project_node_key = frozen.project_spec.project.name.casefold().strip()
        page_paths: list[Path] = []
        for page_index, (page, filename) in enumerate(zip(pages, filenames)):
            recipe = self.page_recipes.get(page.page_type)
            nav_items = "\n".join(
                f'<a class="nav-tab{" active" if nav_index == page_index else ""}" href="{html.escape(target)}"'
                f'{" aria-current=\"page\"" if nav_index == page_index else ""}>{html.escape(nav_page.name)}</a>'
                for nav_index, (nav_page, target) in enumerate(zip(pages, filenames))
            )
            blocks = "\n".join(
                self._add_node_id(
                    self._render_page_block(block, page.name, frozen.project_spec.project.name, page_index),
                    stable_node_id(project_node_key, page.id, f"section/{block}/{block_index}"),
                )
                for block_index, block in enumerate(recipe.blocks, start=1)
            )
            source = (
                template.replace("{{PROJECT_NAME}}", project_name)
                .replace("{{PAGE_TITLE}}", html.escape(page.name))
                .replace("{{PAGE_TYPE}}", html.escape(page.page_type))
                .replace("{{PAGE_ID}}", html.escape(page.id))
                .replace("{{RECIPE_LABEL}}", html.escape(recipe.label))
                .replace("{{ROOT_NODE_ID}}", stable_node_id(project_node_key, page.id, "page/root"))
                .replace("{{NAV_TABS}}", nav_items)
                .replace("{{PAGE_BLOCKS}}", blocks)
            )
            path = workspace / filename
            path.write_text(source, encoding="utf-8")
            page_paths.append(path)
        palettes = {
            "blue": ("#2563eb", "#1d4ed8", "#eff6ff"),
            "green": ("#059669", "#047857", "#ecfdf5"),
            "purple": ("#7c3aed", "#6d28d9", "#f5f3ff"),
            "orange": ("#ea580c", "#c2410c", "#fff7ed"),
            "neutral": ("#334155", "#1e293b", "#f1f5f9"),
        }
        accent, accent_dark, accent_soft = palettes[frozen.project_spec.appearance.color_tone]
        css_source = (
            (templates / "styles.css.tpl").read_text(encoding="utf-8")
            .replace("{{FONT_FAMILY}}", theme.typography["font_family"])
            .replace("{{TEXT_COLOR}}", theme.colors["text"])
            .replace("{{MUTED_COLOR}}", theme.colors["muted_text"])
            .replace("{{ACCENT_COLOR}}", accent)
            .replace("{{ACCENT_DARK}}", accent_dark)
            .replace("{{ACCENT_SOFT}}", accent_soft)
        )
        app_source = (templates / "app.js").read_text(encoding="utf-8")
        asset_paths = [workspace / "styles.css", workspace / "app.js"]
        asset_paths[0].write_text(css_source, encoding="utf-8")
        asset_paths[1].write_text(app_source, encoding="utf-8")
        return page_paths + asset_paths

    @staticmethod
    def _add_node_id(source: str, node_id: str) -> str:
        """Attach the stable id to the first element of a rendered block."""
        opening_end = source.find(">")
        if opening_end < 0:
            raise ValueError("rendered block has no opening element")
        opening = source[:opening_end]
        if "data-node-id=" in opening:
            return source
        return f'{opening} data-node-id="{html.escape(node_id, quote=True)}">{source[opening_end + 1:]}'

    def _render_page_block(self, block: str, page_name: str, project_name: str, page_index: int) -> str:
        title = html.escape(page_name)
        project = html.escape(project_name)
        cards = lambda labels, kind="content-card": "".join(
            f'<article class="{kind}" data-search-item><span class="card-index">{index:02d}</span><h3>{html.escape(label)}</h3>'
            f'<p>ข้อมูลตัวอย่างสำหรับ {html.escape(label)} สามารถแก้ไขและเพิ่มรายละเอียดได้</p><a href="#">ดูรายละเอียด →</a></article>'
            for index, label in enumerate(labels, start=1)
        )
        if block == "hero":
            return f'<section class="hero-block"><div><p class="eyebrow">WELCOME TO {project}</p><h1>{title}</h1><p>พื้นที่ดิจิทัลที่รวบรวมข้อมูล บริการ และเรื่องสำคัญขององค์กรไว้ในที่เดียว</p><a class="primary-link" href="#featured">สำรวจเว็บไซต์</a></div><div class="hero-visual" data-image-slot><span>เลือกภาพหลัก</span><input class="page-image-input" type="file" accept="image/*" aria-label="เลือกภาพหลัก"></div></section>'
        if block == "page_header_image":
            return f'<section class="page-header image-header"><div><p class="eyebrow">{project}</p><h1>{title}</h1><p>ข้อมูลอย่างเป็นทางการที่จัดหมวดหมู่เพื่อค้นหาและใช้งานได้สะดวก</p></div><div class="header-image" data-image-slot><span>เพิ่มภาพที่เกี่ยวข้อง</span><input class="page-image-input" type="file" accept="image/*" aria-label="เพิ่มภาพประกอบ"></div></section>'
        if block == "page_header":
            return f'<section class="page-header"><div><p class="eyebrow">{project}</p><h1>{title}</h1><p>ค้นหาและเข้าถึงข้อมูลในหัวข้อนี้ได้อย่างรวดเร็ว</p></div></section>'
        if block in {"highlights", "featured_links", "company_stats", "policy_principles", "contact_cards"}:
            labels = {
                "highlights": ["ข้อมูลสำคัญ", "บริการยอดนิยม", "ข่าวล่าสุด"],
                "featured_links": ["เกี่ยวกับองค์กร", "เอกสารและนโยบาย", "ช่องทางติดต่อ"],
                "company_stats": ["ประสบการณ์", "โครงการสำเร็จ", "ทีมงานมืออาชีพ"],
                "policy_principles": ["โปร่งใส", "รับผิดชอบ", "ตรวจสอบได้"],
                "contact_cards": ["โทรศัพท์", "อีเมล", "เวลาทำการ"],
            }[block]
            return f'<section id="featured" class="content-block"><div class="block-heading"><p class="eyebrow">HIGHLIGHTS</p><h2>{title}</h2></div><div class="card-grid">{cards(labels)}</div></section>'
        if block in {"company_story", "policy_article", "rich_text"}:
            headings = {"company_story": "เรื่องราวของเรา", "policy_article": "แนวทางและนโยบาย", "rich_text": title}
            return f'<section class="content-block article-layout"><div><p class="eyebrow">OVERVIEW</p><h2>{html.escape(headings[block])}</h2></div><div class="article-copy"><p>{project} ให้ความสำคัญกับการสื่อสารข้อมูลที่ชัดเจน ถูกต้อง และเข้าถึงง่าย เนื้อหาส่วนนี้พร้อมสำหรับใส่รายละเอียดจริงขององค์กร</p><p>สามารถเพิ่มหัวข้อย่อย รูปภาพ เอกสารอ้างอิง และวันที่ปรับปรุงล่าสุดได้ตามความเหมาะสม</p></div></section>'
        if block in {"team_preview", "image_gallery"}:
            return f'<section class="content-block"><div class="block-heading"><p class="eyebrow">GALLERY</p><h2>ภาพประกอบ {title}</h2></div><div class="image-grid">' + "".join(f'<label class="image-slot" data-image-slot><span>ภาพ {index}</span><input class="page-image-input" type="file" accept="image/*" aria-label="เลือกภาพ {index}"></label>' for index in range(1, 4)) + '</div></section>'
        if block in {"document_search", "library_toolbar", "catalog_filters"}:
            return f'<section class="filter-toolbar"><label><span>ค้นหา</span><input type="search" data-page-search placeholder="ค้นหาใน {title}…"></label><label><span>เรียงลำดับ</span><select data-page-sort><option value="az">ก–ฮ / A–Z</option><option value="za">ฮ–ก / Z–A</option></select></label></section>'
        if block == "document_categories":
            return '<section class="category-chips" aria-label="หมวดเอกสาร"><button class="active">ทั้งหมด</button><button>นโยบาย</button><button>กฎระเบียบ</button><button>แบบฟอร์ม</button></section>'
        if block in {"document_list", "knowledge_shelf", "product_grid", "service_grid", "article_grid"}:
            labels = {
                "document_list": ["ระเบียบการปฏิบัติงาน", "คู่มือพนักงาน", "แบบฟอร์มมาตรฐาน", "ประกาศฉบับล่าสุด"],
                "knowledge_shelf": ["คู่มือเริ่มต้น", "องค์ความรู้ขององค์กร", "หนังสือแนะนำ", "กรณีศึกษา"],
                "product_grid": ["ผลิตภัณฑ์ยอดนิยม", "ชุดแนะนำ", "สินค้าใหม่", "โซลูชันสำหรับธุรกิจ"],
                "service_grid": ["บริการหลัก", "บริการสำหรับองค์กร", "แพ็กเกจเริ่มต้น", "บริการเฉพาะทาง"],
                "article_grid": ["ข่าวองค์กร", "กิจกรรมล่าสุด", "บทความแนะนำ", "ประกาศสำคัญ"],
            }[block]
            kind = "resource-card" if block in {"document_list", "knowledge_shelf"} else "content-card"
            upload = '<label class="resource-upload">+ เพิ่ม PDF<input type="file" accept="application/pdf,.pdf" data-resource-file></label>' if kind == "resource-card" else ""
            return f'<section class="content-block searchable-list"><div class="block-heading"><p class="eyebrow">COLLECTION</p><h2>{title}</h2>{upload}</div><div class="card-grid" data-search-grid>{cards(labels, kind)}</div></section>'
        if block in {"featured_article", "featured_resource", "testimonial", "download_panel", "newsletter", "map_panel"}:
            heading = {"featured_article": "เรื่องเด่น", "featured_resource": "รายการแนะนำ", "testimonial": "เสียงจากผู้ใช้บริการ", "download_panel": "เอกสารอ้างอิง", "newsletter": "ติดตามข่าวสาร", "map_panel": "แผนที่และสถานที่ตั้ง"}[block]
            return f'<section class="feature-panel"><p class="eyebrow">FEATURED</p><h2>{heading}</h2><p>พื้นที่พร้อมสำหรับข้อมูล รูปภาพ หรือลิงก์ที่เกี่ยวข้องกับ {title}</p><a class="secondary-link" href="#">ดูข้อมูลเพิ่มเติม</a></section>'
        if block == "work_process":
            return f'<section class="content-block"><div class="block-heading"><p class="eyebrow">PROCESS</p><h2>ขั้นตอนการทำงาน</h2></div><ol class="process-list"><li><strong>01</strong>รับข้อมูลและวิเคราะห์ความต้องการ</li><li><strong>02</strong>วางแผนและดำเนินงาน</li><li><strong>03</strong>ตรวจสอบและส่งมอบ</li></ol></section>'
        if block == "contact_form":
            return '<section class="content-block contact-layout"><div><p class="eyebrow">CONTACT</p><h2>ส่งข้อความถึงเรา</h2><p>กรอกข้อมูลเพื่อให้ทีมงานติดต่อกลับ</p></div><form class="contact-form"><label>ชื่อ<input required></label><label>อีเมล<input type="email" required></label><label>ข้อความ<textarea rows="5" required></textarea></label><button type="submit">ส่งข้อความ</button></form></section>'
        if block == "call_to_action":
            return f'<section class="cta-block"><div><p class="eyebrow">NEXT STEP</p><h2>พร้อมเริ่มต้นกับ {project}</h2></div><a class="primary-link" href="#">ติดต่อเรา</a></section>'
        return f'<section class="content-block"><h2>{title}</h2><p>ส่วนเนื้อหา {html.escape(block.replace("_", " "))}</p></section>'

    def _compose_catalog(self, frozen: FrozenProjectSpec, theme, workspace: Path) -> list[Path]:
        templates = self.template_root / "catalog_standard"
        project_name = html.escape(frozen.project_spec.project.name)
        project_node_key = frozen.project_spec.project.name.casefold().strip()
        blueprint_name = html.escape(self.blueprints.get(frozen.project_spec.blueprint.id).name)
        tabs = frozen.project_spec.navigation.tabs
        nav_items = "\n".join(
            f'<button class="nav-tab" type="button" data-tab="{html.escape(tab.id)}">{html.escape(tab.name)}</button>'
            for tab in tabs
        )
        topic_options = "\n".join(
            f'<option value="{html.escape(tab.id)}">{html.escape(tab.name)}</option>' for tab in tabs
        )
        topic_sections = []
        for index, tab in enumerate(tabs, start=1):
            tab_id = html.escape(tab.id)
            tab_name = html.escape(tab.name)
            starter_title = html.escape(f"{tab.name} — รายการตัวอย่าง {index}")
            topic_sections.append(
                f'<section id="{tab_id}" class="site-section" data-node-id="{stable_node_id(project_node_key, tab.id, "section/root")}" data-topic="{tab_id}">'
                f'<div class="section-heading"><div><p class="section-kicker">TOPIC {index:02d}</p><h2>{tab_name}</h2></div>'
                f'<span class="topic-count" aria-live="polite">1 รายการ</span></div>'
                f'<div class="catalog-grid">'
                f'<article class="catalog-card" data-node-id="{stable_node_id(project_node_key, tab.id, "item/1")}" data-title="{starter_title}" data-topic="{tab_id}" '
                f'data-topic-name="{tab_name}" data-description="รายการตัวอย่างสำหรับ {tab_name}">'
                f'<div class="cover-placeholder" aria-hidden="true"><span>{index:02d}</span></div>'
                f'<div class="card-copy"><span class="card-topic">{tab_name}</span><h3>{starter_title}</h3>'
                f'<p>เปิดดูรายละเอียดและเพิ่มไฟล์ PDF หรือหน้าปกของคุณได้</p>'
                f'<button class="open-detail" type="button">ดูรายละเอียด</button></div></article>'
                f'</div></section>'
            )
        index_source = (
            (templates / "index.html.tpl").read_text(encoding="utf-8")
            .replace("{{PROJECT_NAME}}", project_name)
            .replace("{{BLUEPRINT_NAME}}", blueprint_name)
            .replace("{{TOPIC_NAV}}", nav_items)
            .replace("{{TOPIC_OPTIONS}}", topic_options)
            .replace("{{TOPIC_SECTIONS}}", "\n".join(topic_sections))
        )
        palettes = {
            "blue": ("#2563eb", "#1d4ed8", "#eff6ff"),
            "green": ("#059669", "#047857", "#ecfdf5"),
            "purple": ("#7c3aed", "#6d28d9", "#f5f3ff"),
            "orange": ("#ea580c", "#c2410c", "#fff7ed"),
            "neutral": ("#334155", "#1e293b", "#f1f5f9"),
        }
        accent, accent_dark, accent_soft = palettes[frozen.project_spec.appearance.color_tone]
        css_source = (
            (templates / "styles.css.tpl").read_text(encoding="utf-8")
            .replace("{{FONT_FAMILY}}", theme.typography["font_family"])
            .replace("{{TEXT_COLOR}}", theme.colors["text"])
            .replace("{{MUTED_COLOR}}", theme.colors["muted_text"])
            .replace("{{ACCENT_COLOR}}", accent)
            .replace("{{ACCENT_DARK}}", accent_dark)
            .replace("{{ACCENT_SOFT}}", accent_soft)
        )
        app_source = (templates / "app.js").read_text(encoding="utf-8")
        paths = [workspace / "index.html", workspace / "styles.css", workspace / "app.js"]
        paths[0].write_text(index_source, encoding="utf-8")
        paths[1].write_text(css_source, encoding="utf-8")
        paths[2].write_text(app_source, encoding="utf-8")
        return paths

    def _block(self, task: str, reason: str, attempted: list[str]) -> None:
        raise BuildBlocked(
            BuildFailure(
                task=task,
                reason=reason,
                attempted=attempted,
                needs_human=True,
                suggested_actions=["Resolve the reported requirement or dependency.", "Create a new frozen spec revision if requirements change.", "Resume the build from the blocked task."],
            )
        )
