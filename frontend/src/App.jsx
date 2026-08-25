import { Routes, Route, Navigate, Outlet } from "react-router-dom"
import { useEffect, useState } from 'react'
import Login from './pages/Login'
import Home from './pages/Home'
import Users from './pages/Users'
import Roles from './pages/Roles'
import Devices from './pages/Devices'
import Sidebar from './components/Sidebar'
import { useConfig } from "./configContext"

function ProtectedRoute({token, children}) {
  if (!token)
    return <Navigate to='/' replace />;
  else
    return children;
}
function Layout({token, setToken, account}) {
  return (
    <div className='d-flex'>
      <Sidebar setToken={setToken} account={account} />
      <div className='p-4 flex-grow-1 w-100'>
        <Routes>
          <Route path='/' element={<ProtectedRoute token={token}><Home /></ProtectedRoute>} />
          <Route path='home' element={<ProtectedRoute token={token}><Home /></ProtectedRoute>} />
          <Route path='users' element={<ProtectedRoute token={token}><Users /></ProtectedRoute>} />
          <Route path='roles' element={<ProtectedRoute token={token}><Roles /></ProtectedRoute>} />
          <Route path='devices' element={<ProtectedRoute token={token}><Devices /></ProtectedRoute>} />
        </Routes>
      </div>
    </div>
  )
}

export default function App() {
  const [token, setToken] = useState(localStorage.token);
  const [account, setAccount] = useState(localStorage.account);
  const config = useConfig();

  useEffect(() => {
    document.title = config.APP_TITLE;
  }, [config]);

  return (
    <Routes>
      <Route path='/' element={
        token ? (
          <Navigate to='/home' />
        ) : (
          <Login setToken={setToken} setAccount={setAccount}/>
        )
      } />
      <Route path='/*' element={<Layout token={token} setToken={setToken} account={account} />} />
    </Routes>  
  )
}