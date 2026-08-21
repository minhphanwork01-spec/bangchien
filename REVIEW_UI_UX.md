# BangCheck — hồ sơ dự án để review UI/UX

## Bối cảnh

Web điểm danh bang chiến cho game MMO (Nghịch Thủy Hàn / Justice Online).
Người dùng: một bang khoảng **60-90 thành viên**, chủ yếu người Việt.
Bang chiến diễn ra **tối thứ 7 hàng tuần, 20:00**, khóa sổ báo danh trước 2 tiếng.

Stack: Django + SQLite, deploy PythonAnywhere. Không dùng framework JS —
chỉ Django template + Bootstrap 5 + một ít vanilla JS.

## Hai nhóm người dùng, hai nhu cầu khác nhau

**Member (đa số, ~90% lượt truy cập, gần như 100% trên điện thoại)**
- Vào web, tìm tên nhân vật mình, bấm Tham gia / Không tham gia. Xong.
- Không đăng nhập. Nhận diện bằng cookie (chọn nhân vật một lần, nhớ 30 ngày).
- Ưu tiên tuyệt đối: **ít ma sát**. Càng ít bước càng tốt. Bắt đăng nhập =
  tỷ lệ báo danh rớt.
- Trang họ dùng: checkin_home, checkin_select, checkin_status,
  public_result, public_leaderboard, feedback_form, member_request.

**Leader (3-5 người, dùng cả điện thoại lẫn desktop)**
- Xem ai đã báo danh, sửa hộ người quên, kéo thả xếp đội hình 4 team x 30 ô,
  duyệt đơn xin vào bang, xem chuyên cần, xem nhật ký quản trị.
- Trang họ dùng: các file leader_*.html
- Chấp nhận mật độ thông tin cao hơn, nhưng party board và dashboard vẫn
  phải dùng được trên điện thoại (leader hay thao tác lúc đang chơi game).

## Hệ thiết kế hiện tại: "Mực & Ấn" (Ink & Seal)

Trước đây dùng ảnh nền AI-generated (núi sương mù, hoa đào) — bị đánh giá là
"nặng mùi AI" nên đã bỏ hoàn toàn. Thay bằng hệ thuần CSS:

- **Ý tưởng**: thư pháp / con dấu triện. Nền giấy có noise nhẹ, mực đen,
  một màu nhấn duy nhất là **đỏ chu sa** (màu son dấu triện).
- **Signature**: hình vuông ấn triện — dùng làm logo, favicon, dấu đầu mục,
  huy hiệu hạng 1 trên bảng xếp hạng.
- **Cấu trúc**: phân tách bằng **nét kẻ** (border, đường mảnh), KHÔNG dùng
  shadow mềm hay glassmorphism.
- **Typography**: heading dùng Cormorant Garamond (serif), body dùng
  Be Vietnam Pro. Cả hai hỗ trợ tiếng Việt đầy đủ.
- **Hai chế độ màu**: sáng = giấy dó; tối = sơn mài. Cùng một ngôn ngữ thiết
  kế, chỉ đổi token màu. Tự động theo hệ điều hành + nút gạt thủ công.
- **Màu 7 phái** dùng làm mã màu chức năng (Toái Mộng, Huyết Hà, Thiết Y,
  Tố Vấn, Long Ngâm, Thần Tương, Cửu Linh) — xuất hiện trên chip thành viên
  và pill tên trong danh sách.

Tất cả token màu nằm trong `static/css/foundation.css` (`:root` và
`html[data-theme="dark"]`).

## File CSS

    static/css/foundation.css   — token màu, typography, component nền
                                  (navbar, button, form, card, table)
    static/css/public.css       — trang member: chọn nhân vật, kết quả, BXH
    static/css/leader.css       — khu leader: dashboard, ma trận chuyên cần,
                                  nhật ký quản trị
    static/css/party-board.css  — bảng kéo thả xếp đội hình
    static/css/responsive.css   — điều chỉnh mobile (áp cuối cùng)

## Những gì đã biết là còn yếu / cần góc nhìn mới

1. **Ma trận chuyên cần** (`leader_attendance_history.html`) — bảng rộng,
   cột dính bên trái, phải vuốt ngang trên điện thoại. Đã sửa một lần vì
   cột dính bị trong suốt. Vẫn chưa thật sự thoải mái trên màn hình nhỏ.
2. **Party board** (`leader_party_board.html`) — lưới 5 cột x 6 hàng, 4 tab
   team. Kéo thả trên điện thoại là thao tác khó nhất của cả web.
3. **Dashboard leader** (`leader_dashboard.html`) — bảng nhiều cột
   (tên, phái, 5 trận gần nhất, trạng thái, cập nhật, nút lưu), đông đúc
   trên điện thoại.
4. **Trang nhật ký quản trị** (`leader_admin_log.html`) — mới làm, chưa
   được đánh giá thẩm mỹ lần nào.
5. Toàn bộ web chưa từng được kiểm tra khả năng tiếp cận (accessibility)
   một cách bài bản.

## Ràng buộc khi đề xuất thay đổi

- Không thêm framework JS (không React/Vue). Django template + vanilla JS.
- Bootstrap 5 đang dùng qua CDN — có thể tận dụng, nhưng phần lớn giao diện
  là CSS tự viết đè lên.
- Ưu tiên giữ hệ "Mực & Ấn"; nếu đề xuất đổi hướng thẩm mỹ thì cần lý do rõ.
- Mọi thay đổi màu phải hoạt động ở CẢ hai chế độ sáng/tối.
- Tránh mọi thứ trông "AI generate" — đây là yêu cầu gốc của chủ dự án.

## Cách chạy thử

    cp .env.example .env          # trong đó đã có DEBUG=True
    pip install -r requirements.txt
    python manage.py migrate
    python manage.py seed_demo_data
    python manage.py createsuperuser
    python manage.py runserver

Trang chính: /checkin/ (member) và /leader/dashboard/ (leader, cần đăng nhập).
