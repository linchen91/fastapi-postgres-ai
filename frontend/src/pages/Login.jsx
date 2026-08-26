import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import axios from '../axios'
import { useConfig } from '../configContext'

export default function Login({ setToken, setAccount}) {
  const [account, setAcct] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const navigate = useNavigate();
  const config = useConfig();

  const handleLogin = async () => {
    setError('');
      try {
        const response = await axios.post(`${config.API_BASE_URL}auth/token`, {
            account,
            password
        });

        if (response.status === 200) {
            localStorage.token = response.data.access_token;
            localStorage.account = account;
            setToken(response.data.access_token);
            setAccount(account);
            navigate('/home');
        } else
            setError('Login failed, try again');
      } catch (err) {
        if (err.response?.status === 400 && err.response?.data?.detail)
            setError(err.response.data.detail);
        else
            setError('Login failed, try again later');
      }
    }

    return (
      <div className='d-flex justify-content-center align-items-center vh-100 bg-light'>
        <div className='bg-white shadow p-4 rounded' style={{ width: '100%', maxWidth: '400px' }}>
          <h2 className='mb-4 text-center'>Login</h2>
          {error && <div className='alert alert-danger'>{error}</div>}
          <div className='mb-3'>
            <label className='form-label'>Account</label>
            <input className='form-control' value={account} onChange={e => setAcct(e.target.value)} />
          </div>
          <div className='mb-3'>
            <label className='form-label'>Password</label>
            <input type='password' className='form-control' value={password} onChange={e => setPassword(e.target.value)} />
          </div>
          <button className='btn btn-primary w-100' onClick={handleLogin}>Login</button>
        </div>
      </div>
    );
}