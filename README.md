# Day04 — ReAct Agent tư vấn Thực phẩm chức năng

Ứng dụng local tư vấn thực phẩm chức năng dựa **duy nhất** trên
`data/DataTPCN.csv`. Agent dùng LangGraph ReAct, Chroma local và safety gate có
thể kiểm thử. Backend không lưu hoặc hiển thị raw chain-of-thought.

Dataset hiện tại có **100 sản phẩm và 21 cột**. Con số 50 trong yêu cầu ban đầu
không còn khớp với file CSV đang có, vì vậy code và acceptance test dùng số liệu
thực tế là 100.

## Kiến trúc

```text
backend/app/
├── agent/
│   ├── shared/        # catalog, retrieval, scoring, safety, providers, persistence
│   └── version_1/     # manifest, prompt, allowlist, StateGraph + ToolNode
├── main.py            # FastAPI + SSE
├── services.py        # background LangGraph runner + SQLite checkpoints
└── schemas.py
frontend/src/          # React/TypeScript mentor dashboard
data/DataTPCN.csv      # nguồn sự thật canonical
storage/               # SQLite + Chroma, không commit
starter_v0/            # giữ nguyên để tham khảo, không được import
```

Luồng graph:

```text
agent ↔ tools → finalize
  │       │
  └ repair┘
```

Graph giới hạn 6 vòng, 12 tool call, phát hiện call lặp và chỉ sửa output một
lần. Terminal tool `submit_consultation` chỉ chấp nhận sản phẩm đã retrieve,
safety-check và rank.

## Yêu cầu

- Python 3.11+ khuyến nghị (Python 3.10 vẫn chạy nhưng Google sẽ dừng hỗ trợ
  phiên bản này trong các package mới từ tháng 10/2026).
- Node.js LTS. Trên máy hiện tại đã cài Node `v24.18.0` và npm `11.16.0`.
- Một `OPENAI_API_KEY`. Gemini là optional và tự skip live test khi chưa có key.

Sau khi cài Node, hãy mở terminal mới để Windows nạp lại `PATH`.

## Chạy local trên Windows PowerShell

Từ thư mục repo:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

Mở `.env`, chỉ điền:

```dotenv
OPENAI_API_KEY=<your-key>
```

Khởi động backend:

```powershell
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --app-dir backend --reload
```

Backend tự chạy Alembic migration. Swagger ở
`http://127.0.0.1:8000/docs`.

Trong terminal khác:

```powershell
cd frontend
npm install
npm run dev
```

Mở `http://127.0.0.1:5173`.

Lần chạy tư vấn đầu tiên sẽ tạo embedding cho catalog. Có thể tạo trước:

```powershell
python -m app.cli index --provider openai
```

## Tool set version 1

1. `request_profile_fields`
2. `search_product_catalog`
3. `get_product_details`
4. `assess_product_safety`
5. `rank_product_fit`
6. `compare_products`
7. `submit_consultation`

Vector search chỉ tạo candidate. Giá, liều, thành phần, chống chỉ định và
provenance trong câu trả lời luôn được đọc lại từ repository CSV canonical.
Safety là gate riêng, không cộng vào điểm phù hợp.

## API

- `POST/GET/PATCH/DELETE /api/v1/profiles`
- `POST/GET /api/v1/sessions`
- `POST /api/v1/sessions/{session_id}/runs`
- `GET /api/v1/runs/{run_id}/events` — SSE, hỗ trợ `Last-Event-ID`
- `GET /api/v1/runs/{run_id}`
- `POST /api/v1/runs/{run_id}/resume`
- `GET /api/v1/versions`
- `GET /api/v1/health`

SSE chỉ phát trace công khai có cấu trúc: lifecycle, node, tool, retrieval,
ranking, safety, profile requirement và answer. Không phát raw reasoning.

## Kiểm thử

```powershell
# Backend, live provider tự skip nếu thiếu key
.\.venv\Scripts\python.exe -m pytest -q

# Chỉ live OpenAI/Gemini
.\.venv\Scripts\python.exe -m pytest -m live -q

# Frontend
cd frontend
npm test
npm run build
npm run e2e
```

Playwright dùng Chrome đã cài trên máy, không cần tải Chromium riêng.
Bộ eval định nghĩa đúng 5 single-turn và 5 multi-turn tại
`backend/app/evals/version_1.json`.

## Giới hạn an toàn

- Đây không phải công cụ chẩn đoán hoặc kê đơn.
- Không thay đổi liều thuốc điều trị và không khẳng định sản phẩm “an toàn”.
- TPCN không phải thuốc và không thay thế thuốc chữa bệnh.
- Với bệnh nền, thuốc, thai kỳ hoặc dữ liệu chống chỉ định chưa đủ, kết quả yêu
  cầu người dùng trao đổi bác sĩ/dược sĩ.
- Không web search, review, chứng nhận hay bằng chứng lâm sàng ngoài CSV.

Chỉ tạo `version_2` khi eval `version_1` chứng minh một failure cụ thể. Code
`shared` không phụ thuộc version; registry đăng ký version tường minh.
