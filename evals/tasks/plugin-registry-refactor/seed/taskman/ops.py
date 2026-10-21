"""Business operations on a Store. Every mutating operation saves the store."""
from .clock import today
from .errors import ConflictError
from .models import PRIORITIES, PRIORITY_RANK, Task


def add_task(store, title, priority="normal", tags=(), due=None):
    task = Task(id=0, title=title, priority=priority, tags=list(tags), due=due, created=today().isoformat())
    store.insert(task)
    store.save()
    return task


def complete(store, task_id):
    task = store.get(task_id)
    if task.done:
        raise ConflictError(f"task #{task_id} is already done")
    task.done = True
    store.save()
    return task


def reopen(store, task_id):
    task = store.get(task_id)
    if not task.done:
        raise ConflictError(f"task #{task_id} is not done")
    task.done = False
    store.save()
    return task


def delete(store, task_id):
    task = store.remove(task_id)
    store.save()
    return task


def rename(store, task_id, title):
    task = store.get(task_id)
    old = task.title
    task.title = title
    store.save()
    return old, task


def add_tags(store, task_id, tags):
    task = store.get(task_id)
    for t in tags:
        if t not in task.tags:
            task.tags.append(t)
    store.save()
    return task


def remove_tags(store, task_id, tags):
    task = store.get(task_id)
    task.tags = [t for t in task.tags if t not in tags]
    store.save()
    return task


def set_priority(store, task_id, priority):
    task = store.get(task_id)
    task.priority = priority
    store.save()
    return task


def set_due(store, task_id, due):
    task = store.get(task_id)
    if task.done and due is not None:
        raise ConflictError(f"task #{task_id} is already done")
    task.due = due
    store.save()
    return task


def list_tasks(store, include_done=False, tag=None, sort="id"):
    tasks = [t for t in store.all() if include_done or not t.done]
    if tag is not None:
        tasks = [t for t in tasks if tag in t.tags]
    if sort == "pri":
        tasks.sort(key=lambda t: (-PRIORITY_RANK[t.priority], t.id))
    elif sort == "due":
        tasks.sort(key=lambda t: (t.due is None, t.due or "", t.id))
    return tasks


def search(store, query):
    q = query.lower()
    if q.startswith("#"):
        return [t for t in store.all() if q[1:] in t.tags]
    return [t for t in store.all() if q in t.title.lower() or any(q in tag for tag in t.tags)]


def stats(store):
    iso = today().isoformat()
    tasks = store.all()
    open_tasks = [t for t in tasks if not t.done]
    return {
        "total": len(tasks),
        "open": len(open_tasks),
        "done": len(tasks) - len(open_tasks),
        "overdue": sum(1 for t in open_tasks if t.due and t.due < iso),
        "by_priority": {p: sum(1 for t in open_tasks if t.priority == p) for p in PRIORITIES},
    }


def purge(store, dry_run=False):
    victims = [t for t in store.all() if t.done]
    if not dry_run:
        for t in victims:
            store.remove(t.id)
        if victims:
            store.save()
    return victims
