#!/usr/bin/env python3
"""
Web UI for the Gravton analytics agent.

Usage:
    pip install fastapi "uvicorn[standard]"
    python ui_app.py
Then open http://localhost:8000
"""

import argparse, asyncio, datetime, decimal, json, os, sys, threading, uuid
from pathlib import Path
from typing import Optional

# Load .env without requiring python-dotenv
_env_file = Path(__file__).parent / ".env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

try:
    from fastapi import FastAPI, Request
    from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, Response
    import uvicorn
except ImportError:
    sys.exit("Web UI needs:  pip install fastapi 'uvicorn[standard]'")

sys.path.insert(0, str(Path(__file__).parent))
from script import Agent, DB, SKILLS_DIR, DEFAULT_MODEL, _run_web_search, _run_check_url

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app):
    global _agent
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY"):
        try:
            _agent = _make_agent({})
        except Exception:
            pass
    yield

app = FastAPI(title="Gravton Analytics Agent", lifespan=lifespan)
_agent: Optional[Agent] = None
_lock = threading.Lock()


class StreamingAgent(Agent):
    """Agent that emits structured events to a callback instead of printing."""

    def ask_streaming(self, question: str, emit):
        if self.provider == "openai":
            return self._ask_streaming_openai(question, emit)
        return self._ask_streaming_anthropic(question, emit)

    def _handle_tool_streaming(self, name: str, args: dict, emit, round_num: int) -> str:
        """Dispatch a tool call, emit events, and return the payload string."""
        if name == "load_skill":
            nm = (args.get("name") or "").strip()
            sk = self.skills.get(nm)
            if sk:
                if sk.get("visibility", "external") == "external":
                    emit({"type": "skill", "name": nm, "description": sk.get("description", "")})
                return sk["body"][:200000]
            return f"ERROR: no skill '{nm}'. Available: {', '.join(self.skills) or '(none)'}"
        if name == "web_search":
            q = args.get("query", ""); purpose = args.get("purpose", "")
            emit({"type": "web_search", "query": q, "purpose": purpose})
            payload = _run_web_search(q)
            try:
                data = json.loads(payload)
                emit({"type": "web_results", "results": data.get("results", []), "error": data.get("error")})
            except Exception:
                pass
            return payload
        if name == "check_url":
            url = args.get("url", ""); purpose = args.get("purpose", "")
            emit({"type": "check_url", "url": url, "purpose": purpose})
            payload = _run_check_url(url)
            try:
                data = json.loads(payload)
                emit({"type": "url_result", "url": url, "exists": data.get("exists", False),
                      "status": data.get("status"), "title": data.get("title", "")})
            except Exception:
                pass
            return payload
        if name == "run_investigation":
            if self.db is None:
                return "ERROR: knowledge-only mode; no database connected."
            plan = args.get("investigation_plan", "")
            reqs = args.get("information_requirements", [])
            emit({"type": "investigation_plan", "round": round_num + 1, "plan": plan,
                  "query_count": len(reqs)})
            batch = []
            for req in reqs:
                sql = req.get("sql", ""); purpose = req.get("purpose", "")
                emit({"type": "query", "purpose": purpose, "sql": sql})
                try:
                    cols, rows = self.db.query(sql)
                    emit({"type": "rows", "count": len(rows), "columns": cols, "preview": rows[:5]})
                    batch.append(self._summarize_result(cols, rows, purpose))
                except Exception as e:
                    emit({"type": "query_error", "message": str(e)})
                    batch.append({"purpose": purpose, "error": str(e), "sql_attempted": sql,
                                  "retry_hint": "This query failed. Fix the SQL error and retry it in the next run_investigation call."})
            return json.dumps(batch, default=str)[:24000]
        return f"ERROR: unknown tool '{name}'"

    def _ask_streaming_anthropic(self, question: str, emit):
        self._maybe_compress_history()
        self.messages.append({"role": "user", "content": question})
        chat_input = 0; chat_output = 0; chat_cache_read = 0; chat_cache_write = 0

        for round_num in range(self.max_steps):
            use_thinking = (round_num == 0 and not self.docs_only
                            and self.model in ("claude-sonnet-4-6", "claude-opus-4-8"))
            kwargs = dict(model=self.model,
                          max_tokens=6000 if use_thinking else 8192,
                          system=self.system_prompt,
                          tools=self.tools,
                          messages=self.messages)
            if use_thinking:
                kwargs["thinking"] = {"type": "enabled", "budget_tokens": 2000}
                emit({"type": "thinking_start", "round": round_num + 1})

            # Use streaming to keep the HTTP connection alive and prevent timeout on
            # long responses (mirrors script.py's stream approach).
            with self.client.messages.stream(**kwargs) as stream:
                for _ in stream.text_stream:
                    pass  # drain — keeps connection alive without buffering all at once
                resp = stream.get_final_message()
            chat_input += resp.usage.input_tokens
            chat_output += resp.usage.output_tokens
            chat_cache_read += getattr(resp.usage, "cache_read_input_tokens", 0) or 0
            chat_cache_write += getattr(resp.usage, "cache_creation_input_tokens", 0) or 0
            self.messages.append({"role": "assistant", "content": resp.content})

            if resp.stop_reason != "tool_use":
                answer = "".join(b.text for b in resp.content if b.type == "text").strip()
                emit({"type": "answer", "text": answer,
                      "usage": {"input": chat_input, "output": chat_output,
                                "cache_read": chat_cache_read, "cache_write": chat_cache_write}})
                return answer

            # Emit pre-tool reasoning text only when extended thinking is OFF.
            # When thinking is ON the model's verbose planning text is redundant —
            # the structured investigation_plan shown below is cleaner.
            if not use_thinking:
                for b in resp.content:
                    if b.type == "text" and b.text.strip():
                        emit({"type": "thought", "text": b.text.strip()})

            results = []
            for tu in (b for b in resp.content if b.type == "tool_use"):
                payload = self._handle_tool_streaming(tu.name, tu.input, emit, round_num)
                results.append({"type": "tool_result", "tool_use_id": tu.id, "content": payload})
            self.messages.append({"role": "user", "content": results})

        emit({"type": "answer", "text": "(Stopped: hit the max investigation-round limit.)"})

    def _ask_streaming_openai(self, question: str, emit):
        self._maybe_compress_history()
        self.messages.append({"role": "user", "content": question})
        chat_input = 0; chat_output = 0
        tools_param = self.openai_tools if self.openai_tools else None

        for round_num in range(self.max_steps):
            all_messages = [{"role": "system", "content": self.system_text}] + self.messages

            full_text = ""
            tool_calls_acc = {}  # index -> {id, name, arguments}
            finish_reason = "stop"

            # Stream to keep connection alive; accumulate tool call deltas
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=all_messages,
                tools=tools_param,
                stream=True,
                stream_options={"include_usage": True},
                max_completion_tokens=8192,
            )
            for chunk in stream:
                if chunk.usage:
                    chat_input += chunk.usage.prompt_tokens or 0
                    chat_output += chunk.usage.completion_tokens or 0
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                if choice.finish_reason:
                    finish_reason = choice.finish_reason
                delta = choice.delta
                if delta.content:
                    full_text += delta.content
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        i = tc.index
                        if i not in tool_calls_acc:
                            tool_calls_acc[i] = {"id": "", "name": "", "arguments": ""}
                        if tc.id:
                            tool_calls_acc[i]["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                tool_calls_acc[i]["name"] += tc.function.name
                            if tc.function.arguments:
                                tool_calls_acc[i]["arguments"] += tc.function.arguments

            tool_calls_list = [tool_calls_acc[i] for i in sorted(tool_calls_acc)]
            assistant_msg = {"role": "assistant", "content": full_text or None}
            if tool_calls_list:
                assistant_msg["tool_calls"] = [
                    {"id": tc["id"], "type": "function",
                     "function": {"name": tc["name"], "arguments": tc["arguments"]}}
                    for tc in tool_calls_list
                ]
            self.messages.append(assistant_msg)

            if finish_reason != "tool_calls":
                emit({"type": "answer", "text": full_text.strip(),
                      "usage": {"input": chat_input, "output": chat_output,
                                "cache_read": 0, "cache_write": 0}})
                return full_text.strip()

            # Emit pre-tool reasoning text if any
            if full_text.strip():
                emit({"type": "thought", "text": full_text.strip()})

            for tc in tool_calls_list:
                try: args = json.loads(tc["arguments"])
                except Exception: args = {}
                payload = self._handle_tool_streaming(tc["name"], args, emit, round_num)
                self.messages.append({"role": "tool", "tool_call_id": tc["id"], "content": payload})

        emit({"type": "answer", "text": "(Stopped: hit the max investigation-round limit.)"})


def _make_agent(config: dict) -> StreamingAgent:
    docs_only = config.get("docs_only", False)
    dsn = config.get("pg_dsn") or os.environ.get("DATABASE_URL") or os.environ.get("GRAVTON_PG_DSN")
    model = config.get("model", DEFAULT_MODEL)
    max_steps = int(config.get("max_steps", 8))
    org_id = int(config["org_id"]) if config.get("org_id") else None
    domain_id = int(config["domain_id"]) if config.get("domain_id") else None
    skills_dir = str(config.get("skills_dir") or SKILLS_DIR)

    if docs_only or not dsn:
        return StreamingAgent(None, model=model, max_steps=max_steps, skills_dir=skills_dir)
    db = DB.postgres(dsn)
    return StreamingAgent(db, model=model, max_steps=max_steps,
                          org_id=org_id, domain_id=domain_id, skills_dir=skills_dir)



@app.get("/")
async def index():
    return HTMLResponse((Path(__file__).parent / "static" / "index.html").read_text())


@app.get("/api/env-hints")
async def env_hints():
    return {
        "has_api_key": bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY")),
        "has_anthropic_key": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "has_openai_key": bool(os.environ.get("OPENAI_API_KEY")),
        "has_db": bool(os.environ.get("DATABASE_URL") or os.environ.get("GRAVTON_PG_DSN")),
        "db_var": ("DATABASE_URL" if os.environ.get("DATABASE_URL")
                   else ("GRAVTON_PG_DSN" if os.environ.get("GRAVTON_PG_DSN") else None)),
    }


@app.get("/api/status")
async def get_status():
    if not _agent:
        return {"configured": False}
    turns = sum(1 for m in _agent.messages
                if m.get("role") == "user" and isinstance(m.get("content"), str))
    external_skills = [n for n, s in _agent.skills.items() if s.get("visibility", "external") == "external"]
    return {
        "configured": True,
        "mode": "docs-only" if _agent.docs_only else "database",
        "org": _agent.org or "(knowledge-only)",
        "brand": _agent.brand or "",
        "domain": getattr(_agent, "domain", "") or "",
        "model": _agent.model,
        "skills": external_skills,
        "turns": turns,
    }


@app.post("/api/configure")
async def configure(req: Request):
    global _agent
    try:
        data = await req.json()
        with _lock:
            agent = _make_agent(data)
            _agent = agent
        mode = "docs-only" if agent.docs_only else "database"
        external_skills = [n for n, s in agent.skills.items() if s.get("visibility", "external") == "external"]
        return {
            "status": "ok", "mode": mode,
            "org": agent.org or "(knowledge-only)",
            "brand": agent.brand or "",
            "domain": getattr(agent, "domain", "") or "",
            "skills": external_skills,
            "model": agent.model,
        }
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@app.post("/api/reset")
async def reset():
    if _agent:
        _agent.reset()
    return {"status": "ok"}


def _serial(o):
    if isinstance(o, decimal.Decimal):
        return float(o)
    if isinstance(o, (datetime.datetime, datetime.date)):
        return o.isoformat()
    if isinstance(o, uuid.UUID):
        return str(o)
    return str(o)


@app.post("/api/run-query")
async def run_query_direct(req: Request):
    """Execute a single read-only SQL query and return columns + rows. Used by the UI's 'Edit & Run' feature."""
    data = await req.json()
    sql = (data.get("sql") or "").strip()
    if not sql:
        return JSONResponse({"error": "Empty query"}, status_code=400)
    if not _agent or _agent.db is None:
        return JSONResponse({"error": "No database connected"}, status_code=400)
    try:
        cols, rows = _agent.db.query(sql)
        payload = json.dumps({"columns": cols, "rows": rows[:50], "count": len(rows)}, default=_serial)
        return Response(content=payload, media_type="application/json")
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.post("/api/chat")
async def chat(req: Request):
    data = await req.json()
    question = (data.get("message") or "").strip()
    if not question:
        return JSONResponse({"error": "Empty message"}, status_code=400)
    if not _agent:
        return JSONResponse({"error": "Agent not configured. Fill in the connection settings first."}, status_code=400)

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def run():
        try:
            _agent.ask_streaming(question, lambda ev: loop.call_soon_threadsafe(queue.put_nowait, ev))
        except Exception as e:
            loop.call_soon_threadsafe(queue.put_nowait, {"type": "error", "message": str(e)})
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, {"type": "done"})

    threading.Thread(target=run, daemon=True).start()

    async def stream():
        while True:
            event = await queue.get()
            yield f"data: {json.dumps(event, default=_serial)}\n\n"
            if event["type"] in ("done", "error"):
                break

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Gravton Analytics Agent — Web UI")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--reload", action="store_true")
    a = ap.parse_args()
    print(f"\n  Gravton Analytics Agent UI  →  http://localhost:{a.port}\n")
    uvicorn.run("ui_app:app", host=a.host, port=a.port, reload=a.reload)
