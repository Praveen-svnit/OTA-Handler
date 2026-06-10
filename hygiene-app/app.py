"""
BDC Hygiene control panel — a tiny local web app.

Start it (Start Hygiene App.bat) and it opens a page in your browser with a
button per hygiene field. It runs on YOUR pc because it rides your logged-in
Chrome. Nothing here is public.
"""

import asyncio
import os
import subprocess
import sys
import threading
import webbrowser

from flask import Flask, jsonify, request, send_from_directory

import scrape_core
from scrapers import SCRAPERS, BY_ID, CATEGORIES

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("APP_PORT", "8765"))
CHROME_PROFILE = os.path.join(os.path.expanduser("~"), "bdc-profile")

app = Flask(__name__, static_folder=None)

# Single-user shared progress state.
PROGRESS = {"running": False, "scraper": None, "stage": "idle", "total": 0,
            "done": 0, "message": "", "result": None, "error": None, "stop": False,
            "batch": ""}


def find_chrome():
    for pth in [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]:
        if os.path.exists(pth):
            return pth
    return None


@app.route("/")
def index():
    return send_from_directory(HERE, "index.html")


@app.route("/api/scrapers")
def api_scrapers():
    return jsonify({
        "categories": CATEGORIES,
        "scrapers": [{k: s.get(k) for k in ("id", "label", "desc", "status", "cat")}
                     for s in SCRAPERS],
    })


@app.route("/api/status")
def api_status():
    sess = asyncio.run(scrape_core.session_status())
    return jsonify({"chrome": sess["chrome"], "logged_in": sess["logged_in"], "run": PROGRESS})


@app.route("/api/open-chrome", methods=["POST"])
def api_open_chrome():
    chrome = find_chrome()
    if not chrome:
        return jsonify({"ok": False, "error": "chrome.exe not found"}), 400
    subprocess.Popen([
        chrome,
        f"--remote-debugging-port={scrape_core.CDP_PORT}",
        f"--user-data-dir={CHROME_PROFILE}",
        "https://admin.booking.com",
    ])
    return jsonify({"ok": True})


def _run_thread(scraper, ids, limit):
    PROGRESS.update({"running": True, "scraper": scraper["id"], "stage": "starting",
                     "done": 0, "total": 0, "message": "Starting…", "result": None,
                     "error": None, "stop": False, "batch": ""})
    try:
        res = asyncio.run(scrape_core.run_scraper(scraper, progress=PROGRESS, ids=ids, limit=limit))
        PROGRESS["result"] = res
    except Exception as e:
        PROGRESS["error"] = str(e)
        PROGRESS["message"] = str(e)
    finally:
        PROGRESS["running"] = False


def _run_category_thread(members, ids, limit, cat_label):
    """Run all scrapers in a category as ONE combined pass — per property, fetch
    every member's fields, then move to the next property."""
    PROGRESS.update({"running": True, "scraper": None, "stage": "starting",
                     "done": 0, "total": 0, "message": f"Starting {cat_label} batch…",
                     "result": None, "error": None, "stop": False, "batch": ""})
    try:
        res = asyncio.run(scrape_core.run_combined(
            members, progress=PROGRESS, ids=ids, limit=limit, label=cat_label))
        PROGRESS["result"] = res
    except Exception as e:
        PROGRESS["error"] = str(e)
        PROGRESS["message"] = str(e)
    finally:
        PROGRESS["running"] = False


@app.route("/api/run", methods=["POST"])
def api_run():
    if PROGRESS["running"]:
        return jsonify({"ok": False, "error": "A scrape is already running."}), 409
    body = request.get_json(force=True, silent=True) or {}
    scraper = BY_ID.get(body.get("id"))
    if not scraper:
        return jsonify({"ok": False, "error": "Unknown scraper."}), 400
    if scraper["status"] != "live" or not scraper.get("fetch"):
        return jsonify({"ok": False, "error": f"{scraper['label']} isn't available yet."}), 400
    ids = [x.strip() for x in str(body.get("ids", "")).replace(",", " ").split() if x.strip()]
    limit = int(body.get("limit") or 0)
    threading.Thread(target=_run_thread, args=(scraper, ids or None, limit), daemon=True).start()
    return jsonify({"ok": True})


@app.route("/api/run-category", methods=["POST"])
def api_run_category():
    if PROGRESS["running"]:
        return jsonify({"ok": False, "error": "A scrape is already running."}), 409
    body = request.get_json(force=True, silent=True) or {}
    cat = body.get("cat")
    members = [s for s in SCRAPERS
               if s.get("cat") == cat and s["status"] == "live" and s.get("fetch")]
    if not members:
        return jsonify({"ok": False, "error": "No runnable scrapers in this category."}), 400
    cat_label = next((c["label"] for c in CATEGORIES if c["key"] == cat), cat)
    ids = [x.strip() for x in str(body.get("ids", "")).replace(",", " ").split() if x.strip()]
    limit = int(body.get("limit") or 0)
    threading.Thread(target=_run_category_thread,
                     args=(members, ids or None, limit, cat_label), daemon=True).start()
    return jsonify({"ok": True})


@app.route("/api/progress")
def api_progress():
    return jsonify(PROGRESS)


@app.route("/api/stop", methods=["POST"])
def api_stop():
    if not PROGRESS["running"]:
        return jsonify({"ok": False, "error": "Nothing is running."}), 400
    PROGRESS["stop"] = True
    PROGRESS["message"] = "Stopping… finishing the current property and saving."
    return jsonify({"ok": True})


def main():
    url = f"http://localhost:{PORT}"
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    print(f"\n  BDC Hygiene control panel → {url}\n  (close this window to stop)\n")
    app.run(host="127.0.0.1", port=PORT, threaded=True)


if __name__ == "__main__":
    main()
