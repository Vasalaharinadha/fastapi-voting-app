# main.py
import sqlite3
from fastapi import FastAPI, HTTPException, Depends, status, Header
from pydantic import BaseModel, constr
from typing import Optional, List
from datetime import datetime, timedelta
import enum
import os

DB_FILE = "voting.db"

# --- Init DB ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    # proposals table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS proposals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        created_at TEXT NOT NULL,
        deadline TEXT NOT NULL,
        status TEXT NOT NULL
    );
    """)

    # votes table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS votes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        proposal_id INTEGER NOT NULL,
        voter_name TEXT NOT NULL,
        vote TEXT NOT NULL CHECK(vote IN ('yes','no','abstain')),
        voted_at TEXT NOT NULL,
        UNIQUE(proposal_id, voter_name),
        FOREIGN KEY(proposal_id) REFERENCES proposals(id) ON DELETE CASCADE
    );
    """)
    conn.commit()
    conn.close()

init_db()

# --- ENUMs ---
class ProposalStatus(str, enum.Enum):
    active = "active"
    closed = "closed"
    expired = "expired"

# --- Schemas ---
class ProposalCreate(BaseModel):
    title: constr(min_length=1)
    description: constr(min_length=1)
    days_open: Optional[int] = 2

class ProposalOut(BaseModel):
    id: int
    title: str
    description: str
    created_at: datetime
    deadline: datetime
    status: ProposalStatus
    yes_count: int
    no_count: int
    abstain_count: int

class VoteCreate(BaseModel):
    voter_name: constr(min_length=1)
    vote: constr(regex="^(yes|no|abstain)$")

class VoteOut(BaseModel):
    id: int
    proposal_id: int
    voter_name: str
    vote: str
    voted_at: datetime

# --- FastAPI ---
app = FastAPI(title="Community Digital Voting System (SQLite3)")

def get_conn():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

# --- Helpers ---
def get_proposal_or_404(conn, proposal_id: int):
    cur = conn.cursor()
    cur.execute("SELECT * FROM proposals WHERE id=?", (proposal_id,))
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Proposal not found")
    # check expiry
    deadline = datetime.fromisoformat(row["deadline"])
    if row["status"] == ProposalStatus.active.value and datetime.utcnow() > deadline:
        cur.execute("UPDATE proposals SET status=? WHERE id=?", (ProposalStatus.expired.value, proposal_id))
        conn.commit()
        cur.execute("SELECT * FROM proposals WHERE id=?", (proposal_id,))
        row = cur.fetchone()
    return row

def tally_votes(conn, proposal_id: int):
    cur = conn.cursor()
    cur.execute("SELECT vote, COUNT(*) as c FROM votes WHERE proposal_id=? GROUP BY vote", (proposal_id,))
    counts = {"yes": 0, "no": 0, "abstain": 0}
    for r in cur.fetchall():
        counts[r["vote"]] = r["c"]
    return counts["yes"], counts["no"], counts["abstain"]

# --- Routes ---
@app.post("/proposals/", response_model=ProposalOut, status_code=status.HTTP_201_CREATED)
def create_proposal(payload: ProposalCreate):
    conn = get_conn()
    cur = conn.cursor()
    created_at = datetime.utcnow()
    deadline = created_at + timedelta(days=payload.days_open)
    cur.execute("INSERT INTO proposals (title, description, created_at, deadline, status) VALUES (?,?,?,?,?)",
                (payload.title, payload.description, created_at.isoformat(), deadline.isoformat(), ProposalStatus.active.value))
    conn.commit()
    pid = cur.lastrowid
    row = get_proposal_or_404(conn, pid)
    yes, no, abstain = tally_votes(conn, pid)
    conn.close()
    return ProposalOut(id=row["id"], title=row["title"], description=row["description"],
                       created_at=datetime.fromisoformat(row["created_at"]),
                       deadline=datetime.fromisoformat(row["deadline"]),
                       status=row["status"], yes_count=yes, no_count=no, abstain_count=abstain)

