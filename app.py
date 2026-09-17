import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
import bcrypt
import datetime
import unicodedata
import io

st.set_page_config(page_title="Quản Lý Kho Tôn, Phụ Kiện & Panel", layout="wide")

# --- HÀM HỖ TRỢ XUẤT FILE EXCEL QUA BỘ NHỚ RAM ---
def to_excel_bytes(df, sheet_name='Du_Lieu'):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
    return output.getvalue()

# --- 1. KẾT NỐI DATABASE (CACHE) ---
@st.cache_resource
def get_db_engine():
    if "db_url" in st.secrets:
        db_url = st.secrets["db_url"]
    else:
        db_url = "sqlite:///ton_inventory.db"
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    return create_engine(
        db_url, 
        pool_pre_ping=True, 
        pool_size=10, 
        max_overflow=20,
        pool_recycle=300
    )

engine = get_db_engine()

# --- 2. HÀM CHUYỂN ĐỔI AN TOÀN ---
def safe_float(val, default=0.0):
    if pd.isna(val) or val is None or str(val).strip() == "":
        return float(default)
    try:
        return float(str(val).replace(",", ".").strip())
    except Exception:
        return float(default)

def safe_int(val, default=0):
    if pd.isna(val) or val is None or str(val).strip() == "":
        return int(default)
    try:
        return int(float(str(val).strip()))
    except Exception:
        return int(default)

def safe_date(val):
    if pd.isna(val) or val is None or str(val).strip() == "" or str(val).strip() == "-":
        return datetime.date.today()
    if isinstance(val, (datetime.date, datetime.datetime)):
        return val if isinstance(val, datetime.date) else val.date()
    try:
        return datetime.datetime.strptime(str(val).strip()[:10], "%Y-%m-%d").date()
    except Exception:
        return datetime.date.today()

def safe_str(val, default=""):
    if pd.isna(val) or val is None:
        return default
    return str(val).strip()

def xoa_dau_tieng_viet(text_input):
    if not text_input or pd.isna(text_input):
        return ""
    text_input = str(text_input).replace('đ', 'd').replace('Đ', 'd')
    nfkd_form = unicodedata.normalize('NFKD', text_input)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)]).lower().strip()

# DANH MỤC HÓA CHẤT CHUẨN
DANH_SACH_HOA_CHAT = [
    "ISO PM200", "ISO BAYER", "ISO BASF", "ISO MR200",
    "POLY ORIKEN 2228 H2", "POLY ORIKEN 2230 H2", "POLY ORIKEN 2236 H2", "POLY ORIKEN 2258 H2",
    "KPX-6685", "POLY RESIN", "DUNG DỊCH MC"
]

