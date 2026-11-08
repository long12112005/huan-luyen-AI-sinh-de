"""
Module Tải & Tiền Xử Lý Trực Tiếp Các Bộ Dữ Liệu Thực Tế Từ Hugging Face Hub (Quy mô 3.600 mẫu):
1. tridm/VMLU                       -> Trắc nghiệm tiếng Việt đa môn học (Multiple Choice)
2. taidng/UIT-ViQuAD2.0             -> Tự luận, Điền khuyết & Ghép cặp ngữ cảnh tiếng Việt (Essay, Fill-blank, Matching)
3. bkai-foundation-models/vi-alpaca -> Tự luận mở theo chỉ dẫn tiếng Việt (Open-ended Essay)
4. allenai/sciq                     -> Trắc nghiệm Khoa học có đoạn văn giải thích (Multiple Choice + Support)
5. ehovy/race                       -> Trắc nghiệm Đọc hiểu học thuật (RACE Reading Comprehension)
6. AndyChiang/cloth                 -> Điền khuyết Cloze Test chuẩn ĐH Carnegie Mellon (Fill-in-the-blank)

Cách chạy trực tiếp trên Terminal:
    py -m ai_training.hf_importer
"""

import json
import os
import re
import sys
import urllib.parse
import urllib.request

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from backend.config import TRAINING_DATA_PATH
from ai_training.train_qlora import run_qlora_training

BLOOM_LEVELS = ["Nhận biết", "Thông hiểu", "Vận dụng", "Vận dụng cao"]


def fetch_hf_rows(dataset_name: str, config: str = "default", split: str = "train", offset: int = 0, length: int = 100) -> list[dict]:
    """Tải trực tiếp 1 lô (batch) dữ liệu thực từ Hugging Face Datasets Server API."""
    encoded_ds = urllib.parse.quote(dataset_name)
    url = (
        f"https://datasets-server.huggingface.co/rows?"
        f"dataset={encoded_ds}&config={config}&split={split}&offset={offset}&length={length}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (AIExamGen-Trainer/3.0)"})
    with urllib.request.urlopen(req, timeout=25) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
        return [item["row"] for item in payload.get("rows", [])]


def fetch_hf_multi_batches(dataset_name: str, config: str = "default", split: str = "train", total_wanted: int = 500) -> list[dict]:
    """Tải nhiều batch liên tiếp (mỗi batch 100 dòng) từ Hugging Face Hub."""
    all_rows = []
    for offset in range(0, total_wanted, 100):
        batch_len = min(100, total_wanted - offset)
        try:
            batch = fetch_hf_rows(dataset_name, config=config, split=split, offset=offset, length=batch_len)
            if not batch:
                break
            all_rows.extend(batch)
        except Exception:
            break
    return all_rows


def convert_vmlu_rows(rows: list[dict], start_idx: int) -> list[dict]:
    """Chuyển đổi dữ liệu trắc nghiệm tiếng Việt tridm/VMLU sang chuẩn huấn luyện ChatML."""
    samples = []
    for i, r in enumerate(rows):
        q_text = str(r.get("question", "")).strip()
        choices = r.get("choices") or []
        ans = str(r.get("answer", "A")).strip().upper()
        if not q_text or len(choices) < 4:
            continue

        opts = {}
        for idx, letter in enumerate(["A", "B", "C", "D"]):
            raw_c = str(choices[idx]).strip()
            raw_c = re.sub(r"^[A-Da-d][\.\)\:\-]\s*", "", raw_c)
            opts[letter] = raw_c

        if ans not in ["A", "B", "C", "D"]:
            ans = "A"

        diff = BLOOM_LEVELS[i % 4]
        correct_content = opts.get(ans, "")
        context_str = f"Ngữ cảnh kiến thức (VMLU #{r.get('id', i)}): {q_text} Trọng tâm đáp án đúng: {correct_content}."

        samples.append(
            {
                "id": f"TRAIN_{start_idx + len(samples):04d}",
                "subject": "VMLU - Đa môn học Việt Nam",
                "difficulty": diff,
                "question_type": "multiple_choice",
                "source_dataset": "tridm/VMLU",
                "context": context_str,
                "output": {
                    "question_type": "multiple_choice",
                    "question": q_text,
                    "options": opts,
                    "answer": ans,
                    "explanation": f"Theo bộ dữ liệu chuẩn VMLU ({r.get('id', '')}), đáp án chính xác là {ans}: {correct_content}.",
                },
            }
        )
    return samples


