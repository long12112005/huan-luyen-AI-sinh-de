"""
Cấu hình trung tâm cho Hệ thống Web AI Sinh Đề Thi.
"""

import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
SAMPLE_DOCS_DIR = os.path.join(DATA_DIR, "sample_docs")
DB_PATH = os.path.join(DATA_DIR, "app.db")
TRAINING_DATA_PATH = os.path.join(DATA_DIR, "training_dataset.json")
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(SAMPLE_DOCS_DIR, exist_ok=True)

MODEL_CONFIG = {
    "base_model": "Qwen/Qwen2.5-7B-Instruct",
    "fine_tune_method": "QLoRA 4-bit NormalFloat (NF4)",
    "lora_rank": 16,
    "lora_alpha": 32,
    "lora_dropout": 0.05,
    "max_seq_length": 1024,
    "checkpoint_dir": os.path.join(BASE_DIR, "checkpoints", "qwen2.5-aqg-qlora"),
}

