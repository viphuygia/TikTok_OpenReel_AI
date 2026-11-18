# TikTok OpenReel AI — Local Zero-Copy Multi-Channel Studio

Hệ thống sản xuất video ngắn TikTok Shop tự động 100% (chạy Local trên GPU NVIDIA, hỗ trợ điều khiển & tải video trực tiếp từ **iPhone**, kết nối từ xa qua **Cloudflare Tunnel**, và nhân bản nhiều kênh TikTok độc lập bằng **Windows Junction**).

---

## Tính năng nổi bật

- **Đa Engine dựng Motion Graphics:** Remotion Classic, Innovation Remotion (Wildcard AI + Lottie khóa theo frame + Light Leak/Grain Overlays), và HyperFrames.
- **Giọng đọc tiếng Việt AI (F5-TTS) & Phụ đề Karaoke (Faster-Whisper):** Tự tách nhịp thở tự nhiên, Mastering âm thanh FFmpeg, auto-duck nhạc nền.
- **Kho tài nguyên tích hợp sẵn:**
  - `420` Sticker động Lottie + `420` Animated WebP + `408` Twemoji Vector SVG
  - `12` Font chữ tiếng Việt (Baloo 2, Montserrat Black, Be Vietnam Pro, Anton, Oswald, Nunito, Quicksand, Bricolage Grotesque, Lora, Paytone One, Dancing Script, Pacifico)
  - `16` Track nhạc nền BGM không bản quyền + `13` hiệu ứng âm thanh SFX
  - `8` Overlay ánh sáng & chất liệu (`light_leak_*`, `bokeh_sparkle`, `film_grain_soft`, `paper_texture_*`, `grid_hud_overlay`)
- **Định danh từng Kênh TikTok:** Bắt buộc đặt Tên Kênh lần đầu mở và hiển thị ngay trên Header/Tab trình duyệt để không nhầm kênh khi chạy song song nhiều kênh.
- **Tối ưu iPhone & Truy cập mọi nơi:**
  - Quét mã QR Wi-Fi nội bộ (độ trễ `0ms`) hoặc bật **Cloudflare Tunnel 1-Click** ngay trên giao diện web để dùng từ 4G/Internet.
  - Có nút **`⬇️ Tải MP4`** và **`📲 Lưu vào Ảnh (iPhone)`** lưu thẳng vào Album Ảnh iPhone bằng 1 chạm.

---

## Cách 1: Cài đặt từ GitHub (Hoặc file ZIP tải từ GitHub)

### Yêu cầu tối thiểu (Windows 10/11)
- Python `3.10` – `3.12` (khuyên dùng `3.11`)
- Node.js `LTS` (`18+` hoặc `20+`)
- FFmpeg (script cài đặt tự hỗ trợ cài qua `winget` nếu máy chưa có)
- GPU NVIDIA CUDA (khuyên dùng, hoặc chạy CPU nếu thử nghiệm)

### Các bước cài đặt
1. Tải mã nguồn về máy (từ GitHub chọn **Code -> Download ZIP** rồi giải nén, hoặc dùng `git clone`):
   ```bash
   git clone <URL_REPO_CUA_BAN> TikTok_OpenReel_AI
   cd TikTok_OpenReel_AI
   ```
2. Bấm đúp file **`install.bat`** (hoặc chạy với đường dẫn thư mục đích tùy chọn: `install.bat "D:\Studio\Kenh_1" 8000`).
   * Script sẽ tự động:
     * Kiểm tra Python, Node.js, FFmpeg.
     * Tạo `03_voice_clone\venv` đúng theo đường dẫn máy mới và cài PyTorch CUDA + F5-TTS + Faster-Whisper + FastAPI.
     * Tự tải file model tiếng Việt `model_last.pt` (`~643 MB`) về `03_voice_clone\model\`.
     * Cài `npm install` cho `remotion_studio` & `hyperframes_studio`.
     * Đồng bộ đủ 1,200+ tài nguyên sang `remotion_studio/public/assets/`.
3. Bấm **`start_studio.bat`** để mở giao diện web (hoặc **`start_server_24_7.bat`** nếu chạy trên PC 24/7).

---

## Cách 2: Mang toàn bộ sang PC 24/7 mạnh hơn (Bỏ qua `projects/` cũ)

Nếu máy hiện tại đã có sẵn đầy đủ model + tài nguyên và bạn muốn đóng gói gọn để chép qua USB/LAN/Drive sang con PC 24/7:

1. Trên máy cũ, mở PowerShell tại thư mục dự án và chạy:
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\pack_portable.ps1
   ```
   Lệnh này tạo ra file **`TikTok_OpenReel_AI_Portable.zip`** (~650 MB, bao gồm toàn bộ Code + Model `model_last.pt` + 420 Sticker + 12 Font + 16 BGM + 13 SFX + 8 Overlays; **tự động loại bỏ sạch** `projects/`, `04_workspace/`, `venv/`, `node_modules/`).
2. Chép file `.zip` sang PC 24/7, giải nén vào thư mục mong muốn (ví dụ `D:\TikTok_Kenh_1`) rồi bấm đúp **`install.bat`** (lần này cài rất nhanh vì đã có sẵn `model_last.pt`).
3. Chạy **`start_server_24_7.bat`** để server chạy liên tục 24/7 ở địa chỉ `0.0.0.0:8000` (tự khởi động lại nếu có sự cố).

---

## Nhân bản cho 3 Kênh TikTok (Mỗi kênh 1 Style & 1 Port riêng)

Khi muốn tách 3 kênh TikTok hoàn toàn độc lập (`Kenh_1` cổng `8000`, `Kenh_2` cổng `8001`, `Kenh_3` cổng `8002`) trên cùng 1 PC:

1. Bấm đúp file **`clone_new_channel.bat`**.
2. Nhập đường dẫn thư mục mới (ví dụ `D:\TikTok_Kenh_2`) và cổng chạy riêng (ví dụ `8001`).
3. Script sử dụng **Windows Junction (`mklink /J`)** để chia sẻ `venv`, `model`, `node_modules`, `assets`, `06_assets_audio` → nhân bản chỉ mất **~3 giây, tốn thêm 0 MB ổ cứng**, trong khi **`projects/`**, **`style_dna.json`**, **`phong_cach_kenh.md`**, **`04_workspace/`** và **`channel_profile.json`** tách biệt 100%.
4. Mở `start_server_24_7.bat` trong thư mục kênh mới và truy cập `http://localhost:8001` → giao diện tự hiện popup yêu cầu đặt **Tên Kênh TikTok** mới ngay lần đầu.

---

## Truy cập từ iPhone (Trong nhà & Ngoài đường)

1. Trên Header góc trên bên phải, bấm nút **`🏠 LAN (...) · QR / Internet`**.
2. **Khi ở nhà (cùng Wi-Fi):** Dùng Camera iPhone quét mã **QR Mạng Wi-Fi Nội Bộ** để mở giao diện tốc độ tối đa và tải video siêu nhanh.
3. **Khi ra ngoài / dùng 4G:** Bấm **`🚀 Bật Internet (1-Click)`** trong cùng Popup — hệ thống tự kiểm tra/tải `cloudflared.exe` và cấp link `https://*.trycloudflare.com` kèm mã QR để quét vào trực tiếp từ mọi nơi.
4. Khi xuất xong video, bấm **`📲 Lưu vào Ảnh (iPhone)`** để lưu thẳng `.mp4` vào Album Ảnh của iPhone và đăng lên TikTok.
