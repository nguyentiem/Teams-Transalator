# Teams Meeting Translator 🎙

Dịch realtime từ tiếng Anh → tiếng Việt trong Microsoft Teams.  
Hiển thị song ngữ và lưu transcript sau meeting.

---

## Yêu cầu hệ thống

- Windows 10/11 (64-bit)
- Python 3.9+ (nếu chạy từ source)
- Kết nối Internet (để Google STT và Google Translate hoạt động)

---

## Bước 1: Bật Stereo Mix (bắt buộc)

Ứng dụng cần capture system audio. Windows cần bật "Stereo Mix":

1. Chuột phải vào icon loa góc phải taskbar → **Sounds**
2. Tab **Recording** → chuột phải vào vùng trống → tích **"Show Disabled Devices"**
3. Tìm **"Stereo Mix"** → chuột phải → **Enable**
4. Set Stereo Mix làm **Default Device**

> Nếu không thấy Stereo Mix: vào Device Manager → Sound → Update driver card âm thanh  
> Hoặc dùng virtual audio cable như [VB-CABLE](https://vb-audio.com/Cable/) (miễn phí)

---

## Bước 2: Chạy ứng dụng

### Option A – Chạy file .exe (không cần Python)
```
Chạy TeamsTranslator.exe
```

### Option B – Chạy từ source
```bash
python main.py
```

> Nếu bạn clone project từ repo, thư mục `libs/` đã chứa sẵn dependency nên không cần tải lại.
> Nếu muốn cập nhật dependency trong project, chạy:
> ```bash
> pip install -r requirements.txt -t libs
> ```

### Option C – Build .exe tự
```bash
build.bat
# File .exe sẽ nằm trong thư mục dist/
```

---

## Cách dùng

1. Mở Teams, vào meeting như bình thường
2. Mở **TeamsTranslator.exe**
3. Nhấn **▶ Bắt đầu dịch**
4. Nói chuyện/nghe – transcript song ngữ hiện realtime
5. Nhấn **■ Dừng** khi xong
6. Nhấn **💾 Lưu transcript** để lưu file .txt

---

## Cấu trúc transcript được lưu

```
[09:15:32]
EN: We need to finalize the project timeline by Friday.
VI: Chúng ta cần hoàn thiện tiến độ dự án trước thứ Sáu.
--------------------------------------------------
```

---

## Lưu ý

- Độ trễ khoảng 4-6 giây/đoạn (do chunk 4 giây)
- Chất lượng phụ thuộc vào âm lượng Teams và chất lượng mạng
- Google STT miễn phí có giới hạn nếu dùng rất nhiều liên tục
- Không thu tiếng từ micro của bạn, chỉ thu âm thanh phát ra từ loa/headphone

---

## Troubleshooting

| Lỗi | Giải pháp |
|-----|-----------|
| "Không tìm thấy thiết bị loopback" | Bật Stereo Mix (xem Bước 1) |
| Transcript trống dù có tiếng | Tăng âm lượng Teams, kiểm tra Stereo Mix là default |
| Lỗi Google STT | Kiểm tra kết nối Internet |
| Lỗi dịch | googletrans đôi khi bị rate limit – thử lại sau vài giây |
