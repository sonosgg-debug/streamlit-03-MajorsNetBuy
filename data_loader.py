import os
import time
import pickle
import datetime
import pandas as pd
from pykrx import stock

# 캐시 디렉토리 설정
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)

def setup_krx_auth(krx_id, krx_pw):
    """
    KRX 계정 정보를 환경변수에 주입하여 pykrx가 세션을 맺을 수 있도록 설정합니다.
    """
    if krx_id and krx_pw:
        os.environ["KRX_ID"] = krx_id
        os.environ["KRX_PW"] = krx_pw
        # pykrx의 내부 auth 모듈을 임포트하여 강제로 세션 초기화 유도
        try:
            from pykrx.website.comm.auth import get_auth_session
            session = get_auth_session()
            if session and session.is_authenticated:
                return True
        except Exception as e:
            print(f"KRX Auth Setup Error: {e}")
    return False

import requests

# 한국거래소(KRX) 정규 휴장일 및 법정 공휴일 (2024~2027)
KRX_HOLIDAYS = {
    # 2024
    '20240101', '20240209', '20240212', '20240301', '20240410', '20240501', '20240506',
    '20240515', '20240606', '20240815', '20240916', '20240917', '20240918', '20241001',
    '20241003', '20241009', '20241225', '20241231',
    # 2025
    '20250101', '20250128', '20250129', '20250130', '20250303', '20250501', '20250505',
    '20250506', '20250606', '20250815', '20251003', '20251006', '20251007', '20251008',
    '20251009', '20251225', '20251231',
    # 2026
    '20260101', '20260216', '20260217', '20260218', '20260302', '20260501', '20260505',
    '20260525', '20260603', '20260606', '20260817', '20260924', '20260925', '20261005',
    '20261009', '20261225', '20261231',
    # 2027
    '20270101', '20270208', '20270209', '20270210', '20270301', '20270503', '20270505',
    '20270513', '20270607', '20270816', '20270914', '20270915', '20270916', '20271004',
    '20271011', '20271225', '20271231'
}

_CACHED_TRADING_DAYS = None

def get_krx_trading_days(count=120):
    """
    한국거래소(KRX)의 실제 거래일(개장일) 목록을 반환합니다.
    1. 네이버 증시 API를 통해 실시간 실제 거래일 리스트를 우선 확보
    2. 네트워크 장애 등 실패 시 사전에 정의된 휴장일 캘린더 및 주말 제외 알고리즘으로 폴백
    """
    global _CACHED_TRADING_DAYS
    if _CACHED_TRADING_DAYS is not None and len(_CACHED_TRADING_DAYS) >= count:
        return _CACHED_TRADING_DAYS
        
    days = []
    headers = {'User-Agent': 'Mozilla/5.0'}
    pages_needed = (count + 59) // 60
    for page in range(1, pages_needed + 1):
        try:
            url = f'https://m.stock.naver.com/api/stock/005930/price?pageSize=60&page={page}'
            r = requests.get(url, headers=headers, timeout=3)
            if r.status_code == 200:
                items = r.json()
                if items:
                    days.extend([item['localTradedAt'].replace('-', '') for item in items])
                else:
                    break
        except Exception:
            pass
            
    if days:
        _CACHED_TRADING_DAYS = sorted(list(set(days)))
        return _CACHED_TRADING_DAYS
        
    # 오프라인/네트워크 장애 대비 폴백 알고리즘
    fallback_days = []
    now_kst = get_now_kst()
    d = now_kst
    for _ in range(count * 3):
        d_str = d.strftime('%Y%m%d')
        if d.weekday() < 5 and d_str not in KRX_HOLIDAYS:
            fallback_days.append(d_str)
            if len(fallback_days) >= count:
                break
        d -= datetime.timedelta(days=1)
        
    _CACHED_TRADING_DAYS = sorted(fallback_days)
    return _CACHED_TRADING_DAYS

def is_krx_trading_day(date_str):
    """주어진 날짜(YYYYMMDD 또는 YYYY-MM-DD)가 실제 거래일인지 판별합니다."""
    clean_date = date_str.replace('-', '')
    trading_days = get_krx_trading_days(120)
    if clean_date in trading_days:
        return True
    # 거래일 목록 범위를 벗어난 과거/미래의 경우 규칙 기반 판별
    try:
        dt = datetime.datetime.strptime(clean_date, "%Y%m%d")
        return (dt.weekday() < 5) and (clean_date not in KRX_HOLIDAYS)
    except:
        return False

