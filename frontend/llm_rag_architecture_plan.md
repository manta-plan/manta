# Fullstack RAG Architecture Plan: Software Docs & Energy Modeling Chat

This document details the architectural plan and code implementation for building a scalable, streaming Retrieval-Augmented Generation (RAG) fullstack LLM application.

## 1. System Architecture Overview

The system is designed to handle software documentation alongside complex domain-specific knowledge (such as energy modeling).

```mermaid
flowchart TB
    subgraph Sources["Knowledge Sources"]
        DOCS["Software Docs"]
        DOMAIN["Domain Data<br/>(Energy Modeling)"]
    end

    subgraph ETL["Ingestion Pipeline (Prefect)"]
        CHUNK["Semantic Chunking<br/>(heading / paragraph aware)"]
        EMBED_TASK["Embedding Task"]
    end

    subgraph Gemini["Google Gemini API"]
        EMB_MODEL["text-embedding-004<br/>768-dim vectors"]
        GEN_MODEL["gemini-2.5-flash<br/>streaming text"]
    end

    subgraph DB["PostgreSQL + pgvector"]
        T_DOCS[("documents")]
        T_CHUNKS[("document_chunks<br/>vector(768) + HNSW index")]
    end

    subgraph Backend["FastAPI Backend (ASGI async)"]
        RETRIEVE["get_relevant_chunks()<br/>cosine similarity search"]
        SSE["sse_event_generator()<br/>StreamingResponse"]
    end

    subgraph Frontend["React + Vite SPA"]
        HOOK["useChatStream hook<br/>fetch + ReadableStream"]
        UI["ChatApp component"]
    end

    DOCS --> CHUNK
    DOMAIN --> CHUNK
    CHUNK --> EMBED_TASK
    EMBED_TASK -->|contents| EMB_MODEL
    EMB_MODEL -->|768-dim vectors| EMBED_TASK
    EMBED_TASK --> T_DOCS
    EMBED_TASK --> T_CHUNKS

    UI -->|POST /api/chat| HOOK
    HOOK -->|query message| SSE
    SSE --> RETRIEVE
    RETRIEVE -->|query embedding| EMB_MODEL
    RETRIEVE -->|"ORDER BY embedding <=> $1"| T_CHUNKS
    T_CHUNKS -->|top-K chunks| RETRIEVE
    RETRIEVE -->|context| SSE
    SSE -->|system_instruction + query| GEN_MODEL
    GEN_MODEL -->|token stream| SSE
    SSE -->|"SSE: text/event-stream"| HOOK
    HOOK -->|incremental messages| UI
```

**Tech Stack Breakdown:**

- **Frontend:** React + Vite (SPA) with custom SSE stream hook.
- **Backend:** FastAPI (ASGI async event loop with `StreamingResponse`).
- **Database:** PostgreSQL with pgvector extension (HNSW index).
- **ETL & Data Pipeline:** Prefect flows for chunking, embedding, and syncing the knowledge base.
- **LLM & Embeddings:** Google Gemini API (`gemini-2.5-flash` for streaming text, `text-embedding-004` for 768-dim embeddings).

---

## 2. Database Schema (Postgres + pgvector)

Ensure PostgreSQL has the vector extension enabled.

```sql
-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Parent table for document sources
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(255) NOT NULL,
    category VARCHAR(100) NOT NULL, -- e.g., 'software_docs', 'energy_modeling'
    source_url TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Chunks and vector embeddings table
CREATE TABLE document_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    chunk_content TEXT NOT NULL,
    chunk_index INT NOT NULL,
    metadata JSONB, -- Stores section headers, page numbers, or tags
    embedding vector(768),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- HNSW Index for fast vector similarity queries (Cosine distance)
CREATE INDEX ON document_chunks
USING hnsw (embedding vector_cosine_ops);
```

---

## 3. Ingestion & Vector Pipeline (Prefect)

Prefect orchestrates document loading, semantic chunking, embedding generation, and database updates.

