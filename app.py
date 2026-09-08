import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
import bcrypt

# --- KẾT NỐI DATABASE ĐÁM MÂY (NEON) ---
if "db_url" in st.secrets:
    DB_URL = st.secrets["db_url"]
else:
    DB_URL = "sqlite:///ton_inventory.db"

# Tự động sửa đầu link nếu là postgres:// sang postgresql:// cho SQLAlchemy
if DB_URL.startswith("postgres://"):
    DB_URL = DB_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DB_URL, pool_pre_ping=True)

# Khởi tạo các bảng trên Neon
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
    
    # Tạo sẵn tài khoản Admin gốc (Tài khoản: admin | Mật khẩu: 123456)
    check_admin = conn.execute(text("SELECT COUNT(*) FROM users WHERE username = 'admin'")).scalar()
    if check_admin == 0:
        pw_hash = bcrypt.hashpw("123456".encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        conn.execute(text("""
        INSERT INTO users (username, password_hash, full_name, role, is_approved)
        VALUES ('admin', :pw, 'Quản Trị Viên', 'admin', 1)
        """), {"pw": pw_hash})
    conn.commit()

st.set_page_config(page_title="Quản Lý Kho Tôn - Poshaco", layout="wide")

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

# --- MENU CHỨC NĂNG ---
menu_options = ["📋 Tra cứu tồn kho", "📊 Báo cáo Dashboard"]
if st.session_state.user is not None:
    menu_options.insert(1, "➕ Nhập hàng lỗi phát sinh")
    menu_options.insert(2, "✂️ Tìm kiếm & Ghép đơn")
    if st.session_state.user['role'] == 'admin':
        menu_options.append("👑 Phê duyệt & Cấp quyền tài khoản")

lua_chon = st.sidebar.radio("Chức năng:", menu_options)

DANH_SACH_SONG = ["6 sóng", "11 sóng"]
DANH_SACH_LOAI_TON = ["Tôn 1L", "Tôn 3L", "Ngói 1L", "Ngói 3L"]
DANH_SACH_XOP = ["Không xốp", "Xốp Eco", "Xốp G8", "Xốp G7", "Xốp G*", "Ngói N8", "Ngói N*"]
DANH_SACH_VI_TRI = ["KV_Cán tôn 1L", "KV_Cán tôn 3L", "KV_Ngói xốp", "KV_PK"]
DANH_SACH_NGUYEN_NHAN = ["Đuôi cuộn", "NV_cắt sai", "Lỗi xước sơn", "Lỗi máy", "Lỗi cuộn NVL", "Lỗi sai kích thước", "Lỗi khác"]

# --- 1. TRA CỨU TỒN KHO ---
if lua_chon == "📋 Tra cứu tồn kho":
    st.title("📋 Danh mục tôn lỗi tồn kho")
    df_ton = pd.read_sql("""
        SELECT id, source_warehouse as "Kho", vi_tri_de as "Vị trí để", order_code as "Mã đơn", 
               brand as "Hãng", thickness as "Dày (mm)", color as "Màu", corrugation_type as "Sóng", 
               ton_type as "Loại tôn", foam_type as "Quy cách xốp/ngói", sheet_length as "Dài (m)", 
               current_sheets as "Số tấm", total_meters as "Tổng mét", reason as "Nguyên nhân", 
               fault_by as "Lỗi do ai" 
        FROM inventory 
        WHERE current_sheets > 0 
        ORDER BY id DESC
    """, engine)
    st.dataframe(df_ton, width='stretch')

# --- 2. NHẬP HÀNG LỖI PHÁT SINH ---
elif lua_chon == "➕ Nhập hàng lỗi phát sinh":
    st.title("➕ Cập nhật tôn lỗi phát sinh vào kho")
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        kho = st.selectbox("Kho lưu", ["Kho hàng lỗi trả về", "Kho hàng lỗi NM"])
        don = st.text_input("Mã đơn hàng").strip()
        vi_tri = st.selectbox("Vị trí để", DANH_SACH_VI_TRI)
        hang = st.text_input("Hãng tôn (Hòa Phát, SSSC, Poshaco...)").strip()
        day = st.number_input("Độ dày (dem/mm)", value=0.40, step=0.05)
    with col_b:
        mau = st.text_input("Màu sắc").strip()
        song = st.selectbox("Loại sóng", DANH_SACH_SONG)
        loai_ton = st.selectbox("Loại tôn", DANH_SACH_LOAI_TON)
        quy_cach_xop = st.selectbox("Quy cách xốp / ngói", DANH_SACH_XOP)
    with col_c:
        dai = st.number_input("Độ dài 1 tấm (m)", value=6.0, step=0.1)
        so_tam = st.number_input("Số tấm", min_value=1, value=5, step=1)
        loi_ai = st.text_input("Lỗi do ai (Tên NV / Tổ máy)").strip()
        ly_do_chon = st.selectbox("Nguyên nhân lỗi", DANH_SACH_NGUYEN_NHAN)
        ly_do_chi_tiet = st.text_area("Ghi chú chi tiết") if ly_do_chon == "Lỗi khác" else ""

    if st.button("Lưu dữ liệu vào kho"):
        if not don or not hang or not mau:
            st.warning("⚠️ Vui lòng điền đủ: Mã đơn, Hãng tôn và Màu sắc!")
        else:
            nguyen_nhan_luu = f"Lỗi khác: {ly_do_chi_tiet.strip()}" if ly_do_chon == "Lỗi khác" else ly_do_chon
            tong_m = dai * so_tam
            with engine.connect() as conn:
                conn.execute(text("""
                INSERT INTO inventory (source_warehouse, order_code, vi_tri_de, brand, thickness, color, 
                                       corrugation_type, ton_type, foam_type, sheet_length, 
                                       current_sheets, total_meters, reason, fault_by)
                VALUES (:wh, :oc, :vt, :br, :th, :co, :cr, :tt, :fo, :sl, :cs, :tm, :re, :fb)
                """), {
                    "wh": kho, "oc": don, "vt": vi_tri, "br": hang, "th": day, "co": mau,
                    "cr": song, "tt": loai_ton, "fo": quy_cach_xop, "sl": dai, "cs": so_tam,
                    "tm": tong_m, "re": nguyen_nhan_luu, "fb": loi_ai
                })
                conn.commit()
            st.success("✅ Đã lưu thành công vào cơ sở dữ liệu chung!")
            st.rerun()

# --- 3. TÌM KIẾM & GHÉP ĐƠN ---
elif lua_chon == "✂️ Tìm kiếm & Ghép đơn":
    st.title("✂️ Tìm kiếm thông minh ghép đơn")
    XOP_RANKS = {"Không xốp": 0, "Xốp Eco": 1, "Xốp G8": 2, "Xốp G7": 3, "Xốp G*": 4, "Ngói N8": 1, "Ngói N*": 2}

    c1, c2, c3 = st.columns(3)
    with c1:
        s_hang = st.text_input("Hãng tôn yêu cầu").strip()
        s_mau = st.text_input("Màu sắc yêu cầu").strip()
        s_day = st.number_input("Độ dày yêu cầu", value=0.40, step=0.05)
    with c2:
        s_song = st.selectbox("Loại sóng", DANH_SACH_SONG)
        s_ton = st.selectbox("Loại tôn", DANH_SACH_LOAI_TON)
        s_xop = st.selectbox("Cấp xốp tối thiểu", DANH_SACH_XOP)
    with c3:
        s_dai = st.number_input("Độ dài cần cắt ghép (m)", value=4.0, step=0.1)
        st.write("")
        st.write("")
        btn_tim = st.button("🔎 Quét kho tìm tôn")

    if s_hang and s_mau:
        query = """
        SELECT id, source_warehouse as "Kho", vi_tri_de as "Vị trí", order_code as "Mã đơn", 
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
                st.subheader("📝 Xác nhận ghép và trừ kho")
                with st.form("form_confirm_ghep"):
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
                st.warning("⚠️ Có lô phù hợp kích thước nhưng xốp trong kho mềm hơn yêu cầu (không được phép ghép)!")
        else:
            st.info("Không tìm thấy tấm tôn nào thỏa mãn điều kiện.")

# --- 4. BÁO CÁO DASHBOARD ---
elif lua_chon == "📊 Báo cáo Dashboard":
    st.title("📊 Báo cáo Thống kê Kho Tôn")
    c_d1, c_d2 = st.columns(2)
    with c_d1:
        st.subheader("⚠️ Top người / tổ gây lỗi nhiều nhất")
        df_f = pd.read_sql("""
            SELECT fault_by as "Người/Tổ máy", SUM(total_meters) as "Tổng mét lỗi", COUNT(id) as "Số lần phát sinh"
            FROM inventory 
            GROUP BY fault_by 
            ORDER BY SUM(total_meters) DESC
        """, engine)
        st.dataframe(df_f, width='stretch')
    with c_d2:
        st.subheader("🏆 Top người ghép giải cứu hàng nhiều nhất")
        df_m = pd.read_sql("""
            SELECT matched_by as "Nhân viên ghép", SUM(matched_meters) as "Tổng mét ghép", COUNT(id) as "Số lần ghép"
            FROM matching_history 
            GROUP BY matched_by 
            ORDER BY SUM(matched_meters) DESC
        """, engine)
        st.dataframe(df_m, width='stretch')

# --- 5. PHÊ DUYỆT TÀI KHOẢN (ADMIN) ---
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
