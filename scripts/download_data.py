"""Download the FDEP data required by the dashboard.
Run: python scripts/download_data.py
Requires internet access and: pip install requests pandas matplotlib
"""
from datetime import date
import os
from pathlib import Path
import json
import re
import requests
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]; DATA=ROOT/'data'; DATA.mkdir(exist_ok=True)
WAFR='https://ags.dep.state.fl.us/arcgis/rest/services/OpenData/WAFR/MapServer/3/query'
PNP='https://ca.dep.state.fl.us/arcgis/rest/services/External_Services/PNP/MapServer/1/query'
PNP_YEARS=int(os.environ.get('PNP_YEARS','10'))
WAFR_FIELDS=('FACILITY_ID','FACILITY_NAME','FACILITY_TYPE','FACILITY_STATUS','COUNTY_NAME')
PNP_FIELDS=('OBJECTID','INCIDENT_NUMBER','INCIDENT_NAME','INCIDENT_REPORT','DATE_TIME_OF_REPORT','FACILITY_NAME','AFFECTED_COUNTIES')
S=requests.Session(); S.headers['User-Agent']='FloridaWastewaterResearchDashboard/1.0 (academic research)'


def incident_type(name, report):
    text=f'{name} {report}'.lower()
    categories=(
        ('Hurricane / tropical storm', ('hurricane', 'tropical storm', 'tropical depression')),
        ('Flooding', ('flood', 'flooding', 'inundat', 'stormwater')),
        ('Storm surge', ('storm surge',)),
        ('Heavy rainfall', ('heavy rain', 'heavy rainfall', 'downpour', 'extreme precipitation')),
        ('Sewer overflow', ('sewer overflow', 'sewage overflow', 'wastewater overflow', 'manhole overflow', 'sso')),
        ('Oil / chemical spill', ('oil spill', 'hydraulic', 'gasoline', 'diesel', 'chemical spill', 'fuel spill')),
        ('Wastewater spill', ('wastewater spill', 'sewage spill', 'wastewater discharged', 'sewage discharged')),
    )
    for category, terms in categories:
        if any(term in text for term in terms):
            return category
    return 'Other'


def gallons_discharged(report):
    text=str(report or '')
    for sentence in re.split(r'(?<=[.!?])\s+', text):
        lower=sentence.lower()
        if not any(term in lower for term in ('gallon', 'gal.')):
            continue
        if not any(term in lower for term in ('discharg', 'spill', 'release', 'overflow', 'lost', 'loss')):
            continue
        candidates=re.findall(
            r'(?<![\d.])(\d[\d,]*(?:\.\d+)?)\s*(million\s+)?(?:gallons?|gal\.)',
            sentence,
            flags=re.IGNORECASE,
        )
        for value, multiplier in candidates:
            number=float(value.replace(',', '')) * (1_000_000 if multiplier else 1)
            before=lower[:lower.find(value.lower())]
            if any(term in before[-40:] for term in ('recover', 'collect', 'pump', 'reclaim')):
                continue
            return int(number) if number.is_integer() else number
    return None


def enrich_incident(feature):
    properties=feature.get('properties') or {}
    properties['incident_type']=incident_type(
        properties.get('INCIDENT_NAME'),
        properties.get('INCIDENT_REPORT'),
    )
    properties['gallons_discharged']=gallons_discharged(properties.get('INCIDENT_REPORT'))
    feature['properties']=properties


def ten_year_start():
    today=date.today()
    try:
        return today.replace(year=today.year-PNP_YEARS)
    except ValueError:
        return today.replace(year=today.year-PNP_YEARS, day=28)
def fetch_layer(url, label, fields, where='1=1'):
    rows=[]; offset=0
    while True:
        params={'where':where,'outFields':','.join(fields),'returnGeometry':'true','outSR':'4326','f':'geojson','resultOffset':offset,'resultRecordCount':2000}
        r=S.get(url,params=params,timeout=90); r.raise_for_status(); data=r.json()
        if 'error' in data: raise RuntimeError(f"{label}: {data['error']}")
        features=data.get('features',[])
        if url == PNP:
            for feature in features:
                enrich_incident(feature)
        rows.extend(features)
        print(f'{label}: downloaded {len(rows)} records')
        if len(features)<2000: break
        offset+=len(features)
        if offset>100000: raise RuntimeError('Pagination safety limit reached')
    return {'type':'FeatureCollection','features':rows}


def save_layer(url,label,stem,fields,where='1=1',save_csv=False):
    geo=fetch_layer(url,label,fields,where)
    (DATA/f'{stem}.geojson').write_text(json.dumps(geo,ensure_ascii=False),encoding='utf-8')
    if save_csv:
        rows=[]
        for feature in geo['features']:
            properties=feature.get('properties') or {}
            coordinates=(feature.get('geometry') or {}).get('coordinates') or [None, None]
            rows.append({
                **properties,
                'longitude': coordinates[0],
                'latitude': coordinates[1],
            })
        pd.DataFrame(rows).to_csv(DATA/f'{stem}.csv',index=False)
        print(f'Saved data/{stem}.geojson and data/{stem}.csv')
    else:
        print(f'Saved data/{stem}.geojson')
    return geo


if __name__=='__main__':
    save_layer(WAFR,'FDEP WAFR wastewater facilities','fl_wastewater_facilities',WAFR_FIELDS)
    try:
        start=ten_year_start()
        where=f"DATE_TIME_OF_REPORT >= DATE '{start.isoformat()}'"
        save_layer(PNP,f'FDEP Public Notice of Pollution (last {PNP_YEARS} years)','fdep_pnp_10y',PNP_FIELDS,where,save_csv=True)
        print(f'PNP query start date: {start.isoformat()}')
    except Exception as e:
        print('Could not download the optional PNP layer:',e)
        print('The WAFR facility download completed if no earlier error occurred.')
