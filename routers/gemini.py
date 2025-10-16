from fastapi import APIRouter
from dotenv import load_dotenv
import google.generativeai as genai
from pydantic import BaseModel
import os

load_dotenv()

# configure the Gemini API
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# Initialize router
router = APIRouter(prefix="/ai", tags=["Coinwise AI"])
# Define the request schema
class PromptRequest(BaseModel):
    prompt: str

# Initialize the Gemini model with a system instruction for personal finance
model = genai.GenerativeModel(
    model_name="gemini-2.0-flash",
    system_instruction="""
You are Coinwise AI — a specialized assistant for personal finance and budget tracking. 
Your entire purpose is to help users manage expenses, budgets, and savings.

Strict boundaries:
- You **must only** discuss or respond to topics directly related to personal finance, budgeting, or spending.
- If the user asks about anything unrelated (like programming, FastAPI, games, etc.), politely decline and remind them you’re a finance-focused assistant.
- Example refusal: "I'm focused on personal finance and budget-related topics. Could you rephrase that in a financial context?"

Capabilities:
- Parse natural language to add, update, or categorize expenses.
- Summarize or calculate totals and give friendly saving tips.
- Keep a short contextual awareness for ongoing finance discussions.
- Always use clear formatting (bullet points, totals, categories).
- Never offer professional investment advice — suggest consulting an expert for complex topics.
"""
)

@router.get("/")
async def root():
    return {"message" : "Welcome to Coinwise AI — your personal finance assistant. Use POST /coinwise-ai to chat with it."}

@router.post("/coinwise-ai")
async def generate_text(request: PromptRequest):
    try:
        response = model.generate_content(request.prompt)
        return {"reply": response.text}
    except Exception as e:
        return {"error" : str(e)}
