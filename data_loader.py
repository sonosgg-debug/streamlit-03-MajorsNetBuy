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

def get_nearest_business_day(date_str=None):
    """
    주어진 날짜 또는 현재 날짜 기준 가장 가까운 최근 영업일(평일)을 YYYYMMDD 형태로 반환합니다.
    """
    if date_str:
        dt = datetime.datetime.strptime(date_str, "%Y%m%d")
    else:
        dt = datetime.datetime.now()
    
    # 주말인 경우 금요일로 조정 (5: 토요일, 6: 일요일)
    while dt.weekday() >= 5:
        dt -= datetime.timedelta(days=1)
        
    return dt.strftime("%Y%m%d")

def fetch_market_cap_with_cache(date_str, market="ALL"):
    """
    특정 날짜의 시장 전체 종목 시가총액 정보를 가져오고 캐싱합니다.
    (종가, 시가총액, 거래량, 거래대금, 상장주식수)
    """
    date_str = get_nearest_business_day(date_str)
    cache_path = os.path.join(CACHE_DIR, f"mkt_cap_{market}_{date_str}.pkl")
    
    # 오늘 또는 미래 날짜는 캐시하지 않음
    today_str = datetime.datetime.now().strftime("%Y%m%d")
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
    
    # 외국인+투신+연기금 3대 주체 합산 처리
    if investor == "외국인+투신+연기금":
        sub_investors = ["외국인", "투신", "연기금"]
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
    
    today_str = datetime.datetime.now().strftime("%Y%m%d")
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
    today_str = datetime.datetime.now().strftime("%Y%m%d")
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
