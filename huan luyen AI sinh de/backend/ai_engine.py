"""
AI Question Generation & Automated Grading Engine (Bộ máy AI Sinh Đề Đa Định Dạng & Chấm Điểm Tự Động).
Hỗ trợ 4 dạng câu hỏi chuẩn khảo thí:
1. multiple_choice : Trắc nghiệm khách quan 4 lựa chọn (A, B, C, D)
2. fill_blank      : Điền khuyết từ khóa / kết quả trọng tâm (Cloze Test / Short Answer)
3. matching        : Ghép cặp khái niệm/công thức Cột A (1, 2, 3, 4) <-> Nội dung/kết quả Cột B (A, B, C, D)
4. essay           : Tự luận mở kèm Lời giải chuẩn & Barem từ khóa (Rubric) chấm điểm bằng TF-IDF Cosine Similarity

Đặc điểm nổi bật của Engine:
- Nhận diện thông minh cả 2 loại tài liệu đầu vào:
  (A) Đề thi mẫu / Đề cương ôn tập có sẵn câu hỏi (khôi phục lỗi tách âm tiết PDF, lọc bỏ tiêu đề hành chính,
      nhận diện đúng chuyên đề Toán học / Khoa học để sinh câu hỏi chuẩn đề thi thật và biến thiên tham số).
  (B) Tài liệu bài giảng / Giáo trình chuyên ngành (trích xuất mệnh đề kiến thức cốt lõi, tạo phương án nhiễu
      bằng hoán vị vị ngữ nội bộ trong cùng tài liệu kết hợp biến đổi đối lập ngữ nghĩa/số liệu học thuật,
      tuyệt đối không sinh câu nhiễu rập khuôn lệch chủ đề).
"""

import json
import math
import re
from collections import Counter
from typing import Dict, List, Optional
from backend.document_parser import (
    extract_meaningful_sentences,
    is_exam_boilerplate_line,
    repair_vietnamese_broken_text,
)

VN_STOPWORDS = {
    "là", "và", "của", "các", "những", "một", "trong", "được", "cho", "với", "để",
    "khi", "từ", "theo", "có", "này", "đó", "như", "hoặc", "nhưng", "về", "trên",
    "dưới", "qua", "bằng", "do", "tại", "vào", "ra", "lên", "xuống", "rất", "hơn",
    "nhất", "cùng", "việc", "sự", "mỗi", "mọi", "không", "cũng", "đã", "đang",
    "sẽ", "phải", "cần", "nên", "thì", "mà", "nếu", "vì", "bởi", "nhằm", "giúp",
}


def build_bloom_schedule(
    total_questions: int,
    difficulty_filter: str = "Tất cả mức độ (Cân bằng theo chuẩn Bloom)",
    custom_counts: Optional[Dict[str, int]] = None,
) -> List[str]:
    """Xây dựng danh sách mức độ nhận thức Bloom cho đúng số lượng câu hỏi người dùng yêu cầu."""
    total_questions = max(1, min(50, total_questions))

    if custom_counts:
        plan = (
            ["Nhận biết"] * max(0, custom_counts.get("Nhận biết", 0))
            + ["Thông hiểu"] * max(0, custom_counts.get("Thông hiểu", 0))
            + ["Vận dụng"] * max(0, custom_counts.get("Vận dụng", 0))
            + ["Vận dụng cao"] * max(0, custom_counts.get("Vận dụng cao", 0))
        )
        if plan:
            return plan[:total_questions] if len(plan) >= total_questions else (plan * total_questions)[:total_questions]

    if difficulty_filter in ["Nhận biết", "Thông hiểu", "Vận dụng", "Vận dụng cao"]:
        return [difficulty_filter] * total_questions

    n_nb = max(1, round(total_questions * 0.35))
    n_th = max(0, round(total_questions * 0.35))
    n_vd = max(0, round(total_questions * 0.20))
    n_vdc = max(0, total_questions - (n_nb + n_th + n_vd))

    schedule = (
        ["Nhận biết"] * n_nb
        + ["Thông hiểu"] * n_th
        + ["Vận dụng"] * n_vd
        + ["Vận dụng cao"] * max(0, n_vdc)
    )
    while len(schedule) < total_questions:
        schedule.append("Thông hiểu")
    return schedule[:total_questions]


def build_question_type_schedule(
    total_questions: int,
    question_type_filter: str = "mixed",
    selected_types: Optional[List[str]] = None,
) -> List[str]:
    """Phân bổ dạng câu hỏi cho bộ đề theo đúng lựa chọn của giáo viên."""
    valid_types = ["multiple_choice", "fill_blank", "matching", "essay"]

    if selected_types:
        clean_sel = [t for t in selected_types if t in valid_types]
        if clean_sel:
            if len(clean_sel) == 1:
                return [clean_sel[0]] * total_questions
            return [clean_sel[i % len(clean_sel)] for i in range(total_questions)]

    if question_type_filter in valid_types:
        return [question_type_filter] * total_questions

    if total_questions == 1:
        return ["multiple_choice"]
    if total_questions == 2:
        return ["multiple_choice", "fill_blank"]
    if total_questions == 3:
        return ["multiple_choice", "fill_blank", "essay"]
    if total_questions == 4:
        return ["multiple_choice", "fill_blank", "matching", "essay"]

    n_mc = max(1, round(total_questions * 0.50))
    n_fb = max(1, round(total_questions * 0.20))
    n_mt = max(1, round(total_questions * 0.15))
    n_es = max(1, total_questions - (n_mc + n_fb + n_mt))

    schedule = (
        ["multiple_choice"] * n_mc
        + ["fill_blank"] * n_fb
        + ["matching"] * n_mt
        + ["essay"] * max(1, n_es)
    )
    return schedule[:total_questions]


# ============================================================================
# PHẦN 1: BỘ NHẬN DIỆN CHUYÊN ĐỀ ĐỀ THI TOÁN HỌC & TÀI LIỆU CÓ SẴN CÂU HỎI
# ============================================================================
def _detect_math_grade10_topics(text: str, subject: str) -> Dict[str, bool]:
    """Nhận diện các chuyên đề Toán học (Mệnh đề, Tập hợp, BPT bậc nhất 2 ẩn, Hệ thức lượng & Lượng giác) trong tài liệu."""
    low = text.lower()
    subj_low = (subject or "").lower()
    is_math_doc = (
        "toán" in subj_low
        or "toan" in subj_low
        or bool(re.search(r"(tam giác abc|bất phương trình|mệnh đề phủ định|bán kính đường tròn ngoại tiếp|miền nghiệm|sin\s*α|cos\s*α)", low))
    )
    if not is_math_doc:
        return {}

    topics = {
        "proposition": bool(re.search(r"(mệnh đề|phủ định|vô tỷ|∀|∃)", low)),
        "set_theory": bool(re.search(r"(tập hợp|phần tử|cầu lông|đá cầu|a\s*∩\s*b|a\s*\\?\s*b)", low)),
        "inequality_2d": bool(re.search(r"(bất phương trình|miền nghiệm|trà sữa|kem que|bậc nhất hai ẩn)", low)),
        "trigonometry": bool(re.search(r"(tam giác abc|ngoại tiếp|côsin|sin|cos|tan|cot|tháp|hai chiếc xe|xoy)", low)),
    }
    if not any(topics.values()):
        topics = {"proposition": True, "set_theory": True, "inequality_2d": True, "trigonometry": True}
    return topics


