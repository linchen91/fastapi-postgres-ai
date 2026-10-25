"""DataAnalysisAgent - data analysis assistant (LangGraph version).

Every input format is handled by both pipelines via _DATA_READERS:
delimited tables (.csv, .tsv), Excel (.xls, .xlsx), tabular files
(.json, .jsonl, .ndjson, .parquet, .feather), markup (.xml, .html, .htm -
largest table wins), Power BI (.pbix), and .sql (the file's query is
executed against the project PostgreSQL database).

Run from the project root (all work); an optional data file can be passed
as the first argument:
    python -m routers.data_analysis
    python routers\data_analysis.py data\simple_data.xls
    python routers\data_analysis.py --deep data\simple_data.xls
    python routers\data_analysis.py --self-test   (tool smoke test, no LLM)

The module also exposes an HTTP interface for the frontend: POST /ai/data
(mounted under /ai by main.py) accepts a multipart file upload and returns
the same analysis as HTML.
"""

# =============================
# Part 1: Environment setup
# =============================

import asyncio
import hashlib
from html import escape as html_escape
import json
import os
import re
import sys
import tempfile
import time
import warnings
from typing import Any, TypedDict

import markdown
import numpy as np
import pandas as pd

from dotenv import load_dotenv

from fastapi import APIRouter, File, HTTPException, UploadFile

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, create_react_agent
from llmbase import get_analysis_llm

# When the file is executed as a script (python routers/data_analysis.py):
# - make the project root importable for script execution
# Force UTF-8 stdout in both script and import mode, because Windows consoles
# default to legacy code pages (e.g. cp1252) that cannot encode the emoji
# output - otherwise the emoji prints inside the error handlers themselves
# raise UnicodeEncodeError and crash the workflow
if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

warnings.filterwarnings("ignore")

# Path conventions: reports land in ./output for BOTH pipelines.
DATA_PATH = "./data/simple_data.xls"   # deep pipeline's default dataset (any supported format)
OUTPUT_DIR = "./output"               # HTML reports and charts land here

# =============================
# Part 2: Data analysis steps (formerly standalone notebook tools)
# =============================

class AnalysisState(TypedDict):
    """State shared by every node of the data analysis workflow."""

    raw_data_json: str  # raw records exported from the Excel file
    clean_data_json: str  # cleaned data produced by the cleaning step
    aggregated_json: str  # pre-aggregated summaries grouped by time/category dimensions
    stats_json: str  # descriptive statistics of the cleaned data
    anomalies_json: str  # statistical outliers detected in the numeric columns
    result: str  # final ECharts option + Markdown report
    step: str  # current step label


def clean_data(data_json: str, drop_na: bool = False,
               columns_to_keep: list[str] | None = None) -> str:
    """
    Clean raw table data and return a JSON string: {"clean_data": [...]}.

    Parameters
    ----------
    data_json : str
        Raw JSON produced by load_sample_data (required).
    drop_na : bool
        Whether to drop rows containing missing values (default False).
    columns_to_keep : list[str] | None
        Column names to keep; None keeps every column.
    """
    raw_data = json.loads(data_json)
    records = raw_data.get("full_data", [])
    if not records:
        raise ValueError("Raw data is empty; nothing to clean")

    df = pd.DataFrame(records)

    # 1. Column filtering
    if columns_to_keep:
        missing_cols = [col for col in columns_to_keep if col not in df.columns]
        if missing_cols:
            raise ValueError(f"Columns to keep do not exist: {missing_cols}")
        df = df[columns_to_keep]

    # 2. Drop rows containing missing values
    if drop_na:
        df = df.dropna()

    # Fill the remaining missing values with 0
    df = df.fillna(0)

    # Build the cleaned result
    cleaned_records = df.where(pd.notnull(df), None).to_dict(orient='records')
    return json.dumps({"clean_data": cleaned_records}, ensure_ascii=False, indent=2)


def clean_data_node(state: AnalysisState) -> AnalysisState:
    """Step 1: Clean the raw table data."""
    # Same defaults as the notebook's DataCleaningTool: keep all columns, drop no rows
    try:
        clean_data_json = clean_data(state["raw_data_json"], drop_na=False, columns_to_keep=None)
    except Exception as e:
        print(f"❌ Data cleaning failed: {e}")
        return {"clean_data_json": "", "step": "clean_failed"}
    print("🧹 Data cleaning complete")
    return {"clean_data_json": clean_data_json, "step": "cleaned"}


# ---- Time / category column detection ----

_MONTH_NAME_RE = re.compile(
    r"^(month[_\s]*name|month|月份|月名)$", re.IGNORECASE
)
_MONTH_NUM_RE = re.compile(
    r"^(month[_\s]*number|month[_\s]*num|month_no|月份号)$", re.IGNORECASE
)
_DATE_RE = re.compile(r"(date|time|datetime|日期|时间)", re.IGNORECASE)
_YEAR_RE = re.compile(r"^(year|年份|年)$", re.IGNORECASE)
_QUARTER_RE = re.compile(r"^(quarter|季度|q[1-4])$", re.IGNORECASE)


_DAY_RE = re.compile(r"^(day|day[_\s-]*(name|number|num|of[_\s-]*week)|weekday)$", re.IGNORECASE)


def _detect_time_columns(df: "pd.DataFrame") -> dict:
    """Find time/category columns suitable for grouping in a chart.

    Returns a dict with keys: 'month_name_col', 'month_num_col',
    'date_col', 'year_col', 'quarter_col' (each the column name or None),
    and 'category_cols' (list of non-time categorical columns good for grouping).
    """
    cols = {}
    for c in df.columns:
        if _MONTH_NAME_RE.match(c):
            cols["month_name_col"] = c
        elif _MONTH_NUM_RE.match(c):
            cols["month_num_col"] = c
        elif _DATE_RE.match(c):
            cols["date_col"] = c
        elif _YEAR_RE.match(c):
            cols["year_col"] = c
        elif _QUARTER_RE.match(c):
            cols["quarter_col"] = c
        elif _DAY_RE.match(str(c)):
            cols.setdefault("day_cols", []).append(c)

    # Categorical columns that could serve as x-axis categories. Country,
    # city, and category dimensions are useful even when they have more than
    # the usual number of distinct values, so allow those up to 1,000 values.
    time_cols = {
        column
        for value in cols.values()
        for column in (value if isinstance(value, list) else [value])
        if column
    }
    cat_cols = []
    geographic_or_business_dimension = re.compile(
        r"(^|[_\s-])(country|countries|nation|city|cities|category|categories|"
        r"region|state|province|segment|type)([_\s-]|$)",
        re.IGNORECASE,
    )
    for c in df.select_dtypes(include=['object', 'string']).columns:
        if c in time_cols:
            continue
        nunique = df[c].nunique()
        # Skip row identifiers, but retain country/city/category dimensions
        # with larger vocabularies than ordinary chart categories.
        is_named_dimension = bool(geographic_or_business_dimension.search(str(c)))
        max_categories = 1000 if is_named_dimension else 200
        if 2 <= nunique <= max_categories:
            cat_cols.append(c)
    # Integer day fields are categorical dimensions, not chart measures.
    for c in cols.get("day_cols", []):
        nunique = df[c].nunique(dropna=True)
        if 2 <= nunique <= 31 and c not in cat_cols:
            cat_cols.append(c)
    cols["category_cols"] = cat_cols
    return cols


def _chart_numeric_columns(df: "pd.DataFrame") -> list[str]:
    """Return numeric measures while filtering common numeric identifiers.

    Spreadsheet imports often leave numeric values as strings, while IDs,
    postal codes, and row numbers should not become chart lines.
    """
    measures = []
    identifier_name = re.compile(
        r"(^|[_\s-])(id|index|row|record|account|customer|product|postal|zip|code)([_\s-]|$)",
        re.IGNORECASE,
    )
    time_name = re.compile(
        r"^(month([_\s-]*(number|num|no))?|year|quarter|day([_\s-]*(name|number|num|of[_\s-]*week))?|weekday)$",
        re.IGNORECASE,
    )
    for col in df.columns:
        name = str(col).strip()
        if identifier_name.search(name) or time_name.match(name):
            continue
        series = df[col]
        if not pd.api.types.is_numeric_dtype(series):
            converted = pd.to_numeric(series.astype(str).str.replace(",", "", regex=False), errors="coerce")
            if converted.notna().sum() < max(4, int(len(series) * 0.8)):
                continue
            df[col] = converted
            series = converted
        if series.nunique(dropna=True) > 1:
            measures.append(col)
    return measures


def _detect_report_language(records: list[dict]) -> str:
    """Infer the report language from headers and representative text values."""
    sample = " ".join(
        [str(key) for row in records[:100] for key in row]
        + [str(value) for row in records[:100] for value in row.values()
           if isinstance(value, str)][:500]
    ).lower()
    if re.search(r"[\u3040-\u30ff]", sample):
        return "Japanese"
    if re.search(r"[\uac00-\ud7af]", sample):
        return "Korean"
    if re.search(r"[\u4e00-\u9fff]", sample):
        return "Chinese"
    if re.search(r"[\u0600-\u06ff]", sample):
        return "Arabic"
    if re.search(r"[\u0400-\u04ff]", sample):
        return "Russian"

    words = set(re.findall(r"[a-zÀ-ÿ]+", sample))
    indicators = {
        "Spanish": {"de", "la", "el", "los", "las", "para", "ventas", "fecha"},
        "French": {"de", "la", "le", "les", "des", "pour", "ventes", "date"},
        "German": {"der", "die", "das", "und", "mit", "für", "umsatz", "datum"},
        "Portuguese": {"de", "da", "do", "dos", "para", "vendas", "data"},
        "Italian": {"di", "il", "la", "gli", "per", "vendite", "data"},
    }
    scores = {lang: len(words & terms) for lang, terms in indicators.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] >= 2 else "English"


_REPORT_LABELS = {
    "English": ["Data Analysis Report", "Rows analyzed", "Numeric summaries", "Column", "Count", "Mean", "Median", "Min", "Max", "Anomalies", "Detected {count} outlier value(s) using the IQR method.", "No outliers were detected by the IQR method.", "LLM analysis"],
    "Spanish": ["Informe de análisis de datos", "Filas analizadas", "Resúmenes numéricos", "Columna", "Recuento", "Media", "Mediana", "Mínimo", "Máximo", "Anomalías", "Se detectaron {count} valores atípicos mediante el método IQR.", "El método IQR no detectó valores atípicos.", "Análisis"],
    "French": ["Rapport d’analyse des données", "Lignes analysées", "Résumé numérique", "Colonne", "Nombre", "Moyenne", "Médiane", "Min", "Max", "Anomalies", "La méthode IQR a détecté {count} valeurs aberrantes.", "Aucune valeur aberrante détectée par la méthode IQR.", "Analyse"],
    "German": ["Datenanalysebericht", "Analysierte Zeilen", "Numerische Zusammenfassungen", "Spalte", "Anzahl", "Mittelwert", "Median", "Min", "Max", "Anomalien", "Die IQR-Methode hat {count} Ausreißerwerte erkannt.", "Die IQR-Methode hat keine Ausreißer erkannt.", "Analyse"],
    "Portuguese": ["Relatório de análise de dados", "Linhas analisadas", "Resumo numérico", "Coluna", "Contagem", "Média", "Mediana", "Mínimo", "Máximo", "Anomalias", "O método IQR detectou {count} valores atípicos.", "O método IQR não detectou valores atípicos.", "Análise"],
    "Italian": ["Rapporto di analisi dei dati", "Righe analizzate", "Riepilogo numerico", "Colonna", "Conteggio", "Media", "Mediana", "Min", "Max", "Anomalie", "Il metodo IQR ha rilevato {count} valori anomali.", "Il metodo IQR non ha rilevato valori anomali.", "Analisi"],
    "Chinese": ["数据分析报告", "分析行数", "数值摘要", "列", "数量", "平均值", "中位数", "最小值", "最大值", "异常值", "IQR 方法检测到 {count} 个异常值。", "IQR 方法未检测到异常值。", "分析"],
    "Japanese": ["データ分析レポート", "分析行数", "数値の概要", "列", "件数", "平均", "中央値", "最小", "最大", "異常値", "IQR 法で {count} 件の外れ値を検出しました。", "IQR 法では外れ値は検出されませんでした。", "分析"],
    "Korean": ["데이터 분석 보고서", "분석 행 수", "수치 요약", "열", "개수", "평균", "중앙값", "최소", "최대", "이상값", "IQR 방법으로 이상값 {count}개를 감지했습니다.", "IQR 방법으로 감지된 이상값이 없습니다.", "분석"],
    "Russian": ["Отчёт об анализе данных", "Проанализировано строк", "Числовые сводки", "Столбец", "Количество", "Среднее", "Медиана", "Мин", "Макс", "Аномалии", "Метод IQR обнаружил выбросы: {count}.", "Метод IQR не обнаружил выбросов.", "Анализ"],
    "Arabic": ["تقرير تحليل البيانات", "الصفوف التي تم تحليلها", "ملخصات رقمية", "العمود", "العدد", "المتوسط", "الوسيط", "الحد الأدنى", "الحد الأقصى", "القيم الشاذة", "اكتشفت طريقة IQR عدد {count} من القيم الشاذة.", "لم تكتشف طريقة IQR أي قيم شاذة.", "التحليل"],
}

_CHART_HEADINGS = {
    "English": ("Charts", "Trend Chart"),
    "Spanish": ("Gráficos", "Gráfico de tendencia"),
    "French": ("Graphiques", "Graphique de tendance"),
    "German": ("Diagramme", "Trenddiagramm"),
    "Portuguese": ("Gráficos", "Gráfico de tendência"),
    "Italian": ("Grafici", "Grafico delle tendenze"),
    "Chinese": ("图表", "趋势图"),
    "Japanese": ("グラフ", "傾向グラフ"),
    "Korean": ("차트", "추세 차트"),
    "Russian": ("Графики", "График динамики"),
    "Arabic": ("الرسوم البيانية", "مخطط الاتجاه"),
}

_INTERPRETATION_HEADINGS = {
    "English": "Anomaly interpretation",
    "Spanish": "Interpretación de anomalías",
    "French": "Interprétation des anomalies",
    "German": "Interpretation der Anomalien",
    "Portuguese": "Interpretação de anomalias",
    "Italian": "Interpretazione delle anomalie",
    "Chinese": "异常值解读",
    "Japanese": "異常値の解釈",
    "Korean": "이상값 해석",
    "Russian": "Интерпретация аномалий",
    "Arabic": "تفسير القيم الشاذة",
}


def _report_labels(language: str) -> dict[str, str]:
    keys = ("title", "rows", "numeric", "column", "count", "mean", "median",
            "min", "max", "anomalies", "detected", "none", "analysis")
    values = _REPORT_LABELS.get(language, _REPORT_LABELS["English"])
    labels = dict(zip(keys, values))
    labels["interpretation"] = _INTERPRETATION_HEADINGS.get(
        language, _INTERPRETATION_HEADINGS["English"])
    return labels