def get_now_kst():
    """한국 표준시(KST, UTC+9) datetime 객체 반환"""
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    return now_utc + datetime.timedelta(hours=9)

def get_nearest_business_day(date_str=None):
    """
    주어진 날짜 또는 현재 날짜 기준 가장 가까운 최근 '실제 거래일(개장일)'을 YYYYMMDD 형태로 반환합니다.
    - date_str이 없는 경우: KST 기준 16:00 이전이거나 오늘이 휴장일인 경우 '직전 실제 마감 거래일'을 반환
    - date_str이 있는 경우: 해당 날짜가 실제 거래일이면 그대로 반환, 주말/휴장일인 경우 '직전 실제 거래일'로 자동 보정
    """
    trading_days = get_krx_trading_days(120)
    
    if date_str:
        clean_date = str(date_str).replace('-', '')
        # 이미 실제 거래일 목록에 존재하는 경우
        if clean_date in trading_days:
            return clean_date
        # 휴장일이나 주말인 경우: 해당 날짜 이하(<=)의 가장 최근 실제 거래일 탐색
        earlier_days = [d for d in trading_days if d <= clean_date]
        if earlier_days:
            return earlier_days[-1]
            
        # fallback: 날짜를 하루씩 줄여가며 평일 및 공휴일 아닌 날짜 탐색
        try:
            dt = datetime.datetime.strptime(clean_date, "%Y%m%d")
            while True:
                d_str = dt.strftime("%Y%m%d")
                if dt.weekday() < 5 and d_str not in KRX_HOLIDAYS:
                    return d_str
                dt -= datetime.timedelta(days=1)
        except Exception:
            return clean_date
    
    # date_str이 전달되지 않은 경우 (최신 마감 거래일)
    now_kst = get_now_kst()
    today_str = now_kst.strftime("%Y%m%d")
    
    # 평일 16:00 이후이고 오늘이 실제 거래일 목록에 있으면 오늘 반환
    if now_kst.hour >= 16 and today_str in trading_days:
        return today_str
        
    # 16:00 이전이거나 오늘이 휴장일인 경우: 오늘보다 이전(<)의 가장 최근 거래일
    prior_days = [d for d in trading_days if d < today_str]
    if prior_days:
        return prior_days[-1]
        
    return trading_days[-1] if trading_days else (now_kst - datetime.timedelta(days=1)).strftime("%Y%m%d")

def fetch_market_cap_with_cache(date_str, market="ALL"):
    """
    특정 날짜의 시장 전체 종목 시가총액 정보를 가져오고 캐싱합니다.
    (종가, 시가총액, 거래량, 거래대금, 상장주식수)
    """
    date_str = get_nearest_business_day(date_str)
    cache_path = os.path.join(CACHE_DIR, f"mkt_cap_{market}_{date_str}.pkl")
    
    # 오늘 또는 미래 날짜는 캐시하지 않음
    today_str = get_now_kst().strftime("%Y%m%d")
    is_today = (date_str >= today_str)
    
    if not is_today and os.path.exists(cache_path):
        try:
            with open(cache_path, "rb") as f:
                return pickle.load(f)
        except Exception as e:
            print(f"Cache read error for market cap: {e}")
            
    # API 요청 전 딜레이 부여
    time.sleep(0.5)
    try:
        # pykrx를 통한 시가총액 정보 가져오기
        df = stock.get_market_cap_by_ticker(date_str, market=market)
        
        # 종목명 추가 매핑
        if not df.empty:
            names = []
            for ticker in df.index:
                try:
                    name = stock.get_market_net_purchases_of_equities_by_ticker
                    # 단순 종목명 얻기
                    name = stock.get_market_ticker_name(ticker)
                except:
                    name = ""
                names.append(name)
            df["종목명"] = names
            
        if not is_today and not df.empty:
            with open(cache_path, "wb") as f:
                pickle.dump(df, f)
        return df
    except Exception as e:
        print(f"Failed to fetch market cap for {date_str}: {e}")
        return pd.DataFrame()

