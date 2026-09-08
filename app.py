import streamlit as st
import pandas as pd
import sqlite3
import bcrypt

# Kết nối database
conn = sqlite3.connect("ton_inventory.db", check_same_thread=False)
c = conn.cursor()

# Khởi tạo bảng nếu chưa có
c.execute("""
CREATE TABLE IF NOT EXISTS inventory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_warehouse TEXT NOT NULL,
    order_code TEXT,
    brand TEXT,
    thickness REAL,
    color TEXT,
    corrugation_type TEXT,
    ton_type TEXT,
    foam_type TEXT,
    vi_tri_de TEXT,
    sheet_length REAL,
    current_sheets INTEGER,
    total_meters REAL,
    reason TEXT,
    fault_by TEXT,
    created_at DATE DEFAULT (DATE('now'))
)
""")
c.execute("""
CREATE TABLE IF NOT EXISTS matching_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    inventory_id INTEGER,
    new_order_code TEXT,
    matched_meters REAL,
    matched_by TEXT,
    matched_date DATE DEFAULT (DATE('now'))
)
""")
conn.commit()

# Tự động cập nhật thêm cột vi_tri_de nếu database cũ chưa có
try:
    c.execute("ALTER TABLE inventory ADD COLUMN vi_tri_de TEXT DEFAULT 'KV_PK'")
    conn.commit()
except sqlite3.OperationalError:
    pass

st.set_page_config(page_title="Quản Lý & Ghép Tôn Lỗi", layout="wide")

if "user" not in st.session_state:
    st.session_state.user = None

# --- ĐĂNG NHẬP / CẤP QUYỀN ---
st.sidebar.title("🔐 Phân quyền hệ thống")

if st.session_state.user is None:
    st.sidebar.info("Trạng thái: **Khách (Chỉ xem tồn kho & Báo cáo)**")
    with st.sidebar.form("login_form"):
        u = st.text_input("Tài khoản")
        p = st.text_input("Mật khẩu", type="password")
        btn_login = st.form_submit_button("Đăng nhập")
        if btn_login:
            c.execute("SELECT password_hash, full_name, role, is_approved FROM users WHERE username = ?", (u,))
            res = c.fetchone()
            if res:
                hash_val, full_name, role, is_approved = res
                if is_approved == 0:
                    st.sidebar.error("Tài khoản chưa được phê duyệt!")
                elif bcrypt.checkpw(p.encode('utf-8'), hash_val.encode('utf-8')):
                    st.session_state.user = {"username": u, "name": full_name, "role": role}
                    st.sidebar.success(f"Chào {full_name}")
                    st.rerun()
                else:
                    st.sidebar.error("Mật khẩu không đúng!")
            else:
                st.sidebar.error("Tài khoản không tồn tại!")
else:
    st.sidebar.success(f"Đã đăng nhập: **{st.session_state.user['name']}**")
    st.sidebar.caption(f"Quyền hạn: {st.session_state.user['role']}")
    if st.sidebar.button("Đăng xuất"):
        st.session_state.user = None
        st.rerun()

# --- MENU CHỨC NĂNG ---
menu = ["📋 Tra cứu tồn kho", "📊 Báo cáo Dashboard"]
if st.session_state.user is not None:
    menu.insert(1, "➕ Nhập hàng lỗi phát sinh")
    menu.insert(2, "✂️ Tìm kiếm & Ghép đơn")

chon = st.sidebar.radio("Chức năng:", menu)

DANH_SACH_SONG = ["6 sóng", "11 sóng"]
DANH_SACH_LOAI_TON = ["Tôn 1L", "Tôn 3L", "Ngói 1L", "Ngói 3L"]
DANH_SACH_XOP = ["Không xốp", "Xốp Eco", "Xốp G8", "Xốp G7", "Xốp G*", "Ngói N8", "Ngói N*"]
DANH_SACH_VI_TRI = ["KV_Cán tôn 1L", "KV_Cán tôn 3L", "KV_Ngói xốp", "KV_PK"]
DANH_SACH_NGUYEN_NHAN = ["Đuôi cuộn", "NV_cắt sai", "Lỗi xước sơn", "Lỗi máy", "Lỗi cuộn NVL", "Lỗi sai kích thước", "Lỗi khác"]

# -------------------------------------------------------------
# 1. TRA CỨU TỒN KHO
# -------------------------------------------------------------
if chon == "📋 Tra cứu tồn kho":
    st.title("📋 Danh mục tôn lỗi tồn kho")
    df = pd.read_sql("""
        SELECT id, source_warehouse as 'Kho', vi_tri_de as 'Vị trí để', order_code as 'Mã đơn', brand as 'Hãng', 
               thickness as 'Dày (mm)', color as 'Màu', corrugation_type as 'Sóng', 
               ton_type as 'Loại tôn', foam_type as 'Quy cách xốp/ngói', 
               sheet_length as 'Dài (m)', current_sheets as 'Số tấm', 
               total_meters as 'Tổng mét', reason as 'Nguyên nhân', fault_by as 'Lỗi do ai' 
        FROM inventory 
        WHERE current_sheets > 0
    """, conn)
    st.dataframe(df, use_container_width=True)