# --- 3. KHỞI TẠO BẢNG & TỰ ĐỘNG CẬP NHẬT CỘT ---
@st.cache_resource
def init_database_tables():
    with engine.connect() as conn:
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(50) UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            full_name VARCHAR(100),
            role VARCHAR(20) DEFAULT 'operator',
            is_approved INTEGER DEFAULT 0,
            created_at DATE DEFAULT CURRENT_DATE
        );
        """))
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS inventory (
            id SERIAL PRIMARY KEY,
            ngay_loi DATE DEFAULT CURRENT_DATE,
            source_warehouse VARCHAR(50) NOT NULL,
            vi_tri_de VARCHAR(50),
            order_code VARCHAR(50),
            brand VARCHAR(50),
            thickness REAL,
            color VARCHAR(50),
            corrugation_type VARCHAR(20),
            ton_type VARCHAR(20),
            foam_type VARCHAR(50),
            sheet_length REAL,
            current_sheets INTEGER,
            total_meters REAL,
            remaining_meters REAL,
            scrap_meters REAL DEFAULT 0.0,
            is_matched VARCHAR(100) DEFAULT 'Chưa ghép',
            reason TEXT,
            fault_by VARCHAR(100),
            matched_order_code VARCHAR(150),
            matched_by_user VARCHAR(150),
            matched_length REAL,
            matched_sheets INTEGER,
            usable_length REAL DEFAULT 0.0,
            created_at DATE DEFAULT CURRENT_DATE
        );
        """))
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS matching_history (
            id SERIAL PRIMARY KEY,
            inventory_id INTEGER,
            new_order_code VARCHAR(150),
            matched_sheets INTEGER DEFAULT 1,
            matched_length REAL DEFAULT 0.0,
            matched_meters REAL DEFAULT 0.0,
            matched_by VARCHAR(100),
            matched_date DATE DEFAULT CURRENT_DATE
        );
        """))
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS accessory_inventory (
            id SERIAL PRIMARY KEY,
            ngay_loi DATE DEFAULT CURRENT_DATE,
            source_warehouse VARCHAR(50) NOT NULL,
            customer_name VARCHAR(150),
            vi_tri_de VARCHAR(50),
            order_code VARCHAR(50),
            accessory_type VARCHAR(50) NOT NULL,
            brand VARCHAR(100),
            kho_phu_kien VARCHAR(50),
            thickness REAL,
            color VARCHAR(50),
            sheet_length REAL,
            current_sheets INTEGER,
            total_meters REAL,
            trang_thai VARCHAR(50) DEFAULT 'Chưa xử lý',
            don_da_ghep VARCHAR(50),
            nguoi_ghep VARCHAR(100),
            ngay_ghep DATE,
            reason TEXT,
            fault_by VARCHAR(100),
            usable_length REAL DEFAULT 0.0,
            created_at DATE DEFAULT CURRENT_DATE
        );
        """))
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS accessory_matching_history (
            id SERIAL PRIMARY KEY,
            accessory_id INTEGER,
            new_order_code VARCHAR(50),
            matched_sheets INTEGER,
            matched_meters REAL,
            matched_by VARCHAR(100),
            matched_date DATE DEFAULT CURRENT_DATE
        );
        """))
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS panel_inventory (
            id SERIAL PRIMARY KEY,
            ngay_loi DATE DEFAULT CURRENT_DATE,
            source_warehouse VARCHAR(50) NOT NULL,
            vi_tri_de VARCHAR(50),
            order_code VARCHAR(50),
            brand VARCHAR(50),
            steel_thickness REAL DEFAULT 0.40,
            color VARCHAR(50),
            core_thickness VARCHAR(50),
            kho_ton VARCHAR(50),
            foam_type VARCHAR(50),
            sheet_length REAL,
            current_sheets INTEGER,
            total_meters REAL,
            total_area_m2 REAL,
            remaining_meters REAL,
            scrap_meters REAL DEFAULT 0.0,
            is_matched VARCHAR(100) DEFAULT 'Chưa ghép',
            reason TEXT,
            fault_by VARCHAR(100),
            matched_order_code VARCHAR(150),
            matched_by_user VARCHAR(150),
            matched_length REAL,
            matched_sheets INTEGER,
            usable_length REAL DEFAULT 0.0,
            created_at DATE DEFAULT CURRENT_DATE
        );
        """))
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS panel_matching_history (
            id SERIAL PRIMARY KEY,
            panel_id INTEGER,
            new_order_code VARCHAR(50),
            matched_sheets INTEGER,
            matched_meters REAL,
            matched_m2 REAL,
            matched_by VARCHAR(100),
            matched_date DATE DEFAULT CURRENT_DATE
        );
        """))
        
        # Bảng hóa chất
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS chemical_import (
            id SERIAL PRIMARY KEY,
            import_date DATE DEFAULT CURRENT_DATE,
            chemical_name VARCHAR(100) NOT NULL,
            phuy_count REAL DEFAULT 0.0,
            kg_per_phuy REAL DEFAULT 250.0,
            total_kg REAL DEFAULT 0.0,
            note TEXT,
            created_by VARCHAR(100),
            created_at DATE DEFAULT CURRENT_DATE
        );
        """))

        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS chemical_production_log (
            id SERIAL PRIMARY KEY,
            log_date DATE DEFAULT CURRENT_DATE,
            chemical_name VARCHAR(100) NOT NULL,
            department VARCHAR(100),
            phuy_nguyen_count REAL DEFAULT 0.0,
            kg_per_phuy REAL DEFAULT 250.0,
            phuy_nguyen_kg REAL DEFAULT 0.0,
            phuy_gio_count REAL DEFAULT 0.0,
            phuy_gio_kg REAL DEFAULT 0.0,
            bon_kg REAL DEFAULT 0.0,
            total_kg REAL DEFAULT 0.0,
            operator_name VARCHAR(100),
            created_at DATE DEFAULT CURRENT_DATE
        );
        """))

        # Bảng lưu định mức trung bình ngày nhập tay (Ảnh 2)
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS chemical_norm (
            chemical_name VARCHAR(100) PRIMARY KEY,
            norm_phuy REAL DEFAULT 0.0,
            norm_kg REAL DEFAULT 0.0
        );
        """))

        # Khởi tạo giá trị định mức mặc định nếu chưa có
        for hc in DANH_SACH_HOA_CHAT:
            conn.execute(text("""
                INSERT INTO chemical_norm (chemical_name, norm_phuy, norm_kg)
                VALUES (:name, 0.0, 0.0)
                ON CONFLICT (chemical_name) DO NOTHING;
            """), {"name": hc})
        
        check_admin = conn.execute(text("SELECT COUNT(*) FROM users WHERE username = 'admin'")).scalar()
        if check_admin == 0:
            pw_hash = bcrypt.hashpw("123456".encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            conn.execute(text("""
            INSERT INTO users (username, password_hash, full_name, role, is_approved)
            VALUES ('admin', :pw, 'Quản Trị Viên', 'admin', 1)
            """), {"pw": pw_hash})
        conn.commit()
    return True

init_database_tables()

# DANH MỤC CẤU HÌNH
DANH_SACH_HANG_TON = ["Poshaco", "Kazin", "Kazin Kim Cương", "Kamanz", "SSSC", "Simtek", "Hòa Phát", "Hoa Sen", "Olimpic", "Khác"]
DANH_SACH_SONG = ["6 sóng", "11 sóng", "Sóng Ngói"]
DANH_SACH_LOAI_TON = ["Tôn 1L", "Tôn 3L", "Ngói 1L", "Ngói 3L"]
DANH_SACH_XOP = ["Không xốp", "Xốp Eco", "Xốp G8", "Xốp G7", "Xốp G*", "Ngói N8", "Ngói N*"]
DANH_SACH_VI_TRI = ["KV_Cán tôn 1L", "KV_Cán tôn 3L", "KV_Xốp 3L", "KV_PK", "KV_Panel"]
DANH_SACH_NGUYEN_NHAN_CHUNG = ["Đuôi cuộn", "NV_cắt sai", "Lỗi xước sơn", "Lỗi máy", "Lỗi cuộn NVL", "Lỗi sai kích thước", "Lỗi khác"]
DANH_SACH_NGUYEN_NHAN_PANEL = ["Đuôi cuộn", "Không đủ thân máy", "NV_cắt sai", "Lỗi xước sơn", "Lỗi máy", "Lỗi cuộn NVL", "Lỗi sai kích thước", "Lỗi khác"]
DANH_SACH_PHU_KIEN = ["Máng", "Sườn", "Xối", "Nóc", "U", "V", "T", "H"]
DANH_SACH_DO_DAY_PANEL = ["5cm (50mm)", "7.5cm (75mm)", "10cm (100mm)"]
DANH_SACH_KHO_PANEL = ["Khổ nhỏ 1020mm", "Khổ to 1170mm"]
DANH_SACH_XOP_PANEL = ["Xốp thường", "Xốp chống cháy"]
DANH_SACH_MAU_PANEL = ["Trắng", "Vân gỗ"]
DANH_SACH_TRANG_THAI_PK = ["🔴 Chưa xử lý", "🟢 Đã xử lý", "🟡 Đã xả"]
DANH_SACH_TRANG_THAI_TON_PANEL = ["🔴 Chưa ghép", "🟢 Đã ghép"]

# --- 4. BỘ HÀM TẢI DỮ LIỆU ---
@st.cache_data(ttl=2)
def load_ton_data():
    with engine.connect() as conn:
        return pd.read_sql(text("""
            SELECT id, ngay_loi as "Ngày lỗi", source_warehouse as "Kho", vi_tri_de as "Vị trí", 
                   order_code as "Mã đơn", brand as "Hãng", thickness as "Dày (mm)", color as "Màu", 
                   corrugation_type as "Sóng", ton_type as "Loại tôn", foam_type as "Quy cách xốp/ngói", 
                   sheet_length as "Dài (m)", current_sheets as "Số tấm còn", 
                   COALESCE(remaining_meters, total_meters) as "Còn lại mét tồn kho",
                   CASE WHEN is_matched LIKE '%Đã ghép%' THEN '🟢 Đã ghép' ELSE '🔴 Chưa ghép' END as "Hàng đã xử lý ghép",
                   reason as "Nguyên nhân", fault_by as "Lỗi do ai",
                   COALESCE(matched_order_code, '') as "Đơn hàng ghép",
                   COALESCE(matched_by_user, '') as "Ai là người ghép",
                   COALESCE(matched_length, 0.0) as "Ghép sang kích thước (m)",
                   COALESCE(matched_sheets, 0) as "Số lượng tấm ghép",
                   COALESCE(scrap_meters, 0.0) as "Phế (m)",
                   COALESCE(usable_length, sheet_length) as "Độ dài ghép được (m)"
            FROM inventory ORDER BY id DESC
        """), conn)

@st.cache_data(ttl=2)
def load_pk_data():
    with engine.connect() as conn:
        return pd.read_sql(text("""
            SELECT id, ngay_loi as "Ngày lỗi", source_warehouse as "Kho", 
                   COALESCE(customer_name, '') as "Khách Hàng/Đại Lý",
                   vi_tri_de as "Vị trí", order_code as "Mã đơn", 
                   accessory_type as "Loại phụ kiện", brand as "Tên phụ kiện", 
                   COALESCE(kho_phu_kien, '') as "Khổ PK",
                   thickness as "Dày (mm)", color as "Màu", 
                   sheet_length as "Dài 1 tấm (m)", current_sheets as "Số tấm còn", 
                   total_meters as "Tổng mét", 
                   CASE 
                       WHEN trang_thai LIKE '%Đã xử lý%' THEN '🟢 Đã xử lý'
                       WHEN trang_thai LIKE '%Đã xả%' THEN '🟡 Đã xả'
                       ELSE '🔴 Chưa xử lý'
                   END as "Trạng thái", 
                   COALESCE(don_da_ghep, '') as "Đơn đã ghép",
                   COALESCE(nguoi_ghep, '') as "Người ghép",
                   COALESCE(CAST(ngay_ghep AS TEXT), '') as "Ngày ghép",
                   reason as "Nguyên nhân", fault_by as "Lỗi do ai",
                   COALESCE(usable_length, sheet_length) as "Độ dài ghép được (m)"
            FROM accessory_inventory ORDER BY id DESC
        """), conn)

@st.cache_data(ttl=2)
def load_panel_data():
    with engine.connect() as conn:
        return pd.read_sql(text("""
            SELECT id, ngay_loi as "Ngày lỗi", source_warehouse as "Kho", vi_tri_de as "Vị trí", 
                   order_code as "Mã đơn", brand as "Hãng tôn", COALESCE(steel_thickness, 0.40) as "Dày tôn (mm)", 
                   color as "Màu", core_thickness as "Độ dày Panel", kho_ton as "Khổ tôn", foam_type as "Quy cách xốp", 
                   sheet_length as "Dài 1 tấm (m)", current_sheets as "Số tấm còn", 
                   COALESCE(remaining_meters, total_meters) as "Còn lại mét tồn kho",
                   total_area_m2 as "Tổng m2",
                   CASE WHEN is_matched LIKE '%Đã ghép%' THEN '🟢 Đã ghép' ELSE '🔴 Chưa ghép' END as "Hàng đã xử lý ghép",
                   reason as "Nguyên nhân", fault_by as "Lỗi do ai",
                   COALESCE(matched_order_code, '') as "Đơn hàng ghép",
                   COALESCE(matched_by_user, '') as "Ai là người ghép",
                   COALESCE(matched_length, 0.0) as "Ghép sang kích thước (m)",
                   COALESCE(matched_sheets, 0) as "Số lượng tấm ghép",
                   COALESCE(scrap_meters, 0.0) as "Phế (m)",
                   COALESCE(usable_length, sheet_length) as "Độ dài ghép được (m)"
            FROM panel_inventory ORDER BY id DESC
        """), conn)

@st.cache_data(ttl=2)
def load_chemical_import():
    with engine.connect() as conn:
        return pd.read_sql(text("""
            SELECT id, import_date as "Ngày nhập", chemical_name as "Tên hóa chất", 
                   phuy_count as "Số phuy", kg_per_phuy as "Kg/Phuy", total_kg as "Tổng Kg", 
                   COALESCE(note, '') as "Ghi chú", created_by as "Người nhập"
            FROM chemical_import ORDER BY id DESC
        """), conn)

@st.cache_data(ttl=2)
def load_chemical_production():
    with engine.connect() as conn:
        return pd.read_sql(text("""
            SELECT id, log_date as "Ngày", chemical_name as "Tên hóa chất", department as "Bộ phận",
                   phuy_nguyen_count as "Phuy nguyên", kg_per_phuy as "Kg/Phuy", phuy_nguyen_kg as "Kg phuy nguyên",
                   phuy_gio_count as "Phuy giở", phuy_gio_kg as "Kg phuy giở", bon_kg as "Kg bồn",
                   total_kg as "Tổng Kg", operator_name as "Người ghi"
            FROM chemical_production_log ORDER BY id DESC
        """), conn)

@st.cache_data(ttl=2)
def load_chemical_norms():
    with engine.connect() as conn:
        return pd.read_sql(text("SELECT chemical_name as \"Chủng loại\", norm_phuy as \"Định mức Phuy\", norm_kg as \"Định mức Kg\" FROM chemical_norm"), conn)

# --- 5. DUY TRÌ ĐĂNG NHẬP VĨNH VIỄN ---
if "user" not in st.session_state:
    st.session_state.user = None

if st.session_state.user is None and "u" in st.query_params:
    cached_user = st.query_params["u"]
    with engine.connect() as conn:
        res = conn.execute(text("SELECT username, full_name, role, is_approved FROM users WHERE username = :u"), {"u": cached_user}).fetchone()
    if res and res[3] == 1:
        st.session_state.user = {"username": res[0], "name": res[1], "role": res[2]}

msg_flash = st.session_state.pop("msg_success", None)
if msg_flash:
    st.success(msg_flash)
    st.toast(msg_flash, icon="✅")

if "num_specs_ton" not in st.session_state: st.session_state.num_specs_ton = 1
if "num_specs_pk" not in st.session_state: st.session_state.num_specs_pk = 1
if "num_specs_pn" not in st.session_state: st.session_state.num_specs_pn = 1
if "so_dong_kich_thuoc" not in st.session_state: st.session_state.so_dong_kich_thuoc = 1

# --- SIDEBAR: PHÂN QUYỀN HỆ THỐNG ---
st.sidebar.title("🔐 Phân quyền hệ thống")

if st.session_state.user is None:
    tab_auth = st.sidebar.radio("Chọn thao tác:", ["Đăng nhập", "Đăng ký tài khoản mới"])
    if tab_auth == "Đăng nhập":
        with st.sidebar.form("form_login"):
            u_login = st.text_input("Tài khoản").strip().lower()
            p_login = st.text_input("Mật khẩu", type="password")
            if st.form_submit_button("Đăng nhập"):
                with engine.connect() as conn:
                    res = conn.execute(text("SELECT password_hash, full_name, role, is_approved FROM users WHERE username = :u"), {"u": u_login}).fetchone()
                if res and res[3] == 1 and bcrypt.checkpw(p_login.encode('utf-8'), res[0].encode('utf-8')):
                    st.session_state.user = {"username": u_login, "name": res[1], "role": res[2]}
                    st.query_params["u"] = u_login
                    st.rerun()
                elif res and res[3] == 0:
                    st.sidebar.warning("⏳ Tài khoản đang chờ duyệt!")
                else:
                    st.sidebar.error("Sai tài khoản hoặc mật khẩu!")
    else:
        with st.sidebar.form("form_register"):
            reg_u = st.text_input("Tên tài khoản").strip().lower()
            reg_name = st.text_input("Họ tên")
            reg_p = st.text_input("Mật khẩu", type="password")
            if st.form_submit_button("Đăng ký"):
                if reg_u and reg_p and reg_name:
                    p_hash = bcrypt.hashpw(reg_p.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                    with engine.connect() as conn:
                        conn.execute(text("INSERT INTO users (username, password_hash, full_name, role, is_approved) VALUES (:u, :p, :n, 'operator', 0)"),
                                     {"u": reg_u, "p": p_hash, "n": reg_name})
                        conn.commit()
                    st.sidebar.success("✅ Đã gửi đăng ký!")
else:
    st.sidebar.success(f"Xin chào: **{st.session_state.user['name']}**")
    st.sidebar.caption(f"Vai trò: `{st.session_state.user['role']}`")
    if st.sidebar.button("Đăng xuất"):
        st.session_state.user = None
        if "u" in st.query_params: del st.query_params["u"]
        st.rerun()

menu_options = ["📋 Tra cứu tồn kho", "🧪 Tồn kho & Định mức Hóa chất", "📊 Báo cáo Dashboard"]
if st.session_state.user is not None:
    menu_options.insert(1, "➕ Nhập lỗi Tôn")
    menu_options.insert(2, "➕ Nhập lỗi Phụ kiện")
    menu_options.insert(3, "➕ Nhập lỗi Panel")
    menu_options.insert(4, "✂️ Tìm kiếm & Ghép đơn")
    menu_options.insert(5, "📥 Nhập kho Hóa chất")
    menu_options.insert(6, "📝 Nhật ký SX Hóa chất")
    if st.session_state.user['role'] == 'admin':
        menu_options.append("👑 Phê duyệt & Cấp quyền tài khoản")

lua_chon = st.sidebar.radio("Chức năng:", menu_options)
da_dang_nhap = st.session_state.user is not None

# =============================================================
# 1. TRA CỨU TỒN KHO
# =============================================================
if lua_chon == "📋 Tra cứu tồn kho":
    if not da_dang_nhap:
        st.warning("🔒 **Bạn đang ở Chế độ Chỉ Xem (Read-only)**. Vui lòng đăng nhập để thao tác.")
    tab_ton, tab_pk, tab_pn = st.tabs(["📦 Tồn kho Tôn lỗi", "🛠️ Tồn kho Phụ kiện", "🧱 Tồn kho Panel"])
    with tab_ton:
        st.subheader("📋 Danh mục Tôn lỗi tồn kho")
        df_ton = load_ton_data()
        st.download_button("📥 Tải kho Tôn về Excel (.xlsx)", to_excel_bytes(df_ton, 'Ton_Loi'), f"Ton_Kho_Ton_{datetime.date.today()}.xlsx")
        edited_ton = st.data_editor(df_ton, disabled=df_ton.columns.tolist() if not da_dang_nhap else ["id"], width='stretch', key="editor_ton")
        if da_dang_nhap and st.button("💾 Lưu thay đổi trên bảng Tôn", type="primary", key="btn_save_ton_manual"):
            with engine.connect() as conn:
                for idx, r in edited_ton.iterrows():
                    sl_val = safe_float(r["Dài (m)"])
                    cs_val = safe_int(r["Số tấm còn"])
                    conn.execute(text("""
                        UPDATE inventory SET ngay_loi=:nl, source_warehouse=:wh, vi_tri_de=:vt, order_code=:oc,
                        brand=:br, thickness=:th, color=:co, corrugation_type=:cr, ton_type=:tt, foam_type=:fo,
                        sheet_length=:sl, current_sheets=:cs, remaining_meters=:rm, total_meters=:tm, scrap_meters=:sm,
                        usable_length=:ul, is_matched=:im, reason=:re, fault_by=:fb, matched_order_code=:moc,
                        matched_by_user=:mbu, matched_length=:ml, matched_sheets=:ms WHERE id=:id
                    """), {
                        "nl": safe_date(r["Ngày lỗi"]), "wh": safe_str(r["Kho"]), "vt": safe_str(r["Vị trí"]),
                        "oc": safe_str(r["Mã đơn"]), "br": safe_str(r["Hãng"]), "th": safe_float(r["Dày (mm)"]),
                        "co": safe_str(r["Màu"]), "cr": safe_str(r["Sóng"]), "tt": safe_str(r["Loại tôn"]),
                        "fo": safe_str(r["Quy cách xốp/ngói"]), "sl": sl_val, "cs": cs_val, "rm": safe_float(r["Còn lại mét tồn kho"]),
                        "tm": float(sl_val * cs_val), "sm": safe_float(r["Phế (m)"]), "ul": safe_float(r["Độ dài ghép được (m)"], sl_val),
                        "im": "Đã ghép" if "Đã ghép" in str(r["Hàng đã xử lý ghép"]) else "Chưa ghép", "re": safe_str(r["Nguyên nhân"]),
                        "fb": safe_str(r["Lỗi do ai"]), "moc": safe_str(r["Đơn hàng ghép"]), "mbu": safe_str(r["Ai là người ghép"]),
                        "ml": safe_float(r["Ghép sang kích thước (m)"]), "ms": safe_int(r["Số lượng tấm ghép"]), "id": int(r["id"])
                    })
                conn.commit()
            st.cache_data.clear()
            st.session_state["msg_success"] = "Đã lưu bảng Tôn thành công!"
            st.rerun()

    with tab_pk:
        st.subheader("🛠️ Danh mục Phụ kiện")
        df_pk = load_pk_data()
        st.download_button("📥 Tải kho Phụ kiện về Excel (.xlsx)", to_excel_bytes(df_pk, 'Phu_Kien'), f"Ton_Kho_PK_{datetime.date.today()}.xlsx")
        edited_pk = st.data_editor(df_pk, disabled=df_pk.columns.tolist() if not da_dang_nhap else ["id"], width='stretch', key="editor_pk")
        if da_dang_nhap and st.button("💾 Lưu thay đổi trên bảng Phụ kiện", type="primary", key="btn_save_pk_manual"):
            with engine.connect() as conn:
                for idx, r in edited_pk.iterrows():
                    sl_v = safe_float(r["Dài 1 tấm (m)"])
                    cs_v = safe_int(r["Số tấm còn"])
                    conn.execute(text("""
                        UPDATE accessory_inventory SET ngay_loi=:nl, source_warehouse=:wh, customer_name=:cust, vi_tri_de=:vt,
                        order_code=:oc, accessory_type=:at, brand=:br, kho_phu_kien=:kpk, thickness=:th, color=:co, sheet_length=:sl,
                        current_sheets=:cs, total_meters=:tm, usable_length=:ul, trang_thai=:tt, don_da_ghep=:dg, nguoi_ghep=:ng, reason=:re, fault_by=:fb
                        WHERE id=:id
                    """), {
                        "nl": safe_date(r["Ngày lỗi"]), "wh": safe_str(r["Kho"]), "cust": safe_str(r["Khách Hàng/Đại Lý"]), "vt": safe_str(r["Vị trí"]),
                        "oc": safe_str(r["Mã đơn"]), "at": safe_str(r["Loại phụ kiện"]), "br": safe_str(r["Tên phụ kiện"]), "kpk": safe_str(r["Khổ PK"]),
                        "th": safe_float(r["Dày (mm)"]), "co": safe_str(r["Màu"]), "sl": sl_v, "cs": cs_v, "tm": float(sl_v * cs_v),
                        "ul": safe_float(r["Độ dài ghép được (m)"], sl_v), "tt": safe_str(r["Trạng thái"]).replace("🔴 ", "").replace("🟢 ", "").replace("🟡 ", ""),
                        "dg": safe_str(r["Đơn đã ghép"]), "ng": safe_str(r["Người ghép"]), "re": safe_str(r["Nguyên nhân"]), "fb": safe_str(r["Lỗi do ai"]), "id": int(r["id"])
                    })
                conn.commit()
            st.cache_data.clear()
            st.session_state["msg_success"] = "Đã lưu bảng Phụ kiện thành công!"
            st.rerun()

    with tab_pn:
        st.subheader("🧱 Danh mục Panel lỗi tồn kho")
        df_pn = load_panel_data()
        st.download_button("📥 Tải kho Panel về Excel (.xlsx)", to_excel_bytes(df_pn, 'Panel'), f"Ton_Kho_Panel_{datetime.date.today()}.xlsx")
        edited_pn = st.data_editor(df_pn, disabled=df_pn.columns.tolist() if not da_dang_nhap else ["id"], width='stretch', key="editor_pn")
        if da_dang_nhap and st.button("💾 Lưu thay đổi trên bảng Panel", type="primary", key="btn_save_pn_manual"):
            with engine.connect() as conn:
                for idx, r in edited_pn.iterrows():
                    sl_v = safe_float(r["Dài 1 tấm (m)"])
                    cs_v = safe_int(r["Số tấm còn"])
                    rm_v = safe_float(r["Còn lại mét tồn kho"])
                    conn.execute(text("""
                        UPDATE panel_inventory SET ngay_loi=:nl, source_warehouse=:wh, vi_tri_de=:vt, order_code=:oc, brand=:br,
                        steel_thickness=:st, color=:co, core_thickness=:ct, kho_ton=:kt, foam_type=:fo, sheet_length=:sl, current_sheets=:cs,
                        remaining_meters=:rm, scrap_meters=:sm, usable_length=:ul, total_meters=:tm, total_area_m2=:ta, is_matched=:im,
                        reason=:re, fault_by=:fb, matched_order_code=:moc, matched_by_user=:mbu, matched_length=:ml, matched_sheets=:ms
                        WHERE id=:id
                    """), {
                        "nl": safe_date(r["Ngày lỗi"]), "wh": safe_str(r["Kho"]), "vt": safe_str(r["Vị trí"]), "oc": safe_str(r["Mã đơn"]),
                        "br": safe_str(r["Hãng tôn"]), "st": safe_float(r["Dày tôn (mm)"]), "co": safe_str(r["Màu"]), "ct": safe_str(r["Độ dày Panel"]),
                        "kt": safe_str(r["Khổ tôn"]), "fo": safe_str(r["Quy cách xốp"]), "sl": sl_v, "cs": cs_v, "rm": rm_v, "sm": safe_float(r["Phế (m)"]),
                        "ul": safe_float(r["Độ dài ghép được (m)"], sl_v), "tm": float(sl_v * cs_v), "ta": float(rm_v * (1.02 if "1020" in str(r["Khổ tôn"]) else 1.17)),
                        "im": "Đã ghép" if "Đã ghép" in str(r["Hàng đã xử lý ghép"]) else "Chưa ghép", "re": safe_str(r["Nguyên nhân"]), "fb": safe_str(r["Lỗi do ai"]),
                        "moc": safe_str(r["Đơn hàng ghép"]), "mbu": safe_str(r["Ai là người ghép"]), "ml": safe_float(r["Ghép sang kích thước (m)"]),
                        "ms": safe_int(r["Số lượng tấm ghép"]), "id": int(r["id"])
                    })
                conn.commit()
            st.cache_data.clear()
            st.session_state["msg_success"] = "Đã lưu bảng Panel thành công!"
            st.rerun()

# =============================================================
# 2. NHẬP KHO HÓA CHẤT (HỖ TRỢ SỬA KHI NHẬP SAI - ẢNH 1)
# =============================================================
elif lua_chon == "📥 Nhập kho Hóa chất":
    st.title("📥 Nhập Kho Hóa Chất")
    with st.form("form_nhap_hoa_chat"):
        col_hc1, col_hc2 = st.columns(2)
        with col_hc1:
            ngay_nhap_hc = st.date_input("Ngày nhập kho", datetime.date.today())
            ten_hc = st.selectbox("Loại Hóa Chất *", DANH_SACH_HOA_CHAT)
            so_phuy_nhap = st.number_input("Số lượng (Phuy) *", min_value=0.1, value=1.0, step=1.0)
        with col_hc2:
            is_iso = "ISO" in ten_hc
            kg_options = [250.0] if is_iso else [220.0, 210.0, 250.0]
            kg_per_phuy = st.selectbox("Quy cách trọng lượng (Kg / Phuy) *", kg_options)
            ghi_chu_hc = st.text_input("Ghi chú / Số lô sản xuất", placeholder="Ví dụ: Lô SX ngày...")

        tong_kg_nhap = float(so_phuy_nhap * kg_per_phuy)
        st.info(f"👉 Tổng trọng lượng quy đổi: **{tong_kg_nhap:,.1f} Kg** ({so_phuy_nhap:.1f} Phuy x {kg_per_phuy} Kg)")
        btn_luu_nhap_hc = st.form_submit_button("💾 Lưu Nhập Kho Hóa Chất", type="primary")

    if btn_luu_nhap_hc:
        with engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO chemical_import (import_date, chemical_name, phuy_count, kg_per_phuy, total_kg, note, created_by)
                VALUES (:dt, :name, :phuy, :kg_p, :tot_kg, :note, :user)
            """), {
                "dt": ngay_nhap_hc, "name": ten_hc, "phuy": so_phuy_nhap, "kg_p": kg_per_phuy,
                "tot_kg": tong_kg_nhap, "note": ghi_chu_hc,
                "user": st.session_state.user['name'] if st.session_state.user else "NV"
            })
            conn.commit()
        st.cache_data.clear()
        st.session_state["msg_success"] = f"✅ Đã nhập kho thành công {so_phuy_nhap:.1f} Phuy ({tong_kg_nhap:,.1f} Kg) {ten_hc}!"
        st.rerun()

    st.markdown("---")
    st.subheader("📋 Lịch sử các đợt nhập kho gần nhất (Có thể sửa trực tiếp)")
    st.caption("💡 *Click đúp chuột vào bất kỳ ô nào nhập sai để sửa lại rồi bấm **Lưu thay đổi**.*")
    
    df_im_hc = load_chemical_import()
    if not df_im_hc.empty:
        edited_im_hc = st.data_editor(
            df_im_hc,
            disabled=["id", "Người nhập"],
            column_config={
                "Tên hóa chất": st.column_config.SelectboxColumn("Tên hóa chất", options=DANH_SACH_HOA_CHAT),
                "Số phuy": st.column_config.NumberColumn("Số phuy", format="%.1f"),
                "Kg/Phuy": st.column_config.NumberColumn("Kg/Phuy", format="%.1f"),
                "Tổng Kg": st.column_config.NumberColumn("Tổng Kg", format="%.1f")
            },
            width='stretch',
            key="editor_im_hc"
        )
        
        c_hc_btn1, c_hc_btn2 = st.columns([3, 7])
        with c_hc_btn1:
            if st.button("💾 Lưu thay đổi lịch sử nhập kho", type="primary", key="btn_save_im_hc_edit"):
                with engine.connect() as conn:
                    for idx, r in edited_im_hc.iterrows():
                        p_cnt = safe_float(r["Số phuy"])
                        k_per = safe_float(r["Kg/Phuy"])
                        tot_k = float(p_cnt * k_per)
                        conn.execute(text("""
                            UPDATE chemical_import
                            SET import_date = :dt, chemical_name = :name, phuy_count = :phuy,
                                kg_per_phuy = :kg_p, total_kg = :tot_kg, note = :note
                            WHERE id = :id
                        """), {
                            "dt": safe_date(r["Ngày nhập"]), "name": safe_str(r["Tên hóa chất"]),
                            "phuy": p_cnt, "kg_p": k_per, "tot_kg": tot_k,
                            "note": safe_str(r["Ghi chú"]), "id": int(r["id"])
                        })
                    conn.commit()
                st.cache_data.clear()
                st.session_state["msg_success"] = "Đã cập nhật thay đổi lịch sử nhập kho hóa chất thành công!"
                st.rerun()
                
        with st.expander("🗑️ Xóa dòng nhập kho bị sai"):
            c_del_im1, c_del_im2 = st.columns([3, 2])
            with c_del_im1:
                id_del_im = st.selectbox("Chọn ID nhập kho cần xóa:", df_im_hc['id'].tolist(), key="sel_del_im_hc")
            with c_del_im2:
                st.write("")
                st.write("")
                if st.button("❌ Xóa dòng nhập này", key="btn_del_im_hc_act"):
                    with engine.connect() as conn:
                        conn.execute(text("DELETE FROM chemical_import WHERE id = :id"), {"id": int(id_del_im)})
                        conn.commit()
                    st.cache_data.clear()
                    st.session_state["msg_success"] = f"Đã xóa dòng nhập kho ID {id_del_im}!"
                    st.rerun()

# =============================================================
# 3. NHẬT KÝ SẢN XUẤT HÓA CHẤT (HỖ TRỢ SỬA KHI NHẬP SAI - ẢNH 2)
# =============================================================
elif lua_chon == "📝 Nhật ký SX Hóa chất":
    st.title("📝 Nhật Ký Sản Xuất Hóa Chất")
    with st.form("form_nhat_ky_sx_hc"):
        c_nk1, c_nk2 = st.columns(2)
        with c_nk1:
            ngay_sx_hc = st.date_input("Ngày sản xuất", datetime.date.today())
            ten_hc_sx = st.selectbox("Loại Hóa Chất *", DANH_SACH_HOA_CHAT)
            bo_phan_sd = st.selectbox("Bộ phận sử dụng *", ["Tổ Panel", "Tổ Xốp Cán Tôn", "Tổ Ngói Xốp", "Bảo dưỡng / Khác"])
        with c_nk2:
            is_iso_sx = "ISO" in ten_hc_sx
            kg_options_sx = [250.0] if is_iso_sx else [220.0, 210.0, 250.0]
            kg_quy_cach_sx = st.selectbox("Quy cách Phuy nguyên (Kg/Phuy) *", kg_options_sx)

        st.markdown("##### 🔢 Chi tiết số lượng tiêu hao:")
        c_sx_a, c_sx_b, c_sx_c = st.columns(3)
        with c_sx_a:
            phuy_nguyen_cnt = st.number_input("Số phuy nguyên", min_value=0.0, value=0.0, step=1.0)
            kg_phuy_nguyen = float(phuy_nguyen_cnt * kg_quy_cach_sx)
            st.caption(f"= {kg_phuy_nguyen:,.1f} Kg")
        with c_sx_b:
            phuy_gio_cnt = st.number_input("Số phuy giở", min_value=0.0, value=0.0, step=0.1)
            kg_phuy_gio = st.number_input("Số Kg thực tế phuy giở", min_value=0.0, value=0.0, step=1.0)
        with c_sx_c:
            kg_trong_bon = st.number_input("H/C trong bồn (Kg)", min_value=0.0, value=0.0, step=5.0)

        tong_kg_tieu_hao = kg_phuy_nguyen + kg_phuy_gio + kg_trong_bon
        st.info(f"👉 **Tổng lượng H/C xuất dùng: {tong_kg_tieu_hao:,.1f} Kg**")
        btn_luu_nk_sx = st.form_submit_button("💾 Lưu Nhật Ký Sản Xuất", type="primary")

    if btn_luu_nk_sx:
        if tong_kg_tieu_hao <= 0:
            st.warning("⚠️ Vui lòng nhập số lượng hóa chất sản xuất lớn hơn 0!")
        else:
            with engine.connect() as conn:
                conn.execute(text("""
                    INSERT INTO chemical_production_log (
                        log_date, chemical_name, department, phuy_nguyen_count, kg_per_phuy,
                        phuy_nguyen_kg, phuy_gio_count, phuy_gio_kg, bon_kg, total_kg, operator_name
                    ) VALUES (
                        :dt, :name, :dept, :pn_c, :kg_p, :pn_kg, :pg_c, :pg_kg, :bon_kg, :tot, :user
                    )
                """), {
                    "dt": ngay_sx_hc, "name": ten_hc_sx, "dept": bo_phan_sd, "pn_c": phuy_nguyen_cnt,
                    "kg_p": kg_quy_cach_sx, "pn_kg": kg_phuy_nguyen, "pg_c": phuy_gio_cnt,
                    "pg_kg": kg_phuy_gio, "bon_kg": kg_trong_bon, "tot": tong_kg_tieu_hao,
                    "user": st.session_state.user['name'] if st.session_state.user else "NV"
                })
                conn.commit()
            st.cache_data.clear()
            st.session_state["msg_success"] = f"✅ Đã ghi nhận nhật ký SX {ten_hc_sx} ({tong_kg_tieu_hao:,.1f} Kg)!"
            st.rerun()

    st.markdown("---")
    st.subheader("📋 Nhật ký sản xuất gần đây (Có thể sửa trực tiếp)")
    st.caption("💡 *Click đúp chuột vào bất kỳ ô nào nhập sai để sửa lại rồi bấm **Lưu thay đổi**.*")
    
    df_sx_hc = load_chemical_production()
    if not df_sx_hc.empty:
        edited_sx_hc = st.data_editor(
            df_sx_hc,
            disabled=["id", "Người ghi"],
            column_config={
                "Tên hóa chất": st.column_config.SelectboxColumn("Tên hóa chất", options=DANH_SACH_HOA_CHAT),
                "Bộ phận": st.column_config.SelectboxColumn("Bộ phận", options=["Tổ Panel", "Tổ Xốp Cán Tôn", "Tổ Ngói Xốp", "Bảo dưỡng / Khác"]),
                "Phuy nguyên": st.column_config.NumberColumn("Phuy nguyên", format="%.1f"),
                "Kg phuy nguyên": st.column_config.NumberColumn("Kg phuy nguyên", format="%.1f"),
                "Phuy giở": st.column_config.NumberColumn("Phuy giở", format="%.1f"),
                "Kg phuy giở": st.column_config.NumberColumn("Kg phuy giở", format="%.1f"),
                "Kg bồn": st.column_config.NumberColumn("Kg bồn", format="%.1f"),
                "Tổng Kg": st.column_config.NumberColumn("Tổng Kg", format="%.1f")
            },
            width='stretch',
            key="editor_sx_hc"
        )
        
        c_sx_btn1, c_sx_btn2 = st.columns([3, 7])
        with c_sx_btn1:
            if st.button("💾 Lưu thay đổi nhật ký sản xuất", type="primary", key="btn_save_sx_hc_edit"):
                with engine.connect() as conn:
                    for idx, r in edited_sx_hc.iterrows():
                        pn_c = safe_float(r["Phuy nguyên"])
                        kg_p = safe_float(r["Kg/Phuy"])
                        pn_kg = float(pn_c * kg_p)
                        pg_c = safe_float(r["Phuy giở"])
                        pg_kg = safe_float(r["Kg phuy giở"])
                        b_kg = safe_float(r["Kg bồn"])
                        tot_k = pn_kg + pg_kg + b_kg
                        
                        conn.execute(text("""
                            UPDATE chemical_production_log
                            SET log_date = :dt, chemical_name = :name, department = :dept,
                                phuy_nguyen_count = :pn_c, kg_per_phuy = :kg_p, phuy_nguyen_kg = :pn_kg,
                                phuy_gio_count = :pg_c, phuy_gio_kg = :pg_kg, bon_kg = :bon_kg, total_kg = :tot
                            WHERE id = :id
                        """), {
                            "dt": safe_date(r["Ngày"]), "name": safe_str(r["Tên hóa chất"]),
                            "dept": safe_str(r["Bộ phận"]), "pn_c": pn_c, "kg_p": kg_p,
                            "pn_kg": pn_kg, "pg_c": pg_c, "pg_kg": pg_kg, "bon_kg": b_kg,
                            "tot": tot_k, "id": int(r["id"])
                        })
                    conn.commit()
                st.cache_data.clear()
                st.session_state["msg_success"] = "Đã cập nhật thay đổi nhật ký sản xuất hóa chất thành công!"
                st.rerun()

        with st.expander("🗑️ Xóa dòng nhật ký SX bị sai"):
            c_del_sx1, c_del_sx2 = st.columns([3, 2])
            with c_del_sx1:
                id_del_sx = st.selectbox("Chọn ID nhật ký SX cần xóa:", df_sx_hc['id'].tolist(), key="sel_del_sx_hc")
            with c_del_sx2:
                st.write("")
                st.write("")
                if st.button("❌ Xóa dòng nhật ký này", key="btn_del_sx_hc_act"):
                    with engine.connect() as conn:
                        conn.execute(text("DELETE FROM chemical_production_log WHERE id = :id"), {"id": int(id_del_sx)})
                        conn.commit()
                    st.cache_data.clear()
                    st.session_state["msg_success"] = f"Đã xóa dòng nhật ký SX ID {id_del_sx}!"
                    st.rerun()

# =============================================================
# 4. TỒN KHO HÓA CHẤT & ĐỊNH MỨC (CẤU TRÚC CHUẨN ẢNH 1 & NHẬP TAY ẢNH 2)
# =============================================================
elif lua_chon == "🧪 Tồn kho & Định mức Hóa chất":
    st.markdown("<h2 style='text-align: center;'>TỒN KHO HÓA CHẤT CHƯƠNG MỸ</h2>", unsafe_allow_html=True)
    st.caption("<div style='text-align: center;'>Biểu mẫu tổng hợp số liệu nhập - tồn thực tế và định mức sản xuất.</div>", unsafe_allow_html=True)

    df_im = load_chemical_import()
    df_sx = load_chemical_production()
    df_norms = load_chemical_norms()

    # Tạo map tra cứu định mức nhập tay
    norms_map = {}
    for idx, r in df_norms.iterrows():
        norms_map[r["Chủng loại"]] = {
            "phuy": safe_float(r["Định mức Phuy"]),
            "kg": safe_float(r["Định mức Kg"])
        }

    report_data = []
    for hc in DANH_SACH_HOA_CHAT:
        kg_std = 250.0 if "ISO" in hc else 220.0

        # 1. TỔNG SL HÓA CHẤT NHẬP KHO (Chính xác từ bảng Nhập)
        im_filtered = df_im[df_im["Tên hóa chất"] == hc]
        tong_nhap_phuy = im_filtered["Số phuy"].sum()
        tong_nhap_kg = im_filtered["Tổng Kg"].sum()

        # 2. DỮ LIỆU SẢN XUẤT
        sx_filtered = df_sx[df_sx["Tên hóa chất"] == hc]
        sx_phuy_nguyen_count = sx_filtered["Phuy nguyên"].sum()
        sx_phuy_nguyen_kg = sx_filtered["Kg phuy nguyên"].sum()

        sx_phuy_gio_count = sx_filtered["Phuy giở"].sum()
        sx_phuy_gio_kg = sx_filtered["Kg phuy giở"].sum()
        sx_bon_kg = sx_filtered["Kg bồn"].sum()

        sx_phuy_total = sx_phuy_nguyen_count
        sx_kg_total = sx_phuy_nguyen_kg

        # 3. TỒN KHO THỰC TẾ
        ton_phuy_nguyen = max(0.0, tong_nhap_phuy - sx_phuy_nguyen_count)
        ton_kg_phuy_nguyen = max(0.0, tong_nhap_kg - sx_phuy_nguyen_kg)

        ton_phuy_gio = sx_phuy_gio_count
        ton_kg_phuy_gio = sx_phuy_gio_kg

        ton_bon_kg = sx_bon_kg

        # 4. ĐỊNH MỨC TB NGÀY (LẤY TỪ BẢNG NHẬP TAY THEO ẢNH 2)
        norm_val = norms_map.get(hc, {"phuy": 0.0, "kg": 0.0})

        report_data.append({
            "hc": hc,
            "nhap_phuy": f"{tong_nhap_phuy:.1f}" if tong_nhap_phuy > 0 else "",
            "nhap_kg": f"{tong_nhap_kg:.1f}" if tong_nhap_kg > 0 else "",
            "kho_pn_phuy": f"{ton_phuy_nguyen:.1f}" if ton_phuy_nguyen > 0 else "",
            "kho_pn_kg": f"{ton_kg_phuy_nguyen:.1f}" if ton_kg_phuy_nguyen > 0 else "",
            "kho_pg_phuy": f"{ton_phuy_gio:.1f}" if ton_phuy_gio > 0 else "",
            "kho_pg_kg": f"{ton_kg_phuy_gio:.1f}" if ton_kg_phuy_gio > 0 else "",
            "sx_p_phuy": f"{sx_phuy_total:.1f}" if sx_phuy_total > 0 else "",
            "sx_p_kg": f"{sx_kg_total:.1f}" if sx_kg_total > 0 else "",
            "sx_bon_kg": f"{ton_bon_kg:.1f}" if ton_bon_kg > 0 else "",
            "norm_phuy": f"{norm_val['phuy']:.1f}" if norm_val['phuy'] > 0 else "",
            "norm_kg": f"{norm_val['kg']:.1f}" if norm_val['kg'] > 0 else ""
        })

    # XUẤT BẢNG HTML CHUẨN MERGE HEADER ĐÚNG 100% THEO ẢNH 1
    table_html = """
    <style>
        .chem-table {
            width: 100%;
            border-collapse: collapse;
            font-family: 'Times New Roman', Times, serif;
            color: #000;
            background-color: #fff;
            margin-top: 10px;
        }
        .chem-table th, .chem-table td {
            border: 1px solid #000;
            padding: 6px 8px;
            text-align: center;
            font-size: 14px;
        }
        .chem-table th {
            font-weight: bold;
            background-color: #f9f9f9;
        }
        .chem-table td.col-name {
            text-align: left;
            font-weight: bold;
            padding-left: 10px;
        }
    </style>
    <table class="chem-table">
        <thead>
            <tr>
                <th rowspan="3" style="width: 20%;">CHỦNG LOẠI</th>
                <th colspan="2" rowspan="2" style="width: 14%;">Tổng SL Hóa Chất<br>Nhập Kho</th>
                <th colspan="7" style="width: 48%;">SL Hóa Chất Trong Kho</th>
                <th colspan="2" rowspan="2" style="width: 18%;">Định mức trung bình sản xuất<br>trong 1 ngày</th>
            </tr>
            <tr>
                <th colspan="2">SL Hóa Chất<br>(Phuy nguyên)</th>
                <th colspan="2">SL Hóa Chất<br>(Phuy giở)</th>
                <th colspan="2">SL Hóa Chất<br>SX (Phuy)</th>
                <th rowspan="2">SL H/C SX<br>(Trong bồn)<br>Kg</th>
            </tr>
            <tr>
                <th>Phuy</th><th>Kg</th>
                <th>Phuy</th><th>Kg</th>
                <th>Phuy</th><th>Kg</th>
                <th>Phuy</th><th>Kg</th>
                <th>Phuy</th><th>Kg</th>
            </tr>
        </thead>
        <tbody>
    """
    for row in report_data:
        table_html += f"""
            <tr>
                <td class="col-name">{row['hc']}</td>
                <td>{row['nhap_phuy']}</td>
                <td>{row['nhap_kg']}</td>
                <td>{row['kho_pn_phuy']}</td>
                <td>{row['kho_pn_kg']}</td>
                <td>{row['kho_pg_phuy']}</td>
                <td>{row['kho_pg_kg']}</td>
                <td>{row['sx_p_phuy']}</td>
                <td>{row['sx_p_kg']}</td>
                <td>{row['sx_bon_kg']}</td>
                <td>{row['norm_phuy']}</td>
                <td>{row['norm_kg']}</td>
            </tr>
        """
    table_html += "</tbody></table>"
    st.markdown(table_html, unsafe_allow_html=True)

    # Nút xuất file Excel
    st.write("")
    df_excel_export = pd.DataFrame([{
        "CHỦNG LOẠI": r["hc"],
        "Tổng Nhập (Phuy)": r["nhap_phuy"],
        "Tổng Nhập (Kg)": r["nhap_kg"],
        "Phuy nguyên tồn (Phuy)": r["kho_pn_phuy"],
        "Phuy nguyên tồn (Kg)": r["kho_pn_kg"],
        "Phuy giở (Phuy)": r["kho_pg_phuy"],
        "Phuy giở (Kg)": r["kho_pg_kg"],
        "SX Phuy (Phuy)": r["sx_p_phuy"],
        "SX Phuy (Kg)": r["sx_p_kg"],
        "SX Trong bồn (Kg)": r["sx_bon_kg"],
        "Định mức TB ngày (Phuy)": r["norm_phuy"],
        "Định mức TB ngày (Kg)": r["norm_kg"]
    } for r in report_data])

    st.download_button(
        label="📥 Tải Báo cáo Hóa chất về Excel (.xlsx)",
        data=to_excel_bytes(df_excel_export, 'Ton_Kho_Hoa_Chat'),
        file_name=f"Ton_Kho_Hoa_Chat_Chuong_My_{datetime.date.today().strftime('%d_%m_%Y')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="btn_dl_excel_hc_custom"
    )

    # MỤC NHẬP TAY ĐỊNH MỨC TRUNG BÌNH NGÀY (ẢNH 2)
    st.markdown("---")
    with st.expander("⚙️ NHẬP / CẬP NHẬT ĐỊNH MỨC TRUNG BÌNH SẢN XUẤT 1 NGÀY (NHẬP TAY)", expanded=True):
        st.caption("💡 Bạn gõ trực tiếp số Phuy hoặc số Kg định mức vào bảng bên dưới rồi nhấn **Lưu Định Mức**.")
        
        edited_norms = st.data_editor(
            df_norms,
            disabled=["Chủng loại"],
            column_config={
                "Định mức Phuy": st.column_config.NumberColumn("Định mức Phuy", format="%.2f", min_value=0.0),
                "Định mức Kg": st.column_config.NumberColumn("Định mức Kg", format="%.1f", min_value=0.0)
            },
            width='stretch',
            key="editor_chemical_norms"
        )

        if st.button("💾 Lưu Định Mức Sản Xuất", type="primary", key="btn_save_chemical_norms"):
            with engine.connect() as conn:
                for idx, r in edited_norms.iterrows():
                    conn.execute(text("""
                        INSERT INTO chemical_norm (chemical_name, norm_phuy, norm_kg)
                        VALUES (:name, :phuy, :kg)
                        ON CONFLICT (chemical_name) DO UPDATE
                        SET norm_phuy = EXCLUDED.norm_phuy, norm_kg = EXCLUDED.norm_kg;
                    """), {
                        "name": safe_str(r["Chủng loại"]),
                        "phuy": safe_float(r["Định mức Phuy"]),
                        "kg": safe_float(r["Định mức Kg"])
                    })
                conn.commit()
            st.cache_data.clear()
            st.session_state["msg_success"] = "✅ Đã lưu định mức sản xuất hóa chất thành công!"
            st.rerun()

# =============================================================
# (CÁC MỤC KHÁC GIỮ NGUYÊN HOÀN TOÀN)
# =============================================================
elif lua_chon == "➕ Nhập lỗi Tôn":
    st.title("➕ Nhập hàng lỗi phát sinh cho Tôn")
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        ngay_loi_ton = st.date_input("Ngày phát sinh lỗi", datetime.date.today(), key="nl_ton_date")
        kho_ton = st.selectbox("Kho lưu", ["Kho hàng lỗi NM", "Kho hàng lỗi trả về"], key="wh_ton_sel")
        don_ton = st.text_input("Mã đơn hàng", key="oc_ton_txt").strip()
        vi_tri_ton = st.selectbox("Vị trí để", DANH_SACH_VI_TRI, key="vt_ton_sel")
    with col_b:
        hang_ton = st.selectbox("Hãng tôn *", DANH_SACH_HANG_TON, key="br_ton_sel")
        mau_ton = st.text_input("Màu sắc *", key="co_ton_txt").strip()
        day_ton = st.number_input("Độ dày (dem/mm)", value=0.40, step=0.05, key="th_ton_num")
        song_ton = st.selectbox("Loại sóng", DANH_SACH_SONG, key="cr_ton_sel")
    with col_c:
        loai_ton = st.selectbox("Loại tôn", DANH_SACH_LOAI_TON, key="tt_ton_sel")
        quy_cach_xop = st.selectbox("Quy cách xốp / ngói", DANH_SACH_XOP, key="fo_ton_sel")
        loi_ai_ton = st.text_input("Lỗi do ai", key="fb_ton_txt").strip()
        ly_do_chon_ton = st.selectbox("Nguyên nhân lỗi", DANH_SACH_NGUYEN_NHAN_CHUNG, key="re_ton_sel")
        ly_do_chi_tiet_ton = st.text_area("Ghi chú chi tiết", key="re_ton_note") if ly_do_chon_ton == "Lỗi khác" else ""

    col_btn_spec1, col_btn_spec2 = st.columns([3, 7])
    with col_btn_spec1:
        if st.button("➕ Thêm quy cách kích thước (Add)", key="btn_add_spec_ton"):
            st.session_state.num_specs_ton += 1
            st.rerun()
    with col_btn_spec2:
        if st.session_state.num_specs_ton > 1 and st.button("➖ Bớt dòng", key="btn_del_spec_ton"):
            st.session_state.num_specs_ton -= 1
            st.rerun()

    specs_ton_data = []
    for i in range(st.session_state.num_specs_ton):
        if kho_ton == "Kho hàng lỗi trả về":
            c_sp1, c_sp2, c_sp3 = st.columns(3)
            with c_sp1: d_val = st.number_input(f"Dài 1 tấm (m) #{i+1} *", value=6.0, step=0.1, key=f"ton_len_{i}")
            with c_sp2: u_val = st.number_input(f"Dài ghép được (m) #{i+1} *", value=d_val, step=0.1, key=f"ton_ulen_{i}")
            with c_sp3: q_val = st.number_input(f"Số tấm #{i+1} *", value=5, min_value=1, step=1, key=f"ton_qty_{i}")
            specs_ton_data.append((d_val, q_val, u_val))
        else:
            c_sp1, c_sp2 = st.columns(2)
            with c_sp1: d_val = st.number_input(f"Dài 1 tấm (m) #{i+1} *", value=6.0, step=0.1, key=f"ton_len_{i}")
            with c_sp2: q_val = st.number_input(f"Số tấm #{i+1} *", value=5, min_value=1, step=1, key=f"ton_qty_{i}")
            specs_ton_data.append((d_val, q_val, d_val))

    if st.button("💾 Lưu tôn lỗi vào kho", type="primary", key="btn_save_ton_all"):
        if not hang_ton or not mau_ton:
            st.warning("⚠️ Vui lòng điền đủ Hãng và Màu!")
        else:
            with engine.connect() as conn:
                for d_v, q_v, u_v in specs_ton_data:
                    d_float, q_int, u_float = safe_float(d_v), safe_int(q_v), safe_float(u_v, safe_float(d_v))
                    t_meters = float(d_float * q_int)
                    conn.execute(text("""
                    INSERT INTO inventory (ngay_loi, source_warehouse, order_code, vi_tri_de, brand, thickness, color, 
                                           corrugation_type, ton_type, foam_type, sheet_length, usable_length,
                                           current_sheets, total_meters, remaining_meters, scrap_meters, is_matched, reason, fault_by)
                    VALUES (:nl, :wh, :oc, :vt, :br, :th, :co, :cr, :tt, :fo, :sl, :ul, :cs, :tm, :rm, 0.0, 'Chưa ghép', :re, :fb)
                    """), {
                        "nl": safe_date(ngay_loi_ton), "wh": safe_str(kho_ton), "oc": don_ton or "Không có", "vt": safe_str(vi_tri_ton), 
                        "br": safe_str(hang_ton), "th": safe_float(day_ton), "co": safe_str(mau_ton), "cr": safe_str(song_ton), 
                        "tt": safe_str(loai_ton), "fo": safe_str(quy_cach_xop), "sl": d_float, "ul": u_float, "cs": q_int, 
                        "tm": t_meters, "rm": t_meters, "re": f"Lỗi khác: {ly_do_chi_tiet_ton.strip()}" if ly_do_chon_ton == "Lỗi khác" else ly_do_chon_ton,
                        "fb": safe_str(loi_ai_ton)
                    })
                conn.commit()
            st.cache_data.clear()
            st.session_state.num_specs_ton = 1
            st.session_state["msg_success"] = f"✅ Đã lưu tôn lỗi {hang_ton}!"
            st.rerun()

elif lua_chon == "➕ Nhập lỗi Phụ kiện":
    st.title("➕ Nhập hàng lỗi cho Phụ kiện")
    col_p1, col_p2, col_p3 = st.columns(3)
    with col_p1:
        ngay_loi_pk = st.date_input("Ngày lỗi", datetime.date.today(), key="pk_ngay")
        pk_kho = st.selectbox("Kho lưu", ["Kho hàng lỗi NM", "Kho hàng lỗi trả về"], key="pk_kho")
        pk_customer = st.text_input("🏢 Tên Khách Hàng", key="pk_customer").strip()
        pk_don = st.text_input("Mã đơn", key="pk_don").strip()
        pk_loai = st.selectbox("Loại PK", DANH_SACH_PHU_KIEN, key="pk_loai")
        pk_vi_tri = st.selectbox("Vị trí", DANH_SACH_VI_TRI, key="pk_vt")
    with col_p2:
        pk_ten = st.text_input("Tên phụ kiện *", key="pk_ten").strip()
        pk_kho_phukien = st.text_input("Khổ PK", key="pk_kho_pk").strip()
        pk_mau = st.text_input("Màu sắc *", key="pk_mau").strip()
        pk_day = st.number_input("Độ dày (dem/mm)", value=0.40, step=0.05, key="pk_day")
    with col_p3:
        pk_loi_ai = st.text_input("Lỗi do ai", key="pk_loi_ai").strip()
        pk_ly_do_chon = st.selectbox("Nguyên nhân", DANH_SACH_NGUYEN_NHAN_CHUNG, key="pk_nn")
        pk_ly_do_chi_tiet = st.text_area("Ghi chú", key="pk_note") if pk_ly_do_chon == "Lỗi khác" else ""

    col_btn_pk1, col_btn_pk2 = st.columns([3, 7])
    with col_btn_pk1:
        if st.button("➕ Thêm quy cách kích thước (Add)", key="btn_add_spec_pk"):
            st.session_state.num_specs_pk += 1
            st.rerun()
    with col_btn_pk2:
        if st.session_state.num_specs_pk > 1 and st.button("➖ Bớt dòng", key="btn_del_spec_pk"):
            st.session_state.num_specs_pk -= 1
            st.rerun()

    specs_pk_data = []
    for i in range(st.session_state.num_specs_pk):
        if pk_kho == "Kho hàng lỗi trả về":
            c_sp1, c_sp2, c_sp3 = st.columns(3)
            with c_sp1: d_val = st.number_input(f"Dài (m) #{i+1} *", value=2.0, step=0.1, key=f"pk_len_{i}")
            with c_sp2: u_val = st.number_input(f"Dài ghép được (m) #{i+1} *", value=d_val, step=0.1, key=f"pk_ulen_{i}")
            with c_sp3: q_val = st.number_input(f"Số tấm #{i+1} *", value=5, min_value=1, step=1, key=f"pk_qty_{i}")
            specs_pk_data.append((d_val, q_val, u_val))
        else:
            c_sp1, c_sp2 = st.columns(2)
            with c_sp1: d_val = st.number_input(f"Dài (m) #{i+1} *", value=2.0, step=0.1, key=f"pk_len_{i}")
            with c_sp2: q_val = st.number_input(f"Số tấm #{i+1} *", value=5, min_value=1, step=1, key=f"pk_qty_{i}")
            specs_pk_data.append((d_val, q_val, d_val))

    trang_thai_chon_pk = st.selectbox("Trạng thái:", DANH_SACH_TRANG_THAI_PK, key="pk_tt_init")
    c_xl1, c_xl2 = st.columns(2)
    with c_xl1: don_xu_ly = st.text_input("Đơn ghép (nếu đã xử lý)", key="pk_don_ghep_input").strip()
    with c_xl2: nv_ghep_pk = st.text_input("NV ghép", value=st.session_state.user['name'] if st.session_state.user else "", key="pk_nv_ghep_input").strip()

    if st.button("💾 Lưu phụ kiện vào kho", type="primary", key="btn_save_pk_all"):
        if pk_ten and pk_mau:
            with engine.connect() as conn:
                for d_v, q_v, u_v in specs_pk_data:
                    pk_dai, pk_tam, pk_ulen = safe_float(d_v), safe_int(q_v), safe_float(u_v, safe_float(d_v))
                    conn.execute(text("""
                    INSERT INTO accessory_inventory (ngay_loi, source_warehouse, customer_name, vi_tri_de, order_code, 
                                                     accessory_type, brand, kho_phu_kien, thickness, color, sheet_length, usable_length,
                                                     current_sheets, total_meters, trang_thai, don_da_ghep, nguoi_ghep, reason, fault_by)
                    VALUES (:nl, :wh, :cust, :vt, :oc, :at, :br, :kpk, :th, :co, :sl, :ul, :cs, :tm, :tt, :dg, :ng, :re, :fb)
                    """), {
                        "nl": safe_date(ngay_loi_pk), "wh": safe_str(pk_kho), "cust": safe_str(pk_customer), "vt": safe_str(vi_tri), 
                        "oc": pk_don or "Không có", "at": safe_str(pk_loai), "br": safe_str(pk_ten), "kpk": safe_str(pk_kho_phukien), 
                        "th": safe_float(pk_day), "co": safe_str(pk_mau), "sl": pk_dai, "ul": pk_ulen, "cs": 0 if "Đã xử lý" in trang_thai_chon_pk else pk_tam, 
                        "tm": 0.0 if "Đã xử lý" in trang_thai_chon_pk else float(pk_dai * pk_tam),
                        "tt": trang_thai_chon_pk.replace("🔴 ", "").replace("🟢 ", "").replace("🟡 ", ""),
                        "dg": safe_str(don_xu_ly) if "Đã xử lý" in trang_thai_chon_pk else None, "ng": safe_str(nv_ghep_pk) if "Đã xử lý" in trang_thai_chon_pk else None,
                        "re": safe_str(pk_ly_do_chi_tiet) if pk_ly_do_chon == "Lỗi khác" else pk_ly_do_chon, "fb": safe_str(pk_loi_ai)
                    })
                conn.commit()
            st.cache_data.clear()
            st.session_state.num_specs_pk = 1
            st.session_state["msg_success"] = f"✅ Đã lưu phụ kiện {pk_ten}!"
            st.rerun()

elif lua_chon == "➕ Nhập lỗi Panel":
    st.title("➕ Nhập hàng lỗi phát sinh cho Panel")
    col_pn1, col_pn2, col_pn3 = st.columns(3)
    with col_pn1:
        ngay_loi_pn = st.date_input("Ngày lỗi", datetime.date.today(), key="pn_ngay")
        pn_kho = st.selectbox("Kho lưu", ["Kho hàng lỗi NM", "Kho hàng lỗi trả về"], key="pn_kho")
        pn_don = st.text_input("Mã đơn", key="pn_don").strip()
        vi_tri_pn = st.selectbox("Vị trí", DANH_SACH_VI_TRI, key="pn_vt")
    with col_pn2:
        pn_hang = st.text_input("Hãng tôn *", key="pn_hang").strip()
        pn_day_ton = st.number_input("Độ dày tôn mặt ngoài (dem/mm)", value=0.40, step=0.05, key="pn_day_ton")
        pn_mau = st.selectbox("Màu sắc", DANH_SACH_MAU_PANEL, key="pn_mau")
        pn_core = st.selectbox("Độ dày Panel", DANH_SACH_DO_DAY_PANEL, key="pn_core")
        pn_kho_ton = st.selectbox("Khổ tôn", DANH_SACH_KHO_PANEL, key="pn_kho_ton")
    with col_pn3:
        pn_xop_quy_cach = st.selectbox("Quy cách xốp", DANH_SACH_XOP_PANEL, key="pn_xop")
        pn_loi_ai = st.text_input("Lỗi do ai", key="pn_loi_ai").strip()
        pn_ly_do_chon = st.selectbox("Nguyên nhân", DANH_SACH_NGUYEN_NHAN_PANEL, key="pn_nn")
        pn_ly_do_chi_tiet = st.text_area("Ghi chú", key="pn_note") if pn_ly_do_chon == "Lỗi khác" else ""

    col_btn_pn1, col_btn_pn2 = st.columns([3, 7])
    with col_btn_pn1:
        if st.button("➕ Thêm quy cách kích thước (Add)", key="btn_add_spec_pn"):
            st.session_state.num_specs_pn += 1
            st.rerun()
    with col_btn_pn2:
        if st.session_state.num_specs_pn > 1 and st.button("➖ Bớt dòng", key="btn_del_spec_pn"):
            st.session_state.num_specs_pn -= 1
            st.rerun()

    specs_pn_data = []
    for i in range(st.session_state.num_specs_pn):
        if pn_kho == "Kho hàng lỗi trả về":
            c_sp1, c_sp2, c_sp3 = st.columns(3)
            with c_sp1: d_val = st.number_input(f"Dài 1 tấm (m) #{i+1} *", value=5.0, step=0.1, key=f"pn_len_{i}")
            with c_sp2: u_val = st.number_input(f"Dài ghép được (m) #{i+1} *", value=d_val, step=0.1, key=f"pn_ulen_{i}")
            with c_sp3: q_val = st.number_input(f"Số tấm #{i+1} *", value=4, min_value=1, step=1, key=f"pn_qty_{i}")
            specs_pn_data.append((d_val, q_val, u_val))
        else:
            c_sp1, c_sp2 = st.columns(2)
            with c_sp1: d_val = st.number_input(f"Dài 1 tấm (m) #{i+1} *", value=5.0, step=0.1, key=f"pn_len_{i}")
            with c_sp2: q_val = st.number_input(f"Số tấm #{i+1} *", value=4, min_value=1, step=1, key=f"pn_qty_{i}")
            specs_pn_data.append((d_val, q_val, d_val))

    if st.button("💾 Lưu Panel vào kho", type="primary", key="btn_save_pn_all"):
        if pn_hang:
            he_so_rong = 1.02 if "1020" in pn_kho_ton else 1.17
            with engine.connect() as conn:
                for d_v, q_v, u_v in specs_pn_data:
                    pn_dai, pn_tam, pn_ulen = safe_float(d_v), safe_int(q_v), safe_float(u_v, safe_float(d_v))
                    m_val = float(pn_dai * pn_tam)
                    conn.execute(text("""
                    INSERT INTO panel_inventory (ngay_loi, source_warehouse, vi_tri_de, order_code, brand, steel_thickness, color, 
                                                 core_thickness, kho_ton, foam_type, sheet_length, usable_length,
                                                 current_sheets, total_meters, remaining_meters, scrap_meters, total_area_m2, is_matched, reason, fault_by)
                    VALUES (:nl, :wh, :vt, :oc, :br, :st, :co, :ct, :kt, :fo, :sl, :ul, :cs, :tm, :rm, 0.0, :ta, 'Chưa ghép', :re, :fb)
                    """), {
                        "nl": safe_date(ngay_loi_pn), "wh": safe_str(pn_kho), "vt": safe_str(vi_tri_pn), "oc": pn_don or "Không có", 
                        "br": safe_str(pn_hang), "st": safe_float(pn_day_ton), "co": safe_str(pn_mau), "ct": safe_str(pn_core), 
                        "kt": safe_str(pn_kho_ton), "fo": safe_str(pn_xop_quy_cach), "sl": pn_dai, "ul": pn_ulen, "cs": pn_tam, 
                        "tm": m_val, "rm": m_val, "ta": float(m_val * he_so_rong), "re": safe_str(pn_ly_do_chi_tiet) if pn_ly_do_chon == "Lỗi khác" else pn_ly_do_chon,
                        "fb": safe_str(pn_loi_ai)
                    })
                conn.commit()
            st.cache_data.clear()
            st.session_state.num_specs_pn = 1
            st.session_state["msg_success"] = f"✅ Đã lưu Panel {pn_hang}!"
            st.rerun()

elif lua_chon == "✂️ Tìm kiếm & Ghép đơn":
    tab_ghep_ton, tab_ghep_pk, tab_ghep_pn = st.tabs(["✂️ Ghép Tôn tấm", "🛠️ Xuất / Ghép Phụ kiện", "🧱 Xuất / Ghép Panel"])
    with tab_ghep_ton:
        st.subheader("✂️ Tìm kiếm ghép Tôn mới")
        with st.form("form_tim_kiem_ton"):
            c1, c2, c3 = st.columns(3)
            with c1:
                s_hang = st.selectbox("Hãng tôn", ["Tất cả"] + DANH_SACH_HANG_TON, key="gt_hang")
                s_mau = st.text_input("Màu sắc cần", key="gt_mau").strip()
                s_day = st.number_input("Độ dày (dem/mm)", value=0.35, step=0.05, key="gt_day")
            with c2:
                s_song = st.selectbox("Loại sóng", ["Tất cả"] + DANH_SACH_SONG, key="gt_song")
                s_ton = st.selectbox("Loại tôn", ["Tất cả"] + DANH_SACH_LOAI_TON, key="gt_ton")
                s_xop = st.selectbox("Cấp xốp", DANH_SACH_XOP, key="gt_xop")
            with c3:
                s_dai = st.number_input("Độ dài cần ghép (m)", value=2.0, step=0.1, key="gt_dai")
                btn_tim_ton = st.form_submit_button("🔎 Quét kho tìm tôn", type="primary")

        if btn_tim_ton:
            st.session_state.ton_search_params = {"hang": s_hang, "mau": s_mau, "day": s_day, "song": s_song, "ton": s_ton, "xop": s_xop, "dai": s_dai}

        if "ton_search_params" in st.session_state:
            p = st.session_state.ton_search_params
            df_all_ton = load_ton_data()
            df_all_ton = df_all_ton[df_all_ton["Số tấm còn"] > 0]
            if not df_all_ton.empty:
                df_matched = df_all_ton[df_all_ton["Độ dài ghép được (m)"] >= p["dai"]].copy()
                df_matched = df_matched[df_matched["Dày (mm)"].round(2) >= round(p["day"], 2)]
                if p["hang"] != "Tất cả": df_matched = df_matched[df_matched["Hãng"] == p["hang"]]
                if p["mau"]: df_matched = df_matched[df_matched["Màu"].apply(lambda x: xoa_dau_tieng_viet(p["mau"]) in xoa_dau_tieng_viet(x))]
                if p["song"] != "Tất cả": df_matched = df_matched[df_matched["Sóng"] == p["song"]]
                if p["ton"] != "Tất cả": df_matched = df_matched[df_matched["Loại tôn"] == p["ton"]]

                if not df_matched.empty:
                    st.success(f"🎯 Tìm thấy {len(df_matched)} vị trí đạt chuẩn:")
                    st.dataframe(df_matched, width='stretch')
                    with st.form("form_confirm_ghep_ton_now"):
                        id_ghep = st.selectbox("Chọn ID lô tôn cần lấy", df_matched['id'].tolist())
                        r_target = df_matched[df_matched['id'] == id_ghep].iloc[0]
                        cg1, cg2, cg3 = st.columns(3)
                        with cg1: ma_moi = st.text_input("Mã đơn ghép *").strip()
                        with cg2: tam_ghep = st.number_input("Số tấm cần", min_value=1, max_value=int(r_target['Số tấm còn']), value=1)
                        with cg3: nguoi_ghep = st.text_input("NV ghép", value=st.session_state.user['name'] if st.session_state.user else "")
                        if st.form_submit_button("✅ Xác nhận Ghép", type="primary"):
                            if ma_moi:
                                t_int = safe_int(tam_ghep, 1)
                                t_con = safe_int(r_target['Số tấm còn']) - t_int
                                m_con = float(t_con * safe_float(r_target['Dài (m)']))
                                with engine.connect() as conn:
                                    conn.execute(text("""
                                        UPDATE inventory SET current_sheets=:tc, total_meters=:mc, remaining_meters=:rm, is_matched=:im,
                                        matched_order_code=:moc, matched_by_user=:mbu, matched_length=:ml, matched_sheets=:ms WHERE id=:id
                                    """), {
                                        "tc": t_con, "mc": m_con, "rm": m_con, "im": "Đã ghép" if t_con == 0 else "Chưa ghép",
                                        "moc": ma_moi, "mbu": nguoi_ghep, "ml": safe_float(p["dai"]), "ms": t_int, "id": int(id_ghep)
                                    })
                                    conn.execute(text("""
                                        INSERT INTO matching_history (inventory_id, new_order_code, matched_sheets, matched_length, matched_meters, matched_by, matched_date) 
                                        VALUES (:iid, :od, :ms, :ml, :mm, :mb, CURRENT_DATE)
                                    """), {"iid": int(id_ghep), "od": ma_moi, "ms": t_int, "ml": safe_float(p["dai"]), "mm": float(t_int * p["dai"]), "mb": nguoi_ghep})
                                    conn.commit()
                                st.cache_data.clear()
                                del st.session_state.ton_search_params
                                st.session_state["msg_success"] = f"✅ Đã ghép {t_int} tấm vào đơn {ma_moi}!"
                                st.rerun()
                else: st.info("Không tìm thấy tấm tôn nào thỏa mãn điều kiện yêu cầu.")

    with tab_ghep_pk:
        st.subheader("🛠️ Tìm kiếm Phụ kiện")
        df_pk_all = load_pk_data()
        df_pk_all = df_pk_all[(df_pk_all["Số tấm còn"] > 0) & (~df_pk_all["Trạng thái"].str.contains("Đã xử lý", na=False))]
        st.dataframe(df_pk_all, width='stretch')

    with tab_ghep_pn:
        st.subheader("🧱 Tìm kiếm Panel")
        df_pn_all = load_panel_data()
        df_pn_all = df_pn_all[df_pn_all["Số tấm còn"] > 0]
        st.dataframe(df_pn_all, width='stretch')

elif lua_chon == "📊 Báo cáo Dashboard":
    st.title("📊 Báo cáo Thống kê Toàn xưởng (Tôn - Phụ kiện - Panel)")
    current_now = datetime.date.today()
    c_f_mode, c_f_month, c_f_year = st.columns([3, 3, 3])
    with c_f_mode: view_time_mode = st.radio("⏱️ Chế độ xem:", ["Theo Tháng", "Theo Năm", "Theo Tuần", "Toàn bộ lịch sử"], horizontal=True, index=0)
    danh_sach_nam = list(range(current_now.year - 2, current_now.year + 3))

    if view_time_mode == "Theo Tháng":
        with c_f_month: selected_month = st.selectbox("Tháng:", list(range(1, 13)), index=current_now.month - 1)
        with c_f_year: selected_year = st.selectbox("Năm:", danh_sach_nam, index=danh_sach_nam.index(current_now.year))
        period_text = f"Tháng {selected_month}/{selected_year}"
        sql_time_filter = f"WHERE EXTRACT(MONTH FROM matched_date) = {selected_month} AND EXTRACT(YEAR FROM matched_date) = {selected_year}"
    elif view_time_mode == "Theo Năm":
        with c_f_month: st.write("")
        with c_f_year: selected_year = st.selectbox("Năm:", danh_sach_nam, index=danh_sach_nam.index(current_now.year))
        period_text = f"Năm {selected_year}"
        sql_time_filter = f"WHERE EXTRACT(YEAR FROM matched_date) = {selected_year}"
    elif view_time_mode == "Theo Tuần":
        start_week = current_now - datetime.timedelta(days=current_now.weekday())
        period_text = f"Tuần này (từ {start_week.strftime('%d/%m/%Y')})"
        sql_time_filter = "WHERE matched_date >= CURRENT_DATE - INTERVAL '7 days'"
    else:
        period_text = "Toàn bộ lịch sử tích lũy"
        sql_time_filter = ""

    st.caption(f"📅 Phân tích: **{period_text}**")
    df_ton_all, df_pk_all, df_pn_all = load_ton_data(), load_pk_data(), load_panel_data()
    df_ton_all["Ngày chuẩn"] = pd.to_datetime(df_ton_all["Ngày lỗi"], errors='coerce')
    df_pk_all["Ngày chuẩn"] = pd.to_datetime(df_pk_all["Ngày lỗi"], errors='coerce')
    df_pn_all["Ngày chuẩn"] = pd.to_datetime(df_pn_all["Ngày lỗi"], errors='coerce')

    if view_time_mode == "Theo Tháng":
        df_ton_f = df_ton_all[(df_ton_all["Ngày chuẩn"].dt.month == selected_month) & (df_ton_all["Ngày chuẩn"].dt.year == selected_year)]
        df_pk_f = df_pk_all[(df_pk_all["Ngày chuẩn"].dt.month == selected_month) & (df_pk_all["Ngày chuẩn"].dt.year == selected_year)]
        df_pn_f = df_pn_all[(df_pn_all["Ngày chuẩn"].dt.month == selected_month) & (df_pn_all["Ngày chuẩn"].dt.year == selected_year)]
    elif view_time_mode == "Theo Năm":
        df_ton_f = df_ton_all[df_ton_all["Ngày chuẩn"].dt.year == selected_year]
        df_pk_f = df_pk_all[df_pk_all["Ngày chuẩn"].dt.year == selected_year]
        df_pn_f = df_pn_all[df_pn_all["Ngày chuẩn"].dt.year == selected_year]
    elif view_time_mode == "Theo Tuần":
        df_ton_f = df_ton_all[df_ton_all["Ngày chuẩn"] >= pd.to_datetime(start_week)]
        df_pk_f = df_pk_all[df_pk_all["Ngày chuẩn"] >= pd.to_datetime(start_week)]
        df_pn_f = df_pn_all[df_pn_all["Ngày chuẩn"] >= pd.to_datetime(start_week)]
    else:
        df_ton_f, df_pk_f, df_pn_f = df_ton_all, df_pk_all, df_pn_all

    m_loi_ton = (df_ton_f["Dài (m)"].fillna(0) * df_ton_f["Số tấm còn"].fillna(0)) + (df_ton_f["Ghép sang kích thước (m)"].fillna(0) * df_ton_f["Số lượng tấm ghép"].fillna(0)) + df_ton_f["Phế (m)"].fillna(0)
    m_loi_pk = df_pk_f["Tổng mét"].fillna(0) if "Tổng mét" in df_pk_f.columns else pd.Series(0, index=df_pk_f.index)
    m_loi_pn = (df_pn_f["Dài 1 tấm (m)"].fillna(0) * df_pn_f["Số tấm còn"].fillna(0)) + (df_pn_f["Ghép sang kích thước (m)"].fillna(0) * df_pn_f["Số lượng tấm ghép"].fillna(0)) + df_pn_f["Phế (m)"].fillna(0)
    
    tong_m_loi = float(m_loi_ton.sum() + m_loi_pk.sum() + m_loi_pn.sum())
    tong_m_ghep = float((df_ton_f["Ghép sang kích thước (m)"].fillna(0) * df_ton_f["Số lượng tấm ghép"].fillna(0)).sum() + (df_pn_f["Ghép sang kích thước (m)"].fillna(0) * df_pn_f["Số lượng tấm ghép"].fillna(0)).sum())
    tong_m_phe = float(df_ton_f["Phế (m)"].fillna(0).sum() + df_pn_f["Phế (m)"].fillna(0).sum())
    tong_m_ton_chua_ghep = float(df_ton_f[df_ton_f["Hàng đã xử lý ghép"].str.contains("Chưa ghép", na=False)]["Còn lại mét tồn kho"].fillna(0).sum() + df_pn_f[df_pn_f["Hàng đã xử lý ghép"].str.contains("Chưa ghép", na=False)]["Còn lại mét tồn kho"].fillna(0).sum() + df_pk_f[df_pk_f["Trạng thái"].str.contains("Chưa xử lý", na=False)]["Tổng mét"].fillna(0).sum())

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("🔴 Tổng số m lỗi phát sinh", f"{tong_m_loi:,.1f} m")
    k2.metric("🟢 Tổng số m ghép được", f"{tong_m_ghep:,.1f} m")
    k3.metric("❌ Số lượng phế thải", f"{tong_m_phe:,.1f} m")
    k4.metric("📦 Tồn kho chưa ghép được", f"{tong_m_ton_chua_ghep:,.1f} m")

    st.markdown("---")
    c_d1, c_d2 = st.columns(2)
    with c_d1:
        st.subheader(f"⚠️ Top 5 người/tổ gây lỗi nhiều nhất ({period_text})")
        df_fault_combined = pd.concat([
            df_ton_f[["Lỗi do ai", "Còn lại mét tồn kho"]].rename(columns={"Lỗi do ai": "Người/Tổ máy", "Còn lại mét tồn kho": "Mét"}),
            df_pk_f[["Lỗi do ai", "Tổng mét"]].rename(columns={"Lỗi do ai": "Người/Tổ máy", "Tổng mét": "Mét"}),
            df_pn_f[["Lỗi do ai", "Còn lại mét tồn kho"]].rename(columns={"Lỗi do ai": "Người/Tổ máy", "Còn lại mét tồn kho": "Mét"})
        ])
        df_fault_combined = df_fault_combined[df_fault_combined["Người/Tổ máy"].str.strip() != ""]
        if not df_fault_combined.empty:
            df_top_fault = df_fault_combined.groupby("Người/Tổ máy")["Mét"].agg(["sum", "count"]).reset_index()
            df_top_fault.columns = ["Người/Tổ máy", "Tổng mét lỗi (m)", "Số lần vi phạm"]
            df_top_fault = df_top_fault.sort_values(by="Tổng mét lỗi (m)", ascending=False).head(5).reset_index(drop=True)
            df_top_fault.insert(0, "STT", range(1, len(df_top_fault) + 1))
            st.download_button("📥 Tải Top vi phạm (.xlsx)", to_excel_bytes(df_top_fault, 'Top_Loi'), f"Top_Loi_{period_text.replace('/', '_')}.xlsx")
            st.dataframe(df_top_fault, hide_index=True, use_container_width=True)
        else: st.info("Không có dữ liệu lỗi phát sinh.")

    with c_d2:
        st.subheader(f"🏆 Top 5 người ghép được hàng nhiều nhất ({period_text})")
        with engine.connect() as conn:
            df_top_match = pd.read_sql(text(f"""
                SELECT matched_by as "Nhân viên ghép", ROUND(CAST(SUM(matched_meters) AS numeric), 2) as "Tổng mét ghép (m)", COUNT(id) as "Số lần ghép"
                FROM (
                    SELECT matched_by, matched_meters, id, matched_date FROM matching_history
                    UNION ALL SELECT matched_by, matched_meters, id, matched_date FROM accessory_matching_history
                    UNION ALL SELECT matched_by, matched_meters, id, matched_date FROM panel_matching_history
                ) t {sql_time_filter}
                GROUP BY matched_by ORDER BY SUM(matched_meters) DESC LIMIT 5
            """), conn)
        if not df_top_match.empty and df_top_match["Tổng mét ghép (m)"].sum() > 0:
            df_top_match = df_top_match.reset_index(drop=True)
            df_top_match.insert(0, "STT", range(1, len(df_top_match) + 1))
            st.download_button("📥 Tải Top ghép hàng (.xlsx)", to_excel_bytes(df_top_match, 'Top_Ghep'), f"Top_Ghep_{period_text.replace('/', '_')}.xlsx")
            st.dataframe(df_top_match, hide_index=True, use_container_width=True)
        else: st.info("Không có dữ liệu ghép hàng.")

elif lua_chon == "👑 Phê duyệt & Cấp quyền tài khoản":
    st.title("👑 Quản trị & Phê duyệt nhân viên")
    with engine.connect() as conn:
        df_pending = pd.read_sql(text("SELECT id, username, full_name, role, created_at FROM users WHERE is_approved = 0"), conn)
    if not df_pending.empty:
        for idx, row in df_pending.iterrows():
            with st.container():
                col_u1, col_u2, col_u3, col_u4 = st.columns([2, 3, 2, 2])
                col_u1.write(f"Tài khoản: **{row['username']}**")
                col_u2.write(f"Họ tên: **{row['full_name']}**")
                assigned_role = col_u3.selectbox("Vai trò", ["operator", "admin"], key=f"role_{row['id']}")
                if col_u4.button("✅ Kích hoạt", key=f"btn_ap_{row['id']}"):
                    with engine.connect() as conn:
                        conn.execute(text("UPDATE users SET is_approved = 1, role = :r WHERE id = :id"), {"r": assigned_role, "id": int(row['id'])})
                        conn.commit()
                    st.cache_data.clear()
                    st.session_state["msg_success"] = f"Đã duyệt cho {row['full_name']}!"
                    st.rerun()
            st.divider()
    else: st.info("Hiện không có yêu cầu nào chờ phê duyệt.")
