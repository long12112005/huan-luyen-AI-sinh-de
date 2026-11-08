# BÁO CÁO ĐỒ ÁN / BÀI TẬP LỚN CUỐI KỲ
## ĐỀ TÀI: XÂY DỰNG HỆ THỐNG WEB HUẤN LUYỆN AI VÀ TỰ ĐỘNG SINH ĐỀ THI TRẮC NGHIỆM TỪ TÀI LIỆU

## LỜI CẢM ƠN
Nhóm thực hiện xin gửi lời cảm ơn chân thành đến Giảng viên hướng dẫn đã tận tình định hướng chuyên môn và phương pháp xây dựng hệ thống phần mềm kết hợp trí tuệ nhân tạo trong suốt quá trình thực hiện đề tài.

## TÓM TẮT BÁO CÁO (ABSTRACT)
Báo cáo trình bày quy trình nghiên cứu, huấn luyện mô hình ngôn ngữ lớn **Qwen2.5-7B-Instruct** bằng kỹ thuật **QLoRA 4-bit** và xây dựng hoàn chỉnh **Hệ thống Web Application (AI ExamGen Platform)** hỗ trợ tự động sinh đề thi trắc nghiệm từ tài liệu của người dùng. Hệ thống được thiết kế theo kiến trúc phần mềm phân tầng rõ ràng (`backend/`, `ai_training/`, `frontend/`, `data/`), cho phép người dùng **Đăng ký / Đăng nhập tài khoản cá nhân**, **Đọc trực tiếp tệp tài liệu (`.pdf`, `.docx`, `.txt`, `.md`, `.json`)**, **Tùy chọn số lượng câu hỏi muốn sinh ra (từ 1 đến 50 câu)** theo thang đo nhận thức Bloom, **Lưu trữ bộ đề và lịch sử hoạt động theo từng tài khoản** trên cơ sở dữ liệu quan hệ SQLite (7 bảng), **Làm bài thi thử chấm điểm tự động** và **Xuất bộ đề ra tệp Microsoft Word (`.docx` bản Giáo viên có đáp án và bản Học sinh ẩn đáp án)**.

---

## CHƯƠNG 1: TỔNG QUAN ĐỀ TÀI

### 1.1. Đặt vấn đề và Bối cảnh thực tế
Việc biên soạn đề thi trắc nghiệm khách quan từ giáo trình, tài liệu giảng dạy đòi hỏi nhiều thời gian của giáo viên để đảm bảo tính chính xác kiến thức, cân đối độ khó theo thang đo Bloom và thiết kế các phương án nhiễu (distractors) hợp lý. Khi sử dụng các công cụ AI rời rạc hoặc kịch bản thử nghiệm đơn lẻ, người dùng thiếu một môi trường Web đồng bộ để quản lý tài khoản cá nhân, đọc trực tiếp tệp tài liệu `.docx`, tùy chỉnh số lượng câu hỏi cần tạo, lưu trữ lịch sử bộ đề và xuất bản ra định dạng in ấn chuẩn khảo thí. Do đó, việc xây dựng một **Hệ thống Web Application hoàn chỉnh tích hợp quy trình huấn luyện AI sinh đề** là yêu cầu cấp thiết và có giá trị thực tiễn cao.

### 1.2. Mục tiêu của đề tài
1. **Xây dựng quy trình huấn luyện AI (`ai_training/`):** Chuẩn hóa tập dữ liệu câu hỏi trắc nghiệm theo định dạng `ChatML` (`data/training_dataset.json`), tinh chỉnh mô hình bằng kỹ thuật ma trận hạng thấp LoRA/QLoRA (`ai_training/train_qlora.py`) và đánh giá chất lượng tự động (`ai_training/evaluator.py`).
2. **Phát triển hệ thống Backend & Cơ sở dữ liệu (`backend/`):** Thiết kế cơ sở dữ liệu SQLite gồm 7 bảng chuẩn hóa (`users`, `sessions`, `documents`, `exams`, `questions`, `activity_history`, `quiz_attempts`), tích hợp xác thực bảo mật `PBKDF2-HMAC-SHA256`, bộ đọc tài liệu đa định dạng và bộ máy sinh đề bám sát ngữ cảnh.
3. **Xây dựng giao diện Web thân thiện, dễ sử dụng (`frontend/`):** Hỗ trợ trọn vẹn luồng nghiệp vụ từ Đăng nhập/Đăng ký $\rightarrow$ Tải tài liệu & chọn số câu hỏi $\rightarrow$ Xem, sửa, lưu & xuất bộ đề $\rightarrow$ Làm bài thi thử & theo dõi lịch sử tài khoản.

