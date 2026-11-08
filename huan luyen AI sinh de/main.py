"""
Điểm khởi chạy chính của Hệ thống Web AI Sinh Đề Thi (FastAPI Server).
Cung cấp đầy đủ các chức năng:
1. Đăng ký, Đăng nhập & Quản lý Tài khoản Người dùng.
2. Đọc tài liệu (.docx, .txt, .md, .json) để trích xuất ngữ cảnh sinh đề.
3. Tuỳ chọn số lượng câu hỏi muốn sinh (1 -> 50 câu) & mức độ nhận thức Bloom.
4. Lưu trữ bộ đề riêng theo từng tài khoản người dùng & chỉnh sửa câu hỏi trực tiếp.
5. Lưu trữ đầy đủ lịch sử (Lịch sử đọc tài liệu, lịch sử sinh đề, lịch sử xuất đề, lịch sử làm bài).
6. Xuất bộ đề ra đa định dạng: Word (.docx có đáp án), Word (.docx đề thi học sinh), Markdown (.md), JSON (.json).
7. Quản lý Quy trình Huấn luyện AI (Dataset ChatML, QLoRA Config, Đóng góp dữ liệu huấn luyện).

Cách chạy:
    python main.py
Mở trình duyệt tại: http://localhost:8000
"""

import json
import os
import random
import re
from datetime import datetime
from typing import Dict, List, Optional

import uvicorn
from docx import Document
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ai_training.dataset_builder import (
    add_exam_to_training_corpus,
    get_training_corpus_stats,
    init_training_corpus,
    query_training_samples,
)
from ai_training.evaluator import evaluate_generated_questions
from ai_training.train_qlora import get_latest_training_log, run_qlora_training
from backend.ai_engine import generate_exam_from_document, grade_user_question_answer
from backend.auth import (
    create_user_session,
    get_user_by_token,
    hash_password,
    require_current_user,
    verify_password,
)
from backend.config import FRONTEND_DIR, MODEL_CONFIG, SAMPLE_DOCS_DIR
from backend.database import get_db, init_database, log_user_activity
from backend.document_parser import create_sample_pdf_bytes, parse_uploaded_document
from backend.exporter import build_exam_docx, build_exam_markdown

app = FastAPI(
    title="AI ExamGen Platform — Hệ thống Web Huấn luyện AI & Sinh Đề Thi Thông Minh",
    version="3.0.0",
)

# Phục vụ thư mục tĩnh CSS & JS của Frontend
os.makedirs(os.path.join(FRONTEND_DIR, "css"), exist_ok=True)
os.makedirs(os.path.join(FRONTEND_DIR, "js"), exist_ok=True)
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


# ============================================================================
# SCHEMAS DỮ LIỆU ĐẦU VÀO (PYDANTIC MODELS)
# ============================================================================
class RegisterRequest(BaseModel):
    full_name: str
    email: str
    password: str
    role: str = "Giáo viên / Giảng viên"


class LoginRequest(BaseModel):
    email: str
    password: str


class UploadDocPayload(BaseModel):
    filename: str
    content_base64: str
    extracted_text_override: Optional[str] = None


class GenerateExamPayload(BaseModel):
    title: str
    subject: str
    exam_code: str = "DE-01"
    duration_minutes: int = 15
    total_questions: int = 5
    difficulty_filter: str = "Tất cả mức độ (Cân bằng theo chuẩn Bloom)"
    question_type_filter: str = "mixed"
    selected_types: Optional[List[str]] = None
    custom_counts: Optional[Dict[str, int]] = None
    context_text: str
    document_id: Optional[int] = None


class UpdateQuestionPayload(BaseModel):
    difficulty: str
    question_text: str
    opt_a: str
    opt_b: str
    opt_c: str
    opt_d: str
    correct_answer: str
    explanation: str


class CreateQuestionPayload(BaseModel):
    question_type: str = "multiple_choice"
    difficulty: str = "Thông hiểu"
    question_text: str
    opt_a: str = ""
    opt_b: str = ""
    opt_c: str = ""
    opt_d: str = ""
    correct_answer: str = "A"
    explanation: str = ""


class ShuffleExamPayload(BaseModel):
    new_exam_code: Optional[str] = None


class QuizSubmitPayload(BaseModel):
    time_spent_sec: int
    answers: Dict[str, str]


# ============================================================================
# 1. GIAO DIỆN CHÍNH & TÀI LIỆU MẪU
# ============================================================================
@app.get("/favicon.ico")
def favicon_ico():
    svg_icon = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
        '<rect width="64" height="64" rx="16" fill="#4C49E8"/>'
        '<polygon points="36 8 14 36 30 36 26 56 50 28 34 28 36 8" fill="#F59E0B"/>'
        "</svg>"
    )
    return Response(content=svg_icon, media_type="image/svg+xml")