```python
# flows/ingest_docs.py
import asyncpg
from prefect import task, flow
from google import genai

ai_client = genai.Client()

@task
def generate_embeddings(texts: list[str]) -> list[list[float]]:
    """Generate 768-dimensional embeddings using Gemini text-embedding-004."""
    result = ai_client.models.embed_content(
        model="text-embedding-004",
        contents=texts
    )
    return [e.values for e in result.embeddings]

@task
def chunk_text(raw_text: str, chunk_size: int = 800, overlap: int = 100) -> list[str]:
    """Semantic chunking preserving paragraph/heading structures for domain context."""
    paragraphs = raw_text.split("\n\n")
    chunks, current = [], ""
    for p in paragraphs:
        if len(current) + len(p) <= chunk_size:
            current += p + "\n\n"
        else:
            chunks.append(current.strip())
            current = p + "\n\n"
    if current:
        chunks.append(current.strip())
    return chunks

@flow(name="Ingest Knowledge Base")
def sync_knowledge_base(doc_title: str, category: str, raw_content: str):
    chunks = chunk_text(raw_content)
    embeddings = generate_embeddings(chunks)
    # Database insertion logic into Postgres (documents & document_chunks)
    print(f"Processed {len(chunks)} chunks for '{doc_title}' ({category}).")

if __name__ == "__main__":
    pass
```

---

## 4. FastAPI Backend Endpoint (Retrieval + SSE Stream)

The FastAPI server receives chat queries, retrieves top-K vector matches, feeds them into Gemini's system instruction, and streams token-by-token responses back to the client using Server-Sent Events (`text/event-stream`).

```python
# app/main.py
import json
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from google import genai
import asyncpg

ai_client = genai.Client()

# Lifecycle state for database connection pool
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Setup PostgreSQL pool (configure your connection URI)
    app.state.db_pool = await asyncpg.create_pool("postgresql://user:password@localhost/dbname")
    yield
    await app.state.db_pool.close()

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatQuery(BaseModel):
    message: str
    category_filter: str | None = None  # Optional filter ('energy_modeling' | 'software_docs')

async def get_relevant_chunks(db_pool, query: str, top_k: int = 5) -> str:
    # 1. Generate query embedding
    emb_res = ai_client.models.embed_content(
        model="text-embedding-004",
        contents=query
    )
    query_vector = str(emb_res.embeddings[0].values)

    # 2. Perform cosine distance search (<->) in pgvector
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT chunk_content
            FROM document_chunks
            ORDER BY embedding <=> $1
            LIMIT $2
            """,
            query_vector, top_k
        )

    return "\n\n---\n\n".join([r["chunk_content"] for r in rows])

async def sse_event_generator(user_query: str, db_pool):
    try:
        # Retrieve context from vector store
        context = await get_relevant_chunks(db_pool, user_query)

        system_instruction = (
            "You are an expert assistant for software docs and energy modeling.\n"
            "Use the provided context to answer the user query accurately.\n\n"
            f"CONTEXT:\n{context}"
        )

        response = ai_client.models.generate_content_stream(
            model="gemini-2.5-flash",
            contents=user_query,
            config={"system_instruction": system_instruction}
        )

        for chunk in response:
            if chunk.text:
                payload = json.dumps({"text": chunk.text})
                yield f"data: {payload}\n\n"
                await asyncio.sleep(0)  # Relinquish control to ASGI event loop

        yield "data: [DONE]\n\n"

    except asyncio.CancelledError:
        print("Client disconnected mid-stream.")

@app.post("/api/chat")
async def chat_endpoint(query: ChatQuery):
    return StreamingResponse(
        sse_event_generator(query.message, app.state.db_pool),
        media_type="text/event-stream"
    )
```

### Request lifecycle