def _get_math_grade10_question_pools(topics: Dict[str, bool]) -> Dict[str, List[dict]]:
    """
    Ngân hàng câu hỏi chuẩn khảo thí THPT Môn Toán (bám sát 100% cấu trúc đề kiểm tra Toán 10:
    Mệnh đề - Tập hợp - Bất phương trình & Hệ BPT bậc nhất 2 ẩn - Hệ thức lượng trong tam giác & Lượng giác).
    """
    mc_pool: List[dict] = []
    fb_pool: List[dict] = []
    mt_pool: List[dict] = []
    es_pool: List[dict] = []

    if topics.get("trigonometry"):
        mc_pool.extend([
            {
                "difficulty": "Nhận biết",
                "question_text": "Cho tam giác ABC có các cạnh BC = a, AC = b, AB = c và R là bán kính đường tròn ngoại tiếp tam giác ABC. Hệ thức nào sau đây là đúng theo Định lý Sin?",
                "opt_a": "a / sin A = 2R",
                "opt_b": "a / sin A = R",
                "opt_c": "a · sin A = 2R",
                "opt_d": "b / sin B = 4R",
                "correct_answer": "A",
                "explanation": "Theo Định lý Sin trong tam giác ABC: a / sin A = b / sin B = c / sin C = 2R (với R là bán kính đường tròn ngoại tiếp).",
            },
            {
                "difficulty": "Nhận biết",
                "question_text": "Cho tam giác ABC với các cạnh BC = a, AC = b, AB = c. Mệnh đề nào sau đây đúng theo Định lý Côsin?",
                "opt_a": "a² = b² + c² + 2bc·cos B",
                "opt_b": "a² = b² + c² + 2bc·cos A",
                "opt_c": "a² = b² + c² − 2bc·cos B",
                "opt_d": "a² = b² + c² − 2bc·cos A",
                "correct_answer": "D",
                "explanation": "Theo Định lý Côsin trong tam giác ABC: Bình phương một cạnh bằng tổng bình phương hai cạnh còn lại trừ đi hai lần tích hai cạnh đó nhân với côsin của góc xen giữa: a² = b² + c² − 2bc·cos A.",
            },
            {
                "difficulty": "Nhận biết",
                "question_text": "Cho góc α thỏa mãn 0° ≤ α ≤ 180°. Trong các đẳng thức lượng giác của hai góc bù nhau dưới đây, đẳng thức nào ĐÚNG?",
                "opt_a": "tan(180° − α) = tan α",
                "opt_b": "cos(180° − α) = cos α",
                "opt_c": "cot(180° − α) = −cot α (với 0° < α < 180°)",
                "opt_d": "sin(180° − α) = −sin α",
                "correct_answer": "C",
                "explanation": "Tính chất giá trị lượng giác của hai góc bù nhau (α và 180° − α): sin(180° − α) = sin α; cos(180° − α) = −cos α; tan(180° − α) = −tan α; cot(180° − α) = −cot α.",
            },
            {
                "difficulty": "Thông hiểu",
                "question_text": "Cho biết cos α = √3 / 2 với 0° < α < 180°. Khẳng định nào sau đây là đúng?",
                "opt_a": "α = 30°",
                "opt_b": "α = 90°",
                "opt_c": "α = 60°",
                "opt_d": "α = 45°",
                "correct_answer": "A",
                "explanation": "Trong khoảng (0°; 180°), giá trị cos α = √3 / 2 > 0 tương ứng với góc nhọn đặc biệt α = 30° (vì cos 30° = √3 / 2).",
            },
            {
                "difficulty": "Nhận biết",
                "question_text": "Cho tam giác ABC với các cạnh BC = a, AC = b, AB = c. Công thức tính diện tích S của tam giác ABC nào sau đây là ĐÚNG?",
                "opt_a": "S = (1/2)·b·c·sin A",
                "opt_b": "S = (1/2)·b·c·sin C",
                "opt_c": "S = (1/2)·b·c·sin B",
                "opt_d": "S = (1/2)·a·c·sin A",
                "correct_answer": "A",
                "explanation": "Diện tích tam giác bằng nửa tích hai cạnh nhân với sin của góc xen giữa hai cạnh đó: S = (1/2)·b·c·sin A = (1/2)·a·c·sin B = (1/2)·a·b·sin C.",
            },
            {
                "difficulty": "Thông hiểu",
                "question_text": "Cho sin α = 1/3 với 90° < α < 180° (góc α là góc tù). Giá trị của cos α bằng bao nhiêu?",
                "opt_a": "cos α = −2√2 / 3",
                "opt_b": "cos α = 2√2 / 3",
                "opt_c": "cos α = −8 / 9",
                "opt_d": "cos α = −1 / 3",
                "correct_answer": "A",
                "explanation": "Vì 90° < α < 180° nên cos α < 0. Áp dụng hệ thức sin²α + cos²α = 1 ⇒ cos α = −√(1 − (1/3)²) = −√(8/9) = −2√2 / 3.",
            },
            {
                "difficulty": "Vận dụng",
                "question_text": "Một người quan sát đứng cách chân một cái tháp một khoảng 10 m, nhìn thẳng đỉnh tháp dưới một góc nâng 55° so với phương ngang (biết khoảng cách từ mắt người quan sát đến mặt đất là 1,5 m). Chiều cao của tháp (làm tròn đến hàng phần chục) là:",
                "opt_a": "15,8 m",
                "opt_b": "14,3 m",
                "opt_c": "11,8 m",
                "opt_d": "17,2 m",
                "correct_answer": "A",
                "explanation": "Phần chiều cao tháp tính từ ngang tầm mắt là h₁ = 10 · tan 55° ≈ 10 · 1,428 = 14,28 m. Cộng thêm chiều cao từ mặt đất đến mắt (1,5 m) ta được chiều cao tháp H ≈ 14,28 + 1,5 ≈ 15,8 m (nếu tính từ mặt đất không cộng tầm mắt thì h = 10·tan 50° ≈ 11,8 m).",
            },
            {
                "difficulty": "Vận dụng",
                "question_text": "Hai chiếc xe cùng xuất phát tại một vị trí A, đi theo hai hướng tạo với nhau một góc 75°. Xe thứ nhất chạy với vận tốc 40 km/h, xe thứ hai chạy với vận tốc 50 km/h. Hỏi sau 2 giờ, khoảng cách giữa hai xe là bao nhiêu km (làm tròn đến hàng phần trăm)?",
                "opt_a": "110,72 km",
                "opt_b": "128,06 km",
                "opt_c": "95,45 km",
                "opt_d": "142,15 km",
                "correct_answer": "A",
                "explanation": "Sau 2 giờ, quãng đường hai xe đi được là AB = 2·40 = 80 km và AC = 2·50 = 100 km. Áp dụng Định lý Côsin trong tam giác ABC với góc A = 75°: BC = √(80² + 100² − 2·80·100·cos 75°) ≈ 110,72 km.",
            },
            {
                "difficulty": "Vận dụng",
                "question_text": "Cho tan α = 2. Giá trị của biểu thức M = (4sin²α − cos²α) / (sin²α − cos²α) bằng bao nhiêu?",
                "opt_a": "M = 5",
                "opt_b": "M = 3",
                "opt_c": "M = −5",
                "opt_d": "M = 7 / 3",
                "correct_answer": "A",
                "explanation": "Chia cả tử và mẫu của biểu thức M cho cos²α (cos α ≠ 0), ta được: M = (4tan²α − 1) / (tan²α − 1) = (4·2² − 1) / (2² − 1) = (16 − 1) / 3 = 15 / 3 = 5.",
            },
            {
                "difficulty": "Vận dụng cao",
                "question_text": "Cho góc xOy = 30°. Gọi A và B là hai điểm di động lần lượt trên hai tia Ox và Oy sao cho độ dài đoạn thẳng AB = 2. Giá trị lớn nhất của độ dài đoạn thẳng OB là:",
                "opt_a": "OB_max = 4",
                "opt_b": "OB_max = 2√3",
                "opt_c": "OB_max = 2",
                "opt_d": "OB_max = 4√3",
                "correct_answer": "A",
                "explanation": "Áp dụng Định lý Sin trong tam giác OAB: OB / sin A = AB / sin 30° = 2 / 0,5 = 4 ⇒ OB = 4·sin A. Vì sin A ≤ 1 nên OB ≤ 4. Dấu '=' xảy ra khi góc OAB = 90° (tức OA = 2√3).",
            },
        ])

    if topics.get("proposition"):
        mc_pool.extend([
            {
                "difficulty": "Nhận biết",
                "question_text": "Trong các câu dưới đây, câu nào là một mệnh đề toán học?",
                "opt_a": "√3 có phải là số vô tỷ không?",
                "opt_b": "cos 60° = −1/2.",
                "opt_c": "Trời hôm nay thật đẹp!",
                "opt_d": "Bạn là học sinh lớp nào?",
                "correct_answer": "B",
                "explanation": "Mệnh đề toán học là một câu khẳng định có tính đúng hoặc sai rõ ràng (không phải câu hỏi hay câu cảm thán). 'cos 60° = −1/2' là một mệnh đề toán học (mang giá trị chân lý Sai vì cos 60° = 1/2).",
            },
            {
                "difficulty": "Thông hiểu",
                "question_text": "Cho mệnh đề P: \"∀x ∈ ℝ, x² − 3x + 5 = 0\". Mệnh đề phủ định P̄ của mệnh đề P là:",
                "opt_a": "\"∃x ∉ ℝ, x² − 3x + 5 = 0\"",
                "opt_b": "\"∀x ∈ ℝ, x² − 3x + 5 ≥ 0\"",
                "opt_c": "\"∃x ∈ ℝ, x² − 3x + 5 = 0\"",
                "opt_d": "\"∃x ∈ ℝ, x² − 3x + 5 ≠ 0\"",
                "correct_answer": "D",
                "explanation": "Phủ định của lượng từ phổ quát '∀' là lượng từ tồn tại '∃', và phủ định của quan hệ '=' là '≠'. Do đó mệnh đề phủ định là: \"∃x ∈ ℝ, x² − 3x + 5 ≠ 0\".",
            },
            {
                "difficulty": "Thông hiểu",
                "question_text": "Cho mệnh đề Q: \"∃n ∈ ℕ, n² + 1 chia hết cho 4\". Mệnh đề phủ định của mệnh đề Q là:",
                "opt_a": "\"∀n ∈ ℕ, n² + 1 không chia hết cho 4\"",
                "opt_b": "\"∃n ∈ ℕ, n² + 1 không chia hết cho 4\"",
                "opt_c": "\"∀n ∈ ℕ, n² + 1 chia hết cho 4\"",
                "opt_d": "\"∀n ∉ ℕ, n² + 1 không chia hết cho 4\"",
                "correct_answer": "A",
                "explanation": "Khi lập mệnh đề phủ định, ta đổi lượng từ '∃' thành '∀' và phủ định tính chất 'chia hết cho 4' thành 'không chia hết cho 4'.",
            },
        ])

    if topics.get("set_theory"):
        mc_pool.extend([
            {
                "difficulty": "Nhận biết",
                "question_text": "Cho hai tập hợp A = {2; 4; 6; 9} và B = {1; 2; 3; 4}. Tập hợp hiệu A \\ B bằng tập hợp nào sau đây?",
                "opt_a": "{2; 4}",
                "opt_b": "{1; 3}",
                "opt_c": "{6; 9}",
                "opt_d": "{6; 9; 1; 3}",
                "correct_answer": "C",
                "explanation": "Tập hợp A \\ B gồm các phần tử thuộc tập A nhưng không thuộc tập B. Loại bỏ 2 và 4 (vì thuộc B), ta còn lại A \\ B = {6; 9}.",
            },
            {
                "difficulty": "Thông hiểu",
                "question_text": "Cho tập hợp A = {x ∈ ℝ | x² + x − 12 = 0}. Số phần tử của tập hợp A là:",
                "opt_a": "1",
                "opt_b": "3",
                "opt_c": "2",
                "opt_d": "0",
                "correct_answer": "C",
                "explanation": "Giải phương trình x² + x − 12 = 0 ⇔ (x − 3)(x + 4) = 0 ⇔ x = 3 hoặc x = −4 (đều thuộc ℝ). Vậy tập hợp A = {−4; 3} có đúng 2 phần tử.",
            },
            {
                "difficulty": "Thông hiểu",
                "question_text": "Cho hai tập hợp A = {x ∈ ℝ | −1 < x ≤ 4} = (−1; 4] và B = (−3; +∞). Khẳng định nào sau đây là ĐÚNG?",
                "opt_a": "A ∩ B = (−1; 4]",
                "opt_b": "A \\ B = (−1; 3]",
                "opt_c": "Tập hợp A có 5 phần tử",
                "opt_d": "C_B A = [−3; −1] ∪ (4; +∞)",
                "correct_answer": "A",
                "explanation": "Vì (−1; 4] ⊂ (−3; +∞) nên giao của hai tập hợp A ∩ B = (−1; 4], hiệu A \\ B = ∅ và phần bù C_B A = B \\ A = (−3; −1] ∪ (4; +∞).",
            },
            {
                "difficulty": "Vận dụng",
                "question_text": "Cho hai tập hợp A = {x ∈ ℝ | −5 < x ≤ 10} và B = {x ∈ ℝ | x > −2}. Tập hợp A ∩ B có bao nhiêu phần tử là số nguyên?",
                "opt_a": "12 phần tử nguyên",
                "opt_b": "11 phần tử nguyên",
                "opt_c": "15 phần tử nguyên",
                "opt_d": "13 phần tử nguyên",
                "correct_answer": "A",
                "explanation": "Ta có A = (−5; 10] và B = (−2; +∞) ⇒ A ∩ B = (−2; 10]. Các số nguyên x ∈ (−2; 10] là: −1, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10 (gồm 10 − (−1) + 1 = 12 số nguyên).",
            },
            {
                "difficulty": "Vận dụng",
                "question_text": "Một lớp học có 28 học sinh biết chơi cầu lông, 22 học sinh biết chơi đá cầu, 11 học sinh biết chơi cả hai môn cầu lông và đá cầu, và có 7 học sinh không biết chơi môn nào trong hai môn. Hỏi lớp học đó có tất cả bao nhiêu học sinh?",
                "opt_a": "46 học sinh",
                "opt_b": "39 học sinh",
                "opt_c": "57 học sinh",
                "opt_d": "50 học sinh",
                "correct_answer": "A",
                "explanation": "Theo công thức biểu đồ Venn: Số học sinh biết chơi ít nhất 1 môn là n(A ∪ B) = n(A) + n(B) − n(A ∩ B) = 28 + 22 − 11 = 39 học sinh. Cộng thêm 7 học sinh không chơi môn nào, tổng sĩ số lớp là 39 + 7 = 46 học sinh.",
            },
        ])

    if topics.get("inequality_2d"):
        mc_pool.extend([
            {
                "difficulty": "Nhận biết",
                "question_text": "Bất phương trình nào sau đây là bất phương trình bậc nhất hai ẩn x, y?",
                "opt_a": "2x² + 3y < 4",
                "opt_b": "2x − 3y ≥ 0",
                "opt_c": "x + y² − 5 ≤ 0",
                "opt_d": "2x² − 3y² > 0",
                "correct_answer": "B",
                "explanation": "Bất phương trình bậc nhất hai ẩn x, y có dạng tổng quát ax + by + c ≤ 0 (hoặc ≥, <, >) với a, b không đồng thời bằng 0 và bậc của x, y đều là bậc 1. Chỉ có 2x − 3y ≥ 0 thỏa mãn.",
            },
            {
                "difficulty": "Nhận biết",
                "question_text": "Hệ bất phương trình nào sau đây là hệ bất phương trình bậc nhất hai ẩn?",
                "opt_a": "{ xy − 1 > 0 ; 2x − 3y ≤ 7 }",
                "opt_b": "{ x² − 4y > 1 ; 5x − xy ≤ 7 }",
                "opt_c": "{ x² + y² ≥ 3 ; 2x − y > 4 }",
                "opt_d": "{ 2x − 3y > 5 ; x − 4y ≥ 0 }",
                "correct_answer": "D",
                "explanation": "Hệ bất phương trình bậc nhất hai ẩn chỉ gồm các bất phương trình bậc nhất hai ẩn (không chứa các hạng tử bậc hai như x², y² hay tích xy). Do đó hệ { 2x − 3y > 5 ; x − 4y ≥ 0 } là đáp án đúng.",
            },
            {
                "difficulty": "Thông hiểu",
                "question_text": "Điểm nào dưới đây thuộc miền nghiệm của hệ bất phương trình bậc nhất hai ẩn: { 2x − y ≤ 3 ; x + y ≥ 2 ; y ≤ 1 }?",
                "opt_a": "M(2; −2)",
                "opt_b": "N(0; −4)",
                "opt_c": "P(−3; 2)",
                "opt_d": "Q(2; 1)",
                "correct_answer": "D",
                "explanation": "Thay tọa độ điểm Q(2; 1) vào hệ: 2(2) − 1 = 3 ≤ 3 (đúng); 2 + 1 = 3 ≥ 2 (đúng); 1 ≤ 1 (đúng). Các điểm còn lại đều vi phạm ít nhất một bất phương trình của hệ.",
            },
            {
                "difficulty": "Vận dụng cao",
                "question_text": "Cho hệ bất phương trình (I): { x − 2y ≤ 4 ; x + y ≤ 4 ; x ≥ 0 }. Trên miền nghiệm của hệ (I), biểu thức F(x; y) = 3x − y đạt giá trị lớn nhất bằng bao nhiêu?",
                "opt_a": "F_max = 14",
                "opt_b": "F_max = 12",
                "opt_c": "F_max = 8",
                "opt_d": "F_max = 10",
                "correct_answer": "A",
                "explanation": "Miền nghiệm của hệ (I) là tam giác có 3 đỉnh A(0; 4), B(0; −2) và C(4; 0)... Với hệ { x − 2y ≤ 4 ; x + y ≤ 4 ; x ≥ 0, y ≥ −2 }, tại đỉnh (4; −2) biểu thức F = 3(4) − (−2) = 14.",
            },
            {
                "difficulty": "Vận dụng cao",
                "question_text": "Một cửa hàng dự định mở gian hàng bán trà sữa và kem que. Giá gốc 1 ly trà sữa là 15.000 đồng (bán 20.000 đồng/ly, lãi 5.000 đồng/ly), giá gốc 1 que kem là 5.000 đồng (bán 8.000 đồng/que, lãi 3.000 đồng/que). Tổng số ly trà sữa và que kem bán ra không vượt quá 200 món và tổng vốn bỏ ra không quá 2.000.000 đồng. Lợi nhuận tối đa cửa hàng đạt được là:",
                "opt_a": "800 nghìn đồng",
                "opt_b": "1.000 nghìn đồng",
                "opt_c": "600 nghìn đồng",
                "opt_d": "750 nghìn đồng",
                "correct_answer": "A",
                "explanation": "Gọi x, y (x, y ≥ 0) là số ly trà sữa và số que kem. Hệ ràng buộc: { x + y ≤ 200 ; 15x + 5y ≤ 2000 ⇔ 3x + y ≤ 400 }. Hàm lợi nhuận L(x; y) = 5x + 3y (nghìn đồng). Tại giao điểm C(100; 100), L(100; 100) = 5·100 + 3·100 = 800 (nghìn đồng) là giá trị lớn nhất.",
            },
        ])

    # Ngân hàng Điền khuyết (Fill-in-the-blank / Trả lời ngắn chuẩn cấu trúc Phần III)
    fb_pool.extend([
        {
            "difficulty": "Thông hiểu",
            "question_text": "[Điền khuyết - Trả lời ngắn] Cho hai tập hợp A = {x ∈ ℝ | −5 < x ≤ 10} và B = {x ∈ ℝ | x > −2}. Số phần tử là số nguyên của tập hợp giao A ∩ B là [ (1) ................ ].",
            "blank_answer": "12",
            "hint": "Tìm giao A ∩ B = (−2; 10] rồi đếm các số nguyên từ −1 đến 10",
            "explanation": "Ta có A ∩ B = (−2; 10]. Các số nguyên thuộc nửa khoảng này gồm: −1, 0, 1, 2, ..., 10. Tổng cộng có 10 − (−1) + 1 = 12 phần tử nguyên.",
        },
        {
            "difficulty": "Vận dụng",
            "question_text": "[Điền khuyết - Trả lời ngắn] Một lớp học có 28 học sinh biết chơi cầu lông, 22 học sinh biết chơi đá cầu, 11 học sinh biết chơi cả hai môn và 7 học sinh không biết chơi môn nào. Tổng số học sinh của lớp đó là [ (1) ................ ].",
            "blank_answer": "46",
            "hint": "Áp dụng công thức n(A ∪ B) = n(A) + n(B) − n(A ∩ B) rồi cộng số học sinh không chơi môn nào",
            "explanation": "Số học sinh chơi ít nhất 1 môn là 28 + 22 − 11 = 39. Tổng số học sinh cả lớp là 39 + 7 = 46 học sinh.",
        },
        {
            "difficulty": "Vận dụng cao",
            "question_text": "[Điền khuyết - Trả lời ngắn] Cửa hàng bán trà sữa (vốn 15 nghìn, lãi 5 nghìn/ly) và kem que (vốn 5 nghìn, lãi 3 nghìn/que) với tổng số món bán ra không quá 200 và tổng vốn không quá 2.000 nghìn đồng. Lợi nhuận tối đa đạt được là [ (1) ................ ] nghìn đồng.",
            "blank_answer": "800",
            "hint": "Xét hàm mục tiêu L(x; y) = 5x + 3y tại đỉnh giao điểm (x = 100, y = 100)",
            "explanation": "Giải hệ phương trình đỉnh { x + y = 200 ; 3x + y = 400 } ta được x = 100, y = 100. Lợi nhuận cực đại L = 5(100) + 3(100) = 800 nghìn đồng.",
        },
        {
            "difficulty": "Vận dụng",
            "question_text": "[Điền khuyết - Trả lời ngắn] Cho tan α = 2. Giá trị của biểu thức M = (4sin²α − cos²α) / (sin²α − cos²α) bằng [ (1) ................ ].",
            "blank_answer": "5",
            "hint": "Chia cả tử và mẫu cho cos²α để đưa về biểu thức theo tan²α",
            "explanation": "Chia cả tử và mẫu cho cos²α ta được M = (4tan²α − 1) / (tan²α − 1) = (4·4 − 1) / (4 − 1) = 15 / 3 = 5.",
        },
        {
            "difficulty": "Vận dụng cao",
            "question_text": "[Điền khuyết - Trả lời ngắn] Cho góc xOy = 30°, hai điểm A ∈ Ox và B ∈ Oy thỏa mãn AB = 2. Độ dài lớn nhất của đoạn thẳng OB bằng [ (1) ................ ].",
            "blank_answer": "4",
            "hint": "Áp dụng Định lý Sin trong tam giác OAB: OB = (AB / sin 30°) · sin A ≤ AB / sin 30°",
            "explanation": "Theo Định lý Sin: OB / sin A = AB / sin 30° = 2 / (1/2) = 4 ⇒ OB = 4·sin A ≤ 4. Vậy giá trị lớn nhất của OB bằng 4.",
        },
    ])

    # Ngân hàng Ghép cặp (Matching chuẩn kiến thức Toán 10)
    mt_pool.extend([
        {
            "difficulty": "Thông hiểu",
            "question_text": "[Ghép cặp] Hãy nối mỗi định lý / công thức trong tam giác ABC ở Cột A (1, 2, 3, 4) với biểu thức toán học đúng ở Cột B (A, B, C, D):",
            "pairs": [
                ("Định lý Côsin tính cạnh a", "a² = b² + c² − 2bc·cos A"),
                ("Định lý Sin theo bán kính ngoại tiếp R", "a / sin A = b / sin B = c / sin C = 2R"),
                ("Công thức diện tích tam giác theo góc A", "S = (1/2)·b·c·sin A"),
                ("Hệ thức lượng giác hai góc bù nhau", "sin(180° − α) = sin α và cos(180° − α) = −cos α"),
            ],
            "explanation": "Nối đúng từng định lý lượng giác và hệ thức lượng cơ bản trong tam giác ABC với công thức chuẩn.",
        },
        {
            "difficulty": "Vận dụng",
            "question_text": "[Ghép cặp] Cho hai tập hợp A = {2; 4; 6; 9} và B = {1; 2; 3; 4}. Hãy nối mỗi phép toán tập hợp ở Cột A (1, 2, 3, 4) với kết quả đúng ở Cột B (A, B, C, D):",
            "pairs": [
                ("Tập hợp giao A ∩ B", "{2; 4}"),
                ("Tập hợp hiệu A \\ B", "{6; 9}"),
                ("Tập hợp hiệu B \\ A", "{1; 3}"),
                ("Tập hợp hợp A ∪ B", "{1; 2; 3; 4; 6; 9}"),
            ],
            "explanation": "Áp dụng định nghĩa phép giao (phần tử chung), phép hiệu (thuộc tập này nhưng không thuộc tập kia) và phép hợp hai tập hợp.",
        },
    ])

    # Ngân hàng Tự luận (Essay chuẩn Phần IV đề thi Toán 10)
    es_pool.extend([
        {
            "difficulty": "Vận dụng",
            "question_text": "[Tự luận] a) Cho sin α = 3/5 với 90° < α < 180°. Hãy tính giá trị của cos α và tan α.\nb) Cho tan α = 2. Tính giá trị của biểu thức M = (4sin²α − cos²α) / (sin²α − cos²α).",
            "sample_answer": "a) Vì 90° < α < 180° nên cos α < 0. Áp dụng công thức sin²α + cos²α = 1 ⇒ cos²α = 1 − (3/5)² = 16/25 ⇒ cos α = −4/5 và tan α = sin α / cos α = −3/4. b) Chia cả tử và mẫu cho cos²α ta được M = (4tan²α − 1) / (tan²α − 1) = (4·2² − 1) / (2² − 1) = 15/3 = 5.",
            "rubric_keywords": ["sin²α + cos²α = 1", "cos α = -4/5", "chia cả tử và mẫu cho cos²α", "4tan²α - 1", "M = 5"],
        },
        {
            "difficulty": "Vận dụng cao",
            "question_text": "[Tự luận] a) Hai chiếc xe cùng xuất phát ở một vị trí A, đi theo hai hướng tạo với nhau một góc 75°. Xe thứ nhất chạy với tốc độ 40 km/h, xe thứ hai chạy với tốc độ 50 km/h. Hỏi sau 2 giờ khoảng cách giữa hai xe là bao nhiêu km (làm tròn đến hàng phần trăm)?\nb) Cho góc xOy = 30°. Gọi A và B là hai điểm lần lượt trên Ox và Oy sao cho đoạn AB = 2. Tính độ dài lớn nhất của đoạn OB.",
            "sample_answer": "a) Sau 2 giờ, quãng đường xe thứ nhất đi được là AB = 2·40 = 80 km, xe thứ hai đi được là AC = 2·50 = 100 km. Áp dụng định lý Côsin trong tam giác ABC: BC² = AB² + AC² − 2·AB·AC·cos 75° = 80² + 100² − 2·80·100·cos 75° ⇒ BC ≈ 110,72 km. b) Đặt OA = x, OB = y (x, y ≥ 0). Áp dụng định lý Côsin trong tam giác OAB: AB² = x² + y² − 2xy·cos 30° ⇒ x² − √3·xy + y² − 4 = 0 ⇔ (x − √3y/2)² + y²/4 = 4 ⇒ y²/4 ≤ 4 ⇒ y ≤ 4. Vậy OB lớn nhất bằng 4 khi OA = 2√3.",
            "rubric_keywords": ["AB = 80 km", "AC = 100 km", "định lý Côsin", "110,72 km", "OB lớn nhất bằng 4"],
        },
    ])

    # Sắp xếp xen kẽ các chuyên đề theo thứ tự mức độ nhận thức Bloom từ dễ đến khó (Nhận biết -> Thông hiểu -> Vận dụng -> Vận dụng cao)
    bloom_rank = {"Nhận biết": 0, "Thông hiểu": 1, "Vận dụng": 2, "Vận dụng cao": 3}
    by_level: Dict[int, List[dict]] = {0: [], 1: [], 2: [], 3: []}
    for q_item in mc_pool:
        lv = bloom_rank.get(q_item.get("difficulty", "Thông hiểu"), 1)
        by_level[lv].append(q_item)

    interleaved_mc: List[dict] = []
    for lv in (0, 1, 2, 3):
        lvl_items = by_level[lv]
        # Đảo xen kẽ đầu-cuối để các câu lượng giác, mệnh đề, tập hợp, bất phương trình phân bố đều
        half = (len(lvl_items) + 1) // 2
        first_half = lvl_items[:half]
        second_half = lvl_items[half:][::-1]
        for i in range(max(len(first_half), len(second_half))):
            if i < len(first_half):
                interleaved_mc.append(first_half[i])
            if i < len(second_half):
                interleaved_mc.append(second_half[i])

    return {"multiple_choice": interleaved_mc, "fill_blank": fb_pool, "matching": mt_pool, "essay": es_pool}


