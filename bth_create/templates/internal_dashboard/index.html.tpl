<!doctype html>
<html lang="th">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{PROJECT_NAME}}</title>
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <main class="window">
    <header class="title-bar"><h1>{{PROJECT_NAME}}</h1></header>
    <div class="window-body">
      <nav class="sidebar" aria-label="Dashboard navigation">BTH Control Center</nav>
      <div class="module-grid">{{MODULE_CARDS}}</div>
    </div>
    <footer class="statusbar"><span id="build-status">Loading configuration…</span></footer>
  </main>
  <script src="app.js"></script>
</body>
</html>