@app.get("/", response_class=HTMLResponse)
def index_page():
    index_file = os.path.join(FRONTEND_DIR, "index.html")
    with open(index_file, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


def create_sample_docx_files():
    """Tạo sẵn file tài liệu mẫu Word (.docx) và PDF (.pdf) trong `data/sample_docs/` để người dùng tải thử."""
    paragraphs = [
        "Kiến trúc Transformer là nền tảng cốt lõi của các mô hình ngôn ngữ lớn (Large Language Models - LLMs) hiện đại nhờ cơ chế Self-Attention xử lý song song toàn bộ chuỗi văn bản.",
        "Kỹ thuật tinh chỉnh có giám sát (Supervised Fine-Tuning - SFT) giúp mô hình ngôn ngữ lớn học cách tuân thủ tập chỉ dẫn chuyên biệt và xuất dữ liệu đúng định dạng cấu trúc JSON.",
        "Phương pháp LoRA (Low-Rank Adaptation) đóng băng ma trận trọng số gốc W0 và chèn cặp ma trận phân rã hạng thấp A, B vào các tầng tuyến tính, giúp giảm hơn 99% số lượng tham số cần cập nhật.",
        "Kỹ thuật QLoRA kết hợp lượng tử hóa trọng số gốc xuống kiểu dữ liệu 4-bit NormalFloat (NF4), sử dụng Double Quantization và Paged Optimizers giúp tiết kiệm tối đa bộ nhớ VRAM trên máy chủ GPU.",
        "Thang đo nhận thức Bloom chia câu hỏi kiểm tra đánh giá thành các cấp độ từ thấp đến cao gồm Nhận biết, Thông hiểu, Vận dụng và Vận dụng cao nhằm phân loại chính xác năng lực người học.",
        "Trong bài toán sinh đề thi trắc nghiệm tự động, các phương án nhiễu (distractors) cần có độ dài và thuật ngữ tương đương đáp án đúng để tránh việc học sinh đoán mò dựa trên độ dài câu.",
    ]

    sample_docx_path = os.path.join(SAMPLE_DOCS_DIR, "Tai_lieu_Mau_Tri_Tue_Nhan_Tao.docx")
    if not os.path.exists(sample_docx_path):
        doc = Document()
        doc.add_heading("TÀI LIỆU BÀI GIẢNG: TRÍ TUỆ NHÂN TẠO VÀ MÔ HÌNH NGÔN NGỮ LỚN", level=1)
        for p in paragraphs:
            doc.add_paragraph(p)
        doc.save(sample_docx_path)

    sample_pdf_path = os.path.join(SAMPLE_DOCS_DIR, "Tai_lieu_Mau_Tri_Tue_Nhan_Tao.pdf")
    if not os.path.exists(sample_pdf_path):
        pdf_bytes = create_sample_pdf_bytes(paragraphs)
        with open(sample_pdf_path, "wb") as f:
            f.write(pdf_bytes)


# ============================================================================
# 2. API ĐĂNG KÝ, ĐĂNG NHẬP & QUẢN LÝ TÀI KHOẢN
# ============================================================================
@app.post("/api/auth/register")
def register_account(req: RegisterRequest):
    email = req.email.strip().lower()
    full_name = req.full_name.strip()
    if not full_name or not email or len(req.password) < 4:
        raise HTTPException(status_code=400, detail="Vui lòng nhập đầy đủ họ tên, email và mật khẩu (tối thiểu 4 ký tự).")

    conn = get_db()
    existing = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    if existing:
        conn.close()
        raise HTTPException(status_code=400, detail="Email này đã được đăng ký. Vui lòng đăng nhập hoặc dùng email khác.")

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    pw_hash = hash_password(req.password)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (full_name, email, password_hash, role, created_at) VALUES (?, ?, ?, ?, ?)",
        (full_name, email, pw_hash, req.role, now_str),
    )
    user_id = cur.lastrowid
    log_user_activity(conn, user_id, "REGISTER", f"Đăng ký tài khoản mới: {full_name} ({email})")
    conn.commit()
    conn.close()

    token = create_user_session(user_id)
    return {
        "token": token,
        "user": {
            "id": user_id,
            "full_name": full_name,
            "email": email,
            "role": req.role,
        },
    }


@app.post("/api/auth/login")
def login_account(req: LoginRequest):
    email = req.email.strip().lower()
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if not row or not verify_password(req.password, row["password_hash"]):
        conn.close()
        raise HTTPException(status_code=401, detail="Email hoặc mật khẩu không chính xác.")

    user = dict(row)
    log_user_activity(conn, user["id"], "LOGIN", "Đăng nhập vào hệ thống")
    conn.commit()
    conn.close()

    token = create_user_session(user["id"])
    return {
        "token": token,
        "user": {
            "id": user["id"],
            "full_name": user["full_name"],
            "email": user["email"],
            "role": user["role"],
        },
    }


@app.get("/api/auth/me")
def get_current_account(user: dict = Depends(require_current_user)):
    return {"user": user}


@app.post("/api/auth/logout")
def logout_account(authorization: Optional[str] = Header(default=None)):
    if authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "", 1).strip()
        conn = get_db()
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        conn.commit()
        conn.close()
    return {"status": "ok"}


# ============================================================================
# 3. API ĐỌC TÀI LIỆU & QUẢN LÝ KHO TÀI LIỆU CỦA NGƯỜI DÙNG
# ============================================================================
@app.post("/api/documents/upload")
def upload_and_parse_document(
    req: UploadDocPayload,
    user: dict = Depends(require_current_user),
):
    parsed = parse_uploaded_document(
        req.filename,
        req.content_base64,
        req.extracted_text_override,
    )
    if parsed["word_count"] < 5:
        raise HTTPException(status_code=400, detail="Tài liệu tải lên trống hoặc quá ngắn. Vui lòng chọn tệp có nội dung.")

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO documents (user_id, filename, file_type, word_count, sentence_count, content, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user["id"],
            parsed["filename"],
            parsed["file_type"],
            parsed["word_count"],
            parsed["sentence_count"],
            parsed["content"],
            now_str,
        ),
    )
    doc_id = cur.lastrowid
    log_user_activity(
        conn,
        user["id"],
        "UPLOAD_DOC",
        f"Đã đọc tài liệu '{parsed['filename']}' ({parsed['word_count']} từ, {parsed['sentence_count']} mệnh đề)",
        {"document_id": doc_id, "filename": parsed["filename"], "word_count": parsed["word_count"]},
    )
    conn.commit()
    conn.close()

    parsed["id"] = doc_id
    return parsed


