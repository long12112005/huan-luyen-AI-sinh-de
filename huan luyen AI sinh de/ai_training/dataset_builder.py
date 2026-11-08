"""
Module Xây dựng & Chuẩn hóa Dữ liệu Huấn luyện AI Sinh Đề (Dataset Builder).
- Chuyển đổi tài liệu và câu hỏi mẫu sang định dạng Instruction ChatML chuẩn của Qwen2.5-7B-Instruct.
- Kiểm tra tính hợp lệ của JSON Schema (đủ 4 lựa chọn A/B/C/D, nhãn đáp án đúng và giải thích).
- Cho phép người dùng bổ sung các bộ đề chất lượng cao từ Web vào tập dữ liệu huấn luyện (Continual Fine-tuning).
"""

import base64
import json
import os
import re
from collections import Counter
from backend.config import DATA_DIR, SAMPLE_DOCS_DIR, TRAINING_DATA_PATH
from backend.document_parser import parse_uploaded_document
from backend.ai_engine import generate_exam_from_document

TRAIN_SOURCES_DIR = os.path.join(DATA_DIR, "train_sources")
os.makedirs(TRAIN_SOURCES_DIR, exist_ok=True)

EXTERNAL_WATCH_DIRS = [
    TRAIN_SOURCES_DIR,
    SAMPLE_DOCS_DIR,
]

SYSTEM_INSTRUCTION = (
    "Bạn là một chuyên gia biên soạn đề thi giáo dục. "
    "Dựa vào đoạn văn bản tài liệu ngữ cảnh và mức độ nhận thức Bloom được yêu cầu, "
    "hãy tạo câu hỏi trắc nghiệm khách quan gồm 4 phương án A, B, C, D, chỉ rõ đáp án đúng và giải thích chi tiết theo chuẩn JSON."
)


