import { Route, Routes } from 'react-router-dom';
import { AppLayout } from '@/components/layout/AppLayout';
import { ProtectedRoute } from '@/components/ProtectedRoute';
import Analytics from '@/pages/Analytics';
import Dashboard from '@/pages/Dashboard';
import Login from '@/pages/Login';
import AppDownload from '@/pages/AppDownload';
import MapApi from '@/pages/MapApi';
import NotFound from '@/pages/NotFound';
import Reports from '@/pages/Reports';
import Rides from '@/pages/Rides';
import Settings from '@/pages/Settings';
import Suspended from '@/pages/Suspended';
import Trips from '@/pages/Trips';
import Users from '@/pages/Users';
import Vehicles from '@/pages/Vehicles';
import Verifications from '@/pages/Verifications';

/** Public login route + every console module behind the ADMIN guard (§17). */
export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        element={
          <ProtectedRoute>
            <AppLayout />
          </ProtectedRoute>
        }
      >
        <Route index element={<Dashboard />} />
        <Route path="users" element={<Users />} />
        <Route path="verifications" element={<Verifications />} />
        <Route path="vehicles" element={<Vehicles />} />
        <Route path="rides" element={<Rides />} />
        <Route path="trips/active" element={<Trips mode="active" />} />
        <Route path="trips/completed" element={<Trips mode="completed" />} />
        <Route path="reports" element={<Reports />} />
        <Route path="suspended" element={<Suspended />} />
        <Route path="analytics" element={<Analytics />} />
        <Route path="map-api" element={<MapApi />} />
        <Route path="app-download" element={<AppDownload />} />
        <Route path="settings" element={<Settings />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
