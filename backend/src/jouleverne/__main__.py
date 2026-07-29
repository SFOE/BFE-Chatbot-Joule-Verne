import uvicorn
from .app import app


def main():
    uvicorn.run(app, host="0.0.0.0", port=8000, timeout_keep_alive=125)


if __name__ == "__main__":
    main()
