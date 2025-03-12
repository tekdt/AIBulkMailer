# AIBulkMailer
- Tên phần mềm: AI Bulk Mailer
- Tác giả: TekDT
- Mô tả: Phần mềm gửi email hàng loạt với khả năng hỗ trợ đa luồng, tạo nội dung tự động bằng nhiều mô hình AI và thu thập tất cả email trên một trang web.
- Ngày phát hành: 08-03-2025
- Phiên bản: 1.1.0
- Email: dinhtrungtek@gmail.com
- Telegram: @tekdt1152
- Facebook: @tekdtcom

# Hướng dẫn cài đặt
* Chạy trực tiếp từ script python
- Cài đặt Python3: https://www.python.org/downloads/
- Cài đặt thư viện cần thiết bằng câu lệnh python py -m pip install <tên thư viện>

* Chạy trực tiếp từ file EXE đã biên dịch (khuyến khích)

# Hướng dẫn sử dụng
Ở giao diện chương trình sẽ có tổng cộng 4 tab, bao gồm: GỬI MAIL, TẠO NỘI DUNG TỰ ĐỘNG, THU THẬP EMAIL và THÔNG TIN
- Tab GỬI MAIL: Thiết lập chính để chạy chương trình
+ Email của bạn: Đây là User name mà các dịch vụ SMTP cung cấp, thường sẽ là mail của bạn.
+ Mật khẩu: Đây là Password mà các dịch vụ SMTP cung cấp, thường sẽ là mật khẩu mail, mật khẩu ứng dụng của mail.
+ Tiêu đề: Tiêu đề của mail sẽ gửi đến các mail nhận.
+ Trả lời tới: Khi người nhận nhấn Trả lời mail, thì email tại ô này sẽ là mail được nhận. Ví dụ: bạn gửi từ mail A, nhưng muốn mail B nhận trả lời từ người khác, thì mail B bạn nhập vào ô này.
+ Nội dung mail: Nếu bạn có mẫu mail sẵn, hãy nhập vào ô Soạn thảo trực quan. Nếu bạn có mail sẵn nhưng nội dung là code HTML thì nhập vào ô RAW HTML.
+ Máy chủ SMTP: Chọn máy chủ SMTP theo danh sách có sẵn, nếu không còn nằm trong danh sách thì chọn Khác để điền máy chủ tuỳ chỉnh.
+ Kết nối TLS: Cần chọn đúng kiểu kết nối mà dịch vụ SMTP cung cấp.
+ Thêm danh sách người nhận CSV: Nhập danh sách người nhận, mỗi người nhận một dòng trong tập tin CSV.
+ Gửi mail: Khi thiết lập hoàn tất hãy nhấn nút này. Quá trình gửi mail hàng loạt sẽ bắt đầu.
+ Kiểm tra địa chỉ email trước khi gửi: Nếu tuỳ chọn này được tick, chương trình sẽ kiểm tra địa chỉ email có tồn tại hay không. Việc này sẽ làm kéo dài thời gian gửi mail lên, có khi gây lỗi khi máy chủ SMTP không hỗ trợ. Không khuyến khích sử dụng.

