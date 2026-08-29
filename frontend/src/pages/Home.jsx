import React, { useEffect, useMemo, useState } from 'react'
import { useConfig } from '../configContext'
import axios from '../axios'

import { Pie, Bar } from 'react-chartjs-2'
import { Chart as ChartJS, ArcElement, CategoryScale, LinearScale, BarElement, Title, Tooltip, Legend} from 'chart.js'

ChartJS.register(ArcElement, CategoryScale, LinearScale, BarElement, Title, Tooltip, Legend);

const colorForStatus = (status) => {
    const s = (status || '').toString().toLowerCase();
    if (s === 'active') return '#28a745';
    if (s === 'offline') return '#6c757d';
    if (s === 'error') return '#dc3545';
    return '#ffc107';
}

const statusBadge = (status) => {
    const s = (status || '').toString().toLowerCase();
    if (s === 'active' || s === 'enable') return <span className='badge bg-success'>{status}</span>;
    if (s === 'offline') return <span className='badge bg-secondary'>{status}</span>;
    if (s === 'error') return <span className='badge bg-danger'>{status}</span>;
    return <span className='badge bg-warning text-dark'>{status || 'Unknown'}</span>;
}

const Home = () => {
    const config = useConfig();
    const [users, setUsers] = useState([]);
    const [roles, setRoles] = useState([]);
    const [token, setToken] = useState('');
    const [devices, setDevices] = useState([]);
    const [error, setError] = useState('');
    const authHeaders = (t) => ({ headers: { Authorization: `Bearer ${t}` }});

    useEffect(() => {
        if (!config) return;
        const savedToken = localStorage.token;
        if (!savedToken) return;
        setToken(savedToken);
        Promise.all([
            axios.get(`${config.API_BASE_URL}users/`, authHeaders(savedToken)),
            axios.get(`${config.API_BASE_URL}roles/`, authHeaders(savedToken)),
            axios.get(`${config.API_BASE_URL}devices/`, authHeaders(savedToken))
        ]).then(([u,r,d]) => {
            setUsers(Array.isArray(u.data) ? u.data : (u.data?.items ?? []));
            setRoles(Array.isArray(r.data) ? r.data : (r.data?.items ?? []));
            setDevices(Array.isArray(d.data) ? d.data : (d.data?.items ?? []));
        }).catch((err) => setError(err?.message || 'Load Failed'))
    }, [config]);

    const deviceStates = useMemo(() => {
        const counts = new Map();
        devices.forEach((d) => {
            const key = d.Status;
            counts.set(key, (counts.get(key) || 0) + 1);
        });
        return Array.from(counts, ([label, value]) => ({label, value}));
    }, [devices]);

    const roleDeviceStates = useMemo(() => {
        return roles.map((r) => ({ label: r.name || `Role #${r.Id}`, value: (r.Devices || []).length }));
    }, [roles]);

    const recentDevices = useMemo(() => {
        const seen = new Set();
        const unique = devices.filter((d) => {
            if (seen.has(d.Id)) return false;
            seen.add(d.Id);
            return true;
        });
        return unique
            .sort((a, b) => new Date(b.UpdatedDate) - new Date(a.UpdatedDate))
            .slice(0, 5);
    }, [devices]);

    return (
        <div className='container'>
            <div className='row mb-4 text-white'>
                <div className='col-md-4 mb-3'>
                    <div className='card bg-primary p-3 text-center text-white'>
                        <h5>Total Users</h5>
                        <div className='fs-2 fw-bold'>{users.length}</div>
                    </div>
                </div>
                <div className='col-md-4 mb-3'>
                    <div className='card bg-success p-3 text-center text-white'>
                        <h5>Total Roles</h5>
                        <div className='fs-2 fw-bold'>{roles.length}</div>
                    </div>
                </div>
                <div className='col-md-4 mb-3'>
                    <div className='card bg-warning p-3 text-center text-white'>
                        <h5>Total Devices</h5>
                        <div className='fs-2 fw-bold'>{devices.length}</div>
                    </div>
                </div>
            </div>
            <div className='row mb-4'>
                <div className='col-md-6'>
                    <div className='card p-3 h-100'>
                        <h5 className='mb-3'>Device States</h5>
                        {
                            deviceStates.length > 0 ? (
                                <div style={{ height: '250px' }}>
                                    <Pie
                                    data = {{
                                        labels: deviceStates.map((it) => it.label),
                                        datasets: [
                                            {
                                                data: deviceStates.map((it) => it.value),
                                                backgroundColor: deviceStates.map((it) => colorForStatus(it.label)),
                                                borderWidth: 1
                                            }
                                        ],
                                    }}
                                    options={{
                                        maintainAspectRatio: false,
                                        responsive: true,
                                        plugins: {legend: { position: 'bottom' } }
                                    }}
                                    />
                                </div>
                            ) : (
                                <div className='text-muted'>No Data</div>
                            )
                        }
                    </div>
                </div>
                <div className='col-md-6'>
                    <div className='card p-3 h-100'>
                        <h5 className='mb-3'>Devices per Role</h5>
                        {
                            roleDeviceStates.length > 0 ? (
                                <div style={{ height: '250px' }}>
                                    <Bar
                                    data = {{
                                        labels: roleDeviceStates.map((it) => it.label),
                                        datasets: [
                                            {
                                                label: 'Devices Number',
                                                data: roleDeviceStates.map((it) => it.value),
                                                backgroundColor: '#0d6efd'
                                            }
                                        ],
                                    }}
                                    options={{
                                        maintainAspectRatio: false,
                                        responsive: true,
                                        plugins: {legend: { display: false } },
                                        scales: {y: { beginAtZero: true, precision: 0 }}
                                    }}
                                    />
                                </div>
                            ) : (
                                <div className='text-muted'>No Data</div>
                            )
                        }
                    </div>
                </div>
            </div>
            <div className='card p3'>
                <h5>Recent Devices</h5>
                <table className='table table-bordered mt-2'>
                    <thead className='table-light'>
                        <tr>
                            <th>Name</th>
                            <th>Status</th>
                            <th>Updated Time</th>
                        </tr>
                    </thead>
                    <tbody>
                        {recentDevices.map((d, idx) => (
                            <tr key={d.Id || idx}>
                                <td>{d.Name || '_'}</td>
                                <td>{statusBadge(d.Status ?? (d.IsActive ? 'active' : 'offline'))}</td>
                                <td>{d.UpdatedDate ? new Date(d.UpdatedDate).toLocaleString() : '_'}</td>
                            </tr>
                        ))}
                        {recentDevices.length === 0 && (
                            <tr>
                                <td colSpan='3' className='text-muted'>No Device</td>
                            </tr>
                        )}
                    </tbody>
                </table>
            </div>
        </div>
    )
}

export default Home;