"""
실시간 금융 대시보드 — Streamlit + yfinance
KOSPI, S&P 500, Nikkei 225, 금·은, 원/달러·원/엔
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

# ---------------------------------------------------------------------------
# 자산 정의 (Yahoo Finance 티커)
# ---------------------------------------------------------------------------
ASSETS: list[dict[str, Any]] = [
    {
        "category": "주가 지수",
        "name": "KOSPI",
        "ticker": "^KS11",
        "unit": "pt",
        "decimals": 2,
    },
    {
        "category": "주가 지수",
        "name": "S&P 500",
        "ticker": "^GSPC",
        "unit": "pt",
        "decimals": 2,
    },
    {
        "category": "주가 지수",
        "name": "Nikkei 225",
        "ticker": "^N225",
        "unit": "pt",
        "decimals": 2,
    },
    {
        "category": "귀금속",
        "name": "국제 금 (선물)",
        "ticker": "GC=F",
        "unit": "USD/oz",
        "decimals": 2,
    },
    {
        "category": "귀금속",
        "name": "국제 은 (선물)",
        "ticker": "SI=F",
        "unit": "USD/oz",
        "decimals": 3,
    },
    {
        "category": "환율",
        "name": "원/달러",
        "ticker": "KRW=X",
        "unit": "KRW/USD",
        "decimals": 2,
    },
    {
        "category": "환율",
        "name": "원/엔",
        "ticker": "JPYKRW=X",
        "unit": "KRW/JPY",
        "decimals": 4,
    },
]

def _fi_get(fast_info: Any, key: str, default: Any = None) -> Any:
    if hasattr(fast_info, "get"):
        return fast_info.get(key, default)
    return getattr(fast_info, key, default)


PERIOD_OPTIONS = {
    "1일 (5분)": ("1d", "5m"),
    "5일 (15분)": ("5d", "15m"),
    "1개월 (1시간)": ("1mo", "1h"),
    "3개월 (1일)": ("3mo", "1d"),
    "6개월 (1일)": ("6mo", "1d"),
    "1년 (1일)": ("1y", "1d"),
}


@st.cache_data(ttl=60, show_spinner=False)
def fetch_snapshot(tickers: tuple[str, ...]) -> pd.DataFrame:
    """현재가·전일대비 등 스냅샷."""
    yf_tickers = yf.Tickers(" ".join(tickers))
    rows: list[dict[str, Any]] = []

    for asset in ASSETS:
        sym = asset["ticker"]
        try:
            t = yf_tickers.tickers.get(sym) or yf.Ticker(sym)
            fi = t.fast_info
            price = _fi_get(fi, "last_price") or _fi_get(fi, "lastPrice") or _fi_get(
                fi, "regular_market_price"
            ) or _fi_get(fi, "regularMarketPrice")
            prev = (
                _fi_get(fi, "previous_close")
                or _fi_get(fi, "previousClose")
                or _fi_get(fi, "regular_market_previous_close")
                or _fi_get(fi, "regularMarketPreviousClose")
                or price
            )

            if price is None:
                hist = t.history(period="5d", interval="1d")
                if hist.empty:
                    raise ValueError("가격 없음")
                close = hist["Close"].dropna()
                price = float(close.iloc[-1])
                prev = float(close.iloc[-2]) if len(close) >= 2 else price
            else:
                price = float(price)
                prev = float(prev) if prev else price

            change = price - prev
            change_pct = (change / prev * 100) if prev else 0.0

            rows.append(
                {
                    "구분": asset["category"],
                    "항목": asset["name"],
                    "티커": sym,
                    "현재가": price,
                    "전일종가": prev,
                    "변동": change,
                    "변동률(%)": change_pct,
                    "단위": asset["unit"],
                    "decimals": asset["decimals"],
                }
            )
        except Exception:
            rows.append(
                {
                    "구분": asset["category"],
                    "항목": asset["name"],
                    "티커": sym,
                    "현재가": None,
                    "전일종가": None,
                    "변동": None,
                    "변동률(%)": None,
                    "단위": asset["unit"],
                    "decimals": asset["decimals"],
                }
            )

    return pd.DataFrame(rows)


@st.cache_data(ttl=120, show_spinner=False)
def fetch_history(ticker: str, period: str, interval: str) -> pd.DataFrame:
    """차트용 시계열."""
    df = yf.download(
        ticker,
        period=period,
        interval=interval,
        progress=False,
        auto_adjust=True,
    )
    if df.empty:
        return df
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df[["Close"]].dropna()


def format_price(value: float | None, decimals: int) -> str:
    """가격·지수 등 부호 없는 절대값."""
    if value is None or pd.isna(value):
        return "—"
    return f"{value:,.{decimals}f}"


def format_signed_number(value: float | None, decimals: int) -> str:
    """변동액 — 양수는 반드시 '+' 접두."""
    if value is None or pd.isna(value):
        return "—"
    return f"{value:+,.{decimals}f}"


def format_signed_percent(value: float | None, decimals: int = 2) -> str:
    """변동률 — 양수는 반드시 '+' 접두."""
    if value is None or pd.isna(value):
        return "—"
    return f"{value:+.{decimals}f}%"


def change_direction(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "none"
    if value > 0:
        return "up"
    if value < 0:
        return "down"
    return "flat"


COLOR_UP = "#e74c3c"
COLOR_DOWN = "#3498db"
COLOR_FLAT = "#95a5a6"
BG_UP = "rgba(231, 76, 60, 0.18)"
BG_DOWN = "rgba(52, 152, 219, 0.18)"
BG_FLAT = "rgba(149, 165, 166, 0.12)"


def signed_cell_style(value: float | None) -> str:
    """표 셀: 상승 빨강, 하락 파랑."""
    direction = change_direction(value)
    if direction == "up":
        return f"color: {COLOR_UP}; font-weight: 600"
    if direction == "down":
        return f"color: {COLOR_DOWN}; font-weight: 600"
    return f"color: {COLOR_FLAT}"


def signed_badge_style(value: float | None) -> str:
    """카드 배지: 상승 빨강 배경/글자, 하락 파랑 배경/글자."""
    direction = change_direction(value)
    if direction == "up":
        return (
            f"color: {COLOR_UP}; background-color: {BG_UP}; "
            "font-weight: 700; border: 1px solid rgba(231, 76, 60, 0.35);"
        )
    if direction == "down":
        return (
            f"color: {COLOR_DOWN}; background-color: {BG_DOWN}; "
            "font-weight: 700; border: 1px solid rgba(52, 152, 219, 0.35);"
        )
    return (
        f"color: {COLOR_FLAT}; background-color: {BG_FLAT}; "
        "font-weight: 600; border: 1px solid rgba(149, 165, 166, 0.35);"
    )


def render_summary_card(
    label: str,
    price: float | None,
    change_pct: float | None,
    unit: str,
    decimals: int,
) -> None:
    """한눈에 보기 — 한국식 상승(빨강)/하락(파랑) 카드."""
    price_text = format_price(price, decimals)
    delta_text = format_signed_percent(change_pct)
    badge_css = signed_badge_style(change_pct)
    st.markdown(
        f"""
        <div style="
            border: 1px solid rgba(128, 128, 128, 0.25);
            border-radius: 10px;
            padding: 14px 12px;
            min-height: 118px;
            background: rgba(255, 255, 255, 0.02);
        ">
            <div style="font-size: 0.82rem; color: #888; margin-bottom: 6px;">{label}</div>
            <div style="font-size: 1.35rem; font-weight: 700; line-height: 1.2;">{price_text}</div>
            <div style="
                {badge_css}
                display: inline-block;
                margin-top: 8px;
                padding: 4px 10px;
                border-radius: 6px;
                font-size: 0.95rem;
            ">{delta_text}</div>
            <div style="font-size: 0.75rem; color: #888; margin-top: 8px;">{unit}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def build_display_table(snapshot: pd.DataFrame) -> pd.DataFrame:
    """표시용 테이블 — 변동·변동률은 부호 포함 문자열."""
    records: list[dict[str, str]] = []
    for _, row in snapshot.iterrows():
        dec = int(row["decimals"])
        records.append(
            {
                "구분": str(row["구분"]),
                "항목": str(row["항목"]),
                "현재가": format_price(row["현재가"], dec),
                "전일종가": format_price(row["전일종가"], dec),
                "변동": format_signed_number(row["변동"], dec),
                "변동률(%)": format_signed_percent(row["변동률(%)"]),
                "단위": str(row["단위"]),
            }
        )
    return pd.DataFrame(records)


