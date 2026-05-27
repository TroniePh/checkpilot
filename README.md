# CheckPilot

Inspection Automation Assistant for SafetyCulture.

Thiết kế bởi Phạm Duy. Liên hệ hỗ trợ: 0868609901.

## Mục tiêu

CheckPilot tự động tạo inspection hằng ngày từ file CSV/Excel mẫu. App dùng ngày hiện tại khi chạy Auto Mode, điền dữ liệu, upload ảnh và chỉ Complete/Submit khi dữ liệu đã validate và automation không ghi nhận lỗi item.

## Chế độ chạy

Auto Mode là chế độ vận hành chính cho khách. Scheduler luôn dùng Auto Mode, tự dùng ngày hôm nay, không hiện popup confirm và không dừng trước submit.

Test mode - không auto submit dùng để setup hoặc kiểm thử template. App nhập dữ liệu, upload ảnh, đi tới cuối inspection và dừng trước Complete/Submit để người dùng kiểm tra thủ công.

## Dữ liệu đầu vào

Các cột bắt buộc:

| Cột | Ý nghĩa |
| --- | --- |
| `template_name` | Tên template trên SafetyCulture |
| `site_location` | Site/location cần chọn |
| `inspection_date` | Ngày inspection; Auto Mode có thể tự đổi sang hôm nay |
| `section` | Tên section |
| `question` | Câu hỏi cần trả lời |
| `answer` | Câu trả lời cần nhập/chọn |

Các cột tùy chọn:

| Cột | Ý nghĩa |
| --- | --- |
| `notes` | Ghi chú |
| `image_path` | Tên ảnh, nhiều ảnh ngăn cách bằng dấu `;` |
| `image_required` | `yes/true/1` nếu ảnh bắt buộc |
| `question_alias` | Text phụ để tìm câu hỏi khi SafetyCulture hiển thị khác |

## Quy trình chạy

1. Chọn file CSV/Excel.
2. Chọn thư mục ảnh.
3. Bấm Validate.
4. Nếu thiếu ảnh, app hiển thị cảnh báo “Có ảnh không tìm thấy. Bạn có muốn tiếp tục không?”
5. Bấm Load.
6. Chọn Auto Mode hoặc Test mode.
7. Bấm Start.

App lưu lại file dữ liệu và thư mục ảnh đã chọn để Scheduler có thể tự nạp lại khi mở app.

## Các lớp an toàn đã có

- Validate thiếu cột, thiếu question, thiếu answer trước khi Start.
- Scheduler không chạy nếu file hiện tại chưa validate OK.
- Không click answer nếu không tìm đúng question container.
- Không submit nếu có item error.
- Không submit nếu upload ảnh bắt buộc lỗi.
- Chụp screenshot và lưu HTML dump khi lỗi quan trọng.
- Template lock chỉ dùng để cảnh báo/setup; Auto Mode không bị chặn nếu CSV đã validate OK.
- Run lock theo ngày để tránh submit trùng template/site trong cùng ngày.
- Health check trước khi chạy automation.
- Report HTML sau mỗi inspection.
- Telegram alert nếu được cấu hình.
- Nếu SafetyCulture hiện popup "An error has occurred", app bỏ draft lỗi và chạy lại đúng template đó tối đa 3 lần.
- Telegram lỗi gửi thêm template, site, câu hỏi hiện tại, URL và các lỗi item gần nhất.
- Auto Mode tự dừng sau 3 template lỗi liên tiếp để tránh submit/chạy sai hàng loạt khi website hoặc dữ liệu có vấn đề.

## Scheduler

Scheduler hỗ trợ nhiều giờ chạy trong ngày. Khi tới giờ, app tự load file đã lưu, validate, đặt ngày hôm nay, tắt Test mode và bật Auto submit.

Nếu app chưa có file dữ liệu hoặc validate không đạt, lịch chạy sẽ dừng và ghi log.

