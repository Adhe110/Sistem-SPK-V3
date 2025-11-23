from flask import Flask, render_template, request, send_file
import pandas as pd
import numpy as np
import os

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['OUTPUT_FOLDER'] = 'outputs'

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)

df_global = None
hasil_global = None

NUMERIC_COLS = ["Jumlah Tanggungan", "Usia", "Pekerjaan", "Status"]

# =========================================================
# SAW
# =========================================================
def saw_normalisasi_berbobot(df, weights, benefit_mask):
    X = df[NUMERIC_COLS].astype(float)
    max_vals = X.max()
    min_vals = X.min()

    R = pd.DataFrame(index=X.index)

    for i, col in enumerate(NUMERIC_COLS):
        if benefit_mask[i]:
            R[col] = X[col] / max_vals[col]
        else:
            R[col] = min_vals[col] / X[col]

    R = R[NUMERIC_COLS]
    Rb = R * weights
    return Rb, Rb.sum(axis=1).round(3)


# =========================================================
# TOPSIS
# =========================================================
def topsis_rangking(df, weights, benefit_mask):
    X = df[NUMERIC_COLS].astype(float)
    norm = np.sqrt((X ** 2).sum(axis=0))
    R = X / norm
    V = R * weights
    V_np = V.values

    Aplus = np.where(benefit_mask, V_np.max(axis=0), V_np.min(axis=0))
    Aminus = np.where(benefit_mask, V_np.min(axis=0), V_np.max(axis=0))

    Dplus = np.sqrt(((V_np - Aplus) ** 2).sum(axis=1))
    Dminus = np.sqrt(((V_np - Aminus) ** 2).sum(axis=1))

    return np.round(Dminus / (Dplus + Dminus), 3)


# =========================================================
# HOME
# =========================================================
@app.route('/')
def home():
    return render_template("home.html")


