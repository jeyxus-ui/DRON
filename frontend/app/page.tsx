'use client';

import { useEffect, useState } from 'react';
import { API_URL, WS_URL } from './config';

export default function Home() {
  const [telemetry, setTelemetry] = useState<any>({});
  const [drones, setDrones] = useState<any[]>([]);
  const [missions, setMissions] = useState<any[]>([]);
  const [users, setUsers] = useState<any[]>([]);
  const [routes, setRoutes] = useState<any[]>([]);

  useEffect(() => {
    // WebSocket para telemetría (backend en Raspberry 192.168.137.43)
    const ws = new WebSocket(WS_URL);
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      setTelemetry(data);
    };
    ws.onopen = () => console.log('Connected to WebSocket');
    ws.onclose = () => console.log('WebSocket closed');

    // Fetch para datos estáticos
    fetch(`${API_URL}/drones`).then(res => res.json()).then(setDrones);
    fetch(`${API_URL}/missions`).then(res => res.json()).then(setMissions);
    fetch(`${API_URL}/users`).then(res => res.json()).then(setUsers);
    fetch(`${API_URL}/flight-routes`).then(res => res.json()).then(setRoutes);

    return () => ws.close();
  }, []);

  return (
    <div className="flex min-h-screen items-center justify-center bg-zinc-50 font-sans dark:bg-black">
      <main className="flex min-h-screen w-full max-w-4xl flex-col items-center py-32 px-16 bg-white dark:bg-black">
        <h1 className="text-3xl font-semibold mb-8">Drone Telemetry Dashboard</h1>

        <div className="w-full space-y-6">
          <div>
            <h2 className="text-xl font-bold">Telemetría en Tiempo Real:</h2>
            <pre className="bg-gray-100 p-4 rounded">{JSON.stringify(telemetry, null, 2)}</pre>
          </div>

          <div>
            <h2 className="text-xl font-bold">Drones:</h2>
            <ul className="list-disc pl-5">
              {drones.map(d => <li key={d.id}>{d.name} - {d.status} (Modelo: {d.model})</li>)}
            </ul>
          </div>

          <div>
            <h2 className="text-xl font-bold">Misiones:</h2>
            <ul className="list-disc pl-5">
              {missions.map(m => <li key={m.id}>{m.name} - {m.status} ({m.progress_percent}%)</li>)}
            </ul>
          </div>

          <div>
            <h2 className="text-xl font-bold">Usuarios:</h2>
            <ul className="list-disc pl-5">
              {users.map(u => <li key={u.id}>{u.username} - {u.role}</li>)}
            </ul>
          </div>

          <div>
            <h2 className="text-xl font-bold">Rutas de Vuelo:</h2>
            <ul className="list-disc pl-5">
              {routes.map(r => <li key={r.id}>{r.name} - Distancia: {r.total_distance}km</li>)}
            </ul>
          </div>
        </div>
      </main>
    </div>
  );
}