```mermaid
sequenceDiagram
    participant U as User
    participant H as useChatStream (SPA)
    participant F as FastAPI /api/chat
    participant G as Gemini API
    participant P as Postgres + pgvector

    U->>H: submit message
    H->>H: optimistic user + empty assistant message
    H->>F: POST /api/chat { message }
    F->>G: embed_content(text-embedding-004, query)
    G-->>F: 768-dim query vector
    F->>P: ORDER BY embedding <=> $1 LIMIT top_k
    P-->>F: top-K chunk_content
    F->>G: generate_content_stream(gemini-2.5-flash, query + context)
    loop token stream
        G-->>F: text chunk
        F-->>H: data: {"text": "..."}\n\n
        H->>U: append to assistant message
    end
    F-->>H: data: [DONE]\n\n
    H->>U: finalize, isGenerating = false
```

---

## 5. Frontend Integration (React + Vite SPA)

A lightweight custom hook consuming the FastAPI SSE stream line by line using standard `fetch` and `ReadableStream`.

```typescript
// src/useChatStream.ts
import { useState } from 'react';

export interface Message {
  role: 'user' | 'assistant';
  content: string;
}

export function useChatStream() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isGenerating, setIsGenerating] = useState<boolean>(false);

  const sendMessage = async (userMessage: string) => {
    if (!userMessage.trim()) return;

    setIsGenerating(true);

    // Optimistically update message state
    setMessages((prev) => [
      ...prev,
      { role: 'user', content: userMessage },
      { role: 'assistant', content: '' },
    ]);

    try {
      const response = await fetch('http://localhost:8000/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: userMessage }),
      });

      if (!response.body) throw new Error('No readable stream available.');

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let assistantMessage = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split('\n');

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const dataStr = line.slice(6).trim();
            if (dataStr === '[DONE]') break;

            try {
              const parsed = JSON.parse(dataStr);
              assistantMessage += parsed.text;

              setMessages((prev) => {
                const updated = [...prev];
                updated[updated.length - 1] = {
                  role: 'assistant',
                  content: assistantMessage,
                };
                return updated;
              });
            } catch {
              // Ignore incomplete JSON chunks across boundaries
            }
          }
        }
      }
    } catch (error) {
      console.error('Error streaming chat response:', error);
    } finally {
      setIsGenerating(false);
    }
  };

  return { messages, sendMessage, isGenerating };
}
```

**React Component Usage Example:**

```tsx
// src/App.tsx
import React, { useState } from 'react';
import { useChatStream } from './useChatStream';

export function ChatApp() {
  const [input, setInput] = useState('');
  const { messages, sendMessage, isGenerating } = useChatStream();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input || isGenerating) return;
    sendMessage(input);
    setInput('');
  };

  return (
    <div style={{ maxWidth: '800px', margin: '0 auto', padding: '2rem' }}>
      <h2>Software & Energy Modeling Assistant</h2>
      <div style={{ minHeight: '400px', border: '1px solid #ccc', padding: '1rem', marginBottom: '1rem' }}>
        {messages.map((m, idx) => (
          <div key={idx} style={{ margin: '1rem 0', textAlign: m.role === 'user' ? 'right' : 'left' }}>
            <strong>{m.role === 'user' ? 'You' : 'AI'}:</strong>
            <p style={{ whiteSpace: 'pre-wrap' }}>{m.content}</p>
          </div>
        ))}
      </div>
      <form onSubmit={handleSubmit} style={{ display: 'flex', gap: '0.5rem' }}>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about software features or energy modeling..."
          style={{ flex: 1, padding: '0.5rem' }}
        />
        <button type="submit" disabled={isGenerating}>
          {isGenerating ? 'Streaming...' : 'Send'}
        </button>
      </form>
    </div>
  );
}
```

---

## 6. Key Considerations for Domain Scaling

1. **Metadata Filtering:** Include domain tags (`category = 'energy_modeling'`) in metadata so queries can be constrained by scope.
2. **Chunking Strategy:** For technical energy modeling documents, use section-based chunking (h1, h2, h3 hierarchy boundaries) rather than strict token length to preserve complete formulas and variable definitions.
3. **Cancellation Handling:** Always handle `asyncio.CancelledError` in FastAPI so aborted requests immediately free up resources.
