"""
Module Đánh giá Chất lượng Mô hình & Bộ Đề Sinh Ra (Model & Exam Evaluator).
Hỗ trợ đánh giá cho cả 4 dạng câu hỏi:
1. multiple_choice (Trắc nghiệm 4 lựa chọn)
2. fill_blank (Điền khuyết)
3. matching (Ghép cặp Cột A - Cột B)
4. essay (Tự luận kèm Rubric chấm điểm)
"""

import re


def _word_count(text: str) -> int:
    return max(1, len(re.findall(r"\w+", str(text), flags=re.UNICODE)))


def evaluate_generated_questions(questions: list[dict]) -> dict:
    if not questions:
        return {
            "total_evaluated": 0,
            "format_validity_rate": 0.0,
            "distractor_uniqueness_rate": 0.0,
            "length_balance_rate": 0.0,
            "overall_quality_score": 0.0,
        }

    valid_format = 0
    unique_opts = 0
    balanced_len = 0

    for q in questions:
        q_type = q.get("question_type") or "multiple_choice"

        if q_type == "multiple_choice":
            has_fields = (
                bool(str(q.get("question_text", "")).strip())
                and all(bool(str(q.get(k, "")).strip()) for k in ["opt_a", "opt_b", "opt_c", "opt_d"])
                and str(q.get("correct_answer", "")).upper() in ["A", "B", "C", "D"]
                and bool(str(q.get("explanation", "")).strip())
            )
            if has_fields:
                valid_format += 1

            opts = [str(q.get(k, "")).strip().lower() for k in ["opt_a", "opt_b", "opt_c", "opt_d"]]
            if len(set(opts)) == 4:
                unique_opts += 1

            ans_key = "opt_" + str(q.get("correct_answer", "A")).lower()
            ans_wc = _word_count(q.get(ans_key, ""))
            dist_wcs = [
                _word_count(q.get(k, ""))
                for k in ["opt_a", "opt_b", "opt_c", "opt_d"]
                if k != ans_key
            ]
            avg_dist = sum(dist_wcs) / max(1, len(dist_wcs))
            ratio = ans_wc / max(1.0, avg_dist)
            if 0.40 <= ratio <= 2.4:
                balanced_len += 1
        else:
            # Điền khuyết, Ghép cặp, Tự luận: Kiểm tra cấu trúc câu hỏi + đáp án + giải thích
            has_fields = (
                bool(str(q.get("question_text", "")).strip())
                and bool(str(q.get("correct_answer", "")).strip())
                and bool(str(q.get("explanation", "")).strip())
            )
            if has_fields:
                valid_format += 1
                unique_opts += 1
                balanced_len += 1

    n = len(questions)
    fvr = round(valid_format / n * 100, 1)
    dur = round(unique_opts / n * 100, 1)
    lbr = round(balanced_len / n * 100, 1)
    overall = round((fvr * 0.4 + dur * 0.35 + lbr * 0.25), 1)

    return {
        "total_evaluated": n,
        "format_validity_rate": fvr,
        "distractor_uniqueness_rate": dur,
        "length_balance_rate": lbr,
        "overall_quality_score": overall,
    }
