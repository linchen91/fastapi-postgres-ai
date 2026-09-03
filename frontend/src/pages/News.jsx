import React, { useEffect, useState, useMemo, useRef, useCallback } from 'react'
import { useConfig } from '../configContext'
import axios from '../axios'
import { MapContainer, TileLayer, LayersControl, Marker, Tooltip, Popup, useMap } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { Modal } from 'bootstrap'

const positionIcon = L.divIcon({
    className: '',
    iconSize: [28, 40],
    iconAnchor: [14, 40],
    popupAnchor: [0, -40],
    tooltipAnchor: [0, -36],
    html: '<div style="margin:0;padding:0;width:28px;height:40px;line-height:0"><svg xmlns="http://www.w3.org/2000/svg" width="28" height="40" viewBox="0 0 28 40" style="display:block"><path fill="#e53935" d="M14 0C6.3 0 0 6.3 0 14c0 10.5 14 26 14 26s14-15.5 14-26C28 6.3 21.7 0 14 0z"/><circle fill="#fff" cx="14" cy="14" r="5"/></svg></div>'
})

function FitBounds({ point }) {
    const map = useMap()
    useEffect(() => {
        const timer = setTimeout(() => {
            map.invalidateSize()
            if (!point) return
            const bounds = L.latLngBounds([point])
            map.fitBounds(bounds, { padding: [40, 40], maxZoom: 13 })
        }, 300)
        return () => clearTimeout(timer)
    }, [point, map])
    return null
}

const VISUALIZATION_BADGES = {
    stau: { label: 'Stau', className: 'text-bg-danger' },
    unfall: { label: 'Unfall', className: 'text-bg-warning text-dark' },
    vorsicht: { label: 'Vorsicht', className: 'text-bg-info text-dark' },
    engstelle: { label: 'Engstelle', className: 'text-bg-secondary' },
    verbot_fahrzeuge: { label: 'Verbot', className: 'text-bg-dark' },
    baustelle: { label: 'Baustelle', className: 'text-bg-primary' },
    info: { label: 'Info', className: 'text-bg-light text-dark' },
}

const CATEGORY_LABELS = {
    gefahren: 'Gefahrenmeldungen',
    autobahnen: 'Autobahnen',
    strassen: 'Bundes-/Staatsstraßen',
    stadt_gemeinde_region: 'Städte/Gemeinden',
    ausland_grenzen: 'Ausland',
    warnmeldungen: 'Allg. Warnungen',
}

