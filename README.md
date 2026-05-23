# Demand-Driven Hangang River Bus Operation Optimization

This project proposes a demand-driven optimization framework for Han River Bus operation by integrating geospatial analysis, demand modeling, machine learning-based feature optimization, dock recommendation, and route planning.

The analysis considers subway accessibility, subway ridership demand, administrative-dong population and worker counts, nearby tourist/night-view places, and distance from existing docks.

📄 Presentation: [PDF Slides](./스마트%20한강버스%20운영%20시스템.pdf)

🌐 Interactive Map:
https://kyungwo0lee.github.io/Hangang-River-Bus/

## Repository Structure

- `code/`: Jupyter notebooks documenting development process, exploratory analysis, modeling pipeline, and helper Python scripts
- `outputs/`: Final processed Excel datasets
- `maps/`: Final interactive HTML maps
- `figures/`: Images used for presentation or documentation


## Project Goal

This project aims to optimize Hangang River Bus operation through:

1. Demand prediction using spatial and transportation data
2. Recommendation of additional dock locations
3. Demand-driven route planning
4. Data-driven operation optimization

## Methodology

1. Collect public transportation and geospatial datasets

2. Construct analysis region
- 1 km administrative-dong influence zone
- 1.5 km Hangang boundary analysis region

3. Build spatial demand features
- Subway accessibility
- Subway ridership
- Population
- Worker counts
- Tourist attractions
- SNS popularity

4. Apply Min-Max normalization

5. Optimize feature weights using Random Search

6. Generate dock candidates at 200 m intervals along the Han River

7. Generate candidate docks

8. Cluster candidate locations

9. Select representative dock locations

10. Design optimized Hangang River Bus routes


## Major Results

Recommended additional docks:

- Banpo
- Seogang
- Seoul Forest
- Guui
- Ichon

New demand-driven routes were proposed based on predicted passenger demand patterns.


## Project Scope

The repository includes final deliverables as well as selected development artifacts to improve transparency and reproducibility.

Included materials:

- Final processed datasets
- Interactive maps and visual outputs
- Final analysis notebooks
- Jupyter notebooks showing the development process, exploratory analysis, and intermediate experimentation
- Helper Python scripts and supporting code

Excluded materials:

- Cache files (`__pycache__/`)
- Random temporary files
- Extremely large raw geospatial source files
- Duplicate or unnecessary intermediate outputs

The repository is curated to balance reproducibility, readability, and repository size.

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


## Tech Stack

- Python
- GeoPandas
- Pandas
- NumPy
- Scikit-learn
- Folium
- Jupyter Notebook
- GIS / Spatial Analysis

---
## Author

**Kyungwoo Lee**  
Undergraduate Student, Mechanical Engineering
