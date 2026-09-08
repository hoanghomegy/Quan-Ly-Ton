import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
import bcrypt
import datetime

# --- KẾT NỐI DATABASE ĐÁM MÂY (NEON) ---
if "db_url" in st.secrets:
    DB_URL = st.secrets["db_url"]
else:
    DB_URL = "sqlite:///ton_inventory.db"

if DB_URL.startswith("postgres://"):
    DB_URL = DB_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DB_URL, pool_pre_ping=True)

# Khởi tạo các bảng trên cơ sở dữ liệu
with engine.connect() as conn:
    # 1. Bảng tài khoản
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
    
    # 2. Bảng kho Tôn lỗi
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
        reason TEXT,
        fault_by VARCHAR(100),
        created_at DATE DEFAULT CURRENT_DATE
    );
    """))
    
    # 3. Lịch sử ghép Tôn
    conn.execute(text("""
    CREATE TABLE IF NOT EXISTS matching_history (
        id SERIAL PRIMARY KEY,
        inventory_id INTEGER,
        new_order_code VARCHAR(50),
        matched_meters REAL,
        matched_by VARCHAR(100),
        matched_date DATE DEFAULT CURRENT_DATE
    );
    """))

    # 4. Bảng kho Phụ Kiện lỗi
    conn.execute(text("""
    CREATE TABLE IF NOT EXISTS accessory_inventory (
        id SERIAL PRIMARY KEY,
        ngay_loi DATE DEFAULT CURRENT_DATE,
        source_warehouse VARCHAR(50) NOT NULL,
        vi_tri_de VARCHAR(50),
        order_code VARCHAR(50),
        accessory_type VARCHAR(50) NOT NULL,
        brand VARCHAR(50),
        thickness REAL,
        color VARCHAR(50),
        sheet_length REAL,
        current_sheets INTEGER,
        total_meters REAL,
        trang_thai VARCHAR(50) DEFAULT 'Chưa xử lý',
        don_da_ghep VARCHAR(50),
        reason TEXT,
        fault_by VARCHAR(100),
        created_at DATE DEFAULT CURRENT_DATE
    );
    """))

    # 5. Lịch sử ghép Phụ kiện
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

    # 6. Bảng kho Panel lỗi
    conn.execute(text("""
    CREATE TABLE IF NOT EXISTS panel_inventory (
        id SERIAL PRIMARY KEY,
        ngay_loi DATE DEFAULT CURRENT_DATE,
        source_warehouse VARCHAR(50) NOT NULL,
        vi_tri_de VARCHAR(50),
        order_code VARCHAR(50),
        brand VARCHAR(50),
        color VARCHAR(50),
        core_thickness VARCHAR(50),
        kho_ton VARCHAR(50),
        foam_type VARCHAR(50),
        sheet_length REAL,
        current_sheets INTEGER,
        total_meters REAL,
        total_area_m2 REAL,
        reason TEXT,
        fault_by VARCHAR(100),
        created_at DATE DEFAULT CURRENT_DATE
    );
    """))

    # 7. Lịch sử ghép Panel
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

    # Tự động cập nhật cột mới nếu database cũ chưa có
    try:
        conn.execute(text("ALTER TABLE inventory ADD COLUMN IF NOT EXISTS ngay_loi DATE DEFAULT CURRENT_DATE;"))
        conn.execute(text("ALTER TABLE accessory_inventory ADD COLUMN IF NOT EXISTS ngay_loi DATE DEFAULT CURRENT_DATE;"))
        conn.execute(text("ALTER TABLE accessory_inventory ADD COLUMN IF NOT EXISTS trang_thai VARCHAR(50) DEFAULT 'Chưa xử lý';"))
        conn.execute(text("ALTER TABLE accessory_inventory ADD COLUMN IF NOT EXISTS don_da_ghep VARCHAR(50);"))
        conn.execute(text("ALTER TABLE panel_inventory ADD COLUMN IF NOT EXISTS ngay_loi DATE DEFAULT CURRENT_DATE;"))
        conn.execute(text("ALTER TABLE panel_inventory ADD COLUMN IF NOT EXISTS kho_ton VARCHAR(50);"))
    except Exception:
        pass
    
    # Tài khoản admin gốc
    check_admin = conn.execute(text("SELECT COUNT(*) FROM users WHERE username = 'admin'")).scalar()
    if check_admin == 0:
        pw_hash = bcrypt.hashpw("123456".encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        conn.execute(text("""
        INSERT INTO users (username, password_hash, full_name, role, is_approved)
        VALUES ('admin', :pw, 'Quản Trị Viên', 'admin', 1)
        """), {"pw": pw_hash})
    conn.commit()

st.set_page_config(page_title="Quản Lý Kho Tôn, Phụ Kiện & Panel", layout="wide")

if "user" not in st.session_state:
    st.session_state.user = None

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

DANH_SACH_SONG = ["6 sóng", "11 sóng"]
DANH_SACH_LOAI_TON = ["Tôn 1L", "Tôn 3L", "Ngói 1L", "Ngói 3L"]
DANH_SACH_XOP = ["Không xốp", "Xốp Eco", "Xốp G8", "Xốp G7", "Xốp G*", "Ngói N8", "Ngói N*"]
DANH_SACH_VI_TRI = ["KV_Cán tôn 1L", "KV_Cán tôn 3L", "KV_Ngói xốp", "KV_PK", "KV_Panel"]
DANH_SACH_NGUYEN_NHAN = ["Đuôi cuộn", "NV_cắt sai", "Lỗi xước sơn", "Lỗi máy", "Lỗi cuộn NVL", "Lỗi sai kích thước", "Lỗi khác"]
DANH_SACH_PHU_KIEN = ["Máng", "Sườn", "Xối", "Nóc"]
DANH_SACH_DO_DAY_PANEL = ["5cm (50mm)", "7.5cm (75mm)", "10cm (100mm)"]
DANH_SACH_KHO_PANEL = ["Khổ nhỏ 1020mm", "Khổ to 1170mm"]
DANH_SACH_XOP_PANEL = ["Xốp thường", "Xốp chống cháy"]

# =============================================================
# 1. TRA CỨU TỒN KHO
# =============================================================
if lua_chon == "📋 Tra cứu tồn kho":
    tab_ton, tab_pk, tab_pn = st.tabs(["📦 Tồn kho Tôn lỗi", "🛠️ Tồn kho Phụ kiện", "🧱 Tồn kho Panel"])
    
    with tab_ton:
        st.subheader("📋 Danh mục Tôn lỗi tồn kho")
        df_ton = pd.read_sql("""
            SELECT id, ngay_loi as "Ngày lỗi", source_warehouse as "Kho", vi_tri_de as "Vị trí", 
                   order_code as "Mã đơn", brand as "Hãng", thickness as "Dày (mm)", color as "Màu", 
                   corrugation_type as "Sóng", ton_type as "Loại tôn", foam_type as "Quy cách xốp/ngói", 
                   sheet_length as "Dài (m)", current_sheets as "Số tấm", total_meters as "Tổng mét", 
                   reason as "Nguyên nhân", fault_by as "Lỗi do ai" 
            FROM inventory 
            WHERE current_sheets > 0 
            ORDER BY id DESC
        """, engine)
        st.dataframe(df_ton, width='stretch')

    with tab_pk:
        st.subheader("🛠️ Danh mục Phụ kiện (Máng, Sườn, Xối, Nóc)")
        df_pk = pd.read_sql("""
            SELECT id, ngay_loi as "Ngày lỗi", trang_thai as "Trạng thái", don_da_ghep as "Đơn đã ghép",
                   source_warehouse as "Kho", vi_tri_de as "Vị trí", order_code as "Mã đơn", 
                   accessory_type as "Loại phụ kiện", brand as "Hãng", thickness as "Dày (mm)", 
                   color as "Màu", sheet_length as "Dài 1 tấm (m)", current_sheets as "Số tấm", 
                   total_meters as "Tổng mét", reason as "Nguyên nhân", fault_by as "Lỗi do ai" 
            FROM accessory_inventory 
            ORDER BY id DESC
        """, engine)
        st.dataframe(df_pk, width='stretch')

    with tab_pn:
        st.subheader("🧱 Danh mục Panel lỗi tồn kho")
        df_pn = pd.read_sql("""
            SELECT id, ngay_loi as "Ngày lỗi", source_warehouse as "Kho", vi_tri_de as "Vị trí", 
                   order_code as "Mã đơn", brand as "Hãng tôn", color as "Màu", 
                   core_thickness as "Độ dày Panel", kho_ton as "Khổ tôn", foam_type as "Quy cách xốp", 
                   sheet_length as "Dài 1 tấm (m)", current_sheets as "Số tấm", 
                   total_meters as "Tổng mét dài", total_area_m2 as "Tổng m2", 
                   reason as "Nguyên nhân", fault_by as "Lỗi do ai" 
            FROM panel_inventory 
            WHERE current_sheets > 0 
            ORDER BY id DESC
        """, engine)
        st.dataframe(df_pn, width='stretch')

# =============================================================
# 2. ➕ NHẬP LỖI TÔN (CHO PHÉP BỎ TRỐNG MÃ ĐƠN)
# =============================================================
elif lua_chon == "➕ Nhập lỗi Tôn":
    st.title("➕ Nhập hàng lỗi phát sinh cho Tôn")
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        ngay_loi_ton = st.date_input("Ngày phát sinh lỗi", datetime.date.today())
        kho = st.selectbox("Kho lưu", ["Kho hàng lỗi trả về", "Kho hàng lỗi NM"])
        don = st.text_input("Mã đơn hàng (không có thì bỏ trống)").strip()
        vi_tri = st.selectbox("Vị trí để", DANH_SACH_VI_TRI)
    with col_b:
        hang = st.text_input("Hãng tôn (Hòa Phát, SSSC, Poshaco...) *").strip()
        mau = st.text_input("Màu sắc *").strip()
        day = st.number_input("Độ dày (dem/mm)", value=0.40, step=0.05)
        song = st.selectbox("Loại sóng", DANH_SACH_SONG)
    with col_c:
        loai_ton = st.selectbox("Loại tôn", DANH_SACH_LOAI_TON)
        quy_cach_xop = st.selectbox("Quy cách xốp / ngói", DANH_SACH_XOP)
        dai = st.number_input("Độ dài 1 tấm (m)", value=6.0, step=0.1)
        so_tam = st.number_input("Số tấm", min_value=1, value=5, step=1)
        tong_m_ton = dai * so_tam
        st.info(f"Tổng mét dài: **{tong_m_ton:.2f} m**")
        loi_ai = st.text_input("Lỗi do ai (Tên NV / Tổ máy)").strip()
        ly_do_chon = st.selectbox("Nguyên nhân lỗi", DANH_SACH_NGUYEN_NHAN)
        ly_do_chi_tiet = st.text_area("Ghi chú chi tiết") if ly_do_chon == "Lỗi khác" else ""

    if st.button("Lưu tôn lỗi vào kho"):
        if not hang or not mau:
            st.warning("⚠️ Vui lòng điền đủ: Hãng tôn và Màu sắc!")
        else:
            ma_don_luu = don if don else "Không có"
            nguyen_nhan_luu = f"Lỗi khác: {ly_do_chi_tiet.strip()}" if ly_do_chon == "Lỗi khác" else ly_do_chon
            with engine.connect() as conn:
                conn.execute(text("""
                INSERT INTO inventory (ngay_loi, source_warehouse, order_code, vi_tri_de, brand, thickness, color, 
                                       corrugation_type, ton_type, foam_type, sheet_length, 
                                       current_sheets, total_meters, reason, fault_by)
                VALUES (:nl, :wh, :oc, :vt, :br, :th, :co, :cr, :tt, :fo, :sl, :cs, :tm, :re, :fb)
                """), {
                    "nl": ngay_loi_ton, "wh": kho, "oc": ma_don_luu, "vt": vi_tri, "br": hang, "th": day, "co": mau,
                    "cr": song, "tt": loai_ton, "fo": quy_cach_xop, "sl": dai, "cs": so_tam,
                    "tm": tong_m_ton, "re": nguyen_nhan_luu, "fb": loi_ai
                })
                conn.commit()
            st.success("✅ Đã nhập thành công lô Tôn vào kho!")
            st.rerun()

# =============================================================
# 3. ➕ NHẬP LỖI PHỤ KIỆN (CHO PHÉP BỎ TRỐNG MÃ ĐƠN)
# =============================================================
elif lua_chon == "➕ Nhập lỗi Phụ kiện":
    st.title("➕ Nhập hàng lỗi cho Phụ kiện (Máng, Sườn, Xối, Nóc)")
    col_p1, col_p2, col_p3 = st.columns(3)
    with col_p1:
        ngay_loi_pk = st.date_input("Ngày phát sinh lỗi", datetime.date.today(), key="pk_ngay")
        pk_kho = st.selectbox("Kho lưu", ["Kho hàng lỗi NM", "Kho hàng lỗi trả về"], key="pk_kho")
        pk_don = st.text_input("Mã đơn hàng (không có thì bỏ trống)", key="pk_don").strip()
        pk_loai = st.selectbox("Loại phụ kiện", DANH_SACH_PHU_KIEN, key="pk_loai")
        pk_vi_tri = st.selectbox("Vị trí để", DANH_SACH_VI_TRI, key="pk_vt")
    with col_p2:
        pk_hang = st.text_input("Hãng tôn phụ kiện *", key="pk_hang").strip()
        pk_mau = st.text_input("Màu sắc *", key="pk_mau").strip()
        pk_day = st.number_input("Độ dày tôn (dem/mm)", value=0.40, step=0.05, key="pk_day")
        pk_dai = st.number_input("Chiều dài 1 tấm (m)", value=2.0, step=0.1, key="pk_dai")
        pk_so_tam = st.number_input("Số tấm (cái)", min_value=1, value=5, step=1, key="pk_tam")
        pk_tong_met = pk_dai * pk_so_tam
        st.info(f"Tổng mét quy đổi: **{pk_tong_met:.2f} m**")
    with col_p3:
        da_xu_ly = st.checkbox("Đã xử lý (đã ghép vào đơn mới)", value=False)
        don_xu_ly = ""
        if da_xu_ly:
            don_xu_ly = st.text_input("Nhập mã đơn đã ghép xử lý:").strip()
            
        pk_loi_ai = st.text_input("Lỗi do ai (Tên NV / Tổ chấn)", key="pk_loi_ai").strip()
        pk_ly_do_chon = st.selectbox("Nguyên nhân lỗi", DANH_SACH_NGUYEN_NHAN, key="pk_nn")
        pk_ly_do_chi_tiet = st.text_area("Ghi chú chi tiết", key="pk_note") if pk_ly_do_chon == "Lỗi khác" else ""

    if st.button("Lưu phụ kiện vào kho"):
        if not pk_hang or not pk_mau:
            st.warning("⚠️ Vui lòng điền đủ: Hãng tôn và Màu sắc!")
        elif da_xu_ly and not don_xu_ly:
            st.warning("⚠️ Đã tích 'Đã xử lý' thì phải điền mã đơn ghép!")
        else:
            ma_pk_luu = pk_don if pk_don else "Không có"
            trang_thai_pk = "Đã xử lý" if da_xu_ly else "Chưa xử lý"
            so_tam_con = 0 if da_xu_ly else pk_so_tam
            so_met_con = 0.0 if da_xu_ly else pk_tong_met
            pk_nguyen_nhan_luu = f"Lỗi khác: {pk_ly_do_chi_tiet.strip()}" if pk_ly_do_chon == "Lỗi khác" else pk_ly_do_chon
            
            with engine.connect() as conn:
                res_pk = conn.execute(text("""
                INSERT INTO accessory_inventory (ngay_loi, source_warehouse, vi_tri_de, order_code, accessory_type, 
                                                 brand, thickness, color, sheet_length, current_sheets, 
                                                 total_meters, trang_thai, don_da_ghep, reason, fault_by)
                VALUES (:nl, :wh, :vt, :oc, :at, :br, :th, :co, :sl, :cs, :tm, :tt, :dg, :re, :fb)
                RETURNING id
                """), {
                    "nl": ngay_loi_pk, "wh": pk_kho, "vt": pk_vi_tri, "oc": ma_pk_luu, "at": pk_loai,
                    "br": pk_hang, "th": pk_day, "co": pk_mau, "sl": pk_dai,
                    "cs": so_tam_con, "tm": so_met_con, "tt": trang_thai_pk, "dg": don_xu_ly,
                    "re": pk_nguyen_nhan_luu, "fb": pk_loi_ai
                })
                new_pk_id = res_pk.scalar()
                
                if da_xu_ly:
                    conn.execute(text("""
                    INSERT INTO accessory_matching_history (accessory_id, new_order_code, matched_sheets, matched_meters, matched_by)
                    VALUES (:aid, :od, :ms, :mm, :mb)
                    """), {
                        "aid": new_pk_id, "od": don_xu_ly, "ms": pk_so_tam, "mm": pk_tong_met, "mb": st.session_state.user['name']
                    })
                conn.commit()
            st.success(f"✅ Đã lưu phụ kiện vào hệ thống (Trạng thái: {trang_thai_pk})!")
            st.rerun()

# =============================================================
# 4. ➕ NHẬP LỖI PANEL (CHO PHÉP BỎ TRỐNG MÃ ĐƠN)
# =============================================================
elif lua_chon == "➕ Nhập lỗi Panel":
    st.title("➕ Nhập hàng lỗi phát sinh cho Panel")
    col_pn1, col_pn2, col_pn3 = st.columns(3)
    with col_pn1:
        ngay_loi_pn = st.date_input("Ngày phát sinh lỗi", datetime.date.today(), key="pn_ngay")
        pn_kho = st.selectbox("Kho lưu", ["Kho hàng lỗi NM", "Kho hàng lỗi trả về"], key="pn_kho")
        pn_don = st.text_input("Mã đơn hàng (không có thì bỏ trống)", key="pn_don").strip()
        pn_vi_tri = st.selectbox("Vị trí để", DANH_SACH_VI_TRI, key="pn_vt")
    with col_pn2:
        pn_hang = st.text_input("Hãng tôn mặt ngoài *", key="pn_hang").strip()
        pn_mau = st.text_input("Màu sắc tôn mặt", value="Trắng sữa / Ghi sáng", key="pn_mau").strip()
        pn_core = st.selectbox("Độ dày Panel", DANH_SACH_DO_DAY_PANEL, key="pn_core")
        pn_kho_ton = st.selectbox("Khổ tôn Panel", DANH_SACH_KHO_PANEL, key="pn_kho_ton")
    with col_pn3:
        pn_xop_quy_cach = st.selectbox("Quy cách xốp lõi", DANH_SACH_XOP_PANEL, key="pn_xop")
        pn_dai = st.number_input("Chiều dài 1 tấm (m)", value=5.0, step=0.1, key="pn_dai")
        pn_so_tam = st.number_input("Số tấm", min_value=1, value=4, step=1, key="pn_tam")
        
        he_so_rong = 1.02 if "1020" in pn_kho_ton else 1.17
        pn_tong_m = pn_dai * pn_so_tam
        pn_tong_m2 = pn_tong_m * he_so_rong
        st.info(f"Tổng mét dài: **{pn_tong_m:.2f} m** | Tổng diện tích: **{pn_tong_m2:.2f} m²**")
        
        pn_loi_ai = st.text_input("Lỗi do ai (Tên NV / Tổ ép panel)", key="pn_loi_ai").strip()
        pn_ly_do_chon = st.selectbox("Nguyên nhân lỗi", DANH_SACH_NGUYEN_NHAN, key="pn_nn")
        pn_ly_do_chi_tiet = st.text_area("Ghi chú chi tiết", key="pn_note") if pn_ly_do_chon == "Lỗi khác" else ""

    if st.button("Lưu tấm Panel lỗi vào kho"):
        if not pn_hang:
            st.warning("⚠️ Vui lòng điền Hãng tôn!")
        else:
            ma_pn_luu = pn_don if pn_don else "Không có"
            pn_nguyen_nhan_luu = f"Lỗi khác: {pn_ly_do_chi_tiet.strip()}" if pn_ly_do_chon == "Lỗi khác" else pn_ly_do_chon
            with engine.connect() as conn:
                conn.execute(text("""
                INSERT INTO panel_inventory (ngay_loi, source_warehouse, vi_tri_de, order_code, brand, color, 
                                             core_thickness, kho_ton, foam_type, sheet_length, 
                                             current_sheets, total_meters, total_area_m2, reason, fault_by)
                VALUES (:nl, :wh, :vt, :oc, :br, :co, :ct, :kt, :fo, :sl, :cs, :tm, :ta, :re, :fb)
                """), {
                    "nl": ngay_loi_pn, "wh": pn_kho, "vt": pn_vi_tri, "oc": ma_pn_luu, "br": pn_hang, "co": pn_mau,
                    "ct": pn_core, "kt": pn_kho_ton, "fo": pn_xop_quy_cach, "sl": pn_dai,
                    "cs": pn_so_tam, "tm": pn_tong_m, "ta": pn_tong_m2, "re": pn_nguyen_nhan_luu, "fb": pn_loi_ai
                })
                conn.commit()
            st.success(f"✅ Đã nhập thành công {pn_so_tam} tấm Panel ({pn_tong_m2:.2f} m²) vào kho!")
            st.rerun()

# =============================================================
# 5. TÌM KIẾM & GHÉP ĐƠN
# =============================================================
elif lua_chon == "✂️ Tìm kiếm & Ghép đơn":
    tab_ghep_ton, tab_ghep_pk, tab_ghep_pn = st.tabs(["✂️ Ghép Tôn tấm", "🛠️ Xuất / Ghép Phụ kiện", "🧱 Xuất / Ghép Panel"])
    
    # 5.1 Ghép Tôn
    with tab_ghep_ton:
        st.subheader("✂️ Tìm kiếm thông minh ghép Tôn mới")
        XOP_RANKS = {"Không xốp": 0, "Xốp Eco": 1, "Xốp G8": 2, "Xốp G7": 3, "Xốp G*": 4, "Ngói N8": 1, "Ngói N*": 2}

        c1, c2, c3 = st.columns(3)
        with c1:
            s_hang = st.text_input("Hãng tôn yêu cầu", key="gt_hang").strip()
            s_mau = st.text_input("Màu sắc yêu cầu", key="gt_mau").strip()
            s_day = st.number_input("Độ dày yêu cầu", value=0.40, step=0.05, key="gt_day")
        with c2:
            s_song = st.selectbox("Loại sóng", DANH_SACH_SONG, key="gt_song")
            s_ton = st.selectbox("Loại tôn", DANH_SACH_LOAI_TON, key="gt_ton")
            s_xop = st.selectbox("Cấp xốp tối thiểu", DANH_SACH_XOP, key="gt_xop")
        with c3:
            s_dai = st.number_input("Độ dài cần cắt ghép (m)", value=4.0, step=0.1, key="gt_dai")
            st.write("")
            st.write("")
            btn_tim = st.button("🔎 Quét kho tìm tôn")

        if s_hang and s_mau:
            query = """
            SELECT id, ngay_loi as "Ngày lỗi", source_warehouse as "Kho", vi_tri_de as "Vị trí", order_code as "Mã đơn", 
                   brand as "Hãng", thickness as "Dày (mm)", color as "Màu", corrugation_type as "Sóng", 
                   ton_type as "Loại tôn", foam_type as "Xốp/Ngói", sheet_length as "Dài (m)", 
                   current_sheets as "Số tấm còn", total_meters as "Tổng mét"
            FROM inventory 
            WHERE current_sheets > 0 
              AND LOWER(TRIM(brand)) = LOWER(TRIM(:hang))
              AND LOWER(TRIM(color)) = LOWER(TRIM(:mau))
              AND corrugation_type = :song
              AND ton_type = :ton
              AND sheet_length >= :dai_yc
              AND thickness >= :day_yc
            """
            df_all = pd.read_sql(query, engine, params={
                "hang": s_hang, "mau": s_mau, "song": s_song, "ton": s_ton,
                "dai_yc": s_dai, "day_yc": s_day
            })

            if not df_all.empty:
                req_rank = XOP_RANKS.get(s_xop, 0)
                df_all['rank'] = df_all['Xốp/Ngói'].map(lambda x: XOP_RANKS.get(x, 0))
                df_match = df_all[df_all['rank'] >= req_rank].copy()

                if not df_match.empty:
                    df_match['lech_xop'] = df_match['rank'] - req_rank
                    df_match['lech_day'] = df_match['Dày (mm)'] - s_day
                    df_match['du_dai'] = df_match['Dài (m)'] - s_dai
                    df_sorted = df_match.sort_values(by=['lech_xop', 'lech_day', 'du_dai']).drop(columns=['rank', 'lech_xop', 'lech_day', 'du_dai'])

                    st.success(f"🎯 Tìm thấy {len(df_sorted)} vị trí đạt chuẩn ghép:")
                    st.dataframe(df_sorted, width='stretch')

                    st.markdown("---")
                    with st.form("form_confirm_ghep_ton"):
                        id_ghep = st.selectbox("Chọn ID dòng cần lấy ghép", df_sorted['id'].tolist())
                        r_target = df_sorted[df_sorted['id'] == id_ghep].iloc[0]
                        
                        cg1, cg2, cg3 = st.columns(3)
                        with cg1:
                            ma_moi = st.text_input("Mã đơn mới ghép vào")
                        with cg2:
                            tam_ghep = st.number_input("Số tấm cần lấy", min_value=1, max_value=int(r_target['Số tấm còn']), value=1)
                            met_ghep = tam_ghep * s_dai
                            st.info(f"Tổng mét ghép: **{met_ghep:.2f} m**")
                        with cg3:
                            nguoi_ghep = st.text_input("Nhân viên ghép", value=st.session_state.user['name'])

                        if st.form_submit_button("Xác nhận trừ kho"):
                            tam_con = int(r_target['Số tấm còn']) - tam_ghep
                            met_con = tam_con * float(r_target['Dài (m)'])
                            with engine.connect() as conn:
                                conn.execute(text("UPDATE inventory SET current_sheets = :tc, total_meters = :mc WHERE id = :id"),
                                             {"tc": tam_con, "mc": met_con, "id": id_ghep})
                                conn.execute(text("INSERT INTO matching_history (inventory_id, new_order_code, matched_meters, matched_by) VALUES (:iid, :od, :mm, :mb)"),
                                             {"iid": id_ghep, "od": ma_moi, "mm": met_ghep, "mb": nguoi_ghep})
                                conn.commit()
                            st.success(f"✅ Đã trừ kho thành công! Vị trí {r_target['Vị trí']} còn lại {tam_con} tấm.")
                            st.rerun()
                else:
                    st.warning("⚠️ Có lô phù hợp kích thước nhưng xốp mềm hơn yêu cầu (không được ghép)!")
            else:
                st.info("Không tìm thấy tấm tôn nào thỏa mãn điều kiện.")

    # 5.2 Ghép Phụ kiện
    with tab_ghep_pk:
        st.subheader("🛠️ Tìm kiếm & Xuất ghép Phụ kiện (Chỉ quét hàng Chưa xử lý)")
        cp1, cp2, cp3 = st.columns(3)
        with cp1:
            q_pk_loai = st.selectbox("Loại phụ kiện cần tìm", DANH_SACH_PHU_KIEN, key="q_pk_loai")
            q_pk_hang = st.text_input("Hãng tôn phụ kiện", key="q_pk_hang").strip()
        with cp2:
            q_pk_mau = st.text_input("Màu sắc cần", key="q_pk_mau").strip()
            q_pk_day = st.number_input("Độ dày tối thiểu (dem/mm)", value=0.40, step=0.05, key="q_pk_day")
        with cp3:
            q_pk_dai = st.number_input("Chiều dài tối thiểu (m)", value=2.0, step=0.1, key="q_pk_dai")
            st.write("")
            st.write("")
            btn_tim_pk = st.button("🔎 Quét kho tìm phụ kiện")

        if q_pk_hang and q_pk_mau:
            df_pk_found = pd.read_sql("""
                SELECT id, ngay_loi as "Ngày lỗi", source_warehouse as "Kho", vi_tri_de as "Vị trí", 
                       order_code as "Mã đơn", accessory_type as "Loại PK", brand as "Hãng", 
                       thickness as "Dày (mm)", color as "Màu", sheet_length as "Dài (m)", 
                       current_sheets as "Số tấm còn", total_meters as "Tổng mét"
                FROM accessory_inventory
                WHERE current_sheets > 0 AND (trang_thai = 'Chưa xử lý' OR trang_thai IS NULL)
                  AND accessory_type = :at
                  AND LOWER(TRIM(brand)) = LOWER(TRIM(:hang))
                  AND LOWER(TRIM(color)) = LOWER(TRIM(:mau))
                  AND thickness >= :day_yc
                  AND sheet_length >= :dai_yc
                ORDER BY thickness ASC, sheet_length ASC
            """, engine, params={"at": q_pk_loai, "hang": q_pk_hang, "mau": q_pk_mau, "day_yc": q_pk_day, "dai_yc": q_pk_dai})

            if not df_pk_found.empty:
                st.success(f"🎯 Tìm thấy {len(df_pk_found)} vị trí phụ kiện đủ điều kiện:")
                st.dataframe(df_pk_found, width='stretch')

                st.markdown("---")
                with st.form("form_confirm_ghep_pk"):
                    pk_id_chon = st.selectbox("Chọn ID phụ kiện muốn lấy", df_pk_found['id'].tolist())
                    r_pk = df_pk_found[df_pk_found['id'] == pk_id_chon].iloc[0]
                    
                    g_pk1, g_pk2, g_pk3 = st.columns(3)
                    with g_pk1:
                        pk_don_moi = st.text_input("Mã đơn mới ghép vào", key="pk_don_moi")
                    with g_pk2:
                        pk_tam_lay = st.number_input("Số tấm cần lấy", min_value=1, max_value=int(r_pk['Số tấm còn']), value=1, key="pk_tam_lay")
                        pk_m_lay = pk_tam_lay * float(r_pk['Dài (m)'])
                        st.info(f"Tổng mét phụ kiện: **{pk_m_lay:.2f} m**")
                    with g_pk3:
                        pk_nguoi_lay = st.text_input("Nhân viên ghép", value=st.session_state.user['name'], key="pk_nv_lay")

                    if st.form_submit_button("Xác nhận trừ kho phụ kiện"):
                        pk_tam_con = int(r_pk['Số tấm còn']) - pk_tam_lay
                        pk_m_con = pk_tam_con * float(r_pk['Dài (m)'])
                        trang_thai_moi = "Đã xử lý" if pk_tam_con == 0 else "Chưa xử lý"
                        
                        with engine.connect() as conn:
                            conn.execute(text("""
                            UPDATE accessory_inventory 
                            SET current_sheets = :tc, total_meters = :mc, trang_thai = :tt, don_da_ghep = :dg 
                            WHERE id = :id
                            """), {
                                "tc": pk_tam_con, "mc": pk_m_con, "tt": trang_thai_moi, "dg": pk_don_moi, "id": pk_id_chon
                            })
                            conn.execute(text("""
                            INSERT INTO accessory_matching_history (accessory_id, new_order_code, matched_sheets, matched_meters, matched_by) 
                            VALUES (:aid, :od, :ms, :mm, :mb)
                            """), {
                                "aid": pk_id_chon, "od": pk_don_moi, "ms": pk_tam_lay, "mm": pk_m_lay, "mb": pk_nguoi_lay
                            })
                            conn.commit()
                        st.success(f"✅ Đã trừ thành công {pk_tam_lay} tấm {r_pk['Loại PK']}! Còn lại {pk_tam_con} tấm.")
                        st.rerun()
            else:
                st.info("Không có phụ kiện nào thỏa mãn điều kiện yêu cầu.")

    # 5.3 Ghép Panel
    with tab_ghep_pn:
        st.subheader("🧱 Tìm kiếm & Xuất ghép Panel")
        pn_c1, pn_c2, pn_c3 = st.columns(3)
        with pn_c1:
            q_pn_hang = st.text_input("Hãng tôn mặt Panel", key="q_pn_hang").strip()
            q_pn_core = st.selectbox("Độ dày Panel yêu cầu", DANH_SACH_DO_DAY_PANEL, key="q_pn_core")
        with pn_c2:
            q_pn_mau = st.text_input("Màu sắc tôn mặt", key="q_pn_mau").strip()
            q_pn_kho = st.selectbox("Khổ tôn yêu cầu", DANH_SACH_KHO_PANEL, key="q_pn_kho")
        with pn_c3:
            q_pn_dai = st.number_input("Chiều dài tối thiểu (m)", value=3.0, step=0.1, key="q_pn_dai")
            st.write("")
            st.write("")
            btn_tim_pn = st.button("🔎 Quét kho tìm Panel")

        if q_pn_hang:
            df_pn_found = pd.read_sql("""
                SELECT id, ngay_loi as "Ngày lỗi", source_warehouse as "Kho", vi_tri_de as "Vị trí", 
                       order_code as "Mã đơn", brand as "Hãng tôn", color as "Màu", 
                       core_thickness as "Độ dày Panel", kho_ton as "Khổ tôn", foam_type as "Quy cách xốp", 
                       sheet_length as "Dài (m)", current_sheets as "Số tấm còn", total_area_m2 as "Tổng m2"
                FROM panel_inventory
                WHERE current_sheets > 0 
                  AND core_thickness = :ct
                  AND kho_ton = :kt
                  AND LOWER(TRIM(brand)) = LOWER(TRIM(:hang))
                  AND sheet_length >= :sl
                ORDER BY sheet_length ASC
            """, engine, params={"ct": q_pn_core, "kt": q_pn_kho, "hang": q_pn_hang, "sl": q_pn_dai})

            if not df_pn_found.empty:
                st.success(f"🎯 Tìm thấy {len(df_pn_found)} vị trí Panel đủ điều kiện ghép:")
                st.dataframe(df_pn_found, width='stretch')

                st.markdown("---")
                with st.form("form_confirm_ghep_pn"):
                    pn_id_chon = st.selectbox("Chọn ID Panel muốn lấy", df_pn_found['id'].tolist())
                    r_pn = df_pn_found[df_pn_found['id'] == pn_id_chon].iloc[0]
                    
                    g_pn1, g_pn2, g_pn3 = st.columns(3)
                    with g_pn1:
                        pn_don_moi = st.text_input("Mã đơn hàng ghép vào", key="pn_don_moi")
                    with g_pn2:
                        pn_tam_lay = st.number_input("Số tấm cần lấy", min_value=1, max_value=int(r_pn['Số tấm còn']), value=1, key="pn_tam_lay")
                        pn_m_lay = pn_tam_lay * float(r_pn['Dài (m)'])
                        he_so = 1.02 if "1020" in r_pn['Khổ tôn'] else 1.17
                        pn_m2_lay = pn_m_lay * he_so
                        st.info(f"Xuất: **{pn_m_lay:.2f} m** | Diện tích: **{pn_m2_lay:.2f} m²**")
                    with g_pn3:
                        pn_nguoi_lay = st.text_input("Nhân viên ghép", value=st.session_state.user['name'], key="pn_nv_lay")

                    if st.form_submit_button("Xác nhận trừ kho Panel"):
                        pn_tam_con = int(r_pn['Số tấm còn']) - pn_tam_lay
                        pn_m_con = pn_tam_con * float(r_pn['Dài (m)'])
                        pn_m2_con = pn_m_con * he_so
                        with engine.connect() as conn:
                            conn.execute(text("UPDATE panel_inventory SET current_sheets = :tc, total_meters = :mc, total_area_m2 = :m2c WHERE id = :id"),
                                         {"tc": pn_tam_con, "mc": pn_m_con, "m2c": pn_m2_con, "id": pn_id_chon})
                            conn.execute(text("INSERT INTO panel_matching_history (panel_id, new_order_code, matched_sheets, matched_meters, matched_m2, matched_by) VALUES (:pid, :od, :ms, :mm, :m2, :mb)"),
                                         {"pid": pn_id_chon, "od": pn_don_moi, "ms": pn_tam_lay, "mm": pn_m_lay, "m2": pn_m2_lay, "mb": pn_nguoi_lay})
                            conn.commit()
                        st.success(f"✅ Đã trừ thành công {pn_tam_lay} tấm Panel! Còn lại {pn_tam_con} tấm ({pn_m2_con:.2f} m²).")
                        st.rerun()
            else:
                st.info("Không có tấm Panel nào trong kho thỏa mãn tiêu chí.")

# =============================================================
# 6. BÁO CÁO DASHBOARD
# =============================================================
elif lua_chon == "📊 Báo cáo Dashboard":
    st.title("📊 Báo cáo Thống kê Toàn xưởng (Tôn - Phụ kiện - Panel)")
    c_d1, c_d2 = st.columns(2)
    with c_d1:
        st.subheader("⚠️ Top người / tổ gây lỗi nhiều nhất")
        df_fault_all = pd.read_sql("""
            SELECT fault_by as "Người/Tổ máy", 
                   SUM(total_meters) as "Tổng mét lỗi", 
                   COUNT(id) as "Số lần phát sinh"
            FROM (
                SELECT fault_by, total_meters, id FROM inventory
                UNION ALL
                SELECT fault_by, total_meters, id FROM accessory_inventory
                UNION ALL
                SELECT fault_by, total_meters, id FROM panel_inventory
            ) t
            GROUP BY fault_by 
            ORDER BY SUM(total_meters) DESC
        """, engine)
        st.dataframe(df_fault_all, width='stretch')
    with c_d2:
        st.subheader("🏆 Top người ghép giải cứu hàng nhiều nhất")
        df_match_all = pd.read_sql("""
            SELECT matched_by as "Nhân viên ghép", 
                   SUM(matched_meters) as "Tổng mét ghép", 
                   COUNT(id) as "Số lần ghép"
            FROM (
                SELECT matched_by, matched_meters, id FROM matching_history
                UNION ALL
                SELECT matched_by, matched_meters, id FROM accessory_matching_history
                UNION ALL
                SELECT matched_by, matched_meters, id FROM panel_matching_history
            ) t
            GROUP BY matched_by 
            ORDER BY SUM(matched_meters) DESC
        """, engine)
        st.dataframe(df_match_all, width='stretch')

# =============================================================
# 7. PHÊ DUYỆT TÀI KHOẢN (ADMIN)
# =============================================================
elif lua_chon == "👑 Phê duyệt & Cấp quyền tài khoản":
    st.title("👑 Quản trị & Phê duyệt nhân viên")
    st.subheader("⏳ Yêu cầu tài khoản đang chờ duyệt")
    df_pending = pd.read_sql("SELECT id, username, full_name, role, created_at FROM users WHERE is_approved = 0", engine)
    
    if not df_pending.empty:
        for idx, row in df_pending.iterrows():
            with st.container():
                col_u1, col_u2, col_u3, col_u4 = st.columns([2, 3, 2, 2])
                col_u1.write(f"Tài khoản: **{row['username']}**")
                col_u2.write(f"Họ tên: **{row['full_name']}**")
                assigned_role = col_u3.selectbox("Cấp quyền vai trò", ["operator", "admin"], key=f"role_{row['id']}")
                if col_u4.button("✅ Kích hoạt", key=f"btn_ap_{row['id']}"):
                    with engine.connect() as conn:
                        conn.execute(text("UPDATE users SET is_approved = 1, role = :r WHERE id = :id"), {"r": assigned_role, "id": row['id']})
                        conn.commit()
                    st.success(f"Đã duyệt cho {row['full_name']}!")
                    st.rerun()
            st.divider()
    else:
        st.info("Hiện không có yêu cầu nào chờ phê duyệt.")

    st.subheader("👥 Danh sách nhân viên đang hoạt động")
    df_active = pd.read_sql("SELECT id, username, full_name, role, created_at FROM users WHERE is_approved = 1", engine)
    st.dataframe(df_active, width='stretch')