def convert_viquad_rows(rows: list[dict], start_idx: int) -> list[dict]:
    """Chuyển đổi dữ liệu đọc hiểu tiếng Việt taidng/UIT-ViQuAD2.0 sang Tự luận, Điền khuyết & Ghép cặp."""
    samples = []
    valid_qa = []
    for r in rows:
        if r.get("is_impossible"):
            continue
        context = str(r.get("context", "")).strip()
        question = str(r.get("question", "")).strip()
        title = str(r.get("title", "Kiến thức Bách khoa")).strip()
        ans_obj = r.get("answers") or {}
        ans_texts = ans_obj.get("text") or []
        if not context or not question or not ans_texts:
            continue
        ans_str = str(ans_texts[0]).strip()
        if ans_str:
            valid_qa.append((title, context, question, ans_str))

    for i, (title, context, question, ans_str) in enumerate(valid_qa):
        diff = BLOOM_LEVELS[i % 4]
        mode = i % 3
        if mode == 0:
            samples.append(
                {
                    "id": f"TRAIN_{start_idx + len(samples):04d}",
                    "subject": f"UIT-ViQuAD 2.0 ({title})",
                    "difficulty": diff,
                    "question_type": "essay",
                    "source_dataset": "taidng/UIT-ViQuAD2.0",
                    "context": context[:750],
                    "output": {
                        "question_type": "essay",
                        "question": f"[Tự luận] {question}",
                        "options": {
                            "A": f"Đáp án chuẩn: {ans_str}",
                            "B": f"Chủ đề bài đọc: {title}",
                            "C": "Nguồn dữ liệu: UIT-ViQuAD 2.0 (ĐHQG TP.HCM)",
                            "D": "Phương pháp chấm: Độ tương đồng ngữ nghĩa TF-IDF Cosine & Khớp từ khóa",
                        },
                        "answer": ans_str,
                        "explanation": f"Trích xuất trực tiếp từ ngữ cảnh UIT-ViQuAD 2.0 (Chủ đề {title}): «{ans_str}».",
                    },
                }
            )
        elif mode == 1:
            cloze_ctx = context
            pat = re.compile(re.escape(ans_str), flags=re.IGNORECASE)
            if pat.search(cloze_ctx):
                cloze_ctx = pat.sub("[ (1) ................ ]", cloze_ctx, count=1)
            else:
                cloze_ctx = f"{question} -> Trả lời: [ (1) ................ ]"

            samples.append(
                {
                    "id": f"TRAIN_{start_idx + len(samples):04d}",
                    "subject": f"UIT-ViQuAD 2.0 ({title})",
                    "difficulty": diff,
                    "question_type": "fill_blank",
                    "source_dataset": "taidng/UIT-ViQuAD2.0",
                    "context": context[:750],
                    "output": {
                        "question_type": "fill_blank",
                        "question": f"[Điền khuyết] Dựa vào câu hỏi «{question}», hãy điền cụm từ còn thiếu vào vị trí (1) trong đoạn văn sau:\n« {cloze_ctx[:420]} »",
                        "options": {
                            "A": f"Gợi ý: Cụm từ gồm {len(ans_str.split())} từ",
                            "B": f"Đáp án chuẩn: {ans_str}",
                            "C": f"Chủ đề: {title}",
                            "D": "Nguồn: UIT-ViQuAD 2.0",
                        },
                        "answer": ans_str,
                        "explanation": f"Cụm từ chính xác cần điền theo ngữ cảnh UIT-ViQuAD 2.0 là: «{ans_str}».",
                    },
                }
            )
        else:
            p1 = valid_qa[i % len(valid_qa)]
            p2 = valid_qa[(i + 1) % len(valid_qa)]
            p3 = valid_qa[(i + 2) % len(valid_qa)]
            p4 = valid_qa[(i + 3) % len(valid_qa)]
            samples.append(
                {
                    "id": f"TRAIN_{start_idx + len(samples):04d}",
                    "subject": f"UIT-ViQuAD 2.0 ({title})",
                    "difficulty": diff,
                    "question_type": "matching",
                    "source_dataset": "taidng/UIT-ViQuAD2.0",
                    "context": f"{p1[1][:250]} {p2[1][:250]}",
                    "output": {
                        "question_type": "matching",
                        "question": f"[Ghép cặp] Nối mỗi câu hỏi/dữ kiện ở Cột A (1, 2, 3, 4) với đáp án chính xác ở Cột B (A, B, C, D) theo ngữ cảnh UIT-ViQuAD 2.0:",
                        "options": {
                            "A": f"1. {p1[2][:90]}  ⟷  B. {p1[3][:80]}",
                            "B": f"2. {p2[2][:90]}  ⟷  D. {p2[3][:80]}",
                            "C": f"3. {p3[2][:90]}  ⟷  A. {p3[3][:80]}",
                            "D": f"4. {p4[2][:90]}  ⟷  C. {p4[3][:80]}",
                        },
                        "answer": "1-B, 2-D, 3-A, 4-C",
                        "explanation": f"Đáp án ghép cặp đúng: 1-B ({p1[3]}), 2-D ({p2[3]}), 3-A ({p3[3]}), 4-C ({p4[3]}).",
                    },
                }
            )
    return samples