@app.get("/api/documents")
def list_user_documents(user: dict = Depends(require_current_user)):
    conn = get_db()
    rows = conn.execute(
        "SELECT id, filename, file_type, word_count, sentence_count, content, created_at FROM documents WHERE user_id = ? ORDER BY id DESC",
        (user["id"],),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.delete("/api/documents/{doc_id}")
def delete_user_document(doc_id: int, user: dict = Depends(require_current_user)):
    conn = get_db()
    cur = conn.cursor()
    row = cur.execute(
        "SELECT filename FROM documents WHERE id = ? AND user_id = ?",
        (doc_id, user["id"]),
    ).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Tài liệu không tồn tại trong kho của bạn.")

    cur.execute("UPDATE exams SET document_id = NULL WHERE document_id = ? AND user_id = ?", (doc_id, user["id"]))
    cur.execute("DELETE FROM documents WHERE id = ? AND user_id = ?", (doc_id, user["id"]))
    log_user_activity(conn, user["id"], "DELETE_DOC", f"Đã xóa tài liệu '{row['filename']}' khỏi kho lưu trữ")
    conn.commit()
    conn.close()
    return {"status": "ok"}


@app.get("/api/documents/sample-docx")
def download_sample_docx():
    create_sample_docx_files()
    sample_path = os.path.join(SAMPLE_DOCS_DIR, "Tai_lieu_Mau_Tri_Tue_Nhan_Tao.docx")
    return FileResponse(
        sample_path,
        filename="Tai_lieu_Mau_Tri_Tue_Nhan_Tao.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@app.get("/api/documents/sample-pdf")
def download_sample_pdf():
    create_sample_docx_files()
    sample_pdf_path = os.path.join(SAMPLE_DOCS_DIR, "Tai_lieu_Mau_Tri_Tue_Nhan_Tao.pdf")
    return FileResponse(
        sample_pdf_path,
        filename="Tai_lieu_Mau_Tri_Tue_Nhan_Tao.pdf",
        media_type="application/pdf",
    )


# ============================================================================
# 4. API AI SINH ĐỀ THI, LƯU BỘ ĐỀ THEO TÀI KHOẢN & CHỈNH SỬA
# ============================================================================
@app.post("/api/exams/generate")
def generate_and_save_exam(
    req: GenerateExamPayload,
    user: dict = Depends(require_current_user),
):
    if not req.context_text or len(req.context_text.strip().split()) < 8:
        raise HTTPException(
            status_code=400,
            detail="Vui lòng tải tài liệu lên hoặc nhập nội dung tài liệu tối thiểu 8 từ để AI sinh đề.",
        )

    num_q = max(1, min(50, req.total_questions))
    generated_questions = generate_exam_from_document(
        context_text=req.context_text,
        subject=req.subject.strip() or "Tổng hợp",
        total_questions=num_q,
        difficulty_filter=req.difficulty_filter,
        custom_counts=req.custom_counts,
        question_type_filter=req.question_type_filter,
        selected_types=req.selected_types,
    )

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO exams (
            user_id, document_id, title, subject, exam_code,
            duration_minutes, total_questions, source_context, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user["id"],
            req.document_id,
            req.title.strip() or f"Đề kiểm tra {req.subject}",
            req.subject.strip() or "Tổng hợp",
            req.exam_code.strip() or "DE-01",
            req.duration_minutes,
            len(generated_questions),
            req.context_text,
            now_str,
        ),
    )
    exam_id = cur.lastrowid

    for q in generated_questions:
        cur.execute(
            """
            INSERT INTO questions (
                exam_id, question_order, question_type, difficulty, question_text,
                opt_a, opt_b, opt_c, opt_d, correct_answer, explanation, extra_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                exam_id,
                q["question_order"],
                q.get("question_type", "multiple_choice"),
                q["difficulty"],
                q["question_text"],
                q["opt_a"],
                q["opt_b"],
                q["opt_c"],
                q["opt_d"],
                q["correct_answer"],
                q["explanation"],
                q.get("extra_data", "{}"),
            ),
        )

    log_user_activity(
        conn,
        user["id"],
        "GENERATE_EXAM",
        f"Đã sinh & lưu bộ đề '{req.title}' gồm {len(generated_questions)} câu hỏi (Môn: {req.subject})",
        {"exam_id": exam_id, "total_questions": len(generated_questions), "subject": req.subject},
    )
    conn.commit()
    conn.close()

    return get_user_exam_detail(exam_id, user)


@app.get("/api/exams")
def list_user_exams(user: dict = Depends(require_current_user)):
    conn = get_db()
    cur = conn.cursor()
    exams = [
        dict(r)
        for r in cur.execute(
            "SELECT * FROM exams WHERE user_id = ? ORDER BY id DESC",
            (user["id"],),
        ).fetchall()
    ]

    for ex in exams:
        rows = cur.execute(
            "SELECT difficulty, COUNT(*) as cnt FROM questions WHERE exam_id = ? GROUP BY difficulty",
            (ex["id"],),
        ).fetchall()
        ex["bloom_summary"] = {r["difficulty"]: r["cnt"] for r in rows}

        type_rows = cur.execute(
            "SELECT COALESCE(question_type, 'multiple_choice') as qt, COUNT(*) as cnt FROM questions WHERE exam_id = ? GROUP BY qt",
            (ex["id"],),
        ).fetchall()
        ex["type_summary"] = {r["qt"]: r["cnt"] for r in type_rows}

    conn.close()
    return exams


@app.get("/api/exams/{exam_id}")
def get_user_exam_detail(exam_id: int, user: dict = Depends(require_current_user)):
    conn = get_db()
    cur = conn.cursor()
    row = cur.execute(
        "SELECT * FROM exams WHERE id = ? AND user_id = ?",
        (exam_id, user["id"]),
    ).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Không tìm thấy bộ đề trong tài khoản của bạn.")

    exam = dict(row)
    q_rows = cur.execute(
        "SELECT * FROM questions WHERE exam_id = ? ORDER BY question_order ASC",
        (exam_id,),
    ).fetchall()
    exam["questions"] = [dict(r) for r in q_rows]
    exam["quality_metrics"] = evaluate_generated_questions(exam["questions"])
    conn.close()
    return exam


def sync_question_extra_data(
    q_type: str,
    opt_a: str,
    opt_b: str,
    opt_c: str,
    opt_d: str,
    correct_answer: str,
    existing_extra_json: str = "{}",
) -> tuple[str, str]:
    """Đồng bộ hóa `extra_data` và `correct_answer` khi thêm/sửa câu hỏi ở cả 4 dạng thức."""
    try:
        extra = json.loads(existing_extra_json or "{}")
        if not isinstance(extra, dict):
            extra = {}
    except Exception:
        extra = {}

    q_type = q_type or "multiple_choice"
    extra["question_type"] = q_type

    if q_type == "multiple_choice":
        clean_ans = correct_answer.upper().strip()
        if clean_ans not in ("A", "B", "C", "D"):
            clean_ans = "A"
        return clean_ans, json.dumps({"question_type": "multiple_choice"}, ensure_ascii=False)

    if q_type == "fill_blank":
        clean_ans = correct_answer.strip(" .,;:()\"'")
        variants = list(
            {
                clean_ans.lower(),
                re.sub(r"[-_/]", " ", clean_ans.lower()),
                re.sub(r"\s+", " ", clean_ans.lower()),
            }
        )
        extra.pop("hint", None)
        extra.update(
            {
                "blank_answer": clean_ans,
                "accepted_variants": variants,
            }
        )
        return clean_ans, json.dumps(extra, ensure_ascii=False)

    if q_type == "matching":
        mapping: Dict[str, str] = {}
        pairs = re.findall(r"([1-4])\s*[-:=]\s*([A-Da-d])", correct_answer or "")
        for num_k, let_v in pairs:
            mapping[num_k] = let_v.upper()
        default_letters = ["A", "B", "C", "D"]
        for idx_num in range(1, 5):
            k_str = str(idx_num)
            if k_str not in mapping:
                mapping[k_str] = default_letters[idx_num - 1]

        raw_opts = [opt_a or "", opt_b or "", opt_c or "", opt_d or ""]
        old_col_a = {str(item.get("id")): item.get("text", "") for item in extra.get("col_a", []) if isinstance(item, dict)}
        old_col_b = {str(item.get("id")): item.get("text", "") for item in extra.get("col_b", []) if isinstance(item, dict)}

        col_a = []
        b_map_text: Dict[str, str] = dict(old_col_b)

        for idx_i, opt_str in enumerate(raw_opts):
            num_id = str(idx_i + 1)
            target_letter = mapping[num_id]
            if "⟷" in opt_str or "<->" in opt_str or "|" in opt_str:
                parts = re.split(r"⟷|<->|\|", opt_str, maxsplit=1)
                left_txt = re.sub(r"^[1-4][\.\)]\s*", "", parts[0].strip())
                right_txt = re.sub(r"^[A-Da-d][\.\)]\s*", "", parts[1].strip())
                col_a.append({"id": num_id, "text": left_txt or f"Khái niệm {num_id}"})
                if right_txt:
                    b_map_text[target_letter] = right_txt
            else:
                clean_txt = re.sub(r"^[1-4][\.\)]\s*", "", opt_str.strip())
                col_a.append({"id": num_id, "text": clean_txt or old_col_a.get(num_id, f"Khái niệm {num_id}")})

        col_b = []
        for let_k in ["A", "B", "C", "D"]:
            col_b.append({"id": let_k, "text": b_map_text.get(let_k, f"Nội dung mô tả {let_k}")})

        clean_ans = ", ".join(f"{k}-{mapping[k]}" for k in ["1", "2", "3", "4"])
        extra.update({"col_a": col_a, "col_b": col_b, "mapping": mapping})
        return clean_ans, json.dumps(extra, ensure_ascii=False)

    if q_type == "essay":
        clean_ans = (correct_answer or "").strip()
        raw_kw_str = re.sub(
            r"^Từ khóa chấm điểm\s*(\(Rubric Keywords\))?\s*:\s*",
            "",
            (opt_b or "").strip(),
            flags=re.IGNORECASE,
        )
        kw_list = [k.strip(" \"'.,;") for k in re.split(r"[,;]+", raw_kw_str) if len(k.strip(" \"'.,;")) >= 2]
        if not kw_list and clean_ans:
            words = [w.strip(" .,;:()\"'") for w in clean_ans.split() if len(w.strip(" .,;:()\"'")) >= 4]
            kw_list = list(dict.fromkeys(words[:4]))
        extra.update(
            {
                "sample_answer": clean_ans,
                "rubric_keywords": kw_list[:6],
                "scoring_guide": extra.get(
                    "scoring_guide",
                    "Chấm điểm tự động bằng AI: Kết hợp độ tương đồng ngữ nghĩa TF-IDF Cosine Similarity (50%) và tỷ lệ bao phủ từ khóa trọng tâm trong Rubric (50%).",
                ),
            }
        )
        return clean_ans, json.dumps(extra, ensure_ascii=False)

    return correct_answer.strip(), json.dumps(extra, ensure_ascii=False)


@app.put("/api/questions/{question_id}")
def edit_question(
    question_id: int,
    req: UpdateQuestionPayload,
    user: dict = Depends(require_current_user),
):
    conn = get_db()
    cur = conn.cursor()
    # Kiểm tra quyền sở hữu câu hỏi thông qua bảng exams
    q_row = cur.execute(
        """
        SELECT q.id, q.exam_id, q.question_type, q.extra_data, e.title
        FROM questions q
        JOIN exams e ON q.exam_id = e.id
        WHERE q.id = ? AND e.user_id = ?
        """,
        (question_id, user["id"]),
    ).fetchone()
    if not q_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Không tìm thấy câu hỏi cần sửa.")

    q_type = q_row["question_type"] or "multiple_choice"
    clean_ans, updated_extra = sync_question_extra_data(
        q_type=q_type,
        opt_a=req.opt_a,
        opt_b=req.opt_b,
        opt_c=req.opt_c,
        opt_d=req.opt_d,
        correct_answer=req.correct_answer,
        existing_extra_json=q_row["extra_data"] or "{}",
    )

    cur.execute(
        """
        UPDATE questions
        SET difficulty = ?, question_text = ?, opt_a = ?, opt_b = ?, opt_c = ?, opt_d = ?,
            correct_answer = ?, explanation = ?, extra_data = ?
        WHERE id = ?
        """,
        (
            req.difficulty,
            req.question_text,
            req.opt_a,
            req.opt_b,
            req.opt_c,
            req.opt_d,
            clean_ans,
            req.explanation,
            updated_extra,
            question_id,
        ),
    )
    log_user_activity(
        conn,
        user["id"],
        "EDIT_EXAM",
        f"Đã chỉnh sửa câu hỏi trong bộ đề '{q_row['title']}'",
        {"exam_id": q_row["exam_id"], "question_id": question_id},
    )
    conn.commit()
    conn.close()
    return {"status": "ok"}


@app.post("/api/exams/{exam_id}/questions")
def add_question_to_exam(
    exam_id: int,
    req: CreateQuestionPayload,
    user: dict = Depends(require_current_user),
):
    conn = get_db()
    cur = conn.cursor()
    exam_row = cur.execute(
        "SELECT id, title FROM exams WHERE id = ? AND user_id = ?",
        (exam_id, user["id"]),
    ).fetchone()
    if not exam_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Không tìm thấy bộ đề.")

    max_order_row = cur.execute(
        "SELECT COALESCE(MAX(question_order), 0) as max_ord FROM questions WHERE exam_id = ?",
        (exam_id,),
    ).fetchone()
    next_order = (max_order_row["max_ord"] or 0) + 1

    q_type = req.question_type or "multiple_choice"
    clean_ans, extra_json = sync_question_extra_data(
        q_type=q_type,
        opt_a=req.opt_a,
        opt_b=req.opt_b,
        opt_c=req.opt_c,
        opt_d=req.opt_d,
        correct_answer=req.correct_answer,
        existing_extra_json="{}",
    )

    cur.execute(
        """
        INSERT INTO questions (
            exam_id, question_order, question_type, difficulty, question_text,
            opt_a, opt_b, opt_c, opt_d, correct_answer, explanation, extra_data
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            exam_id,
            next_order,
            q_type,
            req.difficulty,
            req.question_text,
            req.opt_a,
            req.opt_b,
            req.opt_c,
            req.opt_d,
            clean_ans,
            req.explanation or "Câu hỏi bổ sung bởi Giáo viên.",
            extra_json,
        ),
    )
    cur.execute(
        "UPDATE exams SET total_questions = (SELECT COUNT(*) FROM questions WHERE exam_id = ?) WHERE id = ?",
        (exam_id, exam_id),
    )
    log_user_activity(
        conn,
        user["id"],
        "ADD_QUESTION",
        f"Đã thêm câu hỏi số {next_order} vào bộ đề '{exam_row['title']}'",
        {"exam_id": exam_id, "question_order": next_order},
    )
    conn.commit()
    conn.close()
    return get_user_exam_detail(exam_id, user)


@app.delete("/api/questions/{question_id}")
def delete_single_question(
    question_id: int,
    user: dict = Depends(require_current_user),
):
    conn = get_db()
    cur = conn.cursor()
    q_row = cur.execute(
        """
        SELECT q.id, q.exam_id, q.question_order, e.title
        FROM questions q
        JOIN exams e ON q.exam_id = e.id
        WHERE q.id = ? AND e.user_id = ?
        """,
        (question_id, user["id"]),
    ).fetchone()
    if not q_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Không tìm thấy câu hỏi cần xóa.")

    exam_id = q_row["exam_id"]
    cnt_row = cur.execute("SELECT COUNT(*) as cnt FROM questions WHERE exam_id = ?", (exam_id,)).fetchone()
    if (cnt_row["cnt"] or 0) <= 1:
        conn.close()
        raise HTTPException(status_code=400, detail="Bộ đề phải có tối thiểu 1 câu hỏi. Không thể xóa câu cuối cùng.")

    cur.execute("DELETE FROM questions WHERE id = ?", (question_id,))

    # Đánh lại số thứ tự câu hỏi liên tục 1..N
    remaining = cur.execute(
        "SELECT id FROM questions WHERE exam_id = ? ORDER BY question_order ASC, id ASC",
        (exam_id,),
    ).fetchall()
    for idx_ord, r_item in enumerate(remaining, start=1):
        cur.execute("UPDATE questions SET question_order = ? WHERE id = ?", (idx_ord, r_item["id"]))

    cur.execute("UPDATE exams SET total_questions = ? WHERE id = ?", (len(remaining), exam_id))
    log_user_activity(
        conn,
        user["id"],
        "DELETE_QUESTION",
        f"Đã xóa câu hỏi số {q_row['question_order']} khỏi bộ đề '{q_row['title']}'",
        {"exam_id": exam_id, "deleted_question_id": question_id},
    )
    conn.commit()
    conn.close()
    return get_user_exam_detail(exam_id, user)


@app.post("/api/exams/{exam_id}/shuffle")
def shuffle_exam_variant(
    exam_id: int,
    req: Optional[ShuffleExamPayload] = None,
    user: dict = Depends(require_current_user),
):
    """Trộn thứ tự câu hỏi và đảo phương án A/B/C/D để tạo mã đề thi mới chống quay cóp."""
    orig_exam = get_user_exam_detail(exam_id, user)
    orig_questions = list(orig_exam.get("questions", []))
    if not orig_questions:
        raise HTTPException(status_code=400, detail="Bộ đề gốc chưa có câu hỏi để trộn.")

    # Tạo mã đề mới tự động
    base_code = re.sub(r"-M\d+$", "", orig_exam["exam_code"].strip())
    rand_suffix = random.randint(102, 999)
    new_code = (
        req.new_exam_code.strip()
        if (req and req.new_exam_code and req.new_exam_code.strip())
        else f"{base_code}-{rand_suffix}"
    )
    base_title = re.sub(r"\s*\(Mã trộn [^\)]+\)$", "", orig_exam["title"].strip())
    new_title = f"{base_title} (Mã trộn {new_code})"

    shuffled_qs = list(orig_questions)
    random.shuffle(shuffled_qs)

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO exams (
            user_id, document_id, title, subject, exam_code,
            duration_minutes, total_questions, source_context, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user["id"],
            orig_exam.get("document_id"),
            new_title,
            orig_exam["subject"],
            new_code,
            orig_exam["duration_minutes"],
            len(shuffled_qs),
            orig_exam.get("source_context", ""),
            now_str,
        ),
    )
    new_exam_id = cur.lastrowid

    for new_ord, q in enumerate(shuffled_qs, start=1):
        q_type = q.get("question_type") or "multiple_choice"
        opt_a, opt_b, opt_c, opt_d = q["opt_a"], q["opt_b"], q["opt_c"], q["opt_d"]
        correct_ans = q["correct_answer"]
        extra_str = q.get("extra_data") or "{}"

        if q_type == "multiple_choice":
            orig_map = {"A": opt_a, "B": opt_b, "C": opt_c, "D": opt_d}
            orig_correct_key = (correct_ans or "A").strip().upper()
            if orig_correct_key not in orig_map:
                orig_correct_key = "A"
            keys = ["A", "B", "C", "D"]
            random.shuffle(keys)
            new_opts = {}
            new_correct_key = "A"
            for idx_k, target_k in enumerate(["A", "B", "C", "D"]):
                src_k = keys[idx_k]
                new_opts[target_k] = orig_map[src_k]
                if src_k == orig_correct_key:
                    new_correct_key = target_k
            opt_a, opt_b, opt_c, opt_d = new_opts["A"], new_opts["B"], new_opts["C"], new_opts["D"]
            correct_ans = new_correct_key

        elif q_type == "matching":
            try:
                extra_obj = json.loads(extra_str)
                col_a = extra_obj.get("col_a", [])
                col_b = extra_obj.get("col_b", [])
                old_map = extra_obj.get("mapping", {})
                if len(col_a) == 4 and len(col_b) == 4 and old_map:
                    old_b_by_id = {item["id"]: item["text"] for item in col_b}
                    correct_b_texts = [old_b_by_id.get(old_map.get(str(i + 1), "A"), "") for i in range(4)]
                    perm = [0, 1, 2, 3]
                    random.shuffle(perm)
                    letters = ["A", "B", "C", "D"]
                    new_col_b = [None] * 4
                    new_mapping = {}
                    for i in range(4):
                        b_pos = perm[i]
                        b_let = letters[b_pos]
                        new_col_b[b_pos] = {"id": b_let, "text": correct_b_texts[i]}
                        new_mapping[str(i + 1)] = b_let
                    b_lookup = {item["id"]: item["text"] for item in new_col_b}
                    opt_a = f"1. {col_a[0]['text']}  ⟷  {new_mapping['1']}. {b_lookup[new_mapping['1']]}"
                    opt_b = f"2. {col_a[1]['text']}  ⟷  {new_mapping['2']}. {b_lookup[new_mapping['2']]}"
                    opt_c = f"3. {col_a[2]['text']}  ⟷  {new_mapping['3']}. {b_lookup[new_mapping['3']]}"
                    opt_d = f"4. {col_a[3]['text']}  ⟷  {new_mapping['4']}. {b_lookup[new_mapping['4']]}"
                    correct_ans = ", ".join(f"{k}-{new_mapping[k]}" for k in ["1", "2", "3", "4"])
                    extra_obj["col_b"] = new_col_b
                    extra_obj["mapping"] = new_mapping
                    extra_str = json.dumps(extra_obj, ensure_ascii=False)
            except Exception:
                pass

        cur.execute(
            """
            INSERT INTO questions (
                exam_id, question_order, question_type, difficulty, question_text,
                opt_a, opt_b, opt_c, opt_d, correct_answer, explanation, extra_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_exam_id,
                new_ord,
                q_type,
                q["difficulty"],
                q["question_text"],
                opt_a,
                opt_b,
                opt_c,
                opt_d,
                correct_ans,
                q["explanation"],
                extra_str,
            ),
        )

    log_user_activity(
        conn,
        user["id"],
        "SHUFFLE_EXAM",
        f"Đã trộn & tạo mã đề mới '{new_code}' từ đề gốc '{orig_exam['exam_code']}' ({len(shuffled_qs)} câu hỏi)",
        {"source_exam_id": exam_id, "new_exam_id": new_exam_id, "new_exam_code": new_code},
    )
    conn.commit()
    conn.close()
    return get_user_exam_detail(new_exam_id, user)


@app.delete("/api/exams/{exam_id}")
def delete_user_exam(exam_id: int, user: dict = Depends(require_current_user)):
    conn = get_db()
    cur = conn.cursor()
    row = cur.execute("SELECT title FROM exams WHERE id = ? AND user_id = ?", (exam_id, user["id"])).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Bộ đề không tồn tại.")

    cur.execute("DELETE FROM questions WHERE exam_id = ?", (exam_id,))
    cur.execute("DELETE FROM quiz_attempts WHERE exam_id = ?", (exam_id,))
    cur.execute("DELETE FROM exams WHERE id = ?", (exam_id,))
    log_user_activity(conn, user["id"], "DELETE_EXAM", f"Đã xóa bộ đề '{row['title']}'")
    conn.commit()
    conn.close()
    return {"status": "ok"}


# ============================================================================
# 5. API XUẤT BỘ ĐỀ THI (WORD .DOCX ĐẦY ĐỦ, WORD ĐỀ HỌC SINH, MD, JSON)
# ============================================================================
@app.get("/api/exams/{exam_id}/export")
def export_user_exam(
    exam_id: int,
    format: str = Query(default="docx_full"),
    token: Optional[str] = Query(default=None),
    authorization: Optional[str] = Header(default=None),
):
    auth_token = token
    if not auth_token and authorization and authorization.startswith("Bearer "):
        auth_token = authorization.replace("Bearer ", "", 1).strip()
    user = get_user_by_token(auth_token or "")
    if not user:
        raise HTTPException(status_code=401, detail="Vui lòng đăng nhập để xuất bộ đề.")

    exam = get_user_exam_detail(exam_id, user)
    conn = get_db()
    log_user_activity(
        conn,
        user["id"],
        "EXPORT_EXAM",
        f"Đã xuất bộ đề '{exam['title']}' ra định dạng {format.upper()}",
        {"exam_id": exam_id, "format": format},
    )
    conn.commit()
    conn.close()

    code_slug = re.sub(r"[^a-zA-Z0-9_\-]", "_", exam["exam_code"]) if "re" in globals() else exam["exam_code"]

    if format == "docx_student":
        docx_bytes = build_exam_docx(exam, include_answers=False)
        return Response(
            content=docx_bytes,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="De_Thi_{code_slug}_Ban_Hoc_Sinh.docx"'},
        )
    elif format == "md":
        md_str = build_exam_markdown(exam)
        return Response(
            content=md_str.encode("utf-8"),
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="De_Thi_{code_slug}.md"'},
        )
    elif format == "json":
        json_str = json.dumps(exam, ensure_ascii=False, indent=2)
        return Response(
            content=json_str.encode("utf-8"),
            media_type="application/json; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="De_Thi_{code_slug}.json"'},
        )
    else:
        docx_bytes = build_exam_docx(exam, include_answers=True)
        return Response(
            content=docx_bytes,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="De_Thi_{code_slug}_Co_Dap_An.docx"'},
        )


# ============================================================================
# 6. API LÀM ĐỀ THI THỬ & LỊCH SỬ HOẠT ĐỘNG TÀI KHOẢN
# ============================================================================
@app.post("/api/exams/{exam_id}/attempt")
def submit_quiz_attempt(
    exam_id: int,
    req: QuizSubmitPayload,
    user: dict = Depends(require_current_user),
):
    exam = get_user_exam_detail(exam_id, user)
    questions = exam["questions"]
    if not questions:
        raise HTTPException(status_code=400, detail="Bộ đề chưa có câu hỏi.")

    total_points_earned = 0.0
    correct_cnt = 0
    details = []
    bloom_breakdown: Dict[str, Dict[str, float]] = {}
    type_breakdown: Dict[str, Dict[str, float]] = {}

    for q in questions:
        raw_ans = req.answers.get(str(q["id"]), "")
        grade_res = grade_user_question_answer(q, raw_ans)
        pts = float(grade_res["points_earned"])
        total_points_earned += pts
        if grade_res["is_correct"]:
            correct_cnt += 1

        diff = q.get("difficulty", "Thông hiểu")
        if diff not in bloom_breakdown:
            bloom_breakdown[diff] = {"total": 0, "earned": 0.0}
        bloom_breakdown[diff]["total"] += 1
        bloom_breakdown[diff]["earned"] = round(bloom_breakdown[diff]["earned"] + pts, 2)

        qtype = q.get("question_type", "multiple_choice")
        if qtype not in type_breakdown:
            type_breakdown[qtype] = {"total": 0, "earned": 0.0}
        type_breakdown[qtype]["total"] += 1
        type_breakdown[qtype]["earned"] = round(type_breakdown[qtype]["earned"] + pts, 2)

        details.append(
            {
                "question_id": q["id"],
                "question_order": q["question_order"],
                "question_type": qtype,
                "difficulty": diff,
                "points_earned": pts,
                "user_choice": grade_res["formatted_user_answer"],
                "correct_answer": q["correct_answer"],
                "is_correct": grade_res["is_correct"],
                "explanation": grade_res["feedback_note"],
            }
        )

    total_q = len(questions)
    score = round(total_points_earned / total_q * 10.0, 2)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = get_db()
    conn.execute(
        """
        INSERT INTO quiz_attempts (user_id, exam_id, score, correct_count, total_questions, time_spent_sec, answers_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user["id"],
            exam_id,
            score,
            correct_cnt,
            total_q,
            req.time_spent_sec,
            json.dumps(req.answers, ensure_ascii=False),
            now_str,
        ),
    )
    log_user_activity(
        conn,
        user["id"],
        "TAKE_QUIZ",
        f"Đã làm bài thi thử '{exam['title']}' — Đạt {score}/10 điểm ({correct_cnt}/{total_q} câu đúng)",
        {"exam_id": exam_id, "score": score},
    )
    conn.commit()
    conn.close()

    return {
        "exam_id": exam_id,
        "exam_title": exam["title"],
        "score": score,
        "correct_count": correct_cnt,
        "total_questions": total_q,
        "time_spent_sec": req.time_spent_sec,
        "bloom_breakdown": bloom_breakdown,
        "type_breakdown": type_breakdown,
        "details": details,
    }


