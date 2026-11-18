---
name: motion-director-wow
description: Đạo diễn hình ảnh, kịch bản tự nhiên đa format và thiết kế Motion Graphics sáng tạo cho TikTok Shop (Innovation Remotion & HyperFrames).
---

# Motion Director WOW — Mở Khóa Sáng Tạo Toàn Diện

Skill này định hướng AI thoát khỏi khuôn mẫu cứng khi lên kịch bản, chọn cảnh từ video thô và thiết kế đồ họa chuyển động trên cả **Innovation Remotion** và **HyperFrames**.

## 1. Đa Dạng Hóa Format Kể Chuyện (Storytelling)
Không ép mọi video vào 3 khuôn mẫu cứng. Chọn linh hoạt 3 góc kể chuyện tự nhiên phù hợp nhất với sản phẩm trong `brand_brief.json`:
- **POV Tâm sự / Trải nghiệm thật:** Mở đầu bằng tình huống đời thường gần gũi, giọng kể tự nhiên như người bạn chia sẻ.
- **So sánh / Thử nghiệm trực diện (Test 24h / Before-After):** Đưa thẳng bằng chứng hình ảnh, cảm giác sử dụng thực tế.
- **Bắt trend Q&A / Phản hồi thắc mắc:** Trả lời câu hỏi người mua hay phân vân nhất.
- **Săn Deal / Mở hộp nhanh:** Nhịp dứt khoát, nhấn mạnh giá trị nhận được khi đặt đúng khung giờ.

**Quy tắc tuyệt đối:**
- Không chèn câu đệm sáo rỗng, văn mẫu chung chung.
- Tuân thủ 100% danh sách từ cấm kỵ toàn app (`global_banned_words.json` + `brand_brief.banned_words`).

## 2. AI Visual Scene Matching & Speed Ramp
- Luôn đối chiếu ảnh khung hình trong `04_workspace/frames/02_video_tho/` để khớp **đúng hành động trên hình** với **câu thoại đang đọc**.
- Cho phép biến thiên tốc độ (`speed` từ `0.85` đến `1.35`): tua nhanh nhẹ (`1.25x–1.35x`) ở thao tác phụ/mở hộp, làm chậm (`0.85x–0.92x`) ở đoạn cận cảnh chất sản phẩm.

## 3. Thiết Kế Đồ Họa Độc Bản (HyperFrames Generative Scene & Innovation)
- Tận dụng bảng màu `popPalette` (4–5 màu tương phản), `stickerEvents` đa sắc bật nảy theo beat, và hiệu ứng confetti/vector động.
- Trong **HyperFrames**, kết hợp lớp HTML5 + CSS + SVG + GSAP sáng tạo theo mood sản phẩm, đồng thời giữ nguyên vùng phụ đề `HF_DATA.chunks` rõ nét ở `y ≈ 0.72` và đồng bộ đầy đủ `voice.wav`, `bgm.wav`, `sfx_*.wav`.