def fetch_investor_net_purchases_with_cache(start_date, end_date, market="ALL", investor="기관합계"):
    """
    특정 기간 동안 특정 투자자의 종목별 순매수 데이터를 가져오고 캐싱합니다.
    - investor: '외국인', '기관합계', '연기금', '투신', '사모', '금융투자', '개인' 등
    """
    start_date = get_nearest_business_day(start_date)
    end_date = get_nearest_business_day(end_date)
    
    # 복합 주체 합산 처리 (외국인+연기금, 외국인+투신+연기금 등)
    if "+" in investor:
        sub_investors = [sub.strip() for sub in investor.split("+")]
        dfs = []
        for sub in sub_investors:
            df_sub = fetch_investor_net_purchases_with_cache(start_date, end_date, market=market, investor=sub)
            if not df_sub.empty:
                dfs.append(df_sub[["순매수거래량", "순매수거래대금"]])
        if not dfs:
            return pd.DataFrame()
            
        df_combined = pd.concat(dfs).groupby(level=0).sum()
        
        # 종목명 맵핑 복원
        for sub in sub_investors:
            df_sub = fetch_investor_net_purchases_with_cache(start_date, end_date, market=market, investor=sub)
            if not df_sub.empty and "종목명" in df_sub.columns:
                df_combined["종목명"] = df_sub["종목명"]
                break
                
        # 기존 스키마 호환성 필드 구성
        df_combined["매도거래량"] = 0
        df_combined["매수거래량"] = 0
        df_combined["매도거래대금"] = 0
        df_combined["매수거래대금"] = 0
        return df_combined

    # 투자자 한글명 -> pykrx 인자 매핑
    # pykrx의 get_market_net_purchases_of_equities_by_ticker는 한글 수급 주체명을 인자로 받음
    # (예: '외국인', '기관합계', '연기금', '투신', '사모', '금융투자', '보험', '개인' 등)
    
    cache_key = f"net_buy_{investor}_{market}_{start_date}_{end_date}.pkl"
    cache_path = os.path.join(CACHE_DIR, cache_key)
    
    today_str = get_now_kst().strftime("%Y%m%d")
    is_live = (end_date >= today_str)
    
    if not is_live and os.path.exists(cache_path):
        try:
            with open(cache_path, "rb") as f:
                return pickle.load(f)
        except Exception as e:
            print(f"Cache read error for net purchases: {e}")
            
    time.sleep(0.5)
    try:
        # pykrx 호출
        df = stock.get_market_net_purchases_of_equities_by_ticker(
            start_date, end_date, market=market, investor=investor
        )
        
        if not is_live and not df.empty:
            with open(cache_path, "wb") as f:
                pickle.dump(df, f)
        return df
    except Exception as e:
        print(f"Failed to fetch net purchases ({investor}) from {start_date} to {end_date}: {e}")
        return pd.DataFrame()

def fetch_daily_net_purchases_series(start_date, end_date, ticker):
    """
    특정 종목의 일자별 투자자별 순매수 거래대금 추이를 가져옵니다. (시각화용)
    """
    start_date = get_nearest_business_day(start_date)
    end_date = get_nearest_business_day(end_date)
    
    cache_path = os.path.join(CACHE_DIR, f"daily_series_{ticker}_{start_date}_{end_date}.pkl")
    today_str = get_now_kst().strftime("%Y%m%d")
    is_live = (end_date >= today_str)
    
    if not is_live and os.path.exists(cache_path):
        try:
            with open(cache_path, "rb") as f:
                return pickle.load(f)
        except Exception as e:
            print(f"Cache read error for daily series: {e}")
            
    time.sleep(0.5)
    try:
        # get_market_trading_value_by_date는 일자별 투자자들의 순매수대금을 가져옴 (원 단위)
        df = stock.get_market_trading_value_by_date(start_date, end_date, ticker, detail=True)
        
        if not is_live and not df.empty:
            with open(cache_path, "wb") as f:
                pickle.dump(df, f)
        return df
    except Exception as e:
        print(f"Failed to fetch daily series for {ticker}: {e}")
        return pd.DataFrame()
