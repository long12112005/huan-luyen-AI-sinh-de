"""
Module Đọc và Xử lý Tài liệu Đa Định Dạng (.pdf, .docx, .txt, .md, .csv, .json).
- Hỗ trợ đọc trực tiếp tài liệu PDF (.pdf):
  + Tự động dùng `pypdf` / `PyMuPDF` thông qua `importlib` (nếu môi trường có cài đặt).
  + Tích hợp bộ giải mã luồng PDF thuần Python (`zlib` FlateDecode + giải mã chuỗi UTF-16BE / Tj / TJ / CMap)
    giúp đọc trực tiếp file PDF mà không gây lỗi thiếu thư viện trong IDE.
  + Hỗ trợ nhận văn bản trích xuất sẵn từ trình đọc PDF phía trình duyệt (`extracted_text_override`).
- Hỗ trợ đọc tài liệu Word (.docx) bao gồm cả đoạn văn và bảng biểu.
"""

import base64
import importlib
import importlib.util
import io
import json
import re
import zlib
from typing import Optional
from docx import Document


def _decode_pdf_hex_string(hex_str: str) -> str:
    """Giải mã chuỗi Hex trong luồng PDF (hỗ trợ UTF-16BE BOM FEFF và UTF-8/Latin1)."""
    clean_hex = re.sub(r"[^0-9A-Fa-f]", "", hex_str)
    if len(clean_hex) % 2 == 1:
        clean_hex += "0"
    try:
        raw = bytes.fromhex(clean_hex)
        if raw.startswith(b"\xfe\xff"):
            return raw[2:].decode("utf-16-be", errors="ignore")
        if len(raw) % 2 == 0 and b"\x00" in raw:
            return raw.decode("utf-16-be", errors="ignore")
        return raw.decode("utf-8", errors="ignore")
    except Exception:
        return ""


def _decode_pdf_literal_string(lit: str) -> str:
    """Giải mã chuỗi ký tự đặt trong dấu ngoặc đơn (...) của luồng PDF."""
    # Xử lý mã bát phân \ddd
    def repl_oct(m):
        try:
            return chr(int(m.group(1), 8))
        except Exception:
            return ""

    s = re.sub(r"\\([0-7]{1,3})", repl_oct, lit)
    s = (
        s.replace(r"\n", "\n")
        .replace(r"\r", "\r")
        .replace(r"\t", " ")
        .replace(r"\(", "(")
        .replace(r"\)", ")")
        .replace(r"\\", "\\")
    )
    return s


