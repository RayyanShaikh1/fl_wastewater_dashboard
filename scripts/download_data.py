"""Download public FDEP WAFR facilities and ten years of Public Notice of Pollution points.
Run: python scripts/download_data.py
Requires internet access and: pip install requests pandas matplotlib
"""
from datetime import date
import os
from pathlib import Path
import json, requests, pandas as pd
ROOT=Path(__file__).resolve().parents[1]; DATA=ROOT/'data'; DATA.mkdir(exist_ok=True)
WAFR='https://ags.dep.state.fl.us/arcgis/rest/services/OpenData/WAFR/MapServer/3/query'
PNP='https://ca.dep.state.fl.us/arcgis/rest/services/External_Services/PNP/MapServer/1/query'
PNP_YEARS=int(os.environ.get('PNP_YEARS','10'))
S=requests.Session(); S.headers['User-Agent']='FloridaWastewaterResearchDashboard/1.0 (academic research)'
def ten_year_start():
    today=date.today()
    try:
        return today.replace(year=today.year-PNP_YEARS)
    except ValueError:
        return today.replace(year=today.year-PNP_YEARS, day=28)
def fetch_layer(url, label, where='1=1'):
    rows=[]; offset=0
    while True:
        params={'where':where,'outFields':'*','returnGeometry':'true','outSR':'4326','f':'geojson','resultOffset':offset,'resultRecordCount':2000}
        r=S.get(url,params=params,timeout=90); r.raise_for_status(); data=r.json()
        if 'error' in data: raise RuntimeError(f"{label}: {data['error']}")
        features=data.get('features',[]); rows.extend(features)
        print(f'{label}: downloaded {len(rows)} records')
        if len(features)<2000: break
        offset+=len(features)
        if offset>100000: raise RuntimeError('Pagination safety limit reached')
    return {'type':'FeatureCollection','features':rows}
def save_layer(url,label,stem,where='1=1'):
    geo=fetch_layer(url,label,where)
    (DATA/f'{stem}.geojson').write_text(json.dumps(geo,ensure_ascii=False),encoding='utf-8')
    out=[]
    for f in geo['features']:
        p=f.get('properties') or {}; g=f.get('geometry') or {}; xy=g.get('coordinates') or [None,None]
        out.append({**p,'longitude':xy[0],'latitude':xy[1]})
    pd.DataFrame(out).to_csv(DATA/f'{stem}.csv',index=False)
    print(f'Saved data/{stem}.geojson and data/{stem}.csv')
    return geo
def save_year_partitions(geo):
    years={}
    for feature in geo['features']:
        value=(feature.get('properties') or {}).get('DATE_TIME_OF_REPORT')
        if value:
            year=pd.to_datetime(value,unit='ms',errors='coerce').year
            if pd.notna(year):
                years.setdefault(str(int(year)),[]).append(feature)
    for year,features in years.items():
        partition={'type':'FeatureCollection','features':features}
        (DATA/f'fdep_pnp_{year}.geojson').write_text(json.dumps(partition,ensure_ascii=False),encoding='utf-8')
        pd.DataFrame([{**(f.get('properties') or {}),
                       'longitude':(f.get('geometry') or {}).get('coordinates',[None,None])[0],
                       'latitude':(f.get('geometry') or {}).get('coordinates',[None,None])[1]}
                      for f in features]).to_csv(DATA/f'fdep_pnp_{year}.csv',index=False)
    (DATA/'pnp_years.json').write_text(json.dumps(sorted(years)),encoding='utf-8')
    print(f'Saved {len(years)} yearly PNP partitions')
if __name__=='__main__':
    save_layer(WAFR,'FDEP WAFR wastewater facilities','fl_wastewater_facilities')
    try:
        start=ten_year_start()
        where=f"DATE_TIME_OF_REPORT >= DATE '{start.isoformat()}'"
        pnp=save_layer(PNP,f'FDEP Public Notice of Pollution (last {PNP_YEARS} years)','fdep_pnp_10y',where)
        save_year_partitions(pnp)
        print(f'PNP query start date: {start.isoformat()}')
    except Exception as e:
        print('Could not download the optional PNP layer:',e)
        print('The WAFR facility download completed if no earlier error occurred.')
