import unittest
import pandas as pd
import numpy as np
from indicators import calculate_dbd, calculate_abim, calculate_panel_zscore

class TestIndicators(unittest.TestCase):
    def setUp(self):
        # 테스트용 기본 데이터 준비
        self.tickers = ["005930", "000660", "035420"]
        
    def test_calculate_dbd(self):
        # 1. 가상 당일 순매수 데이터 생성
        df_net_buy = pd.DataFrame(
            {"순매수거래대금": [100, -50, 0]},  # 단위: 억 원
            index=self.tickers
        )
        
        # 2. 가상 시가총액 및 거래대금 데이터 생성
        df_mkt_cap = pd.DataFrame(
            {"거래대금": [1000, 500, 200]},  # 단위: 억 원
            index=self.tickers
        )
        
        # 3. DBD 계산
        dbd = calculate_dbd(df_net_buy, df_mkt_cap)
        
        # 4. 검증
        # 005930: 100 / 1000 * 100 = 10%
        # 000660: -50 / 500 * 100 = -10%
        # 035420: 0 / 200 * 100 = 0%
        self.assertEqual(dbd.loc["005930"], 10.0)
        self.assertEqual(dbd.loc["000660"], -10.0)
        self.assertEqual(dbd.loc["035420"], 0.0)

    def test_calculate_abim(self):
        # 1. 가상 누적 순매수 데이터 생성
        df_net_buy_accum = pd.DataFrame(
            {"순매수거래대금": [50, 100, -10]},  # 단위: 억 원
            index=self.tickers
        )
        
        # 2. 가상 시가총액 데이터 생성
        df_mkt_cap = pd.DataFrame(
            {"시가총액": [5000, 20000, 1000]},  # 단위: 억 원
            index=self.tickers
        )
        
        # 3. ABIM 계산
        abim = calculate_abim(df_net_buy_accum, df_mkt_cap)
        
        # 4. 검증
        # 005930: 50 / 5000 * 100 = 1.0%
        # 000660: 100 / 20000 * 100 = 0.5%
        # 035420: -10 / 1000 * 100 = -1.0%
        self.assertAlmostEqual(abim.loc["005930"], 1.0)
        self.assertAlmostEqual(abim.loc["000660"], 0.5)
        self.assertAlmostEqual(abim.loc["035420"], -1.0)

    def test_calculate_panel_zscore(self):
        # 1. 패널 데이터 생성 [날짜 x 종목]
        # 5일간의 데이터
        dates = pd.to_datetime(["20240102", "20240103", "20240104", "20240105", "20240106"], format="%Y%m%d")
        
        # 005930 종목: 값 리스트 [6, 8, 10, 12, 14] -> 평균=10.0, 표준편차=np.std([6,8,10,12,14], ddof=1) = 3.162277
        # 당일값(14) - 평균(10) = 4 -> Z = 4 / 3.162277 = 1.2649
        
        # 000660 종목: 값 리스트 [10, 10, 10, 10, 10] -> 평균=10, 표준편차=0 -> Z-Score는 NaN이 되거나 드롭되어야 함 (나눗셈 방지)
        
        data = {
            "005930": [6.0, 8.0, 10.0, 12.0, 14.0],
            "000660": [10.0, 10.0, 10.0, 10.0, 10.0]
        }
        df_panel = pd.DataFrame(data, index=dates)
        
        # 2. Z-Score 일괄 계산
        z_scores = calculate_panel_zscore(df_panel)
        
        # 3. 검증
        # 005930의 Z-score는 (14 - 10) / 3.16227766 = 1.264911
        self.assertAlmostEqual(z_scores.loc["005930"], 1.264911064, places=6)
        
        # 000660은 표준편차가 0이므로 결과 리스트에서 제외(dropna)되었는지 검사
        self.assertNotIn("000660", z_scores.index)

if __name__ == "__main__":
    unittest.main()
