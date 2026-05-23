from pathlib import Path
import re

import pandas as pd


base = Path.cwd()

station_candidates = [
    base / "한강_1500m이내_지하철역_환승역통합.xlsx",
    base / "빅데이터자료" / "한강_1500m이내_지하철역_환승역통합.xlsx",
]
ride_candidates = [
    base / "지하철 승하차 인원.xlsx",
    base / "빅데이터자료" / "지하철 승하차 인원.xlsx",
]

station_file = next((path for path in station_candidates if path.exists()), None)
ride_file = next((path for path in ride_candidates if path.exists()), None)

if station_file is None:
    raise FileNotFoundError("한강_1500m이내_지하철역_환승역통합.xlsx 파일을 찾지 못했습니다.")
if ride_file is None:
    raise FileNotFoundError("지하철 승하차 인원.xlsx 파일을 찾지 못했습니다.")

output_file = ride_file.parent / "한강_1500m이내_지하철역_하루평균_승하차인원.xlsx"

stations = pd.read_excel(station_file)
rides = pd.read_excel(ride_file)


def clean_station_name(name):
    name = str(name).strip()
    return re.sub(r"\s+", "", name)


stations["역명_정리"] = stations["역사명"].apply(clean_station_name)
rides["역명_정리"] = rides["역명"].apply(clean_station_name)

# 승하차 자료의 최신 역명과 기준 자료의 기존 역명을 맞춘다.
alias_map = {
    "자양(뚝섬한강공원)": "뚝섬유원지",
}
rides["역명_매칭"] = rides["역명_정리"].replace(alias_map)

target_stations = set(stations["역명_정리"])
filtered = rides[rides["역명_매칭"].isin(target_stations)].copy()
filtered["사용일자"] = pd.to_datetime(
    filtered["사용일자"].astype(str), format="%Y%m%d", errors="coerce"
)
filtered["총승하차인원"] = filtered["승차총승객수"] + filtered["하차총승객수"]

# 같은 역이 여러 노선에 잡힌 날은 역-날짜 단위로 먼저 합산한다.
station_daily = filtered.groupby(
    ["역명_매칭", "사용일자"], as_index=False
)[["승차총승객수", "하차총승객수", "총승하차인원"]].sum()

avg_daily = station_daily.groupby("역명_매칭", as_index=False).agg(
    수집일수=("사용일자", "nunique"),
    하루평균_승차인원=("승차총승객수", "mean"),
    하루평균_하차인원=("하차총승객수", "mean"),
    하루평균_총승하차인원=("총승하차인원", "mean"),
    한달총_승차인원=("승차총승객수", "sum"),
    한달총_하차인원=("하차총승객수", "sum"),
    한달총_총승하차인원=("총승하차인원", "sum"),
)

for col in ["하루평균_승차인원", "하루평균_하차인원", "하루평균_총승하차인원"]:
    avg_daily[col] = avg_daily[col].round(1)

result = avg_daily.merge(
    stations[
        [
            "역사명",
            "호선",
            "ADM_NM",
            "위도",
            "경도",
            "한강거리_m",
            "한강거리_km",
            "역명_정리",
        ]
    ],
    left_on="역명_매칭",
    right_on="역명_정리",
    how="left",
)

result = result[
    [
        "역사명",
        "호선",
        "ADM_NM",
        "위도",
        "경도",
        "한강거리_m",
        "한강거리_km",
        "수집일수",
        "하루평균_승차인원",
        "하루평균_하차인원",
        "하루평균_총승하차인원",
        "한달총_승차인원",
        "한달총_하차인원",
        "한달총_총승하차인원",
    ]
].sort_values("하루평균_총승하차인원", ascending=False)

with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
    result.to_excel(writer, sheet_name="역별_하루평균", index=False)
    station_daily.to_excel(writer, sheet_name="역별_일별합계", index=False)

print(f"완료: {output_file}")
print(f"기준 역 수: {stations['역명_정리'].nunique()}")
print(f"결과 역 수: {result['역사명'].nunique()}")
print(f"수집 기간: {station_daily['사용일자'].min().date()} ~ {station_daily['사용일자'].max().date()}")
