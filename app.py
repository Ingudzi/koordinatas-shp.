import io, json, zipfile
import pandas as pd
import streamlit as st
import requests
from shapely.geometry import shape
from shapely.ops import unary_union
from core import geometry, country_status, export_zip, LV_BBOX
from ocr import pages, read_image

st.set_page_config(page_title='Koordinātas → SHP',page_icon='🗺️',layout='wide')
st.title('🗺️ Koordinātas → SHP')
st.write('Augšupielādē koordinātu tabulu, pārbaudi atpazītās virsotnes un saņem QGIS poligona ZIP arhīvu (EPSG:3059).')
st.warning('OCR var kļūdīties! Pirms SHP izveides obligāti pārbaudi visas koordinātas pret attēlu.')

# GeoBoundaries public ADM0 dataset; if unavailable the app fails closed.
@st.cache_data(ttl=86400,show_spinner=False)
def get_boundary():
    url='https://www.geoboundaries.org/api/current/gbOpen/LVA/ADM0/'
    try:
        r=requests.get(url,timeout=12);r.raise_for_status()
        meta=r.json()
        geo=requests.get(meta['gjDownloadURL'],timeout=25);geo.raise_for_status()
        obj=geo.json()
        geoms=[shape(f['geometry']) for f in obj['features']] if obj['type']=='FeatureCollection' else [shape(obj['geometry'] if obj['type']=='Feature' else obj)]
        return unary_union(geoms)
    except Exception:
        return None

uploads=st.file_uploader('Pievieno attēlus vai PDF',type=['jpg','jpeg','png','pdf'],accept_multiple_files=True)
if not uploads: st.info('Pievieno pirmo failu. Katrs fails tiek apstrādāts atsevišķi.')
all_zips=[]
for ix,f in enumerate(uploads,1):
    with st.expander(f'{ix}. {f.name}',expanded=True):
        key=f'{ix}_{f.name}_{f.size}'
        if st.session_state.get(f'key_{ix}')!=key:
            st.session_state[f'key_{ix}']=key
            st.session_state.pop(f'rows_{ix}',None)
            st.session_state.pop(f'ocr_{ix}',None)
        if f'rows_{ix}' not in st.session_state:
            try:
                found=[];raw=[]
                for page in pages(f.getvalue(),f.name.rsplit('.',1)[-1]):
                    rows,text=read_image(page)
                    found.extend(rows);raw.append(text)
                st.session_state[f'rows_{ix}']=pd.DataFrame(found,columns=['Nr','X','Y']) if found else pd.DataFrame(columns=['Nr','X','Y'])
                st.session_state[f'ocr_{ix}']='\n\n'.join(raw)
            except Exception as e:
                st.error(f'Neizdevās nolasīt: {e}');continue
        if f.name.lower().endswith('.pdf'):
            st.caption('PDF apstrādāts pa lapām. Ja PDF ir vairāki poligoni, augšupielādē katru atsevišķi.')
        else: st.image(f.getvalue(),caption='Oriģinālais attēls',width=500)
        with st.expander('OCR nolasītais teksts (salīdzināšanai)'):
            st.code(st.session_state.get(f'ocr_{ix}',''))
        st.write('**Pārbaudi un izlabo visas rindas.** Var pievienot vai dzēst rindas. Virsotņu secību nosaka rindu kārtība.')
        edited=st.data_editor(st.session_state[f'rows_{ix}'],num_rows='dynamic',hide_index=True,key=f'editor_{key}',column_config={'Nr':st.column_config.NumberColumn('Nr',step=1),'X':st.column_config.TextColumn('X'),'Y':st.column_config.TextColumn('Y')},use_container_width=True)
        swap=st.checkbox('Apmainīt X un Y vietām',key=f'swap_{key}')
        confirm=st.checkbox('Esmu salīdzinājis/-usi KATRU koordinātu ar oriģinālo attēlu',key=f'confirm_{key}')
        try:
            data=edited.to_dict('records')
            if len(data)<3: raise ValueError('Nepieciešamas vismaz 3 virsotnes. Papildini tabulu.')
            if any(pd.isna(r['X']) or pd.isna(r['Y']) for r in data):raise ValueError('Tabulā ir tukšas koordinātas')
            poly,wgs,plausible=geometry(data,swap)
            st.metric('Platība',f'{poly.area/10000:.4f} ha')
            st.write(f'**Virsotnes:** {len(data)} | **Koordinātu sistēma:** EPSG:3059')
            if not plausible:
                st.error('Koordinātas nav ticamas Latvijas atrašanās vietai. Pārbaudi X/Y un skaitļus.')
                continue
            boundary=get_boundary()
            status=country_status(wgs,boundary)
            if status=='Pilnībā Latvijas teritorijā': st.success(status)
            else: st.error(status+' — SHP lejupielāde ir bloķēta.');continue
            # map coordinates converted to WGS84; st.map points as quick preview
            xy=list(wgs.exterior.coords)
            st.map(pd.DataFrame({'lat':[p[1] for p in xy],'lon':[p[0] for p in xy]}),zoom=12)
            st.caption('Kartē redzamas virsotnes; poligona kontūru un atrašanās vietu papildus pārbaudi QGIS.')
            if not confirm:
                st.info('Apstiprini koordinātu pārbaudi, lai aktivizētu lejupielādi.')
                continue
            name=f'Poligons_{ix:02d}_LKS92'
            content=export_zip(data,poly,name)
            st.download_button('⬇️ Lejupielādēt SHP + CSV ZIP',content,file_name=name+'.zip',mime='application/zip',key=f'download_{key}')
            all_zips.append((name+'.zip',content))
        except Exception as e:
            st.error(f'Pārbaude neizdevās: {e}')
if len(all_zips)>1:
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for name,data in all_zips:z.writestr(name,data)
    st.download_button('⬇️ Lejupielādēt visus apstiprinātos poligonus',out.getvalue(),file_name='Visi_poligoni_LKS92.zip',mime='application/zip')
st.caption('Robežu dati: geoBoundaries gbOpen. Neapstiprinātas koordinātas un nepieejama robežu pārbaude bloķē eksportu. Faili netiek glabāti datubāzē.')
