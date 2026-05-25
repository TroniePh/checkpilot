# Hướng dẫn phát hành bản cập nhật CheckPilot

## Quy trình release mới (ví dụ: v2.3.0)

### Bước 1: Cập nhật version trong code

Sửa version ở 3 chỗ:

1. **`updater.py`** dòng đầu:
   ```python
   CURRENT_VERSION = "2.3.0"
   ```

2. **`installer/CheckPilot.iss`**:
   ```
   #define MyAppVersion "2.3.0"
   ```

3. **`installer/build_release.ps1`**:
   ```powershell
   $Version = "2.3.0"
   ```

### Bước 2: Build installer

```cmd
build.bat
```

Kết quả: `release/CheckPilot_Setup_v2.3.0.exe`

### Bước 3: Upload installer lên GitHub Releases

1. Vào GitHub repo → Releases → Create new release
2. Tag: `v2.3.0`
3. Upload file `CheckPilot_Setup_v2.3.0.exe`
4. Publish

### Bước 4: Cập nhật version.json trên GitHub

Sửa file `version.json` ở branch `main`:

```json
{
  "version": "2.3.0",
  "download_url": "https://github.com/phamduy/checkpilot/releases/download/v2.3.0/CheckPilot_Setup_v2.3.0.exe",
  "changelog": "- Tính năng mới ABC\n- Sửa lỗi XYZ\n- Cải thiện hiệu suất",
  "mandatory": false
}
```

### Bước 5: Xong!

Tất cả khách hàng đang dùng app sẽ:
- Tự động check khi mở app (mỗi 24h check 1 lần)
- Thấy dialog thông báo có bản mới
- Click "Cập nhật ngay" → tải về → cài đặt tự động → app restart

---

## Cách hoạt động chi tiết

```
┌─────────────────────────────────────────────────────┐
│  App khởi động                                       │
│  ↓                                                   │
│  Chờ 2 giây → check version.json trên GitHub        │
│  ↓                                                   │
│  So sánh version: local 2.2.0 vs remote 2.3.0       │
│  ↓ (có bản mới)                                     │
│  Hiện dialog: "Có bản mới v2.3.0"                   │
│  ↓ (user click "Cập nhật ngay")                     │
│  Tải installer .exe về %LOCALAPPDATA%\CheckPilot    │
│  ↓ (tải xong)                                       │
│  Hiện nút "Cài đặt & Khởi động lại"                │
│  ↓ (user click)                                     │
│  Chạy installer /SILENT → tắt app → cài đè → mở   │
└─────────────────────────────────────────────────────┘
```

## Lưu ý

- `mandatory: true` trong version.json → bắt buộc cập nhật (chưa implement, để sau)
- App check tối đa 1 lần/24h để không spam server
- User vẫn có thể check thủ công: Diagnostics → Check update
- Nếu tải thất bại, user có thể thử lại
- File installer cũ tự xóa sau 7 ngày

## URL cần thay đổi

Nếu bạn dùng server riêng thay vì GitHub, sửa URL trong `updater.py`:

```python
VERSION_CHECK_URL = "https://your-server.com/checkpilot/version.json"
```
