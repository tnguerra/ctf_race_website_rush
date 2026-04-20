import os
import sqlite3
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.getenv("DB_PATH", str(BASE_DIR / "ctf_data.db")))


def get_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = get_db()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL,
            display_name TEXT NOT NULL,
            race_name TEXT NOT NULL,
            ticket_code TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            racer_name TEXT NOT NULL,
            kart_name TEXT NOT NULL,
            ticket_code TEXT UNIQUE NOT NULL,
            grid_position INTEGER NOT NULL,
            status TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS seating (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seat_code TEXT UNIQUE NOT NULL,
            seat_type TEXT NOT NULL,
            status TEXT NOT NULL,
            note TEXT NOT NULL,
            claimed_by_user_id INTEGER,
            seat_token TEXT UNIQUE NOT NULL
        );
        """
    )

    default_admin_user = os.getenv("DEFAULT_ADMIN_USER", "pitmarshal")
    default_admin_password = os.getenv("DEFAULT_ADMIN_PASSWORD", "mushr00mgrid")

    conn.execute(
        """
        INSERT OR IGNORE INTO users (username, password, role, display_name, race_name, ticket_code)
        VALUES (?, ?, 'admin', 'Race Control Admin', 'Master Cup Controller', 'ADM-CTRL-001')
        """,
        (default_admin_user, default_admin_password),
    )
    racer_accounts = [
        ("racer01", "mario", "Mario", "Standard Kart", "FLAG{mkc7e_racer_redshell_9a12}"),
        ("racer02", "luigi", "Luigi", "Pipe Frame", "FLAG{mkc7e_racer_pipe_turn_4f63}"),
        ("racer03", "peach", "Peach", "Mach 8", "FLAG{mkc7e_racer_royal_drift_b29e}"),
        ("racer04", "toad", "Toad", "Biddybuggy", "FLAG{mkc7e_racer_biddy_launch_31cd}"),
        ("racer05", "yoshi", "Yoshi", "Yoshi Bike", "FLAG{mkc7e_racer_eggline_7d8b}"),
        ("racer06", "8ow5er", "Bowser", "Flame Runner", "FLAG{mkc7e_racer_koopa_burn_f441}"),
        ("racer07", "d4!sy", "Daisy", "Wild Wing", "FLAG{mkc7e_racer_wild_wing_aa09}"),
        ("racer08", "W4r1o", "Wario", "Wario Bike", "FLAG{mkc7e_racer_gold_spin_5ce2}"),
        ("racer09", "kingboo123", "King Boo", "Splat Buggy", "FLAG{mkc7e_racer_boo_hide_18ef}"),
        ("racer10", "guyshy", "Shy Guy", "Sneeker", "FLAG{mkc7e_racer_shy_dodge_c742}"),
        ("racer11", "rosalina07", "Rosalina", "Comet", "FLAG{mkc7e_racer_luma_arc_2e95}"),
        ("racer12", "MsToadette", "Toadette", "Cat Cruiser", "FLAG{mkc7e_racer_jungle_boost_6ab1}"),
    ]
    conn.executemany(
        """
        INSERT OR IGNORE INTO users (username, password, role, display_name, race_name, ticket_code)
        VALUES (?, ?, 'user', ?, ?, ?)
        """,
        racer_accounts,
    )

    racer_grid = [
        ("Mario", "Standard Kart", "GRID-001", 1, "confirmed"),
        ("Luigi", "Pipe Frame", "GRID-002", 2, "confirmed"),
        ("Peach", "Mach 8", "GRID-003", 3, "confirmed"),
        ("Toad", "Biddybuggy", "GRID-004", 4, "confirmed"),
        ("Yoshi", "Yoshi Bike", "GRID-005", 5, "confirmed"),
        ("Bowser", "Flame Runner", "GRID-006", 6, "confirmed"),
        ("Daisy", "Wild Wing", "GRID-007", 7, "confirmed"),
        ("Wario", "Wario Bike", "GRID-008", 8, "confirmed"),
        ("King Boo", "Splat Buggy", "GRID-009", 9, "confirmed"),
        ("Shy Guy", "Sneeker", "GRID-010", 10, "confirmed"),
        ("Rosalina", "Comet", "GRID-011", 11, "confirmed"),
        ("Toadette", "Cat Cruiser", "GRID-012", 12, "confirmed"),
    ]

    conn.executemany(
        """
        INSERT OR IGNORE INTO tickets (racer_name, kart_name, ticket_code, grid_position, status)
        VALUES (?, ?, ?, ?, ?)
        """,
        racer_grid,
    )

    # Create only the VIP seats used by the challenge.
    seating_data = [
        ('VIP-01', 'vip', 'open', 'VIP stadium pass', 'FLAG{vip_stadium_pass}'),
        ('VIP-02', 'vip', 'open', 'VIP stadium pass', 'FLAG{vip_stadium_pass}'),
        ('VIP-03', 'vip', 'open', 'VIP stadium pass', 'FLAG{vip_stadium_pass}'),
    ]
    conn.executemany(
        """
        INSERT OR IGNORE INTO seating (seat_code, seat_type, status, note, seat_token)
        VALUES (?, ?, ?, ?, ?)
        """,
        seating_data,
    )

    conn.commit()
    conn.close()


def authenticate_user(username: str, password: str) -> sqlite3.Row | None:
    conn = get_db()
    user = conn.execute(
        "SELECT id, username, role FROM users WHERE username = ? AND password = ?",
        (username, password),
    ).fetchone()
    conn.close()
    return user


def get_user_profile(user_id: int) -> sqlite3.Row | None:
    conn = get_db()
    user = conn.execute(
        "SELECT id, display_name, race_name, ticket_code FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    conn.close()
    return user


def list_tickets() -> list[sqlite3.Row]:
    conn = get_db()
    rows = conn.execute(
        """
        SELECT t.id, t.racer_name, t.kart_name, t.ticket_code, t.grid_position, t.status
        FROM tickets t
        ORDER BY t.grid_position ASC
        """
    ).fetchall()
    conn.close()
    return rows


def create_ticket(racer_name: str, kart_name: str, grid_position: int, status: str = "confirmed") -> None:
    conn = get_db()
    code = f"GRID-{int(time.time()) % 100000:05d}"
    conn.execute(
        "INSERT INTO tickets (racer_name, kart_name, ticket_code, grid_position, status) VALUES (?, ?, ?, ?, ?)",
        (racer_name, kart_name, code, grid_position, status),
    )
    conn.commit()
    conn.close()


def delete_ticket(ticket_id: int) -> None:
    conn = get_db()
    conn.execute("DELETE FROM tickets WHERE id = ?", (ticket_id,))
    conn.commit()
    conn.close()


def list_seating() -> list[sqlite3.Row]:
    conn = get_db()
    rows = conn.execute(
        """
        SELECT s.id, s.seat_code, s.seat_type, s.status, s.note, s.claimed_by_user_id, s.seat_token, u.username AS claimed_username
        FROM seating s
        LEFT JOIN users u ON u.id = s.claimed_by_user_id
        ORDER BY s.id ASC
        """
    ).fetchall()
    conn.close()
    return rows


def list_open_seats() -> list[sqlite3.Row]:
    conn = get_db()
    rows = conn.execute(
        "SELECT id, seat_code, seat_type, status, note FROM seating WHERE status = 'open' ORDER BY id ASC"
    ).fetchall()
    conn.close()
    return rows


def list_open_vip_seats() -> list[sqlite3.Row]:
    conn = get_db()
    rows = conn.execute(
        "SELECT id, seat_code FROM seating WHERE seat_type = 'vip' AND status = 'open' ORDER BY seat_code ASC"
    ).fetchall()
    conn.close()
    return rows


def get_user_claimed_seat(user_id: int) -> sqlite3.Row | None:
    conn = get_db()
    row = conn.execute(
        "SELECT id, seat_code, seat_type, status, note, seat_token FROM seating WHERE claimed_by_user_id = ? LIMIT 1",
        (user_id,),
    ).fetchone()
    conn.close()
    return row


def upsert_seating(seat_code: str, status: str, note: str) -> None:
    conn = get_db()
    conn.execute(
        """
        INSERT OR REPLACE INTO seating (id, seat_code, seat_type, status, note, claimed_by_user_id, seat_token)
        VALUES (
            (SELECT id FROM seating WHERE seat_code = ?),
            ?,
            COALESCE((SELECT seat_type FROM seating WHERE seat_code = ?), 'viewer'),
            ?, ?,
            (SELECT claimed_by_user_id FROM seating WHERE seat_code = ?),
            COALESCE((SELECT seat_token FROM seating WHERE seat_code = ?), 'SEAT_PENDING')
        )
        """,
        (seat_code, seat_code, seat_code, status, note, seat_code, seat_code),
    )
    conn.commit()
    conn.close()


def delete_seating(seat_id: int) -> None:
    conn = get_db()
    conn.execute("DELETE FROM seating WHERE id = ?", (seat_id,))
    conn.commit()
    conn.close()


def create_user_with_reserved_seat(username: str, display_name: str, seat_code: str) -> dict[str, str] | None:
    """Create user and assign the selected VIP seat if it is still open."""
    conn = get_db()

    seat = conn.execute(
        "SELECT id, seat_code, seat_type, status, seat_token FROM seating WHERE seat_code = ?",
        (seat_code,),
    ).fetchone()
    
    if not seat or seat["status"] != "open" or seat["seat_type"] != "vip":
        conn.close()
        return None

    username_clean = "".join(ch.lower() if ch.isalnum() or ch in "-_" else "-" for ch in username).strip("-_")
    if not username_clean:
        conn.close()
        return None

    existing = conn.execute("SELECT id FROM users WHERE username = ?", (username_clean,)).fetchone()
    if existing:
        conn.close()
        return None

    password = os.getenv("VIEWER_DEFAULT_PASSWORD", "vipviewer2026")
    ticket_code = os.getenv("VIEWER_TICKET_CODE", "FLAG{vip_stadium_pass}")

    conn.execute(
        """
        INSERT INTO users (username, password, role, display_name, race_name, ticket_code)
        VALUES (?, ?, 'user', ?, ?, 'PENDING')
        """,
        (username_clean, password, display_name, "Spectator"),
    )
    user_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]

    conn.execute(
        "UPDATE users SET username = ?, ticket_code = ? WHERE id = ?",
        (username_clean, ticket_code, user_id),
    )
    conn.execute(
        "UPDATE seating SET status = 'claimed', claimed_by_user_id = ? WHERE id = ?",
        (user_id, seat["id"]),
    )
    conn.commit()

    claimed = conn.execute(
        "SELECT seat_code, seat_token FROM seating WHERE id = ?",
        (seat["id"],),
    ).fetchone()
    conn.close()

    return {
        "username": username_clean,
        "password": password,
        "ticket_code": ticket_code,
        "seat_code": claimed["seat_code"],
        "seat_token": claimed["seat_token"],
    }