@app.get("/api/attempts/{attempt_id}")
def get_quiz_attempt_detail(attempt_id: int, user: dict = Depends(require_current_user)):
    conn = get_db()
    cur = conn.cursor()
    row = cur.execute(
        """
        SELECT qa.*, e.title as exam_title, e.exam_code, e.subject
        FROM quiz_attempts qa
        JOIN exams e ON qa.exam_id = e.id
        WHERE qa.id = ? AND qa.user_id = ?
        """,
        (attempt_id, user["id"]),
    ).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Không tìm thấy lịch sử bài làm.")

    attempt = dict(row)
    q_rows = cur.execute(
        "SELECT * FROM questions WHERE exam_id = ? ORDER BY question_order ASC",
        (attempt["exam_id"],),
    ).fetchall()
    conn.close()

    try:
        saved_answers = json.loads(attempt.get("answers_json") or "{}")
    except Exception:
        saved_answers = {}

    details = []
    for r in q_rows:
        q = dict(r)
        raw_ans = saved_answers.get(str(q["id"]), "")
        grade_res = grade_user_question_answer(q, raw_ans)
        details.append(
            {
                "question_id": q["id"],
                "question_order": q["question_order"],
                "question_type": q.get("question_type", "multiple_choice"),
                "difficulty": q.get("difficulty", "Thông hiểu"),
                "question_text": q.get("question_text", ""),
                "points_earned": float(grade_res["points_earned"]),
                "user_choice": grade_res["formatted_user_answer"],
                "correct_answer": q["correct_answer"],
                "is_correct": grade_res["is_correct"],
                "explanation": grade_res["feedback_note"],
            }
        )

    attempt["details"] = details
    return attempt


