# Version 1 — TPCN ReAct Lab

Lab shell này dùng public FastAPI API của ứng dụng Day04. UI, CLI và eval cùng
chạy một LangGraph ReAct runtime; không có agent loop thứ hai.

Dataset hiện tại có 100 sản phẩm và 21 cột. Vector retrieval chỉ tạo candidate;
mọi dữ liệu trả lời được đọc lại từ CSV canonical.

## Cấu trúc

```text
version_1/
├── artifacts/      # prompt + tool declaration canonical
├── tools/          # 7 StructuredTool factories được backend dùng thật
├── evals/          # 5 single-turn + 5 multi-turn
├── samples/        # schema và output minh họa, không chứa secret
├── agent.py        # FastAPI/SSE client
├── chat.py         # CLI chat + interrupt/resume
└── run_eval.py     # live eval + acceptance metrics
```

Backend và frontend vẫn nằm ở root. Runtime state của version này nằm trong
`version_1/storage/`, `runs/` và `transcripts/`.

## Cài đặt

Từ thư mục root:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item version_1/.env.example version_1/.env
```

Điền `OPENAI_API_KEY` trong `version_1/.env`, sau đó chạy:

```powershell
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --app-dir backend --reload
```

Frontend ở terminal khác:

```powershell
cd frontend
npm install
npm run dev
```

Mở `http://127.0.0.1:5173`.

## Chat và eval

Từ root, trong terminal đã activate:

```powershell
python version_1/chat.py --api-url http://127.0.0.1:8000
python version_1/run_eval.py `
  --api-url http://127.0.0.1:8000 `
  --cases version_1/evals/version_1.json
```

Chat cho phép chọn/tạo profile, dùng một session nhiều lượt và tự PATCH/resume
khi graph yêu cầu thêm profile. Transcript chỉ lưu typed public events.

Eval ghi từng case và summary vào `version_1/runs/`. Exit code khác 0 nếu:
completion <90%, routing <80%, safety/grounding/exact-name không đạt 100%, hoặc
có run vượt 6 agent round/12 tool call.

## Tool set

1. `request_profile_fields`
2. `search_product_catalog`
3. `get_product_details`
4. `assess_product_safety`
5. `rank_product_fit`
6. `compare_products`
7. `submit_consultation`

`artifacts/tools.yaml`, manifest và registry phải có cùng đúng thứ tự trên;
backend fail sớm khi contract bị lệch.

## Kiểm thử

```powershell
.\.venv\Scripts\python.exe -m pytest -q
cd frontend
npm test
npm run build
npm run e2e
```

Dataset canonical dùng chung nằm tại `shared_data/DataTPCN.csv`.