const News = () => {
    const config = useConfig()
    const [messages, setMessages] = useState([])
    const [summary, setSummary] = useState('')
    const [timestamp, setTimestamp] = useState('')
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState('')
    const [filterCategory, setFilterCategory] = useState('all')
    const [mapMsg, setMapMsg] = useState(null)
    const [mapOpen, setMapOpen] = useState(false)
    const modalRef = useRef(null)
    const bsModalRef = useRef(null)

    const closeMap = useCallback(() => {
        setMapOpen(false)
        setMapMsg(null)
    }, [])

    const openMap = (msg) => {
        if (!msg.lat && !msg.lon) return
        setMapMsg(msg)
        setMapOpen(true)
        const el = modalRef.current
        if (el) {
            if (!bsModalRef.current) {
                bsModalRef.current = new Modal(el)
                el.addEventListener('hidden.bs.modal', closeMap)
            }
            bsModalRef.current.show()
        }
    }

    const fetchNews = async (force = false) => {
        setLoading(true)
        setError('')
        try {
            const params = force ? { force: true, _t: Date.now() } : undefined
            const res = await axios.get(`${config.API_BASE_URL}news`, { params })
            setMessages(res.data.messages || [])
            setSummary(res.data.summary || '')
            setTimestamp(res.data.timestamp || '')
        } catch (err) {
            setError(err?.response?.data?.detail || err.message || 'Failed to load')
        } finally {
            setLoading(false)
        }
    }

    useEffect(() => {
        fetchNews()
    }, [config])

    const categories = useMemo(() => {
        const ids = [...new Set(messages.map(m => m.category_id))]
        return ids.map(id => ({ id, label: CATEGORY_LABELS[id] || id }))
    }, [messages])

    const filtered = useMemo(() => {
        if (filterCategory === 'all') return messages
        return messages.filter(m => m.category_id === filterCategory)
    }, [messages, filterCategory])

    const badge = (viz) => {
        const b = VISUALIZATION_BADGES[viz] || { label: viz, className: 'text-bg-secondary' }
        return <span className={`badge ${b.className}`}>{b.label}</span>
    }

    return (
        <div className='container-fluid p-3'>
            <div className='d-flex justify-content-between align-items-center mb-3'>
                <div>
                    <h3 className='m-0'>Traffic News</h3>
                    {summary && <small className='text-muted'>{summary}</small>}
                </div>
                <div className='d-flex align-items-center gap-2'>
                    {timestamp && <small className='text-muted'>Updated: {timestamp}</small>}
                    <button className='btn btn-sm btn-outline-primary' onClick={() => fetchNews(true)} disabled={loading}>
                        {loading ? 'Loading...' : 'Refresh'}
                    </button>
                </div>
            </div>

            {categories.length > 0 && (
                <div className='mb-3'>
                    <select
                        className='form-select form-select-sm w-auto'
                        value={filterCategory}
                        onChange={e => setFilterCategory(e.target.value)}
                    >
                        <option value='all'>All Categories</option>
                        {categories.map(c => (
                            <option key={c.id} value={c.id}>{c.label}</option>
                        ))}
                    </select>
                </div>
            )}

            {error && <div className='alert alert-danger py-2'>{error}</div>}

            <div className='table-responsive'>
                <table className='table table-bordered table-hover table-sm align-middle'>
                    <thead className='table-light'>
                        <tr>
                            <th style={{ minWidth: 130 }}>Category</th>
                            <th style={{ minWidth: 180 }}>Headline</th>
                            <th>Description</th>
                            <th style={{ minWidth: 60 }}>Time</th>
                            <th style={{ minWidth: 90 }}>Status</th>
                            <th style={{ minWidth: 50 }}>Both Dir.</th>
                        </tr>
                    </thead>
                    <tbody>
                        {filtered.map(m => {
                            const hasCoords = typeof m.lat === 'number' && typeof m.lon === 'number' && (m.lat !== 0 || m.lon !== 0)
                            return (
                                <tr key={m.id}>
                                    <td><small>{m.category}</small></td>
                                    <td>
                                        {hasCoords ? (
                                            <button className='btn btn-link btn-sm p-0 text-decoration-none'
                                                onClick={() => openMap(m)}
                                                title={`${m.lat.toFixed(5)}, ${m.lon.toFixed(5)}`}>
                                                {m.headline} <small className='text-muted'>&#x1f4cd;</small>
                                            </button>
                                        ) : m.headline}
                                    </td>
                                    <td><small>{m.description}</small></td>
                                    <td className='text-nowrap'>{m.time}</td>
                                    <td>{badge(m.visualization)}</td>
                                    <td className='text-center'>{m.both_directions ? '✓' : ''}</td>
                                </tr>
                            )
                        })}
                        {filtered.length === 0 && !loading && (
                            <tr><td colSpan='6' className='text-center text-muted py-4'>No traffic messages</td></tr>
                        )}
                    </tbody>
                </table>
            </div>

            <div className='modal fade' id='newsMapModal' ref={modalRef} tabIndex='-1' aria-hidden='true'>
                <div className='modal-dialog modal-xl modal-dialog-centered'>
                    <div className='modal-content'>
                        <div className='modal-header'>
                            <h5 className='modal-title'>{mapMsg?.headline || 'Location'}</h5>
                            <button type='button' className='btn-close' data-bs-dismiss='modal' aria-label='Close'></button>
                        </div>
                        <div className='modal-body p-0' style={{ height: 800 }}>
                            {mapOpen && mapMsg && (
                                <MapContainer
                                    center={[48.14, 11.56]}
                                    zoom={6}
                                    scrollWheelZoom
                                    style={{ height: '100%', width: '100%' }}
                                >
                                    <FitBounds point={[mapMsg.lat, mapMsg.lon]} />
                                    <LayersControl position='topright'>
                                        <LayersControl.BaseLayer checked name='Street'>
                                            <TileLayer
                                                attribution='&copy; OpenStreetMap contributors'
                                                url='https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png'
                                            />
                                        </LayersControl.BaseLayer>
                                        <LayersControl.BaseLayer name='Satellite'>
                                            <TileLayer
                                                attribution='&copy; Esri, Maxar, Earthstar Geographics'
                                                url='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'
                                            />
                                        </LayersControl.BaseLayer>
                                    </LayersControl>
                                    <Marker position={[mapMsg.lat, mapMsg.lon]} icon={positionIcon}>
                                        <Tooltip direction='top' offset={[0, -30]}>
                                            <div style={{ fontSize: 12, lineHeight: 1.2 }}>
                                                <div><b>{mapMsg.headline}</b></div>
                                                <div>{mapMsg.category}</div>
                                                <div>{mapMsg.time}</div>
                                            </div>
                                        </Tooltip>
                                        <Popup>
                                            <div style={{ minWidth: 200 }}>
                                                <div className='fw-bold mb-1'>{mapMsg.headline}</div>
                                                <div className='mb-1'><small>{mapMsg.description}</small></div>
                                                <div className='text-muted'>{mapMsg.time}</div>
                                            </div>
                                        </Popup>
                                    </Marker>
                                </MapContainer>
                            )}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    )
}

export default News
