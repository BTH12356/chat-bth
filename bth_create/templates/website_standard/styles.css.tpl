:root { font-family: {{FONT_FAMILY}}; color: {{TEXT_COLOR}}; background: #f8fafc; --text: {{TEXT_COLOR}}; --muted: {{MUTED_COLOR}}; --accent: {{ACCENT_COLOR}}; --accent-dark: {{ACCENT_DARK}}; --accent-soft: {{ACCENT_SOFT}}; --line: #e2e8f0; }
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body { margin: 0; background: linear-gradient(180deg, var(--accent-soft), #f8fafc 430px); }
button, input, select, textarea { font: inherit; }
a { color: inherit; }
.site-shell { min-height: 100vh; display: flex; flex-direction: column; }
.site-header { position: sticky; top: 0; z-index: 20; display: flex; align-items: center; gap: 24px; padding: 14px clamp(18px, 4vw, 64px); border-bottom: 1px solid var(--line); background: rgba(255,255,255,.95); backdrop-filter: blur(18px); }
.site-brand { display: flex; align-items: center; gap: 10px; color: var(--accent-dark); font-weight: 850; text-decoration: none; white-space: nowrap; }
.site-brand small { display: block; margin-top: 2px; color: var(--muted); font-size: .64rem; font-weight: 600; }
.brand-mark { display: grid; place-items: center; width: 36px; height: 36px; border-radius: 11px; background: var(--accent); color: #fff; }
.site-nav { display: flex; flex: 1; justify-content: center; flex-wrap: wrap; gap: 5px; }
.nav-tab { padding: 8px 11px; border-radius: 999px; color: var(--muted); font-size: .86rem; text-decoration: none; }
.nav-tab:hover, .nav-tab.active { color: var(--accent-dark); background: var(--accent-soft); }
.menu-toggle { display: none; padding: 8px 12px; border: 1px solid var(--line); border-radius: 9px; background: #fff; color: var(--text); }
.page-main { width: min(1180px, calc(100% - 40px)); margin: 0 auto; flex: 1; }
.eyebrow { margin: 0; color: var(--accent); font-size: .72rem; font-weight: 850; letter-spacing: .15em; text-transform: uppercase; }
.hero-block, .page-header { display: grid; grid-template-columns: minmax(0, 1.2fr) minmax(300px, .8fr); align-items: center; gap: clamp(28px, 6vw, 80px); padding: clamp(64px, 10vw, 125px) 0 58px; }
.page-header:not(.image-header) { grid-template-columns: minmax(0, 780px); }
.hero-block h1, .page-header h1 { margin: 12px 0 18px; max-width: 850px; font-size: clamp(2.5rem, 6vw, 5.2rem); line-height: 1.03; }
.hero-block p:not(.eyebrow), .page-header p:not(.eyebrow) { max-width: 670px; color: var(--muted); line-height: 1.75; }
.hero-visual, .header-image, .image-slot { position: relative; overflow: hidden; display: grid; place-items: center; min-height: 320px; border: 1px solid rgba(255,255,255,.8); border-radius: 28px; background: linear-gradient(145deg, var(--accent), var(--accent-dark)); background-position: center; background-size: cover; color: #fff; box-shadow: 0 25px 70px rgba(15,23,42,.18); }
.hero-visual::after, .header-image::after, .image-slot::after { content: ""; position: absolute; inset: 0; background: linear-gradient(135deg, transparent, rgba(255,255,255,.18)); pointer-events: none; }
.page-image-input { position: absolute; inset: auto 16px 16px; z-index: 2; max-width: calc(100% - 32px); color: #fff; font-size: .7rem; }
.primary-link, .secondary-link, .contact-form button { display: inline-flex; align-items: center; justify-content: center; min-height: 42px; margin-top: 13px; padding: 10px 16px; border: 1px solid var(--accent); border-radius: 11px; background: var(--accent); color: #fff; font-weight: 780; text-decoration: none; }
.secondary-link { border-color: var(--line); background: #fff; color: var(--accent-dark); }
.content-block { padding: 55px 0; }
.block-heading { display: flex; align-items: end; justify-content: space-between; gap: 24px; margin-bottom: 20px; }
.block-heading h2, .content-block h2, .feature-panel h2, .cta-block h2 { margin: 7px 0 0; font-size: clamp(1.6rem, 3vw, 2.5rem); }
.card-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 17px; }
.content-card, .resource-card { display: flex; align-items: flex-start; flex-direction: column; min-height: 210px; padding: 23px; border: 1px solid var(--line); border-radius: 19px; background: #fff; box-shadow: 0 14px 38px rgba(15,23,42,.06); }
.resource-card { min-height: 245px; border-top: 4px solid var(--accent); }
.card-index { color: var(--accent); font-weight: 850; }
.content-card h3, .resource-card h3 { margin: 24px 0 8px; }
.content-card p, .resource-card p { color: var(--muted); font-size: .87rem; line-height: 1.65; }
.content-card a, .resource-card a { margin-top: auto; color: var(--accent-dark); font-size: .82rem; font-weight: 750; text-decoration: none; }
.article-layout, .contact-layout { display: grid; grid-template-columns: minmax(220px, .7fr) minmax(0, 1.3fr); gap: clamp(35px, 8vw, 110px); }
.article-copy { color: var(--muted); font-size: 1.05rem; line-height: 1.9; }
.image-grid { display: grid; grid-template-columns: 1.3fr 1fr 1fr; gap: 16px; }
.image-slot { min-height: 250px; border-radius: 18px; box-shadow: none; }
.filter-toolbar { position: sticky; top: 76px; z-index: 12; display: grid; grid-template-columns: 1fr auto; gap: 12px; margin: 0 0 28px; padding: 13px; border: 1px solid var(--line); border-radius: 16px; background: rgba(255,255,255,.95); box-shadow: 0 12px 35px rgba(15,23,42,.07); }
.filter-toolbar label { display: flex; align-items: center; gap: 10px; color: var(--muted); font-size: .8rem; }
.filter-toolbar input, .filter-toolbar select { width: 100%; padding: 9px 10px; border: 1px solid var(--line); border-radius: 9px; background: #fff; }
.category-chips { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 10px; }
.category-chips button { padding: 8px 13px; border: 1px solid var(--line); border-radius: 999px; background: #fff; color: var(--muted); }
.category-chips button.active { border-color: var(--accent); background: var(--accent-soft); color: var(--accent-dark); }
.resource-upload { position: relative; overflow: hidden; padding: 9px 13px; border: 1px solid var(--accent); border-radius: 10px; color: var(--accent-dark); font-size: .8rem; font-weight: 750; cursor: pointer; }
.resource-upload input { position: absolute; inset: 0; opacity: 0; cursor: pointer; }
.feature-panel, .cta-block { margin: 35px 0 65px; padding: clamp(28px, 5vw, 55px); border: 1px solid var(--line); border-radius: 25px; background: #fff; box-shadow: 0 18px 55px rgba(15,23,42,.07); }
.feature-panel p:not(.eyebrow) { color: var(--muted); line-height: 1.75; }
.process-list { display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; padding: 0; list-style: none; }
.process-list li { display: grid; gap: 22px; padding: 25px; border-radius: 18px; background: var(--accent-soft); line-height: 1.6; }
.process-list strong { color: var(--accent); font-size: 1.7rem; }
.contact-form { display: grid; gap: 13px; padding: 24px; border: 1px solid var(--line); border-radius: 20px; background: #fff; }
.contact-form label { display: grid; gap: 6px; color: var(--muted); font-size: .8rem; }
.contact-form input, .contact-form textarea { padding: 11px; border: 1px solid var(--line); border-radius: 9px; resize: vertical; }
.contact-form button { cursor: pointer; }
.cta-block { display: flex; align-items: center; justify-content: space-between; gap: 25px; background: linear-gradient(135deg, #fff, var(--accent-soft)); }
.site-footer { display: flex; justify-content: space-between; gap: 16px; padding: 24px clamp(18px, 4vw, 64px); border-top: 1px solid var(--line); color: var(--muted); font-size: .78rem; }
[hidden] { display: none !important; }
@media (max-width: 820px) { .site-header { flex-wrap: wrap; } .menu-toggle { display: block; margin-left: auto; } .site-nav { display: none; order: 3; width: 100%; justify-content: flex-start; flex-direction: column; } .site-nav.open { display: flex; } .hero-block, .page-header, .article-layout, .contact-layout { grid-template-columns: 1fr; } .hero-visual, .header-image { min-height: 260px; } .filter-toolbar { top: 72px; } }
@media (max-width: 580px) { .page-main { width: min(100% - 26px, 1180px); } .image-grid, .process-list, .filter-toolbar { grid-template-columns: 1fr; } .block-heading, .cta-block, .site-footer { align-items: flex-start; flex-direction: column; } }
