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
    # gpu=False karena server gratisan Streamlit tidak punya GPU
    return easyocr.Reader(['en'], gpu=False)

# --- 4. DATABASE HANDLER ---
@st.cache_data
def load_db(file):
    if file:
        df = pd.read_excel(file, dtype=str)
        df.columns = [str(c).strip().upper() for c in df.columns]
        return df
    return None

# --- JALANKAN APLIKASI ---
if not st.session_state["logged_in"]:
    login()
else:
    reader = load_ocr()
    st.title("📂 BAPP Master Pro - Web Edition")
    
    # SIDEBAR UNTUK DATABASE
    with st.sidebar:
        st.header("⚙️ Pengaturan")
        db_file = st.file_uploader("1. Upload Database Sekolah (.xlsx)", type=['xlsx'])
        db = load_db(db_file)
        if db is not None:
            st.success("✅ Database Siap")
        
        if st.button("Logout"):
            st.session_state["logged_in"] = False
            st.rerun()

    # MAIN AREA UNTUK PDF
    st.subheader("📥 Step 2: Unggah & Rename PDF")
    uploaded_pdfs = st.file_uploader("Pilih file PDF yang akan di-rename", type=['pdf'], accept_multiple_files=True)

    if uploaded_pdfs and db is not None:
        if st.button("🚀 PROSES SEKARANG", type="primary"):
            zip_buffer = io.BytesIO()
            logs = []
            
            with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
                progress_bar = st.progress(0)
                
                for i, pdf_file in enumerate(uploaded_pdfs):
                    try:
                        # Baca bytes file
                        pdf_bytes = pdf_file.read()
                        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                        page = doc.load_page(0)
                        
                        # OCR Proses
                        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
                        roi_h = int(img.shape[0] * 0.35)
                        crop = img[0:roi_h, :]
                        
                        res = reader.readtext(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), detail=0)
                        teks = " ".join(res).upper()
                        
                        # Cari Kode BAPP (ZMB atau HI)
                        match = re.search(r"(ZMB/\d{2}/\d{5}|HI\d{13})", teks)
                        
                        new_name = pdf_file.name # Default jika gagal
                        
                        if match:
                            kode = match.group(0)
                            # Cari di DB (Pastikan kolom ZMB_KEY atau NO_BAPP tersedia)
                            mask = db.astype(str).apply(lambda x: x.str.contains(kode)).any(axis=1)
                            row = db[mask]
                            
                            if not row.empty:
                                r = row.iloc[0]
                                npsn = r.get('NPSN', '00000000')
                                nama_sek = re.sub(r'[\\/*?:"<>|]', "", str(r.get('NAMA_SEKOLAH', 'Unknown'))).replace(" ", "_")
                                urut = str(r.get('NO_URUT', '0')).split('.')[0].zfill(3)
                                new_name = f"{urut}_{npsn}_{nama_sek}.pdf"
                                logs.append({"File": pdf_file.name, "Hasil": new_name, "Status": "✅ Berhasil"})
                            else:
                                new_name = f"TAK_ADA_DI_EXCEL_{pdf_file.name}"
                                logs.append({"File": pdf_file.name, "Hasil": "NPSN tidak ditemukan", "Status": "⚠️"})
                        else:
                            new_name = f"GAGAL_SCAN_{pdf_file.name}"
                            logs.append({"File": pdf_file.name, "Hasil": "Kode BAPP tidak terbaca", "Status": "❌"})

                        # Simpan ke ZIP dengan nama baru
                        zip_file.writestr(new_name, pdf_bytes)
                        doc.close()
                        
                    except Exception as e:
                        logs.append({"File": pdf_file.name, "Hasil": str(e), "Status": "🔥 Error"})
                    
                    progress_bar.progress((i + 1) / len(uploaded_pdfs))

            # TOMBOL DOWNLOAD ZIP
            st.divider()
            st.success("Semua file telah selesai diproses!")
            st.download_button(
                label="📥 DOWNLOAD SEMUA PDF (.ZIP)",
                data=zip_buffer.getvalue(),
                file_name=f"BAPP_RENAME_{datetime.now().strftime('%Y%m%d')}.zip",
                mime="application/zip"
            )
            st.dataframe(pd.DataFrame(logs), use_container_width=True)

    elif uploaded_pdfs and db is None:
        st.warning("⚠️ Harap upload file Excel Database di sidebar kiri dulu!")