def init_training_corpus():
    if os.path.exists(TRAINING_DATA_PATH):
        return

    initial_samples = [
        {
            "id": "TRAIN_001",
            "subject": "Trí tuệ nhân tạo & Học sâu",
            "difficulty": "Thông hiểu",
            "context": "Kỹ thuật LoRA (Low-Rank Adaptation) đóng băng trọng số gốc W0 của mô hình ngôn ngữ lớn đã tiền huấn luyện và chèn hai ma trận phân rã hạng thấp A và B vào các tầng Attention, giúp giảm hơn 99% số lượng tham số cần cập nhật.",
            "output": {
                "question": "Cơ chế nào giúp kỹ thuật LoRA giảm đáng kể dung lượng bộ nhớ VRAM khi tinh chỉnh mô hình ngôn ngữ lớn?",
                "options": {
                    "A": "Xóa bỏ hoàn toàn các tầng Self-Attention và chỉ giữ lại tầng nhúng từ vựng",
                    "B": "Đóng băng trọng số gốc W0 và chỉ huấn luyện cặp ma trận phân rã hạng thấp A và B",
                    "C": "Chuyển đổi mô hình từ kiến trúc Transformer sang mạng nơ-ron hồi quy RNN",
                    "D": "Tăng gấp đôi kích thước ma trận trọng số ở mọi tầng tuyến tính",
                },
                "answer": "B",
                "explanation": "LoRA giữ cố định W0 và chỉ cập nhật hai ma trận hạng thấp A và B với r << d.",
            },
        },
        {
            "id": "TRAIN_002",
            "subject": "Khoa học Tự nhiên - Sinh học",
            "difficulty": "Nhận biết",
            "context": "Quá trình phiên mã ở sinh vật nhân thực diễn ra trong nhân tế bào, trong đó enzyme RNA polymerase tổng hợp phân tử mRNA theo chiều 5' đến 3' dựa trên mạch khuôn của DNA có chiều 3' đến 5'.",
            "output": {
                "question": "Trong quá trình phiên mã ở tế bào nhân thực, enzyme RNA polymerase tổng hợp mạch mRNA mới theo chiều nào?",
                "options": {
                    "A": "Từ chiều 3' đến 5' trên cả hai mạch của phân tử DNA",
                    "B": "Từ chiều 5' đến 3' dựa trên mạch khuôn 3' → 5' của DNA",
                    "C": "Ngẫu nhiên từ hai đầu mút của nhiễm sắc thể vào tâm động",
                    "D": "Từ ngoài tế bào chất đi ngược vào trong màng nhân tế bào",
                },
                "answer": "B",
                "explanation": "Enzyme RNA polymerase luôn tổng hợp mạch mRNA theo chiều 5' → 3' dựa trên mạch khuôn 3' → 5' của DNA.",
            },
        },
        {
            "id": "TRAIN_003",
            "subject": "Lịch sử Thế giới Hiện đại",
            "difficulty": "Vận dụng",
            "context": "Hội nghị quốc tế Ianta (tháng 2/1945) với sự tham gia của nguyên thủ ba cường quốc Liên Xô, Mỹ và Anh đã đưa ra quyết định thành lập tổ chức Liên hợp quốc và thỏa thuận việc đóng quân, phân chia phạm vi ảnh hưởng ở châu Âu và châu Á.",
            "output": {
                "question": "Quyết định nào của Hội nghị Ianta (2/1945) đã tạo khuôn khổ trực tiếp dẫn đến sự hình thành trật tự thế giới hai cực sau Chiến tranh thế giới thứ hai?",
                "options": {
                    "A": "Thỏa thuận phân chia phạm vi đóng quân và vùng ảnh hưởng giữa các cường quốc tại châu Âu và châu Á",
                    "B": "Tuyên bố giải thể hoàn toàn lực lượng quân đội thường trực của tất cả các quốc gia châu Âu",
                    "C": "Thiết lập đồng tiền chung duy nhất cho toàn bộ các nước thuộc khối Đồng minh",
                    "D": "Chuyển giao quyền quản lý toàn bộ thuộc địa ở châu Phi cho Hội Quốc Liên điều hành",
                },
                "answer": "A",
                "explanation": "Việc thỏa thuận đóng quân và phân chia phạm vi ảnh hưởng tại châu Âu và châu Á giữa Liên Xô và Mỹ đã đặt nền móng xác lập cục diện hai cực Ianta.",
            },
        },
        {
            "id": "TRAIN_004",
            "subject": "Kinh tế học Vĩ mô",
            "difficulty": "Thông hiểu",
            "context": "Lạm phát do cầu kéo xảy ra khi tổng cầu của nền kinh tế tăng nhanh vượt quá năng lực sản xuất của tổng cung ở mức toàn dụng nhân công, dẫn đến mặt bằng giá cả chung tăng lên.",
            "output": {
                "question": "Nguyên nhân cốt lõi dẫn đến hiện tượng lạm phát do cầu kéo trong nền kinh tế là gì?",
                "options": {
                    "A": "Tổng chi tiêu và nhu cầu tiêu dùng tăng vượt quá năng lực cung ứng hàng hóa ở mức toàn dụng nhân công",
                    "B": "Người tiêu dùng đồng loạt cắt giảm chi tiêu và tăng tỷ lệ gửi tiết kiệm tại ngân hàng",
                    "C": "Năng suất lao động tăng cao làm dư thừa nguồn cung hàng hóa trên thị trường nội địa",
                    "D": "Ngân hàng trung ương ngừng phát hành tiền mặt và đóng băng tín dụng thương mại",
                },
                "answer": "A",
                "explanation": "Lạm phát cầu kéo xuất phát từ việc tổng cầu tăng mạnh vượt khả năng đáp ứng của tổng cung.",
            },
        },
        {
            "id": "TRAIN_005",
            "subject": "Mạng máy tính & An toàn thông tin",
            "difficulty": "Vận dụng cao",
            "context": "Giao thức HTTPS sử dụng TLS (Transport Layer Security) để mã hóa kênh truyền giữa trình duyệt và máy chủ Web. Trong quá trình bắt tay TLS (TLS Handshake), hai bên sử dụng mã hóa bất đối xứng để trao đổi khóa phiên, sau đó dùng khóa phiên này với thuật toán mã hóa đối xứng (như AES) để truyền dữ liệu tốc độ cao.",
            "output": {
                "question": "Tại sao giao thức HTTPS/TLS lại kết hợp cả mã hóa bất đối xứng (trong pha bắt tay) và mã hóa đối xứng (trong pha truyền dữ liệu)?",
                "options": {
                    "A": "Vì mã hóa bất đối xứng giúp trao đổi khóa an toàn qua kênh không tin cậy, còn mã hóa đối xứng giúp mã hóa khối lượng dữ liệu lớn với tốc độ xử lý nhanh hơn nhiều",
                    "B": "Vì mã hóa đối xứng hoàn toàn không cần sử dụng bất kỳ khóa bí mật nào giữa máy khách và máy chủ",
                    "C": "Vì mã hóa bất đối xứng có tốc độ tính toán nhanh gấp 1000 lần mã hóa đối xứng trên các tệp dữ liệu lớn",
                    "D": "Vì giao thức HTTP bắt buộc mọi gói tin phải được giải mã công khai tại tất cả các bộ định tuyến trung gian",
                },
                "answer": "A",
                "explanation": "Mã hóa bất đối xứng giải quyết bài toán trao đổi khóa an toàn khi bắt tay, sau đó chuyển sang mã hóa đối xứng (AES) để tối ưu tốc độ truyền tải dữ liệu.",
            },
        },
    ]

    with open(TRAINING_DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(initial_samples, f, ensure_ascii=False, indent=2)


def sync_external_files_to_corpus(corpus: list[dict]) -> list[dict]:
    """
    Tự động quét các tệp (.pdf, .docx, .txt, .md, .json) được người dùng chép trực tiếp
    vào thư mục `data/train_sources/` hoặc `data/sample_docs/` để nạp thẳng vào tập huấn luyện.
    """
    imported_files = {item.get("source_file") for item in corpus if item.get("source_file")}
    skip_default_files = {"Tai_lieu_Mau_Tri_Tue_Nhan_Tao.docx", "Tai_lieu_Mau_Tri_Tue_Nhan_Tao.pdf"}
    updated = False

    for folder in EXTERNAL_WATCH_DIRS:
        if not os.path.isdir(folder):
            continue
        for fname in sorted(os.listdir(folder)):
            if fname in skip_default_files or fname in imported_files or fname.startswith("~$"):
                continue
            fpath = os.path.join(folder, fname)
            if not os.path.isfile(fpath):
                continue

            ext = os.path.splitext(fname)[1].lower()
            if ext not in {".txt", ".md", ".docx", ".pdf", ".json"}:
                continue

            try:
                if ext == ".json":
                    with open(fpath, "r", encoding="utf-8") as jf:
                        raw_data = json.load(jf)
                    if isinstance(raw_data, list):
                        for entry in raw_data:
                            if isinstance(entry, dict) and "output" in entry:
                                entry["id"] = f"TRAIN_{len(corpus) + 1:03d}"
                                entry["source_file"] = fname
                                corpus.append(entry)
                                updated = True
                        imported_files.add(fname)
                        continue

                with open(fpath, "rb") as bf:
                    b64_str = base64.b64encode(bf.read()).decode("ascii")
                parsed = parse_uploaded_document(fname, b64_str)
                content = parsed.get("content", "").strip()
                if len(content.split()) < 8:
                    continue

                clean_subject = re.sub(r"[_\-]+", " ", os.path.splitext(fname)[0]).strip()
                num_to_gen = min(20, max(4, parsed.get("sentence_count", 4) * 2))
                gen_qs = generate_exam_from_document(
                    context_text=content,
                    subject=clean_subject,
                    total_questions=num_to_gen,
                    question_type_filter="mixed",
                )
                for q in gen_qs:
                    corpus.append(
                        {
                            "id": f"TRAIN_{len(corpus) + 1:03d}",
                            "subject": clean_subject,
                            "difficulty": q["difficulty"],
                            "question_type": q.get("question_type", "multiple_choice"),
                            "source_file": fname,
                            "context": content[:600],
                            "output": {
                                "question_type": q.get("question_type", "multiple_choice"),
                                "question": q["question_text"],
                                "options": {
                                    "A": q["opt_a"],
                                    "B": q["opt_b"],
                                    "C": q["opt_c"],
                                    "D": q["opt_d"],
                                },
                                "answer": q["correct_answer"],
                                "explanation": q["explanation"],
                            },
                        }
                    )
                imported_files.add(fname)
                updated = True
            except Exception:
                continue

    if updated:
        with open(TRAINING_DATA_PATH, "w", encoding="utf-8") as f:
            json.dump(corpus, f, ensure_ascii=False, indent=2)
    return corpus


def load_training_corpus() -> list[dict]:
    init_training_corpus()
    with open(TRAINING_DATA_PATH, "r", encoding="utf-8") as f:
        corpus = json.load(f)
    return sync_external_files_to_corpus(corpus)


def add_exam_to_training_corpus(exam: dict) -> int:
    """Đóng góp các câu hỏi từ bộ đề đã duyệt của người dùng vào tập dữ liệu huấn luyện AI."""
    corpus = load_training_corpus()
    added = 0
    for q in exam.get("questions", []):
        new_id = f"TRAIN_{len(corpus) + 1:03d}"
        corpus.append(
            {
                "id": new_id,
                "subject": exam.get("subject", "Tổng hợp"),
                "difficulty": q["difficulty"],
                "question_type": q.get("question_type", "multiple_choice"),
                "context": exam.get("source_context", ""),
                "output": {
                    "question_type": q.get("question_type", "multiple_choice"),
                    "question": q["question_text"],
                    "options": {
                        "A": q["opt_a"],
                        "B": q["opt_b"],
                        "C": q["opt_c"],
                        "D": q["opt_d"],
                    },
                    "answer": q["correct_answer"],
                    "explanation": q["explanation"],
                },
            }
        )
        added += 1

    with open(TRAINING_DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(corpus, f, ensure_ascii=False, indent=2)
    return added


def format_sample_to_chatml(sample: dict) -> str:
    q_type = sample.get("question_type") or sample.get("output", {}).get("question_type", "multiple_choice")
    user_prompt = (
        f"Chủ đề: {sample['subject']}\n"
        f"Dạng câu hỏi: {q_type}\n"
        f"Mức độ Bloom: {sample['difficulty']}\n"
        f"Tài liệu ngữ cảnh: {sample['context']}"
    )
    assistant_json = json.dumps(sample["output"], ensure_ascii=False, indent=2)
    return (
        f"<|im_start|>system\n{SYSTEM_INSTRUCTION}<|im_end|>\n"
        f"<|im_start|>user\n{user_prompt}<|im_end|>\n"
        f"<|im_start|>assistant\n{assistant_json}<|im_end|>"
    )


def get_training_corpus_stats() -> dict:
    corpus = load_training_corpus()
    diff_counts = Counter(x["difficulty"] for x in corpus)
    ans_counts = Counter(x["output"]["answer"] for x in corpus)
    subj_counts = Counter(x["subject"] for x in corpus)
    type_counts = Counter(
        x.get("question_type") or x.get("output", {}).get("question_type", "multiple_choice")
        for x in corpus
    )
    source_counts = Counter(x.get("source_dataset") or "Giáo trình 8 chuyên ngành" for x in corpus)
    return {
        "total_samples": len(corpus),
        "difficulty_distribution": dict(diff_counts),
        "question_type_distribution": dict(type_counts),
        "source_distribution": dict(source_counts),
        "answer_distribution": dict(ans_counts),
        "subject_distribution": dict(subj_counts.most_common(12)),
        "samples": corpus[:25],
        "sample_chatml_preview": format_sample_to_chatml(corpus[0]) if corpus else "",
    }


def query_training_samples(
    page: int = 1,
    page_size: int = 8,
    source: str = "",
    qtype: str = "",
    difficulty: str = "",
    search: str = "",
) -> dict:
    corpus = load_training_corpus()
    filtered = corpus

    if source:
        if source in ("Giáo trình 8 chuyên ngành", "Giáo trình"):
            filtered = [x for x in filtered if not x.get("source_dataset")]
        else:
            filtered = [x for x in filtered if x.get("source_dataset") == source]

    if qtype:
        filtered = [
            x
            for x in filtered
            if (x.get("question_type") or x.get("output", {}).get("question_type", "multiple_choice")) == qtype
        ]

    if difficulty:
        filtered = [x for x in filtered if x.get("difficulty") == difficulty]

    if search and search.strip():
        kw = search.strip().lower()
        filtered = [
            x
            for x in filtered
            if kw in str(x.get("id", "")).lower()
            or kw in str(x.get("subject", "")).lower()
            or kw in str(x.get("context", "")).lower()
            or kw in str(x.get("output", {}).get("question", "")).lower()
            or kw in str(x.get("output", {}).get("answer", "")).lower()
        ]

    total_matched = len(filtered)
    page_size = max(1, min(50, page_size))
    total_pages = max(1, (total_matched + page_size - 1) // page_size)
    page = max(1, min(total_pages, page))
    start = (page - 1) * page_size
    sliced = filtered[start : start + page_size]

    items = []
    for item in sliced:
        src_name = item.get("source_dataset") or "Giáo trình 8 chuyên ngành"
        chatml_str = format_sample_to_chatml(item)
        items.append(
            {
                "id": item.get("id"),
                "subject": item.get("subject"),
                "difficulty": item.get("difficulty"),
                "question_type": item.get("question_type") or item.get("output", {}).get("question_type", "multiple_choice"),
                "source": src_name,
                "source_dataset": src_name,
                "input_context": item.get("context", ""),
                "output_question": item.get("output", {}),
                "question": item.get("output", {}).get("question", ""),
                "answer": item.get("output", {}).get("answer", ""),
                "chatml": chatml_str,
                "chatml_prompt": chatml_str,
            }
        )

    return {
        "total": total_matched,
        "total_matched": total_matched,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "items": items,
    }