def style_display_table(display_df: pd.DataFrame, snapshot: pd.DataFrame) -> Any:
    """변동·변동률: 각 값의 부호에 따라 빨강/파랑."""
    changes = snapshot["변동"].to_numpy()
    pcts = snapshot["변동률(%)"].to_numpy()

    def row_styles(row: pd.Series) -> list[str]:
        idx = row.name
        styles: list[str] = []
        for col in display_df.columns:
            if col == "변동":
                styles.append(signed_cell_style(changes[idx]))
            elif col == "변동률(%)":
                styles.append(signed_cell_style(pcts[idx]))
            else:
                styles.append("")
        return styles

    return display_df.style.apply(row_styles, axis=1)


def make_sparkline(df: pd.DataFrame, color: str) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=df["Close"],
            mode="lines",
            line=dict(color=color, width=2),
            fill="tozeroy",
            fillcolor="rgba(52, 152, 219, 0.12)",
        )
    )
    fig.update_layout(
        height=220,
        margin=dict(l=40, r=20, t=30, b=40),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(showgrid=False, title=""),
        yaxis=dict(showgrid=True, gridcolor="rgba(128,128,128,0.2)", title=""),
        showlegend=False,
        hovermode="x unified",
    )
    return fig


def main() -> None:
    st.set_page_config(
        page_title="실시간 금융 대시보드",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.title("📊 실시간 금융 대시보드")
    st.caption(
        "KOSPI · S&P 500 · Nikkei 225 · 금·은 · 원/달러 · 원/엔 — "
        "데이터: Yahoo Finance (yfinance)"
    )

    with st.sidebar:
        st.header("설정")
        period_label = st.selectbox(
            "차트 기간",
            list(PERIOD_OPTIONS.keys()),
            index=2,
        )
        period, interval = PERIOD_OPTIONS[period_label]
        refresh_sec = st.slider("자동 새로고침 (초)", 30, 300, 60, step=30)
        auto_refresh = st.toggle("자동 새로고침", value=True)
        if st.button("지금 새로고침", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

        st.divider()
        st.markdown(
            "**참고**\n"
            "- 시장 휴장 시 마지막 체결가가 표시됩니다.\n"
            "- 금·은은 COMEX 선물(GC=F, SI=F) 기준입니다.\n"
            "- 원/달러: `KRW=X`, 원/엔: `JPYKRW=X`"
        )

    tickers = tuple(a["ticker"] for a in ASSETS)

    with st.spinner("시세 불러오는 중…"):
        snapshot = fetch_snapshot(tickers)

    now_utc = datetime.now(timezone.utc)
    st.info(
        f"마지막 업데이트: {now_utc.astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')} "
        f"(자동 새로고침: {refresh_sec}초)"
    )

    # --- 요약 카드 (한국식: 상승 빨강 + '+', 하락 파랑) ---
    st.subheader("한눈에 보기")
    cols = st.columns(len(ASSETS))
    for i, (_, row) in enumerate(snapshot.iterrows()):
        with cols[i]:
            render_summary_card(
                label=str(row["항목"]),
                price=row["현재가"],
                change_pct=row["변동률(%)"],
                unit=str(row["단위"]),
                decimals=int(row["decimals"]),
            )

    # --- 표 ---
    st.subheader("실시간 시세 표")
    display_df = build_display_table(snapshot)
    st.dataframe(
        style_display_table(display_df, snapshot),
        use_container_width=True,
        hide_index=True,
    )
    st.caption(
        "한국식 표기: 상승(+) 빨강 · 하락(-) 파랑 · 보합/없음 회색 "
        "(양수 변동·변동률 앞에 '+' 표시)"
    )

    # --- 차트 ---
    st.subheader("차트")
    chart_colors = {
        "KOSPI": "#E74C3C",
        "S&P 500": "#3498DB",
        "Nikkei 225": "#9B59B6",
        "국제 금 (선물)": "#F1C40F",
        "국제 은 (선물)": "#BDC3C7",
        "원/달러": "#2ECC71",
        "원/엔": "#1ABC9C",
    }

    tab_names = [a["name"] for a in ASSETS]
    tabs = st.tabs(tab_names)

    for tab, asset in zip(tabs, ASSETS):
        with tab:
            hist = fetch_history(asset["ticker"], period, interval)
            if hist.empty:
                st.warning(f"{asset['name']} 데이터를 불러오지 못했습니다.")
                continue

            color = chart_colors.get(asset["name"], "#3498DB")
            fig = make_sparkline(hist, color)
            fig.update_layout(title=f"{asset['name']} ({asset['unit']}) — {period_label}")
            st.plotly_chart(fig, use_container_width=True)

            col1, col2, col3 = st.columns(3)
            last = float(hist["Close"].iloc[-1])
            high = float(hist["Close"].max())
            low = float(hist["Close"].min())
            dec = asset["decimals"]
            col1.metric("현재", format_price(last, dec))
            col2.metric("기간 고가", format_price(high, dec))
            col3.metric("기간 저가", format_price(low, dec))

    # --- 전체 비교 (정규화) ---
    st.subheader("지수·환율 비교 (기간 시작 = 100)")
    norm_frames: list[pd.Series] = []
    for asset in ASSETS:
        if asset["category"] == "귀금속":
            continue
        h = fetch_history(asset["ticker"], period, interval)
        if h.empty:
            continue
        base = float(h["Close"].iloc[0])
        if base == 0:
            continue
        norm_frames.append((h["Close"] / base * 100).rename(asset["name"]))

    if norm_frames:
        combined = pd.concat(norm_frames, axis=1).dropna(how="any")
        if not combined.empty:
            fig_cmp = go.Figure()
            for col in combined.columns:
                fig_cmp.add_trace(
                    go.Scatter(
                        x=combined.index,
                        y=combined[col],
                        mode="lines",
                        name=col,
                    )
                )
            fig_cmp.update_layout(
                height=400,
                margin=dict(l=40, r=20, t=40, b=40),
                xaxis_title="",
                yaxis_title="지수 (100 = 기간 시작)",
                hovermode="x unified",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            )
            st.plotly_chart(fig_cmp, use_container_width=True)

    st.divider()
    st.caption(
        "본 화면은 투자 참고용이며, Yahoo Finance 데이터 지연·오류가 있을 수 있습니다."
    )

    if auto_refresh:
        time.sleep(refresh_sec)
        st.rerun()


if __name__ == "__main__":
    main()
