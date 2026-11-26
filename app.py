import io
import re
import time
import requests
import pandas as pd
import streamlit as st

st.set_page_config(page_title="PC28 双口诀预测与复盘", layout="wide")

# ==========================================
# 1. 核心口诀与合判逻辑（与电脑版完全一致）
# ==========================================

def formula_1(history):
    """口诀一：前6期11位和（奇买单，偶买双）"""
    if len(history) < 6:
        return "数据不足"
    s = (
        history[-1]["A"]
        + history[-2]["C"]
        + history[-3]["A"] + history[-3]["B"] + history[-3]["C"]
        + history[-4]["A"] + history[-4]["B"]
        + history[-5]["B"] + history[-5]["C"]
        + history[-6]["A"] + history[-6]["B"]
    )
    return "单" if s % 2 == 1 else "双"


def formula_2(history):
    """口诀二：七位只下双期（13位和：偶买单，奇买双）"""
    if len(history) < 7:
        return "数据不足"
    s = (
        history[-1]["A"] + history[-1]["B"] + history[-1]["C"]
        + history[-2]["A"] + history[-2]["C"]
        + history[-3]["C"]
        + history[-4]["B"]
        + history[-5]["A"] + history[-5]["B"] + history[-5]["C"]
        + history[-6]["A"] + history[-6]["C"]
        + history[-7]["C"]
    )
    return "单" if s % 2 == 0 else "双"


def combine_predictions(p1, p2, actual_sum=None):
    """共振/分歧判定，已开奖分歧标注命中方（6期/七期）"""
    valid = ("单", "双")
    if p1 in valid and p2 in valid:
        if p1 == p2:
            return f"共振:{p1}"
        if actual_sum is not None:
            actual_parity = "单" if actual_sum % 2 == 1 else "双"
            if p1 == actual_parity:
                return "分歧（6期）"
            if p2 == actual_parity:
                return "分歧（七期）"
        return "分歧"
    return "-"


# ==========================================
# 2. 日期与时间解析工具
# ==========================================

