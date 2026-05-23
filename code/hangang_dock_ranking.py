from __future__ import annotations

import argparse
import html
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


LATITUDE_NAMES = ("위도", "lat", "latitude", "LAT", "Latitude")
LONGITUDE_NAMES = ("경도", "lon", "lng", "longitude", "LON", "LNG", "Longitude")
FEATURE_COLUMNS = [
    "n_nearest_subway_access",
    "n_nearby_subway_demand",
    "n_population",
    "n_workers",
    "n_hotplace",
    "n_dock_spacing",
]


@dataclass(frozen=True)
class RankingConfig:
    subway_radius_m: float = 1500.0
    population_radius_m: float = 2000.0
    poi_radius_m: float = 2000.0
    dock_exclusion_m: float = 1000.0
    dock_spacing_cap_m: float = 5000.0
    top_n: int = 10
    random_state: int = 42
    weights: tuple[float, float, float, float, float, float] = (
        0.22,
        0.18,
        0.12,
        0.13,
        0.25,
        0.10,
    )


def haversine_matrix_m(
    left_lat: np.ndarray,
    left_lon: np.ndarray,
    right_lat: np.ndarray,
    right_lon: np.ndarray,
) -> np.ndarray:
    """Return the pairwise great-circle distance matrix in meters."""
    radius_m = 6_371_000.0
    left_phi = np.radians(left_lat)[:, None]
    right_phi = np.radians(right_lat)[None, :]
    delta_phi = np.radians(right_lat[None, :] - left_lat[:, None])
    delta_lambda = np.radians(right_lon[None, :] - left_lon[:, None])
    a = (
        np.sin(delta_phi / 2.0) ** 2
        + np.cos(left_phi) * np.cos(right_phi) * np.sin(delta_lambda / 2.0) ** 2
    )
    return radius_m * 2.0 * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def minmax(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce").fillna(0.0)
    lower = values.min()
    upper = values.max()
    if upper <= lower:
        return pd.Series(0.0, index=series.index)
    return (values - lower) / (upper - lower)


def _numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.astype(str).str.replace(",", "", regex=False).str.strip(),
        errors="coerce",
    ).fillna(0.0)


def _first_column(frame: pd.DataFrame, names: tuple[str, ...]) -> str | None:
    return next((name for name in names if name in frame.columns), None)


def prepare_candidate_frame(candidates: pd.DataFrame) -> pd.DataFrame:
    """Normalize a candidate DataFrame to candidate_id, 위도, 경도."""
    result = candidates.copy()
    lat_col = _first_column(result, LATITUDE_NAMES)
    lon_col = _first_column(result, LONGITUDE_NAMES)

    if lat_col is None or lon_col is None:
        raise ValueError(
            "Candidate coordinates need latitude/longitude columns such as "
            "'위도' and '경도' or 'lat' and 'lon'."
        )

    result["위도"] = _numeric(result[lat_col])
    result["경도"] = _numeric(result[lon_col])
    result = result[
        result["위도"].between(33.0, 39.5) & result["경도"].between(124.0, 132.0)
    ].copy()
    result = result.drop_duplicates(subset=["위도", "경도"]).reset_index(drop=True)
    if result.empty:
        raise ValueError("No valid candidate coordinates remain after normalization.")

    if "후보ID" not in result.columns:
        result.insert(0, "후보ID", np.arange(1, len(result) + 1))
    return result


def load_reference_workbook(data_path: str | Path) -> dict[str, pd.DataFrame]:
    sheets = pd.read_excel(data_path, sheet_name=None)
    expected = {"지하철역", "한강버스선착장", "관광명소", "야경명소", "한강1km행정동"}
    missing = expected.difference(sheets)
    if missing:
        raise ValueError(f"Missing workbook sheets: {', '.join(sorted(missing))}")

    subway = sheets["지하철역"].copy()
    subway["하루평균_총이용량"] = _numeric(subway["하루평균_총이용량"])
    subway["행정동_인구수"] = _numeric(subway["행정동_인구수"])
    subway["행정동_총종사자수"] = _numeric(subway["행정동_총종사자수"])

    docks = sheets["한강버스선착장"].copy()
    pois = pd.concat(
        [
            sheets["관광명소"].assign(장소유형="관광명소"),
            sheets["야경명소"].assign(장소유형="야경명소"),
        ],
        ignore_index=True,
    )
    pois["월평균_SNS언급횟수"] = _numeric(pois["월평균_SNS언급횟수"])
    positive_sns = pois.loc[pois["월평균_SNS언급횟수"] > 0, "월평균_SNS언급횟수"]
    default_sns = float(positive_sns.median()) if not positive_sns.empty else 1.0
    pois["SNS_피처값"] = pois["월평균_SNS언급횟수"].mask(
        pois["월평균_SNS언급횟수"] <= 0,
        default_sns,
    )

    return {
        "subway": subway,
        "docks": docks,
        "pois": pois,
        "admin": sheets["한강1km행정동"].copy(),
    }


