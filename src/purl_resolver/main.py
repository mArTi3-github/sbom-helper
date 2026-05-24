import uvicorn
from fastapi import FastAPI

from .config import settings
from .router import router

app = FastAPI(title="PURL Resolver")
app.include_router(router)


def main() -> None:
    uvicorn.run(
        "purl_resolver.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )


if __name__ == "__main__":
    main()