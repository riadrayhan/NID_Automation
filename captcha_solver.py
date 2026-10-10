# import csv
# import tkinter as tk
# import webbrowser
# from datetime import date
# from pathlib import Path
# from tkinter import filedialog, messagebox, ttk


# PORTAL_URL = "https://services.nidw.gov.bd/nid-pub/card-status"
# CSV_FIELDS = ("nid", "day", "month", "year")


# class NIDListApp:
#     def __init__(self, root: tk.Tk) -> None:
#         self.root = root
#         self.root.title("NID Card Status - Manual Assistant")
#         self.root.geometry("760x500")
#         self.records: list[dict[str, str]] = []
#         self.selected_record: dict[str, str] | None = None

#         self._build_ui()

#     def _build_ui(self) -> None:
#         container = ttk.Frame(self.root, padding=16)
#         container.pack(fill=tk.BOTH, expand=True)

#         ttk.Label(
#             container,
#             text="Load your CSV, select one record, then complete verification yourself.",
#             wraplength=700,
#         ).pack(anchor=tk.W, pady=(0, 10))

#         actions = ttk.Frame(container)
#         actions.pack(fill=tk.X, pady=(0, 10))
#         ttk.Button(actions, text="Import CSV", command=self.import_csv).pack(side=tk.LEFT)
#         ttk.Button(
#             actions, text="Open official status page", command=self.open_portal
#         ).pack(side=tk.LEFT, padx=(8, 0))
#         ttk.Button(actions, text="Clear list", command=self.clear_list).pack(side=tk.RIGHT)

#         table_frame = ttk.Frame(container)
#         table_frame.pack(fill=tk.BOTH, expand=True)
#         self.table = ttk.Treeview(
#             table_frame,
#             columns=("number", "nid", "dob"),
#             show="headings",
#             selectmode="browse",
#         )
#         self.table.heading("number", text="#")
#         self.table.heading("nid", text="NID (masked)")
#         self.table.heading("dob", text="Date of birth")
#         self.table.column("number", width=55, anchor=tk.CENTER, stretch=False)
#         self.table.column("nid", width=260, anchor=tk.W)
#         self.table.column("dob", width=180, anchor=tk.W)
#         scrollbar = ttk.Scrollbar(
#             table_frame, orient=tk.VERTICAL, command=self.table.yview
#         )
#         self.table.configure(yscrollcommand=scrollbar.set)
#         self.table.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
#         scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
#         self.table.bind("<<TreeviewSelect>>", self._on_select)

#         self.selection_label = ttk.Label(
#             container, text="Select a row to enable manual copy actions."
#         )
#         self.selection_label.pack(anchor=tk.W, pady=(12, 6))

#         copy_actions = ttk.Frame(container)
#         copy_actions.pack(fill=tk.X)
#         self.copy_nid_button = ttk.Button(
#             copy_actions,
#             text="Copy selected NID",
#             command=self.copy_nid,
#             state=tk.DISABLED,
#         )
#         self.copy_nid_button.pack(side=tk.LEFT)
#         self.copy_dob_button = ttk.Button(
#             copy_actions,
#             text="Copy selected date of birth",
#             command=self.copy_dob,
#             state=tk.DISABLED,
#         )
#         self.copy_dob_button.pack(side=tk.LEFT, padx=(8, 0))

#         self.status_label = ttk.Label(
#             container,
#             text="Data stays in this window only; it is not uploaded or saved by this app.",
#             wraplength=700,
#         )
#         self.status_label.pack(anchor=tk.W, pady=(12, 0))

#     def import_csv(self) -> None:
#         selected_path = filedialog.askopenfilename(
#             title="Select NID list CSV",
#             filetypes=(("CSV files", "*.csv"), ("All files", "*.*")),
#         )
#         if not selected_path:
#             return

#         try:
#             records = self._read_csv(Path(selected_path))
#         except (OSError, UnicodeError, csv.Error, ValueError) as error:
#             messagebox.showerror("Could not import CSV", str(error), parent=self.root)
#             return

#         self.records = records
#         self._refresh_table()
#         self.status_label.config(
#             text=f"Loaded {len(records)} record(s). Data is held in memory for this session."
#         )

#     @staticmethod
#     def _read_csv(path: Path) -> list[dict[str, str]]:
#         records: list[dict[str, str]] = []
#         with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
#             reader = csv.DictReader(csv_file)
#             if reader.fieldnames is None:
#                 raise ValueError("The CSV is empty or has no header row.")

#             header_map = {
#                 header.strip().lower(): header for header in reader.fieldnames if header
#             }
#             missing_fields = [field for field in CSV_FIELDS if field not in header_map]
#             if missing_fields:
#                 raise ValueError(
#                     "CSV header must include: nid, day, month, year."
#                 )

