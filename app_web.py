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

st.set_page_config(page_title="Boony System Web v4", layout="wide")

# --- Inisialisasi Session State ---
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "process_results" not in st.session_state:
    st.session_state["process_results"] = None
if "zip_buffer" not in st.session_state:
    st.session_state["zip_buffer"] = None
if "excel_buffer" not in st.session_state:
    st.session_state["excel_buffer"] = None

def login():
    st.markdown("<h1 style='text-align: center;'>🤖 Boony System Login v4</h1>", unsafe_allow_html=True)
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
                        st.error("Maaf, Username atau Password salah!")

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
    
    st.title("📂 BAPP Master Pro - Web Edition v4")
    st.markdown("Selamat datang, **Deni Catur Cahyadi**! Silakan kelola dokumen BAPP Anda di bawah ini.")
    
    with st.sidebar:
        st.header("⚙️ Konfigurasi Nama")
        pasang_depan = st.checkbox("Pasang No Urut di DEPAN", value=True)
        pasang_belakang = st.checkbox("Pasang No Urut di BELAKANG", value=False)
        
        st.divider()
        st.header("📂 Fitur Folder")
        split_by_provinsi = st.toggle("Pisahkan File per Folder Provinsi", value=True)
        
        st.divider()
        if st.button("🚪 Logout"):
            for key in st.session_state.keys():
                st.session_state[key] = False if key == "logged_in" else None
            st.rerun()

    if db is None:
        st.error("❌ File 'database_master.xlsx' tidak ditemukan. Harap pastikan file tersedia di direktori utama.")
    else:
        st.success(f"✅ Database Aktif memuat {len(db)} data referensi.")

    # Menggunakan antarmuka Tab
    tab1, tab2 = st.tabs(["🚀 Unggah & Proses", "📊 Laporan & Unduhan"])

    with tab1:
        st.subheader("📥 Step 1: Unggah & Rename PDF")
        uploaded_pdfs = st.file_uploader("Pilih file PDF BAPP yang ingin diproses", type=['pdf'], accept_multiple_files=True)

        if uploaded_pdfs and db is not None:
            if st.button("🚀 MULAI PROSES OCR", type="primary"):
                all_results = []
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                for i, pdf_file in enumerate(uploaded_pdfs):
                    status_text.text(f"Memproses {pdf_file.name} ({i+1}/{len(uploaded_pdfs)})...")
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
                            "FILE_ASLI": pdf_file.name,
                            "PROVINSI": provinsi,
                            "HASIL_RENAME": new_name,
                            "BYTES": pdf_bytes,
                            "STATUS": status,
                            "KODE": kode_terbaca
                        })
                        doc.close()
                    except Exception as e:
                        all_results.append({
                            "FILE_ASLI": pdf_file.name,
                            "PROVINSI": "ERROR", 
                            "HASIL_RENAME": pdf_file.name, 
                            "BYTES": pdf_bytes, 
                            "STATUS": "🔥", 
                            "KODE": str(e)
                        })
                    
                    progress_bar.progress((i + 1) / len(uploaded_pdfs))

                status_text.text("Menyiapkan file ZIP dan Laporan Excel...")

                # --- PROSES ZIPPING PER FOLDER ---
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
                    for res in all_results:
                        if split_by_provinsi:
                            zip_path = f"{res['PROVINSI']}/{res['HASIL_RENAME']}"
                        else:
                            zip_path = res['HASIL_RENAME']
                        zip_file.writestr(zip_path, res['BYTES'])

                # --- PROSES PEMBUATAN EXCEL SUMMARY ---
                df_results = pd.DataFrame(all_results).drop(columns=['BYTES'])
                excel_buffer = io.BytesIO()
                with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                    df_results.to_excel(writer, index=False, sheet_name='Laporan_BAPP')

                # Simpan ke Session State agar tidak hilang
                st.session_state["process_results"] = df_results
                st.session_state["zip_buffer"] = zip_buffer
                st.session_state["excel_buffer"] = excel_buffer
                
                status_text.empty()
                st.success("🎉 Proses selesai! Silakan buka tab 'Laporan & Unduhan' untuk mengambil file.")

    with tab2:
        st.subheader("📊 Hasil Pemrosesan Dokumen")
        
        if st.session_state["process_results"] is not None:
            df_res = st.session_state["process_results"]
            
            # Dasbor Metrik
            total_file = len(df_res)
            sukses = len(df_res[df_res['STATUS'] == '✅'])
            gagal = total_file - sukses
            
            col1, col2, col3 = st.columns(3)
            col1.metric("Total Dokumen", total_file)
            col2.metric("Berhasil (✅)", sukses)
            col3.metric("Gagal / Error (❌/🔥)", gagal)
            
            st.divider()
            
            # Tombol Download berjajar
            dl_col1, dl_col2 = st.columns(2)
            with dl_col1:
                st.download_button(
                    label="📥 DOWNLOAD HASIL ZIP (PDF)", 
                    data=st.session_state["zip_buffer"].getvalue(), 
                    file_name=f"BAPP_PROSESSED_{datetime.now().strftime('%d%m%Y_%H%M')}.zip",
                    use_container_width=True
                )
            with dl_col2:
                st.download_button(
                    label="📊 DOWNLOAD LAPORAN EXCEL", 
                    data=st.session_state["excel_buffer"].getvalue(), 
                    file_name=f"LAPORAN_BAPP_{datetime.now().strftime('%d%m%Y_%H%M')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
            
            # Tampilkan tabel rekap
            st.markdown("### Detail Rekapitulasi")
            st.dataframe(df_res, use_container_width=True)
        else:
            st.info("Belum ada data yang diproses. Silakan unggah dan proses PDF di tab 'Unggah & Proses'.")