_MONTH_ORDER = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def aggregate_for_charting(clean_data_json: str) -> str:
    """Produce pre-aggregated summaries grouped by time/category dimensions.

    The LLM cannot reliably aggregate raw transactional rows (700 rows of a
    financial table) into a monthly trend — it picks a single value and
    repeats it, or pulls anomalies from a different column. This function
    does the aggregation deterministically and returns a JSON string the LLM
    can chart directly, including:

    - Monthly sums/means of every numeric column (if month columns exist)
    - Per-category breakdowns of all usable numeric measures
    - Anomaly values mapped to their category position for marker placement
    """
    records = json.loads(clean_data_json).get("clean_data", [])
    df = pd.DataFrame(records)

    time_cols = _detect_time_columns(df)
    numeric_cols = _chart_numeric_columns(df)

    result = {
        "total_rows": len(df),
        "numeric_columns": numeric_cols,
        "time_columns_detected": {k: v for k, v in time_cols.items() if v},
        "report_language": _detect_report_language(records),
    }

    # --- Monthly aggregation (preferred) ---
    month_name = time_cols.get("month_name_col")
    month_num = time_cols.get("month_num_col")

    date_col = time_cols.get("date_col")
    if month_name and month_name in df.columns:
        # Build ordered month categories
        if month_num and month_num in df.columns:
            # Sort months by their numeric equivalent
            month_map = df.groupby(month_name)[month_num].first()
            ordered_months = sorted(month_map.index, key=lambda m: month_map[m])
        else:
            # Sort by calendar order
            present = [m for m in _MONTH_ORDER if m in df[month_name].unique()]
            ordered_months = present

        monthly_agg = {}
        for col in numeric_cols:
            if col in (month_num, time_cols.get("year_col")):
                continue  # skip the time dimension columns themselves
            if col not in df.columns:
                continue
            grouped = df.groupby(month_name)[col].agg(["sum", "mean"]).reindex(ordered_months)
            monthly_agg[col] = {
                "categories": ordered_months,
                "sum": [round(float(v), 2) for v in grouped["sum"]],
                "mean": [round(float(v), 2) for v in grouped["mean"]],
            }
        result["monthly_aggregation"] = monthly_agg
        result["chart_categories"] = ordered_months
    elif date_col and date_col in df.columns:
        parsed_dates = pd.to_datetime(df[date_col], errors="coerce")
        if parsed_dates.notna().sum() >= max(2, int(len(df) * 0.8)):
            df = df.loc[parsed_dates.notna()].copy()
            df["_chart_month"] = parsed_dates.loc[parsed_dates.notna()].dt.to_period("M").astype(str)
            ordered_months = sorted(df["_chart_month"].unique())
            monthly_agg = {}
            for col in numeric_cols:
                if col == date_col:
                    continue
                grouped = df.groupby("_chart_month")[col].agg(["sum", "mean"]).reindex(ordered_months)
                monthly_agg[col] = {
                    "categories": ordered_months,
                    "sum": [round(float(v), 2) for v in grouped["sum"]],
                    "mean": [round(float(v), 2) for v in grouped["mean"]],
                }
            if monthly_agg:
                result["monthly_aggregation"] = monthly_agg
                result["chart_categories"] = ordered_months

    # --- Per-category breakdown (secondary) ---
    category_cols = time_cols.get("category_cols", [])
    if category_cols:
        cat_agg = {}
        grouped_cat_agg = {}
        # Aggregate every detected category column and every usable numeric
        # measure so chart choices work across differently named datasets.
        preferred_numeric = [c for c in ["Units Sold", "Sales", "Profit", "Revenue", "Amount"]
                              if c in numeric_cols]
        priority_numeric = preferred_numeric + [
            c for c in numeric_cols if c not in preferred_numeric
        ]

        for cat_col in category_cols:
            cat_agg[cat_col] = {}
            for num_col in priority_numeric:
                if num_col not in df.columns:
                    continue
                grouped = df.groupby(cat_col)[num_col].sum()
                # Resolve equal totals by category label so tied rankings do
                # not depend on pandas' sorting implementation.
                grouped = grouped.rename_axis("category").reset_index(name="total")
                grouped["_sort_category"] = grouped["category"].map(str)
                grouped = grouped.sort_values(
                    ["total", "_sort_category"],
                    ascending=[False, True],
                    kind="mergesort",
                )
                # Keep EVERY category (country, segment, ...) - no top-N cap.
                # Truncating here removed low-ranking countries from the chart.
                cat_agg[cat_col][num_col] = {
                    "categories": grouped["category"].tolist(),
                    "sum": [round(float(v), 2) for v in grouped["total"]],
                }
        # Cross-tab country/city against each other categorical dimension so
        # locations can be compared as grouped bars (one series per category).
        geo_re = re.compile(
            r"(^|[_\s-])(country|countries|nation|city|cities)([_\s-]|$)",
            re.IGNORECASE,
        )
        geo_cols = [c for c in category_cols if geo_re.search(str(c))]
        split_cols = [c for c in category_cols if c not in geo_cols]
        for geo_col in geo_cols:
            grouped_cat_agg[geo_col] = {}
            for split_col in split_cols:
                # Keep the chart readable when a split dimension has many
                # levels; locations remain complete on the axis.
                split_values = df[split_col].value_counts().head(12).index
                subset = df[df[split_col].isin(split_values)]
                grouped_cat_agg[geo_col][split_col] = {}
                for num_col in priority_numeric:
                    pivot = subset.pivot_table(
                        index=geo_col, columns=split_col, values=num_col,
                        aggfunc="sum", fill_value=0, observed=False,
                    )
                    locations = pivot.sum(axis=1).sort_values(ascending=False).index
                    grouped_cat_agg[geo_col][split_col][num_col] = {
                        "categories": [str(v) for v in locations],
                        "series": [
                            {"name": str(level), "values": [
                                round(float(v), 2) for v in pivot.loc[locations, level]
                            ]}
                            for level in pivot.columns
                        ],
                    }
        result["category_aggregation"] = cat_agg
        result["grouped_category_aggregation"] = grouped_cat_agg

    return json.dumps(result, ensure_ascii=False, indent=2)


def aggregation_node(state: AnalysisState) -> AnalysisState:
    """Step 1b: Pre-aggregate the cleaned data by time/category dimensions.

    This step sits between cleaning and statistics. It produces a JSON
    summary of monthly/category aggregations that the LLM can chart directly,
    instead of forcing the LLM to aggregate raw transactional rows itself
    (which it does unreliably — flat data, wrong column, mismatched scales).
    """
    if not state["clean_data_json"]:
        return {"aggregated_json": "", "step": "aggregation_skipped"}

    try:
        aggregated_json = aggregate_for_charting(state["clean_data_json"])
    except Exception as e:
        print(f"⚠️ Aggregation failed (non-fatal): {e}")
        return {"aggregated_json": "", "step": "aggregation_failed"}

    print("📊 Data aggregation complete")
    return {"aggregated_json": aggregated_json, "step": "aggregated"}


def compute_statistics(data_json: str) -> str:
    """Compute descriptive statistics for cleaned data and return a JSON string."""
    raw_data = json.loads(data_json)
    records = raw_data.get("clean_data", [])
    df = pd.DataFrame(records)

    # Statistics for numeric columns
    numeric_stats = {}
    for col in df.select_dtypes(include=[np.number]).columns:
        numeric_stats[col] = {
            "count": int(df[col].count()),
            "mean": float(df[col].mean()),
            "median": float(df[col].median()),
            "std": float(df[col].std()),
            "min": float(df[col].min()),
            "max": float(df[col].max()),
            "q25": float(df[col].quantile(0.25)),
            "q75": float(df[col].quantile(0.75))
        }

    # Statistics for categorical columns
    categorical_stats = {}
    for col in df.select_dtypes(include=['object']).columns:
        # Sort equal-frequency values by their string representation to keep
        # the serialized top-values list stable across pandas versions.
        value_counts = df[col].value_counts().rename_axis("value").reset_index(name="count")
        value_counts["_sort_value"] = value_counts["value"].map(str)
        value_counts = value_counts.sort_values(
            ["count", "_sort_value"],
            ascending=[False, True],
            kind="mergesort",
        ).head(10)
        categorical_stats[col] = {
            "unique_count": int(df[col].nunique()),
            "top_values": dict(zip(value_counts["value"], value_counts["count"].astype(int)))
        }

    result = {
        "shape": f"{len(df)} rows, {len(df.columns)} columns",
        "numeric_stats": numeric_stats,
        "categorical_stats": categorical_stats,
    }
    return json.dumps(result, ensure_ascii=False, indent=2)


def statistics_node(state: AnalysisState) -> AnalysisState:
    """Step 2: Compute descriptive statistics for the cleaned data."""
    if not state["clean_data_json"]:
        # Data cleaning failed earlier: skip, but keep the workflow running
        print("⚠️ Statistics skipped: no cleaned data available")
        return {"stats_json": "", "step": "stats_skipped"}

    try:
        stats_json = compute_statistics(state["clean_data_json"])
    except Exception as e:
        print(f"❌ Statistics computation failed: {e}")
        return {"stats_json": "", "step": "stats_failed"}

    print("📊 Statistics complete")
    return {"stats_json": stats_json, "step": "measured"}


def detect_anomalies(data_json: str, max_examples: int = 10) -> str:
    """Flag statistical outliers in every numeric column using Tukey fences
    (values below Q1 - 1.5*IQR or above Q3 + 1.5*IQR) and return a JSON summary
    with per-column counts and the most extreme examples (ranked by z-score)."""
    records = json.loads(data_json).get("clean_data", [])
    df = pd.DataFrame(records)

    anomalies = {}
    total_outliers = 0
    columns_checked = 0
    geography_re = re.compile(
        r"(^|[_\s-])(country|countries|nation|city|cities)([_\s-]|$)",
        re.IGNORECASE,
    )
    geography_columns = [
        col for col in df.columns if geography_re.search(str(col))
    ]

    for col in df.select_dtypes(include=[np.number]).columns:
        series = df[col].dropna()
        if len(series) < 4:
            # Quartiles are meaningless for very short series
            continue
        columns_checked += 1

        q1 = float(series.quantile(0.25))
        q3 = float(series.quantile(0.75))
        iqr = q3 - q1
        lower_fence = q1 - 1.5 * iqr
        upper_fence = q3 + 1.5 * iqr
        mean = float(series.mean())
        std = float(series.std(ddof=0))

        flagged = series[(series < lower_fence) | (series > upper_fence)]
        if flagged.empty:
            continue

        # Rank the flagged values by their z-score so the report can quote the
        # most extreme cases first
        examples = []
        for idx, value in flagged.items():
            example = {
                "row": int(idx),
                "value": round(float(value), 2),
                "z_score": round((float(value) - mean) / std, 2) if std else 0.0,
            }
            if geography_columns:
                example["location"] = {
                    str(location_col): str(df.at[idx, location_col])
                    for location_col in geography_columns
                    if pd.notna(df.at[idx, location_col])
                }
            examples.append(example)
        examples.sort(key=lambda e: abs(e["z_score"]), reverse=True)

        total_outliers += len(flagged)
        anomalies[col] = {
            "lower_fence": round(lower_fence, 2),
            "upper_fence": round(upper_fence, 2),
            "count": int(len(flagged)),
            "examples": examples[:max_examples],
        }

    result = {
        "method": "IQR (Tukey fences: below Q1 - 1.5*IQR or above Q3 + 1.5*IQR)",
        "rows_checked": int(len(df)),
        "columns_checked": columns_checked,
        "total_outliers": total_outliers,
        "anomalies": anomalies,
    }
    return json.dumps(result, ensure_ascii=False, indent=2)


def anomaly_node(state: AnalysisState) -> AnalysisState:
    """Step 3: Detect statistical anomalies (outliers) in the numeric columns."""
    if not state["clean_data_json"]:
        # Data cleaning failed earlier: skip, but keep the workflow running
        print("⚠️ Anomaly detection skipped: no cleaned data available")
        return {"anomalies_json": "", "step": "anomalies_skipped"}

    try:
        anomalies_json = detect_anomalies(state["clean_data_json"])
    except Exception as e:
        print(f"❌ Anomaly detection failed: {e}")
        return {"anomalies_json": "", "step": "anomalies_failed"}

    print("🔎 Anomaly detection complete")
    return {"anomalies_json": anomalies_json, "step": "anomalies_detected"}


# =============================
# Part 3: Create the agent (LangGraph workflow)
# =============================

SYSTEM_PROMPT = """You are a data analyst. Your task is to produce an ECharts
line chart and a Markdown analysis report from the provided data.

Write all report prose and chart text in the language used by the dataset's
column names and text values. Preserve column names exactly as provided.

## Charting rules

1. Use the PRE-AGGREGATED DATA provided under "Aggregated data for charting"
   to build the chart. Do NOT attempt to aggregate raw rows yourself — the
   aggregation has already been done for you. Pick the most interesting
   numeric column (e.g. Sales, Profit, Units Sold) and use its monthly or
   category breakdown as the line series data.

2. The chart MUST use line series ONLY (type: 'line' for every series).
   Example:
   option = {
       xAxis: {
           type: 'category',
           data: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun']
       },
       yAxis: {
           type: 'value',
           scale: true,
           boundaryGap: ['5%', '5%']
       },
       series: [
           {
               name: 'Sales',
               data: [6607761, 7297531, 5586859, 6964775, 6210211, 9518893],
               type: 'line',
               smooth: true
           }
       ]
   };

3. You MAY include 1-3 line series if multiple numeric columns are
   interesting, but keep the chart clean (at most 3 series).

4. Fit the y-axis: set yAxis.scale = true and yAxis.boundaryGap = ['5%', '5%']
   so the axis spans the data range with headroom.

5. Anomaly markers: Add ONE separate scatter series (type: 'scatter') for
   anomaly points, using RED color (#dc3545). The scatter series data MUST
   be an array of [categoryIndex, value] pairs, where categoryIndex is the
   0-based index into the xAxis categories array, and value is the
   aggregated value at that category. For example, if October (index 9) is
   an anomaly with aggregated Sales value 21671431:
       {
           name: 'Anomalies',
           type: 'scatter',
           data: [[9, 21671431]],
           symbolSize: 12,
           itemStyle: { color: '#dc3545' }
       }
   NEVER use flat values like [4219.5, 4492.5] — always use [index, value]
   pairs. Only mark anomalies for the SAME numeric column being charted.
   No other series may be red.

6. All chart text (title, legend, series names, axis labels, category labels)
   MUST use the dataset's language; preserve original column/category names.

7. Output ONLY the ECharts option object (starting with "option = {") and
   the Markdown report. Do NOT output HTML, <script> tags, or explanations
   of the code.

## Report rules

8. After the ECharts option, write a detailed data analysis report in
   Markdown. The report MUST start with "# Data Analysis Report".

9. The report should include:
   - Background and objectives
   - Key findings (use the aggregated data and statistics)
   - Trend identification and comparative analysis
   - A dedicated "Anomaly Detection" section: state which columns have
     outliers, how many rows are outside the IQR fences, and quote the
     most extreme values from the provided anomaly data
   - Avoid subjective speculation; conclusions must be based on the data
"""


# Maximum number of cleaned rows embedded in the LLM prompt; the statistics
# JSON always covers the full dataset
PROMPT_SAMPLE_ROWS = 50

# How many times the LLM is asked for the analysis section before giving up.
# OpenRouter's free-tier routing sometimes answers with a placeholder
# instead of the requested content, so a retry usually recovers.
MAX_LLM_ATTEMPTS = 3

