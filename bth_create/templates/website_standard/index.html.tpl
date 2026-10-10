<!doctype html>
<html lang="th">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="{{PAGE_TITLE}} — {{PROJECT_NAME}}">
  <title>{{PAGE_TITLE}} · {{PROJECT_NAME}}</title>
  <link rel="stylesheet" href="styles.css">
</head>
<body data-source-model="hermes.source-model/v1" data-page-type="{{PAGE_TYPE}}">
  <div class="site-shell">
    <header class="site-header">
      <a class="site-brand" href="index.html"><span class="brand-mark">B</span><span>{{PROJECT_NAME}}<small>Multi-page Website</small></span></a>
      <nav class="site-nav" aria-label="เมนูหลัก">{{NAV_TABS}}</nav>
      <button class="menu-toggle" type="button" aria-expanded="false" aria-label="เปิดเมนู">เมนู</button>
    </header>
    <main id="{{PAGE_ID}}" class="site-section page-main" data-node-id="{{ROOT_NODE_ID}}" data-page-recipe="{{PAGE_TYPE}}" data-recipe-label="{{RECIPE_LABEL}}">
      {{PAGE_BLOCKS}}
    </main>
    <footer class="site-footer"><span>{{PROJECT_NAME}}</span><span id="build-status">กำลังโหลดข้อมูล Build…</span></footer>
  </div>
  <script src="app.js"></script>
</body>
</html>