#             for row_number, row in enumerate(reader, start=2):
#                 if None in row:
#                     raise ValueError(f"Row {row_number} has more columns than the header.")

#                 values = {
#                     field: (row.get(header_map[field]) or "").strip()
#                     for field in CSV_FIELDS
#                 }
#                 if not all(values.values()):
#                     raise ValueError(
#                         f"Row {row_number} must have NID, day, month, and year."
#                     )
#                 if not values["nid"].isascii() or not values["nid"].isdigit():
#                     raise ValueError(f"Row {row_number} has a non-numeric NID.")
#                 if not all(values[field].isascii() and values[field].isdigit()
#                            for field in ("day", "month", "year")):
#                     raise ValueError(
#                         f"Row {row_number} must use numeric day, month, and year."
#                     )

#                 try:
#                     date(
#                         int(values["year"]),
#                         int(values["month"]),
#                         int(values["day"]),
#                     )
#                 except ValueError as error:
#                     raise ValueError(
#                         f"Row {row_number} has an invalid date of birth."
#                     ) from error
#                 records.append(values)

#         if not records:
#             raise ValueError("The CSV has a header but no data rows.")
#         return records

#     def _refresh_table(self) -> None:
#         self.table.delete(*self.table.get_children())
#         self.selected_record = None
#         self._set_copy_buttons(tk.DISABLED)
#         self.selection_label.config(text="Select a row to enable manual copy actions.")
#         for index, record in enumerate(self.records, start=1):
#             self.table.insert(
#                 "",
#                 tk.END,
#                 iid=str(index - 1),
#                 values=(
#                     index,
#                     self._mask_nid(record["nid"]),
#                     f'{record["day"]}/{record["month"]}/{record["year"]}',
#                 ),
#             )

#     @staticmethod
#     def _mask_nid(nid: str) -> str:
#         if len(nid) <= 4:
#             return "*" * len(nid)
#         return f'{"*" * (len(nid) - 4)}{nid[-4:]}'

#     def _on_select(self, _event: tk.Event) -> None:
#         selected = self.table.selection()
#         if not selected:
#             self.selected_record = None
#             self._set_copy_buttons(tk.DISABLED)
#             return

#         self.selected_record = self.records[int(selected[0])]
#         record = self.selected_record
#         self.selection_label.config(
#             text=(
#                 f'NID: {self._mask_nid(record["nid"])}  |  '
#                 f'Date of birth: {record["day"]}/{record["month"]}/{record["year"]}'
#             )
#         )
#         self._set_copy_buttons(tk.NORMAL)

#     def _set_copy_buttons(self, state: str) -> None:
#         self.copy_nid_button.config(state=state)
#         self.copy_dob_button.config(state=state)

#     def copy_nid(self) -> None:
#         if self.selected_record is not None:
#             self._copy_to_clipboard(self.selected_record["nid"], "NID")

#     def copy_dob(self) -> None:
#         if self.selected_record is not None:
#             record = self.selected_record
#             dob = f'{record["day"]}/{record["month"]}/{record["year"]}'
#             self._copy_to_clipboard(dob, "date of birth")

#     def _copy_to_clipboard(self, value: str, label: str) -> None:
#         self.root.clipboard_clear()
#         self.root.clipboard_append(value)
#         self.root.update()
#         self.status_label.config(
#             text=f"Selected {label} copied to the system clipboard. Handle it securely."
#         )

#     def open_portal(self) -> None:
#         if not webbrowser.open(PORTAL_URL):
#             messagebox.showerror(
#                 "Could not open page",
#                 "Your default browser could not be opened. Please visit the official page manually.",
#                 parent=self.root,
#             )

#     def clear_list(self) -> None:
#         self.records.clear()
#         self._refresh_table()
#         self.status_label.config(text="The in-memory list has been cleared.")


# def main() -> None:
#     root = tk.Tk()
#     NIDListApp(root)
#     root.mainloop()


# if __name__ == "__main__":
#     main()


"""
CAPTCHA 解决模块
- 简单文本 CAPTCHA: 用 ddddocr（免费，本地）
- reCAPTCHA: 用 2Captcha（付费 API）
"""

import io
import cv2
import numpy as np
from collections import Counter
import ddddocr

# 全局初始化 ddddocr（只初始化一次，避免重复加载模型）
_ocr = ddddocr.DdddOcr(show_ad=False)


# ============================================================
# 文本 CAPTCHA 识别（ddddocr）
# ============================================================

def _preprocess(image_bytes: bytes, block_size: int = 11) -> bytes:
    """图像预处理：灰度 -> 自适应二值化 -> 去噪"""
    img_array = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
    if img is None:
        return image_bytes

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    binary = cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        block_size, 2
    )
    denoised = cv2.medianBlur(binary, 3)
    _, encoded = cv2.imencode('.png', denoised)
    return encoded.tobytes()


