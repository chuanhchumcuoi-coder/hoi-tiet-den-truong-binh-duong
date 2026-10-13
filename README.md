# ĐƯỜNG ĐẾN TRƯỜNG AN TOÀN – V14.1 (chỉ Open-Meteo)

Đây là bản chỉnh từ V14 theo yêu cầu: **loại bỏ khối khí tượng quốc gia**, không tự động sử dụng MET Norway hoặc nguồn thời tiết khác.

## Dữ liệu và giới hạn

- Nguồn duy nhất cho hai thẻ thời tiết GPS và trường học: [Open-Meteo](https://open-meteo.com/).
- Kết quả là **dữ liệu mô hình và dự báo theo tọa độ**, không phải phép đo thực tế ở điện thoại.
- Mốc gọi lại mỗi 5 phút nhằm kiểm tra dữ liệu mới, không đảm bảo mô hình cập nhật 5 phút/lần.
- Mỗi thẻ hiện giờ dữ liệu nguồn và nhãn Open-Meteo. Khả năng mưa là dữ liệu xác suất theo giờ, không phải khẳng định trời đang mưa.
- Khi Open-Meteo tạm lỗi, chỉ dùng kết quả Open-Meteo đã lấy trong tối đa 15 phút **có ghi nhãn dữ liệu cũ**, hoặc hiển thị lỗi để người dùng thử lại. Không thay thế bằng số đo từ nguồn khác.
- Bản đồ, 30 trường, GPS, Nhà riêng, 3 kiểu hành trình, cảnh báo/lời khuyên, logo, PWA được giữ nguyên.
- Liên kết cảnh báo chính thức ở phần ghi chú an toàn chỉ là **liên kết tham khảo**, không phải nguồn dữ liệu tự động của WebApp.

## Chạy local

```bash
pip install -r requirements.txt
python app.py
```

## Đưa lên Render

- Language: Python 3
- Build Command: `pip install -r requirements.txt`
- Start Command: `gunicorn app:app`
- Root Directory: để trống

Kiểm tra `GET /api/health` phải có `weather_provider: Open-Meteo`, và `GET /api/weather-info?school_id=...` để xác nhận dữ liệu.
