from fusionframe import App, cors_middleware


app = App(title="fusionframe React API Example", version="0.1.0")
app.use(
    cors_middleware(
        allow_origins=["http://localhost:5173"],
        allow_credentials=True,
    )
)


@app.get("/api/health")
async def health(request):
    return {"status": "ok", "framework": "fusionframe"}


@app.get("/api/tasks")
async def tasks(request):
    return {
        "items": [
            {"id": 1, "title": "Connect React app"},
            {"id": 2, "title": "Verify CORS and auth flow"},
            {"id": 3, "title": "Ship product features"},
        ]
    }