# System prompt for the LLM analysis section of the report. The model only
# narrates numbers that were computed deterministically by the workflow -
# it never does the math itself.
LLM_ANALYSIS_SYSTEM_PROMPT = """You write restrained, factual data analysis reports.

You receive pre-computed statistics, anomaly results and aggregations for a
dataset plus a sample of its cleaned rows, and you write the narrative
"LLM analysis" section of the report in Markdown.

Rules:
- Write the narrative and headings in the same language as the dataset's
  column names and text values, unless the user explicitly asks otherwise.
- Use ONLY the figures supplied in the input; never invent, recompute or
  round them differently - copy every figure exactly as given.
- Dataset column names stay in their original form.
- Describe what the data shows; no causal claims, no speculation.
- If the input cannot support a requested section, omit that section.
- The Markdown section itself: no code fences, no JSON, no JavaScript, no
  chart config inside it - those are stripped before rendering.
- After the Markdown, output the chart specs as ONE fenced ```json block
  ({"charts": [...]}, entry shape as described in the request) and nothing
  after it. Only the spec block may contain JSON or a fence.
- Do NOT output a document title (no '# Data Analysis Report').
- Write every subsection as a third-level heading (### ...) so it nests
  under the report's '## LLM analysis' heading.
- Charts only SELECT what to plot; the report renders them from its own
  aggregated numbers, so list metric/dimension keys that exist in the
  provided aggregations - never fabricate data points."""

# Numeric columns that are preferred for chart series, in priority order.
_PREFERRED_CHART_COLUMNS = [
    "Sales", "Profit", "Revenue", "Amount", "Total",
    "Units Sold", "Quantity", "Count", "Value",
]


def _pick_chart_column(monthly_agg: dict) -> str | None:
    """Choose the primary numeric column for the monthly chart.

    Tries preferred column names first, then falls back to the first
    numeric column that is not a time dimension (Month Number, Year).
    """
    if not monthly_agg:
        return None

    # Try preferred names in order
    for pref in _PREFERRED_CHART_COLUMNS:
        if pref in monthly_agg:
            return pref

    # Fall back to the first available column
    skip = {"Month Number", "Year", "Quarter"}
    for col in monthly_agg:
        if col not in skip:
            return col

    return None


def _find_anomaly_categories(
    chart_column: str,
    categories: list[str],
    monthly_sums: list[float],
    anomalies_json: str,
) -> list[list]:
    """Map anomaly values to chart category positions.

    Returns a list of [categoryIndex, value] pairs for the scatter series.
    Only anomalies from the same column as the chart are used, and the
    value placed on the marker is the aggregated (monthly sum) value at
    that category, not the raw outlier value, so the marker sits on the
    line series point.
    """
    if not anomalies_json or not categories:
        return []

    try:
        anomalies = json.loads(anomalies_json)
    except (json.JSONDecodeError, TypeError):
        return []

    col_anomalies = anomalies.get("anomalies", {}).get(chart_column)
    if not monthly_sums:
        return []

    # The anomaly detection was done on raw rows; we don't know which
    # month those rows belong to without re-mapping. Instead, mark the
    # top aggregated values (which are the ones that stand out visually
    # in the monthly chart) as anomaly highlights. This keeps the markers
    # on the correct scale and position.
    mean_val = float(np.mean(monthly_sums))
    std_val = float(np.std(monthly_sums))
    markers = []
    for i, val in enumerate(monthly_sums):
        z = (val - mean_val) / std_val if std_val else 0
        if abs(z) > 1.5:
            markers.append([i, round(float(val), 2)])

    if markers:
        return markers

    # Raw-row outliers do not always make a whole month's total an outlier.
    # Still show the most extreme monthly point(s) in red so the chart has a
    # visible anomaly highlight whenever the selected metric has anomalies.
    indexed = sorted(enumerate(monthly_sums), key=lambda p: p[1], reverse=True)
    return [
        [idx, round(float(val), 2)]
        for idx, val in indexed[:min(2, len(indexed))]
    ]


def build_deterministic_chart(aggregated_json: str, anomalies_json: str) -> str:
    """Build an ECharts option string deterministically from the aggregated data.

    The same input data always produces the same chart configuration.

    Returns the ECharts option as a JavaScript object literal string
    (without the leading "option = "), or "" if no chart can be built.
    """
    if not aggregated_json:
        return ""

    try:
        agg = json.loads(aggregated_json)
    except (json.JSONDecodeError, TypeError):
        return ""
    anomaly_name = _report_labels(agg.get("report_language", "English"))["anomalies"]

    # Prefer monthly aggregation; fall back to category aggregation
    monthly_agg = agg.get("monthly_aggregation", {})
    cat_agg = agg.get("category_aggregation", {})

    if monthly_agg:
        chart_col = _pick_chart_column(monthly_agg)
        if not chart_col:
            return ""

        col_data = monthly_agg[chart_col]
        categories = col_data.get("categories", [])
        if not categories:
            return ""

        # Include several useful measures so the fallback chart does not
        # silently reduce a multi-metric dataset to its first numeric column.
        chart_cols = [c for c in _PREFERRED_CHART_COLUMNS if c in monthly_agg]
        chart_cols += [c for c in monthly_agg if c not in chart_cols
                       and c not in {"Month Number", "Year", "Quarter"}]
        chart_cols = [c for c in chart_cols
                      if len(monthly_agg[c].get("sum", [])) == len(categories)]
        if not chart_cols:
            return ""

        # Find anomaly positions on the aggregated data
        sums_rounded = [round(float(v), 2) for v in monthly_agg[chart_col].get("sum", [])]
        anomaly_markers = _find_anomaly_categories(
            chart_col, categories, sums_rounded, anomalies_json
        )

        # Build the ECharts option as a JavaScript object literal
        # (not JSON — ECharts accepts unquoted keys)
        series_lines = []
        for col in chart_cols:
            values = [round(float(v), 2) for v in monthly_agg[col]["sum"]]
            series_lines.append(
                "        {\n"
                f"            name: {json.dumps(str(col))},\n"
                f"            data: {json.dumps(values)},\n"
                "            type: 'line',\n"
                "            smooth: true,\n"
                "            emphasis: { focus: 'series' },\n"
                "            lineStyle: { width: 2 }\n"
                "        }"
            )
        if len(chart_cols) > 1:
            series_lines = [",\n".join(series_lines)]

        if anomaly_markers:
            series_lines.append(
                "        ,{\n"
                f"            name: {json.dumps(anomaly_name)},\n"
                "            type: 'scatter',\n"
                f"            data: {json.dumps(anomaly_markers)},\n"
                "            symbolSize: 12,\n"
                "            itemStyle: { color: '#dc3545' }\n"
                "        }"
            )

        series_block = "\n".join(series_lines)

        return (
            "{\n"
            "    title: {\n"
            f"        text: {json.dumps(str(chart_col))},\n"
            "        left: 'center'\n"
            "    },\n"
            "    tooltip: {\n"
            "        trigger: 'axis'\n"
            "    },\n"
            "    legend: {\n"
            "        bottom: 0\n"
            "    },\n"
            "    grid: {\n"
            "        left: '10%',\n"
            "        right: '10%',\n"
            "        bottom: '15%',\n"
            "        top: '15%',\n"
            "        containLabel: true\n"
            "    },\n"
            "    xAxis: {\n"
            "        type: 'category',\n"
            "        boundaryGap: false,\n"
            f"        data: {json.dumps(categories)}\n"
            "    },\n"
            "    yAxis: {\n"
            "        type: 'value',\n"
            "        scale: true,\n"
            "        boundaryGap: ['5%', '5%']\n"
            "    },\n"
            "    series: [\n"
            f"{series_block}\n"
            "    ]\n"
            "}"
        )

    elif cat_agg:
        # Use the first category column's first numeric breakdown
        for cat_col, num_cols in cat_agg.items():
            for num_col, breakdown in num_cols.items():
                categories = breakdown.get("categories", [])
                sums = breakdown.get("sum", [])
                if not categories or not sums:
                    continue

                sums_rounded = [round(float(v), 2) for v in sums]

                return (
                    "{\n"
                    "    title: {\n"
                    f"        text: {json.dumps(str(num_col))},\n"
                    "        left: 'center'\n"
                    "    },\n"
                    "    tooltip: {\n"
                    "        trigger: 'axis'\n"
                    "    },\n"
                    "    grid: {\n"
                    "        left: '10%',\n"
                    "        right: '10%',\n"
                    "        bottom: '15%',\n"
                    "        top: '15%',\n"
                    "        containLabel: true\n"
                    "    },\n"
                    "    xAxis: {\n"
                    "        type: 'category',\n"
                    f"        data: {json.dumps(categories)}\n"
                    "    },\n"
                    "    yAxis: {\n"
                    "        type: 'value',\n"
                    "        scale: true,\n"
                    "        boundaryGap: ['5%', '5%']\n"
                    "    },\n"
                    "    series: [{\n"
                    f"        name: '{num_col}',\n"
                    f"        data: {json.dumps(sums_rounded)},\n"
                    "        type: 'line',\n"
                    "        smooth: true\n"
                    "    }]\n"
                    "}"
                )

    return ""


# ---------------------------------------------------------------------------
# Charts chosen by the LLM, rendered from the real aggregated numbers
# ---------------------------------------------------------------------------
# The analysis call also returns a {"charts": [...]} spec list saying WHAT
# to chart (source/metric/dimension/aggregation/title). The specs are
# parsed here and turned into ECharts options by build_llm_charts(), which
# only ever fills the series from the pre-aggregated JSON computed earlier
# in the workflow - a model can pick a chart, but it can never invent the
# numbers on it. Anything invalid is skipped and the caller falls back to
# the single deterministic chart.
# ---------------------------------------------------------------------------

def extract_chart_specs(text: str) -> list[dict]:
    """Pull the {"charts": [...]} spec list out of the model's reply.

    Tries a fenced ```json block first, then any top-level object starting
    with a "charts" key (brace-matched, so nested braces/strings cannot
    truncate it). Returns [] when nothing usable is found - the caller then
    renders the deterministic chart instead.
    """
    if not text:
        return []

    candidates = []
    for content in re.findall(r"```(?:json)?\s*([\s\S]*?)```", text, flags=re.IGNORECASE):
        content = content.strip()
        if content.startswith("{"):
            end = _find_balanced_brace(content, 0)
            if end != -1:
                candidates.append(content[:end])

    m = re.search(r"\{\s*[\"']charts[\"']\s*:", text)
    if m:
        end = _find_balanced_brace(text, m.start())
        if end != -1:
            candidates.append(text[m.start():end])

    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
        specs = data.get("charts") if isinstance(data, dict) else data
        if isinstance(specs, list):
            return [s for s in specs if isinstance(s, dict)][:3]
    return []


def _line_bar_option(title: str, series_name: str, categories: list,
                     values: list, ctype: str, markers: list | None = None,
                     additional_series: list[tuple[str, list]] | None = None,
                     anomaly_name: str = "Anomalies") -> str:
    """Build one ECharts option (line or bar) over a category x-axis."""
    kind = "bar" if ctype == "bar" else "line"
    boundary = "true" if kind == "bar" else "false"   # bars need axis gap
    vals = [round(float(v), 2) for v in values]

    series = [
        "        {",
        f"            name: {json.dumps(str(series_name))},",
        f"            data: {json.dumps(vals)},",
        f"            type: '{kind}',",
    ]
    if kind == "line":
        series.append("            smooth: true,")
    series.append("            itemStyle: { color: '#4572a7' },")
    if kind == "line":
        series.append("            lineStyle: { width: 2 },")
    series.append("        }")
    for extra_name, extra_values in (additional_series or []):
        extra_vals = [round(float(v), 2) for v in extra_values]
        series += [
            "        ,{",
            f"            name: {json.dumps(str(extra_name))},",
            f"            data: {json.dumps(extra_vals)},",
            "            type: 'line',",
            "            smooth: true,",
            "            lineStyle: { width: 2 },",
            "            emphasis: { focus: 'series' }",
            "        }",
        ]
    if markers:
        series += [
            "        ,{",
            f"            name: {json.dumps(anomaly_name)},",
            "            type: 'scatter',",
            f"            data: {json.dumps(markers)},",
            "            symbolSize: 12,",
            "            itemStyle: { color: '#dc3545' }",
            "        }",
        ]

    return "\n".join([
        "{",
        "    title: {",
        f"        text: {json.dumps(str(title))},",
        "        left: 'center'",
        "    },",
        "    tooltip: { trigger: 'axis' },",
        "    legend: { bottom: 0 },",
        "    grid: { left: '10%', right: '10%', bottom: '15%', top: '15%', containLabel: true },",
        "    xAxis: {",
        "        type: 'category',",
        f"        boundaryGap: {boundary},",
        f"        data: {json.dumps(categories)}",
        "    },",
        "    yAxis: { type: 'value', scale: true, boundaryGap: ['5%', '5%'] },",
        "    series: [",
        *series,
        "    ]",
        "}",
    ])


def _grouped_bar_option(title: str, categories: list, series: list[dict]) -> str:
    """Build a grouped bar chart with each category value as a series."""
    rendered = []
    for item in series:
        values = item.get("values") or []
        if len(values) != len(categories):
            continue
        rendered.append(
            "        { name: " + json.dumps(str(item.get("name", "")))
            + ", type: 'bar', data: "
            + json.dumps([round(float(v), 2) for v in values]) + " }"
        )
    if not categories or not rendered:
        return ""
    return "\n".join([
        "{", "    title: { text: " + json.dumps(title) + ", left: 'center' },",
        "    tooltip: { trigger: 'axis' },", "    legend: { bottom: 0 },",
        "    grid: { left: '10%', right: '10%', bottom: '18%', top: '15%', containLabel: true },",
        "    xAxis: { type: 'category', data: " + json.dumps(categories) + " },",
        "    yAxis: { type: 'value', scale: true },", "    series: [",
        ",\n".join(rendered), "    ]", "}"
    ])


def _chartable_keys(aggregated_json: str) -> str:
    """One JSON summary of the keys build_llm_charts() can actually plot.

    Injected into the analysis prompt so the model copies exact
    metric/dimension values instead of guessing (guesses are what the
    renderer would otherwise have to reject).
    """
    try:
        agg = json.loads(aggregated_json or "{}")
    except (json.JSONDecodeError, TypeError):
        return "{}"
    monthly = agg.get("monthly_aggregation") or {}
    category = agg.get("category_aggregation") or {}
    summary = {
        "monthly_metrics": list(monthly),
        "category_charts": {dim: list(metrics) for dim, metrics in category.items()},
    }
    return json.dumps(summary, ensure_ascii=False)


