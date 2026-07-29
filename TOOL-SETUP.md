# Local setup notes

Ứng dụng mới chỉ dùng OpenAI và Gemini. Không dùng provider, tool hoặc `.env`
trong `starter_v0/`.

## Provider

OpenAI là mặc định:

```dotenv
LLM_PROVIDER=openai
OPENAI_API_KEY=
OPENAI_CHAT_MODEL=gpt-4o-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
```

Gemini đã có adapter nhưng optional:

```dotenv
GEMINI_API_KEY=
GEMINI_CHAT_MODEL=gemini-2.5-flash
GEMINI_EMBEDDING_MODEL=gemini-embedding-001
```

Không commit `.env`, SQLite database, Chroma index, log có dữ liệu người dùng
hoặc screenshot chứa key.

## Node trên máy hiện tại

Node.js LTS được cài bằng Windows Package Manager tại:

```text
C:\Program Files\nodejs
```

Phiên terminal mới sẽ nhận PATH. Nếu terminal cũ chưa nhận, chạy tạm:

```powershell
$env:Path = "C:\Program Files\nodejs;$env:Path"
node --version
npm --version
```

## Ports

- FastAPI: `8000`
- Vite: `5173`

Vite proxy `/api` sang `http://127.0.0.1:8000`; FastAPI cũng chỉ cho phép CORS
từ hai origin localhost của Vite.
