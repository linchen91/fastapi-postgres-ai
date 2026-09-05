import { Routes, Route, Navigate, Outlet } from "react-router-dom"
import { useEffect, useState, lazy, Suspense } from 'react'
import Login from './pages/Login'
import Home from './pages/Home'
import Users from './pages/Users'
import Roles from './pages/Roles'
import Devices from './pages/Devices'
import Sidebar from './components/Sidebar'
import { useConfig } from "./configContext"
import Events from './pages/Events'
import { EventsProvider } from "./eventsContext"

const DevicesMap = lazy(() => import('./pages/DevicesMap'))
const News = lazy(() => import('./pages/News'))
const LangGraph = lazy(() => import('./pages/LangGraph'))

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
          <Route path='devicesmap' element={<ProtectedRoute token={token}><Suspense fallback={<div className='text-center p-4'>Loading map...</div>}><DevicesMap /></Suspense></ProtectedRoute>} />
          <Route path='events' element={<ProtectedRoute token={token}><Events /></ProtectedRoute>} />
          <Route path='news' element={<ProtectedRoute token={token}><Suspense fallback={<div className='text-center p-4'>Loading news...</div>}><News /></Suspense></ProtectedRoute>} />
          <Route path='langgraph' element={<ProtectedRoute token={token}><Suspense fallback={<div className='text-center p-4'>Loading search assistant...</div>}><LangGraph /></Suspense></ProtectedRoute>} />
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
    <EventsProvider token={token}>
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
    </EventsProvider> 
  )
}