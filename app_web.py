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

# --- 3. ENGINE OCR ---
@st.cache_resource
def load_ocr():
    return easyocr.Reader(['en'], gpu=False)

# --- 4. LOAD DATABASE INTERNAL ---
@st.cache_data
def load_internal_db():
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
    db = load_internal_db()
    
    st.title("📂 BAPP Master Pro - Web Edition")
    
    # --- SIDEBAR: PENGATURAN PENAMAAN ---
    with st.sidebar:
        st.header("⚙️ Pengaturan Nama File")
        
        # Opsi untuk mengatur nomor urut
        mode_urut = st.radio("Sumber Nomor Urut:", ["Dari Database", "Input Manual"])
        
        manual_urut_val = ""
        if mode_urut == "Input Manual":
            manual_urut_val = st.text_input("Masukkan No Urut Manual:", "001")
            st.info("Nomor ini akan dipakai di depan & belakang semua file.")
        
        st.divider()
        if st.button("Logout"):
            st.session_state["logged_in"] = False
            st.rerun()

    if db is None:
        st.error("❌ File 'database_master.xlsx' tidak ditemukan di GitHub.")
    else:
        st.success(f"✅ Database Master Aktif ({len(db)} data sekolah)")

    # MAIN AREA
    st.subheader("📥 Step: Unggah & Rename PDF")
    uploaded_pdfs = st.file_uploader("Pilih file PDF BAPP", type=['pdf'], accept_multiple_files=True)

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
                        
                        # Cari Kode BAPP
                        match = re.search(r"(ZMB/\d{2}/\d{5}|HI\d{13}|\d{6}/BAPP/[A-Z0-9-]+/\d{4})", teks)
                        new_name = pdf_file.name
                        
                        if match:
                            kode = match.group(0)
                            mask = db.astype(str).apply(lambda x: x.str.contains(kode, na=False)).any(axis=1)
                            row = db[mask]
                            
                            if not row.empty:
                                r = row.iloc[0]
                                npsn = r.get('NPSN', '00000000')
                                nama_sek = re.sub(r'[\\/*?:"<>|]', "", str(r.get('NAMA_SEKOLAH', 'Unknown'))).replace(" ", "_")
                                
                                # Tentukan Nomor Urut (Database atau Manual)
                                if mode_urut == "Dari Database":
                                    urut_final = str(r.get('NO_URUT', '0')).split('.')[0].zfill(3)
                                else:
                                    urut_final = manual_urut_val
                                
                                # FORMAT: [URUT]_[NPSN]_[NAMA]_[URUT]_
                                new_name = f"{urut_final}_{npsn}_{nama_sek}_{urut_final}_.pdf"
                                logs.append({"File": pdf_file.name, "Hasil": new_name, "Status": "✅"})
                            else:
                                new_name = f"TIDAK_DI_DB_{pdf_file.name}"
                        else:
                            new_name = f"GAGAL_OCR_{pdf_file.name}"

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
