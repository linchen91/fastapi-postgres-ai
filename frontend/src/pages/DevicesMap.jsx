import React, { useEffect, useState, useMemo } from 'react'
import { useConfig } from '../configContext'
import axios from '../axios'
import { Modal } from 'bootstrap'

import { MapContainer, TileLayer, Marker, Tooltip, Popup, useMap } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

const cameraSvg = encodeURIComponent(`
<svg version="1.0" id="Layer_1" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" 
	 width="800px" height="800px" viewBox="0 0 64 64" enable-background="new 0 0 64 64" xml:space="preserve">
<g>
	<path fill="#3167ad" d="M60,10H49.656l-6.828-6.828C42.078,2.422,41.062,2,40,2H24c-1.062,0-2.078,0.422-2.828,1.172L14.344,10H4
		c-2.211,0-4,1.789-4,4v44c0,2.211,1.789,4,4,4h56c2.211,0,4-1.789,4-4V14C64,11.789,62.211,10,60,10z M32,50
		c-8.836,0-16-7.164-16-16s7.164-16,16-16s16,7.164,16,16S40.836,50,32,50z"/>
	<circle fill="#3167ad" cx="32" cy="34" r="8"/>
</g>
</svg>
`);
const cameraIcon = new L.Icon({
    iconUrl: `data:image/svg+xml;charset=UTF-8,${cameraSvg}`,
    iconSize: [38, 38],
    iconAnchor: [19, 19],
    popupAnchor: [0, -20],
    tooltipAnchor: [0, -14],
    className: 'camera-marker'
});

function FitBounds({ points }) {
    const map = useMap();
    useEffect(() => {
        if (!points?.length) return;
        const bounds = L.latLngBounds(points.map(p => [p.Lat, p.Lng]));
        map.fitBounds(bounds, { padding: [40, 40] });
    }, [points, map]);
    return null;
}

const DevicesMap = () => {
    const config = useConfig();
    const [devices, setDevices] = useState([]);
    const [token, setToken] = useState('');
    const [liveUrl, setLiveUrl] = useState('');

    const defaultCenter = useMemo(() => [48.1402, 11.5583], []);

    const authHeaders = (t) => ({ headers: { Authorization: `Bearer ${t}` }});

    const loadDevices = async (t) => {
        try {
            const account = localStorage.getItem('account');
            const url = account
                ? `${config.API_BASE_URL}devices/?user_account=${account}`
                : `${config.API_BASE_URL}devices/`;
            const res = await axios.get(url, authHeaders(t));
            const list = (res.data || []).filter(d =>
                typeof d.Lat === 'number' && !Number.isNaN(d.Lat) &&
                typeof d.Lng === 'number' && !Number.isNaN(d.Lng)
            );
            setDevices(list);
        } catch (err) {
            console.error('loadDevices error: ', err);
        }
    };

    useEffect(() => {
        if (config) {
            const saveToken = localStorage.token;
            if (saveToken) {
                setToken(saveToken);
                loadDevices(saveToken);
            }
        }
    }, [config]);

    const points = devices.map(d => ({ Lat: d.Lat, Lng: d.Lng }));

    const openLive = (device) => {
        try {
            let url = '';
            if (device?.Params) {
                try {
                    const p = typeof device.Params === 'string' ? JSON.parse(device.Params) : device.Params;
                    url = p?.VideoStream || '';
                } catch {
                    url = device.Params;
                }
            }
            if (!url) {
                alert('No Device Parameters (Params.VideoStream).');
                return;
            }
            setLiveUrl(url);
            const modalE = document.getElementById('liveModal');
            if (modalE) {
                const modal = new Modal(modalE);
                modal.show();
            }
        } catch (e) {
            console.error('openLive error: ', e);
        }
    }

    return (
    <div className='cars'>
        <div className='card-body p-0' style={{ height: 'calc(100vh - 100px)' }}>
            <MapContainer
                center={defaultCenter}
                zoom={12}
                scrollWheelZoom
                style={{ height: '100%', width: '100%'}}
            >
                <TileLayer
                    attribution='&copy; OpenStreetMap contributors'
                    url='https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png'
                />
                <FitBounds points={points} />
                {devices.map(d => (
                    <Marker key={d.Id} position={[d.Lat, d.Lng]} icon={cameraIcon}>
                        <Tooltip direction='top' offset={[0, -18]}>
                            <div style={{ fontSize: 12, lineHeight: 1.2 }}>
                                <div><b>{d.Name || d.Code}</b></div>
                                <div>Type: {d.DeviceType || 'Camera'}</div>
                                <div>State: {d.IsActive ? 'Online' : 'Offline'}</div>
                                {d.Status && <div>Status: {d.Status}</div>}
                            </div>
                        </Tooltip>
                        <Popup>
                            <div style={{ minWidth: 240 }}>
                                <div className='fw-bold mb-1'>{d.Name || d.Code}</div>
                                <div className='mb-1'>Type: {d.DeviceType || 'Camera'}</div>
                                <div className='mb-1'>Position: {d.Lat}, {d.Lng}</div>
                                <div className='mb-1'>
                                    State: <span className={d.IsActive ? 'text-success' : 'text-danger'}>
                                            {d.IsActive ? 'Online' : 'Offline'}
                                    </span>
                                    {d.Status ? <span className='ms-2 badge bg-secondary'>{d.Status}</span> : null}
                                </div>
                                <div className='d-flex justify-content-center mt-3'>
                                    <button className='btn btn-sm btn-outline-primary' onClick={() => openLive(d)}>
                                        ▶ Live Stream
                                    </button>
                                </div>
                            </div>
                        </Popup>
                    </Marker>
                ))

                }
            </MapContainer>
        </div>
        <div className='modal fade' id='liveModal' tabIndex='-1' aria-hidden='true'>
            <div className='modal-dialog modal-lg modal-dialog-centered'>
                <div className='modal-content'>
                    <div className='modal-header'>
                        <h5 className='modal-title'>Live</h5>
                        <button type='button' className='btn-close' data-bs-dismiss='modal' aria-label='Close'></button>
                    </div>
                    <div className='modal-body text-center'>
                        {liveUrl
                            ? <img src={liveUrl} alt='live' style={{maxWidth: '100%', maxHeight: '80vh', objectFit: 'contain'}} />
                            : <div className='text-muted'>No Live Address</div>
                        }
                    </div>
                </div>
            </div>
        </div>
    </div>)
}

export default DevicesMap;