# Kiểm tra chạy tự động TongHopTin — 06/09/2026

## Kết quả kiểm tra ban đầu

- Đây là hai tác vụ Windows Task Scheduler, không phải automation trong Codex. Không có cấu hình Codex automation khớp TongHopTin. GitHub Actions chỉ cho chạy thủ công; lịch cloud vẫn tắt theo chính sách tiết kiệm phút.
- `TongHopTin Startup`: chạy hai phút sau đăng nhập, dùng dấu ngày thành công để bỏ qua các lần đăng nhập tiếp theo. Không có giờ chạy sáng cố định. `TongHopTin 9PM`: chạy 21:00 UTC+7 mỗi ngày.
- Hai task đều có kết quả gần nhất bằng **1 (lỗi)**: tối 05/09 lúc 21:00:01 và sáng 06/09 lúc 09:12:45. Chỉ riêng thông tin task đã được kích hoạt không chứng minh đã xuất bản thành công.
- Tái hiện được lỗi thật bằng `.venv\Scripts\python.exe scripts/build_editorial.py --publish`: `ModuleNotFoundError: No module named 'tonghoptin'`. Cài các dependency không đồng nghĩa đã cài package dự án; chạy script trực tiếp chỉ thêm thư mục `scripts` vào Python import path.
- Crawl sáng 06/09 đã có 455 bài, 19 cấu hình nguồn, 560 lỗi ở cấp nguồn/URL. Năm nguồn không có bài; nhiều nguồn còn lại có lỗi một phần. Đây là mức phủ best effort, không thể coi là thu thập đầy đủ hoặc xác thực mọi thông tin báo chí.
- Private archive có commit sao lưu tối 05/09 và sáng 06/09; website remote vẫn ở commit `aff840d932145c49f5693e76917dc6c4e397eb5f`. Quy trình cũ giữ được bản sao lưu khi biên tập lỗi, nhưng chưa cập nhật website.
- Nhật ký cũ ghi nhận hai lần hoàn tất mỗi ngày từ 27/08 đến 04/09; giờ sáng biến động, có ngày đến 13:10. Nhật ký này không kiểm tra hash của website sau triển khai nên không dùng làm bằng chứng đầy đủ cho xuất bản.

## Thay đổi

1. Sửa import path của script biên tập và tìm Codex CLI trong thư mục cài ứng dụng nếu Task Scheduler không có PATH tạm của Codex desktop. Đã kiểm tra login bằng ChatGPT khi bỏ Codex khỏi PATH. Giữ nguyên hai model và cách biên tập đang dùng; không dùng API key.
2. Kết quả suy luận mới chỉ chuyển thành cache hoàn chỉnh khi CLI trả mã 0 và JSON đọc được. Kết quả dang dở được giữ riêng để tránh dùng lại kết quả thất bại như một batch thành công.
3. `tonghoptin/automation.py` điều khiển toàn bộ thu thập → biên tập → sao lưu riêng tư → đẩy website → kiểm tra website. `run.bat`, wrapper startup và các task dùng chung cơ chế này.
4. Hai lượt theo UTC+7: sáng khi đăng nhập lần đầu hoặc lúc 09:00, tối 21:00. Đăng nhập sau 21:00 dùng chung lượt tối. Dấu thành công theo lượt tránh xuất bản trùng; khóa hệ điều hành chung tránh chạy chồng cả quy trình.
5. Đóng băng đường dẫn crawl report để lần thử lại tiếp tục đúng dữ liệu. Lỗi push không làm thu thập hoặc biên tập lại. Vẫn sao lưu chứng cứ nếu thu thập/biên tập lỗi. Không force-push, tự giải quyết xung đột hoặc xóa tài liệu lịch sử.
6. Các task chạy ẩn, có wake timer, chạy bù khi khả dụng, thử lại tối đa ba lần cách nhau 15 phút. Giới hạn task tăng từ một giờ lên bốn giờ vì nay có thêm biên tập nhiều batch; từng bước cũng có timeout.
7. Chỉ ghi `success` sau khi index trực tuyến có SHA-256 trùng hoàn toàn với bản trong Git commit xuất bản và kiểm tra byte của JSON/JS nội dung cùng một ảnh mẫu. Đối chiếu byte trong Git thay vì tệp Windows để xử lý đúng việc Git chuẩn hóa CRLF sang LF. Có nhật ký từng bước, thời gian, mã lỗi, coverage và trạng thái tại `output/automation/`.
8. Launcher lưu stdout và stderr riêng bằng tiến trình ẩn; tránh Windows PowerShell 5 biến dòng stderr đầu tiên thành lỗi kết thúc và làm mất phần còn lại của traceback.

## Kiểm chứng

