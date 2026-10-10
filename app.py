"""
NID Verification — উচ্চ নির্ভরযোগ্যতা সংস্করণ
- দ্বৈত OCR ইঞ্জিন: ppllocr (প্রধান) + ddddocr (ব্যাকআপ)
- OCR ফলাফল ভোটিং মেকানিজম
- প্রতিটি NID-এর আগে জোরপূর্বক পৃষ্ঠা রিলোড
- নিশ্চিত ফলাফল না আসা পর্যন্ত অসীম পুনঃপ্রচেষ্টা
- ম্যানুয়াল ইনপুট মোড
"""

import csv
import io
import threading
import queue
import time
from flask import Flask, render_template, request
from playwright.sync_api import sync_playwright
import ddddocr
from ppllocr import OCR as PpllOCR
import cv2
import numpy as np
from collections import Counter

app = Flask(__name__)

TARGET_URL = "https://services.nidw.gov.bd/nid-pub/card-status"

SELECTORS = {
    "nid_input":     'input[name="nid"]',
    "day_input":     'input[name="day"]',
    "month_input":   'input[name="month"]',
    "year_input":    'input[name="year"]',
    "captcha_image": '#captcha-image',
    "captcha_input": 'input[name="captcha"]',
    "submit_button": '#validate',
}

MAX_CAPTCHA_RETRIES = 6
CAPTCHA_ERROR_KEYWORDS = ["কোড", "captcha", "প্রদর্শিত কোড", "ভুল কোড"]
INVALID_NID_KEYWORDS = [
    "জন্মতারিখ ভুল", "পরিচয়পত্র নম্বর", "ফর্ম নম্বর",
    "ভুল দিয়েছেন", "পাওয়া যায়নি",
]

# ============================================================
# দ্বৈত OCR ইঞ্জিন
# ============================================================
ppll_ocr = PpllOCR()
dddd_ocr = ddddocr.DdddOcr(show_ad=False)

def _preprocess(img_bytes, block_size=11):
    """OpenCV প্রতিচ্ছবি প্রিপ্রসেসিং"""
    arr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return img_bytes
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    binary = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, block_size, 2
    )
    denoised = cv2.medianBlur(binary, 3)
    _, encoded = cv2.imencode('.png', denoised)
    return encoded.tobytes()

def solve_captcha_dual_engine(image_bytes):
    """
    দ্বৈত ইঞ্জিন OCR ভোটিং:
    1. ppllocr এবং ddddocr যথাক্রমে স্বীকৃতি
    2. ফলাফল একই হলে, সরাসরি ফেরত দিন
    3. অসঙ্গতি হলে, আরও বিশ্বাসযোগ্য ফলাফল ফেরত দিন
    4. উভয়ই খালি হলে, প্রিপ্রসেসিংয়ের পরে পুনরায় চেষ্টা করুন
    """
    ppll_result = ""
    dddd_result = ""
    
    # ppllocr স্বীকৃতি
    try:
        r = ppll_ocr.classification(image_bytes)
        if r:
            ppll_result = r.strip()
    except Exception as e:
        print(f"[ppllocr] failed: {e}")
    
    # ddddocr স্বীকৃতি
    try:
        r = dddd_ocr.classification(image_bytes)
        if r:
            dddd_result = r.strip()
    except Exception as e:
        print(f"[ddddocr] failed: {e}")
    
    print(f"[OCR] ppllocr='{ppll_result}', ddddocr='{dddd_result}'")
    
    # ভোটিং লজিক
    if ppll_result and dddd_result:
        if ppll_result == dddd_result:
            print(f"[OCR] both agree: '{ppll_result}'")
            return ppll_result
        # অসঙ্গতি: লম্বা ফলাফল অগ্রাধিকার (সাধারণত আরও সম্পূর্ণ)
        if len(ppll_result) >= len(dddd_result):
            return ppll_result
        return dddd_result
    elif ppll_result:
        return ppll_result
    elif dddd_result:
        return dddd_result
    else:
        # উভয়ই ব্যর্থ: প্রিপ্রসেসিংয়ের পরে পুনরায় চেষ্টা করুন
        for bs in (9, 11, 13):
            try:
                processed = _preprocess(image_bytes, bs)
                r = ppll_ocr.classification(processed)
                if r:
                    print(f"[OCR] preprocessed result: '{r}'")
                    return r.strip()
            except Exception:
                pass
        return ""