def convert_sciq_rows(rows: list[dict], start_idx: int) -> list[dict]:
    """Chuyển đổi dữ liệu Khoa học allenai/sciq (có đoạn giải thích support) sang chuẩn huấn luyện."""
    samples = []
    letters = ["A", "B", "C", "D"]
    for i, r in enumerate(rows):
        q_text = str(r.get("question", "")).strip()
        support = str(r.get("support", "")).strip()
        correct = str(r.get("correct_answer", "")).strip()
        d1 = str(r.get("distractor1", "")).strip()
        d2 = str(r.get("distractor2", "")).strip()
        d3 = str(r.get("distractor3", "")).strip()
        if not q_text or not correct:
            continue
        if not support:
            support = f"Scientific fact: {q_text} Answer: {correct}."

        correct_letter = letters[i % 4]
        distractors = [d1, d2, d3]
        opts = {}
        d_ptr = 0
        for l_key in letters:
            if l_key == correct_letter:
                opts[l_key] = correct
            else:
                opts[l_key] = distractors[d_ptr]
                d_ptr += 1

        samples.append(
            {
                "id": f"TRAIN_{start_idx + len(samples):04d}",
                "subject": "Khoa học Tự nhiên (SciQ Dataset)",
                "difficulty": BLOOM_LEVELS[i % 4],
                "question_type": "multiple_choice",
                "source_dataset": "allenai/sciq",
                "context": support[:700],
                "output": {
                    "question_type": "multiple_choice",
                    "question": q_text,
                    "options": opts,
                    "answer": correct_letter,
                    "explanation": f"Căn cứ theo đoạn văn khoa học (SciQ Support): «{support[:350]}»",
                },
            }
        )
    return samples


def convert_race_rows(rows: list[dict], start_idx: int) -> list[dict]:
    """Chuyển đổi dữ liệu đọc hiểu trắc nghiệm ehovy/race sang chuẩn huấn luyện."""
    samples = []
    letters = ["A", "B", "C", "D"]
    for i, r in enumerate(rows):
        article = str(r.get("article", "")).strip()
        q_text = str(r.get("question", "")).strip()
        options = r.get("options") or []
        ans = str(r.get("answer", "A")).strip().upper()
        if not article or not q_text or len(options) < 4:
            continue
        if ans not in letters:
            ans = "A"
        opts = {letters[j]: str(options[j]).strip() for j in range(4)}

        samples.append(
            {
                "id": f"TRAIN_{start_idx + len(samples):04d}",
                "subject": "Đọc hiểu Học thuật (RACE Dataset)",
                "difficulty": BLOOM_LEVELS[i % 4],
                "question_type": "multiple_choice",
                "source_dataset": "ehovy/race",
                "context": article[:700],
                "output": {
                    "question_type": "multiple_choice",
                    "question": q_text,
                    "options": opts,
                    "answer": ans,
                    "explanation": f"Theo ngữ cảnh đoạn văn đọc hiểu RACE ({r.get('example_id', '')}), đáp án đúng là {ans}: {opts[ans]}.",
                },
            }
        )
    return samples