def normalize_date_str(text):
    if not text:
        return ""
    m = re.search(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", str(text))
    if not m:
        return ""
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    return f"{y:04d}-{mo:02d}-{d:02d}"


def extract_time_parts(text):
    if not text:
        return "", None
    m = re.search(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", str(text))
    if not m:
        return "", None
    h, mi = int(m.group(1)), int(m.group(2))
    sec = int(m.group(3)) if m.group(3) is not None else 0
    if 0 <= h <= 23 and 0 <= mi <= 59:
        return f"{h:02d}:{mi:02d}:{sec:02d}", h * 60 + mi
    return "", None


def parse_user_time_input(text, is_end=False):
    s = str(text).strip()
    if not s:
        return None
    s = s.replace("：", ":").replace("点", ":").rstrip(":")
    if re.fullmatch(r"\d{1,2}", s):
        h = int(s)
        if h == 24 and is_end:
            return 23 * 60 + 59
        if 0 <= h <= 23:
            return h * 60
        raise ValueError(f"时间小时数超出范围：{text}")
    m = re.fullmatch(r"(\d{1,2}):(\d{1,2})(?::\d{1,2})?", s)
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        if h == 24 and mi == 0 and is_end:
            return 23 * 60 + 59
        if 0 <= h <= 23 and 0 <= mi <= 59:
            return h * 60 + mi
    raise ValueError(f"时间格式不正确：{text}（请输入如 6 或 06:30）")


# ==========================================
# 3. API 解析与文件导入
# ==========================================

DEFAULT_API = "https://pc28.help/api/kj.json?nbr=100"

COLUMNS = [
    "期号",
    "开奖时间",
    "七位只下双期",
    "前6期11位和",
    "双口诀合判",
    "开奖结果",
    "合判结果",
]


def fetch_api_records(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    }
    resp = requests.get(url, headers=headers, timeout=12)
    resp.raise_for_status()
    raw_json = resp.json()

    countdown = ""
    if isinstance(raw_json, dict):
        countdown = str(raw_json.get("countdown", "")).strip()
        items = raw_json.get("data", [])
    elif isinstance(raw_json, list):
        items = raw_json
    else:
        raise ValueError("接口返回内容不是合法的 JSON 格式。")

    records = []
    for row in items:
        if not isinstance(row, dict):
            continue
        period_val = None
        for k in ("nbr", "qihao", "expect", "issue", "period", "qh", "id", "no"):
            if row.get(k) not in (None, ""):
                period_val = row[k]
                break

        raw_date = str(row.get("date", "")).strip()
        raw_time = str(row.get("time") or row.get("opentime") or "").strip()
        date_norm = normalize_date_str(raw_date) or normalize_date_str(raw_time)
        time_norm, time_mins = extract_time_parts(raw_time)
        display_time = f"{date_norm} {time_norm}".strip() if (date_norm or time_norm) else f"{raw_date} {raw_time}".strip()

        nums = []
        for k in ("number", "opennum", "opencode", "code", "numbers", "kjnum"):
            v = row.get(k)
            if v is not None and v != "":
                nums = [int(x) for x in re.findall(r"\d+", str(v))]
                if len(nums) >= 3:
                    break

        p_digits = re.sub(r"\D", "", str(period_val)) if period_val is not None else ""
        if p_digits and len(nums) >= 3:
            a, b, c = nums[0], nums[1], nums[2]
            records.append({
                "period": int(p_digits),
                "time": display_time,
                "date_norm": date_norm,
                "time_mins": time_mins,
                "A": a,
                "B": b,
                "C": c,
                "S": a + b + c,
                "code": f"{a}+{b}+{c}",
            })

    unique_map = {r["period"]: r for r in records}
    return [unique_map[p] for p in sorted(unique_map.keys())], countdown


def load_uploaded_file(uploaded_file):
    raw_bytes = uploaded_file.getvalue()
    filename = uploaded_file.name.lower()
    df = None

    if filename.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(raw_bytes))
    else:
        for engine in ("openpyxl", "xlrd"):
            try:
                df = pd.read_excel(io.BytesIO(raw_bytes), engine=engine)
                break
            except Exception:
                pass

    if df is None:
        html = raw_bytes.decode("utf-8", errors="ignore")
        tables = re.findall(r"<table.*?>.*?</table>", html, re.DOTALL | re.IGNORECASE)
        parsed_dfs = []
        for tbl in tables:
            rows = re.findall(r"<tr.*?>(.*?)</tr>", tbl, re.DOTALL | re.IGNORECASE)
            matrix = []
            for r in rows:
                cells = re.findall(r"<t[dh].*?>(.*?)</t[dh]>", r, re.DOTALL | re.IGNORECASE)
                clean_cells = [re.sub(r"<.*?>", "", c).strip() for c in cells]
                if clean_cells:
                    matrix.append(clean_cells)
            if len(matrix) >= 2:
                parsed_dfs.append(pd.DataFrame(matrix[1:], columns=matrix[0]))
        if not parsed_dfs:
            raise ValueError("无法识别该表格格式，请确认包含期号和开奖号码列。")
        df = max(parsed_dfs, key=len)

    cols = [str(c).strip() for c in df.columns]
    df.columns = cols
    col_period = next((c for c in cols if "期" in c), None)
    col_code = next((c for c in cols if "号" in c and c != col_period), None)
    col_date = next((c for c in cols if "日期" in c), None)
    col_time = next((c for c in cols if "时间" in c), None)

    if not col_period or not col_code:
        raise ValueError(f"未找到【期号】或【开奖号码】列，当前表头：{cols}")

    records = []
    for _, row in df.iterrows():
        p_raw = re.sub(r"\D", "", str(row[col_period]))
        nums = [int(x) for x in re.findall(r"\d+", str(row[col_code]))]
        if not p_raw or len(nums) < 3:
            continue

        raw_date = str(row[col_date]).strip() if col_date else ""
        raw_time = str(row[col_time]).strip() if col_time else ""
        date_norm = normalize_date_str(raw_date) or normalize_date_str(raw_time)
        time_norm, time_mins = extract_time_parts(raw_time)
        if time_mins is None and raw_date and not col_time:
            time_norm, time_mins = extract_time_parts(raw_date)

        display_time = f"{date_norm} {time_norm}".strip() or f"{raw_date} {raw_time}".strip()
        a, b, c = nums[0], nums[1], nums[2]
        records.append({
            "period": int(p_raw),
            "time": display_time,
            "date_norm": date_norm,
            "time_mins": time_mins,
            "A": a,
            "B": b,
            "C": c,
            "S": a + b + c,
            "code": f"{a}+{b}+{c}",
        })

    unique_map = {r["period"]: r for r in records}
    return [unique_map[p] for p in sorted(unique_map.keys())]


# ==========================================
# 4. 推演、筛选与表格高亮
# ==========================================

def format_result(code, s):
    size = "大" if s >= 14 else "小"
    parity = "单" if s % 2 == 1 else "双"
    return f"{code}={s}（{size}{parity}）"


def check_hit(pred, actual_sum):
    if pred not in ("共振:单", "共振:双"):
        return "-"
    target = pred.replace("共振:", "")
    actual_parity = "单" if actual_sum % 2 == 1 else "双"
    return "命中" if target == actual_parity else "未中"


def run_backtest(records):
    results = []
    for i in range(len(records)):
        hist = records[:i]
        cur = records[i]
        p1 = formula_1(hist)
        p2 = formula_2(hist)
        comb = combine_predictions(p1, p2, actual_sum=cur["S"])

        results.append({
            "期号": cur["period"],
            "开奖时间": cur["time"],
            "七位只下双期": p2,
            "前6期11位和": p1,
            "双口诀合判": comb,
            "开奖结果": format_result(cur["code"], cur["S"]),
            "合判结果": check_hit(comb, cur["S"]),
            "_date": cur.get("date_norm", ""),
            "_mins": cur.get("time_mins", None),
        })
    results.reverse()
    return results


def filter_rows(rows, period_mode="全部", date_str="全部日期", start_mins=None, end_mins=None):
    target_date = ""
    if date_str and date_str not in ("全部", "全部日期"):
        target_date = normalize_date_str(date_str) or date_str.strip()

    filtered = []
    for r in rows:
        if period_mode == "只看双期" and r["期号"] % 2 != 0:
            continue
        if period_mode == "只看单期" and r["期号"] % 2 != 1:
            continue
        if target_date and r["_date"] != target_date and target_date not in r["开奖时间"]:
            continue

        if start_mins is not None or end_mins is not None:
            m = r["_mins"]
            if m is None:
                continue
            if start_mins is not None and end_mins is not None:
                if start_mins <= end_mins:
                    if not (start_mins <= m <= end_mins):
                        continue
                else:
                    if not (m >= start_mins or m <= end_mins):
                        continue
            elif start_mins is not None and m < start_mins:
                continue
            elif end_mins is not None and m > end_mins:
                continue

        filtered.append(r)
    return filtered


def style_table(df):
    def highlight_row(row):
        if row["开奖结果"] == "等待开奖":
            return ["background-color: #e8f3ff; color: #0b5394; font-weight: bold"] * len(row)
        if row["合判结果"] == "命中":
            return ["background-color: #eefaf0"] * len(row)
        if row["合判结果"] == "未中":
            return ["background-color: #fff1f0"] * len(row)
        return [""] * len(row)

    return df.style.apply(highlight_row, axis=1)


# ==========================================
# 5. 手机自适应网页界面
# ==========================================

st.title("PC28 双口诀预测与复盘")
tab_live, tab_review = st.tabs(["实时 API 预测", "历史表格复盘"])


def render_live_block(api_url, period_mode, date_val, start_str, end_str):
    try:
        s_mins = parse_user_time_input(start_str, is_end=False)
        e_mins = parse_user_time_input(end_str, is_end=True)
    except ValueError as err:
        st.warning(str(err))
        return

    try:
        records, countdown = fetch_api_records(api_url)
    except Exception as e:
        st.error(f"拉取接口失败：{e}")
        return

    if not records:
        st.warning("接口未返回有效开奖数据。")
        return

    all_rows = run_backtest(records)
    avail_dates = sorted({r["_date"] for r in all_rows if r["_date"]}, reverse=True)
    st.session_state["live_dates"] = ["全部日期"] + avail_dates

    next_period = records[-1]["period"] + 1
    next_p1 = formula_1(records)
    next_p2 = formula_2(records)
    next_comb = combine_predictions(next_p1, next_p2)
    next_tag = "双期" if next_period % 2 == 0 else "单期"

    # 手机端置顶卡片：一眼看清下一期预测
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(f"下期 ({next_tag})", f"{next_period}", f"倒计时 {countdown or '-'}")
    c2.metric("七位只下双期", next_p2)
    c3.metric("前6期11位和", next_p1)
    c4.metric("双口诀合判", next_comb)

    shown_rows = filter_rows(all_rows, period_mode, date_val, s_mins, e_mins)
    display_rows = [{c: r[c] for c in COLUMNS} for r in shown_rows]

    no_dt_filter = (date_val in ("", "全部", "全部日期")) and s_mins is None and e_mins is None
    match_next = (
        period_mode == "全部"
        or (period_mode == "只看双期" and next_period % 2 == 0)
        or (period_mode == "只看单期" and next_period % 2 == 1)
    )
    if no_dt_filter and match_next:
        display_rows.insert(0, {
            "期号": next_period,
            "开奖时间": f"倒计时 {countdown}" if countdown else "待开奖",
            "七位只下双期": next_p2,
            "前6期11位和": next_p1,
            "双口诀合判": next_comb,
            "开奖结果": "等待开奖",
            "合判结果": "-",
        })

    st.caption(f"最后刷新：{time.strftime('%H:%M:%S')} | 当前显示 {len(shown_rows)} 期已开奖记录")
    if display_rows:
        df_show = pd.DataFrame(display_rows)
        st.dataframe(style_table(df_show), use_container_width=True, hide_index=True, height=560)
    else:
        st.info("当前筛选条件下暂无记录。")


with tab_live:
    col_a, col_b = st.columns([3, 1])
    api_url = col_a.text_input("开奖 API 地址", value=DEFAULT_API)
    auto_refresh = col_b.toggle("每15秒自动刷新", value=True)

    f1, f2, f3, f4 = st.columns([2, 1.5, 1, 1])
    live_mode = f1.radio("期号筛选", ["全部", "只看双期", "只看单期"], horizontal=True, key="live_mode")
    live_date_opts = st.session_state.get("live_dates", ["全部日期"])
    live_date = f2.selectbox("日期", live_date_opts, key="live_date")
    live_start = f3.text_input("开始时间", placeholder="如 6 或 06:30", key="live_start")
    live_end = f4.text_input("结束时间", placeholder="如 10 或 10:00", key="live_end")

    if auto_refresh:
        @st.fragment(run_every=15)
        def _auto_live():
            render_live_block(api_url, live_mode, live_date, live_start, live_end)
        _auto_live()
    else:
        if st.button("手动刷新一次"):
            st.rerun()
        render_live_block(api_url, live_mode, live_date, live_start, live_end)


with tab_review:
    uploaded = st.file_uploader("导入历史开奖表格（支持 .xlsx / .xls / .csv 及网页导出表）", type=["xlsx", "xls", "csv"])
    if uploaded is not None:
        try:
            records = load_uploaded_file(uploaded)
            all_rev = run_backtest(records)
            avail_dates = ["全部日期"] + sorted({r["_date"] for r in all_rev if r["_date"]}, reverse=True)

            r1, r2, r3, r4 = st.columns([2, 1.5, 1, 1])
            rev_mode = r1.radio("期号筛选", ["全部", "只看双期", "只看单期"], horizontal=True, key="rev_mode")
            rev_date = r2.selectbox("日期", avail_dates, key="rev_date")
            rev_start = r3.text_input("开始时间", placeholder="如 19", key="rev_start")
            rev_end = r4.text_input("结束时间", placeholder="如 3", key="rev_end")

            s_mins = parse_user_time_input(rev_start, is_end=False)
            e_mins = parse_user_time_input(rev_end, is_end=True)

            filtered_rev = filter_rows(all_rev, rev_mode, rev_date, s_mins, e_mins)
            st.caption(f"原始总期数：{len(all_rev)} 期 | 筛选后：{len(filtered_rev)} 期（口诀均按完整连续历史计算）")

            if filtered_rev:
                export_df = pd.DataFrame([{c: r[c] for c in COLUMNS} for r in filtered_rev])
                buf = io.BytesIO()
                export_df.to_excel(buf, index=False)
                st.download_button(
                    label="下载当前筛选结果 (.xlsx)",
                    data=buf.getvalue(),
                    file_name=f"PC28复盘_{rev_mode}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
                st.dataframe(style_table(export_df.head(2000)), use_container_width=True, hide_index=True, height=560)
            else:
                st.info("当前筛选条件下暂无记录。")
        except Exception as e:
            st.error(f"导入或筛选出错：{e}")