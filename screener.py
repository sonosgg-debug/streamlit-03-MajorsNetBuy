import datetime
import pandas as pd
import numpy as np
from data_loader import (
    fetch_market_cap_with_cache,
    fetch_investor_net_purchases_with_cache,
    get_nearest_business_day
)
from indicators import (
    calculate_dbd,
    calculate_abim,
    get_business_days_list,
    fetch_net_purchases_panel,
    calculate_panel_zscore
)

class StockScreener:
    def __init__(self, target_date=None, market="ALL"):
        """
        target_date: 스크리닝 기준일 (YYYYMMDD). None인 경우 가장 최근 영업일
        market: 시장 구분 ('ALL', 'KOSPI', 'KOSDAQ')
        """
        self.market = market
        self.target_date = get_nearest_business_day(target_date)
        
        # 기준일 시가총액 데이터 미리 로드
        print(f"Loading market cap data for {self.target_date}...")
        self.df_mkt_cap = fetch_market_cap_with_cache(self.target_date, market=self.market)
        
    def _get_historical_business_days(self, days_needed):
        """
        기준일(target_date) 포함하여 과거로 N개의 영업일 리스트를 반환합니다.
        """
        # 넉넉하게 약 3배 기간의 일력을 생성하여 평일 필터링
        start_date_dt = datetime.datetime.strptime(self.target_date, "%Y%m%d") - datetime.timedelta(days=days_needed * 3 + 10)
        start_date = start_date_dt.strftime("%Y%m%d")
        
        all_b_days = get_business_days_list(start_date, self.target_date)
        # target_date가 포함되어 있고 역순 정렬
        if self.target_date not in all_b_days:
            all_b_days.append(self.target_date)
            all_b_days.sort()
            
        # 기준일 이하 영업일만 필터링
        valid_days = [d for d in all_b_days if d <= self.target_date]
        
        # 최근순으로 정렬하여 필요한 일수만큼 슬라이싱 후 다시 날짜순 정렬
        recent_days = valid_days[-days_needed:]
        return recent_days

    def screen(self, 
               min_market_cap_krw=1000 * 100000000,    # 최소 시가총액 (1000억 원)
               min_turnover_5d_krw=20 * 100000000,     # 최근 5일 평균 거래대금 (20억 원)
               accum_days=5,                           # 누적 수급 계산 기간 N일
               target_investor="연기금",                 # 분석할 주요 투자 주체
               min_accum_intensity=0.2,                # 시총 대비 누적 순매수 비율 임계치 (%)
               min_zscore=1.5,                         # 당일 Z-Score 임계치 (수급 폭발)
               zscore_lookback_days=20,                # Z-Score 산출용 과거 룩백 기간 M일
               require_dual_buy=False                  # 외국인 + 기관합계 동시 순매수(양매수) 필수 여부
              ):
        """
        설정된 조건에 맞춰 종목들을 필터링하고 상세 지표 데이터프레임을 반환합니다.
        """
        if self.df_mkt_cap.empty:
            print("Market cap data is empty. Screening aborted.")
            return pd.DataFrame()
            
        # 1. 기본 대상 필터링 (시가총액)
        df_filtered = self.df_mkt_cap[self.df_mkt_cap["시가총액"] >= min_market_cap_krw].copy()
        if df_filtered.empty:
            return pd.DataFrame()
            
        # 2. 거래대금 필터링 (최근 5일 평균 거래대금 계산)
        # N일 전 날짜 계산
        recent_5_days = self._get_historical_business_days(5)
        if len(recent_5_days) > 0:
            turnovers = []
            for date in recent_5_days:
                df_cap = fetch_market_cap_with_cache(date, market=self.market)
                if not df_cap.empty:
                    turnovers.append(df_cap["거래대금"])
            if turnovers:
                df_turnover_avg = pd.concat(turnovers, axis=1).mean(axis=1)
                # 필터 적용
                valid_tickers = df_turnover_avg[df_turnover_avg >= min_turnover_5d_krw].index
                df_filtered = df_filtered[df_filtered.index.isin(valid_tickers)]
                df_filtered["5일평균거래대금"] = df_turnover_avg[df_filtered.index]
        
        if df_filtered.empty:
            return pd.DataFrame()
            
        # 3. 누적 수급 계산 (최근 N일 누적 순매수 대금)
        recent_N_days = self._get_historical_business_days(accum_days)
        start_accum_date = recent_N_days[0]
        end_accum_date = recent_N_days[-1]
        
        print(f"Fetching cumulative purchases ({target_investor}) from {start_accum_date} to {end_accum_date}...")
        df_net_buy_accum = fetch_investor_net_purchases_with_cache(
            start_accum_date, end_accum_date, market=self.market, investor=target_investor
        )
        
        # 시총 대비 누적 매집 강도 계산
        abim_series = calculate_abim(df_net_buy_accum, self.df_mkt_cap)
        df_filtered["누적순매수대금"] = df_net_buy_accum["순매수거래대금"].reindex(df_filtered.index) if not df_net_buy_accum.empty else np.nan
        df_filtered["누적수급강도(시총비)"] = abim_series.reindex(df_filtered.index)
        
        # 4. 당일 수급 강도 (DBD) 계산
        df_net_buy_today = fetch_investor_net_purchases_with_cache(
            self.target_date, self.target_date, market=self.market, investor=target_investor
        )
        dbd_series = calculate_dbd(df_net_buy_today, self.df_mkt_cap)
        df_filtered["당일순매수대금"] = df_net_buy_today["순매수거래대금"].reindex(df_filtered.index) if not df_net_buy_today.empty else np.nan
        df_filtered["당일수급지배력(거래대금비)"] = dbd_series.reindex(df_filtered.index)
        
        # 5. 수급 Z-Score 연산
        z_lookback_days = self._get_historical_business_days(zscore_lookback_days)
        start_z_date = z_lookback_days[0]
        end_z_date = z_lookback_days[-1]
        
        print(f"Fetching panel data for Z-Score from {start_z_date} to {end_z_date}...")
        df_panel = fetch_net_purchases_panel(
            start_z_date, end_z_date, market=self.market, investor=target_investor
        )
        
        z_scores = calculate_panel_zscore(df_panel)
        df_filtered["수급ZScore"] = z_scores.reindex(df_filtered.index)
        
        # 6. 양매수 필터 조건 (외국인 & 기관합계 동시 순매수 여부)
        # 당일 외국인 순매수
        df_foreigner_today = fetch_investor_net_purchases_with_cache(
            self.target_date, self.target_date, market=self.market, investor="외국인"
        )
        # 당일 기관합계 순매수
        df_institution_today = fetch_investor_net_purchases_with_cache(
            self.target_date, self.target_date, market=self.market, investor="기관합계"
        )
        
        is_foreigner_buy = (df_foreigner_today["순매수거래대금"].reindex(df_filtered.index) > 0) if not df_foreigner_today.empty else False
        is_institution_buy = (df_institution_today["순매수거래대금"].reindex(df_filtered.index) > 0) if not df_institution_today.empty else False
        
        df_filtered["외인순매수(당일)"] = df_foreigner_today["순매수거래대금"].reindex(df_filtered.index) if not df_foreigner_today.empty else np.nan
        df_filtered["기관순매수(당일)"] = df_institution_today["순매수거래대금"].reindex(df_filtered.index) if not df_institution_today.empty else np.nan
        df_filtered["양매수여부"] = is_foreigner_buy & is_institution_buy
        
        # 7. 스크리닝 필터 적용
        # 조건 A: 누적수급강도가 임계치 이상
        cond_accum = (df_filtered["누적수급강도(시총비)"] >= min_accum_intensity)
        # 조건 B: Z-Score가 임계치 이상
        cond_zscore = (df_filtered["수급ZScore"] >= min_zscore)
        # 조건 C: 양매수 필수 여부
        cond_dual = df_filtered["양매수여부"] if require_dual_buy else True
        
        # 최종 스크리닝
        df_screened = df_filtered[cond_accum & cond_zscore & cond_dual].copy()
        
        # 가독성을 위한 컬럼 정리 및 정렬 (누적 수급 강도 높은 순)
        if not df_screened.empty:
            df_screened = df_screened.sort_values(by="누적수급강도(시총비)", ascending=False)
            # 수치 가독성 처리 (금액 단위를 억 원으로 표시)
            df_screened["시가총액(억)"] = (df_screened["시가총액"] / 100000000).round(1)
            df_screened["5일평균거래대금(억)"] = (df_screened["5일평균거래대금"] / 100000000).round(1)
            df_screened["누적순매수대금(억)"] = (df_screened["누적순매수대금"] / 100000000).round(2)
            df_screened["당일순매수대금(억)"] = (df_screened["당일순매수대금"] / 100000000).round(2)
            df_screened["외인순매수(억)"] = (df_screened["외인순매수(당일)"] / 100000000).round(2)
            df_screened["기관순매수(억)"] = (df_screened["기관순매수(당일)"] / 100000000).round(2)
            df_screened["당일수급지배력(%)"] = df_screened["당일수급지배력(거래대금비)"].round(2)
            df_screened["누적수급강도(%)"] = df_screened["누적수급강도(시총비)"].round(2)
            df_screened["ZScore"] = df_screened["수급ZScore"].round(2)
            
            output_cols = [
                "종목명", "종가", "시가총액(억)", "5일평균거래대금(억)", 
                "누적순매수대금(억)", "누적수급강도(%)", 
                "당일순매수대금(억)", "당일수급지배력(%)", "ZScore",
                "외인순매수(억)", "기관순매수(억)", "양매수여부"
            ]
            df_screened = df_screened[output_cols]
            
        return df_screened