- 85 kiểm thử đạt, gồm import độc lập, Codex thiếu PATH, kết quả model lỗi, mất mạng sau biên tập, website cũ, sidecar sai, khóa giữa hai tiến trình, bỏ qua lượt đã thành công, sai ngày dữ liệu, CRLF/LF và các mốc ngày/giờ.
- GitHub Actions cũng đạt trên Ubuntu/Python 3.12 cho commit `7f54e1980ffc2e83806c08ac88219a1dba76ecaa`: [run 34016454766](https://github.com/muahong/TongHopTin/actions/runs/34016454766).
- XML cũ được xuất trước sửa tại `output/automation/scheduler-backup-*`. Đọc lại Windows xác nhận cả hai task Ready, WakeToRun=true, RetryCount=3, RetryInterval=PT15M, ExecutionTimeLimit=PT4H. Lịch kế tiếp: 06/09 21:00 và 07/09 09:00, cùng trigger đăng nhập hiện có.
- Phục hồi thành công lượt sáng từ `output/runs/2026-09-06_091254_50c374a9.json`: 455 bài nguồn, 244 mục biên tập, đầy đủ kiểm tra fingerprint và nguồn trích dẫn. Không thu thập lại khi phục hồi.
- Chạy thực tế qua Windows Task Scheduler: đã sao lưu 3.825 đường dẫn thêm/thay đổi trong một pack mới, rồi đẩy website. Tổng index archive là 347.737 đường dẫn tại thời điểm sao lưu, tiếp tục giữ lịch sử cũ.
- Xác minh website thành công **13:27:23 ngày 06/09/2026 (UTC+7)**. SHA-256 index trực tuyến: `55845ce9d70c4ae44d760c706e0b0a6c5716c601bad65ce3680a87cd1d0005ba`; JSON/JS body và ảnh mẫu cũng khớp byte. [GitHub Pages deployment](https://github.com/muahong/TongHopTin/actions/runs/34016454527) thành công.
- Đã thử gọi lại cả hai launcher lúc 13:27:58: cùng trả `Already verified: 2026-09-06-am`, mã task bằng 0 và hash tệp trạng thái lượt sáng không đổi. Đây là phép thử bỏ qua lượt đã xong, không phải bằng chứng cho lần chạy tối 21:00 chưa diễn ra.
- Trong kiểm chứng, đã dừng bộ kiểm tra website cũ ở giai đoạn chỉ đọc sau khi push xong để áp dụng sửa CRLF/LF. Windows giữ lại tiến trình Python con, nên lần khởi động kế tiếp bị khóa chung chặn đúng; đã dừng riêng tiến trình xác minh cũ và chạy tiếp thành công. Khi dừng tác vụ đang chạy, cần kiểm tra tiến trình con; không xóa lock file để ép chạy chồng.
- Bằng chứng máy đọc được: `reports/automation-verification-2026-09-06.json`. Bản ghi cấu hình trước smoke test: `reports/scheduler-2026-09-06.json`.

## Giới hạn vận hành

Máy phải bật hoặc có thể thức dậy, người dùng Windows phải còn đăng nhập (khóa màn hình được), có mạng và phiên đăng nhập ChatGPT/GitHub còn hợp lệ. Máy tắt hoặc đăng xuất không thể bảo đảm xuất bản đúng giờ bằng lịch cục bộ. Không chuyển sang dịch vụ cloud hay thay đổi chính sách GitHub Actions trong lần sửa này. Wake timer còn phụ thuộc phần cứng và chính sách nguồn điện Windows.

Kiểm tra cấu trúc và trích dẫn giúp phát hiện thiếu bài, thiếu nguồn và dữ liệu cũ; không bảo đảm tuyệt đối độ đúng về nội dung của báo nguồn hoặc bản biên tập AI. Mỗi ngày vẫn thu thập theo phạm vi ngày Việt Nam đã cấu hình. Không suy diễn các snapshot đã bỏ lỡ là đã được tái tạo.

## Tệp vận hành và tham chiếu

- `scripts/configure_schedule.ps1 -InspectOnly`: xem lịch; bỏ tùy chọn để cài lại lịch hiện tại sau khi xuất bản sao XML.
- `output/automation/YYYY-MM-DD-am.json` và `...-pm.json`: trạng thái từng lượt.
- `run.bat --trigger startup`: thử lại lượt hiện tại; đã thành công thì bỏ qua.
- [Tài liệu OpenAI về Codex chạy không tương tác](https://learn.chatgpt.com/docs/non-interactive-mode): đối chiếu `codex exec`, đầu ra JSON schema và chế độ chạy script; các cờ và đăng nhập đã được kiểm tra thêm trên CLI cục bộ.
