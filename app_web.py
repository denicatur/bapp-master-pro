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
        st.header("⚙️ Posisi Nomor Urut")
        pasang_depan = st.checkbox("Pasang di DEPAN", value=True)
        pasang_belakang = st.checkbox("Pasang di BELAKANG", value=False)
        
        st.divider()
        if st.button("Logout"):
            st.session_state["logged_in"] = False
            st.rerun()

    if db is None:
        st.error("❌ File 'database_master.xlsx' tidak ditemukan/rusak.")
    else:
        st.success(f"✅ Database Aktif ({len(db)} data)")

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
                        
                        # Ambil area lebih luas agar OCR tidak terpotong
                        pix = page.get_pixmap(matrix=fitz.Matrix(2.5, 2.5))
                        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
                        # Fokus ke 40% bagian atas PDF
                        roi_h = int(img.shape[0] * 0.40)
                        crop = img[0:roi_h, :]
                        
                        res = reader.readtext(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), detail=0)
                        teks = " ".join(res).upper()
                        
                        # Regex lebih kuat untuk menangkap variasi teks
                        match = re.search(r"(ZMB/\d{2}/\d{5}|HI\d{13}|BAPP/[A-Z0-9-/]+/\d{4})", teks)
                        new_name = pdf_file.name
                        found_kode = match.group(0) if match else "TIDAK TERBACA"
                        
                        if match:
                            kode = match.group(0)
                            # Bersihkan spasi/karakter aneh di data
                            mask = db.apply(lambda row: row.astype(str).str.contains(kode, na=False).any(), axis=1)
                            row = db[mask]
                            
                            if not row.empty:
                                r = row.iloc[0]
                                npsn = str(r.get('NPSN', '00000000')).strip()
                                nama_sek = re.sub(r'[\\/*?:"<>|]', "", str(r.get('NAMA_SEKOLAH', 'Unknown'))).strip().replace(" ", "_")
                                urut = str(r.get('NO_URUT', '0')).split('.')[0].strip().zfill(3)
                                
                                name_parts = []
                                if pasang_depan: name_parts.append(urut)
                                name_parts.append(npsn)
                                name_parts.append(nama_sek)
                                if pasang_belakang: name_parts.append(urut)
                                
                                new_name = "_".join(name_parts) + "_.pdf"
                                logs.append({"File Asli": pdf_file.name, "Kode Terbaca": kode, "Hasil Rename": new_name, "Status": "✅"})
                            else:
                                logs.append({"File Asli": pdf_file.name, "Kode Terbaca": kode, "Hasil Rename": "TIDAK ADA DI DB", "Status": "⚠️"})
                        else:
                            logs.append({"File Asli": pdf_file.name, "Kode Terbaca": "Gagal Scan", "Hasil Rename": "OCR FAILED", "Status": "❌"})

                        zip_file.writestr(new_name, pdf_bytes)
                        doc.close()
                        
                    except Exception as e:
                        logs.append({"File Asli": pdf_file.name, "Kode Terbaca": "Error", "Hasil Rename": str(e), "Status": "🔥"})
                    
                    progress_bar.progress((i + 1) / len(uploaded_pdfs))

            st.divider()
            st.download_button("📥 DOWNLOAD HASIL RENAME (.ZIP)", zip_buffer.getvalue(), f"BAPP_{datetime.now().strftime('%H%M')}.zip", "application/zip")
            st.dataframe(pd.DataFrame(logs), use_container_width=True)