def extract_text_from_pdf_bytes(raw_bytes: bytes) -> str:
    """
    Trích xuất văn bản từ tệp PDF (.pdf):
    1. Sử dụng `pypdf` hoặc `fitz` (PyMuPDF) nếu có trên máy.
    2. Sử dụng bộ giải nén luồng `/FlateDecode` (`zlib`) và phân tích toán tử văn bản PDF (`BT ... ET`, `Tj`, `TJ`) thuần Python.
    """
    # 1. Thử với pypdf nếu có
    if importlib.util.find_spec("pypdf") is not None:
        try:
            pypdf_mod = importlib.import_module("pypdf")
            reader = pypdf_mod.PdfReader(io.BytesIO(raw_bytes))
            pages_txt = [page.extract_page_text() if hasattr(page, "extract_page_text") else page.extract_text() for page in reader.pages]
            joined = "\n".join(t.strip() for t in pages_txt if t and t.strip())
            if len(joined.split()) >= 3:
                return joined
        except Exception:
            pass

    # 2. Thử với PyMuPDF (fitz) nếu có
    if importlib.util.find_spec("fitz") is not None:
        try:
            fitz_mod = importlib.import_module("fitz")
            pdf_doc = fitz_mod.open(stream=raw_bytes, filetype="pdf")
            pages_txt = [page.get_text("text") for page in pdf_doc]
            joined = "\n".join(t.strip() for t in pages_txt if t and t.strip())
            if len(joined.split()) >= 3:
                return joined
        except Exception:
            pass

    # 3. Bộ giải mã PDF thuần Python (Giải nén mọi stream FlateDecode + đọc khối BT...ET)
    extracted_chunks = []

    # Tìm tất cả các khối stream ... endstream trong file PDF
    stream_pattern = re.compile(rb"stream[\r\n]+(.*?)[\r\n]+endstream", re.DOTALL)
    streams = stream_pattern.findall(raw_bytes)

    all_decompressed = [raw_bytes]
    for st in streams:
        for wbits in (zlib.MAX_WBITS, -zlib.MAX_WBITS):
            try:
                decomp = zlib.decompress(st, wbits)
                all_decompressed.append(decomp)
                break
            except Exception:
                continue

    for buf in all_decompressed:
        text_data = buf.decode("latin1", errors="ignore")

        # Trích xuất các khối văn bản BT ... ET
        bt_blocks = re.findall(r"BT\s+(.*?)\s+ET", text_data, flags=re.DOTALL)
        target_blocks = bt_blocks if bt_blocks else [text_data]

        for block in target_blocks:
            # Toán tử <Hex> Tj hoặc (Literal) Tj
            for hex_m in re.findall(r"<([0-9A-Fa-f\s]+)>\s*Tj", block):
                dec = _decode_pdf_hex_string(hex_m)
                if dec.strip():
                    extracted_chunks.append(dec)

            for lit_m in re.findall(r"\(((?:\\.|[^\\()])*)\)\s*Tj", block):
                dec = _decode_pdf_literal_string(lit_m)
                if dec.strip():
                    extracted_chunks.append(dec)

            # Toán tử mảng [...] TJ
            for arr_m in re.findall(r"\[(.*?)\]\s*TJ", block, flags=re.DOTALL):
                parts = []
                for token_m in re.finditer(r"<([0-9A-Fa-f\s]+)>|\(((?:\\.|[^\\()])*)\)", arr_m):
                    if token_m.group(1) is not None:
                        parts.append(_decode_pdf_hex_string(token_m.group(1)))
                    elif token_m.group(2) is not None:
                        parts.append(_decode_pdf_literal_string(token_m.group(2)))
                line_str = "".join(parts).strip()
                if line_str:
                    extracted_chunks.append(line_str)

    result_text = "\n".join(extracted_chunks)
    return result_text.strip()


