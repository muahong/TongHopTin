# Toàn cảnh Việt Nam — bản biên tập ngày 05/09/2026

829 bài gốc từ 15 nguồn được gom thành 254 câu chuyện trong 11 lĩnh vực. Mỗi bài gốc thuộc đúng một nhóm và được dẫn nguồn trong ít nhất một đoạn biên tập. Bài gốc và các bản xuất trước đó được giữ nguyên.

Quy trình dùng Codex CLI đăng nhập ChatGPT: GPT-5.5 gom nhóm và rà soát các trường hợp cần sửa; GPT-5.4-mini viết lại từ toàn bộ 3.509.532 ký tự nội dung đã thu thập. Không cấu hình API key hoặc gọi LLM API riêng; sử dụng hạn mức Codex của tài khoản. Prompt, phản hồi gốc, bản sửa và mã băm đầu vào được lưu trong output/editorial và sao lưu vào kho GitHub riêng tư.

Bản biên tập có giọng gần gũi, hóm hỉnh vừa phải; các chủ đề nhạy cảm giữ giọng nghiêm túc. Đã sửa các trường hợp thiếu/nhầm nguồn, lẫn ngôn ngữ, nhầm ngày đăng với ngày sự kiện, nhầm số liệu đã ghi nhận với kế hoạch và thiếu điều kiện giá sản phẩm. Kiểm tra số liệu là đối chiếu có chọn lọc với nội dung đã thu thập, không phải xác minh độc lập mọi thông tin từ các báo.

Giao diện mới mở mặc định tại URL gốc. Mục lục có phần nhìn nhanh cho từng lĩnh vực; phía dưới là cây câu chuyện trên cùng một trang. Người đọc có thể tìm kiếm hoặc chuyển sang chỉ tiêu đề. Modal có bản tổng hợp, nguồn theo từng đoạn và danh sách bài gốc. ESC/Thoát giữ vị trí đọc. #news vẫn mở bản đọc theo nguồn.

Xác minh: 67 kiểm thử Python đạt; JavaScript hợp lệ; Chromium kiểm tra đầy đủ 829 ID nguồn, 254 nhóm, mặc định Toàn cảnh, mở nguồn/quay lại, ESC/Thoát, tìm kiếm, chế độ gọn và điện thoại không tràn ngang. Cũng sửa việc đổi hash không chuyển tab và thêm thử lại có giới hạn khi Windows tạm khóa file index lúc xuất bản.
