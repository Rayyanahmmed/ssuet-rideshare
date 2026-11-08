import { Link } from 'react-router-dom';

/** Unknown console URL — honest 404 instead of a fake module. */
export default function NotFound() {
  return (
    <div className="card mx-auto max-w-lg p-10 text-center">
      <p className="text-3xl">🧭</p>
      <h2 className="mt-4 text-xl font-semibold">Page not found</h2>
      <p className="mt-2 text-sm text-muted">
        This address is not part of the admin console. Use the sidebar to reach Dashboard, Users, Verification,
        Vehicles, Rides, Trips, Reports, Suspended accounts, Analytics, Map API, App download or Settings.
      </p>
      <Link to="/" className="btn-primary mt-6 inline-flex">
        Back to dashboard
      </Link>
    </div>
  );
}
