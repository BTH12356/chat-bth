:root { font-family: {{FONT_FAMILY}}; color: {{TEXT_COLOR}}; background: #f8fafc; --text: {{TEXT_COLOR}}; --accent: {{ACCENT_COLOR}}; --accent-dark: {{ACCENT_DARK}}; --accent-soft: {{ACCENT_SOFT}}; --muted: {{MUTED_COLOR}}; --line: #e2e8f0; }
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body { margin: 0; background: linear-gradient(180deg, var(--accent-soft), #f8fafc 420px); }
button, input, select, textarea { font: inherit; }
button, select { cursor: pointer; }
.site-shell { min-height: 100vh; display: flex; flex-direction: column; }
.site-header { position: sticky; top: 0; z-index: 20; display: flex; align-items: center; gap: 24px; padding: 14px clamp(20px, 4vw, 64px); border-bottom: 1px solid var(--line); background: rgba(255,255,255,.94); backdrop-filter: blur(18px); }
.site-brand { display: flex; align-items: center; gap: 10px; color: var(--accent-dark); font-weight: 800; text-decoration: none; white-space: nowrap; }
.site-brand small { display: block; margin-top: 2px; color: var(--muted); font-size: .65rem; font-weight: 600; }
.brand-mark { display: grid; place-items: center; width: 36px; height: 36px; border-radius: 11px; background: var(--accent); color: #fff; }
.site-nav { display: flex; flex: 1; flex-wrap: wrap; justify-content: center; gap: 5px; }
.nav-tab { padding: 8px 11px; border: 0; border-radius: 999px; background: transparent; color: var(--muted); }
.nav-tab:hover, .nav-tab.active { color: var(--accent-dark); background: var(--accent-soft); }
.primary-button, .secondary-button, .open-detail { display: inline-flex; align-items: center; justify-content: center; min-height: 40px; padding: 9px 15px; border-radius: 11px; font-weight: 750; text-decoration: none; }
.primary-button, .open-detail { border: 1px solid var(--accent); background: var(--accent); color: #fff; }
.primary-button:hover, .open-detail:hover { border-color: var(--accent-dark); background: var(--accent-dark); }
.secondary-button { border: 1px solid var(--line); background: #fff; color: var(--text); }
main { width: min(1180px, calc(100% - 40px)); margin: 0 auto; flex: 1; }
.catalog-hero { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: end; gap: 40px; padding: clamp(60px, 10vw, 120px) 0 44px; }
.eyebrow, .section-kicker, .card-topic { color: var(--accent); font-size: .72rem; font-weight: 850; letter-spacing: .14em; text-transform: uppercase; }
.catalog-hero h1 { margin: 10px 0 18px; max-width: 850px; font-size: clamp(2.5rem, 6vw, 5rem); line-height: 1.03; }
.catalog-hero > div > p:last-child { color: var(--muted); line-height: 1.7; }
.hero-stat { min-width: 170px; padding: 25px; border: 1px solid rgba(255,255,255,.8); border-radius: 22px; background: rgba(255,255,255,.68); box-shadow: 0 18px 50px rgba(15,23,42,.08); }
.hero-stat strong { display: block; color: var(--accent-dark); font-size: 2.5rem; }
.hero-stat span { color: var(--muted); font-size: .82rem; }
.catalog-toolbar { position: sticky; top: 79px; z-index: 12; display: grid; grid-template-columns: 1fr auto; gap: 12px; margin-bottom: 30px; padding: 12px; border: 1px solid var(--line); border-radius: 17px; background: rgba(255,255,255,.94); box-shadow: 0 14px 35px rgba(15,23,42,.07); backdrop-filter: blur(14px); }
.search-field { display: flex; align-items: center; gap: 8px; min-width: 0; }
.search-field span { color: var(--accent); font-size: 1.4rem; }
.search-field input { width: 100%; border: 0; outline: 0; background: transparent; color: inherit; }
.sort-field { display: flex; align-items: center; gap: 8px; color: var(--muted); font-size: .8rem; }
.sort-field select { padding: 8px 30px 8px 10px; border: 1px solid var(--line); border-radius: 9px; background: #fff; color: inherit; }
.section-list { display: grid; gap: 28px; padding-bottom: 80px; }
.site-section { scroll-margin-top: 150px; }
.section-heading { display: flex; align-items: end; justify-content: space-between; gap: 20px; margin-bottom: 14px; }
.section-heading h2 { margin: 5px 0 0; font-size: clamp(1.5rem, 3vw, 2.2rem); }
.topic-count { color: var(--muted); font-size: .8rem; }
.catalog-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(245px, 1fr)); gap: 17px; }
.catalog-card { display: grid; grid-template-columns: 98px minmax(0, 1fr); gap: 16px; min-height: 190px; padding: 15px; border: 1px solid var(--line); border-radius: 18px; background: #fff; box-shadow: 0 12px 35px rgba(15,23,42,.055); transition: transform .18s, box-shadow .18s; }
.catalog-card:hover { transform: translateY(-3px); box-shadow: 0 18px 45px rgba(15,23,42,.1); }
.cover-placeholder, .card-cover, .detail-cover { overflow: hidden; border-radius: 12px; background: linear-gradient(145deg, var(--accent), var(--accent-dark)); }
.cover-placeholder { display: grid; place-items: center; min-height: 150px; color: #fff; font-size: 1.8rem; font-weight: 850; }
.card-cover { width: 98px; height: 150px; object-fit: cover; }
.card-copy { min-width: 0; display: flex; align-items: flex-start; flex-direction: column; }
.card-copy h3 { margin: 8px 0; font-size: 1.03rem; line-height: 1.35; }
.card-copy p { display: -webkit-box; overflow: hidden; margin: 0 0 13px; color: var(--muted); font-size: .82rem; line-height: 1.55; -webkit-box-orient: vertical; -webkit-line-clamp: 3; }
.open-detail { min-height: 34px; margin-top: auto; padding: 6px 10px; font-size: .76rem; }
.empty-state { padding: 48px; border: 1px dashed var(--line); border-radius: 18px; background: #fff; text-align: center; color: var(--muted); }
.site-footer { display: flex; justify-content: space-between; gap: 16px; padding: 24px clamp(20px, 4vw, 64px); border-top: 1px solid var(--line); color: var(--muted); font-size: .78rem; }
.catalog-dialog { width: min(680px, calc(100% - 28px)); padding: 0; border: 0; border-radius: 22px; box-shadow: 0 28px 90px rgba(15,23,42,.26); }
.catalog-dialog::backdrop { background: rgba(15,23,42,.58); backdrop-filter: blur(3px); }
.catalog-dialog form, .detail-dialog { padding: 24px; }
.dialog-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; margin-bottom: 22px; }
.dialog-heading h2 { margin: 4px 0 0; }
.icon-button { width: 38px; height: 38px; border: 1px solid var(--line); border-radius: 50%; background: #fff; color: var(--muted); font-size: 1.5rem; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.form-grid label { display: grid; gap: 7px; color: var(--muted); font-size: .8rem; font-weight: 700; }
.form-grid input, .form-grid select, .form-grid textarea { width: 100%; padding: 11px 12px; border: 1px solid var(--line); border-radius: 10px; outline: 0; color: var(--text); resize: vertical; }
.form-grid input:focus, .form-grid select:focus, .form-grid textarea:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }
.full-field { grid-column: 1 / -1; }
.file-field { padding: 13px; border: 1px dashed var(--line); border-radius: 12px; background: #f8fafc; }
.file-field input { padding: 5px; background: #fff; }
.file-field small { font-weight: 500; }
.dialog-actions { display: flex; justify-content: flex-end; gap: 9px; margin-top: 22px; }
.detail-layout { display: grid; grid-template-columns: 210px 1fr; gap: 24px; }
.detail-cover { display: grid; place-items: center; width: 210px; min-height: 285px; color: #fff; font-size: 2.5rem; font-weight: 850; background-size: cover; background-position: center; }
.detail-author, .detail-description, .muted-note { color: var(--muted); line-height: 1.7; }
[hidden] { display: none !important; }
@media (max-width: 780px) { .site-header { align-items: flex-start; flex-wrap: wrap; } .site-nav { order: 3; width: 100%; justify-content: flex-start; overflow-x: auto; flex-wrap: nowrap; } .catalog-toolbar { top: 132px; } .catalog-hero { grid-template-columns: 1fr; } .hero-stat { width: fit-content; } }
@media (max-width: 560px) { main { width: min(100% - 26px, 1180px); } .site-header > .primary-button { margin-left: auto; } .catalog-toolbar, .form-grid, .detail-layout { grid-template-columns: 1fr; } .sort-field { justify-content: space-between; } .catalog-card { grid-template-columns: 82px minmax(0, 1fr); } .card-cover { width: 82px; height: 128px; } .detail-cover { width: 100%; min-height: 240px; } .site-footer { flex-direction: column; } }
