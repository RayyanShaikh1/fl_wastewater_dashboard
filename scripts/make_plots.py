"""Create exploratory PNG plots from the downloaded WAFR CSV.
Run: python scripts/make_plots.py
"""
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[1]; DATA=ROOT/'data'; OUT=ROOT/'plots'; OUT.mkdir(exist_ok=True)
p=DATA/'fl_wastewater_facilities.csv'
if not p.exists(): raise SystemExit('Missing data/fl_wastewater_facilities.csv. Run python scripts/download_data.py first.')
df=pd.read_csv(p,low_memory=False)
lat=next((c for c in df.columns if c.lower() in ('latitude','lat')),None); lon=next((c for c in df.columns if c.lower() in ('longitude','lon','long')),None)
if lat is None or lon is None: raise SystemExit('No latitude/longitude columns found in downloaded facility file.')
xy=df[[lon,lat]].apply(pd.to_numeric,errors='coerce').dropna(); xy=xy[xy[lat].between(24,32.5)&xy[lon].between(-88,-79)]
plt.figure(figsize=(8,9)); plt.scatter(xy[lon],xy[lat],s=5,alpha=.5); plt.xlim(-88,-79);plt.ylim(24,32.5);plt.xlabel('Longitude');plt.ylabel('Latitude');plt.title(f'FDEP WAFR wastewater facility locations in Florida (n={len(xy):,})');plt.grid(alpha=.2);plt.tight_layout();plt.savefig(OUT/'florida_facility_locations.png',dpi=180);plt.close()
def find_col(candidates):
    for cand in candidates:
        for c in df.columns:
            if cand in c.lower(): return c
    return None
for title,candidates,name in [('Operating status',['operating_status','facility_status','status'],'facilities_by_status'),('Program / facility type',['program_name','program','facility_type','type'],'facilities_by_type')]:
    c=find_col(candidates)
    if c:
        counts=df[c].fillna('Not specified').astype(str).value_counts().head(15).sort_values()
        plt.figure(figsize=(9,6));counts.plot(kind='barh');plt.xlabel('Number of facilities');plt.title(f'Florida wastewater facilities by {title.lower()}');plt.tight_layout();plt.savefig(OUT/f'{name}.png',dpi=180);plt.close()
print('Plots written to plots/. Note: location scatter is a coordinate plot, not a county boundary map; use index.html for the Leaflet basemap.')