def _distance_decay(distances_m: np.ndarray, radius_m: float) -> np.ndarray:
    return np.clip(1.0 - distances_m / radius_m, 0.0, 1.0)


def _dong_weighted_features(
    subway: pd.DataFrame,
    candidate_to_subway_m: np.ndarray,
    config: RankingConfig,
) -> tuple[np.ndarray, np.ndarray]:
    """Use each nearby dong once, represented by its nearest subway station."""
    populations = np.zeros(candidate_to_subway_m.shape[0])
    workers = np.zeros(candidate_to_subway_m.shape[0])
    dong_names = subway["행정동"].fillna("미상").astype(str)

    for dong_name in dong_names.drop_duplicates():
        station_indexes = np.flatnonzero(dong_names.to_numpy() == dong_name)
        dong_distances = candidate_to_subway_m[:, station_indexes].min(axis=1)
        decay = _distance_decay(dong_distances, config.population_radius_m)
        populations += decay * float(subway.iloc[station_indexes]["행정동_인구수"].max())
        workers += decay * float(subway.iloc[station_indexes]["행정동_총종사자수"].max())
    return populations, workers


def engineer_features(
    candidates: pd.DataFrame,
    references: dict[str, pd.DataFrame],
    config: RankingConfig | None = None,
) -> pd.DataFrame:
    config = config or RankingConfig()
    result = prepare_candidate_frame(candidates)
    subway = references["subway"].dropna(subset=["위도", "경도"]).reset_index(drop=True)
    docks = references["docks"].dropna(subset=["위도", "경도"]).reset_index(drop=True)
    pois = references["pois"].dropna(subset=["위도", "경도"]).reset_index(drop=True)

    candidate_lat = result["위도"].to_numpy(float)
    candidate_lon = result["경도"].to_numpy(float)
    subway_distance = haversine_matrix_m(
        candidate_lat,
        candidate_lon,
        subway["위도"].to_numpy(float),
        subway["경도"].to_numpy(float),
    )
    dock_distance = haversine_matrix_m(
        candidate_lat,
        candidate_lon,
        docks["위도"].to_numpy(float),
        docks["경도"].to_numpy(float),
    )
    poi_distance = haversine_matrix_m(
        candidate_lat,
        candidate_lon,
        pois["위도"].to_numpy(float),
        pois["경도"].to_numpy(float),
    )

    nearest_station_pos = subway_distance.argmin(axis=1)
    nearest_station = subway.iloc[nearest_station_pos].reset_index(drop=True)
    nearest_subway_distance = subway_distance[np.arange(len(result)), nearest_station_pos]
    nearest_subway_demand = nearest_station["하루평균_총이용량"].to_numpy(float)
    subway_decay = _distance_decay(subway_distance, config.subway_radius_m)
    poi_decay = _distance_decay(poi_distance, config.poi_radius_m)
    population_feature, worker_feature = _dong_weighted_features(
        subway,
        subway_distance,
        config,
    )

    result["가까운_지하철역"] = nearest_station["역명"].to_numpy()
    result["가까운_지하철역_거리(m)"] = nearest_subway_distance.round(1)
    result["가까운_지하철역_하루평균_총이용량"] = nearest_subway_demand.round(1)
    result["f_nearest_subway_access"] = (
        nearest_subway_demand * _distance_decay(nearest_subway_distance, config.subway_radius_m)
    )
    result["f_nearby_subway_demand"] = (
        subway_decay * subway["하루평균_총이용량"].to_numpy(float)[None, :]
    ).sum(axis=1)
    result["f_population"] = population_feature
    result["f_workers"] = worker_feature
    result["주변_POI_개수"] = (poi_distance <= config.poi_radius_m).sum(axis=1)
    result["f_hotplace"] = (
        poi_decay * pois["SNS_피처값"].to_numpy(float)[None, :]
    ).sum(axis=1)
    result["기존선착장_최소거리(m)"] = dock_distance.min(axis=1).round(1)
    result["f_dock_spacing"] = result["기존선착장_최소거리(m)"].clip(
        lower=0.0,
        upper=config.dock_spacing_cap_m,
    )
    result["기존선착장_중복제외"] = (
        result["기존선착장_최소거리(m)"] < config.dock_exclusion_m
    )

    feature_map = {
        "n_nearest_subway_access": "f_nearest_subway_access",
        "n_nearby_subway_demand": "f_nearby_subway_demand",
        "n_population": "f_population",
        "n_workers": "f_workers",
        "n_hotplace": "f_hotplace",
        "n_dock_spacing": "f_dock_spacing",
    }
    for normalized, raw in feature_map.items():
        result[normalized] = minmax(result[raw])

    weights = np.asarray(config.weights, dtype=float)
    if not np.isclose(weights.sum(), 1.0):
        raise ValueError("RankingConfig.weights must sum to 1.0.")
    result["baseline_score"] = result[FEATURE_COLUMNS].to_numpy(float).dot(weights) * 100.0
    return result


