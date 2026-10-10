<!doctype html>
<html lang="th">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="{{PROJECT_NAME}} — searchable catalog website">
  <title>{{PROJECT_NAME}}</title>
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <div class="site-shell">
    <header class="site-header">
      <a class="site-brand" href="#catalog-top"><span class="brand-mark">B</span><span>{{PROJECT_NAME}}<small>{{BLUEPRINT_NAME}}</small></span></a>
      <nav class="site-nav" aria-label="หัวข้อและหมวดหมู่">{{TOPIC_NAV}}</nav>
      <button id="open-add-item" class="primary-button" type="button">+ เพิ่มรายการ</button>
    </header>
    <main id="catalog-top">
      <section class="catalog-hero">
        <div><p class="eyebrow">SMART CATALOG</p><h1>ค้นพบข้อมูลที่ต้องการ<br>ได้อย่างเป็นระบบ</h1><p>ค้นหา เรียงลำดับ และเปิดรายละเอียดจากทุกหัวข้อในที่เดียว</p></div>
        <div class="hero-stat"><strong id="total-count">0</strong><span>รายการในแค็ตตาล็อก</span></div>
      </section>
      <section class="catalog-toolbar" aria-label="เครื่องมือค้นหาและเรียงลำดับ">
        <label class="search-field"><span aria-hidden="true">⌕</span><input id="catalog-search" type="search" placeholder="ค้นหาชื่อ หัวข้อ หรือรายละเอียด…" autocomplete="off"></label>
        <label class="sort-field"><span>เรียงตาม</span><select id="catalog-sort"><option value="az">ชื่อ A–Z / ก–ฮ</option><option value="za">ชื่อ Z–A / ฮ–ก</option></select></label>
      </section>
      <p id="catalog-empty" class="empty-state" hidden>ไม่พบรายการที่ตรงกับคำค้นหา</p>
      <div id="catalog-sections" class="section-list">{{TOPIC_SECTIONS}}</div>
    </main>
    <footer class="site-footer"><span>{{PROJECT_NAME}}</span><span id="build-status">กำลังโหลดข้อมูล Build…</span></footer>
  </div>

  <dialog id="add-item-dialog" class="catalog-dialog">
    <form id="add-item-form">
      <div class="dialog-heading"><div><p class="eyebrow">NEW ITEM</p><h2>เพิ่มรายการใหม่</h2></div><button class="icon-button" type="button" data-close="add-item-dialog" aria-label="ปิด">×</button></div>
      <div class="form-grid">
        <label class="full-field">ชื่อรายการ<input id="item-title" maxlength="160" required placeholder="เช่น หนังสือ คู่มือ สินค้า หรือบทเรียน"></label>
        <label>หัวข้อ<select id="item-topic" required>{{TOPIC_OPTIONS}}</select></label>
        <label>ผู้เขียน / เจ้าของข้อมูล<input id="item-author" maxlength="120" placeholder="ไม่บังคับ"></label>
        <label class="full-field">คำอธิบาย<textarea id="item-description" rows="4" maxlength="1000" placeholder="รายละเอียดโดยย่อ"></textarea></label>
        <label class="file-field">เลือกหน้าปก<input id="item-cover" type="file" accept="image/*"><small>JPG, PNG, WebP หรือไฟล์ภาพอื่น สูงสุด 5 MB</small></label>
        <label class="file-field">เพิ่มไฟล์ PDF<input id="item-pdf" type="file" accept="application/pdf,.pdf"><small>สูงสุด 50 MB · จัดเก็บไว้ในเบราว์เซอร์เครื่องนี้</small></label>
      </div>
      <div class="dialog-actions"><button class="secondary-button" type="button" data-close="add-item-dialog">ยกเลิก</button><button class="primary-button" type="submit">บันทึกรายการ</button></div>
    </form>
  </dialog>

  <dialog id="item-detail-dialog" class="catalog-dialog detail-dialog">
    <div class="dialog-heading"><div><p id="detail-topic" class="eyebrow"></p><h2 id="detail-title"></h2></div><button class="icon-button" type="button" data-close="item-detail-dialog" aria-label="ปิด">×</button></div>
    <div class="detail-layout"><div id="detail-cover" class="detail-cover"></div><div><p id="detail-author" class="detail-author"></p><p id="detail-description" class="detail-description"></p><a id="detail-pdf-link" class="primary-button" href="#" target="_blank" rel="noopener" hidden>เปิดไฟล์ PDF</a><p id="detail-no-pdf" class="muted-note">รายการนี้ยังไม่มีไฟล์ PDF</p></div></div>
  </dialog>
  <script src="app.js"></script>
</body>
</html>