def get_captcha_text(page):
    """পৃষ্ঠা থেকে CAPTCHA স্ক্রিনশট নিন এবং স্বীকৃতি দিন"""
    try:
        img = page.locator(SELECTORS["captcha_image"]).first
        if img.count() == 0:
            return None
        img.wait_for(state="visible", timeout=5000)
        page.wait_for_timeout(250)
        img_bytes = img.screenshot()  # Playwright এলিমেন্ট স্ক্রিনশট [citation:5]
        text = solve_captcha_dual_engine(img_bytes)
        print(f"[CAPTCHA] final: '{text}'")
        return text if text else None
    except Exception as e:
        print(f"[CAPTCHA] OCR failed: {e}")
        return None

def wait_for_captcha_loaded(page, timeout_ms=8000):
    """CAPTCHA ছবি সম্পূর্ণ লোড হওয়ার জন্য অপেক্ষা করুন"""
    try:
        page.wait_for_function(
            """() => {
                const img = document.querySelector('#captcha-image');
                return img && img.complete && img.naturalWidth > 0;
            }""",
            timeout=timeout_ms
        )
        return True
    except Exception as e:
        print(f"[CAPTCHA] wait_for_loaded failed: {e}")
        return False

def refresh_captcha(page):
    """CAPTCHA রিফ্রেশ করুন এবং লোড হওয়ার জন্য অপেক্ষা করুন"""
    try:
        page.click(SELECTORS["captcha_image"])
        page.wait_for_timeout(900)
        wait_for_captcha_loaded(page)
        return True
    except Exception as e:
        print(f"[CAPTCHA] refresh failed: {e}")
        return False

# ============================================================
# ফলাফল/ত্রুটি সনাক্তকরণ
# ============================================================
def page_has_result(page):
    """ফলাফল সারণী আছে কিনা পরীক্ষা করুন (Box ID/Comp ID হেডার সনাক্তকরণের মাধ্যমে)"""
    try:
        tables = page.locator("table")
        for i in range(tables.count()):
            t = tables.nth(i)
            try:
                text = t.text_content() or ""
                if "Box ID" in text and "Comp ID" in text and "Status" in text:
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False

def format_result_table(page):
    """ফলাফল সারণীকে 'Header: Value | Header: Value' ফরম্যাটে রূপান্তর করুন"""
    try:
        tables = page.locator("table")
        for i in range(tables.count()):
            t = tables.nth(i)
            text = t.text_content() or ""
            if "Box ID" not in text or "Comp ID" not in text:
                continue
            first_row = t.locator("tr").first
            header_cells = first_row.locator("th, td")
            headers = [header_cells.nth(j).text_content().strip()
                       for j in range(header_cells.count())]
            rows = t.locator("tr")
            data_cells = None
            for r_idx in range(1, rows.count()):
                cells = rows.nth(r_idx).locator("td")
                if cells.count() >= 3:
                    first_val = cells.nth(0).text_content().strip()
                    if first_val and first_val.lower() != "status":
                        data_cells = cells
                        break
            if data_cells and headers:
                parts = []
                for j in range(min(len(headers), data_cells.count())):
                    h = headers[j]
                    v = data_cells.nth(j).text_content().strip()
                    parts.append(f"{h}: {v}")
                return " | ".join(parts)
            return " ".join(text.split())
    except Exception as e:
        print(f"[RESULT] parse error: {e}")
    return "Result table found but parsing failed"

def get_all_error_messages(page):
    """পৃষ্ঠার সমস্ত দৃশ্যমান ত্রুটি বার্তা পান"""
    messages = []
    for sel in ['.ui.negative.message', '.ui.red.message',
                '.error.message', '.ui.negative', '.ui.message']:
        try:
            els = page.locator(sel)
            for i in range(els.count()):
                el = els.nth(i)
                if el.is_visible():
                    txt = (el.text_content() or "").strip()
                    if txt:
                        messages.append(txt)
        except Exception:
            continue
    return list(dict.fromkeys(messages))

def classify_error(messages):
    """ত্রুটির ধরন শ্রেণীবদ্ধ করুন: 'invalid' অথবা 'captcha'"""
    combined = " ".join(messages)
    for kw in INVALID_NID_KEYWORDS:
        if kw in combined:
            return ("invalid", combined)
    for kw in CAPTCHA_ERROR_KEYWORDS:
        if kw in combined:
            return ("captcha", combined)
    return (None, combined)

