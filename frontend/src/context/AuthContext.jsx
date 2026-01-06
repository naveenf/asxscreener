import React, { createContext, useState, useContext, useEffect } from 'react';
import { jwtDecode } from 'jwt-decode';
import axios from 'axios';

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const savedToken = localStorage.getItem('google_token');
    const savedUser = localStorage.getItem('user_info');
    if (savedToken && savedUser) {
      setUser(JSON.parse(savedUser));
    }
    setLoading(false);
  }, []);

  const login = async (credentialResponse) => {
    try {
      const { credential } = credentialResponse;
      // Send token to backend to verify and get/create user
      const response = await axios.post('/auth/google', {
        credential
      });

      const userData = response.data;
      localStorage.setItem('google_token', credential);
      localStorage.setItem('user_info', JSON.stringify(userData));
      setUser(userData);
      return userData;
    } catch (error) {
      console.error('Login process failed:', error);
      if (error.response) {
        console.error('Backend response:', error.response.status, error.response.data);
      }
      throw error;
    }
  };

  const logout = () => {
    localStorage.removeItem('google_token');
    localStorage.removeItem('user_info');
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, login, logout, loading }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);
