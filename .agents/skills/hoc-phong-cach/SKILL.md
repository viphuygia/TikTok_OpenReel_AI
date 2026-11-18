---
name: hoc-phong-cach
description: Phân tích video TikTok mẫu bán chạy trong 01_video_mau (trích xuất khung hình, bóc lời thoại gốc) để rút ra DNA dựng video và lưu thành phong_cach_kenh.md.
---

# Skill `/hoc-phong-cach`: Phân tích DNA dựng video TikTok Shop của kênh

Thực hiện lần lượt các bước sau đây để học phong cách dựng video, nhịp cắt và văn phong từ các video bán chạy nhất của người dùng trong thư mục `01_video_mau`:

## Bước 1: Kiểm tra chất lượng video mẫu đầu vào
1. Liệt kê các tệp trong thư mục `01_video_mau/` (bao gồm cả thư mục con nếu có).
2. Nếu thư mục `01_video_mau/` đang trống, dừng lại và nhắc người dùng chép 2–3 video TikTok bán chạy nhất vào `01_video_mau/` (hoặc tải qua Tab 1 của Dashboard `http://localhost:8000`) rồi chạy lại `/hoc-phong-cach`.
3. Kiểm tra nhanh metadata (qua `ffprobe` hoặc output của `extract_frames.py`): nếu phát hiện tệp `.mp4` không có luồng hình (`width == 0`, tệp chỉ có âm thanh), cảnh báo rõ cho người dùng biết tệp đó bị thiếu hình để thay thế/tải lại.

## Bước 2: Chạy công cụ trích xuất khung hình & lời thoại gốc
Chạy `scripts/extract_frames.py` bằng Python trong môi trường ảo `03_voice_clone/venv`:
- **Windows:**
  ```powershell
  03_voice_clone\venv\Scripts\python.exe scripts/extract_frames.py --source 01_video_mau --fps 1.0 --max-width 540
  ```
- **macOS / Linux:**
  ```bash
  03_voice_clone/venv/bin/python scripts/extract_frames.py --source 01_video_mau --fps 1.0 --max-width 540
  ```

Lệnh này tạo ra:
- Khung hình theo từng giây (`frame_0001.jpg`, `frame_0002.jpg`, ...) trong `04_workspace/frames/01_video_mau/<ten_video>/`
- Bảng tổng hợp metadata: `04_workspace/frames/01_video_mau/manifest.json`
- Lời thoại gốc kèm timestamp: `04_workspace/frames/01_video_mau/loi_thoai_goc.md`

## Bước 3: Trực tiếp xem hình ảnh & đọc lời thoại gốc (Bắt buộc)
1. Dùng `read_file` đọc toàn bộ `04_workspace/frames/01_video_mau/loi_thoai_goc.md` và `04_workspace/frames/01_video_mau/manifest.json` để nắm thời lượng, độ phân giải, số video và toàn bộ lời thoại gốc.
2. Dùng `read_file` **mở xem trực tiếp hình ảnh** (`frame_0001.jpg`, `frame_0002.jpg`, `frame_0003.jpg` cho phần Hook 3 giây đầu, cộng thêm các khung hình giữa video và 3 giây cuối của từng video mẫu). Không được suy đoán hình ảnh chỉ từ lời thoại.
3. Phân tích sâu 6 trục sau:
   - **Hook 3 giây đầu:** Cảnh mở màn là gì (nỗi đau, kết quả trước-sau, khui hàng, sốc giá)? Có chữ tiêu đề lớn trên màn hình không?
   - **Nhịp độ chuyển cảnh (ASL - Average Shot Length):** Trung bình bao nhiêu giây đổi góc máy/cảnh một lần (ví dụ `1.5s–2.5s`)? Tổng thời lượng lý tưởng là bao nhiêu giây?
   - **Bố cục kể chuyện & góc quay sản phẩm:** Trình tự cảnh (Hook -> Vấn đề -> Cận chất liệu/công dụng -> Chứng minh thực tế -> Chốt đơn).
   - **Văn bản & Phụ đề chuẩn OpenReel (9:16):** Font, cỡ chữ, màu chữ/viền/nền, vị trí an toàn theo % màn hình (tránh bị icon bên phải và caption bên dưới của TikTok che khuất).
   - **Văn phong & Tốc độ đọc:** Cách xưng hô (`mình - mọi người`, `em - các bác`, `tui - mấy bà`), từ đệm đặc trưng, tốc độ đọc ước tính (`từ/giây`, gợi ý `--speed` cho F5-TTS từ `0.95` đến `1.15`).
   - **Công thức chốt đơn (CTA):** Cách nhắc giỏ hàng góc trái, nhấn mạnh ưu đãi/freeship/bảo hành ở 3–5 giây cuối.

## Bước 4: Lưu công thức thành `phong_cach_kenh.md`
Ghi kết quả phân tích cụ thể (có số liệu thời lượng, công thức câu chữ và quy tắc cắt dựng) ra `phong_cach_kenh.md` tại thư mục gốc với 6 mục chuẩn:
1. **Tổng quan video mẫu đã phân tích** (tên file, độ phân giải, thời lượng từng video).
2. **DNA Nhịp độ & Cấu trúc Timeline** (độ dài Hook, ASL trung bình mỗi clip, tổng thời lượng mục tiêu, gợi ý `--speed` cho F5-TTS).
3. **Công thức Hook 3 giây đầu** (kèm 3–5 mẫu câu mở đầu áp dụng được ngay).
4. **Quy tắc chọn cảnh & Thứ tự dựng B-roll** (từng chặng theo giây).
5. **Style Văn bản & Phụ đề trong OpenReel** (màu sắc, viền/nền, vị trí vùng an toàn 9:16).
6. **Văn phong xưng hô, Từ khóa đắt & CTA giỏ hàng**.

## Bước 5: Trích xuất `style_dna.json` & Báo cáo cho người dùng
1. Chạy script trích xuất DNA thị giác & ảnh mẫu đại diện:
   ```powershell
   03_voice_clone\venv\Scripts\python.exe scripts/style_dna.py
   ```
   Lệnh này tạo `04_workspace/style_dna.json`, `04_workspace/style_ref_hook.jpg`, và `04_workspace/style_ref_Mid.jpg` để Remotion tái hiện bảng màu đa sắc và bố cục vùng an toàn.
2. Thông báo đã hoàn tất cập nhật [phong_cach_kenh.md](file:///phong_cach_kenh.md) và [style_dna.json](file:///04_workspace/style_dna.json), tóm tắt 3–5 điểm cốt lõi nhất vừa rút ra (nhịp cắt, kiểu hook, xưng hô, tốc độ đọc), sau đó chép video thô vào `02_video_tho/` rồi chạy `/dung-tiktok`.
