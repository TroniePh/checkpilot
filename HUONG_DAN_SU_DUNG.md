# Hướng dẫn sử dụng CheckPilot

**Phần mềm tự động điền checklist SafetyCulture**  
Hỗ trợ: Phạm Duy — 0868609901 (Zalo/Call)

---

## Cài đặt

Chạy file `CheckPilot_Setup_vX.X.X.exe` → Next → Next → Done. Xong.

Phần mềm cài vào `AppData\Local\Programs\CheckPilot`, không cần quyền Admin.

Từ lần sau mở app bằng shortcut CheckPilot trên Desktop hoặc Start Menu.

---

## Đăng nhập lần đầu

Mở app lên sẽ thấy màn hình login.

- User mặc định: `admin`
- Pass mặc định: `admin123`

Lần đầu đăng nhập sẽ bắt đổi mật khẩu. Đổi xong đăng nhập lại bằng pass mới.

---

## Chuẩn bị file dữ liệu (quan trọng nhất)

Đây là bước quyết định phần mềm chạy đúng hay sai. Anh cần tạo 1 file Excel (.xlsx) hoặc CSV.

### Các cột cần có:

| Tên cột | Ghi gì vào | Lưu ý |
|---------|------------|-------|
| site_location | Tên nhà hàng | Ví dụ: Nhà hàng Sushi ABC |
| inspection_date | Ngày kiểm tra | Format: 2024-12-15 (năm-tháng-ngày) |
| template_name | Tên template trên SafetyCulture | **Phải copy đúng 100%** từ web |
| section | Tên mục/phần | Ví dụ: Fire Safety, Equipment |
| question | Câu hỏi | **Phải copy đúng 100%** từ web |
| answer | Đáp án | Yes / No / N/A / Safe / At Risk... |
| notes | Ghi chú (nếu cần) | Để trống nếu không có |
| image_path | Tên file ảnh (nếu cần) | Để trống nếu không có |

### Ví dụ thực tế:

```
site_location,inspection_date,template_name,section,question,answer,notes,image_path
Nhà máy Bình Dương,2024-12-20,Daily Safety Check,Thiết bị PCCC,Bình chữa cháy còn hạn sử dụng?,Yes,Hạn đến 06/2025,binh_chua_chay.jpg
Nhà máy Bình Dương,2024-12-20,Daily Safety Check,Thiết bị PCCC,Vòi nước chữa cháy hoạt động tốt?,Yes,,
Nhà máy Bình Dương,2024-12-20,Daily Safety Check,Lối thoát hiểm,Lối thoát không bị chắn?,No,Có thùng hàng chắn,loi_thoat_bi_chan.jpg
Nhà máy Bình Dương,2024-12-20,Daily Safety Check,Lối thoát hiểm,Biển báo thoát hiểm sáng đèn?,Yes,,
```

### Mẹo quan trọng:

1. **Tên template** — Vào SafetyCulture trên web, copy nguyên tên template paste vào Excel. Sai 1 chữ là không tìm được.

2. **Câu hỏi** — Tương tự, copy nguyên câu hỏi từ web. Đừng tự gõ lại vì dễ sai dấu cách, dấu chấm.

3. **Đáp án** — Chỉ dùng các giá trị sau:
   - `Yes` / `No` / `N/A`
   - `Safe` / `At Risk`
   - `Pass` / `Fail`
   - `Compliant` / `Non-Compliant`
   - `Good` / `Satisfactory` / `Unsatisfactory`

4. **Ảnh** — Nếu 1 câu cần nhiều ảnh, ngăn cách bằng dấu chấm phẩy: `anh1.jpg;anh2.jpg`

5. **Ngày** — Nếu bạn tick "Ngày = hôm nay" trong app thì cột inspection_date sẽ bị bỏ qua, app tự lấy ngày hiện tại.

---

## Chuẩn bị ảnh

Tạo 1 thư mục riêng, bỏ hết ảnh vào đó. Ví dụ:

```
📁 D:\Ảnh kiểm tra\
├── binh_chua_chay.jpg
├── loi_thoat_bi_chan.jpg
├── bang_dien.png
└── ...
```

Trong file Excel cột `image_path` chỉ cần ghi tên file (không cần đường dẫn đầy đủ). Khi chạy app sẽ hỏi bạn chọn thư mục ảnh.

Hỗ trợ: JPG, PNG.

---

## Chạy phần mềm

Trang **Tự động** chia làm 3 bước, làm lần lượt từ trên xuống.

### Bước 1: Dữ liệu

1. Dòng **File dữ liệu** → bấm **Đổi…** → chọn file Excel/CSV
2. Dòng **Thư mục ảnh** → bấm **Đổi…** → chọn thư mục chứa ảnh (bỏ qua nếu không có ảnh)
3. Bấm **Kiểm tra** để soát lỗi file. App sẽ báo (chi tiết ở khung **Nhật ký** phía dưới):
   - Thiếu cột nào
   - Câu hỏi nào trống
   - Đáp án nào không nhận diện được
   - Ảnh nào không tìm thấy

   Sửa xong bấm **Kiểm tra** lại cho đến khi hiện "Dữ liệu hợp lệ".
4. Bấm **Tải dữ liệu** → thấy dòng xanh "✓ X inspection · Y mục" là OK

### Chạy thử (lần đầu bắt buộc)

Vẫn ở Bước 1, dòng **Chạy thử**: bấm **Chọn mục…** → chọn 1 inspection → bấm **Chạy thử mục đã chọn** → app hiện bảng xem trước dữ liệu sẽ điền → bấm "Chạy thử".

