# Version 1 Tool Setup

Tài liệu này tập trung vào cài môi trường và chẩn đoán startup. Quy trình chạy
app đầy đủ nằm trong `version_1/README.md`.

## 1. Python

Khuyến nghị Python 3.11. Từ root repository:

```powershell
cd D:\AI-DS-Study\Lab\Day04_2A202601032_LeNguyenPhuocThanh

# Chỉ tạo khi chưa có .venv
py -3.11 -m venv .venv

.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Luôn ưu tiên `.\.venv\Scripts\python.exe`. Lệnh `python` toàn cục trên máy có
thể trỏ sang Python của Laragon và thiếu FastAPI, LangGraph hoặc SQLAlchemy
đúng phiên bản.

Kiểm tra:

```powershell
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m pip --version
.\.venv\Scripts\python.exe -m pip check
```

Không bắt buộc activate virtual environment. Nếu muốn activate nhưng
PowerShell chặn script:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1
```

Thay đổi này chỉ áp dụng cho terminal hiện tại.

## 2. Node.js và npm

Node.js được cài tại:

```text
C:\Program Files\nodejs
```

Mở PowerShell mới và kiểm tra:

```powershell
node --version
npm --version
```

Nếu terminal hiện tại chưa nhận Node:

```powershell
$env:Path = "C:\Program Files\nodejs;$env:Path"
node --version
npm --version
```

Cài dependency frontend:

```powershell
cd D:\AI-DS-Study\Lab\Day04_2A202601032_LeNguyenPhuocThanh\frontend
$env:Path = "C:\Program Files\nodejs;$env:Path"
npm install
```

`npm install` chỉ cần chạy lại khi `package.json` hoặc lockfile thay đổi.

## 3. Provider và `.env`

Backend chỉ đọc:

```text
version_1/.env
```

Không đọc `.env` ở root hoặc cấu hình trong `starter_v0`.

Tạo file nếu chưa tồn tại:

```powershell
cd D:\AI-DS-Study\Lab\Day04_2A202601032_LeNguyenPhuocThanh

if (-not (Test-Path .\version_1\.env)) {
    Copy-Item .\version_1\.env.example .\version_1\.env
}

notepad .\version_1\.env
```

Cấu hình OpenAI:

```dotenv
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-your-real-key
OPENAI_CHAT_MODEL=gpt-4o-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
```

Không dùng dấu `< >`, không thêm `export`, và không commit `.env`.

Kiểm tra key đã được điền mà không in giá trị:

```powershell
$configured = @(
    Get-Content .\version_1\.env |
        Where-Object { $_ -match '^OPENAI_API_KEY=\S+' }
).Count -gt 0

Write-Output "OPENAI_API_KEY configured: $configured"
```

Kết quả phải là:

```text
OPENAI_API_KEY configured: True
```

Sau mọi thay đổi trong `.env`, phải restart backend. Uvicorn không đảm bảo tự
reload khi chỉ có `.env` thay đổi.

Gemini là tùy chọn:

```dotenv
GEMINI_API_KEY=
GEMINI_CHAT_MODEL=gemini-2.5-flash
GEMINI_EMBEDDING_MODEL=gemini-embedding-001
```

Gemini live test tự skip khi chưa có `GEMINI_API_KEY`.

## 4. Backend smoke test

Terminal 1:

```powershell
cd D:\AI-DS-Study\Lab\Day04_2A202601032_LeNguyenPhuocThanh

.\.venv\Scripts\python.exe -m uvicorn app.main:app `
  --app-dir backend `
  --host 127.0.0.1 `
  --port 8000
```

Lần startup đầu tiên không dùng `--reload`.

Terminal khác:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
Invoke-RestMethod http://127.0.0.1:8000/api/v1/versions
```

Health phải báo `status=ok` và `product_count=100`. Health thành công chỉ chứng
minh API và dataset đã sẵn sàng; OpenAI key được sử dụng khi bắt đầu một agent
run.

## 5. Frontend smoke test

Backend phải đang chạy ở port 8000.

```powershell
cd D:\AI-DS-Study\Lab\Day04_2A202601032_LeNguyenPhuocThanh\frontend
$env:Path = "C:\Program Files\nodejs;$env:Path"
npm run dev
```

