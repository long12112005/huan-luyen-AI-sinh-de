"""
Quản lý Cơ sở dữ liệu Quan hệ SQLite cho Hệ thống Web AI Sinh Đề Thi.
Lưu trữ:
1. users: Tài khoản người dùng (Đăng ký / Đăng nhập)
2. sessions: Phiên đăng nhập xác thực Bearer Token
3. documents: Tài liệu người dùng đã tải lên (.docx, .txt, .md...)
4. exams: Các bộ đề thi được lưu riêng theo từng tài khoản người dùng
5. questions: Danh sách câu hỏi đa định dạng (Trắc nghiệm, Điền khuyết, Ghép cặp, Tự luận)
6. activity_history: Lịch sử hoạt động (sinh đề, đọc tài liệu, xuất đề, làm bài)
7. quiz_attempts: Lịch sử kết quả làm bài kiểm tra của người dùng
"""

import hashlib
import json
import sqlite3
from datetime import datetime
from backend.config import DB_PATH


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _hash_default_pw(password: str) -> str:
    salt = "aiexam_default_salt"
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000)
    return f"{salt}${dk.hex()}"


def log_user_activity(conn, user_id: int, action_type: str, description: str, metadata: dict = None):
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        """
        INSERT INTO activity_history (user_id, action_type, description, metadata_json, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            user_id,
            action_type,
            description,
            json.dumps(metadata or {}, ensure_ascii=False),
            now_str,
        ),
    )


def init_database():
    conn = get_db()
    cur = conn.cursor()

    # 1. Bảng Tài khoản Người dùng
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'Giáo viên / Giảng viên',
            created_at TEXT NOT NULL
        )
        """
    )

    # 2. Bảng Phiên đăng nhập (Session Tokens)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )

    # 3. Bảng Kho Tài liệu của Người dùng
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            file_type TEXT NOT NULL,
            word_count INTEGER NOT NULL,
            sentence_count INTEGER NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )

    # 4. Bảng Bộ Đề Thi Lưu Theo Tài Khoản Người Dùng
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS exams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            document_id INTEGER,
            title TEXT NOT NULL,
            subject TEXT NOT NULL,
            exam_code TEXT NOT NULL,
            duration_minutes INTEGER DEFAULT 15,
            total_questions INTEGER DEFAULT 0,
            source_context TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )

    # 5. Bảng Câu Hỏi Đa Định Dạng (multiple_choice, fill_blank, matching, essay)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            exam_id INTEGER NOT NULL,
            question_order INTEGER NOT NULL,
            question_type TEXT DEFAULT 'multiple_choice',
            difficulty TEXT NOT NULL,
            question_text TEXT NOT NULL,
            opt_a TEXT NOT NULL,
            opt_b TEXT NOT NULL,
            opt_c TEXT NOT NULL,
            opt_d TEXT NOT NULL,
            correct_answer TEXT NOT NULL,
            explanation TEXT NOT NULL,
            extra_data TEXT DEFAULT '{}',
            FOREIGN KEY (exam_id) REFERENCES exams(id) ON DELETE CASCADE
        )
        """
    )

    # Tự động nâng cấp schema nếu DB cũ chưa có cột question_type và extra_data
    existing_cols = [r["name"] for r in cur.execute("PRAGMA table_info(questions)").fetchall()]
    if "question_type" not in existing_cols:
        cur.execute("ALTER TABLE questions ADD COLUMN question_type TEXT DEFAULT 'multiple_choice'")
    if "extra_data" not in existing_cols:
        cur.execute("ALTER TABLE questions ADD COLUMN extra_data TEXT DEFAULT '{}'")

    # 6. Bảng Lịch Sử Hoạt Động Người Dùng
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS activity_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            action_type TEXT NOT NULL,
            description TEXT NOT NULL,
            metadata_json TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )

    # 7. Bảng Lịch Sử Làm Bài Thi Thử
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS quiz_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            exam_id INTEGER NOT NULL,
            score REAL NOT NULL,
            correct_count INTEGER NOT NULL,
            total_questions INTEGER NOT NULL,
            time_spent_sec INTEGER NOT NULL,
            answers_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (exam_id) REFERENCES exams(id) ON DELETE CASCADE
        )
        """
    )

    # Khởi tạo tài khoản mẫu & dữ liệu ban đầu nếu DB mới tạo
    cur.execute("SELECT COUNT(*) as c FROM users")
    if cur.fetchone()["c"] == 0:
        _seed_initial_data(conn)

    # Đảm bảo tài khoản Demo có sẵn 1 bộ đề mẫu 4 dạng câu hỏi để trải nghiệm ngay
    _ensure_multiformat_sample_exam(conn)

    conn.commit()
    conn.close()


