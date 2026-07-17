from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

# Blueprint for a new task
class Task(BaseModel):
    title: str

# In-memory database
tasks = [
    {
        "id": 1,
        "title": "Study Python",
        "done": False
    },
    {
        "id": 2,
        "title": "Buy Milk",
        "done": True
    },
    {
        "id": 3,
        "title": "Exercise",
        "done": False
    }
]

@app.get("/")
def home():
    return {
        "name": "Task API",
        "version": "1.0",
        "endpoints": ["/tasks"]
    }

@app.get("/health")
def health():
    return {
        "status": "ok"
    }

@app.get("/tasks")
def get_tasks():
    return tasks

@app.get("/tasks/{task_id}")
def get_task(task_id: int):

    for task in tasks:
        if task["id"] == task_id:
            return task

    return {
        "error": f"Task {task_id} not found"
    }

@app.post("/tasks")
def create_task(task: Task):

    new_task = {
        "id": len(tasks) + 1,
        "title": task.title,
        "done": False
    }

    tasks.append(new_task)

    return new_task