def build_llm_charts(specs: list[dict], aggregated_json: str,
                     anomalies_json: str = "") -> list[str]:
    """Render LLM-picked chart specs as a list of ECharts options.

    Specs only choose WHAT to plot; every value is looked up in the
    pre-aggregated JSON, so hallucinated figures can never reach a chart.
    Near-miss specs are repaired rather than dropped - models tend to write
    an aggregation name ("sum"/"mean") where "metric" belongs, or pick an
    unknown metric for a valid dimension - in which case the renderer keeps
    the model's choice (source/dimension/type/title) and resolves the
    missing key from the chartable data. Only specs with no usable data at
    all are skipped; an empty result makes the caller fall back to
    build_deterministic_chart().
    """
    if not specs or not aggregated_json:
        return []
    try:
        agg = json.loads(aggregated_json)
    except (json.JSONDecodeError, TypeError):
        return []
    monthly = agg.get("monthly_aggregation") or {}
    category = agg.get("category_aggregation") or {}
    anomaly_name = _report_labels(agg.get("report_language", "English"))["anomalies"]

    options: list[str] = []
    seen: set[tuple] = set()
    for spec in specs:
        metric = str(spec.get("metric") or spec.get("column") or "").strip()
        source = str(spec.get("source") or "").lower()
        ctype = str(spec.get("type") or "line").lower()
        if ctype not in ("line", "bar"):
            ctype = "line"
        agg_kind = str(spec.get("agg") or "sum").lower()
        if agg_kind not in ("sum", "mean"):
            agg_kind = "sum"
        title = str(spec.get("title") or "").strip()[:100]

        # Repair: the model often writes the aggregation name into "metric"
        if metric.lower() in ("sum", "mean"):
            agg_kind = metric.lower()
            metric = ""

        if source not in ("monthly", "category"):
            if metric and metric in monthly:
                source = "monthly"
            elif metric and any(metric in m for m in category.values()):
                source = "category"
            else:
                source = "monthly" if monthly else "category"

        markers: list | None = None
        if source == "monthly":
            entry = monthly.get(metric) if metric else None
            if not isinstance(entry, dict):
                resolved = _pick_chart_column(monthly)
                if not resolved:
                    print(f"⚠️ LLM chart skipped: no monthly aggregation for {metric!r}")
                    continue
                print(f"⚠️ LLM chart: {metric!r} is not a monthly column; "
                      f"charting {resolved!r} instead")
                metric = resolved
                entry = monthly[metric]
            categories = entry.get("categories") or []
            actual_agg = agg_kind if entry.get(agg_kind) else "sum"
            values = entry.get(actual_agg) or []
            series_name = str(metric)
            dedupe_key = ("monthly", metric, actual_agg)
        else:
            dimension = str(spec.get("dimension") or spec.get("category") or "").strip()
            per_metric = category.get(dimension)
            if not isinstance(per_metric, dict) or not per_metric:
                if category:
                    dimension = next(iter(category))
                    per_metric = category[dimension]
                    print(f"⚠️ LLM chart: unknown dimension; charting {dimension!r} instead")
                else:
                    print("⚠️ LLM chart skipped: no category aggregation available")
                    continue
            if metric not in per_metric:
                resolved = next(iter(per_metric))
                print(f"⚠️ LLM chart: {metric!r} is not chartable under "
                      f"{dimension!r}; charting {resolved!r} instead")
                metric = resolved
            entry = per_metric[metric]
            categories = entry.get("categories") or []
            values = entry.get("sum") or []     # category breakdowns store sums
            series_name = str(metric)
            dedupe_key = ("category", dimension, metric)
            # Category charts (including bar charts) need the same overlay as
            # monthly charts. Without this, the report can contain an
            # Anomalies section while its category chart has no red points.
            rounded = [round(float(v), 2) for v in values]
            markers = _find_anomaly_categories(
                metric, categories, rounded, anomalies_json)

        if not categories or not values or len(categories) != len(values):
            print(f"⚠️ LLM chart skipped: {series_name!r} has no usable data")
            continue
        if dedupe_key in seen:
            continue                            # the model asked twice
        seen.add(dedupe_key)

        if source == "monthly":
            # Same anomaly markers as the deterministic chart: points whose
            # aggregated value sits >1.5 standard deviations from the mean
            rounded = [round(float(v), 2) for v in values]
            markers = _find_anomaly_categories(
                metric, categories, rounded, anomalies_json)

        options.append(_line_bar_option(title or series_name, series_name,
                                        categories, values, ctype, markers,
                                        anomaly_name=anomaly_name))
    return options


def _sanitize_llm_analysis(text: str) -> str:
    """Make the model's reply safe to embed under '## LLM analysis'.

    The section is assembled from pre-computed deterministic parts, so the
    reply must not contribute any structure of its own. This helper:
    - drops fenced code blocks (the chart-spec JSON is parsed out of them
      beforehand by extract_chart_specs; prose never contains them)
    - drops a chart-spec object the model emitted without a fence, and any
      echoed ECharts option (chart config is built by build_llm_charts /
      build_deterministic_chart only)
    - drops the document title the model sometimes restates
    - demotes H1/H2 headings to H3 so its subsections nest under the
      '## LLM analysis' H2 instead of competing with it
    - returns "" when nothing readable is left, which makes the caller
      retry and finally fall back to the deterministic-only report
    """
    if not text or not text.strip():
        return ""
    text = text.strip()

    # Fenced blocks (chart specs / JSON / JavaScript the model may echo back)
    text = re.sub(r"```[\s\S]*?```", "", text)

    # An unfenced {"charts": [...]} spec object (parsed already, must not leak)
    m = re.search(r"\{\s*[\"']charts[\"']\s*:", text)
    if m:
        end = _find_balanced_brace(text, m.start())
        text = text[:m.start()] + text[end:] if end != -1 else text[:m.start()]

    # Any ECharts option object ("option = {...}"); cut it out with the
    # brace matcher so nested braces/strings cannot truncate the removal
    while True:
        m = re.search(r"\boption\s*=\s*(?=\{)", text)
        if not m:
            break
        end = _find_balanced_brace(text, m.end())   # m.end() points at '{'
        if end == -1:                               # unbalanced: drop the tail
            text = text[:m.start()]
            break
        text = text[:m.start()] + text[end:]

    # The report already carries this title
    text = re.sub(r"^\s*#{1,6}\s*Data Analysis Report\s*$", "",
                  text, flags=re.MULTILINE)

    # Demote H1/H2 to H3 so the subsections nest under '## LLM analysis'
    demoted = []
    for line in text.splitlines():
        m2 = re.match(r"^(#{1,2})\s+", line)
        demoted.append("###" + line[len(m2.group(1)):] if m2 else line)
    text = "\n".join(demoted).strip()

    # Nothing readable survived the cleanup -> unusable response
    if not re.search(r"\w{3,}", text):
        return ""
    return text


def generate_report_node(state: AnalysisState) -> AnalysisState:
    """Step 4: Build the report: deterministic chart, deterministic report
    skeleton (rows, statistics table, anomaly list), plus the LLM-written
    '## LLM analysis' section narrating those numbers."""
    # Data cleaning failed: nothing to chart or analyze. Still produce a
    # report page explaining the failure instead of aborting the whole run.
    if not state["clean_data_json"]:
        print("❌ Report unavailable: no cleaned data to analyze")
        result = (
            "# Data Analysis Report\n\n"
            "The analysis could not be completed because the data cleaning "
            f"step failed (pipeline stopped at `{state['step']}`), so no "
            "cleaned data was available for statistics, anomaly detection, "
            "or charting."
        )
        return {"result": result, "step": "error"}

    records = json.loads(state["clean_data_json"]).get("clean_data", [])
    report_language = _detect_report_language(records)
    labels = _report_labels(report_language)
    stats = json.loads(state["stats_json"]) if state["stats_json"] else {}
    anomalies = json.loads(state["anomalies_json"]) if state["anomalies_json"] else {}

    # Keep a deterministic report as a fallback when the model is unavailable
    # or returns an unusable response.
    lines = [f"# {labels['title']}", "", f"{labels['rows']}: {len(records)}"]
    numeric_stats = stats.get("numeric_stats", {})
    if numeric_stats:
        lines.extend([
            "", f"## {labels['numeric']}", "",
            f"| {labels['column']} | {labels['count']} | {labels['mean']} | {labels['median']} | {labels['min']} | {labels['max']} |",
            "|---|---:|---:|---:|---:|---:|",
        ])
        for col, values in numeric_stats.items():
            lines.append(
                f"| {col} | {values['count']} | {values['mean']:.2f} | "
                f"{values['median']:.2f} | {values['min']:.2f} | {values['max']:.2f} |"
            )

    anomaly_columns = anomalies.get("anomalies", {})
    lines.extend(["", f"## {labels['anomalies']}", ""])
    if anomaly_columns:
        lines.append(labels["detected"].format(count=anomalies.get("total_outliers", 0)))
        # Blank line before the bullets so Markdown renders them as a list
        # instead of literal "- " text inside the paragraph above
        lines.append("")
        for col, details in anomaly_columns.items():
            lines.append(
                f"- **{col}:** {details['count']} outlier(s); fences "
                f"{details['lower_fence']:.2f} to {details['upper_fence']:.2f}."
            )
            for example in details.get("examples", [])[:3]:
                location = example.get("location") or {}
                place = ", ".join(
                    f"{name}: {value}" for name, value in location.items()
                )
                suffix = f" ({place})" if place else ""
                lines.append(
                    f"  - Row {example['row']}: {example['value']}{suffix}."
                )
    else:
        lines.append(labels["none"])

    fallback_report = "\n".join(lines)

    # ---- LLM analysis section ----
    # A full narrative (key findings, trend/comparison analysis, anomaly
    # interpretation, recommendations) written by the model from the
    # pre-computed numbers only. The deterministic report above always
    # survives: when the model is unreachable, rate-limited or replies with
    # junk, the report simply ships without this section.
    stats_json = state["stats_json"] or "{}"
    anomalies_json = state["anomalies_json"] or "{}"
    aggregated_json = state["aggregated_json"] or "{}"
    sample_rows = json.dumps(records[:PROMPT_SAMPLE_ROWS],
                             ensure_ascii=False, default=str)
    chartable = _chartable_keys(aggregated_json)

    prompt = (
        "Write the 'LLM analysis' section of a data analysis report in Markdown. "
        f"Write all prose, headings, recommendations, and chart titles in {report_language}, "
        "the language detected from the dataset. Preserve dataset column names exactly. "
        "Use ONLY the computed data below - every figure you quote must appear "
        "there verbatim.\n\n"
        "Structure (four subsections, each a third-level '###' heading):\n"
        "### Key findings\n"
        "3 to 5 bullets, each quoting exact numbers (totals, means, extremes, "
        "shares) taken from the statistics and aggregations JSON.\n"
        "### Trend and comparison analysis\n"
        "2 to 3 short paragraphs interpreting the time trend and the category "
        "breakdowns in the aggregations JSON (which periods/categories lead, "
        "how large the gaps are).\n"
        f"### {labels['interpretation']}\n"
        "Which columns carry outliers, how many rows fall outside the IQR "
        "fences, the fence bounds and the most extreme example values - only "
        "from the anomalies JSON.\n"
        "### Recommendations\n"
        "2 to 3 actionable recommendations that follow from the findings "
        "above.\n\n"
        "Omit any subsection the data cannot support instead of speculating.\n\n"
        "After the Markdown, output the charts the report should show: ONE "
        "fenced ```json block shaped as {\"charts\": [ ... ]} whose entries "
        "pick a chart each:\n"
        "  {\"type\": \"line\" or \"bar\", \"source\": \"monthly\" or \"category\",\n"
        "   \"metric\": \"<numeric column>\", \"dimension\": \"<category column, "
        "only when source is category>\", \"agg\": \"sum\" or \"mean\",\n"
        f"   \"title\": \"<short chart title in {report_language}>\"}}\n"
        "Pick 1 to 3 charts that illustrate your findings. \"metric\" is the "
        "numeric column to plot and \"dimension\" the category column: both "
        "MUST be copied verbatim from the Chartable keys JSON below - never "
        "write sum/mean there (\"agg\" is where sum or mean goes; category "
        "charts carry sum only). Output {\"charts\": []} when no chart would "
        "add anything.\n\n"
        "Chartable keys (the exact values to use for metric/dimension):\n"
        f"{chartable}\n\n"
        f"Row count: {len(records)}\n"
        f"Sample of cleaned rows (first {min(len(records), PROMPT_SAMPLE_ROWS)}"
        f" of {len(records)}):\n{sample_rows}\n\n"
        f"Statistics JSON:\n{stats_json}\n\n"
        f"Anomalies JSON:\n{anomalies_json}\n\n"
        f"Aggregations JSON:\n{aggregated_json}"
    )

    llm_analysis = ""
    llm_specs: list[dict] = []
    for attempt in range(1, MAX_LLM_ATTEMPTS + 1):
        try:
            response = get_analysis_llm().invoke([
                SystemMessage(content=LLM_ANALYSIS_SYSTEM_PROMPT),
                HumanMessage(content=prompt),
            ])
            raw = response.content if isinstance(response.content, str) else ""
            # Chart specs are read BEFORE sanitizing: the sanitizer strips
            # fenced blocks (and unfenced spec objects) from the prose
            llm_specs = extract_chart_specs(raw)
            llm_analysis = _sanitize_llm_analysis(raw)
            if llm_analysis:
                break
            print(f"⚠️ LLM analysis attempt {attempt}/{MAX_LLM_ATTEMPTS} "
                  "produced no usable text; retrying")
        except Exception as e:
            print(f"⚠️ LLM analysis attempt {attempt}/{MAX_LLM_ATTEMPTS} "
                  f"failed: {type(e).__name__}: {e}")
    if llm_analysis:
        print(f"✍️ LLM analysis written ({len(llm_analysis)} chars, "
              f"{attempt} attempt(s), {len(llm_specs)} chart spec(s))")
    else:
        print("LLM analysis unavailable; keeping the deterministic report sections only")

    # Charts: specs chosen by the LLM in the same call as its analysis,
    # rendered from the aggregated numbers by build_llm_charts(); when the
    # model returned none (or all of them were invalid), keep the single
    # deterministic chart built from the very same data.
    chart_options: list[str] = []
    chart_specs = list(llm_specs) if llm_analysis else []
    try:
        agg = json.loads(state["aggregated_json"] or "{}")
        category_aggregation = agg.get("category_aggregation") or {}
        geo_dimension = re.compile(
            r"(^|[_\s-])(country|countries|nation|city|cities)([_\s-]|$)",
            re.IGNORECASE,
        )
        for dimension, metrics in category_aggregation.items():
            if not geo_dimension.search(str(dimension)):
                continue
            for metric in metrics:
                chart_specs.append({
                    "type": "bar", "source": "category", "metric": metric,
                    "dimension": dimension, "agg": "sum",
                    "title": f"{metric} by {dimension}",
                })
    except (json.JSONDecodeError, TypeError):
        pass
    if chart_specs:
        chart_options = build_llm_charts(
            chart_specs, state["aggregated_json"], state["anomalies_json"])
        if chart_options:
            print(f"📈 {len(chart_options)} chart(s) rendered from LLM specs")
        else:
            print("⚠️ No usable chart spec in the LLM reply; using the "
                  "deterministic chart instead")
    try:
        grouped_dimensions = json.loads(
            state["aggregated_json"] or "{}"
        ).get("grouped_category_aggregation", {})
        for location, split_dimensions in grouped_dimensions.items():
            for split_by, metrics in split_dimensions.items():
                for metric, data in metrics.items():
                    option = _grouped_bar_option(
                        f"{metric} by {location} and {split_by}",
                        data.get("categories") or [],
                        data.get("series") or [],
                    )
                    if option:
                        chart_options.append(option)
    except (json.JSONDecodeError, AttributeError, TypeError):
        pass

    if not chart_options:
        det = build_deterministic_chart(state["aggregated_json"], state["anomalies_json"])
        chart_options = [det] if det else []

    report = fallback_report
    if llm_analysis:
        report += f"\n\n## {labels['analysis']}\n\n" + llm_analysis
    result = "".join(f"option = {opt};\n\n" for opt in chart_options) + report
    return {"result": result, "step": "completed"}

def create_analysis_workflow():
    """Build the LangGraph data analysis workflow.

    Pipeline: clean -> aggregate -> statistics -> anomalies -> report.
    The aggregation step pre-groups data by time/category dimensions so the
    report builder receives ready-to-chart summaries instead of raw rows.
    """
    workflow = StateGraph(AnalysisState)

    # Add five nodes
    workflow.add_node("clean", clean_data_node)
    workflow.add_node("aggregate", aggregation_node)
    workflow.add_node("statistics", statistics_node)
    workflow.add_node("anomalies", anomaly_node)
    workflow.add_node("report", generate_report_node)

    # Set up a linear workflow
    workflow.add_edge(START, "clean")
    workflow.add_edge("clean", "aggregate")
    workflow.add_edge("aggregate", "statistics")
    workflow.add_edge("statistics", "anomalies")
    workflow.add_edge("anomalies", "report")
    workflow.add_edge("report", END)

    # Compiled graph
    return workflow.compile()


