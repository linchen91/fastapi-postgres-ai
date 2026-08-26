import axios from 'axios';

const api = axios.create();

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      const isLoginRequest = error.config?.url?.includes('auth/token');
      if (!isLoginRequest) {
        localStorage.removeItem('token');
        localStorage.removeItem('account');
        window.location.href = '/';
      }
    }
    return Promise.reject(error);
  }
);

export default api;