@app.get("/api/history")
def get_user_history_and_stats(user: dict = Depends(require_current_user)):
    conn = get_db()
    cur = conn.cursor()

    total_exams = cur.execute("SELECT COUNT(*) as c FROM exams WHERE user_id = ?", (user["id"],)).fetchone()["c"]
    total_docs = cur.execute("SELECT COUNT(*) as c FROM documents WHERE user_id = ?", (user["id"],)).fetchone()["c"]
    total_qs = cur.execute(
        "SELECT COUNT(*) as c FROM questions q JOIN exams e ON q.exam_id = e.id WHERE e.user_id = ?",
        (user["id"],),
    ).fetchone()["c"]

    activities = [
        dict(r)
        for r in cur.execute(
            "SELECT * FROM activity_history WHERE user_id = ? ORDER BY id DESC LIMIT 40",
            (user["id"],),
        ).fetchall()
    ]

    attempts = [
        dict(r)
        for r in cur.execute(
            """
            SELECT qa.*, e.title as exam_title, e.exam_code, e.subject
            FROM quiz_attempts qa
            JOIN exams e ON qa.exam_id = e.id
            WHERE qa.user_id = ?
            ORDER BY qa.id DESC LIMIT 20
            """,
            (user["id"],),
        ).fetchall()
    ]

    conn.close()
    return {
        "summary": {
            "total_exams": total_exams,
            "total_documents": total_docs,
            "total_questions": total_qs,
            "total_attempts": len(attempts),
        },
        "activities": activities,
        "quiz_attempts": attempts,
    }