# =========================================================
# INDEX
# =========================================================
@app.route('/index', methods=['GET', 'POST'])
def index():
    global df_global, hasil_global

    # ============================
    # GET REQUEST
    # ============================
    if request.method == 'GET':
        return render_template(
            "index.html",
            tableshow=False,
            file_uploaded=False,
            error_msg=None,
            total_bobot=0,
            sisa_bobot=1
        )

    # ============================
    # POST REQUEST
    # ============================
    step = request.form.get("step", "")

    # =========================================================
    # STEP 1 — UPLOAD FILE
    # =========================================================
    if step == "upload":
        file = request.files.get("file")
        if file is None or file.filename == "":
            return render_template("index.html",
                                   tableshow=False,
                                   file_uploaded=False,
                                   total_bobot=0,
                                   sisa_bobot=1,
                                   error_msg="❌ File tidak valid.")

        filename = file.filename
        path_input = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(path_input)

        try:
            df = pd.read_excel(path_input)
        except:
            return render_template("index.html",
                                   tableshow=False,
                                   file_uploaded=False,
                                   total_bobot=0,
                                   sisa_bobot=1,
                                   error_msg="❌ File tidak bisa dibaca.")

        # AUTO MAP
        map_patterns = {
            "RW": ["rw"],
            "RT": ["rt"],
            "Dusun": ["dusun", "desa"],
            "NIK": ["nik"],
            "Nama Kepala Keluarga": ["nama"],
            "Jumlah Tanggungan": ["tanggungan"],
            "Usia": ["usia", "umur"],
            "Pekerjaan": ["pekerjaan", "job"],
            "Status": ["status"]
        }

        df.columns = df.columns.str.lower().str.strip()
        col_map = {}

        for std, keys in map_patterns.items():
            for pat in keys:
                for col in df.columns:
                    if pat in col:
                        col_map[std] = col

        required = ["RW", "RT", "Dusun", "NIK", "Nama Kepala Keluarga"] + NUMERIC_COLS
        missing_cols = [c for c in required if c not in col_map]

        if missing_cols:
            return render_template("index.html",
                                   tableshow=False,
                                   file_uploaded=False,
                                   total_bobot=0,
                                   sisa_bobot=1,
                                   show_template=True,
                                   error_msg=f"❌ Kolom berikut tidak ditemukan:<br><b>{missing_cols}</b>")

        df = df[[col_map[c] for c in required]]
        df.columns = required

        # CEK KOSONG
        empty_cols = [col for col in df.columns if df[col].isna().all()]
        if empty_cols:
            return render_template("index.html",
                                   tableshow=False,
                                   file_uploaded=False,
                                   total_bobot=0,
                                   sisa_bobot=1,
                                   show_template=True,
                                   error_msg=f"❌ Kolom berikut kosong:<br><b>{empty_cols}</b>")

        df_global = df.copy()
        hasil_global = None

        return render_template("index.html",
                               tableshow=False,
                               file_uploaded=True,
                               uploaded_filename=filename,
                               total_bobot=0,
                               sisa_bobot=1,
                               error_msg=None)

    # =========================================================
    # STEP 2 — INPUT BOBOT
    # =========================================================
    if step == "weights":

        if df_global is None:
            return render_template("index.html",
                                   tableshow=False,
                                   file_uploaded=False,
                                   total_bobot=0,
                                   sisa_bobot=1,
                                   error_msg="❌ Belum ada file.")

        try:
            w = [
                float(request.form.get("w_jt", 0)),
                float(request.form.get("w_usia", 0)),
                float(request.form.get("w_pekerjaan", 0)),
                float(request.form.get("w_status", 0))
            ]
        except:
            return render_template("index.html",
                                   tableshow=False,
                                   file_uploaded=True,
                                   total_bobot=0,
                                   sisa_bobot=1,
                                   error_msg="❌ Bobot harus angka.")

        weights = np.array(w)
        total = weights.sum()
        sisa = 1 - total

        # NEGATIF
        if np.any(weights < 0):
            return render_template("index.html",
                                   tableshow=False,
                                   file_uploaded=True,
                                   total_bobot=total,
                                   sisa_bobot=sisa,
                                   error_msg="❌ Bobot tidak boleh negatif.")

        # TOTAL ≠ 1
        if round(total, 3) != 1.000:
            return render_template("index.html",
                                   tableshow=False,
                                   file_uploaded=True,
                                   total_bobot=round(total, 3),
                                   sisa_bobot=round(sisa, 3),
                                   error_msg=f"❌ Total bobot harus = 1 (sekarang {total:.3f})")

        benefit_mask = np.array([
            request.form.get("t_jt") == "benefit",
            request.form.get("t_usia") == "benefit",
            request.form.get("t_pekerjaan") == "benefit",
            request.form.get("t_status") == "benefit"
        ])

        Rb, nilai_saw = saw_normalisasi_berbobot(df_global, weights, benefit_mask)
        nilai_topsis = topsis_rangking(df_global, weights, benefit_mask)

        hasil = pd.DataFrame({
            "RW": df_global["RW"].astype(str),
            "RT": df_global["RT"].astype(str),
            "Dusun": df_global["Dusun"].astype(str),
            "NIK": df_global["NIK"].astype(str).str.zfill( df_global["NIK"].astype(str).str.len().max() ),
            "Nama": df_global["Nama Kepala Keluarga"],
            "Nilai_SAW": nilai_saw,
            "Nilai_TOPSIS": nilai_topsis
        })

        hasil["Ranking"] = hasil["Nilai_TOPSIS"].rank(ascending=False, method="min")
        hasil = hasil.sort_values("Ranking")

        hasil_global = hasil.copy()

        # Buat kriteria_info untuk preview bobot
        kriteria_info = []
        jenis_list = []
        for i, col in enumerate(NUMERIC_COLS):
            jenis = "Benefit" if benefit_mask[i] else "Cost"
            jenis_list.append(jenis)
            kriteria_info.append({
                "nama": col,
                "bobot": float(weights[i]),
                "jenis": jenis
            })

        return render_template("index.html",
                               tableshow=True,
                               file_uploaded=True,
                               data=hasil.to_dict(orient="records"),
                               kriteria_info=kriteria_info,
                               total_bobot=1,
                               sisa_bobot=0,
                               error_msg=None)

    # FALLBACK
    return render_template("index.html",
                           tableshow=False,
                           file_uploaded=False,
                           total_bobot=0,
                           sisa_bobot=1,
                           error_msg="❌ Aksi tidak dikenali.")


