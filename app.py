"""CSV Doctor's Streamlit interface. Run from the project root."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.analyzer import IQR_WARNING, build_report, finite_values, numeric_columns, report_json
from src.cleaner import clean_data, export_csv
from src.loader import DataLoadError, list_sheets, load_data

ROOT = Path(__file__).resolve().parent
ACCENT = "#52E5BE"
MUTED = "#98A7BD"
STATUS_LABELS = {"applicable": "已检测", "insufficient_samples": "有限样本少于 4 个",
                 "constant": "取值单一，跳过", "zero_iqr": "IQR 为 0，跳过",
                 "nonfinite_bounds": "数值范围过大，跳过"}

st.set_page_config(page_title="CSV Doctor · 数据体检助手", page_icon="🩺", layout="wide")
st.html("""
<style>
:root {color-scheme: dark;}
body {font-family: Inter, "Segoe UI", "Microsoft YaHei", "PingFang SC", sans-serif;}
.doctor-header {display:flex;align-items:center;justify-content:space-between;gap:24px;
  padding:8px 0 25px;border-bottom:1px solid #26354b;margin-bottom:30px;}
.doctor-brand {display:flex;align-items:center;gap:15px;}
.doctor-logo {display:grid;place-items:center;width:46px;height:46px;border-radius:14px;
  background:#52e5be18;border:1px solid #52e5be55;color:#52E5BE;font-size:28px;font-weight:500;}
.doctor-title {font-size:26px;letter-spacing:-.8px;font-weight:750;color:#F7FAFF;}
.doctor-subtitle {color:#98A7BD;font-size:13px;margin-top:4px;}
.doctor-badge {border:1px solid #30445c;border-radius:30px;padding:5px 12px;font-size:12px;color:#98A7BD;}
.doctor-eyebrow {font-size:11px;font-weight:650;letter-spacing:2px;color:#52E5BE;margin-bottom:10px;}
.doctor-hero {padding:40px 34px;border:1px solid #2b4059;border-radius:22px;
  background:linear-gradient(120deg,#152b39 0%,#152238 65%,#142038 100%);margin:12px 0 26px;}
.doctor-hero h1 {font-size:clamp(26px,3vw,40px);font-weight:700;letter-spacing:-1px;
  line-height:1.4;margin:0 0 12px;color:#F7FAFF;}
.doctor-hero p {max-width:640px;color:#98A7BD;font-size:15px;line-height:1.9;margin:0;}
.doctor-step {background:#152238;border:1px solid #263952;border-radius:16px;
  padding:24px;min-height:160px;transition:border-color .15s ease;}
.doctor-step:hover {border-color:#52E5BE;}
.doctor-step b {display:block;margin:12px 0 8px;color:#F7FAFF;font-size:17px;}
.doctor-step p {color:#98A7BD;font-size:13px;line-height:1.8;}
.st-key-kpi_0, .st-key-kpi_1, .st-key-kpi_2, .st-key-kpi_3,
.st-key-completeness, .st-key-quality_summary {background:#152238;border-radius:16px;}
.st-key-kpi_0:hover, .st-key-kpi_1:hover, .st-key-kpi_2:hover, .st-key-kpi_3:hover
  {box-shadow:0 0 0 1px #52e5be66;}
.doctor-footer {border-top:1px solid #26354b;margin-top:36px;padding:18px 0;
  color:#98A7BD;font-size:12px;line-height:1.8;}
@media(max-width:700px) {.doctor-header {gap:12px;} .doctor-title {font-size:22px;}
  .doctor-hero {padding:25px 22px;} .doctor-badge {white-space:nowrap;}}
</style>
<div class="doctor-header">
 <div class="doctor-brand"><div class="doctor-logo" aria-hidden="true">✚</div>
 <div><div class="doctor-title">CSV Doctor</div><div class="doctor-subtitle">让数据质量检查更简单</div></div></div>
 <div class="doctor-badge">v1.0 · 数据体检助手</div>
</div>
""")


def chart_style(figure, *, height=290):
    figure.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
                         plot_bgcolor="rgba(0,0,0,0)", font=dict(color=MUTED, family="Microsoft YaHei, sans-serif"),
                         margin=dict(l=12, r=12, t=15, b=30), height=height,
                         colorway=[ACCENT, "#74A7FA", "#FFC77D"], showlegend=False)
    figure.update_xaxes(gridcolor="#26354B", zeroline=False)
    figure.update_yaxes(gridcolor="#26354B", zeroline=False)
    return figure


def missing_chart(result):
    if not result["rows"] or not result["columns"]:
        st.info("当前没有可分析的数据，暂不展示缺失率。")
        return
    if result["missing"]["count"] == 0:
        st.info("当前数据未检测到缺失值，各字段完整率均为 100%。")
        return
    entries = sorted(result["missing"]["by_column"], key=lambda item: item["ratio"], reverse=True)[:20]
    figure = go.Figure(go.Bar(x=[e["column"] for e in entries], y=[e["ratio"] for e in entries],
                              marker_color=ACCENT, hovertemplate="%{x}<br>缺失率 %{y:.2%}<extra></extra>"))
    chart_style(figure)
    figure.update_xaxes(title_text="字段")
    figure.update_yaxes(title_text="缺失率", tickformat=".0%",
                        range=[0, min(1.0, max(0.1, max(e["ratio"] for e in entries) * 1.15))])
    st.plotly_chart(figure, width="stretch", config={"displayModeBar": False})
    st.caption("按缺失率从高到低展示，最多显示 20 列。")


def reset_dataset():
    for key in ("dataset_id", "loaded", "report", "preview", "clean_blank", "clean_duplicate"):
        st.session_state.pop(key, None)


with st.sidebar:
    st.markdown("### ✚ 数据工作台")
    st.caption("从一份文件，开始了解你的数据。")
    uploaded = st.file_uploader("上传数据文件", type=["csv", "xlsx"],
                                help="最多 10 MiB；CSV 支持 UTF-8、UTF-8-SIG、GB18030。", key="upload")
    st.caption("将文件拖入上方区域，或点击“Browse files”选择文件。支持 CSV / XLSX，最大 10 MiB。")
    if st.button("加载虚构示例", icon=":material/science:", width="stretch", disabled=uploaded is not None):
        st.session_state["use_demo"] = True
    if st.session_state.get("use_demo") and uploaded is None:
        if st.button("关闭示例", width="stretch"):
            st.session_state["use_demo"] = False
    st.divider()
    page = st.radio("功能导航", ["数据总览", "质量分析", "数据清洗", "报告导出"], key="page")

loaded = None
source = None
if uploaded is not None:
    source = (uploaded.getvalue(), uploaded.name)
elif st.session_state.get("use_demo"):
    source = ((ROOT / "data" / "sample_dirty.csv").read_bytes(), "sample_dirty.csv")

if source is not None:
    content, filename = source
    fingerprint = hashlib.sha256(content).hexdigest()
    try:
        sheet = None
        if filename.lower().endswith(".xlsx"):
            with st.sidebar:
                sheet = st.selectbox("选择工作表", list_sheets(content, filename), key=f"sheet_{fingerprint}")
        identity = (fingerprint, filename, sheet)
        if st.session_state.get("dataset_id") != identity:
            reset_dataset()
            with st.spinner("正在读取文件并检查数据质量…"):
                new_loaded = load_data(content, filename, sheet)
                new_report = build_report(new_loaded)
            st.session_state.update(dataset_id=identity, loaded=new_loaded, report=new_report)
        loaded = st.session_state["loaded"]
    except DataLoadError as exc:
        reset_dataset()
        st.error(str(exc), icon=":material/error:")
        st.info("请修复文件后重新上传。CSV 需使用逗号分隔、第一行为唯一且非空的字段名。")
else:
    reset_dataset()

with st.sidebar:
    st.divider()
    if loaded is not None:
        st.caption("当前文件")
        st.text(loaded.filename)
        st.caption(f"{loaded.size_bytes / 1024:.1f} KiB · {len(loaded.frame):,} 行 · {len(loaded.frame.columns)} 列")
        st.caption(f"工作表：{loaded.sheet}" if loaded.sheet else f"编码：{loaded.encoding}")
    with st.expander("使用帮助", expanded=loaded is None):
        st.write("① 上传 CSV / XLSX，或加载示例。\n\n② 查看缺失、重复与统计异常。\n\n③ 手动选择清洗操作，预览后下载。")
        st.caption("数据仅在服务进程内存中处理，不主动落盘。公开部署时上传内容会传送到云端服务。")

if loaded is None:
    st.html("""<div class="doctor-hero"><div class="doctor-eyebrow">DATA QUALITY, MADE CLEAR</div>
    <h1>给数据做一次<br>清晰、透明的体检。</h1>
    <p>从缺失值到重复记录，快速发现影响分析的细节。<br>上传一份 CSV 或 Excel，即可开始；也可以先试试左侧的虚构示例。</p></div>""")
    for column, number, title, description in zip(st.columns(3), ["01", "02", "03"],
            ["看清数据全貌", "定位质量问题", "安心预览与导出"],
            ["关键指标、字段类型与数值分布，让数据状态一目了然。",
             "检查缺失、重复与 IQR 异常，评分依据完整公开。",
             "保留原始数据，手动选择清洗操作，下载 CSV 与 JSON 报告。"]):
        with column:
            st.html(f'<div class="doctor-step"><span class="doctor-eyebrow">{number}</span><b>{title}</b><p>{description}</p></div>')
    st.caption("支持 CSV / XLSX · 单文件 ≤ 10 MiB · 无需注册 · 无付费接口")
else:
    frame = loaded.frame
    report = st.session_state["report"]
    result = report["analysis"]
    st.html('<div class="doctor-eyebrow">YOUR DATA, AT A GLANCE</div>')
    st.subheader(page)
    st.caption("虚构示例已加载 · 可通过左侧上传自己的文件" if uploaded is None else "文件读取成功 · 当前分析基于原始数据")
    if frame.empty:
        st.warning("当前文件只有表头，没有数据行。可以查看字段，暂不计算质量评分。")
    cards = st.columns(4)
    metrics = [("数据总行数", f'{result["rows"]:,}', "包含完全空白行"),
               ("数据总列数", str(result["columns"]), "按表头统计字段"),
               ("缺失单元格比例", f'{result["missing"]["ratio"]:.1%}' if frame.size else "暂无数据", "空值与纯空白字符串"),
               ("数据质量综合评分", f'{result["score"]:.1f}' if result["score"] is not None else "暂无评分", "经验性参考 · 满分 100")]
    for index, (card, (label, value, help_text)) in enumerate(zip(cards, metrics)):
        with card:
            with st.container(border=True, key=f"kpi_{index}"):
                st.metric(label, value)
                st.caption(help_text)
    st.write("")

    if page == "数据总览":
        left, right = st.columns([1.65, 1])
        with left, st.container(border=True, key="completeness"):
            st.markdown("#### 各字段缺失率")
            missing_chart(result)
        with right, st.container(border=True, key="quality_summary"):
            st.markdown("#### 体检摘要")
            st.metric("完整单元格比例", f'{1 - result["missing"]["ratio"]:.1%}' if frame.size else "—")
            st.progress(1 - result["missing"]["ratio"] if frame.size else 0)
            st.write(f'发现 **{result["duplicates"]["count"]:,}** 条完整重复记录')
            if result["outliers"]["applicable_cells"]:
                st.write(f'发现 **{result["outliers"]["count"]:,}** 个统计异常单元格')
            else:
                st.caption("当前无适用的 IQR 数值字段，未进行统计异常检测。")
            st.caption("建议先核对缺失与重复记录，再结合业务判断异常值。")
        with st.container(border=True):
            st.markdown("#### 数据预览")
            st.caption(f"显示前 {min(100, len(frame))} 行 · 所有指标均基于完整数据计算")
            st.dataframe(frame.head(100), hide_index=True, width="stretch")
        field_tab, stats_tab = st.tabs(["字段数据类型", "数值字段统计"])
        with field_tab:
            st.dataframe(pd.DataFrame({"字段": list(result["field_types"]),
                                       "类型": list(result["field_types"].values())}), hide_index=True, width="stretch")
        with stats_tab:
            numeric = numeric_columns(frame)
            if numeric:
                finite_frame = frame[numeric].replace([float("inf"), float("-inf")], float("nan"))
                st.dataframe(finite_frame.describe().T, width="stretch")
                st.caption("统计仅使用有限且非缺失的数值；count 为样本数，std 为样本标准差。")
            else:
                st.info("没有可用于统计的数值字段。")

    elif page == "质量分析":
        missing_tab, duplicate_tab, outlier_tab = st.tabs(["缺失值", "重复记录", "异常值与分布"])
        with missing_tab:
            missing_chart(result)
            missing_table = pd.DataFrame(result["missing"]["by_column"]).rename(
                columns={"column": "字段", "count": "缺失数量", "ratio": "缺失率"})
            missing_table["缺失率"] = missing_table["缺失率"].map(
                lambda r: f"{r:.2%}" if result["rows"] else "暂无数据")
            st.dataframe(missing_table, hide_index=True, width="stretch")
            st.caption("空值、空字符串及纯空白字符串计为缺失。整体分母 = 行数 × 列数；每列分母 = 行数。")
        with duplicate_tab:
            a, b = st.columns(2)
            a.metric("完整重复行数量", result["duplicates"]["count"])
            b.metric("完整重复行比例", f'{result["duplicates"]["ratio"]:.2%}' if len(frame) else "暂无数据")
            st.info("以全部字段比较，先统一空白值；相同记录的首次出现有效，其余行计为重复。分母为全部行数。")
        with outlier_tab:
            st.warning(IQR_WARNING)
            entries = result["outliers"]["by_column"]
            if entries:
                table = pd.DataFrame(entries)
                table["status"] = table["status"].map(STATUS_LABELS)
                table = table.rename(columns={"column": "字段", "sample_count": "有限样本数", "nonfinite_count": "无穷值数",
                    "status": "检测状态", "count": "异常数量", "ratio": "异常比例", "lower": "下界", "upper": "上界"})
                st.dataframe(table, hide_index=True, width="stretch")
                selected_column = st.selectbox("查看数值分布", numeric_columns(frame))
                values = finite_values(frame[selected_column])
                if len(values):
                    figure = go.Figure(go.Histogram(x=values, nbinsx=30, marker_color=ACCENT))
                    chart_style(figure, height=330)
                    figure.update_layout(xaxis_title=selected_column, yaxis_title="记录数量", bargap=0.08)
                    st.plotly_chart(figure, width="stretch", config={"displaylogo": False})
                else:
                    st.info("该字段没有有限的非缺失数值，无法绘制分布。")
            else:
                st.info("没有数值字段，IQR 不适用，评分中的 O 取 0。")
            st.caption("IQR = Q3 − Q1；下界 = Q1 − 1.5 × IQR；上界 = Q3 + 1.5 × IQR。边界本身不算异常。")
            st.caption("有限样本少于 4 个、取值单一、IQR 为 0 或边界溢出的字段跳过；无穷值单独计数，不纳入 IQR 和 O。")

    elif page == "数据清洗":
        with st.container(border=True):
            st.markdown("#### 选择清洗操作")
            st.caption("默认不执行任何清洗。原始数据保持不变；不自动填补缺失值或删除统计异常值。")
            blank = st.checkbox("删除完全空白的行", key="clean_blank")
            duplicate = st.checkbox("删除整行完全重复的记录", key="clean_duplicate")
            signature = (st.session_state["dataset_id"], blank, duplicate)
            if st.session_state.get("preview", {}).get("signature") != signature:
                st.session_state.pop("preview", None)
            if st.button("预览清洗结果", type="primary", icon=":material/preview:"):
                cleaned = clean_data(frame, drop_blank=blank, drop_duplicates=duplicate)
                st.session_state["preview"] = {"signature": signature, "frame": cleaned,
                                               "csv": export_csv(cleaned)}
        preview = st.session_state.get("preview")
        if preview:
            cleaned = preview["frame"]
            a, b, c = st.columns(3)
            a.metric("原始行数", len(frame))
            b.metric("清洗后行数", len(cleaned))
            c.metric("删除记录数量", len(frame) - len(cleaned))
            st.dataframe(cleaned.head(100), hide_index=True, width="stretch")
            st.caption("预览最多 100 行。下载包含全部保留行，编码为 UTF-8-SIG。")
            st.info("导出时会为可能触发电子表格公式的文本及表头添加单引号，正常数值字段保持数值。预览显示添加保护前的内容。")
            st.download_button("下载清洗后的 CSV", preview["csv"], file_name="csv_doctor_cleaned.csv",
                               mime="text/csv", type="primary", icon=":material/download:")
        else:
            st.info("选择操作后点击“预览清洗结果”，确认行数变化后即可下载。")

    elif page == "报告导出":
        with st.container(border=True):
            st.markdown("#### 一份可追溯的数据体检报告")
            st.write("导出原始数据的质量统计、分析时间与评分依据，适用于留档与复核。清洗预览不会改变本报告。")
            st.caption("包含文件名、工作表名、字段名及聚合统计；不包含原始数据行或单元格内容。分享前仍应检查元数据是否敏感。")
            st.download_button("下载 JSON 质量报告", report_json(report), file_name="csv_doctor_report.json",
                               mime="application/json", type="primary", icon=":material/download:")
        with st.expander("查看评分依据", expanded=True):
            st.code("Score = 100 × (1 − 0.5M − 0.3D − 0.2O)", language=None)
            st.write(f'M（缺失率）= {result["scoring"]["M"]:.4%}　·　D（重复率）= {result["scoring"]["D"]:.4%}　·　O（异常率）= {result["scoring"]["O"]:.4%}')
            st.write(result["scoring"]["outlier_definition"])
            st.caption(result["scoring"]["disclaimer"])
        with st.expander("预览 JSON 报告"):
            st.json(report)

st.html('<div class="doctor-footer">CSV Doctor · 数据体检助手　/　轻量、透明、可复现<br>仅做统计检查与手动清洗，数据质量评分为经验性参考。</div>')
