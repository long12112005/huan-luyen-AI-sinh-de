# 🎓 AI ExamGen Platform — Hệ Thống Web Đọc Tài Liệu & Huấn Luyện AI Sinh Đề Thi

Hệ thống Web Application hoàn chỉnh cho phép người dùng **Đăng ký / Đăng nhập tài khoản**, **Đọc trực tiếp tài liệu bài giảng (`.pdf`, `.docx`, `.txt`, `.md`, `.json`)**, **Tùy chọn số lượng câu hỏi muốn sinh ra (1 – 50 câu)**, **Lưu trữ bộ đề và lịch sử riêng theo từng tài khoản**, **Làm bài thi thử chấm điểm tự động** và **Xuất bộ đề ra đa định dạng (Word `.docx` có đáp án, Word `.docx` đề học sinh, Markdown, JSON)**.

---

## 📁 Cấu Trúc Mã Nguồn & Dữ Liệu Dự Án

```text
huan luyen AI sinh de/
├── main.py                          # Điểm khởi chạy chính của Web Server (FastAPI REST API)
├── requirements.txt                 # Danh sách thư viện Python
├── backend/                         # Tầng xử lý nghiệp vụ Backend & Cơ sở dữ liệu
│   ├── __init__.py
│   ├── config.py                    # Cấu hình đường dẫn hệ thống & tham số mô hình Qwen2.5-7B QLoRA
│   ├── database.py                  # Quản lý SQLite3 (7 bảng: users, sessions, documents, exams, questions, activity_history, quiz_attempts)
│   ├── auth.py                      # Đăng ký, Đăng nhập, Băm mật khẩu PBKDF2-SHA256 & Xác thực Bearer Token
│   ├── document_parser.py           # Đọc & bóc tách văn bản từ tệp tài liệu tải lên (.pdf, .docx, .txt, .md, .json)
│   ├── ai_engine.py                 # Bộ máy AI phân tích tài liệu & sinh câu hỏi theo số lượng yêu cầu + thang đo Bloom
│   └── exporter.py                  # Xuất bộ đề ra Word (.docx bản Giáo viên & bản Học sinh), Markdown (.md), JSON (.json)
├── ai_training/                     # Quy trình Huấn luyện & Đánh giá Mô hình AI
│   ├── __init__.py
│   ├── dataset_builder.py           # Chuẩn hóa tập dữ liệu huấn luyện sang định dạng ChatML / JSON Schema
│   ├── train_qlora.py               # Quy trình huấn luyện Qwen2.5-7B-Instruct với 4-bit NormalFloat QLoRA
│   ├── evaluator.py                 # Đánh giá tự động chất lượng bộ đề (Format Validity, Distractor Uniqueness, Length Balance)
│   └── report_generator.py          # Sinh đồng bộ tài liệu báo cáo & slide thuyết trình vào docs/
├── frontend/                        # Giao diện Web Người dùng (HTML5 / CSS3 / JavaScript SPA)
│   ├── index.html                   # Giao diện Đăng nhập/Đăng ký + Không gian làm việc 5 Phân hệ
│   ├── css/
│   │   └── style.css                # Thiết kế giao diện thân thiện, trực quan, dễ sử dụng
│   └── js/
│       └── app.js                   # Xử lý tương tác người dùng, tải tài liệu PDF/DOCX/TXT, chọn số câu hỏi, lưu & xuất đề
└── data/                            # Tầng Lưu trữ Dữ liệu
    ├── app.db                       # Cơ sở dữ liệu SQLite lưu Tài khoản, Tài liệu, Bộ đề & Lịch sử
    ├── training_dataset.json        # Tập dữ liệu huấn luyện AI chuẩn cấu trúc
    └── sample_docs/                 # Tệp tài liệu PDF (.pdf) và Word (.docx) mẫu để kiểm thử nhanh
```

---

## 🚀 Hướng Dẫn Khởi Chạy Hệ Thống Web

### 1. Cài đặt thư viện
```bash
pip install -r requirements.txt
```

### 2. Chạy Web Server
```bash
python main.py
```
Sau đó mở trình duyệt truy cập: **`http://localhost:8000`**
- **Tài khoản Demo có sẵn:** Email `demo@aiexam.vn` | Mật khẩu `123456` *(hoặc bấm nút Đăng ký tài khoản mới ngay trên trang chủ)*.

