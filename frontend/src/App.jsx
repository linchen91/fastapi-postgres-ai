import { Routes, Route, Navigate, Outlet } from "react-router-dom"
import Login from './pages/Login'
import Home from './pages/Home'
import Users from './pages/Users'
import Roles from './pages/Roles'
import Devices from './pages/Devices'
import Sidebar from './components/Sidebar'

function Layout() {
  return (
    <div className='d-flex'>
      <Sidebar />
      <div className='p-4 flex-grow-1 w-100'>
        <Outlet />
      </div>
    </div>
  )
}

export default function App() {
  return (
    <Routes>
      <Route path='/login' element={<Login />} />
      <Route element={<Layout />}>
        <Route index element={<Home />} />
        <Route path='home' element={<Home />} />
        <Route path='users' element={<Users />} />
        <Route path='roles' element={<Roles />} />
        <Route path='devices' element={<Devices />} />
      </Route>
    </Routes>  
  )
}