import { createContext, useContext, useEffect, useMemo, useRef, useState } from "react"
import { useConfig } from './configContext'
import axios from './axios'

const EventsContext = createContext(null);
export const useEvents = () => useContext(EventsContext);

function toWS(url) {
    return url ? url.replace(/^http/i, 'ws') : '';
}

function parseTime(s) {
    if (!s) return new Date();
    const d = new Date(s.replace(' ', 'T'));
    return isNaN(d.getTime()) ? new Date() : d;
}

export function EventsProvider({ token, children }) {
    const config = useConfig();
    const [events, setEvents] = useState([]);
    const [hasUnread, setHasUnread] = useState(false);
    const wsRef = useRef(null);
    const mapRef = useRef(new Map());

    const authHeaders = (t) => ({ headers: { Authorization: `Bearer ${t}` }});

    useEffect(() => {
        if (!token || !config?.API_BASE_URL) return;

        axios.get(`${config.API_BASE_URL}events`, authHeaders(token))
        .then(res => {
            const lst = Array.isArray(res.data) ? res.data : [];
            mapRef.current = new Map(lst.map(e => [e.deviceid, e]));
            const arr = Array.from(mapRef.current.values());
            setEvents(arr.sort((a,b) => parseTime(b.eventtime) -  parseTime(a.eventtime)));
        }).catch(() => { });

        const wsURL = `${toWS(config.API_BASE_URL)}events/ws?token=${encodeURIComponent(token)}`;
        let cancelled = false;
        let ping = null;
        let ws = null;

        // Defer WebSocket creation so StrictMode's synchronous
        // effect→cleanup→effect cycle cancels the first timer
        // before it ever fires.
        const timer = setTimeout(() => {
            if (cancelled) return;
            ws = new WebSocket(wsURL);
            wsRef.current = ws;

            ws.onmessage = (evt) => {
                try {
                    const msg = JSON.parse(evt.data);
                    if (msg.kind === 'snapshot' && Array.isArray(msg.payload)) {
                        mapRef.current = new Map(msg.payload.map(e => [e.deviceid, e]));
                        const arr = Array.from(mapRef.current.values());
                        setEvents(arr.sort((a,b) => parseTime(b.eventtime) -  parseTime(a.eventtime)));
                    } else if (msg.kind === 'event' && msg.payload) {
                        mapRef.current.set(msg.payload.deviceid, msg.payload);
                        const arr = Array.from(mapRef.current.values());
                        setEvents(arr.sort((a,b) => parseTime(b.eventtime) -  parseTime(a.eventtime)));
                        setHasUnread(true);
                    }
                } catch { }
            };

            ping = setInterval(() => { try { ws.send('ping'); } catch { } }, 30000);
            ws.onclose = () => clearInterval(ping);
        }, 0);

        return () => {
            cancelled = true;
            clearTimeout(timer);
            clearInterval(ping);
            try { ws?.close(); } catch { }
            if (wsRef.current === ws) wsRef.current = null;
        };
    }, [token, config?.API_BASE_URL]);

    const markRead = () => setHasUnread(false);

    const value = useMemo(() => ({ events, hasUnread, markRead }), [events, hasUnread]);

    return (
        <EventsContext.Provider value={value}>
            {children}
        </EventsContext.Provider>
    );
}