def convert_cloth_rows(rows: list[dict], start_idx: int) -> list[dict]:
    """Chuyển đổi dữ liệu điền khuyết AndyChiang/cloth sang dạng fill_blank."""
    samples = []
    for i, r in enumerate(rows):
        sent = str(r.get("sentence", "")).strip()
        ans = str(r.get("answer", "")).strip()
        distractors = r.get("distractors") or []
        if not sent or not ans:
            continue

        cloze_sent = sent.replace("[MASK]", "[ (1) ................ ]")
        hint_opts = ", ".join([ans] + [str(d) for d in distractors[:3]])

        samples.append(
            {
                "id": f"TRAIN_{start_idx + len(samples):04d}",
                "subject": "Tiếng Anh Học Thuật (CLOTH CMU)",
                "difficulty": BLOOM_LEVELS[i % 4],
                "question_type": "fill_blank",
                "source_dataset": "AndyChiang/cloth",
                "context": sent.replace("[MASK]", ans),
                "output": {
                    "question_type": "fill_blank",
                    "question": f"[Điền khuyết - Cloze Test] Chọn từ vựng chính xác điền vào chỗ trống (1):\n« {cloze_sent} »",
                    "options": {
                        "A": f"Gợi ý các từ lựa chọn: ({hint_opts})",
                        "B": f"Đáp án đúng: {ans}",
                        "C": f"Phương án nhiễu: {', '.join(str(d) for d in distractors)}",
                        "D": "Nguồn: CLOTH Dataset (Carnegie Mellon University)",
                    },
                    "answer": ans,
                    "explanation": f"Từ điền khuyết chính xác trong ngữ cảnh câu là «{ans}» (Các phương án nhiễu: {', '.join(str(d) for d in distractors)}).",
                },
            }
        )
    return samples


def convert_vialpaca_rows(rows: list[dict], start_idx: int) -> list[dict]:
    """Chuyển đổi dữ liệu tự luận mở bkai-foundation-models/vi-alpaca sang dạng essay."""
    samples = []
    for i, r in enumerate(rows):
        inst = str(r.get("instruction", "")).strip()
        inp = str(r.get("input", "")).strip()
        out = str(r.get("output", "")).strip()
        if not inst or not out or len(out.split()) < 6:
            continue

        full_q = f"[Tự luận] {inst}" + (f" ({inp})" if inp else "")
        samples.append(
            {
                "id": f"TRAIN_{start_idx + len(samples):04d}",
                "subject": "Vi-Alpaca (Tự luận Đa lĩnh vực)",
                "difficulty": BLOOM_LEVELS[i % 4],
                "question_type": "essay",
                "source_dataset": "bkai-foundation-models/vi-alpaca",
                "context": out[:650],
                "output": {
                    "question_type": "essay",
                    "question": full_q,
                    "options": {
                        "A": f"Đáp án mẫu: {out[:280]}...",
                        "B": "Nguồn: BKAI Foundation Models (vi-alpaca)",
                        "C": "Loại câu hỏi: Tự luận mở theo chỉ dẫn (Instruction-following)",
                        "D": "Phương pháp chấm: Độ tương đồng ngữ nghĩa TF-IDF Cosine",
                    },
                    "answer": out[:500],
                    "explanation": f"Đáp án tham khảo chuẩn từ bộ dữ liệu BKAI Vi-Alpaca: «{out[:320]}»",
                },
            }
        )
    return samples


