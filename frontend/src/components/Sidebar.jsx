import { Link } from 'react-router-dom'
import React, { useEffect, useState } from 'react'
import { useConfig } from '../configContext'
import axios from '../axios'
import { useEvents } from '../eventsContext'

export default function Sidebar({setToken,  account}) {
    const { hasUnread, markRead } = useEvents() || {};
    const config = useConfig();
    const [showModal, setShowModal] = useState(false);
    const [saving, setSaving] = useState(false);
    const [loadingUser, setLoadingUser] = useState(false);
    const [jwt, setJwt] = useState('');
    const [currentAccount, setCurrentAccount] = useState(account || '');

    const [form, setForm] = useState({
        Id: null,
        Account: '',
        Name: '',
        Email: '',
        Pwd: ''
    });

    const authHeaders = (t) => ({ headers: { Authorization: `Bearer ${t}` }});

    useEffect(() => {
        const t = localStorage.token;
        const acc =  localStorage.account || account || '';
        if (t) setJwt(t);
        if (acc) setCurrentAccount(acc);
    }, [account]);

    const openEditModal = async () => {
        if (!jwt) {
            alert('Not Login or Token expired');
            return;
        }
        setLoadingUser(true);
        try {
            const res = await axios.get(`${config.API_BASE_URL}users/`, authHeaders(jwt));
            const me = (res.data || []).find(u => u.Account === currentAccount);
            if (!me) {
                alert('No User from Current Account');
                setLoadingUser(false);
                return;
            }
            setForm( {Id: me.Id, Account: me.Account, Name: me.Name || '',  Email: me.Email || '', Pwd: ''});
            setShowModal(true);
        } catch (err) {
            console.error(err);
            alert('Load User failed');
        } finally {
            setLoadingUser(false);
        }
    }

    const handleSave = async () => {
        if (!form.Id) {
            alert('Invalid: No User Id');
            return;
        }
        setSaving(true);
        try {
            const data = { ...form };
            if (!data.Pwd) delete data.Pwd;
            await axios.put(`${config.API_BASE_URL}users/${form.Id}`, data, authHeaders(jwt));
            alert('Update Finished');
            setShowModal(false);

            if (currentAccount !== data.Account) {
                localStorage.account = data.Account;
                setCurrentAccount(data.Account);
            }
        } catch (err) {
            console.error(err);
            alert('Save failed');
        } finally {
            setSaving(false);
        }
    }

    const handleLogout = () => {
        localStorage.removeItem( 'token' );
        localStorage.removeItem( 'account' );
        setToken(null);
    }
    return (
        <div className='bg-light border-end p-3' style={{ width: '200px', minHeight: '100vh'}}>
            <h5>Management</h5>
            <button  className='btn btn-outline-secondary mt-3'
                style={{ cursor: loadingUser ? 'not-allowed' : 'pointer', userSelect: 'none' }}
                title='Click to modify Account'
                onClick={loadingUser ? undefined : openEditModal}
                >Account: {currentAccount}{loadingUser ? ' (loading...)' : ''}
            </button>
            <ul className='nav flex-column'>
                <li className='nav-item'><Link className='nav-link' to='/home'>Home</Link></li>
                <li className='nav-item'><Link className='nav-link' to='/users'>Users</Link></li>
                <li className='nav-item'><Link className='nav-link' to='/roles'>Roles</Link></li>
                <li className='nav-item'><Link className='nav-link' to='/devices'>Devices</Link></li>
                <li className='nav-item'><Link className='nav-link' to='/devicesmap'>Devices Map</Link></li>
                <li className='nav-item'><Link className='nav-link' to='/events'>Events
                {hasUnread ? (
                    <span className='ms-2 rounded-circle bg-danger'
                    style={{ width: 8, height: 8, display: 'inline-block' }} />
                ) : null}
                </Link></li>
                <li className='nav-item'>
                    <Link className='btn btn-outline-secondary mt-3' to='/' onClick={handleLogout}>Logout</Link></li>
            </ul>
            {showModal && (
                <div className='modal show d-block' tabIndex='-1' role='dialog' aria-model='true'>
                    <div className='modal-dialog'>
                        <div className='modal-content'>
                            <div className='modal-header'>
                                <h5 className='modal-title'>Modify User Account</h5>
                                <button type='button' className='btn-close' onClick={() => setShowModal(false)}></button>
                            </div>
                            <div className='modal-body'>
                                <div className='mb-3'>
                                    <label className='form-label'>Account</label>
                                    <input className='form-control' value={form.Account} onChange={e => setForm({ ...form, Account: e.target.value })}/>
                                </div>
                                <div className='mb-3'>
                                    <label className='form-label'>Name</label>
                                    <input className='form-control' value={form.Name} onChange={e => setForm({ ...form, Name: e.target.value })}/>
                                </div>
                                <div className='mb-3'>
                                    <label className='form-label'>Email</label>
                                    <input className='form-control' value={form.Email} onChange={e => setForm({ ...form, Email: e.target.value })}/>
                                </div>
                                <div className='mb-3'>
                                    <label className='form-label'>Password (Empty no Change)</label>
                                    <input type='password' className='form-control' value={form.Pwd} onChange={e => setForm({ ...form, Pwd: e.target.value })}/>
                                </div>
                            </div>
                            <div className='modal-footer'>
                                <button className='btn btn-secondary' onClick={() => setShowModal(false)} disabled={saving}>Cancel
                                </button>
                                <button className='btn btn-primary' onClick={handleSave} disabled={saving}>{saving ? 'Saving...' : 'Saved'}
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    )
}