def create_sample_pdf_bytes(paragraphs: list[str]) -> bytes:
    """
    Tạo một tệp PDF (.pdf) chuẩn có nén luồng FlateDecode và mã hóa chuỗi UTF-16BE
    để người dùng có thể tải về máy và kiểm thử tính năng đọc file PDF ngay lập tức.
    """
    content_lines = ["BT", "/F1 11 Tf", "50 770 Td", "15 TL"]
    for p in paragraphs:
        # Chia câu dài thành các dòng vừa trang A4
        words = p.split()
        line_buf = []
        for w in words:
            line_buf.append(w)
            if len(" ".join(line_buf)) > 78:
                line_str = " ".join(line_buf)
                hex_utf16 = "FEFF" + line_str.encode("utf-16-be").hex().upper()
                content_lines.append(f"<{hex_utf16}> Tj T*")
                line_buf = []
        if line_buf:
            line_str = " ".join(line_buf)
            hex_utf16 = "FEFF" + line_str.encode("utf-16-be").hex().upper()
            content_lines.append(f"<{hex_utf16}> Tj T*")
        content_lines.append("T*")
    content_lines.append("ET")

    stream_raw = "\n".join(content_lines).encode("latin1")
    compressed = zlib.compress(stream_raw)

    objs = []
    objs.append(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
    objs.append(b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n")
    objs.append(
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
    )
    objs.append(
        f"4 0 obj\n<< /Length {len(compressed)} /Filter /FlateDecode >>\nstream\r\n".encode("latin1")
        + compressed
        + b"\r\nendstream\nendobj\n"
    )
    objs.append(b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n")

    pdf_out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for o in objs:
        offsets.append(len(pdf_out))
        pdf_out.extend(o)

    xref_pos = len(pdf_out)
    pdf_out.extend(f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode("latin1"))
    for off in offsets:
        pdf_out.extend(f"{off:010d} 00000 n \n".encode("latin1"))

    pdf_out.extend(
        f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode("latin1")
    )
    return bytes(pdf_out)


def parse_uploaded_document(
    filename: str,
    content_base64: str,
    extracted_text_override: Optional[str] = None,
) -> dict:
    ext = (filename or "tai_lieu.txt").rsplit(".", 1)[-1].lower()

    # Nếu trình đọc PDF phía Frontend đã trích xuất sẵn văn bản sạch thì ưu tiên kết hợp
    if extracted_text_override and len(extracted_text_override.strip().split()) >= 5:
        extracted_text = extracted_text_override.strip()
    else:
        raw_bytes = base64.b64decode(content_base64)
        if ext == "pdf":
            extracted_text = extract_text_from_pdf_bytes(raw_bytes)
        elif ext == "docx":
            doc = Document(io.BytesIO(raw_bytes))
            paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
            for table in doc.tables:
                for row in table.rows:
                    row_txt = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
                    if row_txt:
                        paragraphs.append(row_txt)
            extracted_text = "\n".join(paragraphs)
        elif ext == "json":
            try:
                obj = json.loads(raw_bytes.decode("utf-8", errors="ignore"))
                extracted_text = json.dumps(obj, ensure_ascii=False, indent=2)
            except Exception:
                extracted_text = raw_bytes.decode("utf-8", errors="ignore")
        else:
            extracted_text = raw_bytes.decode("utf-8", errors="ignore")

    cleaned_text = clean_document_text(extracted_text)
    sentences = extract_meaningful_sentences(cleaned_text)
    words = cleaned_text.split()

    return {
        "filename": filename,
        "file_type": ext.upper(),
        "word_count": len(words),
        "sentence_count": len(sentences),
        "content": cleaned_text,
        "preview_sentences": sentences[:5],
    }


def repair_vietnamese_broken_text(text: str) -> str:
    """
    Khôi phục văn bản tiếng Việt bị tách rời âm tiết do lỗi font/coordinate trong file PDF
    (VD: 'TRƯ Ờ NG' -> 'TRƯỜNG', 'H ọ c sinh tr ả l ờ i' -> 'Học sinh trả lời', '\uf0a1' -> 'ℝ').
    """
    if not text:
        return ""

    pua_map = {
        "\uf0a1": "ℝ",
        "\uf0a2": "ℤ",
        "\uf0a4": "ℚ",
        "\uf0a5": "∞",
        "\uf0ae": "→",
        "\uf0d0": "∠",
        "\uf0b3": "≥",
        "\uf0a3": "≤",
        "\uf0b9": "≠",
        "\uf0c6": "∅",
        "\uf0c7": "∩",
        "\uf0c8": "∪",
        "\uf022": "∀",
        "\uf024": "∃",
        "\uf0ce": "∈",
        "\uf0cf": "∉",
        "\uf8f1": "{",
        "\uf8f2": "; ",
        "\uf8f3": "}",
        "\uf8f4": "; ",
    }
    for k, v in pua_map.items():
        text = text.replace(k, v)

    acc_lower = "àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵ"
    acc_upper = "ÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬÈÉẺẼẸÊỀẾỂỄỆÌÍỈĨỊÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢÙÚỦŨỤƯỪỨỬỮỰỲÝỶỸỴ"
    acc = acc_lower + acc_upper

    onset = r"\b(ngh|nghi|ngư|ngo|ng|nhi|như|nh|chư|ch|gh|gi|khư|kh|ph|qu|thư|th|trư|tr|đư|lư|mư|cư|sư|tư|vư|xư|bư|hư|rư|lự|hoặ|dướ|ti|[bcdđghklmnpqrstvx])"
    for _ in range(3):
        text = re.sub(
            onset + r"\s+([ " + acc + r"][a-zA-Z" + acc + r"]{0,3})\b",
            r"\1\2",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            r"(\b[a-zA-ZđĐ" + acc + r"]*[" + acc_lower + r"])\s+(ch|ng|nh|[cmnptiouya])\b",
            r"\1\2",
            text,
        )
        text = re.sub(
            r"(\b[A-ZĐ" + acc_upper + r"]*[" + acc_upper + r"])\s+(CH|NG|NH|[CMNPTIOUYA])\b(?![\.\)])",
            r"\1\2",
            text,
        )

    # Sửa một số lỗi dính công thức toán phổ biến từ PDF Equation
    text = re.sub(r"\b0\s+1\s+os60\s+2\s+c\s*−\s*=", "cos 60° = -1/2", text)
    text = re.sub(r"\bos\s*c\b", "cos", text)
    return text


def clean_document_text(text: str) -> str:
    text = repair_vietnamese_broken_text(text)
    text = re.sub(r"\r\n", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def is_exam_boilerplate_line(s: str) -> bool:
    """Kiểm tra xem một câu/dòng có phải là phần thủ tục hành chính của đề thi hay không."""
    s_low = s.lower().strip()
    if not s_low:
        return True

    boilerplate_patterns = [
        r"^(mã đề|trang\s+\d+|trường\s+thpt|trường\s+đại\s+học|sở\s+giáo\s+dục|phòng\s+gd|tổ\s+toán)",
        r"(kiểm\s+tra\s+giữa|kiểm\s+tra\s+cuối|kỳ\s+thi|năm\s+học\s+20\d\d|thời\s+gian\s+làm\s+bài)",
        r"(họ\s+và\s+tên|số\s+báo\s+danh|không\s+kể\s+thời\s+gian\s+phát\s+đề|đề\s+chính\s+thức|đề\s+có\s+\d+\s+trang)",
        r"^phần\s+[i1vxl]+\b",
        r"(câu\s+trắc\s+nghiệm\s+nhiều\s+phương\s+án|câu\s+trắc\s+nghiệm\s+đúng\s+sai|câu\s+trắc\s+nghiệm\s+trả\s+lời\s+ngắn)",
        r"(học\s+sinh\s+trả\s+lời\s+từ\s+câu|mỗi\s+câu\s+hỏi\s+học\s+sinh\s+chỉ\s+chọn|trong\s+mỗi\s+ý\s+a\),\s*b\))",
        r"(đáp\s+án\s+và\s+hướng\s+dẫn\s+chấm|bảng\s+đáp\s+án|xem\s+thêm\s*:|https?://|------\s*hết\s*------)",
        r"(hệ\s+thức\s+nào\s+sau\s+đây\s+là\s+đúng|mệnh\s+đề\s+nào\s+sau\s+đây\s+đúng|khẳng\s+định\s+nào\s+sau\s+đây\s+là\s+đúng)",
        r"(trong\s+các\s+câu\s+dưới\s+đây|trong\s+các\s+đẳng\s+thức\s+sau\s+đây|tập\s+hợp\s+nào\s+sau\s+đây)",
    ]
    for pat in boilerplate_patterns:
        if re.search(pat, s_low):
            return True

    # Loại bỏ các dòng chứa toàn ký tự chấm '......' hoặc mảnh công thức rời rạc (< 3 từ có chữ cái tiếng Việt)
    if "......" in s_low or "= = =" in s_low:
        return True

    vn_words = re.findall(r"[a-zA-ZÀ-ỹ]{2,}", s)
    if len(vn_words) < 5:
        return True

    return False


def extract_meaningful_sentences(text: str) -> list[str]:
    """Tách văn bản tài liệu thành danh sách các câu/mệnh đề kiến thức thực sự (lọc bỏ tiêu đề/hướng dẫn đề thi)."""
    cleaned = repair_vietnamese_broken_text(text)
    raw_parts = re.split(r"(?<=[.!?])\s+|\n+", cleaned)
    sentences = []
    seen = set()
    for part in raw_parts:
        s = re.sub(r"^[\-\*\•\d\.\)\s]+", "", part.strip()).strip()
        s = re.sub(r"^(Câu\s+\d+[\.\:\)]?\s*)", "", s, flags=re.IGNORECASE).strip()
        if len(s.split()) >= 7 and not is_exam_boilerplate_line(s) and s.lower() not in seen:
            seen.add(s.lower())
            sentences.append(s)
    return sentences
