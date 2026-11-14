from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import json
from brain_starter import answer  # Import your team's agent logic

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/api/chat")
async def chat_endpoint(request: Request):
    body = await request.json()
    prompt = body.get("prompt")

    def event_generator():
        yield f"data: {json.dumps({'type': 'status', 'message': 'Searching database via agent tools...'})}\n\n"

        # Run the agent logic connected to the real building.db
        result = answer(prompt)

        answer_text = result.get("answer", "No answer found.")
        for word in answer_text.split(" "):
            yield f"data: {json.dumps({'type': 'text_delta', 'content': word + ' '})}\n\n"

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)