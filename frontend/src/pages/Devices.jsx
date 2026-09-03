import React, { useEffect, useState } from 'react'
import { useConfig } from '../configContext'
import axios from '../axios'
import { Modal } from 'bootstrap'

const Devices = () => {
  const config = useConfig();
  const [devices, setDevices] = useState([]);
  const [token, setToken] = useState('');
  const [error, setError] = useState('');
  const [videoUrl, setVideoUrl] = useState('');
  const [mapUrl, setMapUrl] = useState('');

  const [trafficImg, setTrafficImg] = useState('');
  const [trafficCount, setTrafficCount] = useState(0);
  const [trafficLoading, setTrafficLoading] = useState(false);
  const [trafficErr, setTrafficErr] = useState('');

  const [form, setForm] = useState({
    Id: null,
    Code: '',
    Name: '',
    DeviceType: 'camera',
    Params: '',
    Lat: '',
    Lng: '',
    IsActive: true,
    Status: 'active'
  });

  const authHeaders = (t) => ({ headers: { Authorization: `Bearer ${t}` }});

  const loadDevices = async (t) => {
    const account = localStorage.account;
    const url = account
      ? `${config.API_BASE_URL}devices/?user_account=${account}`
      : `${config.API_BASE_URL}devices/`;
    const res = await axios.get(url, {
      headers: { Authorization: `Bearer ${t}` }
    });
    setDevices(res.data);
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

  const normalizeParamsForSend = (val) => {
    if (val == null) return '';
    if (typeof val === 'string') return val;
    try { return JSON.stringify(val); } catch { return String(val); }
  };

  const handleSubmit = async () => {
    setError('');
    const data = { ...form, Params: normalizeParamsForSend(form.Params)};

    if (data.Lat !== '' && data.Lat !== null) data.Lat = parseFloat(data.Lat);
    if (data.Lng !== '' && data.Lng !== null) data.Lng = parseFloat(data.Lng);

    if (!data.Code || !data.Name) {
        alert('Please enter Code and Name');
        return;
    }

    try {
      if (form.Id) {
        await axios.put(`${config.API_BASE_URL}devices/${form.Id}`, data, authHeaders(token));
      } else {
        await axios.post(`${config.API_BASE_URL}devices/`, data, authHeaders(token));
      }
      setForm({ Id: null, Code: '', Name: '', DeviceType: 'camera', Params: '', Lat: '', Lng: '', IsActive: true, Status: 'active' });
      loadDevices(token);
    } catch (err) {
      setError(err.response?.data?.detail || 'Operation failed');
    }
  };

  const handleEdit = (d) => {
    setForm({
      Id: d.Id,
      Code: d.Code,
      Name: d.Name,
      DeviceType: d.DeviceType || 'camera',
      Params: d.Params || '',
      Lat: d.Lat ?? '',
      Lng: d.Lng ?? '',
      IsActive: !!d.IsActive,
      Status: d.Status || 'active'
    });
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Are you sure to delete the device?')) return;
    setError('');
    try {
      await axios.delete(`${config.API_BASE_URL}devices/${id}`, authHeaders(token));
      loadDevices(token);
    } catch (err) {
      setError(err.response?.data?.detail || 'Delete failed');
    }
  };

  const openLive = (device) => {
    try {
      const params = typeof device.Params === 'string' ? JSON.parse(device.Params) : device.Params;
      const url = params?.VideoStream;
      if (!url) {
        alert('No video stream URL found for this device');
        return;
      }
      setVideoUrl(url);
      const modalE = document.getElementById('liveModal');
      if (modalE) {
        const modal = new Modal(modalE);
        modal.show();
      }
    } catch {
      alert('Invalid parameters JSON for this device');
    }
  };

  const openMap = (device) => {
    const url = `https://www.google.de/maps?q=${device.Lat},${device.Lng}&output=embed`;
    setMapUrl(url);
    const modalE = document.getElementById('mapModal');
    if (modalE) {
      const modal = new Modal(modalE);
      modal.show();
    }
  };

  const openTraffic = async (device) => {
    setTrafficImg('');
    setTrafficErr('');
    setTrafficCount(0);
    try {
      const params = typeof device.Params === 'string' ? JSON.parse(device.Params) : device.Params;
      const url = params?.VideoStream;
      if (!url) {
        alert('No video stream URL found for this device');
        return;
      }
      const modalE = document.getElementById('trafficModal');
      if (modalE) {
        const modal = new Modal(modalE);
        modal.show();
      }
      setTrafficLoading(true);
      const payload = { url };
      const res = await axios.post(`${config.API_BASE_URL}ai/traffic/cars`, payload, token ? authHeaders(token) : {});
      setTrafficImg(res.data?.image_base64 || '');
      setTrafficCount(res.data?.vehicles ?? 0);
    } catch (err) {
      setTrafficErr(err.response?.data?.detail || 'Failed to analyze traffic');
    } finally {
      setTrafficLoading(false); 
    }
  }; 

  return (
    <div className='container-fluid mt-4'>
      <div className='card p-3 mb-4'>
        <h4>{form.Id ? 'Edit Device' : 'Add Device'}</h4>
        <div className='row g-3'>
          <div className='col-md-3'>
            <label className='form-label'>Code</label>
            <input className='form-control' value={form.Code} onChange={(e) => setForm({ ...form, Code: e.target.value })} />
          </div>
          <div className='col-md-3'>
            <label className='form-label'>Device Name</label>
            <input className='form-control' value={form.Name} onChange={(e) => setForm({ ...form, Name: e.target.value })} />
          </div>
          <div className='col-md-3'>
            <label className='form-label'>Device Type</label>
            <input className='form-control' value={form.DeviceType} onChange={(e) => setForm({ ...form, DeviceType: e.target.value })} />
          </div>
          <div className='col-md-3'>
            <label className='form-label'>Status</label>
            <input className='form-control' value={form.Status} onChange={(e) => setForm({ ...form, Status: e.target.value })} />
          </div>
          <div className='col-md-12'>
            <label className='form-label'>Parameters</label>
            <textarea className='form-control' rows={2} value={form.Params} onChange={(e) => setForm({ ...form, Params: e.target.value })} />
          </div>
          <div className='col-md-3'>
            <label className='form-label'>Lat</label>
            <input className='form-control' value={form.Lat} onChange={(e) => setForm({ ...form, Lat: e.target.value })} />
          </div>
          <div className='col-md-3'>
            <label className='form-label'>Lng</label>
            <input className='form-control' value={form.Lng} onChange={(e) => setForm({ ...form, Lng: e.target.value })} />
          </div>
          <div className='col-md-3'>
            <label className='form-label'>Active</label>
            <select className='form-select' value={form.IsActive ? '1' : '0'} onChange={(e) => setForm({ ...form, IsActive: e.target.value === '1' })}>
              <option value='1'>Yes</option>
              <option value='0'>No</option>
            </select>
          </div>
        </div>
        <div className='mt-3'>
          <button className='btn btn-primary' onClick={handleSubmit}>{form.Id ? 'Update Device' : 'Add Device'}</button>
        </div>
      </div>
      <table className='table table-bordered'>
        <thead className='table-light'>
          <tr>
            <th>Code</th>
            <th>Name</th>
            <th>Type</th>
            <th>Active</th>
            <th>Status</th>
            <th>Live Stream</th>
            <th>View Map</th>
            <th>Traffic Analysis</th>
            <th>Operate</th>
          </tr>
        </thead>
        <tbody>
          {devices.map((d) => (
            <tr key={d.Id}>
              <td>{d.Code}</td>
              <td>{d.Name}</td>
              <td>{d.DeviceType}</td>
              <td>{d.IsActive ? 'Yes' : 'No'}</td>
              <td>{d.Status}</td>
              <td>
                <button className='btn btn-sm btn-outline-primary' onClick={() => openLive(d)}>Live Stream</button>
              </td>
              <td>
                <button className='btn btn-sm btn-outline-success' onClick={() => openMap(d)}>View Map</button>
              </td>
              <td>
                <button className='btn btn-sm btn-outline-warning' onClick={() => openTraffic(d)}>View Traffic</button>
              </td>
              <td>
                <button className='btn btn-sm btn-secondary me-2' onClick={() => handleEdit(d)}>Edit</button>
                <button className='btn btn-sm btn-danger' onClick={() => handleDelete(d.Id)}>Delete</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className='modal fade' id='liveModal' tabIndex='-1' aria-hidden='true'>
        <div className='modal-dialog modal-lg modal-dialog-centered'>
          <div className='modal-content'>
            <div className='modal-header'>
              <h5 className='modal-title'>Live Stream</h5>
              <button type='button' className='btn-close' data-bs-dismiss='modal' aria-label='Close'></button>
            </div>
            <div className='modal-body text-center'>
              {videoUrl && <video src={videoUrl} autoPlay controls style={{ maxWidth: '100%', maxHeight: '80vh' }} />}
            </div>
          </div>
        </div>
      </div>

      <div className='modal fade' id='mapModal' tabIndex='-1' aria-hidden='true'>
        <div className='modal-dialog modal-lg modal-dialog-centered'>
          <div className='modal-content'>
            <div className='modal-header'>
              <h5 className='modal-title'>Map</h5>
              <button type='button' className='btn-close' data-bs-dismiss='modal' aria-label='Close'></button>
            </div>
            <div className='modal-body p-0'>
              {mapUrl && (
                <iframe
                  src={mapUrl}
                  style={{ width: '100%', height: '70vh', border: 0 }}
                  allowFullScreen='true'
                  loading='lazy'
                  referrerPolicy='no-referrer-when-downgrade'
                  title='map'
                />
              )}
            </div>
          </div>
        </div>
      </div>
      <div className='modal fade' id='trafficModal' tabIndex='-1' aria-hidden='true'>
        <div className='modal-dialog modal-xl modal-dialog-centered'>
          <div className='modal-content'>
            <div className='modal-header'>
              <h5 className='modal-title'>Traffic Analysis</h5>
              <button type='button' className='btn-close' data-bs-dismiss='modal' aria-label='Close'></button>
            </div>
            <div className='modal-body text-center'>
              {trafficLoading && <div>Loading traffic analysis...</div>}
              {trafficErr && <div className='text-danger'>{trafficErr}</div>}
              <div className='d-flex align-items-center gap-3 mb-3'>
                <span>Detected Vehicles: {trafficCount}</span>
              </div>
              {!trafficLoading && !trafficErr && trafficImg && (
                <div className='text-center'>
                  <img src={trafficImg} alt='Traffic Analysis' style={{ maxWidth: '100%', maxHeight: '80vh' }} />
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default Devices;
