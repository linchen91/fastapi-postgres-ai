import React, { useEffect, useState } from 'react'
import { useConfig } from '../configContext'
import axios from '../axios'

const Roles = () => {
  const config = useConfig();
  const [roles, setRoles] = useState([]);
  const [devices, setDevices] = useState([]);
  const [token, setToken] = useState('');
  const [error, setError] = useState('');

  const [form, setForm] = useState({
    Id: null,
    Name: '',
    DeviceIds: []
  });

  const loadRoles = async (t) => {
    const res = await axios.get(`${config.API_BASE_URL}roles/`, {
      headers: { Authorization: `Bearer ${t}` }
    });
    setRoles(res.data);
  };

  const loadDevices = async (t) => {
    const res = await axios.get(`${config.API_BASE_URL}devices/`, {
      headers: { Authorization: `Bearer ${t}` }
    });
    setDevices(res.data);
  };

  useEffect(() => {
    if (config) {
      const saveToken = localStorage.token;
      if (saveToken) {
        setToken(saveToken);
        loadRoles(saveToken);
        loadDevices(saveToken);
      }
    }
  }, [config]);

  const handleSubmit = async () => {
    setError('');
    const data = {
      Name: form.Name,
      DeviceIds: form.DeviceIds
    };

    try {
      if (form.Id) {
        await axios.put(`${config.API_BASE_URL}roles/${form.Id}`, data, {
          headers: { Authorization: `Bearer ${token}` }
        });
      } else {
        await axios.post(`${config.API_BASE_URL}roles/`, data, {
          headers: { Authorization: `Bearer ${token}` }
        });
      }
      setForm({ Id: null, Name: '', DeviceIds: [] });
      loadRoles(token);
    } catch (err) {
      setError(err.response?.data?.detail || 'Operation failed');
    }
  };

  const handleEdit = (r) => {
    setForm({
      Id: r.Id,
      Name: r.Name,
      DevicesId: r.Devices?.map(d => d.Id) || []
    });
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Are you sure to delete the role?')) return;
    setError('');
    try {
      await axios.delete(`${config.API_BASE_URL}roles/${id}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      loadRoles(token);
    } catch (err) {
      setError(err.response?.data?.detail || 'Delete failed');
    }
  };

  return (
    <div className='container mt-4'>
      <div className='card p-3 mb-4'>
        <h4>{form.Id ? 'Edit Role' : 'Add Role'}</h4>
        <div className='row g-3'>
          <div className='col-md-6'>
            <label className='form-label'>Role Name</label>
            <input className='form-control' value={form.Name} onChange={(e) => setForm({ ...form, Name: e.target.value })} />
          </div>
          <div className='col-md-12'>
            <label className='form-label'>Relate Devices (Multiple)</label>
            <select
              className='form-select'
              multiple
              size='5'
              value={form.DeviceIds}
              onChange={(e) => {
                const selected = Array.from(e.target.selectedOptions).map(opt => parseInt(opt.value));
                setForm(prev => ({ ...prev, DeviceIds: selected }));
              }}
              >
              {devices.map(d => (
                <option key={d.Id} value={d.Id}>{d.Name}</option>
              ))}
            </select>
          </div>
        </div>
        <div className='mt-3'>
          <button className='btn btn-primary' onClick={handleSubmit}>{form.Id ? 'Update Role' : 'Add Role'}</button>
        </div>
      </div>
      <table className='table table-bordered'>
        <thead className='table-light'>
          <tr>
            <th>Role Name</th>
            <th>Relate Devices</th>
            <th>Operate</th>
          </tr>
        </thead>
        <tbody>
          {roles.map((r) => (
            <tr key={r.Id}>
              <td>{r.Name}</td>
              <td>
                {r.Devices && r.Devices.length > 0
                    ? r.Devices.map(d => d.Name).join(':')
                : <span className='text-muted'>Empty</span>}
              </td>
              <td>
                <button className='btn btn-sm btn-secondary me-2' onClick={() => handleEdit(r)}>Edit</button>
                <button className='btn btn-sm btn-danger' onClick={() => handleDelete(r.Id)}>Delete</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default Roles;