# -------------------------------------------------------------
# 2. NHẬP HÀNG LỖI PHÁT SINH
# -------------------------------------------------------------
elif chon == "➕ Nhập hàng lỗi phát sinh":
    st.title("➕ Nhập hàng tôn lỗi vào kho")
    
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        kho = st.selectbox("Kho lưu", ["Kho hàng lỗi trả về", "Kho hàng lỗi NM"])
        don = st.text_input("Mã đơn hàng")
        vi_tri = st.selectbox("Vị trí để", DANH_SACH_VI_TRI)
        hang = st.text_input("Hãng tôn (VD: Hòa Phát, SSSC, Poshaco...)")
        day = st.number_input("Độ dày (dem/mm)", value=0.40, step=0.05)
    with col_b:
        mau = st.text_input("Màu sắc")
        song = st.selectbox("Loại sóng", DANH_SACH_SONG)
        loai_ton = st.selectbox("Loại tôn", DANH_SACH_LOAI_TON)
        quy_cach_xop = st.selectbox("Quy cách xốp / ngói", DANH_SACH_XOP)
    with col_c:
        dai = st.number_input("Độ dài 1 tấm (m)", value=6.0, step=0.1)
        so_tam = st.number_input("Số tấm", min_value=1, value=5, step=1)
        loi_ai = st.text_input("Lỗi do ai (Tên / Tổ máy)")
        ly_do_chon = st.selectbox("Nguyên nhân lỗi", DANH_SACH_NGUYEN_NHAN)
        
        # Nếu chọn Lỗi khác thì mở thêm ô ghi chú chi tiết
        ly_do_chi_tiet = ""
        if ly_do_chon == "Lỗi khác":
            ly_do_chi_tiet = st.text_area("Ghi chú chi tiết lỗi khác")

    if st.button("Lưu dữ liệu vào kho"):
        if not don or not hang or not mau:
            st.warning("Vui lòng nhập đầy đủ Mã đơn hàng, Hãng tôn và Màu sắc!")
        else:
            ly_do_cuoi = f"Lỗi khác: {ly_do_chi_tiet.strip()}" if ly_do_chon == "Lỗi khác" else ly_do_chon
            tong_m = dai * so_tam
            c.execute("""
            INSERT INTO inventory (source_warehouse, order_code, vi_tri_de, brand, thickness, color, 
                                   corrugation_type, ton_type, foam_type, sheet_length, 
                                   current_sheets, total_meters, reason, fault_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (kho, don, vi_tri, hang.strip(), day, mau.strip(), song, loai_ton, quy_cach_xop, dai, so_tam, tong_m, ly_do_cuoi, loi_ai.strip()))
            conn.commit()
            st.success("Đã nhập thành công lô hàng vào kho!")
            st.rerun()

# -------------------------------------------------------------
# 3. TÌM KIẾM & GHÉP ĐƠN
# -------------------------------------------------------------
elif chon == "✂️ Tìm kiếm & Ghép đơn":
    st.title("✂️ Tìm kiếm thông minh để ghép đơn mới")
    
    XOP_RANKS = {
        "Không xốp": 0,
        "Xốp Eco": 1,
        "Xốp G8": 2,
        "Xốp G7": 3,
        "Xốp G*": 4,
        "Ngói N8": 1,
        "Ngói N*": 2
    }

    c1, c2, c3 = st.columns(3)
    with c1:
        s_hang = st.text_input("Hãng tôn chuẩn (Hòa Phát, SSSC...)")
        s_mau = st.text_input("Màu sắc chuẩn")
        s_day = st.number_input("Độ dày yêu cầu (dem/mm)", value=0.40, step=0.05)
    with c2:
        s_song = st.selectbox("Loại sóng", DANH_SACH_SONG)
        s_ton = st.selectbox("Loại tôn", DANH_SACH_LOAI_TON)
        s_xop = st.selectbox("Yêu cầu xốp / ngói", DANH_SACH_XOP)
    with c3:
        s_dai = st.number_input("Độ dài cần cắt ghép (m)", value=4.0, step=0.1)
        st.write("")
        st.write("")
        btn_tim = st.button("🔎 Quét kho tìm vị trí ghép")

    query = """
    SELECT id, source_warehouse as 'Kho', vi_tri_de as 'Vị trí để', order_code as 'Mã đơn', brand as 'Hãng', 
           thickness as 'Dày (mm)', color as 'Màu', corrugation_type as 'Sóng',
           ton_type as 'Loại tôn', foam_type as 'Xốp/Ngói', sheet_length as 'Dài (m)', 
           current_sheets as 'Số tấm còn', total_meters as 'Tổng mét'
    FROM inventory 
    WHERE current_sheets > 0 
      AND LOWER(TRIM(brand)) = LOWER(TRIM(:hang))
      AND LOWER(TRIM(color)) = LOWER(TRIM(:mau))
      AND corrugation_type = :song
      AND ton_type = :ton
      AND sheet_length >= :dai_yeu_cau
      AND thickness >= :day_yeu_cau
    """
    params = {
        "hang": s_hang,
        "mau": s_mau,
        "song": s_song,
        "ton": s_ton,
        "dai_yeu_cau": s_dai,
        "day_yeu_cau": s_day
    }
    
    if s_hang and s_mau:
        df_all = pd.read_sql(query, conn, params=params)

        if not df_all.empty:
            req_rank = XOP_RANKS.get(s_xop, 0)
            df_all['rank_xop'] = df_all['Xốp/Ngói'].map(lambda x: XOP_RANKS.get(x, 0))
            df_match = df_all[df_all['rank_xop'] >= req_rank].copy()

            if not df_match.empty:
                df_match['do_du_dai'] = df_match['Dài (m)'] - s_dai
                df_match['do_lech_day'] = df_match['Dày (mm)'] - s_day
                df_match['do_lech_xop'] = df_match['rank_xop'] - req_rank

                df_sorted = df_match.sort_values(
                    by=['do_lech_xop', 'do_lech_day', 'do_du_dai'],
                    ascending=[True, True, True]
                ).drop(columns=['rank_xop', 'do_du_dai', 'do_lech_day', 'do_lech_xop'])

                st.success(f"🎯 Tìm thấy {len(df_sorted)} vị trí đủ điều kiện ghép (Đã xếp theo ưu tiên tối ưu nhất):")
                st.dataframe(df_sorted, use_container_width=True)

                st.markdown("---")
                st.subheader("📝 Xác nhận ghép hàng vào đơn mới")
                with st.form("form_ghep"):
                    id_chon = st.selectbox("Chọn ID dòng tôn muốn lấy để ghép", df_sorted['id'].tolist())
                    row_chon = df_sorted[df_sorted['id'] == id_chon].iloc[0]
                    
                    c_g1, c_g2, c_g3 = st.columns(3)
                    with c_g1:
                        don_moi = st.text_input("Mã đơn hàng mới cần ghép")
                    with c_g2:
                        so_tam_ghep = st.number_input("Số tấm cần ghép", min_value=1, max_value=int(row_chon['Số tấm còn']), value=1)
                        met_da_ghep = so_tam_ghep * s_dai
                        st.info(f"Tổng mét ghép đơn: **{met_da_ghep:.2f} m**")
                    with c_g3:
                        ten_nv = st.text_input("Tên nhân viên ghép", value=st.session_state.user['name'])

                    if st.form_submit_button("Cắt ghép & Cập nhật kho"):
                        tam_con = int(row_chon['Số tấm còn']) - so_tam_ghep
                        met_con = tam_con * float(row_chon['Dài (m)'])
                        
                        c.execute("UPDATE inventory SET current_sheets = ?, total_meters = ? WHERE id = ?", (tam_con, met_con, id_chon))
                        c.execute("INSERT INTO matching_history (inventory_id, new_order_code, matched_meters, matched_by) VALUES (?, ?, ?, ?)", 
                                  (id_chon, don_moi, met_da_ghep, ten_nv))
                        conn.commit()
                        st.success(f"Ghép thành công! Đã trừ {so_tam_ghep} tấm. Dòng ID {id_chon} còn lại {tam_con} tấm ({met_con:.2f}m).")
                        st.rerun()
            else:
                st.warning("Tìm thấy lô cùng hãng/màu, nhưng xốp trong kho mềm hơn yêu cầu nên không cho phép ghép!")
        else:
            st.info("Không có tấm tôn nào thỏa mãn độ dày hoặc độ dài yêu cầu.")
    else:
        st.caption("💡 Vui lòng điền Hãng tôn và Màu sắc để tìm kiếm.")

# -------------------------------------------------------------
# 4. BÁO CÁO DASHBOARD
# -------------------------------------------------------------
elif chon == "📊 Báo cáo Dashboard":
    st.title("📊 Báo cáo Thống kê Kho Tôn")
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("⚠️ Top người / tổ gây lỗi nhiều nhất")
        df_fault = pd.read_sql("""
            SELECT fault_by as 'Người/Tổ máy', 
                   SUM(total_meters) as 'Tổng mét lỗi', 
                   COUNT(id) as 'Số lần phát sinh' 
            FROM inventory 
            GROUP BY fault_by 
            ORDER BY SUM(total_meters) DESC
        """, conn)
        st.dataframe(df_fault, use_container_width=True)
    with c2:
        st.subheader("🏆 Top người ghép giải cứu hàng nhiều nhất")
        df_match_stat = pd.read_sql("""
            SELECT matched_by as 'Nhân viên ghép', 
                   SUM(matched_meters) as 'Tổng mét ghép', 
                   COUNT(id) as 'Số lần ghép' 
            FROM matching_history 
            GROUP BY matched_by 
            ORDER BY SUM(matched_meters) DESC
        """, conn)
        st.dataframe(df_match_stat, use_container_width=True)