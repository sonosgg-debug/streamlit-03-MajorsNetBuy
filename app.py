import streamlit as st
import io
import pandas as pd
import datetime
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os

from data_loader import (
    setup_krx_auth,
    fetch_daily_net_purchases_series,
    get_nearest_business_day,
    is_krx_trading_day
)
from screener import StockScreener

# 페이지 설정
st.set_page_config(
    page_title="한국 증시 메이저 수급 스크리너",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    /* 전체 배경 및 폰트 */
    .stApp {
        background-color: #0f172a;
        color: #f8fafc;
        font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
    }

    /* Streamlit 고정 상단 헤더 배경 투명화 */
    header[data-testid="stHeader"] {
        background: transparent !important;
    }

    /* 메인 컨테이너 패딩 조절 */
    .main .block-container,
    [data-testid="stMainBlockContainer"],
    .block-container {
        padding-top: 2.0rem !important;
        padding-bottom: 3.5rem !important;
    }

    /* 사이드바 스타일링 */
    section[data-testid="stSidebar"], [data-testid="stSidebar"] {
        background-color: #1e293b !important;
        border-right: 1px solid #334155 !important;
    }
    section[data-testid="stSidebar"] h1,
    section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] h3 {
        color: #f8fafc !important;
        -webkit-text-fill-color: #f8fafc !important;
    }

    /* 헤더 및 타이틀 색상 (#8AB4F8) */
    h1, .app-main-title {
        color: #8AB4F8 !important;
        font-size: 2.0rem !important;
        font-weight: 800 !important;
        letter-spacing: -0.5px;
    }

    h2, h3, h4 {
        color: #f8fafc !important;
        font-weight: 700 !important;
    }

    /* Primary button style */
    .stButton button[kind="primary"],
    .stButton > button[kind="primary"],
    section[data-testid="stSidebar"] button[kind="primary"] {
        background-color: #2563eb !important;
        color: #ffffff !important;
        border: none !important;
        font-weight: 600 !important;
        border-radius: 6px !important;
        transition: all 0.2s ease !important;
    }
    .stButton button[kind="primary"]:hover,
    .stButton > button[kind="primary"]:hover,
    section[data-testid="stSidebar"] button[kind="primary"]:hover {
        background-color: #1d4ed8 !important;
        box-shadow: 0 0 10px rgba(37, 99, 235, 0.4) !important;
    }

    /* 다운로드 버튼 공통 통일 스타일 */
    div[data-testid="stDownloadButton"] > button,
    .stDownloadButton > button {
        background-color: #334155 !important;
        color: #f8fafc !important;
        border: 1px solid #475569 !important;
        border-radius: 6px !important;
        font-size: 0.875rem !important;
        font-weight: 500 !important;
        height: 38px !important;
        min-height: 38px !important;
        max-height: 38px !important;
        line-height: 36px !important;
        padding: 0 16px !important;
        display: inline-flex !important;
        align-items: center !important;
        justify-content: center !important;
        text-align: center !important;
        transition: all 0.2s ease-in-out !important;
        box-sizing: border-box !important;
    }
    div[data-testid="stDownloadButton"] > button:hover,
    .stDownloadButton > button:hover {
        background-color: #475569 !important;
        border-color: #38bdf8 !important;
        color: #ffffff !important;
        box-shadow: 0 0 10px rgba(56, 189, 248, 0.25) !important;
    }
    div[data-testid="stDownloadButton"] > button:active,
    .stDownloadButton > button:active {
        background-color: #1e293b !important;
        border-color: #0284c7 !important;
    }
    div[data-testid="stDownloadButton"] > button p,
    div[data-testid="stDownloadButton"] > button span,
    .stDownloadButton > button p,
    .stDownloadButton > button span {
        font-size: 0.875rem !important;
        font-weight: 500 !important;
        color: inherit !important;
        line-height: inherit !important;
        margin: 0 !important;
        padding: 0 !important;
    }
    .section-title {
        font-size: 1.25rem;
        font-weight: 700;
        color: #8AB4F8;
        margin-top: 1.2rem;
        margin-bottom: 0.6rem;
    }
    .sub-section-title {
        font-size: 1.0rem;
        font-weight: 700;
        color: #8AB4F8;
        margin-top: 1.2rem;
        margin-bottom: 0.5rem;
    }
    /* 주 분석 수급 주체 표시 뱃지 */
    .investor-badge {
        display: inline-flex;
        align-items: center;
        font-size: 0.84rem;
        font-weight: 600;
        color: #38bdf8;
        background-color: rgba(56, 189, 248, 0.12);
        border: 1px solid rgba(56, 189, 248, 0.35);
        padding: 0.2rem 0.65rem;
        border-radius: 20px;
        vertical-align: middle;
    }
    /* 엑셀 다운로드 버튼 우측 정렬 */
    .stDownloadButton {
        display: flex;
        justify-content: flex-end;
    }

    /* =========================================================
       사이드바 접기(<<) 및 펼치기(>>) 버튼 항상 표시 및 시인성/대비 강화
       ========================================================= */
    /* 1. 사이드바가 열려 있을 때 접기 버튼 (<<) 상시 표시 */
    [data-testid="stSidebarCollapseButton"] {
        visibility: visible !important;
        opacity: 1 !important;
        display: inline-flex !important;
    }
    
    [data-testid="stSidebarCollapseButton"] button {
        visibility: visible !important;
        opacity: 1 !important;
        background-color: #1e293b !important;       /* 진한 네이비 배경 */
        border: 1.5px solid #38bdf8 !important;     /* 선명한 스카이블루 테두리로 상자 명확화 */
        border-radius: 8px !important;
        width: 38px !important;
        height: 38px !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.4), 0 0 6px rgba(56, 189, 248, 0.2) !important;
        transition: all 0.2s ease !important;
    }
    
    /* 상자 내부의 << 아이콘(Material Icon span/svg/문자)을 순백색으로 강제하여 상자와 극명한 대비 구현 */
    [data-testid="stSidebarCollapseButton"] button *,
    [data-testid="stSidebarCollapseButton"] span,
    [data-testid="stSidebarCollapseButton"] [data-testid="stIconMaterial"],
    [data-testid="stSidebarCollapseButton"] svg {
        color: #ffffff !important;
        fill: #ffffff !important;
        opacity: 1 !important;
        visibility: visible !important;
        font-size: 1.35rem !important;
        font-weight: 700 !important;
    }
    
    /* 호버(PC) 및 터치 시 반전 효과 */
    [data-testid="stSidebarCollapseButton"] button:hover {
        background-color: #38bdf8 !important;
        border-color: #38bdf8 !important;
    }
    [data-testid="stSidebarCollapseButton"] button:hover * {
        color: #0f172a !important;
        fill: #0f172a !important;
    }

    /* 2. 사이드바 헤더 영역 패딩 및 정렬 보정 */
    [data-testid="stSidebarHeader"] {
        padding-top: 0.5rem !important;
        padding-bottom: 0.5rem !important;
    }

    /* 3. 사이드바가 닫혔을 때 다시 여는 버튼 (>>) 시인성 강화 */
    [data-testid="stSidebarCollapsedControl"] {
        visibility: visible !important;
        opacity: 1 !important;
    }
    
    [data-testid="stSidebarCollapsedControl"] button {
        background-color: #1e293b !important;
        border: 1.5px solid #38bdf8 !important;
        border-radius: 8px !important;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.4), 0 0 6px rgba(56, 189, 248, 0.2) !important;
    }
    
    [data-testid="stSidebarCollapsedControl"] button *,
    [data-testid="stSidebarCollapsedControl"] span,
    [data-testid="stSidebarCollapsedControl"] [data-testid="stIconMaterial"],
    [data-testid="stSidebarCollapsedControl"] svg {
        color: #38bdf8 !important;
        fill: #38bdf8 !important;
        opacity: 1 !important;
        visibility: visible !important;
        font-size: 1.35rem !important;
    }
