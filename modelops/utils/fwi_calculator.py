#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Canadian Forest Fire Weather Index (FWI) System Calculator
WMO-CFS 공식 알고리즘 구현

참고문헌:
- Van Wagner, C.E. 1987. Development and structure of the Canadian Forest Fire Weather Index System.
  Canadian Forestry Service, Forestry Technical Report 35.
- WMO (World Meteorological Organization) Fire Weather Index System

FWI 시스템 구성:
1. FFMC (Fine Fuel Moisture Code): 낙엽 등 미세 연료의 습도 (0-101)
2. DMC (Duff Moisture Code): 중간층 토양/유기물의 습도 (0-∞)
3. DC (Drought Code): 깊은 토양의 가뭄 지수 (0-∞)
4. ISI (Initial Spread Index): 화재 초기 확산 지수 (0-∞)
5. BUI (Buildup Index): 연료 축적 지수 (0-∞)
6. FWI (Fire Weather Index): 종합 산불 위험 지수 (0-∞)

입력 데이터:
- 기온 (°C, 정오 12시)
- 상대습도 (%, 정오 12시)
- 풍속 (km/h, 정오 12시)
- 강수량 (mm, 24시간 누적)
"""

import math
from typing import Dict


class FWICalculator:
    """
    Canadian Forest Fire Weather Index (FWI) System Calculator

    WMO 공식 알고리즘 기반 FWI 계산
    """

    def __init__(self):
        """초기화"""
        pass

    def calculate_ffmc(
        self, temp: float, rh: float, wind: float, rain: float, ffmc_prev: float = 85.0
    ) -> float:
        """
        FFMC (Fine Fuel Moisture Code) 계산

        미세 연료(낙엽, 마른 풀 등)의 습도를 나타내는 지수

        Args:
            temp: 기온 (°C)
            rh: 상대습도 (%)
            wind: 풍속 (km/h)
            rain: 24시간 강수량 (mm)
            ffmc_prev: 전날 FFMC 값 (기본값: 85.0)

        Returns:
            FFMC 값 (0-101)
        """
        # 습도 보정
        mo = 147.2 * (101.0 - ffmc_prev) / (59.5 + ffmc_prev)

        # 강수 효과
        if rain > 0.5:
            rf = rain - 0.5
            if mo <= 150.0:
                mr = mo + 42.5 * rf * math.exp(-100.0 / (251.0 - mo)) * (1.0 - math.exp(-6.93 / rf))
            else:
                mr = (
                    mo
                    + 42.5 * rf * math.exp(-100.0 / (251.0 - mo)) * (1.0 - math.exp(-6.93 / rf))
                    + 0.0015 * (mo - 150.0) ** 2 * rf**0.5
                )

            if mr > 250.0:
                mr = 250.0
            mo = mr

        # 건조 효과
        ed = (
            0.942 * (rh**0.679)
            + 11.0 * math.exp((rh - 100.0) / 10.0)
            + 0.18 * (21.1 - temp) * (1.0 - math.exp(-0.115 * rh))
        )

        if mo > ed:
            ko = 0.424 * (1.0 - ((rh / 100.0) ** 1.7)) + 0.0694 * (wind**0.5) * (
                1.0 - ((rh / 100.0) ** 8)
            )
            kd = ko * 0.581 * math.exp(0.0365 * temp)
            m = ed + (mo - ed) * (10.0 ** (-kd))
        else:
            ew = (
                0.618 * (rh**0.753)
                + 10.0 * math.exp((rh - 100.0) / 10.0)
                + 0.18 * (21.1 - temp) * (1.0 - math.exp(-0.115 * rh))
            )

            if mo < ew:
                kl = 0.424 * (1.0 - (((100.0 - rh) / 100.0) ** 1.7)) + 0.0694 * (wind**0.5) * (
                    1.0 - (((100.0 - rh) / 100.0) ** 8)
                )
                kw = kl * 0.581 * math.exp(0.0365 * temp)
                m = ew - (ew - mo) * (10.0 ** (-kw))
            else:
                m = mo

        # FFMC 계산
        ffmc = 59.5 * (250.0 - m) / (147.2 + m)

        if ffmc > 101.0:
            ffmc = 101.0
        if ffmc < 0.0:
            ffmc = 0.0

        return ffmc

    def calculate_dmc(
        self, temp: float, rh: float, rain: float, dmc_prev: float = 6.0, month: int = 7
    ) -> float:
        """
        DMC (Duff Moisture Code) 계산

        중간층 유기물(낙엽층, 부식토)의 습도를 나타내는 지수

        Args:
            temp: 기온 (°C)
            rh: 상대습도 (%)
            rain: 24시간 강수량 (mm)
            dmc_prev: 전날 DMC 값 (기본값: 6.0)
            month: 월 (1-12, 일조시간 계산용)

        Returns:
            DMC 값 (0-∞)
        """
        # 월별 일조시간 계수
        day_length_factor = [
            -1.6,
            -1.6,
            -1.6,
            0.9,
            3.8,
            5.8,  # Jan-Jun
            6.4,
            5.0,
            2.4,
            0.4,
            -1.6,
            -1.6,  # Jul-Dec
        ]

        if temp < -1.1:
            dmc = dmc_prev
        else:
            # 강수 효과
            if rain > 1.5:
                re = 0.92 * rain - 1.27
                mo = 20.0 + math.exp(5.6348 - dmc_prev / 43.43)

                if dmc_prev <= 33.0:
                    b = 100.0 / (0.5 + 0.3 * dmc_prev)
                elif dmc_prev <= 65.0:
                    b = 14.0 - 1.3 * math.log(dmc_prev)
                else:
                    b = 6.2 * math.log(dmc_prev) - 17.2

                mr = mo + 1000.0 * re / (48.77 + b * re)
                pr = 244.72 - 43.43 * math.log(mr - 20.0)

                if pr < 0.0:
                    pr = 0.0
                dmc_prev = pr

            # 건조 효과
            if temp > -1.1:
                k = 1.894 * (temp + 1.1) * (100.0 - rh) * day_length_factor[month - 1] * 0.0001
            else:
                k = 0.0

            dmc = dmc_prev + 100.0 * k

        if dmc < 0.0:
            dmc = 0.0

        return dmc

    def calculate_dc(
        self, temp: float, rain: float, dc_prev: float = 15.0, month: int = 7, lat: float = 45.0
    ) -> float:
        """
        DC (Drought Code) 계산

        깊은 토양층의 가뭄 정도를 나타내는 지수

        Args:
            temp: 기온 (°C)
            rain: 24시간 강수량 (mm)
            dc_prev: 전날 DC 값 (기본값: 15.0)
            month: 월 (1-12, 일조시간 계산용)
            lat: 위도 (일조시간 계산용, 기본값: 45.0°N)

        Returns:
            DC 값 (0-∞)
        """
        # 월별/위도별 일조시간 계수 (북위 기준)
        if lat >= 15 and lat < 20:
            day_length_factor = [6.5, 7.5, 9.0, 12.8, 13.9, 13.9, 12.4, 10.9, 9.4, 8.0, 7.0, 6.0]
        elif lat >= 20 and lat < 25:
            day_length_factor = [7.9, 8.4, 8.9, 9.5, 9.9, 10.2, 10.1, 9.7, 9.1, 8.6, 8.1, 7.8]
        elif lat >= 25 and lat < 30:
            day_length_factor = [10.1, 9.6, 9.1, 7.8, 6.8, 6.2, 6.5, 7.4, 8.7, 10.0, 11.5, 11.2]
        elif lat >= 30 and lat < 35:
            day_length_factor = [11.5, 10.5, 9.2, 7.9, 6.8, 6.2, 6.5, 7.8, 9.0, 10.2, 11.8, 12.1]
        elif lat >= 35 and lat < 40:
            day_length_factor = [12.5, 11.0, 9.5, 8.1, 7.0, 6.4, 6.7, 8.1, 9.4, 10.6, 12.3, 13.0]
        elif lat >= 40 and lat < 45:
            day_length_factor = [14.0, 11.8, 10.0, 8.3, 7.1, 6.4, 6.9, 8.4, 9.9, 11.2, 13.0, 14.5]
        else:  # lat >= 45 (한국 기본값)
            day_length_factor = [15.5, 12.7, 10.5, 8.5, 7.3, 6.5, 7.0, 8.7, 10.4, 11.9, 13.8, 16.0]

        if temp < -2.8:
            dc = dc_prev
        else:
            # 강수 효과
            if rain > 2.8:
                rd = 0.83 * rain - 1.27
                qo = 800.0 * math.exp(-dc_prev / 400.0)
                qr = qo + 3.937 * rd
                dr = 400.0 * math.log(800.0 / qr)

                if dr < 0.0:
                    dr = 0.0
                dc_prev = dr

            # 건조 효과
            if temp > -2.8:
                v = 0.36 * (temp + 2.8) + day_length_factor[month - 1]
            else:
                v = day_length_factor[month - 1]

            if v < 0.0:
                v = 0.0

            dc = dc_prev + 0.5 * v

        if dc < 0.0:
            dc = 0.0

        return dc

    def calculate_isi(self, ffmc: float, wind: float) -> float:
        """
        ISI (Initial Spread Index) 계산

        화재 초기 확산 속도를 나타내는 지수

        Args:
            ffmc: FFMC 값
            wind: 풍속 (km/h)

        Returns:
            ISI 값 (0-∞)
        """
        # 습도에 따른 화재 확산 계수
        mo = 147.2 * (101.0 - ffmc) / (59.5 + ffmc)
        ff = 19.115 * math.exp(-0.1386 * mo) * (1.0 + (mo**5.31) / 4.93e7)

        # 풍속 효과
        isi = ff * math.exp(0.05039 * wind)

        return isi

    def calculate_bui(self, dmc: float, dc: float) -> float:
        """
        BUI (Buildup Index) 계산

        연료 축적 정도를 나타내는 지수 (가뭄 + 건조)

        Args:
            dmc: DMC 값
            dc: DC 값

        Returns:
            BUI 값 (0-∞)
        """
        if dmc <= 0.4 * dc:
            bui = 0.8 * dmc * dc / (dmc + 0.4 * dc)
        else:
            bui = dmc - (1.0 - 0.8 * dc / (dmc + 0.4 * dc)) * (0.92 + (0.0114 * dmc) ** 1.7)

        if bui < 0.0:
            bui = 0.0

        return bui

    def calculate_fwi(self, isi: float, bui: float) -> float:
        """
        FWI (Fire Weather Index) 계산

        종합 산불 위험 지수 (확산 + 연료축적)

        Args:
            isi: ISI 값
            bui: BUI 값

        Returns:
            FWI 값 (0-∞)
        """
        if bui <= 80.0:
            fd = 0.626 * (bui**0.809) + 2.0
        else:
            fd = 1000.0 / (25.0 + 108.64 * math.exp(-0.023 * bui))

        b = 0.1 * isi * fd

        if b > 1.0:
            s = math.exp(2.72 * (0.434 * math.log(b)) ** 0.647)
        else:
            s = b

        fwi = s

        return fwi

    def calculate_all(
        self,
        temp: float,
        rh: float,
        wind: float,
        rain: float,
        ffmc_prev: float = 85.0,
        dmc_prev: float = 6.0,
        dc_prev: float = 15.0,
        month: int = 7,
        lat: float = 37.5,
    ) -> Dict[str, float]:
        """
        전체 FWI 시스템 계산 (6개 지수)

        Args:
            temp: 기온 (°C, 정오 12시)
            rh: 상대습도 (%, 정오 12시)
            wind: 풍속 (km/h, 정오 12시)
            rain: 24시간 강수량 (mm)
            ffmc_prev: 전날 FFMC 값
            dmc_prev: 전날 DMC 값
            dc_prev: 전날 DC 값
            month: 월 (1-12)
            lat: 위도

        Returns:
            {
                'ffmc': float,  # Fine Fuel Moisture Code
                'dmc': float,   # Duff Moisture Code
                'dc': float,    # Drought Code
                'isi': float,   # Initial Spread Index
                'bui': float,   # Buildup Index
                'fwi': float    # Fire Weather Index
            }
        """
        ffmc = self.calculate_ffmc(temp, rh, wind, rain, ffmc_prev)
        dmc = self.calculate_dmc(temp, rh, rain, dmc_prev, month)
        dc = self.calculate_dc(temp, rain, dc_prev, month, lat)
        isi = self.calculate_isi(ffmc, wind)
        bui = self.calculate_bui(dmc, dc)
        fwi = self.calculate_fwi(isi, bui)

        return {"ffmc": ffmc, "dmc": dmc, "dc": dc, "isi": isi, "bui": bui, "fwi": fwi}

    @staticmethod
    def classify_fwi(fwi: float) -> str:
        """
        FWI 값을 산불 위험 등급으로 분류

        Canadian 기준:
        - Very Low: 0-5
        - Low: 5-11
        - Moderate: 11-21
        - High: 21-38
        - Very High: 38-50
        - Extreme: 50+

        Args:
            fwi: FWI 값

        Returns:
            위험 등급 ('very_low', 'low', 'moderate', 'high', 'very_high', 'extreme')
        """
        if fwi < 5:
            return "very_low"
        elif fwi < 11:
            return "low"
        elif fwi < 21:
            return "moderate"
        elif fwi < 38:
            return "high"
        elif fwi < 50:
            return "very_high"
        else:
            return "extreme"


# 테스트 코드
if __name__ == "__main__":
    calculator = FWICalculator()

    print("\n" + "=" * 80)
    print("Canadian Fire Weather Index (FWI) Calculator 테스트")
    print("=" * 80)

    # 테스트 1: 여름 고온 건조 (산불 위험 높음)
    print("\n[테스트 1] 여름 고온 건조일 (산불 위험 예상)")
    result = calculator.calculate_all(
        temp=32.0,  # 32°C
        rh=25.0,  # 25% (매우 건조)
        wind=20.0,  # 20 km/h (강풍)
        rain=0.0,  # 무강수
        month=7,  # 7월
        lat=37.5,  # 서울 위도
    )

    print(f"  FFMC (Fine Fuel Moisture): {result['ffmc']:.1f}")
    print(f"  DMC (Duff Moisture): {result['dmc']:.1f}")
    print(f"  DC (Drought Code): {result['dc']:.1f}")
    print(f"  ISI (Initial Spread Index): {result['isi']:.1f}")
    print(f"  BUI (Buildup Index): {result['bui']:.1f}")
    print(f"  FWI (Fire Weather Index): {result['fwi']:.1f}")
    print(f"  위험 등급: {calculator.classify_fwi(result['fwi']).upper()}")

    # 테스트 2: 비 온 후 (산불 위험 낮음)
    print("\n[테스트 2] 강수 후 (산불 위험 낮음 예상)")
    result2 = calculator.calculate_all(
        temp=22.0,  # 22°C
        rh=75.0,  # 75% (습함)
        wind=5.0,  # 5 km/h (약풍)
        rain=15.0,  # 15mm 강수
        ffmc_prev=result["ffmc"],  # 전날 값 사용
        dmc_prev=result["dmc"],
        dc_prev=result["dc"],
        month=7,
        lat=37.5,
    )

    print(f"  FFMC: {result2['ffmc']:.1f}")
    print(f"  DMC: {result2['dmc']:.1f}")
    print(f"  DC: {result2['dc']:.1f}")
    print(f"  ISI: {result2['isi']:.1f}")
    print(f"  BUI: {result2['bui']:.1f}")
    print(f"  FWI: {result2['fwi']:.1f}")
    print(f"  위험 등급: {calculator.classify_fwi(result2['fwi']).upper()}")

    print("\n" + "=" * 80)
