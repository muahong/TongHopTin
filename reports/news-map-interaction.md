# Bản đồ tin tức tương tác

Tin tóm tắt nằm trực tiếp trên 11 cụm lĩnh vực bố trí theo vòng tròn. Mỗi cụm hiển thị hai tin mỗi trang; mũi tên tại cụm cho phép đọc các tin còn lại của ngày đã chọn. Không loại bỏ các tin ở những trang sau.

- Cuộn chuột, nút +/− và chụm hai ngón để zoom; kéo để di chuyển.
- Bấm tên lĩnh vực để phóng tới cụm đó; “Toàn bộ bản đồ” đưa về góc nhìn tổng thể.
- Bấm tiêu đề, tóm tắt hoặc nguồn để mở cửa sổ đọc bài.
- Nút Thoát/Đóng hoặc ESC đóng bài; giữ nguyên zoom, vị trí bản đồ, trang tin và vị trí cuộn của trang.
- Có tìm kiếm, chọn ngày và thao tác bàn phím (+, −, 0, các phím mũi tên khi bản đồ có tiêu điểm).

Kiểm tra: 62 kiểm thử Python đạt; JavaScript hợp lệ. Kiểm thử trình duyệt đạt cho 22 thẻ tóm tắt, 11 cụm, kéo, wheel zoom, pinch zoom, chuyển trang lĩnh vực, giữ camera khi đổi tab, ESC/Thoát, giữ vị trí cuộn, và giao diện điện thoại không tràn ngang. Không có lỗi JavaScript.

Chạy lại kiểm thử giao diện khi đang phục vụ dự án qua localhost: `python tests/browser_news_map.py`. Đặt `NEWS_MAP_URL` để kiểm tra bản triển khai. Dữ liệu lần dựng này sử dụng bản crawl đã lưu; không chạy crawl mới cho thay đổi giao diện.

[Toàn cảnh](news-map-overview.png) · [Phóng gần](news-map-zoomed.png) · [Điện thoại](news-map-mobile.png) · [Kết quả kiểm tra](news-map-validation.json)
