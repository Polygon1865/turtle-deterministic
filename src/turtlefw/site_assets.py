"""Static assets for the published site.

The site has no build step and no external CDN: CSS and JS are emitted once per
release under ``assets/`` so pages stay small and cacheable.

The visual language mirrors the report renderer (``turtlefw.report.html``): warm
paper, ink text, clay accent, serif headlines, monospace numerals, hairline
borders and dense tables. Tokens are deliberately kept in sync with the report
CSS so the index pages and the report pages read as one publication.
"""

from __future__ import annotations

SITE_CSS = """\
:root{
  --paper:#f3f0e8;--card:#fbf8f1;--fg:#1f1d18;--muted:#6e675b;--line:#d8d0c0;
  --accent:#b4552f;--soft:#ebe3d5;--warn:#8a5a1f;--warn-soft:#f3e8d6;
  --buy:#33583f;--buy-soft:#e6ece3;--reject:#8f3f24;--reject-soft:#f0e2d8;
  --mono:ui-monospace,SFMono-Regular,"Cascadia Mono",Consolas,monospace;
  --serif:"Iowan Old Style","Palatino Linotype","Songti SC",Georgia,serif;
}
@media (prefers-color-scheme:dark){
  :root{
    --paper:#171512;--card:#211e19;--fg:#eee9de;--muted:#a59d8e;--line:#3b352b;
    --accent:#e3a07d;--soft:#2b261f;--warn:#f0b27a;--warn-soft:#3b2a19;
    --buy:#9fc0a9;--buy-soft:#1e2a23;--reject:#e3a07d;--reject-soft:#3a241d;
  }
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--paper);color:var(--fg);
  font:15px/1.75 ui-sans-serif,-apple-system,"Segoe UI","Microsoft YaHei","PingFang SC",sans-serif}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
.shell{max-width:1280px;margin:0 auto;padding:0 28px}
.main{padding-bottom:20px}

/* ---- top bar ------------------------------------------------------------ */
.top{display:flex;align-items:center;gap:18px;padding:18px 0;border-bottom:1px solid var(--line);
  font-size:12px;color:var(--muted)}
.brand{display:flex;align-items:center;gap:10px;color:var(--fg);font-weight:800;letter-spacing:-.02em}
.brand .mark{width:28px;height:28px;border-radius:8px;background:var(--fg);color:var(--paper);
  display:grid;place-items:center;font-size:13px;font-family:var(--serif);letter-spacing:0}
.brand-name{font-size:14px}
.brand-sub{font-weight:500;color:var(--muted);margin-left:6px;font-size:11px;letter-spacing:.04em}
.nav{display:flex;gap:2px;margin-left:10px}
.nav a{padding:5px 11px;border-radius:5px;color:var(--muted);font-size:12.5px;letter-spacing:.02em}
.nav a:hover{color:var(--fg);background:var(--soft);text-decoration:none}
.nav a[aria-current="page"]{color:var(--fg);font-weight:700;box-shadow:inset 0 -1px 0 var(--fg)}
.spacer{flex:1}
.asof{font-family:var(--mono);font-size:11px;letter-spacing:.02em;color:var(--muted)}

/* ---- hero --------------------------------------------------------------- */
.hero{padding:38px 0 26px;border-bottom:1px solid var(--line);margin-bottom:26px}
.kicker{margin:0 0 14px;color:var(--muted);font-size:11px;letter-spacing:.08em;
  text-transform:uppercase;display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.kicker .dot{opacity:.5}
.hero h1{font-family:var(--serif);font-size:clamp(30px,3.6vw,48px);line-height:1.08;
  letter-spacing:-.03em;font-weight:700;margin:0 0 12px;max-width:920px}
.hero h1 .badge{vertical-align:middle}
.lede{color:var(--muted);max-width:800px;margin:0;font-size:14px;line-height:1.7}
.lede a{color:var(--accent)}
.hero .meta{margin:14px 0 0;color:var(--muted);font-size:11.5px;font-family:var(--mono);
  display:flex;gap:16px;flex-wrap:wrap}

/* ---- numbers ------------------------------------------------------------ */
.statline{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
  margin:0 0 26px;background:var(--card);border:1px solid var(--line);border-radius:8px;overflow:hidden}
.stat{padding:13px 16px;border-right:1px solid var(--line);min-width:0}
.stat:last-child{border-right:0}
.stat span{display:block;color:var(--muted);font-size:10px;letter-spacing:.06em;text-transform:uppercase}
.stat b{display:block;margin-top:3px;font-family:var(--mono);font-size:19px;font-weight:700;
  letter-spacing:-.02em;font-variant-numeric:tabular-nums}
.stat b small{font-size:12px;color:var(--muted);font-weight:500}
.statline.hot .stat b{color:var(--accent)}
.stat.warn b{color:var(--warn)}

/* ---- section panels ----------------------------------------------------- */
.panel{background:var(--card);border:1px solid var(--line);border-radius:8px;margin:0 0 26px}
.panel>header{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;
  padding:13px 18px;border-bottom:1px solid var(--line)}
.panel>header h2{margin:0;font-family:var(--serif);font-size:21px;line-height:1.25;
  letter-spacing:-.02em;font-weight:700}
.panel>header .hint{color:var(--muted);font-size:11.5px}
.panel>header .links{margin-left:auto;display:flex;gap:14px;font-size:12px}
.panel .body{padding:14px 18px}
.panel .body.flush{padding:0}
.panel .body>p{margin:.4rem 0}
.panel .body>p.note{margin:.2rem 0}

/* ---- tables ------------------------------------------------------------- */
.table-wrap{overflow-x:auto;margin:0;background:var(--card)}
.panel .table-wrap{border-top:0}
table{width:100%;border-collapse:collapse;font-size:13.5px;font-variant-numeric:tabular-nums}
th,td{border-bottom:1px solid var(--line);padding:9px 12px;text-align:left;vertical-align:top;
  line-height:1.5}
th{position:sticky;top:0;z-index:1;background:var(--soft);color:var(--muted);
  font-size:11px;letter-spacing:.04em;font-weight:800;white-space:nowrap}
tbody tr:nth-child(even){background:color-mix(in srgb,var(--soft) 34%,transparent)}
tbody tr:hover{background:var(--soft)}
tr:last-child td{border-bottom:0}
td.num,th.num{text-align:right;font-family:var(--mono);font-variant-numeric:tabular-nums}
td.mono{font-family:var(--mono);font-size:12.5px;color:var(--muted)}
td strong{font-weight:700}
.table-wrap table.kv{min-width:0}

/* ---- badges ------------------------------------------------------------- */
.badge{display:inline-flex;align-items:center;border-radius:4px;padding:1px 7px;
  font:800 10px/1.6 var(--mono);letter-spacing:.04em;background:var(--soft);color:var(--accent);
  white-space:nowrap}
.badge.buy{background:var(--fg);color:var(--paper)}
.badge.watch{background:var(--warn-soft);color:var(--warn)}
.badge.reject{background:var(--reject-soft);color:var(--reject)}
.badge.muted{background:var(--soft);color:var(--muted)}
.badge.market{background:transparent;color:var(--muted);border:1px solid var(--line);
  font-weight:700;letter-spacing:.06em}
.badge.bad{background:var(--reject);color:var(--paper)}
.badge.ok{background:var(--buy-soft);color:var(--buy)}
.badge.star{background:transparent;color:var(--accent);padding:0 2px;font-size:11px}

/* ---- quick read (stock page) -------------------------------------------- */
.quickread{display:grid;grid-template-columns:1.15fr 1fr;gap:26px;margin:0 0 26px;
  padding:20px 22px;background:var(--card);border:1px solid var(--line);border-radius:8px}
.qr-main .verdict{font-family:var(--serif);font-size:34px;font-weight:700;line-height:1;
  letter-spacing:-.04em;margin:0 0 8px}
.qr-main p{margin:0;color:var(--muted);font-size:13px;line-height:1.6}
.qr-kicker{font-size:10px;font-weight:800;letter-spacing:.09em;text-transform:uppercase;
  color:var(--muted);margin-bottom:8px}
.qr-grid{display:grid;grid-template-columns:1fr 1fr;gap:0 20px;align-content:start}
.qr-cell{border-top:1px solid var(--line);padding:8px 0}
.qr-cell span{display:block;font-size:10px;letter-spacing:.05em;color:var(--muted);text-transform:uppercase}
.qr-cell strong{font:700 16px/1.5 var(--mono);font-variant-numeric:tabular-nums}
.qr-main .verdict.buy{color:var(--fg)}
.qr-main .verdict.watch{color:var(--warn)}
.qr-main .verdict.reject{color:var(--accent)}
.qr-position{margin:10px 0 0;font:600 10.5px/1.6 var(--mono);color:var(--muted);letter-spacing:.02em}

/* ---- sub sections ------------------------------------------------------- */
.subhead{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;padding:10px 18px;
  border-bottom:1px solid var(--line);background:color-mix(in srgb,var(--soft) 45%,transparent)}
.subhead h3{margin:0;font-family:var(--serif);font-size:16px;letter-spacing:-.01em;font-weight:700}
.subhead .hint{color:var(--muted);font-size:11.5px}
.subhead .count{margin-left:auto;font-family:var(--mono);font-size:11px;color:var(--muted)}

/* ---- controls ----------------------------------------------------------- */
.toolbar{display:flex;gap:10px;flex-wrap:wrap;align-items:center;padding:12px 16px;
  border-bottom:1px solid var(--line);background:var(--card)}
.toolbar input[type="search"],.toolbar select{height:32px;padding:0 10px;background:var(--paper);
  border:1px solid var(--line);border-radius:6px;color:var(--fg);font:inherit;font-size:13px}
.toolbar input[type="search"]{flex:1 1 220px;min-width:160px}
.toolbar input[type="search"]:focus,.toolbar select:focus{outline:2px solid var(--soft);border-color:var(--accent)}
.seg{display:inline-flex;border:1px solid var(--line);border-radius:6px;overflow:hidden}
.seg a,.seg button{padding:0 13px;height:32px;display:inline-flex;align-items:center;
  background:var(--card);color:var(--muted);border:0;font:700 12px/1 var(--mono);
  letter-spacing:.03em;cursor:pointer}
.seg a+a,.seg a+button,.seg button+a{border-left:1px solid var(--line)}
.seg .on{background:var(--fg);color:var(--paper)}

/* ---- misc --------------------------------------------------------------- */
.note{color:var(--muted);font-size:12.5px}
.dim{color:var(--muted)}
.mono{font-family:var(--mono);font-variant-numeric:tabular-nums}
.pos{color:var(--buy)}.neg{color:var(--reject)}
.empty{padding:30px 18px;color:var(--muted);text-align:center;font-size:13px}
.changes{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(240px,1fr))}
.changes .box{padding:12px 14px;border:1px solid var(--line);border-radius:6px;background:var(--paper)}
.changes h3{margin:0 0 6px;font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.changes ul{margin:0;padding-left:18px;font-size:13px;line-height:1.7}
.kv{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:0 20px}
.kv .item{border-top:1px solid var(--line);padding:9px 0}
.kv .item span{display:block;color:var(--muted);font-size:10px;letter-spacing:.05em;text-transform:uppercase}
.kv .item b{font:700 17px/1.5 var(--mono);font-variant-numeric:tabular-nums}
.section-title{margin:34px 0 12px;font-family:var(--serif);font-size:24px;letter-spacing:-.02em;
  padding-bottom:.4rem;border-bottom:1px solid var(--line)}
.prose{max-width:860px}
.prose h2{font-family:var(--serif);font-size:24px;line-height:1.25;letter-spacing:-.02em;
  margin:2.4rem 0 .8rem;padding-bottom:.4rem;border-bottom:1px solid var(--line)}
.prose h3{font-size:18px;margin:1.6rem 0 .5rem}
.prose p{line-height:1.85;margin:.8rem 0}
.prose ul,.prose ol{padding-left:1.3rem;line-height:1.85}
.prose blockquote{margin:1rem 0;padding:10px 14px;border-left:3px solid var(--accent);
  background:var(--soft);border-radius:0 6px 6px 0;color:var(--muted);font-size:13px}
.prose table{font-size:13px}
.prose code{font:12px/1.5 var(--mono);background:var(--soft);padding:2px 5px;border-radius:3px}

/* ---- footer ------------------------------------------------------------- */
.footer{display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap;
  color:var(--muted);font-size:11px;padding:18px 0 40px;border-top:1px solid var(--line);margin-top:34px}
.footer nav{display:flex;gap:14px;flex-wrap:wrap}
.footer a{color:var(--muted)}
.footer a:hover{color:var(--accent)}
.footer .spacer{flex:1}

@media (max-width:900px){
  .quickread{grid-template-columns:1fr}
  .hero{padding-top:28px}
  .nav a{padding:5px 8px}
}
@media (max-width:640px){
  .shell{padding:0 16px}
  .top{gap:10px;padding:12px 0}
  .brand-sub{display:none}
  .nav{overflow-x:auto}
  .hero h1{font-size:30px}
  .statline{grid-template-columns:repeat(2,1fr)}
  .stat{border-bottom:1px solid var(--line)}
  table{font-size:12.5px}
  th,td{padding:8px 9px}
  .qr-grid{grid-template-columns:1fr 1fr}
}
@media print{
  .top,.nav,.toolbar,.footer{display:none}
  body{background:#fff;color:#000;font-size:10.5pt}
  .table-wrap{overflow:visible}
  th{position:static}
}
"""

SITE_JS = """\
(function () {
  function eachTable(root, fn) {
    (root || document).querySelectorAll("table[data-sortable]").forEach(fn);
  }
  eachTable(document, function (table) {
    var rows = Array.prototype.slice.call(table.querySelectorAll("tbody tr"));
    var scope = table.closest("[data-table-scope]") || document;
    var search = scope.querySelector("[data-search]");
    var sort = scope.querySelector("[data-sort]");
    function apply() {
      var q = (search && search.value || "").trim().toLowerCase();
      rows.forEach(function (row) {
        var hit = !q || row.textContent.toLowerCase().indexOf(q) !== -1;
        row.style.display = hit ? "" : "none";
      });
    }
    if (search) search.addEventListener("input", apply);
    if (sort) sort.addEventListener("change", function () {
      var key = sort.value;
      if (!key) return;
      var body = table.querySelector("tbody");
      rows.slice().sort(function (a, b) {
        var av = parseFloat(a.getAttribute("data-" + key) || "0");
        var bv = parseFloat(b.getAttribute("data-" + key) || "0");
        return key === "rank" ? av - bv : bv - av;
      }).forEach(function (row) { body.appendChild(row); });
    });
  });
})();
"""
