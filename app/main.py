import os
from html import escape
from pathlib import Path
from secrets import token_hex

from fastapi import FastAPI, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .db import (
    authenticate_user,
    create_user_with_reserved_seat,
    create_ticket as db_create_ticket,
    delete_seating as db_delete_seating,
    delete_ticket as db_delete_ticket,
    get_user_claimed_seat,
    get_user_profile,
    init_db,
    list_open_vip_seats,
    list_seating,
    list_tickets,
    upsert_seating as db_upsert_seating,
)

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
CONTENT_DIR = BASE_DIR / "content"

app = FastAPI(title="CTF Race Website", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET", "change-me-in-later-stages"),
    same_site="lax",
    https_only=False,
)

FLAG_VALUE = os.getenv("FLAG_VALUE", "FLAG{foundation_ready}")
SESSION_BOOT_TOKEN = token_hex(16)


@app.on_event("startup")
def startup() -> None:
    init_db()


def load_page(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@app.middleware("http")
async def force_assets_index_redirect(request: Request, call_next):
    path = request.url.path
    if path == "/assets/index.html":
        return RedirectResponse(url="/portal/login", status_code=303)
    return await call_next(request)


def session_is_valid(request: Request, required_role: str | None = None) -> bool:
    if not request.session.get("authenticated"):
        return False
    if request.session.get("session_boot") != SESSION_BOOT_TOKEN:
        return False
    if required_role and request.session.get("role") != required_role:
        return False
    return True


@app.get("/portal/login", response_class=HTMLResponse)
def portal_login_page() -> str:
    return load_page(CONTENT_DIR / "portal" / "login.html")


@app.get("/login", response_class=HTMLResponse)
def login_page() -> str:
    return RedirectResponse(url="/portal/login", status_code=303)


@app.get("/", response_class=HTMLResponse)
def landing() -> str:
    return load_page(CONTENT_DIR / "portal" / "index.html")


@app.get("/assets/index.html", response_class=HTMLResponse)
def assets_index_redirect() -> Response:
    return RedirectResponse(url="/portal/login", status_code=303)


app.mount("/assets", StaticFiles(directory=STATIC_DIR, html=True), name="assets")
app.mount("/hidden", StaticFiles(directory=CONTENT_DIR / "hidden", html=True), name="hidden")
app.mount("/backup", StaticFiles(directory=CONTENT_DIR / "backup", html=True), name="backup")
app.mount("/logs", StaticFiles(directory=CONTENT_DIR / "logs", html=True), name="logs")


@app.post("/api/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)) -> Response:
    user = authenticate_user(username, password)

    if user:
        request.session["authenticated"] = True
        request.session["session_boot"] = SESSION_BOOT_TOKEN
        request.session["user_id"] = user["id"]
        request.session["username"] = user["username"]
        request.session["role"] = user["role"]
        redirect = "/admin" if user["role"] == "admin" else "/profile"
        return JSONResponse({"ok": True, "redirect": redirect})

    raise HTTPException(status_code=401, detail="Invalid credentials")


@app.post("/api/logout")
def logout(request: Request) -> Response:
    request.session.clear()
    return JSONResponse({"ok": True, "redirect": "/"})


@app.get("/api/me")
def me(request: Request) -> dict[str, object]:
    return {
        "authenticated": session_is_valid(request),
        "user_id": request.session.get("user_id"),
        "username": request.session.get("username"),
        "role": request.session.get("role"),
    }


@app.get("/admin", response_class=HTMLResponse)
def admin_panel(request: Request) -> str:
    if not session_is_valid(request, "admin"):
        return RedirectResponse(url="/portal/login", status_code=303)
    page = load_page(STATIC_DIR / "admin.html")
    return page.replace("{{FLAG}}", FLAG_VALUE)


@app.get("/profile", response_class=HTMLResponse)
def profile_panel(request: Request) -> str:
    if not session_is_valid(request):
        return RedirectResponse(url="/portal/login", status_code=303)
    if request.session.get("role") != "user":
        return RedirectResponse(url="/admin", status_code=303)

    user = get_user_profile(request.session["user_id"])
    claimed_seat = get_user_claimed_seat(request.session["user_id"])

    if not user:
        request.session.clear()
        return RedirectResponse(url="/portal/login", status_code=303)

    ticket_code = user["ticket_code"] if user else "PENDING"
    seat_code = "NOT ASSIGNED"
    seating_id = "N/A"
    seating_link = ""

    if claimed_seat and claimed_seat["seat_type"] == "vip":
        seat_code = claimed_seat["seat_code"]
        seating_id = claimed_seat["seat_token"]
        seating_link = '<p class="hint"><a href="/seating">View the reserved seating pass</a></p>'

    page = load_page(STATIC_DIR / "profile.html")
    page = page.replace("{{DISPLAY_NAME}}", escape(user["display_name"]))
    page = page.replace("{{RACE_NAME}}", escape(user["race_name"]))
    page = page.replace("{{TICKET_ID}}", escape(ticket_code))
    page = page.replace("{{SEAT_CODE}}", escape(seat_code))
    page = page.replace("{{SEATING_ID}}", escape(seating_id))
    page = page.replace("{{SEATING_LINK}}", seating_link)
    return page


@app.get("/admin/tickets", response_class=HTMLResponse)
def admin_tickets(request: Request) -> str:
    if not session_is_valid(request, "admin"):
        return RedirectResponse(url="/portal/login", status_code=303)

    rows = list_tickets()

    table_rows = []
    for row in rows:
        table_rows.append(
            "<tr>"
            f"<td>{row['id']}</td>"
            f"<td>{escape(row['racer_name'])}</td>"
            f"<td>{escape(row['kart_name'])}</td>"
            f"<td>{escape(row['ticket_code'])}</td>"
            f"<td>{escape(str(row['grid_position']))}</td>"
            f"<td>{escape(row['status'])}</td>"
            "</tr>"
        )

    page = load_page(STATIC_DIR / "admin_tickets.html")
    return page.replace("{{TICKET_ROWS}}", "".join(table_rows) or "<tr><td colspan='5'>No racers</td></tr>")


@app.post("/admin/tickets/create")
def create_ticket(
    request: Request,
    racer_name: str = Form(...),
    kart_name: str = Form(...),
    grid_position: int = Form(...),
    status: str = Form("confirmed"),
) -> Response:
    if not session_is_valid(request, "admin"):
        return RedirectResponse(url="/portal/login", status_code=303)

    db_create_ticket(racer_name, kart_name, grid_position, status)
    return RedirectResponse(url="/admin/tickets", status_code=303)


@app.post("/admin/tickets/{ticket_id}/delete")
def delete_ticket(request: Request, ticket_id: int) -> Response:
    if not session_is_valid(request, "admin"):
        return RedirectResponse(url="/portal/login", status_code=303)

    db_delete_ticket(ticket_id)
    return RedirectResponse(url="/admin/tickets", status_code=303)


@app.get("/admin/seating", response_class=HTMLResponse)
def admin_seating(request: Request) -> str:
    if not session_is_valid(request, "admin"):
        return RedirectResponse(url="/portal/login", status_code=303)

    created_notice = request.session.pop("created_user_notice", None)
    notice_block = ""
    if created_notice:
        notice_block = (
            "<div class='message'>"
            "Created viewer credentials:<br>"
            f"Username: <strong>{escape(created_notice['username'])}</strong><br>"
            f"Password: <strong>{escape(created_notice['password'])}</strong><br>"
            f"Ticket ID: <strong>{escape(created_notice['ticket_code'])}</strong><br>"
            f"Stadium seat: <strong>{escape(created_notice['seat_code'])}</strong><br>"
            f"Seating ID: <strong>{escape(created_notice['seat_token'])}</strong>"
            "</div>"
        )

    seat_rows = []
    for seat in list_seating():
        token_value = seat["seat_token"] if seat["seat_type"] != "vip" else "VIP PASS HIDDEN"
        claimed_value = seat["claimed_username"] or "Open"
        seat_rows.append(
            "<tr>"
            f"<td>{escape(seat['seat_code'])}</td>"
            f"<td>{escape(seat['seat_type'])}</td>"
            f"<td>{escape(seat['status'])}</td>"
            f"<td>{escape(claimed_value)}</td>"
            f"<td>{escape(token_value)}</td>"
            "</tr>"
        )

    vip_options = []
    for vip in list_open_vip_seats():
        vip_options.append(f"<option value='{escape(vip['seat_code'])}'>{escape(vip['seat_code'])}</option>")
    vip_options_html = "".join(vip_options) or "<option value='' disabled selected>No VIP seats available</option>"

    page = load_page(STATIC_DIR / "admin_seating.html")
    page = page.replace("{{CREATED_NOTICE}}", notice_block)
    page = page.replace("{{VIP_OPTIONS}}", vip_options_html)
    page = page.replace("{{SEAT_ROWS}}", "".join(seat_rows) or "<tr><td colspan='5'>No seats</td></tr>")
    return page


@app.post("/admin/seating/create-user")
def create_user_for_seat(
    request: Request,
    username: str = Form(...),
    display_name: str = Form(...),
    seat_code: str = Form(...),
) -> Response:
    if not session_is_valid(request, "admin"):
        return RedirectResponse(url="/portal/login", status_code=303)

    created = create_user_with_reserved_seat(username, display_name, seat_code)
    if created:
        request.session["created_user_notice"] = created
    else:
        request.session["created_user_notice"] = {
            "username": "creation-failed",
            "password": "n/a",
            "ticket_code": "n/a",
            "seat_code": "no-seat",
            "seat_token": "Seat unavailable",
        }

    return RedirectResponse(url="/admin/seating", status_code=303)


@app.get("/internal/garage", response_class=HTMLResponse)
def internal_garage(request: Request) -> str:
    if not session_is_valid(request, "admin"):
        return RedirectResponse(url="/portal/login", status_code=303)
    return load_page(CONTENT_DIR / "internal" / "garage.html")


def render_seating_page(request: Request, message: str = "") -> str:
    user = get_user_profile(request.session["user_id"])
    if not user:
        request.session.clear()
        return load_page(CONTENT_DIR / "portal" / "login.html")

    claimed_seat = get_user_claimed_seat(request.session["user_id"])

    claimed_block = ""
    if claimed_seat:
        claimed_block = (
            "<div class='message'>"
            f"Stadium seat: <strong>{escape(claimed_seat['seat_code'])}</strong><br>"
            f"Seating ID: <strong>{escape(claimed_seat['seat_token'])}</strong>"
            "</div>"
        )
    else:
        claimed_block = (
            "<div class='message'>"
            "No seat has been assigned yet. Return to the admin panel to reserve one."
            "</div>"
        )

    page = load_page(STATIC_DIR / "seating.html")
    page = page.replace("{{DISPLAY_NAME}}", escape(user["display_name"]))
    page = page.replace("{{RACE_NAME}}", escape(user["race_name"]))
    page = page.replace("{{TICKET_ID}}", escape(user["ticket_code"]))
    page = page.replace("{{MESSAGE}}", escape(message))
    page = page.replace("{{CLAIMED_BLOCK}}", claimed_block)
    return page


@app.get("/seating", response_class=HTMLResponse)
def seating_page(request: Request) -> str:
    if not session_is_valid(request):
        return RedirectResponse(url="/portal/login", status_code=303)
    if request.session.get("role") != "user":
        return RedirectResponse(url="/admin", status_code=303)
    return render_seating_page(request)


