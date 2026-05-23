# Han River Bus Dock Location Analysis

This repository contains the final analysis outputs for comparing candidate locations for new Han River Bus docks in Seoul. 

The analysis considers subway accessibility, subway ridership demand, administrative-dong population and worker counts, nearby tourist/night-view places, and distance from existing docks.

📄 Presentation: [PDF Slides](./스마트%20한강버스%20운영%20시스템.pdf)

🌐 Interactive Map:
https://kyungwo0lee.github.io/Hangang-River-Bus/

## Repository Structure

- `code/`: Final analysis notebook and helper Python scripts
- `outputs/`: Final processed Excel datasets
- `maps/`: Final interactive HTML maps
- `figures/`: Images used for presentation or documentation

## Curation Criteria

Only the final deliverables are included. Intermediate experiments, cache files, temporary files, and large raw SHP source files were excluded to keep the repository lightweight and readable.

Examples of excluded files:

- `test.ipynb`
- `__pycache__/`
- Randomly named 4-byte temporary files
- Large raw geospatial files such as `N3A_E0032111.*` and `BND_ADM_DONG_PG.*`
- Intermediate maps and experiment-specific candidate maps

## Key Deliverables

- `maps/최종_지하철역_지도_서울영역_기존신규선착장_레이어분리.html`
- `maps/한강버스_TOP30_97016_지도.html`
- `maps/한강버스_TOP30_97016_클러스터만_지도.html`
- `outputs/최종_한강_모든_장소_통합_정보.xlsx`
- `outputs/최종_한강_1500m이내_지하철역_하루평균_이용량.xlsx`
- `outputs/최종_한강주변_행정동_직장수_인구수.xlsx`
- `outputs/최종_한강_1_5km이내_관광명소_야경명소.xlsx`
- `outputs/최종_지하철역.xlsx`

## Raw Data Note

Raw source data is not included because of file size and redistribution considerations. To reproduce the analysis, download the required public datasets from sources such as Seoul Open Data Plaza, public data portals, or geospatial data portals, then place them according to the paths expected by the notebook and scripts in `code/`.