def download_and_merge_huggingface_datasets(target_total: int = 3600) -> dict:
    if os.path.exists(TRAINING_DATA_PATH):
        with open(TRAINING_DATA_PATH, "r", encoding="utf-8") as f:
            corpus = json.load(f)
    else:
        corpus = []

    # Giữ lại 240 mẫu nền tảng của 8 môn học
    corpus = [x for x in corpus if not x.get("source_dataset")]
    stats_imported = {"Base_Academic_8_Subjects": len(corpus)}

    # 1. Tải UIT-ViQuAD 2.0 (1.300 dòng -> ~900+ mẫu Essay, Fill-blank, Matching tiếng Việt)
    print("  -> Đang tải UIT-ViQuAD 2.0 (1.300 dòng)...")
    viquad_rows = fetch_hf_multi_batches("taidng/UIT-ViQuAD2.0", "default", "train", total_wanted=1300)
    viquad_samples = convert_viquad_rows(viquad_rows, len(corpus) + 1)
    corpus.extend(viquad_samples)
    stats_imported["taidng/UIT-ViQuAD2.0"] = len(viquad_samples)

    # 2. Tải VMLU từ train + validation + test (~850 mẫu Trắc nghiệm tiếng Việt)
    print("  -> Đang tải VMLU (train, validation, test)...")
    vmlu_rows = (
        fetch_hf_multi_batches("tridm/VMLU", "default", "train", total_wanted=300)
        + fetch_hf_multi_batches("tridm/VMLU", "default", "validation", total_wanted=200)
        + fetch_hf_multi_batches("tridm/VMLU", "default", "test", total_wanted=450)
    )
    vmlu_samples = convert_vmlu_rows(vmlu_rows, len(corpus) + 1)
    corpus.extend(vmlu_samples)
    stats_imported["tridm/VMLU"] = len(vmlu_samples)

    # 3. Tải SciQ (500 mẫu Trắc nghiệm Khoa học)
    print("  -> Đang tải SciQ (500 dòng)...")
    sciq_rows = fetch_hf_multi_batches("allenai/sciq", "default", "train", total_wanted=500)
    sciq_samples = convert_sciq_rows(sciq_rows, len(corpus) + 1)
    corpus.extend(sciq_samples)
    stats_imported["allenai/sciq"] = len(sciq_samples)

    # 4. Tải RACE (500 mẫu Đọc hiểu Trắc nghiệm)
    print("  -> Đang tải RACE (500 dòng)...")
    race_rows = fetch_hf_multi_batches("ehovy/race", "all", "train", total_wanted=500)
    race_samples = convert_race_rows(race_rows, len(corpus) + 1)
    corpus.extend(race_samples)
    stats_imported["ehovy/race"] = len(race_samples)

    # 5. Tải CLOTH (500 mẫu Điền khuyết)
    print("  -> Đang tải CLOTH (500 dòng)...")
    cloth_rows = fetch_hf_multi_batches("AndyChiang/cloth", "default", "train", total_wanted=500)
    cloth_samples = convert_cloth_rows(cloth_rows, len(corpus) + 1)
    corpus.extend(cloth_samples)
    stats_imported["AndyChiang/cloth"] = len(cloth_samples)

    # 6. Tải BKAI Vi-Alpaca (500 mẫu Tự luận tiếng Việt)
    print("  -> Đang tải BKAI Vi-Alpaca (500 dòng)...")
    alpaca_rows = fetch_hf_multi_batches("bkai-foundation-models/vi-alpaca", "default", "train", total_wanted=500)
    alpaca_samples = convert_vialpaca_rows(alpaca_rows, len(corpus) + 1)
    corpus.extend(alpaca_samples)
    stats_imported["bkai-foundation-models/vi-alpaca"] = len(alpaca_samples)

    if len(corpus) > target_total:
        corpus = corpus[:target_total]

    for idx, item in enumerate(corpus, 1):
        item["id"] = f"TRAIN_{idx:04d}"

    with open(TRAINING_DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(corpus, f, ensure_ascii=False, indent=2)

    return {
        "imported_by_source": stats_imported,
        "total_corpus_size": len(corpus),
    }


if __name__ == "__main__":
    print("⏳ Đang tải nhiều lô dữ liệu từ Hugging Face Hub để đạt mốc 3.600 mẫu...")
    res = download_and_merge_huggingface_datasets(target_total=3600)
    print("✅ Kết quả tải & chuyển đổi từ Hugging Face:", json.dumps(res, ensure_ascii=False, indent=2))
    print("⏳ Đang chạy huấn luyện lại mô hình QLoRA trên 3.600 mẫu dữ liệu...")
    train_out = run_qlora_training(epochs=5, lora_rank=16)
    print(
        f"🎉 Huấn luyện hoàn tất! Tổng số mẫu: {train_out['trained_samples']} | Final Loss: {train_out['final_training_loss']}"
    )