# ============================================================================
# 7. API QUẢN LÝ QUY TRÌNH HUẤN LUYỆN AI (DATASET & MODEL PIPELINE)
# ============================================================================
class RunTrainingPayload(BaseModel):
    epochs: int = 3
    lora_rank: int = 16


@app.get("/api/training/info")
def get_ai_training_pipeline_info(user: dict = Depends(require_current_user)):
    stats = get_training_corpus_stats()
    training_log = get_latest_training_log()
    return {
        "model_config": MODEL_CONFIG,
        "corpus_stats": stats,
        "training_log": training_log,
    }


@app.get("/api/training/samples")
def get_training_samples_explorer(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=8, ge=1, le=50),
    source: str = Query(default=""),
    qtype: str = Query(default=""),
    difficulty: str = Query(default=""),
    search: str = Query(default=""),
    user: dict = Depends(require_current_user),
):
    return query_training_samples(
        page=page,
        page_size=page_size,
        source=source,
        qtype=qtype,
        difficulty=difficulty,
        search=search,
    )


@app.post("/api/training/run")
def trigger_qlora_training(
    req: RunTrainingPayload,
    user: dict = Depends(require_current_user),
):
    result = run_qlora_training(epochs=max(1, min(10, req.epochs)), lora_rank=req.lora_rank)
    conn = get_db()
    log_user_activity(
        conn,
        user["id"],
        "TRAIN_MODEL",
        f"Đã chạy huấn luyện QLoRA ({result['epochs']} epochs, {result['trained_samples']} mẫu) -> Final Loss: {result['final_training_loss']}",
        {"final_loss": result["final_training_loss"], "trained_samples": result["trained_samples"]},
    )
    conn.commit()
    conn.close()
    return result