---

## CHƯƠNG 2: CƠ SỞ LÝ THUYẾT

### 2.1. Bài toán Sinh câu hỏi tự động bám sát tài liệu (Context-Grounded AQG)
Cho văn bản tài liệu đầu vào $C$, môn học $S$, tổng số câu hỏi người dùng yêu cầu $N \in [1, 50]$ và phân bố mức độ nhận thức theo thang đo Bloom $L \in \{\text{Nhận biết}, \text{Thông hiểu}, \text{Vận dụng}, \text{Vận dụng cao}\}$. Hệ thống phân tích các mệnh đề ngữ nghĩa trong $C$ và sinh ra danh sách $N$ câu hỏi có cấu trúc chuẩn $Y_i = (Q_i, O_A, O_B, O_C, O_D, K_i, E_i)$ sao cho đáp án đúng $K_i$ và lời giải thích $E_i$ hoàn toàn căn cứ trên tài liệu gốc $C$, triệt tiêu hiện tượng ảo giác kiến thức (hallucination).

### 2.2. Kỹ thuật Tinh chỉnh Ma trận Hạng thấp (LoRA & QLoRA)
Thay vì cập nhật toàn bộ ma trận trọng số gốc $W_0 \in \mathbb{R}^{d \times k}$, kỹ thuật **LoRA (Low-Rank Adaptation)** đóng băng $W_0$ và biểu diễn phần cập nhật thông qua hai ma trận hạng thấp $A \in \mathbb{R}^{r \times k}$ và $B \in \mathbb{R}^{d \times r}$ với $r \ll \min(d, k)$:

$$h = W_0 x + \frac{\alpha}{r} B A x$$

Kết hợp với lượng tử hóa **4-bit NormalFloat (NF4)** của QLoRA, dung lượng bộ nhớ cần thiết giảm hơn 70% trong khi vẫn duy trì tỷ lệ tuân thủ cấu trúc JSON đạt **99,2%**.

---

## CHƯƠNG 3: PHÂN TÍCH THIẾT KẾ HỆ THỐNG VÀ DỮ LIỆU

### 3.1. Kiến trúc Phần mềm Phân tầng (Modular Architecture)
Hệ thống được tổ chức thành 4 phân hệ độc lập nhưng liên kết chặt chẽ thông qua RESTful API như minh họa tại **Hình 3.1**:

![Hình 3.1: Kiến trúc phần mềm hệ thống Web AI Sinh Đề Thi](docs/figures/fig1_architecture.png)

### 3.2. Thiết kế Cơ sở dữ liệu Quan hệ SQLite (7 Bảng Chuẩn hóa)

| STT | Tên bảng (Table) | Khóa chính & Khóa ngoại | Chức năng lưu trữ trong hệ thống |
| :---: | :--- | :--- | :--- |
| **1** | `users` | `id` (PK), `email` (Unique) | Lưu thông tin tài khoản người dùng, vai trò và mật khẩu băm `PBKDF2-SHA256` |
| **2** | `sessions` | `token` (PK), `user_id` (FK) | Quản lý phiên đăng nhập xác thực `Bearer Token` của từng người dùng |
| **3** | `documents` | `id` (PK), `user_id` (FK) | Lưu kho tài liệu (`.docx`, `.txt`, `.md`) người dùng đã đọc để tái sử dụng |
| **4** | `exams` | `id` (PK), `user_id` (FK), `document_id` (FK) | Lưu thông tin các bộ đề thi gắn riêng với từng tài khoản người dùng |
| **5** | `questions` | `id` (PK), `exam_id` (FK) | Lưu nội dung câu hỏi, mức độ Bloom, 4 phương án A/B/C/D, đáp án & giải thích |
| **6** | `activity_history` | `id` (PK), `user_id` (FK) | Lưu lịch sử hoạt động chi tiết (tải tài liệu, sinh đề, sửa đề, xuất file, thi thử) |
| **7** | `quiz_attempts` | `id` (PK), `user_id` (FK), `exam_id` (FK) | Lưu lịch sử điểm số, thời gian làm bài và chi tiết đáp án các lần thi thử |

### 3.3. Chuẩn hóa Tập dữ liệu Huấn luyện và Phân bố Thang đo Bloom
Tập dữ liệu huấn luyện và bộ máy sinh đề được thiết kế đảm bảo tính cân bằng vị trí đáp án đúng (`A, B, C, D` mỗi nhãn chiếm ~25% như **Hình 3.2**) và phân bổ chuẩn theo 4 cấp độ nhận thức của thang đo Bloom (**Hình 3.3**).

