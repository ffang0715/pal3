# -*- coding: utf-8 -*-
"""
撿貨單分類 網頁版  Picking-list Sorter
------------------------------------------------
上傳撿貨單 PDF，網頁把所有商品分成 常溫 / 冷藏 / 冷凍。
分類依據：SKU 欄位裡的「常溫 / 冷藏 / 冷凍」字樣。
（SKU 還沒填的列，先用商品名稱判斷，並標上「SKU未填」提醒。）
按「列印 / 存成 PDF」，瀏覽器就會存成 PDF。

本機執行:  pip install flask pdfplumber
          python app.py   ->  http://127.0.0.1:5000
"""
import io
import re
import html
import logging

import pdfplumber
from flask import Flask, request, Response, redirect

logging.getLogger("pdfminer").setLevel(logging.ERROR)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024

BUCKET_ORDER = ["常溫", "冷藏", "冷凍"]
BUCKET_TINT = {"常溫": "#f4efe4", "冷藏": "#e7f0f7", "冷凍": "#e6f2f4"}
BUCKET_INK = {"常溫": "#8a6d3b", "冷藏": "#2e6da4", "冷凍": "#2f7d8c"}


# ============================================================
# 分類：以 SKU 欄為準
# ============================================================
def categorize(sku, name, spec):
    """
    回傳 (籃子, sku_ok)。
    sku_ok=True 代表這一列是靠 SKU 判斷的；
    False 代表 SKU 還沒填，暫時改用商品名稱／規格判斷。
    """
    for b in ("冷凍", "冷藏", "常溫"):
        if b in sku:
            return b, True
    blob = f"{name} {spec}"
    if "冷凍" in blob:
        return "冷凍", False
    if "冷藏" in blob:
        return "冷藏", False
    if "常溫" in blob:
        return "常溫", False
    return "常溫", False


# ============================================================
# 讀撿貨單 PDF
# ============================================================
def parse_picklist(stream):
    items = []
    meta = {"count": "", "date": ""}
    with pdfplumber.open(stream) as pdf:
        t0 = pdf.pages[0].extract_text() or ""
        m = re.search(r"選擇訂單數[:：]\s*(\d+)", t0)
        if m:
            meta["count"] = m.group(1)
        m = re.search(r"列印日期[:：]\s*([\d/:\s]+)", t0)
        if m:
            meta["date"] = m.group(1).strip()
        for page in pdf.pages:
            for tb in page.extract_tables():
                for r in tb:
                    if not r:
                        continue
                    pid = (r[0] or "").strip()
                    if not pid.isdigit():
                        continue
                    items.append({
                        "pid": pid,
                        "sku": (r[1] or "").strip().replace("\n", ""),
                        "model": (r[2] or "").strip().replace("\n", ""),
                        "name": (r[3] or "").strip().replace("\n", ""),
                        "spec": (r[4] or "").strip().replace("\n", ""),
                        "qty": (r[6] or "").strip() if len(r) > 6 else "",
                    })
            try:
                page.flush_cache()
            except Exception:
                pass
    return {"items": items, "meta": meta}


def _qnum(q):
    d = re.sub(r"\D", "", q or "")
    return int(d) if d else 0


def group_items(items):
    b = {x: [] for x in BUCKET_ORDER}
    for it in items:
        bucket, sku_ok = categorize(it["sku"], it["name"], it["spec"])
        it = dict(it)
        it["sku_ok"] = sku_ok
        b[bucket].append(it)
    present = [x for x in BUCKET_ORDER if b[x]]
    denom = len(present)
    return [(x, i, denom, b[x]) for i, x in enumerate(present, 1)]


