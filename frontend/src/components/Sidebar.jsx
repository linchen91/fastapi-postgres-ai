import { Link } from 'react-router-dom'

export default function Sidebar() {
    return (
        <div className='bg-light border-end p-3' style={{ width: '200px', minHeight: '100vh'}}>
            <h5>Management</h5>
            <ul className='nav flex-column'>
                <li className='nav-item'><Link className='nav-link' to='/home'>Home</Link></li>
                <li className='nav-item'><Link className='nav-link' to='/users'>Users</Link></li>
                <li className='nav-item'><Link className='nav-link' to='/roles'>Roles</Link></li>
                <li className='nav-item'><Link className='nav-link' to='/devices'>Devices</Link></li>
            </ul>
        </div>
    )
}