Mở [http://127.0.0.1:5173](http://127.0.0.1:5173). Vite proxy các request
`/api/*` sang `http://127.0.0.1:8000`.

## 6. Runtime paths

- FastAPI: `http://127.0.0.1:8000`
- Vite: `http://127.0.0.1:5173`
- Eval Lab: `http://127.0.0.1:5173/eval`
- Dataset: `shared_data/DataTPCN.csv`
- SQLite: `version_1/storage/app.db`
- Checkpoint: `version_1/storage/checkpoints.db`
- Chroma: `version_1/storage/chroma/`
- Eval output: `version_1/runs/`
- Transcript: `version_1/transcripts/`

`storage/`, `runs/`, `transcripts/` và `.env` là runtime state, không được
commit.

### Eval Lab preflight

Trước khi chạy live eval, kiểm tra backend và browser theo thứ tự:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
Invoke-WebRequest http://127.0.0.1:5173/eval -UseBasicParsing |
    Select-Object StatusCode
```

Health phải có `status=ok`, `product_count=100`; trang eval phải trả HTTP 200. Trên
`/eval`, chọn concurrency 1–5 (mặc định 3). Mỗi case có session độc lập, không dùng
profile legacy. Eval không tự retry lỗi OpenAI/timeout/429. Sau khi có baseline, dùng
**Chạy lại case lỗi** và thêm năm smoke case thay vì chạy lại toàn bộ 30 case.

Nếu SSE bị ngắt, frontend chỉ reconnect/replay từ event ID cuối cùng; thao tác này không
tạo model run mới. Một worker lỗi không dừng các worker khác.

## 7. Chẩn đoán lỗi

### `ModuleNotFoundError: fastapi`, `langchain_core` hoặc `pydantic_settings`

Bạn đang dùng sai Python hoặc chưa cài project:

```powershell
cd D:\AI-DS-Study\Lab\Day04_2A202601032_LeNguyenPhuocThanh
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pip check
```

Sau đó chạy backend bằng chính `.venv\Scripts\python.exe`.

### `npm` hoặc `node` is not recognized

```powershell
$env:Path = "C:\Program Files\nodejs;$env:Path"
node --version
npm --version
```

Nếu lệnh trên hoạt động, hãy đóng và mở PowerShell mới để nhận User PATH.

### `provider_not_configured`

Nguyên nhân thường gặp:

- `OPENAI_API_KEY` còn trống;
- key được đặt trong nhầm `.env`;
- backend đã chạy trước khi key được thêm.

Cách xử lý:

1. Điền `version_1/.env`.
2. Dừng backend bằng `Ctrl+C`.
3. Chạy lại backend.
4. Gửi một agent run mới.

### `FastAPI trả HTTP 422 khi bổ sung context`

CLI chấp nhận:

- tuổi dạng số, ví dụ `20`;
- `không có` cho danh sách trống và trạng thái không mang thai;
- `loại nào cũng được` hoặc `không ưu tiên` cho dạng bào chế;
- ngân sách dạng `500000` hoặc `500.000`.

Giá trị không hợp lệ sẽ được hỏi lại tại CLI. Nếu gọi API trực tiếp, phải dùng
enum canonical được khai báo trong OpenAPI schema.

### `401`, `invalid_api_key`

Key không hợp lệ hoặc bị thừa dấu cách/dấu `< >`. Sửa `version_1/.env`, lưu file
và restart backend. Không gửi key khi yêu cầu hỗ trợ.

### `429`, `insufficient_quota`

Key đã được nhận nhưng OpenAI project không còn quota hoặc chưa cấu hình
billing. Kiểm tra quota/billing của OpenAI project; đây không phải lỗi
frontend.

### `Waiting for application startup`

1. Chờ vài giây để Alembic hoàn tất.
2. Nếu vẫn đứng, nhấn `Ctrl+C`.
3. Chạy lại không có `--reload`.
4. Kiểm tra port 8000 và health endpoint.

### `Address already in use`

```powershell
Get-NetTCPConnection -LocalPort 8000 -State Listen |
    Select-Object LocalAddress, LocalPort, OwningProcess
```

Đóng terminal backend cũ bằng `Ctrl+C`. Frontend dùng port 5173.

### UI mở được nhưng request API thất bại

Kiểm tra theo thứ tự:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
Invoke-RestMethod http://127.0.0.1:8000/api/v1/sessions
```

Nếu các lệnh này thất bại, xử lý backend trước. Nếu chúng thành công, restart
Vite và mở lại `http://127.0.0.1:5173`.

### Agent yêu cầu bổ sung ngữ cảnh

Đây là hành vi mong đợi của tool `request_profile_fields`. UI/CLI sẽ merge dữ
liệu vào `sessions.context` và resume đúng run/checkpoint; không tạo session mới. Tool luôn phát tên
field canonical, còn CLI chịu trách nhiệm chuyển nhãn/giá trị tiếng Việt về
schema API.

### Run đầu chậm

OpenAI có thể đang embedding 100 sản phẩm để tạo Chroma collection. Khi index
đã có và fingerprint/model không đổi, các run sau tái sử dụng index.

## 8. Tool registry

Bảy package trong `version_1/tools/` là registry runtime thật:

1. `request_profile_fields`
2. `search_product_catalog`
3. `get_product_details`
4. `assess_product_safety`
5. `rank_product_fit`
6. `compare_products`
7. `submit_consultation`

Mỗi package gồm `TOOL.md` và `tool.py`. Declaration gửi cho model được khóa tại
`version_1/artifacts/tools.yaml`. Backend fail sớm nếu registry, manifest và
YAML không có cùng tool theo đúng thứ tự.