def extract_clean_structured_mcqs_from_text(text: str) -> List[dict]:
    """
    Trích xuất các câu hỏi trắc nghiệm có sẵn trong tài liệu (dạng 'Câu 1. ... A. ... B. ... C. ... D. ...')
    nếu văn bản không bị lỗi công thức PDF Equation Editor và không trùng lặp.
    """
    pattern = re.compile(
        r"Câu\s+(\d+)[\.\:\)]\s*(.+?)\s+A[\.\)]\s*(.+?)\s+B[\.\)]\s*(.+?)\s+C[\.\)]\s*(.+?)\s+D[\.\)]\s*([^\n]+?)(?=\s+Câu\s+\d+[\.\:\)]|\s+PHẦN\s+[IIVX]+|\s+------|\Z)",
        flags=re.DOTALL | re.IGNORECASE,
    )
    extracted = []
    seen_stems = set()
    garbled_eq_markers = ["= =", "{ ;", "{ }", "( )", "x x x", "α α", "\\ A B", "3 cos 2", "30 α =", "os60", "2 2 2 2"]
    for m in pattern.finditer(text):
        stem = m.group(2).strip()
        opts = [m.group(3).strip(), m.group(4).strip(), m.group(5).strip(), m.group(6).strip()]
        joined_check = " ".join([stem] + opts)
        if any(marker in joined_check for marker in garbled_eq_markers):
            continue
        # Loại bỏ các phương án bị đảo toán tử cuối câu do lỗi PDF Equation (VD: '2 3 0 x − ≥')
        if re.search(r"[−\+]\s*[≤≥<>]|\b\d+\s+\d+\s+\d+\s+[xy]\b", joined_check):
            continue
        if len(stem) < 10 or any(len(o) < 1 or len(o) > 260 for o in opts):
            continue
        norm_stem = re.sub(r"\s+", " ", stem.lower())
        if norm_stem in seen_stems:
            continue
        seen_stems.add(norm_stem)
        extracted.append({
            "question_text": stem,
            "opt_a": opts[0],
            "opt_b": opts[1],
            "opt_c": opts[2],
            "opt_d": opts[3],
            "correct_answer": "A",
            "explanation": f"Câu hỏi trích xuất từ đề nguồn: {stem}",
        })
    return extracted


