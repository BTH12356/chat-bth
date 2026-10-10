:root {
  font-family: {{FONT_FAMILY}};
  font-size: {{FONT_SIZE}};
  color: {{TEXT_COLOR}};
  background: {{DESKTOP_COLOR}};
}
* { box-sizing: border-box; }
body { margin: 0; min-height: 100vh; padding: 24px; background: {{DESKTOP_COLOR}}; }
.window { max-width: 1100px; margin: auto; border: 2px outset #fff; background: {{SURFACE_COLOR}}; box-shadow: 3px 3px 0 #222; }
.title-bar { padding: 5px 8px; color: #fff; background: linear-gradient(90deg, {{ACCENT_DARK}}, {{ACCENT_COLOR}}); }
.title-bar h1 { margin: 0; font-size: 14px; }
.window-body { display: grid; grid-template-columns: 180px 1fr; min-height: 540px; }
.sidebar { padding: 12px; border-right: 2px inset #fff; font-weight: 700; }
.module-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 10px; padding: 12px; align-content: start; }
.module-card { min-height: 110px; padding: 10px; border: 2px outset #fff; background: {{SURFACE_COLOR}}; }
.module-card h2 { margin: 0 0 12px; font-size: 13px; text-transform: capitalize; }
.statusbar { min-height: 24px; padding: 4px 8px; border-top: 2px inset #fff; }
@media (max-width: 640px) { .window-body { grid-template-columns: 1fr; } .sidebar { border-right: 0; border-bottom: 2px inset #fff; } }
