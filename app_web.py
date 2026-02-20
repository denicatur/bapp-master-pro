import streamlit as st
import pandas as pd
import re
import fitz  # PyMuPDF
import cv2
import numpy as np
import easyocr
import io
import zipfile
import os
from datetime import datetime

# --- 1. KONFIGURASI HALAMAN ---
st.set_page_config(page_title="Boony System Web", layout="wide")

# --- 2. SISTEM LOGIN ---
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

# --- 3. ENGINE OCR (LOAD SEKALI SAJA) ---
@st.cache_resource
def load_ocr():
    return easyocr.Reader(['en'], gpu=False)

# --- 4. DATABASE HANDLER (LOAD DARI FILE INTERNAL) ---
@st.cache_data
def load_internal_db():
    # Mengambil file yang sudah ada di folder GitHub
    file_path = "database_master.xlsx"
    if os.path.exists(file_path):
        df = pd.read_excel(file_path, dtype=str)
        df.columns = [str(c).strip().upper() for c in df.columns]
        return df
    return None

# --- JALANKAN APLIKASI ---
if not st.session_state["logged_in"]:
    login()
else:
    reader = load_ocr()
    db = load_internal_db() # Database otomatis terisi
    
    st.title("📂 BAPP Master Pro - Web Edition")
    
    if db is None:
        st.error("❌ File 'database_master.xlsx' tidak ditemukan di GitHub. Harap unggah filenya dulu.")
    else:
        st.success(f"✅ Database Internal Aktif ({len(db)} data sekolah terdaftar)")

    with st.sidebar:
        st.header("⚙️ Menu")
        if st.button("Logout"):
            st.session_state["logged_in"] = False
            st.rerun()

    # MAIN AREA UNTUK PDF
    st.subheader("📥 Step: Unggah & Rename PDF")
    uploaded_pdfs = st.file_uploader("Pilih file PDF yang akan di-rename", type=['pdf'], accept_multiple_files=True)

    if uploaded_pdfs and db is not None:
        if st.button("🚀 PROSES SEKARANG", type="primary"):
            zip_buffer = io.BytesIO()
            logs = []
            
            with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
                progress_bar = st.progress(0)
                
                for i, pdf_file in enumerate(uploaded_pdfs):
                    try:
                        pdf_bytes = pdf_file.read()
                        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                        page = doc.load_page(0)
                        
                        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
                        roi_h = int(img.shape[0] * 0.35)
                        crop = img[0:roi_h, :]
                        
                        res = reader.readtext(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), detail=0)
                        teks = " ".join(res).upper()
                        
                        match = re.search(r"(ZMB/\d{2}/\d{5}|HI\d{13})", teks)
                        new_name = pdf_file.name
                        
                        if match:
                            kode = match.group(0)
                            mask = db.astype(str).apply(lambda x: x.str.contains(kode)).any(axis=1)
                            row = db[mask]
                            
                            if not row.empty:
                                r = row.iloc[0]
                                npsn = r.get('NPSN', '00000000')
                                nama_sek = re.sub(r'[\\/*?:"<>|]', "", str(r.get('NAMA_SEKOLAH', 'Unknown'))).replace(" ", "_")
                                urut = str(r.get('NO_URUT', '0')).split('.')[0].zfill(3)
                                
                                # FORMAT BARU: URUT_NPSN_NAMA_
                                new_name = f"{urut}_{npsn}_{nama_sek}_.pdf"
                                logs.append({"File": pdf_file.name, "Hasil": new_name, "Status": "✅ Berhasil"})
                            else:
                                new_name = f"TAK_ADA_DI_DB_{pdf_file.name}"
                                logs.append({"File": pdf_file.name, "Hasil": "Data tidak ditemukan", "Status": "⚠️"})
                        else:
                            new_name = f"GAGAL_SCAN_{pdf_file.name}"
                            logs.append({"File": pdf_file.name, "Hasil": "Kode tidak terbaca", "Status": "❌"})

                        zip_file.writestr(new_name, pdf_bytes)
                        doc.close()
                        
                    except Exception as e:
                        logs.append({"File": pdf_file.name, "Hasil": str(e), "Status": "🔥 Error"})
                    
                    progress_bar.progress((i + 1) / len(uploaded_pdfs))

            st.divider()
            st.download_button(
                label="📥 DOWNLOAD HASIL RENAME (.ZIP)",
                data=zip_buffer.getvalue(),
                file_name=f"BAPP_RENAME_{datetime.now().strftime('%Y%m%d')}.zip",
                mime="application/zip"
            )
            st.dataframe(pd.DataFrame(logs), use_container_width=True)
