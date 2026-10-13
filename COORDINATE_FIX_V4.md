# Rà soát tọa độ trường - V4

Bản V4 chỉ tập trung sửa dữ liệu marker trường; không thay đổi bố cục đã chốt ở V3.

- 12 marker từng dùng tọa độ ước lượng đã được thay bằng vị trí đã đối chiếu.
- Không còn trường nào mang `coordinate_quality = estimated_from_address`.
- 25/30 tọa độ ở mức chính xác cao từ dữ liệu bản đồ/Plus Code.
- 5/30 tọa độ đã khớp listing bản đồ trong phạm vi dưới 100 m; phù hợp hiển thị marker. Trước khi dùng làm điểm đến định tuyến chính thức, có thể tinh chỉnh tiếp đến cổng trường nếu cần.
- Frontend V4 có thêm chốt an toàn: tọa độ nào bị đánh dấu `estimated_from_address` hoặc `unverified*` sẽ không được vẽ marker.

Các marker được rà soát lại trong V4: Dầu Tiếng, Huỳnh Văn Nghệ, Lê Lợi, Long Hòa, Nguyễn An Ninh, THCS & THPT Nguyễn Huệ, Nguyễn Đình Chiểu, Phước Vĩnh, Tân Bình, Tân Phước Khánh, THCS & THPT Tây Sơn, Nguyễn Thị Minh Khai - Bình Dương.
