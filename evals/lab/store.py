"""The lab's history in one SQLite file: runs, their rounds (the brief, then each follow-up), sessions, what each
session produced in each round, blind votes and judge scores. API keys are never stored."""

import json
from pathlib import Path
import sqlite3
import statistics
import threading
import time

SCHEMA = """
create table if not exists runs (
    id text primary key, created real, prompt text, provider text, model text, spec text, status text);
create table if not exists run_rounds (
    run_id text, round integer, prompt text, created real, primary key (run_id, round));
create table if not exists sessions (
    id text primary key, run_id text, arm text, repeat integer, status text);
create table if not exists generations (
    session_id text, round integer, status text, metrics text, error text, preview text, preview_note text,
    final text, files text, changed text, started real, finished real, primary key (session_id, round));
create table if not exists votes (
    run_id text, round integer, repeat integer, winner text, created real, primary key (run_id, round, repeat));
create table if not exists judgments (
    session_id text, round integer, judge text, scores text, mean real, notes text, error text, created real,
    primary key (session_id, round, judge));
"""
JSON_FIELDS = {"spec", "metrics", "files", "changed", "scores"}
LIVE = ("queued", "running")


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        with self.connect() as db:
            db.executescript(SCHEMA)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        return db

    def execute(self, sql, values=()):
        with self.lock, self.connect() as db:
            db.execute(sql, values)

    def rows(self, sql, values=()):
        with self.lock, self.connect() as db:
            found = [dict(row) for row in db.execute(sql, values)]
        for row in found:
            for key in JSON_FIELDS & row.keys():
                row[key] = json.loads(row[key]) if row[key] else None
        return found

    # --- writes --------------------------------------------------------------------------------------------------

    def add_run(self, run_id, spec):
        now = time.time()
        self.execute("insert into runs values (?, ?, ?, ?, ?, ?, ?)",
                     (run_id, now, spec["prompt"], spec["provider"], spec["model"], json.dumps(spec), "running"))
        self.add_round(run_id, 1, spec["prompt"])

    def add_round(self, run_id, number, prompt):
        self.execute("insert into run_rounds values (?, ?, ?, ?)", (run_id, number, prompt, time.time()))

    def add_session(self, session_id, run_id, arm, repeat):
        self.execute("insert into sessions values (?, ?, ?, ?, 'queued')", (session_id, run_id, arm, repeat))

    def set_session_status(self, session_id, status):
        self.execute("update sessions set status = ? where id = ?", (status, session_id))

    def save_generation(self, session_id, number, **fields):
        """Insert or update what a session did in one round."""
        fields = {key: json.dumps(value) if key in JSON_FIELDS else value for key, value in fields.items()}
        with self.lock, self.connect() as db:
            db.execute("insert or ignore into generations (session_id, round, status) values (?, ?, 'queued')",
                       (session_id, number))
            if fields:
                assignments = ", ".join(f"{key} = ?" for key in fields)
                db.execute(f"update generations set {assignments} where session_id = ? and round = ?",
                           (*fields.values(), session_id, number))

    def set_run_status(self, run_id, status):
        self.execute("update runs set status = ? where id = ?", (status, run_id))

    def vote(self, run_id, number, repeat, winner):
        self.execute("insert or replace into votes values (?, ?, ?, ?, ?)",
                     (run_id, number, repeat, winner, time.time()))

    def judgment(self, session_id, number, judge, result):
        self.execute("insert or replace into judgments values (?, ?, ?, ?, ?, ?, ?, ?)",
                     (session_id, number, judge, json.dumps(result.get("scores")), result.get("mean"),
                      result.get("notes", ""), result.get("error", ""), time.time()))

    def delete_run(self, run_id):
        with self.lock, self.connect() as db:
            sessions = [(row[0],) for row in db.execute("select id from sessions where run_id = ?", (run_id,))]
            db.executemany("delete from judgments where session_id = ?", sessions)
            db.executemany("delete from generations where session_id = ?", sessions)
            for table in ("sessions", "votes", "run_rounds"):
                db.execute(f"delete from {table} where run_id = ?", (run_id,))
            db.execute("delete from runs where id = ?", (run_id,))

    # --- reads ---------------------------------------------------------------------------------------------------

    def runs(self, limit=500):
        return self.rows("select r.id, r.created, r.prompt, r.provider, r.model, r.status, "
                         "(select count(*) from sessions s where s.run_id = r.id) as sessions, "
                         "(select count(*) from run_rounds o where o.run_id = r.id) as rounds, "
                         "(select count(*) from votes v where v.run_id = r.id) as votes "
                         "from runs r order by r.created desc limit ?", (limit,))

    def run(self, run_id):
        """A run with its rounds, its sessions (each with its generations and their judgments) and its votes."""
        found = self.rows("select * from runs where id = ?", (run_id,))
        if not found:
            return None
        run = found[0]
        run["rounds"] = self.rows("select round, prompt, created from run_rounds where run_id = ? order by round",
                                  (run_id,))
        run["sessions"] = self.rows("select * from sessions where run_id = ? order by repeat, arm", (run_id,))
        generations = self.rows("select g.* from generations g join sessions s on s.id = g.session_id "
                                "where s.run_id = ? order by g.round", (run_id,))
        judged = self.rows("select j.* from judgments j join sessions s on s.id = j.session_id "
                           "where s.run_id = ? order by j.created", (run_id,))
        for session in run["sessions"]:
            session["generations"] = [g for g in generations if g["session_id"] == session["id"]]
            for generation in session["generations"]:
                generation["judgments"] = [j for j in judged if j["session_id"] == session["id"]
                                           and j["round"] == generation["round"]]
        run["votes"] = {f"{row['round']}:{row['repeat']}": row["winner"]
                        for row in self.rows("select * from votes where run_id = ?", (run_id,))}
        return run

    def session(self, session_id):
        found = self.rows("select * from sessions where id = ?", (session_id,))
        return found[0] if found else None

    def stats(self, run_ids=None):
        """Per model and arm, over every finished generation (of ``run_ids`` when given): how often it delivered,
        its judge mean, its blind-vote record, and its time, tokens, cost and tool errors."""
        generations = self.rows("select g.*, s.run_id, s.arm, s.repeat, r.model, r.provider from generations g "
                                "join sessions s on s.id = g.session_id join runs r on r.id = s.run_id")
        votes = self.rows("select * from votes")
        if run_ids is not None:
            generations = [g for g in generations if g["run_id"] in run_ids]
            votes = [v for v in votes if v["run_id"] in run_ids]
        judgments = self.rows("select * from judgments where error = '' or error is null")
        groups = {}

        def group(row):
            key = (row["provider"], row["model"], row["arm"])
            return groups.setdefault(key, {"provider": key[0], "model": key[1], "arm": key[2], "generations": 0,
                                           "followups": 0, "delivered": 0, "judge": [], "wins": 0, "votes": 0,
                                           "seconds": [], "tokens": [], "cost": [], "tool_errors": 0,
                                           "tool_calls": 0})

        for row in generations:
            if row["status"] in LIVE:
                continue
            entry, metrics = group(row), row["metrics"] or {}
            entry["generations"] += 1
            entry["followups"] += row["round"] > 1
            entry["delivered"] += bool(row["preview"])
            entry["seconds"].append(metrics.get("seconds", 0))
            entry["tokens"].append(sum(metrics.get(k, 0) for k in ("input", "output", "cache_read", "cache_write")))
            if metrics.get("cost") is not None:
                entry["cost"].append(metrics["cost"])
            entry["tool_calls"] += metrics.get("tool_calls", 0)
            entry["tool_errors"] += metrics.get("tool_errors", 0)
            entry["judge"] += [j["mean"] for j in judgments if j["session_id"] == row["session_id"]
                               and j["round"] == row["round"] and j["mean"]]
        for vote in votes:
            for row in generations:
                if (row["run_id"], row["round"], row["repeat"]) == (vote["run_id"], vote["round"], vote["repeat"]):
                    entry = group(row)
                    entry["votes"] += 1
                    entry["wins"] += vote["winner"] == row["session_id"]
        result = []
        for entry in groups.values():
            result.append({
                "provider": entry["provider"], "model": entry["model"], "arm": entry["arm"],
                "generations": entry["generations"], "followups": entry["followups"],
                "delivered": entry["delivered"],
                "judge_mean": round(statistics.mean(entry["judge"]), 2) if entry["judge"] else None,
                "judged": len(entry["judge"]), "wins": entry["wins"], "votes": entry["votes"],
                "median_seconds": round(statistics.median(entry["seconds"]), 1) if entry["seconds"] else None,
                "median_tokens": int(statistics.median(entry["tokens"])) if entry["tokens"] else None,
                "mean_cost": round(statistics.mean(entry["cost"]), 4) if entry["cost"] else None,
                "tool_calls": entry["tool_calls"], "tool_errors": entry["tool_errors"],
            })
        return sorted(result, key=lambda r: (r["model"], r["arm"]))
