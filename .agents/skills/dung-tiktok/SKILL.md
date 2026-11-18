---
name: dung-tiktok
description: Dựng bộ tài nguyên TikTok Shop hoàn chỉnh từ video thô trong 02_video_tho theo phong_cach_kenh.md (viết kịch bản, nhân bản giọng F5-TTS, xuất phụ đề .srt, cắt clip 9:16 và mở OpenReel Video).
---

# Skill `/dung-tiktok`: Tự động biên tập, lồng tiếng & chuẩn bị Timeline OpenReel Video

Thực hiện đúng quy trình 7 bước dưới đây để biến các clip quay thô trong `02_video_tho` thành bộ tài nguyên hoàn chỉnh sẵn sàng kéo vào trình dựng **OpenReel Video** (và đồng bộ trực tiếp với Webapp Dashboard `http://localhost:8000` Tab 4 & Tab 5):

## Bước 1: Nạp phong cách kênh & kiểm tra nguyên liệu đầu vào
1. Đọc `phong_cach_kenh.md` tại thư mục gốc để nắm chính xác nhịp cắt (ASL), tổng thời lượng mục tiêu, công thức hook, văn phong xưng hô, tốc độ đọc (`--speed`) và câu CTA. Nếu chưa có `phong_cach_kenh.md`, nhắc người dùng chạy `/hoc-phong-cach` trước (hoặc hỏi xác nhận dùng phong cách TikTok Shop mặc định).
2. Kiểm tra thư mục `02_video_tho/` xem có video thô chưa. Nếu trống, dừng lại và nhắc người dùng chép/tải/kéo thả video thô vào `02_video_tho/`.
3. Kiểm tra giọng mẫu tại `03_voice_clone/model/giong_mau.wav` và `03_voice_clone/model/noi_dung_giong_mau.txt` (hoặc `03_voice_clone/`). Nhắc nhẹ nếu đang dùng giọng mẫu cũ/ngắn (< 5 giây) để người dùng có thể thu âm lại trong Tab 2 nếu muốn giống giọng thật hơn.

## Bước 2: Trích xuất & xem trực tiếp khung hình thô từ `02_video_tho`
Chạy `scripts/extract_frames.py` (chỉ trích xuất ảnh, không bóc thoại cho clip thô):
- **Windows:**
  ```powershell
  03_voice_clone\venv\Scripts\python.exe scripts/extract_frames.py --source 02_video_tho --fps 1.0 --max-width 540 --transcribe never
  ```
- **macOS / Linux:**
  ```bash
  03_voice_clone/venv/bin/python scripts/extract_frames.py --source 02_video_tho --fps 1.0 --max-width 540 --transcribe never
  ```

Đọc `04_workspace/frames/02_video_tho/tom_tat_khung_hinh.md` và `04_workspace/frames/02_video_tho/manifest.json`, sau đó dùng `read_file` **xem trực tiếp các ảnh khung hình** (`frame_XXXX.jpg`) trong từng thư mục con để đánh giá chất lượng hình ảnh từng giây (cận chất liệu, cầm tay, khui hộp, test công dụng, loại bỏ đoạn rung tay/mờ/chết hình).

## Bước 3: Viết kịch bản chuẩn F5-TTS & lập kế hoạch cắt `edit_plan.json`
1. **Viết kịch bản (`04_workspace/kich_ban.txt` và `04_workspace/kich_ban_hien_thi.md`):**
   - Bám sát Hook 3s, văn phong xưng hô và CTA trong `phong_cach_kenh.md`.
   - Độ dài lời bình cân đối với tổng thời lượng cảnh đẹp chọn được (tốc độ đọc tiếng Việt tự nhiên khoảng **3.5–4.2 từ/giây**, ví dụ 25 giây ~ 90–105 từ).
   - **QUY TẮC LÀM SẠCH & PHIÊN ÂM BẮT BUỘC cho `04_workspace/kich_ban.txt`:**
     - Chỉ viết văn xuôi thuần có dấu chấm (`.`), dấu phẩy (`,`) để ngắt nhịp thở tự nhiên; **không** dùng emoji, ký tự markdown (`**`, `#`, `-`), dấu ngoặc đơn hoặc xuống dòng vụn.
     - Tự động phiên âm các từ tiếng Anh / viết tắt phổ biến sang cách đọc tiếng Việt: `freeship` -> `phờ ri síp`, `flash sale` -> `phờ lát sêu`, `sale` -> `sêu`, `voucher` -> `vao chờ`, `deal` -> `điu`, `review` -> `ri viu`, `unbox` -> `ăn bóc`, `livestream` -> `lai trym`, `combo` -> `com bo`, `best seller` -> `bét seo lơ`, `feedback` -> `phít bách`, `skincare` -> `xì kin ke`, `serum` -> `xê rum`, `size` -> `sai`, `form` -> `phom`, `check` -> `chếch`, `link` -> `linh`, `tiktok` -> `tích tóc`, `shop` -> `sóp`, `order` -> `o đờ`.
     - Viết số/đơn vị quan trọng thành chữ tiếng Việt nếu dễ đọc nhầm (ví dụ `3in1` -> `ba trong một`, `100%` -> `một trăm phần trăm`).
   - Ghi bản đã phiên âm vào `04_workspace/kich_ban.txt` (UTF-8) và bản giữ nguyên từ gốc đẹp mắt vào `04_workspace/kich_ban_hien_thi.md`.

