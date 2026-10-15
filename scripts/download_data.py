"""Download public FDEP WAFR facilities and recent Public Notice of Pollution points.
Run: python scripts/download_data.py
Requires internet access and: pip install requests pandas matplotlib
"""
from pathlib import Path
import json, requests, pandas as pd
ROOT=Path(__file__).resolve().parents[1]; DATA=ROOT/'data'; DATA.mkdir(exist_ok=True)
WAFR='https://ags.dep.state.fl.us/arcgis/rest/services/OpenData/WAFR/MapServer/3/query'
PNP='https://ca.dep.state.fl.us/arcgis/rest/services/External_Services/PNP/MapServer/0/query'
S=requests.Session(); S.headers['User-Agent']='FloridaWastewaterResearchDashboard/1.0 (academic research)'
def fetch_layer(url, label):
    rows=[]; offset=0
    while True:
        params={'where':'1=1','outFields':'*','returnGeometry':'true','outSR':'4326','f':'geojson','resultOffset':offset,'resultRecordCount':2000}
        r=S.get(url,params=params,timeout=90); r.raise_for_status(); data=r.json()
        if 'error' in data: raise RuntimeError(f"{label}: {data['error']}")
        features=data.get('features',[]); rows.extend(features)
        print(f'{label}: downloaded {len(rows)} records')
        if len(features)<2000: break
        offset+=len(features)
        if offset>100000: raise RuntimeError('Pagination safety limit reached')
    return {'type':'FeatureCollection','features':rows}
def save_layer(url,label,stem):
    geo=fetch_layer(url,label)
    (DATA/f'{stem}.geojson').write_text(json.dumps(geo,ensure_ascii=False),encoding='utf-8')
    out=[]
    for f in geo['features']:
        p=f.get('properties') or {}; g=f.get('geometry') or {}; xy=g.get('coordinates') or [None,None]
        out.append({**p,'longitude':xy[0],'latitude':xy[1]})
    pd.DataFrame(out).to_csv(DATA/f'{stem}.csv',index=False)
    print(f'Saved data/{stem}.geojson and data/{stem}.csv')
    return geo
if __name__=='__main__':
    save_layer(WAFR,'FDEP WAFR wastewater facilities','fl_wastewater_facilities')
    try:
        save_layer(PNP,'FDEP Public Notice of Pollution (service currently labelled last 30 days)','fdep_pnp_recent')
        print('NOTE: the PNP layer endpoint may be a recent/current view, not a complete historical incident archive.')
    except Exception as e:
        print('Could not download the optional PNP layer:',e)
        print('The WAFR facility download completed if no earlier error occurred.')