Khi lịch đang bật, bấm Start ở Auto Mode sẽ không chạy ngay nếu chưa tới đúng phút đã set. Ví dụ lịch đặt `05:30`, nếu bấm Start lúc `05:10` thì app chuyển sang trạng thái chờ và tự chạy lúc `05:30`. Nếu bấm đúng trong phút `05:30` thì app chạy Auto Mode ngay và đánh dấu slot đó đã chạy để tránh chạy trùng.

Nếu Windows/app mở lại sau giờ lịch nhưng còn trong khoảng chạy bù mặc định 180 phút, scheduler sẽ chạy bù slot vừa trễ. Ví dụ lịch `17:30`, máy có điện lại lúc `17:32` thì runner sẽ tự chạy Auto Mode cho slot `17:30`.

## Khởi động cùng Windows

Trong Settings, mục Windows có 2 lựa chọn:

- “Mở app sau khi user login”: mở GUI CheckPilot sau khi user đăng nhập Windows.
- “Runner nền trước login (headless)”: tạo Windows Task Scheduler task chạy khi máy boot, không cần mở GUI, chờ đúng lịch rồi chạy Auto Mode.

Runner trước login dùng `main.py --runner --watch` và ép browser chạy headless. Windows không cho app GUI điều khiển desktop trước khi có user session, nên chế độ trước login bắt buộc dùng runner nền.

Điều kiện để runner trước login chạy ổn định:

- SafetyCulture session hoặc credentials đã được lưu trong CheckPilot.
- File CSV/Excel và thư mục ảnh là đường dẫn local máy này, account chạy task có quyền đọc.
- Nếu dữ liệu có ảnh thiếu, phải mở GUI, bấm Validate và xác nhận tiếp tục trước; runner nền không hiện popup confirm.
- Nếu SafetyCulture yêu cầu MFA/manual login, runner sẽ dừng và gửi Telegram lỗi vì trước login không có người thao tác.

Khi lịch đang bật, bấm Start ở Auto Mode sẽ không chạy sớm nếu chưa tới đúng phút đã set. Runner nền cũng dùng logic này: ví dụ lịch `05:30`, máy boot lúc `05:10` thì runner chờ tới `05:30` mới chạy.

Nếu máy boot lại sau giờ lịch nhưng còn trong khoảng chạy bù mặc định 180 phút, runner nền sẽ chạy bù slot đó.

## Telegram nhiều người nhận

Trong Settings, mục Telegram Alerts:

1. Nhập Bot Token.
2. Nhập nhiều Chat ID bằng dấu phẩy, ví dụ `123456, 987654`.
3. Tick “Bật thông báo”.
4. Bấm Lưu rồi Test.

Khi automation lỗi, app gửi tin nhắn và ảnh screenshot lỗi tới toàn bộ Chat ID đã cấu hình.

## Cấu hình thư mục template

Mặc định app mở trang Templates của SafetyCulture. Nếu khách cần vào thẳng một folder template cụ thể, vào Settings, mục Templates, dán Template folder URL rồi bấm Lưu.

Có thể cấu hình bằng biến môi trường nếu cần triển khai nâng cao:

`CHECKPILOT_TEMPLATE_FOLDER_URL=https://app.safetyculture.com/templates/folders/...`

Không hardcode folder khách hàng trong source code.

## Kiểm tra dev

Chạy kiểm tra cú pháp:

```powershell
.\venv\Scripts\python.exe -m py_compile auth.py automation.py backup.py config.py data_loader.py gui.py history.py main.py notifier.py reporter.py runlock.py scheduler.py session_manager.py template_lock.py tray.py updater.py watchdog.py app_settings.py runner.py
```

Load sample:

```powershell
.\venv\Scripts\python.exe -c "from data_loader import load_data, validate_detailed; print(len(load_data('sample_data.csv','assets'))); print(validate_detailed('sample_data.csv','assets')['stats'])"
```

Kiểm tra runner nền không mở GUI:

```powershell
.\venv\Scripts\python.exe main.py --runner --status
```

Không build installer trừ khi chuẩn bị release final.
