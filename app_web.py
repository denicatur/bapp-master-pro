import streamlit as st
import pandas as pd
import re
import fitz
import cv2
import numpy as np
import easyocr
import io
import zipfile
import os
from datetime import datetime

st.set_page_config(page_title="Boony System Web", layout="wide")

if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

def login():
    st.markdown("<h1 style='text-align: center;'>🤖 Boony System Login</h1>", unsafe_allow_html=True)
    with st.container():
        _, col2, _ = st.columns([1, 2, 1])
        with col2:
            with st.form("login_form"):
                u = st.text_input("Username")
                p = st.text_input("Password", type="password")
                if st.form_submit_button("Login"):
                    if u == "bony" and p == "bonyswz20":
                        st.session_state["logged_in"] = True
                        st.rerun()
                    else:
                        st.error("Username/Password Salah!")

@st.cache_resource
def load_ocr():
    return easyocr.Reader(['en'], gpu=False)

@st.cache_data
def load_internal_db():
    file_path = "database_master.xlsx"
    if os.path.exists(file_path):
        try:
            df = pd.read_excel(file_path, dtype=str, engine='openpyxl')
            df.columns = [str(c).strip().upper() for c in df.columns]
            return df
        except:
            return None
    return None

if not st.session_state["logged_in"]:
    login()
else:
    reader = load_ocr()
    db = load_internal_db()
    
    st.title("📂 BAPP Master Pro - Web Edition")
    
    with st.sidebar:
        st.header("⚙️ Konfigurasi Nama")
        pasang_depan = st.checkbox("Pasang No Urut di DEPAN", value=True)
        pasang_belakang = st.checkbox("Pasang No Urut di BELAKANG", value=False)
        
        st.divider()
        st.header("📂 Fitur Folder")
        # Aktifkan sortir per folder
        split_by_provinsi = st.toggle("Pisahkan File per Folder Provinsi", value=True)
        
        st.divider()
        if st.button("Logout"):
            st.session_state["logged_in"] = False
            st.rerun()

    if db is None:
        st.error("❌ File 'database_master.xlsx' tidak ditemukan.")
    else:
        st.success(f"✅ Database Aktif ({len(db)} data)")

    st.subheader("📥 Step: Unggah & Rename PDF")
    uploaded_pdfs = st.file_uploader("Pilih file PDF BAPP", type=['pdf'], accept_multiple_files=True)

    if uploaded_pdfs and db is not None:
        if st.button("🚀 PROSES SEKARANG", type="primary"):
            all_results = []
            progress_bar = st.progress(0)
            
            for i, pdf_file in enumerate(uploaded_pdfs):
                try:
                    pdf_bytes = pdf_file.read()
                    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                    page = doc.load_page(0)
                    pix = page.get_pixmap(matrix=fitz.Matrix(2.5, 2.5))
                    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
                    roi_h = int(img.shape[0] * 0.40)
                    crop = img[0:roi_h, :]
                    
                    res = reader.readtext(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), detail=0)
                    teks = " ".join(res).upper()
                    
                    match = re.search(r"(ZMB/\d{2}/\d{5}|HI\d{13}|BAPP/[A-Z0-9-/]+/\d{4})", teks)
                    
                    # Data default
                    npsn, nama_sek, urut, provinsi = "00000000", "Unknown", "000", "TANPA_PROVINSI"
                    status, kode_terbaca = "❌", "Gagal Scan"
                    
                    if match:
                        kode_terbaca = match.group(0)
                        mask = db.apply(lambda row: row.astype(str).str.contains(kode_terbaca, na=False).any(), axis=1)
                        row_data = db[mask]
                        
                        if not row_data.empty:
                            r = row_data.iloc[0]
                            npsn = str(r.get('NPSN', '00000000')).strip()
                            nama_sek = re.sub(r'[\\/*?:"<>|]', "", str(r.get('NAMA_SEKOLAH', 'Unknown'))).strip().replace(" ", "_")
                            urut = str(r.get('NO_URUT', '0')).split('.')[0].strip().zfill(3)
                            # Ambil data provinsi
                            provinsi = re.sub(r'[\\/*?:"<>|]', "", str(r.get('PROVINSI', 'TANPA_PROVINSI'))).strip().replace(" ", "_")
                            status = "✅"

                    # Susun Nama Baru
                    name_parts = []
                    if pasang_depan: name_parts.append(urut)
                    name_parts.append(npsn)
                    name_parts.append(nama_sek)
                    if pasang_belakang: name_parts.append(urut)
                    new_name = "_".join(name_parts) + "_.pdf"

                    all_results.append({
                        "PROVINSI": provinsi,
                        "HASIL_RENAME": new_name,
                        "BYTES": pdf_bytes,
                        "STATUS": status,
                        "KODE": kode_terbaca
                    })
                    doc.close()
                except Exception as e:
                    all_results.append({"PROVINSI": "ERROR", "HASIL_RENAME": pdf_file.name, "BYTES": pdf_bytes, "STATUS": "🔥", "KODE": str(e)})
                
                progress_bar.progress((i + 1) / len(uploaded_pdfs))

            # --- PROSES ZIPPING PER FOLDER ---
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
                for res in all_results:
                    if split_by_provinsi:
                        # Masukkan ke dalam folder (Nama_Provinsi/Nama_File.pdf)
                        zip_path = f"{res['PROVINSI']}/{res['HASIL_RENAME']}"
                    else:
                        zip_path = res['HASIL_RENAME']
                    
                    zip_file.writestr(zip_path, res['BYTES'])

            st.divider()
            st.success(f"Selesai! File telah dikelompokkan berdasarkan Provinsi.")
            st.download_button("📥 DOWNLOAD HASIL ZIP", zip_buffer.getvalue(), f"BAPP_PER_PROVINSI_{datetime.now().strftime('%H%M')}.zip")
            
            # Tampilkan tabel rekap
            st.dataframe(pd.DataFrame(all_results).drop(columns=['BYTES']), use_container_width=True)