@app.get("/proposals/", response_model=List[ProposalOut])
def get_proposals():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id FROM proposals")
    ids = [r["id"] for r in cur.fetchall()]
    results = []
    for pid in ids:
        row = get_proposal_or_404(conn, pid)
        yes, no, abstain = tally_votes(conn, pid)
        results.append(ProposalOut(id=row["id"], title=row["title"], description=row["description"],
                                   created_at=datetime.fromisoformat(row["created_at"]),
                                   deadline=datetime.fromisoformat(row["deadline"]),
                                   status=row["status"], yes_count=yes, no_count=no, abstain_count=abstain))
    conn.close()
    return results

@app.get("/proposals/{proposal_id}", response_model=ProposalOut)
def get_proposal(proposal_id: int):
    conn = get_conn()
    row = get_proposal_or_404(conn, proposal_id)
    yes, no, abstain = tally_votes(conn, proposal_id)
    conn.close()
    return ProposalOut(id=row["id"], title=row["title"], description=row["description"],
                       created_at=datetime.fromisoformat(row["created_at"]),
                       deadline=datetime.fromisoformat(row["deadline"]),
                       status=row["status"], yes_count=yes, no_count=no, abstain_count=abstain)

@app.post("/proposals/{proposal_id}/vote", response_model=VoteOut, status_code=status.HTTP_201_CREATED)
def submit_vote(proposal_id: int, payload: VoteCreate):
    conn = get_conn()
    row = get_proposal_or_404(conn, proposal_id)
    if row["status"] != ProposalStatus.active.value:
        conn.close()
        raise HTTPException(status_code=400, detail="Proposal is not active; voting is not allowed.")

    cur = conn.cursor()
    cur.execute("SELECT id FROM votes WHERE proposal_id=? AND voter_name=?", (proposal_id, payload.voter_name))
    if cur.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Voter has already voted. Revoke first to change vote.")
    voted_at = datetime.utcnow()
    cur.execute("INSERT INTO votes (proposal_id, voter_name, vote, voted_at) VALUES (?,?,?,?)",
                (proposal_id, payload.voter_name, payload.vote, voted_at.isoformat()))
    conn.commit()
    vid = cur.lastrowid
    cur.execute("SELECT * FROM votes WHERE id=?", (vid,))
    v = cur.fetchone()
    conn.close()
    return VoteOut(id=v["id"], proposal_id=v["proposal_id"], voter_name=v["voter_name"],
                   vote=v["vote"], voted_at=datetime.fromisoformat(v["voted_at"]))

@app.delete("/votes/{vote_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_vote(vote_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM votes WHERE id=?", (vote_id,))
    v = cur.fetchone()
    if not v:
        conn.close()
        raise HTTPException(status_code=404, detail="Vote not found")
    p = get_proposal_or_404(conn, v["proposal_id"])
    if p["status"] != ProposalStatus.active.value:
        conn.close()
        raise HTTPException(status_code=400, detail="Cannot revoke vote: proposal not active.")
    cur.execute("DELETE FROM votes WHERE id=?", (vote_id,))
    conn.commit()
    conn.close()
    return None

@app.patch("/proposals/{proposal_id}/close", response_model=ProposalOut)
def close_proposal(proposal_id: int, x_admin_token: Optional[str] = Header(None)):
    ADMIN_TOKEN = "secret-admin-token"
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Admin token required")
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM proposals WHERE id=?", (proposal_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Proposal not found")
    cur.execute("UPDATE proposals SET status=? WHERE id=?", (ProposalStatus.closed.value, proposal_id))
    conn.commit()
    row = get_proposal_or_404(conn, proposal_id)
    yes, no, abstain = tally_votes(conn, proposal_id)
    conn.close()
    return ProposalOut(id=row["id"], title=row["title"], description=row["description"],
                       created_at=datetime.fromisoformat(row["created_at"]),
                       deadline=datetime.fromisoformat(row["deadline"]),
                       status=row["status"], yes_count=yes, no_count=no, abstain_count=abstain)

@app.get("/votes/", response_model=List[VoteOut])
def list_votes():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM votes")
    rows = cur.fetchall()
    conn.close()
    return [VoteOut(id=r["id"], proposal_id=r["proposal_id"], voter_name=r["voter_name"],
                    vote=r["vote"], voted_at=datetime.fromisoformat(r["voted_at"])) for r in rows]

@app.get("/health")
def health():
    return {"status": "ok"}