- Tab TẠO NỘI DUNG TỰ ĐỘNG: Thiết lập các thông số cho mô hình để tạo nội dung tự động
+ Máy chủ AI: Hãy chọn AI bạn có sẵn các API. Nếu muốn miễn phí mà vẫn tốt, có thể xem xét chọn Groq, đăng ký một khoá API ở đây: https://console.groq.com/keys
+ Mô hình: Mỗi AI sẽ có rất nhiều mô hình, không phải tất cả chúng đều sử dụng được. Hãy thử từng cái.
+ Nhập yêu cầu cho AI: Đây là khung nhập yêu cầu mà bạn muốn AI tạo nội dung email cho bạn. Ví dụ: Tạo nội dung mail định dạng HTML, giới thiệu phần mềm AI Bulk Mailer, đây là phần mềm gửi email hàng loạt với khả năng hỗ trợ đa luồng, tạo nội dung tự động bằng nhiều mô hình AI và thu thập tất cả email trên một trang web.
+ Tự động tích hợp vào mail: Nếu tuỳ chọn này được tick, chương trình sẽ tự tạo mới nội dung email theo yêu cầu bạn đã nhập ở trên cho mỗi email. Điều này sẽ giúp nội dung email của bạn sẽ đa dạng hơn cho từng người nhận. Tuy nhiên, sẽ làm quá trình gửi mail hàng loạt diễn ra lâu hơn, vì nội dung mail sẽ được tạo mới liên tục.
+ Tạo nội dung: Khi nhấn nút này, sẽ tạo nội dung mail mới dựa theo các tuỳ chọn bạn đã thiết lập ở trên. Nút nhấn này giúp bạn có thể kiểm tra việc tạo nội dung bằng AI có hoạt động không. Hãy thử trước khi bắt đầu gửi mail hàng loạt.
+ Áp dụng cho nội dung mail: Khi bạn tạo nội dung mail từ AI rồi, và muốn sử dụng nội dung mail đó để gửi mail thì nút này sẽ đưa nội dung được bởi AI sang khung nội dung mail (bên tab GỬI MAIL).

- Tab THU THẬP EMAIL: Chương trình sẽ tự động thu thập Email thông qua các trang web
+ Nhập link trang web: Nếu bạn muốn lấy tất cả email có bên trong một trang web, hãy nhập địa chỉ trang web đó vào đây. Chương trình sẽ tự động lọc email. Địa chỉ trang web phải bao gồm http:// hoặc https://
+ Dựa trên Sitemap: Một website sẽ có Sitemap để đánh dấu cho các công cụ tìm kiếm tham chiếu. Chương trình sẽ dựa vào đó để duyệt tìm và lọc tất cả những trang con trên website. Điều này sẽ tốn rất nhiều thời gian, nếu website có nhiều trang con. Không khuyến khích sử dụng tính năng này.
+ Số luồng: Nếu máy tính của bạn đủ mạnh, hãy nâng số luồng lên để chương trình thu thập mail nhanh hơn khi tính năng Dựa trên Sitemap được bật.
+ Thu thập/Dừng: Quá trình thu thập sẽ Bắt đầu hoặc Kết thúc dựa trên 2 nút này.
+ Xuất CSV: Khi quá trình thu thập mail hoàn tất, bạn muốn xuất tập tin CSV để làm việc khác hoặc đơn giản là tạo file CSV để nạp cho chương trình hoạt động thì dùng tính năng này.

- Tab THÔNG TIN: Chứa thông tin về chương trình này

# Trách nhiệm
TekDT không chịu trách nhiệm cho tài khoản của bạn khi bạn tải ở các nguồn khác được tuỳ biến, sửa đổi dựa trên script này. Bạn có thể sử dụng chương trình này miễn phí thì hãy tin nó. TekDT sẽ không thu thập tài khoản tài khoản hay làm bất cứ điều gì với tài khoản của bạn.
Nếu không tin TekDT hoặc sợ mất tài khoản, vui lòng thoát khỏi trang này, hãy xoá phần mềm/script đã tải.

# Hỗ trợ:
Mọi liên lạc của bạn với TekDT sẽ rất hoan nghênh và đón nhận để TekDT có thể cải tiến phần mềm/script này tốt hơn. Hãy thử liên hệ với TekDT bằng những cách sau:
- Telegram: @tekdt1152
- Zalo: 0944.095.092
- Email: dinhtrungtek@gmail.com
- Facebook: @tekdtcom

# Đóng góp:
Để phần mềm/script ngày càng hoàn thiện và nhiều tính năng hơn. TekDT cũng cần có động lực để duy trì. Nếu phần mềm/script này có ích với công việc của bạn, hãy đóng góp một chút. TekDT rất cảm kích việc làm chân thành này của bạn.
- MOMO: https://me.momo.vn/TekDT1152
- Biance ID: 877691831
- USDT (BEP20): 0x53a4f3c22de1caf465ee7b5b6ef26aed9749c721
