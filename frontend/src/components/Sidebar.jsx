import { Link } from 'react-router-dom'

export default function Sidebar({setToken,  account}) {
    const handleLogout = () => {
        localStorage.removeItem( 'token' );
        localStorage.removeItem( 'account' );
        setToken(null);
    }
    return (
        <div className='bg-light border-end p-3' style={{ width: '200px', minHeight: '100vh'}}>
            <h5>Management</h5>
            <p className='text-muted small'>Account: {account}</p>
            <ul className='nav flex-column'>
                <li className='nav-item'><Link className='nav-link' to='/home'>Home</Link></li>
                <li className='nav-item'><Link className='nav-link' to='/users'>Users</Link></li>
                <li className='nav-item'><Link className='nav-link' to='/roles'>Roles</Link></li>
                <li className='nav-item'><Link className='nav-link' to='/devices'>Devices</Link></li>
                <li className='nav-item'>
                    <Link className='btn btn-outline-secondary mt-3' to='/' onClick={handleLogout}>Logout</Link></li>
            </ul>
        </div>
    )
}