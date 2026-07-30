# Version 1 — TPCN ReAct Lab

`version_1` là lab shell dùng public FastAPI API của ứng dụng Day04. Frontend,
CLI và eval đều chạy chung một LangGraph ReAct runtime trong backend; không có
agent loop thứ hai.

Dataset canonical nằm tại `shared_data/DataTPCN.csv`, gồm 100 sản phẩm và 21
cột. Vector retrieval chỉ tạo candidate; dữ liệu cuối cùng luôn được đọc lại từ
CSV.

## Chạy nhanh trên Windows

Các lệnh bên dưới phải được chạy từ:

```text
D:\AI-DS-Study\Lab\Day04_2A202601032_LeNguyenPhuocThanh
```

Nên dùng đường dẫn Python trong `.venv` thay vì lệnh `python` hoặc `uvicorn`
toàn cục. Cách này tránh chạy nhầm Python của Laragon.

### Bước 1 — Chuẩn bị Python

Mở PowerShell:

```powershell
cd D:\AI-DS-Study\Lab\Day04_2A202601032_LeNguyenPhuocThanh

# Chỉ tạo khi chưa có .venv
py -3.11 -m venv .venv

.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Nếu `.venv` đã tồn tại và cài dependency thành công thì không cần tạo lại.
Không bắt buộc chạy `Activate.ps1`.

### Bước 2 — Cấu hình OpenAI

Không ghi đè `.env` nếu bạn đã điền key:

```powershell
if (-not (Test-Path .\version_1\.env)) {
    Copy-Item .\version_1\.env.example .\version_1\.env
}

notepad .\version_1\.env
```

Điền key theo đúng dạng:

```dotenv
OPENAI_API_KEY=sk-your-real-key
OPENAI_CHAT_MODEL=gpt-4o-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
```

Lưu ý:

- Không đặt key trong `<...>`.
- Không thêm từ khóa `export`.
- Backend chỉ đọc `version_1/.env`; `.env` tại root không được sử dụng.
- Sau khi thêm hoặc đổi key, phải dừng và chạy lại backend.
- Không commit hoặc gửi API key vào log, ảnh chụp hay tin nhắn.

### Bước 3 — Chạy backend trong Terminal 1

```powershell
cd D:\AI-DS-Study\Lab\Day04_2A202601032_LeNguyenPhuocThanh

.\.venv\Scripts\python.exe -m uvicorn app.main:app `
  --app-dir backend `
  --host 127.0.0.1 `
  --port 8000
```

Lần chạy đầu nên bỏ `--reload` để dễ phát hiện lỗi startup. Khi thành công,
terminal sẽ hiện:

```text
Application startup complete.
Uvicorn running on http://127.0.0.1:8000
```

Giữ Terminal 1 đang chạy. Có thể kiểm tra API từ một terminal khác:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
```

Kết quả mong đợi:

```text
status        : ok
product_count : 100
```

### Bước 4 — Chạy frontend trong Terminal 2

Mở PowerShell mới:

```powershell
cd D:\AI-DS-Study\Lab\Day04_2A202601032_LeNguyenPhuocThanh\frontend

node --version
npm --version

# Chỉ cần cho terminal cũ chưa nhận Node trong PATH
$env:Path = "C:\Program Files\nodejs;$env:Path"

npm install
npm run dev
```

Mở [http://127.0.0.1:5173](http://127.0.0.1:5173).

Trong những lần chạy sau, nếu `node_modules` đã tồn tại thì chỉ cần:

```powershell
cd D:\AI-DS-Study\Lab\Day04_2A202601032_LeNguyenPhuocThanh\frontend
npm run dev
```

### Bước 5 — Sử dụng ứng dụng

1. Nhập câu hỏi ngay trong panel chat; không cần tạo hồ sơ trước.
2. Agent tra cứu trực tiếp nếu câu hỏi chỉ cần dữ liệu sản phẩm.
3. Nếu agent hiện form yêu cầu thêm ngữ cảnh, chỉ điền các mục được hỏi. Đây là
   LangGraph interrupt/resume, không phải lỗi.
4. Ngữ cảnh được lưu trong chính session và dùng lại cho các lượt sau.
5. Lượt đầu có thể lâu hơn vì OpenAI tạo embedding và Chroma index cho 100 sản
   phẩm.

Khi agent hỏi bổ sung ngữ cảnh trong CLI:

- Có thể nhập tuổi dạng số như `20`; CLI tự chuyển thành `adult`.
- Có thể nhập `không có` cho mục tiêu, bệnh nền, thuốc hoặc dị ứng.
- Có thể nhập `không có` cho thai/cho con bú; CLI chuyển thành `none`.
- Có thể nhập `loại nào cũng được` hoặc `không ưu tiên` cho dạng bào chế; CLI
  chuyển thành danh sách không ràng buộc.
- Ngân sách phải là số dương, ví dụ `500000` hoặc `500.000`.
- Nếu giá trị không hợp lệ, CLI giải thích và hỏi lại thay vì gửi request 422.

Nhấn `Ctrl+C` trong từng terminal để dừng backend hoặc frontend.

## Chat CLI

Backend phải đang chạy ở port 8000. Từ root:

```powershell
.\.venv\Scripts\python.exe .\version_1\chat.py `
  --api-url http://127.0.0.1:8000
```