App sẽ:
- Mở trình duyệt
- Vào SafetyCulture
- Tìm template
- Điền inspection đã chọn
- **DỪNG LẠI** — không submit

Bạn kiểm tra trên trình duyệt xem điền đúng chưa. Nếu OK → đóng trình duyệt → chạy thật.

### Bước 2: Chế độ

Chọn 1 trong 2 chế độ:
- **Thử – không submit** — chỉ điền form, không bấm Complete/Submit
- **Tự động submit** — tự bấm Complete/Submit khi điền xong

Tùy chọn thêm:
- ☑ **Ngày = hôm nay** — tự lấy ngày hiện tại thay vì ngày trong file
- ☑ **Tạm dừng sau mỗi inspection** — dừng giữa mỗi inspection để bạn kiểm tra (nên bật lúc đầu), bấm **Tiếp tục** để chạy tiếp

### Bước 3: Chạy

- **▶ Chạy ngay** — chạy toàn bộ file ngay bây giờ
- **Chờ lịch** — chờ đến giờ trong trang **Lịch chạy** rồi tự chạy
- **Tạm dừng / Tiếp tục** — tạm dừng hoặc chạy tiếp
- **Dừng** — dừng hẳn
- **Chạy lại lỗi** — chạy lại những inspection bị lỗi

Thanh tiến trình và dòng "x/y inspection · Thành công · Lỗi · Còn lại" cho biết đang chạy tới đâu. Khung **Nhật ký** có thể bấm **Thu gọn** / **Mở rộng**.

---

## Đăng nhập SafetyCulture tự động

Để không phải login SafetyCulture mỗi lần:

1. Vào trang **Tài khoản**
2. Mục **Tài khoản mặc định** → nhập email + mật khẩu SafetyCulture
3. Bấm **Lưu**

Nếu file có nhiều account (cột account), thêm từng account ở mục **Danh sách tài khoản** → **+ Thêm tài khoản**. Nhấp đúp vào một dòng để sửa.

Từ lần sau app tự đăng nhập luôn, không cần thao tác gì.

---

## Lịch chạy tự động

Muốn app tự chạy mỗi ngày mà không cần mở lên bấm Chạy ngay:

1. Vào trang **Lịch chạy**
2. Bật công tắc **"Bật lịch chạy"**
3. Thêm giờ chạy (ví dụ 05:00, 14:00) — bấm **"+ Thêm giờ"** để thêm nhiều lần/ngày, hoặc **"Lấy giờ từ CSV"**
4. Tick ngày trong tuần muốn chạy
5. Bấm **Lưu lịch**
6. Quay lại trang **Tự động** → bấm **Chờ lịch**

**Điều kiện:** Máy tính phải bật 24/7 và app CheckPilot phải đang mở (có thể bấm **Thu nhỏ** xuống khay hệ thống).

**Lưu ý:** Phải bấm **Tải dữ liệu** trước khi bật lịch chạy. App sẽ chạy dữ liệu đã tải.

---

## Telegram thông báo

Muốn nhận thông báo khi chạy xong hoặc bị lỗi:

1. Tạo bot Telegram (hỏi @BotFather trên Telegram)
2. Lấy Bot Token + Chat ID
3. Vào **Cài đặt** → mục **Thông báo Telegram** → nhập Bot token + Chat ID → tick "Bật thông báo" → Lưu
4. Click **Test** để thử

---

## Cập nhật phần mềm

Khi có bản mới, app sẽ tự hiện thông báo khi anh mở lên:

> "Có bản cập nhật mới! v2.3.2 → v2.4.0"

Click **"Cập nhật ngay"** → chờ tải → click **"Cài đặt & Khởi động lại"** → xong.

Không cần tải thủ công, không cần liên hệ hỗ trợ.

---

## Lỗi thường gặp

### "Template not found"
→ Tên template trong file Excel không khớp với tên trên SafetyCulture. Copy lại cho đúng.

### "Question not found on page"
→ Câu hỏi trong Excel không khớp. Có thể SafetyCulture đã đổi nội dung câu hỏi. Copy lại từ web.

### "Login timeout"
→ Không đăng nhập được SafetyCulture. Kiểm tra:
- Internet có ổn không
- Email/password SafetyCulture có đúng không
- Tài khoản có bị khóa không

### "Answer button not found"
→ Đáp án trong file không khớp với nút trên web. Kiểm tra lại cột answer, chỉ dùng các giá trị cho phép.

### App tự tắt hoặc treo
→ Kiểm tra RAM máy (cần ít nhất 4GB trống). Trình duyệt tự động ngốn khá nhiều RAM.

---

## Mẹo sử dụng

1. **Lần đầu dùng template mới** → luôn chạy thử trước, đừng chạy auto ngay.

2. **File Excel lớn** → chia nhỏ theo site hoặc theo template, dễ quản lý hơn.

3. **Ảnh nặng** → nén ảnh xuống dưới 2MB/ảnh, upload sẽ nhanh hơn.

4. **Máy yếu** → tắt bớt Chrome/Firefox đang mở, để RAM cho app.

5. **Muốn xem lịch sử** → tab "Lịch sử" hiện toàn bộ các lần chạy, thành công/thất bại.

6. **Quên mật khẩu app** → liên hệ 0868609901 để reset.

---

## Liên hệ hỗ trợ

Gặp vấn đề gì không tự xử lý được:

- **Zalo/Call:** 0868609901 (Phạm Duy)
- **Giờ hỗ trợ:** 8:00 - 22:00 hàng ngày

Khi liên hệ, gửi kèm:
- Screenshot lỗi
- File log (vào trang Chẩn đoán → Mở thư mục → Nhật ký)
- File Excel đang dùng (nếu liên quan đến dữ liệu)
