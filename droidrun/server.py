"""
Price Comparison Server v4
Captures agent output to extract prices from complete() calls
"""

import asyncio
import uuid
import re
import os
import sys
import io
from datetime import datetime
from pathlib import Path
from contextlib import redirect_stdout
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

from droidrun import DroidAgent, DroidrunConfig, AgentConfig, AdbTools
from llama_index.llms.litellm import LiteLLM

# Store for active tasks and agent outputs
tasks = {}
connected_clients = {}
agent_outputs = {}

app = FastAPI(title="Price Comparison API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="web"), name="static")

class SearchRequest(BaseModel):
    product: str
    app: Optional[str] = None

class OrderRequest(BaseModel):
    product: str
    app: str

def get_llm():
    return LiteLLM(
        model="openrouter/google/gemini-2.0-flash-001",
        api_key=os.environ.get("OPENROUTER_API_KEY")
    )

def get_search_prompt(app_name: str, product: str) -> str:
    prompts = {
        "flipkart": f"""Find price of '{product}' on Flipkart.

1. open_app('Flipkart')
2. Wait 2 sec
3. Tap search bar
4. Type '{product}'
5. Tap search/Enter
6. LOOK at first result - find price (₹XXX)
7. Call: complete(success=True, reason="PRICE: ₹XXX for [product]")

If stuck, use system_button('Back')
""",
        "amazon": f"""Find price of '{product}' on Amazon.

1. open_app('Amazon Shopping')  
2. Wait 2 sec
3. Tap search bar
4. Type '{product}'
5. Tap search
6. Look at FIRST result price
7. Call: complete(success=True, reason="PRICE: ₹XXX for [product]")
""",
        "blinkit": f"""Find price of '{product}' on Blinkit.

1. open_app('Blinkit')
2. Tap search
3. Type '{product}'
4. Look at first product price
5. Call: complete(success=True, reason="PRICE: ₹XXX for [product]")
""",
        "zepto": f"""Find price of '{product}' on Zepto.

1. open_app('Zepto')
2. Tap search
3. Type '{product}'  
4. Look at first product price
5. Call: complete(success=True, reason="PRICE: ₹XXX for [product]")
"""
    }
    return prompts.get(app_name, "")

class OutputCapture:
    """Capture print output during agent run"""
    def __init__(self):
        self.output = []
        self.original_stdout = sys.stdout
        
    def write(self, text):
        self.output.append(text)
        self.original_stdout.write(text)
        
    def flush(self):
        self.original_stdout.flush()
        
    def get_output(self):
        return ''.join(self.output)

async def check_device() -> bool:
    try:
        proc = await asyncio.create_subprocess_exec(
            'adb', 'devices',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        output = stdout.decode()
        for line in output.split('\n'):
            if 'device' in line and 'List' not in line and 'unauthorized' not in line:
                return True
        return False
    except:
        return False

async def search_app(app_name: str, product: str, task_id: str) -> dict:
    print(f"\n{'='*50}")
    print(f"🔍 Searching {app_name.upper()} for '{product}'")
    print(f"{'='*50}")
    
    if not await check_device():
        return {
            "app": app_name,
            "product": product,
            "found": False,
            "price": None,
            "error": "Phone not connected"
        }
    
    prompt = get_search_prompt(app_name, product)
    capture = OutputCapture()
    
    try:
        llm = get_llm()
        tools = AdbTools()
        
        agent = DroidAgent(
            prompt,
            config=DroidrunConfig(agent=AgentConfig(max_steps=18)),
            llms=llm,
            tools=tools
        )
        
        # Capture output during run
        old_stdout = sys.stdout
        sys.stdout = capture
        
        try:
            result = await agent.run()
        finally:
            sys.stdout = old_stdout
        
        # Get captured output
        output = capture.get_output()
        
        # Also check agent_outputs if stored
        full_output = output + str(result) if result else output
        
        print(f"📋 Captured {len(output)} chars of output")
        
        # Extract price from captured output
        price = extract_price_from_output(full_output)
        product_name = extract_product_from_output(full_output, product)
        
        if price:
            print(f"✅ Found price: ₹{price}")
            return {
                "app": app_name,
                "product": product_name,
                "found": True,
                "price": price
            }
        else:
            print(f"⚠️ No price found")
            return {
                "app": app_name,
                "product": product,
                "found": False,
                "price": None,
                "error": "Price not found"
            }
            
    except Exception as e:
        sys.stdout = old_stdout if 'old_stdout' in dir() else sys.stdout
        print(f"❌ Error: {str(e)[:100]}")
        return {
            "app": app_name,
            "product": product,
            "found": False,
            "price": None,
            "error": str(e)[:50]
        }

def extract_price_from_output(text: str) -> Optional[str]:
    """Extract price from agent output looking for PRICE: pattern"""
    if not text:
        return None
    
    # Pattern 1: PRICE: ₹XXX pattern from complete() calls
    match = re.search(r'PRICE:\s*₹?\s*([\d,]+(?:\.\d{1,2})?)', text, re.IGNORECASE)
    if match:
        return match.group(1).replace(',', '')
    
    # Pattern 2: "The price is ₹XXX"
    match = re.search(r'price\s+is\s+₹?\s*([\d,]+)', text, re.IGNORECASE)
    if match:
        return match.group(1).replace(',', '')
    
    # Pattern 3: ₹XXX in the text
    matches = re.findall(r'₹\s*([\d,]+)', text)
    for m in matches:
        try:
            val = float(m.replace(',', ''))
            if 10 <= val <= 50000:
                return m.replace(',', '')
        except:
            pass
    
    return None

def extract_product_from_output(text: str, default: str) -> str:
    """Extract product name from output"""
    match = re.search(r'for\s+([^"\n]+?)(?:\"|$|\n|\))', text, re.IGNORECASE)
    if match:
        name = match.group(1).strip()
        if 3 < len(name) < 100:
            return name
    return default

async def broadcast_update(task_id: str, message: dict):
    if task_id in connected_clients:
        for ws in connected_clients[task_id]:
            try:
                await ws.send_json(message)
            except:
                pass

@app.get("/")
async def root():
    return FileResponse("web/index.html")

@app.post("/search")
async def search_product(request: SearchRequest):
    task_id = str(uuid.uuid4())
    tasks[task_id] = {"status": "pending", "product": request.product, "results": {}}
    
    print(f"\n🚀 Search: '{request.product}'")
    
    if request.app:
        asyncio.create_task(run_single_search(task_id, request.product, request.app))
    else:
        asyncio.create_task(run_search(task_id, request.product))
    
    return {"task_id": task_id, "status": "started"}

async def run_single_search(task_id: str, product: str, app: str):
    tasks[task_id]["status"] = "searching"
    await broadcast_update(task_id, {
        "status": "searching",
        "current_app": app,
        "message": f"Searching {app.capitalize()}..."
    })
    
    result = await search_app(app, product, task_id)
    tasks[task_id]["results"][app] = result
    tasks[task_id]["status"] = "completed"
    
    await broadcast_update(task_id, {
        "status": "completed",
        "app_complete": app,
        "result": result,
        "results": {app: result}
    })

async def run_search(task_id: str, product: str):
    apps = ["flipkart", "amazon", "blinkit", "zepto"]
    
    tasks[task_id]["status"] = "searching"
    await broadcast_update(task_id, {"status": "searching", "message": "Starting..."})
    
    for app in apps:
        if not await check_device():
            tasks[task_id]["results"][app] = {"app": app, "found": False, "error": "Phone disconnected"}
            await broadcast_update(task_id, {"status": "searching", "app_complete": app, "result": tasks[task_id]["results"][app]})
            continue
        
        await broadcast_update(task_id, {
            "status": "searching",
            "current_app": app,
            "message": f"Searching {app.capitalize()}..."
        })
        
        result = await search_app(app, product, task_id)
        tasks[task_id]["results"][app] = result
        
        await broadcast_update(task_id, {
            "status": "searching",
            "app_complete": app,
            "result": result
        })
        
        await asyncio.sleep(2)
    
    # Best price
    best = None
    best_price = float('inf')
    for app, res in tasks[task_id]["results"].items():
        if res.get("found") and res.get("price"):
            try:
                p = float(str(res["price"]).replace(',', ''))
                if p < best_price:
                    best_price = p
                    best = {"app": app, "price": res["price"]}
            except:
                pass
    
    tasks[task_id]["status"] = "completed"
    tasks[task_id]["best"] = best
    
    await broadcast_update(task_id, {
        "status": "completed",
        "results": tasks[task_id]["results"],
        "best": best
    })

@app.get("/status/{task_id}")
async def get_status(task_id: str):
    if task_id not in tasks:
        return {"error": "Task not found"}
    return tasks[task_id]

@app.get("/check-device")
async def api_check_device():
    return {"connected": await check_device()}

@app.post("/order")
async def place_order(request: OrderRequest):
    task_id = str(uuid.uuid4())
    prompt = f"""Order '{request.product}' from {request.app.capitalize()} with COD.

1. Open {request.app.capitalize()}
2. Search '{request.product}'
3. Add first result to cart
4. Checkout
5. Select Cash on Delivery
6. Use default address
7. Place order
8. complete(success=True, reason="Order placed!")
"""
    asyncio.create_task(run_order(task_id, request.app, prompt))
    return {"task_id": task_id, "status": "ordering"}

async def run_order(task_id: str, app: str, prompt: str):
    try:
        llm = get_llm()
        agent = DroidAgent(
            prompt,
            config=DroidrunConfig(agent=AgentConfig(max_steps=40)),
            llms=llm,
            tools=AdbTools()
        )
        result = await agent.run()
        await broadcast_update(task_id, {"status": "completed", "app": app, "result": str(result)})
    except Exception as e:
        await broadcast_update(task_id, {"status": "error", "app": app, "error": str(e)})

@app.websocket("/ws/{task_id}")
async def websocket_endpoint(websocket: WebSocket, task_id: str):
    await websocket.accept()
    if task_id not in connected_clients:
        connected_clients[task_id] = []
    connected_clients[task_id].append(websocket)
    
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if task_id in connected_clients:
            connected_clients[task_id].remove(websocket)

if __name__ == "__main__":
    import uvicorn
    print("=" * 60)
    print("🎯 PriceHunter Server v4 - Output Capture Edition")
    print("=" * 60)
    print("📱 Connect phone via USB (USB debugging ON)")
    print("🌐 http://localhost:8000")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=8000)
