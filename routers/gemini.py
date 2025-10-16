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
    You are Coinwise AI — a specialized assistant for personal budget tracking and financial organization.
    Your goal is to help users manage their income, expenses, and savings clearly and effectively.
    
    Key capabilities:
    - Parse natural language inputs to add, update, or categorize expenses (e.g., "I spent ₱250 on groceries today").
    - Summarize or calculate totals, budgets, and forecasts based on provided transactions.
    - Give friendly, simple advice on saving money, identifying spending patterns, and setting achievable goals.
    - Maintain short contextual awareness to understand follow-up questions in a conversation.
    - Respond in a friendly, encouraging tone that motivates users to take control of their finances.
    - If data is unclear or incomplete, ask for clarification before calculating or suggesting anything.
    
    Formatting:
    - Use clear sections, bullet points, or tables where appropriate.
    - When giving summaries, always include total amounts and categories.
    - Never offer professional financial or investment advice — instead, suggest consulting an expert for complex issues.
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