def rank_with_xgboost(
    features: pd.DataFrame,
    config: RankingConfig | None = None,
    allow_baseline_fallback: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Rank candidates with XGBoost trained on the engineered baseline score.

    There is no observed dock-demand label in the reference workbook, so the
    weighted baseline score is the pseudo-label for the model.
    """
    config = config or RankingConfig()
    eligible = features.loc[~features["기존선착장_중복제외"]].copy()
    if eligible.empty:
        raise ValueError("All candidates are inside the existing-dock exclusion radius.")

    X = eligible[FEATURE_COLUMNS].to_numpy(float)
    y = eligible["baseline_score"].to_numpy(float)
    model_name = "XGBoost"
    try:
        from xgboost import XGBRegressor

        model = XGBRegressor(
            n_estimators=350,
            max_depth=4,
            learning_rate=0.04,
            subsample=0.9,
            colsample_bytree=0.9,
            objective="reg:squarederror",
            random_state=config.random_state,
            verbosity=0,
        )
        model.fit(X, y)
        eligible["xgb_score"] = np.clip(model.predict(X), 0.0, 100.0)
        importances = model.feature_importances_
    except ModuleNotFoundError as exc:
        if not allow_baseline_fallback:
            raise ModuleNotFoundError(
                "xgboost is required for model ranking. Install it in the notebook "
                "kernel or call rank_with_xgboost(..., allow_baseline_fallback=True) "
                "for a baseline-only smoke test."
            ) from exc
        model_name = "baseline_fallback"
        eligible["xgb_score"] = eligible["baseline_score"]
        importances = np.asarray(config.weights, dtype=float)

    eligible["baseline_rank"] = (
        eligible["baseline_score"].rank(ascending=False, method="first").astype(int)
    )
    eligible["xgb_rank"] = (
        eligible["xgb_score"].rank(ascending=False, method="first").astype(int)
    )
    eligible["rank_change"] = eligible["baseline_rank"] - eligible["xgb_rank"]
    eligible["ranking_model"] = model_name
    eligible = eligible.sort_values(["xgb_rank", "baseline_rank"]).reset_index(drop=True)

    importance = pd.DataFrame(
        {
            "feature": FEATURE_COLUMNS,
            "importance": importances,
            "baseline_weight": config.weights,
        }
    ).sort_values("importance", ascending=False)
    return eligible, importance


def _leaflet_payload(frame: pd.DataFrame, columns: list[str]) -> list[dict[str, Any]]:
    clean = frame[columns].replace({np.nan: None})
    return clean.to_dict(orient="records")


def save_interactive_map(
    ranked: pd.DataFrame,
    docks: pd.DataFrame,
    output_path: str | Path,
    top_n: int = 10,
) -> Path:
    output_path = Path(output_path)
    all_points = _leaflet_payload(
        ranked,
        [
            "후보ID",
            "위도",
            "경도",
            "xgb_rank",
            "xgb_score",
            "baseline_score",
            "가까운_지하철역",
            "가까운_지하철역_거리(m)",
            "가까운_지하철역_하루평균_총이용량",
            "f_population",
            "f_workers",
            "f_hotplace",
            "기존선착장_최소거리(m)",
        ],
    )
    top_points = all_points[:top_n]
    dock_points = _leaflet_payload(docks, ["위도", "경도", "선착장명", "주소"])
    center_lat = float(ranked["위도"].mean())
    center_lon = float(ranked["경도"].mean())

    def dump(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False)

    title = html.escape("한강버스 선착장 TOP 10 후보")
    page = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
  <style>
    html, body, #map {{ height: 100%; margin: 0; font-family: Arial, sans-serif; }}
    .panel {{
      position: absolute; z-index: 500; top: 16px; left: 16px; width: min(360px, calc(100vw - 48px));
      padding: 14px 16px; background: rgba(255,255,255,.96); border: 1px solid #d7dde5;
      box-shadow: 0 10px 30px rgba(25,39,52,.16); border-radius: 8px; color: #16212d;
    }}
    .panel h1 {{ font-size: 18px; line-height: 1.25; margin: 0 0 8px; }}
    .panel p {{ font-size: 13px; line-height: 1.45; margin: 4px 0; }}
    .rank-label {{
      display: grid; place-items: center; width: 24px; height: 24px; border-radius: 50%;
      background: #0f766e; border: 2px solid white; color: white; font: bold 12px Arial;
      box-shadow: 0 2px 10px rgba(0,0,0,.25);
    }}
    .leaflet-popup-content {{ line-height: 1.45; }}
  </style>
</head>
<body>
  <div class="panel">
    <h1>{title}</h1>
    <p>초록 숫자는 XGBoost TOP {top_n}, 파랑 점은 전체 후보, 빨강 표시는 기존 선착장입니다.</p>
    <p>기존 선착장과 너무 가까운 후보를 제외한 뒤 랭킹 결과를 표시합니다.</p>
  </div>
  <div id="map"></div>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script>
    const candidates = {dump(all_points)};
    const topPoints = {dump(top_points)};
    const docks = {dump(dock_points)};
    const map = L.map("map").setView([{center_lat:.6f}, {center_lon:.6f}], 12);
    L.tileLayer("https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png", {{
      maxZoom: 19, attribution: "&copy; OpenStreetMap contributors"
    }}).addTo(map);
    const fmt = value => Number(value || 0).toLocaleString("ko-KR", {{maximumFractionDigits: 1}});
    const candidateLayer = L.layerGroup().addTo(map);
    candidates.forEach(point => {{
      L.circleMarker([point["위도"], point["경도"]], {{
        radius: 4, weight: 1, color: "#2563eb", fillColor: "#60a5fa", fillOpacity: .45
      }}).bindPopup(`
        <b>후보 ${{point["후보ID"]}}</b><br>
        XGBoost 순위: ${{point["xgb_rank"]}}위<br>
        XGBoost 점수: ${{fmt(point["xgb_score"])}}<br>
        가까운 역: ${{point["가까운_지하철역"]}} (${{fmt(point["가까운_지하철역_거리(m)"])}}m)<br>
        기존 선착장 거리: ${{fmt(point["기존선착장_최소거리(m)"])}}m
      `).addTo(candidateLayer);
    }});
    docks.forEach(point => {{
      L.circleMarker([point["위도"], point["경도"]], {{
        radius: 8, weight: 2, color: "#b91c1c", fillColor: "#ef4444", fillOpacity: .9
      }}).bindPopup(`<b>기존 선착장</b><br>${{point["선착장명"]}}<br>${{point["주소"] || ""}}`).addTo(map);
    }});
    const topLayer = L.layerGroup().addTo(map);
    topPoints.forEach(point => {{
      const marker = L.marker([point["위도"], point["경도"]], {{
        icon: L.divIcon({{className: "", html: `<div class="rank-label">${{point["xgb_rank"]}}</div>`}})
      }}).bindPopup(`
        <b>#${{point["xgb_rank"]}} 후보 ${{point["후보ID"]}}</b><br>
        XGBoost 점수: ${{fmt(point["xgb_score"])}}<br>
        베이스라인: ${{fmt(point["baseline_score"])}}<br>
        가까운 역: ${{point["가까운_지하철역"]}}<br>
        역 거리: ${{fmt(point["가까운_지하철역_거리(m)"])}}m<br>
        역 이용량: ${{fmt(point["가까운_지하철역_하루평균_총이용량"])}}명/일<br>
        주변 인구 피처: ${{fmt(point["f_population"])}}<br>
        주변 직장인 피처: ${{fmt(point["f_workers"])}}<br>
        핫플 피처: ${{fmt(point["f_hotplace"])}}
      `).addTo(topLayer);
    }});
    L.control.layers(null, {{"전체 후보": candidateLayer, "TOP 10": topLayer}}).addTo(map);
    const bounds = L.latLngBounds(candidates.map(point => [point["위도"], point["경도"]]));
    if (bounds.isValid()) map.fitBounds(bounds.pad(.12));
  </script>
</body>
</html>
"""
    output_path.write_text(page, encoding="utf-8")
    return output_path


def export_ranking(
    ranked: pd.DataFrame,
    importance: pd.DataFrame,
    config: RankingConfig,
    references: dict[str, pd.DataFrame],
    output_prefix: str | Path = "한강버스_선착장_후보_랭킹",
) -> dict[str, Path]:
    prefix = Path(output_prefix)
    excel_path = prefix.with_suffix(".xlsx")
    map_path = prefix.with_name(f"{prefix.name}_지도").with_suffix(".html")
    top10 = ranked.head(config.top_n).copy()
    config_rows = pd.DataFrame(
        {
            "항목": list(asdict(config)),
            "값": [str(value) for value in asdict(config).values()],
        }
    )

    with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
        ranked.to_excel(writer, sheet_name="전체후보", index=False)
        top10.to_excel(writer, sheet_name="TOP10", index=False)
        importance.to_excel(writer, sheet_name="피처중요도", index=False)
        config_rows.to_excel(writer, sheet_name="설정", index=False)

    save_interactive_map(top10 if len(ranked) == len(top10) else ranked, references["docks"], map_path, config.top_n)
    return {"excel": excel_path, "map": map_path}


def run_ranking(
    candidates: pd.DataFrame,
    data_path: str | Path = "최종_한강_모든_장소_통합_정보.xlsx",
    output_prefix: str | Path = "한강버스_선착장_후보_랭킹",
    config: RankingConfig | None = None,
    allow_baseline_fallback: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Path]]:
    config = config or RankingConfig()
    references = load_reference_workbook(data_path)
    features = engineer_features(candidates, references, config)
    ranked, importance = rank_with_xgboost(features, config, allow_baseline_fallback)
    outputs = export_ranking(ranked, importance, config, references, output_prefix)
    return ranked, importance, outputs


