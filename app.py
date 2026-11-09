import streamlit as st

st.set_page_config(page_title="Koordinātas → SHP — augšupielādes pārbaude", page_icon="🗺️")
st.title("🗺️ Koordinātas → SHP")
st.info("Pagaidu pārbaudes versija. Tā tikai pārbauda attēlu augšupielādi un vēl neveido SHP failus.")
st.write("Izvēlies vienu nelielu JPG vai PNG attēlu no telefona.")
photo = st.file_uploader("Pievieno pārbaudes attēlu", type=["jpg", "jpeg", "png"], accept_multiple_files=False, key="upload_test_v1")
if photo is None:
    st.write("Fails vēl nav pievienots.")
else:
    st.success(f"Fails veiksmīgi saņemts: {photo.name} ({photo.size} baiti)")
    st.image(photo, caption="Saņemtais attēls")
