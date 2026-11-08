"""
Module Xuất Bộ Đề Thi Đa Định Dạng (Hỗ trợ đầy đủ 4 dạng câu hỏi: Trắc nghiệm, Điền khuyết, Ghép cặp, Tự luận):
1. Microsoft Word (.docx) - Bản đầy đủ có đáp án, bảng ghép cặp & barem chấm tự luận (dành cho Giáo viên).
2. Microsoft Word (.docx) - Bản đề thi phát cho học sinh (ẩn đáp án, có dòng kẻ điền khuyết & dòng kẻ làm bài tự luận).
3. Markdown (.md) & JSON chuẩn (.json).
"""

import io
import json
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Pt, RGBColor

QUESTION_TYPE_LABELS = {
    "multiple_choice": "Trắc nghiệm 4 lựa chọn",
    "fill_blank": "Điền khuyết",
    "matching": "Ghép cặp Cột A - Cột B",
    "essay": "Tự luận",
}


def _parse_extra(q: dict) -> dict:
    try:
        return json.loads(q.get("extra_data") or "{}")
    except Exception:
        return {}


def build_exam_docx(exam: dict, include_answers: bool = True) -> bytes:
    doc = Document()

    for section in doc.sections:
        section.top_margin = Cm(2.0)
        section.bottom_margin = Cm(2.0)
        section.left_margin = Cm(2.5)
        section.right_margin = Cm(2.0)

    # Tiêu đề đề thi
    p_head = doc.add_paragraph()
    p_head.alignment = WD_ALIGN_PARAGRAPH.CENTER

    r_sys = p_head.add_run("HỆ THỐNG WEB AI SINH ĐỀ THI & KHẢO THÍ THÔNG MINH\n")
    r_sys.bold = True
    r_sys.font.size = Pt(11.5)
    r_sys.font.color.rgb = RGBColor(37, 99, 235)

    r_title = p_head.add_run(f"{exam['title'].upper()}\n")
    r_title.bold = True
    r_title.font.size = Pt(14)

    r_meta = p_head.add_run(
        f"Môn/Chủ đề: {exam['subject']}  |  Mã đề: {exam['exam_code']}  |  "
        f"Số câu: {len(exam['questions'])} câu  |  Thời gian: {exam['duration_minutes']} phút"
    )
    r_meta.italic = True
    r_meta.font.size = Pt(11)

    if not include_answers:
        p_stu = doc.add_paragraph()
        p_stu.paragraph_format.space_before = Pt(6)
        r_stu = p_stu.add_run(
            "Họ và tên thí sinh: ............................................................   Số báo danh / MSSV: ..........................."
        )
        r_stu.font.size = Pt(11)

    doc.add_paragraph("─" * 64).alignment = WD_ALIGN_PARAGRAPH.CENTER

    # Nội dung các câu hỏi theo từng dạng
    for q in exam["questions"]:
        q_type = q.get("question_type") or "multiple_choice"
        type_label = QUESTION_TYPE_LABELS.get(q_type, "Trắc nghiệm")
        extra = _parse_extra(q)

        p_q = doc.add_paragraph()
        p_q.paragraph_format.space_before = Pt(8)
        p_q.paragraph_format.space_after = Pt(3)
        r_q = p_q.add_run(f"Câu {q['question_order']} ({type_label} — {q['difficulty']}): {q['question_text']}")
        r_q.bold = True
        r_q.font.size = Pt(12)

        if q_type == "multiple_choice":
            for key_opt, col_name in [("A", "opt_a"), ("B", "opt_b"), ("C", "opt_c"), ("D", "opt_d")]:
                p_o = doc.add_paragraph()
                p_o.paragraph_format.left_indent = Cm(0.75)
                p_o.paragraph_format.space_before = Pt(1)
                p_o.paragraph_format.space_after = Pt(1)
                r_k = p_o.add_run(f"{key_opt}. ")
                r_k.bold = True
                r_k.font.size = Pt(11.5)
                r_v = p_o.add_run(str(q.get(col_name, "")))
                r_v.font.size = Pt(11.5)

        elif q_type == "fill_blank":
            p_ans_line = doc.add_paragraph()
            p_ans_line.paragraph_format.left_indent = Cm(0.75)
            r_al = p_ans_line.add_run("✍ Trả lời / Điền vào vị trí trống (1): ....................................................................................")
            r_al.font.size = Pt(11)

        elif q_type == "matching":
            col_a = extra.get("col_a", [])
            col_b = extra.get("col_b", [])
            if col_a and col_b:
                table = doc.add_table(rows=1 + max(len(col_a), len(col_b)), cols=2)
                table.style = "Table Grid"
                hdr_cells = table.rows[0].cells
                hdr_cells[0].text = "CỘT A (Khái niệm / Thuật ngữ)"
                hdr_cells[1].text = "CỘT B (Nội dung mô tả / Định nghĩa)"
                for idx_row in range(max(len(col_a), len(col_b))):
                    row_cells = table.rows[idx_row + 1].cells
                    if idx_row < len(col_a):
                        row_cells[0].text = f"{col_a[idx_row]['id']}. {col_a[idx_row]['text']}"
                    if idx_row < len(col_b):
                        row_cells[1].text = f"{col_b[idx_row]['id']}. {col_b[idx_row]['text']}"
            else:
                for col_name in ["opt_a", "opt_b", "opt_c", "opt_d"]:
                    p_m = doc.add_paragraph()
                    p_m.paragraph_format.left_indent = Cm(0.75)
                    p_m.add_run(str(q.get(col_name, ""))).font.size = Pt(11)

            p_match_box = doc.add_paragraph()
            p_match_box.paragraph_format.space_before = Pt(4)
            p_match_box.paragraph_format.left_indent = Cm(0.75)
            r_mb = p_match_box.add_run("✍ Trả lời ghép cặp:   1 - [ ..... ]      2 - [ ..... ]      3 - [ ..... ]      4 - [ ..... ]")
            r_mb.bold = True
            r_mb.font.size = Pt(11)

        elif q_type == "essay":
            for _ in range(4):
                p_line = doc.add_paragraph()
                p_line.paragraph_format.left_indent = Cm(0.75)
                p_line.paragraph_format.space_before = Pt(2)
                p_line.paragraph_format.space_after = Pt(2)
                r_l = p_line.add_run("............................................................................................................................................................")
                r_l.font.size = Pt(10.5)

    # Nếu xuất bản dành cho Giáo viên thì đính kèm trang Bảng Đáp án & Barem chấm điểm ở cuối
    if include_answers:
        doc.add_page_break()
        p_ans_head = doc.add_paragraph()
        p_ans_head.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r_ah = p_ans_head.add_run(f"BẢNG ĐÁP ÁN, HƯỚNG DẪN CHẤM & GIẢI THÍCH CHI TIẾT (MÃ ĐỀ: {exam['exam_code']})")
        r_ah.bold = True
        r_ah.font.size = Pt(13)
        r_ah.font.color.rgb = RGBColor(5, 150, 105)

        for q in exam["questions"]:
            q_type = q.get("question_type") or "multiple_choice"
            type_label = QUESTION_TYPE_LABELS.get(q_type, "Trắc nghiệm")
            p_exp = doc.add_paragraph()
            p_exp.paragraph_format.space_before = Pt(5)
            r1 = p_exp.add_run(
                f"• Câu {q['question_order']} [{type_label} — {q['difficulty']}] — Đáp án chuẩn: {q['correct_answer']}\n"
            )
            r1.bold = True
            r1.font.size = Pt(11.5)
            r2 = p_exp.add_run(f"  Giải thích / Barem chấm: {q['explanation']}")
            r2.italic = True
            r2.font.size = Pt(11)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def build_exam_markdown(exam: dict) -> str:
    lines = [
        f"# {exam['title'].upper()}",
        f"- **Môn / Chủ đề:** {exam['subject']}",
        f"- **Mã đề:** `{exam['exam_code']}` | **Thời gian:** {exam['duration_minutes']} phút | **Số câu:** {len(exam['questions'])} câu\n",
        "---\n",
    ]
    for q in exam["questions"]:
        q_type = q.get("question_type") or "multiple_choice"
        type_label = QUESTION_TYPE_LABELS.get(q_type, "Trắc nghiệm")
        extra = _parse_extra(q)

        lines.append(f"### Câu {q['question_order']} [{type_label} — {q['difficulty']}]: {q['question_text']}")
        if q_type == "multiple_choice":
            lines.append(f"- **A.** {q['opt_a']}")
            lines.append(f"- **B.** {q['opt_b']}")
            lines.append(f"- **C.** {q['opt_c']}")
            lines.append(f"- **D.** {q['opt_d']}\n")
        elif q_type == "fill_blank":
            lines.append("- **Trả lời / Điền vào vị trí (1):** `........................................`\n")
        elif q_type == "matching":
            col_a = extra.get("col_a", [])
            col_b = extra.get("col_b", [])
            if col_a and col_b:
                lines.append("| Cột A (Khái niệm) | Cột B (Mô tả / Định nghĩa) |")
                lines.append("| :--- | :--- |")
                for i in range(max(len(col_a), len(col_b))):
                    a_txt = f"**{col_a[i]['id']}.** {col_a[i]['text']}" if i < len(col_a) else ""
                    b_txt = f"**{col_b[i]['id']}.** {col_b[i]['text']}" if i < len(col_b) else ""
                    lines.append(f"| {a_txt} | {b_txt} |")
                lines.append("")
        elif q_type == "essay":
            lines.append(f"- *{q.get('opt_b', '')}*\n")

        lines.append(f"> **Đáp án chuẩn:** `{q['correct_answer']}`  ")
        lines.append(f"> **Giải thích / Barem:** {q['explanation']}\n")
    return "\n".join(lines)
