import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
import bcrypt
import datetime
import unicodedata

st.set_page_config(page_title="Quản Lý Kho Tôn, Phụ Kiện & Panel", layout="wide")

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
        
        try:
            conn.execute(text("ALTER TABLE inventory ADD COLUMN IF NOT EXISTS usable_length REAL DEFAULT 0.0;"))
            conn.execute(text("ALTER TABLE accessory_inventory ADD COLUMN IF NOT EXISTS usable_length REAL DEFAULT 0.0;"))
            conn.execute(text("ALTER TABLE panel_inventory ADD COLUMN IF NOT EXISTS usable_length REAL DEFAULT 0.0;"))
            conn.execute(text("ALTER TABLE inventory ADD COLUMN IF NOT EXISTS scrap_meters REAL DEFAULT 0.0;"))
            conn.execute(text("ALTER TABLE panel_inventory ADD COLUMN IF NOT EXISTS scrap_meters REAL DEFAULT 0.0;"))
            conn.execute(text("ALTER TABLE matching_history ADD COLUMN IF NOT EXISTS matched_sheets INTEGER DEFAULT 1;"))
            conn.execute(text("ALTER TABLE matching_history ADD COLUMN IF NOT EXISTS matched_length REAL DEFAULT 0.0;"))
            conn.execute(text("ALTER TABLE matching_history ADD COLUMN IF NOT EXISTS matched_meters REAL DEFAULT 0.0;"))
            conn.execute(text("ALTER TABLE matching_history ADD COLUMN IF NOT EXISTS new_order_code VARCHAR(150);"))
            conn.execute(text("ALTER TABLE inventory ADD COLUMN IF NOT EXISTS remaining_meters REAL;"))
            conn.execute(text("ALTER TABLE inventory ADD COLUMN IF NOT EXISTS is_matched VARCHAR(100) DEFAULT 'Chưa ghép';"))
            conn.execute(text("ALTER TABLE panel_inventory ADD COLUMN IF NOT EXISTS remaining_meters REAL;"))
            conn.execute(text("ALTER TABLE panel_inventory ADD COLUMN IF NOT EXISTS is_matched VARCHAR(100) DEFAULT 'Chưa ghép';"))
            conn.execute(text("ALTER TABLE panel_inventory ADD COLUMN IF NOT EXISTS steel_thickness REAL DEFAULT 0.40;"))
        except Exception:
            pass

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
DANH_SACH_PHU_KIEN = ["Máng", "Sườn", "Xối", "Nóc"]
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
                   CASE 
                       WHEN is_matched LIKE '%Đã ghép%' THEN '🟢 Đã ghép'
                       ELSE '🔴 Chưa ghép'
                   END as "Hàng đã xử lý ghép",
                   reason as "Nguyên nhân", 
                   fault_by as "Lỗi do ai",
                   COALESCE(matched_order_code, '') as "Đơn hàng ghép",
                   COALESCE(matched_by_user, '') as "Ai là người ghép",
                   COALESCE(matched_length, 0.0) as "Ghép sang kích thước (m)",
                   COALESCE(matched_sheets, 0) as "Số lượng tấm ghép",
                   COALESCE(scrap_meters, 0.0) as "Phế (m)",
                   COALESCE(usable_length, sheet_length) as "Độ dài ghép được (m)"
            FROM inventory 
            ORDER BY id DESC
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
            FROM accessory_inventory 
            ORDER BY id DESC
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
                   CASE 
                       WHEN is_matched LIKE '%Đã ghép%' THEN '🟢 Đã ghép'
                       ELSE '🔴 Chưa ghép'
                   END as "Hàng đã xử lý ghép",
                   reason as "Nguyên nhân", 
                   fault_by as "Lỗi do ai",
                   COALESCE(matched_order_code, '') as "Đơn hàng ghép",
                   COALESCE(matched_by_user, '') as "Ai là người ghép",
                   COALESCE(matched_length, 0.0) as "Ghép sang kích thước (m)",
                   COALESCE(matched_sheets, 0) as "Số lượng tấm ghép",
                   COALESCE(scrap_meters, 0.0) as "Phế (m)",
                   COALESCE(usable_length, sheet_length) as "Độ dài ghép được (m)"
            FROM panel_inventory 
            ORDER BY id DESC
        """), conn)

# --- 5. DUY TRÌ ĐĂNG NHẬP VĨNH VIỄN ---
if "user" not in st.session_state:
    st.session_state.user = None

if st.session_state.user is None and "u" in st.query_params:
    cached_user = st.query_params["u"]
    with engine.connect() as conn:
        res = conn.execute(text("SELECT username, full_name, role, is_approved FROM users WHERE username = :u"), {"u": cached_user}).fetchone()
    if res and res[3] == 1:
        st.session_state.user = {"username": res[0], "name": res[1], "role": res[2]}

if "msg_success" in st.session_state:
    st.success(st.session_state.msg_success)
    st.toast(st.session_state.msg_success, icon="✅")
    del st.session_state.msg_success

# Quản lý số dòng quy cách động cho từng mục nhập lỗi
if "num_specs_ton" not in st.session_state:
    st.session_state.num_specs_ton = 1
if "num_specs_pk" not in st.session_state:
    st.session_state.num_specs_pk = 1
if "num_specs_pn" not in st.session_state:
    st.session_state.num_specs_pn = 1
if "so_dong_kich_thuoc" not in st.session_state:
    st.session_state.so_dong_kich_thuoc = 1

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
                if res:
                    pw_db, f_name, r_role, approved = res
                    if approved == 0:
                        st.sidebar.warning("⏳ Tài khoản đang chờ Quản trị viên phê duyệt!")
                    elif bcrypt.checkpw(p_login.encode('utf-8'), pw_db.encode('utf-8')):
                        st.session_state.user = {"username": u_login, "name": f_name, "role": r_role}
                        st.query_params["u"] = u_login
                        st.rerun()
                    else:
                        st.sidebar.error("Mật khẩu không chính xác!")
                else:
                    st.sidebar.error("Tài khoản không tồn tại!")
    else:
        with st.sidebar.form("form_register"):
            st.write("Điền thông tin để đăng ký:")
            reg_u = st.text_input("Tên tài khoản (viết liền, không dấu)").strip().lower()
            reg_name = st.text_input("Họ và tên nhân viên")
            reg_p = st.text_input("Mật khẩu", type="password")
            reg_confirm = st.text_input("Nhập lại mật khẩu", type="password")
            if st.form_submit_button("Gửi yêu cầu đăng ký"):
                if not reg_u or not reg_name or not reg_p:
                    st.sidebar.warning("Vui lòng điền đầy đủ các mục!")
                elif reg_p != reg_confirm:
                    st.sidebar.error("Mật khẩu nhập lại không khớp!")
                else:
                    try:
                        p_hash = bcrypt.hashpw(reg_p.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                        with engine.connect() as conn:
                            conn.execute(text("""
                            INSERT INTO users (username, password_hash, full_name, role, is_approved)
                            VALUES (:u, :p, :n, 'operator', 0)
                            """), {"u": reg_u, "p": p_hash, "n": reg_name})
                            conn.commit()
                        st.sidebar.success("✅ Đã gửi đăng ký! Hãy báo Admin phê duyệt để sử dụng.")
                    except Exception:
                        st.sidebar.error("Tên đăng nhập này đã được sử dụng!")
else:
    st.sidebar.success(f"Xin chào: **{st.session_state.user['name']}**")
    st.sidebar.caption(f"Vai trò: `{st.session_state.user['role']}`")
    
    if st.sidebar.button("Đăng xuất"):
        st.session_state.user = None
        if "u" in st.query_params:
            del st.query_params["u"]
        st.rerun()
        
    with st.sidebar.expander("🔑 Đổi mật khẩu"):
        with st.form("form_change_pw"):
            old_pw = st.text_input("Mật khẩu hiện tại", type="password")
            new_pw = st.text_input("Mật khẩu mới", type="password")
            confirm_pw = st.text_input("Xác nhận MK mới", type="password")
            if st.form_submit_button("Cập nhật mật khẩu"):
                if not old_pw or not new_pw:
                    st.error("Vui lòng nhập đầy đủ thông tin!")
                elif len(new_pw) < 6:
                    st.error("Mật khẩu mới phải từ 6 ký tự trở lên!")
                elif new_pw != confirm_pw:
                    st.error("Mật khẩu xác nhận không khớp!")
                else:
                    with engine.connect() as conn:
                        res = conn.execute(
                            text("SELECT password_hash FROM users WHERE username = :u"),
                            {"u": st.session_state.user['username']}
                        ).fetchone()
                        
                        if res and bcrypt.checkpw(old_pw.encode('utf-8'), res[0].encode('utf-8')):
                            new_hash = bcrypt.hashpw(new_pw.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                            conn.execute(
                                text("UPDATE users SET password_hash = :p WHERE username = :u"),
                                {"p": new_hash, "u": st.session_state.user['username']}
                            )
                            conn.commit()
                            st.success("✅ Đã đổi mật khẩu thành công!")
                        else:
                            st.error("Mật khẩu hiện tại không đúng!")

# --- MENU CHỨC NĂNG ---
menu_options = ["📋 Tra cứu tồn kho", "📊 Báo cáo Dashboard"]
if st.session_state.user is not None:
    menu_options.insert(1, "➕ Nhập lỗi Tôn")
    menu_options.insert(2, "➕ Nhập lỗi Phụ kiện")
    menu_options.insert(3, "➕ Nhập lỗi Panel")
    menu_options.insert(4, "✂️ Tìm kiếm & Ghép đơn")
    if st.session_state.user['role'] == 'admin':
        menu_options.append("👑 Phê duyệt & Cấp quyền tài khoản")

lua_chon = st.sidebar.radio("Chức năng:", menu_options)

# =============================================================
# 1. TRA CỨU TỒN KHO
# =============================================================
if lua_chon == "📋 Tra cứu tồn kho":
    tab_ton, tab_pk, tab_pn = st.tabs(["📦 Tồn kho Tôn lỗi", "🛠️ Tồn kho Phụ kiện", "🧱 Tồn kho Panel"])
    
    # 1.1 TỒN KHO TÔN LỖI
    with tab_ton:
        st.subheader("📋 Danh mục Tôn lỗi tồn kho")
        
        col_f1, col_f2, col_f3 = st.columns([3, 3, 4])
        with col_f1:
            loc_hang = st.selectbox("🔍 Lọc nhanh theo Hãng tôn:", ["Tất cả"] + DANH_SACH_HANG_TON, key="filter_hang_ton")
        with col_f2:
            loc_mau = st.text_input("🔍 Lọc nhanh theo Màu sắc:", placeholder="Ví dụ: Đen, Xanh, Trắng...", key="filter_mau_ton").strip()
        with col_f3:
            st.write("")
            st.caption("💡 *Đã bổ sung cột **Phế (m)** và **Độ dài ghép được (m)**.*")

        df_ton = load_ton_data()
        
        if loc_hang != "Tất cả":
            df_ton = df_ton[df_ton["Hãng"] == loc_hang]
        if loc_mau:
            df_ton = df_ton[df_ton["Màu"].apply(lambda x: xoa_dau_tieng_viet(loc_mau) in xoa_dau_tieng_viet(x))]

        edited_ton = st.data_editor(
            df_ton,
            disabled=["id"],
            column_config={
                "Hàng đã xử lý ghép": st.column_config.SelectboxColumn(
                    "Hàng đã xử lý ghép", 
                    options=DANH_SACH_TRANG_THAI_TON_PANEL,
                    help="🔴 Chưa ghép | 🟢 Đã ghép (phải có Đơn hàng ghép đi cùng)"
                ),
                "Phế (m)": st.column_config.NumberColumn("Phế (m)", format="%.2f"),
                "Độ dài ghép được (m)": st.column_config.NumberColumn("Độ dài ghép được (m)", format="%.2f"),
                "Kho": st.column_config.SelectboxColumn("Kho", options=["Kho hàng lỗi NM", "Kho hàng lỗi trả về"]),
                "Vị trí": st.column_config.SelectboxColumn("Vị trí", options=DANH_SACH_VI_TRI),
                "Hãng": st.column_config.SelectboxColumn("Hãng", options=DANH_SACH_HANG_TON),
                "Sóng": st.column_config.SelectboxColumn("Sóng", options=DANH_SACH_SONG),
                "Loại tôn": st.column_config.SelectboxColumn("Loại tôn", options=DANH_SACH_LOAI_TON),
                "Quy cách xốp/ngói": st.column_config.SelectboxColumn("Quy cách xốp/ngói", options=DANH_SACH_XOP)
            },
            width='stretch',
            key="editor_ton"
        )

        col_t1, col_t2 = st.columns([3, 7])
        with col_t1:
            if st.button("💾 Lưu thay đổi trên bảng Tôn", type="primary", key="btn_save_ton"):
                co_loi_chua_dien_don = False
                for idx, r in edited_ton.iterrows():
                    if "Đã ghép" in str(r["Hàng đã xử lý ghép"]) and not str(r["Đơn hàng ghép"]).strip():
                        co_loi_chua_dien_don = True
                        st.error(f"⚠️ Dòng ID {r['id']}: Đã chọn '🟢 Đã ghép' thì bắt buộc phải nhập ô 'Đơn hàng ghép'!")
                        break
                
                if not co_loi_chua_dien_don:
                    with engine.connect() as conn:
                        for idx, r in edited_ton.iterrows():
                            row_id = int(r["id"])
                            nl_val = safe_date(r["Ngày lỗi"])
                            sl_val = safe_float(r["Dài (m)"], 0.0)
                            cs_val = safe_int(r["Số tấm còn"], 0)
                            rm_val = safe_float(r["Còn lại mét tồn kho"], 0.0)
                            phe_val = safe_float(r["Phế (m)"], 0.0)
                            ul_val = safe_float(r["Độ dài ghép được (m)"], sl_val)
                            tm_val = float(sl_val * cs_val)
                            im_val = "Đã ghép" if "Đã ghép" in str(r["Hàng đã xử lý ghép"]) else "Chưa ghép"

                            conn.execute(text("""
                                UPDATE inventory 
                                SET ngay_loi = :nl,
                                    source_warehouse = :wh,
                                    vi_tri_de = :vt,
                                    order_code = :oc,
                                    brand = :br,
                                    thickness = :th,
                                    color = :co,
                                    corrugation_type = :cr,
                                    ton_type = :tt,
                                    foam_type = :fo,
                                    sheet_length = :sl,
                                    current_sheets = :cs,
                                    remaining_meters = :rm,
                                    total_meters = :tm,
                                    scrap_meters = :sm,
                                    usable_length = :ul,
                                    is_matched = :im,
                                    reason = :re,
                                    fault_by = :fb,
                                    matched_order_code = :moc,
                                    matched_by_user = :mbu,
                                    matched_length = :ml,
                                    matched_sheets = :ms
                                WHERE id = :id
                            """), {
                                "nl": nl_val, "wh": safe_str(r["Kho"], "Kho hàng lỗi NM"), 
                                "vt": safe_str(r["Vị trí"], "KV_Cán tôn 1L"), "oc": safe_str(r["Mã đơn"], "Không có"),
                                "br": safe_str(r["Hãng"], "Khác"), "th": safe_float(r["Dày (mm)"], 0.40), 
                                "co": safe_str(r["Màu"]), "cr": safe_str(r["Sóng"], "6 sóng"),
                                "tt": safe_str(r["Loại tôn"], "Tôn 1L"), "fo": safe_str(r["Quy cách xốp/ngói"], "Không xốp"), 
                                "sl": sl_val, "cs": cs_val, "rm": rm_val, "tm": tm_val, "sm": phe_val, "ul": ul_val,
                                "im": im_val, "re": safe_str(r["Nguyên nhân"]), "fb": safe_str(r["Lỗi do ai"]),
                                "moc": safe_str(r["Đơn hàng ghép"]), "mbu": safe_str(r["Ai là người ghép"]),
                                "ml": safe_float(r["Ghép sang kích thước (m)"], 0.0), 
                                "ms": safe_int(r["Số lượng tấm ghép"], 0),
                                "id": row_id
                            })
                        conn.commit()
                    st.cache_data.clear()
                    st.session_state.msg_success = "Đã lưu toàn bộ thay đổi bảng Tôn thành công!"
                    st.rerun()

        # --- CÔNG CỤ GHÉP ĐƠN NHIỀU KÍCH THƯỚC ---
        st.markdown("---")
        with st.expander("✏️ CÔNG CỤ GHÉP ĐƠN: 1 MÃ ĐƠN CẮT NHIỀU KÍCH THƯỚC & XỬ LÝ PHẾ TỰ ĐỘNG"):
            df_ghep_avail = df_ton[df_ton["Còn lại mét tồn kho"] > 0]
            if not df_ghep_avail.empty:
                c_gp1, c_gp2 = st.columns([3.5, 6.5])
                with c_gp1:
                    id_ghep_custom = st.selectbox("Chọn ID Lô Tôn cần thao tác ghép:", df_ghep_avail['id'].tolist(), key="sel_ghep_custom")
                    row_cur = df_ghep_avail[df_ghep_avail['id'] == id_ghep_custom].iloc[0]
                    st.info(f"Đang chọn Lô ID **{id_ghep_custom}**\n* Hãng: **{row_cur['Hãng']}** | Màu: **{row_cur['Màu']}**\n* Dài tấm: **{row_cur['Dài (m)']}m** | Số tấm: **{row_cur['Số tấm còn']}**\n* **Mét tồn thực tế: {row_cur['Còn lại mét tồn kho']:.2f} m**")
                    
                    st.write("**Thao tác kích thước:**")
                    c_btn_add1, c_btn_add2 = st.columns(2)
                    with c_btn_add1:
                        if st.button("➕ Thêm kích thước cắt", use_container_width=True):
                            st.session_state.so_dong_kich_thuoc += 1
                            st.rerun()
                    with c_btn_add2:
                        if st.session_state.so_dong_kich_thuoc > 1:
                            if st.button("➖ Bớt kích thước", use_container_width=True):
                                st.session_state.so_dong_kich_thuoc -= 1
                                st.rerun()

                with c_gp2:
                    with st.form("form_ghep_multi_sizes_single_order"):
                        c_ord1, c_ord2 = st.columns(2)
                        with c_ord1:
                            ma_don_ghep_chung = st.text_input("Mã đơn hàng cần ghép vào *", placeholder="Ví dụ: DH0809260348", key="mdg_chung").strip()
                        with c_ord2:
                            nguoi_thuc_hien_ghep = st.text_input("Tên người thực hiện ghép *", value=st.session_state.user['name'] if st.session_state.user else "", key="nth_ghep").strip()

                        st.write("---")
                        st.write("**Danh sách kích thước cần cắt từ lô này:**")
                        
                        list_dai_cat = []
                        list_tam_cat = []
                        for i in range(st.session_state.so_dong_kich_thuoc):
                            col_sz1, col_sz2 = st.columns(2)
                            with col_sz1:
                                d_val = st.number_input(f"Chiều dài kích thước {i+1} (m) *", value=1.5, step=0.1, key=f"sz_len_{i}")
                                list_dai_cat.append(d_val)
                            with col_sz2:
                                t_val = st.number_input(f"Số tấm cắt kích thước {i+1} *", value=1, min_value=1, step=1, key=f"sz_qty_{i}")
                                list_tam_cat.append(t_val)

                        st.write("---")
                        st.write("**Xử lý phần chiều dài dư thừa sau ghép:**")
                        lua_chon_phan_thua = st.radio(
                            "Chọn hướng xử lý đoạn thừa:",
                            ["🟠 Chờ ghép tiếp (lưu kho tiếp để ghép đơn sau)", "❌ Bỏ phế (đoạn thừa tính vào Phế, trừ sạch tồn về 0)"],
                            key="rad_thua"
                        )

                        btn_submit_ghep_custom = st.form_submit_button("🚀 Xác nhận Ghép và Tự động trừ tồn kho", type="primary")

                    if btn_submit_ghep_custom:
                        if not ma_don_ghep_chung or not nguoi_thuc_hien_ghep:
                            st.error("Vui lòng điền đầy đủ Mã đơn hàng ghép và Tên người ghép!")
                        else:
                            tong_met_da_ghep = 0.0
                            tong_so_tam_ghep = 0
                            chi_tiet_cat_str = []
                            
                            for d, t in zip(list_dai_cat, list_tam_cat):
                                if d > 0 and t > 0:
                                    m_line = float(d) * int(t)
                                    tong_met_da_ghep += m_line
                                    tong_so_tam_ghep += int(t)
                                    chi_tiet_cat_str.append(f"{d}mx{t}t")

                            met_ton_hien_tai = safe_float(row_cur['Còn lại mét tồn kho'])
                            if tong_met_da_ghep > met_ton_hien_tai:
                                st.error(f"Tổng mét ghép ({tong_met_da_ghep:.2f}m) vượt quá số mét tồn thực tế của lô ({met_ton_hien_tai:.2f}m)!")
                            else:
                                met_du_thua = met_ton_hien_tai - tong_met_da_ghep
                                
                                if "Bỏ phế" in lua_chon_phan_thua:
                                    met_ton_moi = 0.0
                                    tam_ton_moi = 0
                                    met_phe_moi = float(met_du_thua)
                                    trang_thai_moi = "Đã ghép"
                                else:
                                    met_ton_moi = met_du_thua
                                    dai_tam_goc = safe_float(row_cur['Dài (m)'])
                                    tam_ton_moi = int(met_du_thua / dai_tam_goc) if dai_tam_goc > 0 else 0
                                    if tam_ton_moi == 0 and met_du_thua > 0:
                                        tam_ton_moi = 1
                                    met_phe_moi = 0.0
                                    trang_thai_moi = "Chưa ghép" if met_ton_moi > 0 else "Đã ghép"

                                mota_don_luu = f"{ma_don_ghep_chung} (" + ", ".join(chi_tiet_cat_str) + ")"
                                target_id = int(id_ghep_custom)
                                
                                with engine.connect() as conn:
                                    conn.execute(text("""
                                        UPDATE inventory 
                                        SET current_sheets = :cs, 
                                            remaining_meters = :rm, 
                                            scrap_meters = :sm,
                                            is_matched = :im, 
                                            matched_order_code = :moc, 
                                            matched_by_user = :mbu, 
                                            matched_length = :ml, 
                                            matched_sheets = :ms 
                                        WHERE id = :id
                                    """), {
                                        "cs": int(tam_ton_moi), "rm": float(met_ton_moi), "sm": float(met_phe_moi),
                                        "im": trang_thai_moi, "moc": mota_don_luu, "mbu": nguoi_thuc_hien_ghep, 
                                        "ml": float(list_dai_cat[0]) if list_dai_cat else 0.0, 
                                        "ms": int(tong_so_tam_ghep),
                                        "id": target_id
                                    })
                                    
                                    conn.execute(text("""
                                        INSERT INTO matching_history (inventory_id, new_order_code, matched_sheets, matched_length, matched_meters, matched_by, matched_date) 
                                        VALUES (:iid, :od, :ms, :ml, :mm, :mb, CURRENT_DATE)
                                    """), {
                                        "iid": target_id, 
                                        "od": mota_don_luu, 
                                        "ms": int(tong_so_tam_ghep), 
                                        "ml": float(list_dai_cat[0]) if list_dai_cat else 0.0, 
                                        "mm": float(tong_met_da_ghep), 
                                        "mb": nguoi_thuc_hien_ghep
                                    })
                                    conn.commit()

                                st.cache_data.clear()
                                st.session_state.so_dong_kich_thuoc = 1
                                st.session_state.msg_success = f"✅ Đã ghép {tong_met_da_ghep:.2f}m vào đơn {mota_don_luu}! Tồn còn lại: {met_ton_moi:.2f}m | Phế phát sinh: {met_phe_moi:.2f}m."
                                st.rerun()
            else:
                st.info("Hiện không có lô tôn nào có mét tồn > 0 để ghép.")

        if st.session_state.user and st.session_state.user['role'] == 'admin' and not df_ton.empty:
            with st.expander("🗑️ Xóa dòng Tôn bị nhập sai"):
                c_del1, c_del2 = st.columns([3, 2])
                with c_del1:
                    id_del_ton = st.selectbox("Chọn ID cần xóa:", df_ton['id'].tolist(), key="del_ton_sel")
                with c_del2:
                    st.write("")
                    st.write("")
                    if st.button("❌ Xóa dòng này", key="btn_del_ton"):
                        with engine.connect() as conn:
                            conn.execute(text("DELETE FROM inventory WHERE id = :id"), {"id": int(id_del_ton)})
                            conn.commit()
                        st.cache_data.clear()
                        st.session_state.msg_success = f"Đã xóa vĩnh viễn dòng Tôn ID {id_del_ton}!"
                        st.rerun()

    # 1.2 TỒN KHO PHỤ KIỆN
    with tab_pk:
        st.subheader("🛠️ Danh mục Phụ kiện (Máng, Sườn, Xối, Nóc)")
        df_pk = load_pk_data()

        edited_pk = st.data_editor(
            df_pk,
            disabled=["id"],
            column_config={
                "Kho": st.column_config.SelectboxColumn("Kho", options=["Kho hàng lỗi NM", "Kho hàng lỗi trả về"]),
                "Loại phụ kiện": st.column_config.SelectboxColumn("Loại phụ kiện", options=DANH_SACH_PHU_KIEN),
                "Vị trí": st.column_config.SelectboxColumn("Vị trí", options=DANH_SACH_VI_TRI),
                "Độ dài ghép được (m)": st.column_config.NumberColumn("Độ dài ghép được (m)", format="%.2f"),
                "Trạng thái": st.column_config.SelectboxColumn(
                    "Trạng thái", 
                    options=DANH_SACH_TRANG_THAI_PK,
                    help="🔴 Chưa xử lý | 🟢 Đã xử lý | 🟡 Đã xả"
                )
            },
            width='stretch',
            key="editor_pk"
        )

        col_pk_btn1, col_pk_btn2 = st.columns([3, 7])
        with col_pk_btn1:
            if st.button("💾 Lưu thay đổi trên bảng Phụ kiện", type="primary", key="btn_save_pk"):
                with engine.connect() as conn:
                    for idx, r in edited_pk.iterrows():
                        row_id_pk = int(r["id"])
                        ng_ghep_val = None
                        if r["Ngày ghép"] and str(r["Ngày ghép"]).strip() != "" and str(r["Ngày ghép"]) != "-":
                            try:
                                ng_ghep_val = datetime.datetime.strptime(str(r["Ngày ghép"]).strip()[:10], "%Y-%m-%d").date()
                            except Exception:
                                ng_ghep_val = None
                                
                        nl_pk_val = safe_date(r["Ngày lỗi"])
                        sl_pk_val = safe_float(r["Dài 1 tấm (m)"], 0.0)
                        cs_pk_val = safe_int(r["Số tấm còn"], 0)
                        ul_pk_val = safe_float(r["Độ dài ghép được (m)"], sl_pk_val)
                        m_moi = float(sl_pk_val * cs_pk_val)
                        tt_clean = safe_str(r["Trạng thái"]).replace("🔴 ", "").replace("🟢 ", "").replace("🟡 ", "").replace("🟠 ", "")
                        
                        conn.execute(text("""
                            UPDATE accessory_inventory 
                            SET ngay_loi = :nl,
                                source_warehouse = :wh,
                                customer_name = :cust,
                                vi_tri_de = :vt,
                                order_code = :oc,
                                accessory_type = :at,
                                brand = :br,
                                kho_phu_kien = :kpk,
                                thickness = :th,
                                color = :co,
                                sheet_length = :sl,
                                current_sheets = :cs,
                                total_meters = :tm,
                                usable_length = :ul,
                                trang_thai = :tt,
                                don_da_ghep = :dg,
                                nguoi_ghep = :ng,
                                ngay_ghep = :ngp,
                                reason = :re,
                                fault_by = :fb
                            WHERE id = :id
                        """), {
                            "nl": nl_pk_val, "wh": safe_str(r["Kho"], "Kho hàng lỗi NM"), "cust": safe_str(r["Khách Hàng/Đại Lý"]), 
                            "vt": safe_str(r["Vị trí"], "KV_PK"), "oc": safe_str(r["Mã đơn"], "Không có"), 
                            "at": safe_str(r["Loại phụ kiện"], "Máng"), "br": safe_str(r["Tên phụ kiện"]), 
                            "kpk": safe_str(r["Khổ PK"]), "th": safe_float(r["Dày (mm)"], 0.40), 
                            "co": safe_str(r["Màu"]), "sl": sl_pk_val, "cs": cs_pk_val, 
                            "tm": m_moi, "ul": ul_pk_val, "tt": tt_clean, "dg": safe_str(r["Đơn đã ghép"]), 
                            "ng": safe_str(r["Người ghép"]), "ngp": ng_ghep_val,
                            "re": safe_str(r["Nguyên nhân"]), "fb": safe_str(r["Lỗi do ai"]), 
                            "id": row_id_pk
                        })
                    conn.commit()
                st.cache_data.clear()
                st.session_state.msg_success = "Đã lưu toàn bộ thay đổi bảng Phụ kiện thành công!"
                st.rerun()

        if st.session_state.user and st.session_state.user['role'] == 'admin' and not df_pk.empty:
            with st.expander("🗑️ Xóa dòng Phụ kiện bị nhập sai"):
                c_del_pk1, c_del_pk2 = st.columns([3, 2])
                with c_del_pk1:
                    id_del_pk = st.selectbox("Chọn ID Phụ kiện cần xóa:", df_pk['id'].tolist(), key="del_pk_sel")
                with c_del_pk2:
                    st.write("")
                    st.write("")
                    if st.button("❌ Xóa dòng này", key="btn_del_pk"):
                        with engine.connect() as conn:
                            conn.execute(text("DELETE FROM accessory_inventory WHERE id = :id"), {"id": int(id_del_pk)})
                            conn.commit()
                        st.cache_data.clear()
                        st.session_state.msg_success = f"Đã xóa vĩnh viễn dòng Phụ kiện ID {id_del_pk}!"
                        st.rerun()

    # 1.3 TỒN KHO PANEL
    with tab_pn:
        st.subheader("🧱 Danh mục Panel lỗi tồn kho")
        df_pn = load_panel_data()

        edited_pn = st.data_editor(
            df_pn,
            disabled=["id"],
            column_config={
                "Kho": st.column_config.SelectboxColumn("Kho", options=["Kho hàng lỗi NM", "Kho hàng lỗi trả về"]),
                "Vị trí": st.column_config.SelectboxColumn("Vị trí", options=DANH_SACH_VI_TRI),
                "Độ dày Panel": st.column_config.SelectboxColumn("Độ dày Panel", options=DANH_SACH_DO_DAY_PANEL),
                "Khổ tôn": st.column_config.SelectboxColumn("Khổ tôn", options=DANH_SACH_KHO_PANEL),
                "Màu": st.column_config.SelectboxColumn("Màu", options=DANH_SACH_MAU_PANEL),
                "Quy cách xốp": st.column_config.SelectboxColumn("Quy cách xốp", options=DANH_SACH_XOP_PANEL),
                "Phế (m)": st.column_config.NumberColumn("Phế (m)", format="%.2f"),
                "Độ dài ghép được (m)": st.column_config.NumberColumn("Độ dài ghép được (m)", format="%.2f"),
                "Hàng đã xử lý ghép": st.column_config.SelectboxColumn(
                    "Hàng đã xử lý ghép", 
                    options=DANH_SACH_TRANG_THAI_TON_PANEL,
                    help="🔴 Chưa ghép | 🟢 Đã ghép (phải có Đơn hàng ghép đi cùng)"
                )
            },
            width='stretch',
            key="editor_pn"
        )

        col_pn_btn1, col_pn_btn2 = st.columns([3, 7])
        with col_pn_btn1:
            if st.button("💾 Lưu thay đổi trên bảng Panel", type="primary", key="btn_save_pn"):
                co_loi_chua_dien_don_pn = False
                for idx, r in edited_pn.iterrows():
                    if "Đã ghép" in str(r["Hàng đã xử lý ghép"]) and not str(r["Đơn hàng ghép"]).strip():
                        co_loi_chua_dien_don_pn = True
                        st.error(f"⚠️ Dòng Panel ID {r['id']}: Đã chọn '🟢 Đã ghép' thì bắt buộc phải nhập ô 'Đơn hàng ghép'!")
                        break

                if not co_loi_chua_dien_don_pn:
                    with engine.connect() as conn:
                        for idx, r in edited_pn.iterrows():
                            row_id_pn = int(r["id"])
                            rm_pn_val = safe_float(r["Còn lại mét tồn kho"], 0.0)
                            phe_pn_val = safe_float(r["Phế (m)"], 0.0)
                            he_so_panel = 1.02 if "1020" in str(r["Khổ tôn"]) else 1.17
                            m2_moi = float(rm_pn_val * he_so_panel)
                            nl_pn_val = safe_date(r["Ngày lỗi"])
                            tt_pn_luu = "Đã ghép" if "Đã ghép" in str(r["Hàng đã xử lý ghép"]) else "Chưa ghép"
                            sl_pn_val = safe_float(r["Dài 1 tấm (m)"], 0.0)
                            cs_pn_val = safe_int(r["Số tấm còn"], 0)
                            ul_pn_val = safe_float(r["Độ dài ghép được (m)"], sl_pn_val)
                            tm_pn_val = float(sl_pn_val * cs_pn_val)
                            
                            conn.execute(text("""
                                UPDATE panel_inventory 
                                SET ngay_loi = :nl,
                                    source_warehouse = :wh,
                                    vi_tri_de = :vt,
                                    order_code = :oc,
                                    brand = :br,
                                    steel_thickness = :st,
                                    color = :co,
                                    core_thickness = :ct,
                                    kho_ton = :kt,
                                    foam_type = :fo,
                                    sheet_length = :sl,
                                    current_sheets = :cs,
                                    remaining_meters = :rm,
                                    scrap_meters = :sm,
                                    usable_length = :ul,
                                    total_meters = :tm,
                                    total_area_m2 = :ta,
                                    is_matched = :im,
                                    reason = :re,
                                    fault_by = :fb,
                                    matched_order_code = :moc,
                                    matched_by_user = :mbu,
                                    matched_length = :ml,
                                    matched_sheets = :ms
                                WHERE id = :id
                            """), {
                                "nl": nl_pn_val, "wh": safe_str(r["Kho"], "Kho hàng lỗi NM"), 
                                "vt": safe_str(r["Vị trí"], "KV_Panel"), "oc": safe_str(r["Mã đơn"], "Không có"),
                                "br": safe_str(r["Hãng tôn"]), "st": safe_float(r["Dày tôn (mm)"], 0.40), 
                                "co": safe_str(r["Màu"]), "ct": safe_str(r["Độ dày Panel"], "5cm (50mm)"),
                                "kt": safe_str(r["Khổ tôn"], "Khổ nhỏ 1020mm"), "fo": safe_str(r["Quy cách xốp"], "Xốp thường"), 
                                "sl": sl_pn_val, "cs": cs_pn_val, "rm": rm_pn_val, "sm": phe_pn_val, "ul": ul_pn_val,
                                "tm": tm_pn_val, "ta": m2_moi, "im": tt_pn_luu, "re": safe_str(r["Nguyên nhân"]), 
                                "fb": safe_str(r["Lỗi do ai"]), "moc": safe_str(r["Đơn hàng ghép"]), 
                                "mbu": safe_str(r["Ai là người ghép"]), "ml": safe_float(r["Ghép sang kích thước (m)"], 0.0), 
                                "ms": safe_int(r["Số lượng tấm ghép"], 0), "id": row_id_pn
                            })
                        conn.commit()
                    st.cache_data.clear()
                    st.session_state.msg_success = "Đã lưu toàn bộ thay đổi bảng Panel thành công!"
                    st.rerun()

        if st.session_state.user and st.session_state.user['role'] == 'admin' and not df_pn.empty:
            with st.expander("🗑️ Xóa dòng Panel bị nhập sai"):
                c_del_pn1, c_del_pn2 = st.columns([3, 2])
                with c_del_pn1:
                    id_del_pn = st.selectbox("Chọn ID Panel cần xóa:", df_pn['id'].tolist(), key="del_pn_sel")
                with c_del_pn2:
                    st.write("")
                    st.write("")
                    if st.button("❌ Xóa dòng này", key="btn_del_pn"):
                        with engine.connect() as conn:
                            conn.execute(text("DELETE FROM panel_inventory WHERE id = :id"), {"id": int(id_del_pn)})
                            conn.commit()
                        st.cache_data.clear()
                        st.session_state.msg_success = f"Đã xóa vĩnh viễn dòng Panel ID {id_del_pn}!"
                        st.rerun()

# =============================================================
# 2. ➕ NHẬP LỖI TÔN (HỖ TRỢ NHIỀU KÍCH THƯỚC & ĐỘ DÀI GHÉP ĐƯỢC)
# =============================================================
elif lua_chon == "➕ Nhập lỗi Tôn":
    st.title("➕ Nhập hàng lỗi phát sinh cho Tôn")
    
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        ngay_loi_ton = st.date_input("Ngày phát sinh lỗi", datetime.date.today(), key="nl_ton_date")
        kho_ton = st.selectbox("Kho lưu", ["Kho hàng lỗi NM", "Kho hàng lỗi trả về"], key="wh_ton_sel")
        don_ton = st.text_input("Mã đơn hàng (không có thì bỏ trống)", key="oc_ton_txt").strip()
        vi_tri_ton = st.selectbox("Vị trí để", DANH_SACH_VI_TRI, key="vt_ton_sel")
    with col_b:
        hang_ton = st.selectbox("Hãng tôn *", DANH_SACH_HANG_TON, key="br_ton_sel")
        hang_khac_ton = st.text_input("Nhập hãng khác (nếu chọn 'Khác')", key="br_ton_other").strip() if hang_ton == "Khác" else ""
        mau_ton = st.text_input("Màu sắc *", key="co_ton_txt").strip()
        day_ton = st.number_input("Độ dày (dem/mm)", value=0.40, step=0.05, key="th_ton_num")
        song_ton = st.selectbox("Loại sóng", DANH_SACH_SONG, key="cr_ton_sel")
    with col_c:
        loai_ton = st.selectbox("Loại tôn", DANH_SACH_LOAI_TON, key="tt_ton_sel")
        quy_cach_xop = st.selectbox("Quy cách xốp / ngói", DANH_SACH_XOP, key="fo_ton_sel")
        loi_ai_ton = st.text_input("Lỗi do ai (Tên NV / Tổ máy)", key="fb_ton_txt").strip()
        ly_do_chon_ton = st.selectbox("Nguyên nhân lỗi", DANH_SACH_NGUYEN_NHAN_CHUNG, key="re_ton_sel")
        ly_do_chi_tiet_ton = st.text_area("Ghi chú chi tiết", key="re_ton_note") if ly_do_chon_ton == "Lỗi khác" else ""

    st.markdown("---")
    st.markdown("#### 📏 DANH SÁCH QUY CÁCH KÍCH THƯỚC TẤM")
    
    col_btn_spec1, col_btn_spec2 = st.columns([3, 7])
    with col_btn_spec1:
        if st.button("➕ Thêm quy cách kích thước (Add)", key="btn_add_spec_ton"):
            st.session_state.num_specs_ton += 1
            st.rerun()
    with col_btn_spec2:
        if st.session_state.num_specs_ton > 1:
            if st.button("➖ Bớt dòng", key="btn_del_spec_ton"):
                st.session_state.num_specs_ton -= 1
                st.rerun()

    specs_ton_data = []
    for i in range(st.session_state.num_specs_ton):
        st.write(f"**Quy cách {i+1}:**")
        if kho_ton == "Kho hàng lỗi trả về":
            c_sp1, c_sp2, c_sp3 = st.columns(3)
            with c_sp1:
                d_val = st.number_input(f"Độ dài 1 tấm (m) #{i+1} *", value=6.0, step=0.1, key=f"ton_len_{i}")
            with c_sp2:
                u_val = st.number_input(f"Độ dài ghép được (m) #{i+1} *", value=d_val, step=0.1, key=f"ton_ulen_{i}")
            with c_sp3:
                q_val = st.number_input(f"Số tấm #{i+1} *", value=5, min_value=1, step=1, key=f"ton_qty_{i}")
            specs_ton_data.append((d_val, q_val, u_val))
        else:
            c_sp1, c_sp2 = st.columns(2)
            with c_sp1:
                d_val = st.number_input(f"Độ dài 1 tấm (m) #{i+1} *", value=6.0, step=0.1, key=f"ton_len_{i}")
            with c_sp2:
                q_val = st.number_input(f"Số tấm #{i+1} *", value=5, min_value=1, step=1, key=f"ton_qty_{i}")
            specs_ton_data.append((d_val, q_val, d_val))

    st.write("")
    if st.button("💾 Lưu tôn lỗi vào kho", type="primary", key="btn_save_ton_all"):
        hang_luu = hang_khac_ton if hang_ton == "Khác" and hang_khac_ton else hang_ton
        if not hang_luu or not mau_ton:
            st.warning("⚠️ Vui lòng điền đủ: Hãng tôn và Màu sắc!")
        else:
            ma_don_luu = don_ton if don_ton else "Không có"
            nguyen_nhan_luu = f"Lỗi khác: {ly_do_chi_tiet_ton.strip()}" if ly_do_chon_ton == "Lỗi khác" else ly_do_chon_ton
            
            with engine.connect() as conn:
                for d_v, q_v, u_v in specs_ton_data:
                    d_float = safe_float(d_v)
                    q_int = safe_int(q_v)
                    u_float = safe_float(u_v, d_float)
                    t_meters = float(d_float * q_int)
                    
                    conn.execute(text("""
                    INSERT INTO inventory (ngay_loi, source_warehouse, order_code, vi_tri_de, brand, thickness, color, 
                                           corrugation_type, ton_type, foam_type, sheet_length, usable_length,
                                           current_sheets, total_meters, remaining_meters, scrap_meters, is_matched, reason, fault_by)
                    VALUES (:nl, :wh, :oc, :vt, :br, :th, :co, :cr, :tt, :fo, :sl, :ul, :cs, :tm, :rm, 0.0, 'Chưa ghép', :re, :fb)
                    """), {
                        "nl": safe_date(ngay_loi_ton), "wh": safe_str(kho_ton), "oc": ma_don_luu, "vt": safe_str(vi_tri_ton), 
                        "br": safe_str(hang_luu), "th": safe_float(day_ton), "co": safe_str(mau_ton), "cr": safe_str(song_ton), 
                        "tt": safe_str(loai_ton), "fo": safe_str(quy_cach_xop), "sl": d_float, "ul": u_float, "cs": q_int, 
                        "tm": t_meters, "rm": t_meters, "re": safe_str(nguyen_nhan_luu), "fb": safe_str(loi_ai_ton)
                    })
                conn.commit()
            st.cache_data.clear()
            st.session_state.num_specs_ton = 1
            st.session_state.msg_success = f"✅ Đã lưu thành công {len(specs_ton_data)} quy cách lô Tôn {hang_luu} - Màu {mau_ton} vào kho!"
            st.rerun()

# =============================================================
# 3. ➕ NHẬP LỖI PHỤ KIỆN (HỖ TRỢ NHIỀU KÍCH THƯỚC & ĐỘ DÀI GHÉP ĐƯỢC)
# =============================================================
elif lua_chon == "➕ Nhập lỗi Phụ kiện":
    st.title("➕ Nhập hàng lỗi cho Phụ kiện (Máng, Sườn, Xối, Nóc)")
    
    col_p1, col_p2, col_p3 = st.columns(3)
    with col_p1:
        ngay_loi_pk = st.date_input("Ngày phát sinh lỗi", datetime.date.today(), key="pk_ngay")
        pk_kho = st.selectbox("Kho lưu", ["Kho hàng lỗi NM", "Kho hàng lỗi trả về"], key="pk_kho")
        pk_customer = st.text_input("🏢 Tên Khách Hàng / Đại Lý (nếu là hàng trả về)", key="pk_customer").strip()
        pk_don = st.text_input("Mã đơn hàng (không có thì bỏ trống)", key="pk_don").strip()
        pk_loai = st.selectbox("Loại phụ kiện", DANH_SACH_PHU_KIEN, key="pk_loai")
        pk_vi_tri = st.selectbox("Vị trí để", DANH_SACH_VI_TRI, key="pk_vt")

    with col_p2:
        pk_ten = st.text_input("Tên phụ kiện *", placeholder="Ví dụ: Máng xối Inox 304, Diềm sườn ngói...", key="pk_ten").strip()
        pk_kho_phukien = st.text_input("Khổ Phụ Kiện", placeholder="Ví dụ: Khổ 300, Khổ 400, Khổ 600...", key="pk_kho_pk").strip()
        pk_mau = st.text_input("Màu sắc *", key="pk_mau").strip()
        pk_day = st.number_input("Độ dày tôn (dem/mm)", value=0.40, step=0.05, key="pk_day")

    with col_p3:
        pk_loi_ai = st.text_input("Lỗi do ai (Tên NV / Tổ chấn)", key="pk_loi_ai").strip()
        pk_ly_do_chon = st.selectbox("Nguyên nhân lỗi", DANH_SACH_NGUYEN_NHAN_CHUNG, key="pk_nn")
        pk_ly_do_chi_tiet = st.text_area("Ghi chú chi tiết", key="pk_note") if pk_ly_do_chon == "Lỗi khác" else ""

    st.markdown("---")
    st.markdown("#### 📏 DANH SÁCH QUY CÁCH KÍCH THƯỚC PHỤ KIỆN")
    
    col_btn_pk1, col_btn_pk2 = st.columns([3, 7])
    with col_btn_pk1:
        if st.button("➕ Thêm quy cách kích thước (Add)", key="btn_add_spec_pk"):
            st.session_state.num_specs_pk += 1
            st.rerun()
    with col_btn_pk2:
        if st.session_state.num_specs_pk > 1:
            if st.button("➖ Bớt dòng", key="btn_del_spec_pk"):
                st.session_state.num_specs_pk -= 1
                st.rerun()

    specs_pk_data = []
    for i in range(st.session_state.num_specs_pk):
        st.write(f"**Quy cách {i+1}:**")
        if pk_kho == "Kho hàng lỗi trả về":
            c_sp1, c_sp2, c_sp3 = st.columns(3)
            with c_sp1:
                d_val = st.number_input(f"Chiều dài 1 tấm (m) #{i+1} *", value=2.0, step=0.1, key=f"pk_len_{i}")
            with c_sp2:
                u_val = st.number_input(f"Độ dài ghép được (m) #{i+1} *", value=d_val, step=0.1, key=f"pk_ulen_{i}")
            with c_sp3:
                q_val = st.number_input(f"Số tấm (cái) #{i+1} *", value=5, min_value=1, step=1, key=f"pk_qty_{i}")
            specs_pk_data.append((d_val, q_val, u_val))
        else:
            c_sp1, c_sp2 = st.columns(2)
            with c_sp1:
                d_val = st.number_input(f"Chiều dài 1 tấm (m) #{i+1} *", value=2.0, step=0.1, key=f"pk_len_{i}")
            with c_sp2:
                q_val = st.number_input(f"Số tấm (cái) #{i+1} *", value=5, min_value=1, step=1, key=f"pk_qty_{i}")
            specs_pk_data.append((d_val, q_val, d_val))

    st.markdown("---")
    st.markdown("#### ⚡ Trạng thái xử lý")
    trang_thai_chon_pk = st.selectbox("Chọn trạng thái phụ kiện:", DANH_SACH_TRANG_THAI_PK, index=0, key="pk_tt_init")
    c_xl1, c_xl2, c_xl3 = st.columns(3)
    with c_xl1:
        don_xu_ly = st.text_input("Nhập đơn hàng được ghép (nếu đã xử lý)", key="pk_don_ghep_input").strip()
    with c_xl2:
        nv_ghep_pk = st.text_input("Tên NV ghép", value=st.session_state.user['name'] if st.session_state.user else "", key="pk_nv_ghep_input").strip()
    with c_xl3:
        ngay_ghep_pk = st.date_input("Ngày ghép", datetime.date.today(), key="pk_ngay_ghep_input")

    st.write("")
    if st.button("💾 Lưu phụ kiện vào kho", type="primary", key="btn_save_pk_all"):
        if not pk_ten or not pk_mau:
            st.warning("⚠️ Vui lòng điền đủ: Tên phụ kiện và Màu sắc!")
        elif pk_kho == "Kho hàng lỗi trả về" and not pk_customer:
            st.warning("⚠️ Đã chọn Kho lỗi trả về, vui lòng điền Tên Khách Hàng / Đại Lý!")
        elif "Đã xử lý" in trang_thai_chon_pk and (not don_xu_ly or not nv_ghep_pk):
            st.warning("⚠️ Chọn 'Đã xử lý' thì bắt buộc điền: Đơn hàng được ghép và Tên NV ghép!")
        else:
            ma_pk_luu = pk_don if pk_don else "Không có"
            tt_clean = trang_thai_chon_pk.replace("🔴 ", "").replace("🟢 ", "").replace("🟡 ", "").replace("🟠 ", "")
            pk_nguyen_nhan_luu = f"Lỗi khác: {pk_ly_do_chi_tiet.strip()}" if pk_ly_do_chon == "Lỗi khác" else pk_ly_do_chon
            
            with engine.connect() as conn:
                for d_v, q_v, u_v in specs_pk_data:
                    pk_dai_val = safe_float(d_v)
                    pk_so_tam_val = safe_int(q_v)
                    pk_ulen_val = safe_float(u_v, pk_dai_val)
                    pk_tong_met = float(pk_dai_val * pk_so_tam_val)
                    so_tam_con = 0 if "Đã xử lý" in trang_thai_chon_pk else pk_so_tam_val
                    so_met_con = 0.0 if "Đã xử lý" in trang_thai_chon_pk else pk_tong_met

                    res_pk = conn.execute(text("""
                    INSERT INTO accessory_inventory (ngay_loi, source_warehouse, customer_name, vi_tri_de, order_code, 
                                                     accessory_type, brand, kho_phu_kien, thickness, color, sheet_length, usable_length,
                                                     current_sheets, total_meters, trang_thai, don_da_ghep, nguoi_ghep, 
                                                     ngay_ghep, reason, fault_by)
                    VALUES (:nl, :wh, :cust, :vt, :oc, :at, :br, :kpk, :th, :co, :sl, :ul, :cs, :tm, :tt, :dg, :ng, :ngp, :re, :fb)
                    RETURNING id
                    """), {
                        "nl": safe_date(ngay_loi_pk), "wh": safe_str(pk_kho), "cust": safe_str(pk_customer), "vt": safe_str(pk_vi_tri), 
                        "oc": ma_pk_luu, "at": safe_str(pk_loai), "br": safe_str(pk_ten), "kpk": safe_str(pk_kho_phukien), 
                        "th": safe_float(pk_day), "co": safe_str(pk_mau), "sl": pk_dai_val, "ul": pk_ulen_val, "cs": so_tam_con, 
                        "tm": so_met_con, "tt": tt_clean, "dg": safe_str(don_xu_ly) if "Đã xử lý" in trang_thai_chon_pk else None,
                        "ng": safe_str(nv_ghep_pk) if "Đã xử lý" in trang_thai_chon_pk else None, 
                        "ngp": safe_date(ngay_ghep_pk) if "Đã xử lý" in trang_thai_chon_pk else None,
                        "re": safe_str(pk_nguyen_nhan_luu), "fb": safe_str(pk_loi_ai)
                    })
                    new_pk_id = res_pk.scalar()
                    
                    if "Đã xử lý" in trang_thai_chon_pk:
                        conn.execute(text("""
                        INSERT INTO accessory_matching_history (accessory_id, new_order_code, matched_sheets, matched_meters, matched_by, matched_date)
                        VALUES (:aid, :od, :ms, :mm, :mb, :md)
                        """), {
                            "aid": int(new_pk_id), "od": safe_str(don_xu_ly), "ms": pk_so_tam_val, "mm": pk_tong_met, 
                            "mb": safe_str(nv_ghep_pk), "md": safe_date(ngay_ghep_pk)
                        })
                conn.commit()
            st.cache_data.clear()
            st.session_state.num_specs_pk = 1
            st.session_state.msg_success = f"✅ Đã lưu thành công {len(specs_pk_data)} quy cách phụ kiện {pk_ten} vào hệ thống!"
            st.rerun()

# =============================================================
# 4. ➕ NHẬP LỖI PANEL (HỖ TRỢ NHIỀU KÍCH THƯỚC & ĐỘ DÀI GHÉP ĐƯỢC)
# =============================================================
elif lua_chon == "➕ Nhập lỗi Panel":
    st.title("➕ Nhập hàng lỗi phát sinh cho Panel")
    
    col_pn1, col_pn2, col_pn3 = st.columns(3)
    with col_pn1:
        ngay_loi_pn = st.date_input("Ngày phát sinh lỗi", datetime.date.today(), key="pn_ngay")
        pn_kho = st.selectbox("Kho lưu", ["Kho hàng lỗi NM", "Kho hàng lỗi trả về"], key="pn_kho")
        pn_don = st.text_input("Mã đơn hàng (không có thì bỏ trống)", key="pn_don").strip()
        vi_tri_pn = st.selectbox("Vị trí để", DANH_SACH_VI_TRI, key="pn_vt")
    with col_pn2:
        pn_hang = st.text_input("Hãng tôn mặt ngoài *", key="pn_hang").strip()
        pn_day_ton = st.number_input("Độ dày tôn mặt ngoài (dem/mm) *", value=0.40, step=0.05, key="pn_day_ton")
        pn_mau = st.selectbox("Màu sắc tôn mặt", DANH_SACH_MAU_PANEL, key="pn_mau")
        pn_core = st.selectbox("Độ dày Panel", DANH_SACH_DO_DAY_PANEL, key="pn_core")
        pn_kho_ton = st.selectbox("Khổ tôn Panel", DANH_SACH_KHO_PANEL, key="pn_kho_ton")
    with col_pn3:
        pn_xop_quy_cach = st.selectbox("Quy cách xốp lõi", DANH_SACH_XOP_PANEL, key="pn_xop")
        pn_loi_ai = st.text_input("Lỗi do ai (Tên NV / Tổ ép panel)", key="pn_loi_ai").strip()
        pn_ly_do_chon = st.selectbox("Nguyên nhân lỗi", DANH_SACH_NGUYEN_NHAN_PANEL, key="pn_nn")
        
        pn_ly_do_chi_tiet = ""
        if pn_ly_do_chon == "Lỗi khác":
            pn_ly_do_chi_tiet = st.text_area("Nhập chi tiết lỗi khác *", placeholder="Ghi rõ mô tả lỗi tại đây...", key="pn_note")

    st.markdown("---")
    st.markdown("#### 📏 DANH SÁCH QUY CÁCH KÍCH THƯỚC PANEL")
    
    col_btn_pn1, col_btn_pn2 = st.columns([3, 7])
    with col_btn_pn1:
        if st.button("➕ Thêm quy cách kích thước (Add)", key="btn_add_spec_pn"):
            st.session_state.num_specs_pn += 1
            st.rerun()
    with col_btn_pn2:
        if st.session_state.num_specs_pn > 1:
            if st.button("➖ Bớt dòng", key="btn_del_spec_pn"):
                st.session_state.num_specs_pn -= 1
                st.rerun()

    specs_pn_data = []
    for i in range(st.session_state.num_specs_pn):
        st.write(f"**Quy cách {i+1}:**")
        if pn_kho == "Kho hàng lỗi trả về":
            c_sp1, c_sp2, c_sp3 = st.columns(3)
            with c_sp1:
                d_val = st.number_input(f"Chiều dài 1 tấm (m) #{i+1} *", value=5.0, step=0.1, key=f"pn_len_{i}")
            with c_sp2:
                u_val = st.number_input(f"Độ dài ghép được (m) #{i+1} *", value=d_val, step=0.1, key=f"pn_ulen_{i}")
            with c_sp3:
                q_val = st.number_input(f"Số tấm #{i+1} *", value=4, min_value=1, step=1, key=f"pn_qty_{i}")
            specs_pn_data.append((d_val, q_val, u_val))
        else:
            c_sp1, c_sp2 = st.columns(2)
            with c_sp1:
                d_val = st.number_input(f"Chiều dài 1 tấm (m) #{i+1} *", value=5.0, step=0.1, key=f"pn_len_{i}")
            with c_sp2:
                q_val = st.number_input(f"Số tấm #{i+1} *", value=4, min_value=1, step=1, key=f"pn_qty_{i}")
            specs_pn_data.append((d_val, q_val, d_val))

    st.write("")
    if st.button("💾 Lưu tấm Panel lỗi vào kho", type="primary", key="btn_save_pn_all"):
        if not pn_hang:
            st.warning("⚠️ Vui lòng điền Hãng tôn mặt ngoài!")
        elif pn_ly_do_chon == "Lỗi khác" and not pn_ly_do_chi_tiet.strip():
            st.warning("⚠️ Đã chọn 'Lỗi khác', vui lòng điền chi tiết lỗi vào ô nhập tay!")
        else:
            he_so_rong = 1.02 if "1020" in pn_kho_ton else 1.17
            ma_pn_luu = pn_don if pn_don else "Không có"
            pn_nguyen_nhan_luu = f"Lỗi khác: {pn_ly_do_chi_tiet.strip()}" if pn_ly_do_chon == "Lỗi khác" else pn_ly_do_chon
            
            with engine.connect() as conn:
                for d_v, q_v, u_v in specs_pn_data:
                    pn_dai_val = safe_float(d_v)
                    pn_so_tam_val = safe_int(q_v)
                    pn_ulen_val = safe_float(u_v, pn_dai_val)
                    pn_tong_m = float(pn_dai_val * pn_so_tam_val)
                    pn_tong_m2 = float(pn_tong_m * he_so_rong)
                    
                    conn.execute(text("""
                    INSERT INTO panel_inventory (ngay_loi, source_warehouse, vi_tri_de, order_code, brand, steel_thickness, color, 
                                                 core_thickness, kho_ton, foam_type, sheet_length, usable_length,
                                                 current_sheets, total_meters, remaining_meters, scrap_meters, total_area_m2, 
                                                 is_matched, reason, fault_by)
                    VALUES (:nl, :wh, :vt, :oc, :br, :st, :co, :ct, :kt, :fo, :sl, :ul, :cs, :tm, :rm, 0.0, :ta, 'Chưa ghép', :re, :fb)
                    """), {
                        "nl": safe_date(ngay_loi_pn), "wh": safe_str(pn_kho), "vt": safe_str(vi_tri_pn), "oc": ma_pn_luu, 
                        "br": safe_str(pn_hang), "st": safe_float(pn_day_ton), "co": safe_str(pn_mau), 
                        "ct": safe_str(pn_core), "kt": safe_str(pn_kho_ton), "fo": safe_str(pn_xop_quy_cach), 
                        "sl": pn_dai_val, "ul": pn_ulen_val, "cs": pn_so_tam_val, "tm": pn_tong_m, "rm": pn_tong_m, "ta": pn_tong_m2, 
                        "re": safe_str(pn_nguyen_nhan_luu), "fb": safe_str(pn_loi_ai)
                    })
                conn.commit()
            st.cache_data.clear()
            st.session_state.num_specs_pn = 1
            st.session_state.msg_success = f"✅ Đã lưu thành công {len(specs_pn_data)} quy cách tấm Panel {pn_hang} - Màu {pn_mau} vào kho!"
            st.rerun()

# =============================================================
# 5. ✂️ TÌM KIẾM & GHÉP ĐƠN
# =============================================================
elif lua_chon == "✂️ Tìm kiếm & Ghép đơn":
    tab_ghep_ton, tab_ghep_pk, tab_ghep_pn = st.tabs(["✂️ Ghép Tôn tấm", "🛠️ Xuất / Ghép Phụ kiện", "🧱 Xuất / Ghép Panel"])
    
    # 5.1 GHÉP TÔN TẤM
    with tab_ghep_ton:
        st.subheader("✂️ Tìm kiếm thông minh ghép Tôn mới")
        XOP_RANKS = {"Không xốp": 0, "Xốp Eco": 1, "Xốp G8": 2, "Xốp G7": 3, "Xốp G*": 4, "Ngói N8": 1, "Ngói N*": 2}

        with st.form("form_tim_kiem_ton"):
            c1, c2, c3 = st.columns(3)
            with c1:
                s_hang = st.selectbox("Hãng tôn", ["Tất cả"] + DANH_SACH_HANG_TON, key="gt_hang")
                s_mau = st.text_input("Màu sắc cần (đen, xanh, đỏ...)", key="gt_mau").strip()
                s_day = st.number_input("Độ dày yêu cầu (dem/mm)", value=0.35, step=0.05, key="gt_day")
            with c2:
                s_song = st.selectbox("Loại sóng", ["Tất cả"] + DANH_SACH_SONG, key="gt_song")
                s_ton = st.selectbox("Loại tôn", ["Tất cả"] + DANH_SACH_LOAI_TON, key="gt_ton")
                s_xop = st.selectbox("Cấp xốp tối thiểu", DANH_SACH_XOP, key="gt_xop")
            with c3:
                s_dai = st.number_input("Độ dài cần cắt ghép (m)", value=2.0, step=0.1, key="gt_dai")
                st.write("")
                st.write("")
                btn_tim_ton = st.form_submit_button("🔎 Quét kho tìm tôn", type="primary")

        if btn_tim_ton:
            st.session_state.ton_search_params = {
                "hang": s_hang, "mau": s_mau, "day": s_day,
                "song": s_song, "ton": s_ton, "xop": s_xop, "dai": s_dai
            }

        if "ton_search_params" in st.session_state:
            p = st.session_state.ton_search_params
            df_all_ton = load_ton_data()
            df_all_ton = df_all_ton[df_all_ton["Số tấm còn"] > 0]

            if not df_all_ton.empty:
                # Quét dựa trên độ dài ghép được (hữu dụng)
                df_matched = df_all_ton[df_all_ton["Độ dài ghép được (m)"] >= p["dai"]].copy()
                df_matched = df_matched[df_matched["Dày (mm)"].round(2) >= round(p["day"], 2)]

                if p["hang"] != "Tất cả":
                    df_matched = df_matched[df_matched["Hãng"] == p["hang"]]
                if p["mau"]:
                    df_matched = df_matched[df_matched["Màu"].apply(lambda x: xoa_dau_tieng_viet(p["mau"]) in xoa_dau_tieng_viet(x))]
                if p["song"] != "Tất cả":
                    df_matched = df_matched[df_matched["Sóng"] == p["song"]]
                if p["ton"] != "Tất cả":
                    df_matched = df_matched[df_matched["Loại tôn"] == p["ton"]]

                if not df_matched.empty:
                    req_rank = XOP_RANKS.get(p["xop"], 0)
                    df_matched['rank'] = df_matched['Quy cách xốp/ngói'].map(lambda x: XOP_RANKS.get(x, 0))
                    df_final = df_matched[df_matched['rank'] >= req_rank].copy()

                    if not df_final.empty:
                        df_final['lech_xop'] = df_final['rank'] - req_rank
                        df_final['lech_day'] = df_final['Dày (mm)'] - p["day"]
                        df_final['du_dai'] = df_final['Độ dài ghép được (m)'] - p["dai"]
                        df_sorted = df_final.sort_values(by=['lech_xop', 'lech_day', 'du_dai']).drop(columns=['rank', 'lech_xop', 'lech_day', 'du_dai'])

                        st.success(f"🎯 Tìm thấy {len(df_sorted)} vị trí đạt chuẩn ghép:")
                        st.dataframe(df_sorted, width='stretch')

                        st.markdown("### 📝 Điền thông tin ghép đơn ngay tại đây:")
                        with st.form("form_confirm_ghep_ton_now"):
                            id_ghep = st.selectbox("Chọn ID lô tôn cần lấy ghép", df_sorted['id'].tolist())
                            r_target = df_sorted[df_sorted['id'] == id_ghep].iloc[0]
                            
                            st.write(f"Đang chọn Lô ID **{id_ghep}** | Vị trí: **{r_target['Vị trí']}** | Dài: **{r_target['Dài (m)']}m** (Ghép được: **{r_target['Độ dài ghép được (m)']}m**) | Còn: **{r_target['Số tấm còn']} tấm**")
                            
                            cg1, cg2, cg3 = st.columns(3)
                            with cg1:
                                ma_moi = st.text_input("Mã đơn mới ghép vào *").strip()
                            with cg2:
                                tam_ghep = st.number_input("Số tấm cần lấy", min_value=1, max_value=int(r_target['Số tấm còn']), value=1)
                                met_ghep = tam_ghep * p["dai"]
                                st.info(f"Tổng mét ghép: **{met_ghep:.2f} m**")
                            with cg3:
                                nguoi_ghep = st.text_input("Nhân viên ghép", value=st.session_state.user['name'] if st.session_state.user else "")

                            btn_ghep_ton = st.form_submit_button("✅ Xác nhận Ghép và Trừ kho ngay", type="primary")

                            if btn_ghep_ton:
                                if not ma_moi:
                                    st.error("Vui lòng điền mã đơn hàng mới ghép vào!")
                                else:
                                    tam_ghep_int = safe_int(tam_ghep, 1)
                                    tam_con = safe_int(r_target['Số tấm còn']) - tam_ghep_int
                                    met_con = float(tam_con * safe_float(r_target['Dài (m)']))
                                    trang_thai_moi = "Đã ghép" if tam_con == 0 else "Chưa ghép"
                                    target_ton_id = int(id_ghep)
                                    
                                    with engine.connect() as conn:
                                        conn.execute(text("""
                                            UPDATE inventory 
                                            SET current_sheets = :tc, 
                                                total_meters = :mc, 
                                                remaining_meters = :rm, 
                                                is_matched = :im, 
                                                matched_order_code = :moc, 
                                                matched_by_user = :mbu, 
                                                matched_length = :ml, 
                                                matched_sheets = :ms 
                                            WHERE id = :id
                                        """), {
                                            "tc": tam_con, "mc": met_con, "rm": met_con, "im": trang_thai_moi,
                                            "moc": safe_str(ma_moi), "mbu": safe_str(nguoi_ghep), "ml": safe_float(p["dai"]),
                                            "ms": tam_ghep_int, "id": target_ton_id
                                        })
                                        conn.execute(text("""
                                            INSERT INTO matching_history (inventory_id, new_order_code, matched_sheets, matched_length, matched_meters, matched_by, matched_date) 
                                            VALUES (:iid, :od, :ms, :ml, :mm, :mb, CURRENT_DATE)
                                        """), {
                                            "iid": target_ton_id, "od": safe_str(ma_moi), "ms": tam_ghep_int, 
                                            "ml": safe_float(p["dai"]), "mm": float(met_ghep), "mb": safe_str(nguoi_ghep)
                                        })
                                        conn.commit()
                                    st.cache_data.clear()
                                    del st.session_state.ton_search_params
                                    st.session_state.msg_success = f"✅ Đã ghép thành công {tam_ghep_int} tấm ({met_ghep:.2f}m) vào đơn {ma_moi}! Vị trí {r_target['Vị trí']} còn lại {tam_con} tấm ({met_con:.2f}m)."
                                    st.rerun()
                    else:
                        st.warning("⚠️ Có lô phù hợp kích thước nhưng cấp xốp mềm hơn yêu cầu!")
                else:
                    st.info("Không tìm thấy tấm tôn nào thỏa mãn điều kiện yêu cầu.")
            else:
                st.info("Kho hiện tại không có tôn lỗi tồn kho.")

    # 5.2 GHÉP PHỤ KIỆN
    with tab_ghep_pk:
        st.subheader("🛠️ Tìm kiếm & Xuất ghép Phụ kiện")
        with st.form("form_tim_kiem_pk"):
            cp1, cp2, cp3 = st.columns(3)
            with cp1:
                q_pk_loai = st.selectbox("Loại phụ kiện cần tìm", ["Tất cả"] + DANH_SACH_PHU_KIEN, key="q_pk_loai")
                q_pk_ten = st.text_input("Tên phụ kiện (máng, diềm, nóc...)", key="q_pk_ten").strip()
            with cp2:
                q_pk_mau = st.text_input("Màu sắc cần", key="q_pk_mau").strip()
                q_pk_day = st.number_input("Độ dày tối thiểu (dem/mm)", value=0.30, step=0.05, key="q_pk_day")
            with cp3:
                q_pk_dai = st.number_input("Chiều dài tối thiểu (m)", value=1.0, step=0.1, key="q_pk_dai")
                st.write("")
                st.write("")
                btn_tim_pk = st.form_submit_button("🔎 Quét kho tìm phụ kiện", type="primary")

        if btn_tim_pk:
            st.session_state.pk_search_params = {
                "loai": q_pk_loai, "ten": q_pk_ten, "mau": q_pk_mau, "day": q_pk_day, "dai": q_pk_dai
            }

        if "pk_search_params" in st.session_state:
            pk_p = st.session_state.pk_search_params
            df_pk_all = load_pk_data()
            df_pk_all = df_pk_all[(df_pk_all["Số tấm còn"] > 0) & (~df_pk_all["Trạng thái"].str.contains("Đã xử lý", na=False))]

            if not df_pk_all.empty:
                df_pk_matched = df_pk_all[df_pk_all["Độ dài ghép được (m)"] >= pk_p["dai"]].copy()
                df_pk_matched = df_pk_matched[df_pk_matched["Dày (mm)"].round(2) >= round(pk_p["day"], 2)]

                if pk_p["loai"] != "Tất cả":
                    df_pk_matched = df_pk_matched[df_pk_matched["Loại phụ kiện"] == pk_p["loai"]]
                if pk_p["ten"]:
                    df_pk_matched = df_pk_matched[df_pk_matched["Tên phụ kiện"].apply(lambda x: xoa_dau_tieng_viet(pk_p["ten"]) in xoa_dau_tieng_viet(x))]
                if pk_p["mau"]:
                    df_pk_matched = df_pk_matched[df_pk_matched["Màu"].apply(lambda x: xoa_dau_tieng_viet(pk_p["mau"]) in xoa_dau_tieng_viet(x))]

                if not df_pk_matched.empty:
                    st.success(f"🎯 Tìm thấy {len(df_pk_matched)} vị trí phụ kiện đủ điều kiện:")
                    st.dataframe(df_pk_matched, width='stretch')

                    st.markdown("### 📝 Điền thông tin xuất ghép Phụ kiện ngay tại đây:")
                    with st.form("form_confirm_ghep_pk_now"):
                        pk_id_chon = st.selectbox("Chọn ID phụ kiện muốn lấy", df_pk_matched['id'].tolist())
                        r_pk = df_pk_matched[df_pk_matched['id'] == pk_id_chon].iloc[0]
                        
                        g_pk1, g_pk2, g_pk3 = st.columns(3)
                        with g_pk1:
                            pk_don_moi = st.text_input("Mã đơn mới ghép vào *", key="pk_don_moi").strip()
                        with g_pk2:
                            pk_tam_lay = st.number_input("Số tấm cần lấy", min_value=1, max_value=int(r_pk['Số tấm còn']), value=1, key="pk_tam_lay")
                            pk_m_lay = pk_tam_lay * float(r_pk['Dài 1 tấm (m)'])
                            st.info(f"Tổng mét phụ kiện: **{pk_m_lay:.2f} m**")
                        with g_pk3:
                            pk_nguoi_lay = st.text_input("Nhân viên ghép", value=st.session_state.user['name'] if st.session_state.user else "", key="pk_nv_lay")
                            pk_ngay_lay = st.date_input("Ngày ghép", datetime.date.today(), key="pk_ngay_lay_search")

                        btn_ghep_pk_submit = st.form_submit_button("✅ Xác nhận Ghép và Trừ kho Phụ kiện", type="primary")

                        if btn_ghep_pk_submit:
                            if not pk_don_moi:
                                st.error("Vui lòng điền mã đơn ghép!")
                            else:
                                pk_tam_lay_int = safe_int(pk_tam_lay, 1)
                                pk_tam_con = safe_int(r_pk['Số tấm còn']) - pk_tam_lay_int
                                pk_m_con = float(pk_tam_con * safe_float(r_pk['Dài 1 tấm (m)']))
                                trang_thai_moi = "Đã xử lý" if pk_tam_con == 0 else "Chưa xử lý"
                                target_pk_id = int(pk_id_chon)
                                
                                with engine.connect() as conn:
                                    conn.execute(text("""
                                    UPDATE accessory_inventory 
                                    SET current_sheets = :tc, total_meters = :mc, trang_thai = :tt, 
                                        don_da_ghep = :dg, nguoi_ghep = :ng, ngay_ghep = :ngp 
                                    WHERE id = :id
                                    """), {
                                        "tc": pk_tam_con, "mc": pk_m_con, "tt": trang_thai_moi, 
                                        "dg": safe_str(pk_don_moi), "ng": safe_str(pk_nguoi_lay), 
                                        "ngp": safe_date(pk_ngay_lay), "id": target_pk_id
                                    })
                                    conn.execute(text("""
                                    INSERT INTO accessory_matching_history (accessory_id, new_order_code, matched_sheets, matched_meters, matched_by, matched_date) 
                                    VALUES (:aid, :od, :ms, :mm, :mb, :md)
                                    """), {
                                        "aid": target_pk_id, "od": safe_str(pk_don_moi), "ms": pk_tam_lay_int, 
                                        "mm": float(pk_m_lay), "mb": safe_str(pk_nguoi_lay), "md": safe_date(pk_ngay_lay)
                                    })
                                    conn.commit()
                                st.cache_data.clear()
                                del st.session_state.pk_search_params
                                st.session_state.msg_success = f"✅ Đã trừ thành công {pk_tam_lay_int} tấm {r_pk['Loại phụ kiện']} vào đơn {pk_don_moi}! Còn lại {pk_tam_con} tấm."
                                st.rerun()
                else:
                    st.info("Không có phụ kiện nào thỏa mãn điều kiện yêu cầu.")
            else:
                st.info("Kho hiện tại không có phụ kiện chưa xử lý.")

    # 5.3 GHÉP PANEL
    with tab_ghep_pn:
        st.subheader("🧱 Tìm kiếm & Xuất ghép Panel")
        with st.form("form_tim_kiem_pn"):
            pn_c1, pn_c2, pn_c3 = st.columns(3)
            with pn_c1:
                q_pn_hang = st.text_input("Hãng tôn mặt Panel", key="q_pn_hang").strip()
                q_pn_core = st.selectbox("Độ dày Panel", ["Tất cả"] + DANH_SACH_DO_DAY_PANEL, key="q_pn_core")
            with pn_c2:
                q_pn_mau = st.selectbox("Màu sắc tôn mặt", ["Tất cả"] + DANH_SACH_MAU_PANEL, key="q_pn_mau")
                q_pn_kho = st.selectbox("Khổ tôn yêu cầu", ["Tất cả"] + DANH_SACH_KHO_PANEL, key="q_pn_kho")
            with pn_c3:
                q_pn_dai = st.number_input("Chiều dài tối thiểu (m)", value=2.0, step=0.1, key="q_pn_dai")
                st.write("")
                st.write("")
                btn_tim_pn = st.form_submit_button("🔎 Quét kho tìm Panel", type="primary")

        if btn_tim_pn:
            st.session_state.pn_search_params = {
                "hang": q_pn_hang, "core": q_pn_core, "mau": q_pn_mau, "kho": q_pn_kho, "dai": q_pn_dai
            }

        if "pn_search_params" in st.session_state:
            pn_p = st.session_state.pn_search_params
            df_pn_all = load_panel_data()
            df_pn_all = df_pn_all[df_pn_all["Số tấm còn"] > 0]

            if not df_pn_all.empty:
                df_pn_matched = df_pn_all[df_pn_all["Độ dài ghép được (m)"] >= pn_p["dai"]].copy()
                if pn_p["hang"]:
                    df_pn_matched = df_pn_matched[df_pn_matched["Hãng tôn"].apply(lambda x: xoa_dau_tieng_viet(pn_p["hang"]) in xoa_dau_tieng_viet(x))]
                if pn_p["mau"] != "Tất cả":
                    df_pn_matched = df_pn_matched[df_pn_matched["Màu"] == pn_p["mau"]]
                if pn_p["core"] != "Tất cả":
                    df_pn_matched = df_pn_matched[df_pn_matched["Độ dày Panel"] == pn_p["core"]]
                if pn_p["kho"] != "Tất cả":
                    df_pn_matched = df_pn_matched[df_pn_matched["Khổ tôn"] == pn_p["kho"]]

                if not df_pn_matched.empty:
                    st.success(f"🎯 Tìm thấy {len(df_pn_matched)} vị trí Panel đủ điều kiện ghép:")
                    st.dataframe(df_pn_matched, width='stretch')

                    st.markdown("### 📝 Điền thông tin xuất ghép Panel ngay tại đây:")
                    with st.form("form_confirm_ghep_pn_now"):
                        pn_id_chon = st.selectbox("Chọn ID Panel muốn lấy", df_pn_matched['id'].tolist())
                        r_pn = df_pn_matched[df_pn_matched['id'] == pn_id_chon].iloc[0]
                        
                        g_pn1, g_pn2, g_pn3 = st.columns(3)
                        with g_pn1:
                            pn_don_moi = st.text_input("Mã đơn hàng ghép vào *", key="pn_don_moi").strip()
                        with g_pn2:
                            pn_tam_lay = st.number_input("Số tấm cần lấy", min_value=1, max_value=int(r_pn['Số tấm còn']), value=1, key="pn_tam_lay")
                            pn_m_lay = pn_tam_lay * float(r_pn['Dài 1 tấm (m)'])
                            he_so = 1.02 if "1020" in r_pn['Khổ tôn'] else 1.17
                            pn_m2_lay = pn_m_lay * he_so
                            st.info(f"Xuất: **{pn_m_lay:.2f} m** | Diện tích: **{pn_m2_lay:.2f} m²**")
                        with g_pn3:
                            pn_nguoi_lay = st.text_input("Nhân viên ghép", value=st.session_state.user['name'] if st.session_state.user else "", key="pn_nv_lay")

                        btn_ghep_pn_submit = st.form_submit_button("✅ Xác nhận Ghép và Trừ kho Panel", type="primary")

                        if btn_ghep_pn_submit:
                            if not pn_don_moi:
                                st.error("Vui lòng điền mã đơn hàng ghép vào!")
                            else:
                                pn_tam_lay_int = safe_int(pn_tam_lay, 1)
                                pn_tam_con = safe_int(r_pn['Số tấm còn']) - pn_tam_lay_int
                                pn_m_con = float(pn_tam_con * safe_float(r_pn['Dài 1 tấm (m)']))
                                pn_m2_con = float(pn_m_con * he_so)
                                trang_thai_pn_moi = "Đã ghép" if pn_tam_con == 0 else "Chưa ghép"
                                target_pn_id = int(pn_id_chon)
                                
                                with engine.connect() as conn:
                                    conn.execute(text("""
                                        UPDATE panel_inventory SET current_sheets = :tc, total_meters = :mc, total_area_m2 = :m2c, is_matched = :im WHERE id = :id
                                    """), {"tc": pn_tam_con, "mc": pn_m_con, "m2c": pn_m2_con, "im": trang_thai_pn_moi, "id": target_pn_id})
                                    conn.execute(text("""
                                        INSERT INTO panel_matching_history (panel_id, new_order_code, matched_sheets, matched_meters, matched_m2, matched_by) 
                                        VALUES (:pid, :od, :ms, :mm, :m2, :mb)
                                    """), {"pid": target_pn_id, "od": safe_str(pn_don_moi), "ms": pn_tam_lay_int, "mm": float(pn_m_lay), "m2": float(pn_m2_lay), "mb": safe_str(pn_nguoi_lay)})
                                    conn.commit()
                                st.cache_data.clear()
                                del st.session_state.pn_search_params
                                st.session_state.msg_success = f"✅ Đã trừ thành công {pn_tam_lay_int} tấm Panel vào đơn {pn_don_moi}! Còn lại {pn_tam_con} tấm ({pn_m2_con:.2f} m²)."
                                st.rerun()
                else:
                    st.info("Không có tấm Panel nào trong kho thỏa mãn tiêu chí.")
            else:
                st.info("Kho hiện tại không có panel lỗi tồn kho.")

# =============================================================
# 6. BÁO CÁO DASHBOARD
# =============================================================
elif lua_chon == "📊 Báo cáo Dashboard":
    st.title("📊 Báo cáo Thống kê Toàn xưởng (Tôn - Phụ kiện - Panel)")
    
    current_now = datetime.date.today()
    
    c_f_mode, c_f_month, c_f_year = st.columns([3, 3, 3])
    with c_f_mode:
        view_time_mode = st.radio("⏱️ Chế độ xem báo cáo:", ["Theo Tháng", "Theo Năm", "Theo Tuần", "Toàn bộ lịch sử"], horizontal=True, index=0)
    
    danh_sach_nam = list(range(current_now.year - 2, current_now.year + 3))
    
    if view_time_mode == "Theo Tháng":
        with c_f_month:
            selected_month = st.selectbox("📅 Chọn Tháng:", list(range(1, 13)), index=current_now.month - 1)
        with c_f_year:
            selected_year = st.selectbox("📅 Chọn Năm:", danh_sach_nam, index=danh_sach_nam.index(current_now.year))
        period_text = f"Tháng {selected_month}/{selected_year}"
        sql_time_filter = f"WHERE EXTRACT(MONTH FROM matched_date) = {selected_month} AND EXTRACT(YEAR FROM matched_date) = {selected_year}"
    elif view_time_mode == "Theo Năm":
        with c_f_month:
            st.write("")
        with c_f_year:
            selected_year = st.selectbox("📅 Chọn Năm:", danh_sach_nam, index=danh_sach_nam.index(current_now.year))
        period_text = f"Năm {selected_year}"
        sql_time_filter = f"WHERE EXTRACT(YEAR FROM matched_date) = {selected_year}"
    elif view_time_mode == "Theo Tuần":
        start_week = current_now - datetime.timedelta(days=current_now.weekday())
        period_text = f"Tuần này (từ {start_week.strftime('%d/%m/%Y')} đến nay)"
        sql_time_filter = "WHERE matched_date >= CURRENT_DATE - INTERVAL '7 days'"
    else:
        period_text = "Toàn bộ lịch sử tích lũy"
        sql_time_filter = ""

    st.caption(f"📅 Đang phân tích số liệu: **{period_text}**")

    df_ton_all = load_ton_data()
    df_pk_all = load_pk_data()
    df_pn_all = load_panel_data()
    
    df_ton_all["Ngày chuẩn"] = pd.to_datetime(df_ton_all["Ngày lỗi"], errors='coerce')
    df_pk_all["Ngày chuẩn"] = pd.to_datetime(df_pk_all["Ngày lỗi"], errors='coerce')
    df_pn_all["Ngày chuẩn"] = pd.to_datetime(df_pn_all["Ngày lỗi"], errors='coerce')

    if view_time_mode == "Theo Tháng":
        df_ton_f = df_ton_all[(df_ton_all["Ngày chuẩn"].dt.month == selected_month) & (df_ton_all["Ngày chuẩn"].dt.year == selected_year)].copy()
        df_pk_f = df_pk_all[(df_pk_all["Ngày chuẩn"].dt.month == selected_month) & (df_pk_all["Ngày chuẩn"].dt.year == selected_year)].copy()
        df_pn_f = df_pn_all[(df_pn_all["Ngày chuẩn"].dt.month == selected_month) & (df_pn_all["Ngày chuẩn"].dt.year == selected_year)].copy()
    elif view_time_mode == "Theo Năm":
        df_ton_f = df_ton_all[df_ton_all["Ngày chuẩn"].dt.year == selected_year].copy()
        df_pk_f = df_pk_all[df_pk_all["Ngày chuẩn"].dt.year == selected_year].copy()
        df_pn_f = df_pn_all[df_pn_all["Ngày chuẩn"].dt.year == selected_year].copy()
    elif view_time_mode == "Theo Tuần":
        df_ton_f = df_ton_all[df_ton_all["Ngày chuẩn"] >= pd.to_datetime(start_week)].copy()
        df_pk_f = df_pk_all[df_pk_all["Ngày chuẩn"] >= pd.to_datetime(start_week)].copy()
        df_pn_f = df_pn_all[df_pn_all["Ngày chuẩn"] >= pd.to_datetime(start_week)].copy()
    else:
        df_ton_f = df_ton_all.copy()
        df_pk_f = df_pk_all.copy()
        df_pn_f = df_pn_all.copy()

    # TÍNH TOÁN 4 CHỈ SỐ METRIC
    m_loi_ton = (df_ton_f["Dài (m)"].fillna(0) * df_ton_f["Số tấm còn"].fillna(0)) + (df_ton_f["Ghép sang kích thước (m)"].fillna(0) * df_ton_f["Số lượng tấm ghép"].fillna(0)) + df_ton_f["Phế (m)"].fillna(0)
    m_loi_pk = df_pk_f["Tổng mét"].fillna(0) if "Tổng mét" in df_pk_f.columns else pd.Series(0, index=df_pk_f.index)
    m_loi_pn = (df_pn_f["Dài 1 tấm (m)"].fillna(0) * df_pn_f["Số tấm còn"].fillna(0)) + (df_pn_f["Ghép sang kích thước (m)"].fillna(0) * df_pn_f["Số lượng tấm ghép"].fillna(0)) + df_pn_f["Phế (m)"].fillna(0)
    
    tong_m_loi = float(m_loi_ton.sum() + m_loi_pk.sum() + m_loi_pn.sum())

    tong_m_ghep = float(
        (df_ton_f["Ghép sang kích thước (m)"].fillna(0) * df_ton_f["Số lượng tấm ghép"].fillna(0)).sum() +
        (df_pn_f["Ghép sang kích thước (m)"].fillna(0) * df_pn_f["Số lượng tấm ghép"].fillna(0)).sum()
    )

    tong_m_phe = float(df_ton_f["Phế (m)"].fillna(0).sum() + df_pn_f["Phế (m)"].fillna(0).sum())

    tong_m_ton_chua_ghep = float(
        df_ton_f[df_ton_f["Hàng đã xử lý ghép"].str.contains("Chưa ghép", na=False)]["Còn lại mét tồn kho"].fillna(0).sum() +
        df_pn_f[df_pn_f["Hàng đã xử lý ghép"].str.contains("Chưa ghép", na=False)]["Còn lại mét tồn kho"].fillna(0).sum() +
        df_pk_f[df_pk_f["Trạng thái"].str.contains("Chưa xử lý", na=False)]["Tổng mét"].fillna(0).sum()
    )

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
            st.dataframe(df_top_fault, hide_index=True, use_container_width=True)
        else:
            st.info("Không có dữ liệu lỗi phát sinh trong khoảng thời gian này.")

    with c_d2:
        st.subheader(f"🏆 Top 5 người ghép được hàng nhiều nhất ({period_text})")
        with engine.connect() as conn:
            df_top_match = pd.read_sql(text(f"""
                SELECT matched_by as "Nhân viên ghép", 
                       ROUND(CAST(SUM(matched_meters) AS numeric), 2) as "Tổng mét ghép (m)", 
                       COUNT(id) as "Số lần ghép"
                FROM (
                    SELECT matched_by, matched_meters, id, matched_date FROM matching_history
                    UNION ALL
                    SELECT matched_by, matched_meters, id, matched_date FROM accessory_matching_history
                    UNION ALL
                    SELECT matched_by, matched_meters, id, matched_date FROM panel_matching_history
                ) t
                {sql_time_filter}
                GROUP BY matched_by 
                ORDER BY SUM(matched_meters) DESC
                LIMIT 5
            """), conn)
            
        if not df_top_match.empty and df_top_match["Tổng mét ghép (m)"].sum() > 0:
            df_top_match = df_top_match.reset_index(drop=True)
            df_top_match.insert(0, "STT", range(1, len(df_top_match) + 1))
            st.dataframe(df_top_match, hide_index=True, use_container_width=True)
        else:
            st.info("Không có dữ liệu ghép hàng trong khoảng thời gian này.")

# =============================================================
# 7. PHÊ DUYỆT TÀI KHOẢN (ADMIN)
# =============================================================
elif lua_chon == "👑 Phê duyệt & Cấp quyền tài khoản":
    st.title("👑 Quản trị & Phê duyệt nhân viên")
    st.subheader("⏳ Yêu cầu tài khoản đang chờ duyệt")
    with engine.connect() as conn:
        df_pending = pd.read_sql(text("SELECT id, username, full_name, role, created_at FROM users WHERE is_approved = 0"), conn)
    
    if not df_pending.empty:
        for idx, row in df_pending.iterrows():
            with st.container():
                col_u1, col_u2, col_u3, col_u4 = st.columns([2, 3, 2, 2])
                col_u1.write(f"Tài khoản: **{row['username']}**")
                col_u2.write(f"Họ tên: **{row['full_name']}**")
                assigned_role = col_u3.selectbox("Cấp quyền vai trò", ["operator", "admin"], key=f"role_{row['id']}")
                if col_u4.button("✅ Kích hoạt", key=f"btn_ap_{row['id']}"):
                    with engine.connect() as conn:
                        conn.execute(text("UPDATE users SET is_approved = 1, role = :r WHERE id = :id"), {"r": assigned_role, "id": int(row['id'])})
                        conn.commit()
                    st.cache_data.clear()
                    st.session_state.msg_success = f"Đã duyệt cấp quyền cho nhân viên {row['full_name']} thành công!"
                    st.rerun()
            st.divider()
    else:
        st.info("Hiện không có yêu cầu nào chờ phê duyệt.")

    st.subheader("👥 Danh sách nhân viên đang hoạt động")
    with engine.connect() as conn:
        df_active = pd.read_sql(text("SELECT id, username, full_name, role, created_at FROM users WHERE is_approved = 1"), conn)
    st.dataframe(df_active, width='stretch')