# ============================================================
# পৃষ্ঠা রিসেট
# ============================================================
def reset_page(page):
    """জোরপূর্বক সম্পূর্ণ সতেজ পৃষ্ঠা লোড করুন"""
    print("[RESET] hard reloading...")
    try:
        page.goto(TARGET_URL, wait_until="load", timeout=20000)
    except Exception as e:
        print(f"[RESET] goto failed: {e}, retrying...")
        page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=20000)
    try:
        page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass
    try:
        page.wait_for_selector(SELECTORS["nid_input"], timeout=10000)
        page.wait_for_selector(SELECTORS["captcha_image"], timeout=10000)
    except Exception as e:
        print(f"[RESET] form not ready: {e}")
    wait_for_captcha_loaded(page)
    # ইংরেজি পৃষ্ঠায় স্যুইচ করুন
    try:
        page.click('text=English', timeout=2500)
        page.wait_for_timeout(700)
        wait_for_captcha_loaded(page)
    except Exception:
        pass
    page.wait_for_timeout(300)
    print("[RESET] done")

def clear_and_fill_form(page, nid, day, month, year):
    """ফর্ম ক্ষেত্রগুলি সাফ করুন এবং পূরণ করুন"""
    try:
        for sel in [SELECTORS["nid_input"], SELECTORS["day_input"],
                    SELECTORS["month_input"], SELECTORS["year_input"],
                    SELECTORS["captcha_input"]]:
            try:
                page.fill(sel, "")
            except Exception:
                pass
        page.fill(SELECTORS["nid_input"], str(nid))
        page.fill(SELECTORS["day_input"], str(day).zfill(2))
        page.fill(SELECTORS["month_input"], str(month).zfill(2))
        page.fill(SELECTORS["year_input"], str(year))
        # মান যাচাই করুন
        v_nid = page.input_value(SELECTORS["nid_input"])
        v_day = page.input_value(SELECTORS["day_input"])
        v_month = page.input_value(SELECTORS["month_input"])
        v_year = page.input_value(SELECTORS["year_input"])
        print(f"[FORM] values: {v_nid}/{v_day}/{v_month}/{v_year}")
        return v_nid.strip() == str(nid).strip()
    except Exception as e:
        print(f"[FORM] fill error: {e}")
        return False

def click_submit(page):
    """সাবমিট বোতামে ক্লিক করুন (একাধিক ফলব্যাক)"""
    try:
        page.locator(SELECTORS["submit_button"]).first.wait_for(state="visible", timeout=5000)
    except Exception as e:
        print(f"[SUBMIT] button not visible: {e}")
        return False
    try:
        page.click(SELECTORS["submit_button"], timeout=5000)
        return True
    except Exception as e:
        print(f"[SUBMIT] normal click failed: {e}")
    try:
        page.dispatch_event(SELECTORS["submit_button"], "click")
        return True
    except Exception as e:
        print(f"[SUBMIT] dispatch click failed: {e}")
    try:
        page.evaluate(f"""() => {{
            const el = document.querySelector('{SELECTORS["submit_button"]}');
            if (el) el.click();
        }}""")
        return True
    except Exception as e:
        print(f"[SUBMIT] js click failed: {e}")
    return False

def wait_for_outcome(page, timeout_ms=8000):
    """ফলাফল সারণী অথবা ত্রুটি বার্তার জন্য অপেক্ষা করুন"""
    start = time.time()
    while (time.time() - start) * 1000 < timeout_ms:
        if page_has_result(page):
            return ("result", None)
        msgs = get_all_error_messages(page)
        if msgs:
            return ("error", msgs)
        page.wait_for_timeout(300)
    return ("timeout", None)

# ============================================================
# একক NID প্রসেসিং
# ============================================================
def process_single_nid(page, nid, day, month, year):
    """একক NID প্রক্রিয়া করুন, নিশ্চিত ফলাফল না আসা পর্যন্ত পুনঃপ্রচেষ্টা করুন"""
    reset_page(page)
    if not clear_and_fill_form(page, nid, day, month, year):
        reset_page(page)
        if not clear_and_fill_form(page, nid, day, month, year):
            return f"FORM_ERROR | could not set field values"
    
    for attempt in range(MAX_CAPTCHA_RETRIES):
        captcha_text = get_captcha_text(page)
        if not captcha_text or len(captcha_text) < 3:
            print(f"[NID {nid}] attempt {attempt+1}: empty OCR")
            refresh_captcha(page)
            continue
        try:
            page.fill(SELECTORS["captcha_input"], captcha_text)
        except Exception as e:
            print(f"[NID {nid}] captcha fill error: {e}")
            refresh_captcha(page)
            continue
        if not click_submit(page):
            refresh_captcha(page)
            continue
        
        outcome, data = wait_for_outcome(page, timeout_ms=8000)
        
        if outcome == "result":
            formatted = format_result_table(page)
            print(f"[NID {nid}] VALID: {formatted[:200]}")
            return f"VALID | {formatted}"
        
        if outcome == "error":
            kind, text = classify_error(data)
            if kind == "invalid":
                print(f"[NID {nid}] INVALID: {text[:120]}")
                return f"INVALID | {text}"
            if kind == "captcha":
                print(f"[NID {nid}] attempt {attempt+1}: captcha wrong")
                refresh_captcha(page)
                continue
            if attempt < MAX_CAPTCHA_RETRIES - 1:
                refresh_captcha(page)
                continue
            return f"ERROR | {text}"
        
        print(f"[NID {nid}] attempt {attempt+1}: timeout, refreshing")
        refresh_captcha(page)
    
    return "FAILED | exhausted retries without definitive answer"

