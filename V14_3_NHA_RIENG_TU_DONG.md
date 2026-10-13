# V14.3 — Chỉ chọn trường khi đã lưu Nhà riêng

- Khi mở WebApp trên **cùng thiết bị và cùng trình duyệt**, tọa độ Nhà riêng đã lưu được khôi phục tự động từ localStorage. Hành trình mặc định được chuyển thành **Nhà riêng → Trường**.
- Chỉ cần chọn trường: tự lấy đường đi dự kiến từ tọa độ Nhà riêng đã lưu; đồng thời lấy thời tiết ở Nhà riêng và tại trường qua Open-Meteo. Không tự yêu cầu lại quyền GPS.
- Lúc lưu Nhà riêng lần đầu, tự chuyển sang chế độ Nhà riêng → Trường; nếu đã chọn trường thì tính lại hành trình.
- Có thể chuyển thủ công sang **Hiện tại → Trường** (cần GPS) hoặc **Trường → Nhà riêng**. Thời tiết ở điểm Nhà riêng luôn ghi rõ lấy theo tọa độ đã lưu, không phải vị trí GPS hiện tại.
- Vẫn có chức năng cập nhật / xóa Nhà riêng trong menu ⋮. Xóa nhà sẽ trở lại chế độ vị trí hiện tại, không dùng lại tọa độ đã xóa.
- Tránh lẫn dữ liệu thời tiết từ nhà và GPS nếu đổi chế độ, giữ tất cả tính năng bản đồ, PWA, Donate, lịch cập nhật 5 phút và thuật toán Open-Meteo từ V14.2.

## Cách kiểm tra

1. Mở WebApp bằng HTTPS, bấm GPS khi đang ở nhà, chọn **Đặt nhà riêng**.
2. Tắt tab rồi vào lại bằng **cùng địa chỉ web, cùng trình duyệt/thiết bị**.
3. Xác nhận hành trình tự chọn **🏠 Nhà riêng → 🏫 Trường**; bấm chọn trường, không cần bấm GPS. Web tự tính đường.
4. Thử đổi chế độ sang **📍 Hiện tại → 🏫 Trường**; phải yêu cầu GPS nếu chưa định vị, và không gán nhầm nhà thành vị trí hiện tại.
5. Thử xóa Nhà riêng rồi tải lại, xác nhận không còn tự chọn tuyến nhà.

**Lưu ý:** Dữ liệu Nhà riêng nằm trong bộ nhớ trình duyệt trên chính thiết bị, không đồng bộ giữa điện thoại và máy tính hoặc giữa các tên miền web. Xóa dữ liệu website hoặc sử dụng chế độ ẩn danh có thể làm mất tọa độ đã lưu.