# ============================================================
# 產生結果頁
# ============================================================
SHEET_CSS = """
  * { box-sizing:border-box; }
  body { font-family:"PingFang TC","Microsoft JhengHei","Noto Sans CJK TC","Heiti TC",sans-serif;
         color:#2b2b2b; margin:0; background:#efeae0;
         -webkit-print-color-adjust:exact; print-color-adjust:exact; }
  .toolbar { position:sticky; top:0; z-index:10; background:#5b4a2f; color:#fff;
             display:flex; align-items:center; gap:14px; padding:12px 18px; }
  .toolbar .grow { flex:1; font-size:14px; }
  .toolbar button, .toolbar a { font:inherit; font-size:14px; border:none; border-radius:8px;
             padding:9px 16px; cursor:pointer; text-decoration:none; }
  .btn-pdf { background:#e5b769; color:#3a2f1a; font-weight:700; }
  .btn-back { background:#7a6647; color:#fff; }
  .page { background:#efeae0; padding:20px 0; }
  .sheet { max-width:820px; margin:0 auto; background:#fff; padding:26px 34px;
           box-shadow:0 1px 6px rgba(0,0,0,.12); }
  .pk-title { font-size:22px; font-weight:800; margin-bottom:14px; }
  .pk-meta { font-size:13px; font-weight:400; color:#7a6647; margin-left:10px; }
  table { width:100%; border-collapse:collapse; font-size:12.5px; }
  tr { break-inside:avoid; }
  thead th { background:#f3f1ec; border:1px solid #d9d5cb; padding:6px 10px;
             font-weight:600; text-align:left; color:#444; }
  tbody td { border:1px solid #e2ded4; padding:5px 10px; vertical-align:top; }
  .c-idx { width:40px; text-align:center; color:#888; }
  .c-spec { width:120px; color:#555; }
  .c-num { width:60px; text-align:right; white-space:nowrap; }
  thead th.c-num, thead th.c-spec { text-align:left; }
  .grouphead td { padding:8px 12px; font-weight:700; }
  .gname { font-size:15px; letter-spacing:2px; }
  .gfrac { float:right; font-size:15px; font-weight:800;
           border:1.5px solid currentColor; border-radius:14px; padding:1px 12px; }
  .gcount { float:right; margin-right:14px; font-size:13px; font-weight:600; opacity:.85; }
  .flag { display:inline-block; margin-left:8px; font-size:10.5px; color:#b45309;
          background:#fdf1dc; border:1px solid #e7c98f; border-radius:5px; padding:0 5px; }
  @media print {
    .toolbar { display:none; }
    body, .page { background:#fff; padding:0; }
    .sheet { box-shadow:none; max-width:none; padding-left:0; padding-right:0; }
    @page { margin:10mm; }
  }
"""


def picklist_page(data):
    items, meta = data["items"], data["meta"]
    esc = html.escape

    def cell(v):
        return esc(v or "")

    rows, unfilled = [], 0
    for name, num, denom, its in group_items(items):
        tint, ink = BUCKET_TINT.get(name, "#eee"), BUCKET_INK.get(name, "#333")
        tot = sum(_qnum(it["qty"]) for it in its)
        rows.append(
            f'<tr class="grouphead" style="background:{tint};color:{ink}">'
            f'<td colspan="5"><span class="gname">{esc(name)}</span>'
            f'<span class="gfrac">{num} / {denom}</span>'
            f'<span class="gcount">{len(its)} 項 · 共 {tot} 件</span></td></tr>')
        for it in its:
            flag = ""
            if not it["sku_ok"]:
                unfilled += 1
                flag = '<span class="flag">SKU未填</span>'
            rows.append(
                "<tr>"
                f'<td class="c-idx">{cell(it["pid"])}</td>'
                f'<td class="c-name">{cell(it["name"])}{flag}</td>'
                f'<td class="c-spec">{cell(it["model"])}</td>'
                f'<td class="c-spec">{cell(it["spec"])}</td>'
                f'<td class="c-num">{cell(it["qty"])}</td></tr>')

    metatxt = []
    if meta.get("count"):
        metatxt.append(f'訂單數 {esc(meta["count"])}')
    if meta.get("date"):
        metatxt.append(f'列印 {esc(meta["date"])}')
    if unfilled:
        metatxt.append(f'{unfilled} 項 SKU 未填（暫用品名判斷）')
    metaline = "　".join(metatxt)

    return f"""<!DOCTYPE html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>撿貨單分類</title>
<style>{SHEET_CSS}</style></head>
<body>
  <div class="toolbar">
    <span class="grow">撿貨單　已分好 常溫 / 冷藏 / 冷凍</span>
    <button class="btn-pdf" onclick="window.print()">列印 / 存成 PDF</button>
    <a class="btn-back" href="/">重新上傳</a>
  </div>
  <div class="page"><div class="sheet">
    <div class="pk-title">撿貨單分類 <span class="pk-meta">{metaline}</span></div>
    <table>
      <thead><tr>
        <th class="c-idx">ID</th><th class="c-name">商品名稱</th>
        <th class="c-spec">型號</th><th class="c-spec">規格</th><th class="c-num">數量</th>
      </tr></thead>
      <tbody>{''.join(rows)}</tbody>
    </table>
  </div></div>
</body></html>"""


