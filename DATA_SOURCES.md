# Ghi chú nguồn dữ liệu

## Phạm vi

Danh sách được xây dựng theo địa giới **tỉnh Bình Dương trước sáp nhập năm 2025**, gồm 9 đơn vị cấp huyện:

- TP. Thủ Dầu Một
- TP. Thuận An
- TP. Dĩ An
- TP. Tân Uyên
- TP. Bến Cát
- H. Bàu Bàng
- H. Dầu Tiếng
- H. Phú Giáo
- H. Bắc Tân Uyên

## Danh sách và địa chỉ trường

Nguồn tổng hợp dùng để khởi tạo dữ liệu:

- https://vi.wikipedia.org/wiki/Danh_sách_trường_trung_học_phổ_thông_tại_Bình_Dương
- https://jes.edu.vn/danh-sach-cac-truong-thpt-tai-binh-duong
- Website công khai của từng trường được lưu trong trường `website` của `data/schools.json`.

Do một số nguồn công khai hiện đã chuyển sang tên đơn vị hành chính sau sáp nhập, tệp JSON ưu tiên giữ cách ghi địa chỉ thuộc Bình Dương trước năm 2025 để phù hợp bản đồ của dự án.

## Tọa độ

- `verified_osm`: đã đối chiếu với dữ liệu bản đồ mở OpenStreetMap/Mapcarta.
- `estimated_from_address`: tọa độ đại diện theo địa chỉ, chưa nên dùng ngay để tính tuyến đường chính thức.
- `user_verified`: đã được người dùng kéo marker và lưu lại trong ứng dụng.

Ứng dụng có sẵn chức năng rà soát tọa độ. Sau khi lưu, dữ liệu được ghi trực tiếp vào `data/schools.json`.

## Bản đồ V3

- Nền bản đồ: Esri World Street Map.
- Ranh giới tỉnh/huyện: GADM 4.1 (2022), truy cập qua ArcGIS FeatureServer `gadm41_VNM_shp`.
- Mục đích: giữ phạm vi Bình Dương trước sáp nhập năm 2025 và che phần ngoài tỉnh.

## Thời tiết V7

- Nguồn API: Open-Meteo Forecast API — `https://api.open-meteo.com/v1/forecast`.
- Tọa độ được gửi riêng cho vị trí GPS học sinh và trường đang chọn.
- Trường dữ liệu hiện tại: nhiệt độ, cảm giác như, độ ẩm, lượng mưa, mã thời tiết, gió.
- Dự báo theo giờ: nhiệt độ, cảm giác như, độ ẩm, xác suất mưa, lượng mưa, mã thời tiết và gió.
- Mốc cập nhật ứng dụng: mỗi 5 phút tính từ 00:00.
- Điều kiện hiện tại của Open-Meteo dựa trên dữ liệu mô hình 15 phút; ứng dụng không tự nội suy hoặc tạo số liệu giả.


## Nguồn thời tiết V7.3

- Nguồn chính: Open-Meteo Forecast API.
- Nguồn dự phòng: MET Norway Locationforecast 2.0 compact API.
- Ứng dụng không tự sinh số liệu; chỉ chuẩn hóa dữ liệu nguồn để hiển thị.
- Khi các nguồn tạm thời không phản hồi, ứng dụng chỉ dùng dữ liệu thành công gần nhất nếu dữ liệu đó chưa quá 90 phút và ghi rõ trạng thái trên giao diện.
