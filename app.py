"""Koordinātas → SHP: upload first, then OCR and reviewed polygon export."""
import io
import zipfile

import streamlit as st

st.set_page_config(page_title="Koordinātas → SHP", page_icon="🗺️", layout="wide")
st.title("🗺️ Koordinātas → SHP")
st.write("Augšupielādē koordinātu tabulu, pārbaudi visas virsotnes un lejupielādē QGIS SHP ZIP (EPSG:3059).")
st.warning("OCR var kļūdīties. Pirms SHP izveides salīdzini katru koordinātu ar oriģinālu.")

# Keep the working, simple upload widget from the successful phone test.
uploads = st.file_uploader(
    "Pievieno attēlus vai PDF",
    type=["jpg", "jpeg", "png", "pdf"],
    accept_multiple_files=True,
    key="coordinate_upload_v2",
)
if not uploads:
    st.info("Izvēlies pirmo failu. Katrs fails tiks apstrādāts atsevišķi.")
    st.stop()

# Import heavier OCR/GIS dependencies only after a file was received.
import pandas as pd
import requests
from shapely.geometry import shape
from shapely.ops import unary_union
from core import geometry, country_status, export_zip
from ocr import pages, read_image

@st.cache_data(ttl=86400, show_spinner=False)
def get_boundary():
    try:
        r = requests.get("https://www.geoboundaries.org/api/current/gbOpen/LVA/ADM0/", timeout=12)
        r.raise_for_status()
        meta = r.json()
        geo = requests.get(meta["gjDownloadURL"], timeout=25)
        geo.raise_for_status()
        obj = geo.json()
        if obj["type"] == "FeatureCollection":
            geoms = [shape(f["geometry"]) for f in obj["features"]]
        else:
            geoms = [shape(obj["geometry"] if obj["type"] == "Feature" else obj)]
        return unary_union(geoms)
    except Exception:
        return None

all_zips = []
for ix, uploaded in enumerate(uploads, 1):
    with st.expander(f"{ix}. {uploaded.name}", expanded=True):
        st.success(f"Fails saņemts: {uploaded.name} ({uploaded.size} baiti)")
        data_bytes = uploaded.getvalue()
        suffix = "." + uploaded.name.rsplit(".", 1)[-1].lower()
        file_id = f"{ix}_{uploaded.name}_{uploaded.size}"
        if st.session_state.get(f"file_id_{ix}") != file_id:
            st.session_state[f"file_id_{ix}"] = file_id
            st.session_state.pop(f"rows_{ix}", None)
            st.session_state.pop(f"ocr_{ix}", None)

        if not uploaded.name.lower().endswith(".pdf"):
            st.image(data_bytes, caption="Oriģinālais attēls", use_container_width=True)
        else:
            st.caption("PDF tiek apstrādāts pa lapām. Ja ir vairāki poligoni, augšupielādē tos atsevišķi.")

        if f"rows_{ix}" not in st.session_state:
            with st.spinner("Atpazīstu koordinātas…"):
                try:
                    found, raw = [], []
                    for page in pages(data_bytes, suffix):
                        rows, debug = read_image(page)
                        found.extend(rows)
                        raw.append(debug)
                    st.session_state[f"rows_{ix}"] = pd.DataFrame(found, columns=["Nr", "X", "Y"])
                    st.session_state[f"ocr_{ix}"] = "\n\n".join(raw)
                except Exception as exc:
                    st.error(f"Neizdevās nolasīt failu: {exc}")
                    continue

        with st.expander("OCR nolasītais teksts"):
            st.code(st.session_state.get(f"ocr_{ix}", ""))
        st.write("**Pārbaudi visas rindas.** Trūkstošās virsotnes vari pievienot, kļūdainās — labot.")
        edited = st.data_editor(
            st.session_state[f"rows_{ix}"],
            num_rows="dynamic", hide_index=True,
            key=f"editor_{file_id}",
            column_config={
                "Nr": st.column_config.NumberColumn("Nr", step=1),
                "X": st.column_config.TextColumn("X"),
                "Y": st.column_config.TextColumn("Y"),
            },
            use_container_width=True,
        )
        swap = st.checkbox("Apmainīt X un Y vietām", key=f"swap_{file_id}")
        confirmed = st.checkbox("Esmu salīdzinājis/-usi KATRU koordinātu ar attēlu", key=f"confirm_{file_id}")
        try:
            records = edited.to_dict("records")
            if len(records) < 3:
                raise ValueError("Nepieciešamas vismaz 3 virsotnes.")
            if any(pd.isna(r["Nr"]) or pd.isna(r["X"]) or pd.isna(r["Y"]) or str(r["X"]).strip() == "" or str(r["Y"]).strip() == "" for r in records):
                raise ValueError("Tabulā ir tukši lauki.")
            numbers = [int(r["Nr"]) for r in records]
            if numbers != list(range(1, len(records) + 1)):
                raise ValueError("Virsotņu numuriem jābūt secīgiem no 1.")
            poly, wgs, plausible = geometry(records, swap)
            st.metric("Platība", f"{poly.area / 10000:.4f} ha")
            st.write(f"**Virsotnes:** {len(records)} | **Koordinātu sistēma:** EPSG:3059")
            if not plausible:
                st.error("Koordinātas nav ticamas Latvijas teritorijai. Pārbaudi X/Y.")
                continue
            boundary = get_boundary()
            status = country_status(wgs, boundary)
            if status != "Pilnībā Latvijas teritorijā":
                st.error(status + " — eksports bloķēts.")
                continue
            st.success(status)
            xy = list(wgs.exterior.coords)
            st.map(pd.DataFrame({"lat": [p[1] for p in xy], "lon": [p[0] for p in xy]}), zoom=12)
            if not confirmed:
                st.info("Apstiprini koordinātu pārbaudi, lai lejupielādētu SHP.")
                continue
            name = f"Poligons_{ix:02d}_LKS92"
            content = export_zip(records, poly, name)
            st.download_button("⬇️ Lejupielādēt SHP + CSV ZIP", content, file_name=name + ".zip", mime="application/zip", key=f"download_{file_id}")
            all_zips.append((name + ".zip", content))
        except Exception as exc:
            st.info(f"Pārbaude: {exc}")

if len(all_zips) > 1:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in all_zips:
            archive.writestr(name, content)
    st.download_button("⬇️ Lejupielādēt visus apstiprinātos poligonus", output.getvalue(), file_name="Visi_poligoni_LKS92.zip", mime="application/zip")
st.caption("Robežu dati: geoBoundaries gbOpen. Ja robežu pārbaude nav pieejama, eksports tiek bloķēts.")