UPLOAD_PAGE = """<!DOCTYPE html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>撿貨單分類</title>
<style>
  body { font-family:"PingFang TC","Microsoft JhengHei","Noto Sans CJK TC",sans-serif;
         background:#efeae0; color:#3a2f1a; margin:0;
         min-height:100vh; display:flex; align-items:center; justify-content:center; }
  .card { background:#fff; width:min(560px,92vw); padding:34px 30px;
          border-radius:16px; box-shadow:0 4px 20px rgba(0,0,0,.10); text-align:center; }
  h1 { font-size:22px; margin:0 0 6px; }
  p.sub { color:#7a6647; margin:0 0 22px; font-size:14px; }
  #drop { display:block; border:2px dashed #c7b48d; border-radius:12px; padding:44px 20px;
          background:#faf7ef; cursor:pointer; transition:.15s; }
  #drop.hover { background:#f3ead2; border-color:#a98f5c; }
  #drop .big { font-size:16px; font-weight:700; margin-bottom:6px; }
  #drop .small { font-size:13px; color:#8a7a5c; }
  input[type=file] { display:none; }
  .foot { margin-top:18px; font-size:12px; color:#a2926f; }
</style></head>
<body>
  <div class="card">
    <h1>撿貨單分類</h1>
    <p class="sub">上傳撿貨單 PDF，依 SKU 欄分成 常溫 / 冷藏 / 冷凍</p>
    <form id="f" method="post" action="/process" enctype="multipart/form-data">
      <label id="drop" for="file">
        <div class="big">把撿貨單 PDF 拖到這裡</div>
        <div class="small">或點一下選擇檔案</div>
      </label>
      <input id="file" name="file" type="file" accept="application/pdf">
    </form>
    <div class="foot">處理完成後按「列印 / 存成 PDF」即可存成 PDF</div>
  </div>
<script>
  const drop=document.getElementById('drop'), inp=document.getElementById('file'),
        form=document.getElementById('f');
  function go(){ if(inp.files.length){ form.submit(); } }
  inp.addEventListener('change', go);
  ['dragenter','dragover'].forEach(e=>drop.addEventListener(e,ev=>{ev.preventDefault();drop.classList.add('hover');}));
  ['dragleave','drop'].forEach(e=>drop.addEventListener(e,ev=>{ev.preventDefault();drop.classList.remove('hover');}));
  drop.addEventListener('drop',ev=>{ if(ev.dataTransfer.files.length){ inp.files=ev.dataTransfer.files; go(); }});
</script>
</body></html>"""


@app.route("/")
def index():
    return UPLOAD_PAGE


@app.route("/process", methods=["POST"])
def process():
    f = request.files.get("file")
    if not f or not f.filename.lower().endswith(".pdf"):
        return redirect("/")
    try:
        data = parse_picklist(f.stream)
    except Exception as e:
        return Response(f"讀取失敗：{html.escape(str(e))}", mimetype="text/plain")
    if not data["items"]:
        return Response("這份撿貨單裡沒有抓到商品。", mimetype="text/plain")
    return Response(picklist_page(data), mimetype="text/html")


if __name__ == "__main__":
    import os
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