@app.post("/api/training/contribute/{exam_id}")
def contribute_exam_to_dataset(exam_id: int, user: dict = Depends(require_current_user)):
    exam = get_user_exam_detail(exam_id, user)
    added_cnt = add_exam_to_training_corpus(exam)

    conn = get_db()
    log_user_activity(
        conn,
        user["id"],
        "TRAIN_DATA",
        f"Đã đóng góp {added_cnt} câu hỏi từ bộ đề '{exam['title']}' vào tập dữ liệu huấn luyện AI",
        {"exam_id": exam_id, "added_samples": added_cnt},
    )
    conn.commit()
    conn.close()
    return {"status": "ok", "added_samples": added_cnt}


# Khởi tạo Database, Tập dữ liệu huấn luyện và Tài liệu mẫu ngay khi chạy Server
init_database()
init_training_corpus()
create_sample_docx_files()

if __name__ == "__main__":
    print("\n" + "=" * 75)
    print("🚀 HỆ THỐNG WEB AI SINH ĐỀ THI ĐÃ KHỞI ĐỘNG THÀNH CÔNG!")
    print("🌐 Địa chỉ truy cập Web: http://localhost:8000")
    print("🔑 Tài khoản dùng thử: demo@aiexam.vn | Mật khẩu: 123456 (hoặc Đăng ký mới)")
    print("=" * 75 + "\n")
    uvicorn.run(app, host="127.0.0.1", port=8000)
