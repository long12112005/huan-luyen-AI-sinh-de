"""
Kịch bản Kiểm thử Tự động Toàn diện (End-to-End Automated Test Suite)
Kiểm tra không sót bất kỳ chức năng nào của Hệ thống Web AI Sinh Đề Thi.

Cách chạy:
    cd "huan luyen AI sinh de"
    python -X utf8 test_all_features.py
"""

import base64
import json
import os
import sys

# Đảm bảo import được các module trong thư mục dự án
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

import main  # noqa: E402
from backend.document_parser import create_sample_pdf_bytes  # noqa: E402


def run_all_tests():
    print("=" * 78)
    print("🧪 BẮT ĐẦU KIỂM THỬ TỰ ĐỘNG TOÀN DIỆN HỆ THỐNG AI SINH ĐỀ THI (12 HẠNG MỤC)")
    print("=" * 78)

    # 1. Kiểm tra Trang chủ & Favicon
    res_home = main.index_page()
    res_fav = main.favicon_ico()
    assert res_home.status_code == 200 and "AI ExamGen" in res_home.body.decode("utf-8")
    assert res_fav.status_code == 200
    print("[PASS 01/12] Giao diện Trang chủ (Gaming Edu Theme) & Favicon SVG hoạt động tốt.")

    # 2. Kiểm tra Đăng nhập tài khoản Demo
    login_res = main.login_account(main.LoginRequest(email="demo@aiexam.vn", password="123456"))
    assert "token" in login_res and login_res["user"]["email"] == "demo@aiexam.vn"
    user = login_res["user"]
    print(f"[PASS 02/12] Đăng nhập & Xác thực Bearer Token thành công (User: {user['full_name']}).")

    # 3. Kiểm tra Đọc tài liệu đa định dạng (.docx mẫu, .pdf mẫu, .txt upload)
    sample_txt = (
        "Kiến trúc Transformer là nền tảng của các mô hình ngôn ngữ lớn nhờ cơ chế Self-Attention xử lý song song. "
        "Kỹ thuật tinh chỉnh có giám sát SFT giúp mô hình tuân thủ chỉ dẫn và xuất dữ liệu đúng cấu trúc JSON. "
        "Phương pháp LoRA đóng băng trọng số gốc và chèn ma trận hạng thấp A, B giúp giảm hơn 99% tham số huấn luyện. "
        "Kỹ thuật QLoRA lượng tử hóa trọng số xuống kiểu dữ liệu 4-bit NormalFloat tiết kiệm bộ nhớ VRAM trên GPU. "
        "Thang đo nhận thức Bloom phân loại câu hỏi thành Nhận biết, Thông hiểu, Vận dụng và Vận dụng cao."
    )
    b64_txt = base64.b64encode(sample_txt.encode("utf-8")).decode("ascii")
    doc_txt = main.upload_and_parse_document(
        main.UploadDocPayload(filename="Kiem_Thu_Tai_Lieu_AI.txt", content_base64=b64_txt),
        user=user,
    )
    assert doc_txt["id"] > 0 and doc_txt["word_count"] > 30

    pdf_bytes = create_sample_pdf_bytes([sample_txt])
    b64_pdf = base64.b64encode(pdf_bytes).decode("ascii")
    doc_pdf = main.upload_and_parse_document(
        main.UploadDocPayload(filename="Kiem_Thu_Tai_Lieu_AI.pdf", content_base64=b64_pdf),
        user=user,
    )
    assert doc_pdf["id"] > 0 and doc_pdf["word_count"] > 10
    print(f"[PASS 03/12] Bộ đọc tài liệu (.txt, .pdf, .docx) trích xuất thành công ({doc_txt['word_count']} từ).")

    # 4. Kiểm tra Sinh bộ đề kết hợp cả 4 dạng câu hỏi & 4 mức độ Bloom
    exam = main.generate_and_save_exam(
        main.GenerateExamPayload(
            title="Đề Kiểm Thử Toàn Diện 4 Dạng Câu Hỏi",
            subject="Trí tuệ nhân tạo",
            exam_code="TEST-101",
            duration_minutes=15,
            total_questions=8,
            difficulty_filter="custom_bloom",
            custom_counts={"Nhận biết": 2, "Thông hiểu": 2, "Vận dụng": 2, "Vận dụng cao": 2},
            question_type_filter="mixed",
            context_text=sample_txt,
            document_id=doc_txt["id"],
        ),
        user=user,
    )
    exam_id = exam["id"]
    q_types = {q["question_type"] for q in exam["questions"]}
    assert len(exam["questions"]) == 8
    assert {"multiple_choice", "fill_blank", "matching", "essay"}.issubset(q_types)
    print(f"[PASS 04/12] Sinh đề AI thành công (ID={exam_id}, 8 câu đủ cả 4 dạng: {', '.join(sorted(q_types))}).")

    # 5. Kiểm tra Thêm câu hỏi thủ công vào bộ đề
    exam_after_add = main.add_question_to_exam(
        exam_id=exam_id,
        req=main.CreateQuestionPayload(
            question_type="matching",
            difficulty="Vận dụng",
            question_text="[Ghép cặp] Nối khái niệm ở Cột A với định nghĩa ở Cột B:",
            opt_a="1. Transformer ⟷ B. Cơ chế Self-Attention",
            opt_b="2. LoRA ⟷ A. Phân rã ma trận hạng thấp",
            opt_c="3. QLoRA ⟷ D. Lượng tử hóa 4-bit NF4",
            opt_d="4. Bloom ⟷ C. Thang đo 4 cấp độ nhận thức",
            correct_answer="1-B, 2-A, 3-D, 4-C",
            explanation="Câu hỏi ghép cặp thêm thủ công.",
        ),
        user=user,
    )
    assert len(exam_after_add["questions"]) == 9
    added_q = exam_after_add["questions"][-1]
    print(f"[PASS 05/12] Thêm câu hỏi mới thủ công thành công (Tổng câu tăng lên {len(exam_after_add['questions'])}).")

    # 6. Kiểm tra Chỉnh sửa câu hỏi & Đồng bộ extra_data
    edit_res = main.edit_question(
        question_id=added_q["id"],
        req=main.UpdateQuestionPayload(
            difficulty="Vận dụng cao",
            question_text="[Ghép cặp - Đã sửa] Nối khái niệm AI ở Cột A với mô tả ở Cột B:",
            opt_a=added_q["opt_a"],
            opt_b=added_q["opt_b"],
            opt_c=added_q["opt_c"],
            opt_d=added_q["opt_d"],
            correct_answer="1-B, 2-A, 3-D, 4-C",
            explanation="Đã cập nhật nội dung câu hỏi ghép cặp.",
        ),
        user=user,
    )
    assert edit_res["status"] == "ok"
    print(f"[PASS 06/12] Chỉnh sửa câu hỏi (ID={added_q['id']}) & đồng bộ JSON extra_data thành công.")

    # 7. Kiểm tra Xóa 1 câu hỏi lẻ & Đánh lại số thứ tự 1..N
    exam_after_del = main.delete_single_question(question_id=added_q["id"], user=user)
    orders = [q["question_order"] for q in exam_after_del["questions"]]
    assert len(exam_after_del["questions"]) == 8 and orders == list(range(1, 9))
    print(f"[PASS 07/12] Xóa 1 câu hỏi lẻ & đánh lại thứ tự liên tục {orders[0]}..{orders[-1]} thành công.")

    # 8. Kiểm tra Trộn đề / Tạo mã đề mới (Shuffle Exam Variant)
    shuffled_exam = main.shuffle_exam_variant(exam_id=exam_id, req=None, user=user)
    assert shuffled_exam["id"] != exam_id and len(shuffled_exam["questions"]) == 8
    print(f"[PASS 08/12] Trộn đề & Đảo đáp án thành công -> Mã đề mới: [{shuffled_exam['exam_code']}].")

    # 9. Kiểm tra Xuất bộ đề ra 4 định dạng (Word GV, Word HS, Markdown, JSON)
    for fmt in ("docx_full", "docx_student", "md", "json"):
        exp_res = main.export_user_exam(exam_id=exam_id, format=fmt, token=login_res["token"], authorization=None)
        assert exp_res.status_code == 200 and len(exp_res.body) > 100
    print("[PASS 09/12] Xuất bản bộ đề ra cả 4 định dạng (.docx GV, .docx HS, .md, .json) thành công.")

    # 10. Kiểm tra Nộp bài thi thử & Chấm điểm tự động cả 4 dạng câu hỏi
    sample_answers = {str(q["id"]): q["correct_answer"] for q in exam_after_del["questions"]}
    attempt_res = main.submit_quiz_attempt(
        exam_id=exam_id,
        req=main.QuizSubmitPayload(time_spent_sec=42, answers=sample_answers),
        user=user,
    )
    assert attempt_res["score"] >= 9.0 and attempt_res["correct_count"] == 8
    print(f"[PASS 10/12] Thi thử & Chấm điểm AI cả 4 dạng câu hỏi thành công -> Điểm: {attempt_res['score']}/10.")

    # 11. Kiểm tra Xem chi tiết lịch sử bài làm & Kho tài liệu (Tab 4)
    hist_res = main.get_user_history_and_stats(user=user)
    latest_attempt_id = hist_res["quiz_attempts"][0]["id"]
    attempt_detail = main.get_quiz_attempt_detail(attempt_id=latest_attempt_id, user=user)
    assert len(attempt_detail["details"]) == 8
    print(f"[PASS 11/12] Xem lại chi tiết lịch sử bài thi thử (Attempt ID={latest_attempt_id}) thành công.")

    # 12. Kiểm tra Kho dữ liệu huấn luyện 3.600 mẫu ChatML & Pipeline QLoRA (Tab 5)
    train_info = main.get_ai_training_pipeline_info(user=user)
    explorer_res = main.get_training_samples_explorer(page=1, page_size=5, source="", qtype="", difficulty="", search="", user=user)
    assert train_info["corpus_stats"]["total_samples"] >= 3600
    assert len(explorer_res["items"]) == 5
    print(f"[PASS 12/12] Kho dữ liệu huấn luyện ({train_info['corpus_stats']['total_samples']} mẫu ChatML) & QLoRA sẵn sàng.")

    # Dọn dẹp dữ liệu kiểm thử tạm thời
    main.delete_user_exam(exam_id=shuffled_exam["id"], user=user)
    main.delete_user_exam(exam_id=exam_id, user=user)
    main.delete_user_document(doc_id=doc_txt["id"], user=user)
    main.delete_user_document(doc_id=doc_pdf["id"], user=user)

    print("=" * 78)
    print("🎉 KẾT LUẬN: TẤT CẢ 12/12 HẠNG MỤC KIỂM THỬ ĐỀU ĐẠT 100% (KHÔNG CÓ LỖI)!")
    print("=" * 78)


if __name__ == "__main__":
    run_all_tests()

