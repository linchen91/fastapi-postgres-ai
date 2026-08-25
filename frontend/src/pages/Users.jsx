import React, { useEffect, useState } from 'react'
import { useConfig } from '../configContext'
import axios from 'axios'

const Users = () => {
  const config = useConfig();
  const [users, setUsers] = useState([]);
  const [roles, setRoles] = useState([]);
  const [token, setToken] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [form, setForm] = useState({
    Id: null,
    Account: '',
    Pwd: '',
    Name: '',
    Email: '',
    RoleId: 1,
    IsActive: true
  });

  const loadUsers = async (t) => {
    const res = await axios.get(`${config.API_BASE_URL}users/`, {
      headers: { Authorization: `Bearer ${t}` }
    });
    setUsers(res.data);
  };

  const loadRoles = async (t) => {
    const res = await axios.get(`${config.API_BASE_URL}roles/`, {
      headers: { Authorization: `Bearer ${t}` }
    });
    setRoles(res.data);
  };

  const handleSubmit = async () => {
    setError('');
    const data = { ...form };
    if (!data.Pwd) delete data.Pwd;

    try {
      if (form.Id) {
        await axios.put(`${config.API_BASE_URL}users/${form.Id}`, data, {
          headers: { Authorization: `Bearer ${token}` }
        });
      } else {
        await axios.post(`${config.API_BASE_URL}users/`, data, {
          headers: { Authorization: `Bearer ${token}` }
        });
      }
      setForm({ Id: null, Account: '', Pwd: '', Name: '', Email: '', RoleId: 1, IsActive: true });
      loadUsers(token);
    } catch (err) {
      setError(err.response?.data?.detail || 'Operation failed');
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Are you sure to delete the user?')) return;
    setError('');
    try {
      await axios.delete(`${config.API_BASE_URL}users/${id}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      loadUsers(token);
    } catch (err) {
      setError(err.response?.data?.detail || 'Delete failed');
    }
  };

  const handleEdit = (u) => {
    setForm({ ...u, Pwd: '' });
  };

  useEffect(() => {
    if (config) {
      const saveToken = localStorage.token;
      if (saveToken) {
        setToken(saveToken);
        Promise.all([loadUsers(saveToken), loadRoles(saveToken)])
          .catch(err => setError(err.response?.data?.detail || 'Failed to load data'))
          .finally(() => setLoading(false));
      } else {
        setLoading(false);
      }
    }
  }, [config]);

  if (loading) return <div className="p-4">Loading...</div>;

  return (
    <div className='container mt-4'>
      <div className='container card p-3 mb-4'>
        <h4>{form.Id ? 'Edit User' : 'Add User'}</h4>
        <div className='row g-3'>
          <div className='col-md-6'>
            <label className='form-label'>Account</label>
            <input className='form-control' value={form.Account} onChange={(e) => setForm({ ...form, Account: e.target.value })} />
          </div>
          <div className='col-md-6'>
            <label className='form-label'>Name</label>
            <input className='form-control' value={form.Name} onChange={(e) => setForm({ ...form, Name: e.target.value })} />
          </div>
          <div className='col-md-6'>
            <label className='form-label'>Email</label>
            <input className='form-control' value={form.Email} onChange={(e) => setForm({ ...form, Email: e.target.value })} />
          </div>
          <div className='col-md-6'>
            <label className='form-label'>Password</label>
            <input type='password' className='form-control' value={form.Pwd} onChange={(e) => setForm({ ...form, Pwd: e.target.value })} />
          </div>
          <div className='col-md-6'>
            <label className='form-label'>RoleId</label>
            <select className='form-select' value={form.RoleId} onChange={(e) => setForm({ ...form, RoleId: parseInt(e.target.value) })}>
              {roles.map(role => <option key={role.Id} value={role.Id}>{role.Name}</option>)}
            </select>
          </div>
          <div className='col-md-6'>
            <label className='form-label'>Active</label>
            <select className='form-select' value={form.IsActive ? '1' : '0'} onChange={(e) => setForm({ ...form, IsActive: e.target.value === '1' })}>
              <option value='1'>Yes</option>
              <option value='0'>No</option>
            </select>
          </div>
        </div>
        <div className='mt-3'>
          <button className='btn btn-primary' onClick={handleSubmit}>{form.Id ? 'Update User' : 'Add User'}</button>
        </div>
      </div>
      <table className='table table-bordered'>
        <thead className='table-light'>
          <tr>
            <th>Account</th>
            <th>Name</th>
            <th>Email</th>
            <th>Role</th>
            <th>Active</th>
            <th>Operate</th>
          </tr>
        </thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.Id}>
              <td>{u.Account}</td>
              <td>{u.Name}</td>
              <td>{u.Email}</td>
              <td>{roles.find(r => r.Id === u.RoleId)?.Name || u.RoleId}</td>
              <td>{u.IsActive ? 'Yes' : 'No'}</td>
              <td>
                <button className='btn btn-sm btn-secondary me-2' onClick={() => handleEdit(u)}>Edit</button>
                <button className='btn btn-sm btn-danger' onClick={() => handleDelete(u.Id)}>Delete</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default Users;
