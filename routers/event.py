from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, Query
from typing import Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime, timezone, timedelta
import asyncio

from core.security import get_current_user, decode_token
from database import get_db
from sqlalchemy.orm import Session
from models.device import Device
from models.user import User

router = APIRouter()

TZ_MUNICH = timezone(timedelta(hours=2))

def now_str() -> str:
    return datetime.now(TZ_MUNICH).strftime('%Y-%m-%d %H:%M:%S')

class EventIn(BaseModel):
    deviceid: str = Field(..., description='device unique id')
    devicename: str = Field(..., description='device name')
    status: str = Field(..., description='status: active; error; offline')
    type: str = Field(..., description='event type: stateChange; alarm; info')
    eventtime: Optional[str] = Field(None, description='YYYY-MM-DD HH:MM:SS (can ignore)')

class EventOut(BaseModel):
    deviceid: str
    devicename: str
    status: str
    type: str
    eventtime: str

EVENTS: dict[str, EventOut] = {}
EVENTS_LOCK = asyncio.Lock()

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        async with self._lock:
            self.active_connections.append(websocket)

    async def disconnect(self, websocket: WebSocket):
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)

    async def broadcast_json(self, data: Any):
        stale: list[WebSocket] = []
        async with self._lock:
            for ws in list(self.active_connections):
                try:
                    await ws.send_json(data)
                except Exception:
                    stale.append(ws)
            for s in stale:
                if s in self.active_connections:
                    self.active_connections.remove(s)

manager = ConnectionManager()

def normalize_time(ts: Optional[str]) -> str:
    if not ts:
        return now_str()
    try:
        try:
            dt = datetime.strptime(ts, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TZ_MUNICH)
        else:
            dt = dt.astimezone(TZ_MUNICH)
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        return now_str()

@router.get('', response_model=list[EventOut])
async def get_events(current_user: User = Depends(get_current_user)):
    async with EVENTS_LOCK:
        return list(EVENTS.values())

@router.post('', response_model=EventOut)
async def add_events(event: EventIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    out = EventOut(
        deviceid = event.deviceid.strip(),
        devicename = event.devicename.strip(),
        status = event.status.strip(),
        type = event.type.strip(),
        eventtime = normalize_time(event.eventtime)
    )
    async with EVENTS_LOCK:
        EVENTS[out.deviceid] = out

    await manager.broadcast_json({"kind": "event", "payload": out.dict()})

    try:
        dev = (
            db.query(Device)
            .filter(Device.Code == out.deviceid)
            .first()
        )
        if not dev and out.deviceid.isdigit():
            dev = (
                db.query(Device)
                .filter(Device.Code == int(out.deviceid))
                .first()
            )
        if dev:
            dev.Status = out.status
            dev.UpdatedDate = datetime.strptime(out.eventtime, '%Y-%m-%d %H:%M:%S')
            db.commit()
    except Exception:
        db.rollback()

    return out

async def _validate_ws_token(token: str, db: Session) -> User:
    try:
        payload = decode_token(token)
        username = payload.get('sub')
        if not username:
            raise HTTPException(status_code=401, detail='Token invalide')
        user = db.query(User).filter(User.Account == username).first()
        if not user:
            raise HTTPException(status_code=401, detail='User not exist')
        return user
    except Exception:
        raise

@router.websocket('/ws')
async def ws_events(websocket: WebSocket, token: Optional[str] = Query(default=None)):
    from database import SessionLocal
    db = SessionLocal()
    try:
        if not token:
            await websocket.close(code=4401)
            return
        _ = await asyncio.get_event_loop().run_in_executor(None, _validate_ws_token, token, db)
    except Exception:
        await websocket.close(code=4401)
        db.close()
        return
    await manager.connect(websocket)
    try:
        async with EVENTS_LOCK:
            snapshot = [e.dict() for e in EVENTS.values()]
        await websocket.send_json({"kind": "snapshot", "payload": snapshot})

        while True:
            try:
                msg = await websocket.receive_text()
                if msg == 'ping':
                    await websocket.send_json({"kind": "pong", "time": now_str()})
            except Exception:
                break
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(websocket)
        db.close()