CLI tạo session rỗng để bạn hỏi ngay, dùng session đó cho nhiều lượt và tự
merge context/resume khi graph yêu cầu thêm thông tin. Transcript chỉ lưu typed public events, không
lưu API key hoặc raw chain-of-thought.

## Eval

Backend phải đang chạy và `version_1/.env` phải có OpenAI key:

```powershell
.\.venv\Scripts\python.exe .\version_1\run_eval.py `
  --api-url http://127.0.0.1:8000 `
  --cases .\version_1\evals\version_1.json
```

Eval ghi từng run và summary vào `version_1/runs/`. Exit code khác 0 nếu:

- completion dưới 90%;
- tool routing dưới 80%;
- safety, grounding/provenance hoặc exact-name không đạt 100%;
- có run vượt 6 agent round hoặc 12 tool call.

## Các lỗi thường gặp

### `python`, `uvicorn` hoặc module không được nhận diện

Không dùng executable toàn cục. Chạy:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --port 8000
```

### `npm` hoặc `node` is not recognized

Mở PowerShell mới. Nếu vẫn lỗi:

```powershell
$env:Path = "C:\Program Files\nodejs;$env:Path"
node --version
npm --version
```

Node được cài tại `C:\Program Files\nodejs`.

### `provider_not_configured` hoặc `Thiếu OPENAI_API_KEY`

Key chưa nằm đúng file hoặc backend được chạy trước khi key được thêm:

1. Kiểm tra `version_1/.env`.
2. Đảm bảo dòng `OPENAI_API_KEY=` có giá trị.
3. Nhấn `Ctrl+C` ở Terminal 1.
4. Chạy lại backend.

### `FastAPI trả HTTP 422 khi bổ sung context`

Các enum canonical của API là:

- `age_group`: `infant`, `child`, `adolescent`, `adult`, `older_adult`;
- `pregnancy_status`: `not_applicable`, `none`, `pregnant`, `breastfeeding`,
  `prefer_not_to_say`.

CLI cũng chấp nhận tuổi dạng số và các cụm tiếng Việt được liệt kê ở phần sử dụng.

### Backend đứng ở `Waiting for application startup`

Nhấn `Ctrl+C`, chạy lại lệnh backend không có `--reload`, rồi kiểm tra:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
```

### `Address already in use` hoặc port đã được dùng

Kiểm tra tiến trình đang giữ port:

```powershell
Get-NetTCPConnection -LocalPort 8000 -State Listen |
    Select-Object LocalAddress, LocalPort, OwningProcess
```

Đóng terminal backend cũ bằng `Ctrl+C`, sau đó chạy lại. Frontend dùng port
5173 và có thể kiểm tra tương tự.

### Run đầu tiên chậm

Đây có thể là bước tạo embedding/index. Giữ backend chạy và chờ event
`retrieval.index.ready`. Những run sau sẽ tái sử dụng collection nếu dataset và
embedding model không thay đổi.

## Cấu trúc `version_1`

```text
version_1/
├── artifacts/      # prompt và tool declaration canonical
├── tools/          # 7 StructuredTool factories được backend sử dụng
├── evals/          # 5 single-turn và 5 multi-turn
├── samples/        # schema và output minh họa, không chứa secret
├── agent.py        # FastAPI/SSE client
├── chat.py         # CLI chat và interrupt/resume
└── run_eval.py     # live eval và acceptance metrics
```

Runtime state nằm trong `version_1/storage/`, `version_1/runs/` và
`version_1/transcripts/`; các thư mục này được gitignore.

## Tool set

1. `request_profile_fields`
2. `search_product_catalog`
3. `get_product_details`
4. `assess_product_safety`
5. `rank_product_fit`
6. `compare_products`
7. `submit_consultation`

`artifacts/tools.yaml`, manifest và registry phải có cùng đúng bảy tool theo thứ
tự trên. Backend fail sớm nếu tool contract bị lệch.

## Kiểm thử

Từ root:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -q

cd frontend
$env:Path = "C:\Program Files\nodejs;$env:Path"
npm test
npm run build
npm run e2e
```
