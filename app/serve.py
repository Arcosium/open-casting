import json
import logging
import os
import socket

import uvicorn


class JsonFormatter(logging.Formatter):
    def format(self, record):
        message = record.getMessage()
        try:
            payload = json.loads(message)
        except (ValueError, TypeError):
            payload = {"event": "server", "message": message}
        return json.dumps(payload, ensure_ascii=False)


def main():
    sock = None
    host = "0.0.0.0" if os.getenv("PORT") else "127.0.0.1"
    ports = [int(os.environ["PORT"])] if os.getenv("PORT") else range(8900, 9000)
    for port in ports:
        candidate = socket.socket()
        try:
            candidate.bind((host, port))
            candidate.listen(128)
            sock = candidate
            break
        except OSError:
            candidate.close()
    if sock is None:
        raise SystemExit("No free port in 8900-8999")
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for handler in logging.getLogger().handlers:
        handler.setFormatter(JsonFormatter())
    from .main import create_app
    logging.info(json.dumps({"event": "listening", "url": f"http://{host}:{port}"}))
    server = uvicorn.Server(uvicorn.Config(create_app(), host=host, port=port, access_log=False, log_config=None))
    try:
        server.run(sockets=[sock])
    finally:
        sock.close()


if __name__ == "__main__":
    main()
