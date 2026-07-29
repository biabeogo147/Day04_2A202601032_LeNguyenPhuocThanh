# Version 1 Tool Setup

## Provider

Sao chép `.env.example` thành `.env` trong chính thư mục `version_1/`. Backend
chỉ đọc file này.

OpenAI mặc định:

```dotenv
OPENAI_API_KEY=<your-key>
OPENAI_CHAT_MODEL=gpt-4o-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
```

Gemini là tùy chọn và live test tự skip khi chưa có `GEMINI_API_KEY`.

Node.js LTS đã được cài tại `C:\Program Files\nodejs`. Mở terminal mới để nhận
PATH; với terminal cũ:

```powershell
$env:Path = "C:\Program Files\nodejs;$env:Path"
node --version
npm --version
```

## Tool registry

Bảy package trong `version_1/tools/` là registry runtime thật. Mỗi package gồm
`TOOL.md` và `tool.py`; declaration gửi cho model được khóa tại
`artifacts/tools.yaml`.

Không commit `.env`, `storage/`, `runs/` hoặc `transcripts/`.

## Ports và dữ liệu

- FastAPI: `8000`
- Vite: `5173`
- Dataset: `../shared_data/DataTPCN.csv`
- SQLite/Chroma/checkpoint: `storage/`

Tool không web search và không sử dụng bằng chứng ngoài dataset. Safety conflict
là gate riêng; trường hợp thiếu bằng chứng phải yêu cầu bác sĩ/dược sĩ.
