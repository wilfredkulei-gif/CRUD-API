import sqlite3
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# Database file lives next to main.py and is created automatically on first run
DB_PATH = Path(__file__).parent / "tasks.db"

SEED_TASKS = [
    ("Study Python", 0),
    ("Buy Milk", 1),
    ("Exercise", 0),
]


# ---------- Data layer ----------
@contextmanager
def get_db():
    """Open a connection, commit on success, always close."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    """Create the table if missing and seed 3 tasks only when it is empty."""
    with get_db() as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id    INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                done  BOOLEAN NOT NULL DEFAULT 0
            )
            """
        )
        count = db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        if count == 0:
            db.executemany("INSERT INTO tasks (title, done) VALUES (?, ?)", SEED_TASKS)


def row_to_task(row: sqlite3.Row) -> dict:
    return {"id": row["id"], "title": row["title"], "done": bool(row["done"])}


# ---------- API layer ----------
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(lifespan=lifespan)


class TaskCreate(BaseModel):
    title: str


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    done: Optional[bool] = None


def not_found():
    return JSONResponse(status_code=404, content={"error": "Task not found"})


def bad_request(message: str):
    return JSONResponse(status_code=400, content={"error": message})


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    # Assignment requires 400 (not FastAPI's default 422) for invalid requests
    return bad_request("Invalid request: a valid 'title' (text) is required")


@app.get("/")
def home():
    return {
        "name": "Task API",
        "version": "2.0",
        "endpoints": ["/tasks", "/tasks/{id}", "/stats", "/health"],
    }

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/tasks")
def get_tasks(
    search: Optional[str] = None,
    done: Optional[bool] = None,
    sort: Optional[str] = None,
):
    query = "SELECT id, title, done FROM tasks"
    clauses, params = [], []

    if search:  # GET /tasks?search=milk
        clauses.append("title LIKE ?")
        params.append(f"%{search}%")
    if done is not None:  # GET /tasks?done=true
        clauses.append("done = ?")
        params.append(1 if done else 0)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)

    # GET /tasks?sort=title -> alphabetical, otherwise by id
    query += " ORDER BY title COLLATE NOCASE" if sort == "title" else " ORDER BY id"

    with get_db() as db:
        rows = db.execute(query, params).fetchall()
    return [row_to_task(r) for r in rows]


@app.get("/stats")
def stats():
    with get_db() as db:
        row = db.execute(
            """
            SELECT COUNT(*) AS total,
                   COALESCE(SUM(done), 0) AS completed
            FROM tasks
            """
        ).fetchone()
    return {
        "total": row["total"],
        "completed": row["completed"],
        "pending": row["total"] - row["completed"],
    }


@app.get("/tasks/{task_id}")
def get_task(task_id: int):
    with get_db() as db:
        row = db.execute(
            "SELECT id, title, done FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
    if row is None:
        return not_found()
    return row_to_task(row)


@app.post("/tasks", status_code=201)
def create_task(task: TaskCreate):
    title = task.title.strip()
    if not title:
        return bad_request("Title cannot be empty")

    with get_db() as db:
        cur = db.execute("INSERT INTO tasks (title, done) VALUES (?, 0)", (title,))
        new_id = cur.lastrowid
    return {"id": new_id, "title": title, "done": False}


@app.put("/tasks/{task_id}")
def update_task(task_id: int, update: TaskUpdate):
    if update.title is None and update.done is None:
        return bad_request("Provide 'title' and/or 'done' to update")
    if update.title is not None and not update.title.strip():
        return bad_request("Title cannot be empty")

    with get_db() as db:
        row = db.execute(
            "SELECT id, title, done FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if row is None:
            return not_found()

        new_title = update.title.strip() if update.title is not None else row["title"]
        new_done = int(update.done) if update.done is not None else row["done"]

        db.execute(
            "UPDATE tasks SET title = ?, done = ? WHERE id = ?",
            (new_title, new_done, task_id),
        )
    return {"id": task_id, "title": new_title, "done": bool(new_done)}


@app.delete("/tasks/{task_id}")
def delete_task(task_id: int):
    with get_db() as db:
        cur = db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        if cur.rowcount == 0:
            return not_found()
    return {"message": f"Task {task_id} deleted"}
