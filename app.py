import streamlit as st
import io
import pandas as pd
import datetime
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os

from data_loader import setup_krx_auth, fetch_daily_net_purchases_series
from screener import StockScreener

# 페이지 설정
st.set_page_config(
    page_title="한국 증시 메이저 수급 스크리너",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("📊 한국 증시 외국인/기관 수급 스크리너")
st.markdown("""
최근 $N$일 동안의 외국인 및 기관(연기금, 투신, 사모 등 세부 주체 분리) 순매수 데이터를 분석하여, 
수급이 집중되는 유망 종목을 발굴하고 시각화하는 대시보드입니다.
""")

# 세션 상태 초기화 (결과 캐싱용)
if "screened_df" not in st.session_state:
    st.session_state.screened_df = None
if "auth_status" not in st.session_state:
    st.session_state.auth_status = False

# ================= SIDEBAR =================
st.sidebar.header("🔑 1. KRX 세션 설정")
st.sidebar.markdown(
    "수급 세부 주체(연기금, 투신 등) 조회를 위해 [KRX 정보데이터시스템](https://data.krx.co.kr/)의 무료 회원 계정이 필요합니다."
)

krx_id = st.sidebar.text_input("KRX ID", value=os.getenv("KRX_ID", ""))
krx_pw = st.sidebar.text_input("KRX Password", type="password", value=os.getenv("KRX_PW", ""))

if st.sidebar.button("세션 연결 및 로그인"):
    with st.spinner("KRX 로그인 세션 설정 중..."):
        success = setup_krx_auth(krx_id, krx_pw)
        st.session_state.auth_status = success
        if success:
            st.sidebar.success("✅ KRX 로그인 연동 성공!")
        else:
            st.sidebar.error("❌ 로그인 실패 (아이디/비번 혹은 IP 차단 상태 확인)")

# 로그인 안된 상태에서 경고 안내
if not st.session_state.auth_status:
    st.warning("⚠️ KRX 로그인 세션이 연동되지 않았습니다. 분석 시작 전 사이드바에서 로그인을 진행해 주세요.")

st.sidebar.header("⚙️ 2. 스크리닝 필터 설정")

# 시장 구분
market = st.sidebar.selectbox("시장 선택", ["ALL", "KOSPI", "KOSDAQ"], index=0)

# 시가총액/거래대금 기본 필터
min_mkt_cap = st.sidebar.number_input("최소 시가총액 (억 원)", min_value=10, max_value=500000, value=1000, step=100)
min_turnover = st.sidebar.number_input("최소 5일 평균 거래대금 (억 원)", min_value=0, max_value=50000, value=20, step=5)

# 수급 주체 및 세부 필터
st.sidebar.subheader("수급 상세 조건")
target_investor = st.sidebar.selectbox(
    "주 분석 수급 주체", 
    ["연기금", "투신", "사모", "금융투자", "기관합계", "외국인"], 
    index=0
)

accum_days = st.sidebar.slider("누적 수급 계산 기간 N (일)", min_value=1, max_value=60, value=5)
min_accum_intensity = st.sidebar.slider("시총 대비 누적 매집 비율 (%)", min_value=0.01, max_value=5.0, value=0.2, step=0.05)

# Z-Score 조건
min_zscore = st.sidebar.slider("당일 수급 Z-Score 최소치", min_value=-1.0, max_value=5.0, value=1.5, step=0.1)
zscore_lookback = st.sidebar.slider("Z-Score 산출 룩백 기간 M (일)", min_value=5, max_value=60, value=20)

# 양매수 필수 여부
require_dual = st.sidebar.checkbox("당일 외인+기관 양매수 필수", value=False)

# ================= MAIN PAGE =================
col_date, col_btn = st.columns([3, 1])

with col_date:
    # 조회 날짜 선택 (기본값: 오늘)
    default_date = datetime.date.today()
    selected_date = st.date_input("스크리닝 기준일", default_date)
    target_date_str = selected_date.strftime("%Y%m%d")

with col_btn:
    st.markdown("<br>", unsafe_allow_html=True)
    run_button = st.button("🔍 종목 스크리닝 실행", use_container_width=True)

if run_button:
    if not st.session_state.auth_status:
        st.error("분석을 시작하기 위해 먼저 사이드바에서 KRX 로그인을 완료해 주십시오.")
    else:
        with st.spinner("KRX 데이터를 로드하고 지표를 계산 중입니다. 캐시가 없는 날짜는 시간이 다소 소요될 수 있습니다..."):
            try:
                screener = StockScreener(target_date=target_date_str, market=market)
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
            except Exception as e:
                st.error(f"스크리닝 실행 중 에러가 발생했습니다: {e}")

# 스크리닝 결과 표시
if st.session_state.screened_df is not None:
    df_res = st.session_state.screened_df
    
    st.subheader(f"📈 스크리닝 결과 (총 {len(df_res)}개 종목 발굴)")
    
    if df_res.empty:
        st.info("조건에 부합하는 종목이 없습니다. 필터 임계치를 조절해 보세요.")
    else:
        # 데이터프레임 렌더링
        st.dataframe(df_res, use_container_width=True)
        
        # Excel 다운로드 기능
        market_suffixes = {
            "ALL": "ALL",
            "KOSPI": "KS",
            "KOSDAQ": "KQ"
        }
        market_suffix = market_suffixes.get(market, "ALL")
        formatted_date = selected_date.strftime("%Y-%m-%d")
        excel_filename = f"MajorsNetBuy-{market_suffix}-{formatted_date}.xlsx"
        
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            df_res.to_excel(writer, sheet_name='ScreenerResult', index=True)
        excel_data = excel_buffer.getvalue()
        
        st.download_button(
            label="📥 스크리닝 결과 엑셀 다운로드",
            data=excel_data,
            file_name=excel_filename,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
        st.markdown("---")
        st.subheader("🔍 개별 종목 수급 상세 분석 (Plotly 시각화)")
        
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
                            
                    # 차트 레이아웃 조정
                    fig.update_layout(
                        title=f"{selected_name} ({selected_ticker}) 주가 및 누적 수급 흐름",
                        xaxis_title="날짜",
                        legend=dict(x=0.01, y=0.99, bgcolor="rgba(255,255,255,0.8)"),
                        hovermode="x unified",
                        height=600
                    )
                    
                    fig.update_yaxes(title_text="주가 (원)", secondary_y=False)
                    fig.update_yaxes(title_text="누적 순매수 대금 (억 원)", secondary_y=True)
                    
                    st.plotly_chart(fig, use_container_width=True)
                    
                    # 당일의 수급 주체별 상세 표 제공
                    st.markdown("##### 📅 수급 주체별 당일 순매수 상세")
                    today_data = df_series.iloc[-1]
                    df_today_inv = pd.DataFrame(today_data).rename(columns={today_data.name: "순매수대금(원)"})
                    df_today_inv["순매수대금(억)"] = (df_today_inv["순매수대금(원)"] / 100000000).round(2)
                    st.dataframe(df_today_inv[["순매수대금(억)"]].T, use_container_width=True)
