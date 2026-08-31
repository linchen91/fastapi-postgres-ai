import React, { useEffect, useMemo } from 'react'
import { useEvents } from '../eventsContext'

function parseTime(s) {
    if (!s) return new Date();
    const d = new Date(s.replace(' ', 'T'));
    return isNaN(d.getTime()) ? new Date() : d;
}

const Events = () => {
    const { events = [], markRead } = useEvents();

    useEffect(() => {
        if (markRead) markRead();
    }, [markRead]);

    const sorted = useMemo(() => {
        return [...events].sort((a,b) => parseTime(b.eventtime) -  parseTime(a.eventtime));
    }, [events]);

    return (
        <div className='container-fluid p-3'>
            <div className='d-flex justify-content-between align-items-center mb-3'>
                <h3 className='m0'>Events</h3>
                <small className='text-muted'>(only one for each device)</small>
            </div>
            <div className='table-responsive'>
                <table className='table table-bordered table-hover table-sm align-middle'>
                    <thead className='table-light'>
                        <tr>
                            <th style={{ minWidth: 120 }}>Device Id</th>
                            <th style={{ minWidth: 160 }}>Device Name</th>
                            <th style={{ minWidth: 100 }}>Status</th>
                            <th style={{ minWidth: 170 }}>Event Time</th>
                            <th style={{ minWidth: 140 }}>Type</th>
                        </tr>
                    </thead>
                    <tbody>
                        {sorted.map(e => (
                            <tr key={e.deviceid}>
                                <td>{e.deviceid}</td>
                                <td>{e.devicename}</td>
                                <td>
                                    <span className={
                                        e.status === 'error' ? 'badge text-bg-danger' :
                                        e.status === 'offline' ? 'badge text-bg-secondary' : 'badge text-bg-success' 
                                    }>{e.status}</span>
                                </td>
                                <td>{e.eventtime}</td>
                                <td>{e.type}</td>
                            </tr>
                        ))}{sorted.length === 0 && <tr><td colSpan='5' className='text-center text-muted py-4'>No Current Event</td></tr>}
                    </tbody>
                </table>
            </div>
        </div>
    )
}

export default Events;