import { useEffect } from 'react';
import { BrowserRouter, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom';

import { Layout } from '@/components/Layout';
import { HomePage } from '@/pages/HomePage';
import { JoinPage } from '@/pages/JoinPage';
import { RoomPage } from '@/pages/RoomPage';
import { loadSession } from '@/lib/session';

function SessionRedirect() {
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    if (location.pathname !== '/') return;
    const session = loadSession();
    if (session) void navigate(`/rooms/${session.roomCode}`, { replace: true });
  }, [location.pathname, navigate]);

  return null;
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/join" element={<JoinPage />} />
      <Route path="/join/:code" element={<JoinPage />} />
      <Route path="/rooms/:code" element={<RoomPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

function App() {
  return (
    <BrowserRouter>
      <Layout>
        <SessionRedirect />
        <AppRoutes />
      </Layout>
    </BrowserRouter>
  );
}

export default App;