def solve_text_captcha(image_bytes: bytes, expected_length: int = 0) -> str:
    """
    识别简单文本 CAPTCHA，多次尝试 + 投票
    expected_length: 若已知 CAPTCHA 长度（如 5），传入可提高准确率；0 表示未知
    """
    candidates = []

    # 原图
    try:
        r = _ocr.classification(image_bytes)
        if r:
            candidates.append(r.strip())
    except Exception as e:
        print(f"[CAPTCHA] 原图识别失败: {e}")

    # 不同预处理参数
    for bs in [9, 11, 13]:
        try:
            processed = _preprocess(image_bytes, bs)
            r = _ocr.classification(processed)
            if r:
                candidates.append(r.strip())
        except Exception as e:
            print(f"[CAPTCHA] 预处理 {bs} 识别失败: {e}")

    if not candidates:
        return ""

    # 如果知道长度，优先选长度匹配的
    if expected_length > 0:
        valid = [c for c in candidates if len(c) == expected_length]
        if valid:
            return Counter(valid).most_common(1)[0][0]

    # 否则投票选最多的
    return Counter(candidates).most_common(1)[0][0]


def solve_text_captcha_from_element(page, selector: str, expected_length: int = 0) -> str:
    """从 Playwright 页面元素截图识别"""
    element = page.locator(selector).first
    if element.count() == 0:
        return ""
    img_bytes = element.screenshot()
    return solve_text_captcha(img_bytes, expected_length)


def solve_text_captcha_from_url(image_url: str, expected_length: int = 0) -> str:
    """从 URL 下载图片识别"""
    import requests
    try:
        resp = requests.get(image_url, timeout=10)
        if resp.status_code == 200:
            return solve_text_captcha(resp.content, expected_length)
    except Exception as e:
        print(f"[CAPTCHA] 下载失败: {e}")
    return ""


# ============================================================
# reCAPTCHA 检测 + 2Captcha 解决
# ============================================================

def detect_recaptcha(page):
    """检测页面上的 reCAPTCHA 类型和参数"""
    # v3: 通过 api.js?render= 加载
    v3_sitekey = page.evaluate("""
        () => {
            const scripts = document.querySelectorAll('script[src*="recaptcha"]');
            for (const s of scripts) {
                const m = (s.src || '').match(/render=([^&]+)/);
                if (m) return m[1];
            }
            return null;
        }
    """)
    if v3_sitekey:
        action = page.evaluate("""
            () => {
                const scripts = document.querySelectorAll('script');
                for (const s of scripts) {
                    const text = s.textContent || '';
                    const m = text.match(/action\\s*:\\s*['"]([^'"]+)['"]/);
                    if (m) return m[1];
                }
                return 'submit';
            }
        """)
        return {"type": "v3", "sitekey": v3_sitekey, "action": action or "submit"}

    # v2: 可见 .g-recaptcha widget
    v2_el = page.locator(".g-recaptcha").first
    if v2_el.count() > 0:
        sitekey = v2_el.get_attribute("data-sitekey")
        callback = v2_el.get_attribute("data-callback")
        return {"type": "v2", "sitekey": sitekey, "callback": callback}

    return None


def solve_recaptcha(captcha_info, page_url, api_key):
    """调用 2Captcha 解决 reCAPTCHA"""
    from twocaptcha import TwoCaptcha
    solver = TwoCaptcha(api_key)
    try:
        if captcha_info["type"] == "v3":
            result = solver.recaptcha(
                sitekey=captcha_info["sitekey"],
                url=page_url,
                version='v3',
                action=captcha_info["action"],
                min_score=0.3
            )
        else:
            result = solver.recaptcha(
                sitekey=captcha_info["sitekey"],
                url=page_url
            )
        return result['code']
    except Exception as e:
        print(f"[reCAPTCHA] 2Captcha 失败: {e}")
        return None


def inject_recaptcha_token(page, captcha_info, token):
    """将 reCAPTCHA token 注入页面"""
    page.evaluate(f"""
        const el = document.getElementById('g-recaptcha-response');
        if (el) {{ el.value = "{token}"; el.style.display = 'block'; }}
    """)
    if captcha_info.get("callback"):
        cb = captcha_info["callback"]
        page.evaluate(f"""
            if (typeof window.{cb} === 'function') {{
                window.{cb}("{token}");
            }}
        """)
    # 兜底：遍历 ___grecaptcha_cfg
    page.evaluate(f"""
        () => {{
            if (typeof ___grecaptcha_cfg !== 'undefined') {{
                const clients = ___grecaptcha_cfg.clients;
                for (const key in clients) {{
                    const c = clients[key];
                    if (c && c.callback && typeof c.callback === 'function') {{
                        try {{ c.callback("{token}"); }} catch(e) {{}}
                    }}
                }}
            }}
        }}
    """)