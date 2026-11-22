# Huong Dan Chay Template ACE VONS 02090

## File can dung

- File production: `customer_schedule_data.csv`
- File test rieng template moi: `ace_vons_02090_test_template.csv`
- Thu muc anh: `YUMMI SAFETY CULTURE`
- SafetyCulture profile phai luu trong app: `ace_vons_02090`

## Setup account moi

1. Mo CheckPilot.
2. Vao trang `Tai khoan`.
3. O `Danh sach tai khoan`, bam `+ Them tai khoan` va nhap:
   - Ten account: `ace_vons_02090`
   - Email/mat khau SafetyCulture cua account moi
   - Folder URL: de trong neu template nam o trang Templates chung; neu khach co folder rieng thi dan link folder SafetyCulture vao day.
4. Bam `Luu`.

## Chay test template moi truoc

1. Trang `Tu dong`, buoc 1: chon file `ace_vons_02090_test_template.csv`.
2. Thu muc anh chon thu muc `YUMMI SAFETY CULTURE`.
3. Bam `Kiem tra`.
4. Bam `Tai du lieu`.
5. Buoc 2: chon `Thu – khong submit`.
6. Dong `Chay thu`: bam `Chon muc…`, chon template `ACE Daily Food Safety Log`.
7. Bam `Test` (hoac `Chay thu muc da chon`).
8. Lan dau co the app mo browser de login account moi. Login xong app se luu session rieng cho profile `ace_vons_02090`.
9. Sau khi app dien xong form, kiem tra tren SafetyCulture. Neu dung thi bam `Dung` trong app de ket thuc test.

## Chay production hang ngay

1. Chon file `customer_schedule_data.csv`.
2. Thu muc anh chon thu muc `YUMMI SAFETY CULTURE`.
3. Bam `Kiem tra`, sau do `Tai du lieu`.
4. Vao trang `Lich chay`.
5. Bat `Bat lich chay` va bam `Lay gio tu CSV`.
6. Bam `Luu lich`.
7. Quay lai trang `Tu dong`, bam `Cho lich`.

Slot `17:00` se chay theo block account:

1. Account mac dinh: `Yummi Sushi Closing Checklist`, `Yummi Sushi - 5PM Case Photos`.
2. Account `ace_vons_02090`: `ACE Daily Food Safety Log`.

Neu account `ace_vons_02090` chua co session/credentials, app se bo qua rieng template ACE va gui alert; cac template Yummi trong slot 17:00 van tiep tuc chay.

## Kiem tra runner

Chay lenh:

```powershell
.\venv\Scripts\python.exe main.py --runner --status
```

Dong `Missing account login` phai la `None` truoc khi de runner tu dong chay template ACE.