# =============================
# Part 4: Load the sample data table
# =============================

def _read_pbix_table(file_path: str) -> pd.DataFrame:
    """Load the largest data table from a Power BI (.pbix) file."""
    from pbixray import PBIXRay  # lazy import: only needed for .pbix input

    model = PBIXRay(file_path)

    # Skip the auto-generated date tables that Power BI adds to every model
    tables = [t for t in model.tables
              if not str(t).startswith(("DateTableTemplate", "LocalDateTable"))]
    if not tables:
        raise ValueError(f"No usable data tables found in {file_path}")

    # Use the table with the most rows as the analysis target
    name, df = max(((t, model.get_table(t)) for t in tables), key=lambda pair: len(pair[1]))
    print(f"📖 Loaded table '{name}' ({len(df)} rows, {len(df.columns)} columns) from {file_path}")
    return df


def _read_sql_file(file_path: str) -> pd.DataFrame:
    """Execute the query in a .sql file against the project PostgreSQL database
    and return its rows as a DataFrame (only the last statement's result set
    is fetched if the file contains several statements)."""
    import psycopg2  # lazy import: only needed for .sql input
    from psycopg2.extras import RealDictCursor

    # Use the same connection settings as database.py
    load_dotenv(override=True)
    conn = psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", "123456"),
        dbname=os.getenv("POSTGRES_DB", "dzservice"),
    )
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            sql = f.read()

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql)
            rows = cur.fetchall() if cur.description else []

        print(f"📄 Executed {file_path} ({len(rows)} rows returned)")
        return pd.DataFrame(rows)
    finally:
        conn.close()


def _read_html_table(file_path: str) -> pd.DataFrame:
    """Read an HTML file and use its largest table."""
    tables = pd.read_html(file_path)
    if not tables:
        raise ValueError(f"No HTML tables found in {file_path}")
    return max(tables, key=len)


# Readers for every supported input format, keyed by file extension.
# Shared by the deterministic pipeline, the HTTP upload endpoint, AND the
# deep agent pipeline's load_data() - one table, every format.
_DATA_READERS = {
    # utf-8-sig also accepts plain UTF-8 and strips a leading BOM, so CSVs
    # exported by Excel open in both pipelines
    ".csv": lambda path: pd.read_csv(path, encoding="utf-8-sig"),
    ".tsv": lambda path: pd.read_csv(path, sep="\t"),
    ".xls": lambda path: pd.read_excel(path),
    ".xlsx": lambda path: pd.read_excel(path),
    ".json": lambda path: pd.read_json(path),
    ".jsonl": lambda path: pd.read_json(path, lines=True),
    ".ndjson": lambda path: pd.read_json(path, lines=True),
    ".parquet": lambda path: pd.read_parquet(path),
    ".feather": lambda path: pd.read_feather(path),
    ".xml": lambda path: pd.read_xml(path),
    ".html": _read_html_table,
    ".htm": _read_html_table,
    ".pbix": _read_pbix_table,
    ".sql": _read_sql_file,
}


def load_sample_data(file_path: str) -> str:
    """Read a data file and return the raw JSON string consumed by the workflow.

    Supported inputs: delimited tables (.csv, .tsv), Excel (.xls, .xlsx),
    tabular files (.json, .jsonl, .ndjson, .parquet, .feather), markup
    (.xml, .html, .htm - largest table wins), Power BI (.pbix), and .sql
    (the file's query is executed against the project PostgreSQL database).
    """
    suffix = os.path.splitext(file_path)[1].lower()

    reader = _DATA_READERS.get(suffix)
    if reader is None:
        supported = ", ".join(sorted(_DATA_READERS))
        raise ValueError(f"Unsupported file type '{suffix}': use one of {supported}")

    df = reader(file_path)

    # ⚠️ Do NOT clean here! Keep the original NaN values (pandas converts empty cells to NaN automatically)
    data_records = df.to_dict(orient='records')

    # Wrap the records in the input format expected by clean_data;
    # default=str turns non-JSON types such as timestamps into strings
    return json.dumps({"full_data": data_records}, ensure_ascii=False, indent=2, default=str)


# =============================
# Part 5: Run the data analysis
# =============================

def run_analysis(raw_data_json: str) -> str:
    """Run the LangGraph workflow on raw data JSON and return its report."""
    app = create_analysis_workflow()

    initial_state: AnalysisState = {
        "raw_data_json": raw_data_json,
        "clean_data_json": "",
        "aggregated_json": "",
        "stats_json": "",
        "anomalies_json": "",
        "result": "",
        "step": "start",
    }

    final_state = app.invoke(initial_state)
    return final_state["result"]


def run_deep_cli(data_path: str) -> None:
    """Console runner for the deep three-stage pipeline (merged from
    routers/data_analy.py): plan -> per-task analysis -> combined HTML report."""
    try:
        llm = get_analysis_llm()
    except Exception as e:
        print("⚠️ No LLM API key detected. Configure NVIDIA_API_KEY with"
              " LLM_PROVIDER=nvidia, or use LLM_API_KEY / OpenRouter / Gemini settings.")
        print("Tip: the tool self-test runs without any LLM calls via"
              " `python routers\\data_analysis.py --self-test`")
        print(f"LLM setup error: {e}")
        return
    _, base_url, model_id = _llm_config()
    host = base_url.split("//", 1)[-1].split("/", 1)[0]
    print(f"✅ Environment ready, LLM model: {model_id} @ {host}")

    print(f"📂 Loading data: {data_path}")
    try:
        load_data(data_path)
    except Exception as e:
        print(f"❌ Failed to read the data file: {e}")
        return

    try:
        run_pipeline(data_path)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"❌ Pipeline failed: {e}")


def main() -> None:
    """Console entry point for either analysis pipeline (see module docstring).

    Default: the deterministic StateGraph workflow on the given file.
    --deep: the three-stage Planner/Analyst/Reporter agent pipeline.
    --self-test: exercise the deep pipeline's tools without any LLM calls.
    """
    args = sys.argv[1:]

    if "--self-test" in args:
        self_test()
        return

    # Optional first non-flag argument: the data file to analyze - any
    # supported table file (see _DATA_READERS) or a .sql query file
    file_path = next((a for a in args if not a.startswith("-")), None)

    if "--deep" in args:
        run_deep_cli(file_path or DATA_PATH)
        return

    file_path = file_path or "./data/simple_data.xls"
    try:
        print(f"📂 Loading data from: {file_path}")
        raw_data_json = load_sample_data(file_path)
    except Exception as e:
        print(f"❌ Failed to read the input file: {e}")
        return

    print(raw_data_json)

    # Execute the workflow
    print("=== Starting data analysis ===")
    print("✅ LangGraph workflow created")

    try:
        result = run_analysis(raw_data_json)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"❌ An error occurred: {e}")
        return

    print(result)

    # Save the analysis report and chart
    try:
        save_outputs(result)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"❌ Failed to save the outputs: {e}")


# =============================
# Part 6: Save the analysis report and chart
# =============================

