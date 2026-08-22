import pandas as pd
import numpy as np
import datetime
from data_loader import fetch_investor_net_purchases_with_cache, get_nearest_business_day

def calculate_dbd(df_net_buy, df_mkt_cap):
    """
    당일 수급 지배력 (Daily Buying Dominance, DBD) 계산
    Formula: 당일 특정 투자자 순매수 대금 / 당일 거래대금 * 100 (%)
    """
    if df_net_buy.empty or df_mkt_cap.empty:
        return pd.Series(dtype=float)
        
    # '순매수거래대금' 컬럼 추출
    # pykrx의 get_market_net_purchases_of_equities_by_ticker는 '순매수거래대금' 컬럼을 가짐
    net_buy_val = df_net_buy["순매수거래대금"]
    
    # '거래대금' 컬럼 추출
    # pykrx의 get_market_cap_by_ticker는 '거래대금' 컬럼을 가짐
    total_turnover = df_mkt_cap["거래대금"]
    
    # 인덱스(티커) 기준으로 조인하여 연산
    combined = pd.DataFrame({"net_buy": net_buy_val, "turnover": total_turnover})
    
    # 거래대금이 0인 경우 결측치 처리
    combined["turnover"] = combined["turnover"].replace(0, np.nan)
    
    # DBD 계산 (%)
    dbd = (combined["net_buy"] / combined["turnover"]) * 100
    return dbd.dropna()

def calculate_abim(df_net_buy_accum, df_mkt_cap):
    """
    시가총액 대비 누적 순매수 강도 (Accumulated Buying Intensity to Market Cap, ABIM) 계산
    Formula: N일간 누적 순매수 대금 / 당일 시가총액 * 100 (%)
    """
    if df_net_buy_accum.empty or df_mkt_cap.empty:
        return pd.Series(dtype=float)
        
    net_buy_accum_val = df_net_buy_accum["순매수거래대금"]
    market_cap = df_mkt_cap["시가총액"]
    
    combined = pd.DataFrame({"net_buy_accum": net_buy_accum_val, "mkt_cap": market_cap})
    
    # 시가총액이 0인 경우 결측치 처리
    combined["mkt_cap"] = combined["mkt_cap"].replace(0, np.nan)
    
    # ABIM 계산 (%)
    abim = (combined["net_buy_accum"] / combined["mkt_cap"]) * 100
    return abim.dropna()

def get_business_days_list(start_date, end_date):
    """
    두 날짜 사이의 영업일(평일) 목록을 반환합니다. (주말 제외)
    """
    dates = pd.date_range(start=start_date, end=end_date)
    # 월요일=0, 일요일=6 이므로 0~4인 평일만 필터링
    weekday_dates = dates[dates.weekday < 5]
    return [d.strftime("%Y%m%d") for d in weekday_dates]

def fetch_net_purchases_panel(start_date, end_date, market="ALL", investor="기관합계"):
    """
    지정된 기간 동안 일자별로 시장 전체의 순매수 대금을 조회하여
    [날짜 x 종목] 형태의 패널 데이터프레임(시계열)을 구축합니다.
    (Z-Score 일괄 계산을 위한 핵심 최적화 함수)
    """
    business_days = get_business_days_list(start_date, end_date)
    
    panel_data = {}
    
    for date in business_days:
        # data_loader에서 캐시 기반 조회
        df = fetch_investor_net_purchases_with_cache(date, date, market=market, investor=investor)
        if not df.empty and "순매수거래대금" in df.columns:
            panel_data[date] = df["순매수거래대금"]
            
    # 데이터프레임으로 결합 (행: 날짜, 열: 종목 티커)
    df_panel = pd.DataFrame(panel_data).T
    df_panel.index = pd.to_datetime(df_panel.index, format="%Y%m%d")
    return df_panel

def calculate_panel_zscore(df_panel):
    """
    패널 데이터프레임을 기반으로 전 종목의 최근일(가장 마지막 행) 기준 Z-Score를 일괄 연산합니다.
    Formula: (당일값 - 최근 M일 평균) / 최근 M일 표준편차
    """
    if df_panel.empty or len(df_panel) < 5:  # 최소 5일 이상의 데이터가 필요함
        return pd.Series(dtype=float)
        
    # 각 종목(열)별 평균 및 표준편차 계산
    means = df_panel.mean()
    stds = df_panel.std()
    
    # 마지막 행(당일) 데이터 추출
    today_values = df_panel.iloc[-1]
    
    # 표준편차가 0인 경우(수급 변동이 전혀 없는 종목)는 NaN 처리하여 나눗셈 에러 방지
    stds = stds.replace(0, np.nan)
    
    # Z-Score 계산
    z_scores = (today_values - means) / stds
    return z_scores.dropna()
