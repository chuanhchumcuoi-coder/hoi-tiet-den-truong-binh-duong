# V14.2 - Cài WebApp trên Android và iPhone

- Android: ưu tiên hiển thị hộp thoại cài PWA chính thức khi Chrome phát `beforeinstallprompt`; khi trình duyệt chưa hỗ trợ/cấp quyền, hiển thị hướng dẫn trực quan 3 bước. Web không thể tự cài không cần người dùng xác nhận.
- iPhone: Safari không cung cấp API để website tự bật hộp thoại cài. Nút iPhone hiển thị hình hướng dẫn 3 bước: Safari -> Chia sẻ -> Thêm vào Màn hình chính.
- Nếu đang sử dụng WebApp ở chế độ độc lập, hướng dẫn xác nhận đã cài.
- Nâng phiên bản cache Service Worker để giao diện được làm mới sau khi triển khai.
- Giữ nguyên nguồn Open-Meteo, GPS, Nhà riêng, bản đồ, tuyến đường, cảnh báo, PWA và Donate của V14.1.

**Kiểm thử:** Thử trên Android Chrome và Safari iPhone với domain HTTPS thật. Trình duyệt quyết định có phát `beforeinstallprompt` hay không; không bảo đảm mọi thiết bị đều có hộp thoại cài ngay.