# ============================================================
# Playwright ওয়ার্কার
# ============================================================
def run_playwright_task(data_list, result_queue):
    """পটভূমি থ্রেডে Playwright চালান"""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled",
                      "--no-sandbox", "--disable-dev-shm-usage"]
            )
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1366, "height": 768},
            )
            page = context.new_page()
            results = []
            for i, item in enumerate(data_list, 1):
                print(f"\n{'='*60}\n[{i}/{len(data_list)}] NID: {item['nid']}\n{'='*60}")
                try:
                    result = process_single_nid(
                        page, item['nid'], item['day'], item['month'], item['year']
                    )
                    if " | " in result:
                        status, msg = result.split(" | ", 1)
                    else:
                        status, msg = "ERROR", result
                    results.append({
                        'nid': item['nid'],
                        'status': status.strip(),
                        'message': msg.strip()
                    })
                    print(f"[DONE] {item['nid']}: {status} — {msg[:120]}")
                except Exception as e:
                    results.append({'nid': item['nid'], 'status': 'ERROR', 'message': str(e)})
                    print(f"[ERROR] {item['nid']}: {e}")
                page.wait_for_timeout(1000)
            browser.close()
            result_queue.put(("success", results))
    except Exception as e:
        result_queue.put(("error", str(e)))

# ============================================================
# Flask
# ============================================================
@app.route('/', methods=['GET', 'POST'])
def index():
    results = None
    error = None
    mode = request.form.get("mode", "csv")
    
    if request.method == 'POST' and mode == "manual":
        nid = request.form.get("m_nid", "").strip()
        day = request.form.get("m_day", "").strip()
        month = request.form.get("m_month", "").strip()
        year = request.form.get("m_year", "").strip()
        if not all([nid, day, month, year]):
            error = "Please fill all fields"
        else:
            data_list = [{'nid': nid, 'day': day, 'month': month, 'year': year}]
            q = queue.Queue()
            t = threading.Thread(target=run_playwright_task, args=(data_list, q))
            t.start(); t.join()
            status, payload = q.get()
            if status == "success":
                results = payload
            else:
                error = f"Playwright failed: {payload}"
    
    elif request.method == 'POST':
        if 'csv_file' not in request.files:
            error = "Please upload a CSV file"
        else:
            file = request.files['csv_file']
            if file.filename == '':
                error = "No file selected"
            elif not file.filename.lower().endswith('.csv'):
                error = "Only CSV files are supported"
            else:
                try:
                    content = file.stream.read().decode("UTF-8")
                    reader = csv.DictReader(io.StringIO(content))
                    required_cols = ['nid', 'day', 'month', 'year']
                    fieldnames = [f.strip().lower() for f in (reader.fieldnames or [])]
                    if not all(col in fieldnames for col in required_cols):
                        error = f"CSV must have columns: {', '.join(required_cols)}"
                    else:
                        data_list = []
                        for row in reader:
                            rl = {k.strip().lower(): v for k, v in row.items()}
                            nid_val = str(rl.get('nid', '')).strip()
                            if not nid_val:
                                continue
                            data_list.append({
                                'nid': nid_val,
                                'day': str(rl.get('day', '')).strip(),
                                'month': str(rl.get('month', '')).strip(),
                                'year': str(rl.get('year', '')).strip(),
                            })
                        if not data_list:
                            error = "CSV has no valid rows"
                        else:
                            q = queue.Queue()
                            t = threading.Thread(target=run_playwright_task, args=(data_list, q))
                            t.start(); t.join()
                            status, payload = q.get()
                            if status == "success":
                                results = payload
                            else:
                                error = f"Playwright failed: {payload}"
                except Exception as e:
                    error = f"Processing failed: {e}"
    
    return render_template('index.html', results=results, error=error)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)