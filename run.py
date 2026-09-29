"""Start the payroll checker on this computer and open it in the browser.
It only listens on 127.0.0.1, so no other computer on the network can reach it."""
import sys
import threading
import webbrowser

if sys.version_info < (3, 10):
    sys.exit("Python 3.10 or newer is needed. Download it from https://www.python.org/downloads/")

import uvicorn  # noqa: E402

PORT = 8000
URL = f"http://127.0.0.1:{PORT}"

if __name__ == "__main__":
    print(f"\nPayroll file check is running at {URL}")
    print("Leave this window open while you use it. Close it (or press Ctrl+C) to stop.\n")
    threading.Timer(1.5, lambda: webbrowser.open(URL)).start()
    uvicorn.run("app.main:app", host="127.0.0.1", port=PORT, log_level="warning")