def _seed_initial_data(conn):
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO users (full_name, email, password_hash, role, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            "Giảng viên Demo",
            "demo@aiexam.vn",
            _hash_default_pw("123456"),
            "Giáo viên / Giảng viên",
            now_str,
        ),
    )
    user_id = cur.lastrowid

    sample_doc_content = (
        "Trí tuệ nhân tạo (Artificial Intelligence - AI) và Học sâu (Deep Learning) đã tạo ra bước ngoặt lớn "
        "trong lĩnh vực xử lý ngôn ngữ tự nhiên nhờ kiến trúc Transformer được giới thiệu vào năm 2017. "
        "Khác với mạng nơ-ron hồi quy (RNN) phải xử lý tuần tự từng từ từ trái sang phải, kiến trúc Transformer "
        "sử dụng cơ chế Self-Attention cho phép tính toán mức độ liên kết ngữ cảnh giữa mọi cặp từ trong câu song song. "
        "Khi tinh chỉnh các mô hình ngôn ngữ lớn (LLM) như Qwen2.5-7B-Instruct cho bài toán sinh đề thi tự động, "
        "kỹ thuật LoRA (Low-Rank Adaptation) đóng băng trọng số gốc W0 và chỉ huấn luyện hai ma trận phân rã hạng thấp A và B, "
        "giúp giảm hơn 99% số lượng tham số cần cập nhật. Hơn nữa, kỹ thuật QLoRA kết hợp lượng tử hóa trọng số gốc xuống "
        "kiểu dữ liệu 4-bit NormalFloat (NF4), sử dụng Double Quantization và Paged Optimizers giúp tiết kiệm tối đa bộ nhớ VRAM. "
        "Để đánh giá chất lượng câu hỏi sinh ra, hệ thống sử dụng kết hợp các độ đo ROUGE-L, BERTScore và tỷ lệ tuân thủ cấu trúc JSON."
    )

    cur.execute(
        """
        INSERT INTO documents (user_id, filename, file_type, word_count, sentence_count, content, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            "Giao_trinh_AI_va_Transformer.docx",
            "DOCX",
            len(sample_doc_content.split()),
            5,
            sample_doc_content,
            now_str,
        ),
    )
    doc_id = cur.lastrowid

    log_user_activity(
        conn,
        user_id,
        "UPLOAD_DOC",
        "Đã tải lên tài liệu mẫu: Giao_trinh_AI_va_Transformer.docx",
        {"document_id": doc_id, "word_count": len(sample_doc_content.split())},
    )


def _ensure_multiformat_sample_exam(conn):
    cur = conn.cursor()
    user_row = cur.execute("SELECT id FROM users WHERE email = 'demo@aiexam.vn'").fetchone()
    if not user_row:
        return
    user_id = user_row["id"]

    existing = cur.execute(
        "SELECT id FROM exams WHERE user_id = ? AND exam_code = 'AI-4DANG'",
        (user_id,),
    ).fetchone()
    if existing:
        return

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sample_doc_content = (
        "Kiến trúc Transformer sử dụng cơ chế Self-Attention cho phép tính toán mức độ liên kết ngữ cảnh giữa mọi cặp từ trong câu song song. "
        "Kỹ thuật LoRA (Low-Rank Adaptation) đóng băng trọng số gốc W0 và chỉ huấn luyện hai ma trận phân rã hạng thấp A và B, giúp giảm hơn 99% số lượng tham số cần cập nhật. "
        "Kỹ thuật QLoRA kết hợp lượng tử hóa trọng số gốc xuống kiểu dữ liệu 4-bit NormalFloat (NF4), sử dụng Double Quantization và Paged Optimizers giúp tiết kiệm tối đa bộ nhớ VRAM. "
        "Thang đo nhận thức Bloom chia câu hỏi kiểm tra đánh giá thành các cấp độ từ thấp đến cao gồm Nhận biết, Thông hiểu, Vận dụng và Vận dụng cao."
    )

    cur.execute(
        """
        INSERT INTO exams (user_id, document_id, title, subject, exam_code, duration_minutes, total_questions, source_context, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            None,
            "Đề Mẫu Toàn Diện 4 Dạng: Trắc Nghiệm, Điền Khuyết, Ghép Cặp & Tự Luận",
            "Trí tuệ nhân tạo & Học sâu",
            "AI-4DANG",
            20,
            4,
            sample_doc_content,
            now_str,
        ),
    )
    exam_id = cur.lastrowid

    # Câu 1: Trắc nghiệm 4 lựa chọn
    cur.execute(
        """
        INSERT INTO questions (
            exam_id, question_order, question_type, difficulty, question_text,
            opt_a, opt_b, opt_c, opt_d, correct_answer, explanation, extra_data
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            exam_id,
            1,
            "multiple_choice",
            "Nhận biết",
            "Trong kỹ thuật QLoRA, trọng số của mô hình ngôn ngữ lớn gốc được lượng tử hóa xuống kiểu dữ liệu bao nhiêu bit?",
            "32-bit Floating Point (FP32)",
            "16-bit Brain Float (BF16)",
            "4-bit NormalFloat (NF4)",
            "8-bit Integer tiêu chuẩn (INT8)",
            "C",
            "Theo tài liệu, QLoRA lượng tử hóa trọng số gốc xuống kiểu dữ liệu 4-bit NormalFloat (NF4) để tiết kiệm VRAM.",
            json.dumps({"question_type": "multiple_choice"}, ensure_ascii=False),
        ),
    )

    # Câu 2: Điền khuyết (Fill-in-the-blank)
    fill_extra = {
        "question_type": "fill_blank",
        "blank_answer": "Self-Attention",
        "accepted_variants": ["self-attention", "self attention", "cơ chế self-attention"],
        "hint": "Cụm thuật ngữ tiếng Anh gồm 2 từ nối bởi dấu gạch ngang (bắt đầu bằng chữ S)",
    }
    cur.execute(
        """
        INSERT INTO questions (
            exam_id, question_order, question_type, difficulty, question_text,
            opt_a, opt_b, opt_c, opt_d, correct_answer, explanation, extra_data
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            exam_id,
            2,
            "fill_blank",
            "Thông hiểu",
            "Điền thuật ngữ chính xác vào chỗ trống (1) trong câu trích dẫn sau:\n« Kiến trúc Transformer sử dụng cơ chế [ (1) ................ ] cho phép tính toán mức độ liên kết ngữ cảnh giữa mọi cặp từ trong câu song song. »",
            "Gợi ý: Cụm thuật ngữ gồm 2 từ (Bắt đầu bằng chữ S)",
            "Chấp nhận: Self-Attention / cơ chế Self-Attention",
            "Từ khóa thuộc chủ đề: Kiến trúc Transformer",
            "Loại câu hỏi: Điền khuyết (Cloze Test)",
            "Self-Attention",
            "Trích dẫn gốc: «Kiến trúc Transformer sử dụng cơ chế Self-Attention cho phép tính toán mức độ liên kết ngữ cảnh giữa mọi cặp từ trong câu song song.»",
            json.dumps(fill_extra, ensure_ascii=False),
        ),
    )

    # Câu 3: Ghép cặp (Matching Cột A <-> Cột B)
    match_extra = {
        "question_type": "matching",
        "col_a": [
            {"id": "1", "text": "Kiến trúc Transformer"},
            {"id": "2", "text": "Kỹ thuật LoRA"},
            {"id": "3", "text": "Kỹ thuật QLoRA"},
            {"id": "4", "text": "Thang đo nhận thức Bloom"},
        ],
        "col_b": [
            {"id": "A", "text": "Đóng băng trọng số gốc W0 và chỉ huấn luyện hai ma trận phân rã hạng thấp A và B"},
            {"id": "B", "text": "Sử dụng cơ chế Self-Attention tính toán liên kết ngữ cảnh giữa mọi cặp từ song song"},
            {"id": "C", "text": "Phân chia câu hỏi thành 4 mức độ: Nhận biết, Thông hiểu, Vận dụng và Vận dụng cao"},
            {"id": "D", "text": "Kết hợp lượng tử hóa 4-bit NormalFloat (NF4), Double Quantization và Paged Optimizers"},
        ],
        "mapping": {"1": "B", "2": "A", "3": "D", "4": "C"},
    }
    cur.execute(
        """
        INSERT INTO questions (
            exam_id, question_order, question_type, difficulty, question_text,
            opt_a, opt_b, opt_c, opt_d, correct_answer, explanation, extra_data
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            exam_id,
            3,
            "matching",
            "Vận dụng",
            "Hãy ghép nối mỗi khái niệm ở Cột A (1, 2, 3, 4) với nội dung định nghĩa tương ứng ở Cột B (A, B, C, D) sao cho chính xác theo tài liệu:",
            "1. Kiến trúc Transformer  ⟷  B. Sử dụng cơ chế Self-Attention tính toán liên kết ngữ cảnh giữa mọi cặp từ song song",
            "2. Kỹ thuật LoRA  ⟷  A. Đóng băng trọng số gốc W0 và chỉ huấn luyện hai ma trận phân rã hạng thấp A và B",
            "3. Kỹ thuật QLoRA  ⟷  D. Kết hợp lượng tử hóa 4-bit NormalFloat (NF4), Double Quantization và Paged Optimizers",
            "4. Thang đo nhận thức Bloom  ⟷  C. Phân chia câu hỏi thành 4 mức độ: Nhận biết, Thông hiểu, Vận dụng và Vận dụng cao",
            "1-B, 2-A, 3-D, 4-C",
            "Ghép cặp dựa trên mối quan hệ ngữ nghĩa trực tiếp giữa từng thuật ngữ và phần giải thích trong tài liệu nguồn.",
            json.dumps(match_extra, ensure_ascii=False),
        ),
    )

    # Câu 4: Tự luận (Essay + AI chấm điểm ngữ nghĩa)
    essay_extra = {
        "question_type": "essay",
        "sample_answer": "Kỹ thuật LoRA đóng băng trọng số gốc W0 và chỉ huấn luyện hai ma trận phân rã hạng thấp A và B giúp giảm hơn 99% số lượng tham số cần cập nhật. Khi kết hợp với QLoRA lượng tử hóa 4-bit NormalFloat (NF4), Double Quantization và Paged Optimizers, hệ thống tiết kiệm tối đa bộ nhớ VRAM.",
        "rubric_keywords": [
            "đóng băng trọng số",
            "ma trận phân rã hạng thấp",
            "giảm hơn 99%",
            "4-bit normalfloat",
            "tiết kiệm tối đa bộ nhớ vram",
        ],
        "scoring_guide": "AI chấm tự động theo độ tương đồng Cosine TF-IDF (50%) + tỷ lệ bao phủ từ khóa trọng tâm trong Rubric (50%).",
    }
    cur.execute(
        """
        INSERT INTO questions (
            exam_id, question_order, question_type, difficulty, question_text,
            opt_a, opt_b, opt_c, opt_d, correct_answer, explanation, extra_data
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            exam_id,
            4,
            "essay",
            "Vận dụng cao",
            "[Tự luận] Phân tích cơ chế hoạt động của kỹ thuật LoRA và QLoRA trong việc tối ưu hóa bộ nhớ VRAM khi tinh chỉnh mô hình ngôn ngữ lớn theo tài liệu?",
            "Tiêu chí 1: Nêu được cơ chế đóng băng trọng số gốc W0 và huấn luyện 2 ma trận hạng thấp A, B (giảm >99% tham số)",
            "Tiêu chí 2: Nêu được kỹ thuật lượng tử hóa 4-bit NormalFloat (NF4) của QLoRA",
            "Tiêu chí 3: Đề cập đến Double Quantization & Paged Optimizers giúp tiết kiệm VRAM",
            "Phương pháp chấm: AI đo độ tương đồng ngữ nghĩa TF-IDF Cosine + Khớp từ khóa Rubric",
            essay_extra["sample_answer"],
            "Barem chấm điểm tự luận: Học sinh trình bày được nguyên lý ma trận hạng thấp A, B của LoRA và lượng tử hóa 4-bit NF4 của QLoRA.",
            json.dumps(essay_extra, ensure_ascii=False),
        ),
    )
