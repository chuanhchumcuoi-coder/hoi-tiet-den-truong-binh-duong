# V9 — Đường đến trường

Giữ nguyên bản đồ, 30 trường, GPS và thời tiết V7.3. Bổ sung: khoảng cách đường bộ, tuyến đường vẽ trên Leaflet, thời gian ước tính, chọn xe máy/ô tô/xe đạp/đi bộ.

## Sử dụng
1. Chạy `CHAY_UNG_DUNG.bat`.
2. Chọn trường và bấm Định vị học sinh (thứ tự bất kỳ).
3. Khi có đủ hai vị trí, app tự gọi `/api/route` và vẽ tuyến đường xanh. Có thể đổi phương tiện hoặc bấm Tính lại đường.

## Nguồn và giới hạn
- Valhalla demo (dữ liệu đường OpenStreetMap), dự phòng OSRM demo cho xe máy/ô tô. Đây là dịch vụ demo công cộng, có thể giới hạn lưu lượng hoặc gián đoạn. Khi triển khai cho đông học sinh cần nhà cung cấp routing có SLA hoặc máy chủ riêng.
- Không có giao thông realtime, không bảo đảm đường xe máy hợp pháp ở mọi đoạn. OSRM dự phòng dùng profile ô tô cho xe máy và ghi rõ.
- Tọa độ trường ở bộ dữ liệu cũ có thể còn sai; cần kiểm chứng trước khi dùng để điều hướng thực tế.
- Không tự vẽ đường thẳng khi dịch vụ routing lỗi; báo lỗi trung thực.
- GPS học sinh chỉ gửi tới Flask local; Flask gửi tọa độ hai điểm tới dịch vụ định tuyến bên ngoài.