</style>
""", unsafe_allow_html=True)

# 메인 타이틀 영역 (Multi-Indicator Ensemble 표준 일체화)
st.markdown(
    "<h1 style='text-align: center; font-size: 2.0rem; font-weight: 800; line-height: 1.35; margin: 0 0 8px 0; color: #8AB4F8 !important;'>"
    "한국 증시 외국인/기관 수급 스크리너"
    "</h1>",
    unsafe_allow_html=True
)

st.markdown(
    "<div style='text-align: center; font-size: 0.95rem; color: #cbd5e1; margin-bottom: 20px; line-height: 1.5;'>"
    "최근 N일 동안의 외국인 및 기관 순매수 데이터 분석, 수급 집중 유망 종목 발굴 프로그램"
    "</div>",
    unsafe_allow_html=True
)

st.markdown("<hr style='border: 0; height: 1px; background-color: #334155; margin: 18px 0 22px 0;'>", unsafe_allow_html=True)

# 세션 상태 초기화 (결과 캐싱용)
if "screened_df" not in st.session_state:
    st.session_state.screened_df = None
if "auth_status" not in st.session_state:
    st.session_state.auth_status = False

# ================= SIDEBAR =================
with st.sidebar:
    st.markdown(
        """
        <div style='padding: 2px 0 12px 0;'>
            <div style='font-size: 1.25rem; font-weight: 700; color: #f8fafc; letter-spacing: -0.01em; display: flex; align-items: center; gap: 8px;'>
                <span>⚙️</span> 스크리닝 조건 설정
            </div>
            <div style='font-size: 0.82rem; color: #94a3b8; margin-top: 4px; line-height: 1.4;'>
                KRX 세션 연동 및 외국인/기관 수급 분석 조건을 설정합니다.
            </div>
        </div>
        <hr style='border: 0; height: 1px; background-color: #334155; margin: 10px 0 16px 0;'>
        """,
        unsafe_allow_html=True
    )

    krx_id = st.text_input("KRX ID", value=os.getenv("KRX_ID", ""))
    krx_pw = st.text_input("KRX Password", type="password", value=os.getenv("KRX_PW", ""))

    if st.button("🔑 세션 연결 및 로그인", use_container_width=True):
        with st.spinner("KRX 로그인 세션 설정 중..."):
            success = setup_krx_auth(krx_id, krx_pw)
            st.session_state.auth_status = success
            if success:
                st.success("✅ KRX 로그인 연동 성공!")
            else:
                st.error("❌ 로그인 실패 (아이디/비번 혹은 IP 차단 상태 확인)")

    st.markdown("<hr style='border: 0; height: 1px; background-color: #334155; margin: 16px 0;'>", unsafe_allow_html=True)
    st.subheader("⚙️ 스크리닝 필터 설정")

    # 시장 구분
    market_choice = st.radio(
        "🏛️ 시장 선택",
        ["코스피 (KOSPI)", "코스닥 (KOSDAQ)", "전체 (ALL)"],
        index=0,
        horizontal=True
    )
    market_map = {
        "코스피 (KOSPI)": "KOSPI",
        "코스닥 (KOSDAQ)": "KOSDAQ",
        "전체 (ALL)": "ALL",
        "KOSPI": "KOSPI",
        "KOSDAQ": "KOSDAQ",
        "ALL": "ALL"
    }
    market = market_map.get(market_choice, "KOSPI")

    # 시가총액/거래대금 기본 필터
    min_mkt_cap = st.number_input("최소 시가총액 (억 원)", min_value=10, max_value=500000, value=1000, step=100)
    min_turnover = st.number_input("최소 5일 평균 거래대금 (억 원)", min_value=0, max_value=50000, value=20, step=5)

    # 수급 주체 및 세부 필터
    st.subheader("🎯 수급 상세 조건")
    target_investor = st.selectbox(
        "주 분석 수급 주체", 
        ["연기금", "투신", "사모", "금융투자", "기관합계", "외국인", "외국인+연기금", "외국인+투신+연기금"], 
        index=6
    )

    accum_days = st.slider("누적 수급 계산 기간 N (일)", min_value=1, max_value=60, value=5)
    min_accum_intensity = st.slider("시총 대비 누적 매집 비율 (%)", min_value=0.01, max_value=5.0, value=0.2, step=0.05)

    # Z-Score 조건
    min_zscore = st.slider("당일 수급 Z-Score 최소치", min_value=-1.0, max_value=5.0, value=1.5, step=0.1)
    zscore_lookback = st.slider("Z-Score 산출 룩백 기간 M (일)", min_value=5, max_value=60, value=20)

    # 양매수 필수 여부
    require_dual = st.checkbox("당일 외인+기관 양매수 필수", value=False)

# 로그인 안된 상태에서 메인 화면 경고 안내
if not st.session_state.auth_status:
    st.warning("⚠️ KRX 로그인 세션이 연동되지 않았습니다. 분석 시작 전 사이드바에서 로그인을 진행해 주세요.")

# ================= MAIN PAGE =================
col_date, col_btn = st.columns([3, 1])

with col_date:
    # 조회 날짜 선택 (기본값: 가장 최근 마감 완료된 실제 거래일)
    default_bday_str = get_nearest_business_day()
    default_date = datetime.datetime.strptime(default_bday_str, "%Y%m%d").date()
    selected_date = st.date_input("스크리닝 기준일", default_date)
    target_date_str = selected_date.strftime("%Y%m%d")

    # 선택된 날짜가 거래소 휴장일인지 검사 및 안내
    actual_target_bday = get_nearest_business_day(target_date_str)
    if not is_krx_trading_day(target_date_str):
        act_date_fmt = datetime.datetime.strptime(actual_target_bday, "%Y%m%d").strftime("%Y-%m-%d")
        st.info(f"💡 선택하신 기준일({selected_date.strftime('%Y-%m-%d')})은 증시 휴장일(공휴일/주말)입니다. 가장 최근 거래일인 **{act_date_fmt}** 데이터로 자동 보정하여 분석합니다.")

with col_btn:
    st.markdown("<br>", unsafe_allow_html=True)
    run_button = st.button("🔍 스크리닝 시작", type="primary", use_container_width=True)

if run_button:
    if not st.session_state.auth_status:
        st.error("분석을 시작하기 위해 먼저 사이드바에서 KRX 로그인을 완료해 주십시오.")
    else:
        with st.spinner("KRX 데이터를 로드하고 지표를 계산 중입니다. 캐시가 없는 날짜는 시간이 다소 소요될 수 있습니다..."):
            try:
                # 휴장일일 경우 직전 실제 거래일로 안전하게 적용
                target_bday = actual_target_bday
                screener = StockScreener(target_date=target_bday, market=market)
                df_result = screener.screen(
                    min_market_cap_krw=min_mkt_cap * 100000000,
                    min_turnover_5d_krw=min_turnover * 100000000,
                    accum_days=accum_days,
                    target_investor=target_investor,
                    min_accum_intensity=min_accum_intensity,
                    min_zscore=min_zscore,
                    zscore_lookback_days=zscore_lookback,
                    require_dual_buy=require_dual
                )
                st.session_state.screened_df = df_result
                st.session_state.screened_investor = target_investor
                st.session_state.screened_market = market
                st.session_state.screened_date = datetime.datetime.strptime(target_bday, "%Y%m%d").date()
                st.session_state.is_mkt_cap_empty = screener.df_mkt_cap.empty
                st.session_state.was_holiday_adjusted = (actual_target_bday != target_date_str)
                st.session_state.original_date_str = selected_date.strftime("%Y-%m-%d")
            except Exception as e:
                st.error(f"스크리닝 실행 중 에러가 발생했습니다: {e}")

# 스크리닝 결과 표시
if st.session_state.screened_df is not None:
    df_res = st.session_state.screened_df
    current_investor = st.session_state.get("screened_investor", target_investor)
    current_market = st.session_state.get("screened_market", market)
    current_date = st.session_state.get("screened_date", selected_date)
    is_mkt_cap_empty = st.session_state.get("is_mkt_cap_empty", False)
    was_holiday_adjusted = st.session_state.get("was_holiday_adjusted", False)
    original_date_str = st.session_state.get("original_date_str", "")
    
    if was_holiday_adjusted:
        st.info(f"💡 선택하셨던 일자({original_date_str})는 거래소 휴장일이므로, 가장 최근 정상 거래일인 **{current_date.strftime('%Y-%m-%d')}** 기준으로 스크리닝을 진행했습니다.")
        
    if df_res.empty:
        st.markdown(
            f'<div class="section-title" style="display: flex; align-items: center; flex-wrap: wrap; gap: 8px;">'
            f'<span>스크리닝 결과 (총 0개 종목)</span>'
            f'<span class="investor-badge">🎯 주 분석 수급 주체: {current_investor}</span>'
            f'</div>', 
            unsafe_allow_html=True
        )
        if is_mkt_cap_empty:
            st.warning("⚠️ 해당 기준일의 시장 데이터(시가총액/주가)를 가져오지 못했습니다. 사이드바에서 KRX 로그인 상태를 다시 확인하시거나 다른 거래일을 선택해 보세요.")
        else:
            st.info(f"선택하신 주 분석 수급 주체({current_investor}) 조건에 부합하는 종목이 없습니다. 필터 임계치를 조절해 보세요.")
    else:
        # Excel 다운로드 기능 (사전 생성)
        market_suffixes = {
            "ALL": "ALL",
            "KOSPI": "KS",
            "KOSDAQ": "KQ"
        }
        market_suffix = market_suffixes.get(current_market, "ALL")
        
        investor_codes = {
            "연기금": "11",
            "투신": "12",
            "사모": "13",
            "금융투자": "14",
            "기관합계": "15",
            "외국인": "21",
            "외국인+연기금": "98",
            "외국인+투신+연기금": "99"
        }
        investor_code = investor_codes.get(current_investor, "00")
        
        formatted_date = current_date.strftime("%Y-%m-%d")
        excel_filename = f"MajorsNetBuy-{market_suffix}-{investor_code}-{formatted_date}.xlsx"
        
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            df_res.to_excel(writer, sheet_name='ScreenerResult', index=True)
            
            worksheet = writer.sheets['ScreenerResult']
            max_row = worksheet.max_row
            max_col = worksheet.max_column
            
            # 1. 1행 (헤더) 자동 필터 적용 (오름차순/내림차순 토글)
            from openpyxl.utils import get_column_letter
            worksheet.auto_filter.ref = f"A1:{get_column_letter(max_col)}{max_row}"
            
            # 2. 1행 (헤더) 바탕색 및 폰트 설정
            from openpyxl.styles import PatternFill, Font, Alignment
            header_fill = PatternFill(start_color="DCE6F1", end_color="DCE6F1", fill_type="solid")  # 연한 파란색
            header_font = Font(name="Malgun Gothic", bold=True, size=11)
            
            for col_idx in range(1, max_col + 1):
                cell = worksheet.cell(row=1, column=col_idx)
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = Alignment(horizontal="center", vertical="center")
                
            # 3. 데이터 셀 서식 지정 (C열 가운데 정렬 & 소수점 자릿수 포맷 설정)
            for row_idx in range(2, max_row + 1):
                # C열 (시장) 가운데 정렬
                worksheet.cell(row=row_idx, column=3).alignment = Alignment(horizontal="center", vertical="center")
                
                # E, F열 (시가총액, 거래대금): 소수점 1자리
                for col_idx in [5, 6]:
                    worksheet.cell(row=row_idx, column=col_idx).number_format = "0.0"
                    
                # G ~ M열 (누적/당일 수급 및 ZScore 등): 소수점 2자리
                for col_idx in range(7, 14):
                    worksheet.cell(row=row_idx, column=col_idx).number_format = "0.00"

            # 4. 열 너비 자동 조절 (동적 기준)
            for col in worksheet.columns:
                max_len = 0
                col_letter = get_column_letter(col[0].column)
                for cell in col:
                    val_str = str(cell.value or '')
                    # 한글 등 멀티바이트 문자는 길이를 2로 가중치 부여
                    byte_len = sum([2 if ord(c) > 127 else 1 for c in val_str])
                    if byte_len > max_len:
                        max_len = byte_len
                worksheet.column_dimensions[col_letter].width = max(max_len + 3, 12)
                
        excel_data = excel_buffer.getvalue()
        
        # 타이틀과 엑셀 다운로드 버튼을 같은 라인에 배치 (다운로드 버튼은 오른쪽 끝에 정렬)
        col_title, col_btn = st.columns([8, 2], vertical_alignment="bottom")
        with col_title:
            st.markdown(
                f'<div class="section-title" style="display: flex; align-items: center; flex-wrap: wrap; gap: 8px;">'
                f'<span>스크리닝 결과 (총 {len(df_res)}개 종목)</span>'
                f'<span class="investor-badge">🎯 주 분석 수급 주체: {current_investor}</span>'
                f'</div>', 
                unsafe_allow_html=True
            )
            st.caption(f"💡 기준일: **{formatted_date}** | 시장: **{market_suffix}** | 주 분석 수급 주체: **{current_investor}**")
        with col_btn:
            st.download_button(
                label="📥 엑셀 파일 다운로드",
                data=excel_data,
                file_name=excel_filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        
        # 데이터프레임 렌더링
        st.dataframe(df_res, use_container_width=True)
        
        st.markdown("---")
        st.markdown('<div class="section-title">개별 종목 수급 상세 분석 (Plotly 시각화)</div>', unsafe_allow_html=True)
        
        # 종목 선택
        tickers_list = [f"{ticker} | {row['종목명']}" for ticker, row in df_res.iterrows()]
        selected_ticker_str = st.selectbox("수급 흐름을 분석할 종목을 선택하세요", tickers_list)
        
        if selected_ticker_str:
            selected_ticker = selected_ticker_str.split(" | ")[0]
            selected_name = selected_ticker_str.split(" | ")[1]
            
            with st.spinner(f"{selected_name}의 상세 수급 시계열 로딩 중..."):
                # 최근 60 영업일간의 일일 데이터 수집
                # 넉넉하게 90일 전부터 데이터 조회하여 평일(영업일) 기준 60일 분량 슬라이싱
                start_dt = (datetime.datetime.strptime(target_date_str, "%Y%m%d") - datetime.timedelta(days=90)).strftime("%Y%m%d")
                df_series = fetch_daily_net_purchases_series(start_dt, target_date_str, selected_ticker)
                
                if df_series.empty:
                    st.warning("상세 시계열 데이터를 가져오지 못했습니다.")
                else:
                    # 필요한 컬럼만 추출하여 정렬
                    # pykrx의 get_market_trading_value_by_date(detail=True) 반환 컬럼:
                    # ['금융투자', '보험', '투신', '사모', '은행', '기타금융', '연기금', '기관합계', '외국인', '개인', '기타법인', '기타외국인', '전체']
                    # 인덱스는 날짜
                    df_series = df_series.sort_index()
                    
                    # 주가 정보 매핑을 위해 ohlcv 데이터 조회
                    try:
                        from pykrx import stock
                        df_ohlcv = stock.get_market_ohlcv_by_date(start_dt, target_date_str, selected_ticker)
                        df_ohlcv = df_ohlcv.sort_index()
                    except Exception as e:
                        df_ohlcv = pd.DataFrame()
                        st.write(f"주가 데이터 조회 실패: {e}")
                    
                    # 듀얼 Y축 차트 생성
                    fig = make_subplots(specs=[[{"secondary_y": True}]])
                    
                    # 1. 주가 라인 (좌측 Y축)
                    if not df_ohlcv.empty:
                        fig.add_trace(
                            go.Scatter(
                                x=df_ohlcv.index,
                                y=df_ohlcv["종가"],
                                name="종가",
                                line=dict(color="gray", width=2.5)
                            ),
                            secondary_y=False
                        )
                    
                    # 2. 투자자별 누적 순매수 대금 (우측 Y축, 억 원 단위 변환)
                    # 누적합 계산
                    investors_to_plot = ["외국인", "연기금", "투신", "사모", "기관합계"]
                    colors = {
                        "외국인": "red",
                        "연기금": "blue",
                        "투신": "green",
                        "사모": "orange",
                        "기관합계": "purple"
                    }
                    
                    for inv in investors_to_plot:
                        if inv in df_series.columns:
                            # 원 단위를 억 원 단위로 변환
                            cum_sum = (df_series[inv].cumsum() / 100000000).round(2)
                            fig.add_trace(
                                go.Scatter(
                                    x=df_series.index,
                                    y=cum_sum,
                                    name=f"{inv} 누적수급(억)",
                                    line=dict(color=colors.get(inv, "grey"), width=1.5)
                                ),
                                secondary_y=True
                            )
                            
                    # 차트 레이아웃 조정 (고대비 Tailwind Slate 표준 테마)
                    fig.update_layout(
                        template="plotly_dark",
                        paper_bgcolor="#1E293B",
                        plot_bgcolor="#0F172A",
                        title=dict(
                            text=f"<b>{selected_name} ({selected_ticker}) 주가 및 누적 수급 흐름</b>",
                            font=dict(color="#F8FAFC", size=16)
                        ),
                        xaxis=dict(
                            title="날짜",
                            gridcolor="#334155",
                            linecolor="#475569",
                            tickfont=dict(color="#cbd5e1")
                        ),
                        legend=dict(
                            x=0.01,
                            y=0.99,
                            bgcolor="rgba(30, 41, 59, 0.85)",
                            bordercolor="#334155",
                            borderwidth=1,
                            font=dict(color="#F8FAFC", size=11)
                        ),
                        hovermode="x unified",
                        height=600
                    )
                    
                    fig.update_yaxes(title_text="주가 (원)", secondary_y=False, gridcolor="#334155", linecolor="#475569", tickfont=dict(color="#cbd5e1"))
                    fig.update_yaxes(title_text="누적 순매수 대금 (억 원)", secondary_y=True, showgrid=False, linecolor="#475569", tickfont=dict(color="#cbd5e1"))
                    
                    st.plotly_chart(fig, use_container_width=True)
                    
                    # 당일의 수급 주체별 상세 표 제공
                    st.markdown('<div class="sub-section-title">수급 주체별 당일 순매수 상세</div>', unsafe_allow_html=True)
                    today_data = df_series.iloc[-1]
                    df_today_inv = pd.DataFrame(today_data).rename(columns={today_data.name: "순매수대금(원)"})
                    df_today_inv["순매수대금(억)"] = (df_today_inv["순매수대금(원)"] / 100000000).round(2)
                    st.dataframe(df_today_inv[["순매수대금(억)"]].T, use_container_width=True)

st.markdown("<hr style='border: 0; height: 1px; background-color: #334155; margin: 30px 0 10px 0;'>", unsafe_allow_html=True)
st.markdown(
    "<div style='text-align: center; color: #64748b; font-size: 0.8rem; margin-top: 8px; margin-bottom: 24px; line-height: 1.6;'>"
    "⚠️ 본 서비스에서 제공하는 모든 정보는 투자 참고용이며, 투자의 최종 결정과 책임은 투자자 본인에게 있습니다."
    "</div>",
    unsafe_allow_html=True
)