![Hình 3.2: Phân bố cân bằng nhãn đáp án đúng A, B, C, D](docs/figures/fig2_answers.png)

![Hình 3.3: Tỷ lệ phân bố câu hỏi theo thang đo nhận thức Bloom](docs/figures/fig3_bloom.png)

---

## CHƯƠNG 4: THỰC NGHIỆM, ĐÁNH GIÁ VÀ TRIỂN KHAI WEB

### 4.1. Kết quả Huấn luyện Mô hình (`ai_training/train_qlora.py`)
Quá trình tối ưu hóa ma trận thích nghi hạng thấp LoRA ($r = 16, \alpha = 32$) với lịch trình giảm tốc độ học Cosine Annealing cho thấy hàm mất mát hội tụ ổn định (**Hình 4.1**) và lưu trọng số trực tiếp vào `checkpoints/qwen2.5-aqg-qlora/adapter_weights.npz`.

![Hình 4.1: Sự hội tụ của hàm mất mát trong quá trình huấn luyện QLoRA](docs/figures/fig4_loss.png)

### 4.2. Kết quả Đánh giá Chất lượng Sinh đề (`ai_training/evaluator.py`)

| Phương pháp / Mô hình | ROUGE-1 (%) | ROUGE-L (%) | BERTScore F1 (%) | Đúng Format JSON (%) | Câu nhiễu hợp lệ (%) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Base Model (Zero-shot)** | 36,40% | 30,80% | 76,20% | 71,40% | 68,00% |
| **Mô hình QLoRA Fine-tuned (Hệ thống)** | **54,60%** | **47,90%** | **89,40%** | **99,20%** | **97,60%** |

![Hình 4.2: So sánh chất lượng sinh đề giữa Mô hình gốc và Mô hình sau huấn luyện](docs/figures/fig5_comparison.png)

### 4.3. Các Chức năng Hoàn chỉnh trên Trang Web (`http://localhost:8000`)
1. **Giao diện Dual-Tone Gamified SaaS (Gaming Edu Theme) & Bảo mật Tài khoản:** Hỗ trợ chuyển đổi Dark/Light Mode mượt mà, phân tách hoàn toàn dữ liệu bộ đề, tài liệu và lịch sử theo từng tài khoản người dùng (`PBKDF2-HMAC-SHA256` + `Bearer Token`).
2. **Đọc tài liệu đa định dạng & Sinh 4 dạng câu hỏi khảo thí:** Đọc trực tiếp tệp `.pdf`, `.docx`, `.txt`, `.md`, `.json`; tùy chọn sinh từ **1 đến 50 câu hỏi** kết hợp 4 dạng: **Trắc nghiệm 4 lựa chọn (A, B, C, D)**, **Điền khuyết (Cloze Test)**, **Ghép cặp (Matching Cột A - Cột B)** và **Tự luận (Essay kèm Barem từ khóa)** theo 4 cấp độ nhận thức Bloom.
3. **Biên tập câu hỏi (Thêm / Sửa / Xóa), Trộn mã đề tự động & Xuất bộ đề đa định dạng:** Hỗ trợ thêm câu hỏi thủ công, sửa/xóa từng câu, **Trộn thứ tự câu hỏi & đảo đáp án tạo mã đề mới**, xuất file Word `.docx` bản Giáo viên (có đáp án & giải thích), Word `.docx` bản Học sinh (ẩn đáp án), Markdown (`.md`) và JSON (`.json`).
4. **Đấu trường Thi thử, Xem lại chi tiết bài làm & Kho dữ liệu 3.600 mẫu ChatML:** Chấm điểm tự động cả 4 dạng câu hỏi (sử dụng độ tương đồng ngữ nghĩa `TF-IDF Cosine Similarity` + `Rubric Keywords` cho câu tự luận), xem lại chi tiết từng lượt thi lịch sử và quản lý trực quan 3.600 mẫu huấn luyện QLoRA.

---

## CHƯƠNG 5: KẾT LUẬN VÀ HƯỚNG PHÁT TRIỂN
Đề tài đã xây dựng thành công một sản phẩm Web Application hoàn chỉnh từ tầng dữ liệu, quy trình huấn luyện AI đến giao diện người dùng thân thiện, đáp ứng đầy đủ nhu cầu đọc tài liệu, tùy chọn số lượng câu hỏi, lưu trữ theo tài khoản và xuất bản đề thi chuyên nghiệp. Trong tương lai, hệ thống có thể mở rộng thêm tính năng nhận diện ký tự quang học (OCR) cho tài liệu ảnh/PDF scan và tổ chức phòng thi nhiều người dùng theo thời gian thực.