def _read_candidates(path: Path) -> pd.DataFrame:
    if path.suffix.lower() in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    raise ValueError("Candidate file must be .csv, .xlsx, or .xls.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rank Han River dock candidate coordinates with workbook features."
    )
    parser.add_argument("--candidates", type=Path, required=True, help="Candidate CSV or Excel file.")
    parser.add_argument(
        "--data",
        type=Path,
        default=Path("최종_한강_모든_장소_통합_정보.xlsx"),
        help="Workbook containing subway, dock, POI, and dong sheets.",
    )
    parser.add_argument(
        "--output-prefix",
        type=Path,
        default=Path("한강버스_선착장_후보_랭킹"),
        help="Output path prefix for Excel and HTML map.",
    )
    parser.add_argument(
        "--allow-baseline-fallback",
        action="store_true",
        help="Save a baseline-only smoke-test ranking when xgboost is unavailable.",
    )
    args = parser.parse_args()
    ranked, _, outputs = run_ranking(
        _read_candidates(args.candidates),
        args.data,
        args.output_prefix,
        allow_baseline_fallback=args.allow_baseline_fallback,
    )
    print(f"ranked candidates: {len(ranked)}")
    print(f"excel: {outputs['excel']}")
    print(f"map: {outputs['map']}")


if __name__ == "__main__":
    main()