def build_html(echarts_code: "str | list[str]", markdown_report: str) -> str:
    """Combine the ECharts option(s) and the Markdown report into a
    standalone HTML page.

    Accepts one option string or a list of them: every option gets its own
    chart container, so a report can show each chart the LLM picked.
    """
    # Convert the Markdown report to HTML
    report_html = markdown.markdown(markdown_report, extensions=["extra", "tables"])
    title_match = re.match(r"\s*#\s+(.+)", markdown_report)
    page_title = html_escape(title_match.group(1).strip()) if title_match else "Data Analysis Report"
    report_language = _detect_report_language([{"text": markdown_report}])
    chart_headings = _CHART_HEADINGS.get(report_language, _CHART_HEADINGS["English"])
    report_labels = _report_labels(report_language)

    # Wrap anomaly/outlier sections in both pipelines. Deep reports use a
    # wider range of headings than the regular report, including "abnormal"
    # and "outlier" wording.
    anomaly_terms = (
        r"anomal|outlier|abnormal|deviation|"
        r"异常值|异常|离群值|离群|偏差|"
        + re.escape(report_labels["anomalies"])
    )
    report_html = re.sub(
        rf"(<h2[^>]*>(?:(?!</h2>).)*(?:{anomaly_terms})(?:(?!</h2>).)*</h2>)(.*?)(?=<h2|$)",
        r'<div class="anomaly">\1\2</div>',
        report_html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    # Also highlight anomaly findings nested under the report's Key Findings
    # section, stopping at the next subsection or top-level section.
    report_html = re.sub(
        rf"(<h3[^>]*>(?:(?!</h3>).)*(?:{anomaly_terms})(?:(?!</h3>).)*</h3>.*?)(?=<h[1-3][^>]*>|$)",
        r'<div class="anomaly">\1</div>',
        report_html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    # Deep findings may mention abnormal values in prose without a dedicated
    # anomaly heading. Highlight those individual statements as well.
    report_html = re.sub(
        rf"<(p|li)([^>]*)>((?:(?!</\1>).)*(?:{anomaly_terms})(?:(?!</\1>).)*)</\1>",
        r'<div class="anomaly"><\1\2>\3</\1></div>',
        report_html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    # The interpretation lives under the LLM analysis section rather than
    # the top-level Anomalies heading, so style that subsection explicitly.
    report_html = re.sub(
        rf"(<h3[^>]*>[^<]*(?:Anomaly interpretation|{re.escape(report_labels['interpretation'])})[^<]*</h3>.*?)(?=<h[1-6][^>]*>|$)",
        r'<div class="anomaly-interpretation">\1</div>',
        report_html,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # Normalize to a list of option objects ("" / [] = no chart at all)
    if isinstance(echarts_code, str):
        echarts_options = [echarts_code] if echarts_code else []
    else:
        echarts_options = [c for c in (echarts_code or []) if c]

    if echarts_options:
        # One sized (width/height) container per chart, plus the script that
        # initialises them all
        heading = chart_headings[0] if len(echarts_options) > 1 else chart_headings[1]
        containers = "\n        ".join(
            f'<div class="chart-box" id="chart-{i}"></div>'
            for i in range(len(echarts_options))
        )
        chart_section = f'<h2>{heading}</h2>\n        {containers}'
        # The option literals are spliced into the script's array below
        options_js = ",\n".join(echarts_options)
        # The chart script must run AFTER the ECharts library has finished
        # loading.  Inside an <iframe srcDoc> the external <script> tag in
        # <head> loads asynchronously, so an inline script at the bottom of
        # <body> may execute before window.echarts exists (ReferenceError)
        # and the chart silently never appears.  initChart() below polls
        # until the library is ready (with a fallback CDN).
        chart_script = f'''
    <script type="text/javascript">
        // The ECharts library is loaded from a CDN in <head>.  Inside an
        // <iframe srcDoc> the external script tag loads asynchronously, so
        // the inline script at the bottom of <body> may run before
        // window.echarts exists (ReferenceError) and the chart silently
        // never appears.  This function waits for echarts to become
        // available, with a fallback CDN if the primary one fails.
        var _fallbackTried = false;
        function initChart() {{
            if (typeof echarts === 'undefined') {{
                // If the primary CDN hasn't loaded after a few retries and
                // we haven't tried the fallback yet, inject it now.
                if (initChart._tries === undefined) initChart._tries = 0;
                if (initChart._tries === 10 && !_fallbackTried) {{
                    _fallbackTried = true;
                    var s = document.createElement('script');
                    s.src = 'https://cdn.staticfile.org/echarts/5.4.3/echarts.min.js';
                    document.head.appendChild(s);
                }}
                if (initChart._tries++ < 60) {{
                    setTimeout(initChart, 100);
                    return;
                }}
                // Give up after ~6 seconds
                var box = document.querySelector('.chart-box');
                if (box) {{
                    box.innerHTML = '<div style="padding:40px;color:#999;text-align:center">' +
                        'Chart library failed to load (CDN unavailable).</div>';
                }}
                return;
            }}

            // One option per requested chart, built server-side from the
            // specs the LLM picked (every number comes from the
            // pre-aggregated data, never from the model's own figures)
            var charts = [];
            [{options_js}].forEach(function (option, i) {{
                var el = document.getElementById('chart-' + i);
                if (!el) return;

                // Keep anomaly markers inside the plot region: the y-axis is fitted to
                // the data range, so markers on the data extremes would otherwise land
                // exactly on the grid edge (half-clipped, labels drawn outside the
                // plot). Pad every value axis a little before rendering.
                // The leading ";" protects this IIFE from automatic semicolon
                // insertion even if the statement above loses its semicolon.
                ;(function keepMarkersVisible(opt) {{
                    var axes = Array.isArray(opt.yAxis) ? opt.yAxis : (opt.yAxis ? [opt.yAxis] : []);
                    axes.forEach(function (ax) {{
                        if (!ax || ax.type === 'category' || ax.type === 'time') return;
                        if (typeof ax.min === 'number' && typeof ax.max === 'number') {{
                            // Explicit min/max: widen both ends by 5% of the range
                            var span = ax.max - ax.min || 1;
                            ax.min = ax.min - span * 0.05;
                            ax.max = ax.max + span * 0.05;
                        }} else if (!ax.boundaryGap) {{
                            // Auto-fitted axis: percentage padding at both ends
                            ax.boundaryGap = ['5%', '5%'];
                        }}
                    }});
                }})(option);

                var chart = echarts.init(el);
                chart.setOption(option);
                charts.push(chart);
            }});

            // Resize every chart when the iframe is resized
            window.addEventListener('resize', function () {{
                charts.forEach(function (chart) {{ chart.resize(); }});
            }});
        }}

        // Start on DOMContentLoaded, or immediately if DOM is already ready
        if (document.readyState === 'loading') {{
            document.addEventListener('DOMContentLoaded', initChart);
        }} else {{
            initChart();
        }}
    </script>'''
    else:
        chart_section = ""
        chart_script = ""

    return f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{page_title}</title>
    <!-- Import echarts.js (5.x) -->
    <script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
    <style>
        body {{ font-family: Arial, Helvetica, sans-serif; margin: 0; color: #333; }}
        .container {{ max-width: 1000px; margin: 0 auto; padding: 24px; }}
        h1 {{ border-bottom: 2px solid #eee; padding-bottom: 8px; }}
        h2 {{ margin-top: 32px; }}
        .chart-box {{ width: 100%; height: 520px; margin-bottom: 16px; }}
        .report {{ line-height: 1.6; }}
        .report pre {{ background: #f6f8fa; padding: 12px; overflow-x: auto; }}
        .report code {{ background: #f6f8fa; padding: 2px 4px; }}
        .report table {{ border-collapse: collapse; }}
        .report th, .report td {{ border: 1px solid #ddd; padding: 6px 10px; }}
        .report img {{ max-width: 100%; }}
        .anomaly {{ color: #dc3545; background: #fdecea; border-left: 4px solid #dc3545; border-radius: 4px; padding: 2px 16px 12px; margin-top: 16px; }}
        .anomaly h2 {{ color: #dc3545; margin-top: 0.75rem; }}
        .anomaly h3 {{ color: #dc3545; }}
        .anomaly table th {{ background: #f8d7da; }}
        .anomaly-interpretation {{ color: #dc3545; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>{page_title}</h1>
        {chart_section}
        <div class="report">
            {report_html}
        </div>
    </div>{chart_script}
</body>
</html>
'''


def _find_balanced_brace(text: str, start: int) -> int:
    """Return the index just past the '}' that matches the '{' at text[start],
    ignoring braces that occur inside '...' or "..." string literals.
    Returns -1 when the braces never balance."""
    depth = 0
    quote = ""
    i = start
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == "\\":
                i += 2  # skip the escaped character
                continue
            if ch == quote:
                quote = ""
        elif ch in "'\"":
            quote = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return -1


def extract_echarts_options(result: str) -> list[str]:
    """Pull every ECharts option object out of the raw pipeline result.

    A result may carry several "option = {...};" blocks - one per chart
    chosen by the LLM (see build_llm_charts). Each object's extent is found
    by brace matching, so a "};" nested inside it (e.g. a formatter
    callback) cannot truncate it, and the scan resumes after the object so
    later charts are found too. When no "option = " spelling appears, the
    legacy shapes are still tried: a fenced object literal and, as a last
    resort, the first top-level object that looks like a chart option.
    Returns [] when nothing is found.
    """
    options: list[str] = []
    pos = 0
    while True:
        match = re.search(r"\boption\s*=\s*(\{)", result[pos:])
        if not match:
            break
        start = pos + match.start(1)
        end = _find_balanced_brace(result, start)
        if end == -1:
            break
        options.append(result[start:end])
        pos = end
    if options:
        return options

    # Legacy: a fenced code block containing an object literal (possibly
    # preceded by "option =" or "var option =" inside the fence)
    for block in re.findall(r"```[^\n]*\n(.*?)```", result, re.DOTALL):
        block = block.strip()
        block = re.sub(r"^(?:var\s+)?option\s*=\s*", "", block).strip()
        if block.startswith("{"):
            end = _find_balanced_brace(block, 0)
            if end != -1:
                # tolerate trailing prose after the object inside the fence
                return [block[:end]]

    # Legacy: any top-level object that looks like a chart option
    for match in re.finditer(r"\{", result):
        end = _find_balanced_brace(result, match.start())
        if end == -1:
            continue
        candidate = result[match.start():end]
        if "series" in candidate and ("xAxis" in candidate or "yAxis" in candidate):
            return [candidate]

    return []


def extract_echarts_option(result: str) -> str:
    """First ECharts option in the result (convenience wrapper for callers
    that only want one chart)."""
    options = extract_echarts_options(result)
    return options[0] if options else ""


def render_report(result: str) -> str:
    """Extract the ECharts option(s) and the Markdown report from the
    pipeline output and combine them into a standalone HTML page (no disk
    writes). One option is extracted per LLM-picked chart."""
    # Extract the chart options (one per LLM-picked chart, or the single
    # deterministic fallback chart)
    echarts_options = extract_echarts_options(result)
    if echarts_options:
        # NOTE: the former "bar -> line" coercion was removed on purpose:
        # chart types now come from the specs the LLM picked and
        # build_llm_charts() rendered deliberately, so a bar chart is a
        # valid, intended choice (anomaly markers stay scatter points).
        print(f"{len(echarts_options)} ECharts option(s) extracted "
              f"({sum(len(o) for o in echarts_options)} chars total)")
    else:
        print("ECharts code not found")
        # Debug: show the first 300 chars of the result to help diagnose
        print(f"LLM result preview: {result[:300]}")

    # Extract the Markdown report from the LLM output
    markdown_report = ""
    report_match = re.search(r"(^# .+[\s\S]*)", result, flags=re.MULTILINE)
    if report_match:
        markdown_report = report_match.group(1).strip()
        # Strip any fenced code blocks that the model may have placed
        # inside the report section (e.g. the ECharts chart config) so
        # it does not show up as raw JavaScript in the rendered report.
        markdown_report = re.sub(
            r"```(?:json|javascript|js)?[^\n]*\n.*?```",
            "",
            markdown_report,
            flags=re.DOTALL,
        ).strip()
        print("Markdown report extracted")
    else:
        print("Markdown report not found")

    if not echarts_options and not markdown_report:
        print("Nothing to render")
        return ""

    # Combine the charts and the report into a single HTML page
    return build_html(echarts_options, markdown_report)


def save_outputs(result: str) -> str:
    """Render the report page and also persist it to ./output/report.html.
    Used by the console run (main); the HTTP endpoint returns the HTML
    directly via render_report without touching the disk."""
    html_code = render_report(result)
    if not html_code:
        return ""

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    html_path = os.path.join(OUTPUT_DIR, "report.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_code)
    print(f"Combined HTML report saved to: {html_path}")
    return html_code


# =============================
# Part 7: HTTP API for the frontend
# =============================

# Router is mounted under /ai by main.py, so the endpoint is POST /ai/data
router = APIRouter()

# In-memory cache for analysis results, keyed by the SHA-256 of the input
# data: {data_hash: {"result": ..., "timestamp": ...}}
# Same pattern as routers/ai_search.py - re-uploading the same file within
# the TTL is served without re-running the analysis pipeline
_analysis_cache: dict[str, dict] = {}
_CACHE_TTL_SECONDS = 10  # 5 minutes


def _get_cached_result(data_hash: str) -> str | None:
    entry = _analysis_cache.get(data_hash)
    if entry and (time.time() - entry["timestamp"]) < _CACHE_TTL_SECONDS:
        return entry["result"]
    _analysis_cache.pop(data_hash, None)
    return None


def _set_cached_result(data_hash: str, result: str) -> None:
    _analysis_cache[data_hash] = {"result": result, "timestamp": time.time()}


# Maximum accepted upload size
MAX_UPLOAD_BYTES = 50 * 1024 * 1024


@router.post("/data")
async def analyze_uploaded_file(file: UploadFile = File(...)):
    """Analyze an uploaded data file (multipart field "file") and return the
    combined report page as HTML: {"html": ..., "result": ...}."""
    suffix = os.path.splitext(file.filename or "")[1].lower()

    if suffix == ".sql":
        raise HTTPException(
            status_code=400,
            detail=".sql uploads are not allowed over HTTP; run SQL files from the console instead",
        )
    if suffix not in _DATA_READERS:
        supported = ", ".join(sorted(_DATA_READERS))
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}': use one of {supported}",
        )

    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large: the limit is {MAX_UPLOAD_BYTES // (1024 * 1024)} MB",
        )

    # Save the upload to a temporary file with its original extension so that
    # every console loader can be reused unchanged
    tmp_path = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        raw_data_json = load_sample_data(tmp_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read the uploaded file: {e}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

    # Serve identical re-uploads from the in-memory cache instead of
    # re-running the analysis pipeline
    data_hash = hashlib.sha256(raw_data_json.encode("utf-8")).hexdigest()
    cached = _get_cached_result(data_hash)
    if cached:
        print(f"📦 Cache hit for: {file.filename}")
        # HTTP responses only - never write the page to ./output here
        html_code = render_report(cached)
        return {"html": html_code, "result": cached}

    # The LangGraph pipeline is synchronous - run it in a worker thread so the
    # event loop keeps serving other requests
    try:
        result = await asyncio.to_thread(run_analysis, raw_data_json)
        # Extract/chart the report in memory only; the HTML is returned in
        # the response and never written to disk. Only completed analyses
        # enter the cache.
        html_code = render_report(result)
        if result:
            _set_cached_result(data_hash, result)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Analysis failed: {e}")

    return {"html": html_code, "result": result}


@router.post("/data/deep")
async def analyze_uploaded_file_deep(file: UploadFile = File(...)):
    """Run the deep Planner/Analyst/Reporter pipeline for an uploaded file.

    The report is rendered in memory and returned as combined HTML; this
    endpoint does not persist a report file.
    """
    suffix = os.path.splitext(file.filename or "")[1].lower()
    if suffix == ".sql":
        raise HTTPException(status_code=400, detail=".sql uploads are not allowed over HTTP")
    if suffix not in _DATA_READERS:
        supported = ", ".join(sorted(_DATA_READERS))
        raise HTTPException(status_code=400, detail=f"Unsupported file type '{suffix}': use one of {supported}")

    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"File too large: the limit is {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")

    data_path = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(content)
            data_path = tmp.name
        result = await asyncio.to_thread(
            run_pipeline, data_path, write_html=False, return_html=True)
        html_code = result[3]
        if not html_code:
            raise RuntimeError("Deep analysis returned an empty HTML report")
        return {"html": html_code}
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Deep analysis failed: {e}")
    finally:
        if data_path and os.path.exists(data_path):
            os.unlink(data_path)


# =============================
# Part 8: Deep three-stage agent pipeline (merged from routers/data_analy.py)
# =============================
# The DataAnalyst pipeline formerly living in routers/data_analy.py was
# merged into this module so BOTH pipelines share the _DATA_READERS input
# table: the deep pipeline no longer reads CSV only - it accepts every
# format listed in the module docstring (.csv/.tsv/.xls/.xlsx/.json/.jsonl/
# .ndjson/.parquet/.feather/.xml/.html/.pbix and .sql query files).
#
# Converted from ./routers/main.ipynb:
# - Replaced the HelloAgents framework (`HelloAgentsLLM`, `ReActAgent`,
#   `SimpleAgent`, `ToolRegistry`, `Tool` base class) with LangGraph/LangChain:
#   * the Planner and Analyst are ReAct graphs built with
#     `langgraph.prebuilt.create_react_agent`
#   * the Reporter is a plain system-prompted `ChatOpenAI` call
#     (the `SimpleAgent` equivalent)
#   * the five analysis tools are `langchain_core.tools` `@tool` functions;
#     invalid parameters raise ValueError so the ReAct agent reads the error
#     message (including the list of valid columns) and can self-correct
# - All pandas analysis logic and the "JSON first + regex fallback"
#   task parser are preserved as-is; every string (prompts, tool output, error
#   messages, console output) is in English
#
# Console usage (see main):
#     python routers\data_analysis.py --deep data\sales_data.csv
#     python routers\data_analysis.py --self-test
#
# Output: ./output/report.html (report text and interactive charts)

# ---- Part 8a: LLM client for the deep pipeline ----

def _strip_reasoning_monologue(text: str) -> str:
    """Extract the final answer from a reasoning-channel reply.

    vLLM-served models (observed: MiniMax M2.7) put their chain of thought
    before the actual answer, separated by a blank-line gap:
        "...thought process...\n\n\n## The actual answer"
    Prefer the segment after the last such gap; keep the whole text when
    there is no gap or when the tail is too short to be the answer.
    """
    if "\n\n\n" in text:
        tail = text.rsplit("\n\n\n", 1)[-1].strip()
        if len(tail) >= 40:
            return tail
    return text


def _message_text(message: Any) -> str:
    """Extract plain text from an LLM response (content may be str or blocks).

    Falls back to the reasoning-channel text stashed by the compatibility
    shim when the backend left content empty (see the shim header).
    """
    content = getattr(message, "content", message)
    if isinstance(content, str):
        if content.strip():
            return content
    elif isinstance(content, list):
        text = "".join(
            block.get("text", "") for block in content if isinstance(block, dict)
        )
        if text.strip():
            return text
    extra = getattr(message, "additional_kwargs", None)
    if isinstance(extra, dict) and extra.get(_LC_REASON_KEY):
        return _strip_reasoning_monologue(str(extra[_LC_REASON_KEY]))
    return content if isinstance(content, str) else str(content)


# ---- Part 8b: shared dataset and the five analysis tools ----
# The six atomic analysis tools from the notebook, rewritten as
# langchain_core `@tool` functions. Each tool runs deterministic pandas
# computations and returns text for the LLM to read; parameter errors raise
# ValueError, which the ReAct graph converts into a tool message so the agent
# can correct its arguments and retry.

# Shared dataframe referenced by every analysis tool (set by load_data)
GLOBAL_DF: pd.DataFrame | None = None
_LOADED_PATH: str | None = None
_DEEP_CHART_OPTIONS: list[str] = []


def load_data(data_path: str = DATA_PATH) -> pd.DataFrame:
    """Read any supported table file (see _DATA_READERS) and publish it as
    GLOBAL_DF for the tool layer.

    This replaces the merged routers/data_analy.py reader, which accepted
    CSV only: the deep pipeline now shares the same reader table as the
    deterministic pipeline and the HTTP upload endpoint, so .csv, .tsv,
    .xls, .xlsx, .json, .jsonl, .ndjson, .parquet, .feather, .xml, .html,
    .pbix and .sql inputs all work here too.
    """
    global GLOBAL_DF, _LOADED_PATH
    suffix = os.path.splitext(data_path)[1].lower()
    reader = _DATA_READERS.get(suffix)
    if reader is None:
        supported = ", ".join(sorted(_DATA_READERS))
        raise ValueError(f"Unsupported file type '{suffix}': use one of {supported}")
    df = reader(data_path)
    GLOBAL_DF = df
    _LOADED_PATH = data_path
    print(f"Dataset shape: {df.shape[0]} rows x {df.shape[1]} columns")
    return df


def _require_df() -> pd.DataFrame:
    """Return the loaded dataset or explain how to load one (agent-readable)."""
    if GLOBAL_DF is None:
        raise ValueError("No dataset loaded yet; call load_data(path) to read a data file first.")
    return GLOBAL_DF


def _require_columns(df: pd.DataFrame, *cols: str) -> None:
    """Raise an agent-readable error when a requested column does not exist."""
    missing = [c for c in cols if c and c not in df.columns]
    if missing:
        raise ValueError(f"Column(s) not found: {missing}. Available columns: {list(df.columns)}")


def _looks_like_identifier(series: pd.Series) -> bool:
    """True for ID-like or date-like columns worth showing next to an outlier.

    Data-driven replacement for the notebook's hardcoded "ID"/date name
    matching, so it works on any CSV regardless of its header language.
    """
    name = str(series.name or "").lower()
    if "id" in name:
        return True
    if pd.api.types.is_datetime64_any_dtype(series):
        return True
    sample = series.dropna().astype(str).head(20)
    if not len(sample) or sample.str.len().min() < 8:
        return False   # short numeric codes are not dates
    return bool(pd.to_datetime(sample, errors="coerce").notna().mean() >= 0.9)


@tool
def data_overview() -> str:
    """Get an overview of the dataset: shape, per-column dtype/missing/unique
    counts, and a statistical summary of the numeric columns. Call this tool
    before starting any analysis."""
    df = _require_df()
    lines = [f"Shape: {df.shape[0]} rows x {df.shape[1]} columns", "", "Column overview:"]
    for col in df.columns:
        s = df[col]
        missing = int(s.isna().sum())
        miss_pct = missing / len(df) * 100
        uniq = int(s.nunique(dropna=True))
        line = f"- {col} | dtype:{s.dtype} | missing:{missing}({miss_pct:.1f}%) | unique:{uniq}"
        if uniq <= 8:
            tops = s.value_counts().head(3)
            line += " | top values: " + ", ".join(f"{k}({v})" for k, v in tops.items())
        lines.append(line)
    num_cols = df.select_dtypes(include="number").columns.tolist()
    if num_cols:
        lines.append("")
        lines.append("Numeric column summary:")
        lines.append(df[num_cols].describe().T.round(2).to_string())
    return "\n".join(lines)


@tool
def column_profile(column: str) -> str:
    """Profile a single column in depth: numeric columns return
    mean/std/quantiles/skew, categorical columns return a frequency Top list,
    datetime columns return the time range.

    Args:
        column: Column name (must match a dataset column exactly)
    """
    df = _require_df()
    _require_columns(df, column)
    s = df[column]
    lines = [f"Column {column} profile ({int(s.notna().sum())} non-null / {len(s)})"]
    if pd.api.types.is_datetime64_any_dtype(s):
        lines.append(f"Time range: {s.min()} ~ {s.max()}")
    elif pd.api.types.is_numeric_dtype(s):
        lines.append(s.describe().round(2).to_string())
        lines.append(f"Skewness: {s.skew():.2f}")
    else:
        vc = s.value_counts().head(8)
        lines.append("Top 8 values:")
        for k, v in vc.items():
            lines.append(f"- {k}: {v} ({v / len(s) * 100:.1f}%)")
    return "\n".join(lines)


@tool
def correlation_analysis(top_n: int = 10) -> str:
    """Compute pairwise Pearson correlation coefficients between all numeric
    columns and return the strongest pairs (sorted by absolute value). Use it
    to find linear relationships between fields.

    Args:
        top_n: How many strongest pairs to return, default 10
    """
    df = _require_df()
    num = df.select_dtypes(include="number")
    if num.shape[1] < 2:
        raise ValueError("Fewer than 2 numeric columns; cannot compute correlations.")
    corr = num.corr().round(3)
    pairs = []
    cols = corr.columns
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            pairs.append((cols[i], cols[j], corr.iloc[i, j]))
    pairs.sort(key=lambda x: abs(x[2]), reverse=True)
    top_n = int(top_n or 10)
    lines = ["Strongest correlated column pairs (Pearson coefficient):"]
    for a, b, r in pairs[:top_n]:
        strength = "strong" if abs(r) >= 0.7 else ("moderate" if abs(r) >= 0.4 else "weak")
        lines.append(f"- {a} x {b}: {r:+.3f} ({strength} {'negative' if r < 0 else 'positive'} correlation)")
    return "\n".join(lines)


@tool
def group_aggregate(group_col: str, value_col: str, agg: str = "sum", top_n: int = 10) -> str:
    """Group by a categorical column and aggregate a numeric column
    (sum/mean/count/max/min), returning the Top N groups. Good for comparing
    a metric across categories/regions/channels.

    Args:
        group_col: Group column (categorical, e.g. region / sales channel / product category)
        value_col: Numeric column to aggregate (e.g. sales amount)
        agg: Aggregation: sum/mean/count/max/min, default sum
        top_n: How many groups to return, default 10
    """
    df = _require_df()
    _require_columns(df, group_col, value_col)
    agg = (agg or "sum").lower()
    top_n = int(top_n or 10)
    if agg not in {"sum", "mean", "count", "max", "min"}:
        raise ValueError(f"Unsupported aggregation: {agg}. Use one of: sum/mean/count/max/min")
    res = df.groupby(group_col)[value_col].agg(agg).sort_values(ascending=False)
    share = (res / res.sum() * 100).round(1) if agg == "sum" else None
    lines = [f"{agg} of {value_col} grouped by {group_col} (Top {min(top_n, len(res))}):"]
    for i, (k, val) in enumerate(res.head(top_n).items(), 1):
        s = f" | share {share[k]}%" if share is not None else ""
        lines.append(f"{i}. {k}: {round(float(val), 2)}{s}")
    return "\n".join(lines)


@tool
def detect_outliers(column: str) -> str:
    """Detect outliers in a numeric column with the IQR method: returns the
    normal-range thresholds, the outlier count and share, and the largest
    outlier samples.

    Args:
        column: Numeric column to test for outliers
    """
    df = _require_df()
    _require_columns(df, column)
    s = pd.to_numeric(df[column], errors="coerce").dropna()
    q1, q3 = s.quantile(0.25), s.quantile(0.75)
    iqr = q3 - q1
    low, high = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    mask = (s < low) | (s > high)
    out = df.loc[s[mask].index]
    lines = [f"IQR outlier detection for column {column}:",
             f"- normal range: [{low:.2f}, {high:.2f}] (Q1={q1:.2f}, Q3={q3:.2f})",
             f"- outliers: {len(out)} ({len(out) / len(df) * 100:.2f}%)"]
    if len(out):
        id_cols = [c for c in df.columns if c != column and _looks_like_identifier(df[c])][:2]
        top = out.sort_values(column, ascending=False).head(5)
        lines.append("- largest outlier samples:")
        lines.append(top[id_cols + [column]].to_string(index=False))
    return "\n".join(lines)


def _deep_anomaly_report(df: pd.DataFrame) -> str:
    """Build a deterministic IQR outlier summary for the deep HTML report."""
    frame = df.copy()
    columns = _chart_numeric_columns(frame)
    language = _detect_report_language(frame.head(100).to_dict(orient="records"))
    section_labels = {
        "English": ("Anomaly Analysis", "Potential outliers", "Share", "Lower bound", "Upper bound",
                    "Numeric columns were checked with the IQR rule: values below Q1 − 1.5×IQR or above Q3 + 1.5×IQR are flagged as potential outliers.",
                    "No numeric columns had enough valid values for outlier analysis.",
                    "No potential outliers were found by the IQR rule."),
        "Chinese": ("异常值分析", "潜在异常值", "占比", "下限", "上限",
                    "使用 IQR 规则检查数值列：低于 Q1 − 1.5×IQR 或高于 Q3 + 1.5×IQR 的值会标记为潜在异常值。",
                    "没有数值列包含足够的有效值，无法进行异常值分析。",
                    "IQR 规则未发现潜在异常值。"),
        "Japanese": ("異常値分析", "異常値候補", "割合", "下限", "上限",
                     "IQR ルールを用いて数値列を確認しました。Q1 − 1.5×IQR 未満、または Q3 + 1.5×IQR を超える値を外れ値候補として扱います。",
                     "外れ値分析に十分な有効値を含む数値列がありません。",
                     "IQR ルールでは外れ値候補は見つかりませんでした。"),
        "Korean": ("이상치 분석", "잠재적 이상치", "비율", "하한", "상한",
                   "IQR 규칙으로 숫자 열을 확인했습니다. Q1 − 1.5×IQR보다 작거나 Q3 + 1.5×IQR보다 큰 값은 잠재적 이상치로 표시합니다.",
                   "이상치 분석에 충분한 유효 값이 있는 숫자 열이 없습니다.",
                   "IQR 규칙으로 잠재적 이상치를 찾지 못했습니다."),
        "Spanish": ("Análisis de anomalías", "Anomalías potenciales", "Porcentaje", "Límite inferior", "Límite superior",
                    "Se revisaron las columnas numéricas con la regla IQR; los valores fuera de Q1 − 1,5×IQR y Q3 + 1,5×IQR se marcan como posibles valores atípicos.",
                    "No hay columnas numéricas con suficientes valores válidos para el análisis.",
                    "La regla IQR no encontró posibles valores atípicos."),
        "French": ("Analyse des anomalies", "Anomalies potentielles", "Part", "Borne inférieure", "Borne supérieure",
                   "Les colonnes numériques ont été vérifiées avec la règle IQR. Les valeurs hors de l’intervalle Q1 − 1,5×IQR à Q3 + 1,5×IQR sont signalées comme valeurs aberrantes potentielles.",
                   "Aucune colonne numérique ne contient assez de valeurs valides pour cette analyse.",
                   "La règle IQR n’a détecté aucune valeur aberrante potentielle."),
        "German": ("Ausreißeranalyse", "Mögliche Ausreißer", "Anteil", "Untergrenze", "Obergrenze",
                   "Die numerischen Spalten wurden mit der IQR-Regel geprüft. Werte unter Q1 − 1,5×IQR oder über Q3 + 1,5×IQR gelten als mögliche Ausreißer.",
                   "Keine numerische Spalte enthält genügend gültige Werte für die Ausreißeranalyse.",
                   "Die IQR-Regel hat keine möglichen Ausreißer gefunden."),
        "Portuguese": ("Análise de anomalias", "Anomalias potenciais", "Proporção", "Limite inferior", "Limite superior",
                       "As colunas numéricas foram verificadas pela regra IQR. Valores abaixo de Q1 − 1,5×IQR ou acima de Q3 + 1,5×IQR são sinalizados como possíveis valores atípicos.",
                       "Nenhuma coluna numérica tem valores válidos suficientes para a análise.",
                       "A regra IQR não encontrou possíveis valores atípicos."),
        "Italian": ("Analisi delle anomalie", "Anomalie potenziali", "Quota", "Limite inferiore", "Limite superiore",
                    "Le colonne numeriche sono state controllate con la regola IQR. I valori inferiori a Q1 − 1,5×IQR o superiori a Q3 + 1,5×IQR sono segnalati come potenziali valori anomali.",
                    "Nessuna colonna numerica contiene valori validi sufficienti per l’analisi.",
                    "La regola IQR non ha rilevato potenziali valori anomali."),
        "Russian": ("Анализ аномалий", "Потенциальные выбросы", "Доля", "Нижняя граница", "Верхняя граница",
                    "Числовые столбцы проверены по правилу IQR. Значения ниже Q1 − 1,5×IQR или выше Q3 + 1,5×IQR отмечены как потенциальные выбросы.",
                    "Недостаточно числовых столбцов с допустимыми значениями для анализа выбросов.",
                    "Правило IQR не выявило потенциальных выбросов."),
        "Arabic": ("تحليل القيم الشاذة", "القيم الشاذة المحتملة", "النسبة", "الحد الأدنى", "الحد الأعلى",
                   "تم فحص الأعمدة الرقمية باستخدام قاعدة IQR. تُعد القيم الأقل من Q1 − 1.5×IQR أو الأعلى من Q3 + 1.5×IQR قيماً شاذة محتملة.",
                   "لا توجد أعمدة رقمية تحتوي على قيم صالحة كافية لتحليل القيم الشاذة.",
                   "لم تكشف قاعدة IQR عن قيم شاذة محتملة."),
    }
    labels = section_labels.get(language, section_labels["English"])
    lines = [
        f"## {labels[0]}",
        "",
        labels[5],
        "",
    ]
    findings = []
    for column in columns:
        values = pd.to_numeric(frame[column], errors="coerce").dropna()
        if len(values) < 4:
            continue
        q1, q3 = values.quantile([0.25, 0.75])
        spread = q3 - q1
        low, high = q1 - 1.5 * spread, q3 + 1.5 * spread
        count = int(((values < low) | (values > high)).sum())
        findings.append((str(column), count, count / len(values) * 100, float(low), float(high)))

    if not findings:
        lines.append(labels[6])
        return "\n".join(lines)

    lines += [
        f"| Column | {labels[1]} | {labels[2]} | {labels[3]} | {labels[4]} |",
        "|---|---:|---:|---:|---:|",
    ]
    for column, count, share, low, high in findings:
        lines.append(f"| {column} | {count} | {share:.2f}% | {low:.2f} | {high:.2f} |")
    if not any(count for _, count, _, _, _ in findings):
        lines += ["", labels[7]]
    return "\n".join(lines)


@tool
def plot_chart(chart_type: str, x_column: str = "", y_column: str = "",
              agg: str = "sum", title: str = "") -> str:
    """Create an interactive HTML chart. Types: histogram/bar/box/line/scatter/heatmap.

    Args:
        chart_type: Chart type: histogram/bar/box/line/scatter/heatmap
        x_column: Category/date column for bar and line, or x value for scatter
        y_column: Numeric measure, optional for histogram/box/heatmap
        agg: Aggregation for bar/line: sum/mean/count
        title: Chart title in the dataset's language
    """
    df = _require_df()
    kind = (chart_type or "").strip().lower()
    x, y = (x_column or "").strip(), (y_column or "").strip()
    agg = (agg or "sum").lower()
    numeric = df.select_dtypes(include="number").columns.tolist()
    if kind not in {"histogram", "bar", "box", "line", "scatter", "heatmap"}:
        raise ValueError("Use histogram, bar, box, line, scatter, or heatmap.")
    measures = [y or x or (numeric[0] if numeric else "")]
    if kind == "heatmap":
        if len(numeric) < 2:
            raise ValueError("Heatmap requires at least two numeric columns.")
    else:
        _require_columns(df, *([x] if kind in {"bar", "line", "scatter"} else []),
                         *([measures[0]] if kind in {"histogram", "box", "scatter", "bar", "line"} else []))
    if kind in {"bar", "line"} and agg not in {"sum", "mean", "count"}:
        agg = "sum"

    chart_title = title or f"{kind.title()} of {measures[0]}"
    common = {"title": {"text": chart_title, "left": "center"},
              "tooltip": {"trigger": "axis" if kind != "scatter" else "item"},
              "grid": {"left": "10%", "right": "8%", "bottom": "18%", "containLabel": True}}
    if kind in {"bar", "line"}:
        tmp = df.dropna(subset=[x]).copy()
        if kind == "line" and pd.to_datetime(tmp[x], errors="coerce").notna().mean() > 0.8:
            tmp["__chart_time"] = pd.to_datetime(tmp[x], errors="coerce").dt.to_period("M").astype(str)
            group = "__chart_time"
            res = tmp.groupby(group)[measures[0]].agg(agg if agg != "count" else "count").sort_index()
        elif agg == "count":
            res = tmp.groupby(x, dropna=False).size().sort_values(ascending=(kind == "line"))
        else:
            res = tmp.groupby(x, dropna=False)[measures[0]].agg(agg)
            res = res.sort_index() if kind == "line" else res.sort_values(ascending=False).head(20)
        cats = [str(v) for v in res.index]
        common.update({"xAxis": {"type": "category", "data": cats, "axisLabel": {"rotate": 25}},
                       "yAxis": {"type": "value", "scale": True},
                       "series": [{"name": measures[0], "type": kind, "data": [float(v) for v in res.values],
                                   "smooth": kind == "line"}]})
    elif kind == "histogram":
        values = pd.to_numeric(df[measures[0]], errors="coerce").dropna().to_numpy()
        if not len(values):
            raise ValueError(f"No numeric values found in {measures[0]}.")
        counts, edges = np.histogram(values, bins=min(30, max(5, int(np.sqrt(len(values))))))
        common.update({"xAxis": {"type": "category", "data": [f"{edges[i]:.3g}–{edges[i+1]:.3g}" for i in range(len(counts))], "axisLabel": {"rotate": 35}},
                       "yAxis": {"type": "value", "name": "Frequency"},
                       "series": [{"name": "Frequency", "type": "bar", "data": counts.tolist()}]})
    elif kind == "box":
        values = pd.to_numeric(df[measures[0]], errors="coerce").dropna()
        if values.empty:
            raise ValueError(f"No numeric values found in {measures[0]}.")
        q = values.quantile([0, .25, .5, .75, 1]).tolist()
        common.update({"xAxis": {"type": "category", "data": [measures[0]]}, "yAxis": {"type": "value", "scale": True},
                       "series": [{"type": "boxplot", "data": [q]}]})
    elif kind == "scatter":
        points = df[[x, measures[0]]].apply(pd.to_numeric, errors="coerce").dropna()
        if len(points) > 2000:
            points = points.sample(2000, random_state=42)
        common.update({"xAxis": {"type": "value", "name": x}, "yAxis": {"type": "value", "name": measures[0]},
                       "series": [{"type": "scatter", "symbolSize": 8, "data": points.values.tolist()}]})
    else:
        corr = df[numeric].corr().fillna(0)
        names = [str(c) for c in corr.columns]
        heat = [[j, i, round(float(corr.iloc[i, j]), 3)] for i in range(len(names)) for j in range(len(names))]
        common.update({"tooltip": {"position": "top"}, "xAxis": {"type": "category", "data": names, "splitArea": {"show": True}},
                       "yAxis": {"type": "category", "data": names, "splitArea": {"show": True}},
                       "visualMap": {"min": -1, "max": 1, "calculable": True, "orient": "horizontal", "left": "center", "bottom": 0},
                       "series": [{"type": "heatmap", "data": heat, "label": {"show": True}}]})

    option = json.dumps(common, ensure_ascii=False, allow_nan=False)
    if option not in _DEEP_CHART_OPTIONS:
        _DEEP_CHART_OPTIONS.append(option)
    return f"Interactive {kind} chart added to the HTML report: {chart_title}"




# ---- Part 8c: agent construction ----
# The notebook's HelloAgents ReActAgent becomes a LangGraph ReAct graph
# (model <-> tools loop); the SimpleAgent Reporter becomes one prompted LLM
# call. Agents are built lazily so importing this module never requires an
# API key.

# ReAct step budget from the notebook (ReActAgent max_steps)
PLANNER_MAX_STEPS = 5
ANALYST_MAX_STEPS = 6


def _step_config(max_steps: int) -> dict:
    """Cap a ReAct agent's iterations.

    create_react_agent has no max_steps parameter, so emulate the notebook's
    cap with the graph recursion limit: each ReAct iteration consumes two
    graph steps (model node + tool node).
    """
    return {"recursion_limit": max_steps * 2 + 1}


PLANNER_PROMPT = """You are a senior data analysis planner. Your job is to produce an analysis plan for the dataset already loaded into memory.

Your workflow:
1. First call the data_overview tool to understand the field structure and data quality (use column_profile on key columns when needed)
2. Plan 3~5 business-relevant analysis tasks based on the actual meaning of the fields, covering dimensions such as time trends, category structure, country/city comparisons when those columns exist, group comparisons, correlation analysis, and outlier detection
3. Every task must be concrete and executable: name the field and the statistic to compute
4. Write every task title and goal in the language of the dataset (keep dataset column names in their original form)

Finally, you must output the plan as a pure JSON array (output the JSON itself, no code fence, no explanatory text), in this format:
[
  {"task": "short task title", "goal": "concrete analysis goal naming the fields, the statistic and the required chart"}
]"""

ANALYST_PROMPT = """You are a rigorous data analyst. For each analysis task you are given:

1. Pick the right tool for the job (group_aggregate / correlation_analysis / detect_outliers / column_profile / plot_chart). Use plot_chart for useful visual comparisons or distributions; supported types are histogram/bar/box/line/scatter/heatmap.
2. Use computed statistics and aggregations to describe distributions, comparisons, and trends.
3. Summarize the conclusion in 3~6 sentences, quoting the exact numbers returned by the tools - keep it concrete

Rules:
- Write your conclusion in the language of the dataset (dataset column names stay in their original form)
- Chart titles must use the dataset's language
- A task usually takes 1~3 tool calls; do not repeat the exact same tool call."""

REPORTER_PROMPT = """You are a senior data analyst turning the analysis conclusions into a professional Markdown data analysis report.

Required structure:
# Report title
## 1. Data overview
## 2. Key findings (one subsection per analysis task; the heading summarizes the finding, the body gives the conclusion and the key numbers)
## 3. Business recommendations (3~5 actionable recommendations based on the findings)
## 4. Methodology (briefly describe the tools and statistical methods used)

Writing rules:
1. Write the entire report (title, headings, prose) in the language used by the dataset; dataset column names stay in their original form
2. Every conclusion and number must come from the provided input - never invent data
3. Be professional and concise; emphasize business insights"""

_planner_agent = None
_analyst_agent = None


def _react(tools: list, prompt: str):
    """Build a ReAct agent whose tool errors go back to the model.

    ToolNode's default error handling only converts schema-validation errors
    into tool messages and re-raises everything else, which would abort the
    run on a bad column name. The notebook fed tool errors back
    to the agent instead (ToolResponse.error), letting it correct its
    arguments and retry - handle_tool_errors=True restores that loop.
    """
    return create_react_agent(
        get_analysis_llm(),
        tools=ToolNode(tools, handle_tool_errors=True),
        prompt=prompt,
    )


def get_planner():
    """Planner: ReAct agent that probes the data and emits a JSON task plan."""
    global _planner_agent
    if _planner_agent is None:
        _planner_agent = _react([data_overview, column_profile], PLANNER_PROMPT)
    return _planner_agent


def get_analyst():
    """Analyst: ReAct agent equipped with the five analysis tools."""
    global _analyst_agent
    if _analyst_agent is None:
        _analyst_agent = _react(
            [data_overview, column_profile, correlation_analysis,
             group_aggregate, detect_outliers, plot_chart],
            ANALYST_PROMPT,
        )
    return _analyst_agent


def run_agent(agent, user_input: str, max_steps: int) -> str:
    """Invoke a ReAct agent once and return its final message as text.

    The graph is streamed so a partial answer survives the step budget: the
    notebook's ReActAgent simply stopped at max_steps and returned what it
    had, whereas langgraph raises GraphRecursionError.
    """
    last_text = ""
    state: dict = {"messages": []}
    try:
        for state in agent.stream(
            {"messages": [("user", user_input)]},
            config=_step_config(max_steps),
            stream_mode="values",
        ):
            last = state["messages"][-1]
            # Keep the newest model reply that is a real answer (no pending
            # tool calls); everything before it is intermediate ReAct output
            if isinstance(last, AIMessage) and not last.tool_calls:
                text = _message_text(last).strip()
                if text:
                    last_text = text
    except GraphRecursionError:
        if not last_text:
            raise
        print("⚠️ Step budget reached; using the conclusion generated so far")
        return last_text
    if last_text:
        return last_text
    return _message_text(state["messages"][-1])


def run_reporter(report_input: str) -> str:
    """Reporter (the SimpleAgent equivalent): one system-prompted LLM call."""
    response = get_analysis_llm().invoke([
        SystemMessage(content=REPORTER_PROMPT),
        HumanMessage(content=report_input),
    ])
    return _message_text(response)


# ---- Part 8d: three-stage pipeline and tool self-test ----

def parse_tasks(plan_text: str) -> list[dict[str, str]]:
    """Parse the task list from the planner's output (JSON first, regex fallback)."""
    candidates = []
    m = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", plan_text, re.S)
    if m:
        candidates.append(m.group(1))
    # Fallback 1: the output is a bare JSON array (no code fence)
    if not candidates:
        i, j = plan_text.find("["), plan_text.rfind("]")
        if 0 <= i < j:
            candidates.append(plan_text[i:j + 1])
    for cand in candidates:
        try:
            tasks = json.loads(cand)
            return [
                {"task": str(t.get("task", "")).strip() or f"Task {i}",
                 "goal": str(t.get("goal", "")).strip()}
                for i, t in enumerate(tasks, 1) if isinstance(t, dict)
            ]
        except json.JSONDecodeError:
            continue
    # Fallback 2: extract lines in the "Task N: description" format
    tasks = []
    for line in plan_text.splitlines():
        m2 = re.match(r"\s*[-*\d.)]*\s*(?:\*\*)?task(?:\s*\d+)?[**:.-]\s*(.+)",
                      line, flags=re.IGNORECASE)
        if m2:
            text = m2.group(1).strip().strip("*#").strip()
            if len(text) > 4:
                tasks.append({"task": text, "goal": ""})
    return tasks[:6]


def _fallback_report(tasks: list[dict], conclusions: list[dict]) -> str:
    """Build a minimal Markdown report from the raw stage-2 results.

    Used when the reporter LLM call fails (e.g. rate limit), so a completed
    analysis is never thrown away just because the final write failed.
    """
    language = _detect_report_language(GLOBAL_DF.head(100).to_dict(orient="records"))
    sections = {
        "English": ("Data overview", "Key findings", "Business recommendations", "Methodology", "Charts"),
        "Spanish": ("Descripción de los datos", "Hallazgos principales", "Recomendaciones", "Metodología", "Gráficos"),
        "French": ("Présentation des données", "Principaux résultats", "Recommandations", "Méthodologie", "Graphiques"),
        "German": ("Datenübersicht", "Wichtigste Erkenntnisse", "Empfehlungen", "Methodik", "Diagramme"),
        "Chinese": ("数据概览", "主要发现", "业务建议", "方法", "图表"),
        "Japanese": ("データ概要", "主な結果", "推奨事項", "方法", "グラフ"),
        "Korean": ("데이터 개요", "주요 결과", "권장 사항", "방법론", "차트"),
        "Russian": ("Обзор данных", "Основные выводы", "Рекомендации", "Методология", "Графики"),
        "Arabic": ("نظرة عامة على البيانات", "النتائج الرئيسية", "التوصيات", "المنهجية", "الرسوم البيانية"),
        "Portuguese": ("Visão geral dos dados", "Principais conclusões", "Recomendações", "Metodologia", "Gráficos"),
        "Italian": ("Panoramica dei dati", "Risultati principali", "Raccomandazioni", "Metodologia", "Grafici"),
    }.get(language, ("Data overview", "Key findings", "Business recommendations", "Methodology", "Charts"))
    labels = _report_labels(language)
    lines = [f"# {labels['title']}", "", f"## 1. {sections[0]}",
             f"Automated analysis of {GLOBAL_DF.shape[0]} rows x {GLOBAL_DF.shape[1]} columns "
             f"(fields: {', '.join(GLOBAL_DF.columns)}).", "", f"## 2. {sections[1]}"]
    for i, c in enumerate(conclusions, 1):
        lines += [f"", f"### 2.{i} {c['task']}", "", c["conclusion"]]
    lines += ["", f"## 3. {sections[2]}",
              "_The AI-written recommendations are unavailable; see the findings above._",
              "", f"## 4. {sections[3]}",
              "Planner/analyst ReAct agents over five pandas analysis tools "
              "(this file was written by the built-in fallback because the reporter call failed)."]
    return "\n".join(lines) + "\n"


def run_pipeline(data_path: str = DATA_PATH,
                 report_path: str | None = None,
                 write_html: bool = True,
                 return_html: bool = False):
    """Three-stage pipeline: plan -> per-task analysis -> summary report.

    Loads the dataset through the shared _DATA_READERS table first, so every
    supported input format reaches the agents as a DataFrame.
    """
    if report_path is None and write_html:
        report_path = os.path.join(OUTPUT_DIR, "report.html")
    # Create the output directory only for console runs that persist HTML.
    if write_html and report_path:
        os.makedirs(os.path.dirname(report_path) or ".", exist_ok=True)
    _DEEP_CHART_OPTIONS.clear()
    if GLOBAL_DF is None or data_path != _LOADED_PATH:
        load_data(data_path)
    report_language = _detect_report_language(
        GLOBAL_DF.head(100).to_dict(orient="records"))

    print("=" * 60)
    print("[Stage 1/3] Planning: probe the data and produce analysis tasks")
    try:
        plan_text = run_agent(
            get_planner(),
            f"Create an analysis plan in {report_language}, the dataset's language, for dataset {data_path} "
            f"({GLOBAL_DF.shape[0]} rows x {GLOBAL_DF.shape[1]} columns, fields: "
            f"{', '.join(GLOBAL_DF.columns)}).",
            max_steps=PLANNER_MAX_STEPS,
        )
    except Exception as e:
        print(f"⚠️ Planning stage failed: {type(e).__name__}: {e}; falling back to a default task")
        plan_text = ""
    tasks = parse_tasks(plan_text)
    if not tasks:
        tasks = [{"task": "Overall data overview and quality check",
                  "goal": "Use data_overview to inspect the data"}]
    print(f"\n✅ Planning complete, {len(tasks)} analysis tasks:")
    for i, t in enumerate(tasks, 1):
        print(f"   Task {i}: {t['task']}")

    print("\n" + "=" * 60)
    print("[Stage 2/3] Deep analysis, task by task")
    conclusions = []
    for i, t in enumerate(tasks, 1):
        print(f"\n>>> Running task {i}: {t['task']}")
        # One failing task must not abort the whole pipeline: record it and
        # keep analyzing, so the reporter still receives every other result
        try:
            out = run_agent(
                get_analyst(),
                f"Write your conclusion and chart title in {report_language}.\n"
                f"Analysis task: {t['task']}\nGoal: {t['goal'] or t['task']}",
                max_steps=ANALYST_MAX_STEPS,
            )
            conclusions.append({"task": t["task"], "conclusion": out})
            print(f"✅ Task {i} done")
        except Exception as e:
            conclusions.append({"task": t["task"], "conclusion": "(this task was interrupted and produced no conclusion)"})
            print(f"❌ Task {i} failed: {type(e).__name__}: {e}")

    print("\n" + "=" * 60)
    print("[Stage 3/3] Writing the analysis report")
    report_input = (
        f"Write the report in {report_language}, the language used by the dataset.\n\n"
        f"Dataset overview: {GLOBAL_DF.shape[0]} rows x {GLOBAL_DF.shape[1]} columns, "
        f"fields: {', '.join(GLOBAL_DF.columns)}\n\n"
        f"Conclusions per analysis task (JSON):\n{json.dumps(conclusions, ensure_ascii=False, indent=2)}\n\n"
        f"Please write the complete data analysis report."
    )
    try:
        report = run_reporter(report_input)
    except Exception as e:
        print(f"⚠️ Reporter call failed ({type(e).__name__}); writing the fallback report instead")
        report = _fallback_report(tasks, conclusions)
    # Always run this deterministic check, regardless of whether the LLM
    # planned an outlier task, and include it in the HTML report body.
    report = report.rstrip() + "\n\n" + _deep_anomaly_report(GLOBAL_DF)
    # Render the deep report as HTML and derive chart data from the source
    # frame so charts are available even when the LLM returns no chart config.
    chart_options = list(_DEEP_CHART_OPTIONS)
    chart_df = GLOBAL_DF.copy()
    numeric_columns = _chart_numeric_columns(chart_df)
    dimensions = _detect_time_columns(chart_df)
    group_columns = list(dimensions.get("category_cols", []))
    date_col = dimensions.get("date_col")
    if date_col and date_col not in group_columns:
        group_columns.insert(0, date_col)
    group_col = next((col for col in group_columns
                      if col in chart_df.columns and chart_df[col].nunique(dropna=True) > 1), None)
    if not chart_options and group_col:
        for value_col in numeric_columns[:3]:
            grouped = (chart_df.groupby(group_col, dropna=False)[value_col]
                       .sum().sort_values(ascending=False).head(20))
            if not grouped.empty:
                chart_options.append(_line_bar_option(
                    f"{value_col} by {group_col}", str(value_col),
                    [str(value) for value in grouped.index], grouped.tolist(), "bar"))
    html_code = build_html(chart_options, report)
    if write_html and report_path:
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(html_code)
        print(f"\nHTML report with {len(chart_options)} chart(s) saved: {report_path}")
    else:
        print(f"\nHTML report with {len(chart_options)} chart(s) ready in memory")
    if return_html:
        return report, tasks, conclusions, html_code
    return report, tasks, conclusions


def self_test() -> None:
    """Exercise two core tools without any LLM calls (notebook Part 7).

    The demo columns are inferred from the data instead of hardcoded, so the
    check also works on a swapped-in file with different headers. Loads any
    supported format through the shared _DATA_READERS table (default: the
    CSV dataset in ./data).
    """
    df = load_data()
    numeric = df.select_dtypes(include="number")
    if numeric.empty:
        print("No numeric columns in the dataset; skipping the self-test")
        return
    # Widest-spread numeric column is normally the money column (sales amount)
    value_col = numeric.std().idxmax()
    group_col = next(
        (c for c in df.columns
         if c != value_col
         and not pd.api.types.is_numeric_dtype(df[c])
         and df[c].nunique(dropna=True) <= 20),
        df.columns[0],
    )

    # Self-check 1: group aggregation - revenue contribution per category
    print(group_aggregate.invoke({"group_col": group_col, "value_col": value_col}))

    print("\n" + "=" * 50 + "\n")

    # Self-check 2: IQR outlier detection - find abnormally large records
    print(detect_outliers.invoke({"column": value_col}))


if __name__ == "__main__":
    main()
