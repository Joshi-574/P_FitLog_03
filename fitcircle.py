"""FitCircle social features backed by the existing FitLog SQLite database."""
import secrets
import sqlite3
from contextlib import closing
from datetime import date, timedelta

from fitlog_store import DB_FILE, _connect, init_db
from fitlog_devices import init_device_db


def init_fitcircle(db_file=DB_FILE):
    init_db(db_file)
    with closing(_connect(db_file)) as conn, conn:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(users)")}
        for name, declaration in (
            ("fitlog_id", "TEXT"), ("profile_avatar", "TEXT NOT NULL DEFAULT '🏃'"),
            ("discovery_enabled", "INTEGER NOT NULL DEFAULT 0"),
            ("leaderboard_opt_in", "INTEGER NOT NULL DEFAULT 0"),
        ):
            if name not in cols:
                conn.execute(f"ALTER TABLE users ADD COLUMN {name} {declaration}")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_fitlog_id ON users(fitlog_id)")
        conn.execute("""CREATE TABLE IF NOT EXISTS user_privacy (
            user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            share_steps INTEGER NOT NULL DEFAULT 0, share_workouts INTEGER NOT NULL DEFAULT 0,
            share_calories INTEGER NOT NULL DEFAULT 0, share_duration INTEGER NOT NULL DEFAULT 0,
            leaderboard_visibility INTEGER NOT NULL DEFAULT 0)""")
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS friend_requests (
          id INTEGER PRIMARY KEY, sender_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          receiver_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          status TEXT NOT NULL CHECK(status IN ('pending','accepted','rejected','cancelled')),
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(sender_id,receiver_id));
        CREATE TABLE IF NOT EXISTS friendships (
          id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          friend_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          status TEXT NOT NULL DEFAULT 'accepted' CHECK(status='accepted'),
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(user_id,friend_id), CHECK(user_id<friend_id));
        CREATE TABLE IF NOT EXISTS fitness_goals (
          id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          goal_type TEXT NOT NULL, target_value REAL NOT NULL CHECK(target_value>0), current_value REAL NOT NULL DEFAULT 0,
          start_date TEXT NOT NULL, end_date TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'active');
        CREATE TABLE IF NOT EXISTS challenges (
          id INTEGER PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', challenge_type TEXT NOT NULL,
          target_value REAL NOT NULL CHECK(target_value>0), start_date TEXT NOT NULL, end_date TEXT NOT NULL,
          created_by INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS challenge_participants (
          id INTEGER PRIMARY KEY, challenge_id INTEGER NOT NULL REFERENCES challenges(id) ON DELETE CASCADE,
          user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, progress REAL NOT NULL DEFAULT 0,
          completion_status TEXT NOT NULL DEFAULT 'active', UNIQUE(challenge_id,user_id));
        CREATE TABLE IF NOT EXISTS challenge_invites (
          challenge_id INTEGER NOT NULL REFERENCES challenges(id) ON DELETE CASCADE,
          user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          invited_by INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          PRIMARY KEY(challenge_id,user_id));
        CREATE TABLE IF NOT EXISTS achievements (
          id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          badge_name TEXT NOT NULL, description TEXT NOT NULL, earned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(user_id,badge_name));
        CREATE TABLE IF NOT EXISTS invitations (
          code TEXT PRIMARY KEY, created_by INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE INDEX IF NOT EXISTS idx_requests_receiver ON friend_requests(receiver_id,status);
        CREATE INDEX IF NOT EXISTS idx_friends_user ON friendships(user_id,friend_id);
        CREATE INDEX IF NOT EXISTS idx_challenge_participants_user ON challenge_participants(user_id);
        """)
        for row in conn.execute("SELECT id FROM users WHERE fitlog_id IS NULL"):
            conn.execute("UPDATE users SET fitlog_id=? WHERE id=?", (f"FL{row['id']:06d}", row["id"]))
        conn.execute("INSERT OR IGNORE INTO user_privacy(user_id) SELECT id FROM users")


def search_users(actor, query, db_file=DB_FILE):
    init_fitcircle(db_file)
    query = str(query or "").strip()
    if not query: return []
    with closing(_connect(db_file)) as c:
        rows = c.execute("""SELECT id,username,fitlog_id,profile_avatar FROM users
          WHERE id<>? AND (username LIKE ? COLLATE NOCASE OR fitlog_id=? COLLATE NOCASE)
          ORDER BY username LIMIT 30""", (actor, f"%{query}%", query)).fetchall()
        return [dict(r) for r in rows]


def send_request(actor, target, db_file=DB_FILE):
    init_fitcircle(db_file)
    if actor == target: raise ValueError("You cannot send a request to yourself.")
    with closing(_connect(db_file)) as c, c:
        if not c.execute("SELECT 1 FROM users WHERE id=?", (target,)).fetchone(): raise ValueError("User not found.")
        if c.execute("SELECT 1 FROM friendships WHERE user_id=? AND friend_id=?", (min(actor,target),max(actor,target))).fetchone(): raise ValueError("You are already friends.")
        existing = c.execute("SELECT id,status FROM friend_requests WHERE sender_id=? AND receiver_id=?", (actor,target)).fetchone()
        reverse = c.execute("SELECT id,status FROM friend_requests WHERE sender_id=? AND receiver_id=?", (target,actor)).fetchone()
        if reverse and reverse["status"] == "pending": raise ValueError("This user has already sent you a request.")
        if existing and existing["status"] == "pending": raise ValueError("A request is already pending.")
        if existing: c.execute("UPDATE friend_requests SET status='pending',created_at=CURRENT_TIMESTAMP WHERE id=?", (existing["id"],))
        else: c.execute("INSERT INTO friend_requests(sender_id,receiver_id,status) VALUES(?,?,'pending')", (actor,target))


def requests(actor, db_file=DB_FILE):
    init_fitcircle(db_file)
    with closing(_connect(db_file)) as c:
        incoming=c.execute("SELECT r.id,u.id user_id,u.username,u.fitlog_id,'incoming' direction FROM friend_requests r JOIN users u ON u.id=r.sender_id WHERE r.receiver_id=? AND r.status='pending'",(actor,)).fetchall()
        outgoing=c.execute("SELECT r.id,u.id user_id,u.username,u.fitlog_id,'outgoing' direction FROM friend_requests r JOIN users u ON u.id=r.receiver_id WHERE r.sender_id=? AND r.status='pending'",(actor,)).fetchall()
        return [dict(r) for r in [*incoming,*outgoing]]


def respond_request(actor, request_id, action, db_file=DB_FILE):
    if action not in {"accepted","rejected","cancelled"}: raise ValueError("Invalid response.")
    init_fitcircle(db_file)
    with closing(_connect(db_file)) as c, c:
        row=c.execute("SELECT * FROM friend_requests WHERE id=? AND status='pending'",(request_id,)).fetchone()
        if not row or actor not in (row["sender_id"],row["receiver_id"]): raise PermissionError("Pending request not found for this account.")
        if action == "cancelled" and row["sender_id"] != actor: raise PermissionError("Only the sender can cancel this request.")
        if action != "cancelled" and row["receiver_id"] != actor: raise PermissionError("Only the recipient can respond.")
        c.execute("UPDATE friend_requests SET status=? WHERE id=?",(action,request_id))
        if action == "accepted": c.execute("INSERT OR IGNORE INTO friendships(user_id,friend_id) VALUES(?,?)",(min(row["sender_id"],row["receiver_id"]),max(row["sender_id"],row["receiver_id"])))


def friends(actor, db_file=DB_FILE):
    init_fitcircle(db_file)
    with closing(_connect(db_file)) as c:
        return [dict(r) for r in c.execute("""SELECT u.id,u.username,u.fitlog_id,u.profile_avatar FROM friendships f
          JOIN users u ON u.id=CASE WHEN f.user_id=? THEN f.friend_id ELSE f.user_id END
          WHERE f.user_id=? OR f.friend_id=? ORDER BY u.username""",(actor,actor,actor))]


def remove_friend(actor, target, db_file=DB_FILE):
    init_fitcircle(db_file)
    with closing(_connect(db_file)) as c, c: c.execute("DELETE FROM friendships WHERE user_id=? AND friend_id=?",(min(actor,target),max(actor,target)))


def update_privacy(actor, settings, db_file=DB_FILE):
    init_fitcircle(db_file)
    keys=("share_steps","share_workouts","share_calories","share_duration","leaderboard_visibility")
    vals=[int(bool(settings.get(k,False))) for k in keys]
    with closing(_connect(db_file)) as c, c: c.execute("INSERT INTO user_privacy(user_id) VALUES(?) ON CONFLICT(user_id) DO NOTHING",(actor,)); c.execute("UPDATE user_privacy SET share_steps=?,share_workouts=?,share_calories=?,share_duration=?,leaderboard_visibility=? WHERE user_id=?",(*vals,actor))


def get_privacy(actor, db_file=DB_FILE):
    init_fitcircle(db_file)
    with closing(_connect(db_file)) as c:
        r=c.execute("SELECT p.*,u.discovery_enabled,u.leaderboard_opt_in FROM user_privacy p JOIN users u ON u.id=p.user_id WHERE p.user_id=?",(actor,)).fetchone()
        return dict(r) if r else {}


def update_discovery_settings(actor, discovery, leaderboard_opt_in, db_file=DB_FILE):
    init_fitcircle(db_file)
    with closing(_connect(db_file)) as c, c:
        c.execute("UPDATE users SET discovery_enabled=?,leaderboard_opt_in=? WHERE id=?", (int(bool(discovery)), int(bool(leaderboard_opt_in)), actor))


def compare_progress(actor, target, db_file=DB_FILE):
    init_fitcircle(db_file)
    init_device_db(db_file)
    if actor==target: raise ValueError("Choose a friend to compare.")
    with closing(_connect(db_file)) as c:
        if not c.execute("SELECT 1 FROM friendships WHERE user_id=? AND friend_id=?",(min(actor,target),max(actor,target))).fetchone(): raise PermissionError("Progress is available to accepted friends only.")
        p=c.execute("SELECT * FROM user_privacy WHERE user_id=?",(target,)).fetchone()
        if not p: return {}
        today=date.today(); start=(today-timedelta(days=today.weekday())).isoformat(); end=(today+timedelta(days=1)).isoformat(); prior=(today-timedelta(days=today.weekday()+7)).isoformat()
        result={"username":c.execute("SELECT username FROM users WHERE id=?",(target,)).fetchone()[0]}
        metrics={"workouts":"COUNT(*)","duration":"COALESCE(SUM(duration),0)","calories":"COALESCE(SUM(calories),0)"}
        result["you"]={}
        for key,expr in metrics.items():
            result["you"][key]=c.execute(f"SELECT {expr} FROM workouts WHERE user_id=? AND date>=? AND date<?",(actor,start,end)).fetchone()[0]
            result[key]=None
            if p[f"share_{key}"]:
                result[key]=c.execute(f"SELECT {expr} FROM workouts WHERE user_id=? AND date>=? AND date<?",(target,start,end)).fetchone()[0]
                prev=c.execute(f"SELECT {expr} FROM workouts WHERE user_id=? AND date>=? AND date<?",(target,prior,start)).fetchone()[0]
                result[key+"_change"]=round((result[key]-prev)*100/prev,1) if prev else None
        if p["share_steps"]:
            daily_totals="SELECT MAX(steps) AS daily_steps FROM device_daily_steps WHERE user_id=? AND activity_date>=? AND activity_date<? GROUP BY activity_date"
            result["steps"]=c.execute(f"SELECT COALESCE(SUM(daily_steps),0) FROM ({daily_totals})",(target,start,end)).fetchone()[0]
            result["you"]["steps"]=c.execute(f"SELECT COALESCE(SUM(daily_steps),0) FROM ({daily_totals})",(actor,start,end)).fetchone()[0]
            prior_steps=c.execute(f"SELECT COALESCE(SUM(daily_steps),0) FROM ({daily_totals})",(target,prior,start)).fetchone()[0]
            result["steps_change"]=round((result["steps"]-prior_steps)*100/prior_steps,1) if prior_steps else None
        else:
            result["steps"]=None
        result["personal_best_minutes"]=c.execute("SELECT COALESCE(MAX(duration),0) FROM workouts WHERE user_id=?",(actor,)).fetchone()[0]
        return result


def leaderboard(actor, db_file=DB_FILE):
    init_fitcircle(db_file)
    with closing(_connect(db_file)) as c:
        ids=[actor]+[f["id"] for f in friends(actor,db_file)]
        marks=','.join('?' for _ in ids); start=(date.today()-timedelta(days=date.today().weekday())).isoformat(); end=(date.today()+timedelta(days=1)).isoformat()
        rows=c.execute(f"""SELECT u.username,COUNT(w.id) workouts,COALESCE(SUM(w.duration),0) minutes,
          MIN(COUNT(w.id),5)*10+MIN(COALESCE(SUM(w.duration),0),300)/30 points
          FROM users u JOIN user_privacy p ON p.user_id=u.id AND p.leaderboard_visibility=1
          LEFT JOIN workouts w ON w.user_id=u.id AND w.date>=? AND w.date<?
          WHERE u.id IN ({marks}) AND u.leaderboard_opt_in=1 GROUP BY u.id ORDER BY points DESC,workouts DESC""",(start,end,*ids)).fetchall()
        return [dict(r,rank=i+1) for i,r in enumerate(rows)]


def create_challenge(actor,title,description,kind,target,start,end,db_file=DB_FILE,invite_ids=()):
    init_fitcircle(db_file)
    if kind not in {"workouts", "minutes", "steps"}:
        raise ValueError("Challenge tracking must use workouts, minutes, or recorded steps.")
    if kind == "steps": init_device_db(db_file)
    title=str(title).strip()
    if not title or len(title)>80 or float(target)<=0: raise ValueError("Enter a title (up to 80 characters) and positive target.")
    if date.fromisoformat(str(end))<date.fromisoformat(str(start)): raise ValueError("End date must be on or after start date.")
    with closing(_connect(db_file)) as c, c:
        cid=c.execute("INSERT INTO challenges(title,description,challenge_type,target_value,start_date,end_date,created_by) VALUES(?,?,?,?,?,?,?)",(title,str(description)[:500],kind,float(target),str(start),str(end),actor)).lastrowid
        c.execute("INSERT INTO challenge_participants(challenge_id,user_id) VALUES(?,?)",(cid,actor))
        for target_id in set(invite_ids or ()):
            if target_id == actor: continue
            if not c.execute("SELECT 1 FROM friendships WHERE user_id=? AND friend_id=?",(min(actor,target_id),max(actor,target_id))).fetchone():
                raise PermissionError("Challenges can only be invited to accepted friends.")
            c.execute("INSERT OR IGNORE INTO challenge_invites(challenge_id,user_id,invited_by) VALUES(?,?,?)",(cid,target_id,actor))
        return cid


def join_challenge(actor,cid,db_file=DB_FILE):
    init_fitcircle(db_file)
    with closing(_connect(db_file)) as c, c:
        challenge=c.execute("SELECT created_by FROM challenges WHERE id=?",(cid,)).fetchone()
        if not challenge: raise ValueError("Challenge not found.")
        if challenge["created_by"] != actor and not c.execute("SELECT 1 FROM challenge_invites WHERE challenge_id=? AND user_id=?",(cid,actor)).fetchone():
            raise PermissionError("You need an invitation from a friend to join this challenge.")
        c.execute("INSERT OR IGNORE INTO challenge_participants(challenge_id,user_id) VALUES(?,?)",(cid,actor))


def challenges(actor,db_file=DB_FILE):
    init_fitcircle(db_file)
    init_device_db(db_file)
    with closing(_connect(db_file)) as c:
        rows=c.execute("""SELECT ch.*,u.username creator,cp.progress,cp.completion_status,
          (SELECT COUNT(*) FROM challenge_participants x WHERE x.challenge_id=ch.id) participants
          FROM challenges ch JOIN users u ON u.id=ch.created_by LEFT JOIN challenge_participants cp ON cp.challenge_id=ch.id AND cp.user_id=?
          WHERE ch.created_by=? OR cp.user_id IS NOT NULL OR EXISTS(SELECT 1 FROM challenge_invites ci WHERE ci.challenge_id=ch.id AND ci.user_id=?) ORDER BY ch.end_date""",(actor,actor,actor)).fetchall()
        result=[]
        for row in rows:
            item=dict(row)
            if item["progress"] is not None:
                if item["challenge_type"] == "workouts":
                    amount=c.execute("SELECT COUNT(*) FROM workouts WHERE user_id=? AND date>=? AND date<=?",(actor,item["start_date"],item["end_date"])).fetchone()[0]
                elif item["challenge_type"] == "minutes":
                    amount=c.execute("SELECT COALESCE(SUM(duration),0) FROM workouts WHERE user_id=? AND date>=? AND date<=?",(actor,item["start_date"],item["end_date"])).fetchone()[0]
                else:
                    amount=c.execute("SELECT COALESCE(MAX(steps),0) FROM device_daily_steps WHERE user_id=? AND activity_date>=? AND activity_date<=?",(actor,item["start_date"],item["end_date"])).fetchone()[0]
                item["progress"]=amount
                status="complete" if amount>=item["target_value"] else "active"
                item["completion_status"]=status
                c.execute("UPDATE challenge_participants SET progress=?,completion_status=? WHERE challenge_id=? AND user_id=?",(amount,status,item["id"],actor))
                if status=="complete": c.execute("INSERT OR IGNORE INTO achievements(user_id,badge_name,description) VALUES(?,?,?)",(actor,f"Challenge: {item['title']}",f"Completed the {item['title']} challenge."))
            result.append(item)
        c.commit()
        return result


def invite_code(actor,db_file=DB_FILE):
    init_fitcircle(db_file); code=secrets.token_urlsafe(8)
    with closing(_connect(db_file)) as c, c: c.execute("INSERT INTO invitations(code,created_by) VALUES(?,?)",(code,actor))
    return code


def user_achievements(actor, db_file=DB_FILE):
    init_fitcircle(db_file)
    with closing(_connect(db_file)) as c:
        return [dict(r) for r in c.execute("SELECT badge_name,description,earned_at FROM achievements WHERE user_id=? ORDER BY earned_at DESC", (actor,))]


def valid_invite(code, db_file=DB_FILE):
    init_fitcircle(db_file)
    with closing(_connect(db_file)) as c:
        return bool(c.execute("SELECT 1 FROM invitations WHERE code=?", (str(code or "").strip(),)).fetchone())


def suggestions(actor,db_file=DB_FILE):
    init_fitcircle(db_file)
    with closing(_connect(db_file)) as c:
        return [dict(r) for r in c.execute("SELECT id,username,fitlog_id,profile_avatar FROM users WHERE id<>? AND discovery_enabled=1 AND id NOT IN (SELECT friend_id FROM friendships WHERE user_id=? UNION SELECT user_id FROM friendships WHERE friend_id=?) AND id NOT IN (SELECT receiver_id FROM friend_requests WHERE sender_id=? AND status='pending') ORDER BY id LIMIT 10",(actor,actor,actor,actor))]