2. **Xuất cấu trúc cắt dựng (`04_workspace/edit_plan.json`):**
   - Chỉ sử dụng đường dẫn `source` hợp lệ có trong `manifest.json` (`02_video_tho/...`), đảm bảo `0 <= start < end <= duration_sec` của clip gốc.
   - Sắp xếp cảnh theo trình tự Hook -> Cận sản phẩm -> Trải nghiệm/Chứng minh -> Kết quả/CTA với nhịp cắt bám sát ASL trong `phong_cach_kenh.md` (thường `1.5s–3.5s/cảnh`).
   - Đặt `crop_mode`: `"center"` cho clip dọc 9:16 hoặc cần crop giữa; `"blur_bg"` nếu clip ngang muốn giữ toàn khung hình kèm nền mờ.
   - Ghi ra `04_workspace/edit_plan.json` theo cấu trúc:
     ```json
     {
       "title": "Ten san pham",
       "target_resolution": [1080, 1920],
       "target_fps": 30,
       "concat_draft": true,
       "keep_clip_audio": false,
       "clips": [
         {
           "source": "02_video_tho/ten_file.mp4",
           "start": 1.0,
           "end": 3.5,
           "speed": 1.0,
           "mute": true,
           "crop_mode": "center",
           "note": "Hook 2.5s - can canh san pham"
         }
       ]
     }
     ```

## Bước 4: Nhân bản giọng nói thật & Xuất phụ đề `.srt`
Chạy `scripts/voice_engine.py` với `--speed` phù hợp phong cách kênh (mặc định `1.05`):
- **Windows:**
  ```powershell
  03_voice_clone\venv\Scripts\python.exe scripts/voice_engine.py --script 04_workspace/kich_ban.txt --speed 1.05
  ```
- **macOS / Linux:**
  ```bash
  03_voice_clone/venv/bin/python scripts/voice_engine.py --script 04_workspace/kich_ban.txt --speed 1.05
  ```

Kiểm tra kết quả đầu ra và thời lượng audio tại `04_workspace/ready_for_openreel/02_giong_doc_ai.wav` và `04_workspace/ready_for_openreel/03_phu_de.srt`.

## Bước 5: Sơ chế, Cắt clip 9:16 & Khớp thời lượng Hình – Tiếng
Chạy `scripts/prepare_clips.py`:
- **Windows:**
  ```powershell
  03_voice_clone\venv\Scripts\python.exe scripts/prepare_clips.py --config 04_workspace/edit_plan.json --concat
  ```
- **macOS / Linux:**
  ```bash
  03_voice_clone/venv/bin/python scripts/prepare_clips.py --config 04_workspace/edit_plan.json --concat
  ```

Đọc `04_workspace/ready_for_openreel/clips_manifest.json` để so sánh tổng thời lượng video đã cắt với thời lượng của `02_giong_doc_ai.wav`. Nếu chênh lệch `> 1.2 giây`, tự động tinh chỉnh `start`/`end` hoặc `speed` trong `04_workspace/edit_plan.json` rồi chạy lại `prepare_clips.py` để hình và tiếng khớp khít.

## Bước 6: Render Tự Động 100% bằng Remotion Hybrid Graphic Engine
Không cần mở trình duyệt OpenReel thủ công nữa. Chạy lệnh dựng `remotion_props.json` và xuất thẳng `05_output/final_tiktok.mp4` qua Remotion + Bộ Font Việt hóa (`assets/fonts/`) + Stickers (`assets/stickers/`) + BGM/SFX (`06_assets_audio/`):
```powershell
03_voice_clone\venv\Scripts\python.exe -c "import sys; sys.path.insert(0, 'scripts'); import remotion_renderer as rr; print(rr.render_remotion_video())"
```
(Hoặc mở Dashboard `http://localhost:8000` -> Tab 5 **Render Tự Động (Remotion & AI)** -> bấm **Xuất Video MP4 Tự Động 100%**).

## Bước 7: Tự kiểm tra hình ảnh & Báo cáo kết quả
1. Mở xem 3 ảnh kiểm tra tự động trong `04_workspace/render_preview_frames/` (`frame_hook_1s.jpg`, `frame_mid_12s.jpg`, `frame_cta_end.jpg`) để xác nhận Hook Badge hoa lá, nhãn đa sắc và phụ đề Karaoke (`Y = 72%`) không bị tràn khung.
2. Báo cáo cho người dùng đường dẫn thành phẩm [final_tiktok.mp4](file:///05_output/final_tiktok.mp4), tóm tắt kịch bản & thời lượng khớp nhau, kèm hướng dẫn chỉnh sửa nhanh bằng **AI Editor** ở Tab 5 nếu muốn đổi màu/chữ.
