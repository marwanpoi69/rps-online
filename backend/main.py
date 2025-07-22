from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session
import uvicorn
import json
import uuid
import base64
import cv2
import numpy as np
from datetime import datetime
from typing import Dict, List, Optional
import asyncio
import logging

from models.game import Game, GameState
from models.player import Player, PlayerMove
from services.gesture_detector import GestureDetector
from services.game_manager import GameManager
from utils.logging_utils import setup_logging, log_gesture_detection, log_communication, log_game_result

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)

# Import database module
from database import create_db_and_tables

# FastAPI app
app = FastAPI(title="Rock Paper Scissors Online API", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global instances
gesture_detector = GestureDetector()
game_manager = GameManager()

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.room_connections: Dict[str, List[str]] = {}
        self.player_rooms: Dict[str, str] = {}

    async def connect(self, websocket: WebSocket, player_id: str):
        await websocket.accept()
        self.active_connections[player_id] = websocket
        logger.info(f"Player {player_id} connected")

    def disconnect(self, player_id: str):
        if player_id in self.active_connections:
            del self.active_connections[player_id]
        
        if player_id in self.player_rooms:
            room_id = self.player_rooms[player_id]
            if room_id in self.room_connections:
                self.room_connections[room_id] = [pid for pid in self.room_connections[room_id] if pid != player_id]
                if not self.room_connections[room_id]:
                    del self.room_connections[room_id]
            del self.player_rooms[player_id]
        
        logger.info(f"Player {player_id} disconnected")

    def join_room(self, player_id: str, room_id: str):
        if room_id not in self.room_connections:
            self.room_connections[room_id] = []
        
        if len(self.room_connections[room_id]) < 2:
            self.room_connections[room_id].append(player_id)
            self.player_rooms[player_id] = room_id
            return True
        return False

    async def send_to_player(self, player_id: str, message: dict):
        if player_id in self.active_connections:
            await self.active_connections[player_id].send_text(json.dumps(message))

    async def broadcast_to_room(self, room_id: str, message: dict, exclude_player: Optional[str] = None):
        if room_id in self.room_connections:
            for player_id in self.room_connections[room_id]:
                if exclude_player and player_id == exclude_player:
                    continue
                await self.send_to_player(player_id, message)

manager = ConnectionManager()

@app.on_event("startup")
def on_startup():
    create_db_and_tables()

@app.get("/")
async def root():
    return {"message": "Rock Paper Scissors Online API"}

@app.post("/create-room")
async def create_room():
    try:
        room_id = str(uuid.uuid4())[:8].upper()
        logger.info(f"Attempting to create room with ID: {room_id}")
        
        game = game_manager.create_game(room_id)
        if not game:
            logger.error(f"Failed to create game for room: {room_id}")
            raise HTTPException(status_code=500, detail="Failed to create game")
            
        logger.info(f"Successfully created room with ID: {room_id}")
        return {"room_id": room_id}
    except Exception as e:
        logger.error(f"Error creating room: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to create room. Please try again.")

@app.get("/room/{room_id}/status")
async def get_room_status(room_id: str):
    if room_id not in manager.room_connections:
        raise HTTPException(status_code=404, detail="Room not found")
    
    players_count = len(manager.room_connections[room_id])
    game_state = game_manager.get_game_state(room_id)
    
    return {
        "room_id": room_id,
        "players_count": players_count,
        "max_players": 2,
        "game_state": game_state.value if game_state else "waiting"
    }

@app.websocket("/ws/{room_id}/{player_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str, player_id: str):
    await manager.connect(websocket, player_id)
    
    try:
        if manager.join_room(player_id, room_id):
            players_in_room = len(manager.room_connections[room_id])
            
            await manager.broadcast_to_room(room_id, {
                "type": "player_joined",
                "player_id": player_id,
                "players_count": players_in_room
            })
            
            if players_in_room == 2:
                game_manager.start_game(room_id)
                await manager.broadcast_to_room(room_id, {
                    "type": "game_start",
                    "message": "Game starting! Get ready..."
                })
                await start_countdown(room_id)
        else:
            await manager.send_to_player(player_id, {
                "type": "error",
                "message": "Room is full"
            })
            return

        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            await handle_websocket_message(room_id, player_id, message)
            
    except WebSocketDisconnect:
        manager.disconnect(player_id)
        
        if room_id in manager.room_connections:
            await manager.broadcast_to_room(room_id, {
                "type": "player_left",
                "player_id": player_id,
                "players_count": len(manager.room_connections[room_id])
            })
            game_manager.end_game(room_id)

async def handle_websocket_message(room_id: str, player_id: str, message: dict):
    message_type = message.get("type")
    start_time = datetime.now()
    
    if message_type == "video_frame":
        await handle_video_frame(room_id, player_id, message)
    elif message_type == "player_ready":
        await handle_player_ready(room_id, player_id)
    elif message_type == "restart_game":
        await handle_restart_game(room_id, player_id)
    
    latency_ms = (datetime.now() - start_time).total_seconds() * 1000
    log_communication(message_type, room_id, latency_ms, len(json.dumps(message)))

async def handle_video_frame(room_id: str, player_id: str, message: dict):
    try:
        frame_data = message.get("frame")
        if not frame_data:
            return
            
        if frame_data.startswith("data:image"):
            frame_data = frame_data.split(",")[1]
        
        img_bytes = base64.b64decode(frame_data)
        nparr = np.frombuffer(img_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if frame is None:
            return
        
        detection_start = datetime.now()
        gesture, confidence = gesture_detector.detect_gesture(frame)
        processing_time = (datetime.now() - detection_start).total_seconds() * 1000
        
        log_gesture_detection(player_id, gesture, confidence, processing_time)
        
        await manager.send_to_player(player_id, {
            "type": "gesture_detected",
            "gesture": gesture,
            "confidence": confidence
        })
        
        if game_manager.get_game_state(room_id) == GameState.PLAYING:
            if gesture != "none" and confidence > 0.7:
                success = game_manager.record_move(room_id, player_id, gesture)
                
                if success:
                    moves = game_manager.get_moves(room_id)
                    if len(moves) == 2:
                        await evaluate_round(room_id, moves)
        
        await manager.broadcast_to_room(room_id, {
            "type": "opponent_frame",
            "frame": frame_data,
            "player_id": player_id
        }, exclude_player=player_id)
        
    except Exception as e:
        logger.error(f"Error handling video frame: {e}")

async def handle_player_ready(room_id: str, player_id: str):
    game_manager.set_player_ready(room_id, player_id)
    
    await manager.broadcast_to_room(room_id, {
        "type": "player_ready",
        "player_id": player_id
    })
    
    if game_manager.both_players_ready(room_id):
        await start_round(room_id)

async def handle_restart_game(room_id: str, player_id: str):
    game_manager.restart_game(room_id)
    
    await manager.broadcast_to_room(room_id, {
        "type": "game_restarted",
        "message": "Game restarted! Get ready..."
    })
    
    await start_countdown(room_id)

async def start_countdown(room_id: str):
    for i in range(3, 0, -1):
        await manager.broadcast_to_room(room_id, {
            "type": "countdown",
            "count": i
        })
        await asyncio.sleep(1)
    
    await start_round(room_id)

async def start_round(room_id: str):
    game_manager.start_round(room_id)
    
    await manager.broadcast_to_room(room_id, {
        "type": "round_start",
        "message": "Show your move!"
    })
    
    # Set timeout for round (5 seconds)
    await asyncio.sleep(5)
    
    # Force evaluation if timeout
    moves = game_manager.get_moves(room_id)
    await evaluate_round(room_id, moves)

async def evaluate_round(room_id: str, moves: Dict[str, str]):
    round_start_time = datetime.now()
    
    result = game_manager.evaluate_moves(moves)
    game_manager.update_scores(room_id, result)
    scores = game_manager.get_scores(room_id)
    
    player_ids = list(moves.keys())
    log_game_result(
        room_id,
        moves.get(player_ids[0], "none"),
        moves.get(player_ids[1], "none"),
        result.get("winner"),
        (datetime.now() - round_start_time).total_seconds() * 1000
    )
    
    await manager.broadcast_to_room(room_id, {
        "type": "round_result",
        "moves": moves,
        "result": result,
        "scores": scores
    })
    
    game_manager.clear_moves(room_id)
    await asyncio.sleep(3)
    
    max_score = max(scores.values()) if scores else 0
    if max_score < 5:
        await manager.broadcast_to_room(room_id, {
            "type": "next_round",
            "message": "Get ready for next round!"
        })
        await start_countdown(room_id)
    else:
        winner = max(scores, key=scores.get)
        await manager.broadcast_to_room(room_id, {
            "type": "game_end",
            "winner": winner,
            "final_scores": scores
        })
        game_manager.end_game(room_id)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