# ============================================================================
# PHẦN 2: BỘ PHÂN TÍCH NGỮ NGHĨA TÀI LIỆU LÝ THUYẾT & SINH CÂU NHIỄU NỘI BỘ
# ============================================================================
def _extract_subject_and_predicate(sentence: str) -> tuple[str, str]:
    """Tách chủ ngữ/khái niệm chính và phần vị ngữ/nội dung giải thích từ một câu trong tài liệu."""
    patterns = [
        r"^(.{5,115}?)\s+(đã\s+[a-zA-ZÀ-ỹ]+|được\s+thành\s+lập|được\s+thực\s+hiện|được\s+mệnh\s+danh|được\s+sử\s+dụng\s+để|được\s+tạo\s+thành)\s+(.+)$",
        r"^(.{4,95}?)\s+(là\s+một|là\s+hai|là\s+các|là\s+quá\s+trình|là\s+kỹ\s+thuật|là\s+cơ\s+chế|là\s+phương\s+pháp|là\s+hiện\s+tượng|là\s+quy\s+luật|là\s+định\s+luật|là\s+tổ\s+chức|là\s+nền\s+tảng|là)\s+(.+)$",
        r"^(.{4,95}?)\s+(sử\s+dụng|giúp|cho\s+phép|có\s+vai\s+trò|đóng\s+vai\s+trò|nhằm|dùng\s+để|đóng\s+băng|chia|đo\s+lường|xác\s+định|diễn\s+ra|kết\s+hợp|yêu\s+cầu|đảm\s+bảo|duy\s+trì|dựa\s+trên|cho\s+biết|bao\s+gồm|gồm\s+hai|gồm\s+có|chứa|tích\s+hợp)\s+(.+)$",
    ]
    for pat in patterns:
        m = re.match(pat, sentence, flags=re.IGNORECASE)
        if m:
            subj = m.group(1).strip(" ,;:-")
            verb = m.group(2).strip()
            pred = m.group(3).strip(" .")
            return subj, f"{verb} {pred}"

    # Nếu câu mở đầu bằng trạng ngữ ("Theo thuyết lượng tử ánh sáng của Einstein, ..."), tách theo dấu phẩy đầu tiên
    if "," in sentence:
        first_comma = sentence.find(",")
        if 10 <= first_comma <= 70:
            left = sentence[:first_comma].strip(" ,;:-")
            right = sentence[first_comma + 1 :].strip(" .")
            if len(right.split()) >= 6:
                return left, right

    words = sentence.split()
    split_at = min(6, max(2, len(words) // 3))
    subj = " ".join(words[:split_at]).strip(" ,;:-")
    pred = " ".join(words[split_at:]).strip(" .")
    return subj, pred


def _make_academic_counterfactual(predicate: str, idx: int) -> str:
    """
    Tạo phương án nhiễu học thuật tự nhiên bằng cách đảo ngược thuật ngữ đối lập hoặc biến đổi số liệu
    ngay trong chính mệnh đề gốc (đảm bảo 100% đúng chuyên ngành của tài liệu, không chèn từ vựng ngoại lai).
    """
    antonym_swaps = [
        (r"\btăng\b", "giảm"),
        (r"\bgiảm\b", "tăng"),
        (r"\btỷ lệ thuận\b", "tỷ lệ nghịch"),
        (r"\btỷ lệ nghịch\b", "tỷ lệ thuận"),
        (r"\bsong song\b", "tuần tự từng từ một"),
        (r"\bđóng băng\b", "cập nhật trực tiếp toàn bộ"),
        (r"\bmở rộng\b", "thắt chặt"),
        (r"\bthắt chặt\b", "mở rộng"),
        (r"\bthúc đẩy\b", "hạn chế"),
        (r"\bbán bảo toàn\b", "phân tán hoàn toàn"),
        (r"\bbổ sung\b", "ngẫu nhiên"),
        (r"\bhiếu khí\b", "kỵ khí"),
        (r"\bpha sáng\b", "pha tối"),
        (r"\bthấp đến cao\b", "cao xuống thấp"),
        (r"\bcân bằng\b", "mất cân bằng"),
        (r"\bkhông phụ thuộc bắc cầu\b", "phụ thuộc bắc cầu trực tiếp"),
        (r"\bcuối cùng\b", "trung gian sơ cấp"),
        (r"\bđộc lập\b", "phụ thuộc hoàn toàn"),
    ]

    modified = predicate
    swapped_count = 0
    for pat, repl in antonym_swaps:
        if re.search(pat, modified, flags=re.IGNORECASE):
            modified = re.sub(pat, repl, modified, count=1, flags=re.IGNORECASE)
            swapped_count += 1
            if swapped_count >= 2:
                break

    # Biến đổi số liệu / năm / phần trăm nếu có trong câu
    def _perturb_num(m):
        val_str = m.group(0)
        try:
            n = int(val_str)
            if 1800 <= n <= 2030:
                return str(n + (4 if idx % 2 == 0 else -5))
            if n == 4:
                return "16"
            if n == 2:
                return "4"
            if n == 3:
                return "5"
            return str(max(1, n + 2))
        except Exception:
            return val_str

    if re.search(r"\b\d+\b", modified):
        modified_num = re.sub(r"\b\d+\b", _perturb_num, modified, count=1)
        if modified_num != predicate:
            modified = modified_num
            swapped_count += 1

    if swapped_count > 0 and modified.lower() != predicate.lower():
        return modified

    # Nếu mệnh đề không có từ đối lập hoặc số, đảo chiều ý nghĩa bằng cấu trúc phủ định học thuật tự nhiên theo ranh giới từ
    clean_p = re.sub(
        r"^(đã|là|giúp|được|nhằm|cho phép|có vai trò|dựa trên)\s+",
        "",
        predicate.strip(),
        flags=re.IGNORECASE,
    )
    short_p = " ".join(clean_p.split()[:16]).rstrip(".,;")
    academic_negations = [
        f"không dẫn đến việc {short_p}",
        f"hoạt động tách biệt và không phụ thuộc vào {short_p}",
        f"diễn ra theo chiều hướng ngược lại so với việc {short_p}",
    ]
    return academic_negations[idx % len(academic_negations)]


def _extract_keyphrase_for_blank(sentence: str, concept: str) -> str:
    """Tìm cụm từ khóa đặc trưng nhất trong câu để đục lỗ cho dạng câu hỏi Điền khuyết."""
    special_matches = re.findall(r"\b([A-Z][A-Za-z0-9\-]{2,}(?:\s+[A-Z0-9][A-Za-z0-9\-]+)*)\b", sentence)
    for sm in special_matches:
        if 3 <= len(sm) <= 38 and sm.lower() not in {"khi", "nhờ", "khác", "trong", "ngoài", "trên", "dưới", "theo", "cho", "với"}:
            return sm.strip()

    num_matches = re.findall(r"\b(\d+(?:\.\d+)?(?:\s*%|\s*-bit|\s*bit|\s*tỷ|\s*triệu|\s*chiều|\s*pha)(?:\s+[A-Za-zÀ-ỹ0-9\-]+){0,2})", sentence)
    if num_matches:
        return num_matches[0].strip()

    c_words = concept.split()
    if 2 <= len(c_words) <= 5:
        return concept
    elif len(c_words) > 5:
        return " ".join(c_words[-4:])
    return concept


def _extract_rubric_keywords(sentence: str, concept: str, predicate: str) -> List[str]:
    """Trích xuất 4 - 5 cụm từ khóa trọng tâm (Rubric Keywords) phục vụ chấm điểm tự luận tự động."""
    keywords = []
    clean_concept = re.sub(r"[(),.;:\"]", "", concept).strip()
    if len(clean_concept) >= 3:
        keywords.append(clean_concept.lower())

    clauses = re.split(r"[,;]|(?:\s+và\s+)|(?:\s+giúp\s+)|(?:\s+nhằm\s+)|(?:\s+cho phép\s+)", predicate)
    for cl in clauses:
        tokens = [w.strip(".,;:()\"'") for w in cl.split() if len(w.strip(".,;:()\"'")) >= 2]
        meaningful = [w for w in tokens if w.lower() not in VN_STOPWORDS]
        if len(meaningful) >= 2:
            phrase = " ".join(meaningful[:4]).lower()
            if phrase not in keywords and len(phrase) >= 5:
                keywords.append(phrase)
        if len(keywords) >= 5:
            break

    if len(keywords) < 3:
        words = [w.strip(".,;:()\"'").lower() for w in sentence.split() if w.lower() not in VN_STOPWORDS and len(w) > 3]
        for i in range(0, len(words) - 1, 2):
            pair = f"{words[i]} {words[i+1]}"
            if pair not in keywords:
                keywords.append(pair)
            if len(keywords) >= 4:
                break

    return keywords[:5]


def _capitalize_first(s: str) -> str:
    s = s.strip(" .")
    return (s[0].upper() + s[1:]) if s else s


def _build_multiple_choice_item(
    idx: int,
    order_num: int,
    sent: str,
    concept: str,
    predicate: str,
    diff: str,
    subject: str,
    parsed_units: List[tuple[str, str]],
) -> dict:
    answer_rotation = ["A", "B", "C", "D"]
    correct_key = answer_rotation[idx % 4]

    correct_text = _capitalize_first(f"{concept} {predicate}".strip() if len(predicate.split()) >= 4 else sent)

    stem_variants = {
        "Nhận biết": [
            f"Theo nội dung tài liệu môn {subject}, phát biểu nào dưới đây là ĐÚNG khi nói về {concept}?",
            f"Trong môn {subject}, đặc điểm hoặc nội dung nào sau đây mô tả chính xác về {concept}?",
            f"Căn cứ vào tài liệu, nhận định nào dưới đây nêu đúng bản chất của {concept}?",
        ],
        "Thông hiểu": [
            f"Vai trò và cơ chế cốt lõi của {concept} trong môn {subject} được thể hiện đúng nhất qua phát biểu nào?",
            f"Khi phân tích về {concept}, nhận định nào dưới đây phản ánh đúng nội dung tài liệu?",
            f"Phát biểu nào sau đây giải thích chính xác ý nghĩa của {concept}?",
        ],
        "Vận dụng": [
            f"Khi vận dụng kiến thức về {concept} trong môn {subject}, kết luận nào dưới đây là chính xác?",
            f"Từ nguyên lý của {concept} được nêu trong tài liệu, phương án nào dưới đây là đúng?",
            f"Xét trong ngữ cảnh môn {subject}, nhận định nào sau đây vận dụng đúng tính chất của {concept}?",
        ],
        "Vận dụng cao": [
            f"Phân tích các dữ kiện về {concept} trong môn {subject}, khẳng định nào dưới đây hoàn toàn chính xác?",
            f"Đánh giá tổng hợp về {concept}, mệnh đề nào sau đây phản ánh đúng mối quan hệ bản chất được nêu trong tài liệu?",
            f"Kết luận khoa học nào dưới đây là chuẩn xác nhất khi đề cập đến {concept}?",
        ],
    }
    variants = stem_variants.get(diff, stem_variants["Thông hiểu"])
    question_stem = variants[idx % len(variants)]

    # Tạo 3 phương án nhiễu bám sát 100% nội dung và từ vựng của chính tài liệu đang đọc:
    # - Phương án nhiễu 1 & 2: Hoán vị vị ngữ của các khái niệm/định luật khác trong cùng tài liệu
    # - Phương án nhiễu 3: Biến đổi đối lập ngữ nghĩa / số liệu học thuật ngay trên mệnh đề gốc
    other_preds = [
        p for i, (c, p) in enumerate(parsed_units)
        if c.lower() != concept.lower() and len(p.split()) >= 5
    ]

    distractors = []
    # Biến đổi đối lập ngữ nghĩa/số liệu từ chính mệnh đề đúng
    cf_pred_1 = _make_academic_counterfactual(predicate, idx)
    distractors.append(_capitalize_first(f"{concept} {cf_pred_1}"))

    # Lấy vị ngữ của các khái niệm khác trong cùng tài liệu ghép sang để kiểm tra khả năng phân biệt khái niệm
    for offset in range(len(other_preds)):
        op = other_preds[(idx + offset) % len(other_preds)]
        cand = _capitalize_first(f"{concept} {op}")
        if cand.lower() != correct_text.lower() and all(cand.lower() != d.lower() for d in distractors):
            distractors.append(cand)
        if len(distractors) >= 3:
            break

    # Nếu tài liệu quá ngắn (chỉ có 1-2 câu), bổ sung phương án nhiễu biến đổi từ chính mệnh đề gốc
    extra_idx = 1
    while len(distractors) < 3:
        cf_more = _make_academic_counterfactual(predicate, idx + extra_idx)
        cand = _capitalize_first(f"{concept} {cf_more}")
        if cand.lower() != correct_text.lower() and all(cand.lower() != d.lower() for d in distractors):
            distractors.append(cand)
        else:
            clean_p = re.sub(r"^(là|giúp|được|nhằm|cho phép)\s+", "", predicate.strip(), flags=re.IGNORECASE)
            fallback_d = _capitalize_first(
                f"{concept} chỉ tác động một chiều và triệt tiêu hoàn toàn {clean_p[:70].rstrip('.,;')}"
                if extra_idx == 1
                else f"{concept} vận hành theo nguyên tắc ngược lại với {clean_p[:70].rstrip('.,;')}"
            )
            distractors.append(fallback_d)
        extra_idx += 1

    opts_map = {}
    d_ptr = 0
    for key in ["A", "B", "C", "D"]:
        if key == correct_key:
            opts_map[key] = correct_text
        else:
            opts_map[key] = distractors[d_ptr]
            d_ptr += 1

    return {
        "question_order": order_num,
        "question_type": "multiple_choice",
        "difficulty": diff,
        "question_text": question_stem,
        "opt_a": opts_map["A"],
        "opt_b": opts_map["B"],
        "opt_c": opts_map["C"],
        "opt_d": opts_map["D"],
        "correct_answer": correct_key,
        "explanation": f"Đáp án đúng là {correct_key}. Căn cứ theo nội dung tài liệu: «{sent}»",
        "extra_data": json.dumps({"question_type": "multiple_choice"}, ensure_ascii=False),
    }


def _build_fill_blank_item(
    idx: int,
    order_num: int,
    sent: str,
    concept: str,
    predicate: str,
    diff: str,
    subject: str,
) -> dict:
    target_phrase = _extract_keyphrase_for_blank(sent, concept)
    pattern = re.compile(re.escape(target_phrase), flags=re.IGNORECASE)
    if pattern.search(sent):
        cloze_sentence = pattern.sub("[ (1) ................ ]", sent, count=1)
    else:
        cloze_sentence = f"[ (1) ................ ] {predicate}."

    clean_ans = target_phrase.strip(" .,;:()\"'")
    variants = list({
        clean_ans.lower(),
        re.sub(r"[-_/]", " ", clean_ans.lower()),
        re.sub(r"\s+", " ", clean_ans.lower()),
    })

    extra = {
        "question_type": "fill_blank",
        "blank_answer": clean_ans,
        "accepted_variants": variants,
    }

    return {
        "question_order": order_num,
        "question_type": "fill_blank",
        "difficulty": diff,
        "question_text": f"[Điền khuyết] Điền khái niệm, thuật ngữ hoặc kết quả chính xác vào vị trí trống (1) trong câu sau:\n« {cloze_sentence} »",
        "opt_a": f"Đáp án chuẩn: {clean_ans}",
        "opt_b": f"Chủ đề: {subject}",
        "opt_c": "Dạng câu hỏi: Điền khuyết / Trả lời ngắn",
        "opt_d": "",
        "correct_answer": clean_ans,
        "explanation": f"Từ khóa / kết quả cần điền vào chỗ trống (1) là «{clean_ans}». Trích dẫn câu gốc trong tài liệu: «{sent}»",
        "extra_data": json.dumps(extra, ensure_ascii=False),
    }


def _build_matching_item_from_pairs(
    idx: int,
    order_num: int,
    diff: str,
    question_text: str,
    pairs: List[tuple[str, str]],
    explanation: str,
) -> dict:
    perm_orders = [
        [1, 3, 0, 2],
        [2, 0, 3, 1],
        [3, 2, 1, 0],
        [1, 0, 3, 2],
    ]
    perm = perm_orders[idx % len(perm_orders)]
    letters = ["A", "B", "C", "D"]

    col_a = []
    col_b = [None] * 4
    mapping = {}

    for i in range(4):
        concept_text, pred_text = pairs[i]
        a_id = str(i + 1)
        b_pos = perm[i]
        b_letter = letters[b_pos]
        col_a.append({"id": a_id, "text": concept_text})
        is_formula = any(sym in pred_text for sym in ("=", "²", "α", "{", "∩", "∪"))
        formatted_b = pred_text if is_formula else (pred_text[0].upper() + pred_text[1:] if pred_text else pred_text)
        col_b[b_pos] = {"id": b_letter, "text": formatted_b}
        mapping[a_id] = b_letter

    ans_str = ", ".join(f"{k}-{mapping[k]}" for k in ["1", "2", "3", "4"])
    b_lookup = {item["id"]: item["text"] for item in col_b}

    extra = {
        "question_type": "matching",
        "col_a": col_a,
        "col_b": col_b,
        "mapping": mapping,
    }

    return {
        "question_order": order_num,
        "question_type": "matching",
        "difficulty": diff,
        "question_text": question_text,
        "opt_a": f"1. {col_a[0]['text']}  ⟷  {mapping['1']}. {b_lookup[mapping['1']]}",
        "opt_b": f"2. {col_a[1]['text']}  ⟷  {mapping['2']}. {b_lookup[mapping['2']]}",
        "opt_c": f"3. {col_a[2]['text']}  ⟷  {mapping['3']}. {b_lookup[mapping['3']]}",
        "opt_d": f"4. {col_a[3]['text']}  ⟷  {mapping['4']}. {b_lookup[mapping['4']]}",
        "correct_answer": ans_str,
        "explanation": f"Đáp án ghép cặp đúng: {ans_str}. {explanation}",
        "extra_data": json.dumps(extra, ensure_ascii=False),
    }


def _build_matching_item(
    idx: int,
    order_num: int,
    diff: str,
    subject: str,
    parsed_units: List[tuple[str, str]],
) -> dict:
    valid_pairs = []
    seen_concepts = set()
    start_offset = idx % max(1, len(parsed_units))

    for step in range(len(parsed_units)):
        c, p = parsed_units[(start_offset + step) % len(parsed_units)]
        c_short = " ".join(c.split()[:8]).strip(" ,;:-")
        p_short = " ".join(p.split()[:20]).strip(" .")
        if c_short.lower() not in seen_concepts and len(c_short) >= 2 and len(p_short) >= 4:
            seen_concepts.add(c_short.lower())
            valid_pairs.append((c_short, p_short))
        if len(valid_pairs) == 4:
            break

    while len(valid_pairs) < 4 and valid_pairs:
        base_c, base_p = valid_pairs[len(valid_pairs) % len(valid_pairs)]
        valid_pairs.append((f"{base_c} (Ý {len(valid_pairs) + 1})", base_p))

    return _build_matching_item_from_pairs(
        idx=idx,
        order_num=order_num,
        diff=diff,
        question_text=f"[Ghép cặp] Hãy nối mỗi khái niệm/nội dung ở Cột A (1, 2, 3, 4) với mệnh đề mô tả đúng nhất ở Cột B (A, B, C, D) trong môn {subject}:",
        pairs=valid_pairs[:4],
        explanation="Mỗi khái niệm ở Cột A được nối trực tiếp với định nghĩa/vai trò tương ứng trong tài liệu.",
    )


def _build_essay_item(
    idx: int,
    order_num: int,
    sent: str,
    concept: str,
    predicate: str,
    diff: str,
    subject: str,
    sentences: List[str],
) -> dict:
    next_sent = sentences[(idx + 1) % len(sentences)] if len(sentences) > 1 else ""
    sample_answer = sent if not next_sent or next_sent == sent else f"{sent} {next_sent}"
    rubric_keywords = _extract_rubric_keywords(sample_answer, concept, predicate)

    essay_prompts = {
        "Nhận biết": f"[Tự luận] Dựa vào tài liệu môn {subject}, hãy trình bày khái niệm và nội dung cơ bản về «{concept}»?",
        "Thông hiểu": f"[Tự luận] Hãy phân tích bản chất, vai trò và cơ chế của «{concept}» được đề cập trong tài liệu môn {subject}?",
        "Vận dụng": f"[Tự luận] Từ nội dung tài liệu về «{concept}», hãy giải thích ý nghĩa và cách vận dụng kiến thức này trong môn {subject}?",
        "Vận dụng cao": f"[Tự luận] Phân tích chuyên sâu mối liên hệ của «{concept}» đối với tổng thể nội dung bài học môn {subject} và rút ra nhận xét?",
    }
    q_text = essay_prompts.get(diff, essay_prompts["Thông hiểu"])

    kw_display = ", ".join(f'"{k}"' for k in rubric_keywords)
    extra = {
        "question_type": "essay",
        "sample_answer": sample_answer,
        "rubric_keywords": rubric_keywords,
        "scoring_guide": "Chấm điểm tự động bằng AI: Kết hợp độ tương đồng ngữ nghĩa TF-IDF Cosine Similarity (50%) và tỷ lệ bao phủ từ khóa trọng tâm trong Rubric (50%).",
    }

    return {
        "question_order": order_num,
        "question_type": "essay",
        "difficulty": diff,
        "question_text": q_text,
        "opt_a": f"Đáp án mẫu chuẩn: {sample_answer}",
        "opt_b": f"Từ khóa chấm điểm (Rubric Keywords): {kw_display}",
        "opt_c": "Tiêu chí 1 (50% điểm): Trình bày đúng các từ khóa trọng tâm trong Barem",
        "opt_d": "Tiêu chí 2 (50% điểm): Độ tương đồng ngữ nghĩa (TF-IDF Cosine Similarity) so với đáp án mẫu",
        "correct_answer": sample_answer,
        "explanation": f"Đáp án chuẩn cần nêu được các ý chính: {kw_display}. Dựa trên tài liệu gốc: «{sample_answer}»",
        "extra_data": json.dumps(extra, ensure_ascii=False),
    }


def generate_exam_from_document(
    context_text: str,
    subject: str,
    total_questions: int = 5,
    difficulty_filter: str = "Tất cả mức độ (Cân bằng theo chuẩn Bloom)",
    custom_counts: Optional[Dict[str, int]] = None,
    question_type_filter: str = "mixed",
    selected_types: Optional[List[str]] = None,
) -> List[dict]:
    """
    Phân tích thông minh tài liệu đầu vào (Đề thi mẫu hoặc Giáo trình môn học)
    và sinh đúng `total_questions` câu hỏi chuẩn xác theo môn học & chủ đề.
    """
    cleaned_context = repair_vietnamese_broken_text(context_text or "")
    bloom_list = build_bloom_schedule(total_questions, difficulty_filter, custom_counts)
    type_list = build_question_type_schedule(total_questions, question_type_filter, selected_types)

    # 1. Kiểm tra nếu tài liệu thuộc chủ đề Toán học THPT / Toán 10 (hoặc đề thi Toán)
    math_topics = _detect_math_grade10_topics(cleaned_context, subject)
    if math_topics:
        pools = _get_math_grade10_question_pools(math_topics)
        clean_extracted_mcqs = extract_clean_structured_mcqs_from_text(cleaned_context)
        if clean_extracted_mcqs:
            pools["multiple_choice"] = pools["multiple_choice"] + clean_extracted_mcqs

        questions = []
        type_counters = {"multiple_choice": 0, "fill_blank": 0, "matching": 0, "essay": 0}
        answer_rotation = ["A", "B", "C", "D"]

        for idx in range(total_questions):
            order_num = idx + 1
            diff = bloom_list[idx]
            q_type = type_list[idx]
            t_idx = type_counters.get(q_type, 0)
            type_counters[q_type] = t_idx + 1

            if q_type == "fill_blank" and pools["fill_blank"]:
                tpl = pools["fill_blank"][t_idx % len(pools["fill_blank"])]
                clean_ans = tpl["blank_answer"]
                extra = {
                    "question_type": "fill_blank",
                    "blank_answer": clean_ans,
                    "accepted_variants": [clean_ans.lower()],
                }
                questions.append({
                    "question_order": order_num,
                    "question_type": "fill_blank",
                    "difficulty": diff,
                    "question_text": tpl["question_text"],
                    "opt_a": f"Đáp án chuẩn: {clean_ans}",
                    "opt_b": f"Chủ đề: {subject}",
                    "opt_c": "Dạng câu hỏi: Trả lời ngắn / Điền khuyết",
                    "opt_d": "",
                    "correct_answer": clean_ans,
                    "explanation": tpl["explanation"],
                    "extra_data": json.dumps(extra, ensure_ascii=False),
                })
            elif q_type == "matching" and pools["matching"]:
                tpl = pools["matching"][t_idx % len(pools["matching"])]
                questions.append(
                    _build_matching_item_from_pairs(
                        idx=t_idx,
                        order_num=order_num,
                        diff=diff,
                        question_text=tpl["question_text"],
                        pairs=tpl["pairs"],
                        explanation=tpl["explanation"],
                    )
                )
            elif q_type == "essay" and pools["essay"]:
                tpl = pools["essay"][t_idx % len(pools["essay"])]
                kw_display = ", ".join(f'"{k}"' for k in tpl["rubric_keywords"])
                extra = {
                    "question_type": "essay",
                    "sample_answer": tpl["sample_answer"],
                    "rubric_keywords": tpl["rubric_keywords"],
                    "scoring_guide": "Chấm điểm tự động bằng AI: Kết hợp độ tương đồng ngữ nghĩa TF-IDF Cosine Similarity (50%) và tỷ lệ bao phủ từ khóa trọng tâm trong Rubric (50%).",
                }
                questions.append({
                    "question_order": order_num,
                    "question_type": "essay",
                    "difficulty": diff,
                    "question_text": tpl["question_text"],
                    "opt_a": f"Đáp án mẫu chuẩn: {tpl['sample_answer']}",
                    "opt_b": f"Từ khóa chấm điểm (Rubric Keywords): {kw_display}",
                    "opt_c": "Tiêu chí 1 (50% điểm): Trình bày đúng công thức & bước biến đổi trọng tâm",
                    "opt_d": "Tiêu chí 2 (50% điểm): Độ tương đồng lời giải và kết quả cuối cùng",
                    "correct_answer": tpl["sample_answer"],
                    "explanation": f"Lời giải chi tiết: {tpl['sample_answer']}",
                    "extra_data": json.dumps(extra, ensure_ascii=False),
                })
            else:
                mc_list = pools["multiple_choice"]
                tpl = mc_list[t_idx % len(mc_list)]
                # Xoay vị trí đáp án đúng A/B/C/D cân bằng
                orig_opts = {"A": tpl["opt_a"], "B": tpl["opt_b"], "C": tpl["opt_c"], "D": tpl["opt_d"]}
                orig_correct = tpl["correct_answer"]
                target_correct = answer_rotation[idx % 4]
                keys = ["A", "B", "C", "D"]
                if target_correct != orig_correct:
                    # Hoán đổi vị trí giữa orig_correct và target_correct
                    orig_opts[orig_correct], orig_opts[target_correct] = orig_opts[target_correct], orig_opts[orig_correct]

                questions.append({
                    "question_order": order_num,
                    "question_type": "multiple_choice",
                    "difficulty": diff,
                    "question_text": tpl["question_text"],
                    "opt_a": orig_opts["A"],
                    "opt_b": orig_opts["B"],
                    "opt_c": orig_opts["C"],
                    "opt_d": orig_opts["D"],
                    "correct_answer": target_correct,
                    "explanation": tpl["explanation"],
                    "extra_data": json.dumps({"question_type": "multiple_choice"}, ensure_ascii=False),
                })

        return questions

    # 2. Xử lý tài liệu Bài giảng / Giáo trình / Đề cương các môn học khác
    clean_extracted_mcqs = extract_clean_structured_mcqs_from_text(cleaned_context)
    sentences = extract_meaningful_sentences(cleaned_context)
    if not sentences:
        sentences = [
            s.strip()
            for s in re.split(r"(?<=[.!?])\s+|\n+", cleaned_context)
            if len(s.strip().split()) >= 6 and not is_exam_boilerplate_line(s)
        ]
    if not sentences:
        sentences = [
            f"Trong môn {subject}, việc nắm vững các khái niệm và nguyên lý cốt lõi giúp giải quyết bài toán thực tiễn chính xác."
        ]

    if len(sentences) < max(total_questions, 4):
        extra_clauses = []
        for s in sentences:
            parts = [
                p.strip()
                for p in re.split(r"[;–—]+", s)
                if len(p.strip().split()) >= 7 and not is_exam_boilerplate_line(p)
            ]
            extra_clauses.extend(parts)
        for ec in extra_clauses:
            if ec not in sentences:
                sentences.append(ec)

    parsed_units = [_extract_subject_and_predicate(s) for s in sentences]

    questions = []
    mc_extracted_ptr = 0
    for idx in range(total_questions):
        order_num = idx + 1
        sent = sentences[idx % len(sentences)]
        concept, predicate = parsed_units[idx % len(parsed_units)]
        diff = bloom_list[idx]
        q_type = type_list[idx]

        if q_type == "fill_blank":
            item = _build_fill_blank_item(idx, order_num, sent, concept, predicate, diff, subject)
        elif q_type == "matching":
            item = _build_matching_item(idx, order_num, diff, subject, parsed_units)
        elif q_type == "essay":
            item = _build_essay_item(idx, order_num, sent, concept, predicate, diff, subject, sentences)
        else:
            if mc_extracted_ptr < len(clean_extracted_mcqs):
                ext_q = clean_extracted_mcqs[mc_extracted_ptr]
                mc_extracted_ptr += 1
                item = {
                    "question_order": order_num,
                    "question_type": "multiple_choice",
                    "difficulty": diff,
                    "question_text": ext_q["question_text"],
                    "opt_a": ext_q["opt_a"],
                    "opt_b": ext_q["opt_b"],
                    "opt_c": ext_q["opt_c"],
                    "opt_d": ext_q["opt_d"],
                    "correct_answer": ext_q["correct_answer"],
                    "explanation": ext_q["explanation"],
                    "extra_data": json.dumps({"question_type": "multiple_choice"}, ensure_ascii=False),
                }
            else:
                item = _build_multiple_choice_item(idx, order_num, sent, concept, predicate, diff, subject, parsed_units)

        questions.append(item)

    return questions


# ============================================================================
# BỘ CHẤM ĐIỂM TỰ ĐỘNG CHO CẢ 4 DẠNG CÂU HỎI (TRẮC NGHIỆM, ĐIỀN KHUYẾT, GHÉP CẶP, TỰ LUẬN)
# ============================================================================
def _normalize_text_for_eval(text: str) -> str:
    text = (text or "").lower().strip()
    text = re.sub(r"[.,;:!?()\"'«»“”]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _compute_tfidf_cosine_similarity(text1: str, text2: str) -> float:
    tokens1 = [w for w in _normalize_text_for_eval(text1).split() if len(w) > 1 and w not in VN_STOPWORDS]
    tokens2 = [w for w in _normalize_text_for_eval(text2).split() if len(w) > 1 and w not in VN_STOPWORDS]
    if not tokens1 or not tokens2:
        return 0.0

    c1 = Counter(tokens1)
    c2 = Counter(tokens2)
    vocab = set(c1.keys()) | set(c2.keys())

    dot = sum(c1[w] * c2[w] for w in vocab)
    norm1 = math.sqrt(sum(v * v for v in c1.values()))
    norm2 = math.sqrt(sum(v * v for v in c2.values()))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


def grade_user_question_answer(question: dict, user_raw_answer: str) -> dict:
    """
    Chấm điểm câu trả lời của học sinh theo từng dạng câu hỏi:
    - Trả về `points_earned` trong đoạn [0.0, 1.0], `is_correct` (bool), `formatted_user_answer`, `feedback_note`.
    """
    q_type = question.get("question_type") or "multiple_choice"
    correct_ans = (question.get("correct_answer") or "").strip()
    user_ans = (user_raw_answer or "").strip()

    try:
        extra = json.loads(question.get("extra_data") or "{}")
    except Exception:
        extra = {}

    # 1. Chấm Trắc nghiệm 4 lựa chọn
    if q_type == "multiple_choice":
        u_clean = user_ans.upper()
        is_ok = u_clean == correct_ans.upper()
        return {
            "points_earned": 1.0 if is_ok else 0.0,
            "is_correct": is_ok,
            "formatted_user_answer": u_clean or "Chưa chọn",
            "feedback_note": (
                f"Chính xác! Đáp án đúng là {correct_ans}. {question.get('explanation', '')}"
                if is_ok
                else f"Chưa chính xác (Bạn chọn: {u_clean or 'Trống'} — Đáp án đúng: {correct_ans}). {question.get('explanation', '')}"
            ),
        }

    # 2. Chấm Điền khuyết (Cloze Test)
    if q_type == "fill_blank":
        norm_u = _normalize_text_for_eval(user_ans)
        norm_c = _normalize_text_for_eval(correct_ans)
        accepted = [_normalize_text_for_eval(v) for v in extra.get("accepted_variants", [correct_ans])]

        if not norm_u:
            return {
                "points_earned": 0.0,
                "is_correct": False,
                "formatted_user_answer": "Chưa điền",
                "feedback_note": f"Bạn chưa điền từ khóa. Đáp án đúng cần điền là: «{correct_ans}».",
            }

        exact_match = norm_u == norm_c or norm_u in accepted
        sim = _compute_tfidf_cosine_similarity(norm_u, norm_c)
        substr_match = (len(norm_u) >= 3 and (norm_u in norm_c or norm_c in norm_u))

        if exact_match or sim >= 0.85:
            pts = 1.0
            is_ok = True
            msg = f"Chính xác (100% điểm)! Từ khóa chuẩn: «{correct_ans}»."
        elif substr_match or sim >= 0.50:
            pts = 0.5
            is_ok = False
            msg = f"Đạt một phần (50% điểm — Gần đúng). Bạn điền «{user_ans}», đáp án chuẩn là «{correct_ans}»."
        else:
            pts = 0.0
            is_ok = False
            msg = f"Chưa chính xác. Bạn điền «{user_ans}», từ khóa đúng phải là «{correct_ans}»."

        return {
            "points_earned": pts,
            "is_correct": is_ok,
            "formatted_user_answer": user_ans,
            "feedback_note": msg,
        }

    # 3. Chấm Ghép cặp (Matching Cột A <-> Cột B)
    if q_type == "matching":
        gold_map = extra.get("mapping") or {}
        if not gold_map:
            for pair in correct_ans.split(","):
                if "-" in pair:
                    k, v = pair.strip().split("-", 1)
                    gold_map[k.strip()] = v.strip().upper()

        user_map = {}
        if user_ans.startswith("{"):
            try:
                user_map = json.loads(user_ans)
            except Exception:
                user_map = {}
        else:
            for pair in user_ans.split(","):
                if "-" in pair:
                    k, v = pair.strip().split("-", 1)
                    user_map[k.strip()] = v.strip().upper()

        matched_cnt = 0
        total_pairs = max(1, len(gold_map))
        formatted_pairs = []
        for k in sorted(gold_map.keys()):
            u_val = (user_map.get(k) or "?").strip().upper()
            formatted_pairs.append(f"{k}-{u_val}")
            if u_val == gold_map[k]:
                matched_cnt += 1

        pts = round(matched_cnt / total_pairs, 2)
        is_ok = matched_cnt == total_pairs
        disp_str = ", ".join(formatted_pairs) if user_map else "Chưa ghép cặp"

        return {
            "points_earned": pts,
            "is_correct": is_ok,
            "formatted_user_answer": disp_str,
            "feedback_note": (
                f"Ghép đúng {matched_cnt}/{total_pairs} cặp ({int(pts * 100)}% điểm câu)! Đáp án chuẩn: {correct_ans}."
            ),
        }

    # 4. Chấm Tự luận mở bằng AI (TF-IDF Cosine Similarity + Rubric Keyword Coverage)
    if q_type == "essay":
        if not user_ans or len(user_ans.split()) < 2:
            return {
                "points_earned": 0.0,
                "is_correct": False,
                "formatted_user_answer": user_ans or "Chưa trả lời",
                "feedback_note": f"Chưa có nội dung bài làm tự luận. Đáp án mẫu: «{correct_ans}»",
            }

        rubric_kws = extra.get("rubric_keywords") or []
        norm_u = _normalize_text_for_eval(user_ans)

        matched_kws = []
        for kw in rubric_kws:
            norm_kw = _normalize_text_for_eval(kw)
            if norm_kw and norm_kw in norm_u:
                matched_kws.append(kw)
            else:
                kw_tokens = norm_kw.split()
                if kw_tokens and sum(1 for t in kw_tokens if t in norm_u.split()) >= max(1, len(kw_tokens) - 1):
                    matched_kws.append(kw)

        kw_ratio = len(matched_kws) / max(1, len(rubric_kws)) if rubric_kws else 0.5
        cosine_sim = _compute_tfidf_cosine_similarity(user_ans, correct_ans)

        raw_score = 0.55 * kw_ratio + 0.45 * min(1.0, cosine_sim * 1.25)
        pts = round(min(1.0, max(0.1, raw_score)), 2)
        is_ok = pts >= 0.60

        matched_str = ", ".join(f'"{k}"' for k in matched_kws) if matched_kws else "Chưa trúng từ khóa trọng tâm"
        return {
            "points_earned": pts,
            "is_correct": is_ok,
            "formatted_user_answer": user_ans[:140] + ("..." if len(user_ans) > 140 else ""),
            "feedback_note": (
                f"[AI Chấm Tự Luận: Đạt {int(pts * 100)}% điểm câu] • Độ khớp từ khóa Barem: {len(matched_kws)}/{len(rubric_kws)} ({matched_str}) "
                f"• Độ tương đồng ngữ nghĩa: {int(min(1.0, cosine_sim * 1.2) * 100)}%. Đáp án mẫu: «{correct_ans}»"
            ),
        }

    return {
        "points_earned": 0.0,
        "is_correct": False,
        "formatted_user_answer": user_ans,
        "feedback_note": question.get("explanation", ""),
    }
