from fastapi import FastAPI
from pydantic import BaseModel
import google.generativeai as genai
from dotenv import load_dotenv
import os

# Load .env if present
load_dotenv()

# Configure the Gemini API
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

# Initialize FastAPI
app = FastAPI(title="Coinwise AI", description="AI assistant for personal budget tracking and finance management.")

# Define the request schema
class PromptRequest(BaseModel):
    prompt: str

# Initialize the Gemini model with a system instruction for finance/budget specialization
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

@app.post("/generate")
async def generate_text(request: PromptRequest):
    try:
        response = model.generate_content(request.prompt)
        return {"response": response.text}
    except Exception as e:
        return {"error": str(e)}

@app.get("/")
async def root():
    return {"message": "Welcome to Coinwise AI — your personal finance assistant. Use POST /generate to chat with it."}
