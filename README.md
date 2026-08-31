# 撿貨單分類 網頁版

上傳撿貨單 PDF，網頁把所有商品分成 常溫 / 冷藏 / 冷凍，
可按「列印 / 存成 PDF」存成 PDF。

## 分類規則

以 **SKU 欄位** 為準：SKU 內含「冷凍」→ 冷凍，「冷藏」→ 冷藏，「常溫」→ 常溫。
SKU 還沒填的列，暫時改用商品名稱判斷，並在該列標上「SKU未填」，
方便你看出哪些還沒填。SKU 填完後，分類就完全依 SKU。

想改規則：打開 `app.py` 的 `categorize` 函式。

## 本機試跑

    pip install -r requirements.txt
    python app.py        # 打開 http://127.0.0.1:5000

## 放到網路上（給網址）

這是獨立的一支程式，和「出貨單」那支分開部署、各自一個網址。

### Render（免費）
1. 把 `app.py`、`requirements.txt`、`Procfile`、`.python-version`
   放到一個 GitHub repo 的最上層（根目錄）。
2. render.com → New + → Web Service → 選 repo。
3. Build Command：`pip install -r requirements.txt`
   Start Command：`gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 180`
   （一定要整行換掉 Render 預填的 `gunicorn your_application.wsgi`。）
4. Instance Type：Free → Create。完成後會給你一個網址。

### Hugging Face Spaces（免費、記憶體大）
用 `Dockerfile`：New → Space → Docker → Blank，上傳
`app.py`、`requirements.txt`、`Dockerfile` 即可。