# =========================================================
# DOWNLOADS
# =========================================================
@app.route('/download_template')
def download_template():
    return send_file("template/template_excel.xlsx", as_attachment=True)

@app.route('/download_topsis_all')
def download_topsis_all():
    if hasil_global is None:
        return "❌ Belum ada data."
    df = hasil_global[["RW","RT","Dusun","NIK","Nama","Nilai_TOPSIS","Ranking"]]
    path = os.path.join(app.config["OUTPUT_FOLDER"], "TOPSIS_ALL.xlsx")
    df.to_excel(path, index=False)
    return send_file(path, as_attachment=True)

@app.route('/download_saw_all')
def download_saw_all():
    if hasil_global is None:
        return "❌ Belum ada data."
    df = hasil_global[["RW","RT","Dusun","NIK","Nama","Nilai_SAW","Ranking"]]
    path = os.path.join(app.config["OUTPUT_FOLDER"], "SAW_ALL.xlsx")
    df.to_excel(path, index=False)
    return send_file(path, as_attachment=True)

@app.route('/download_topsis_filter', methods=["GET"])
def download_topsis_filter():
    if hasil_global is None:
        return "❌ Belum ada data."

    rw = request.args.get("rw", "")
    rt = request.args.get("rt", "")
    dusun = request.args.get("dusun", "")

    df = hasil_global.copy()

    # Filter RW
    if rw:
        rw_list = [x.strip() for x in rw.split(",") if x.strip()]
        df = df[df["RW"].isin(rw_list)]

    # Filter RT
    if rt:
        rt_list = [x.strip() for x in rt.split(",") if x.strip()]
        df = df[df["RT"].isin(rt_list)]

    # Filter Dusun
    if dusun:
        dusun_list = [x.strip() for x in dusun.split(",") if x.strip()]
        df = df[df["Dusun"].isin(dusun_list)]


    # Simpan hasil
    path = os.path.join(app.config["OUTPUT_FOLDER"], "TOPSIS_FILTERED.xlsx")
    df[["RW","RT","Dusun","NIK","Nama","Nilai_TOPSIS","Ranking"]].to_excel(path, index=False)

    return send_file(path, as_attachment=True)


@app.route('/download_saw_filter', methods=["GET"])
def download_saw_filter():
    if hasil_global is None:
        return "❌ Belum ada data."

    rw = request.args.get("rw", "")
    rt = request.args.get("rt", "")
    dusun = request.args.get("dusun", "")

    df = hasil_global.copy()

    # Filter RW
    if rw:
        rw_list = [x.strip() for x in rw.split(",") if x.strip()]
        df = df[df["RW"].isin(rw_list)]

    # Filter RT
    if rt:
        rt_list = [x.strip() for x in rt.split(",") if x.strip()]
        df = df[df["RT"].isin(rt_list)]

    # Filter Dusun
    if dusun:
        dusun_list = [x.strip() for x in dusun.split(",") if x.strip()]
        df = df[df["Dusun"].isin(dusun_list)]


    path = os.path.join(app.config["OUTPUT_FOLDER"], "SAW_FILTERED.xlsx")
    df[["RW","RT","Dusun","NIK","Nama","Nilai_SAW","Ranking"]].to_excel(path, index=False)

    return send_file(path, as_attachment=True)


if __name__ == "__main__":
    app.run(debug=True)
